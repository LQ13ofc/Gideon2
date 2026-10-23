#!/usr/bin/env python3
"""Stdlib-only SVG mockup kit for the Gideon app.

Every function returns an SVG fragment (str). Coordinates are absolute px on a 1380x904 canvas.
Render with: target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/<name>.svg
Renderer limits (QtSvg): inline attributes only; no CSS classes, filters, blur or foreignObject.
Tokens and layout rules come from docs/UI_DESIGN.md and app/Main.qml.

Text baselines: text(x, y, ...) takes the BASELINE y. Card titles sit at card_y + 34.
Card body starts at card_y + CARD_BODY_TOP (titled) or card_y + CARD_PAD (untitled).
"""
import os
import textwrap
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_DIR = os.path.join(ROOT, "app", "icons")

FONT = "Noto Sans"

# Tokens (docs/UI_DESIGN.md)
BG = "#0b1530"
SIDEBAR_BG = "#142445"
DIVIDER = "#2b3d6a"
CARD_BORDER = "#263a73"
INPUT_BG = "#11203a"
TEXT = "#e8eeff"
TEXT_STRONG = "#f1f5ff"
TEXT_MUTED = "#9db0e0"
TEXT_BODY = "#b0c3e9"
TEXT_LABEL = "#9fb3dc"
ACCENT = "#7693ff"
VIOLET = "#b386ff"
CYAN = "#66dcf4"
PINK = "#f28bd7"
OK = "#5ee0a0"
WARN = "#f2c15c"
ERR = "#ff7d8a"
INFO = ACCENT
MUTED = "#8fa5d0"
ICON_IDLE = "#aebfe6"
NAV_TEXT = "#c9d6f5"
NAV_ACTIVE_TEXT = "#f5f8ff"
SECTION_TEXT = "#7d93c3"
BTN_PRIMARY = "#3e5fcc"
BTN_PRIMARY_EDGE = "#5d7ae6"
BTN_FILL = "#1d3266"
BTN_EDGE = "#35508f"
DANGER_FILL = "#331a26"
DANGER_EDGE = "#c2566a"
DANGER_TEXT = "#ffd3da"
PLACEHOLDER = "#6f82ab"

TONES = {"ok": OK, "warn": WARN, "err": ERR, "info": INFO, "muted": MUTED}

# Layout (app/Main.qml: sidebar 232 px, rail 60 px below 980 px; content margin 24)
CANVAS_W, CANVAS_H = 1380, 904
SIDEBAR_W = 232
RAIL_W = 56
CONTENT_X = 256
CONTENT_RIGHT = 1356
CONTENT_W = CONTENT_RIGHT - CONTENT_X  # 1100
CONTENT_TOP = 96
CARD_GAP = 16
CARD_PAD = 20
CARD_TITLE_BASE = 34
CARD_BODY_TOP = 52
FIELD_H = 62
COLLAPSIBLE_H = 56

# Sidebar: (label, icon name, row centre y in px) per group, plus group title centres.
NAV_GROUPS = [
    ("PRINCIPAL", 90, [("Início", "home", 120), ("Conversa", "chat", 161)]),
    ("VOZ E ÁUDIO", 195, [("Voz e Wake", "mic", 224), ("Áudio", "speaker", 265)]),
    ("EXTENSÕES", 300, [
        ("Gideon Hub", "hub", 330), ("Skills", "sparkles", 371), ("Conexões", "plug", 411),
        ("Modelos LLM", "cpu", 452), ("Percepção e ação", "eye", 493), ("Plugins", "puzzle", 534),
    ]),
    ("SISTEMA", 569, [
        ("Permissões", "shield", 598), ("Diagnóstico", "activity", 639),
        ("Aparência", "palette", 680), ("Preferências", "gear", 721),
    ]),
]
NAV_LABELS = [item[0] for _, _, items in NAV_GROUPS for item in items]

# Approximate Noto Sans advance widths (em). Good to a few percent; verify by rendering.
_BOLD_WEIGHTS = ("bold", "600", "700", "semibold", "bolder")


