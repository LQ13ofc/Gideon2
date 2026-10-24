#!/usr/bin/env python3
"""Mockups v3 for Extensões > Plugins (docs/ui-spec/20-extensoes.md, section 2), theme gideon-escuro.

Writes docs/ui-mockups-v3/b01-plugins-grade.svg, b01-plugins-vazio.svg and
b01-plugins-revisar-permissoes.svg, each rendered to .png next to it:
  target/ui-venv/bin/python -I -B scripts/mockups3/b01_plugins.py
Helpers that scripts/mockup_kit3.py does not have are defined here (the kit is not edited).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)

import mockup_kit3 as k  # noqa: E402

ROOT = os.path.dirname(SCRIPTS)
OUT_DIR = os.path.join(ROOT, "docs", "ui-mockups-v3")
PY = os.path.join(ROOT, "target", "ui-venv", "bin", "python")
RENDER = os.path.join(SCRIPTS, "render_svg.py")
W, H = k.CANVAS_W, k.CANVAS_H
THEME = "gideon-escuro"

SUBTITLE = "Instale e ative plugins verificados. Instalar não executa nada e não concede acesso."
SUB_ALL = ["Plugins", "Skills", "Conexões", "Modelos LLM"]
SUB_NO_LLM = ["Plugins", "Skills", "Conexões"]

CARD_W, CARD_H = 356, 176
GRID_Y = 340
ROW2_Y = GRID_Y + CARD_H + 16
COL1_X, COL2_X = 140, 512
DX, DY, DW, DH = 884, 340, 356, 540

TONE = {"ok": "success", "warn": "warning", "err": "error", "info": "info", "muted": "textMuted"}


def tone_col(tone):
    return k.T[TONE[tone]]


# ---------------------------------------------------------------- helpers local to this file

def chevron(cx, cy, down=True, color=None, sw=1.6):
    color = color or k.T["accent"]
    if down:
        d = f"M{cx - 4} {cy - 2} L{cx} {cy + 2} L{cx + 4} {cy - 2}"
    else:
        d = f"M{cx - 2} {cy - 4} L{cx + 2} {cy} L{cx - 2} {cy + 4}"
    return k.path(d, stroke=color, sw=sw)


def seal_w(label="não verificado"):
    return k.text_w(label, 12) + 16


def seal(x, y, label="não verificado"):
    """Discreet 18 px honesty seal (docs/ui-spec/20-extensoes.md 8.4)."""
    w = seal_w(label)
    return (k.rect(x + 0.5, y + 0.5, w - 1, 17, rx=8.5, fill=k.T["surface"], stroke=k.T["border"])
            + k.text(x + 8, y + 13, label, 12, "normal", k.T["textMuted"]))


def count_err(x, y, n):
    """Error-coloured counter for the sub-tab badge (Plugins: failed or quarantined)."""
    s = str(n)
    w = max(18, k.text_w(s, 11, "bold") + 10)
    return (k.rect(x, y, w, 18, rx=9, fill=k.T["error"])
            + k.text(x + w / 2, y + 13, s, 11, "bold", k.T["onAccent"], anchor="middle"))


def subtabs(items, active, n_err=0):
    out = k.subtabs(items, active)
    if n_err:
        lw = k.text_w(items[0], 14, "bold")
        out += count_err(18 + 18 + lw + 8, 69, n_err)
    return out


def menu_btn(x, y):
    """32 px overflow button with three dots (EX-PL-06)."""
    cx, cy = x + 16, y + 16
    return (k.rect(x + 0.5, y + 0.5, 31, 31, rx=8, fill=k.T["surfaceVariant"], stroke=k.T["border"])
            + "".join(k.circle(cx + d, cy, 1.8, fill=k.T["textMuted"]) for d in (-6, 0, 6)))


def close_x(x, y):
    """28 px close button for the detail panel (label: Fechar detalhe)."""
    cx, cy = x + 14, y + 14
    return (k.rect(x + 0.5, y + 0.5, 27, 27, rx=8, fill=k.T["surfaceVariant"], stroke=k.T["border"])
            + k.line(cx - 4, cy - 4, cx + 4, cy + 4, stroke=k.T["textMuted"], sw=1.6)
            + k.line(cx + 4, cy - 4, cx - 4, cy + 4, stroke=k.T["textMuted"], sw=1.6))


def banner(y=284):
    """Trust banner with 'Como funciona' collapsed (EX-PL-02, EX-PL-03; 2.4.1 text not shown)."""
    x, w = 140, 1100
    out = [k.rect(x + 0.5, y + 0.5, w - 1, 39, rx=10, fill=k.T["surfaceVariant"], stroke=k.T["border"]),
           k.text(x + 16, y + 25, "Pacotes verificados por checksum · sem rede · publisher não autenticado",
                  13, "normal", k.T["textMuted"])]
    right = x + w - 16
    out.append(k.text(right - 22, y + 25, "Como funciona", 13, "bold", k.T["accent"], anchor="end"))
    out.append(chevron(right - 8, y + 20, down=True))
    return "".join(out)


def filter_bar(counts, active):
    items = [f"Todos {counts[0]}", f"Instalados {counts[1]}", f"Disponíveis {counts[2]}",
             f"Quarentena {counts[3]}"]
    return k.segmented(140, 236, items, active)


def shell(items, n_err, state, tone, summary, badges):
    return (k.topbar("Extensões", state=state, state_tone=tone)
            + subtabs(items, "Plugins", n_err)
            + k.page_header("Plugins", SUBTITLE)
            + k.summary_strip(summary, badges))


# ---------------------------------------------------------------- plugin card (2.5)

def plugin_card(x, y, c, selected=False):
    border = k.T["error"] if c.get("err") else k.T["border"]
    out = [k.rect(x + 0.5, y + 0.5, CARD_W - 1, CARD_H - 1, rx=k.RADIUS, fill="url(#cardGrad)", stroke=border,
                  sw=1.5 if c.get("err") else 1)]
    if selected:
        out.append(k.rect(x + 1, y + 1, CARD_W - 2, CARD_H - 2, rx=k.RADIUS - 1, stroke=k.T["accent"], sw=2))
    # L1: plugin id (no friendly name in the snapshot yet) and state badge at right.
    out.append(k.text(x + 20, y + 38, c["name"], 17, "bold", k.T["text"]))
    out.append(k.badge(x + CARD_W - 20 - k.badge_w(c["badge"]), y + 18, c["badge"], c["badge_tone"]))
    # L2: version, publisher, honesty seal.
    out.append(k.text(x + 20, y + 60, c["meta"], 12, "normal", k.T["textMuted"]))
    out.append(seal(x + CARD_W - 20 - seal_w(), y + 46))
    # L3: permissions status (colour + word).
    ok = c["approved"]
    out.append(k.text(x + 20, y + 82, "Permissões aprovadas" if ok else "Permissões não aprovadas", 12, "normal",
                      k.T["success"] if ok else k.T["warning"]))
    # L4: only when the state needs it.
    if c.get("msg"):
        out.append(k.text(x + 20, y + 104, c["msg"], 12, "normal", tone_col(c["msg_tone"])))
    # L5: primary or secondary action and overflow menu.
    label, variant, state = c["btn"]
    bw = k.button_w(label, primary=variant == "primary")
    out.append(k.button(x + 20, y + 116, bw, label, variant=variant, state=state))
    out.append(menu_btn(x + CARD_W - 20 - 32, y + 120))
    return "".join(out)


# ---------------------------------------------------------------- detail panel (2.6)

def detail(d):
    x, y = DX, DY
    ix = x + 20
    muted, text = k.T["textMuted"], k.T["text"]
    out = [k.card(x, y, DW, DH)]
    out.append(k.text(ix, y + 38, d["name"], 17, "bold", text))
    out.append(k.badge(ix + k.text_w(d["name"], 17, "bold") + 10, y + 22, d["badge"], d["badge_tone"]))
    out.append(close_x(x + DW - 48, y + 16))
    out.append(k.text(ix, y + 62, d["meta"], 12, "normal", muted))
    cy = y + 92
    out.append(k.text(ix, cy, "Publisher: dev-local (não autenticado)", 13, "normal", text))
    cy += 22
    out.append(k.text(ix, cy, "Versão: 0.1.0", 13, "normal", text))
    cy += 22
    out.append(k.line(ix, cy + 6, x + DW - 20, cy + 6))
    cy += 30
    out.append(k.text(ix, cy, "Permissões aprovadas para este manifesto:", 13, "bold", text))
    cy += 22
    for lab in d["perms"]:
        out.append(k.circle(ix + 4, cy - 4, 2.5, fill=k.T["accent"]))
        out.append(k.text(ix + 16, cy, lab, 13, "normal", text))
        cy += 22
    cy += 6
    out.append(k.text(ix, cy, "Ver em Permissões", 13, "bold", k.T["accent"]))
    cy += 28
    out.append(k.line(ix, cy - 6, x + DW - 20, cy - 6))
    cy += 18
    label = "Estado técnico: "
    out.append(k.text(ix, cy, label, 13, "normal", text))
    out.append(k.text(ix + k.text_w(label, 13), cy, d["state_word"], 13, "bold", tone_col(d["state_tone"])))
    cy += 22
    out.append(k.text(ix, cy, "Último erro: " + d["last_error"], 13, "normal", k.T["error"]))
    cy += 34
    bw = iw = DW - 40
    out.append(k.button(ix, cy, iw, d["btn"][0], variant="primary", state=d["btn"][1]))
    return "".join(out)


# ---------------------------------------------------------------- catalogue data (fictitious, Portuguese labels)

LLM = dict(name="llm_engine", badge="Ativo", badge_tone="ok", meta="v0.4.2 · publisher dev-local",
           approved=True, btn=("Desativar", "secondary", "normal"))
SCREEN = dict(name="screen_observe", badge="Falhou", badge_tone="err", meta="v0.1.0 · publisher dev-local",
              approved=True, msg="Falhou: Plugin não pode ser executado", msg_tone="err",
              btn=("Ativar", "primary", "normal"), err=True)
MIC = dict(name="mic_advanced", badge="Quarentena", badge_tone="err", meta="v0.3.0 · publisher dev-local",
           approved=True, msg="Em quarentena: não pode ser ativado.", msg_tone="err",
           btn=("Ativar", "primary", "disabled"), err=True)
CAM = dict(name="camera_gesture", badge="Instalado", badge_tone="info", meta="v0.2.0 · publisher dev-local",
           approved=False, msg="Aprove novamente as permissões para ativar", msg_tone="warn",
           btn=("Revisar permissões", "secondary", "normal"))
AUDIO = dict(name="audio_advanced", badge="Disponível", badge_tone="muted", meta="v0.2.1 · publisher dev-local",
             approved=False, btn=("Revisar permissões", "secondary", "normal"))

SUMMARY_GRID = "Catálogo verificado · 4 instalados · 1 ativo · 1 em quarentena"
BADGES_GRID = [("4 instalados", "info"), ("1 ativo", "ok"), ("1 em quarentena", "err")]


# ---------------------------------------------------------------- screens

def build_grade():
    parts = [shell(SUB_ALL, n_err=2, state="Em espera", tone="ok", summary=SUMMARY_GRID, badges=BADGES_GRID),
             filter_bar([6, 4, 1, 1], "Instalados 4"),
             banner(),
             plugin_card(COL1_X, GRID_Y, LLM),
             plugin_card(COL2_X, GRID_Y, SCREEN, selected=True),
             plugin_card(COL1_X, ROW2_Y, MIC),
             plugin_card(COL2_X, ROW2_Y, CAM),
             detail(dict(name="screen_observe", badge="Falhou", badge_tone="err",
                         meta="v0.1.0 · publisher dev-local · não verificado",
                         perms=["observação de tela"], state_word="Falhou", state_tone="err",
                         last_error="Plugin não pode ser executado",
                         btn=("Ativar", "normal")))]
    return k.canvas("".join(parts))


def build_vazio():
    x, y, w, h = 140, 340, 1100, 240
    cx = x + w / 2
    title = "Catálogo não configurado"
    body = "Nenhum plugin no catálogo ainda. Conecte o Core para carregar o catálogo local."
    btn = "Atualizar catálogo"
    bw = k.button_w(btn, primary=True)
    content_h = 32 + 12 + 18 + 6 + 20 + 20 + 40
    top = y + (h - content_h) / 2
    box = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=14, fill=k.T["surfaceVariant"], fo=0.4,
                  stroke=k.T["outline"], so=0.6, dash="6 5"),
           k.icon("puzzle", cx - 16, top, 32, k.T["textMuted"]),
           k.text(cx, top + 32 + 12 + 14, title, 14, "bold", k.T["text"], anchor="middle"),
           k.text(cx, top + 32 + 12 + 18 + 6 + 14, body, 14, "normal", k.T["textMuted"], anchor="middle"),
           k.button(cx - bw / 2, top + content_h - 40, bw, btn, variant="primary")]
    parts = [shell(SUB_NO_LLM, n_err=0, state="Em espera", tone="ok", summary="Catálogo não configurado",
                   badges=[("0 instalados", "info"), ("0 ativos", "ok"), ("0 em quarentena", "muted")]),
             filter_bar([0, 0, 0, 0], "Todos 0"),
             banner()] + box
    return k.canvas("".join(parts))


def review_modal(x, y, w, h):
    text, muted = k.T["text"], k.T["textMuted"]
    head = "audio_advanced 0.2.1 · dev-local"
    out = [k.rect(x + 0.5, y + 0.5, w - 1, h - 1, rx=14, fill=k.T["surface"], stroke=k.T["border"]),
           k.text(x + 24, y + 38, "Revisar permissões", 18, "bold", text),
           k.text(x + 24, y + 68, head, 14, "normal", text),
           seal(x + 24 + k.text_w(head, 14) + 10, y + 54),
           k.text(x + 24, y + 96, "Permissões declaradas (não aprovadas):", 14, "normal", muted)]
    for i, lab in enumerate(["configuração do microfone", "rota de áudio", "armazenamento de configurações"]):
        yy = y + 122 + i * 24
        out.append(k.circle(x + 30, yy - 5, 2.5, fill=k.T["accent"]))
        out.append(k.text(x + 42, yy, lab, 14, "normal", text))
    out.append(k.wrap_px(x + 24, y + 204,
                         "Aprovar permissões não instala nem executa este plugin. "
                         "A aprovação vale somente para este manifesto.", w - 48, 13, "normal", muted, line_h=19))
    out.append(k.checkbox(x + 24, y + 244, "Entendo que o publisher não foi autenticado", checked=False))
    out.append(k.text(x + 52, y + 280, "Marque a confirmação para liberar a aprovação.", 12, "normal", muted))
    by = y + h - 24 - 40
    approve = "Aprovar estas permissões"
    aw = k.button_w(approve, primary=True)
    bx = x + w - 24 - aw
    out.append(k.button(bx, by, aw, approve, variant="primary", state="disabled"))
    fw = k.button_w("Fechar")
    bx -= 8 + fw
    out.append(k.button(bx, by, fw, "Fechar", variant="secondary"))
    return "".join(out)


def build_revisar():
    parts = [shell(SUB_ALL, n_err=2, state="Em espera", tone="ok", summary=SUMMARY_GRID, badges=BADGES_GRID),
             filter_bar([6, 4, 1, 1], "Disponíveis 1"),
             banner(),
             plugin_card(COL1_X, GRID_Y, AUDIO),
             k.scrim(op=0.6)]
    mw, mh = 600, 400
    parts.append(review_modal((W - mw) / 2.0, (H - mh) / 2.0 - 10, mw, mh))
    return k.canvas("".join(parts))


# ---------------------------------------------------------------- output

def write_and_render(name, svg_text):
    os.makedirs(OUT_DIR, exist_ok=True)
    svg_path = os.path.join(OUT_DIR, name + ".svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_text)
    print("wrote", svg_path)
    if os.path.exists(PY):
        subprocess.run([PY, "-I", "-B", RENDER, svg_path], check=True)
    return svg_path


def main():
    k.set_theme(THEME)
    write_and_render("b01-plugins-grade", build_grade())
    write_and_render("b01-plugins-vazio", build_vazio())
    write_and_render("b01-plugins-revisar-permissoes", build_revisar())
    return 0


if __name__ == "__main__":
    sys.exit(main())
