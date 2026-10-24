#!/usr/bin/env python3
"""d06: Configurações > Geral (docs/ui-spec/40-configuracoes.md, 7.6 and 8.2).

  d06-geral.png         default state: 'Mostrar opções avançadas' OFF
  d06-geral-perigo.png  advanced ON (rollback and revision revealed), danger zone, and the
                        type-the-profile-name confirmation modal over it

Writes docs/ui-mockups-v3/*.svg and .png.  python3 -B scripts/mockups3/d06_geral.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg_common as c  # noqa: E402

k = c.k
PROFILE = "Principal"


def c1():
    """Language, login and performance. All disabled rows carry their reason."""
    out = [k.card(c.LX, 236, c.HALF, 330, "Idioma e inicialização")]
    out.append(c.body(160, 298, "Idioma da interface: Português (fixo)"))
    out.append(c.label(160, 326, "Outros idiomas"))
    out.append(c.select_box(160, 334, 300, "Português", disabled=True, h=36))
    out.append(c.reason(160, 392, "Indisponível: só o português existe na interface. Reconhecimento e voz "
                                  "usam inglês, fixo no pacote.", width=502))
    out.append(c.toggle(160, 430, "Iniciar no login", on=False, disabled=True))
    out.append(c.reason(160, 486, "Indisponível: inicialização automática no login não existe neste pacote.",
                        width=502))
    out.append(c.body(160, 520, "Desempenho"))
    out.append(c.reason(160, 538, "Indisponível: não há controle de desempenho; o processamento usa CPU fixa.",
                        width=502))
    return "".join(out)


def c2(advanced):
    out = [k.card(c.RX, 236, c.HALF, 330, "Opções avançadas")]
    out.append(c.toggle(718, 292, "Mostrar opções avançadas", on=advanced))
    out.append(c.note_wrap(718, 362, "Mostra ajustes técnicos em todas as sub-abas de Configurações. "
                                     "Não altera nenhum valor, só a visualização.", 502))
    out.append(c.note(718, 412, "Opções avançadas: " + ("ligadas" if advanced else "desligadas")))
    out.append(c.note(718, 432, "Padrão: desligado. A escolha fica salva pelo Core."))
    return "".join(out)


def summary_text(advanced):
    return ("Idioma: português · Opções avançadas: " + ("ligadas" if advanced else "desligadas")
            + " · Configuração: pronta")


def build_default():
    parts = [c.shell(5, "Geral",
                     "Idioma, inicialização, opções avançadas e restauração da configuração.",
                     summary_text(False))]
    parts.append(c1())
    parts.append(c2(False))

    # Restore. Spec: (140, 582, 1100, 210). Advanced items hidden.
    parts.append(k.card(c.CX, 582, c.CW, 210, "Restaurar padrões"))
    parts.append(k.wrap_px(160, 644, "Volta prazo da sessão, resposta por voz, indicador, volume e frase de "
                                     "despertar aos padrões. Pede confirmação. Se a frase mudar, reinicie o Core.",
                           860, 14, "normal", c.T("text"), line_h=21))
    parts.append(k.button(1040, 628, 180, "Restaurar padrões…", variant="secondary"))
    parts.append(c.note(160, 716, "Restaurar não apaga o arquivo anterior. Em modo seguro, ele é preservado "
                                  "antes da troca."))
    parts.append(c.como(808, "Em modo seguro, o arquivo inválido é preservado antes de ser substituído pelos "
                             "padrões."))
    return "".join(parts)


def build_perigo():
    parts = [c.shell(5, "Geral",
                     "Idioma, inicialização, opções avançadas e restauração da configuração.",
                     summary_text(True))]
    parts.append(c1())
    parts.append(c2(True))

    # Restore row with advanced items (left) and danger zone (right). Spec: (140, 582, 1100, 200).
    parts.append(k.card(c.CX, 582, c.CW, 200, "Restaurar e zona de perigo"))
    parts.append(k.button(160, 630, 180, "Restaurar anterior", variant="secondary"))
    parts.append(k.wrap_px(356, 648, "Desfaz a última alteração de preferências (uma etapa). Se a frase "
                                     "mudar, reinicie o Core.", 400, 12, "normal", c.T("textMuted"), line_h=16))
    parts.append(c.note(160, 718, "Revisão da configuração: 12"))

    zx, zy, zw, zh = 600, 620, 620, 150
    parts.append(k.rect(zx + 0.5, zy + 0.5, zw - 1, zh - 1, rx=10, fill=c.T("bg"), stroke=c.T("error"), so=0.7))
    parts.append(k.text(zx + 20, zy + 28, "Zona de perigo", 14, "bold", c.T("error")))
    parts.append(k.wrap_px(zx + 20, zy + 52, "Restaurar padrões volta frase, resposta por voz, indicador, "
                                             "volume e prazo aos valores do pacote. Pede o nome do perfil.",
                           zw - 40, 14, "normal", c.T("text"), line_h=20))
    parts.append(c.danger(zx + 20, zy + zh - 50, 200, "Restaurar padrões…"))
    parts.append(c.como(798, "Em modo seguro, o arquivo inválido é preservado antes de ser substituído pelos "
                             "padrões."))
    return "".join(parts)


def confirm_modal():
    """Type-the-profile-name dialog (spec 8.2, with the profile name confirmation from ux research)."""
    x, y, w, h = 390, 116, 600, 470
    out = [c.scrim(0.6), c.dialog_frame(x, y, w, h, f"Restaurar padrões do perfil {PROFILE}?")]
    out.append(k.text(x + 24, y + 66, "Estes valores voltam ao padrão do pacote. Linhas iguais ficam em cinza.",
                      14, "normal", c.T("textMuted")))
    head_y = y + 92
    out.append(k.text(x + 24, head_y, "Campo", 12, "bold", c.T("textMuted")))
    out.append(k.text(x + 300, head_y, "Atual", 12, "bold", c.T("textMuted")))
    out.append(k.text(x + 440, head_y, "Padrão", 12, "bold", c.T("textMuted")))
    out.append(k.line(x + 24, y + 102, x + w - 24, y + 102))
    rows = [
        ("Frase de despertar", "Hey Gideon", "Hey Gideon", False),
        ("Resposta por voz", "ligada", "ligada", False),
        ("Indicador visual", "ligado", "ligado", False),
        ("Volume da resposta", "80%", "100%", True),
        ("Prazo máximo da sessão", "30 s", "30 s", False),
    ]
    for i, (field, now, dflt, changed) in enumerate(rows):
        ry = y + 124 + i * 26
        col = c.T("text") if changed else c.T("textMuted")
        if changed:
            out.append(c.modified(x + 14, ry - 16, 22, "warn"))
        out.append(k.text(x + 24, ry, field, 14, "bold" if changed else "normal", col))
        out.append(k.text(x + 300, ry, now, 14, "bold" if changed else "normal", col))
        out.append(k.text(x + 440, ry, dflt, 14, "bold" if changed else "normal", col))
    out.append(k.line(x + 24, y + 260, x + w - 24, y + 260))
    out.append(k.wrap_px(x + 24, y + 284, "Se a frase de despertar mudar, reinicie o Core depois. Até "
                                          "lá, a frase atual continua ativa.",
                         w - 48, 13, "normal", c.T("warning"), line_h=18))
    out.append(k.text(x + 24, y + 326, "Digite o nome do perfil para confirmar", 13, "normal",
                      c.T("textMuted")))
    out.append(k.input_box(x + 24, y + 334, w - 48, 40, "Princ", focus=True))
    out.append(k.text(x + 24, y + 392, f"Digite {PROFILE} exatamente. O botão libera depois.",
                      12, "normal", c.T("textMuted")))
    # Buttons: Cancelar (initial focus) and the disabled danger confirm.
    by = y + h - 24 - 40
    confirm_label = "Restaurar padrões"
    cw = c.bw(confirm_label)
    out.append(c.danger(x + w - 24 - cw, by, cw, confirm_label, disabled=True))
    cancel_w = c.bw("Cancelar")
    out.append(k.button(x + w - 24 - cw - 12 - cancel_w, by, cancel_w, "Cancelar", variant="secondary",
                        state="focus"))
    return "".join(out)


def build_perigo_with_modal():
    return build_perigo() + confirm_modal()


def main():
    c.use_theme("gideon-escuro")
    c.write("d06-geral", build_default())
    c.write("d06-geral-perigo", build_perigo_with_modal())
    return 0


if __name__ == "__main__":
    sys.exit(main())
