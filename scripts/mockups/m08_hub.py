#!/usr/bin/env python3
"""Mockup 08: Gideon Hub (docs/UI_DESIGN.md, item 8) and its empty state.

Writes docs/ui-mockups/08-gideon-hub.svg and docs/ui-mockups/08b-hub-vazio.svg. Render:
  target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/08-gideon-hub.svg
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT_DIR = os.path.join(k.ROOT, "docs", "ui-mockups")
OUT = os.path.join(OUT_DIR, "08-gideon-hub.svg")
OUT_EMPTY = os.path.join(OUT_DIR, "08b-hub-vazio.svg")

GRID_Y = 276
CARD_H = 164
COLLAPSE_Y = 816


def strip(x, y, w, h):
    return k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=12, fill=k.INPUT_BG, stroke=k.CARD_BORDER)


def lock(x, y, size=20, color=k.ICON_IDLE):
    """Padlock drawn in the 24-unit icon grid (no lock icon in app/icons)."""
    return (f'<g transform="translate({k._n(x)} {k._n(y)}) scale({k._n(size / 24.0)})" fill="none" '
            f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
            + k.rect(5, 11, 14, 10, rx=2)
            + k.path("M8 11V8a4 4 0 0 1 8 0v3")
            + "</g>")


def security_note(x, y, w):
    note = "Pacotes verificados por checksum · publisher não autenticado · sem rede"
    return strip(x, y, w, 40) + lock(x + 16, y + 10) + k.text(x + 46, y + 25, note, 13, "normal", k.TEXT_BODY)


def summary(x, w, badge_text, tone, counts):
    cy = k.CONTENT_TOP + 30
    out = [strip(x, k.CONTENT_TOP, w, 60), k.badge(x + 20, cy - 11, badge_text, tone)]
    tx = x + 20 + k.badge_w(badge_text) + 16
    out.append(k.text(tx, cy + 5, counts, 14, "bold", k.TEXT_STRONG))
    return "".join(out)


def plugin_card(x, y, w, h, title, tech, state, tone, desc, note, action, primary=True):
    """Plugin card: name, technical id + version, state badge, one line, primary action on the right."""
    out = [k.card(x, y, w, h)]
    out.append(k.text(x + 20, y + 34, title, 17, "bold", k.TEXT_STRONG))
    out.append(k.badge(x + w - 20 - k.badge_w(state), y + 17, state, tone))
    out.append(k.text(x + 20, y + 60, tech, 12, "normal", k.TEXT_MUTED))
    out.append(k.text(x + 20, y + 92, desc, 14, "normal", k.TEXT_BODY))
    out.append(k.text(x + 20, y + 129, note, 12, "normal", k.MUTED))
    bw = k.button_w(action, primary)
    out.append(k.button(x + w - 20 - bw, y + h - 60, bw, action, primary=primary))
    return "".join(out)


def build_main():
    x, w = k.content_box()
    parts = [k.sidebar(active="Gideon Hub"),
             k.header("Gideon Hub", "Capacidades opcionais, em um só lugar.")]
    parts.append(summary(x, w, "Catálogo local verificado", "ok", "6 plugins · 2 instalados"))
    parts.append(security_note(x, 168, w))

    parts.append(k.segmented(x, 224, ["Todos", "Instalados", "Disponíveis"], 0))

    half = (w - k.CARD_GAP) // 2  # 542
    cols = [x, x + half + k.CARD_GAP]
    plugins = [
        ("Motor LLM", "llm_engine · versão 1.2.0", "Ativo", "ok",
         "Conecta o Gideon a modelos de linguagem locais.", "Permissões aprovadas", "Desativar"),
        ("Observação de tela", "screen_observe · versão 1.0.0", "Instalado", "info",
         "Lê a tela somente quando você permitir.", "Permissões aprovadas · inativo", "Ativar"),
        ("Controle do computador", "computer_control · versão 1.0.0", "Disponível", "muted",
         "Move o mouse e digita, com aprovação por ação.", "Permissões ainda não aprovadas", "Instalar"),
        ("Áudio avançado", "audio_advanced · versão 1.0.0", "Disponível", "muted",
         "Processamento extra da saída de áudio.", "Permissões ainda não aprovadas", "Instalar"),
        ("Microfone avançado", "mic_advanced · versão 0.9.1", "Em quarentena", "err",
         "Captura extra; o pacote falhou na verificação.", "Checksum não confere; não ativar.", "Ver motivo"),
        ("Gesto com câmera", "camera_gesture · versão 1.0.0", "Disponível", "muted",
         "Reconhece gestos pela câmera; exige permissão.", "Permissões ainda não aprovadas", "Instalar"),
    ]
    for i, (title, tech, state, tone, desc, note, action) in enumerate(plugins):
        r, c = divmod(i, 2)
        cx = cols[c]
        cy = GRID_Y + r * (CARD_H + k.CARD_GAP)
        parts.append(plugin_card(cx, cy, half, CARD_H, title, tech, state, tone, desc, note, action,
                                 primary=action != "Ver motivo"))

    parts.append(k.collapsible(x, COLLAPSE_Y, w, "Como funciona",
                               "Instalar copia o pacote verificado; nada é executado até você ativar."))
    return k.canvas("".join(parts))


def build_empty():
    x, w = k.content_box()
    parts = [k.sidebar(active="Gideon Hub"),
             k.header("Gideon Hub", "Capacidades opcionais, em um só lugar.")]
    parts.append(summary(x, w, "Catálogo não configurado", "warn", "0 plugins · 0 instalados"))
    parts.append(security_note(x, 168, w))
    parts.append(k.empty_state(x, GRID_Y, w, 3 * CARD_H + 2 * k.CARD_GAP, "hub",
                               "Configure um catálogo local para ver plugins verificados.",
                               "Explorar catálogo", primary=True))
    parts.append(k.collapsible(x, COLLAPSE_Y, w, "Como funciona",
                               "Instalar copia o pacote verificado; nada é executado até você ativar."))
    return k.canvas("".join(parts))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for path, svg in ((OUT, build_main()), (OUT_EMPTY, build_empty())):
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
