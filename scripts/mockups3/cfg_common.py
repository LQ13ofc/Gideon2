#!/usr/bin/env python3
"""Shared helpers for the Configurações mockups (docs/ui-spec/40-configuracoes.md).

Built on scripts/mockup_kit3.py (imported, never edited). Helpers the kit does not have
are defined here: full-width summary strip, header with x 32, primary action at
(1228, 116, 120, 40), danger outline button, disabled wrapper, preset thumbnails,
accent tiles, live preview card, dialog/modal with custom body, search row.

Colours come from the kit's current theme tokens (k.T), except preset thumbnails, which
show each preset's own palette from k.THEMES (that is the data being shown).
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

OUT_DIR = os.path.join(ROOT, "docs", "ui-mockups-v3")
PY = os.path.join(ROOT, "target", "ui-venv", "bin", "python")
RENDER = os.path.join(SCRIPTS, "render_svg.py")
W, H = k.CANVAS_W, k.CANVAS_H

SUBTABS = ["Voz e Wake", "Áudio", "Dispositivos", "Aparência", "Privacidade", "Geral"]
# Spec accents (docs/ui-spec/40-configuracoes.md AP-9 to AP-12 and section 10).
ACCENTS = [("Azul", "#7693ff"), ("Violeta", "#b386ff"), ("Ciano", "#66dcf4"), ("Rosa", "#f28bd7")]
ACCENT_DEFAULT = "#7693ff"
# Eight presets (docs/research/ux-temas.md 6.4) as (label, theme key in mockup_kit3.THEMES).
PRESETS = [
    ("Gideon escuro", "gideon-escuro"),
    ("Gideon claro", "gideon-claro"),
    ("Alto contraste", "alto-contraste"),
    ("Breeze-like escuro", "breeze-escuro"),
    ("Breeze-like claro", "breeze-claro"),
    ("Mocha-like", "catppuccin"),
    ("Nord-like", "nord"),
    ("Daltonismo-seguro", "daltonismo"),
]
DENSITY_STEPS = ["Compacta", "Normal", "Espaçosa"]
DENSITY_PAD = {"Compacta": 8, "Normal": 12, "Espaçosa": 16}

# Content column (docs/ui-spec/00-casca.md + 40 section 1): x 140, w 1100.
CX, CW = 140, 1100
LX, RX, HALF = 140, 698, 542   # two 6-column cards
DISABLED_OPACITY = 0.42


def use_theme(name, accent=ACCENT_DEFAULT):
    """Set theme, then the accent (set_theme resets accent to the preset's own)."""
    k.set_theme(name)
    if accent:
        k.set_accent(accent)


def T(name):
    return k.T[name]


def dis(svg):
    """Disabled look: the control is drawn normally, then faded as a group."""
    return f'<g opacity="{DISABLED_OPACITY}">{svg}</g>'


def label(x, y, s, color=None):
    """13 px label above a control (muted)."""
    return k.text(x, y, s, 13, "normal", color or T("textMuted"))


def body(x, y, s, size=14, weight="normal", color=None):
    return k.text(x, y, s, size, weight, color or T("text"))


def note(x, y, s, color=None):
    """12 px help line, one line."""
    return k.text(x, y, s, 12, "normal", color or T("textMuted"))


def note_wrap(x, y, s, width, color=None, line_h=17):
    return k.wrap_px(x, y, s, width, 12, "normal", color or T("textMuted"), line_h=line_h)


def reason(x, y, s, width=502, line_h=16):
    """Disabled-row reason, 12 px, text starts with 'Indisponível: '."""
    return k.wrap_px(x, y, s, width, 12, "normal", T("textMuted"), line_h=line_h)


def reason_h(s, width=502, line_h=16):
    return k.wrap_px_height(s, width, 12, "normal", line_h)


def link(x, y, s):
    """Accent text link (no button)."""
    return k.text(x, y, s, 14, "bold", T("accent"))


def modified(x, y, h, tone=None):
    """Left bar marking a changed option (APP_DESCRICAO 6, Busca)."""
    return k.modified_marker(x, y, h, tone)


# ---------------------------------------------------------------- shell


def topbar(state="Em espera", tone="ok"):
    return k.topbar("Configurações", state=state, state_tone=tone)


def subtabs(active):
    return k.subtabs(SUBTABS, active)


def header(title, subtitle):
    """Title baseline 138 and subtitle baseline 163 at x 32 (spec 40 section 1)."""
    return (k.text(32, 138, title, 24, "bold", T("text"))
            + k.text(32, 163, subtitle, 14, "normal", T("textMuted")))


def primary_action(label_s, enabled=True):
    """Header action at (1228, 116, 120, 40), only in Áudio."""
    return k.button(1228, 116, 120, label_s, variant="primary", state="normal" if enabled else "disabled")


def summary(text_s, badges=()):
    """Summary strip (32, 184, 1316, 40): bold sentence left, badges right."""
    x, w, y = 32, 1316, 184
    out = [k.rect(x + 0.5, y + 0.5, w - 1, 39, rx=10, fill=T("surface"), stroke=T("border")),
           k.text(x + 16, y + 25, text_s, 14, "bold", T("text"))]
    cur = x + w - 12
    for lab, tone in reversed(list(badges)):
        bw = k.badge_w(lab)
        cur -= bw
        out.append(k.badge(cur, y + 9, lab, tone))
        cur -= 8
    return "".join(out)


def shell(active, title, subtitle, summary_text, badges=(), action="", state="Em espera", tone="ok"):
    """Topbar + sub-tabs + header + summary. action: extra SVG for the header (e.g. primary_action)."""
    return "".join([topbar(state, tone), subtabs(active), header(title, subtitle), action,
                    summary(summary_text, badges)])


def como(y, text_s):
    """'Como funciona' collapsed, (140, y, 1100, 56)."""
    return k.collapsible(CX, y, CW, "Como funciona", text_s)


# ---------------------------------------------------------------- buttons


def danger(x, y, w, label_s, h=40, disabled=False, focus=False):
    """Danger outline button: contour and text in error colour (casca: Perigo)."""
    col = T("disabled") if disabled else T("error")
    stroke = T("border") if disabled else T("error")
    out = []
    if focus:
        out.append(k.rect(x - 2, y - 2, w + 4, h + 4, rx=12, stroke=T("accent"), sw=2))
    out.append(k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill="none", stroke=stroke, sw=1.5))
    out.append(k.text(x + w / 2, y + h / 2 + 5, label_s, 14, "bold", col, anchor="middle"))
    return "".join(out)


