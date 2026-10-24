#!/usr/bin/env python3
"""d01: Configurações > Voz e Wake, default state (docs/ui-spec/40-configuracoes.md, 7.1).

  target/ui-venv/bin/python -I -B scripts/mockups3/d01_voz.py   (or python3 -B)
Writes docs/ui-mockups-v3/d01-voz.svg and .png.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg_common as c  # noqa: E402

k = c.k
T = c.T


def wake_tile(x, y, w, h, name, badge_label, tone, line3, line4, selected=False, enabled=True):
    accent = c.T("accent")
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=10, fill=c.T("surface"),
                  stroke=accent if selected else c.T("border"), sw=2 if selected else 1)]
    out.append(k.text(x + 16, y + 28, name, 16, "bold", c.T("text")))
    out.append(k.badge(x + 16, y + 36, badge_label, tone))
    out.append(k.text(x + 16, y + 74, line3, 13, "normal", c.T("text")))
    out.append(c.k.wrap_px(x + 16, y + 92, line4, w - 32, 12, "normal", c.T("textMuted"), line_h=16))
    svg = "".join(out)
    return svg if enabled else c.dis(svg)


def build():
    parts = [c.shell(0, "Voz e Wake",
                     "Frase de despertar certificada, prazo da sessão e estado do wake.",
                     "Frase ativa: Hey Gideon · em desenvolvimento · Estado do wake: Em espera")]

    # Card 1: wake phrase tiles and honest text. Spec: (140, 236, 728, 320).
    y1, h1 = c.CX, 0
    parts.append(k.card(c.CX, 236, 728, 320, "Frase de despertar"))
    parts.append(c.note(160, 292, "Só frases qualificadas podem ser escolhidas. "
                        "A troca vale depois de reiniciar o Core."))
    parts.append(wake_tile(160, 306, 336, 118, "Hey Gideon", "em desenvolvimento", "info",
                           "Salva · Ativa neste processo",
                           "Qualificada em desenvolvimento; validação física pendente", selected=True))
    parts.append(wake_tile(512, 306, 336, 118, "Okay Gideon", "requer prova de conceito", "warn",
                           "Bloqueada: sem qualidade aprovada",
                           "Pode ser transcrita como 'K Gideon'.", enabled=False))
    honest = ("Comprovado: a frase 'Hey Gideon' foi reconhecida em corpus de desenvolvimento, com "
              "verificação automática. Não comprovado: uso com microfone físico, em ambientes reais e "
              "com outras vozes. Não há reconhecimento comprovado em português (pt-BR). Não é "
              "certificação acústica. 'Okay Gideon' não tem qualidade aprovada e fica bloqueada.")
    box_y = 440
    lines_h = k.wrap_px_height(honest, 664, 14, "normal", 21)
    parts.append(k.rect(160, box_y, 688, lines_h + 28, rx=10, fill=c.T("surfaceVariant"), stroke=c.T("border")))
    parts.append(k.wrap_px(176, box_y + 24, honest, 656, 14, "normal", c.T("text"), line_h=21))

    # Card 2: session and state, read only. Spec: (884, 236, 356, 320).
    parts.append(k.card(884, 236, 356, 320, "Sessão e estado"))
    parts.append(c.body(904, 300, "Prazo máximo da sessão: 30 s"))
    parts.append(c.body(904, 336, "Estado do wake: Em espera"))
    parts.append(c.body(904, 372, "Captura: Em espera"))
    parts.append(k.line(904, 392, 1220, 392))
    parts.append(c.note_wrap(904, 420, "Só leitura nesta tela. O prazo pode ser editado com "
                                       "Mostrar opções avançadas ligado.", 316))

    # Card 3: detection. Sensitivity is disabled with the reason (NT-07). Spec: (140, 572, 1100, 110).
    parts.append(k.card(c.CX, 572, c.CW, 110, "Ajustes de detecção"))
    parts.append(c.body(160, 646, "Sensibilidade"))
    parts.append(c.dis(k.slider(340, 616, 360, 0.5)))
    parts.append(c.reason(720, 636, "Indisponível: limiar de detecção fixo no pacote; "
                                    "o Core não tem ajuste de sensibilidade.", width=500))

    parts.append(c.como(698, "A frase de despertar muda só entre as opções certificadas do pacote. "
                             "Trocar exige reiniciar o Core."))
    return "".join(parts)


def main():
    c.use_theme("gideon-escuro")
    c.write("d01-voz", build())
    return 0


if __name__ == "__main__":
    sys.exit(main())
