//! C1 Core-brokered HTTP. The Core checks the target allowlist before any process exists, then
//! runs `scripts/net_broker.py` under bwrap with a shared network namespace and no repo, home or
//! user data. The key travels on the broker's second stdin line, never argv or env.
use crate::{
    llmcfg::{self, Provider, ProviderId, Route, LOCAL_HOST, MIN_LOCAL_PORT},
    transport::bounded_frame,
};
use serde::Deserialize;
use std::{
    fs,
    io::{self},
    path::Path,
    process::Stdio,
    time::Duration,
};
use tokio::{
    io::{AsyncWriteExt, BufReader},
    process::{ChildStdout, Command},
    sync::mpsc,
};

pub const CHAT_PATH: &str = "/chat/completions";
pub const MAX_BODY: usize = 256 * 1024;
pub const MAX_RESPONSE: usize = 4 * 1024 * 1024;
pub const DEADLINE: Duration = Duration::from_secs(120);
const MAX_BROKER_LINE: usize = 256 * 1024;
const MAX_CHUNK_CHARS: usize = 16384;
const BROKER_IN_SANDBOX: &str = "/broker/net_broker.py";

/// Resolved, allowlisted destination. `url` is what the broker requests. `keyless` targets are
/// loopback-only local providers: the broker sends no Authorization header to them.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Target {
    pub url: String,
    pub host: String,
    pub https: bool,
    pub loopback: bool,
    pub keyless: bool,
}

/// Fixed host of a built-in cloud provider; `custom` has none and is checked against its URL.
fn fixed_host(provider: Provider) -> Option<&'static str> {
    match provider {
        Provider::Openrouter => Some("openrouter.ai"),
        Provider::Opencode => Some("opencode.ai"),
        Provider::Google => Some("generativelanguage.googleapis.com"),
        Provider::Custom => None,
    }
}

/// Resolves a route to its allowlisted destination. Local routes are always loopback-only and
/// never resolve names; `allow_loopback` (test mode) only opens loopback for `custom`.
pub fn target(route: &Route, allow_loopback: bool) -> Result<Target, &'static str> {
    let (base, fixed, allow) = match route.provider {
        ProviderId::Cloud(Provider::Custom) => (
            route.custom_url.clone().ok_or("provider_not_configured")?,
            None,
            allow_loopback,
        ),
        ProviderId::Cloud(provider) => (
            provider.fixed_base().ok_or("host_not_allowed")?.to_owned(),
            fixed_host(provider),
            allow_loopback,
        ),
        ProviderId::Local | ProviderId::Ollama => (
            llmcfg::local_base(route.local_port.ok_or("provider_not_configured")?),
            Some(LOCAL_HOST),
            true,
        ),
    };
    let endpoint = llmcfg::parse_endpoint(&base, allow).map_err(|_| "host_not_allowed")?;
    if fixed.is_some_and(|host| host != endpoint.host) {
        return Err("host_not_allowed");
    }
    if route.provider.is_local() && endpoint.port < MIN_LOCAL_PORT {
        return Err("host_not_allowed");
    }
    let scheme = if endpoint.https { "https" } else { "http" };
    let authority = if endpoint.host.contains(':') {
        format!("[{}]:{}", endpoint.host, endpoint.port)
    } else {
        format!("{}:{}", endpoint.host, endpoint.port)
    };
    Ok(Target {
        url: format!("{scheme}://{authority}{}{CHAT_PATH}", endpoint.path),
        host: endpoint.host,
        https: endpoint.https,
        loopback: endpoint.loopback,
        keyless: route.provider.is_local(),
    })
}

/// Request line and secret line for the broker. The caller has already set the Core's `model`
/// and `stream: true` on the body and never passes plugin headers: the broker builds its own.
pub struct Payload {
    pub line: Vec<u8>,
    pub key_line: Vec<u8>,
}

/// `key` is `None` only for keyless (local) targets, which send `{"key": null}`; a cloud target
/// without a key is refused before any request line is built.
pub fn payload(
    target: &Target,
    body: &serde_json::Value,
    key: Option<&str>,
) -> Result<Payload, &'static str> {
    let body_text = serde_json::to_string(body).map_err(|_| "invalid_host_call")?;
    if body_text.len() > MAX_BODY {
        return Err("invalid_host_call");
    }
    let request = serde_json::json!({
        "url": target.url,
        "method": "POST",
        "headers": {"Content-Type": "application/json", "Accept": "text/event-stream"},
        "body": body_text,
        "timeout_s": DEADLINE.as_secs(),
        "expected_host": target.host,
        "allow_http": !target.https && target.loopback,
        "allow_loopback": target.loopback,
    });
    let mut line = serde_json::to_vec(&request).map_err(|_| "invalid_host_call")?;
    line.push(b'\n');
    let key_value = match (key, target.keyless) {
        (Some(key), _) => serde_json::json!({"key": key}),
        (None, true) => serde_json::json!({"key": null}),
        (None, false) => return Err("key_missing"),
    };
    let mut key_line = serde_json::to_vec(&key_value).map_err(|_| "invalid_host_call")?;
    key_line.push(b'\n');
    Ok(Payload { line, key_line })
}

