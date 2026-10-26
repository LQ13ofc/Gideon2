#!/usr/bin/env python3
"""Real C4 perception and device worker (WP-12). One payload serves the seven perception plugins.

The Core sends the plugin_id in `hello`; the worker then answers only that plugin's capabilities
(PLUGINS). Protocol: JSON-lines v1 on stdin/stdout (docs/C0.md): hello, invoke, cancel, shutdown.
There is no host_call: these backends act on the desktop directly, so the sandbox must give this
process exactly the access in PLUGIN_ACCESS (docs/WP12p.md lists the Core change that is needed).

Backends, all real on the owner's KDE Plasma Wayland session:
- screen_observe: org.freedesktop.portal.Screenshot (interactive=false). The PNG is hashed and deleted.
- computer_control: AT-SPI tree of the active window. Keys and text go through the RemoteDesktop
  portal keyboard device. `type` is verified by reading the focused AT-SPI text back.
- audio_advanced: PipeWire graph via pw-dump. Default output route via wpctl set-default, and volume
  of application streams via wpctl (sinks and sources are refused).
- mic_advanced: default source gain via wpctl. `record` meters the microphone with pw-record for at
  most MAX_RECORD_S and keeps no audio. `monitor` is refused: a live loop to the speakers would feed back.
- camera_gesture: v4l2 capture node through ffmpeg, one gray 160x120 frame, nothing kept. Opt-in is
  required and held in memory only. Gesture recognition has no model: refused.
- display_manipulate: kscreen-doctor for outputs, scale and brightness. Every change is recorded and
  `restore` (also run at shutdown) puts the previous values back.
- shortcut_global: org.freedesktop.portal.GlobalShortcuts. Activated events are queued for `events`.

Refusals that are not errors (no backend, no model, no path) are ok outputs with "supported": false.
Error codes are the pass-through set of src/plugins.rs (PASS_THROUGH_ERRORS) plus the two codes that the
Core must add for this worker (backend_unavailable, unsupported; see docs/WP12p.md).
"""
import hashlib
import json
import os
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import wave

try:  # PyGObject: portal signals and AT-SPI. Missing => those backends report backend_unavailable.
    import gi
    gi.require_version("Gio", "2.0")
    gi.require_version("GLib", "2.0")
    from gi.repository import Gio, GLib
except Exception:  # pragma: no cover - depends on the host
    gi = None
    Gio = None
    GLib = None

PROTOCOL = 1
MAX_LINE = 65536
MAX_OUTPUT = 8192
IDLE_TICK = 0.2
MAX_RECORD_S = 10
MAX_EVENTS = 16
MAX_ELEMENTS = 64
MAX_NODES_VISIT = 800
MAX_STREAMS = 16
MAX_SINKS = 8
MAX_TYPE_CHARS = 64
MAX_TEXT = 128
MAX_SHOT_BYTES = 64 * 1024 * 1024
PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_OBJ = "/org/freedesktop/portal/desktop"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SESSION_IFACE = "org.freedesktop.portal.Session"
SHOT_IFACE = "org.freedesktop.portal.Screenshot"
RD_IFACE = "org.freedesktop.portal.RemoteDesktop"
GS_IFACE = "org.freedesktop.portal.GlobalShortcuts"
PORTAL_BIND_TIMEOUT = 20.0
KGA_DEST = "org.kde.kglobalaccel"
KGA_OBJ = "/kglobalaccel"
KGA_IFACE = "org.kde.KGlobalAccel"
KGA_COMP_IFACE = "org.kde.kglobalaccel.Component"
KGA_COMPONENT = "gideon_perception"
MAX_INT = 2 ** 31 - 1
PNG_SIG = b"\x89PNG\r\n\x1a\n"
ID_RE = re.compile(r"[a-z][a-z0-9_]{0,31}")
TRIGGER_RE = re.compile(r"[A-Za-z0-9+_ ]{1,32}")
OUTPUT_NAME_RE = re.compile(r"[A-Za-z0-9._-]{1,32}")
DISPLAY_SCALES = (100, 125, 150, 175, 200)
PLUGIN_ACCESS = {
    "screen_observe": "session D-Bus (xdg-desktop-portal Screenshot)",
    "computer_control": "session D-Bus (AT-SPI bus, RemoteDesktop portal), PipeWire not needed",
    "audio_advanced": "PipeWire socket (pw-dump, wpctl)",
    "mic_advanced": "PipeWire socket (wpctl, pw-record)",
    "camera_gesture": "/dev/video* (ffmpeg v4l2), /sys/class/video4linux",
    "display_manipulate": "session D-Bus and KWin config (kscreen-doctor)",
    "shortcut_global": "session D-Bus (xdg-desktop-portal GlobalShortcuts)",
}
PLUGINS = {
    "screen_observe": ["screen_observe.capture", "screen_observe.status"],
    "computer_control": ["computer_control.tree", "computer_control.act", "computer_control.status"],
    "audio_advanced": ["audio_advanced.state", "audio_advanced.act"],
    "mic_advanced": ["mic_advanced.state", "mic_advanced.configure", "mic_advanced.monitor",
                     "mic_advanced.record"],
    "camera_gesture": ["camera_gesture.state", "camera_gesture.optin", "camera_gesture.capture",
                       "camera_gesture.gestures"],
    "display_manipulate": ["display_manipulate.status", "display_manipulate.act",
                           "display_manipulate.restore"],
    "shortcut_global": ["shortcut_global.status", "shortcut_global.bind", "shortcut_global.events"],
}


