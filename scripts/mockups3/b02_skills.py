#!/usr/bin/env python3
"""Mockups v3 for Extensões > Skills (docs/ui-spec/20-extensoes.md, section 3), theme gideon-escuro.

Writes docs/ui-mockups-v3/b02-skills-minhas.svg, b02-skills-estados.svg, b02-skills-criar.svg,
b02-skills-importar-exportar.svg and b02-skills-execucoes.svg, each rendered to .png next to it:
  target/ui-venv/bin/python -I -B scripts/mockups3/b02_skills.py
Helpers that scripts/mockup_kit3.py does not have are defined here (the kit is not edited).
"""
import os
import subprocess
import sys
from xml.sax.saxutils import escape

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

SUBTITLE = "Procedimentos que combinam capacidades instaladas. Nada aqui concede permissão."
SUB_ITEMS = ["Plugins", "Skills", "Conexões", "Modelos LLM"]
SEGMENTS = ["Minhas", "Criar", "Importar/Exportar", "Execuções"]
MONO = "Noto Sans Mono"
MONO_W = 0.6  # advance width of Noto Sans Mono in em

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
    s = str(n)
    w = max(18, k.text_w(s, 11, "bold") + 10)
    return (k.rect(x, y, w, 18, rx=9, fill=k.T["error"])
            + k.text(x + w / 2, y + 13, s, 11, "bold", k.T["onAccent"], anchor="middle"))


def subtabs(active, n_err=0):
    out = k.subtabs(SUB_ITEMS, active)
    if n_err:
        lw = k.text_w(SUB_ITEMS[0], 14, "bold")
        out += count_err(18 + 18 + lw + 8, 69, n_err)
    return out


def num(v):
    return f"{round(float(v), 2):g}"


def mono(x, y, s, size=12, fill=None):
    """Monospace line. Leading spaces are placed by x (callers pass the indent) so SVG whitespace is not needed."""
    fill = fill or k.T["text"]
    return (f'<text x="{num(x)}" y="{num(y)}" font-family="{MONO}" font-size="{num(size)}" '
            f'font-weight="normal" fill="{fill}">{escape(s)}</text>')


def seg_line(x, y, parts, size=12):
    """Run of text pieces; each piece is (text, tone) with tone None for muted.
    Edge spaces are not drawn (SVG text drops them), they only advance the pen."""
    out, cx = [], x
    space = k.text_w(" ", size)
    for s, tone in parts:
        col = tone_col(tone) if tone else k.T["textMuted"]
        body = s.strip()
        cx += (len(s) - len(s.lstrip())) * space
        if body:
            out.append(k.text(cx, y, body, size, "normal", col))
        cx += k.text_w(body, size) + (len(s) - len(s.rstrip())) * space
    return "".join(out)


def shell(active_sub, state, tone, summary, badges, action=None, n_err=2, tab="Extensões"):
    return (k.topbar(tab, state=state, state_tone=tone)
            + subtabs(active_sub, n_err)
            + k.page_header("Skills", SUBTITLE, action=action)
            + k.summary_strip(summary, badges))


def segments(active):
    return k.segmented(140, 236, SEGMENTS, active)


def disclosure_bar(y=284):
    """'Entradas (JSON)' collapsed (3.4.7) with 'Como funciona' collapsed at right (1.5)."""
    x, w = 140, 1100
    out = [k.rect(x + 0.5, y + 0.5, w - 1, 39, rx=10, fill=k.T["surfaceVariant"], stroke=k.T["border"]),
           chevron(x + 22, y + 20, down=False, color=k.T["textMuted"]),
           k.text(x + 36, y + 25, "Entradas (JSON)", 14, "bold", k.T["text"]),
           k.text(x + w - 40, y + 25, "Como funciona", 13, "bold", k.T["accent"], anchor="end"),
           chevron(x + w - 22, y + 20, down=True)]
    return "".join(out)


# ---------------------------------------------------------------- skill card (3.4.3)

CARD_W, CARD_H = 1100, 176


