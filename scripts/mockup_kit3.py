#!/usr/bin/env python3
"""Stdlib-only SVG kit v3: the Gideon app shell (top tab bar + sub-tab bar, no sidebar).

Extends scripts/mockup_kit.py (imported, not edited). Geometry: docs/ui-spec/00-casca.md.
Colours: ONLY from the current theme tokens T (set by set_theme / set_accent). No helper
hardcodes a colour; the same page script renders in any preset.
Render: target/ui-venv/bin/python -I -B scripts/render_svg.py <file>.svg [out.png]
Qt (QtSvg) limits: inline attributes only; no CSS classes, filters, blur, foreignObject.
Bold text: weight 'bold' only. Text helpers take the BASELINE y.

API (every drawing function returns an SVG fragment str):

THEME
  theme_names() -> list[str]
  set_theme(name)                 one of THEME_NAMES; resets accent to that preset's accent
  set_accent(hex)                 '#RRGGBB'; re-derives tints; onAccent fixed to >= 4.5:1
  contrast(a, b) -> float         WCAG ratio
  mix(a, b, t) -> '#rrggbb'       linear mix, t in 0..1
  T                               dict of current tokens (bg surface surfaceVariant outline text
                                  textMuted accent onAccent success warning error info) plus derived
                                  border, cardBot, tint, hover, tintStrong, placeholder, disabled
  canvas(body, w=1380, h=904) -> svg document (adds gradient defs + bg)
  content_box(width=1380) -> (x, w)   margin 32, max 1100, centred
TEXT
  text(x, y, s, size=14, weight='normal', fill=None, anchor='start', letter_spacing=None)
  text_w(s, size=14, weight='normal') -> px
  wrap(x, y, s, max_chars, size, weight, fill, line_h, anchor)   char-based (old kit semantics)
  wrap_px(x, y, s, width_px, size, weight, fill, line_h)         width-based, greedy words
  wrap_px_lines(s, width_px, size, weight) -> [str]
  wrap_px_height(s, width_px, size, weight, line_h) -> px
PRIMITIVES
  rect(x, y, w, h, rx, fill, stroke, sw, fo, so, dash)
  circle(cx, cy, r, fill, stroke, sw, fo, so)
  line(x1, y1, x2, y2, stroke, sw, dash)
  path(d, fill, stroke, sw, so)
  icon(name, x, y, size=20, color=None)   app/icons/<name>.svg (chat hub shield gear activity ...)
  orb(cx, cy, r, state='idle')    states: idle listening thinking speaking error
SHELL (docs/ui-spec/00-casca.md)
  topbar(active_tab, badges={}, state='Em espera', state_tone='ok', cancel=False, width=1380)
         badges: {tab label: count}; tabs: Assistente Extensões Permissões Configurações Diagnóstico
  rail_topbar(active_tab, badges={}, state, state_tone, cancel, width)   icon-only, < 900 px
  subtabs(items, active, disabled=(), badges={}, width=1380)  bar y 56-100
  page_header(title, subtitle, action=None, width=1380)        title baseline 138, action 40 px right
  summary_strip(text, badges=[(label, tone)], width=1380, y=184)   card 40 px tall
COMPONENTS (tones: ok warn err info muted)
  card(x, y, w, h, title=None)    radius 10, surface->surfaceVariant gradient, 1 px border
  card_body_top(y, titled=True)
  badge(x, y, label, tone)        22 px, colour + word;   badge_w(label)
  count_pill(x, y, n)             accent pill for counters -> (svg, width)
  chip(x, y, label, icon_name=None, active=False);  chip_w(label, icon_name)
  button(x, y, w, label, variant='secondary'|'primary'|'danger'|'ghost', state='normal'|'hover'|'pressed'|'focus'|'disabled', h=40)
  button_w(label, primary=False)
  input_box(x, y, w, h, value, placeholder=False, focus=False)
  field(x, y, w, label, value, placeholder=False, focus=False)  label above, 62 px
  toggle(x, y, label, on=True)    44x24 switch + state word
  slider(x, y, w, value=0.5, left, right, value_text)
  segmented(x, y, items, active); segmented_w(items); tabs_in_card = segmented
  select(x, y, w, value, open=False, options=(), h=40)
  checkbox(x, y, label, checked=True)
  radio(x, y, label, selected=True)
  table_header(x, y, w, cols, h=36)   cols: [(rel_x, label)]
  table_row(x, y, w, cols, h=44, selected=False)  cols: [(rel_x, str | dict(s=..., size=..) | f(ax, cy))]
  list_row(x, y, w, title, subtitle=None, icon_name=None, trailing=None, h=56, selected=False)
  collapsible(x, y, w, title, summary, open=False, body_h=0)   'Como funciona', 56 px header
  empty_state(x, y, w, h, icon_name, label, action=None, primary=True)   h >= 140
  toast(x, y, label, tone='ok', width=None)
  scrim(w, h, op=0.6)             full-canvas dim layer to put under a modal
  modal(x, y, w, h, title, body, buttons=())  buttons: [(label, variant)], right aligned
  progress_bar(x, y, w, value, h=8, label=None)
  icon_tile(x, y, size, icon_name, tone=None)
  avatar(x, y, size, initials)
  kbd(x, y, shortcut, size=12) -> svg;  kbd_w(shortcut, size=12)
  bubble(x, y, w, label, role='assistant'|'user', size=14) -> svg;  bubble_h(label, w, size=14)
  swatch(x, y, color, selected=False, size=28)
  modified_marker(x, y, h, tone=None)   3 px left bar
  tooltip(x, y, label)            inverted pill (text on bg colour)
"""
import math
import os
import re
import sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import mockup_kit as _k1  # noqa: E402  (old kit: text metrics, icon shape cache, _n/_attr)

FONT = "Noto Sans"
CANVAS_W, CANVAS_H = 1380, 904

