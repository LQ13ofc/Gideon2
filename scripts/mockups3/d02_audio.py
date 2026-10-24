#!/usr/bin/env python3
"""d02: Configurações > Áudio, default state (docs/ui-spec/40-configuracoes.md, 7.2).

Writes docs/ui-mockups-v3/d02-audio.svg and .png.  python3 -B scripts/mockups3/d02_audio.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg_common as c  # noqa: E402

k = c.k


def build():
    parts = [c.shell(1, "Áudio",
                     "Volume e feedback da resposta do Gideon. Vale a partir da próxima sessão.",
                     "Saída: virtual · Voz: Alba · Volume: 80% · Resposta por voz: ligada",
                     action=c.primary_action("Aplicar", enabled=False))]

    # Card 1: volume (draft = saved, so Apply is disabled). Spec: (140, 236, 542, 250).
    parts.append(k.card(c.LX, 236, c.HALF, 250, "Volume da resposta"))
    parts.append(c.note_wrap(160, 292, "Ganho da resposta por voz na saída virtual. "
                                       "Vale a partir da próxima sessão.", 502))
    parts.append(k.slider(160, 318, 420, 0.8))
    parts.append(k.text(596, 352, "80%", 16, "bold", c.T("text")))
    parts.append(c.note(160, 386, "0% = mudo. Não altera o volume do sistema do host."))
    parts.append(c.note(160, 420, "Valor salvo no Core: 80%. Arraste para mudar; Aplicar grava."))

    # Card 2: audible response and link to the visual indicator. Spec: (698, 236, 542, 250).
    parts.append(k.card(c.RX, 236, c.HALF, 250, "Resposta"))
    parts.append(c.toggle(718, 296, "Resposta por voz (saída virtual)", on=True))
    parts.append(k.text(718, 362, "Indicador visual: ligado. Alterar em Aparência ›", 14, "normal",
                        c.T("accent")))
    parts.append(c.body(718, 444, "Resposta: Em espera"))

    # Card 3: voice. Only the pack voice exists; choice is disabled with reason. Spec: (140, 502, 1100, 150).
    parts.append(k.card(c.CX, 502, c.CW, 150, "Voz"))
    parts.append(c.body(160, 580, "Voz da Base: Pocket TTS · Alba · inglês · saída virtual"))
    parts.append(c.select_box(160, 596, 300, "Alba", disabled=True))
    parts.append(c.reason(480, 620, "Indisponível: escolha de voz não implementada; "
                                    "só a voz do pacote existe.", width=620))

    parts.append(c.como(668, "O volume é aplicado ao áudio gerado pelo Gideon antes da saída virtual. "
                             "Não muda o volume do sistema."))
    return "".join(parts)


def main():
    c.use_theme("gideon-escuro")
    c.write("d02-audio", build())
    return 0


if __name__ == "__main__":
    sys.exit(main())