def _n(v):
    """Compact number formatting for SVG attributes."""
    s = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _attr(v):
    return escape(str(v), {'"': "&quot;"})


def text_w(s, size=14, weight="normal"):
    """Estimated rendered width in px of a single line of Noto Sans."""
    total = 0.0
    for ch in str(s):
        if ch == " ":
            total += 0.26
        elif ch in "il.,:;'|!I":
            total += 0.27
        elif ch in "ftjr()-·":
            total += 0.34
        elif ch in "mwMW":
            total += 0.85
        elif ch.isupper():
            total += 0.64
        elif ch.isdigit():
            total += 0.57
        else:
            total += 0.54
    if weight in _BOLD_WEIGHTS:
        total *= 1.1
    else:
        total *= 1.035  # regular text measured 3-6% wider than the table above
    return total * size


def text(x, y, s, size=14, weight="normal", fill=TEXT, anchor="start", letter_spacing=None):
    """Single-line text. (x, y) is the baseline. anchor: start | middle | end."""
    attrs = (f'x="{_n(x)}" y="{_n(y)}" font-family="{FONT}" font-size="{_n(size)}" '
             f'font-weight="{weight}" fill="{fill}"')
    if anchor != "start":
        attrs += f' text-anchor="{anchor}"'
    if letter_spacing:
        attrs += f' letter-spacing="{_n(letter_spacing)}"'
    return f"<text {attrs}>{escape(str(s))}</text>"


_svg_text = text  # aliases for functions whose parameters shadow the names text/icon


def wrap_lines(s, max_chars):
    return textwrap.wrap(str(s), max_chars, break_long_words=False, break_on_hyphens=False)


def wrap_height(s, max_chars, size=14, line_h=None):
    """Height in px of a wrap() block (baseline of first line to bottom of last line)."""
    lh = line_h or round(size * 1.45)
    return (len(wrap_lines(s, max_chars)) - 1) * lh + size


def wrap(x, y, s, max_chars, size=14, weight="normal", fill=TEXT, line_h=None, anchor="start"):
    """Multi-line text: one <text> per line, first baseline at y."""
    lh = line_h or round(size * 1.45)
    return "".join(
        text(x, y + i * lh, line, size, weight, fill, anchor)
        for i, line in enumerate(wrap_lines(s, max_chars))
    )


def rect(x, y, w, h, rx=0, fill="none", stroke=None, sw=1, fo=None, so=None, dash=None):
    a = f'x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}"'
    if rx:
        a += f' rx="{_n(rx)}"'
    a += f' fill="{fill}"'
    if fo is not None:
        a += f' fill-opacity="{_n(fo)}"'
    if stroke:
        a += f' stroke="{stroke}" stroke-width="{_n(sw)}"'
        if so is not None:
            a += f' stroke-opacity="{_n(so)}"'
    if dash:
        a += f' stroke-dasharray="{dash}"'
    return f"<rect {a}/>"


def circle(cx, cy, r, fill=TEXT, stroke=None, sw=1, fo=None):
    a = f'cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" fill="{fill}"'
    if fo is not None:
        a += f' fill-opacity="{_n(fo)}"'
    if stroke:
        a += f' stroke="{stroke}" stroke-width="{_n(sw)}"'
    return f"<circle {a}/>"


def line(x1, y1, x2, y2, stroke=DIVIDER, sw=1, dash=None):
    a = f'x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" stroke="{stroke}" stroke-width="{_n(sw)}"'
    if dash:
        a += f' stroke-dasharray="{dash}"'
    return f"<line {a}/>"


def path(d, fill="none", stroke=None, sw=1.7, linecap="round", linejoin="round"):
    a = f'd="{_attr(d)}" fill="{fill}"'
    if stroke:
        a += (f' stroke="{stroke}" stroke-width="{_n(sw)}" stroke-linecap="{linecap}"'
              f' stroke-linejoin="{linejoin}"')
    return f"<path {a}/>"