/// Sandboxed broker command: prlimit, then bwrap with a shared network namespace only.
pub(crate) fn command(python: &Path, script: &Path, processes: u64) -> io::Result<Command> {
    if !python.is_absolute() || !script.is_absolute() || !script.is_file() {
        return Err(io::Error::other("absolute broker paths required"));
    }
    let interpreter = crate::plugins::resolve_interpreter(python);
    let runtime = interpreter
        .parent()
        .and_then(Path::parent)
        .ok_or_else(|| io::Error::other("python runtime missing"))?;
    let canonical = fs::canonicalize(runtime)?;
    let mut command = Command::new(crate::plugins::PRLIMIT);
    command
        .env_clear()
        .arg(format!("--as={}", crate::plugins::MAX_ADDRESS_SPACE))
        .arg(format!("--cpu={}", crate::plugins::MAX_CPU_SECONDS))
        .arg(format!("--nofile={}", crate::plugins::MAX_OPEN_FILES))
        .arg(format!("--nproc={processes}"))
        .arg("--")
        .arg(crate::plugins::BWRAP)
        .args([
            "--unshare-all",
            "--share-net",
            "--die-with-parent",
            "--new-session",
            "--clearenv",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib",
            "/lib64",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--ro-bind-try",
            "/etc/resolv.conf",
            "/etc/resolv.conf",
            "--ro-bind-try",
            "/etc/hosts",
            "/etc/hosts",
            "--ro-bind-try",
            "/etc/nsswitch.conf",
            "/etc/nsswitch.conf",
            "--ro-bind-try",
            "/etc/ssl",
            "/etc/ssl",
            "--ro-bind-try",
            "/etc/ca-certificates",
            "/etc/ca-certificates",
        ])
        .arg("--ro-bind")
        .arg(&canonical)
        .arg(&canonical)
        .arg("--ro-bind")
        .arg(runtime)
        .arg(runtime)
        .arg("--ro-bind")
        .arg(script)
        .arg(BROKER_IN_SANDBOX)
        .args(["--remount-ro", "/", "--chdir", "/tmp", "--"])
        .arg(&interpreter)
        .args(["-I", BROKER_IN_SANDBOX])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .kill_on_drop(true);
    Ok(command)
}

/// One decoded line from the broker. `Closed` means EOF or an unreadable stream.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Reply {
    Chunk(String),
    Done(u16),
    Error(&'static str, Option<u16>),
    Closed,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Line {
    #[serde(default)]
    chunk: Option<String>,
    #[serde(default)]
    done: Option<bool>,
    #[serde(default)]
    status: Option<u16>,
    #[serde(default)]
    error: Option<String>,
}

fn code(name: &str) -> &'static str {
    match name {
        "timeout" => "timeout",
        "http_error" => "http_error",
        "redirect_refused" => "redirect_refused",
        "response_too_large" => "response_too_large",
        "host_not_allowed" => "host_not_allowed",
        _ => "network_unavailable",
    }
}

/// Strict: exactly one of chunk / done+2xx status / error. Anything else is a broker failure.
pub(crate) fn parse(bytes: &[u8]) -> Reply {
    let Ok(line) = serde_json::from_slice::<Line>(bytes) else {
        return Reply::Error("network_unavailable", None);
    };
    match (line.chunk, line.done, line.status, line.error) {
        (Some(text), None, None, None) if text.chars().count() <= MAX_CHUNK_CHARS => {
            Reply::Chunk(text)
        }
        (None, Some(true), Some(status), None) if (200..300).contains(&status) => {
            Reply::Done(status)
        }
        (None, None, status, Some(name)) => Reply::Error(code(&name), status),
        _ => Reply::Error("network_unavailable", None),
    }
}

/// Reads broker lines until a terminal line, EOF or a violation; no line is ever trusted raw.
pub(crate) async fn read_replies(stdout: ChildStdout, tx: mpsc::UnboundedSender<Reply>) {
    let mut reader = BufReader::new(stdout);
    loop {
        let reply = match bounded_frame(&mut reader, MAX_BROKER_LINE).await {
            Ok(Some(bytes)) => parse(&bytes),
            Ok(None) | Err(_) => Reply::Closed,
        };
        let terminal = !matches!(reply, Reply::Chunk(_));
        if tx.send(reply).is_err() || terminal {
            return;
        }
    }
}

/// Writes the two broker input lines; the caller closes stdin by dropping it.
pub(crate) async fn write_payload(
    stdin: &mut tokio::process::ChildStdin,
    payload: &Payload,
) -> io::Result<()> {
    stdin.write_all(&payload.line).await?;
    stdin.write_all(&payload.key_line).await?;
    stdin.flush().await
}