def button(x, y, w, label_s, variant="secondary", state="normal", h=40):
    return k.button(x, y, w, label_s, variant=variant, state=state, h=h)


def bw(label_s, minimum=92):
    return max(minimum, k.text_w(label_s, 14, "normal") + 40)


# ---------------------------------------------------------------- tiles, previews


def check_path(x, y, size, color):
    return k.path(f"M{x + size * 0.3:.2f} {y + size * 0.52:.2f} L{x + size * 0.45:.2f} {y + size * 0.66:.2f} "
                  f"L{x + size * 0.72:.2f} {y + size * 0.36:.2f}", stroke=color, sw=2.2)


def preset_thumb(x, y, name, key, selected, w=116, h=64):
    """One preset: mini window in that preset's own palette, name below, check if selected."""
    th = k.THEMES[key]
    ring = T("accent") if selected else T("border")
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill=th["bg"], stroke=ring,
                  sw=2 if selected else 1)]
    out.append(k.rect(x + 8, y + 8, w - 16, h - 16, rx=6, fill=th["surface"], stroke=th["outline"], so=0.4))
    out.append(k.rect(x + 14, y + 16, 40, 6, rx=3, fill=th["accent"]))
    out.append(k.rect(x + 14, y + 28, 62, 4, rx=2, fill=th["text"]))
    out.append(k.rect(x + 14, y + 36, 46, 4, rx=2, fill=th["textMuted"]))
    for i, c in enumerate([th["success"], th["warning"], th["error"], th["info"]]):
        out.append(k.circle(x + 18 + i * 12, y + 48, 3.5, fill=c))
    if selected:
        out.append(k.circle(x + w - 14, y + 14, 8, fill=T("accent")))
        out.append(check_path(x + w - 22, y + 6, 16, T("onAccent")))
    out.append(k.text(x + 1, y + h + 18, name, 12, "bold" if selected else "normal", T("text")))
    return "".join(out)


def accent_tile(x, y, w, name, color, selected, h=64):
    """Named accent sample (AP-9 to AP-12): colour strip, name, ring when selected."""
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill=T("surfaceVariant"),
                  stroke=T("accent") if selected else T("border"), sw=2 if selected else 1)]
    out.append(k.rect(x + 8, y + 8, w - 16, 28, rx=7, fill=color, stroke=T("border"), sw=1))
    if selected:
        ink = "#000000" if k.contrast("#000000", color) >= k.contrast("#FFFFFF", color) else "#FFFFFF"
        out.append(check_path(x + w / 2 - 8, y + 14, 16, ink))
    out.append(k.text(x + 10, y + h - 10, name, 13, "bold" if selected else "normal", T("text")))
    return "".join(out)


