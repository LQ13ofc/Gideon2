#!/usr/bin/env python3
"""Shared drawing helpers for the Diagnostico mockups (docs/ui-spec/50-diagnostico.md).

Built on scripts/mockup_kit3.py, which is imported and NOT edited. Helpers the kit does not
have are defined here: tone pills for the "•N" counters, full-width header and summary strip
(docs/ui-spec/00-casca.md: x 32 .. width-32), 14 px cards, 40x24 switch, monospace text,
modal with a focus ring, and the PNG render wrapper.

Colours come only from the kit theme tokens (k.T). Layout numbers come from the spec.
"""
import os
import subprocess
import sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import mockup_kit3 as k  # noqa: E402

ROOT = os.path.dirname(SCRIPTS)
OUT_DIR = os.path.join(ROOT, "docs", "ui-mockups-v3")
PY = os.path.join(ROOT, "target", "ui-venv", "bin", "python")
RENDER = os.path.join(SCRIPTS, "render_svg.py")
THEME = "gideon-escuro"
MONO = "DejaVu Sans Mono, Noto Sans Mono, monospace"
CARD_R = 14
W = 1380
H = 904
TABS = [("Assistente", "chat"), ("Extensões", "hub"), ("Permissões", "shield"),
        ("Configurações", "gear"), ("Diagnóstico", "activity")]
NUM = k._k1._n


def set_theme():
    k.set_theme(THEME)


def tone(name):
    return k._tone(name)


# ---------------------------------------------------------------- text

def tx(x, y, s, size=14, weight="normal", fill=None, anchor="start"):
    return k.text(x, y, s, size, weight, fill or k.T["text"], anchor)


def mt(x, y, s, size=14, weight="normal", anchor="start"):
    return k.text(x, y, s, size, weight, k.T["textMuted"], anchor)


def legend(x, y, s, fill=None, anchor="start"):
    """12 px legend (spec: legenda 12 px)."""
    return k.text(x, y, s, 12, "normal", fill or k.T["textMuted"], anchor)


def mono_w(s, size=13):
    return len(str(s)) * size * 0.602


def mono(x, y, s, size=13, fill=None, anchor="start"):
    fill = fill or k.T["text"]
    a = (f'x="{NUM(x)}" y="{NUM(y)}" font-family="{MONO}" font-size="{NUM(size)}" '
         f'fill="{fill}"')
    if anchor != "start":
        a += f' text-anchor="{anchor}"'
    return f"<text {a}>{escape(str(s))}</text>"


def wrap(x, y, s, width, size=14, weight="normal", fill=None, line_h=None):
    return k.wrap_px(x, y, s, width, size, weight, fill or k.T["textMuted"], line_h)


def wrap_lines(s, width, size=14, weight="normal"):
    return k.wrap_px_lines(s, width, size, weight)


def rich_wrap(x, y, name, rest, width, name_tone, size=13, line_h=18):
    """'NAME — rest' with NAME bold in its tone, rest wrapped to width. Returns (svg, lines)."""
    name_w = k.text_w(name, size, "bold")
    off = name_w + 24  # fixed gap: name, 10 px, em dash (~14 px), 8 px (kit space estimate is unreliable)
    out = [k.text(x, y, name, size, "bold", tone(name_tone)),
           k.text(x + name_w + 10, y, "—", size, "normal", k.T["textMuted"])]
    lines, line, avail = [], "", width - off
    for word in str(rest).split():
        cand = word if not line else line + " " + word
        if k.text_w(cand, size) <= avail:
            line = cand
        else:
            lines.append(line)
            line, avail = word, width
    lines.append(line)
    out.append(k.text(x + off, y, lines[0], size, "normal", k.T["text"]))
    for i, ln in enumerate(lines[1:], 1):
        out.append(k.text(x, y + i * line_h, ln, size, "normal", k.T["text"]))
    return "".join(out), len(lines)


def wrap_h(s, width, size=14, line_h=20):
    """Height in px of a wrapped block whose first baseline is at 0 (last baseline + 0)."""
    return (len(wrap_lines(s, width, size)) - 1) * line_h


# ---------------------------------------------------------------- shapes

def card(x, y, w, h, title=None):
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=CARD_R, fill="url(#cardGrad)", stroke=k.T["border"])]
    if title:
        out.append(k.text(x + 20, y + 34, title, 17, "bold", k.T["text"]))
    return "".join(out)


def tone_pill(x, y, label, tone_name):
    """18 px solid pill for counters such as '•1'. Returns (svg, width)."""
    c = tone(tone_name)
    w = k.text_w(label, 11, "bold") + 12
    return (k.rect(x, y, w, 18, rx=9, fill=c)
            + k.text(x + w / 2, y + 13, label, 11, "bold", k.T["bg"], anchor="middle")), w


def badge_at(x, base, label, tone_name):
    """22 px badge whose text baseline is `base` (badge top = base - 15)."""
    return k.badge(x, base - 15, label, tone_name)


