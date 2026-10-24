#!/usr/bin/env python3
"""Shared helpers for the Extensoes mockups (b03 Conexoes, b04 Modelos LLM, b05 Percepcao e acao).

Built on scripts/mockup_kit3.py, which is imported and NOT edited. Helpers the kit lacks are defined
here: the shell with the Extensoes sub-tab bar (sub-tab badges in tone colours), the spec header and
summary strip (x 32, width 1316, per docs/ui-spec/20-extensoes.md 0.3 and 1.3-1.4), a discreet tag,
a warning banner, a switch, a menu button, a code box, numbered steps and a status indicator.
Every colour comes from the current theme tokens (k.T); nothing is hardcoded.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
ROOT = os.path.dirname(SCRIPTS)
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import mockup_kit3 as k  # noqa: E402

THEME = "gideon-escuro"
k.set_theme(THEME)

W, H = k.CANVAS_W, k.CANVAS_H
OUT_DIR = os.path.join(ROOT, "docs", "ui-mockups-v3")
PY = os.path.join(ROOT, "target", "ui-venv", "bin", "python")
RENDER = os.path.join(SCRIPTS, "render_svg.py")

SUBTABS = ["Plugins", "Skills", "Conexões", "Modelos LLM", "Percepção e ação"]
# Plugins: 1 plugin failed (mic_advanced). Conexões: 2 pending accounts (Aviso). Spec 1.2.
SUB_BADGES = {"Plugins": (1, "err"), "Conexões": (2, "warn")}

CX, CW = 140, 1100      # content area (spec 0.3): x 140, width 1100, y 236 to 880
RX = 698                # right column (140 + 542 + 16)
HW = 542                # half column (span 6)
HDR_X, HDR_W = 32, 1316  # header and summary strip (spec 0.3, 1.3, 1.4)
BOTTOM = 880            # content bottom: 904 - 24

_TONE_TOKEN = {"ok": "success", "warn": "warning", "err": "error", "info": "info", "muted": "textMuted"}


def tone(name):
    """Tone name (ok, warn, err, info, muted) to theme colour."""
    return k.T[_TONE_TOKEN[name]]


def subtabs(active, badges=None):
    """Level-2 bar y 56 to 100 with the five Extensoes sub-tabs. Badges: {label: (n, tone)}."""
    badges = SUB_BADGES if badges is None else badges
    out = [k.rect(0, 56, W, 44, fill=k.T["bg"])]
    x = 18
    for label in SUBTABS:
        on = label == active
        lw = k.text_w(label, 14, "bold")
        n = badges.get(label)
        pw = 0
        if n:
            pw = max(18, k.text_w(str(n[0]), 11, "bold") + 10)
        tw = 36 + lw + ((8 + pw) if n else 0)
        color = k.T["text"] if on else k.T["textMuted"]
        out.append(k.text(x + 18, 83, label, 14, "bold" if on else "normal", color))
        if n:
            px = x + 18 + lw + 8
            out.append(k.rect(px, 69, pw, 18, rx=9, fill=tone(n[1])))
            out.append(k.text(px + pw / 2, 82, str(n[0]), 11, "bold", k.T["bg"], anchor="middle"))
        if on:
            out.append(k.rect(x, 98, tw, 2, fill=k.T["accent"]))
        x += tw
    out.append(k.rect(0, 99, W, 1, fill=k.T["border"]))
    return "".join(out)


def header(title, subtitle, action=None):
    """Sub-tab header: title 24 bold at baseline 138, subtitle 14 at 163, primary action right at y 116."""
    out = [k.text(HDR_X, 138, title, 24, "bold", k.T["text"]),
           k.text(HDR_X, 163, subtitle, 14, "normal", k.T["textMuted"])]
    if action:
        bw = k.button_w(action, primary=True)
        out.append(k.button(HDR_X + HDR_W - bw, 116, bw, action, variant="primary"))
    return "".join(out)


def summary(text, badges=()):
    """Summary strip y 184, height 40, x 32, width 1316. Sentence left, badges right."""
    x, y, w = HDR_X, 184, HDR_W
    out = [k.rect(x + 0.5, y + 0.5, w - 1, 39, rx=10, fill=k.T["surface"], stroke=k.T["border"]),
           k.text(x + 16, y + 25, text, 14, "bold", k.T["text"])]
    cur = x + w - 12
    for label, tn in reversed(list(badges)):
        cur -= k.badge_w(label)
        out.append(k.badge(cur, y + 9, label, tn))
        cur -= 8
    return "".join(out)


def frame(active, title, subtitle, segments, seg_active, action=None, summary_text="", summary_badges=()):
    """Shell for one sub-tab: top bar, sub-tab bar, header, summary strip and segment bar (y 236)."""
    return "".join([
        k.topbar("Extensões"),
        subtabs(active),
        header(title, subtitle, action),
        summary(summary_text, summary_badges),
        k.segmented(CX, 236, segments, seg_active),
    ])


def tag(x, y, label, tn="muted"):
    """Discreet 18 px outline tag (honesty seal). Returns (svg, width)."""
    c = tone(tn)
    w = k.text_w(label, 12) + 18
    svg = (k.rect(x + 0.5, y + 0.5, w - 1, 17, rx=8.5, fill="none", stroke=c, so=0.7)
           + k.text(x + 9, y + 13, label, 12, "normal", c))
    return svg, w


def banner(x, y, w, msg, tn="warn", size=13):
    """Warning banner: tinted box, triangle glyph, text wrapped inside. Returns (svg, height)."""
    c = tone(tn)
    text_w_ = w - 80  # 44 px to the text on the left, 36 px of right padding (kit text metrics are estimates)
    body_h = k.wrap_px_height(msg, text_w_, size)
    h = 24 + body_h
    gx, gy = x + 18, y + h / 2
    glyph = (k.path(f"M{gx:.2f} {gy - 8:.2f} L{gx + 8:.2f} {gy + 6:.2f} L{gx - 8:.2f} {gy + 6:.2f} Z",
                    stroke=c, sw=1.6)
             + k.line(gx, gy - 3, gx, gy + 1.5, stroke=c, sw=1.8))
    out = (k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill=c, fo=0.12, stroke=c, so=0.5)
           + glyph
           + k.wrap_px(x + 44, y + 12 + size, msg, text_w_, size, "normal", k.T["text"]))
    return out, h


def switch(x, y, label, on=False):
    """44x24 switch with the state text to its right. Occupies 24 px height."""
    track = k.T["accent"] if on else k.T["outline"]
    knob = x + (32 if on else 12)
    return (k.rect(x, y, 44, 24, rx=12, fill=track)
            + k.circle(knob, y + 12, 9, fill=k.T["onAccent"] if on else k.T["surface"])
            + k.text(x + 56, y + 17, label, 14, "normal", k.T["text"]))


def switch_w(label):
    return 56 + k.text_w(label, 14)


def menu_btn(x, y):
    """40x40 overflow button with three dots ("Mais ações de <nome>")."""
    out = [k.rect(x + 0.5, y + 0.5, 39, 39, rx=10, fill=k.T["surfaceVariant"], stroke=k.T["outline"], so=0.6)]
    for i in range(3):
        out.append(k.circle(x + 14 + i * 6, y + 20, 2, fill=k.T["text"]))
    return "".join(out)


def code_box(x, y, w, label, code):
    """Label 13 above a 44 px box with a spaced code. Returns (svg, height 66)."""
    out = [k.text(x, y + 12, label, 13, "normal", k.T["textMuted"]),
           k.rect(x + 0.5, y + 22.5, w - 1, 43, rx=10, fill=k.T["surfaceVariant"], stroke=k.T["border"]),
           k.text(x + 18, y + 51, code, 20, "bold", k.T["text"], letter_spacing=3)]
    return "".join(out), 66


def numbered(x, y, w, items, size=14):
    """Numbered steps, each a circle with the number and wrapped text. Returns (svg, height)."""
    out, cy = [], y
    for i, s in enumerate(items, 1):
        th = k.wrap_px_height(s, w - 30, size)
        out.append(k.circle(x + 11, cy + 11, 11, fill=k.T["surfaceVariant"], stroke=k.T["outline"], sw=1))
        out.append(k.text(x + 11, cy + 15, str(i), 12, "bold", k.T["text"], anchor="middle"))
        out.append(k.wrap_px(x + 30, cy + 15, s, w - 30, size, "normal", k.T["text"]))
        cy += max(22, th + 6) + 12
    return "".join(out), cy - y - 12


def indicator(x, y, label, word, tn):
    """Status dot + text with the state word (colour is never the only cue)."""
    return (k.circle(x + 6, y + 10, 5, fill=tone(tn))
            + k.text(x + 20, y + 15, label, 14, "normal", k.T["text"]))


def link(x, y, label, size=13):
    return k.text(x, y, label, size, "bold", k.T["accent"])


def mask_below(y):
    """Background strip under y: draws the scroll viewport edge for content that continues below."""
    return k.rect(0, y, W, H - y, fill=k.T["bg"])


def write(name, body):
    """Write docs/ui-mockups-v3/<name>.svg and render <name>.png at 1380x904."""
    os.makedirs(OUT_DIR, exist_ok=True)
    svg_path = os.path.join(OUT_DIR, name + ".svg")
    png_path = os.path.join(OUT_DIR, name + ".png")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(k.canvas(body))
    subprocess.run([PY, "-I", "-B", RENDER, svg_path, png_path, str(W), str(H)], check=True)
    print("wrote", png_path)
    return png_path
