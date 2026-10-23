#!/usr/bin/env python3
"""Mockup 01: Início (home) per docs/UI_DESIGN.md. Writes docs/ui-mockups/01-inicio.svg.

Render: target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/01-inicio.svg
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT = os.path.join(k.ROOT, "docs", "ui-mockups", "01-inicio.svg")


def chevron_right(cx, cy, color):
    return k.path(f"M{cx - 3:.1f} {cy - 5:.1f} L{cx + 3:.1f} {cy:.1f} L{cx - 3:.1f} {cy + 5:.1f}", stroke=color)


def plain_header(title, subtitle):
    """Header without state pill: the status band already carries the state."""
    return (k.text(k.CONTENT_X, 50, title, 24, "bold", k.TEXT_STRONG)
            + k.text(k.CONTENT_X, 74, subtitle, 14, "normal", k.TEXT_MUTED))


def bubble(x, y, w, h, s, who):
    """Chat bubble: user = accent tint, Gideon = card tint. One line of text, centred vertically."""
    if who == "user":
        fill, fo, edge, eo, col = k.ACCENT, 0.24, k.ACCENT, 0.55, k.TEXT_STRONG
    else:
        fill, fo, edge, eo, col = "#1a2c57", None, k.CARD_BORDER, None, k.TEXT
    return (k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=12, fill=fill, fo=fo, stroke=edge, so=eo)
            + k.text(x + 16, y + h / 2 + 5, s, 14, "normal", col))


def status_band(x, y, w):
    """Compact state band: 72 px orb, state sentence, 3 clickable chips (they lead to pages)."""
    h = 112
    out = [k.card(x, y, w, h), k.orb(x + 20 + 36, y + 56, 36)]
    tx = x + 20 + 72 + 24
    out.append(k.text(tx, y + 41, "Pronto para ouvir", 24, "bold", k.TEXT_STRONG))
    cx = tx
    for label, icon in (("Wake: Hey Gideon · em desenvolvimento", "mic"),
                        ("Entrada: PCM virtual", "speaker"),
                        ("Modo: Base, sem LLM", "cpu")):
        out.append(k.chip(cx, y + 59, label, icon=icon))
        cx += k.chip_w(label, icon) + 10
    return "".join(out), h


def command_card(x, y, w):
    """Prominent command field with the one primary action and a single example hint."""
    h = 116
    ix, iy, bw = x + 20, y + 20, 112
    iw = w - 40 - bw - 12
    out = [k.card(x, y, w, h)]
    out.append(k.rect(ix + 0.5, iy + 0.5, iw - 1, 51, rx=14, fill=k.INPUT_BG, stroke=k.ACCENT, sw=1.5))
    out.append(k.icon("mic", ix + 18, iy + 15.5, 20, k.ICON_IDLE))
    out.append(k.text(ix + 50, iy + 31, "Diga ou digite um comando", 15, "normal", k.PLACEHOLDER))
    out.append(k.button(x + w - 20 - bw, iy + 6, bw, "Enviar", primary=True))
    out.append(k.text(ix, y + 94, "Ex.: abrir o Brave", 13, "normal", k.TEXT_MUTED))
    return "".join(out), h


def recent_card(x, y, w):
    """Recent exchange: user bubble right, Gideon bubble left with a success badge inside."""
    h = 226
    by = k.card_body_top(y)
    out = [k.card(x, y, w, h, "Conversa recente")]

    right = x + w - 20
    user_s = "Hey Gideon, open brave."
    uw = k.text_w(user_s, 14) + 32
    out.append(k.text(right, by + 10, "Você", 12, "bold", k.TEXT_LABEL, anchor="end"))
    out.append(bubble(right - uw, by + 16, uw, 38, user_s, "user"))

    g_s = "Processo do app verificado no sandbox: com.brave.Browser.desktop"
    gw = max(k.text_w(g_s, 14), k.badge_w("Concluído")) + 44
    gx = x + 20
    out.append(k.text(gx, by + 76, "Gideon", 12, "bold", k.TEXT_LABEL))
    out.append(k.rect(gx + 0.5, by + 82.5, gw - 1, 71, rx=12, fill="#1a2c57", stroke=k.CARD_BORDER))
    out.append(k.text(gx + 16, by + 106, g_s, 14, "normal", k.TEXT))
    out.append(k.badge(gx + 16, by + 118, "Concluído", "ok"))
    return "".join(out), h


def shortcuts(x, y, w):
    """Three shortcut tiles: icon, name, one line. Whole tile is a link."""
    out = [k.text(x, y + 14, "Atalhos", 14, "bold", k.TEXT_LABEL)]
    ty, th, gap = y + 26, 84, 16
    tw = (w - 2 * gap) / 3
    items = (("mic", "Voz e Wake", "Frase de despertar e captura de áudio"),
             ("speaker", "Áudio", "Volume e voz da resposta"),
             ("hub", "Gideon Hub", "Catálogo de plugins e extensões"))
    for i, (glyph, title, line) in enumerate(items):
        tx = x + i * (tw + gap)
        out.append(k.rect(tx + 0.5, ty + 0.5, tw - 1, th - 1, rx=14, fill="url(#cardGrad)", stroke=k.CARD_BORDER))
        out.append(k.icon(glyph, tx + 20, ty + (th - 24) / 2, 24, k.ACCENT))
        out.append(k.text(tx + 60, ty + 36, title, 15, "bold", k.TEXT_STRONG))
        out.append(k.text(tx + 60, ty + 58, line, 13, "normal", k.TEXT_MUTED))
        out.append(chevron_right(tx + tw - 26, ty + th / 2, k.ICON_IDLE))
    return "".join(out), ty + th


def privacy_note(x, y):
    return (k.icon("shield", x, y - 14, 16, k.ICON_IDLE)
            + k.text(x + 24, y, "Sem histórico de conversas. Áudio e legendas ficam só em memória.",
                     13, "normal", k.MUTED))


def build():
    x, w = k.content_box()
    parts = [k.sidebar(active="Início"),
             plain_header("Início", "Fale com o Gideon ou digite um comando.")]

    band, bh = status_band(x, k.CONTENT_TOP, w)
    parts.append(band)
    y = k.CONTENT_TOP + bh + k.CARD_GAP

    cmd, ch = command_card(x, y, w)
    parts.append(cmd)
    y += ch + k.CARD_GAP

    recent, rh = recent_card(x, y, w)
    parts.append(recent)
    y += rh + k.CARD_GAP

    short, sb = shortcuts(x, y, w)
    parts.append(short)

    parts.append(privacy_note(x, 858))
    return k.canvas("".join(parts))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(build())
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
