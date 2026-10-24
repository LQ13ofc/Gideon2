#!/usr/bin/env python3
"""Self-test for scripts/mockup_kit3.py: two pages of the new shell, rendered in several themes.

  'Assistente > Hoje'      (docs/ui-spec/10-assistente.md, section 3) in gideon-escuro, gideon-claro, catppuccin
  'Configuracoes > Aparencia' (docs/ui-spec/40-configuracoes.md, section 7.4) in gideon-escuro

Writes docs/ui-mockups-v3/_example-*.svg and renders each to .png with scripts/render_svg.py.
  target/ui-venv/bin/python -I -B scripts/mockup_example3.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mockup_kit3 as k  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(ROOT, "docs", "ui-mockups-v3")
PY = os.path.join(ROOT, "target", "ui-venv", "bin", "python")
RENDER = os.path.join(HERE, "render_svg.py")
W, H = k.CANVAS_W, k.CANVAS_H


def build_hoje():
    x, w = k.content_box(W)
    parts = [
        k.topbar("Assistente", badges={"Permissões": 1}, state="Aguardando aprovação", state_tone="warn"),
        k.subtabs(["Hoje", "Conversa", "Agente", "Atividade"], "Hoje"),
        k.page_header("Hoje", "Como o Gideon está agora e um comando para ele."),
        k.summary_strip("Aguardando aprovação · 1 proposta pendente",
                        [("Wake: Hey Gideon · em desenvolvimento", "warn"),
                         ("Entrada: PCM virtual", "info"),
                         ("Modo: Base, sem LLM", "muted")]),
    ]

    # Card A: state (orb, phrase, subtitle). Spec: orb x 160 y 256 72x72; phrase x 256.
    ya, ha = k.CONTENT_Y, 168
    parts.append(k.card(x, ya, w, ha))
    parts.append(k.orb(x + 56, ya + 84, 36, "idle"))
    parts.append(k.text(x + 116, ya + 78, "Aguardando sua aprovação", 28, "bold", k.T["text"]))
    parts.append(k.text(x + 116, ya + 106, "Ferramenta arquivos precisa da sua decisão.", 14, "normal",
                        k.T["textMuted"]))

    # Card B: pending proposal (decision buttons, risk badge).
    yb, hb = 420, 180
    by = k.card_body_top(yb)
    parts.append(k.card(x, yb, w, hb, "Ferramenta arquivos.gravar – aguardando sua decisão"))
    parts.append(k.text(x + 20, by + 12, "Alvo: arquivos (plugin Arquivos)", 14, "normal", k.T["text"]))
    parts.append(k.text(x + 20, by + 34, "Efeito: grava 3 arquivos em Documentos/Rascunhos.", 14, "normal",
                        k.T["text"]))
    rx_ = x + 20
    parts.append(k.text(rx_, by + 56, "Risco:", 14, "normal", k.T["text"]))
    parts.append(k.badge(rx_ + k.text_w("Risco: ", 14) + 4, by + 42, "médio", "warn"))
    neg_w = k.button_w("Negar")
    aut_w = k.button_w("Autorizar", primary=True)
    ay = yb + hb - 20 - 40
    parts.append(k.button(x + w - 20 - aut_w, ay, aut_w, "Autorizar", variant="primary"))
    parts.append(k.button(x + w - 20 - aut_w - 12 - neg_w, ay, neg_w, "Negar", variant="secondary"))

    # Card C: command field, send, last interaction.
    yc, hc = 616, 264
    cby = k.card_body_top(yc)
    parts.append(k.card(x, yc, w, hc, "Comando"))
    parts.append(k.text(x + 20, cby + 8, "Texto segue o mesmo caminho da voz. 1 a 512 bytes, uma linha.", 13,
                        "normal", k.T["textMuted"]))
    send_w = k.button_w("Enviar", primary=True)
    parts.append(k.input_box(x + 20, cby + 24, w - 40 - send_w - 12, 44, "Diga ou digite um comando",
                             placeholder=True, focus=True))
    parts.append(k.button(x + w - 20 - send_w, cby + 24, send_w, "Enviar", variant="primary"))
    parts.append(k.text(x + 20, cby + 112, "Última interação", 13, "normal", k.T["textMuted"]))
    bw = 520
    msg = "Abra a pasta de rascunhos e apague os arquivos antigos."
    parts.append(k.bubble(x + w - 20 - bw, cby + 122, bw, msg, role="user"))
    bh = k.bubble_h(msg, bw)
    parts.append(k.text(x + 20, cby + 122 + bh + 24, "Gideon · Aguardando sua decisão · nada foi apagado ainda.",
                        14, "normal", k.T["textMuted"]))
    return k.canvas("".join(parts))


def build_aparencia():
    x, w = k.content_box(W)
    half = (w - 16) / 2.0
    parts = [
        k.topbar("Configurações", state="Em espera", state_tone="ok"),
        k.subtabs(["Voz e Wake", "Áudio", "Dispositivos", "Aparência", "Privacidade", "Geral"], "Aparência"),
        k.page_header("Aparência", "Tema e cor de destaque desta janela, com prévia imediata."),
        k.summary_strip("Tema: Gideon · Destaque: Azul · Esfera: ligada · Não salvo ao reabrir",
                        [("Esfera: ligada", "ok")]),
    ]

    # Card 1: theme presets (radio list) + mode segmented.
    y1, h1 = k.CONTENT_Y, 300
    by1 = k.card_body_top(y1)
    parts.append(k.card(x, y1, half, h1, "Tema"))
    names = ["Gideon escuro", "Gideon claro", "Alto contraste", "Breeze-like escuro",
             "Breeze-like claro", "Mocha-like", "Nord-like", "Daltonismo-seguro"]
    for i, nm in enumerate(names):
        col, row = i // 4, i % 4
        parts.append(k.radio(x + 20 + col * (half / 2), by1 + 4 + row * 30, nm, selected=(i == 0)))
    parts.append(k.text(x + 20, y1 + h1 - 84, "Modo", 13, "normal", k.T["textMuted"]))
    parts.append(k.segmented(x + 20, y1 + h1 - 62, ["Sistema", "Escuro", "Claro"], "Escuro"))

    # Card 2: accent swatches + hex field + ghost reset.
    x2 = x + half + 16
    parts.append(k.card(x2, y1, half, h1, "Cor de destaque"))
    accents = ["#7AA2F7", "#2F5FD0", "#3DAEE9", "#89B4FA", "#88C0D0", "#56B4E9", "#6BCB8B", "#F07178"]
    for i, c in enumerate(accents):
        parts.append(k.swatch(x2 + 20 + i * 44, by1 + 4, c, selected=(i == 0)))
    parts.append(k.field(x2 + 20, by1 + 56, 220, "Cor em hexadecimal", k.T["accent"].upper()))
    rw = k.button_w("Restaurar padrão")
    parts.append(k.button(x2 + 20 + 220 + 12, by1 + 56 + 22, rw, "Restaurar padrão", variant="ghost"))
    parts.append(k.text(x2 + 20, by1 + 150, "Tamanho da fonte", 13, "normal", k.T["textMuted"]))
    parts.append(k.slider(x2 + 20, by1 + 158, half - 40, 0.4, left="12 px", right="20 px", value_text="14 px"))

    # Card 3: activity orb toggle and orb state preview.
    y3, h3 = 552, 240
    by3 = k.card_body_top(y3)
    parts.append(k.card(x, y3, w, h3, "Indicador visual e prévia"))
    parts.append(k.toggle(x + 20, by3 + 4, "Esfera de atividade", on=True))
    parts.append(k.checkbox(x + 380, by3 + 6, "Reduzir animações", checked=False))
    parts.append(k.checkbox(x + 600, by3 + 6, "Alto contraste", checked=False))
    states = [("Parado", "idle"), ("Ouvindo", "listening"), ("Pensando", "thinking"),
              ("Falando", "speaking"), ("Erro", "error")]
    step = (w - 40) / len(states)
    for i, (label, st) in enumerate(states):
        cx = x + 20 + step * i + step / 2
        parts.append(k.orb(cx, by3 + 100, 26, st))
        parts.append(k.text(cx, by3 + 162, label, 12, "normal", k.T["textMuted"], anchor="middle"))

    # Collapsible explainer.
    parts.append(k.collapsible(x, 808, w, "Como funciona",
                               "Tema, cor de destaque e esfera de atividade desta janela"))
    return k.canvas("".join(parts))


def write_and_render(name, svg_text, render=True):
    os.makedirs(OUT_DIR, exist_ok=True)
    svg_path = os.path.join(OUT_DIR, name + ".svg")
    png_path = os.path.join(OUT_DIR, name + ".png")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_text)
    print("wrote", svg_path)
    if render and os.path.exists(PY):
        subprocess.run([PY, "-I", "-B", RENDER, svg_path, png_path, str(W), str(H)], check=True)
    return png_path


def main():
    jobs = [
        ("_example-hoje-gideon-escuro", "gideon-escuro", build_hoje),
        ("_example-hoje-gideon-claro", "gideon-claro", build_hoje),
        ("_example-hoje-catppuccin", "catppuccin", build_hoje),
        ("_example-aparencia-gideon-escuro", "gideon-escuro", build_aparencia),
    ]
    for name, theme, builder in jobs:
        k.set_theme(theme)
        write_and_render(name, builder())
    return 0


if __name__ == "__main__":
    sys.exit(main())
