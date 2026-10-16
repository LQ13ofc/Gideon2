//! C4 synthetic world: `<home>/synthetic/world.json` (version 1, at most 64 KiB, 0600, atomic).
//! Only reachable under `--agent-synthetic`; no service here touches real hardware.
//! The C3 test app lives in `app`. `app.json` is a private mirror of that section, written on every
//! save and read only as a migration source when `world.json` does not exist yet. `base` is a
//! sentinel: no service in this file ever writes it.
//! Every service validates its arguments strictly, checks screen epochs before writing, and re-reads
//! the world after each write (`verified`). Replies are capped at `MAX_REPLY` bytes.
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    fs,
    io::{self, Write},
    os::unix::fs::{OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
    sync::Mutex,
};

pub const VERSION: u32 = 1;
pub const MAX_FILE: usize = 64 * 1024;
pub const MAX_REPLY: usize = 4096;
const MAX_ARGS: usize = 1024;
const FILE: &str = "world.json";
const MIRROR: &str = "app.json";
const SUBDIR: &str = "synthetic";
const TEXT_MAX: usize = 64;
const REGION_MAX: usize = 16;
const COORD_MAX: u32 = 8192;
const WINDOWS_MAX: usize = 8;
const ELEMENTS_MAX: usize = 64;
const ROUTES_MAX: usize = 8;
const APPS_MAX: usize = 16;
pub const EQ_PRESETS: [&str; 4] = ["flat", "voice", "music", "bass"];
pub const MIC_FILTERS: [&str; 3] = ["off", "low_cut", "voice"];
pub const GESTURES: [&str; 2] = ["wave", "thumbs_up"];
pub const KEYS: [&str; 3] = ["enter", "escape", "tab"];
/// Manifest permissions that gate the C4 services. The Core checks approval, never the plugin.
pub const PERMISSIONS: [&str; 5] = [
    "screen_observe",
    "input_control",
    "audio_route",
    "mic_config",
    "camera_capture",
];
/// Service names without the `synthetic.` prefix, with the permission each one needs.
const SERVICES: [(&str, &str); 21] = [
    ("screen.capture", "screen_observe"),
    ("input.a11y_tree", "input_control"),
    ("input.click", "input_control"),
    ("input.type", "input_control"),
    ("input.key", "input_control"),
    ("input.focus", "input_control"),
    ("audio.routes", "audio_route"),
    ("audio.set_route", "audio_route"),
    ("audio.app_volume", "audio_route"),
    ("audio.eq", "audio_route"),
    ("audio.denoise", "audio_route"),
    ("audio.state", "audio_route"),
    ("mic.state", "mic_config"),
    ("mic.configure", "mic_config"),
    ("mic.monitor", "mic_config"),
    ("mic.record_start", "mic_config"),
    ("mic.record_stop", "mic_config"),
    ("camera.state", "camera_capture"),
    ("camera.optin", "camera_capture"),
    ("camera.capture", "camera_capture"),
    ("camera.gestures", "camera_capture"),
];

/// Serializes every access in this process: read-modify-write must never interleave.
static LOCK: Mutex<()> = Mutex::new(());

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct App {
    pub epoch: u64,
    pub counter: u64,
    pub text: String,
    pub published: bool,
}

