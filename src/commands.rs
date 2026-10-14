//! Deterministic final-only commands and explicitly scoped sandbox authority.
use serde::{Deserialize, Serialize};
use std::{io, process::Stdio, time::Duration};
use tokio::io::{AsyncWriteExt, BufReader};

pub const BRAVE: &str = "com.brave.Browser.desktop";
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Command {
    OpenApp { desktop_id: String },
    Volume { level: u8 },
    Mute,
    Status,
    Time,
    Date,
    Cancel,
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
/// Full-string grammar: no substring extraction, fuzzy names, or chained commands.
pub fn parse(raw: &str, wake: &str) -> Option<Command> {
    let normalized = raw
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase();
    let mut text = normalized.as_str();
    let prefix = wake.to_lowercase();
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
            desktop_id: "com.valvesoftware.Steam.desktop".into(),
        }),
        "mute" | "mute audio" | "silenciar" => Some(Command::Mute),
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
/// Actor-owned grant; cannot be supplied through IPC or a transcript.
pub fn authorize(command: &Command) -> Result<(), &'static str> {
    match command {
        Command::OpenApp { desktop_id } if desktop_id != BRAVE => Err("app_unavailable"),
        Command::Volume { level } if *level > 100 => Err("denied"),
        _ => Ok(()),
    }
}
/// Trusted sandbox worker verifies the effect; Rust validates identity and scope again.
pub fn verify(job: &Job, receipt: &Receipt) -> bool {
    receipt.job == *job
        && receipt.verified
        && receipt.scope == "sandbox"
        && !receipt.result.is_empty()
        && receipt.result.len() <= 256
        && !receipt.result.chars().any(char::is_control)
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
        r.scope = "host".into();
        assert!(!verify(&job, &r));
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
