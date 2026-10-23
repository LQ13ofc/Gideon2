#!/usr/bin/env python3
"""Example mockup: the 'Voz e Wake' page composed with scripts/mockup_kit.py.

Writes docs/ui-mockups/_example.svg. Render:
  target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/_example.svg
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mockup_kit as k  # noqa: E402

OUT = os.path.join(k.ROOT, "docs", "ui-mockups", "_example.svg")


def build():
    x, w = k.content_box()
    parts = [k.sidebar(active="Voz e Wake"), k.header("Voz e Wake", "Configure como o Gideon escuta e responde.")]

    # Card 1: wake phrase. Body starts at y + 52 (titled card).
    y1 = k.CONTENT_TOP
    h1 = 224
    by = k.card_body_top(y1)
    parts.append(k.card(x, y1, w, h1, "Frase de despertar"))
    parts.append(k.text(x + 20, by + 14, "Escolha uma frase qualificada do pacote. A alteração requer reinício do Core.",
                        14, "normal", k.TEXT_BODY))
    parts.append(k.text(x + 20, by + 36, "Frase ativa", 12, "normal", k.TEXT_LABEL))
    parts.append(k.text(x + 20, by + 60, "Hey Gideon", 17, "bold", k.TEXT_STRONG))
    parts.append(k.badge(x + 20 + k.text_w("Hey Gideon", 17, "bold") + 14, by + 46,
                         "Em desenvolvimento", "warn"))
    parts.append(k.text(x + 20, by + 84, "Estado do wake: Replay encerrado · validação física pendente",
                        14, "normal", k.TEXT_BODY))
    parts.append(k.text(x + 20, by + 112, "Frases disponíveis", 12, "normal", k.TEXT_LABEL))
    cx = x + 20
    for label, active in (("Hey Gideon · em desenvolvimento", True),
                          ("Okay Gideon · requer prova de conceito", False)):
        parts.append(k.chip(cx, by + 122, label, icon="mic" if active else None, active=active))
        cx += k.chip_w(label, "mic" if active else None) + 12

    # Card 2: capture. Label above value; badges carry the honest limits.
    y2 = y1 + h1 + k.CARD_GAP
    h2 = 234
    by2 = k.card_body_top(y2)
    parts.append(k.card(x, y2, w, h2, "Captura"))
    parts.append(k.text(x + 20, by2 + 12, "Entrada", 12, "normal", k.TEXT_LABEL))
    parts.append(k.text(x + 20, by2 + 34,
                        "PCM virtual · pré-roll de 1 segundo · processamento na CPU.", 14, "normal", k.TEXT))
    parts.append(k.text(x + 20, by2 + 60, "Estado", 12, "normal", k.TEXT_LABEL))
    parts.append(k.text(x + 20, by2 + 82, "Captura: Pronto · prazo da sessão: 30000 ms", 14, "normal", k.TEXT))
    bx = x + 20
    for label, tone in (("Captura pronta", "ok"),
                        ("Microfone físico indisponível", "warn"),
                        ("AEC e redução de ruído indisponíveis", "warn")):
        parts.append(k.badge(bx, by2 + 94, label, tone))
        bx += k.badge_w(label) + 10
    bw = k.button_w("Abrir ajustes da Base")
    parts.append(k.button(x + w - 20 - bw, by2 + 130, bw, "Abrir ajustes da Base"))

    # Card 3: collapsed explainer.
    y3 = y2 + h2 + k.CARD_GAP
    parts.append(k.collapsible(x, y3, w, "Como funciona",
                               "Frase de despertar, captura e limites do áudio virtual"))

    parts.append(k.text(x, 858, "Ajuda: a troca de frase só vale depois de reiniciar o Core.", 12,
                        "normal", k.MUTED))
    return k.canvas("".join(parts))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(build())
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
