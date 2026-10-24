#!/usr/bin/env python3
"""Permissões > Auditoria (docs/ui-spec/30-permissoes.md, section 7), new shell, gideon-escuro.

Writes docs/ui-mockups-v3/c03-auditoria.{svg,png}.
  target/ui-venv/bin/python -I -B scripts/mockups3/c03_auditoria.py
Columns follow spec 7.3 (Nº, Tipo, Origem, Resultado at the spec x positions). A 'Hora' column is
added inside the Tipo span (spec 11.2 NOVO: the ring has no time yet; the times here are sample data).
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
OUT_NAME = "c03-auditoria"

SUBS = ["Visão geral", "Concessões", "Auditoria"]
X0, WC = 32, 1316      # header and summary strip (spec 7.3)
CX, CW = 140, 1100     # content column
ROW_H = 44
INSET = 12
# (label, relative x, width). Nº 80 and Origem/Resultado at spec x; Hora carved out of Tipo (spec 620 -> 520 + 100).
COLS = [("Nº", 0, 80), ("Hora", 80, 100), ("Tipo", 180, 520), ("Origem", 700, 160), ("Resultado", 860, 240)]
CHIPS = ["Todos", "Plugin", "Skill", "Conexão", "Comando"]

# (Nº, hora, phrase from spec 7.6, origem, origem tone, resultado or None, resultado tone)
EVENTS = [
    (48, "14:32:07", "Acesso revogado no servidor; segredos apagados", "Conexão", "muted", "Concluído", "ok"),
    (47, "14:31:58", "Chamada de operação de conta (resultado no log, não no anel)", "Conexão", "muted", None, None),
    (46, "14:20:11", "Permissões de plugin aprovadas", "Plugin", "info", "Concluído", "ok"),
    (45, "14:18:40", "Ação proposta, aguardando sua decisão", "Comando", "muted", None, None),
    (44, "14:18:02", "Passo de skill registrado", "Skill", "muted", None, None),
    (43, "14:12:55", "Comando negado", "Comando", "muted", "Negado", "err"),
    (42, "14:10:31", "Skill tentou um serviço não permitido; recusado", "Skill", "muted", "Recusado", "warn"),
    (41, "14:02:19", "Plugin falhou", "Plugin", "info", "Falhou", "err"),
    (40, "13:57:44", "Sessão de voz iniciada", "Comando", "muted", None, None),
    (39, "13:57:12", "Evento do Core sem descrição", "Core", "muted", None, None),
]


# ---------------------------------------------------------------- local helpers

def shell(pending):
    badges = {"Permissões": pending} if pending else {}
    return k.topbar("Permissões", badges=badges, state="Em espera", state_tone="ok") + k.subtabs(SUBS, "Auditoria")


def header(title, subtitle):
    return (k.text(X0, 138, title, 24, "bold") + k.text(X0, 163, subtitle, 14, "normal", k.T["textMuted"]))


def summary(s):
    return (k.rect(X0 + 0.5, 184.5, WC - 1, 39, rx=k.RADIUS, fill=k.T["surface"], stroke=k.T["border"])
            + k.text(X0 + 16, 209, s, 14, "bold"))


def chips_row(x, y, items, active):
    """Spec 7.3: origin chips in a row at y 236 (30 px chips centred in the 40 px band)."""
    out, cx = [], x
    for label in items:
        out.append(k.chip(cx, y + 5, label, active=label == active))
        cx += k.chip_w(label) + 8
    return "".join(out)


def table_header(y):
    return k.table_header(CX, y, CW, [(rel + INSET, label) for label, rel, _ in COLS], h=32)


def event_row(y, ev):
    n, hora, phrase, origem, origem_tone, resultado, res_tone = ev
    cy = y + ROW_H / 2
    col = {label: rel for label, rel, _ in COLS}
    out = [k.text(CX + col["Nº"] + INSET, cy + 5, f"#{n}", 14, "normal", k.T["textMuted"]),
           k.text(CX + col["Hora"] + INSET, cy + 5, hora, 14, "normal", k.T["textMuted"]),
           k.text(CX + col["Tipo"] + INSET, cy + 5, phrase, 14, "normal", k.T["text"]),
           k.badge(CX + col["Origem"] + INSET, cy - 11, origem, origem_tone)]
    if resultado:
        out.append(k.badge(CX + col["Resultado"] + INSET, cy - 11, resultado, res_tone))
    else:
        out.append(k.text(CX + col["Resultado"] + INSET, cy + 5, "—", 14, "normal", k.T["textMuted"]))
    out.append(k.rect(CX, y + ROW_H - 1, CW, 1, fill=k.T["border"]))
    return "".join(out)


def details_row(y):
    """Spec 7.3 row y 840: 'Detalhes técnicos (Avançado)', collapsed by default, chevron at the right."""
    out = [k.rect(CX + 0.5, y + 0.5, CW - 1, 39, rx=k.RADIUS, fill=k.T["surfaceVariant"], stroke=k.T["border"]),
           k.text(CX + 18, y + 25, "Detalhes técnicos (Avançado)", 14, "bold")]
    cx, cy = CX + CW - 30, y + 20
    out.append(k.path(f"M{cx - 3} {cy - 5} L{cx + 3} {cy} L{cx - 3} {cy + 5}", stroke=k.T["textMuted"]))
    return "".join(out)


def build():
    k.set_theme(THEME)
    parts = [shell(2),
             header("Auditoria", "Eventos recentes do Core, sem conteúdo. Até 64, desde o início desta sessão do Core."),
             summary(f"{len(EVENTS)} eventos nesta sessão"),
             chips_row(CX, 236, CHIPS, "Todos"),
             table_header(284)]
    y = 316
    for ev in EVENTS:
        parts.append(event_row(y, ev))
        y += ROW_H
    parts.append(details_row(840))
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
    write_and_render(OUT_NAME, build())
    return 0


if __name__ == "__main__":
    sys.exit(main())
