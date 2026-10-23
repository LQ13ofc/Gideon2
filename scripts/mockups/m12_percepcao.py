#!/usr/bin/env python3
"""Mockup 12 'Percepção e ação' (docs/UI_DESIGN.md, página 12), composed with scripts/mockup_kit.py.

Writes docs/ui-mockups/12-percepcao-e-acao.svg. Render:
  target/ui-venv/bin/python -I -B scripts/render_svg.py docs/ui-mockups/12-percepcao-e-acao.svg
"""
import os
import sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mockup_kit as k  # noqa: E402

OUT = os.path.join(k.ROOT, "docs", "ui-mockups", "12-percepcao-e-acao.svg")
X, W = k.content_box()  # 256, 1100
GAP = k.CARD_GAP
MONO = "DejaVu Sans Mono, Liberation Mono, monospace"


def mono(x, y, s, size=13, fill=k.TEXT_BODY):
    """Monospace line for technical output."""
    return (f'<text x="{round(x, 2)}" y="{round(y, 2)}" font-family="{MONO}" '
            f'font-size="{size}" fill="{fill}">{escape(str(s))}</text>')


def privacy_card(x, y, w, h):
    out = [k.card(x, y, w, h, "Privacidade")]
    out.append(k.text(x + w - 20, y + 34, "Backends simulados: nenhum hardware real é acessado",
                      13, "normal", k.MUTED, anchor="end"))
    tw = (w - 40 - 12) // 2
    for i, (label, state) in enumerate([("Microfone", "Desligado"), ("Câmera", "Desligada")]):
        tx = x + 20 + i * (tw + 12)
        ty = y + 54
        out.append(k.rect(tx + 0.5, ty + 0.5, tw - 1, 43, rx=12, fill=k.INPUT_BG, stroke=k.DIVIDER))
        out.append(k.circle(tx + 18, ty + 22, 5, fill=k.MUTED))
        out.append(k.text(tx + 34, ty + 27, label, 14, "bold", k.TEXT_STRONG))
        out.append(k.text(tx + tw - 16, ty + 27, state, 13, "normal", k.MUTED, anchor="end"))
    return "".join(out)


PLUGINS = [
    # nome, versão, estado (texto, tom), sintético?, permissão, (texto, tom), backend, botões de teste
    ("screen_observe", "1.0.0", ("Em execução", "ok"), "observação de tela", ("Concedida", "ok"),
     ["Capturar", "Estado"]),
    ("computer_control", "1.0.0", ("Em execução", "ok"), "controle de entrada", ("Concedida", "ok"),
     ["Árvore", "Estado"]),
    ("audio_advanced", "1.0.0", ("Parado", "muted"), "rota de áudio", ("Pendente", "warn"),
     ["Estado"]),
    ("mic_advanced", "1.0.0", ("Parado", "muted"), "microfone avançado", ("Pendente", "warn"),
     ["Estado"]),
    ("camera_gesture", "1.0.0", ("Parado", "muted"), "câmera", ("Pendente", "warn"),
     ["Estado"]),
    ("display_manipulate", "1.0.0", ("Parado", "muted"), "manipulação de tela", ("Pendente", "warn"),
     []),
]


def plugin_card(x, y, w, h, name, version, state, perm, perm_state, buttons, unsupported=False):
    out = [k.card(x, y, w, h)]
    out.append(k.text(x + 20, y + 34, name, 17, "bold", k.TEXT_STRONG))
    out.append(k.text(x + 20 + k.text_w(name, 17, "bold") + 8, y + 34, version, 13, "normal", k.TEXT_MUTED))
    st, tone = state
    out.append(k.badge(x + w - 20 - k.badge_w(st), y + 14, st, tone))

    if unsupported:
        out.append(k.badge(x + 20, y + 50, "UNSUPPORTED", "err"))
    else:
        out.append(k.badge(x + 20, y + 50, "SINTÉTICO — sem hardware real", "warn"))

    pt, pt_tone = perm_state
    out.append(k.text(x + 20, y + 96, f"Permissão: {perm}", 14, "normal", k.TEXT))
    out.append(k.badge(x + w - 20 - k.badge_w(pt), y + 82, pt, pt_tone))

    if unsupported:
        backend = "Backend real: não suportado nesta build"
    else:
        backend = "Backend real: não suportado · pendente de validação humana"
    out.append(k.text(x + 20, y + 120, backend, 13, "normal", k.TEXT_MUTED))

    if buttons:
        bx = x + 20
        for b in buttons:
            bw = k.button_w(b)
            out.append(k.button(bx, y + 130, bw, b, h=36))
            bx += bw + 10
    else:
        out.append(k.text(x + 20, y + 152, "Sem ações de teste nesta build.", 13, "normal", k.MUTED))
    return "".join(out)


def build():
    parts = [k.sidebar(active="Percepção e ação"),
             k.header("Percepção e ação", "Teste sensores e ações simulados; nada age no seu computador.",
                      "Em espera", tone="ok")]

    parts.append(privacy_card(X, 96, W, 116))

    cw = (W - GAP) // 2  # 542
    ch = 176
    y0 = 96 + 116 + GAP  # 228
    for i, (name, ver, state, perm, perm_state, buttons) in enumerate(PLUGINS):
        col, row = i % 2, i // 2
        x = X + col * (cw + GAP)
        y = y0 + row * (ch + GAP)
        parts.append(plugin_card(x, y, cw, ch, name, ver, state, perm, perm_state, buttons,
                                 unsupported=name == "display_manipulate"))

    # Último resultado: painel inferior.
    ry = y0 + 3 * ch + 2 * GAP + GAP  # 804
    rh = 76
    parts.append(k.card(X, ry, W, rh, "Último resultado"))
    bw = k.badge_w("Concluído")
    parts.append(k.badge(X + W - 20 - bw, ry + 14, "Concluído", "ok"))
    parts.append(mono(X + 20, ry + 56,
                      "screen_observe.capture · status=ok · backend=sintético · hardware_real=false · 3 ms"))
    return k.canvas("".join(parts))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(build())
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
