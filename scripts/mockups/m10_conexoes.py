#!/usr/bin/env python3
"""Mockup 10 'Conexões' (docs/UI_DESIGN.md, página 10), composed with scripts/mockup_kit.py.

Writes docs/ui-mockups/10-conexoes.svg. Render:
  target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/10-conexoes.svg
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT = os.path.join(k.ROOT, "docs", "ui-mockups", "10-conexoes.svg")
X, W = k.content_box()  # 256, 1100
GAP = k.CARD_GAP


def right_badges(right, y, items):
    """Badges laid out from the right edge, left to right in the given order."""
    total = sum(k.badge_w(t) for t, _ in items) + 8 * (len(items) - 1)
    x = right - total
    out = []
    for t, tone in items:
        out.append(k.badge(x, y, t, tone))
        x += k.badge_w(t) + 8
    return "".join(out)


def right_buttons(right, y, items, h=40):
    """Buttons laid out from the right edge. items: [(text, primary)] in left-to-right order."""
    widths = [k.button_w(t, p) for t, p in items]
    x = right - sum(widths) - 10 * (len(items) - 1)
    out = []
    for (t, p), bw in zip(items, widths):
        out.append(k.button(x, y, bw, t, primary=p, h=h))
        x += bw + 10
    return "".join(out)


def account_card(x, y, w, h, title, badges, body=None, chips=(), buttons=(), field=None):
    """Account card: title, status badges row, one body line, scope chips, actions bottom-right."""
    out = [k.card(x, y, w, h, title)]
    bx = x + 20
    for t, tone in badges:
        out.append(k.badge(bx, y + 52, t, tone))
        bx += k.badge_w(t) + 10
    if body:
        out.append(k.text(x + 20, y + 98, body, 14, "normal", k.TEXT_BODY))
    if field:
        out.append(k.field(x + 20, y + 84, w - 40, *field))
    cx = x + 20
    for c in chips:
        out.append(k.chip(cx, y + 112, c))
        cx += k.chip_w(c) + 8
    if buttons:
        out.append(right_buttons(x + w - 20, y + 158, buttons))
    return "".join(out)


def build():
    parts = [k.sidebar(active="Conexões"),
             k.header("Conexões", "Contas de serviços; você concede cada escopo.", "Em espera", tone="ok")]

    # Resumo: uma linha com badges.
    parts.append(k.card(X, 96, W, 44))
    parts.append(k.text(X + 20, 96 + 28, "4 contas · 1 conectada", 15, "bold", k.TEXT_STRONG))
    parts.append(right_badges(X + W - 20, 107, [("1 conectada", "ok"), ("2 com ação pendente", "warn")]))

    # Grade de contas: 2 colunas, 2 linhas.
    cw = (W - GAP) // 2  # 542
    ch = 212
    x1, x2 = X, X + cw + GAP
    y1, y2 = 156, 156 + ch + GAP

    parts.append(account_card(
        x1, y1, cw, ch, "GitHub",
        badges=[("Conectado", "ok"), ("SERVIDOR FALSO — sem credenciais reais", "warn")],
        body="Conta: demo-user · account_ref gh-demo-01",
        chips=["repo:read", "issues:write"],
        buttons=[("Atualizar", False), ("Desconectar", False)],
    ))
    parts.append(account_card(
        x2, y1, cw, ch, "Google",
        badges=[("Reautenticação necessária", "warn")],
        body="Conta: agenda-demo · token expirado em 19/10",
        chips=["calendar:read"],
        buttons=[("Desconectar", False), ("Reautenticar", True)],
    ))
    parts.append(account_card(
        x1, y2, cw, ch, "Home Assistant",
        badges=[("Aguardando token", "info")],
        field=("Token de acesso de longa duração", "Cole o token; ele não é exibido depois de salvo", True),
        buttons=[("Cancelar", False), ("Salvar token", True)],
    ))
    parts.append(account_card(
        x2, y2, cw, ch, "MCP",
        badges=[("Desconectado", "muted")],
        body="Servidor MCP local · transporte stdio · 0 ferramentas carregadas",
        buttons=[("Conectar", True)],
    ))

    # Nova conta e Como funciona: recolhidos, lado a lado.
    cy = y2 + ch + GAP
    parts.append(k.collapsible(X, cy, cw, "Nova conta",
                               "Adicionar uma conta de serviço com escopos mínimos"))
    parts.append(k.collapsible(X + cw + GAP, cy, cw, "Como funciona",
                               "Você concede cada escopo; escrita e ações públicas pedem aprovação"))

    # Rotas: cartão próprio.
    ry = cy + k.COLLAPSIBLE_H + GAP
    rh = 180
    parts.append(k.card(X, ry, W, rh, "Rotas"))
    parts.append(k.toggle(X + W - 300, ry + 56, "Permitir fallback visual", on=False))

    row1 = ry + 52
    parts.append(k.text(X + 20, row1 + 16, "Criar issue", 15, "bold", k.TEXT_STRONG))
    bx = X + 170
    parts.append(k.badge(bx, row1, "Escolhida: API GitHub", "ok"))
    cx = bx + k.badge_w("Escolhida: API GitHub") + 10
    parts.append(k.path(f"M{cx} {row1 + 11} l4 4 l8 -8", stroke=k.OK, sw=2))

    row2 = ry + 84
    parts.append(k.badge(bx, row2, "Descartada: MCP", "muted"))
    parts.append(k.text(bx + k.badge_w("Descartada: MCP") + 12, row2 + 15,
                        "sem conta conectada", 14, "normal", k.TEXT_BODY))

    row3 = ry + 116
    parts.append(k.badge(bx, row3, "Descartada: navegador visual", "muted"))
    parts.append(k.text(bx + k.badge_w("Descartada: navegador visual") + 12, row3 + 15,
                        "fallback visual desligado", 14, "normal", k.TEXT_BODY))

    parts.append(k.text(X + 20, ry + 162,
                        "Fallback visual desligado: se a API falhar, o Gideon não usa a tela para concluir.",
                        13, "normal", k.WARN))

    return k.canvas("".join(parts))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(build())
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