#[cfg(test)]
mod tests {
    use super::*;

    const FAKE: &str = "fake-key-0123456789";

    fn route(provider: &str, url: Option<&str>, port: Option<u16>) -> Route {
        let parsed = ProviderId::parse(provider).unwrap();
        Route {
            provider: parsed,
            model: "m".into(),
            custom_url: url.map(str::to_owned),
            local_port: port,
        }
    }

    #[test]
    fn fixed_providers_resolve_only_to_their_hosts() {
        let t = target(&route("google", None, None), false).unwrap();
        assert_eq!(
            t.url,
            "https://generativelanguage.googleapis.com:443/v1beta/openai/chat/completions"
        );
        assert_eq!(t.host, "generativelanguage.googleapis.com");
        assert!(!t.keyless);
        assert_eq!(
            target(&route("openrouter", None, None), false)
                .unwrap()
                .host,
            "openrouter.ai"
        );
        assert_eq!(
            target(&route("opencode", None, None), false).unwrap().url,
            "https://opencode.ai:443/zen/v1/chat/completions"
        );
    }

    #[test]
    fn custom_targets_need_https_or_flagged_loopback() {
        assert!(target(
            &route("custom", Some("https://api.example.com/v1"), None),
            false
        )
        .is_ok());
        assert!(target(
            &route("custom", Some("http://api.example.com/v1"), None),
            false
        )
        .is_err());
        assert!(target(
            &route("custom", Some("https://93.184.216.34/v1"), None),
            false
        )
        .is_err());
        assert!(target(&route("custom", Some("http://127.0.0.1:8/v1"), None), false).is_err());
        let loopback = target(&route("custom", Some("http://127.0.0.1:8/v1"), None), true).unwrap();
        assert!(loopback.loopback && !loopback.https && !loopback.keyless);
        assert_eq!(loopback.url, "http://127.0.0.1:8/v1/chat/completions");
    }

    #[test]
    fn local_targets_are_keyless_loopback_literals_without_consent_flag() {
        let t = target(&route("local", None, Some(8080)), false).unwrap();
        assert_eq!(t.url, "http://127.0.0.1:8080/v1/chat/completions");
        assert_eq!(t.host, "127.0.0.1");
        assert!(t.loopback && t.keyless && !t.https);
        let ollama = target(&route("ollama", None, Some(11434)), false).unwrap();
        assert_eq!(ollama.url, "http://127.0.0.1:11434/v1/chat/completions");
        assert_eq!(
            target(&route("local", None, Some(80)), false),
            Err("host_not_allowed")
        );
        assert_eq!(
            target(&route("local", None, None), false),
            Err("provider_not_configured")
        );
    }

    #[test]
    fn payload_carries_key_only_on_second_line() {
        let t = target(&route("custom", Some("http://127.0.0.1:8/v1"), None), true).unwrap();
        let p = payload(&t, &serde_json::json!({"model": "m"}), Some(FAKE)).unwrap();
        let first = String::from_utf8(p.line.clone()).unwrap();
        assert!(!first.contains(FAKE));
        assert!(String::from_utf8(p.key_line.clone())
            .unwrap()
            .contains(FAKE));
        assert_eq!(
            payload(&t, &serde_json::json!({}), None).err(),
            Some("key_missing")
        );
    }

    #[test]
    fn keyless_payload_sends_null_key_and_never_a_key() {
        let t = target(&route("ollama", None, Some(11434)), false).unwrap();
        let p = payload(&t, &serde_json::json!({"model": "m"}), None).unwrap();
        assert_eq!(String::from_utf8(p.key_line).unwrap(), "{\"key\":null}\n");
        let request: serde_json::Value = serde_json::from_slice(&p.line).unwrap();
        assert_eq!(request["allow_http"], true);
        assert_eq!(request["allow_loopback"], true);
        assert_eq!(request["expected_host"], "127.0.0.1");
    }

    #[test]
    fn broker_lines_are_strict_and_codes_are_closed() {
        assert_eq!(parse(br#"{"chunk":"hi"}"#), Reply::Chunk("hi".into()));
        assert_eq!(parse(br#"{"done":true,"status":200}"#), Reply::Done(200));
        assert_eq!(
            parse(br#"{"error":"http_error","status":401}"#),
            Reply::Error("http_error", Some(401))
        );
        assert_eq!(
            parse(br#"{"error":"free text with secrets"}"#),
            Reply::Error("network_unavailable", None)
        );
        assert_eq!(
            parse(br#"{"done":true,"status":302}"#),
            Reply::Error("network_unavailable", None)
        );
        assert_eq!(
            parse(br#"{"chunk":"x","extra":1}"#),
            Reply::Error("network_unavailable", None)
        );
        assert_eq!(parse(b"garbage"), Reply::Error("network_unavailable", None));
    }
}
