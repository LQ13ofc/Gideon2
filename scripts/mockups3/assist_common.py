#!/usr/bin/env python3
"""Shared helpers for the 'Assistente' mockups (docs/ui-spec/10-assistente.md).

Built on scripts/mockup_kit3.py (imported, never edited). Helpers the kit does not have are
defined here. Every colour comes from the current kit theme tokens (k.T); call k.set_theme()
before building a page.

Render: target/ui-venv/bin/python -I -B scripts/render_svg.py <file>.svg
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

T = k.T
W, H = k.CANVAS_W, k.CANVAS_H
OUT_DIR = os.path.join(ROOT, "docs", "ui-mockups-v3")
PY = os.path.join(ROOT, "target", "ui-venv", "bin", "python")
RENDER = os.path.join(SCRIPTS, "render_svg.py")

COL_X, COL_W = k.content_box(W)          # 140, 1100 (spec 10, section 0)
IN_X = COL_X + 20                        # 160: inner x of cards
IN_R = COL_X + COL_W - 20                # 1220: inner right edge
SUBS = ["Hoje", "Conversa", "Agente", "Atividade"]
RISK_TONE = {"baixo": "ok", "médio": "warn", "alto": "err"}


# ---------------------------------------------------------------- page frame

def shell(sub, title, subtitle, state, tone, cancel=False):
    """Level-1 bar, level-2 bar and the sub-tab header (spec 00-casca, 10 section 1.1)."""
    return (k.topbar("Assistente", state=state, state_tone=tone, cancel=cancel)
            + k.subtabs(SUBS, sub)
            + k.page_header(title, subtitle))


def chip26_w(label):
    return k.text_w(label, 13) + 24


def chip26(x, y, label):
    """26 px chip for the summary strip (spec 10, H-02..H-04)."""
    w = chip26_w(label)
    return (k.rect(x + 0.5, y + 0.5, w - 1, 25, rx=13, fill=T["surfaceVariant"], stroke=T["border"])
            + k.text(x + 12, y + 17.5, label, 13, "normal", T["text"]))


def strip(text_s, right=()):
    """Summary strip y 184-224 (40 px). right: ('chip', label) or ('badge', label, tone), drawn right to left."""
    x, w = COL_X, COL_W
    y = 184
    out = [k.rect(x + 0.5, y + 0.5, w - 1, 39, rx=10, fill=T["surface"], stroke=T["border"]),
           k.text(x + 16, y + 25, text_s, 14, "bold", T["text"])]
    cur = x + w - 20
    for item in reversed(list(right)):
        if item[0] == "chip":
            cur -= chip26_w(item[1])
            out.append(chip26(cur, y + 7, item[1]))
        else:
            cur -= k.badge_w(item[1])
            out.append(k.badge(cur, y + 9, item[1], item[2]))
        cur -= 8
    return "".join(out)


def segmented5(x, y, items, active):
    """Filter control of the Atividade strip: 5 segments of 90 px, 30 px tall (spec 10, 6.4)."""
    out = [k.rect(x + 0.5, y + 0.5, 90 * len(items) - 1, 29, rx=8, fill=T["surfaceVariant"], stroke=T["border"])]
    for i, lab in enumerate(items):
        sx = x + 90 * i
        on = lab == active
        if on:
            out.append(k.rect(sx + 3, y + 3, 84, 24, rx=6, fill=T["tint"], stroke=T["accent"], sw=1))
        out.append(k.text(sx + 45, y + 20, lab, 13, "bold" if on else "normal",
                          T["text"] if on else T["textMuted"], anchor="middle"))
    return "".join(out)


# ---------------------------------------------------------------- controls

def button_pair(right_x, y):
    """Negar (danger outline, 100 px) + Autorizar (primary, 108 px), right aligned to right_x, 40 px tall."""
    return (danger_outline(right_x - 108 - 12 - 100, y, 100, "Negar")
            + k.button(right_x - 108, y, 108, "Autorizar", variant="primary"))


def danger_outline(x, y, w, label, h=40):
    """Perigo: contorno e texto #ff7d8a (spec 10, section 0 / 00-casca)."""
    return (k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill="none", stroke=T["error"], sw=1)
            + k.text(x + w / 2, y + h / 2 + 5, label, 14, "normal", T["error"], anchor="middle"))


def input_disabled(x, y, w, h, value):
    """Disabled text field: keeps the value, muted colours, no focus ring."""
    return (k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill=T["surfaceVariant"], stroke=T["border"])
            + k.text(x + 14, y + h / 2 + 5, value, 14, "normal", T["disabled"]))


def orb_listening(cx, cy, r):
    """Orb with two-step ripple rings drawn outside the base orb (spec 10, H-06 'Ouvindo')."""
    rings = "".join(k.circle(cx, cy, r * f, stroke=T["accent"], sw=1.5, so=op)
                    for f, op in ((1.1, 0.55), (1.25, 0.35), (1.4, 0.18)))
    return k.orb(cx, cy, r, "idle") + rings


