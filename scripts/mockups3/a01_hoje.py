#!/usr/bin/env python3
"""Hoje (spec 10, section 3): idle, listening, approval, plus idle in gideon-claro and breeze-escuro.

  target/ui-venv/bin/python -I -B scripts/mockups3/a01_hoje.py
Writes docs/ui-mockups-v3/a01-hoje*.svg and .png.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import assist_common as c  # noqa: E402
import mockup_kit3 as k  # noqa: E402

T = k.T
MODEL = "llama3.1:8b"
CHIPS = [("chip", "Wake: Hey Gideon · em desenvolvimento"),
         ("chip", "Entrada: PCM virtual"),
         ("chip", f"Modo: Base + LLM ({MODEL})")]
RECENT_Q = "Você: Que horas são?"
RECENT_R = ("Concluído", "ok", "São 14h32, no horário de Brasília.")


def card_a(state):
    """Cartão A (spec 3.4): orb x160 y256 72 px, phrase x256 y262 (28 bold), subtitle, badge."""
    x, y, w, h = c.COL_X, 236, c.COL_W, 168
    cx, cy = 196, 292
    out = [k.card(x, y, w, h)]
    if state == "ouvindo":
        out.append(c.orb_listening(cx, cy, 36))
        phrase, sub = "Ouvindo…", "Fale agora. Cancelar encerra a sessão."
    elif state == "aprovacao":
        out.append(k.orb(cx, cy, 36, "idle"))
        phrase = "Aguardando sua aprovação"
        sub = "Ferramenta calendario.criar_lembrete precisa da sua decisão."
    else:
        out.append(k.orb(cx, cy, 36, "idle"))
        phrase, sub = "Pronto para ouvir", "Diga 'Hey Gideon' ou digite um comando."
    out.append(k.text(256, 286, phrase, 28, "bold", T["text"]))
    out.append(k.text(256, 314, sub, 14, "normal", T["textMuted"]))
    if state == "ouvindo":
        out.append(k.badge(256, 330, "Microfone ativo", "info"))
    return "".join(out)


def card_b_approval():
    """Cartão B (spec 3.4 and 3.5), 140/420, 1100 x 180. Layout lines from the spec table, moved
    so the card title (spec H-10) and the tool line (H-11) do not share y 436."""
    x, y, w, h = c.COL_X, 420, c.COL_W, 180
    out = [k.card(x, y, w, h)]
    out.append(k.text(160, 449, "Proposta pendente", 17, "bold", T["text"]))
    out.append(k.text(160, 470, "Ferramenta calendario.criar_lembrete · aguardando sua decisão",
                      14, "bold", T["text"]))
    out.append(k.text(160, 490, "Alvo: gideon.calendar", 14, "normal", T["text"]))
    out.append(k.text(160, 510, "Efeito: cria o lembrete 'Revisar relatório' para amanhã, 9h.", 14, "normal",
                      T["text"]))
    out.append(k.text(160, 530, "Risco:", 14, "normal", T["text"]))
    out.append(k.badge(160 + k.text_w("Risco: ", 14) + 2, 515, "baixo", "ok"))
    out.append(c.danger_outline(1000, 544, 100, "Negar"))
    out.append(k.button(1112, 544, 108, "Autorizar", variant="primary"))
    return "".join(out)


def strip_for(state):
    if state == "aprovacao":
        return c.strip("Aguardando aprovação · 1 proposta pendente", CHIPS)
    if state == "ouvindo":
        return c.strip("Ouvindo", CHIPS)
    return c.strip("Em espera", CHIPS)


def build(state="idle"):
    pill = {"idle": ("Em espera", "ok", False),
            "ouvindo": ("Ouvindo", "info", True),
            "aprovacao": ("Aguardando aprovação", "warn", False)}[state]
    parts = [c.shell("Hoje", "Hoje", "Como o Gideon está agora e um comando para ele.", pill[0], pill[1], pill[2]),
             strip_for(state), card_a(state)]
    if state == "aprovacao":
        parts.append(card_b_approval())
        cy = 616
    else:
        cy = 420
    if state == "ouvindo":
        parts.append(c.comando_block(cy, busy=True, last=RECENT_Q, receipt=RECENT_R,
                                     motive="Indisponível: uma sessão de voz está em andamento."))
    elif state == "aprovacao":
        parts.append(c.comando_block(cy, last="Você: Crie um lembrete para revisar o relatório amanhã às 9h.",
                                     receipt=("Concluído", "ok", "Proposta criada; nada foi executado ainda.")))
    else:
        parts.append(c.comando_block(cy, last=RECENT_Q, receipt=RECENT_R))
    return k.canvas("".join(parts))


JOBS = [
    ("a01-hoje", "gideon-escuro", "idle"),
    ("a01-hoje-ouvindo", "gideon-escuro", "ouvindo"),
    ("a01-hoje-aprovacao", "gideon-escuro", "aprovacao"),
    ("a01-hoje-claro", "gideon-claro", "idle"),
    ("a01-hoje-breeze", "breeze-escuro", "idle"),
]


def main():
    for name, theme, state in JOBS:
        k.set_theme(theme)
        print(c.render(name, build(state)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