def skill_card(y, c):
    x = 140
    out = [k.card(x, y, CARD_W, CARD_H)]
    # L1: "<nome> · <id> v<versão>", optional 'Ativa' badge, state badge at right.
    title = f"{c['nome']} · {c['id']} v{c['versao']}"
    out.append(k.text(x + 20, y + 38, title, 17, "bold", k.T["text"]))
    right = x + CARD_W - 20
    sb = c["state"]
    right -= k.badge_w(sb[0])
    out.append(k.badge(right, y + 18, sb[0], sb[1]))
    if c.get("active"):
        right -= 8 + k.badge_w("Ativa")
        out.append(k.badge(right, y + 18, "Ativa", "info"))
    # L2: origin (+ active version).
    origem = c["origem"] + (" · versão ativa" if c.get("active") else "")
    out.append(k.text(x + 20, y + 60, "origem: " + origem, 12, "normal", k.T["textMuted"]))
    # L3: dependencies and permissions, colour + word.
    out.append(seg_line(x + 20, y + 82, [
        ("Dependências: ok", "ok") if c["deps_ok"] else ("Dependências: faltando: " + c["missing"], "warn"),
        ("   ·   ", None),
        ("permissões aprovadas", "ok") if c["perms_ok"] else ("permissões pendentes", "warn"),
    ]))
    # L4: permissions panel link (closed).
    out.append(chevron(x + 20 + k.text_w("Permissões", 13) + 12, y + 99, down=True))
    out.append(k.text(x + 20, y + 104, "Permissões", 13, "normal", k.T["accent"]))
    # Actions, table order from 3.4.5; primary action first in its group.
    bx = x + 20
    for label, variant in c["actions"]:
        bw = k.button_w(label, primary=variant == "primary")
        out.append(k.button(bx, y + 116, bw, label, variant=variant))
        bx += bw + 8
    if c.get("remove", True):
        bw = k.button_w("Remover")
        out.append(k.button(x + CARD_W - 20 - bw, y + 116, bw, "Remover", variant="danger"))
    return "".join(out)


SKILLS = {
    "habilitada": dict(nome="Resumir pasta", id="resumir_pasta", versao="0.2.0", state=("Habilitada", "ok"),
                       active=True, origem="criada", deps_ok=True, perms_ok=True,
                       actions=[("Desabilitar", "secondary"), ("Executar", "primary"),
                                ("Exportar", "secondary")]),
    "aprovada": dict(nome="Relatório semanal", id="relatorio_semanal", versao="1.1.0",
                     state=("Aprovada", "info"), origem="importada (publisher não verificado)",
                     deps_ok=True, perms_ok=True,
                     actions=[("Simular", "secondary"), ("Habilitar", "primary"), ("Exportar", "secondary")]),
    "testada": dict(nome="Comparar notas", id="comparar_notas", versao="0.1.0", state=("Testada", "info"),
                    origem="criada", deps_ok=True, perms_ok=False,
                    actions=[("Simular", "secondary"), ("Aprovar", "primary")]),
}


# ---------------------------------------------------------------- screens

def build_minhas():
    parts = [shell("Skills", "Em espera", "ok", "5 instaladas · 1 habilitada · 2 rascunhos", [],
                   action="Nova skill"),
             segments("Minhas"),
             disclosure_bar(),
             skill_card(340, SKILLS["habilitada"]),
             skill_card(532, SKILLS["aprovada"]),
             skill_card(724, SKILLS["testada"]),
             # The list scrolls: the third card is cut at the content bottom (y 880), as the spec's wireframe does.
             k.rect(0, 880, W, H - 880, fill=k.T["bg"]),
             k.rect(1246, 340, 4, 540, rx=2, fill=k.T["surfaceVariant"]),
             k.rect(1246, 340, 4, 250, rx=2, fill=k.T["textMuted"], fo=0.7)]
    return k.canvas("".join(parts))


