#!/usr/bin/env python3
"""Mockup 02: Conversa per docs/UI_DESIGN.md (chat + collapsible 'Agente' panel).

Writes docs/ui-mockups/02-conversa.svg (populated) and docs/ui-mockups/02b-conversa-vazia.svg (empty state).
Render: target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/02-conversa.svg
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT_DIR = os.path.join(k.ROOT, "docs", "ui-mockups")
OUT = os.path.join(OUT_DIR, "02-conversa.svg")
OUT_EMPTY = os.path.join(OUT_DIR, "02b-conversa-vazia.svg")

PANEL_Y = k.CONTENT_TOP
PANEL_H = 772                      # 96 .. 868, same height for chat and agent panels
CHAT_W = 764                       # 256 .. 1020
AGENT_X, AGENT_W = 1036, 320       # 1036 .. 1356
INPUT_H = 52
PAD = 20


def chevron_up(cx, cy, color):
    return k.path(f"M{cx - 5:.1f} {cy + 3:.1f} L{cx:.1f} {cy - 3:.1f} L{cx + 5:.1f} {cy + 3:.1f}", stroke=color)


def bubble(x, y, w, h, s, who):
    """Chat bubble, one line, text centred vertically. who: user (accent tint) or gideon (card tint)."""
    if who == "user":
        fill, fo, edge, eo, col = k.ACCENT, 0.24, k.ACCENT, 0.55, k.TEXT_STRONG
    else:
        fill, fo, edge, eo, col = "#1a2c57", None, k.CARD_BORDER, None, k.TEXT
    return (k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=12, fill=fill, fo=fo, stroke=edge, so=eo)
            + k.text(x + 16, y + h / 2 + 5, s, 14, "normal", col))


def message(cy, x_side, who, s, cx, cw):
    """Label + bubble; returns (svg, next_cursor_y). x_side: left edge (gideon) or right edge (user)."""
    bw = k.text_w(s, 14) + 32
    bh = 40
    if who == "user":
        bx = x_side - bw
        label_anchor = "end"
        label_x = x_side
        name = "Você"
    else:
        bx = x_side
        label_anchor = "start"
        label_x = x_side
        name = "Gideon"
    svg = (k.text(label_x, cy, name, 12, "bold", k.TEXT_LABEL, anchor=label_anchor)
           + bubble(bx, cy + 6, bw, bh, s, who))
    return svg, cy + 6 + bh + 18


def proposal(x, y, w):
    """Tool-call proposal: warn edge, risk badge, the exact action, Autorizar / Negar."""
    h = 152
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=14, fill=k.INPUT_BG, stroke=k.WARN, so=0.6)]
    out.append(k.text(x + 16, y + 31, "Proposta de ferramenta", 12, "bold", k.TEXT_LABEL))
    risk = "Risco: médio"
    out.append(k.badge(x + w - 16 - k.badge_w(risk), y + 16, risk, "warn"))
    out.append(k.text(x + 16, y + 62, "Abrir aplicativo · com.brave.Browser.desktop", 15, "bold", k.TEXT_STRONG))
    out.append(k.text(x + 16, y + 86, "Inicia um processo no computador. Nada é enviado para fora.",
                      13, "normal", k.TEXT_BODY))
    by = y + h - 16 - 40
    aw = k.button_w("Autorizar", primary=True)
    nw = k.button_w("Negar")
    ax = x + w - 16 - aw
    out.append(k.button(ax, by, aw, "Autorizar", primary=True))
    out.append(k.button(ax - 12 - nw, by, nw, "Negar"))
    return "".join(out), h


def input_row(x, w):
    """Input anchored to the bottom of the chat card, with the one primary action."""
    iy = PANEL_Y + PANEL_H - PAD - INPUT_H
    bw = 112
    iw = w - 2 * PAD - bw - 12
    out = [k.rect(x + PAD + 0.5, iy + 0.5, iw - 1, INPUT_H - 1, rx=14, fill=k.INPUT_BG,
                  stroke=k.ACCENT, sw=1.5),
           k.text(x + PAD + 18, iy + 31, "Digite uma mensagem ou comando", 15, "normal", k.PLACEHOLDER),
           k.button(x + w - PAD - bw, iy + 6, bw, "Enviar", primary=True)]
    return "".join(out)


def chat_card(x, w, body):
    out = [k.card(x, PANEL_Y, w, PANEL_H)]
    out.append(k.rect(x + 1, PANEL_Y + PANEL_H - 88, w - 2, 1, fill=k.DIVIDER))
    out.append(body)
    out.append(input_row(x, w))
    return "".join(out)


def chat_populated(x, w):
    cx_mid = x + w / 2
    parts = [k.text(cx_mid, PANEL_Y + 40, "Sem histórico salvo. Esta conversa fica só na sessão.",
                    12, "normal", k.MUTED, anchor="middle")]
    cy = PANEL_Y + 74
    left, right = x + PAD + 4, x + w - PAD - 4
    svg, cy = message(cy, left, "gideon", "Base local pronta. Voz em espera, sem LLM.", x, w)
    parts.append(svg)
    svg, cy = message(cy, right, "user", "Abra o Brave e pesquise notícias de tecnologia.", x, w)
    parts.append(svg)
    svg, cy = message(cy, left, "gideon", "Vou abrir o Brave. Antes, preciso da sua autorização.", x, w)
    parts.append(svg)
    pw = 540
    prop, ph = proposal(left, cy + 4, pw)
    parts.append(prop)
    return "".join(parts)


def chat_empty(x, w):
    body = [k.empty_state(x + PAD, PANEL_Y + PAD, w - 2 * PAD, 470, "chat",
                          "Nenhuma conversa ainda. Digite um comando ou escolha uma sugestão.")]
    suggestions = ("Abrir o Brave", "Qual é o estado da Base?", "Ver permissões")
    widths = [k.chip_w(s) for s in suggestions]
    total = sum(widths) + 10 * (len(suggestions) - 1)
    sx = x + (w - total) / 2
    sy = PANEL_Y + 520
    body.append(k.text(x + w / 2, sy - 12, "Sugestões", 12, "bold", k.TEXT_LABEL, anchor="middle"))
    for s, cw_ in zip(suggestions, widths):
        body.append(k.chip(sx, sy, s))
        sx += cw_ + 10
    return "".join(body)


def agent_panel(x, w, empty=False):
    """Collapsible 'Agente' panel: goal, start, steps with state badges."""
    out = [k.card(x, PANEL_Y, w, PANEL_H, "Agente")]
    out.append(chevron_up(x + w - 30, PANEL_Y + 28, k.ICON_IDLE))
    by = k.card_body_top(PANEL_Y)
    aw = w - 40
    ax = x + 20
    value = "" if empty else "Pesquisar notícias de IA"
    out.append(k.field(ax, by, aw, "Objetivo", value if value else "Descreva o objetivo",
                       placeholder=empty))
    out.append(k.button(ax, by + 74, aw, "Iniciar", primary=not empty))
    div_y = by + 130
    out.append(k.rect(x + 1, div_y, w - 2, 1, fill=k.DIVIDER))
    if empty:
        out.append(k.text(ax, div_y + 26, "Passos", 12, "bold", k.TEXT_LABEL))
        out.append(k.empty_state(ax, div_y + 40, aw, 180, "sparkles",
                                 "Defina um objetivo para começar."))
    else:
        out.append(k.text(ax, div_y + 26, "Passos", 12, "bold", k.TEXT_LABEL))
        steps = (("Abrir o Brave", "Concluído", "ok"),
                 ("Localizar a barra de busca", "Em andamento", "info"),
                 ("Pesquisar notícias de IA", "Aguardando", "muted"),
                 ("Resumir os resultados", "Aguardando autorização", "warn"))
        ry = div_y + 40
        for i, (title, state, tone) in enumerate(steps):
            out.append(k.text(ax, ry + 22, title, 14, "normal", k.TEXT))
            out.append(k.badge(ax, ry + 32, state, tone))
            if i < len(steps) - 1:
                out.append(k.rect(ax, ry + 60, aw, 1, fill=k.DIVIDER))
            ry += 62
    out.append(k.text(ax, PANEL_Y + PANEL_H - 40, "Ações de risco pedem autorização.",
                      12, "normal", k.MUTED))
    return "".join(out)


def build(empty=False):
    x, w = k.content_box()
    parts = [k.sidebar(active="Conversa"),
             k.header("Conversa", "Peça ao Gideon o que precisa. Ações sensíveis pedem sua autorização.")]
    chat_w = CHAT_W
    body = chat_empty(x, chat_w) if empty else chat_populated(x, chat_w)
    parts.append(chat_card(x, chat_w, body))
    parts.append(agent_panel(AGENT_X, AGENT_W, empty=empty))
    return k.canvas("".join(parts))


def write(path, svg):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote", path)


def main():
    write(OUT, build(empty=False))
    write(OUT_EMPTY, build(empty=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