impl Default for App {
    fn default() -> Self {
        Self {
            epoch: 1,
            counter: 0,
            text: String::new(),
            published: false,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Window {
    pub id: String,
    pub title: String,
    pub focused: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Element {
    pub id: String,
    pub role: String,
    pub name: String,
    pub x: u32,
    pub y: u32,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Screen {
    pub epoch: u64,
    pub width: u32,
    pub height: u32,
    pub windows: Vec<Window>,
    pub elements: Vec<Element>,
    /// Element id with keyboard focus; `type` needs a focused textbox.
    pub focus: Option<String>,
    pub text: String,
    pub last_click: Option<String>,
    pub last_key: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AudioApp {
    pub id: String,
    pub volume: u8,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Audio {
    pub routes: Vec<String>,
    /// Current output route; always one of `routes`.
    pub route: String,
    pub apps: Vec<AudioApp>,
    pub eq: String,
    pub denoise: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Mic {
    pub device: String,
    pub gain: u8,
    pub filter: String,
    pub monitor: bool,
    pub recording: bool,
    /// Always `monitor || recording`: the privacy indicator is never off while the mic is in use.
    pub indicator: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Camera {
    pub opt_in: bool,
    /// Always equal to `opt_in`.
    pub indicator: bool,
    pub frame_seq: u64,
    pub gesture: Option<String>,
}

/// Sentinel for the Base mic and speaker. C4 services never write it.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Base {
    pub mic_state: String,
    pub speaker_state: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct World {
    pub version: u32,
    pub app: App,
    pub screen: Screen,
    pub audio: Audio,
    pub mic: Mic,
    pub camera: Camera,
    pub base: Base,
}

impl Default for World {
    fn default() -> Self {
        let element = |id: &str, role: &str, name: &str, x: u32, y: u32| Element {
            id: id.into(),
            role: role.into(),
            name: name.into(),
            x,
            y,
        };
        Self {
            version: VERSION,
            app: App::default(),
            screen: Screen {
                epoch: 1,
                width: 1280,
                height: 720,
                windows: vec![Window {
                    id: "main".into(),
                    title: "Janela sintetica".into(),
                    focused: true,
                }],
                elements: vec![
                    element("field", "textbox", "Campo", 40, 40),
                    element("apply", "button", "Aplicar", 40, 100),
                    element("cancel", "button", "Cancelar", 160, 100),
                ],
                focus: None,
                text: String::new(),
                last_click: None,
                last_key: None,
            },
            audio: Audio {
                routes: vec!["speakers".into(), "headphones".into(), "bluetooth".into()],
                route: "speakers".into(),
                apps: vec![
                    AudioApp {
                        id: "player".into(),
                        volume: 50,
                    },
                    AudioApp {
                        id: "browser".into(),
                        volume: 50,
                    },
                ],
                eq: "flat".into(),
                denoise: false,
            },
            mic: Mic {
                device: "synthetic-mic".into(),
                gain: 50,
                filter: "off".into(),
                monitor: false,
                recording: false,
                indicator: false,
            },
            camera: Camera {
                opt_in: false,
                indicator: false,
                frame_seq: 0,
                gesture: None,
            },
            base: Base {
                mic_state: "base-idle".into(),
                speaker_state: "base-idle".into(),
            },
        }
    }
}

/// Directory that holds `world.json` (and the `app.json` mirror) for the current home.
pub fn dir() -> PathBuf {
    crate::transport::home().join(SUBDIR)
}

/// Permission a service needs, or `None` for an unknown service name.
pub fn permission(service: &str) -> Option<&'static str> {
    SERVICES
        .iter()
        .find(|(name, _)| *name == service)
        .map(|(_, permission)| *permission)
}

/// Audit kind for a service (never content): one family per area.
pub fn audit_kind(service: &str) -> &'static str {
    match service.split('.').next() {
        Some("screen") => "screen_capture",
        Some("input") => "input_action",
        Some("audio") => "audio_action",
        Some("mic") => "mic_action",
        Some("camera") => "camera_action",
        _ => "synthetic_action",
    }
}

fn ensure(ok: bool) -> Result<(), &'static str> {
    if ok {
        Ok(())
    } else {
        Err("world_invalid")
    }
}

/// Non-empty text without control characters.
fn text_ok(value: &str, max: usize) -> bool {
    !value.is_empty() && plain(value, max)
}

/// Text without control characters, possibly empty.
fn plain(value: &str, max: usize) -> bool {
    value.len() <= max && !value.chars().any(char::is_control)
}

/// Lowercase identifier: `[a-z0-9_-]`, 1..=32 bytes.
fn ident_ok(value: &str) -> bool {
    (1..=32).contains(&value.len())
        && value
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_' || b == b'-')
}

/// Shape and cross-field invariants. Anything else is refused on load and before every save.
pub fn validate(world: &World) -> Result<(), &'static str> {
    ensure(world.version == VERSION)?;
    ensure(plain(&world.app.text, TEXT_MAX))?;
    let screen = &world.screen;
    ensure((1..=COORD_MAX).contains(&screen.width) && (1..=COORD_MAX).contains(&screen.height))?;
    ensure(screen.windows.len() <= WINDOWS_MAX)?;
    for window in &screen.windows {
        ensure(ident_ok(&window.id) && text_ok(&window.title, TEXT_MAX))?;
    }
    ensure(screen.elements.len() <= ELEMENTS_MAX)?;
    let mut ids = HashSet::new();
    for element in &screen.elements {
        ensure(
            ident_ok(&element.id)
                && ids.insert(element.id.as_str())
                && text_ok(&element.role, 32)
                && text_ok(&element.name, TEXT_MAX)
                && element.x <= COORD_MAX
                && element.y <= COORD_MAX,
        )?;
    }
    let known = |id: &Option<String>| id.as_ref().is_none_or(|id| ids.contains(id.as_str()));
    ensure(known(&screen.focus) && known(&screen.last_click))?;
    ensure(plain(&screen.text, TEXT_MAX))?;
    ensure(
        screen
            .last_key
            .as_ref()
            .is_none_or(|key| KEYS.contains(&key.as_str())),
    )?;
    let audio = &world.audio;
    ensure((1..=ROUTES_MAX).contains(&audio.routes.len()))?;
    ensure(audio.routes.iter().all(|route| ident_ok(route)))?;
    ensure(audio.routes.contains(&audio.route))?;
    ensure(audio.apps.len() <= APPS_MAX)?;
    ensure(
        audio
            .apps
            .iter()
            .all(|app| ident_ok(&app.id) && app.volume <= 100),
    )?;
    ensure(EQ_PRESETS.contains(&audio.eq.as_str()))?;
    let mic = &world.mic;
    ensure(
        plain(&mic.device, 64)
            && mic.gain <= 100
            && MIC_FILTERS.contains(&mic.filter.as_str())
            && mic.indicator == (mic.monitor || mic.recording),
    )?;
    let camera = &world.camera;
    ensure(camera.indicator == camera.opt_in)?;
    ensure(
        camera
            .gesture
            .as_ref()
            .is_none_or(|gesture| GESTURES.contains(&gesture.as_str())),
    )?;
    ensure(plain(&world.base.mic_state, 32) && plain(&world.base.speaker_state, 32))
}

/// Writes `bytes` to `dir/name` through a 0600 temporary file and a rename.
fn write_private(dir: &Path, name: &str, bytes: &[u8]) -> Result<(), &'static str> {
    let write = || -> io::Result<()> {
        fs::create_dir_all(dir)?;
        fs::set_permissions(dir, fs::Permissions::from_mode(0o700))?;
        let temporary = dir.join(format!("{name}.tmp"));
        let _ = fs::remove_file(&temporary);
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temporary)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temporary, dir.join(name))
    };
    write().map_err(|_| "world_write_failed")
}

/// Loads the world. A missing `world.json` migrates the C3 `app.json` into `app`.
pub fn load(dir: &Path) -> Result<World, &'static str> {
    match fs::metadata(dir.join(FILE)) {
        Ok(meta) if meta.len() > MAX_FILE as u64 => Err("world_unavailable"),
        Ok(_) => {
            let bytes = fs::read(dir.join(FILE)).map_err(|_| "world_unavailable")?;
            let world: World = serde_json::from_slice(&bytes).map_err(|_| "world_unavailable")?;
            validate(&world).map_err(|_| "world_unavailable")?;
            Ok(world)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            let mut world = World::default();
            match fs::read(dir.join(MIRROR)) {
                Ok(bytes) => {
                    world.app = serde_json::from_slice(&bytes).map_err(|_| "app_unavailable")?;
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                Err(_) => return Err("app_unavailable"),
            }
            Ok(world)
        }
        Err(_) => Err("world_unavailable"),
    }
}

/// Saves `world` atomically after validation, and refreshes the `app.json` mirror.
fn save(dir: &Path, world: &World) -> Result<(), &'static str> {
    validate(world)?;
    let bytes = serde_json::to_vec(world).map_err(|_| "world_write_failed")?;
    if bytes.len() > MAX_FILE {
        return Err("world_too_large");
    }
    let mirror = serde_json::to_vec(&world.app).map_err(|_| "world_write_failed")?;
    write_private(dir, FILE, &bytes)?;
    write_private(dir, MIRROR, &mirror)
}

/// Read-only access under the process lock.
pub fn read<T>(
    dir: &Path,
    f: impl FnOnce(&World) -> Result<T, &'static str>,
) -> Result<T, &'static str> {
    let _guard = LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let world = load(dir)?;
    f(&world)
}

