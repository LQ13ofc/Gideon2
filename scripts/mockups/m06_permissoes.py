#!/usr/bin/env python3
"""Mockup 06: 'Permissões' page -> docs/ui-mockups/06-permissoes.svg and
06b-permissoes-vazia.svg (1380x904 each).

Render: target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/06-permissoes.svg
Layout per docs/UI_DESIGN.md (Permissões): summary 'N aprovadas · M pendentes' as coloured chips,
one table-like card (capacidade, declarada por, estado com badge, ação), long text in 'Como funciona'.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT_DIR = os.path.join(k.ROOT, "docs", "ui-mockups")
OUT = os.path.join(OUT_DIR, "06-permissoes.svg")
OUT_EMPTY = os.path.join(OUT_DIR, "06b-permissoes-vazia.svg")

ROWS = [
    ("Rede para LLM", "llm_engine", "Aprovada", "ok", "Detalhes"),
    ("Armazenar configurações", "llm_engine", "Aprovada", "ok", "Detalhes"),
    ("Capturar tela", "screen_observe", "Pendente", "warn", "Revisar"),
    ("Controlar entrada", "computer_control", "Pendente", "warn", "Revisar"),
    ("Microfone avançado", "mic_advanced", "Revogada", "err", "Detalhes"),
]

# Column x offsets inside the card (relative to card left edge).
COL_NAME, COL_BY, COL_STATE = 20, 340, 600
ACTION_W = 112
ROW_H = 60
HEAD_H = 28


def pill(x, y, count, word, tone):
    """Summary chip: coloured count (bold) + word in body colour. Returns (svg, width). 30 px tall."""
    c = k.TONES[tone]
    cw = k.text_w(count, 14, "bold")
    gap = k.text_w(" ", 14)  # leading spaces are collapsed in SVG, so offset the word instead
    ww = k.text_w(word, 14)
    w = 14 + cw + gap + ww + 14
    svg = (k.rect(x + 0.5, y + 0.5, w - 1, 29, rx=14.5, fill=c, fo=0.14, stroke=c, so=0.5)
           + k.text(x + 14, y + 20, count, 14, "bold", c)
           + k.text(x + 14 + cw + gap, y + 20, word, 14, "normal", k.TEXT_BODY))
    return svg, w


def summary_strip(x, y, w, items):
    """Container strip holding the summary chips. 56 px tall."""
    out = [k.rect(x + 0.5, y + 0.5, w - 1, 55, rx=14, fill=k.INPUT_BG, stroke=k.CARD_BORDER)]
    cx = x + 20
    for count, word, tone in items:
        svg, pw = pill(cx, y + 13, count, word, tone)
        out.append(svg)
        cx += pw + 12
    return "".join(out)


def action_button(rel_x, label, primary):
    """Row action (fixed width so the column lines up). Returns callable for k.row."""
    def draw(ax, cy):
        return k.button(ax, cy - 20, ACTION_W, label, primary=primary)
    return draw


def table(x, y, w, rows):
    """Table-like card body: header labels, divider, rows. Returns (svg, bottom_y)."""
    by = k.card_body_top(y)
    out = [k.text(x + COL_NAME, by + 12, "Capacidade", 12, "normal", k.TEXT_LABEL),
           k.text(x + COL_BY, by + 12, "Declarada por", 12, "normal", k.TEXT_LABEL),
           k.text(x + COL_STATE, by + 12, "Estado", 12, "normal", k.TEXT_LABEL),
           k.text(x + w - 20 - ACTION_W, by + 12, "Ação", 12, "normal", k.TEXT_LABEL),
           k.line(x + 1, by + 24, x + w - 1, by + 24, stroke=k.DIVIDER)]
    ry = by + HEAD_H
    for i, (name, owner, state, tone, action) in enumerate(rows):
        cols = [
            (COL_NAME, {"s": name, "size": 15, "weight": "bold", "fill": k.TEXT_STRONG}),
            (COL_BY, {"s": owner, "size": 13, "weight": "normal", "fill": k.TEXT_BODY}),
            (COL_STATE, (lambda st, tn: lambda ax, cy: k.badge(ax, cy - 11, st, tn))(state, tone)),
            (w - 20 - ACTION_W, action_button(0, action, primary=(action == "Revisar"))),
        ]
        out.append(k.row(x, ry, w, cols, h=ROW_H, divider=i < len(rows) - 1))
        ry += ROW_H
    return "".join(out), ry


def page_main():
    x, w = k.content_box()
    parts = [
        k.sidebar(active="Permissões"),
        k.header("Permissões", "Cada capacidade precisa de autorização.", state="Em espera", tone="ok"),
    ]
    parts.append(summary_strip(x, k.CONTENT_TOP, w, [
        ("2", "aprovadas", "ok"),
        ("2", "pendentes", "warn"),
        ("1", "revogada", "err"),
    ]))

    y = k.CONTENT_TOP + 56 + k.CARD_GAP
    body_h = HEAD_H + ROW_H * len(ROWS)
    card_h = k.CARD_BODY_TOP + body_h + 12
    parts.append(k.card(x, y, w, card_h, "Capacidades"))
    svg, _ = table(x, y, w, ROWS)
    parts.append(svg)

    y_col = y + card_h + k.CARD_GAP
    parts.append(k.collapsible(x, y_col, w, "Como funciona",
                               "Como capacidades são declaradas, aprovadas e revogadas"))
    parts.append(k.text(x, 858, "Ajuda: plugins aprovados rodam em sandbox sem rede.", 12, "normal", k.MUTED))
    return k.canvas("".join(parts))


def page_empty():
    x, w = k.content_box()
    parts = [
        k.sidebar(active="Permissões"),
        k.header("Permissões", "Cada capacidade precisa de autorização.", state="Em espera", tone="ok"),
    ]
    parts.append(summary_strip(x, k.CONTENT_TOP, w, [
        ("3", "aprovadas", "ok"),
        ("0", "pendentes", "muted"),
        ("1", "revogada", "err"),
    ]))

    y = k.CONTENT_TOP + 56 + k.CARD_GAP
    card_h = 300
    parts.append(k.card(x, y, w, card_h, "Pendentes"))
    parts.append(k.empty_state(x + 20, k.card_body_top(y), w - 40, card_h - k.CARD_BODY_TOP - 20,
                               "shield", "Nenhuma permissão pendente",
                               action="Abrir Gideon Hub", primary=True))

    y_col = y + card_h + k.CARD_GAP
    parts.append(k.collapsible(x, y_col, w, "Como funciona",
                               "Como capacidades são declaradas, aprovadas e revogadas"))
    parts.append(k.text(x, 858, "Ajuda: plugins aprovados rodam em sandbox sem rede.", 12, "normal", k.MUTED))
    return k.canvas("".join(parts))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for path, svg in ((OUT, page_main()), (OUT_EMPTY, page_empty())):
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
