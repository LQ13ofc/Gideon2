//! A4 read-only audio device enumeration. Runs `pactl` (JSON, then `list short`) or `pw-dump` as
//! plain subprocesses: no shell, no bwrap, cleared environment, one 3 s budget for the whole call
//! and a 64 KiB cap per output. Monitor sources are never offered as inputs. Ids are preference
//! values (`storage::valid_audio_device`); a device whose raw name is outside that charset is
//! dropped, because a sanitized id would point the recorder at a different device. Labels are
//! sanitized to the same charset.
use crate::storage::{valid_audio_device, AUDIO_DEVICE_MAX};
use serde::Serialize;
use serde_json::Value;
use std::{
    ffi::{OsStr, OsString},
    io::{ErrorKind, Read},
    path::Path,
    process::{Command, Stdio},
    time::{Duration, Instant},
};

/// At most this many devices per direction.
pub const MAX_DEVICES: usize = 16;
/// Wall-clock budget of one enumeration (all tool calls together). The Core call is synchronous.
pub const BUDGET: Duration = Duration::from_secs(3);
/// Maximum bytes accepted from one tool call.
pub const OUTPUT_CAP: usize = 64 * 1024;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Device {
    pub id: String,
    pub label: String,
    pub default: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Devices {
    pub inputs: Vec<Device>,
    pub outputs: Vec<Device>,
    pub source: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<&'static str>,
}

/// Enumerates with the Core's own `PATH`.
pub fn enumerate() -> Devices {
    enumerate_in(std::env::var_os("PATH").unwrap_or_default().as_os_str())
}

/// Enumerates with the given `PATH` (tests put fake tools first).
pub fn enumerate_in(path: &OsStr) -> Devices {
    let mut runner = Runner {
        path,
        deadline: Instant::now() + BUDGET,
        present: false,
    };
    let devices = enumerate_with(&mut runner);
    if devices.source == "none" && runner.present {
        return empty("audio_tool_failed");
    }
    devices
}

fn enumerate_with(runner: &mut Runner) -> Devices {
    // pactl JSON first; `list short` is the fallback for a pactl without JSON output.
    if let (Some(sources), Some(sinks)) = (
        runner.run(Tool::Pactl, &["--format=json", "list", "sources"]),
        runner.run(Tool::Pactl, &["--format=json", "list", "sinks"]),
    ) {
        let info = runner
            .run(Tool::Pactl, &["--format=json", "info"])
            .unwrap_or_default();
        if let Some(devices) = from_pactl_json(&sources, &sinks, &info) {
            return devices;
        }
    }
    if let (Some(sources), Some(sinks)) = (
        runner.run(Tool::Pactl, &["list", "short", "sources"]),
        runner.run(Tool::Pactl, &["list", "short", "sinks"]),
    ) {
        let info = runner
            .run(Tool::Pactl, &["--format=json", "info"])
            .unwrap_or_default();
        return from_pactl_short(&sources, &sinks, pactl_defaults(&info));
    }
    if let Some(dump) = runner.run(Tool::PwDump, &[]) {
        if let Some(devices) = from_pw_dump(&dump) {
            return devices;
        }
    }
    empty("no_audio_tool")
}

#[derive(Clone, Copy)]
enum Tool {
    Pactl,
    PwDump,
}

impl Tool {
    fn name(self) -> &'static str {
        match self {
            Tool::Pactl => "pactl",
            Tool::PwDump => "pw-dump",
        }
    }
}

struct Runner<'a> {
    path: &'a OsStr,
    deadline: Instant,
    /// Set once any tool was found on `PATH`, even if it then failed.
    present: bool,
}