/// Read-modify-write. The closure may refuse (nothing is written). A successful write is re-read
/// and compared with the intended world; a mismatch is `verify_failed`.
pub fn mutate<T>(
    dir: &Path,
    f: impl FnOnce(&mut World) -> Result<T, &'static str>,
) -> Result<T, &'static str> {
    let _guard = LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let mut world = load(dir)?;
    let value = f(&mut world)?;
    save(dir, &world)?;
    if load(dir)? != world {
        return Err("verify_failed");
    }
    Ok(value)
}

/// Typed service request. Built only by `parse`, so every field is already validated.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Op {
    Capture,
    Tree,
    Click { epoch: u64, element: String },
    Focus { epoch: u64, element: String },
    Type { epoch: u64, text: String },
    Key { epoch: u64, key: String },
    AudioRoutes,
    AudioState,
    SetRoute { route: String },
    AppVolume { app: String, volume: u8 },
    Eq { preset: String },
    Denoise { enabled: bool },
    MicState,
    Configure { gain: u8, filter: String },
    Monitor { enabled: bool },
    RecordStart,
    RecordStop,
    CamState,
    OptIn { enabled: bool },
    CamCapture,
    Gestures,
}

impl Op {
    /// Screen epoch the caller saw, for services that act on the screen.
    pub fn epoch(&self) -> Option<u64> {
        match self {
            Op::Click { epoch, .. }
            | Op::Focus { epoch, .. }
            | Op::Type { epoch, .. }
            | Op::Key { epoch, .. } => Some(*epoch),
            _ => None,
        }
    }
}

