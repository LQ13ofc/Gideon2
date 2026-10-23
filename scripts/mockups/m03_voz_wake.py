#!/usr/bin/env python3
"""Mockup 03: Voz e Wake per docs/UI_DESIGN.md. Writes docs/ui-mockups/03-voz-e-wake.svg.

Render: target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/03-voz-e-wake.svg
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT = os.path.join(k.ROOT, "docs", "ui-mockups", "03-voz-e-wake.svg")


def summary_strip(x, y, w):
    """One-line summary: active phrase + qualification badge, then state word with dot."""
    h = 56
    cy = y + h / 2
    out = [k.card(x, y, w, h)]
    lx = x + 20
    out.append(k.text(lx, cy + 5, "Frase ativa", 13, "normal", k.TEXT_LABEL))
    nx = lx + k.text_w("Frase ativa", 13) + 14
    out.append(k.text(nx, cy + 6, "Hey Gideon", 16, "bold", k.TEXT_STRONG))
    bx = nx + k.text_w("Hey Gideon", 16, "bold") + 14
    out.append(k.badge(bx, cy - 11, "em desenvolvimento", "warn"))

    sx = x + w / 2 + 40
    out.append(k.rect(x + w / 2 - 20, y + 16, 1, h - 32, fill=k.DIVIDER))
    out.append(k.text(sx, cy + 5, "Estado", 13, "normal", k.TEXT_LABEL))
    out.append(k.circle(sx + k.text_w("Estado", 13) + 22, cy, 4, fill=k.OK))
    out.append(k.text(sx + k.text_w("Estado", 13) + 36, cy + 5, "Em espera", 14, "bold", k.TEXT))
    return "".join(out), h


def option_card(x, y, w, h, title, badge_text, badge_tone, note, selected):
    """Selectable wake-phrase card: radio + title + qualification badge + one line."""
    out = []
    if selected:
        out.append(k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=12, fill=k.ACCENT, fo=0.14, stroke=k.ACCENT, sw=1.5))
    else:
        out.append(k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=12, fill=k.INPUT_BG, stroke=k.CARD_BORDER))
    rcx, rcy = x + 26, y + 30
    out.append(k.circle(rcx, rcy, 8, fill="none", stroke=k.ACCENT if selected else k.ICON_IDLE, sw=1.5))
    if selected:
        out.append(k.circle(rcx, rcy, 4, fill=k.ACCENT))
    tx = x + 50
    out.append(k.text(tx, y + 36, title, 17, "bold", k.TEXT_STRONG))
    bx = tx + k.text_w(title, 17, "bold") + 12
    out.append(k.badge(bx, y + 16, badge_text, badge_tone))
    if selected:
        out.append(k.text(x + w - 16, y + 36, "Selecionada", 12, "bold", k.ACCENT, anchor="end"))
    out.append(k.text(tx, y + h - 22, note, 14, "normal", k.TEXT_BODY))
    return "".join(out)


def wake_card(x, y, w):
    """'Frase de despertar': two selectable options side by side."""
    h = 164
    by = k.card_body_top(y)
    out = [k.card(x, y, w, h, "Frase de despertar")]
    inner = w - 40
    ow = (inner - 16) / 2
    oh = 92
    out.append(option_card(x + 20, by, ow, oh, "Hey Gideon", "em desenvolvimento", "warn",
                           "Frase padrão do pacote. Validação física ainda pendente.", True))
    out.append(option_card(x + 20 + ow + 16, by, ow, oh, "Okay Gideon", "requer prova de conceito", "warn",
                           "Pode disparar em conversa comum. Exige prova de conceito.", False))
    return "".join(out), h


def capture_card(x, y, w):
    """'Captura': four key/value rows and one honest, muted limit line."""
    rows = (("Entrada", "PCM virtual"),
            ("Pré-roll", "1 s antes da fala"),
            ("Estado", None),
            ("Sessão máx.", "30 s (30000 ms)"))
    row_h = 40
    body = k.card_body_top(y)
    h = 52 + len(rows) * row_h + 58
    out = [k.card(x, y, w, h, "Captura")]
    for i, (label, value) in enumerate(rows):
        ry = body + i * row_h
        out.append(k.text(x + 20, ry + 25, label, 14, "normal", k.TEXT_LABEL))
        if value is None:
            out.append(k.badge(x + 240, ry + 9, "Pronta", "ok"))
        else:
            out.append(k.text(x + 240, ry + 25, value, 14, "normal", k.TEXT))
        if i < len(rows) - 1:
            out.append(k.rect(x + 20, ry + row_h - 1, w - 40, 1, fill=k.DIVIDER))
    out.append(k.text(x + 20, body + len(rows) * row_h + 26,
                      "Microfone físico, AEC e redução de ruído ainda indisponíveis",
                      13, "normal", k.MUTED))
    return "".join(out), h


def build():
    x, w = k.content_box()
    parts = [k.sidebar(active="Voz e Wake"),
             k.header("Voz e Wake", "Escolha a frase que acorda o Gideon e veja como a captura funciona.",
                      state="Base local")]
    y = k.CONTENT_TOP
    strip, sh = summary_strip(x, y, w)
    parts.append(strip)
    y += sh + k.CARD_GAP

    wake, wh = wake_card(x, y, w)
    parts.append(wake)
    y += wh + k.CARD_GAP

    cap, ch = capture_card(x, y, w)
    parts.append(cap)
    y += ch + k.CARD_GAP

    parts.append(k.collapsible(x, y, w, "Como funciona",
                               "Frase de despertar, captura e limites do áudio virtual"))
    parts.append(k.text(x, 858, "Ajuda: trocar a frase exige reiniciar o Core.", 12, "normal", k.MUTED))
    return k.canvas("".join(parts))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(build())
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
