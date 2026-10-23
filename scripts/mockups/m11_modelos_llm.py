#!/usr/bin/env python3
"""Mockup 11 'Modelos LLM' (docs/UI_DESIGN.md, página 11), composed with scripts/mockup_kit.py.

Writes docs/ui-mockups/11-modelos-llm.svg. Render:
  target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/11-modelos-llm.svg
"""
import os
import sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT = os.path.join(k.ROOT, "docs", "ui-mockups", "11-modelos-llm.svg")
X, W = k.content_box()  # 256, 1100
GAP = k.CARD_GAP
MONO = "DejaVu Sans Mono, Liberation Mono, monospace"


def mono(x, y, s, size=13, fill=k.TEXT_BODY):
    """Monospace line for technical values (hashes, ids)."""
    return (f'<text x="{round(x, 2)}" y="{round(y, 2)}" font-family="{MONO}" '
            f'font-size="{size}" fill="{fill}">{escape(str(s))}</text>')


def right_badges(right, y, items):
    total = sum(k.badge_w(t) for t, _ in items) + 8 * (len(items) - 1)
    x = right - total
    out = []
    for t, tone in items:
        out.append(k.badge(x, y, t, tone))
        x += k.badge_w(t) + 8
    return "".join(out)


MODELS = [
    # nome, provedor · origem, certificação (texto, tom), latência, custo
    ("Gemini 3.5 Flash Lite", "Google · Nuvem", ("Certificado", "ok"), "1,2 s", "US$ 0,10 / 1M"),
    ("Ministral 3B", "Mistral · Nuvem", ("Certificado", "ok"), "0,9 s", "US$ 0,04 / 1M"),
    ("Llama 3.2 3B Instruct", "OpenRouter · Nuvem", ("Candidato", "warn"), "1,8 s", "US$ 0,06 / 1M"),
    ("GPT-5.4 nano", "OpenCode · Nuvem", ("Declarado", "muted"), "—", "US$ 0,20 / 1M"),
    ("Llama 3.2 3B via Ollama", "Ollama · Local", ("Candidato", "warn"), "2,4 s", "gratuito"),
]
SELECTED = 1  # Ministral 3B


