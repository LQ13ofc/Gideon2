#!/usr/bin/env python3
"""Permissões > Visão geral (docs/ui-spec/30-permissoes.md, sections 1, 5 and 8), new shell, gideon-escuro.

Writes docs/ui-mockups-v3/c01-visao-geral.{svg,png} (2 pending) and
docs/ui-mockups-v3/c01-visao-geral-vazia.{svg,png} (nothing pending, 'Nada pendente').
  target/ui-venv/bin/python -I -B scripts/mockups3/c01_visao.py
Header and summary strip sit at x 32..1348 (spec 5.3); the card column is x 140, width 1100.
Local helpers only: the kit (scripts/mockup_kit3.py) is imported, not edited.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
ROOT = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)

import mockup_kit3 as k  # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "ui-mockups-v3")
PY = os.path.join(ROOT, "target", "ui-venv", "bin", "python")
RENDER = os.path.join(SCRIPTS, "render_svg.py")
W, H = k.CANVAS_W, k.CANVAS_H
THEME = "gideon-escuro"

SUBS = ["Visão geral", "Concessões", "Auditoria"]
X0, WC = 32, 1316      # header and summary strip (spec 5.3)
CX, CW = 140, 1100     # card column (spec 5.3)
PAD = 20


# ---------------------------------------------------------------- local helpers

def shell(pending):
    """Tab bar with Permissões active (badge = pending count) and the sub-tab bar."""
    badges = {"Permissões": pending} if pending else {}
    return k.topbar("Permissões", badges=badges, state="Em espera", state_tone="ok") + k.subtabs(SUBS, "Visão geral")


def header(title, subtitle, action=None, enabled=True):
    """Spec 5.3: title baseline 138, subtitle baseline 163, primary button x 1188-1348, y 124-164."""
    out = [k.text(X0, 138, title, 24, "bold"),
           k.text(X0, 163, subtitle, 14, "normal", k.T["textMuted"])]
    if action:
        out.append(k.button(1188, 124, 160, action, variant="primary",
                            state="normal" if enabled else "disabled", h=40))
    return "".join(out)


def summary(s):
    """Spec 5.3: strip x 32, y 184, 1316 x 40, bold sentence at 14 px."""
    return (k.rect(X0 + 0.5, 184.5, WC - 1, 39, rx=k.RADIUS, fill=k.T["surface"], stroke=k.T["border"])
            + k.text(X0 + 16, 209, s, 14, "bold"))


def divider(y):
    return k.rect(CX + 1, y, CW - 2, 1, fill=k.T["border"])


def pending_row(y, kind, kind_tone, line1, line2, action):
    """Spec 5.6 item 11/12: badge, 14 px line, 12 px line, secondary button. Row height 56."""
    out = [k.badge(CX + PAD, y + 17, kind, kind_tone)]
    tx = CX + PAD + k.badge_w(kind) + 12
    out.append(k.text(tx, y + 24, line1, 14))
    out.append(k.text(tx, y + 43, line2, 12, "normal", k.T["textMuted"]))
    bw = k.button_w(action)
    out.append(k.button(CX + CW - PAD - bw, y + 12, bw, action, variant="secondary", h=32))
    out.append(divider(y + 55))
    return "".join(out)


def grant_row(y, kind, kind_tone, label, state, state_tone):
    """Spec 5.6 items 16/17: 32 px row, badge, text, state badge, 'Ver ›' link at the right."""
    out = [k.badge(CX + PAD, y + 5, kind, kind_tone)]
    out.append(k.text(CX + PAD + k.badge_w(kind) + 12, y + 21, label, 14))
    end = CX + CW - PAD
    out.append(k.text(end, y + 21, "Ver ›", 14, "bold", k.T["accent"], anchor="end"))
    sx = end - k.text_w("Ver ›", 14, "bold") - 36 - k.badge_w(state)
    out.append(k.badge(sx, y + 5, state, state_tone))
    return "".join(out)


def empty_pending(y, h):
    """Spec 5.6 item 14: dashed frame, shield 32 px, 'Nada pendente.' 14 px bold, hint 12 px."""
    cx = CX + CW / 2
    out = [k.rect(CX + PAD + 0.5, y + 0.5, CW - 2 * PAD - 1, h - 1, rx=k.RADIUS + 4, fill=k.T["surfaceVariant"],
                  fo=0.4, stroke=k.T["outline"], so=0.6, dash="6 5")]
    out.append(k.icon("shield", cx - 16, y + 30, 32, k.T["textMuted"]))
    out.append(k.text(cx, y + 92, "Nada pendente.", 14, "bold", k.T["text"], anchor="middle"))
    out.append(k.text(cx, y + 113, "Plugins, skills e contas aparecem aqui quando precisarem da sua decisão.",
                      12, "normal", k.T["textMuted"], anchor="middle"))
    return "".join(out)


def collapsed_explainer(y):
    """Spec 5.6 item 20: 'Como funciona', 56 px, collapsed, chevron at the right."""
    x, w = CX, CW
    out = [k.rect(x + 0.5, y + 0.5, w - 1, 55, rx=k.RADIUS, fill=k.T["surfaceVariant"], stroke=k.T["border"]),
           k.text(x + 18, y + 33, "Como funciona", 15, "bold")]
    cx, cy = x + w - 30, y + 28
    out.append(k.path(f"M{cx - 3} {cy - 5} L{cx + 3} {cy} L{cx - 3} {cy + 5}", stroke=k.T["textMuted"]))
    return "".join(out)


def pending_card(rows_svg, n_pending):
    title = f"Pendências · {n_pending} aguardando sua decisão" if n_pending else "Pendências"
    return k.card(CX, k.CONTENT_Y, CW, 300, title) + rows_svg


def grants_card(rows_svg):
    y = 552
    return k.card(CX, y, CW, 230, "Concessões ativas") + rows_svg + k.text(CX + PAD, 676, "Ver todas em Concessões ›",
                                                                          14, "normal", k.T["accent"])


def build(empty=False):
    parts = [shell(0 if empty else 2)]
    if empty:
        parts.append(header("Visão geral", "O que precisa da sua decisão agora e o que já está concedido.",
                            action="Revisar próxima", enabled=False))
        parts.append(summary("2 aprovadas · 0 pendentes"))
        hint = "Nada pendente."
        tw = k.text_w(hint, 12) + 16
        parts.append(k.tooltip(X0 + WC - tw, 166, hint))
        parts.append(pending_card(empty_pending(k.CONTENT_Y + 52, 160), 0))
    else:
        parts.append(header("Visão geral", "O que precisa da sua decisão agora e o que já está concedido.",
                            action="Revisar próxima"))
        parts.append(summary("2 aprovadas · 2 pendentes"))
        rows = (pending_row(288, "Plugin", "info", "gideon.camera 0.1.0 · publisher não autenticado",
                            "Pede: captura da câmera", "Revisar")
                + pending_row(344, "Conexão", "muted", "Casa · Home Assistant",
                              "aguardando consentimento: 1 escopo", "Revisar"))
        parts.append(pending_card(rows, 2))

    parts.append(grants_card(
        grant_row(596, "Plugin", "info", "gideon.llm_engine 0.2.0 · rede do motor LLM, armazenamento de configurações",
                  "Aprovada", "ok")
        + divider(628)
        + grant_row(628, "Conexão", "muted", "Casa · Home Assistant · 1 escopo concedido", "Concedido", "ok")))
    parts.append(collapsed_explainer(798))
    return k.canvas("".join(parts))


def write_and_render(name, svg_text):
    os.makedirs(OUT_DIR, exist_ok=True)
    svg_path = os.path.join(OUT_DIR, name + ".svg")
    png_path = os.path.join(OUT_DIR, name + ".png")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_text)
    print("wrote", svg_path)
    subprocess.run([PY, "-I", "-B", RENDER, svg_path, png_path, str(W), str(H)], check=True)
    return png_path


def main():
    k.set_theme(THEME)
    write_and_render("c01-visao-geral", build(empty=False))
    k.set_theme(THEME)
    write_and_render("c01-visao-geral-vazia", build(empty=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