/// Strict argument shape: exactly these keys, no others.
fn exact_keys(object: &Map<String, Value>, keys: &[&str]) -> Result<(), &'static str> {
    if object.len() == keys.len() && keys.iter().all(|key| object.contains_key(*key)) {
        Ok(())
    } else {
        Err("invalid_args")
    }
}

/// Parses and validates the arguments of one service (name without `synthetic.`).
pub fn parse(service: &str, args: &Value) -> Result<Op, &'static str> {
    let keys: &[&str] = match service {
        "screen.capture" | "input.a11y_tree" | "audio.routes" | "audio.state" | "mic.state"
        | "mic.record_start" | "mic.record_stop" | "camera.state" | "camera.capture"
        | "camera.gestures" => &[],
        "input.click" | "input.focus" => &["epoch", "element"],
        "input.type" => &["epoch", "text"],
        "input.key" => &["epoch", "key"],
        "audio.set_route" => &["route"],
        "audio.app_volume" => &["app", "volume"],
        "audio.eq" => &["preset"],
        "audio.denoise" | "mic.monitor" | "camera.optin" => &["enabled"],
        "mic.configure" => &["gain", "filter"],
        _ => return Err("unknown_service"),
    };
    let object = args.as_object().ok_or("invalid_args")?;
    exact_keys(object, keys)?;
    let epoch = || {
        object
            .get("epoch")
            .and_then(Value::as_u64)
            .ok_or("invalid_args")
    };
    let ident = |key: &str| {
        object
            .get(key)
            .and_then(Value::as_str)
            .filter(|v| ident_ok(v))
            .map(str::to_owned)
            .ok_or("invalid_args")
    };
    let choice = |key: &str, list: &[&str]| {
        object
            .get(key)
            .and_then(Value::as_str)
            .filter(|v| list.contains(v))
            .map(str::to_owned)
            .ok_or("invalid_args")
    };
    let text = || {
        object
            .get("text")
            .and_then(Value::as_str)
            .filter(|v| plain(v, TEXT_MAX))
            .map(str::to_owned)
            .ok_or("invalid_args")
    };
    let flag = |key: &str| {
        object
            .get(key)
            .and_then(Value::as_bool)
            .ok_or("invalid_args")
    };
    let level = |key: &str| {
        object
            .get(key)
            .and_then(Value::as_u64)
            .filter(|v| *v <= 100)
            .map(|v| v as u8)
            .ok_or("invalid_args")
    };
    Ok(match service {
        "screen.capture" => Op::Capture,
        "input.a11y_tree" => Op::Tree,
        "input.click" => Op::Click {
            epoch: epoch()?,
            element: ident("element")?,
        },
        "input.focus" => Op::Focus {
            epoch: epoch()?,
            element: ident("element")?,
        },
        "input.type" => Op::Type {
            epoch: epoch()?,
            text: text()?,
        },
        "input.key" => Op::Key {
            epoch: epoch()?,
            key: choice("key", &KEYS)?,
        },
        "audio.routes" => Op::AudioRoutes,
        "audio.state" => Op::AudioState,
        "audio.set_route" => Op::SetRoute {
            route: ident("route")?,
        },
        "audio.app_volume" => Op::AppVolume {
            app: ident("app")?,
            volume: level("volume")?,
        },
        "audio.eq" => Op::Eq {
            preset: choice("preset", &EQ_PRESETS)?,
        },
        "audio.denoise" => Op::Denoise {
            enabled: flag("enabled")?,
        },
        "mic.state" => Op::MicState,
        "mic.configure" => Op::Configure {
            gain: level("gain")?,
            filter: choice("filter", &MIC_FILTERS)?,
        },
        "mic.monitor" => Op::Monitor {
            enabled: flag("enabled")?,
        },
        "mic.record_start" => Op::RecordStart,
        "mic.record_stop" => Op::RecordStop,
        "camera.state" => Op::CamState,
        "camera.optin" => Op::OptIn {
            enabled: flag("enabled")?,
        },
        "camera.capture" => Op::CamCapture,
        _ => Op::Gestures,
    })
}

