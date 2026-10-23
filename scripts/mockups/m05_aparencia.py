#!/usr/bin/env python3
"""Mockup 05: 'Aparência' page -> docs/ui-mockups/05-aparencia.svg (1380x904).

Render: target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/05-aparencia.svg
Layout per docs/UI_DESIGN.md (Aparência): 'Tema' and 'Cor de destaque' side by side,
'HUD visual' full width. Tema carries a live preview mini-window.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT = os.path.join(k.ROOT, "docs", "ui-mockups", "05-aparencia.svg")

ACCENTS = [("Azul", "#7693ff"), ("Violeta", "#b386ff"), ("Ciano", "#66dcf4"), ("Rosa", "#f28bd7")]
SELECTED = "Azul"


def check_mark(cx, cy, color="#ffffff"):
    """Check glyph drawn in place (the kit has no check icon)."""
    return k.path(f"M{k._n(cx - 7)} {k._n(cy)} L{k._n(cx - 2)} {k._n(cy + 5)} L{k._n(cx + 7)} {k._n(cy - 5)}",
                  stroke=color, sw=2.8)


def live_preview(x, y, w, h):
    """Mini window rendered with the dark tokens, showing the selected theme and accent."""
    out = [k.rect(x, y, w, h, rx=12, fill=k.BG, stroke=k.DIVIDER)]
    side_w = 128
    out.append(k.rect(x + 1, y + 1, side_w, h - 2, rx=11, fill=k.SIDEBAR_BG))
    out.append(k.rect(x + 1, y + 1, 12, h - 2, fill=k.SIDEBAR_BG))  # square off the left corners
    out.append(k.orb(x + 22, y + 24, 8))
    out.append(k.text(x + 36, y + 28, "Gideon", 13, "bold", "#f3f6ff"))
    # Active nav item in the selected accent.
    out.append(k.rect(x + 10, y + 56, side_w - 20, 26, rx=7, fill=ACCENT_HEX, fo=0.22))
    out.append(k.text(x + 22, y + 74, "Aparência", 12, "bold", k.NAV_ACTIVE_TEXT))
    out.append(k.text(x + 22, y + 104, "Conversa", 12, "normal", k.NAV_TEXT))
    out.append(k.text(x + 22, y + 128, "Áudio", 12, "normal", k.NAV_TEXT))
    # Content: title, one bubble, one primary button in the accent.
    cx = x + side_w + 20
    out.append(k.text(cx, y + 40, "Início", 16, "bold", k.TEXT_STRONG))
    out.append(k.rect(cx, y + 56, 230, 34, rx=10, fill=k.CARD_BORDER, fo=0.5))
    out.append(k.text(cx + 12, y + 78, "Pronto para ouvir.", 13, "normal", k.TEXT))
    out.append(k.rect(cx, y + h - 54, 96, 32, rx=9, fill=ACCENT_HEX))
    out.append(k.text(cx + 48, y + h - 33, "Aplicar", 13, "bold", "#ffffff", anchor="middle"))
    return "".join(out)


# The preview uses the accent that is selected in 'Cor de destaque'.
ACCENT_HEX = dict(ACCENTS)[SELECTED]


def build():
    x, w = k.content_box()
    half = (w - k.CARD_GAP) // 2  # 542
    x_right = x + half + k.CARD_GAP
    top_h = 440
    y = k.CONTENT_TOP

    parts = [
        k.sidebar(active="Aparência"),
        k.header("Aparência", "Defina o estilo visual do Gideon.", state="Em espera", tone="ok"),
    ]

    # Card 1: Tema (segmented, live preview).
    by = k.card_body_top(y)
    parts.append(k.card(x, y, half, top_h, "Tema"))
    parts.append(k.segmented(x + 20, by, ["Escuro", "Claro", "Sistema"], active=0))
    parts.append(k.text(x + 20, by + 62, "Prévia ao vivo", 12, "normal", k.TEXT_LABEL))
    parts.append(live_preview(x + 20, by + 74, half - 40, 250))
    parts.append(k.text(x + 20, y + top_h - 20, "Tema escuro com cor Azul.", 12, "normal", k.MUTED))

    # Card 2: Cor de destaque (large swatches, check ring on the selected one).
    parts.append(k.card(x_right, y, half, top_h, "Cor de destaque"))
    gap = 14
    sw_w = (half - 40 - 3 * gap) / 4
    sw_h = 190
    for i, (name, hexcol) in enumerate(ACCENTS):
        sx = x_right + 20 + i * (sw_w + gap)
        sel = name == SELECTED
        parts.append(k.rect(sx, by, sw_w, sw_h, rx=16, fill=hexcol))
        if sel:
            parts.append(k.rect(sx - 5, by - 5, sw_w + 10, sw_h + 10, rx=20, fill="none",
                                stroke=k.TEXT_STRONG, sw=3))
            parts.append(k.circle(sx + sw_w / 2, by + sw_h / 2, 18, fill=k.BG, fo=0.45))
            parts.append(check_mark(sx + sw_w / 2, by + sw_h / 2))
        parts.append(k.text(sx + sw_w / 2, by + sw_h + 36, name, 14,
                            "bold" if sel else "normal",
                            k.TEXT_STRONG if sel else k.TEXT_MUTED, anchor="middle"))
    parts.append(k.text(x_right + 20, by + sw_h + 88, f"Selecionada: {SELECTED}", 14, "bold", k.TEXT_STRONG))
    parts.append(k.text(x_right + 20, by + sw_h + 112, "Usada em botões, seleção e indicadores.",
                        13, "normal", k.TEXT_BODY))

    # Card 3: HUD visual (full width).
    y3 = y + top_h + k.CARD_GAP
    h3 = 170
    hb = k.card_body_top(y3)
    parts.append(k.card(x, y3, w, h3, "HUD visual"))
    parts.append(k.toggle(x + 20, hb, "Mostrar esfera e indicador de atividade", on=True))
    parts.append(k.text(x + 20, hb + 70, "Estado textual, legendas e cancelamento permanecem disponíveis.",
                        14, "normal", k.TEXT_BODY))
    parts.append(k.text(x + 20, hb + 96, "O indicador é salvo pelo Core.", 12, "normal", k.MUTED))

    parts.append(k.text(x, 858, "Ajuda: tema e cor se aplicam a esta janela.", 12, "normal", k.MUTED))
    return k.canvas("".join(parts))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(build())
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
