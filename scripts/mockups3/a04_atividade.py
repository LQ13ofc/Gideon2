#!/usr/bin/env python3
"""Atividade (spec 10, section 6): session timeline with filters and seven sample rows.

Timestamps are shown on purpose: the spec has no time on Event (AC-25, N-2). The mock shows
the target layout; the Core field is still to be added.

  target/ui-venv/bin/python -I -B scripts/mockups3/a04_atividade.py
Writes docs/ui-mockups-v3/a04-atividade.svg/.png.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import assist_common as c  # noqa: E402
import mockup_kit3 as k  # noqa: E402

T = k.T
FILTERS = ["Tudo", "Comandos", "Skills", "Agente", "Erros"]

# (time, text, badge label or None, badge tone). Newest first, no content (spec 6.9).
ROWS = [
    ("14:32:07", "Ferramenta executada", "Concluído", "ok"),
    ("14:31:52", "Ferramenta autorizada", None, None),
    ("14:31:40", "Ferramenta proposta", None, None),
    ("14:31:38", "Agente iniciado", None, None),
    ("14:26:10", "organizar-fotos v1.2 · concluída · passo 4", "Concluída", "ok"),
    ("14:20:03", "Falha ao executar ferramenta", "Falhou", "err"),
    ("14:05:44", "Comando autorizado", "Concluído", "ok"),
]


def row(i, time, text_s, badge_label, badge_tone):
    y = 256 + i * 48
    x, w, h = c.IN_X, 1060, 40
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill=T["surfaceVariant"], stroke=T["border"]),
           k.text(x + 16, y + 25, time, 13, "normal", T["textMuted"]),
           k.text(x + 110, y + 25, text_s, 14, "normal", T["text"])]
    if badge_label:
        bw = k.badge_w(badge_label)
        out.append(k.badge(x + w - 16 - bw, y + 9, badge_label, badge_tone))
    return "".join(out)


def build():
    n = len(ROWS)
    out = [k.card(c.COL_X, 236, c.COL_W, 644)]
    for i, (t, s, bl, bt) in enumerate(ROWS):
        out.append(row(i, t, s, bl, bt))
    parts = [c.shell("Atividade", "Atividade", "O que aconteceu nesta sessão, sem conteúdo sensível.",
                     "Em espera", "ok"),
             c.strip(f"{n} eventos nesta sessão"),
             c.segmented5(770, 189, FILTERS, "Tudo"),
             "".join(out)]
    return k.canvas("".join(parts))


def main():
    k.set_theme("gideon-escuro")
    print(c.render("a04-atividade", build()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