class _Fail(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class _Cancel(Exception):
    pass


class _Shutdown(Exception):
    pass


# ---------------------------------------------------------------- stdin/stdout protocol

_buf = bytearray()
_discarding = False
_plugin = None
_running = None
_seq = 0


def _send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _log(text):
    """Diagnostics to stderr only (the Core keeps a tail for the owner's diagnostics)."""
    sys.stderr.write(_clean(text, 300) + "\n")
    sys.stderr.flush()


def _size(obj):
    return len(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _take_line():
    global _discarding
    while True:
        newline = _buf.find(b"\n")
        if newline < 0:
            if len(_buf) > MAX_LINE:
                _buf.clear()
                _discarding = True
            return None
        line = bytes(_buf[:newline])
        del _buf[: newline + 1]
        if _discarding:
            _discarding = False
            continue
        if len(line) > MAX_LINE:
            continue
        return line


def _parse(line):
    try:
        msg = json.loads(line)
    except ValueError:
        return None
    return msg if isinstance(msg, dict) else None


def _read_chunk(timeout):
    """Read what stdin has (waiting up to timeout; None = forever). Raises EOFError at end of input."""
    fd = sys.stdin.fileno()
    readable, _, _ = select.select([fd], [], [], timeout)
    if not readable:
        return
    chunk = os.read(fd, 65536)
    if not chunk:
        raise EOFError
    _buf.extend(chunk)


def _pump(timeout):
    """While a request runs: cancel of that request raises _Cancel, shutdown raises _Shutdown, any other
    invoke is answered busy, and everything else is ignored."""
    _read_chunk(timeout)
    while True:
        line = _take_line()
        if line is None:
            return
        msg = _parse(line)
        if msg is None:
            continue
        op = msg.get("op")
        if op == "cancel" and _running is not None and msg.get("id") == _running:
            raise _Cancel()
        if op == "shutdown":
            raise _Shutdown()
        if op == "invoke" and isinstance(msg.get("id"), int) and not isinstance(msg.get("id"), bool):
            _send({"id": msg["id"], "ok": False, "error": "busy"})


def _idle():
    """Dispatch pending GLib events (portal signals) while the worker waits for the Core."""
    if GLib is None:
        return
    ctx = GLib.MainContext.default()
    while ctx.pending():
        ctx.iteration(False)


def _next_message():
    while True:
        line = _take_line()
        if line is not None:
            msg = _parse(line)
            if msg is not None:
                return msg
            continue
        _idle()
        _read_chunk(IDLE_TICK if GLib is not None else None)
        _expire_recording()


# ---------------------------------------------------------------- helpers

def _next_epoch():
    global _seq
    _seq += 1
    return (int(time.time()) * 1000 + _seq) % MAX_INT


def _clean(text, limit):
    """PlainText: no control characters, at most `limit` UTF-8 bytes."""
    cleaned = "".join(ch for ch in str(text) if ord(ch) >= 32 and ord(ch) != 127)
    return cleaned.encode("utf-8")[:limit].decode("utf-8", "ignore")


def _only(inp, keys):
    if not isinstance(inp, dict) or not set(inp) <= set(keys):
        raise _Fail("invalid_input")


def _int_field(inp, key, low, high):
    value = inp.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise _Fail("invalid_input")
    return value


def _str_field(inp, key, pattern):
    value = inp.get(key)
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise _Fail("invalid_input")
    return value


PIPEWIRE_TOOLS = ("wpctl", "pw-dump", "pw-record")


def _pipewire_reachable():
    """WP-18a: without the PipeWire socket the tools fail with a generic error; name the missing backend instead."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    return bool(runtime) and os.path.exists(os.path.join(runtime, "pipewire-0"))


def _run(argv, timeout=10.0, input_bytes=None, binary=False):
    """Run an absolute-path tool. Returns (rc, stdout). Missing tool or missing socket => backend_unavailable."""
    exe = shutil.which(argv[0])
    if exe is None:
        raise _Fail("backend_unavailable")
    if argv[0] in PIPEWIRE_TOOLS and not _pipewire_reachable():
        raise _Fail("backend_unavailable")
    try:
        proc = subprocess.run([exe] + [str(arg) for arg in argv[1:]], input=input_bytes, capture_output=True,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise _Fail("timeout")
    except OSError:
        raise _Fail("plugin_error")
    out = proc.stdout if binary else proc.stdout.decode("utf-8", "replace")
    return proc.returncode, out


def _wpctl_volume(target):
    rc, out = _run(["wpctl", "get-volume", target])
    match = re.search(r"Volume:\s*([0-9]+(?:\.[0-9]+)?)", out)
    if rc != 0 or not match:
        raise _Fail("plugin_error")
    return float(match.group(1)), "[MUTED]" in out


def _wpctl_set_volume(target, fraction, limit=None):
    argv = ["wpctl", "set-volume"]
    if limit is not None:
        argv += ["-l", "%.2f" % limit]
    rc, _ = _run(argv + [str(target), "%.2f" % fraction])
    if rc != 0:
        raise _Fail("plugin_error")


def _pw_dump():
    rc, out = _run(["pw-dump"], timeout=15)
    if rc != 0:
        raise _Fail("plugin_error")
    try:
        data = json.loads(out)
    except ValueError:
        raise _Fail("plugin_error")
    return data if isinstance(data, list) else []


def _pw_defaults(objects):
    """Return (default_sink_name, default_source_name) from the PipeWire default metadata."""
    sink = source = None
    for obj in objects:
        if obj.get("type") != "PipeWire:Interface:Metadata":
            continue
        if (obj.get("props") or {}).get("metadata.name") != "default":
            continue
        for entry in obj.get("metadata") or []:
            value = (entry.get("value") or {}).get("name") if isinstance(entry.get("value"), dict) else None
            if entry.get("key") == "default.audio.sink":
                sink = value
            elif entry.get("key") == "default.audio.source":
                source = value
    return sink, source


def _pw_nodes(objects, media_class):
    out = []
    for obj in objects:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        info = obj.get("info") or {}
        props = info.get("props") or {}
        if props.get("media.class") == media_class:
            out.append((obj.get("id"), props))
    return out


def _png_size(data):
    if len(data) < 24 or data[:8] != PNG_SIG or data[12:16] != b"IHDR":
        raise _Fail("plugin_error")
    return struct.unpack(">II", data[16:24])


# ---------------------------------------------------------------- portal (D-Bus)

class _Portal:
    """Calls to xdg-desktop-portal. Request responses are matched by the token we chose."""

    def __init__(self):
        if Gio is None:
            raise _Fail("backend_unavailable")
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception:
            raise _Fail("backend_unavailable")
        self.sender = self.bus.get_unique_name()[1:].replace(".", "_")
        self.count = 0

    def has(self, iface):
        """True when the portal answers the interface's version property."""
        try:
            self.bus.call_sync(PORTAL, PORTAL_OBJ, "org.freedesktop.DBus.Properties", "Get",
                               GLib.Variant("(ss)", (iface, "version")), None,
                               Gio.DBusCallFlags.NONE, 3000, None)
            return True
        except Exception:
            return False

    def call(self, iface, method, fmt, vals, path=PORTAL_OBJ, dest=PORTAL):
        try:
            ret = self.bus.call_sync(dest, path, iface, method, GLib.Variant(fmt, vals), None,
                                     Gio.DBusCallFlags.NONE, 10000, None)
        except Exception as err:
            _log("%s.%s failed: %s" % (iface, method, err))
            raise _Fail("backend_unavailable")
        return ret.unpack()

    def request(self, iface, method, pos, opts, timeout=60.0):
        """Call a portal method that answers with a Request. Returns (response_code, results dict)."""
        self.count += 1
        token = "gideon_%d_%d" % (os.getpid(), self.count)
        got = []

        def on_response(conn, sender, path, name, signal_name, params, user_data):
            if path.endswith("/" + token):
                got.append(params.unpack())

        sub = self.bus.signal_subscribe(PORTAL, REQUEST_IFACE, "Response", None, None,
                                        Gio.DBusSignalFlags.NONE, on_response, None)
        try:
            options = dict(opts)
            options["handle_token"] = GLib.Variant("s", token)
            fmt = "(" + "".join(f for f, _ in pos) + "a{sv})"
            vals = tuple(v for _, v in pos) + (options,)
            self.call(iface, method, fmt, vals, path=PORTAL_OBJ, dest=PORTAL)
            ctx = GLib.MainContext.default()
            deadline = time.monotonic() + timeout
            while not got:
                if time.monotonic() > deadline:
                    raise _Fail("timeout")
                ctx.iteration(False)
                _pump(0.02)
        finally:
            self.bus.signal_unsubscribe(sub)
        code, results = got[0]
        return code, results


_portal_obj = None


def _portal():
    global _portal_obj
    if _portal_obj is None:
        _portal_obj = _Portal()
    return _portal_obj


# ---------------------------------------------------------------- screen_observe

def _screen_status(_inp):
    if Gio is None:
        return {"backend": "portal", "available": False, "reason": "pygobject_missing"}
    ok = _portal().has(SHOT_IFACE)
    return {"backend": "portal", "available": ok, "reason": "ok" if ok else "portal_missing"}


def _screen_capture(_inp):
    portal = _portal()
    code, res = portal.request(SHOT_IFACE, "Screenshot", [("s", "")],
                               {"interactive": GLib.Variant("b", False)}, timeout=30.0)
    if code == 1:
        raise _Fail("cancelled")
    uri = res.get("uri") if code == 0 else None
    if not isinstance(uri, str) or not uri.startswith("file://"):
        raise _Fail("plugin_error")
    path = urllib.parse.unquote(urllib.parse.urlparse(uri).path)
    try:
        with open(path, "rb") as fh:
            data = fh.read(MAX_SHOT_BYTES + 1)
        if len(data) > MAX_SHOT_BYTES:
            raise _Fail("response_too_large")
        width, height = _png_size(data)
    finally:
        # The portal writes the PNG into the user's pictures folder; the worker keeps nothing.
        try:
            os.unlink(path)
        except OSError:
            pass
    return {"backend": "portal", "epoch": _next_epoch(), "width": width, "height": height,
            "sha256": hashlib.sha256(data).hexdigest(), "regions": []}


# ---------------------------------------------------------------- computer_control (AT-SPI + RemoteDesktop)

_atspi_mod = None
_nodes = []
_tree = {"epoch": 0, "window": ""}
_rd_session = None
_rd_failed = None

KEYSYMS = {"Return": 0xff0d, "Escape": 0xff1b, "Tab": 0xff09, "BackSpace": 0xff08,
           "Left": 0xff51, "Up": 0xff52, "Right": 0xff53, "Down": 0xff54, "space": 0x20}
KEY_RE = re.compile(r"[A-Za-z0-9]|Return|Escape|Tab|BackSpace|Left|Up|Right|Down|space")


def _a11y_bus_answers():
    """WP-18a: AT-SPI aborts the whole process ("Couldn't connect to accessibility bus") when no accessibility bus
    answers, so the session bus is asked for the a11y address first. No answer is backend_unavailable."""
    if Gio is None:
        raise _Fail("backend_unavailable")
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress", None, None,
                              Gio.DBusCallFlags.NONE, 3000, None)
    except Exception:
        raise _Fail("backend_unavailable")
    address = reply.unpack()[0]
    if not isinstance(address, str) or not address.startswith("unix:"):
        raise _Fail("backend_unavailable")


def _atspi():
    global _atspi_mod
    if _atspi_mod is None:
        if gi is None:
            raise _Fail("backend_unavailable")
        _a11y_bus_answers()
        try:
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
        except Exception:
            raise _Fail("backend_unavailable")
        Atspi.init()
        _atspi_mod = Atspi
    return _atspi_mod


def _active_window(atspi):
    """The window that holds keyboard focus. Several toolkits leave a stale ACTIVE flag on other windows,
    so a candidate wins only when it contains the focused accessible; without one, the first candidate."""
    candidates = []
    desk = atspi.get_desktop(0)
    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if app is None:
            continue
        for j in range(app.get_child_count()):
            win = app.get_child_at_index(j)
            if win is None:
                continue
            states = win.get_state_set()
            if states.contains(atspi.StateType.ACTIVE) or states.contains(atspi.StateType.FOCUSED):
                candidates.append(win)
    for win in candidates:
        if _find_focused(atspi, win) is not None:
            return win
    return candidates[0] if candidates else None


def _bfs(root, visit):
    """Breadth-first walk of at most MAX_NODES_VISIT accessibles; visit(node) returns False to stop."""
    queue = [root]
    seen = 0
    while queue and seen < MAX_NODES_VISIT:
        node = queue.pop(0)
        seen += 1
        if visit(node) is False:
            return
        for k in range(node.get_child_count()):
            child = node.get_child_at_index(k)
            if child is not None:
                queue.append(child)


def _text_of(atspi, node):
    """Text content of an accessible through the Atspi.Text interface (the Accessible-level getter returns
    the same object under a name clash, so the interface class is called explicitly)."""
    iface = node.get_text_iface()
    if iface is None:
        return None
    count = atspi.Text.get_character_count(iface)
    return atspi.Text.get_text(iface, 0, min(count, 4096))


def _cc_status(_inp):
    # Only the keys the bridge's availability rule accepts (backend, available, reason).
    try:
        atspi = _atspi()
    except _Fail as fail:
        return {"backend": "atspi", "available": False, "reason": fail.code}
    if _active_window(atspi) is None:
        return {"backend": "atspi", "available": False, "reason": "no_active_window"}
    return {"backend": "atspi", "available": True, "reason": "ok"}


def _cc_tree(_inp):
    atspi = _atspi()
    win = _active_window(atspi)
    if win is None:
        raise _Fail("no_focus")
    found = []
    roles = ("push button", "text", "entry", "check box", "menu item", "link", "combo box",
             "list item", "page tab", "toggle button", "label", "heading")

    def visit(node):
        if len(found) >= MAX_ELEMENTS:
            return False
        name = node.get_name() or ""
        role = node.get_role_name() or ""
        if not name and role not in roles:
            return True
        comp = node.get_component_iface() if hasattr(node, "get_component_iface") else None
        if comp is None:
            return True
        rect = comp.get_extents(atspi.CoordType.SCREEN)
        if rect.width <= 0 or rect.height <= 0:
            return True
        found.append((node, role, name, rect.x, rect.y))
        return True

    _bfs(win, visit)
    _nodes[:] = [item[0] for item in found]
    _tree["epoch"] = _next_epoch()
    _tree["window"] = _clean(win.get_name() or "", 64)
    elements = []
    for idx, (_node, role, name, x, y) in enumerate(found):
        elements.append({"id": idx, "role": _clean(role, 32) or "element",
                         "name": _clean(name, MAX_TEXT), "x": int(x), "y": int(y)})
    return {"backend": "atspi", "epoch": _tree["epoch"], "window": _tree["window"],
            "elements": elements}


def _rd_open():
    """One RemoteDesktop session (keyboard device) per worker. The portal may ask the user; a refusal is
    permission_denied."""
    global _rd_session, _rd_failed
    if _rd_session is not None:
        return _rd_session
    portal = _portal()
    code, res = portal.request(RD_IFACE, "CreateSession", [],
                               {"session_handle_token": GLib.Variant("s", "gideonrd")})
    if code != 0:
        raise _Fail("permission_denied")
    session = res["session_handle"]
    code, _res = portal.request(RD_IFACE, "SelectDevices", [("o", session)],
                                {"types": GLib.Variant("u", 1)})
    if code != 0:
        portal.call(SESSION_IFACE, "Close", "()", (), path=session)
        raise _Fail("permission_denied")
    code, _res = portal.request(RD_IFACE, "Start", [("o", session), ("s", "")], {})
    if code != 0:
        portal.call(SESSION_IFACE, "Close", "()", (), path=session)
        raise _Fail("permission_denied")
    _rd_session = session
    return session


def _keysym_for(ch):
    code = ord(ch)
    if 0x20 <= code <= 0x7e or 0xa0 <= code <= 0xff:
        return code
    return 0x01000000 + code


def _rd_key(sym):
    session = _rd_open()
    for state in (1, 0):
        _portal().call(RD_IFACE, "NotifyKeyboardKeysym", "(oa{sv}iu)", (session, {}, sym, state))


def _find_focused(atspi, win):
    hit = []

    def visit(node):
        if node.get_state_set().contains(atspi.StateType.FOCUSED):
            hit.append(node)
            return False
        return True

    _bfs(win, visit)
    return hit[0] if hit else None


def _cc_focused(atspi):
    win = _active_window(atspi)
    if win is None:
        raise _Fail("no_focus")
    node = _find_focused(atspi, win)
    if node is None:
        raise _Fail("no_focus")
    return node


def _cc_act(inp):
    _only(inp, ("kind", "epoch", "text", "key"))
    kind = inp.get("kind")
    if kind not in ("type", "key"):
        raise _Fail("invalid_input")
    epoch = _int_field(inp, "epoch", 0, MAX_INT)
    # Input shape first, state second: a malformed request is invalid_input whatever the screen is.
    if kind == "key":
        key = inp.get("key")
        if not isinstance(key, str) or not KEY_RE.fullmatch(key):
            raise _Fail("invalid_input")
        sym = KEYSYMS.get(key, ord(key) if len(key) == 1 else None)
    else:
        text = inp.get("text")
        if not isinstance(text, str) or not text or len(text) > MAX_TYPE_CHARS:
            raise _Fail("invalid_input")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
            raise _Fail("invalid_input")
    if _tree["epoch"] == 0 or epoch != _tree["epoch"]:
        raise _Fail("stale_screen")
    atspi = _atspi()
    focused = _cc_focused(atspi)
    if kind == "key":
        _rd_key(sym)
        return {"backend": "remote_desktop", "kind": "key", "injected": 1, "verified": False}
    before = _text_of(atspi, focused)
    for ch in text:
        _rd_key(_keysym_for(ch))
    time.sleep(0.4)
    after = _text_of(atspi, focused)
    verified = after is not None and before is not None and after.count(text) > before.count(text)
    return {"backend": "remote_desktop", "kind": "type", "injected": len(text), "verified": verified}


def _cc_close_session():
    global _rd_session
    if _rd_session is not None:
        try:
            _portal().call(SESSION_IFACE, "Close", "()", (), path=_rd_session)
        except _Fail:
            pass
        _rd_session = None


# ---------------------------------------------------------------- audio_advanced (PipeWire)

def _audio_state(_inp):
    objects = _pw_dump()
    sink_name, _source = _pw_defaults(objects)
    sinks = []
    default_id = None
    for node_id, props in _pw_nodes(objects, "Audio/Sink"):
        if props.get("node.name") == sink_name:
            default_id = node_id
        if len(sinks) < MAX_SINKS:
            sinks.append({"id": node_id, "name": _clean(props.get("node.description") or
                                                          props.get("node.name") or "", 64)})
    streams = []
    for node_id, props in _pw_nodes(objects, "Stream/Output/Audio")[:MAX_STREAMS]:
        volume, _muted = _wpctl_volume(node_id)
        streams.append({"id": node_id, "app": _clean(props.get("application.name") or "", 64),
                        "volume": int(round(volume * 100))})
    return {"backend": "pipewire", "default_sink": default_id if default_id is not None else -1,
            "sinks": sinks, "streams": streams}


def _audio_act(inp):
    _only(inp, ("kind", "sink", "stream", "volume"))
    kind = inp.get("kind")
    if kind == "route":
        _only(inp, ("kind", "sink"))
        target = _int_field(inp, "sink", 1, MAX_INT)
        objects = _pw_dump()
        sinks = {node_id for node_id, _p in _pw_nodes(objects, "Audio/Sink")}
        if target not in sinks:
            raise _Fail("unknown_route")
        before = _audio_state(None)["default_sink"]
        rc, _ = _run(["wpctl", "set-default", str(target)])
        if rc != 0:
            raise _Fail("plugin_error")
        after = _audio_state(None)["default_sink"]
        return {"backend": "pipewire", "kind": "route", "previous": before, "default_sink": after,
                "verified": after == target}
    if kind == "app_volume":
        target = _int_field(inp, "stream", 1, MAX_INT)
        level = _int_field(inp, "volume", 0, 100)
        objects = _pw_dump()
        streams = {node_id for node_id, _p in _pw_nodes(objects, "Stream/Output/Audio")}
        if target not in streams:
            raise _Fail("unknown_app")
        previous, _m = _wpctl_volume(target)
        _wpctl_set_volume(target, level / 100.0)
        now, _m = _wpctl_volume(target)
        return {"backend": "pipewire", "kind": "app_volume", "stream": target,
                "previous": int(round(previous * 100)), "volume": int(round(now * 100)),
                "verified": abs(now - level / 100.0) < 0.011}
    raise _Fail("invalid_input")


# ---------------------------------------------------------------- mic_advanced (PipeWire)

_recording = None  # {"proc": Popen, "dir": str, "path": str, "started": float}


def _mic_state(_inp):
    objects = _pw_dump()
    _sink, source_name = _pw_defaults(objects)
    source_id = -1
    for node_id, props in _pw_nodes(objects, "Audio/Source"):
        if props.get("node.name") == source_name:
            source_id = node_id
    volume, muted = _wpctl_volume("@DEFAULT_AUDIO_SOURCE@")
    return {"backend": "pipewire", "source": source_id, "gain": int(round(volume * 100)),
            "muted": bool(muted), "recording": _recording is not None,
            "indicator": "on" if _recording is not None else "off"}


def _mic_configure(inp):
    _only(inp, ("gain",))
    gain = _int_field(inp, "gain", 0, 150)
    previous, _m = _wpctl_volume("@DEFAULT_AUDIO_SOURCE@")
    _wpctl_set_volume("@DEFAULT_AUDIO_SOURCE@", gain / 100.0, limit=1.5)
    now, _m = _wpctl_volume("@DEFAULT_AUDIO_SOURCE@")
    return {"backend": "pipewire", "previous": int(round(previous * 100)),
            "gain": int(round(now * 100)), "verified": abs(now - gain / 100.0) < 0.011}


def _expire_recording():
    if _recording is not None and time.monotonic() - _recording["started"] > MAX_RECORD_S:
        _stop_recording(keep_result=False)


def _stop_recording(keep_result=True):
    global _recording
    rec, _recording = _recording, None
    result = {"seconds": 0.0, "peak": 0, "rms": 0, "samples": 0}
    try:
        rec["proc"].send_signal(signal.SIGINT)
        try:
            rec["proc"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            rec["proc"].kill()
            rec["proc"].wait(timeout=5)
        if keep_result and os.path.isfile(rec["path"]):
            result = _meter_wav(rec["path"])
    finally:
        try:
            if os.path.isfile(rec["path"]):
                os.unlink(rec["path"])
            os.rmdir(rec["dir"])
        except OSError:
            pass
    return result


def _meter_wav(path):
    try:
        with wave.open(path, "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            width = wav.getsampwidth()
            rate = wav.getframerate() or 1
            count = wav.getnframes()
    except (wave.Error, EOFError, OSError):
        raise _Fail("plugin_error")
    if width != 2 or not frames:
        return {"seconds": 0.0, "peak": 0, "rms": 0, "samples": 0}
    total = 0
    peak = 0
    square = 0
    n = len(frames) // 2
    for i in range(0, n * 2, 2):
        sample = frames[i] | (frames[i + 1] << 8)
        if sample >= 32768:
            sample -= 65536
        mag = abs(sample)
        peak = max(peak, mag)
        square += sample * sample
        total += 1
    rms = (square / total) ** 0.5 if total else 0.0
    return {"seconds": round(count / float(rate), 2), "peak": int(round(peak * 100 / 32768)),
            "rms": int(round(rms * 100 / 32768)), "samples": total}


def _mic_record(inp):
    global _recording
    _only(inp, ("action",))
    action = inp.get("action")
    if action == "start":
        if _recording is not None:
            raise _Fail("already_recording")
        exe = shutil.which("pw-record")
        if exe is None:
            raise _Fail("backend_unavailable")
        directory = tempfile.mkdtemp(prefix="gideon-perc-")
        path = os.path.join(directory, "meter.wav")
        proc = subprocess.Popen([exe, "--rate", "16000", "--channels", "1", "--format", "s16", path],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        _recording = {"proc": proc, "dir": directory, "path": path, "started": time.monotonic()}
        time.sleep(0.3)
        return {"backend": "pipewire", "recording": True, "indicator": "on",
                "max_seconds": MAX_RECORD_S}
    if action == "stop":
        if _recording is None:
            raise _Fail("not_recording")
        meter = _stop_recording(keep_result=True)
        return {"backend": "pipewire", "recording": False, "indicator": "off",
                "seconds": meter["seconds"], "peak": meter["peak"], "rms": meter["rms"],
                "samples": meter["samples"]}
    raise _Fail("invalid_input")


# ---------------------------------------------------------------- camera_gesture (v4l2 via ffmpeg)

_camera_opt_in = False
CAM_W = 160
CAM_H = 120


def _camera_device():
    base = "/sys/class/video4linux"
    if not os.path.isdir(base):
        return None
    for name in sorted(os.listdir(base)):
        if not name.startswith("video"):
            continue
        try:
            with open(os.path.join(base, name, "index"), encoding="ascii") as fh:
                index = fh.read().strip()
        except OSError:
            continue
        if index == "0" and os.path.exists("/dev/" + name):
            return "/dev/" + name
    return None


def _cam_state(_inp):
    device = _camera_device()
    return {"backend": "v4l2", "device": os.path.basename(device) if device else "",
            "present": device is not None, "opt_in": _camera_opt_in,
            "indicator": "on" if _camera_opt_in else "off"}


def _cam_optin(inp):
    global _camera_opt_in
    _only(inp, ("enabled",))
    if not isinstance(inp.get("enabled"), bool):
        raise _Fail("invalid_input")
    _camera_opt_in = inp["enabled"]
    return {"backend": "v4l2", "opt_in": _camera_opt_in,
            "indicator": "on" if _camera_opt_in else "off"}


def _cam_capture(_inp):
    if not _camera_opt_in:
        raise _Fail("opt_in_required")
    device = _camera_device()
    if device is None:
        raise _Fail("backend_unavailable")
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise _Fail("backend_unavailable")
    argv = [exe, "-hide_banner", "-loglevel", "error", "-f", "v4l2", "-video_size", "640x480",
            "-i", device, "-frames:v", "1", "-vf", "scale=%d:%d" % (CAM_W, CAM_H),
            "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    try:
        proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=20,
                              check=False)
    except subprocess.TimeoutExpired:
        raise _Fail("timeout")
    raw = proc.stdout
    if proc.returncode != 0 or len(raw) != CAM_W * CAM_H:
        raise _Fail("plugin_error")
    mean = int(round(sum(raw) / float(len(raw))))
    return {"backend": "v4l2", "width": CAM_W, "height": CAM_H,
            "sha256": hashlib.sha256(raw).hexdigest(), "mean_luma": mean, "indicator": "on"}


def _cam_gestures(_inp):
    return {"backend": "v4l2", "supported": False, "reason": "no_gesture_model_installed"}


# ---------------------------------------------------------------- display_manipulate (kscreen-doctor)

_display_undo = []


def _kscreen_outputs():
    # WP-18a: kscreen-doctor reaches KWin through the Wayland socket and aborts without WAYLAND_DISPLAY (measured).
    if not os.environ.get("WAYLAND_DISPLAY"):
        raise _Fail("backend_unavailable")
    rc, out = _run(["kscreen-doctor", "-j"], timeout=10)
    if rc != 0:
        raise _Fail("plugin_error")
    try:
        data = json.loads(out)
    except ValueError:
        raise _Fail("plugin_error")
    outputs = data.get("outputs")
    if not isinstance(outputs, list):
        raise _Fail("plugin_error")
    return outputs


def _output_by_name(name):
    for item in _kscreen_outputs():
        if item.get("name") == name:
            return item
    raise _Fail("unknown_element")


def _read_setting(name, op):
    item = _output_by_name(name)
    if op == "scale":
        return int(round(float(item.get("scale", 1)) * 100))
    brightness = item.get("brightness")
    if brightness is None:
        raise _Fail("backend_unavailable")
    return int(round(float(brightness) * 100))


def _apply_setting(name, op, value):
    if op == "scale":
        text = "%g" % (value / 100.0)
    else:
        text = str(value)
    rc, _ = _run(["kscreen-doctor", "output.%s.%s.%s" % (name, op, text)], timeout=15)
    if rc != 0:
        raise _Fail("plugin_error")
    now = _read_setting(name, op)
    return now


def _display_status(_inp):
    result = []
    for item in _kscreen_outputs()[:8]:
        brightness = item.get("brightness")
        result.append({"name": _clean(item.get("name") or "", 32),
                       "enabled": bool(item.get("enabled")),
                       "scale": int(round(float(item.get("scale", 1)) * 100)),
                       "brightness": int(round(float(brightness) * 100)) if brightness is not None else -1})
    return {"backend": "kscreen", "outputs": result, "undo_pending": len(_display_undo)}


def _display_act(inp):
    _only(inp, ("output", "op", "value"))
    name = _str_field(inp, "output", OUTPUT_NAME_RE)
    op = inp.get("op")
    if op == "scale":
        value = _int_field(inp, "value", 100, 200)
        if value not in DISPLAY_SCALES:
            raise _Fail("invalid_input")
    elif op == "brightness":
        value = _int_field(inp, "value", 20, 100)
    else:
        raise _Fail("invalid_input")
    previous = _read_setting(name, op)
    _display_undo.append({"output": name, "op": op, "value": previous})
    now = _apply_setting(name, op, value)
    if op == "scale":
        verified = now == value
    else:
        verified = abs(now - value) <= 1
    return {"backend": "kscreen", "output": name, "op": op, "previous": previous, "value": now,
            "verified": verified}


def _display_restore(_inp):
    restored = 0
    verified = True
    while _display_undo:
        entry = _display_undo.pop()
        now = _apply_setting(entry["output"], entry["op"], entry["value"])
        ok = now == entry["value"] if entry["op"] == "scale" else abs(now - entry["value"]) <= 1
        verified = verified and ok
        restored += 1
    return {"backend": "kscreen", "restored": restored, "verified": verified}


# ---------------------------------------------------------------- shortcut_global (GlobalShortcuts portal)

_shortcut_session = None
_shortcut_bound = {}  # id -> {"description", "trigger", "backend": "portal" | "kglobalaccel"}
_shortcut_events = []
_shortcut_sub = None
_kga_sub = None


def _shortcut_on_activated(conn, sender, path, name, signal_name, params, user_data):
    session, shortcut_id, _timestamp, _opts = params.unpack()
    if session != _shortcut_session or len(_shortcut_events) >= MAX_EVENTS:
        return
    # The portal timestamp is not reliable on KDE (it arrives as 0), so the event is stamped on arrival.
    _shortcut_events.append({"id": _clean(shortcut_id, 32), "at_ms": int(time.time() * 1000)})


def _shortcut_ensure():
    global _shortcut_session, _shortcut_sub
    if _shortcut_session is not None:
        return _shortcut_session
    portal = _portal()
    code, res = portal.request(GS_IFACE, "CreateSession", [],
                               {"session_handle_token": GLib.Variant("s", "gideongs")})
    if code != 0:
        raise _Fail("permission_denied")
    _shortcut_session = res["session_handle"]
    _shortcut_sub = portal.bus.signal_subscribe(PORTAL, GS_IFACE, "Activated", PORTAL_OBJ, None,
                                                Gio.DBusSignalFlags.NONE, _shortcut_on_activated, None)
    return _shortcut_session


def _shortcut_status(_inp):
    if Gio is None:
        return {"backend": "portal", "available": False, "reason": "pygobject_missing",
                "bound": 0}
    ok = _portal().has(GS_IFACE)
    return {"backend": "portal", "available": ok, "reason": "ok" if ok else "portal_missing",
            "bound": len(_shortcut_bound)}


def _portal_bind_all(entries):
    """BindShortcuts with the full portal-backed list. Returns the portal response code."""
    session = _shortcut_ensure()
    shortcuts = [(sid, {"description": GLib.Variant("s", item["description"]),
                        "preferred_trigger": GLib.Variant("s", item["trigger"])})
                 for sid, item in sorted(entries.items())]
    code, _res = _portal().request(GS_IFACE, "BindShortcuts",
                                   [("o", session), ("a(sa{sv})", shortcuts), ("s", "")], {},
                                   timeout=PORTAL_BIND_TIMEOUT)
    return code


QT_MODS = {"CTRL": 0x04000000, "ALT": 0x08000000, "SHIFT": 0x02000000, "META": 0x10000000}


def _qt_key_sequence(trigger):
    """'CTRL+ALT+G' -> Qt key code (modifiers | key). Only letters, digits, F1-F12 and space."""
    parts = [p.strip().upper() for p in trigger.split("+")]
    key = parts[-1]
    mods = 0
    for part in parts[:-1]:
        if part not in QT_MODS:
            raise _Fail("invalid_input")
        mods |= QT_MODS[part]
    if len(key) == 1 and key.isalnum():
        code = ord(key)
    elif key == "SPACE":
        code = 0x20
    elif re.fullmatch(r"F([1-9]|1[0-2])", key):
        code = 0x01000030 + int(key[1:]) - 1
    else:
        raise _Fail("invalid_input")
    return mods | code


_kga_connection = None


def _kga_bus():
    """One session connection for the whole process, referenced here: a signal subscription made on a
    connection that is only held by a local variable stopped receiving KDE's signals (measured)."""
    global _kga_connection
    if Gio is None:
        raise _Fail("backend_unavailable")
    if _kga_connection is None:
        try:
            _kga_connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception:
            raise _Fail("backend_unavailable")
    return _kga_connection


def _kga_register(shortcut_id, description, trigger):
    """KGlobalAccel fallback (KDE's own global shortcut service, the one the portal uses on Plasma)."""
    bus = _kga_bus()
    action = [KGA_COMPONENT, shortcut_id, "Gideon", description]
    keys = [_qt_key_sequence(trigger)]
    try:
        bus.call_sync(KGA_DEST, KGA_OBJ, KGA_IFACE, "doRegister",
                      GLib.Variant("(as)", (action,)), None, Gio.DBusCallFlags.NONE, 5000, None)
        bus.call_sync(KGA_DEST, KGA_OBJ, KGA_IFACE, "setShortcut",
                      GLib.Variant("(asaiu)", (action, keys, 0)), None, Gio.DBusCallFlags.NONE,
                      5000, None)
    except Exception as err:
        _log("kglobalaccel register %s failed: %s" % (shortcut_id, err))
        raise _Fail("plugin_error")
    _kga_subscribe(bus)


def _kga_unregister(shortcut_id):
    bus = _kga_bus()
    try:
        bus.call_sync(KGA_DEST, KGA_OBJ, KGA_IFACE, "unRegister",
                      GLib.Variant("(as)", ([KGA_COMPONENT, shortcut_id, "Gideon", ""],)), None,
                      Gio.DBusCallFlags.NONE, 5000, None)
    except Exception:
        pass


def _kga_subscribe(bus):
    global _kga_sub
    if _kga_sub is None:
        # Measured on KDE: a match rule pinned to the sender name or to the object path never delivered
        # this signal, while the interface-only rule did. The callback therefore checks the path itself.
        _kga_sub = bus.signal_subscribe(None, KGA_COMP_IFACE, "globalShortcutPressed", None, None,
                                        Gio.DBusSignalFlags.NONE, _kga_on_pressed, None)


def _kga_on_pressed(conn, sender, path, name, signal_name, params, user_data):
    if path != "/component/" + KGA_COMPONENT or len(_shortcut_events) >= MAX_EVENTS:
        return
    component, shortcut_id = params.unpack()[0], params.unpack()[1]  # (componentUnique, shortcutUnique, ts)
    if component != KGA_COMPONENT:
        return
    if shortcut_id in _shortcut_bound and _shortcut_bound[shortcut_id]["backend"] == "kglobalaccel":
        _shortcut_events.append({"id": _clean(shortcut_id, 32), "at_ms": int(time.time() * 1000)})


def _shortcut_bind(inp):
    _only(inp, ("id", "description", "trigger"))
    shortcut_id = _str_field(inp, "id", ID_RE)
    trigger = _str_field(inp, "trigger", TRIGGER_RE)
    # The bridge binds with {id, trigger} only (WP-17 push-to-talk): the description then has a fixed default.
    description = inp.get("description", "Gideon")
    if not isinstance(description, str) or not 1 <= len(description.encode("utf-8")) <= 64:
        raise _Fail("invalid_input")
    description = _clean(description, 64)
    _qt_key_sequence(trigger)  # refuse an unusable trigger before any backend is touched
    previous = _shortcut_bound.get(shortcut_id)
    # 1) GlobalShortcuts portal, the owner's requested path. A portal that never answers or refuses falls back.
    candidate = dict(_shortcut_bound)
    candidate[shortcut_id] = {"description": description, "trigger": trigger, "backend": "portal"}
    backend = "portal"
    try:
        code = _portal_bind_all({k: v for k, v in candidate.items() if v["backend"] == "portal"})
        portal_ok = code == 0
    except _Fail as fail:
        _log("portal GlobalShortcuts unavailable for %s: %s" % (shortcut_id, fail.code))
        portal_ok = False
    if portal_ok:
        _shortcut_bound.clear()
        _shortcut_bound.update(candidate)
    else:
        # 2) KGlobalAccel: the same KDE service, reached directly. Reported as backend "kglobalaccel".
        backend = "kglobalaccel"
        _kga_register(shortcut_id, description, trigger)
        if previous is not None and previous["backend"] == "kglobalaccel":
            _kga_unregister(shortcut_id)
        _shortcut_bound[shortcut_id] = {"description": description, "trigger": trigger, "backend": backend}
    return {"backend": backend, "id": shortcut_id, "trigger": trigger,
            "bound": len(_shortcut_bound)}


def _shortcut_events_out(_inp):
    events = list(_shortcut_events)
    del _shortcut_events[:]
    return {"backend": "portal", "events": events}


def _shortcut_close():
    global _shortcut_session, _kga_sub
    for shortcut_id, item in list(_shortcut_bound.items()):
        if item["backend"] == "kglobalaccel":
            _kga_unregister(shortcut_id)
    _shortcut_bound.clear()
    if _shortcut_session is not None:
        try:
            _portal().call(SESSION_IFACE, "Close", "()", (), path=_shortcut_session)
        except _Fail:
            pass
        _shortcut_session = None


# ---------------------------------------------------------------- dispatch

HANDLERS = {
    "screen_observe.capture": _screen_capture,
    "screen_observe.status": _screen_status,
    "computer_control.tree": _cc_tree,
    "computer_control.act": _cc_act,
    "computer_control.status": _cc_status,
    "audio_advanced.state": _audio_state,
    "audio_advanced.act": _audio_act,
    "mic_advanced.state": _mic_state,
    "mic_advanced.configure": _mic_configure,
    "mic_advanced.monitor": lambda _inp: {"backend": "pipewire", "supported": False,
                                          "reason": "monitor_would_feed_back_to_speakers"},
    "mic_advanced.record": _mic_record,
    "camera_gesture.state": _cam_state,
    "camera_gesture.optin": _cam_optin,
    "camera_gesture.capture": _cam_capture,
    "camera_gesture.gestures": _cam_gestures,
    "display_manipulate.status": _display_status,
    "display_manipulate.act": _display_act,
    "display_manipulate.restore": _display_restore,
    "shortcut_global.status": _shortcut_status,
    "shortcut_global.bind": _shortcut_bind,
    "shortcut_global.events": _shortcut_events_out,
}


NO_INPUT = frozenset((
    "screen_observe.capture", "screen_observe.status", "computer_control.tree",
    "computer_control.status", "audio_advanced.state", "mic_advanced.state", "mic_advanced.monitor",
    "camera_gesture.state", "camera_gesture.capture", "camera_gesture.gestures",
    "display_manipulate.status", "display_manipulate.restore", "shortcut_global.status",
    "shortcut_global.events",
))


def _run_capability(capability, inp):
    if not isinstance(inp, dict):
        raise _Fail("invalid_input")
    if capability in NO_INPUT and inp:
        raise _Fail("invalid_input")
    return HANDLERS[capability](inp)


def _handle_invoke(msg):
    global _running
    req_id = msg.get("id")
    if not isinstance(req_id, int) or isinstance(req_id, bool):
        return
    capability = msg.get("capability")
    if _plugin is None or not isinstance(capability, str) or capability not in PLUGINS.get(_plugin, []):
        _send({"id": req_id, "ok": False, "error": "unknown_capability"})
        return
    _running = req_id
    try:
        _expire_recording()
        output = _run_capability(capability, msg.get("input"))
        if _size(output) > MAX_OUTPUT:
            raise _Fail("plugin_error")
    except _Fail as fail:
        _send({"id": req_id, "ok": False, "error": fail.code})
    except _Cancel:
        _send({"id": req_id, "ok": False, "error": "cancelled"})
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, RuntimeError) as err:
        _log("%s: %s: %s" % (capability, type(err).__name__, err))
        _send({"id": req_id, "ok": False, "error": "plugin_error"})
    else:
        _send({"id": req_id, "ok": True, "output": output})
    finally:
        _running = None


def _handle_hello(msg):
    global _plugin
    plugin_id = msg.get("plugin_id")
    if not isinstance(plugin_id, str) or plugin_id not in PLUGINS:
        _send({"v": PROTOCOL, "id": msg.get("id"), "ok": False, "error": "unknown_capability"})
        return
    _plugin = plugin_id
    _send({"v": PROTOCOL, "id": msg.get("id"), "ok": True, "plugin_id": plugin_id, "api": 1,
           "capabilities": PLUGINS[plugin_id]})


def _shutdown_cleanup():
    if _recording is not None:
        _stop_recording(keep_result=False)
    while _display_undo:
        try:
            _display_restore(None)
        except _Fail:
            break
    _cc_close_session()
    _shortcut_close()


def main():
    try:
        while True:
            msg = _next_message()
            if msg.get("v", PROTOCOL) != PROTOCOL:
                if isinstance(msg.get("id"), int):
                    _send({"id": msg["id"], "ok": False, "error": "unsupported_version"})
                continue
            op = msg.get("op")
            if op == "shutdown":
                break
            if op == "hello":
                _handle_hello(msg)
            elif op == "invoke":
                _handle_invoke(msg)
            elif op in ("cancel", "host_reply"):
                continue
            elif isinstance(msg.get("id"), int):
                _send({"id": msg["id"], "ok": False, "error": "unknown_op"})
    except (EOFError, _Shutdown):
        pass
    finally:
        _shutdown_cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