_ICON_CACHE = {}


def _icon_shapes(name):
    if name not in _ICON_CACHE:
        root = ET.parse(os.path.join(ICON_DIR, name + ".svg")).getroot()
        shapes = []
        for el in root:
            tag = el.tag.split("}")[-1]
            shapes.append((tag, dict(el.attrib)))
        _ICON_CACHE[name] = (root.get("stroke-width", "1.7"), shapes)
    return _ICON_CACHE[name]


def icon(name, x, y, size=20, color=ICON_IDLE):
    """Stroke icon from app/icons/<name>.svg, placed at (x, y) with side length size."""
    sw, shapes = _icon_shapes(name)
    parts = []
    for tag, attrs in shapes:
        a = " ".join(f'{k}="{_attr(v)}"' for k, v in attrs.items())
        parts.append(f"<{tag} {a}/>")
    return (f'<g transform="translate({_n(x)} {_n(y)}) scale({_n(size / 24.0)})" fill="none" '
            f'stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">'
            + "".join(parts) + "</g>")


_svg_icon = icon


def orb(cx, cy, r):
    """Gradient orb like the app logo: blue base, violet and cyan lobes, soft glow."""
    return (
        circle(cx, cy, r * 1.35, fill="url(#orbGlow)")
        + circle(cx, cy, r, fill="url(#orbBlue)")
        + f'<ellipse cx="{_n(cx - r * 0.2)}" cy="{_n(cy + r * 0.25)}" rx="{_n(r * 0.55)}" ry="{_n(r * 0.4)}" '
          f'fill="url(#orbViolet)" opacity="0.85"/>'
        + f'<ellipse cx="{_n(cx + r * 0.3)}" cy="{_n(cy - r * 0.25)}" rx="{_n(r * 0.5)}" ry="{_n(r * 0.34)}" '
          f'fill="url(#orbCyan)" opacity="0.8"/>'
        + f'<ellipse cx="{_n(cx - r * 0.25)}" cy="{_n(cy - r * 0.42)}" rx="{_n(r * 0.35)}" ry="{_n(r * 0.16)}" '
          f'fill="#ffffff" opacity="0.28"/>'
    )


_DEFS = """
<linearGradient id="cardGrad" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#14224a"/><stop offset="1" stop-color="#101c40"/>
</linearGradient>
<linearGradient id="heroGrad" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#1b2f66"/><stop offset="1" stop-color="#0e1b42"/>
</linearGradient>
<radialGradient id="orbBlue" cx="0.35" cy="0.3" r="0.75">
  <stop offset="0" stop-color="#b7c9ff"/><stop offset="0.35" stop-color="#5a7bf0"/>
  <stop offset="0.7" stop-color="#2a46b8"/><stop offset="1" stop-color="#0f1d55"/>
</radialGradient>
<radialGradient id="orbGlow" cx="0.5" cy="0.5" r="0.5">
  <stop offset="0" stop-color="#7693ff" stop-opacity="0.45"/>
  <stop offset="1" stop-color="#7693ff" stop-opacity="0"/>
</radialGradient>
<radialGradient id="orbViolet" cx="0.4" cy="0.4" r="0.6">
  <stop offset="0" stop-color="#e2c4ff"/><stop offset="0.45" stop-color="#b386ff"/>
  <stop offset="1" stop-color="#5b2fb0" stop-opacity="0.9"/>
</radialGradient>
<radialGradient id="orbCyan" cx="0.4" cy="0.4" r="0.6">
  <stop offset="0" stop-color="#d8fbff"/><stop offset="0.5" stop-color="#66dcf4"/>
  <stop offset="1" stop-color="#1a6f99" stop-opacity="0.9"/>
</radialGradient>
"""


