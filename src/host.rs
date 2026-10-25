//! Host actions of the fixed command table (A11). Runs only when the `real_actions` preference is on and the
//! command passed `commands::authorize_host`. No shell and no PATH lookup: launchers and `wpctl` are fixed paths,
//! the environment is cleared and rebuilt from a short list, every step has a 5 s limit, and `kill_on_drop` stops
//! a step that outlives its task. A receipt is produced only for an effect that was observed: a new process of the
//! launched application, or the volume read back by `wpctl get-volume`. Nothing is claimed beyond that.
use crate::commands::{self, Command};
use std::{
    collections::BTreeSet,
    fs,
    path::{Path, PathBuf},
    process::Stdio,
    time::Duration,
};
use tokio::process::Command as Process;

/// Audio tool and default sink: the Core never names a device.
pub const WPCTL: &str = "/usr/bin/wpctl";
const SINK: &str = "@DEFAULT_AUDIO_SINK@";
/// Environment the host steps receive; nothing else from the Core's environment is passed on.
/// `XAUTHORITY` is the one addition to the A11 list: Chromium-based apps (Brave) take the XWayland path on this
/// Plasma session and exit at once with "Missing X server" when the cookie file is not named (docs/A11).
const ENV_KEYS: [&str; 7] = [
    "WAYLAND_DISPLAY",
    "DISPLAY",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
    "XDG_CURRENT_DESKTOP",
    "HOME",
    "XAUTHORITY",
];
const PATH: &str = "/usr/bin:/bin";
const STEP_TIMEOUT: Duration = Duration::from_secs(5);
const OBSERVE_TIMEOUT: Duration = Duration::from_secs(5);
const OBSERVE_STEP: Duration = Duration::from_millis(100);
/// A new process counts only if it still runs this long after it first appears.
const SETTLE: Duration = Duration::from_secs(1);
const MAX_DESKTOP_BYTES: u64 = 256 * 1024;
const DESKTOP_SUFFIX: &str = ".desktop";
/// The kernel keeps 15 bytes of a process name (`/proc/<pid>/comm`).
const COMM_LEN: usize = 15;

/// Desktop ids of a canonical catalog app, in order. The first installed one wins (aliases of the same app).
fn candidates(canonical: &str) -> &'static [&'static str] {
    match canonical {
        commands::BRAVE => &["com.brave.Browser.desktop", "brave-browser.desktop"],
        commands::STEAM => &["com.valvesoftware.Steam.desktop", "steam.desktop"],
        commands::KCALC => &["org.kde.kcalc.desktop"],
        _ => &[],
    }
}

/// `^[A-Za-z0-9][A-Za-z0-9._-]*\.desktop$`, 9..=128 bytes: the same rule as the tool ids.
pub fn valid_desktop_id(id: &str) -> bool {
    let bytes = id.as_bytes();
    bytes.len() > DESKTOP_SUFFIX.len()
        && bytes.len() <= 128
        && id.ends_with(DESKTOP_SUFFIX)
        && bytes[0].is_ascii_alphanumeric()
        && bytes
            .iter()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
}

/// Standard XDG application directories: system, Flatpak exports and the user's own.
pub fn application_dirs(home: Option<&Path>) -> Vec<PathBuf> {
    let mut dirs = vec![
        PathBuf::from("/usr/local/share/applications"),
        PathBuf::from("/usr/share/applications"),
        PathBuf::from("/var/lib/flatpak/exports/share/applications"),
    ];
    if let Some(home) = home {
        dirs.push(home.join(".local/share/applications"));
        dirs.push(home.join(".local/share/flatpak/exports/share/applications"));
    }
    dirs
}

/// The installed desktop entry of a canonical app: the first candidate id that exists in one of `dirs`.
pub fn resolve(canonical: &str, dirs: &[PathBuf]) -> Option<(&'static str, PathBuf)> {
    candidates(canonical)
        .iter()
        .filter(|id| valid_desktop_id(id))
        .find_map(|id| {
            dirs.iter()
                .map(|dir| dir.join(id))
                .find(|path| path.is_file())
                .map(|path| (*id, path))
        })
}

/// Executable name from the `Exec=` line of the `[Desktop Entry]` group (`brave %U` gives `brave`).
/// Only plain names pass: no arguments, no shell text, no field codes.
pub fn exec_binary(text: &str) -> Option<String> {
    let mut in_entry = false;
    for line in text.lines() {
        if line.starts_with('[') {
            in_entry = line.trim_end() == "[Desktop Entry]";
            continue;
        }
        if !in_entry {
            continue;
        }
        if let Some(value) = line.strip_prefix("Exec=") {
            let first = value.split_whitespace().next()?;
            let name = first.rsplit('/').next()?;
            let plain = !name.is_empty()
                && name.len() <= COMM_LEN
                && name.as_bytes()[0].is_ascii_alphanumeric()
                && name
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'));
            return plain.then(|| name.to_owned());
        }
    }
    None
}

