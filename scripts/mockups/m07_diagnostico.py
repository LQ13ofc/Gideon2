#!/usr/bin/env python3
"""Mockup 07: Diagnóstico (docs/UI_DESIGN.md, item 7).

Writes docs/ui-mockups/07-diagnostico.svg. Render:
  target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/07-diagnostico.svg
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT = os.path.join(k.ROOT, "docs", "ui-mockups", "07-diagnostico.svg")


def strip(x, y, w, h):
    """Summary strip: one line of state with badges, 12 px radius."""
    return k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=12, fill=k.INPUT_BG, stroke=k.CARD_BORDER)


def build():
    x, w = k.content_box()
    parts = [k.sidebar(active="Diagnóstico"),
             k.header("Diagnóstico", "Acompanhe o estado real da Base.")]

    # Summary strip: connection state and engine count (1 line).
    y0 = k.CONTENT_TOP
    parts.append(strip(x, y0, w, 60))
    cy = y0 + 30
    parts.append(k.badge(x + 20, cy - 11, "Core conectado", "ok"))
    tx = x + 20 + k.badge_w("Core conectado") + 16
    parts.append(k.text(tx, cy + 5, "3 motores", 14, "bold", k.TEXT_STRONG))
    parts.append(k.text(tx + k.text_w("3 motores", 14, "bold") + 10, cy + 5,
                        "Wake · STT · TTS", 14, "normal", k.TEXT_MUTED))

    # Card 1: engines, one row each (state badge + detail).
    y1 = y0 + 60 + k.CARD_GAP  # 172
    h1 = 260
    parts.append(k.card(x, y1, w, h1, "Motores"))
    engines = [
        ("Wake", "Replay encerrado", "warn", "Frase Hey Gideon · validação física pendente"),
        ("STT", "Pronto", "ok", "base-en-dev-v1 · em desenvolvimento"),
        ("TTS", "Concluído", "ok", "Voz Alba · inglês · candidata"),
    ]
    ry = k.card_body_top(y1)
    for i, (name, state, tone, detail) in enumerate(engines):
        cols = [
            (0, {"s": name, "size": 15, "weight": "bold", "fill": k.TEXT_STRONG}),
            (110, lambda ax, cy_, s=state, t=tone: k.badge(ax, cy_ - 11, s, t)),
            (290, {"s": detail, "size": 14, "fill": k.TEXT_BODY}),
        ]
        parts.append(k.row(x + 20, ry + i * 64, w - 40, cols, h=64, divider=i < len(engines) - 1))

    # Row 2: system state (left) and recent activity (right), same height.
    y2 = y1 + h1 + k.CARD_GAP  # 448
    h2 = 260
    half = (w - k.CARD_GAP) // 2  # 542
    xl, xr = x, x + half + k.CARD_GAP

    parts.append(k.card(xl, y2, half, h2, "Estado do sistema"))
    state_rows = [("Core", "Conectado"), ("Perfil", "Hey Gideon"),
                  ("Idioma", "Inglês"), ("Privacidade", "Local, sem rede")]
    sy = k.card_body_top(y2)
    for i, (key, value) in enumerate(state_rows):
        cols = [
            (0, {"s": key, "size": 14, "fill": k.TEXT_LABEL}),
            (150, {"s": value, "size": 14, "fill": k.TEXT}),
        ]
        parts.append(k.row(xl + 20, sy + i * 48, half - 40, cols, h=48, divider=i < len(state_rows) - 1))

    parts.append(k.card(xr, y2, half, h2, "Atividade recente"))
    log = [
        ("14:02:11", "Core conectado"),
        ("14:02:12", "Wake: replay encerrado"),
        ("14:02:12", "STT: pronto"),
        ("14:02:13", "TTS: concluído"),
    ]
    for i, (when, msg) in enumerate(log):
        cols = [
            (0, {"s": when, "size": 13, "fill": k.MUTED}),
            (100, {"s": msg, "size": 14, "fill": k.TEXT_MUTED}),
        ]
        parts.append(k.row(xr + 20, sy + i * 48, half - 40, cols, h=48, divider=i < len(log) - 1))

    parts.append(k.text(x, 858, "Ajuda: estes valores são lidos do Core. Alterações de motor exigem reinício do Core.",
                        12, "normal", k.MUTED))
    return k.canvas("".join(parts))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(build())
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
