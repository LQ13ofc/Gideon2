#!/usr/bin/env python3
"""Diagnostico > Recuperação (docs/ui-spec/50-diagnostico.md, section 7).

State shown: configuração em modo seguro com recuperação disponível. Avançado blocks are shown
(the spec puts them behind "Mostrar opções avançadas"); the page is taller than 904 px, see report.

Writes docs/ui-mockups-v3/:
  e03-recuperacao.svg/.png
  e03-recuperacao-modo-seguro-confirmacao.svg/.png   (dialog R-D2 text from the spec)

  target/ui-venv/bin/python -B scripts/mockups3/e03_recuperacao.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import diag_common as d  # noqa: E402

k = d.k
W = 1380
BLOCK_H = 316  # blocks 1 and 2 (spec 200, content needs more; see report)

COMMANDS = [
    ("Instalar", "gideon-install --install-root <RAIZ> install <PACOTE>"),
    ("Atualizar", "gideon-install --install-root <RAIZ> update <PACOTE>"),
    ("Reverter", "gideon-install --install-root <RAIZ> rollback"),
    ("Reparar", "gideon-install --install-root <RAIZ> repair"),
    ("Criar perfil", "gideon-install --install-root <RAIZ> profile create <NOME>"),
    ("Abrir perfil", "gideon-launch --install-root <RAIZ> <PERFIL>"),
]

R_D2_BODY = ("O arquivo inválido fica guardado e as preferências voltam aos padrões. "
             "Reinicie o Core depois.")


def build_body():
    out = [
        d.topbar("Diagnóstico", {"Diagnóstico": (1, "err")}, "Em espera", "muted", W),
        d.subtabs(["Estado", "Motores", "Recuperação"], "Recuperação",
                  badges={"Recuperação": (1, "warn")}, width=W),
        d.header("Recuperação", "Reinício, restauração de configuração e comandos para o terminal.", W),
    ]
    strip, _ = d.summary("Modo seguro: recuperação disponível", [("Pendências: 1", "warn")], W)
    out.append(strip)

    (x1, y1, w1), (x2, y2, w2) = d.grid(W, 236, BLOCK_H, BLOCK_H)

    # Bloco 1 'Reiniciar e restaurar' (R04-R12)
    out.append(d.card(x1, y1, w1, BLOCK_H, "Reiniciar e restaurar"))
    bx = x1 + 20
    out.append(d.badge_at(bx, y1 + 63, "Não necessário", "muted"))
    out.append(d.wrap(bx, y1 + 86, "Reinício exigido ao trocar a frase de despertar, mudar o feedback "
                      "ou alterar plugins.", 502, 14, "normal", k.T["text"], line_h=20))
    out.append(k.button(bx, y1 + 122, k.button_w("Reiniciar Core"), "Reiniciar Core", variant="secondary"))
    out.append(d.tx(bx, y1 + 196, "Configuração", 14, "bold"))
    out.append(d.wrap(bx, y1 + 218, "Preserva o arquivo inválido e volta aos padrões. "
                      "Depois, reinicie o Core.", 502, 14, "normal", k.T["text"], line_h=20))
    bw1 = k.button_w("Restaurar anterior")
    bw2 = k.button_w("Preservar arquivo e restaurar padrões")
    out.append(k.button(bx, y1 + 256, bw1, "Restaurar anterior", variant="secondary"))
    out.append(k.button(bx + bw1 + 8, y1 + 256, bw2, "Preservar arquivo e restaurar padrões",
                        variant="secondary"))

    # Bloco 2 'Motor LLM e catálogo' (R13-R20, Avançado)
    out.append(d.card(x2, y2, w2, BLOCK_H, "Motor LLM e catálogo"))
    bx = x2 + 20
    out.append(d.tx(bx, y2 + 64, "Motor LLM", 14, "bold"))
    out.append(d.tx(bx, y2 + 88, "Há uma configuração boa salva: OpenRouter · modelo x"))
    out.append(k.button(bx, y2 + 104, k.button_w("Voltar à última configuração boa"),
                        "Voltar à última configuração boa", variant="secondary"))
    out.append(d.tx(bx, y2 + 184, "Catálogo de plugins", 14, "bold"))
    out.append(d.tx(bx, y2 + 208, "Nenhum problema de armazenamento."))
    out.append(d.legend(bx, y2 + 232, "O catálogo é verificado por SHA-256; o valor aparece em Desenvolvedor."))

    # Bloco 3 'Comandos no terminal' (R21-R32, Avançado), span 12
    y3 = d.row_bottom(236, BLOCK_H, BLOCK_H) + 16
    cx3, y3, w3 = d.full(W, y3)
    body_h = 424
    out.append(d.card(cx3, y3, w3, body_h, "Comandos no terminal"))
    out.append(d.wrap(cx3 + 20, y3 + 62,
                      "Rodam fora do aplicativo, no terminal. Troque <RAIZ> pelo caminho absoluto da "
                      "instalação; <PACOTE> pelo diretório do pacote; <NOME> pelo nome do perfil; "
                      "<PERFIL> pelo perfil criado.", w3 - 40, 14, "normal", k.T["text"], line_h=20))
    for i, (label, code) in enumerate(COMMANDS):
        top = y3 + 104 + i * 34
        out.append(k.rect(cx3 + 20, top, w3 - 40, 30, rx=8, fill=k.T["surfaceVariant"], stroke=k.T["border"]))
        out.append(k.text(cx3 + 32, top + 19, label, 12, "bold", k.T["textMuted"]))
        out.append(d.mono(cx3 + 136, top + 20, code, 13, k.T["text"]))
        out.append(k.button(cx3 + w3 - 20 - 12 - 96, top, 96, "Copiar", variant="secondary", h=30))
    out.append(d.legend(cx3 + 20, y3 + 326,
                        "Com o Core ativo, instalar, atualizar, reverter e reparar são recusados "
                        "(código de saída 3)."))
    out.append(d.legend(cx3 + 20, y3 + 346,
                        'Se o terminal mostrar "run: gideon-install --install-root <RAIZ> repair", '
                        "execute o comando de reparo."))
    out.append(d.chevron(cx3 + 30, y3 + 371, down=False))
    out.append(k.text(cx3 + 46, y3 + 376, "Códigos de saída", 14, "normal", k.T["textMuted"]))
    out.append(d.legend(cx3 + 20, y3 + 398,
                        "Reparo e atualização ficam no terminal: esta tela não executa instalador."))

    # Como funciona (R34)
    y4 = y3 + body_h + 16
    out.append(k.collapsible(cx3, y4, w3, "Como funciona",
                             "Reinícios e restaurações não apagam dados do usuário. "
                             "Instalação e pacotes só pelo terminal.", open=False))
    return "".join(out), y4 + 56 + 24


def build():
    d.set_theme()
    body, h = build_body()
    return k.canvas(body, W, h), h


def build_modal():
    d.set_theme()
    body, h = build_body()
    modal = d.centred_modal(W, h, 560, "Preservar o arquivo e restaurar os padrões?", R_D2_BODY,
                            [("Cancelar", "secondary", True), ("Restaurar padrões", "primary", False)])
    return k.canvas(body + modal, W, h), h


def main():
    svg, h = build()
    d.write_and_render("e03-recuperacao", svg, W, h)
    svg, h = build_modal()
    d.write_and_render("e03-recuperacao-modo-seguro-confirmacao", svg, W, h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