def build_estados():
    x, w = 140, 1100
    rows = [
        ("Rascunho", "muted", "importada (publisher não verificado)", ["Simular", "Remover", "Reverter versão"]),
        ("Validada", "info", "criada; salva em Criar, ainda não simulada", ["Simular", "Remover"]),
        ("Testada", "info", "simulada sem erro; falta aprovar", ["Aprovar", "Simular", "Remover"]),
        ("Aprovada", "info", "aprovada; ainda não habilitada", ["Habilitar", "Exportar", "Simular", "Remover"]),
        ("Habilitada", "ok", "pode executar; passos que mudam estado pedem decisão", ["Executar", "Desabilitar",
                                                                                     "Exportar"]),
        ("Desabilitada", "muted", "não executa; pode voltar a ser habilitada", ["Habilitar", "Exportar"]),
        ("Revisada", "warn", "nova versão aprovada; aprovar pede nova simulação",
         ["Simular", "Remover"]),
    ]
    y0 = 284
    row_h = 52
    card_h = 52 + 36 + len(rows) * row_h + 12
    out = [k.card(x, y0, w, card_h)]
    out.append(k.text(x + 20, y0 + 34, "Estados de skill e ações visíveis", 17, "bold", k.T["text"]))
    hy = y0 + 52
    out.append(k.table_header(x + 1, hy, w - 2, [(20, "Estado"), (190, "Situação"), (560, "Ações visíveis")]))
    ry = hy + 36
    for label, tone, sit, acts in rows:
        out.append(k.badge(x + 20, ry + 15, label, tone))
        out.append(k.text(x + 190, ry + 31, sit, 13, "normal", k.T["text"]))
        bx = x + 560
        for i, a in enumerate(acts):
            variant = "primary" if i == 0 and label in ("Habilitada", "Testada", "Aprovada") else "secondary"
            bw = k.button_w(a, primary=variant == "primary")
            out.append(k.button(bx, ry + 6, bw, a, variant=variant))
            bx += bw + 8
        out.append(k.rect(x + 1, ry + row_h - 1, w - 2, 1, fill=k.T["border"]))
        ry += row_h
    # Two warning bands from 3.4.8, under the card.
    for i, msg in enumerate([
            "Escalada de permissões: esta versão pede mais que a anterior; aprove de novo antes de usar.",
            "Dependências faltando: arquivos.gravar"]):
        by = y0 + card_h + 16 + i * 44
        out.append(k.rect(x + 0.5, by + 0.5, w - 1, 36, rx=10, fill=k.T["warning"], fo=0.12,
                          stroke=k.T["warning"], so=0.5))
        out.append(k.rect(x, by + 6, 3, 24, rx=1.5, fill=k.T["warning"]))
        out.append(k.text(x + 20, by + 23, msg, 13, "normal", k.T["text"]))
    parts = [shell("Skills", "Em espera", "ok", "5 instaladas · 1 habilitada · 2 rascunhos", [],
                   action="Nova skill"),
             segments("Minhas")] + out
    return k.canvas("".join(parts))


MANIFEST = [
    ("{", 0, None),
    ('"schema_version": 1,', 2, None),
    ('"id": "resumir_pasta",', 2, None),
    ('"version": "0.2.0",', 2, None),
    ('"owner": "eu",', 2, "err"),
    ('"dependencies": ["arquivos.listar", "arquivos.gravar"],', 2, None),
    ('"steps": [', 2, None),
    ('{"id": "listar", "call": "arquivos.listar", "input": {"p": "${input.pasta}"}},', 4, None),
    ('{"id": "gravar", "call": "arquivos.apagar", "grant": true,', 4, "err"),
    ('"input": {"t": "${steps.listar}"}}', 6, "err"),
    ("]", 2, None),
    ("}", 0, None),
]

FINDINGS = [
    ("Campo desconhecido no manifest", "owner"),
    ("Passo chama capability fora das dependências declaradas", "steps[1].call"),
    ("Campo de permissão não é permitido dentro de passos", "steps[1].grant"),
    ("Template inválido: use só ${input.x} ou ${steps.id.campo}", "steps[1].input.t"),
]


