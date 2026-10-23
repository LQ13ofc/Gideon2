#!/usr/bin/env python3
"""Mockup 09: Skills (docs/UI_DESIGN.md, item 9) and its empty state.

Writes docs/ui-mockups/09-skills.svg and docs/ui-mockups/09b-skills-vazio.svg. Render:
  target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/09-skills.svg
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT_DIR = os.path.join(k.ROOT, "docs", "ui-mockups")
OUT = os.path.join(OUT_DIR, "09-skills.svg")
OUT_EMPTY = os.path.join(OUT_DIR, "09b-skills-vazio.svg")

HELP_SUMMARY = "Validar não grava. Simular não chama capacidades. Executar pede sua aprovação em cada passo."


def strip(x, y, w, h):
    return k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=12, fill=k.INPUT_BG, stroke=k.CARD_BORDER)


def header(title, subtitle, state, buttons):
    """Header with secondary buttons placed left of the state pill, vertically centred on it."""
    parts = [k.header(title, subtitle, state)]
    pill_w = 44 + k.text_w(state, 13) + 14
    right = k.CONTENT_RIGHT - pill_w - 12
    for label in reversed(buttons):
        bw = k.button_w(label)
        right -= bw
        parts.append(k.button(right, 32, bw, label))
        right -= 10
    return "".join(parts)


def summary(x, w, installed, enabled_text, enabled_tone):
    cy = k.CONTENT_TOP + 30
    out = [strip(x, k.CONTENT_TOP, w, 60)]
    out.append(k.text(x + 20, cy + 5, installed, 14, "bold", k.TEXT_STRONG))
    bx = x + 20 + k.text_w(installed, 14, "bold") + 16
    out.append(k.badge(bx, cy - 11, enabled_text, enabled_tone))
    return "".join(out)


def collapsible_pair(x, w, y_hist, y_help):
    return (k.collapsible(x, y_hist, w, "Histórico",
                          "Últimas execuções: 2 concluídas e 1 cancelada.")
            + k.collapsible(x, y_help, w, "Como funciona", HELP_SUMMARY))


def build_main():
    x, w = k.content_box()
    parts = [k.sidebar(active="Skills"),
             header("Skills", "Procedimentos sobre capacidades instaladas; não concedem permissões.",
                    "Em espera", ["Criar", "Importar"])]
    parts.append(summary(x, w, "2 instaladas", "1 habilitada", "ok"))

    # Card 1: installed skills, one row each (name, version, state badge, deps, contextual action).
    y1 = k.CONTENT_TOP + 60 + k.CARD_GAP  # 172
    skills = [
        ("Resumir nota", "resumir_nota", "1.0.0", "Habilitada", "ok", True, "Executar"),
        ("Organizar downloads", "organizar_downloads", "0.2.0", "Aprovada", "info", True, "Habilitar"),
        ("Agenda diária", "agenda_diaria", "0.1.0", "Rascunho", "muted", False, "Validar"),
    ]
    h1 = 52 + len(skills) * 68 + 12
    parts.append(k.card(x, y1, w, h1, "Minhas skills"))
    ry = k.card_body_top(y1)
    for i, (name, sid, ver, state, tone, deps_ok, action) in enumerate(skills):
        top = ry + i * 68
        cy = top + 34
        parts.append(k.text(x + 20, cy - 2, name, 15, "bold", k.TEXT_STRONG))
        parts.append(k.text(x + 20, cy + 18, f"{sid} · v{ver}", 12, "normal", k.TEXT_MUTED))
        parts.append(k.badge(x + 330, cy - 11, state, tone))
        if deps_ok:
            parts.append(k.text(x + 480, cy + 5, "Dependências ok", 13, "normal", k.OK))
        else:
            parts.append(k.text(x + 480, cy + 5, "Dependências: faltando calendar_read", 13, "normal", k.WARN))
        bw = k.button_w(action, primary=True)
        parts.append(k.button(x + w - 20 - bw, top + 14, bw, action, primary=True))
        if i < len(skills) - 1:
            parts.append(k.rect(x + 20, top + 67, w - 40, 1, fill=k.DIVIDER))

    # Card 2: a run in progress. Cancel sits top-right, steps list below.
    y2 = y1 + h1 + k.CARD_GAP
    h2 = 264
    parts.append(k.card(x, y2, w, h2, "Execução"))
    cbw = k.button_w("Cancelar")
    parts.append(k.button(x + w - 20 - cbw, y2 + 12, cbw, "Cancelar"))
    parts.append(k.text(x + 20, y2 + 76, "Resumir nota · passo 2 de 4 em andamento", 14, "normal", k.TEXT_BODY))
    steps = [
        ("1. Ler nota", "Concluído", "ok", "nota.md"),
        ("2. Gerar resumo", "Em andamento", "info", "executando agora"),
        ("3. Salvar resumo", "Aguarda aprovação", "warn", "gravação só após sua aprovação"),
        ("4. Atualizar histórico", "Pendente", "muted", "depois do passo 3"),
    ]
    for i, (name, state, tone, detail) in enumerate(steps):
        top = y2 + 92 + i * 40
        cy = top + 20
        parts.append(k.text(x + 20, cy + 5, name, 14, "normal", k.TEXT))
        parts.append(k.badge(x + 300, cy - 11, state, tone))
        parts.append(k.text(x + 500, cy + 5, detail, 13, "normal", k.MUTED))
        if i < len(steps) - 1:
            parts.append(k.rect(x + 20, top + 39, w - 40, 1, fill=k.DIVIDER))

    y_hist = y2 + h2 + k.CARD_GAP
    y_help = y_hist + k.COLLAPSIBLE_H + 16
    parts.append(collapsible_pair(x, w, y_hist, y_help))
    return k.canvas("".join(parts))


def build_empty():
    x, w = k.content_box()
    parts = [k.sidebar(active="Skills"),
             header("Skills", "Procedimentos sobre capacidades instaladas; não concedem permissões.",
                    "Em espera", ["Criar", "Importar"])]
    parts.append(summary(x, w, "0 instaladas", "0 habilitadas", "muted"))

    y1 = k.CONTENT_TOP + 60 + k.CARD_GAP
    h1 = 240
    parts.append(k.card(x, y1, w, h1, "Minhas skills"))
    parts.append(k.empty_state(x + 20, y1 + 52, w - 40, h1 - 52 - 20, "sparkles",
                               "Nenhuma skill instalada ainda.", "Criar skill", primary=True))

    # No history without runs: only the closed explainer stays.
    parts.append(k.collapsible(x, y1 + h1 + k.CARD_GAP, w, "Como funciona", HELP_SUMMARY))
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