def canvas(body, w=CANVAS_W, h=CANVAS_H):
    """Wrap page body in the SVG root, shared gradient defs and the page background."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f"<defs>{_DEFS}</defs>"
            + rect(0, 0, w, h, fill=BG)
            + body + "</svg>")


def content_box(rail=False):
    """(x, width) of the content column for the given shell mode."""
    x = (RAIL_W if rail else SIDEBAR_W) + 24
    return x, CONTENT_RIGHT - x


def sidebar(active=None, rail=False, diagnostic=None):
    """App sidebar copy. active: nav label such as 'Voz e Wake' (or None). rail: icons-only 56 px mode."""
    w = RAIL_W if rail else SIDEBAR_W
    out = [rect(0, 0, w, CANVAS_H, fill=SIDEBAR_BG), rect(w - 1, 0, 1, CANVAS_H, fill=DIVIDER)]
    if rail:
        out.append(orb(28, 36, 13))
    else:
        out.append(orb(38, 40, 17))
        out.append(text(68, 44, "Gideon", 22, "bold", "#f3f6ff"))
        out.append(text(68, 62, "Assistente pessoal", 12, "normal", "#aabbe1"))
    for gi, (title, title_cy, items) in enumerate(NAV_GROUPS):
        if rail:
            if gi > 0:
                out.append(rect(18, title_cy - 1, 20, 1, fill=DIVIDER))
        else:
            out.append(text(26, title_cy + 4, title, 11, "bold", SECTION_TEXT, letter_spacing=1.3))
        for label, glyph, cy in items:
            on = label == active
            x0, iw = (10, 36) if rail else (14, 204)
            if on:
                out.append(rect(x0, cy - 19, iw, 38, rx=8, fill=ACCENT, fo=0.18))
                out.append(rect(x0, cy - 11, 3, 22, rx=2, fill=ACCENT))
            color = ACCENT if on else ICON_IDLE
            ix = (RAIL_W - 20) / 2 if rail else 24
            out.append(icon(glyph, ix, cy - 10, 20, color))
            if not rail:
                out.append(text(54, cy + 5, label, 14, "bold" if on else "normal",
                                NAV_ACTIVE_TEXT if on else NAV_TEXT))
    if not rail:
        diag = diagnostic or ("Áudio virtual · replay encerrado ·", "pronto · concluído")
        out.append(text(14, 834, diag[0], 11, "normal", MUTED))
        out.append(text(14, 849, diag[1], 11, "normal", MUTED))
        out.append(text(14, 870, "Base local", 12, "normal", MUTED))
        out.append(text(14, 888, "inglês · perfil virtual", 12, "normal", MUTED))
    return "".join(out)


def header(title, subtitle, state="Em espera", x=CONTENT_X, tone="ok"):
    """Page header: title (24 bold), subtitle (14 muted), state pill top-right (dot + word)."""
    pill_w = 44 + text_w(state, 13) + 14
    px = CONTENT_RIGHT - pill_w
    return (
        text(x, 50, title, 24, "bold", TEXT_STRONG)
        + text(x, 74, subtitle, 14, "normal", TEXT_MUTED)
        + rect(px + 0.5, 37.5, pill_w - 1, 29, rx=14.5, fill="#16285a", stroke=CARD_BORDER)
        + orb(px + 15, 52, 7)
        + circle(px + 34, 52, 3.5, fill=TONES.get(tone, OK))
        + text(px + 44, 57, state, 13, "normal", "#dce4f7")
    )


def card(x, y, w, h, title=None):
    """Card background (gradient, 14 px radius, 1 px border) with optional 17px semibold title."""
    out = [rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=14, fill="url(#cardGrad)", stroke=CARD_BORDER)]
    if title:
        out.append(text(x + CARD_PAD, y + CARD_TITLE_BASE, title, 17, "bold", TEXT_STRONG))
    return "".join(out)


def card_body_top(y, titled=True):
    """Y where card content starts: below the title, or CARD_PAD when untitled."""
    return y + (CARD_BODY_TOP if titled else CARD_PAD)


def badge_w(text):
    return text_w(text, 12, "bold") + 20


def badge(x, y, text, tone="ok"):
    """Status badge: tinted pill with the word inside (status is never colour only). 22 px tall."""
    c = TONES[tone]
    w = badge_w(text)
    return (rect(x + 0.5, y + 0.5, w - 1, 21, rx=11, fill=c, fo=0.14, stroke=c, so=0.5)
            + _svg_text(x + 10, y + 15, text, 12, "bold", c))


def chip_w(text, icon=None):
    return 12 + (24 if icon else 0) + text_w(text, 13) + 12


def chip(x, y, text, icon=None, active=False):
    """Selectable chip, 30 px tall. icon: app/icons name or None. active: accent tint, bright text."""
    w = chip_w(text, icon)
    fill = ACCENT if active else "#1a2c57"
    out = [rect(x + 0.5, y + 0.5, w - 1, 29, rx=14.5, fill=fill, fo=0.18 if active else None,
                stroke=ACCENT if active else CARD_BORDER)]
    color = NAV_ACTIVE_TEXT if active else NAV_TEXT
    tx = x + 12
    if icon:
        out.append(_svg_icon(icon, x + 12, y + 7, 16, ACCENT if active else ICON_IDLE))
        tx += 24
    out.append(_svg_text(tx, y + 20, text, 13, "normal", color))
    return "".join(out)


def button_w(text, primary=False):
    return max(92, text_w(text, 14, "bold" if primary else "normal") + 40)


def button(x, y, w, text, primary=False, danger=False, h=40):
    """Button, 40 px tall, 12 px radius. primary = the card's one action; danger = destructive."""
    if primary:
        fill, edge, tcol, wt = BTN_PRIMARY, BTN_PRIMARY_EDGE, "#ffffff", "bold"
    elif danger:
        fill, edge, tcol, wt = DANGER_FILL, DANGER_EDGE, DANGER_TEXT, "normal"
    else:
        fill, edge, tcol, wt = BTN_FILL, BTN_EDGE, TEXT, "normal"
    return (rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=12, fill=fill, stroke=edge)
            + _svg_text(x + w / 2, y + h / 2 + 5, text, 14, wt, tcol, anchor="middle"))