def dot_line(x, base, s, tone_name, size=14, weight="normal"):
    """Coloured dot plus text. The word carries the status; the dot only repeats it."""
    return (k.circle(x + 4, base - 5, 4, fill=tone(tone_name))
            + k.text(x + 16, base, s, size, weight, k.T["text"]))


def switch(x, top, on=True, disabled=False):
    """40 x 24 switch (spec S20). The state word is written next to it by the caller."""
    if disabled:
        track, knob = k.T["disabled"], k.T["surface"]
    else:
        track = k.T["accent"] if on else k.T["outline"]
        knob = k.T["onAccent"] if on else k.T["surface"]
    return (k.rect(x, top, 40, 24, rx=12, fill=track)
            + k.circle(x + (28 if on else 12), top + 12, 9, fill=knob))


def mono_box(x, y, w, h, value=None, placeholder=None):
    """Monospace text area / field (spec D16, D20). 13 px mono text, 14 px radius."""
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill=k.T["surfaceVariant"], stroke=k.T["border"])]
    if value:
        out.append(mono(x + 14, y + 26, value, 13, k.T["text"]))
    elif placeholder:
        out.append(mono(x + 14, y + 26, placeholder, 13, k.T["placeholder"]))
    return "".join(out)


def chevron(x, y, down=False):
    if down:
        return k.path(f"M{NUM(x - 5)} {NUM(y - 3)} L{NUM(x)} {NUM(y + 3)} L{NUM(x + 5)} {NUM(y - 3)}",
                      stroke=k.T["textMuted"])
    return k.path(f"M{NUM(x - 3)} {NUM(y - 5)} L{NUM(x + 3)} {NUM(y)} L{NUM(x - 3)} {NUM(y + 5)}",
                  stroke=k.T["textMuted"])


# ---------------------------------------------------------------- shell (docs/ui-spec/00-casca.md)

def topbar(active, badges=None, state="Em espera", state_tone="muted", width=W):
    """Level-1 bar y 0-56. badges: {tab label: (n, tone)} drawn as '•n' in the tone colour."""
    badges = badges or {}
    out = [k.rect(0, 0, width, 56, fill=k.T["surface"]), k.rect(0, 55, width, 1, fill=k.T["border"]),
           k.orb(30, 28, 14), k.text(52, 34, "Gideon", 16, "bold", k.T["text"])]
    x = 132
    for label, icon_name in TABS:
        on = label == active
        b = badges.get(label)
        lw = k.text_w(label, 14, "bold")
        bw = (8 + k.text_w(f"•{b[0]}", 11, "bold") + 12) if b else 0
        tw = 14 + 18 + 8 + lw + 14 + bw
        if on:
            out.append(k.rect(x, 8, tw, 40, rx=8, fill=k.T["tint"]))
            out.append(k.rect(x, 53, tw, 3, rx=1.5, fill=k.T["accent"]))
        out.append(k.icon(icon_name, x + 14, 19, 18, k.T["accent"] if on else k.T["textMuted"]))
        out.append(k.text(x + 40, 33, label, 14, "bold" if on else "normal",
                          k.T["text"] if on else k.T["textMuted"]))
        if b:
            out.append(tone_pill(x + 40 + lw + 8, 19, f"•{b[0]}", b[1])[0])
        x += tw + 4
    _, pw = k._state_pill(0, 13, state, state_tone)
    right = width - 16 - pw
    out.append(k._state_pill(right, 13, state, state_tone)[0])
    right -= 8 + 120
    out.append(k._search_button(right, 13))
    return "".join(out)


def rail_topbar(active, badges=None, state="Em espera", state_tone="muted", width=900):
    """Icon-only level-1 bar for narrow windows (spec 00-casca: abas viram só ícones).
    Tooltips carry the tab names in the app; the state keeps its word next to the dot."""
    badges = badges or {}
    out = [k.rect(0, 0, width, 56, fill=k.T["surface"]), k.rect(0, 55, width, 1, fill=k.T["border"]),
           k.orb(28, 28, 11)]
    x = 60
    for label, icon_name in TABS:
        on = label == active
        if on:
            out.append(k.rect(x, 8, 44, 40, rx=8, fill=k.T["tint"]))
            out.append(k.rect(x, 53, 44, 3, rx=1.5, fill=k.T["accent"]))
        out.append(k.icon(icon_name, x + 13, 19, 18, k.T["accent"] if on else k.T["textMuted"]))
        b = badges.get(label)
        if b:
            out.append(k.circle(x + 36, 16, 7, fill=tone(b[1]))
                       + k.text(x + 36, 19.5, str(b[0]), 9, "bold", k.T["bg"], anchor="middle"))
        x += 48
    _, pw = k._state_pill(0, 13, state, state_tone)
    right = width - 16 - pw
    out.append(k._state_pill(right, 13, state, state_tone)[0])
    right -= 8 + 30
    out.append(k.rect(right + 0.5, 13.5, 29, 29, rx=8, fill=k.T["surfaceVariant"], stroke=k.T["border"]))
    out.append(k.circle(right + 14, 27, 4.5, stroke=k.T["textMuted"], sw=1.5)
               + k.line(right + 17.5, 30.5, right + 21, 34, stroke=k.T["textMuted"], sw=1.5))
    return "".join(out)