def build_criar():
    x = 140
    right_x, right_w = 791, 449
    out = [k.text(x, 300, "Manifesto da skill em JSON", 14, "bold", k.T["text"]),
           k.rect(x + 0.5, 308.5, 634, 380, rx=k.RADIUS, fill=k.T["surfaceVariant"], stroke=k.T["border"])]
    base_x, lh, ty = x + 16, 19, 332
    cw = 12 * MONO_W
    for i, (s, indent, mark) in enumerate(MANIFEST):
        yy = ty + i * lh
        if mark:
            out.append(k.rect(x + 4, yy - 14, 626, lh, fill=k.T["error"], fo=0.10))
            out.append(k.rect(x + 4, yy - 14, 3, lh, fill=k.T["error"]))
        out.append(mono(base_x + indent * cw, yy, s, 12, k.T["text"]))
    # Validation result (3.5.2 region y 752).
    out.append(k.badge(x, 754, f"{len(FINDINGS)} achados", "err"))
    out.append(k.text(x + k.badge_w(f"{len(FINDINGS)} achados") + 12, 770, "Manifesto inválido; nada foi gravado.", 13,
                      "normal", k.T["textMuted"]))
    for i, (msg, campo) in enumerate(FINDINGS):
        out.append(k.text(x, 796 + i * 20, f"Achado: {msg} ({campo})", 13, "normal", k.T["error"]))
    # Buttons row (y 700).
    vw = k.button_w("Validar")
    out.append(k.button(x, 700, vw, "Validar", variant="secondary"))
    sw_ = k.button_w("Salvar rascunho", primary=True)
    out.append(k.button(x + vw + 12, 700, sw_, "Salvar rascunho", variant="primary", state="disabled"))
    out.append(k.text(x + vw + 12 + sw_ + 16, 725, "Corrija os achados antes de salvar.", 12, "normal",
                      k.T["error"]))
    # Gerar com LLM panel (3.5.4).
    py = 284
    out.append(k.card(right_x, py, right_w, 300, "Gerar com LLM"))
    px = right_x + 20
    pw = right_w - 40
    out.append(k.text(px, py + 58, "Descreva o que a skill deve fazer (até 1024 bytes).", 13, "normal",
                      k.T["textMuted"]))
    out.append(k.field(px, py + 70, pw, "Descrição da skill para o LLM",
                       "Lê uma pasta e grava um resumo dos arquivos."))
    gw = k.button_w("Gerar com LLM", primary=True)
    out.append(k.button(px, py + 146, gw, "Gerar com LLM", variant="primary"))
    out.append(k.wrap_px(px, py + 214, "O rascunho nunca fica habilitado. Você valida, simula e aprova antes de usar.",
                         pw, 13, "normal", k.T["textMuted"], line_h=18))
    # Draft output (3.5.5).
    dy = 600
    out.append(k.card(right_x, dy, right_w, 280))
    out.append(k.wrap_px(px, dy + 34, "Rascunho resumo_pasta · v0.1.0 · Rascunho · nada foi habilitado", pw, 14,
                         "bold", k.T["text"], line_h=20))
    out.append(k.wrap_px(px, dy + 80, "Requisitos: leitura de pasta; gravação em Documentos/Rascunhos", pw, 13,
                         "normal", k.T["text"], line_h=18))
    out.append(k.text(px, dy + 118, "Ambiguidades: formato do resumo não definido", 13, "normal", k.T["text"]))
    out.append(k.text(px, dy + 146, "Passos previstos:", 13, "bold", k.T["text"]))
    out.append(k.text(px + 12, dy + 166, "listar → arquivos.listar", 13, "normal", k.T["text"]))
    out.append(k.text(px + 12, dy + 184, "gravar → arquivos.gravar", 13, "normal", k.T["text"]))
    ow = k.button_w("Abrir no editor")
    out.append(k.button(px, dy + 216, ow, "Abrir no editor", variant="secondary"))
    parts = [shell("Skills", "Em espera", "ok", "5 instaladas · 1 habilitada · 2 rascunhos", [],
                   action="Nova skill"),
             segments("Criar")] + out
    return k.canvas("".join(parts))