# Geometry (docs/ui-spec/00-casca.md)
TOPBAR_H = 56
SUBTAB_Y, SUBTAB_H = 56, 44
HEADER_Y = 116
SUMMARY_Y, SUMMARY_H = 184, 40
CONTENT_Y = 236
MARGIN = 32
CONTENT_MAX = 1100
RADIUS = 10
CARD_PAD = 20
CARD_TITLE_BASE = 34
CARD_BODY_TOP = 52
CARD_GAP = 16
FIELD_H = 62
COLLAPSIBLE_H = 56

# Presets: docs/research/ux-temas.md section 6.4 (table rows 1-8). Keys = schema tokens 6.1.
THEMES = {
    "gideon-escuro": dict(bg="#121417", surface="#1B1F24", surfaceVariant="#262C33", outline="#7D8794",
                          text="#E6E9EE", textMuted="#A7B0BC", accent="#7AA2F7", onAccent="#0B1020",
                          success="#6BCB8B", warning="#E8B04B", error="#F07178", info="#6CB6FF"),
    "gideon-claro": dict(bg="#FBFBFD", surface="#FFFFFF", surfaceVariant="#EEF1F5", outline="#7A8491",
                         text="#1A1D21", textMuted="#4B5563", accent="#2F5FD0", onAccent="#FFFFFF",
                         success="#1E7A3F", warning="#8A5A00", error="#B42318", info="#1D5FA8"),
    "alto-contraste": dict(bg="#000000", surface="#0A0A0A", surfaceVariant="#1A1A1A", outline="#FFFFFF",
                           text="#FFFFFF", textMuted="#D0D0D0", accent="#FFD400", onAccent="#000000",
                           success="#00E676", warning="#FFB300", error="#FF5252", info="#40C4FF"),
    "breeze-escuro": dict(bg="#232629", surface="#31363B", surfaceVariant="#3B4045", outline="#7F8C8D",
                          text="#FCFCFC", textMuted="#BDC3C7", accent="#3DAEE9", onAccent="#0B0F13",
                          success="#27AE60", warning="#F67400", error="#F26D7E", info="#3DAEE9"),
    "breeze-claro": dict(bg="#EFF0F1", surface="#FCFCFC", surfaceVariant="#E3E5E7", outline="#7F8C8D",
                         text="#232629", textMuted="#4D5358", accent="#1D6FA8", onAccent="#FFFFFF",
                         success="#1E7A45", warning="#8A4500", error="#B3261E", info="#1D6FA8"),
    "catppuccin": dict(bg="#1e1e2e", surface="#313244", surfaceVariant="#45475a", outline="#7f849c",
                       text="#cdd6f4", textMuted="#a6adc8", accent="#89b4fa", onAccent="#1e1e2e",
                       success="#a6e3a1", warning="#f9e2af", error="#f38ba8", info="#89dceb"),
    "nord": dict(bg="#2E3440", surface="#3B4252", surfaceVariant="#434C5E", outline="#939EB2",
                 text="#ECEFF4", textMuted="#D8DEE9", accent="#88C0D0", onAccent="#2E3440",
                 success="#A3BE8C", warning="#EBCB8B", error="#E38A92", info="#81A1C1"),
    "daltonismo": dict(bg="#15171C", surface="#1E2228", surfaceVariant="#2A2F37", outline="#8A93A0",
                       text="#EDEFF2", textMuted="#B5BCC6", accent="#56B4E9", onAccent="#000000",
                       success="#2BB594", warning="#E69F00", error="#E8743B", info="#56B4E9"),
}
THEME_NAMES = list(THEMES)
TONE_TOKEN = {"ok": "success", "warn": "warning", "err": "error", "info": "info", "muted": "textMuted"}

T = {}
_STATE = {"preset": None}
_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")
_WHITE, _BLACK = "#FFFFFF", "#000000"  # math anchors for mix() only, never drawn directly


# ---------------------------------------------------------------- colour math

def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(v))):02x}" for v in rgb)


def mix(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(ra[i] + (rb[i] - ra[i]) * t for i in range(3)))


def _lum(h):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _derive():
    T["border"] = mix(T["bg"], T["outline"], 0.35)          # 1 px hairlines, quieter than outline
    T["cardBot"] = mix(T["surface"], T["surfaceVariant"], 0.5)  # subtle card gradient end
    T["tint"] = mix(T["surface"], T["accent"], 0.18)        # active tab / selected row
    T["hover"] = mix(T["surface"], T["accent"], 0.10)
    T["tintStrong"] = mix(T["surface"], T["accent"], 0.30)
    T["placeholder"] = mix(T["textMuted"], T["surfaceVariant"], 0.25)
    T["disabled"] = mix(T["textMuted"], T["surface"], 0.5)


def set_theme(name):
    if name not in THEMES:
        raise ValueError(f"unknown theme {name!r}; expected one of {THEME_NAMES}")
    _STATE["preset"] = name
    T.clear()
    T.update(THEMES[name])
    _derive()


def theme_names():
    return list(THEME_NAMES)


def set_accent(hex_):
    if not _HEX.match(str(hex_)):
        raise ValueError(f"accent must be #RRGGBB, got {hex_!r}")
    acc = hex_ if str(hex_).startswith("#") else "#" + hex_
    acc = acc.lower()
    if _STATE["preset"] is None:
        set_theme("gideon-escuro")
    on = THEMES[_STATE["preset"]]["onAccent"]
    if contrast(on, acc) < 4.5:
        on = _BLACK if contrast(_BLACK, acc) >= contrast(_WHITE, acc) else _WHITE
    T["accent"] = acc
    T["onAccent"] = on
    _derive()


def _tone(tone):
    return T[TONE_TOKEN.get(tone, tone)]


# ---------------------------------------------------------------- text

def text_w(s, size=14, weight="normal"):
    return _k1.text_w(s, size, weight)


def text(x, y, s, size=14, weight="normal", fill=None, anchor="start", letter_spacing=None):
    """Single line. (x, y) is the baseline."""
    fill = fill or T["text"]
    a = (f'x="{_k1._n(x)}" y="{_k1._n(y)}" font-family="{FONT}" font-size="{_k1._n(size)}" '
         f'font-weight="{weight}" fill="{fill}"')
    if anchor != "start":
        a += f' text-anchor="{anchor}"'
    if letter_spacing:
        a += f' letter-spacing="{_k1._n(letter_spacing)}"'
    return f"<text {a}>{escape(str(s))}</text>"


