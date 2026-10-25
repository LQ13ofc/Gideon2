//! Deterministic final-only commands and explicitly scoped sandbox authority.
use serde::{Deserialize, Serialize};
use std::{io, process::Stdio, time::Duration};
use tokio::io::{AsyncWriteExt, BufReader};

pub const BRAVE: &str = "com.brave.Browser.desktop";
pub const STEAM: &str = "com.valvesoftware.Steam.desktop";
pub const KCALC: &str = "org.kde.kcalc.desktop";
/// The fixed host catalog (A11). Only these canonical ids reach the host launcher; `host::resolve` finds the
/// installed desktop entry of each (aliases such as `brave-browser.desktop` included).
pub const HOST_APPS: [&str; 3] = [BRAVE, STEAM, KCALC];
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Command {
    OpenApp {
        desktop_id: String,
    },
    Volume {
        level: u8,
    },
    Mute,
    /// Real-actions only (A11): the sandbox executor has no unmute or volume steps.
    Unmute,
    VolumeUp,
    VolumeDown,
    Status,
    Time,
    Date,
    Cancel,
}
impl Command {
    /// Wire name of the command kind (the bridge's `COMMAND_KINDS` names).
    pub fn kind(&self) -> &'static str {
        match self {
            Command::OpenApp { .. } => "open_app",
            Command::Volume { .. } => "volume",
            Command::Mute => "mute",
            Command::Unmute => "unmute",
            Command::VolumeUp => "volume_up",
            Command::VolumeDown => "volume_down",
            Command::Status => "status",
            Command::Time => "time",
            Command::Date => "date",
            Command::Cancel => "cancel",
        }
    }
    /// Commands that change the host (A11): executed on the host only while `real_actions` is on.
    pub fn host_action(&self) -> bool {
        matches!(
            self,
            Command::OpenApp { .. }
                | Command::Volume { .. }
                | Command::Mute
                | Command::Unmute
                | Command::VolumeUp
                | Command::VolumeDown
        )
    }
    /// Commands the sandbox grammar never runs: they exist only with `real_actions`.
    pub fn real_only(&self) -> bool {
        matches!(
            self,
            Command::Unmute | Command::VolumeUp | Command::VolumeDown
        )
    }
}
/// Short label of a catalog app for receipts and the state line (no path, no shell text).
pub fn app_label(desktop_id: &str) -> &'static str {
    match desktop_id {
        BRAVE => "brave",
        STEAM => "steam",
        KCALC => "kcalc",
        _ => "app",
    }
}
/// Real-action record of the last host action (A11). Content-free: no paths, no receipt text.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct LastAction {
    pub kind: &'static str,
    pub app: Option<&'static str>,
    pub ok: bool,
    pub verified: bool,
    pub at_ms: u64,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct RealView {
    pub enabled: bool,
    pub last_action: Option<LastAction>,
}
/// Snapshot block `actions` (A11).
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ActionsView {
    pub real: RealView,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Job {
    pub session_id: u64,
    pub command: Command,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    pub job: Job,
    pub verified: bool,
    pub scope: String,
    pub result: String,
}
#[derive(Clone, Debug, Serialize)]
pub struct Outcome {
    pub session_id: u64,
    pub code: &'static str,
    pub receipt: Option<Receipt>,
}
/// STT often writes the wake word with a comma after its first word ("Hey, Gideon, open brave.").
/// That single comma is read as a space so the wake prefix matches; every other comma keeps the
/// exact grammar ("open, brave" is still refused).
fn unify_wake_comma(text: &str, prefix: &str) -> String {
    if let Some((first, _)) = prefix.split_once(' ') {
        if let Some(rest) = text
            .strip_prefix(first)
            .and_then(|tail| tail.strip_prefix(", "))
        {
            return format!("{first} {rest}");
        }
    }
    text.to_string()
}

/// Spellings STT writes for the wake name (WP-7b, measured on the PT/FR and EN lab clips: "Gedon", "Lagdon",
/// "Gidon", "Gidéon"). Only a listed spelling is accepted, and only in the name slot of the wake phrase.
pub const WAKE_NAME_VARIANTS: [&str; 6] =
    ["gideon", "gedon", "gidon", "lagdon", "gidéon", "gédéon"];

/// Replaces a listed spelling of the wake name with the canonical name, when it sits in the name slot of
/// the wake phrase ("hey lagdon, mute" -> "hey gideon, mute"). Any other word ("Gideonish") is left as is.
fn unify_wake_name(text: &str, prefix: &str) -> String {
    let (head, name) = match prefix.rsplit_once(' ') {
        Some((head, name)) => (format!("{head} "), name),
        None => (String::new(), prefix),
    };
    if name != "gideon" {
        return text.to_string();
    }
    let Some(rest) = text.strip_prefix(head.as_str()) else {
        return text.to_string();
    };
    let end = rest.find([' ', ',', '.', '?']).unwrap_or(rest.len());
    if WAKE_NAME_VARIANTS.contains(&&rest[..end]) {
        return format!("{head}{name}{}", &rest[end..]);
    }
    text.to_string()
}

/// Full-string grammar: no substring extraction, fuzzy names, or chained commands.
pub fn parse(raw: &str, wake: &str) -> Option<Command> {
    let normalized = raw
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase();
    let prefix = wake.to_lowercase();
    let unified = unify_wake_name(&unify_wake_comma(&normalized, &prefix), &prefix);
    let mut text = unified.as_str();
    if !prefix.is_empty() {
        if let Some(tail) = text.strip_prefix(&prefix) {
            // Only a token boundary can remove wake; never remove arbitrary leading text.
            if tail.starts_with(',') || tail.starts_with(' ') {
                text = tail.trim_start_matches(',').trim_start();
            }
        }
    }
    text = text
        .strip_suffix('.')
        .or_else(|| text.strip_suffix('?'))
        .unwrap_or(text);
    match text {
        "open brave" | "abra brave" | "abre o brave" | "abra o brave" => Some(Command::OpenApp {
            desktop_id: BRAVE.into(),
        }),
        "open steam" | "abra steam" => Some(Command::OpenApp {
            desktop_id: STEAM.into(),
        }),
        "open kcalc" | "abra kcalc" | "open calculator" => Some(Command::OpenApp {
            desktop_id: KCALC.into(),
        }),
        "mute" | "mute audio" | "silenciar" => Some(Command::Mute),
        "unmute" | "unmute audio" | "desmutar" => Some(Command::Unmute),
        "volume up" | "aumentar volume" => Some(Command::VolumeUp),
        "volume down" | "diminuir volume" => Some(Command::VolumeDown),
        "status" | "what is your status" => Some(Command::Status),
        "what time is it" | "que horas são" => Some(Command::Time),
        "what is the date" | "qual é a data" => Some(Command::Date),
        "cancel" | "cancelar" => Some(Command::Cancel),
        _ => {
            let level = text
                .strip_prefix("set volume to ")
                .or_else(|| text.strip_prefix("volume "))?;
            if level.is_empty() || level.len() > 3 || !level.bytes().all(|b| b.is_ascii_digit()) {
                return None;
            }
            let level: u8 = level.parse().ok()?;
            (level <= 100).then_some(Command::Volume { level })
        }
    }
}
/// Actor-owned grant for the sandbox executor; cannot be supplied through IPC or a transcript.
pub fn authorize(command: &Command) -> Result<(), &'static str> {
    match command {
        Command::OpenApp { desktop_id } if desktop_id != BRAVE => Err("app_unavailable"),
        Command::Volume { level } if *level > 100 => Err("denied"),
        // Second line of defence: the dispatch filter already keeps these out of the sandbox.
        command if command.real_only() => Err("unsupported"),
        _ => Ok(()),
    }
}
/// Grant for the host executor (A11, `real_actions` on): the fixed catalog and the 0-100% volume range.
pub fn authorize_host(command: &Command) -> Result<(), &'static str> {
    match command {
        Command::OpenApp { desktop_id } if !HOST_APPS.contains(&desktop_id.as_str()) => {
            Err("app_unavailable")
        }
        Command::Volume { level } if *level > 100 => Err("denied"),
        _ => Ok(()),
    }
}
/// Trusted executor verifies the effect (sandbox worker or host verification); Rust validates identity and scope again.
pub fn verify(job: &Job, receipt: &Receipt) -> bool {
    receipt.job == *job
        && receipt.verified
        && matches!(receipt.scope.as_str(), "sandbox" | "host")
        && !receipt.result.is_empty()
        && receipt.result.len() <= 256
        && !receipt.result.chars().any(char::is_control)
}
/// Runs one job on the host when `host` is set (A11 `real_actions`) and the command changes the host; every
/// other job keeps the sandbox executor. Errors are fixed codes for the Core (`command_error`).
pub async fn execute_for(job: Job, host: bool) -> Result<Receipt, &'static str> {
    if host && job.command.host_action() {
        execute_host(job).await
    } else {
        execute(job).await.map_err(|_| "command_failed")
    }
}
/// Host executor (A11). Launch and volume effects are checked by `crate::host`; a receipt exists only when the
/// effect was observed (process seen, or the volume read back at the requested value).
pub async fn execute_host(job: Job) -> Result<Receipt, &'static str> {
    authorize_host(&job.command)?;
    let result = match &job.command {
        Command::OpenApp { desktop_id } => crate::host::open_app(desktop_id).await?,
        command @ (Command::Volume { .. }
        | Command::Mute
        | Command::Unmute
        | Command::VolumeUp
        | Command::VolumeDown) => crate::host::volume(command).await?,
        _ => return Err("unsupported"),
    };
    Ok(Receipt {
        job,
        verified: true,
        scope: "host".into(),
        result,
    })
}
pub async fn execute(job: Job) -> io::Result<Receipt> {
    authorize(&job.command).map_err(io::Error::other)?;
    let mut command = crate::transport::namespace_command(
        std::path::Path::new("/usr/bin/python3"),
        "scripts/command_worker.py",
        &[],
        &[],
    )?;
    // A clean environment also prevents ambient Python/credential settings from leaking.
    command
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .stdin(Stdio::piped());
    let mut child = command.spawn()?;
    let result = tokio::time::timeout(Duration::from_secs(2), async {
        let mut input = child
            .stdin
            .take()
            .ok_or_else(|| io::Error::other("stdin"))?;
        input.write_all(&serde_json::to_vec(&job)?).await?;
        input.write_all(b"\n").await?;
        drop(input);
        let mut output = BufReader::new(
            child
                .stdout
                .take()
                .ok_or_else(|| io::Error::other("stdout"))?,
        );
        let line = crate::transport::bounded_frame(&mut output, 4096)
            .await?
            .ok_or_else(|| io::Error::other("receipt missing"))?;
        let receipt: Receipt = serde_json::from_slice(&line)?;
        if crate::transport::bounded_frame(&mut output, 4096)
            .await?
            .is_some()
            || !child.wait().await?.success()
            || !verify(&job, &receipt)
        {
            return Err(io::Error::other("unverified effect"));
        }
        Ok(receipt)
    })
    .await;
    match result {
        Ok(Ok(receipt)) => Ok(receipt),
        _ => {
            let _ = child.kill().await;
            let _ = child.wait().await;
            Err(io::Error::other("executor failed"))
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_grammar_has_no_unintended_actions() {
        for text in [
            "don't open brave",
            "do not open brave",
            "não abra brave",
            "if I say open brave",
            "maybe open brave",
            "open brave and mute",
            "open brave; reboot",
            "open brave\nrm -rf /",
            "open brave please",
            "Hey Gideon, don't open brave",
            "what does open brave mean",
            "open Brave.exe",
            "set volume to 101",
            "volume -1",
            "volume 50.0",
            "volume 999",
            "open braves",
            "Hey Gideonish open brave",
            "Okay Gideon, open brave",
            "",
            "brave",
            "close firefox",
            "open brave??",
        ] {
            assert!(parse(text, "Hey Gideon").is_none(), "{text}");
        }
        assert_eq!(
            parse("Hey Gideon, open Brave.", "Hey Gideon"),
            Some(Command::OpenApp {
                desktop_id: BRAVE.into()
            })
        );
        assert_eq!(
            parse("Okay Gideon, open Brave.", "Okay Gideon"),
            parse("open brave", "")
        );
        assert_eq!(
            parse("Custom Phrase, volume 50.", "Custom Phrase"),
            Some(Command::Volume { level: 50 })
        );
        assert_eq!(parse("mute", ""), Some(Command::Mute));
        assert_eq!(parse("que horas são?", ""), Some(Command::Time));
        assert!(authorize(&Command::OpenApp {
            desktop_id: "../../bin/sh".into()
        })
        .is_err());
        assert!(authorize(&Command::Volume { level: 255 }).is_err());
    }
    #[test]
    fn stt_comma_after_wake_word_is_the_only_comma_accepted() {
        assert_eq!(
            parse("Hey, Gideon, open brave.", "Hey Gideon"),
            Some(Command::OpenApp {
                desktop_id: BRAVE.into()
            })
        );
        assert_eq!(
            parse("Hey, Gideon. Mute.", "Hey Gideon"),
            None,
            "a period after the wake word is not the STT comma"
        );
        assert_eq!(
            parse("Hey, Gideon, mute.", "Hey Gideon"),
            Some(Command::Mute)
        );
        assert_eq!(
            parse("Hey, Gideon, what time is it?", "Hey Gideon"),
            Some(Command::Time)
        );
        assert_eq!(
            parse("Hey, Custom, volume 50.", "Custom Phrase"),
            None,
            "only the first wake word takes the comma"
        );
        assert_eq!(parse("open, brave", ""), None);
        assert_eq!(parse("Hey, Gideonish open brave", "Hey Gideon"), None);
        assert_eq!(parse("Okay, Gideon, open brave", "Hey Gideon"), None);
        assert_eq!(parse("hey, gideon, open brave, mute", "Hey Gideon"), None);
    }
    #[test]
    fn wake_name_spellings_from_stt_are_accepted_only_in_the_name_slot() {
        // WP-7b: listed mis-transcriptions of the name (positive).
        for spelling in ["Gedon", "Lagdon", "Gidon", "Gidéon", "gédéon"] {
            assert_eq!(
                parse(&format!("Hey {spelling}, mute."), "Hey Gideon"),
                Some(Command::Mute),
                "{spelling}"
            );
            assert_eq!(
                parse(&format!("hey, {spelling}, open brave"), "Hey Gideon"),
                Some(Command::OpenApp {
                    desktop_id: BRAVE.into()
                }),
                "{spelling} with comma"
            );
        }
        assert_eq!(
            parse("Olá Gidon, abra o brave", "Olá Gideon"),
            Some(Command::OpenApp {
                desktop_id: BRAVE.into()
            })
        );
        // Negatives: an unlisted word, a spelling outside the name slot, and a changed head word.
        assert_eq!(parse("Hey Gideonish, mute", "Hey Gideon"), None);
        assert_eq!(parse("Hey Dom, mute", "Hey Gideon"), None);
        assert_eq!(parse("Hey Gidonx, mute", "Hey Gideon"), None);
        assert_eq!(parse("open Gidon, mute", "Hey Gideon"), None);
        assert_eq!(parse("Okay Gidon, mute", "Hey Gideon"), None);
        // Without a comma the canonical wake is accepted too, so the spelling is accepted the same way.
        assert_eq!(
            parse("Hey Gidon open brave", "Hey Gideon"),
            Some(Command::OpenApp {
                desktop_id: BRAVE.into()
            })
        );
    }
    #[test]
    fn receipt_requires_effect_and_exact_correlation() {
        let job = Job {
            session_id: 1,
            command: Command::Status,
        };
        let mut r = Receipt {
            job: job.clone(),
            verified: true,
            scope: "sandbox".into(),
            result: "ready".into(),
        };
        assert!(verify(&job, &r));
        r.job.session_id = 2;
        assert!(!verify(&job, &r));
        r.job = job.clone();
        r.verified = false;
        assert!(!verify(&job, &r));
        r.verified = true;
        r.scope = "other".into();
        assert!(!verify(&job, &r));
        r.scope = "host".into();
        assert!(
            verify(&job, &r),
            "host receipts are accepted only from the host executor path"
        );
    }
    #[test]
    fn real_action_grammar_and_host_policy() {
        assert_eq!(
            parse("Hey Gideon, open kcalc.", "Hey Gideon"),
            Some(Command::OpenApp {
                desktop_id: KCALC.into()
            })
        );
        assert_eq!(parse("unmute", ""), Some(Command::Unmute));
        assert_eq!(parse("volume up", ""), Some(Command::VolumeUp));
        assert_eq!(parse("diminuir volume", ""), Some(Command::VolumeDown));
        for text in [
            "volume up 5",
            "unmute and open brave",
            "volume up; mute",
            "open kcalc!",
        ] {
            assert!(parse(text, "Hey Gideon").is_none(), "{text}");
        }
        assert!(Command::Unmute.real_only() && !Command::Mute.real_only());
        // The sandbox never runs the real-only steps or apps outside its own catalog.
        assert!(authorize(&Command::Unmute).is_err());
        assert!(authorize(&Command::OpenApp {
            desktop_id: KCALC.into()
        })
        .is_err());
        assert!(authorize_host(&Command::OpenApp {
            desktop_id: KCALC.into()
        })
        .is_ok());
        assert!(authorize_host(&Command::OpenApp {
            desktop_id: "../bin/sh".into()
        })
        .is_err());
        assert!(authorize_host(&Command::Volume { level: 101 }).is_err());
        assert!(authorize_host(&Command::VolumeUp).is_ok());
    }
    #[tokio::test]
    async fn real_namespace_executes_and_verifies_all_tools() {
        for command in [
            Command::OpenApp {
                desktop_id: BRAVE.into(),
            },
            Command::Volume { level: 50 },
            Command::Mute,
            Command::Time,
            Command::Date,
            Command::Status,
        ] {
            let job = Job {
                session_id: 42,
                command,
            };
            let receipt = execute(job.clone()).await.unwrap();
            assert!(verify(&job, &receipt));
        }
        assert!(execute(Job {
            session_id: 43,
            command: Command::OpenApp {
                desktop_id: "unknown.desktop".into()
            }
        })
        .await
        .is_err());
    }
}
