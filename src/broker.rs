//! C1 Core-brokered HTTP. The Core checks the target allowlist before any process exists, then
//! runs `scripts/net_broker.py` under bwrap with a shared network namespace and no repo, home or
//! user data. The key travels on the broker's second stdin line, never argv or env.
use crate::{
    llmcfg::{self, HostAuth, Provider},
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

/// Resolved, allowlisted destination. `url` is what the broker requests.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Target {
    pub url: String,
    pub host: String,
    pub https: bool,
    pub loopback: bool,
}

/// Fixed hosts for built-in providers; `custom` takes the configured URL (re-validated here).
pub fn target(auth: &HostAuth) -> Result<Target, &'static str> {
    let provider = auth.provider.ok_or("provider_not_configured")?;
    let base = match provider {
        Provider::Custom => auth
            .custom_url
            .as_deref()
            .ok_or("provider_not_configured")?
            .to_owned(),
        fixed => fixed.fixed_base().ok_or("host_not_allowed")?.to_owned(),
    };
    let endpoint =
        llmcfg::parse_endpoint(&base, auth.allow_loopback).map_err(|_| "host_not_allowed")?;
    let fixed_host = match provider {
        Provider::Openrouter => Some("openrouter.ai"),
        Provider::Opencode => Some("opencode.ai"),
        Provider::Google => Some("generativelanguage.googleapis.com"),
        Provider::Custom => None,
    };
    if fixed_host.is_some_and(|host| host != endpoint.host) {
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
    })
}

/// Request line and secret line for the broker. The caller has already set the Core's `model`
/// and `stream: true` on the body and never passes plugin headers: the broker builds its own.
pub struct Payload {
    pub line: Vec<u8>,
    pub key_line: Vec<u8>,
}

pub fn payload(
    target: &Target,
    body: &serde_json::Value,
    auth: &HostAuth,
) -> Result<Payload, &'static str> {
    let key = auth.key.as_deref().ok_or("key_missing")?;
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
        "allow_http": !target.https && target.loopback && auth.allow_loopback,
        "allow_loopback": auth.allow_loopback,
    });
    let mut line = serde_json::to_vec(&request).map_err(|_| "invalid_host_call")?;
    line.push(b'\n');
    let mut key_line =
        serde_json::to_vec(&serde_json::json!({"key": key})).map_err(|_| "invalid_host_call")?;
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

    fn auth(provider: Provider, url: Option<&str>, loopback: bool) -> HostAuth {
        HostAuth {
            permission: true,
            provider: Some(provider),
            model: Some("m".into()),
            custom_url: url.map(str::to_owned),
            key: Some("fake-key-0123456789".into()),
            cloud_consent: true,
            allow_loopback: loopback,
        }
    }

    #[test]
    fn fixed_providers_resolve_only_to_their_hosts() {
        let t = target(&auth(Provider::Google, None, false)).unwrap();
        assert_eq!(
            t.url,
            "https://generativelanguage.googleapis.com:443/v1beta/openai/chat/completions"
        );
        assert_eq!(t.host, "generativelanguage.googleapis.com");
        assert_eq!(
            target(&auth(Provider::Openrouter, None, false))
                .unwrap()
                .host,
            "openrouter.ai"
        );
        assert_eq!(
            target(&auth(Provider::Opencode, None, false)).unwrap().url,
            "https://opencode.ai:443/zen/v1/chat/completions"
        );
    }

    #[test]
    fn custom_targets_need_https_or_flagged_loopback() {
        assert!(target(&auth(
            Provider::Custom,
            Some("https://api.example.com/v1"),
            false
        ))
        .is_ok());
        assert!(target(&auth(
            Provider::Custom,
            Some("http://api.example.com/v1"),
            false
        ))
        .is_err());
        assert!(target(&auth(
            Provider::Custom,
            Some("https://93.184.216.34/v1"),
            false
        ))
        .is_err());
        assert!(target(&auth(
            Provider::Custom,
            Some("http://127.0.0.1:8/v1"),
            false
        ))
        .is_err());
        let loopback =
            target(&auth(Provider::Custom, Some("http://127.0.0.1:8/v1"), true)).unwrap();
        assert!(loopback.loopback && !loopback.https);
        assert_eq!(loopback.url, "http://127.0.0.1:8/v1/chat/completions");
    }

    #[test]
    fn payload_carries_key_only_on_second_line() {
        let a = auth(Provider::Custom, Some("http://127.0.0.1:8/v1"), true);
        let t = target(&a).unwrap();
        let p = payload(&t, &serde_json::json!({"model": "m"}), &a).unwrap();
        let first = String::from_utf8(p.line.clone()).unwrap();
        assert!(!first.contains("fake-key-0123456789"));
        assert!(String::from_utf8(p.key_line.clone())
            .unwrap()
            .contains("fake-key-0123456789"));
        let no_key = HostAuth { key: None, ..a };
        assert_eq!(
            payload(&t, &serde_json::json!({}), &no_key).err(),
            Some("key_missing")
        );
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
