#!/usr/bin/env python3
"""Diagnostico > Desenvolvedor (docs/ui-spec/50-diagnostico.md, section 8). Dev mode ON.

Writes docs/ui-mockups-v3/e04-desenvolvedor.svg/.png (theme gideon-escuro).
The page is taller than 904 px (blocks grow to their content); see report.

  target/ui-venv/bin/python -B scripts/mockups3/e04_desenvolvedor.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import diag_common as d  # noqa: E402

k = d.k
W = 1380
BLOCK_12_H = 476   # blocks 1 and 2 (block 2 content decides)

VERSIONS = [
    "Versão da Base: 0.1.0",
    "Protocolo do Core: 1",
    "Pacote de voz: base-voz-virtual · escopo dev_virtual_en",
    "Motores: wake wake-replay · stt moonshine-en · tts pocket-tts",
    "SHA-256 do pacote de voz: 9c1e4b7a0d28f635…",
    "SHA-256 do catálogo do Hub: 5a07d2e9c41b8f3e…",
    "arquivos 0.3.1 · manifesto 77e0b4a19c2d…",
    "Revisões: preferências 3 · motor LLM 0",
    "Binário e PACKAGE.json: 2b8f0c6d4e91a7f3… · commit 6e1d4a0b",
    "SHA-256 da última captura: c4d9e0a7b21f5e86…",
]

SELOS = [
    ("SINTÉTICO", "muted", "sem hardware real: o resultado é simulado; nenhum dispositivo real foi usado."),
    ("SERVIDOR FALSO", "muted", "sem credenciais reais: a conexão usa um servidor de teste."),
    ("UNSUPPORTED", "err", "recurso não suportado neste ambiente; nada foi executado."),
    ("em desenvolvimento", "info", "qualificação de teste; validação física pendente."),
    ("requer prova de conceito", "err", "frase não qualificada; não pode ser escolhida."),
    ("não verificado", "warn", "o publisher não foi autenticado."),
    ("pendente de validação humana", "muted", "backend real ainda não validado com hardware."),
]


def build():
    d.set_theme()
    out = [
        d.topbar("Diagnóstico", {}, "Em espera", "muted", W),
        d.subtabs(["Estado", "Motores", "Recuperação", "Desenvolvedor"], "Desenvolvedor", width=W),
        d.header("Desenvolvedor", "Ferramentas de teste. Não concedem permissões; use somente em desenvolvimento.", W),
    ]
    strip, cursor = d.summary("Modo desenvolvedor ligado: ferramentas de teste. Não concedem permissões.",
                              [], W, fill=k.T["warning"])
    off_label = "Desligar modo desenvolvedor"
    bw = k.button_w(off_label)
    out.append(strip)
    out.append(k.button(cursor - bw, 189, bw, off_label, variant="secondary", h=30))

    (x1, y1, w1), (x2, y2, w2) = d.grid(W, 236, BLOCK_12_H, BLOCK_12_H)

    # Bloco 1 'Entrada de teste' (D04-D11)
    out.append(d.card(x1, y1, w1, BLOCK_12_H, "Entrada de teste"))
    bx = x1 + 20
    out.append(d.tx(bx, y1 + 64, "Comando de texto de teste", 14, "bold"))
    field_w = w1 - 40 - 96 - 8
    out.append(k.input_box(bx, y1 + 72, field_w, 40, "Comando de texto no perfil de teste", placeholder=True))
    out.append(k.button(bx + field_w + 8, y1 + 72, 96, "Enviar", variant="primary", state="disabled"))
    out.append(d.mt(bx, y1 + 136, "Nenhum comando de teste enviado."))
    out.append(k.button(bx, y1 + 160, k.button_w("Disparar wake de teste"), "Disparar wake de teste",
                        variant="secondary"))
    out.append(d.tx(bx, y1 + 230, "Replay de wake: encerrado"))
    out.append(d.legend(bx, y1 + 252, "O replay é iniciado pelo Core com --wake-replay. "
                                      "Não há microfone nesta tela."))

    # Bloco 2 'Invocar capacidade' (D12-D20)
    out.append(d.card(x2, y2, w2, BLOCK_12_H, "Invocar capacidade"))
    bx = x2 + 20
    fw = w2 - 40
    out.append(k.text(bx, y2 + 62, "Capacidade", 13, "normal", k.T["textMuted"]))
    out.append(k.select(bx, y2 + 70, fw, "screen_observe.status"))
    out.append(k.segmented(bx, y2 + 124, ["Texto", "JSON"], 1))
    out.append(k.text(bx, y2 + 186, "Entrada em JSON (objeto)", 13, "normal", k.T["textMuted"]))
    out.append(d.mono_box(bx, y2 + 196, fw, 120, placeholder="{ }"))
    inv_w = k.button_w("Invocar", primary=True)
    out.append(k.button(bx, y2 + 332, inv_w, "Invocar", variant="primary"))
    out.append(d.legend(bx + inv_w + 16, y2 + 356, "Prazo: 3 s"))
    out.append(k.text(bx, y2 + 396, "Resultado", 13, "normal", k.T["textMuted"]))
    out.append(d.mono_box(bx, y2 + 404, fw, 52, value="Sem resultado ainda."))

    # Bloco 3 'Versões, hashes e selos' (V01-V10, S01s-S08s), span 12
    y3 = d.row_bottom(236, BLOCK_12_H, BLOCK_12_H) + 16
    cx3, y3, w3 = d.full(W, y3)
    left_x = cx3 + 20
    right_x = cx3 + 580
    right_w = cx3 + w3 - 20 - right_x - 16  # keep the longest line inside the card

    right_rows = []
    cur = y3 + 92
    for name, tn, rest in SELOS:
        svg, lines = d.rich_wrap(right_x, cur, name, rest, right_w, tn, 13, 18)
        right_rows.append(svg)
        cur += lines * 18 + 12
    right_bottom = cur
    left_bottom = y3 + 64 + (len(VERSIONS) - 1) * 22 + 22
    body_h = max(right_bottom, left_bottom) - y3 + 16
    out.append(d.card(cx3, y3, w3, body_h, "Versões, hashes e selos"))
    for i, line in enumerate(VERSIONS):
        out.append(d.mono(left_x, y3 + 64 + i * 22, line, 13, k.T["text"]))
    out.append(k.text(right_x, y3 + 64, "Selos por extenso", 14, "bold", k.T["text"]))
    out.extend(right_rows)

    y4 = y3 + body_h + 24
    return k.canvas("".join(out), W, y4)


def main():
    d.set_theme()
    svg_text = build()
    # canvas height is the last attribute written by canvas(); read it back from the svg root
    import re
    h = int(re.search(r'height="(\d+)"', svg_text).group(1))
    d.write_and_render("e04-desenvolvedor", svg_text, W, h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
