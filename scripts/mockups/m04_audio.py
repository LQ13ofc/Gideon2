#!/usr/bin/env python3
"""Mockup 04: 'Áudio' page -> docs/ui-mockups/04-audio.svg (1380x904).

Render: target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/04-audio.svg
Layout per docs/UI_DESIGN.md (Áudio): summary strip, 'Volume da resposta', 'Voz', limits line,
collapsed 'Como funciona'.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT = os.path.join(k.ROOT, "docs", "ui-mockups", "04-audio.svg")


def summary_strip(x, y, w, pairs):
    """Single-line summary: 'Label valor' pairs separated by thin dividers. 48 px tall."""
    out = [k.rect(x + 0.5, y + 0.5, w - 1, 47, rx=14, fill=k.INPUT_BG, stroke=k.CARD_BORDER)]
    cx = x + 20
    for i, (label, value) in enumerate(pairs):
        out.append(k.text(cx, y + 29, label, 13, "normal", k.TEXT_LABEL))
        vx = cx + k.text_w(label, 13) + 8
        out.append(k.text(vx, y + 29, value, 14, "bold", k.TEXT_STRONG))
        cx = vx + k.text_w(value, 14, "bold")
        if i < len(pairs) - 1:
            cx += 22
            out.append(k.line(cx, y + 15, cx, y + 33, stroke=k.DIVIDER))
            cx += 22
    return "".join(out)


def build():
    x, w = k.content_box()
    parts = [
        k.sidebar(active="Áudio"),
        k.header("Áudio", "Sua voz e os ajustes de áudio.", state="Em espera", tone="ok"),
    ]

    # Summary strip (current values only, all existing data).
    parts.append(summary_strip(x, k.CONTENT_TOP, w, [
        ("Saída:", "virtual"),
        ("Voz:", "padrão"),
        ("Volume:", "80%"),
    ]))

    # Card 1: volume. Large slider, big value, Aplicar bottom-right.
    y1 = k.CONTENT_TOP + 48 + k.CARD_GAP
    h1 = 268
    by1 = k.card_body_top(y1)
    parts.append(k.card(x, y1, w, h1, "Volume da resposta"))
    parts.append(k.text(x + 20, by1 + 14, "Ganho da resposta por voz", 14, "normal", k.TEXT_BODY))
    parts.append(k.text(x + w - 20, by1 + 50, "80%", 44, "bold", k.TEXT_STRONG, anchor="end"))
    parts.append(k.slider(x + 20, by1 + 22, w - 40, value=0.8, left="0%", right="100%"))

    btn_y = y1 + h1 - 20 - 40
    sec_w = k.button_w("Abrir ajustes da Base")
    pri_w = k.button_w("Aplicar", primary=True)
    parts.append(k.button(x + 20, btn_y, sec_w, "Abrir ajustes da Base"))
    parts.append(k.button(x + w - 20 - pri_w, btn_y, pri_w, "Aplicar", primary=True))

    # Card 2: voice and response state.
    y2 = y1 + h1 + k.CARD_GAP
    h2 = 188
    by2 = k.card_body_top(y2)
    parts.append(k.card(x, y2, w, h2, "Voz"))
    parts.append(k.text(x + 20, by2 + 12, "Voz atual", 12, "normal", k.TEXT_LABEL))
    parts.append(k.text(x + 20, by2 + 36, "Pocket TTS · Alba · inglês", 17, "bold", k.TEXT_STRONG))
    parts.append(k.text(x + 20, by2 + 62, "Saída virtual.", 14, "normal", k.TEXT_BODY))
    parts.append(k.text(x + 20, by2 + 92, "Estado da resposta", 12, "normal", k.TEXT_LABEL))
    parts.append(k.badge(x + 20, by2 + 102, "Resposta concluída", "ok"))

    # Muted limits line, outside the cards.
    y_lim = y2 + h2 + 24
    parts.append(k.text(x, y_lim, "Outras vozes e dispositivos físicos ainda indisponíveis.",
                        13, "normal", k.MUTED))

    # Collapsed explainer.
    y3 = y_lim + 24
    parts.append(k.collapsible(x, y3, w, "Como funciona",
                               "Saída virtual, voz da Base e limites do áudio atual"))

    parts.append(k.text(x, 858, "Ajuda: o volume só muda depois de Aplicar.", 12, "normal", k.MUTED))
    return k.canvas("".join(parts))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(build())
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