def field(x, y, w, label, value, placeholder=False):
    """Labelled input (label 13 above, 40 px box). Occupies FIELD_H (62) px."""
    return (text(x, y + 13, label, 13, "normal", TEXT_LABEL)
            + rect(x + 0.5, y + 22.5, w - 1, 39, rx=12, fill=INPUT_BG, stroke=DIVIDER)
            + text(x + 14, y + 47, value, 14, "normal", PLACEHOLDER if placeholder else TEXT))


def toggle(x, y, label, on=True):
    """Switch (44x24) with label and a written state word under it. Occupies 40 px height."""
    track = BTN_PRIMARY if on else DIVIDER
    knob_x = x + (32 if on else 12)
    return (rect(x, y, 44, 24, rx=12, fill=track)
            + circle(knob_x, y + 12, 9, fill="#ffffff")
            + text(x + 56, y + 17, label, 14, "normal", TEXT)
            + text(x + 56, y + 36, "Ligado" if on else "Desligado", 12, "normal", OK if on else MUTED))


def slider(x, y, w, value=0.5, left=None, right=None, value_text=None):
    """Horizontal slider, 58 px tall. value 0..1. value_text drawn bold at top-right."""
    v = min(1.0, max(0.0, value))
    kx = x + w * v
    out = [rect(x, y + 30, w, 6, rx=3, fill=DIVIDER),
           rect(x, y + 30, w * v, 6, rx=3, fill=ACCENT),
           circle(kx, y + 33, 10, fill="#ffffff", stroke=ACCENT, sw=3)]
    if value_text is not None:
        out.append(text(x + w, y + 14, value_text, 16, "bold", TEXT_STRONG, anchor="end"))
    if left is not None:
        out.append(text(x, y + 56, left, 12, "normal", MUTED))
    if right is not None:
        out.append(text(x + w, y + 56, right, 12, "normal", MUTED, anchor="end"))
    return "".join(out)


def segmented_w(items):
    return sum(text_w(s, 13, "bold") + 28 for s in items) + 8