fn sha_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn value<T: Serialize>(item: &T) -> Result<Value, &'static str> {
    serde_json::to_value(item).map_err(|_| "world_unavailable")
}

fn fresh(world: &World, epoch: u64) -> Result<(), &'static str> {
    if world.screen.epoch == epoch {
        Ok(())
    } else {
        Err("stale_screen")
    }
}

fn bump(world: &mut World) {
    world.screen.epoch = world.screen.epoch.saturating_add(1);
}

fn find_element<'a>(world: &'a World, id: &str) -> Result<&'a Element, &'static str> {
    world
        .screen
        .elements
        .iter()
        .find(|element| element.id == id)
        .ok_or("unknown_element")
}

/// Mutating service: re-read verification happens in `mutate`; the reply says `verified:true`.
fn write(
    dir: &Path,
    f: impl FnOnce(&mut World) -> Result<Value, &'static str>,
) -> Result<Value, &'static str> {
    let mut reply = mutate(dir, f)?;
    if let Some(object) = reply.as_object_mut() {
        object.insert("verified".into(), json!(true));
    }
    Ok(reply)
}

/// Runs one parsed service against the world in `dir`. Writes are verified before replying.
fn run(dir: &Path, op: &Op) -> Result<Value, &'static str> {
    match op {
        Op::Capture => read(dir, |w| {
            let bytes = serde_json::to_vec(&w.screen).map_err(|_| "world_unavailable")?;
            let regions: Vec<Value> = w
                .screen
                .elements
                .iter()
                .take(REGION_MAX)
                .map(|e| json!({"role": e.role, "name": e.name, "x": e.x, "y": e.y}))
                .collect();
            Ok(json!({
                "epoch": w.screen.epoch,
                "width": w.screen.width,
                "height": w.screen.height,
                "sha256": sha_hex(&bytes),
                "regions": regions,
                "truncated": w.screen.elements.len() > REGION_MAX,
            }))
        }),
        Op::Tree => read(dir, |w| {
            // `focused` is part of the a11y tree contract: the element the next `type` or `key` lands on.
            let elements: Vec<Value> = w
                .screen
                .elements
                .iter()
                .take(REGION_MAX)
                .map(|e| {
                    json!({
                        "id": e.id,
                        "role": e.role,
                        "name": e.name,
                        "x": e.x,
                        "y": e.y,
                        "focused": w.screen.focus.as_deref() == Some(e.id.as_str()),
                    })
                })
                .collect();
            Ok(json!({
                "epoch": w.screen.epoch,
                "elements": elements,
                "truncated": w.screen.elements.len() > REGION_MAX,
            }))
        }),
        Op::Click { epoch, element } => write(dir, |w| {
            fresh(w, *epoch)?;
            find_element(w, element)?;
            w.screen.last_click = Some(element.clone());
            bump(w);
            Ok(json!({"element": element, "epoch": w.screen.epoch}))
        }),
        Op::Focus { epoch, element } => write(dir, |w| {
            fresh(w, *epoch)?;
            find_element(w, element)?;
            w.screen.focus = Some(element.clone());
            bump(w);
            Ok(json!({"focus": element, "epoch": w.screen.epoch}))
        }),
        Op::Type { epoch, text } => write(dir, |w| {
            fresh(w, *epoch)?;
            let focused = w
                .screen
                .focus
                .as_deref()
                .and_then(|id| w.screen.elements.iter().find(|e| e.id == id));
            if focused.is_none_or(|e| e.role != "textbox") {
                return Err("no_focus");
            }
            w.screen.text = text.clone();
            bump(w);
            Ok(json!({"text": text, "epoch": w.screen.epoch}))
        }),
        Op::Key { epoch, key } => write(dir, |w| {
            fresh(w, *epoch)?;
            w.screen.last_key = Some(key.clone());
            bump(w);
            Ok(json!({"key": key, "epoch": w.screen.epoch}))
        }),
        Op::AudioRoutes => read(dir, |w| {
            Ok(json!({"routes": w.audio.routes, "route": w.audio.route}))
        }),
        Op::AudioState => read(dir, |w| value(&w.audio)),
        Op::SetRoute { route } => write(dir, |w| {
            if !w.audio.routes.contains(route) {
                return Err("unknown_route");
            }
            w.audio.route = route.clone();
            Ok(json!({"route": route}))
        }),
        Op::AppVolume { app, volume } => write(dir, |w| {
            let target = w
                .audio
                .apps
                .iter_mut()
                .find(|item| item.id == *app)
                .ok_or("unknown_app")?;
            target.volume = *volume;
            Ok(json!({"app": app, "volume": volume}))
        }),
        Op::Eq { preset } => write(dir, |w| {
            w.audio.eq = preset.clone();
            Ok(json!({"eq": preset}))
        }),
        Op::Denoise { enabled } => write(dir, |w| {
            w.audio.denoise = *enabled;
            Ok(json!({"denoise": enabled}))
        }),
        Op::MicState => read(dir, |w| value(&w.mic)),
        Op::Configure { gain, filter } => write(dir, |w| {
            w.mic.gain = *gain;
            w.mic.filter = filter.clone();
            value(&w.mic)
        }),
        Op::Monitor { enabled } => write(dir, |w| {
            w.mic.monitor = *enabled;
            w.mic.indicator = *enabled || w.mic.recording;
            value(&w.mic)
        }),
        Op::RecordStart => write(dir, |w| {
            if w.mic.recording {
                return Err("already_recording");
            }
            if !w.mic.indicator {
                return Err("indicator_off");
            }
            w.mic.recording = true;
            value(&w.mic)
        }),
        Op::RecordStop => write(dir, |w| {
            if !w.mic.recording {
                return Err("not_recording");
            }
            w.mic.recording = false;
            w.mic.indicator = w.mic.monitor;
            value(&w.mic)
        }),
        Op::CamState => read(dir, |w| value(&w.camera)),
        Op::OptIn { enabled } => write(dir, |w| {
            w.camera.opt_in = *enabled;
            w.camera.indicator = *enabled;
            if !enabled {
                // Opting out clears the frames and the gesture state.
                w.camera.frame_seq = 0;
                w.camera.gesture = None;
            }
            value(&w.camera)
        }),
        Op::CamCapture => write(dir, |w| {
            if !w.camera.opt_in {
                return Err("opt_in_required");
            }
            w.camera.frame_seq = w.camera.frame_seq.saturating_add(1);
            let seq = w.camera.frame_seq;
            Ok(json!({
                "frame_seq": seq,
                "width": 640,
                "height": 480,
                "sha256": sha_hex(format!("frame:{seq}").as_bytes()),
                "indicator": true,
            }))
        }),
        Op::Gestures => read(dir, |w| {
            if !w.camera.opt_in {
                return Err("opt_in_required");
            }
            Ok(json!({"supported": GESTURES, "current": w.camera.gesture}))
        }),
    }
}

