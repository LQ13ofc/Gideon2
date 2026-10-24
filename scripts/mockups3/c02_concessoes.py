#!/usr/bin/env python3
"""Permissões > Concessões and its dialogs (docs/ui-spec/30-permissoes.md, sections 4, 6 and 3), gideon-escuro.

Writes docs/ui-mockups-v3/:
  c02-concessoes-todas.{svg,png}      filter Todas, group by Origem (default)
  c02-concessoes-conexoes.{svg,png}   filter Conexões, high-risk row highlighted
  c02-revisar-modal.{svg,png}         D-P1 'Revisar permissões' for a plugin (over Todas)
  c02-revogar-confirmacao.{svg,png}   D-P4 'Revogar acesso' with the scopes that will go (over Conexões)
  target/ui-venv/bin/python -I -B scripts/mockups3/c02_concessoes.py
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
X0, WC = 32, 1316      # header and summary strip (spec 6.3)
CX, CW = 140, 1100     # content column
ROW_H, GROUP_H = 52, 28
FILTERS = ["Todas", "Plugins", "Skills", "Conexões"]
GROUPING = ["Agrupar por: Origem", "Agrupar por: Item"]

# Column layout inside the table: (relative x, width, label). Spec 6.3 positions, widened where a
# badge or button would otherwise clip (see report). Content inset 12 px from each column start.
COLS = [(0, 40, "Nº"), (40, 110, "Origem"), (150, 230, "Item"), (380, 250, "Permissão ou escopo"),
        (630, 90, "Acesso"), (720, 210, "Estado"), (930, 170, "Ação")]
INSET = 12
DW = 440               # dialog width (spec 4)


# ---------------------------------------------------------------- local helpers

def shell(pending):
    badges = {"Permissões": pending} if pending else {}
    return k.topbar("Permissões", badges=badges, state="Em espera", state_tone="ok") + k.subtabs(SUBS, "Concessões")


def header(title, subtitle):
    """Spec 6.3: title baseline 138, subtitle baseline 163, x 32; no primary button on this sub-tab."""
    return (k.text(X0, 138, title, 24, "bold") + k.text(X0, 163, subtitle, 14, "normal", k.T["textMuted"]))


def summary(s):
    return (k.rect(X0 + 0.5, 184.5, WC - 1, 39, rx=k.RADIUS, fill=k.T["surface"], stroke=k.T["border"])
            + k.text(X0 + 16, 209, s, 14, "bold"))


def segmented_filter(x, y, w, items, active):
    """Spec 6.3: segmented filter 420 x 40. Four equal segments, active = accent fill."""
    out = [k.rect(x + 0.5, y + 0.5, w - 1, 39, rx=k.RADIUS, fill=k.T["surfaceVariant"], stroke=k.T["border"])]
    seg = (w - 8) / len(items)
    for i, label in enumerate(items):
        sx = x + 4 + i * seg
        on = label == active
        if on:
            out.append(k.rect(sx, y + 4, seg, 32, rx=8, fill=k.T["accent"]))
        out.append(k.text(sx + seg / 2, y + 25, label, 14, "bold" if on else "normal",
                          k.T["onAccent"] if on else k.T["textMuted"], anchor="middle"))
    return "".join(out)


def block_lines(x, cy, lines, size=14, weight="normal", fill=None):
    """One or two 14 px lines centred on cy (line step 20)."""
    n = len(lines)
    start = cy + 5 - (n - 1) * 10
    return "".join(k.text(x, start + i * 20, ln, size, weight, fill) for i, ln in enumerate(lines))


def table_header(y):
    return k.table_header(CX, y, CW, [(rel + INSET, label) for rel, _, label in COLS], h=32)


def group_header(y, title, n):
    return (k.rect(CX, y, CW, GROUP_H, fill=k.T["surfaceVariant"], fo=0.6)
            + k.text(CX + INSET, y + 18, f"{title} · {n}", 12, "bold", k.T["textMuted"]))


def table_row(y, n, r):
    """Spec 6.3-6.5: one 52 px row. r keys: origem, origem_tone, item[], perm[], perm_tone, acesso,
    acesso_tone, estado, estado_tone, action, variant, risk."""
    cy = y + ROW_H / 2
    out = []
    if r.get("risk"):
        out.append(k.rect(CX, y, CW, ROW_H, fill=k.T["error"], fo=0.10))
        out.append(k.modified_marker(CX, y, ROW_H, "err"))
    col = {label: rel for rel, _, label in COLS}
    out.append(k.text(CX + col["Nº"] + INSET, cy + 5, str(n), 14, "normal", k.T["textMuted"]))
    out.append(k.badge(CX + col["Origem"] + INSET, cy - 11, r["origem"], r["origem_tone"]))
    out.append(block_lines(CX + col["Item"] + INSET, cy, r["item"]))
    perm_fill = k.T[r["perm_tone"]] if r.get("perm_tone") else None
    perm_w = COLS[3][1] - 2 * INSET
    perm_lines = k.wrap_px_lines(r["perm"][0], perm_w, 14)
    out.append(block_lines(CX + col["Permissão ou escopo"] + INSET, cy, perm_lines, fill=perm_fill))
    if r.get("acesso"):
        acc_fill = k.T[r["acesso_tone"]] if r.get("acesso_tone") else k.T["text"]
        out.append(k.text(CX + col["Acesso"] + INSET, cy + 5, r["acesso"], 14,
                          "bold" if r.get("acesso_tone") == "error" else "normal", acc_fill))
    else:
        out.append(k.text(CX + col["Acesso"] + INSET, cy + 5, "—", 14, "normal", k.T["textMuted"]))
    out.append(k.badge(CX + col["Estado"] + INSET, cy - 11, r["estado"], r["estado_tone"]))
    bw = k.button_w(r["action"])
    out.append(k.button(CX + col["Ação"] + INSET, cy - 16, bw, r["action"], variant=r["variant"], h=32))
    out.append(k.rect(CX, y + ROW_H - 1, CW, 1, fill=k.T["border"]))
    return "".join(out)


def table(groups, start_y=316):
    """groups: [(title, [row dicts])]. Numbering runs across groups (spec 6.3 'Nº')."""
    out = [table_header(284)]
    y, n = start_y, 0
    for title, rows in groups:
        out.append(group_header(y, title, len(rows)))
        y += GROUP_H
        for r in rows:
            n += 1
            out.append(table_row(y, n, r))
            y += ROW_H
    return "".join(out)


def concessoes_page(active_filter, n_items, n_pending, groups, grouping="Agrupar por: Origem"):
    parts = [shell(2), header("Concessões", "Tudo o que plugins, skills e contas podem usar, com a sua decisão."),
             summary("2 aprovadas · 2 pendentes"),
             segmented_filter(CX, 236, 420, FILTERS, active_filter),
             k.text(CX + 840, 261, f"{n_items} itens · {n_pending} pendente{'s' if n_pending != 1 else ''}",
                    14, "normal", k.T["textMuted"], anchor="end"),
             k.select(1040, 236, 200, grouping, options=GROUPING),
             table(groups)]
    return "".join(parts)


def dialog(title, items, buttons):
    """Modal (spec 4): width 440, radius 14, title 18 bold, body blocks, buttons right aligned.
    items: ('p', text, size, weight, fill, gap_after) | ('cb', label, checked) | ('gap', px).
    buttons: [(label, variant, state)]. Returns (ops, height); ops are drawn by draw_dialog."""
    inner = DW - 48
    cur, ops = 66, []
    for it in items:
        if it[0] == "gap":
            cur += it[1]
        elif it[0] == "p":
            _, s, size, weight, fill, gap = it
            lh = round(size * 1.45)
            lines = k.wrap_px_lines(s, inner, size, weight)
            for i, ln in enumerate(lines):
                ops.append(("t", cur + size + i * lh, ln, size, weight, fill))
            cur += size + (len(lines) - 1) * lh + gap
        elif it[0] == "cb":
            ops.append(("cb", cur, it[1], it[2]))
            cur += 22 + 12
    top = cur + 16
    return ops, top + 40 + 24, top, title, buttons


def draw_dialog(x, y, spec):
    ops, h, top, title, buttons = spec
    out = [k.rect(x + 0.5, y + 0.5, DW - 1, h - 1, rx=14, fill=k.T["surface"], stroke=k.T["border"]),
           k.text(x + 24, y + 38, title, 18, "bold")]
    for op in ops:
        if op[0] == "t":
            _, by, ln, size, weight, fill = op
            out.append(k.text(x + 24, y + by, ln, size, weight, k.T[fill] if fill in k.T else fill))
        else:
            _, by, label, checked = op
            out.append(k.checkbox(x + 24, y + by, label, checked=checked))
    bx = x + DW - 24
    for label, variant, state in reversed(buttons):
        bw = k.button_w(label, primary=variant == "primary")
        bx -= bw
        out.append(k.button(bx, y + top, bw, label, variant=variant, state=state))
        bx -= 8
    return "".join(out)


def dialog_overlay(page_svg, spec):
    """Page dimmed by the scrim (op 0.6), dialog centred."""
    h = spec[1]
    x = (W - DW) / 2.0
    y = (H - h) / 2.0
    return page_svg + k.scrim(W, H, op=0.6) + draw_dialog(x, y, spec)


def write_and_render(name, svg_text):
    os.makedirs(OUT_DIR, exist_ok=True)
    svg_path = os.path.join(OUT_DIR, name + ".svg")
    png_path = os.path.join(OUT_DIR, name + ".png")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_text)
    print("wrote", svg_path)
    subprocess.run([PY, "-I", "-B", RENDER, svg_path, png_path, str(W), str(H)], check=True)
    return png_path


# ---------------------------------------------------------------- data (sample state: 2 aprovadas, 2 pendentes)

CAMERA_PENDING = dict(origem="Plugin", origem_tone="info", item=["gideon.camera 0.1.0"],
                      perm=["captura da câmera"], acesso=None, estado="Pendente", estado_tone="warn",
                      action="Revisar", variant="secondary")
LLM_APPROVED = dict(origem="Plugin", origem_tone="info", item=["gideon.llm_engine 0.2.0"],
                    perm=["rede do motor LLM, armazenamento de configurações"], acesso=None,
                    estado="Aprovada", estado_tone="ok", action="Revogar", variant="danger")
SKILL_ROW = dict(origem="Skill", origem_tone="muted", item=["lista_compras v1.0.0"],
                 perm=["Permissões ok"], perm_tone="success", acesso=None, estado="Testada",
                 estado_tone="muted", action="Ver em Skills", variant="secondary")
CASA_SERVICES_DANGER = dict(origem="Conexão", origem_tone="muted", item=["Casa · Home Assistant"],
                            perm=["Serviços perigosos (fechaduras, alarme, portões)"], acesso="destrutiva",
                            acesso_tone="error", estado="Aguardando consentimento", estado_tone="warn",
                            action="Consentir", variant="secondary", risk=True)
CASA_CALL = dict(origem="Conexão", origem_tone="muted", item=["Casa · Home Assistant"],
                 perm=["Chamar serviços (ligar, desligar, ajustar)"], acesso="escrita", acesso_tone=None,
                 estado="Concedido", estado_tone="ok", action="Revogar conta", variant="danger")
CASA_READ = dict(origem="Conexão", origem_tone="muted", item=["Casa · Home Assistant"],
                 perm=["Ler estados das entidades"], acesso="leitura", acesso_tone=None,
                 estado="Concedido", estado_tone="ok", action="Revogar conta", variant="danger")


def groups_todas():
    return [("Plugins", [CAMERA_PENDING, LLM_APPROVED]),
            ("Skills", [SKILL_ROW]),
            ("Conexões", [CASA_SERVICES_DANGER, CASA_CALL, CASA_READ])]


def groups_conexoes():
    return [("Conexões", [CASA_SERVICES_DANGER, CASA_CALL, CASA_READ])]


# ---------------------------------------------------------------- pages

def page_todas():
    return concessoes_page("Todas", 6, 2, groups_todas())


def page_conexoes():
    return concessoes_page("Conexões", 3, 1, groups_conexoes())


DIALOG_REVISAR = dialog(
    "Revisar permissões",
    [("p", "gideon.camera 0.1.0 · exemplo.dev", 14, "bold", "text", 6),
     ("p", "Estado do plugin: instalado (desativado)", 12, "normal", "textMuted", 14),
     ("p", "Permissões que este manifesto pede:", 14, "bold", "text", 8),
     ("p", "• captura da câmera", 14, "normal", "text", 2),
     ("p", "• observação de tela", 14, "normal", "text", 14),
     ("p", "Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto.",
      14, "normal", "textMuted", 14),
     ("cb", "Entendo que o publisher não foi autenticado", True)],
    [("Fechar", "secondary", "normal"), ("Aprovar estas permissões", "primary", "normal")])

DIALOG_REVOGAR = dialog(
    "Revogar acesso",
    [("p", "Revogar o acesso da conta Casa no servidor? Os segredos locais são apagados, todos os escopos "
           "concedidos são retirados e as ferramentas MCP precisam de nova confiança. Para usar a conta de "
           "novo, conecte e consinta outra vez.", 14, "normal", "text", 10),
     ("p", "Escopos que serão retirados: Ler estados das entidades, Chamar serviços (ligar, desligar, ajustar).",
      12, "normal", "textMuted", 4)],
    [("Cancelar", "secondary", "focus"), ("Revogar acesso", "danger", "normal")])


def build():
    k.set_theme(THEME)
    return {
        "c02-concessoes-todas": k.canvas(page_todas()),
        "c02-concessoes-conexoes": k.canvas(page_conexoes()),
        "c02-revisar-modal": k.canvas(dialog_overlay(page_todas(), DIALOG_REVISAR)),
        "c02-revogar-confirmacao": k.canvas(dialog_overlay(page_conexoes(), DIALOG_REVOGAR)),
    }


def main():
    for name, svg in build().items():
        write_and_render(name, svg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