/// PIDs whose kernel process name equals `name` (its first 15 bytes). Unreadable entries are skipped.
pub fn pids_named(name: &str) -> BTreeSet<u32> {
    let wanted: String = name.chars().take(COMM_LEN).collect();
    let mut pids = BTreeSet::new();
    let Ok(entries) = fs::read_dir("/proc") else {
        return pids;
    };
    for entry in entries.flatten() {
        let Some(pid) = entry
            .file_name()
            .to_str()
            .and_then(|n| n.parse::<u32>().ok())
        else {
            continue;
        };
        if fs::read_to_string(entry.path().join("comm")).is_ok_and(|comm| comm.trim_end() == wanted)
        {
            pids.insert(pid);
        }
    }
    pids
}

/// Command with the fixed environment: cleared, then only the short key list and a fixed PATH.
fn host_command(program: &str) -> Process {
    let mut command = Process::new(program);
    command.env_clear();
    for key in ENV_KEYS {
        if let Some(value) = std::env::var_os(key) {
            command.env(key, value);
        }
    }
    command
        .env("PATH", PATH)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .kill_on_drop(true);
    command
}

/// First launcher available, in order: `gtk-launch <id>`, `gio launch <file>`, `kioclient6 exec <file>`.
fn launcher(id: &str, path: &Path) -> Option<Process> {
    let is_file = |p: &str| Path::new(p).is_file();
    if is_file("/usr/bin/gtk-launch") {
        let mut command = host_command("/usr/bin/gtk-launch");
        command.arg(id.strip_suffix(DESKTOP_SUFFIX).unwrap_or(id));
        return Some(command);
    }
    if is_file("/usr/bin/gio") {
        let mut command = host_command("/usr/bin/gio");
        command.arg("launch").arg(path);
        return Some(command);
    }
    if is_file("/usr/bin/kioclient6") {
        let mut command = host_command("/usr/bin/kioclient6");
        command.arg("exec").arg(path);
        return Some(command);
    }
    None
}

fn read_entry(path: &Path) -> Option<String> {
    let meta = fs::metadata(path).ok()?;
    if !meta.is_file() || meta.len() > MAX_DESKTOP_BYTES {
        return None;
    }
    fs::read_to_string(path).ok()
}

/// Launches a catalog app and confirms it: a process with the entry's executable name must appear that was not
/// running before the launch, within 5 s. A window is not checked here (no window API is available on this host),
/// so the receipt says so. Errors: `app_not_installed`, `launch_failed`, `launch_unconfirmed`.
pub async fn open_app(canonical: &str) -> Result<String, &'static str> {
    let home = std::env::var_os("HOME").map(PathBuf::from);
    let dirs = application_dirs(home.as_deref());
    let (id, path) = resolve(canonical, &dirs).ok_or("app_not_installed")?;
    let text = read_entry(&path).ok_or("app_not_installed")?;
    let binary = exec_binary(&text).ok_or("launch_failed")?;
    let mut launch = launcher(id, &path).ok_or("launch_failed")?;
    let before = pids_named(&binary);
    let mut child = launch.spawn().map_err(|_| "launch_failed")?;
    let status = tokio::time::timeout(STEP_TIMEOUT, child.wait())
        .await
        .map_err(|_| "launch_failed")?
        .map_err(|_| "launch_failed")?;
    if !status.success() {
        return Err("launch_failed");
    }
    let deadline = tokio::time::Instant::now() + OBSERVE_TIMEOUT;
    loop {
        let fresh: Vec<u32> = pids_named(&binary).difference(&before).copied().collect();
        if let Some(&pid) = fresh.first() {
            // A process that exits at once (for example a refused display) is not an opened app: it must still
            // be running after the grace period, otherwise the search goes on until the deadline.
            tokio::time::sleep(SETTLE).await;
            if pids_named(&binary).contains(&pid) {
                return Ok(format!(
                    "Abriu: {} (processo {pid} observado) · iniciado, sem confirmação de janela",
                    commands::app_label(canonical)
                ));
            }
        }
        if tokio::time::Instant::now() >= deadline {
            return Err("launch_unconfirmed");
        }
        tokio::time::sleep(OBSERVE_STEP).await;
    }
}

/// Parses `wpctl get-volume` output: `Volume: 0.65` or `Volume: 0.65 [MUTED]`. Returns percent and mute state.
pub fn parse_volume(text: &str) -> Option<(u16, bool)> {
    let rest = text.trim().strip_prefix("Volume:")?.trim();
    let mut parts = rest.split_whitespace();
    let value: f64 = parts.next()?.parse().ok()?;
    if !value.is_finite() || !(0.0..=1.5).contains(&value) {
        return None;
    }
    let muted = parts.any(|part| part == "[MUTED]");
    Some(((value * 100.0).round() as u16, muted))
}

