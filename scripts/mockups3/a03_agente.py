#!/usr/bin/env python3
"""Agente (spec 10, section 5): goal, budget and steps, final answer and a pending approval.

  target/ui-venv/bin/python -I -B scripts/mockups3/a03_agente.py
Writes docs/ui-mockups-v3/a03-agente.svg/.png.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import assist_common as c  # noqa: E402
import mockup_kit3 as k  # noqa: E402

T = k.T
GOAL = "Organizar as fotos da viagem em pastas por data"
STRIP_BADGES = [("badge", "1 proposta pendente", "warn")]


def card_objetivo():
    """Cartão 1 (140, 236, 1100 x 136): goal field, Iniciar disabled (run active), Abortar enabled."""
    out = [k.card(c.COL_X, 236, c.COL_W, 136)]
    out.append(k.text(c.IN_X, 265, "Objetivo", 17, "bold", T["text"]))
    out.append(c.input_disabled(160, 276, 920, 40, GOAL))
    out.append(k.button(1092, 276, 128, "Iniciar", variant="primary", h=40, state="disabled"))
    out.append(c.danger_outline(1092, 324, 128, "Abortar"))
    out.append(k.text(160, 336, "Já existe um agente em execução; aguarde ou aborte.", 12, "normal",
                      T["warning"]))
    return "".join(out)


STEP_COLS = [(16, "#"), (56, "Tipo"), (180, "Ferramenta"), (440, "Risco"), (600, "Estado"), (820, "Código")]


def step_row(n, kind, tool, risk, badge_label, badge_tone):
    return [(16, str(n)), (56, kind), (180, tool), (440, risk),
            (600, lambda ax, cy: k.badge(ax, cy - 11, badge_label, badge_tone)), (820, "—")]


def card_passos():
    """Cartão 2 (140, 388, 1100 x 280): budget line right, step table with 3 steps."""
    out = [k.card(c.COL_X, 388, c.COL_W, 280)]
    out.append(k.text(c.IN_X, 417, "Passos e orçamento", 17, "bold", T["text"]))
    out.append(k.text(1220, 418, "Tokens: 812 de 4.096 · Passos: 3 de 6 · Tempo: 01:12", 12, "normal",
                      T["textMuted"], anchor="end"))
    out.append(k.table_header(160, 428, 1060, STEP_COLS, h=28))
    rows = [
        step_row(1, "Conversa", "—", "—", "concluído", "ok"),
        step_row(2, "Ferramenta", "calendario.ler_agenda", "Leitura", "concluído", "ok"),
        step_row(3, "Ferramenta", "calendario.criar_evento", "Altera estado", "aguardando sua decisão", "info"),
    ]
    for i, cols in enumerate(rows):
        out.append(k.table_row(160, 460 + i * 40, 1060, cols, h=40))
    return "".join(out)


def card_resposta():
    """Cartão 3 (140, 684, 1100 x 196): final answer (empty) and the pending approval of step 3."""
    out = [k.card(c.COL_X, 684, c.COL_W, 196)]
    out.append(k.text(c.IN_X, 713, "Resposta final", 17, "bold", T["text"]))
    out.append(k.text(c.IN_X, 735, "A resposta aparece aqui quando o agente concluir.", 14, "normal",
                      T["textMuted"]))
    out.append(c.proposal_box(160, 752, 1060, 108,
                              "Ferramenta calendario.criar_evento · aguardando sua decisão",
                              "gideon.calendar",
                              "cria o evento 'Entrega do relatório' na sexta-feira, 10h",
                              "médio"))
    return "".join(out)


def build():
    parts = [c.shell("Agente", "Agente", "Descreva um objetivo; o Gideon propõe passos e pede sua aprovação.",
                     "Aguardando aprovação", "warn"),
             c.strip("Estado: Aguardando sua aprovação", STRIP_BADGES),
             card_objetivo(), card_passos(), card_resposta()]
    return k.canvas("".join(parts))


def main():
    k.set_theme("gideon-escuro")
    print(c.render("a03-agente", build()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