def segmented(x, y, items, active):
    """Segment control, 36 px tall. active: index or label of the selected item."""
    idx = items.index(active) if isinstance(active, str) else int(active)
    w = segmented_w(items)
    out = [rect(x + 0.5, y + 0.5, w - 1, 35, rx=12, fill=INPUT_BG, stroke=DIVIDER)]
    cx = x + 4
    for i, s in enumerate(items):
        sw_ = text_w(s, 13, "bold") + 28
        on = i == idx
        if on:
            out.append(rect(cx, y + 4, sw_, 28, rx=9, fill=BTN_PRIMARY))
        out.append(text(cx + sw_ / 2, y + 23, s, 13, "bold" if on else "normal",
                        "#ffffff" if on else TEXT_BODY, anchor="middle"))
        cx += sw_
    return "".join(out)


def row(x, y, w, cols, h=52, divider=True):
    """List row. cols: [(rel_x, content)]. content is a str (14 px text), a dict of text() kwargs
    with key 's', or a callable f(abs_x, centre_y) -> svg (e.g. lambda ax, cy: badge(ax, cy - 11, 'ok', 'ok'))."""
    cy = y + h / 2
    out = []
    for rel, content in cols:
        ax = x + rel
        if callable(content):
            out.append(content(ax, cy))
        elif isinstance(content, dict):
            kw = dict(content)
            s = kw.pop("s")
            out.append(text(ax, cy + 5, s, **kw))
        else:
            out.append(text(ax, cy + 5, str(content), 14, "normal", TEXT))
    if divider:
        out.append(rect(x, y + h - 1, w, 1, fill=DIVIDER))
    return "".join(out)


def collapsible_height(open=False, body_h=0):
    return COLLAPSIBLE_H + (body_h if open else 0)


def collapsible(x, y, w, title, summary, open=False, body_h=0):
    """'Como funciona'-style block: 56 px header (title, 1 summary line, chevron).
    open=True extends the box by body_h; caller draws the body in y+56 .. y+56+body_h."""
    h = collapsible_height(open, body_h)
    out = [rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=12, fill=INPUT_BG, stroke=CARD_BORDER)]
    out.append(text(x + 18, y + 25, title, 15, "bold", TEXT_STRONG))
    out.append(text(x + 18, y + 45, summary, 13, "normal", TEXT_MUTED))
    cx, cy = x + w - 30, y + 28
    if open:
        out.append(path(f"M{_n(cx - 5)} {_n(cy - 3)} L{_n(cx)} {_n(cy + 3)} L{_n(cx + 5)} {_n(cy - 3)}",
                        stroke=ICON_IDLE))
        if body_h:
            out.append(line(x + 1, y + COLLAPSIBLE_H, x + w - 1, y + COLLAPSIBLE_H, stroke=DIVIDER))
    else:
        out.append(path(f"M{_n(cx - 3)} {_n(cy - 5)} L{_n(cx + 3)} {_n(cy)} L{_n(cx - 3)} {_n(cy + 5)}",
                        stroke=ICON_IDLE))
    return "".join(out)


def empty_state(x, y, w, h, icon, text, action=None, primary=True):
    """Empty state: dashed frame, icon, one sentence, one next-step button. Centred in the frame.
    Needs h >= 124 when action is given (h >= 60 without)."""
    action_h = 56 if action else 0
    total = 28 + 12 + 20 + action_h
    top = y + (h - total) / 2
    cx = x + w / 2
    out = [rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=14, fill=INPUT_BG, fo=0.4, stroke=DIVIDER,
                dash="6 5")]
    out.append(_svg_icon(icon, cx - 14, top, 28, MUTED))
    out.append(_svg_text(cx, top + 28 + 12 + 14, text, 14, "normal", TEXT_BODY, anchor="middle"))
    if action:
        bw = button_w(action, primary)
        out.append(button(cx - bw / 2, top + 28 + 12 + 20 + 16, bw, action, primary=primary))
    return "".join(out)