def build():
    parts = [k.sidebar(active="Modelos LLM"),
             k.header("Modelos LLM", "Escolha, teste e configure o modelo do motor LLM.", "Em espera", tone="ok")]

    # Resumo: uma linha com badges.
    parts.append(k.card(X, 96, W, 44))
    parts.append(k.text(X + 20, 96 + 28, "Modelo atual: gemini-3.5-flash-lite", 15, "bold", k.TEXT_STRONG))
    parts.append(right_badges(X + W - 20, 107, [("Disponível", "ok"), ("Nuvem", "info")]))

    # Filtros: recomendados/personalizados e origem.
    fy = 156
    items_a = ["Recomendados", "Personalizados"]
    items_b = ["Todos", "Local", "Nuvem"]
    parts.append(k.segmented(X, fy, items_a, 0))
    bx = X + k.segmented_w(items_a) + 16
    parts.append(k.segmented(bx, fy, items_b, 0))
    parts.append(k.text(X + W, fy + 23, "5 modelos", 13, "normal", k.TEXT_MUTED, anchor="end"))

    # Lista de modelos (esquerda).
    lx, ly, lw, lh = X, 208, 640, 420
    parts.append(k.card(lx, ly, lw, lh, "Modelos recomendados"))
    hy = ly + 62
    parts.append(k.text(lx + 20, hy, "Modelo", 12, "normal", k.TEXT_LABEL))
    parts.append(k.text(lx + 300, hy, "Certificação", 12, "normal", k.TEXT_LABEL))
    parts.append(k.text(lx + 430, hy, "Latência", 12, "normal", k.TEXT_LABEL))
    parts.append(k.text(lx + 520, hy, "Custo", 12, "normal", k.TEXT_LABEL))
    for i, (name, prov, (cert, tone), lat, cost) in enumerate(MODELS):
        top = ly + 74 + i * 58
        cy = top + 29
        sel = i == SELECTED
        if sel:
            parts.append(k.rect(lx + 10, top + 4, lw - 20, 50, rx=10, fill=k.ACCENT, fo=0.16,
                                stroke=k.ACCENT, so=0.6))
            parts.append(k.rect(lx + 10, top + 14, 3, 30, rx=2, fill=k.ACCENT))
        parts.append(k.text(lx + 24, cy - 2, name, 14, "bold" if sel else "normal",
                            k.TEXT_STRONG if sel else k.TEXT))
        parts.append(k.text(lx + 24, cy + 16, prov, 12, "normal", k.TEXT_MUTED))
        parts.append(k.badge(lx + 300, cy - 11, cert, tone))
        parts.append(k.text(lx + 430, cy + 5, lat, 14, "normal", k.TEXT_BODY))
        parts.append(k.text(lx + 520, cy + 5, cost, 14, "normal", k.TEXT_BODY))
        if i < len(MODELS) - 1:
            parts.append(k.line(lx + 20, top + 57, lx + lw - 20, top + 57, stroke=k.DIVIDER))
    fy2 = ly + 392
    parts.append(k.text(lx + 20, fy2, "Carregar mais", 14, "bold", k.ACCENT))
    parts.append(k.line(lx + 20, fy2 + 5, lx + 20 + k.text_w("Carregar mais", 14, "bold"), fy2 + 5,
                        stroke=k.ACCENT))
    parts.append(k.text(lx + lw - 20, fy2, "valores ilustrativos", 12, "normal", k.MUTED, anchor="end"))

    # Recolhíveis abaixo da lista.
    cy0 = ly + lh + GAP
    for j, (title, summary) in enumerate([
        ("Adicionar modelo personalizado", "Informe nome, provedor e caminho ou URL do modelo"),
        ("Fallback", "Se o modelo principal falhar, usa o próximo certificado"),
        ("Hardware e plugin", "Memória, CPU ou GPU detectadas e plugin de inferência"),
    ]):
        parts.append(k.collapsible(lx, cy0 + j * (k.COLLAPSIBLE_H + 16), lw, title, summary))

    # Detalhes do modelo selecionado (direita).
    dx, dw = X + 656, 444
    dy, dh = 208, 636
    name, prov, (cert, tone), _lat, _cost = MODELS[SELECTED]
    parts.append(k.card(dx, dy, dw, dh, "Detalhes do modelo"))
    parts.append(k.text(dx + 20, dy + 62, name, 15, "bold", k.TEXT_STRONG))
    parts.append(k.text(dx + 20, dy + 82, prov, 13, "normal", k.TEXT_MUTED))
    bx = dx + 20
    for t, tn in [(cert, tone), ("Nuvem", "info")]:
        parts.append(k.badge(bx, dy + 94, t, tn))
        bx += k.badge_w(t) + 8

    pairs = [
        ("Licença", "Termos comerciais do provedor"),
        ("Quantização", "não se aplica (execução na nuvem)"),
        ("Hash do pacote", None),
        ("Custo", "US$ 0,04 por 1M tokens de entrada"),
        ("Hardware mínimo", "nenhum: execução na nuvem"),
    ]
    for i, (label, value) in enumerate(pairs):
        py = dy + 136 + i * 50
        parts.append(k.text(dx + 20, py, label, 12, "normal", k.TEXT_LABEL))
        if value is None:
            parts.append(mono(dx + 20, py + 20, "sha256:9f2c…e41a", 14, k.TEXT))
        else:
            parts.append(k.text(dx + 20, py + 20, value, 14, "normal", k.TEXT))

    ry = dy + 396
    parts.append(k.text(dx + 20, ry, "Recursos", 12, "normal", k.TEXT_LABEL))
    rx = dx + 20
    for t, tone in [("Streaming: sim", "ok"), ("Ferramentas: sim", "ok"), ("Visão: não", "muted")]:
        parts.append(k.badge(rx, ry + 12, t, tone))
        rx += k.badge_w(t) + 8
    parts.append(k.text(dx + 20, ry + 66, "Último teste", 12, "normal", k.TEXT_LABEL))
    parts.append(k.badge(dx + 20, ry + 76, "Não verificado", "muted"))

    parts.append(k.button(dx + 20, dy + dh - 20 - 40, dw - 40, "Usar este modelo", primary=True))
    return k.canvas("".join(parts))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(build())
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
