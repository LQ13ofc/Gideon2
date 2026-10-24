#!/usr/bin/env python3
"""d03: Configurações > Dispositivos, default state (docs/ui-spec/40-configuracoes.md, 7.3).

Writes docs/ui-mockups-v3/d03-dispositivos.svg and .png.  python3 -B scripts/mockups3/d03_dispositivos.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg_common as c  # noqa: E402

k = c.k


def simulated_row(x, y_base, name):
    """'Câmera: simulada' with the SINTÉTICO seal beside it."""
    out = [c.body(x, y_base, name)]
    bx = x + k.text_w(name, 14) + 12
    out.append(k.badge(bx, y_base - 15, "SINTÉTICO", "muted"))
    return "".join(out)


def build():
    parts = [c.shell(2, "Dispositivos",
                     "Entrada e saída em uso: hoje virtuais. Dispositivos físicos ainda não existem.",
                     "Entrada: PCM virtual · Saída: virtual · Câmera e tela: simuladas")]

    # Card 1: input. Spec: (140, 236, 542, 260).
    parts.append(k.card(c.LX, 236, c.HALF, 260, "Entrada (microfone)"))
    parts.append(c.body(160, 308, "Dispositivo em uso: PCM virtual"))
    parts.append(c.note_wrap(160, 336, "PCM virtual · pré-roll de 1 segundo · processamento na CPU. "
                                       "Microfone físico, cancelamento de eco e redução de ruído "
                                       "ainda indisponíveis.", 502))
    parts.append(c.label(160, 386, "Microfone físico"))
    parts.append(c.select_box(160, 394, 300, "Sem microfone físico", disabled=True))
    parts.append(c.reason(160, 456, "Indisponível: adaptador de microfone físico não implementado; "
                                    "validação humana pendente.", width=502))

    # Card 2: output. Spec: (698, 236, 542, 260).
    parts.append(k.card(c.RX, 236, c.HALF, 260, "Saída (alto-falante)"))
    parts.append(c.body(718, 308, "Dispositivo em uso: Saída virtual"))
    parts.append(c.note(718, 336, "Sem reprodução física comprovada."))
    parts.append(c.label(718, 386, "Alto-falante físico"))
    parts.append(c.select_box(718, 394, 300, "Sem alto-falante físico", disabled=True))
    parts.append(c.reason(718, 456, "Indisponível: adaptador de saída física não implementado.", width=502))

    # Card 3: camera and screen, both simulated; link to perception. Spec: (140, 516, 1100, 150).
    parts.append(k.card(c.CX, 516, c.CW, 150, "Câmera e tela"))
    parts.append(simulated_row(160, 590, "Câmera: simulada"))
    parts.append(c.reason(160, 610, "Indisponível: sem câmera real.", width=700, line_h=16))
    parts.append(simulated_row(160, 638, "Tela: simulada"))
    parts.append(c.reason(160, 658, "Indisponível: sem captura de tela real.", width=700, line_h=16))
    link_label = "Ver em Extensões › Percepção e ação"
    lw = c.bw(link_label)
    parts.append(k.button(c.CX + c.CW - 20 - lw, 596, lw, link_label, variant="secondary"))

    parts.append(c.como(682, "Entrada e saída são virtuais nesta versão. "
                             "Dispositivos físicos entram quando o adaptador for validado."))
    return "".join(parts)


def main():
    c.use_theme("gideon-escuro")
    c.write("d03-dispositivos", build())
    return 0


if __name__ == "__main__":
    sys.exit(main())