def live_preview(x, y, w, h, radius, font, pad):
    """Live preview card: the chosen radius, font size and density applied to a sample."""
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=radius, fill=T("bg"), stroke=T("border"))]
    cx, cy, cw, ch = x + 12, y + 12, w - 24, h - 24
    out.append(k.rect(cx + 0.5, cy + 0.5, cw - 1, ch - 1, rx=radius, fill=T("surface"), stroke=T("border")))
    tx = cx + pad
    out.append(k.text(tx, cy + pad + font, "Exemplo de cartão", font + 2, "bold", T("text")))
    out.append(k.text(tx, cy + pad + font + font * 1.6, "Texto de apoio no tamanho escolhido.",
                      font, "normal", T("textMuted")))
    bh = 30
    by = cy + ch - pad - bh
    bwid = 100
    out.append(k.rect(tx, by, bwid, bh, rx=radius, fill=T("accent")))
    out.append(k.text(tx + bwid / 2, by + 20, "Salvar", 13, "bold", T("onAccent"), anchor="middle"))
    out.append(k.rect(tx + bwid + 10 + 0.5, by + 0.5, bwid - 1, bh - 1, rx=radius, fill=T("surfaceVariant"),
                      stroke=T("outline"), so=0.6))
    out.append(k.text(tx + bwid + 10 + bwid / 2, by + 20, "Cancelar", 13, "normal", T("text"), anchor="middle"))
    return "".join(out)


def slider_row(x, y, w, label_s, value, value_text, left=None, right=None, track_only=False):
    """Label 13 above a slider (kit slider), value at the right end of the label line."""
    out = [label(x, y, label_s), k.text(x + w, y, value_text, 13, "bold", T("text"), anchor="end")]
    out.append(k.slider(x, y + 8, w, value, left=left, right=right))
    return "".join(out)


def toggle(x, y, label_s, on=True, disabled=False):
    svg = k.toggle(x, y, label_s, on=on)
    return dis(svg) if disabled else svg


def segmented(x, y, items, active):
    return k.segmented(x, y, items, active)


def seg_w(items):
    return k.segmented_w(items)


def select_box(x, y, w, value, disabled=False, h=40):
    svg = k.select(x, y, w, value, h=h)
    return dis(svg) if disabled else svg


def tooltip_pill(x, y, s):
    return k.tooltip(x, y, s)


# ---------------------------------------------------------------- dialogs and overlays


def scrim(op=0.6):
    return k.scrim(op=op)


def dialog_frame(x, y, w, h, title):
    return (k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=14, fill=T("surface"), stroke=T("border"))
            + k.text(x + 24, y + 40, title, 18, "bold", T("text")))


def field_box(x, y, w, value, placeholder=False, focus=False, h=40):
    return k.input_box(x, y, w, h, value, placeholder=placeholder, focus=focus)


def search_field(x, y, w, value, focus=True, h=44):
    """Search input with magnifier glass, placeholder style when value is a hint."""
    cx, cy = x + 22, y + h / 2
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill=T("surfaceVariant"),
                  stroke=T("accent") if focus else T("border"), sw=2 if focus else 1)]
    out.append(k.circle(cx - 1, cy - 1, 5.5, stroke=T("textMuted"), sw=1.6))
    out.append(k.line(cx + 3.5, cy + 3.5, cx + 8, cy + 8, stroke=T("textMuted"), sw=1.6))
    out.append(k.text(x + 44, cy + 5, value, 15, "normal", T("text")))
    return "".join(out)


def kbd(x, y, s):
    return k.kbd(x, y, s)


def kbd_w(s):
    return k.kbd_w(s)


# ---------------------------------------------------------------- output


def write(name, body_svg, render=True):
    """Write docs/ui-mockups-v3/<name>.svg and render <name>.png (1380 x 904)."""
    os.makedirs(OUT_DIR, exist_ok=True)
    svg_path = os.path.join(OUT_DIR, name + ".svg")
    png_path = os.path.join(OUT_DIR, name + ".png")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(k.canvas(body_svg))
    print("wrote", svg_path)
    if render:
        subprocess.run([PY, "-I", "-B", RENDER, svg_path, png_path, str(W), str(H)], check=True)
    return png_path