def subtabs(items, active, disabled=(), badges=None, width=W):
    """Level-2 bar y 56-100. badges: {label: (n, tone)}; 'Recuperação' uses '•1' in Aviso."""
    badges = badges or {}
    out = [k.rect(0, 56, width, 44, fill=k.T["bg"])]
    x = 18
    for label in items:
        on = label == active
        lw = k.text_w(label, 14, "bold")
        b = badges.get(label)
        bw = (8 + k.text_w(f"•{b[0]}", 11, "bold") + 12) if b else 0
        tw = 36 + lw + bw
        if label in disabled:
            color = k.T["disabled"]
        elif on:
            color = k.T["text"]
        else:
            color = k.T["textMuted"]
        out.append(k.text(x + 18, 83, label, 14, "bold" if on else "normal", color))
        if b:
            out.append(tone_pill(x + 18 + lw + 8, 69, f"•{b[0]}", b[1])[0])
        if on:
            out.append(k.rect(x, 98, tw, 2, fill=k.T["accent"]))
        x += tw
    out.append(k.rect(0, 99, width, 1, fill=k.T["border"]))
    return "".join(out)


def header(title, subtitle, width=W):
    """Header title baseline 138 (24 px bold), subtitle baseline 163 (14 px). x 32 .. width-32."""
    return (k.text(32, 138, title, 24, "bold", k.T["text"])
            + k.text(32, 163, subtitle, 14, "normal", k.T["textMuted"]))


def summary(text_s, badges=(), width=W, fill=None):
    """Summary strip y 184, 40 px, x 32 .. width-32. Returns (svg, left edge of the badges)."""
    x, w, y = 32, width - 64, 184
    out = [k.rect(x + 0.5, y + 0.5, w - 1, 39, rx=10, fill=k.T["surface"], stroke=k.T["border"]),
           k.text(x + 16, y + 25, text_s, 14, "bold", fill or k.T["text"])]
    cursor = x + w - 12
    for label, tn in reversed(list(badges)):
        bw = k.badge_w(label)
        cursor -= bw
        out.append(k.badge(cursor, y + 9, label, tn))
        cursor -= 8
    return "".join(out), cursor


# ---------------------------------------------------------------- grid

def content(width):
    """(x, w) of the content column: 32 px margins, max 1100, centred above 1240 px."""
    cw = min(1100, width - 64)
    cx = (width - cw) / 2.0 if width >= 1240 else 32
    return cx, cw


def grid(width, y, h1, h2, stacked=False):
    """Two blocks: span 6 + 6 (gap 16), or stacked (reflow). Returns ((x, y, w), (x, y, w))."""
    cx, cw = content(width)
    if stacked:
        return (cx, y, cw), (cx, y + h1 + 16, cw)
    half = (cw - 16) / 2.0
    return (cx, y, half), (cx + half + 16, y, half)


def row_bottom(y, h1, h2, stacked=False):
    return y + h1 + 16 + h2 if stacked else y + max(h1, h2)


def full(width, y):
    cx, cw = content(width)
    return cx, y, cw


# ---------------------------------------------------------------- controls

def scrim(width=W, height=H, op=0.6):
    return k.scrim(width, height, op)


def modal_height(w, body):
    n = len(wrap_lines(body, w - 48, 14))
    return 70 + (n - 1) * 20 + 36 + 40 + 24


def modal(x, y, w, title, body, buttons):
    """Dialog 14 px radius. buttons: [(label, variant, focus)], right aligned, Cancelar focused."""
    h = modal_height(w, body)
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=14, fill=k.T["surface"], stroke=k.T["border"]),
           k.text(x + 24, y + 38, title, 18, "bold", k.T["text"]),
           wrap(x + 24, y + 70, body, w - 48, 14, "normal", k.T["textMuted"], line_h=20)]
    bx = x + w - 24
    top = y + h - 24 - 40
    for label, variant, focus in reversed(list(buttons)):
        bw = k.button_w(label, primary=variant == "primary")
        bx -= bw
        out.append(k.button(bx, top, bw, label, variant=variant, state="focus" if focus else "normal"))
        bx -= 8
    return "".join(out), h


def centred_modal(width, height, w, title, body, buttons):
    """Modal centred on the canvas, with the scrim under it."""
    h = modal_height(w, body)
    x = (width - w) / 2.0
    y = (height - h) / 2.0
    svg, _ = modal(x, y, w, title, body, buttons)
    return scrim(width, height, 0.6) + svg


# ---------------------------------------------------------------- output

def write_and_render(name, svg, width, height):
    os.makedirs(OUT_DIR, exist_ok=True)
    svg_path = os.path.join(OUT_DIR, name + ".svg")
    png_path = os.path.join(OUT_DIR, name + ".png")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    subprocess.run([PY, "-I", "-B", RENDER, svg_path, png_path, str(width), str(height)], check=True)
    print("wrote", png_path)
    return png_path
