#!/usr/bin/env python3
"""Diagnostico > Estado (docs/ui-spec/50-diagnostico.md, section 5).

Writes docs/ui-mockups-v3/ (theme gideon-escuro):
  e01-estado.svg/.png                       Core conectado, configuração pronta, modo desenvolvedor desligado
  e01-estado-offline.svg/.png               Core desconectado: pílula cinza e dica de recuperação
  e01-estado-modo-dev-confirmacao.svg/.png  modal "Ativar modo desenvolvedor?" (spec 8.4 text)
  e05-estreito.svg/.png                     shell 900 x 700, barra só com ícones, Diagnóstico > Estado

  target/ui-venv/bin/python -B scripts/mockups3/e01_estado.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import diag_common as d  # noqa: E402

k = d.k
W, H = 1380, 904
NARROW_W, NARROW_H = 900, 700
BLOCK_H = 264      # blocks 1 and 2 (spec 250; raised so the S12 / S20 rows fit, see report)
ERRORS_H = 230     # bloco 3 (spec 230)

ERRORS = [
    ("14:02:11", "Voz", "Falha na transcrição"),
    ("14:01:47", "Plugin", "Plugin encerrou com falha"),
    ("—", "Motores", "Falha na detecção da frase de despertar"),
    ("13:58:03", "Comando", "Comando não concluído: efeito não verificado"),
    ("13:47:09", "Voz", "Captura longa demais"),
]

MODAL_DEV_BODY = (
    "Este modo mostra ferramentas de teste na aba Desenvolvedor: comando de texto de teste, "
    "wake de teste, invocação de capacidades de plugin com JSON e identificadores técnicos "
    "(versões e hashes). Elas não concedem permissões nem mudam o que o Gideon pode fazer no "
    "seu computador. Use somente em desenvolvimento ou teste."
)


def block_core(x, y, w, connected, dev_on):
    """Bloco 1 'Core e configuração' (S05-S12)."""
    out = [d.card(x, y, w, BLOCK_H, "Core e configuração")]
    bx = x + 20
    if connected:
        out.append(d.dot_line(bx, y + 64, "Conectado ao Core", "ok"))
        out.append(d.tx(bx, y + 86, "Estado atual: Em espera"))
        out.append(d.tx(bx, y + 108, "Sessão de voz: nenhuma"))
        out.append(d.tx(bx, y + 130, "Configuração:"))
        out.append(d.badge_at(bx + k.text_w("Configuração: ", 14), y + 130, "Pronta", "ok"))
        out.append(d.mt(bx, y + 152, "Nenhuma ação pendente"))
    else:
        out.append(d.dot_line(bx, y + 64, "Core desconectado", "muted"))
        out.append(d.legend(bx, y + 84, "Tentando reconectar sozinho (intervalo de 0,5 a 5 s)."))
        out.append(d.tx(bx, y + 108, "Estado atual: Core desconectado"))
        out.append(d.tx(bx, y + 130, "Sessão de voz: nenhuma"))
        out.append(d.tx(bx, y + 152, "Configuração:"))
        out.append(d.badge_at(bx + k.text_w("Configuração: ", 14), y + 152, "Indisponível", "muted"))
        bw = k.button_w("Abrir Recuperação")
        out.append(k.button(bx, y + 172, bw, "Abrir Recuperação", variant="secondary", h=30))
    return "".join(out)


def block_base(x, y, w, connected, dev_on):
    """Bloco 2 'Base e privacidade' (S14-S20)."""
    out = [d.card(x, y, w, BLOCK_H, "Base e privacidade")]
    bx = x + 20
    if connected:
        out.append(d.tx(bx, y + 64, "Perfil: Desenvolvimento · áudio virtual · inglês"))
        out.append(d.tx(bx, y + 86, "Idioma da interface: português"))
        out.append(d.tx(bx, y + 108, "Idioma da voz: inglês"))
        out.append(d.legend(bx, y + 124, "Português para voz não está comprovado."))
        out.append(d.tx(bx, y + 146, "Pacote de voz: Base de voz virtual"))
        out.append(d.tx(bx, y + 168, "Versão da Base: 0.1.0"))
        out.append(d.mt(bx, y + 190, "Sem histórico de conversas. Áudio e legendas ficam só em memória."))
    else:
        out.append(d.tx(bx, y + 64, "Perfil: —"))
        out.append(d.tx(bx, y + 86, "Idioma da interface: português"))
        out.append(d.tx(bx, y + 108, "Idioma da voz: —"))
        out.append(d.tx(bx, y + 130, "Pacote de voz: —"))
        out.append(d.tx(bx, y + 152, "Versão da Base: não informada"))
        out.append(d.mt(bx, y + 174, "Sem histórico de conversas. Áudio e legendas ficam só em memória."))
    # S20 switch row: rótulo 14 bold + switch 40x24 + state word; legend 12 px under it
    label = "Modo desenvolvedor"
    lw = k.text_w(label, 14, "bold")
    top = y + (206 if connected else 188)
    base = top + 16
    out.append(k.text(bx, base, label, 14, "bold", k.T["text"] if connected else k.T["disabled"]))
    sx = bx + lw + 16
    out.append(d.switch(sx, top, on=dev_on, disabled=not connected))
    word = "Ligado" if dev_on else "Desligado"
    if not connected:
        word_col = k.T["disabled"]
    else:
        word_col = k.T["success"] if dev_on else k.T["textMuted"]
    out.append(k.text(sx + 52, base, word, 14, "normal", word_col))
    if connected:
        leg = "Mostra a aba Desenvolvedor, com ferramentas de teste. Não concede permissões."
    else:
        leg = "Indisponível: Core desconectado"
    out.append(d.legend(bx, top + 38, leg))
    return "".join(out)


def block_errors(x, y, w, connected, errors):
    """Bloco 3 'Últimos erros' (S21-S27)."""
    out = [d.card(x, y, w, ERRORS_H, "Últimos erros")]
    out.append(d.legend(x + 20, y + 56, "Erros desta sessão, mais recentes primeiro. Máximo de 5."))
    if connected:
        for i, (hora, area, frase) in enumerate(errors):
            out.append(d.tx(x + 20, y + 84 + i * 24, f"{hora} · {area} · {frase}"))
    else:
        out.append(d.mt(x + 20, y + 84, "Sem dados: o Core está desconectado."))
    return "".join(out)


def estado_body(width=W, connected=True, stacked=False, dev_on=False, rail=False, errors=ERRORS):
    n = len(errors) if connected else 0
    # Badge '•N' of the tab: N = engines failed + 1 if configuração ≠ pronta (spec 0.1).
    top_badges = {} if connected else {"Diagnóstico": (1, "err")}
    sub_badges = {} if connected else {"Recuperação": (1, "warn")}
    items = ["Estado", "Motores", "Recuperação"] + (["Desenvolvedor"] if dev_on else [])
    state = "Em espera" if connected else "Core desconectado"

    out = []
    if rail:
        out.append(d.rail_topbar("Diagnóstico", top_badges, state, "muted", width))
    else:
        out.append(d.topbar("Diagnóstico", top_badges, state, "muted", width))
    out.append(d.subtabs(items, "Estado", badges=sub_badges, width=width))
    out.append(d.header("Estado", "Core, configuração, perfil da Base e últimos erros desta sessão.", width))

    if connected:
        s_text = (f"Core conectado · configuração pronta · {n} "
                  f"{'erro recente' if n == 1 else 'erros recentes'}")
    else:
        s_text = "Core desconectado · tentando reconectar"
    strip, _ = d.summary(s_text, [(f"Erros: {n}", "err" if n else "muted")], width)
    out.append(strip)

    (x1, y1, w1), (x2, y2, w2) = d.grid(width, 236, BLOCK_H, BLOCK_H, stacked)
    out.append(block_core(x1, y1, w1, connected, dev_on))
    out.append(block_base(x2, y2, w2, connected, dev_on))

    y3 = d.row_bottom(236, BLOCK_H, BLOCK_H, stacked) + 16
    x3, y3, w3 = d.full(width, y3)
    out.append(block_errors(x3, y3, w3, connected, errors))

    y4 = y3 + ERRORS_H + 16
    out.append(k.collapsible(x3, y4, w3, "Como funciona",
                             "O que o Core informou e os erros desta sessão.", open=False))
    return "".join(out)


def build_estado(connected=True):
    return k.canvas(estado_body(connected=connected), W, H)


def build_modo_dev_modal():
    body = estado_body(connected=True)
    modal = d.centred_modal(W, H, 560, "Ativar modo desenvolvedor?", MODAL_DEV_BODY,
                            [("Cancelar", "secondary", True), ("Ativar modo desenvolvedor", "primary", False)])
    return k.canvas(body + modal, W, H)


def build_narrow():
    body = estado_body(width=NARROW_W, connected=True, stacked=True, rail=True)
    return k.canvas(body, NARROW_W, NARROW_H)


def main():
    d.set_theme()
    d.write_and_render("e01-estado", build_estado(True), W, H)
    d.write_and_render("e01-estado-offline", build_estado(False), W, H)
    d.write_and_render("e01-estado-modo-dev-confirmacao", build_modo_dev_modal(), W, H)
    d.write_and_render("e05-estreito", build_narrow(), NARROW_W, NARROW_H)
    return 0


if __name__ == "__main__":
    sys.exit(main())