impl Runner<'_> {
    /// Output of one read-only call, or `None` when the tool is missing, failed, late or too large.
    fn run(&mut self, tool: Tool, args: &[&str]) -> Option<Vec<u8>> {
        if Instant::now() >= self.deadline {
            return None;
        }
        let mut env_path: OsString = self.path.to_os_string();
        if env_path.is_empty() {
            env_path = OsString::from("/usr/bin:/bin");
        }
        let mut command = Command::new(tool.name());
        command
            .args(args)
            .env_clear()
            .env("PATH", &env_path)
            .env("LC_ALL", "C")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        for key in ["HOME", "XDG_RUNTIME_DIR"] {
            if let Some(value) = std::env::var_os(key).filter(|v| Path::new(v).is_absolute()) {
                command.env(key, value);
            }
        }
        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(error) if error.kind() == ErrorKind::NotFound => return None,
            Err(_) => {
                self.present = true;
                return None;
            }
        };
        self.present = true;
        let mut stdout = child.stdout.take()?;
        let (sender, receiver) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let mut bytes = Vec::new();
            // One byte past the cap is enough to detect an oversized answer.
            let _ = (&mut stdout)
                .take(OUTPUT_CAP as u64 + 1)
                .read_to_end(&mut bytes);
            let _ = sender.send(bytes);
        });
        let succeeded = loop {
            match child.try_wait() {
                Ok(Some(status)) => break status.success(),
                Ok(None) if Instant::now() < self.deadline => {
                    std::thread::sleep(Duration::from_millis(10));
                }
                _ => {
                    let _ = child.kill();
                    let _ = child.wait();
                    break false;
                }
            }
        };
        // A grandchild that kept the pipe open must not hold the Core past its budget.
        let bytes = receiver.recv_timeout(Duration::from_millis(200)).ok()?;
        (succeeded && bytes.len() <= OUTPUT_CAP).then_some(bytes)
    }
}

fn empty(reason: &'static str) -> Devices {
    Devices {
        inputs: Vec::new(),
        outputs: Vec::new(),
        source: "none",
        reason: Some(reason),
    }
}

/// Label charset: Unicode letters and digits, `._:@/+ -`; every other character becomes `_`, and the
/// result stays within `AUDIO_DEVICE_MAX` bytes. Labels are display text only: the id is the
/// preference value and keeps the ASCII charset. Accented names ("Estéreo analógico") stay readable;
/// controls and format marks (bidi overrides) are never kept.
pub fn sanitize_label(raw: &str, fallback: &str) -> String {
    let mut label = String::new();
    for ch in raw.chars() {
        let kept = if ch.is_alphanumeric() || "._:@/+ -".contains(ch) {
            ch
        } else {
            '_'
        };
        if label.len() + kept.len_utf8() > AUDIO_DEVICE_MAX {
            break;
        }
        label.push(kept);
    }
    let trimmed = label.trim();
    if trimmed.is_empty() {
        fallback.to_string()
    } else {
        trimmed.to_string()
    }
}

/// `Some(id)` only when the raw name is already a valid preference value and not a monitor.
fn usable_id(name: &str) -> Option<String> {
    (valid_audio_device(name) && !name.ends_with(".monitor")).then(|| name.to_string())
}

/// One candidate: (id, label, is_default).
type Candidate = (String, String, bool);

fn build(mut inputs: Vec<Candidate>, mut outputs: Vec<Candidate>, source: &'static str) -> Devices {
    let finish = |items: &mut Vec<Candidate>| {
        let mut seen = Vec::<String>::new();
        let mut out = Vec::new();
        for (id, label, default) in items.drain(..) {
            if seen.contains(&id) {
                continue;
            }
            seen.push(id.clone());
            let label = sanitize_label(&label, &id);
            out.push(Device { id, label, default });
            if out.len() == MAX_DEVICES {
                break;
            }
        }
        out
    };
    Devices {
        inputs: finish(&mut inputs),
        outputs: finish(&mut outputs),
        source,
        reason: None,
    }
}

struct PactlDefaults {
    source: Option<String>,
    sink: Option<String>,
}

fn pactl_defaults(info: &[u8]) -> Option<PactlDefaults> {
    let value: Value = serde_json::from_slice(info).ok()?;
    Some(PactlDefaults {
        source: value["default_source_name"].as_str().map(str::to_string),
        sink: value["default_sink_name"].as_str().map(str::to_string),
    })
}

fn is_default(defaults: Option<&PactlDefaults>, sink: bool, name: &str) -> bool {
    defaults
        .and_then(|d| {
            if sink {
                d.sink.as_deref()
            } else {
                d.source.as_deref()
            }
        })
        .is_some_and(|default| default == name)
}

