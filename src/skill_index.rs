//! SKILL-03 (WP-19): the public skills index is fetched by the Core through the broker and kept as the import index.
//!
//! The request is a keyless GET over https to `raw.githubusercontent.com` (the broker's public read allowlist).
//! The Core never fetches anything else. The body is capped at 64 KiB and must pass `skills::parse_index` before it
//! replaces `<data>/skill-imports/index.json`; a refused body leaves the local index untouched. The exchange runs on
//! its own thread with a small runtime, so the request loop never waits for the network.
//!
//! Test only: a loopback `http://127.0.0.1:PORT` base, accepted only with `--net-allow-loopback` (gate
//! scripts/verify_wp19_skills.py). No package path sets it.
use crate::{
    broker,
    skills::{parse_index, IMPORT_DIR, INDEX_FILE},
    transport::data_dir,
};
use std::{
    fs::{self, OpenOptions},
    io::{self, Write},
    os::unix::fs::{DirBuilderExt, OpenOptionsExt},
    path::{Path, PathBuf},
    sync::mpsc,
    time::Duration,
};
use tokio::io::BufReader;

/// Production base. The index lives at the owner's repository `main` branch (`skills-index.json`).
pub const INDEX_BASE: &str = "https://raw.githubusercontent.com";
pub const INDEX_PATH: &str = "/LQ13ofc/Gideon2/main/skills-index.json";
const INDEX_HOST: &str = "raw.githubusercontent.com";
pub const MAX_INDEX_BYTES: usize = 64 * 1024;
const TIMEOUT_S: u64 = 20;
const FILE_TMP: &str = "index.json.tmp";

/// One fetch in flight. `poll` returns the result once the thread has finished.
pub struct Fetch {
    rx: mpsc::Receiver<Result<Vec<u8>, &'static str>>,
}

impl Fetch {
    /// `None` while the fetch runs; a dead thread is reported as `unavailable`.
    pub fn poll(&self) -> Option<Result<Vec<u8>, &'static str>> {
        match self.rx.try_recv() {
            Ok(result) => Some(result),
            Err(mpsc::TryRecvError::Empty) => None,
            Err(mpsc::TryRecvError::Disconnected) => Some(Err("unavailable")),
        }
    }
}

/// Starts one fetch of the index from `base` through the broker (`python` runs `script`).
pub fn start(base: String, python: PathBuf, script: PathBuf) -> Fetch {
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let _ = tx.send(fetch(&base, &python, &script));
    });
    Fetch { rx }
}

/// Destination of the index request. Production: https to the raw host, no loopback. Test: loopback http only.
pub(crate) fn target_for(base: &str) -> Result<broker::Target, &'static str> {
    let (https, rest) = if let Some(rest) = base.strip_prefix("https://") {
        (true, rest)
    } else if let Some(rest) = base.strip_prefix("http://") {
        (false, rest)
    } else {
        return Err("invalid_input");
    };
    let host = rest
        .split('/')
        .next()
        .unwrap_or("")
        .split(':')
        .next()
        .unwrap_or("");
    let loopback = host == "127.0.0.1";
    let allowed = (https && host == INDEX_HOST) || (!https && loopback);
    if !allowed {
        return Err("invalid_input");
    }
    Ok(broker::Target {
        url: format!("{base}{INDEX_PATH}"),
        host: host.to_owned(),
        https,
        loopback,
        keyless: true,
        anthropic: false,
    })
}