def wrap_lines(s, max_chars):
    return _k1.wrap_lines(s, max_chars)


def wrap(x, y, s, max_chars, size=14, weight="normal", fill=None, line_h=None, anchor="start"):
    lh = line_h or round(size * 1.45)
    return "".join(text(x, y + i * lh, ln, size, weight, fill, anchor)
                   for i, ln in enumerate(wrap_lines(s, max_chars)))


def wrap_px_lines(s, width_px, size=14, weight="normal"):
    lines, cur = [], ""
    for word in str(s).split():
        cand = word if not cur else cur + " " + word
        if not cur or text_w(cand, size, weight) <= width_px:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    if cur or not lines:
        lines.append(cur)
    return lines


def wrap_px_height(s, width_px, size=14, weight="normal", line_h=None):
    lh = line_h or round(size * 1.45)
    return (len(wrap_px_lines(s, width_px, size, weight)) - 1) * lh + size


def wrap_px(x, y, s, width_px, size=14, weight="normal", fill=None, line_h=None, anchor="start"):
    lh = line_h or round(size * 1.45)
    return "".join(text(x, y + i * lh, ln, size, weight, fill, anchor)
                   for i, ln in enumerate(wrap_px_lines(s, width_px, size, weight)))


# ---------------------------------------------------------------- primitives

def rect(x, y, w, h, rx=0, fill="none", stroke=None, sw=1, fo=None, so=None, dash=None):
    a = f'x="{_k1._n(x)}" y="{_k1._n(y)}" width="{_k1._n(w)}" height="{_k1._n(h)}"'
    if rx:
        a += f' rx="{_k1._n(rx)}"'
    a += f' fill="{fill}"'
    if fo is not None:
        a += f' fill-opacity="{_k1._n(fo)}"'
    if stroke:
        a += f' stroke="{stroke}" stroke-width="{_k1._n(sw)}"'
        if so is not None:
            a += f' stroke-opacity="{_k1._n(so)}"'
    if dash:
        a += f' stroke-dasharray="{dash}"'
    return f"<rect {a}/>"


def circle(cx, cy, r, fill="none", stroke=None, sw=1, fo=None, so=None):
    a = f'cx="{_k1._n(cx)}" cy="{_k1._n(cy)}" r="{_k1._n(r)}" fill="{fill}"'
    if fo is not None:
        a += f' fill-opacity="{_k1._n(fo)}"'
    if stroke:
        a += f' stroke="{stroke}" stroke-width="{_k1._n(sw)}"'
        if so is not None:
            a += f' stroke-opacity="{_k1._n(so)}"'
    return f"<circle {a}/>"


def line(x1, y1, x2, y2, stroke=None, sw=1, dash=None):
    a = (f'x1="{_k1._n(x1)}" y1="{_k1._n(y1)}" x2="{_k1._n(x2)}" y2="{_k1._n(y2)}" '
         f'stroke="{stroke or T["border"]}" stroke-width="{_k1._n(sw)}"')
    if dash:
        a += f' stroke-dasharray="{dash}"'
    return f"<line {a}/>"


def path(d, fill="none", stroke=None, sw=1.7, so=None):
    a = f'd="{_k1._attr(d)}" fill="{fill}"'
    if stroke:
        a += f' stroke="{stroke}" stroke-width="{_k1._n(sw)}" stroke-linecap="round" stroke-linejoin="round"'
        if so is not None:
            a += f' stroke-opacity="{_k1._n(so)}"'
    return f"<path {a}/>"


def icon(name, x, y, size=20, color=None):
    """Stroke icon from app/icons/<name>.svg placed at (x, y) with side length size."""
    sw, shapes = _k1._icon_shapes(name)
    color = color or T["textMuted"]
    parts = []
    for tag, attrs in shapes:
        a = " ".join(f'{k}="{_k1._attr(v)}"' for k, v in attrs.items())
        parts.append(f"<{tag} {a}/>")
    return (f'<g transform="translate({_k1._n(x)} {_k1._n(y)}) scale({_k1._n(size / 24.0)})" fill="none" '
            f'stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">'
            + "".join(parts) + "</g>")


# ---------------------------------------------------------------- canvas and gradients

def _radial(gid, color, cx=0.4, cy=0.4, r=0.6):
    hi, lo = mix(color, _WHITE, 0.55), mix(color, _BLACK, 0.5)
    return (f'<radialGradient id="{gid}" cx="{cx}" cy="{cy}" r="{r}">'
            f'<stop offset="0" stop-color="{hi}"/><stop offset="0.5" stop-color="{color}"/>'
            f'<stop offset="1" stop-color="{lo}"/></radialGradient>')


def _glow(gid, color):
    return (f'<radialGradient id="{gid}" cx="0.5" cy="0.5" r="0.5">'
            f'<stop offset="0" stop-color="{color}" stop-opacity="0.45"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>')


def _defs():
    return (
        f'<linearGradient id="cardGrad" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{T["surface"]}"/><stop offset="1" stop-color="{T["cardBot"]}"/>'
        f'</linearGradient>'
        + _radial("orbBase", T["accent"], 0.35, 0.3, 0.75)
        + _radial("orbLobeA", T["info"])
        + _radial("orbLobeB", mix(T["accent"], T["text"], 0.4))
        + _radial("orbErr", T["error"], 0.35, 0.3, 0.75)
        + _glow("orbGlow", T["accent"])
        + _glow("orbGlowErr", T["error"])
    )