/// Executes one synthetic service call: strict args, the operation, then the reply cap.
/// The caller has already checked the flag and the permission.
pub fn serve(dir: &Path, service: &str, args: &Value) -> Result<Value, &'static str> {
    if args.to_string().len() > MAX_ARGS {
        return Err("invalid_args");
    }
    let op = parse(service, args)?;
    let mut reply = run(dir, &op)?;
    if let Some(object) = reply.as_object_mut() {
        object.insert("backend".into(), json!("synthetic"));
    }
    let bytes = serde_json::to_vec(&reply).map_err(|_| "world_unavailable")?;
    if bytes.len() > MAX_REPLY {
        return Err("reply_too_large");
    }
    Ok(reply)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_world_is_valid_and_round_trips() {
        let world = World::default();
        validate(&world).unwrap();
        let bytes = serde_json::to_vec(&world).unwrap();
        let back: World = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(back, world);
    }

    #[test]
    fn unknown_fields_and_bad_invariants_are_refused() {
        let mut value = serde_json::to_value(World::default()).unwrap();
        value["extra"] = json!(1);
        assert!(serde_json::from_value::<World>(value).is_err());
        let mut world = World::default();
        world.mic.indicator = true;
        assert_eq!(validate(&world), Err("world_invalid"));
        let mut world = World::default();
        world.audio.route = "nope".into();
        assert_eq!(validate(&world), Err("world_invalid"));
    }

    #[test]
    fn arguments_are_exact_and_typed() {
        assert!(parse("input.click", &json!({"epoch": 1, "element": "apply"})).is_ok());
        assert_eq!(
            parse("input.click", &json!({"epoch": 1})),
            Err("invalid_args")
        );
        assert_eq!(
            parse(
                "input.click",
                &json!({"epoch": 1, "element": "apply", "x": 1})
            ),
            Err("invalid_args")
        );
        assert_eq!(
            parse("input.type", &json!({"epoch": 1, "text": "a\u{7}"})),
            Err("invalid_args")
        );
        assert_eq!(
            parse("audio.app_volume", &json!({"app": "player", "volume": 101})),
            Err("invalid_args")
        );
        assert_eq!(parse("nope.x", &json!({})), Err("unknown_service"));
    }

    #[test]
    fn every_service_has_a_permission_and_audit_family() {
        for (name, permission) in SERVICES {
            assert_eq!(super::permission(name), Some(permission));
            assert_ne!(audit_kind(name), "synthetic_action", "{name}");
        }
        assert_eq!(super::permission("screen.capture"), Some("screen_observe"));
        assert_eq!(super::permission("base.write"), None);
    }

    #[test]
    fn legacy_app_file_migrates_into_the_world() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(
            dir.path().join(MIRROR),
            br#"{"epoch":4,"counter":7,"text":"hi","published":false}"#,
        )
        .unwrap();
        let world = load(dir.path()).unwrap();
        assert_eq!((world.app.epoch, world.app.counter), (4, 7));
        assert_eq!(world.screen.epoch, 1);
    }
}