fn fetch(base: &str, python: &Path, script: &Path) -> Result<Vec<u8>, &'static str> {
    let target = target_for(base)?;
    let headers = [
        ("User-Agent", "Gideon-Core".to_owned()),
        ("Accept", "application/json".to_owned()),
    ];
    let payload = broker::request_payload(&target, "GET", &headers, "", None, TIMEOUT_S)
        .map_err(|_| "unavailable")?;
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|_| "unavailable")?;
    runtime.block_on(async {
        // The same process budget the connection exchanges use (sandbox NPROC headroom for bwrap and the broker).
        let processes = tokio::task::spawn_blocking(crate::plugins::process_budget)
            .await
            .map_err(|_| "unavailable")?;
        let mut command = broker::command(python, script, processes).map_err(|_| "unavailable")?;
        let mut child = command.spawn().map_err(|_| "unavailable")?;
        let (Some(mut stdin), Some(stdout)) = (child.stdin.take(), child.stdout.take()) else {
            return Err("unavailable");
        };
        broker::write_payload(&mut stdin, &payload)
            .await
            .map_err(|_| "unavailable")?;
        drop(stdin);
        let mut reader = BufReader::new(stdout);
        let mut body = Vec::new();
        loop {
            let parsed = tokio::time::timeout(
                Duration::from_secs(TIMEOUT_S + 5),
                broker::read_parsed(&mut reader),
            )
            .await
            .map_err(|_| "timeout")?;
            match parsed.reply {
                broker::Reply::Chunk(text) => {
                    if body.len() + text.len() > MAX_INDEX_BYTES {
                        return Err("response_too_large");
                    }
                    body.extend_from_slice(text.as_bytes());
                }
                broker::Reply::Done(_) => return Ok(body),
                broker::Reply::Error(code, _) => return Err(code),
                broker::Reply::Closed => return Err("provider_unreachable"),
            }
        }
    })
}

/// Validates a fetched body and, only when it is a valid index, replaces the local import index (0600, atomic).
pub fn finish(result: Result<Vec<u8>, &'static str>) -> Result<(), &'static str> {
    let bytes = result?;
    if bytes.len() > MAX_INDEX_BYTES {
        return Err("response_too_large");
    }
    parse_index(&bytes)?;
    save(&bytes)
}

fn save(bytes: &[u8]) -> Result<(), &'static str> {
    let dir = data_dir().join(IMPORT_DIR);
    match fs::symlink_metadata(&dir) {
        Ok(meta) if meta.file_type().is_symlink() || !meta.is_dir() => return Err("unavailable"),
        Ok(_) => {}
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            fs::DirBuilder::new()
                .mode(0o700)
                .create(&dir)
                .map_err(|_| "unavailable")?;
        }
        Err(_) => return Err("unavailable"),
    }
    let tmp = dir.join(FILE_TMP);
    // A leftover temporary file from an interrupted save is replaced; a symlink there is removed, never followed.
    let _ = fs::remove_file(&tmp);
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&tmp)
        .map_err(|_| "unavailable")?;
    file.write_all(bytes)
        .and_then(|()| file.sync_all())
        .map_err(|_| "unavailable")?;
    drop(file);
    fs::rename(&tmp, dir.join(INDEX_FILE)).map_err(|_| "unavailable")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_the_raw_host_over_https_or_loopback_http_is_a_destination() {
        let ok = target_for(INDEX_BASE).unwrap();
        assert_eq!(ok.host, INDEX_HOST);
        assert!(ok.https && !ok.loopback && ok.keyless);
        assert_eq!(ok.url, format!("{INDEX_BASE}{INDEX_PATH}"));
        let fake = target_for("http://127.0.0.1:8080").unwrap();
        assert!(!fake.https && fake.loopback);
        for base in [
            "http://raw.githubusercontent.com",
            "https://github.com",
            "https://evil.example",
            "http://10.0.0.5:80",
            "ftp://127.0.0.1",
            "https://raw.githubusercontent.com.evil.example",
        ] {
            assert_eq!(target_for(base).err(), Some("invalid_input"), "{base}");
        }
    }

    #[test]
    fn a_refused_body_never_reaches_the_local_index() {
        assert_eq!(finish(Err("http_error")), Err("http_error"));
        assert_eq!(finish(Ok(b"not json".to_vec())), Err("invalid_import"));
        assert!(finish(Ok(vec![b' '; MAX_INDEX_BYTES + 1])).is_err());
    }
}
