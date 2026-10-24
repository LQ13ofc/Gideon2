#!/usr/bin/env python3
"""Conversa (spec 10, section 4): conversation with an inline tool proposal, and the empty state.

  target/ui-venv/bin/python -I -B scripts/mockups3/a02_conversa.py
Writes docs/ui-mockups-v3/a02-conversa.svg/.png and a02-conversa-vazia.svg/.png.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import assist_common as c  # noqa: E402
import mockup_kit3 as k  # noqa: E402

T = k.T
MODEL = "llama3.1:8b"
STRIP_BADGES = [("badge", f"Modelo: {MODEL}", "info"), ("badge", "Nuvem: autorizada", "ok")]
MSG_TOP, MSG_BOTTOM = 252, 772          # message area without banner (spec 10, 4.4)
ENTRY_Y = 784


def frame():
    """Cartão único (140, 236, 1100 x 644)."""
    return k.card(c.COL_X, 236, c.COL_W, 644)


def entry():
    """Entry row (spec 10, CV-09..CV-12): empty field, Enviar disabled, hint line."""
    return (k.input_box(160, ENTRY_Y, 920, 48, "Mensagem para o motor LLM", placeholder=True)
            + k.button(1092, ENTRY_Y, 128, "Enviar", variant="primary", h=48, state="disabled")
            + k.text(160, 848, "Enter envia.", 12, "normal", T["textMuted"]))


def conversation():
    """Messages with bubbles and an inline proposal (spec 10, CV-04, CV-05, CV-07)."""
    out, y = [], 268
    # Você (right side, x 720-1140, spec CV-04)
    svg, h = c.chat_bubble(720, y, 420, "Você", "Que horas são?", "user")
    out.append(svg)
    y += h + 12
    svg, h = c.chat_bubble(160, y, 620, "Gideon", "São 14h32, no horário de Brasília.", "assistant")
    out.append(svg)
    y += h + 12
    svg, h = c.chat_bubble(720, y, 420, "Você",
                           "Crie um lembrete para revisar o relatório amanhã às 9h.", "user")
    out.append(svg)
    y += h + 12
    svg, h = c.chat_bubble(160, y, 620, "Gideon",
                           "Posso criar esse lembrete. Confira a proposta abaixo antes de autorizar.", "assistant")
    out.append(svg)
    y += h + 12
    box_h = 160
    out.append(c.proposal_box(160, y, 760, box_h,
                              "Ferramenta calendario.criar_lembrete · aguardando sua decisão",
                              "gideon.calendar", "cria o lembrete 'Revisar relatório' para amanhã, 9h",
                              "baixo"))
    y += box_h
    assert y <= MSG_BOTTOM, f"messages overflow the area: bottom {y}"
    return "".join(out)


def build_conversa():
    parts = [c.shell("Conversa", "Conversa", "Converse com o motor LLM. Respostas e propostas aparecem aqui.",
                     "Aguardando aprovação", "warn"),
             c.strip("Estado da conversa: Concluída", STRIP_BADGES),
             frame(), conversation(), entry()]
    return k.canvas("".join(parts))


def build_vazia():
    """Empty state (spec 10, CV-03): dashed frame, icon, one sentence, two suggestion chips (fill, not send)."""
    x, w = 160, 1060
    h = MSG_BOTTOM - MSG_TOP
    sentence = ("Nenhuma mensagem ainda. O motor LLM é opcional: voz, wake e comandos da Base "
                "funcionam sem ele.")
    lines = k.wrap_px_lines(sentence, 620, 14)
    chips = ["Que horas são?", "Abrir o Brave"]
    chip_ws = [k.chip_w(s) for s in chips]
    block_h = 32 + 16 + len(lines) * 20 + 20 + 30
    top = MSG_TOP + (h - block_h) / 2.0
    cx = x + w / 2.0
    out = [empty_frame_svg(x, MSG_TOP, w, h)]
    out.append(k.icon("chat", cx - 16, top, 32, T["textMuted"]))
    ty = top + 32 + 16 + 14
    for i, ln in enumerate(lines):
        out.append(k.text(cx, ty + i * 20, ln, 14, "normal", T["textMuted"], anchor="middle"))
    cy = top + 32 + 16 + len(lines) * 20 + 20
    total = sum(chip_ws) + 8
    cxl = cx - total / 2.0
    for s, cw in zip(chips, chip_ws):
        out.append(k.chip(cxl, cy, s))
        cxl += cw + 8
    parts = [k.topbar("Assistente", state="Em espera", state_tone="ok"),
             k.subtabs(c.SUBS, "Conversa"),
             k.page_header("Conversa", "Converse com o motor LLM. Respostas e propostas aparecem aqui."),
             c.strip("Estado da conversa: Em espera", STRIP_BADGES),
             frame(), "".join(out), entry()]
    return k.canvas("".join(parts))


def empty_frame_svg(x, y, w, h):
    return c.empty_frame(x, y, w, h)


JOBS = [
    ("a02-conversa", build_conversa),
    ("a02-conversa-vazia", build_vazia),
]


def main():
    k.set_theme("gideon-escuro")
    for name, builder in JOBS:
        print(c.render(name, builder()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
