#!/usr/bin/env python3
"""d05: Configurações > Privacidade, default state (docs/ui-spec/40-configuracoes.md, 7.5).

Writes docs/ui-mockups-v3/d05-privacidade.svg and .png.  python3 -B scripts/mockups3/d05_privacidade.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg_common as c  # noqa: E402

k = c.k


def memory_row(y, tag, tone, text_s):
    """Seal + one sentence. The text wraps beside the seal."""
    bw = k.badge_w(tag)
    out = [k.badge(160, y, tag, tone)]
    out.append(k.wrap_px(160 + bw + 12, y + 15, text_s, 502 - bw - 12, 14, "normal", c.T("text"), line_h=19))
    return "".join(out)


def build():
    parts = [c.shell(4, "Privacidade",
                     "O que o Gideon guarda, onde fica e quem pode receber dados.",
                     "Áudio e legendas: só em memória · Nuvem: não concedida · Retenção: sem controle")]

    # Card 1: what is kept. Spec: (140, 236, 542, 300).
    parts.append(k.card(c.LX, 236, c.HALF, 300, "O que fica guardado"))
    parts.append(memory_row(292, "EM MEMÓRIA", "info",
                            "Áudio capturado: só em memória durante a captura. Nenhum arquivo de voz é gravado."))
    parts.append(memory_row(346, "EM MEMÓRIA", "info", "Legendas: só em memória, sem histórico."))
    parts.append(memory_row(400, "NÃO GUARDADO", "ok", "Histórico de conversas: não há histórico salvo."))
    parts.append(memory_row(454, "PRIVADO", "muted",
                            "Configurações: guardadas pelo Core em área privada. O caminho não é exibido."))

    # Card 2: cloud. Spec: (698, 236, 542, 300). Consent is read here, changed in Modelos LLM.
    parts.append(k.card(c.RX, 236, c.HALF, 300, "Envio à nuvem"))
    parts.append(c.body(718, 308, "Consentimento salvo: não concedido"))
    parts.append(k.wrap_px(718, 344, "Sem consentimento, conversas não são enviadas à nuvem. Você marca "
                                     "o consentimento no provedor do motor LLM.", 502, 14, "normal",
                           c.T("text"), line_h=20))
    link_label = "Abrir Modelos LLM › Provedor e chaves"
    parts.append(k.button(718, 400, c.bw(link_label), link_label, variant="secondary"))
    parts.append(c.note(718, 466, "Esta aba só mostra o consentimento. Ele muda em Modelos LLM."))

    # Card 3: retention and plugin data. Spec: (140, 552, 1100, 200).
    parts.append(k.card(c.CX, 552, c.CW, 200, "Retenção e dados de plugins"))
    parts.append(c.body(160, 612, "Retenção", weight="bold"))
    parts.append(c.reason(160, 632, "Indisponível: não há controle de retenção. Dados em memória deixam "
                                    "de existir quando o Core encerra.", width=1060))
    parts.append(c.note(160, 662, "Dados de plugins: configurações guardadas pelo plugin de LLM. "
                                  "O Core e as chaves não são afetados."))
    parts.append(c.danger(160, 680, 240, "Apagar dados de plugins"))
    parts.append(c.note(416, 705, "Pede confirmação. Não altera o provedor nem as chaves."))

    parts.append(c.como(768, "Nada do que você fala é guardado em disco pela interface. "
                             "A nuvem só recebe conversas com consentimento."))
    return "".join(parts)


def main():
    c.use_theme("gideon-escuro")
    c.write("d05-privacidade", build())
    return 0


if __name__ == "__main__":
    sys.exit(main())