def empty_frame(x, y, w, h):
    """Dashed empty-state frame (spec 00-casca, 'Estado vazio')."""
    return k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=14, fill=T["surfaceVariant"], fo=0.4,
                  stroke=T["outline"], so=0.6, dash="6 5")


# ---------------------------------------------------------------- blocks

def proposal_box(x, y, w, h, title, target, effect, risk):
    """Inline tool proposal (spec 10, CV-07 / AG-13): title, Alvo + Efeito line, Risco badge, buttons.
    Buttons sit bottom-right with 8 px bottom padding; the risk badge sits bottom-left."""
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill=T["surfaceVariant"], stroke=T["border"]),
           k.text(x + 16, y + 24, title, 14, "bold", T["text"]),
           k.text(x + 16, y + 46, f"Alvo: {target} · Efeito: {effect}", 14, "normal", T["text"]),
           k.text(x + 16, y + 68, "Risco:", 14, "normal", T["textMuted"])]
    out.append(k.badge(x + 16 + k.text_w("Risco: ", 14) + 2, y + 53, risk, RISK_TONE[risk]))
    out.append(button_pair(x + w - 16, y + h - 8 - 40))
    return "".join(out)


def chat_bubble(x, y, w, who, body, role):
    """Chat bubble with a 12 px label line and 14 px body (spec 10, CV-04/CV-05). Returns (svg, height)."""
    lines = k.wrap_px_lines(body, w - 28, 14)
    h = 43 + (len(lines) - 1) * 20 + 14
    fill = T["tint"] if role == "user" else T["surfaceVariant"]
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill=fill, stroke=T["border"]),
           k.text(x + 14, y + 22, who, 12, "bold", T["textMuted"])]
    for i, ln in enumerate(lines):
        out.append(k.text(x + 14, y + 42 + i * 20, ln, 14, "normal", T["text"]))
    return "".join(out), h


def receipt_line(x, y, word, tone, rest):
    """'Gideon · <palavra> · <texto>' (spec 10, H-26). The status word carries the colour."""
    out, cx = [], x
    s = "Gideon · "
    out.append(k.text(cx, y, s, 14, "normal", T["textMuted"]))
    cx += k.text_w(s, 14)
    out.append(k.text(cx, y, word, 14, "bold", T[k.TONE_TOKEN[tone]]))
    cx += k.text_w(word, 14, "bold")
    out.append(k.text(cx, y, " · " + rest, 14, "normal", T["text"]))
    return "".join(out)


def comando_block(y0, busy=False, last=None, receipt=None, motive=None):
    """Card C 'Comando e última interação' (spec 10, H-19..H-27) at top y0 (616 with proposal, 420 without).
    All y offsets come from the spec table (tops minus card top). busy: field disabled + motive."""
    out = [k.card(COL_X, y0, COL_W, 264)]
    out.append(k.text(IN_X, y0 + 28, "Comando", 17, "bold", T["text"]))
    out.append(k.text(IN_X, y0 + 48, "Texto segue o mesmo caminho da voz. Até 512 bytes, em uma linha.",
                      12, "normal", T["textMuted"]))
    fy = y0 + 56
    if busy:
        out.append(input_disabled(IN_X, fy, 920, 44, "Diga ou digite um comando"))
    else:
        out.append(k.input_box(IN_X, fy, 920, 44, "Diga ou digite um comando", placeholder=True))
    out.append(k.button(1092, fy, 128, "Enviar", variant="primary", h=44, state="disabled"))
    if motive:
        out.append(k.text(IN_X, y0 + 118, motive, 12, "normal", T["warning"]))
    out.append(k.text(IN_X, y0 + 143, "Última interação", 14, "bold", T["text"]))
    if last:
        out.append(k.rect(IN_X + 0.5, y0 + 152.5, 1059, 39, rx=10, fill=T["surfaceVariant"], stroke=T["border"]))
        out.append(k.text(IN_X + 14, y0 + 177, last, 14, "normal", T["text"]))
    else:
        out.append(k.text(IN_X, y0 + 177, "Sua conversa aparecerá aqui.", 14, "normal", T["textMuted"]))
    if receipt:
        out.append(receipt_line(IN_X, y0 + 215, *receipt))
    return "".join(out)


def render(name, svg_text):
    """Write docs/ui-mockups-v3/<name>.svg and render <name>.png next to it. Returns the PNG path."""
    os.makedirs(OUT_DIR, exist_ok=True)
    svg_path = os.path.join(OUT_DIR, name + ".svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_text)
    subprocess.run([PY, "-I", "-B", RENDER, svg_path], check=True)
    return os.path.join(OUT_DIR, name + ".png")