def canvas(body, w=CANVAS_W, h=CANVAS_H):
    """Wrap a page body in the SVG root with theme gradients and the page background."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f"<defs>{_defs()}</defs>" + rect(0, 0, w, h, fill=T["bg"]) + body + "</svg>")


def content_box(width=CANVAS_W):
    """(x, w) of the content column: 32 px margins, max 1100, centred when wide."""
    w = min(CONTENT_MAX, width - 2 * MARGIN)
    return MARGIN + (width - 2 * MARGIN - w) / 2.0, w


# ---------------------------------------------------------------- orb

def _arc(cx, cy, r, a0, a1, color, sw, so=None):
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    large = 1 if (a1 - a0) % (2 * math.pi) > math.pi else 0
    d = f"M{_k1._n(x0)} {_k1._n(y0)} A{_k1._n(r)} {_k1._n(r)} 0 {large} 1 {_k1._n(x1)} {_k1._n(y1)}"
    return path(d, stroke=color, sw=sw, so=so)


def orb(cx, cy, r, state="idle"):
    """Orb logo/indicator. state: idle | listening (ripple rings) | thinking (swirl dots) |
    speaking (waveform arcs) | error (red base and ring)."""
    err = state == "error"
    out = [circle(cx, cy, r * 1.35, fill="url(#orbGlowErr)" if err else "url(#orbGlow)")]
    if state == "listening":
        for f, op in ((1.25, 0.6), (1.55, 0.4), (1.85, 0.2)):
            out.append(circle(cx, cy, r * f, stroke=T["accent"], sw=1.5, so=op))
    out.append(circle(cx, cy, r, fill="url(#orbErr)" if err else "url(#orbBase)"))
    out.append(f'<ellipse cx="{_k1._n(cx - r * 0.2)}" cy="{_k1._n(cy + r * 0.25)}" rx="{_k1._n(r * 0.55)}" '
               f'ry="{_k1._n(r * 0.4)}" fill="url(#orbLobeA)" opacity="0.85"/>')
    out.append(f'<ellipse cx="{_k1._n(cx + r * 0.3)}" cy="{_k1._n(cy - r * 0.25)}" rx="{_k1._n(r * 0.5)}" '
               f'ry="{_k1._n(r * 0.34)}" fill="url(#orbLobeB)" opacity="0.8"/>')
    out.append(f'<ellipse cx="{_k1._n(cx - r * 0.25)}" cy="{_k1._n(cy - r * 0.42)}" rx="{_k1._n(r * 0.35)}" '
               f'ry="{_k1._n(r * 0.16)}" fill="{_WHITE}" opacity="0.28"/>')
    if state == "thinking":
        for k in range(5):
            a = k * 1.1
            d = r * (0.12 + 0.1 * k)
            out.append(circle(cx + d * math.cos(a), cy + d * math.sin(a), max(1.2, r * (0.17 - 0.02 * k)),
                              fill=T["onAccent"], fo=0.45 + 0.12 * k))
    elif state == "speaking":
        for rr, op in ((0.38, 1.0), (0.58, 0.75), (0.78, 0.5)):
            out.append(_arc(cx - r * 0.25, cy, r * rr, -0.75, 0.75, T["onAccent"], max(1.6, r * 0.07), op))
    elif err:
        out.append(circle(cx, cy, r * 1.2, stroke=T["error"], sw=2))
    return "".join(out)


# ---------------------------------------------------------------- shell

def _count_pill(x, y, n):
    s = str(n)
    w = max(18, text_w(s, 11, "bold") + 10)
    return (rect(x, y, w, 18, rx=9, fill=T["accent"])
            + text(x + w / 2, y + 13, s, 11, "bold", T["onAccent"], anchor="middle")), w


def count_pill(x, y, n):
    """Accent counter pill (18 px tall). Returns (svg, width)."""
    return _count_pill(x, y, n)


def _state_pill(x, y, state, tone, h=30):
    """Pill with coloured dot + word. Returns (svg, width)."""
    w = 24 + text_w(state, 13) + 14
    return (rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=(h - 1) / 2, fill=T["surfaceVariant"], stroke=T["border"])
            + circle(x + 12, y + h / 2, 4, fill=_tone(tone))
            + text(x + 24, y + h / 2 + 4.5, state, 13, "normal", T["text"])), w


def _search_button(x, y, w=120, h=30):
    cx, cy = x + 19, y + h / 2
    return (rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=8, fill=T["surfaceVariant"], stroke=T["border"])
            + circle(cx - 1, cy - 1, 4.5, stroke=T["textMuted"], sw=1.5)
            + line(cx + 2.5, cy + 2.5, cx + 6, cy + 6, stroke=T["textMuted"], sw=1.5)
            + text(x + 36, cy + 4.5, "Ctrl+K", 12, "normal", T["textMuted"]))


def _cancel_button(x, y, h=30):
    w = text_w("Cancelar", 13, "bold") + 28
    return button(x, y, w, "Cancelar", variant="secondary", h=h), w


def topbar(active_tab, badges=None, state="Em espera", state_tone="ok", cancel=False, width=CANVAS_W):
    """Level-1 tab bar, y 0-56. Logo + five tabs (active: accent tint + 3 px bar) + Ctrl+K + state pill."""
    badges = badges or {}
    tabs = [("Assistente", "chat"), ("Extensões", "hub"), ("Permissões", "shield"),
            ("Configurações", "gear"), ("Diagnóstico", "activity")]
    out = [rect(0, 0, width, TOPBAR_H, fill=T["surface"]), rect(0, TOPBAR_H - 1, width, 1, fill=T["border"])]
    out.append(orb(30, 28, 14))
    out.append(text(52, 34, "Gideon", 16, "bold", T["text"]))
    x = 132
    for label, icon_name in tabs:
        on = label == active_tab
        n = badges.get(label)
        tw = 14 + 18 + 8 + text_w(label, 14, "bold") + 14
        if n:
            tw += 8 + _count_pill(0, 0, n)[1]
        if on:
            out.append(rect(x, 8, tw, 40, rx=8, fill=T["tint"]))
            out.append(rect(x, 53, tw, 3, rx=1.5, fill=T["accent"]))
        out.append(icon(icon_name, x + 14, 19, 18, T["accent"] if on else T["textMuted"]))
        out.append(text(x + 40, 33, label, 14, "bold" if on else "normal", T["text"] if on else T["textMuted"]))
        if n:
            pill, pw = _count_pill(x + 40 + text_w(label, 14, "bold") + 8, 19, n)
            out.append(pill)
        x += tw + 4
    # right cluster, laid out right to left from width - 16
    _, pill_w = _state_pill(0, 13, state, state_tone)
    right = width - 16 - pill_w
    out.append(_state_pill(right, 13, state, state_tone)[0])
    if cancel:
        _, cw = _cancel_button(0, 13)
        right -= 8 + cw
        out.append(_cancel_button(right, 13)[0])
    right -= 8 + 120
    out.append(_search_button(right, 13))
    return "".join(out)


def rail_topbar(active_tab, badges=None, state="Em espera", state_tone="ok", cancel=False, width=CANVAS_W):
    """Icon-only tab bar for windows < 900 px. Tooltips carry the names in the real app."""
    badges = badges or {}
    tabs = [("Assistente", "chat"), ("Extensões", "hub"), ("Permissões", "shield"),
            ("Configurações", "gear"), ("Diagnóstico", "activity")]
    out = [rect(0, 0, width, TOPBAR_H, fill=T["surface"]), rect(0, TOPBAR_H - 1, width, 1, fill=T["border"])]
    out.append(orb(28, 28, 11))
    x = 60
    for label, icon_name in tabs:
        on = label == active_tab
        if on:
            out.append(rect(x, 8, 44, 40, rx=8, fill=T["tint"]))
            out.append(rect(x, 53, 44, 3, rx=1.5, fill=T["accent"]))
        out.append(icon(icon_name, x + 13, 19, 18, T["accent"] if on else T["textMuted"]))
        n = badges.get(label)
        if n:
            out.append(circle(x + 36, 16, 7, fill=T["accent"]) + text(x + 36, 19.5, str(n), 9, "bold",
                                                                      T["onAccent"], anchor="middle"))
        x += 48
    right = width - 16
    pill_w = 30
    right -= pill_w
    out.append(rect(right + 0.5, 13.5, pill_w - 1, 29, rx=14.5, fill=T["surfaceVariant"], stroke=T["border"]))
    out.append(circle(right + 15, 28, 5, fill=_tone(state_tone)))
    if cancel:
        cw = text_w("Cancelar", 13, "bold") + 28
        right -= 8 + cw
        out.append(button(right, 13, cw, "Cancelar", variant="secondary", h=30))
    right -= 8 + 30
    out.append(rect(right + 0.5, 13.5, 29, 29, rx=8, fill=T["surfaceVariant"], stroke=T["border"]))
    out.append(circle(right + 14, 27, 4.5, stroke=T["textMuted"], sw=1.5)
               + line(right + 17.5, 30.5, right + 21, 34, stroke=T["textMuted"], sw=1.5))
    return "".join(out)


def subtabs(items, active, disabled=(), badges=None, width=CANVAS_W):
    """Level-2 bar, y 56-100: 14 px labels, active = bold text + 2 px accent underline."""
    badges = badges or {}
    active_label = items[active] if isinstance(active, int) else active
    out = [rect(0, SUBTAB_Y, width, SUBTAB_H, fill=T["bg"])]
    x = 18
    for label in items:
        on = label == active_label
        off = label in disabled
        lw = text_w(label, 14, "bold")
        n = badges.get(label)
        tw = 36 + lw + ((8 + _count_pill(0, 0, n)[1]) if n else 0)
        color = T["disabled"] if off else (T["text"] if on else T["textMuted"])
        out.append(text(x + 18, 83, label, 14, "bold" if on else "normal", color))
        if n:
            pill, _ = _count_pill(x + 18 + lw + 8, 69, n)
            out.append(pill)
        if on:
            out.append(rect(x, SUBTAB_Y + SUBTAB_H - 2, tw, 2, fill=T["accent"]))
        x += tw
    out.append(rect(0, SUBTAB_Y + SUBTAB_H - 1, width, 1, fill=T["border"]))
    return "".join(out)


def page_header(title, subtitle, action=None, width=CANVAS_W):
    """Header y 116-176 at content x. action: label of the primary button, right aligned."""
    x, w = content_box(width)
    out = [text(x, HEADER_Y + 22, title, 24, "bold", T["text"]),
           text(x, HEADER_Y + 47, subtitle, 14, "normal", T["textMuted"])]
    if action:
        bw = button_w(action, primary=True)
        out.append(button(x + w - bw, HEADER_Y, bw, action, variant="primary"))
    return "".join(out)


def summary_strip(text_s, badges=(), width=CANVAS_W, y=SUMMARY_Y):
    """Summary strip, 40 px: bold sentence left, badges right. badges: [(label, tone)]."""
    x, w = content_box(width)
    out = [rect(x + 0.5, y + 0.5, w - 1, SUMMARY_H - 1, rx=RADIUS, fill=T["surface"], stroke=T["border"]),
           text(x + 16, y + 25, text_s, 14, "bold", T["text"])]
    cursor = x + w - 12
    for label, tone in reversed(list(badges)):
        bw = badge_w(label)
        cursor -= bw
        out.append(badge(cursor, y + 9, label, tone))
        cursor -= 8
    return "".join(out)


# ---------------------------------------------------------------- components

def card(x, y, w, h, title=None):
    out = [rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=RADIUS, fill="url(#cardGrad)", stroke=T["border"])]
    if title:
        out.append(text(x + CARD_PAD, y + CARD_TITLE_BASE, title, 17, "bold", T["text"]))
    return "".join(out)


def card_body_top(y, titled=True):
    return y + (CARD_BODY_TOP if titled else CARD_PAD)


def badge_w(label):
    return text_w(label, 12, "bold") + 20


def badge(x, y, label, tone="ok"):
    """22 px tinted pill with the word inside (status is never colour alone)."""
    c = _tone(tone)
    w = badge_w(label)
    return (rect(x + 0.5, y + 0.5, w - 1, 21, rx=11, fill=c, fo=0.14, stroke=c, so=0.5)
            + text(x + 10, y + 15, label, 12, "bold", c))


def chip_w(label, icon_name=None):
    return 12 + (24 if icon_name else 0) + text_w(label, 13) + 12


def chip(x, y, label, icon_name=None, active=False):
    """30 px selectable chip. active: accent tint with bright text."""
    w = chip_w(label, icon_name)
    out = [rect(x + 0.5, y + 0.5, w - 1, 29, rx=14.5, fill=T["tint"] if active else T["surfaceVariant"],
                stroke=T["accent"] if active else T["border"])]
    tx = x + 12
    if icon_name:
        out.append(icon(icon_name, x + 12, y + 7, 16, T["accent"] if active else T["textMuted"]))
        tx += 24
    out.append(text(tx, y + 20, label, 13, "normal", T["text"] if active else T["textMuted"]))
    return "".join(out)


def button_w(label, primary=False):
    return max(92, text_w(label, 14, "bold" if primary else "normal") + 40)


_VARIANTS = {
    # fill, stroke, text, stroke-opacity, weight
    "primary": ("accent", "accent", "onAccent", None, "bold"),
    "secondary": ("surfaceVariant", "outline", "text", 0.6, "normal"),
    "danger": ("danger", "error", "error", None, "normal"),
    "ghost": (None, None, "accent", None, "bold"),
}


def button(x, y, w, label, variant=None, primary=False, danger=False, state="normal", h=40):
    """Button, 40 px, radius 10. variant: primary | secondary | danger | ghost (primary=True kept for
    compatibility). state: normal | hover | pressed | focus (2 px accent ring) | disabled."""
    variant = variant or ("primary" if primary else "danger" if danger else "secondary")
    fill_k, stroke_k, text_k, so, wt = _VARIANTS[variant]
    fill = {"accent": T["accent"], "surfaceVariant": T["surfaceVariant"],
            "danger": mix(T["surface"], T["error"], 0.14), None: "none"}[fill_k]
    if state == "hover" and fill != "none":
        fill = mix(fill, T["accent"], 0.10)
    elif state == "pressed" and fill != "none":
        fill = mix(fill, T["accent"], 0.20)
    stroke = {"accent": T["accent"], "outline": T["outline"], "error": T["error"], None: None}[stroke_k]
    tcol = T["disabled"] if state == "disabled" else {"onAccent": T["onAccent"], "text": T["text"],
                                                        "error": T["error"], "accent": T["accent"]}[text_k]
    if state == "disabled":
        stroke, fill = T["border"], T["surfaceVariant"] if fill != "none" else "none"
    out = []
    if state == "focus":
        out.append(rect(x - 2, y - 2, w + 4, h + 4, rx=13, stroke=T["accent"], sw=2))
    out.append(rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=RADIUS, fill=fill, stroke=stroke, so=so)
               if stroke else rect(x, y, w, h, rx=RADIUS, fill=fill))
    out.append(text(x + w / 2, y + h / 2 + 5, label, 14, wt, tcol, anchor="middle"))
    return "".join(out)


def input_box(x, y, w, h, value, placeholder=False, focus=False):
    fill_col = T["placeholder"] if placeholder else T["text"]
    return (rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=RADIUS, fill=T["surfaceVariant"],
                 stroke=T["accent"] if focus else T["border"], sw=2 if focus else 1)
            + text(x + 14, y + h / 2 + 5, value, 14, "normal", fill_col))


def field(x, y, w, label, value, placeholder=False, focus=False):
    """Label 13 above a 40 px input. Occupies FIELD_H (62) px."""
    return (text(x, y + 13, label, 13, "normal", T["textMuted"])
            + input_box(x, y + 22, w, 40, value, placeholder, focus))


def toggle(x, y, label, on=True):
    """44x24 switch, label, and written state word. 40 px tall."""
    track = T["accent"] if on else T["outline"]
    knob_x = x + (32 if on else 12)
    return (rect(x, y, 44, 24, rx=12, fill=track)
            + circle(knob_x, y + 12, 9, fill=T["onAccent"] if on else T["surface"])
            + text(x + 56, y + 17, label, 14, "normal", T["text"])
            + text(x + 56, y + 36, "Ligado" if on else "Desligado", 12, "normal",
                   T["success"] if on else T["textMuted"]))


def slider(x, y, w, value=0.5, left=None, right=None, value_text=None):
    """Horizontal slider, 58 px tall; value 0..1."""
    v = min(1.0, max(0.0, value))
    out = [rect(x, y + 29, w, 6, rx=3, fill=T["surfaceVariant"], stroke=T["border"], sw=1),
           rect(x, y + 29, w * v, 6, rx=3, fill=T["accent"]),
           circle(x + w * v, y + 32, 9, fill=T["surface"], stroke=T["accent"], sw=2.5)]
    if value_text is not None:
        out.append(text(x + w, y + 14, value_text, 16, "bold", T["text"], anchor="end"))
    if left is not None:
        out.append(text(x, y + 56, left, 12, "normal", T["textMuted"]))
    if right is not None:
        out.append(text(x + w, y + 56, right, 12, "normal", T["textMuted"], anchor="end"))
    return "".join(out)


def segmented_w(items):
    return sum(text_w(s, 13, "bold") + 28 for s in items) + 8


def segmented(x, y, items, active):
    """Segment control, 36 px. active: index or label."""
    idx = items.index(active) if isinstance(active, str) else int(active)
    w = segmented_w(items)
    out = [rect(x + 0.5, y + 0.5, w - 1, 35, rx=RADIUS, fill=T["surfaceVariant"], stroke=T["border"])]
    cx = x + 4
    for i, s in enumerate(items):
        sw_ = text_w(s, 13, "bold") + 28
        on = i == idx
        if on:
            out.append(rect(cx, y + 4, sw_, 28, rx=7, fill=T["accent"]))
        out.append(text(cx + sw_ / 2, y + 23, s, 13, "bold" if on else "normal",
                        T["onAccent"] if on else T["textMuted"], anchor="middle"))
        cx += sw_
    return "".join(out)


tabs_in_card = segmented


def select(x, y, w, value, open=False, options=(), h=40):
    """Dropdown box with chevron; open=True draws the option list below it."""
    out = [input_box(x, y, w, h, value)]
    cx, cy = x + w - 22, y + h / 2
    if open:
        out.append(path(f"M{_k1._n(cx - 5)} {_k1._n(cy + 2.5)} L{_k1._n(cx)} {_k1._n(cy - 2.5)} "
                        f"L{_k1._n(cx + 5)} {_k1._n(cy + 2.5)}", stroke=T["textMuted"]))
        rh = 36
        lh = rh * len(options) + 8
        out.append(rect(x + 0.5, y + h + 4.5, w - 1, lh - 1, rx=RADIUS, fill=T["surface"], stroke=T["border"]))
        for i, opt in enumerate(options):
            oy = y + h + 8 + i * rh
            if opt == value:
                out.append(rect(x + 4, oy, w - 8, rh, rx=8, fill=T["tint"]))
            out.append(text(x + 14, oy + rh / 2 + 5, opt, 14, "bold" if opt == value else "normal", T["text"]))
    else:
        out.append(path(f"M{_k1._n(cx - 5)} {_k1._n(cy - 2.5)} L{_k1._n(cx)} {_k1._n(cy + 2.5)} "
                        f"L{_k1._n(cx + 5)} {_k1._n(cy - 2.5)}", stroke=T["textMuted"]))
    return "".join(out)


def checkbox(x, y, label, checked=True):
    """18 px box (radius 4) + label. Returns 22 px tall block."""
    out = []
    if checked:
        out.append(rect(x + 0.5, y + 0.5, 17, 17, rx=4, fill=T["accent"], stroke=T["accent"]))
        out.append(path(f"M{_k1._n(x + 4.5)} {_k1._n(y + 9.5)} L{_k1._n(x + 7.8)} {_k1._n(y + 12.8)} "
                        f"L{_k1._n(x + 13.5)} {_k1._n(y + 6)}", stroke=T["onAccent"], sw=2.2))
    else:
        out.append(rect(x + 0.5, y + 0.5, 17, 17, rx=4, fill=T["surfaceVariant"], stroke=T["outline"], so=0.8))
    out.append(text(x + 28, y + 14, label, 14, "normal", T["text"]))
    return "".join(out)


def radio(x, y, label, selected=True):
    out = [circle(x + 9, y + 9, 8.5, fill=T["surfaceVariant"], stroke=T["accent"] if selected else T["outline"],
                  sw=2 if selected else 1)]
    if selected:
        out.append(circle(x + 9, y + 9, 4.5, fill=T["accent"]))
    out.append(text(x + 28, y + 14, label, 14, "normal", T["text"]))
    return "".join(out)


def table_header(x, y, w, cols, h=36):
    out = [text(x + rel, y + h / 2 + 4, label, 12, "bold", T["textMuted"]) for rel, label in cols]
    out.append(rect(x, y + h - 1, w, 1, fill=T["border"]))
    return "".join(out)


def table_row(x, y, w, cols, h=44, selected=False):
    """Row with 1 px divider. cols: [(rel_x, str | dict(s=..., size=..., weight=...) | f(ax, cy))]."""
    cy = y + h / 2
    out = [rect(x, y, w, h, fill=T["tint"])] if selected else []
    for rel, content in cols:
        ax = x + rel
        if callable(content):
            out.append(content(ax, cy))
        elif isinstance(content, dict):
            kw = dict(content)
            out.append(text(ax, cy + 5, kw.pop("s"), **kw))
        else:
            out.append(text(ax, cy + 5, str(content), 14, "normal", T["text"]))
    out.append(rect(x, y + h - 1, w, 1, fill=T["border"]))
    return "".join(out)


def list_row(x, y, w, title, subtitle=None, icon_name=None, trailing=None, h=56, selected=False):
    """Icon tile (optional), title (+ subtitle), trailing str or f(right_x, cy). Divider at bottom."""
    cy = y + h / 2
    out = [rect(x, y, w, h, fill=T["tint"])] if selected else []
    lx = x + 12
    if icon_name:
        out.append(icon_tile(lx, y + (h - 32) / 2, 32, icon_name))
        lx += 44
    if subtitle:
        out.append(text(lx, cy - 2, title, 14, "bold" if selected else "normal", T["text"]))
        out.append(text(lx, cy + 15, subtitle, 12, "normal", T["textMuted"]))
    else:
        out.append(text(lx, cy + 5, title, 14, "bold" if selected else "normal", T["text"]))
    if callable(trailing):
        out.append(trailing(x + w - 16, cy))
    elif trailing:
        out.append(text(x + w - 16, cy + 5, trailing, 13, "normal", T["textMuted"], anchor="end"))
    out.append(rect(x, y + h - 1, w, 1, fill=T["border"]))
    return "".join(out)


def collapsible_height(open=False, body_h=0):
    return COLLAPSIBLE_H + (body_h if open else 0)


def collapsible(x, y, w, title, summary, open=False, body_h=0):
    """'Como funciona': 56 px header (title, one summary line, chevron). Open adds body_h below."""
    h = collapsible_height(open, body_h)
    out = [rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=RADIUS, fill=T["surfaceVariant"], stroke=T["border"])]
    out.append(text(x + 18, y + 25, title, 15, "bold", T["text"]))
    out.append(text(x + 18, y + 45, summary, 13, "normal", T["textMuted"]))
    cx, cy = x + w - 30, y + 28
    if open:
        out.append(path(f"M{_k1._n(cx - 5)} {_k1._n(cy - 3)} L{_k1._n(cx)} {_k1._n(cy + 3)} "
                        f"L{_k1._n(cx + 5)} {_k1._n(cy - 3)}", stroke=T["textMuted"]))
        if body_h:
            out.append(line(x + 1, y + COLLAPSIBLE_H, x + w - 1, y + COLLAPSIBLE_H, stroke=T["border"]))
    else:
        out.append(path(f"M{_k1._n(cx - 3)} {_k1._n(cy - 5)} L{_k1._n(cx + 3)} {_k1._n(cy)} "
                        f"L{_k1._n(cx - 3)} {_k1._n(cy + 5)}", stroke=T["textMuted"]))
    return "".join(out)


def empty_state(x, y, w, h, icon_name, label, action=None, primary=True):
    """Dashed frame, 28 px icon, one sentence, one next-step button; centred. h >= 140 with action."""
    action_h = 56 if action else 0
    total = 28 + 12 + 20 + action_h
    top = y + (h - total) / 2
    cx = x + w / 2
    out = [rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=RADIUS + 4, fill=T["surfaceVariant"], fo=0.4,
                stroke=T["outline"], so=0.6, dash="6 5")]
    out.append(icon(icon_name, cx - 14, top, 28, T["textMuted"]))
    out.append(text(cx, top + 28 + 12 + 14, label, 14, "normal", T["textMuted"], anchor="middle"))
    if action:
        bw = button_w(action, primary)
        out.append(button(cx - bw / 2, top + 28 + 12 + 20 + 16, bw, action,
                          variant="primary" if primary else "secondary"))
    return "".join(out)


def toast(x, y, label, tone="ok", width=None):
    """48 px toast: tone bar + dot + message. Put bottom-right, lasts 4 s in the app."""
    w = width or (text_w(label, 14) + 56)
    return (rect(x + 0.5, y + 0.5, w - 1, 47, rx=RADIUS, fill=T["surface"], stroke=T["border"])
            + rect(x, y + 6, 4, 36, rx=2, fill=_tone(tone))
            + circle(x + 20, y + 24, 5, fill=_tone(tone))
            + text(x + 34, y + 29, label, 14, "normal", T["text"]))


def scrim(w=CANVAS_W, h=CANVAS_H, op=0.6):
    return rect(0, 0, w, h, fill=T["bg"], fo=op)


def modal(x, y, w, h, title, body, buttons=()):
    """Dialog 14 px radius: title 18 bold, body wrapped, buttons [(label, variant)] right aligned."""
    out = [rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=14, fill=T["surface"], stroke=T["border"]),
           text(x + 24, y + 38, title, 18, "bold", T["text"])]
    out.append(wrap_px(x + 24, y + 70, body, w - 48, 14, "normal", T["textMuted"]))
    bx = x + w - 24
    for label, variant in reversed(list(buttons)):
        bw = button_w(label, primary=variant == "primary")
        bx -= bw
        out.append(button(bx, y + h - 24 - 40, bw, label, variant=variant))
        bx -= 8
    return "".join(out)


def progress_bar(x, y, w, value, h=8, label=None):
    v = min(1.0, max(0.0, value))
    out = []
    if label:
        out.append(text(x, y - 6, label, 12, "normal", T["textMuted"]))
        y += 14
    out.append(rect(x, y, w, h, rx=h / 2, fill=T["surfaceVariant"], stroke=T["border"], sw=1))
    if v > 0:
        out.append(rect(x, y, max(h, w * v), h, rx=h / 2, fill=T["accent"]))
    return "".join(out)


def icon_tile(x, y, size, icon_name, tone=None):
    """Rounded square with an icon. Tinted by accent, or by tone."""
    base = _tone(tone) if tone else T["accent"]
    fill = mix(T["surface"], base, 0.18)
    s = size * 0.56
    return (rect(x, y, size, size, rx=RADIUS, fill=fill)
            + icon(icon_name, x + (size - s) / 2, y + (size - s) / 2, s, base))


def avatar(x, y, size, initials):
    return (circle(x + size / 2, y + size / 2, size / 2, fill=T["tintStrong"])
            + text(x + size / 2, y + size / 2 + size * 0.14, initials, size * 0.38, "bold", T["text"],
                   anchor="middle"))


def kbd_w(shortcut, size=12):
    keys = str(shortcut).split("+")
    return sum(max(22, text_w(k, size, "bold") + 12) for k in keys) + 4 * (len(keys) - 1)


def kbd(x, y, shortcut, size=12):
    """Keycaps for a shortcut such as 'Ctrl+K' (22 px tall)."""
    out, cx = [], x
    keys = str(shortcut).split("+")
    for i, k in enumerate(keys):
        kw = max(22, text_w(k, size, "bold") + 12)
        out.append(rect(cx + 0.5, y + 0.5, kw - 1, 21, rx=5, fill=T["surfaceVariant"], stroke=T["outline"], so=0.7))
        out.append(text(cx + kw / 2, y + 15, k, size, "bold", T["text"], anchor="middle"))
        cx += kw + (4 if i < len(keys) - 1 else 0)
    return "".join(out)


def bubble_h(label, w, size=14):
    lines = wrap_px_lines(label, w - 28, size)
    return 12 + size + (len(lines) - 1) * round(size * 1.45) + 12


def bubble(x, y, w, label, role="assistant", size=14):
    """Chat bubble. role user: accent tint; assistant: surface variant. (x, y) is the top-left."""
    h = bubble_h(label, w, size)
    fill = T["tint"] if role == "user" else T["surfaceVariant"]
    return (rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=RADIUS, fill=fill, stroke=T["border"])
            + wrap_px(x + 14, y + 12 + size, label, w - 28, size, "normal", T["text"]))


def swatch(x, y, color, selected=False, size=28):
    """Colour chip (caller's colour, e.g. a preset accent). Selected: accent ring + check."""
    out = []
    if selected:
        out.append(rect(x - 3, y - 3, size + 6, size + 6, rx=RADIUS, stroke=T["accent"], sw=2))
    out.append(rect(x + 0.5, y + 0.5, size - 1, size - 1, rx=7, fill=color, stroke=T["border"]))
    if selected:
        ink = _BLACK if contrast(_BLACK, color) >= contrast(_WHITE, color) else _WHITE
        out.append(path(f"M{_k1._n(x + size * 0.3)} {_k1._n(y + size * 0.52)} "
                        f"L{_k1._n(x + size * 0.45)} {_k1._n(y + size * 0.66)} "
                        f"L{_k1._n(x + size * 0.72)} {_k1._n(y + size * 0.36)}", stroke=ink, sw=2.2))
    return "".join(out)


def modified_marker(x, y, h, tone=None):
    return rect(x, y, 3, h, rx=1.5, fill=_tone(tone) if tone else T["accent"])


def tooltip(x, y, label):
    """Inverted pill: text colour as fill, bg colour as text. 24 px tall."""
    w = text_w(label, 12) + 16
    return (rect(x, y, w, 24, rx=6, fill=T["text"])
            + text(x + 8, y + 16, label, 12, "normal", T["bg"]))


set_theme("gideon-escuro")