async fn wpctl(args: &[&str]) -> Result<String, &'static str> {
    let mut command = host_command(WPCTL);
    command.args(args).stdout(Stdio::piped());
    let child = command.spawn().map_err(|_| "volume_unavailable")?;
    let output = tokio::time::timeout(STEP_TIMEOUT, child.wait_with_output())
        .await
        .map_err(|_| "volume_unavailable")?
        .map_err(|_| "volume_unavailable")?;
    if !output.status.success() {
        return Err("volume_unavailable");
    }
    String::from_utf8(output.stdout).map_err(|_| "volume_unavailable")
}

async fn read_sink() -> Result<(u16, bool), &'static str> {
    let text = wpctl(&["get-volume", SINK]).await?;
    parse_volume(&text).ok_or("volume_unavailable")
}

/// Volume and mute of the default sink (A11). Each change is read back with `wpctl get-volume` before it is
/// reported; a mismatch is `volume_unverified`. Levels are 0..=100 (wpctl reads 2 decimals: 1 point of tolerance).
pub async fn volume(command: &Command) -> Result<String, &'static str> {
    #[derive(Clone, Copy)]
    enum Target {
        Level(u16),
        Mute(bool),
    }
    let (current, _) = read_sink().await?;
    let target = match command {
        Command::Volume { level } => Target::Level(u16::from(*level)),
        Command::VolumeUp => Target::Level((current + 10).min(100)),
        Command::VolumeDown => Target::Level(current.saturating_sub(10)),
        Command::Mute => Target::Mute(true),
        Command::Unmute => Target::Mute(false),
        _ => return Err("unsupported"),
    };
    match target {
        Target::Level(level) => {
            if level > 100 {
                return Err("denied");
            }
            let percent = format!("{level}%");
            wpctl(&["set-volume", SINK, percent.as_str()]).await?;
        }
        Target::Mute(muted) => {
            wpctl(&["set-mute", SINK, if muted { "1" } else { "0" }]).await?;
        }
    }
    let (after, muted) = read_sink().await.map_err(|_| "volume_unverified")?;
    match target {
        Target::Level(level) if after.abs_diff(level) <= 1 => {
            Ok(format!("Volume em {after}% · verificado com wpctl"))
        }
        Target::Mute(true) if muted => Ok("Mudo ativado · verificado com wpctl".into()),
        Target::Mute(false) if !muted => Ok("Som ativado · verificado com wpctl".into()),
        _ => Err("volume_unverified"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn desktop_ids_follow_the_tool_rule() {
        assert!(valid_desktop_id("org.kde.kcalc.desktop"));
        assert!(valid_desktop_id("brave-browser.desktop"));
        for bad in [
            "../x.desktop",
            "a/b.desktop",
            ".hidden.desktop",
            "x.desktop;rm",
            "kcalc",
            ".desktop",
        ] {
            assert!(!valid_desktop_id(bad), "{bad}");
        }
    }

    #[test]
    fn exec_line_yields_only_a_plain_binary_name() {
        let entry =
            "[Desktop Entry]\nName=Brave\nExec=brave %U\n[Desktop Action New]\nExec=other\n";
        assert_eq!(exec_binary(entry).as_deref(), Some("brave"));
        assert_eq!(
            exec_binary("[Desktop Entry]\nExec=/usr/bin/kcalc\n").as_deref(),
            Some("kcalc")
        );
        assert_eq!(
            exec_binary("[Desktop Entry]\nExec=sh -c x\n").as_deref(),
            Some("sh")
        );
        assert!(exec_binary("[Desktop Entry]\nExec=\n").is_none());
        assert!(exec_binary("[Desktop Entry]\nExec=$(id)\n").is_none());
        assert!(exec_binary("[Other]\nExec=brave\n").is_none());
    }

    #[test]
    fn resolve_uses_only_the_given_standard_dirs_and_aliases() {
        let dir = tempfile::tempdir().unwrap();
        let alias = dir.path().join("brave-browser.desktop");
        fs::write(&alias, "[Desktop Entry]\nExec=brave %U\n").unwrap();
        let dirs = vec![dir.path().to_path_buf()];
        assert_eq!(
            resolve(commands::BRAVE, &dirs),
            Some(("brave-browser.desktop", alias))
        );
        assert!(resolve(commands::KCALC, &dirs).is_none());
        assert!(resolve(commands::BRAVE, &[]).is_none());
    }

    #[test]
    fn volume_text_is_read_strictly() {
        assert_eq!(parse_volume("Volume: 0.65\n"), Some((65, false)));
        assert_eq!(parse_volume("Volume: 0.30 [MUTED]"), Some((30, true)));
        assert_eq!(parse_volume("Volume: 1.20"), Some((120, false)));
        assert!(parse_volume("Volume: nan").is_none());
        assert!(parse_volume("Volume: 2.5").is_none());
        assert!(parse_volume("garbage").is_none());
    }

    #[test]
    fn own_process_is_found_by_its_name() {
        let name = fs::read_to_string("/proc/self/comm").unwrap();
        assert!(pids_named(name.trim_end()).contains(&std::process::id()));
        assert!(!pids_named("no-such-process-name-xyz").contains(&std::process::id()));
    }
}
