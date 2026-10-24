#!/usr/bin/env python3
"""Mockups b03: Extensoes > Conexoes (segments Contas, Rotas, Nova conta).

Spec: docs/ui-spec/20-extensoes.md section 4 (4.4 Contas, 4.5 Rotas, 4.6 Nova conta) and 00-casca.md.
Writes docs/ui-mockups-v3/b03-conexoes-contas, -rotas, -nova-conta (.svg and .png), theme gideon-escuro.
  target/ui-venv/bin/python -I -B scripts/mockups3/b03_conexoes.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ext_common as c  # noqa: E402
import mockup_kit3 as k  # noqa: E402

SUB = "Conexões"
TITLE = "Conexões"
SUBTITLE = "Contas de serviços pela API. Você concede cada escopo; escrita pede aprovação."
SEGMENTS = ["Contas", "Rotas", "Nova conta"]
SUMMARY = "4 contas · 1 conectada · 2 pendentes"
SUMMARY_BADGES = [("2 pendentes", "warn")]
ACTION = "Nova conta"


def frame(seg):
    return c.frame(SUB, TITLE, SUBTITLE, SEGMENTS, seg, action=ACTION,
                   summary_text=SUMMARY, summary_badges=SUMMARY_BADGES)


def muted():
    return k.T["textMuted"]


def text_c():
    return k.T["text"]


# ---------------------------------------------------------------- Contas (4.4)

FAKE_FULL = "SERVIDOR FALSO — sem credenciais reais"

ACCOUNTS = [
    dict(title="Acesso GitHub · GitHub", badge="Conectado", tone="ok",
         estado="Estado: conectada", conta="conta-teste-github",
         granted=["Ler repositórios (repo:read)", "Criar issues (issues:write)"],
         buttons=[("Conectar", "primary", "disabled")],
         reason="Indisponível: a conta já está conectada."),
    dict(title="Agenda Google · Google", badge="Reautenticar", tone="warn",
         estado="Estado: reautenticação necessária", conta="conta-teste-google",
         granted=["Ler agenda (calendar.read)"],
         buttons=[("Conectar", "primary", "normal")]),
    dict(title="Casa · Home Assistant", badge="Conectando", tone="info",
         estado="Estado: conectando (aguardando confirmação)", conta=None,
         granted=["Ler estados (estados.read)"],
         token=True,
         buttons=[("Enviar token", "primary", "normal")]),
    dict(title="Servidor local · MCP", badge="Desconectado", tone="muted",
         estado="Estado: desconectada", conta=None, granted=[],
         buttons=[("Conectar", "primary", "normal")]),
]


def account_card(x, y, w, a):
    """Account card anatomy (4.4.3): name + provider, status badge, fake seal, state, account,
    granted scopes as chips, optional token field, action row with the advanced menu. Returns (svg, h)."""
    tx = x + 20
    parts = []
    title_w = k.text_w(a["title"], 17, "bold")
    parts.append(k.text(tx, y + 34, a["title"], 17, "bold", text_c()))
    seal, _ = c.tag(tx + title_w + 10, y + 19, "SERVIDOR FALSO")
    parts.append(seal)
    bw = k.badge_w(a["badge"])
    parts.append(k.badge(x + w - 20 - bw, y + 17, a["badge"], a["tone"]))
    parts.append(k.text(tx, y + 56, FAKE_FULL, 12, "normal", muted()))

    cy = 80
    parts.append(k.text(tx, y + cy, a["estado"], 14, "normal", text_c()))
    if a["conta"]:
        cy += 22
        parts.append(k.text(tx, y + cy, "Conta no serviço: " + a["conta"], 14, "normal", text_c()))

    lab = cy + 24
    if a["granted"]:
        parts.append(k.text(tx, y + lab, "Escopos concedidos:", 13, "normal", muted()))
        chip_x = tx
        for lbl in a["granted"]:
            parts.append(k.chip(chip_x, y + lab + 8, lbl))
            chip_x += k.chip_w(lbl) + 8
        cy = lab + 38
    else:
        parts.append(k.text(tx, y + lab, "Escopos concedidos: nenhum", 13, "normal", muted()))
        cy = lab + 8

    if a.get("token"):
        ftop = cy + 12
        parts.append(k.field(tx, y + ftop, w - 40, "Token de longa duração do Home Assistant",
                             "•" * 20))
        cy = ftop + 62

    by = cy + 16
    bx = tx
    for lbl, var, state in a["buttons"]:
        bwid = k.button_w(lbl, primary=var == "primary")
        parts.append(k.button(bx, y + by, bwid, lbl, variant=var, state=state))
        bx += bwid + 8
    if a.get("reason"):
        parts.append(k.text(bx + 4, y + by + 25, a["reason"], 12, "normal", muted()))
    parts.append(c.menu_btn(x + w - 20 - 40, y + by))
    h = by + 40 + 20
    return "".join(parts), h


def placed_card(x, y, w, a):
    """Card background sized to its contents, then the account contents. Returns (svg, height)."""
    _, ih = account_card(x, y, w, a)  # dry run for the height
    inner, _ = account_card(x, y, w, a)
    return k.card(x, y, w, ih, None) + inner, ih


def build_contas():
    """2 x 2 grid (span 6, x 140 and 698). Row height = tallest card in the row (spec 4.4.1)."""
    top = 324
    xs = [c.CX, c.RX]
    row1 = ACCOUNTS[0:2]
    row2 = ACCOUNTS[2:4]
    parts = []
    row1_h = 0
    for i, a in enumerate(row1):
        svg, ih = placed_card(xs[i], top, c.HW, a)
        parts.append(svg)
        row1_h = max(row1_h, ih)
    row2_y = top + row1_h + 16
    for i, a in enumerate(row2):
        svg, _ = placed_card(xs[i], row2_y, c.HW, a)
        parts.append(svg)
    return "".join(parts)


def build_rotas():
    out = []
    intro = ("Rotas: o Gideon escolhe a API autorizada quando há conta conectada com escopo. "
             "Nunca troca de rota para contornar token expirado, reautenticação ou escopo negado.")
    out.append(k.wrap_px(c.CX, 302, intro, c.CW, 14, "normal", muted()))
    cols = [(0, "Situação"), (130, "Rota"), (330, "Estado"), (530, "Motivo")]

    def route_card(y, title, plan, rows, toggle=False, warn=None, peek=False):
        x, w = c.CX, c.CW
        parts = [k.text(x + 20, y + 34, title, 17, "bold", text_c())]
        pw = k.button_w("Planejar")
        parts.append(k.button(x + w - 20 - pw, y + 12, pw, "Planejar", variant="secondary"))
        parts.append(k.text(x + 20, y + 74, plan, 14, "normal", text_c()))
        if toggle:
            label = "Fallback visual: desligado (padrão)"
            parts.append(c.switch(x + w - 20 - c.switch_w(label), y + 62, label, on=False))
        ty = y + 104
        parts.append(k.table_header(x + 20, ty, w - 40, cols, h=30))
        ry = ty + 30
        for r in rows:
            parts.append(k.table_row(x + 20, ry, w - 40, [(cols[i][0], v) for i, v in enumerate(r)], h=40))
            ry += 40
        bottom = ry
        if warn:
            svg, bh = c.banner(x + 20, bottom + 18, w - 40, warn, "warn")
            parts.append(svg)
            bottom = bottom + 18 + bh
        h = bottom - y + 20
        return k.card(x, y, w, h, None) + "".join(parts), h

    def badge_cell(label, tn):
        return lambda ax, cy: k.badge(ax, cy - 11, label, tn)

    def state(s, tn):
        return dict(s=s, size=14, weight="normal", fill=c.tone(tn))

    warn = ("Atenção: o fallback visual dirige uma tela por cliques e digitação, é menos seguro que a API "
            "e só vale quando não há conta conectada. Nunca contorna token expirado, reautenticação ou "
            "escopo negado. A publicação ainda pede sua aprovação.")
    rows_a = [
        [badge_cell("Escolhida", "ok"), "API da conta", state("disponível", "ok"),
         "Conta GitHub conectada com escopo issues:write."],
        [badge_cell("Descartada", "muted"), "Visual (tela sintética)", state("fallback visual desligado", "muted"),
         "Não usado: a API da conta já atende esta finalidade."],
    ]
    rows_b = [
        [badge_cell("Descartada", "muted"), "API da conta", state("reautenticação necessária", "warn"),
         "Reautenticar a conta Google. Nunca troca de rota para contornar."],
        [badge_cell("Descartada", "muted"), "Visual (tela sintética)", state("fallback visual desligado", "muted"),
         "Fallback visual não é usado para listar eventos."],
    ]
    y = 320
    svg_a, ha = route_card(y, "Criar issue", "Criar issue · rota escolhida: API da conta", rows_a,
                           toggle=True, warn=warn)
    out.append(svg_a)
    y += ha + 16
    svg_b, hb = route_card(y, "Listar eventos", "Listar eventos · nenhuma rota disponível", rows_b)
    out.append(svg_b)
    return "".join(out)


def build_nova_conta():
    out = []
    y = 284
    # Left: form (spec 4.6.2)
    x, w, h = c.CX, c.HW, 320
    out.append(k.card(x, y, w, h, "Adicionar conta"))
    by = y + 52
    out.append(k.text(x + 20, by + 13, "Provedor", 13, "normal", muted()))
    out.append(k.select(x + 20, by + 22, w - 40, "GitHub"))
    out.append(k.field(x + 20, by + 74, w - 40, "Nome da conta (ex.: Casa)", "Acesso GitHub"))
    bw = k.button_w("Adicionar conta", primary=True)
    out.append(k.button(x + w - 20 - bw, y + h - 20 - 40, bw, "Adicionar conta", variant="primary"))

    # Right: steps (spec 4.6.4)
    x2 = c.RX
    out.append(k.card(x2, y, w, h, "Como conectar"))
    steps = [
        "Escolha o provedor e dê um nome à conta.",
        "Clique em Conectar. Para GitHub e Google, confirme o código no site do provedor.",
        "Marque só os escopos que você quer conceder e clique em Consentir escopos marcados.",
        "Escrita e ações públicas pedem aprovação a cada uso.",
    ]
    svg_steps, _ = c.numbered(x2 + 20, y + 52, w - 40, steps)
    out.append(svg_steps)

    # Consent step (4.4.6, step 3-5): user code and per-scope checkboxes, nothing pre-checked.
    cy = 620
    ch = 260
    out.append(k.card(c.CX, cy, c.CW, ch, "Consentimento · Acesso GitHub"))
    out.append(k.badge(c.CX + c.CW - 20 - k.badge_w("Conectando"), cy + 18, "Conectando", "info"))
    lx = c.CX + 20
    out.append(k.text(lx, cy + 62, "Estado: conectando (aguardando confirmação)", 14, "normal", text_c()))
    code_svg, code_h = c.code_box(lx, cy + 78, 480, "Código para confirmar no servidor:", "AB12-CD34")
    out.append(code_svg)
    out.append(k.wrap_px(lx, cy + 168, "Confirme o código no site do GitHub. O Gideon não confirma "
                         "por conta própria e não abre o site.", 480, 13, "normal", muted()))

    rx = c.CX + 560
    out.append(k.text(rx, cy + 62, "Escopos pedidos, aguardando seu consentimento:", 13, "normal", muted()))
    scopes = [("Ler repositórios (repo:read)", "leitura", "muted"),
              ("Criar issues (issues:write)", "escrita (pede aprovação)", "warn"),
              ("Ler perfil (user:read)", "leitura", "muted")]
    sy = cy + 86
    for label, risk, tn in scopes:
        out.append(k.checkbox(rx, sy, label, checked=False))
        rw = k.text_w(risk, 12)
        out.append(k.text(c.CX + c.CW - 20 - rw, sy + 14, risk, 12, "normal", c.tone(tn)))
        sy += 32
    by2 = cy + ch - 20 - 40
    cw = k.button_w("Consentir escopos marcados", primary=True)
    out.append(k.button(c.CX + 20, by2, cw, "Consentir escopos marcados", variant="primary", state="disabled"))
    out.append(k.text(c.CX + 20 + cw + 12, by2 + 25, "Marque ao menos um escopo para consentir.", 12,
                      "normal", muted()))
    return "".join(out)


def main():
    contas = frame("Contas") + build_contas()
    rotas = frame("Rotas") + build_rotas()
    nova = frame("Nova conta") + build_nova_conta()
    c.write("b03-conexoes-contas", contas)
    c.write("b03-conexoes-rotas", rotas)
    c.write("b03-conexoes-nova-conta", nova)
    return 0


if __name__ == "__main__":
    sys.exit(main())