def build_importar():
    x = 140
    out = []
    # Import panel (3.6.2), left.
    py = 284
    out.append(k.card(x, py, 542, 300, "Importar pacote"))
    ix, iw = x + 20, 502
    out.append(k.wrap_px(ix, py + 58, "Coloque o arquivo .gskill na pasta de importação e informe o nome, "
                         "sem caminho e sem extensão.", iw, 13, "normal", k.T["textMuted"], line_h=19))
    out.append(seg_line(ix, py + 112, [("Pasta: ", None), ("/home/lucas/.gideon/skill-imports", "info")], 13))
    out.append(k.field(ix, py + 124, iw, "Nome do pacote, sem caminho", "resumo_semanal"))
    bw = k.button_w("Pré-visualizar", primary=True)
    out.append(k.button(ix, py + 204, bw, "Pré-visualizar", variant="primary"))
    # Export panel, right.
    rx = 698
    out.append(k.card(rx, py, 542, 300, "Exportar skill"))
    rows = [("resumir_pasta v0.2.0", "Habilitada", "ok"),
            ("relatorio_semanal v1.1.0", "Aprovada", "info"),
            ("agenda_semanal v0.3.0", "Desabilitada", "muted")]
    ry = py + 44
    for name, st, tone in rows:
        out.append(k.text(rx + 20, ry + 24, name, 14, "bold", k.T["text"]))
        out.append(k.text(rx + 20, ry + 42, st, 12, "bold", tone_col(tone)))
        ew = k.button_w("Exportar")
        out.append(k.button(rx + 542 - 20 - ew, ry + 8, ew, "Exportar", variant="secondary"))
        out.append(k.rect(rx + 1, ry + 55, 540, 1, fill=k.T["border"]))
        ry += 56
    out.append(k.text(rx + 20, py + 240, "Pacote exportado; publisher não verificado", 13, "bold",
                      k.T["success"]))
    out.append(k.text(rx + 20, py + 262, "Arquivo: /home/lucas/.gideon/skill-exports/resumir_pasta-0.2.0.gskill",
                      12, "normal", k.T["textMuted"]))
    # Preview (3.6.4), bottom.
    qy = 600
    out.append(k.card(x, qy, 1100, 280, "Pacote resumo_semanal: resumir_pasta v0.2.0"))
    lx, lw = x + 20, 500
    out.append(k.text(lx, qy + 62, "Publisher: dev-local", 14, "normal", k.T["text"]))
    out.append(seal(lx + k.text_w("Publisher: dev-local", 14) + 10, qy + 48))
    out.append(k.wrap_px(lx, qy + 88, "Importar instala como rascunho e nunca concede permissões. "
                         "Valide, simule e aprove antes de usar.", lw, 13, "normal", k.T["textMuted"], line_h=18))
    out.append(k.text(lx, qy + 140, "Permissões exigidas: armazenamento de configurações", 13, "normal",
                      k.T["text"]))
    out.append(k.text(lx, qy + 162, "Novas nesta versão: rede do motor LLM", 13, "bold", k.T["warning"]))
    out.append(k.wrap_px(lx, qy + 186, "Escalada de permissões: esta versão pede mais que a anterior; "
                         "aprove de novo antes de usar.", lw, 13, "normal", k.T["warning"], line_h=18))
    cx = x + 560
    out.append(k.text(cx, qy + 62, "Achados", 14, "bold", k.T["text"]))
    out.append(k.badge(cx + k.text_w("Achados", 14, "bold") + 12, qy + 46, "1 achado", "err"))
    out.append(k.wrap_px(cx, qy + 92, "Achado: Manifest tenta enviar dados para fora: caminho, URL, shell ou "
                         "segredo (steps[2].call)", 520, 13, "normal", k.T["error"], line_h=18))
    iw_ = k.button_w("Instalar como rascunho", primary=True)
    out.append(k.button(cx, qy + 186, iw_, "Instalar como rascunho", variant="primary", state="disabled"))
    out.append(k.text(cx, qy + 246, "Corrija os achados antes de instalar.", 12, "normal", k.T["error"]))
    parts = [shell("Skills", "Em espera", "ok", "5 instaladas · 1 habilitada · 2 rascunhos", [],
                   action="Nova skill"),
             segments("Importar/Exportar")] + out
    return k.canvas("".join(parts))


