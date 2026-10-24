#!/usr/bin/env python3
"""Diagnostico > Motores (docs/ui-spec/50-diagnostico.md, section 6). Without LLM plugin row.

Writes docs/ui-mockups-v3/e02-motores.svg/.png (theme gideon-escuro, 1380 x 904).
  target/ui-venv/bin/python -B scripts/mockups3/e02_motores.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import diag_common as d  # noqa: E402

k = d.k
W, H = 1380, 904
THIN = " "  # thin space as milhar separator (spec R-07)


def build():
    d.set_theme()
    out = [
        d.topbar("Diagnóstico", {}, "Em espera", "muted", W),
        d.subtabs(["Estado", "Motores", "Recuperação"], "Motores", width=W),
        d.header("Motores", "Wake, transcrição e resposta em voz: o que cada motor está fazendo agora.", W),
    ]
    strip, _ = d.summary("Wake: Replay encerrado · Transcrição: Pronto · Resposta em voz: Concluído", [], W)
    out.append(strip)

    # Bloco 1 'Motores de voz' (x 140, y 236, span 12, height 250): three columns at 152 / 524 / 896.
    y = 236
    cx, cw = d.full(W, y)[0], 1100
    out.append(d.card(140, y, 1100, 250, "Motores de voz"))
    cols = [152, 524, 896]

    # Wake column
    x = cols[0]
    out.append(k.text(x, y + 66, "Wake (frase de despertar)", 17, "bold", k.T["text"]))
    out.append(d.badge_at(x, y + 97, "Replay encerrado", "muted"))
    out.append(d.tx(x, y + 126, "Frase: Hey Gideon · em desenvolvimento"))
    out.append(d.tx(x, y + 148, "Motor: detector de frase de teste"))
    out.append(d.tx(x, y + 170, "Entrada: PCM virtual"))
    out.append(d.legend(x, y + 188, "Reprodução de teste; sem microfone ao vivo."))
    out.append(k.text(x, y + 210, "Replay encerrado: o wake não está armado para ouvir.",
                      12, "normal", k.T["warning"]))

    # STT column
    x = cols[1]
    out.append(k.text(x, y + 66, "Transcrição (STT)", 17, "bold", k.T["text"]))
    out.append(d.badge_at(x, y + 97, "Pronto", "ok"))
    out.append(d.tx(x, y + 126, "Motor: moonshine · idioma inglês"))
    out.append(d.legend(x, y + 148, "Português não está comprovado para transcrição."))

    # TTS column
    x = cols[2]
    out.append(k.text(x, y + 66, "Resposta em voz (TTS)", 17, "bold", k.T["text"]))
    out.append(d.badge_at(x, y + 97, "Concluído", "ok"))
    out.append(d.tx(x, y + 126, "Voz: Alba · Pocket TTS · inglês"))
    out.append(d.tx(x, y + 148, "Saída: virtual"))
    out.append(d.legend(x, y + 170, "Sem alto-falante físico comprovado."))

    # Bloco 2 'Pacote de voz' (x 140, y 502, span 6, height 230)
    y2 = 502
    out.append(d.card(140, y2, 542, 230, "Pacote de voz"))
    bx = 160
    out.append(d.tx(bx, y2 + 64, "Verificação: Verificado"))
    out.append(d.tx(bx, y2 + 88, "Entrada: PCM virtual"))
    out.append(d.tx(bx, y2 + 112, "Saída: virtual"))
    out.append(d.tx(bx, y2 + 136, "Qualificação: em desenvolvimento; validação física pendente"))
    out.append(d.legend(bx, y2 + 160, "Trocar a voz ou a frase exige reinício do Core."))

    # Bloco 3 'Última captura e resposta' (x 698, y 502, span 6, height 230)
    out.append(d.card(698, y2, 542, 230, "Última captura e resposta"))
    bx = 718
    out.append(d.tx(bx, y2 + 64, f"Captura: 1,8 s · 28{THIN}800 amostras"))
    out.append(d.tx(bx, y2 + 88, "Motivo: Captura concluída"))
    out.append(d.tx(bx, y2 + 112, "Resposta: 3,2 s"))

    # Como funciona (x 140, y 748, span 12, height 56)
    out.append(k.collapsible(140, 748, 1100, "Como funciona",
                             "O que cada motor está fazendo. O resumo curto fica no Assistente.", open=False))
    return k.canvas("".join(out), W, H)


def main():
    d.write_and_render("e02-motores", build(), W, H)
    return 0


if __name__ == "__main__":
    sys.exit(main())