/// Parses `pactl --format=json list sources|sinks`. Malformed single entries are skipped; a
/// document that is not a JSON array is refused so the caller can fall back.
fn from_pactl_json(sources: &[u8], sinks: &[u8], info: &[u8]) -> Option<Devices> {
    let defaults = pactl_defaults(info);
    let source_list: Value = serde_json::from_slice(sources).ok()?;
    let sink_list: Value = serde_json::from_slice(sinks).ok()?;
    let mut inputs = Vec::new();
    for item in source_list.as_array()? {
        // A source that monitors a sink is a loopback of playback, never a microphone.
        if item["monitor_of_sink"].as_str().is_some() {
            continue;
        }
        let Some(name) = item["name"].as_str() else {
            continue;
        };
        let Some(id) = usable_id(name) else { continue };
        let label = item["description"].as_str().unwrap_or(name).to_string();
        let default = is_default(defaults.as_ref(), false, name);
        inputs.push((id, label, default));
    }
    let mut outputs = Vec::new();
    for item in sink_list.as_array()? {
        let Some(name) = item["name"].as_str() else {
            continue;
        };
        let Some(id) = usable_id(name) else { continue };
        let label = item["description"].as_str().unwrap_or(name).to_string();
        let default = is_default(defaults.as_ref(), true, name);
        outputs.push((id, label, default));
    }
    Some(build(inputs, outputs, "pactl"))
}

/// Parses `pactl list short sources|sinks` (tab separated: index, name, driver, spec, state).
/// Short listings carry no description, so the label is the id itself.
fn from_pactl_short(sources: &[u8], sinks: &[u8], defaults: Option<PactlDefaults>) -> Devices {
    let parse = |bytes: &[u8], sink: bool| -> Vec<Candidate> {
        String::from_utf8_lossy(bytes)
            .lines()
            .filter_map(|line| line.split('\t').nth(1))
            .filter_map(|name| {
                let id = usable_id(name)?;
                let default = is_default(defaults.as_ref(), sink, name);
                Some((id.clone(), id, default))
            })
            .collect()
    };
    build(parse(sources, false), parse(sinks, true), "pactl")
}

/// Parses `pw-dump`. It carries no default-device marker here, so `default` stays false.
fn from_pw_dump(bytes: &[u8]) -> Option<Devices> {
    let value: Value = serde_json::from_slice(bytes).ok()?;
    let mut inputs = Vec::new();
    let mut outputs = Vec::new();
    for object in value.as_array()? {
        let props = &object["info"]["props"];
        let Some(name) = props["node.name"].as_str() else {
            continue;
        };
        let Some(id) = usable_id(name) else { continue };
        let label = props["node.description"]
            .as_str()
            .or_else(|| props["node.nick"].as_str())
            .unwrap_or(name)
            .to_string();
        match props["media.class"].as_str() {
            Some("Audio/Source") => inputs.push((id, label, false)),
            Some("Audio/Sink") => outputs.push((id, label, false)),
            _ => {}
        }
    }
    Some(build(inputs, outputs, "pw-dump"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn labels_keep_unicode_letters_and_replace_the_rest() {
        assert_eq!(sanitize_label("Mic (USB) ação", "x"), "Mic _USB_ ação");
        // Bidi override (U+202E) and markup characters are replaced, never kept.
        assert_eq!(sanitize_label("Estéreo \u{202e}x<b>", "x"), "Estéreo _x_b_");
        assert_eq!(sanitize_label("   ", "fallback"), "fallback");
        assert!(sanitize_label(&"á".repeat(300), "x").len() <= AUDIO_DEVICE_MAX);
    }

    #[test]
    fn monitors_and_unsafe_names_are_never_offered() {
        assert!(usable_id("alsa_output.pci.monitor").is_none());
        assert!(usable_id("bad$name").is_none());
        assert_eq!(
            usable_id("alsa_input.usb-1.analog").as_deref(),
            Some("alsa_input.usb-1.analog")
        );
    }

    #[test]
    fn missing_tools_report_no_audio_tool() {
        let devices = enumerate_in(OsStr::new("/nonexistent-gideon-audio-dir"));
        assert_eq!(devices.source, "none");
        assert_eq!(devices.reason, Some("no_audio_tool"));
        assert!(devices.inputs.is_empty() && devices.outputs.is_empty());
    }
}