def build_execucoes():
    x = 140
    out = []
    cy = 284
    out.append(k.card(x, cy, 1100, 340))
    # Title with the state word in warning colour (3.7.3 #1).
    tx = x + 20
    base = cy + 34
    sp = k.text_w(" ", 17, "bold")
    head = "Execução run-0042 · resumir_pasta ·"
    out.append(k.text(tx, base, head, 17, "bold", k.T["text"]))
    tx2 = tx + k.text_w(head, 17, "bold") + sp
    state_word = "aguardando sua decisão"
    out.append(k.text(tx2, base, state_word, 17, "bold", k.T["warning"]))
    tx3 = tx2 + k.text_w(state_word, 17, "bold") + sp
    out.append(k.text(tx3, base, "· passo gravar", 17, "bold", k.T["text"]))
    # Steps (3.7.3 #2).
    sy = cy + 66
    out.append(k.text(x + 20, sy, "Passo listar", 14, "normal", k.T["text"]))
    out.append(k.badge(x + 20 + k.text_w("Passo listar", 14) + 12, sy - 15, "concluído", "ok"))
    sy2 = cy + 98
    out.append(k.text(x + 20, sy2, "Passo gravar", 14, "normal", k.T["text"]))
    out.append(k.badge(x + 20 + k.text_w("Passo gravar", 14) + 12, sy2 - 15, "aguardando sua decisão", "warn"))
    # Decision block for the step that changes state (3.7.4).
    bx, by, bw_ = x + 20, cy + 112, 1060
    out.append(k.rect(bx + 0.5, by + 0.5, bw_ - 1, 124, rx=k.RADIUS, fill=k.T["surfaceVariant"],
                      stroke=k.T["border"]))
    out.append(k.text(bx + 16, by + 26, "Alvo: arquivos.gravar", 13, "normal", k.T["text"]))
    out.append(k.text(bx + 16, by + 48, "Efeito: grava resumo.md em Documentos/Rascunhos", 13, "normal",
                      k.T["text"]))
    out.append(seg_line(bx + 16, by + 70, [("Risco: ", None), ("escrita (pede aprovação)", "warn")], 13))
    aw = k.button_w("Autorizar passo", primary=True)
    nw = k.button_w("Negar passo")
    ay = by + 78
    out.append(k.button(bx + bw_ - 16 - aw, ay, aw, "Autorizar passo", variant="primary"))
    out.append(k.button(bx + bw_ - 16 - aw - 8 - nw, ay, nw, "Negar passo", variant="secondary"))
    out.append(k.text(x + 20, cy + 262, "Passo resumir", 14, "normal", k.T["text"]))
    out.append(k.badge(x + 20 + k.text_w("Passo resumir", 14) + 12, cy + 247, "pendente", "muted"))
    # Cancel (3.7.3 #5, confirmation 8.7 not shown).
    cw = k.button_w("Cancelar execução")
    out.append(k.button(x + 1100 - 20 - cw, cy + 288, cw, "Cancelar execução", variant="danger"))
    # History (3.7.3 #7-9).
    hy = 644
    out.append(k.card(x, hy, 1100, 236, "Histórico de execuções"))
    hist = [
        ("run-0041 · resumir_pasta v0.2.0 · passo resumir", 'Saídas: {"arquivos": 3}', "concluída", "ok"),
        ("run-0040 · relatorio_semanal v1.1.0 · passo gravar",
         "Execução revertida: os passos concluídos foram desfeitos", "revertida", "warn"),
        ("run-0039 · resumir_pasta v0.2.0 · passo listar",
         "Dependência ausente: execução bloqueada antes de qualquer passo", "falhou", "err"),
    ]
    ry = hy + 52
    for i, (line1, line2, st, tone) in enumerate(hist):
        out.append(k.text(x + 20, ry + 18, line1, 14, "normal", k.T["text"]))
        out.append(k.text(x + 20, ry + 36, line2, 12, "normal",
                          k.T["textMuted"] if tone == "ok" else tone_col(tone)))
        out.append(k.badge(x + 1100 - 20 - k.badge_w(st), ry + 10, st, tone))
        if i < len(hist) - 1:
            out.append(k.rect(x + 20, ry + 44, 1060, 1, fill=k.T["border"]))
        ry += 44
    parts = [shell("Skills", "Executando", "info", "5 instaladas · 1 habilitada · 2 rascunhos", [],
                   action="Nova skill"),
             segments("Execuções")] + out
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
    write_and_render("b02-skills-minhas", build_minhas())
    write_and_render("b02-skills-estados", build_estados())
    write_and_render("b02-skills-criar", build_criar())
    write_and_render("b02-skills-importar-exportar", build_importar())
    write_and_render("b02-skills-execucoes", build_execucoes())
    return 0


if __name__ == "__main__":
    sys.exit(main())
