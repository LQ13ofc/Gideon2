#!/usr/bin/env python3
"""Mockups b04: Extensoes > Modelos LLM (segments Modelo atual, Catalogo, Personalizados,
Provedor e chaves, Fallback e hardware).

Spec: docs/ui-spec/20-extensoes.md section 5 (5.4 to 5.8) and F4, with 00-casca.md.
Mock data is fictional: "llama.cpp (local) · leve-3b" is the current local model; cloud rows use
"Exemplo ..." labels. Advanced items are shown (Mostrar opções avançadas on) so the detail
panels are visible.
Writes docs/ui-mockups-v3/b04-modelos-atual, -catalogo, -personalizados, -provedor-e-chaves,
-fallback-hardware (.svg and .png), theme gideon-escuro.
  target/ui-venv/bin/python -I -B scripts/mockups3/b04_modelos.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ext_common as c  # noqa: E402
import mockup_kit3 as k  # noqa: E402

SUB = "Modelos LLM"
TITLE = "Modelos LLM"
SUBTITLE = "Escolha, teste e configure o modelo do motor LLM instalado."
SEGMENTS = ["Modelo atual", "Catálogo", "Personalizados", "Provedor e chaves", "Fallback e hardware"]
ACTION = "Atualizar lista"
SUMMARY = "Modelo atual: llama.cpp (local) · leve-3b"
SUMMARY_BADGES = [("Disponível", "ok"), ("Local", "muted")]


def frame(seg):
    return c.frame(SUB, TITLE, SUBTITLE, SEGMENTS, seg, action=ACTION,
                   summary_text=SUMMARY, summary_badges=SUMMARY_BADGES)


def muted():
    return k.T["textMuted"]


def text_c():
    return k.T["text"]


def result_strip(x, y, w, msg, tn="ok"):
    """Result strip (32 px, text only): spec 5.3."""
    return (k.rect(x + 0.5, y + 0.5, w - 1, 31, rx=10, fill=k.T["surfaceVariant"], stroke=k.T["border"])
            + k.circle(x + 18, y + 16, 5, fill=c.tone(tn))
            + k.text(x + 32, y + 21, msg, 14, "bold", c.tone(tn)))


def btn(x, y, label, variant="secondary", state="normal"):
    """Button sized by its label. Returns (svg, width)."""
    w = k.button_w(label, primary=variant == "primary")
    return k.button(x, y, w, label, variant=variant, state=state), w


def button_row(x, y, items):
    """items: [(label, variant, state)]. Returns svg; buttons 8 px apart from x."""
    out, cx = [], x
    for label, variant, state in items:
        svg, w = btn(cx, y, label, variant, state)
        out.append(svg)
        cx += w + 8
    return "".join(out)


# ---------------------------------------------------------------- 5.4 Modelo atual

def build_atual():
    out = [result_strip(c.CX, 284, c.CW, "Modelo testado e marcado como bom.")]
    # Card "Configurado" (5.4.1): y 324, h 260, x 140, w 542
    x, y, w, h = c.CX, 324, c.HW, 260
    out.append(k.card(x, y, w, h, "Configurado"))
    tx = x + 20
    out.append(k.text(tx, y + 62, "Configurado: llama.cpp (local) · leve-3b", 14, "normal", text_c()))
    out.append(k.text(tx, y + 92, "Estado do modelo atual:", 14, "normal", text_c()))
    lbl_w = k.text_w("Estado do modelo atual:", 14)
    out.append(k.badge(tx + lbl_w + 8, y + 77, "Disponível", "ok"))
    out.append(k.text(tx, y + 120, "Último bom: llama.cpp (local) · leve-3b", 13, "normal", muted()))
    out.append(k.text(tx, y + 142, "Funciona offline", 13, "normal", muted()))
    out.append(button_row(tx, y + h - 20 - 40, [
        ("Testar", "secondary", "normal"),
        ("Voltar ao último bom", "secondary", "normal"),
        ("Usar outro modelo", "secondary", "normal"),
    ]))

    # Card "Detalhes do modelo atual" (5.4.4, Avançado): x 698, y 324, h 520
    x2, h2 = c.RX, 520
    out.append(k.card(x2, y, w, h2, "Detalhes do modelo atual"))
    lines = [
        ("Leve 3B · Local · llama.cpp (local) · leve-3b", "bold"),
        ("Certificação: Testado · selftest local · 2026-10-02", None),
        ("Licença: conforme o pacote do modelo", None),
        ("Quantização: Q4_K_M", None),
        ("Hash (SHA-256): 3f9a6c…e21b", None),
        ("Backend: llama.cpp", None),
        ("Recursos", "sub"),
        ("Recurso streaming: Suportado", None),
        ("Recurso uso de ferramenta: Suportado", None),
        ("Recurso vision: Não suportado", None),
        ("Recurso cancel: Suportado", None),
        ("Contexto: 8192 tokens", None),
        ("Custo: não informado", None),
        ("Latência: baixa · hardware mínimo: RAM 8 GB, GPU não exigida", None),
        ("Funciona offline", None),
    ]
    ly = y + 62
    for text, style in lines:
        if style == "bold":
            out.append(k.text(x2 + 20, ly, text, 14, "bold", text_c()))
        elif style == "sub":
            out.append(k.text(x2 + 20, ly, text, 13, "bold", muted()))
        else:
            out.append(k.text(x2 + 20, ly, text, 14, "normal", text_c()))
        ly += 26
    return "".join(out)


# ---------------------------------------------------------------- 5.5 Catalogo

CATALOG = [
    ("Modelo leve 3B", "Local", "Certificado", "ok"),
    ("Modelo médio 8B", "Local", "Testado", "info"),
    ("Modelo grande 14B", "Local", "Declarado", "muted"),
    ("Ollama local 7B", "Local", "Candidato", "warn"),
    ("Exemplo 8B", "Nuvem", "Declarado", "muted"),
    ("Exemplo 70B", "Nuvem", "Testado", "info"),
    ("Exemplo Mini", "Nuvem", "Candidato", "warn"),
    ("Exemplo Pro", "Nuvem", "Certificado", "ok"),
]
SELECTED = 4  # Exemplo 8B: cloud model without consent, so "Usar este modelo" shows its reason


def build_catalogo():
    out = [k.segmented(c.CX, 284, ["Todos", "Local", "Nuvem"], "Todos")]
    out.append(k.text(605, 308, "8 de 12", 13, "normal", muted()))
    # List (span 5, x 140, y 332, rows of 56)
    ly = 332
    for i, (label, kind, cert, tn) in enumerate(CATALOG):
        sel = i == SELECTED
        out.append(k.list_row(
            c.CX, ly, 449, label, kind,
            trailing=(lambda lbl, t: (lambda rx, cy: k.badge(rx - k.badge_w(lbl), cy - 11, lbl, t)))(cert, tn),
            h=56, selected=sel))
        ly += 56
    out.append(button_row(c.CX, 812, [("Carregar mais", "secondary", "normal")]))

    # Detail panel (span 7, x 605, y 332, w 635, h 520)
    x, y, w, h = 605, 332, 635, 520
    out.append(k.card(x, y, w, h, "Exemplo 8B"))
    bw = k.badge_w("Declarado")
    out.append(k.badge(x + w - 20 - bw, y + 17, "Declarado", "muted"))
    tx = x + 20
    rows = [
        ("Exemplo 8B · Nuvem · OpenRouter · exemplo-8b", "bold"),
        ("Certificação: Declarado · sem teste · sem data", None),
        ("Licença: conforme o provedor", None),
        ("Quantização: não se aplica (nuvem)", None),
        ("Backend: API do provedor", None),
        ("Recurso streaming: Suportado", None),
        ("Recurso uso de ferramenta: Desconhecido", None),
        ("Recurso vision: Não suportado", None),
        ("Recurso cancel: Suportado", None),
        ("Contexto: 128000 tokens", None),
        ("Custo (USD por milhão de tokens): entrada 0,10 · saída 0,30", None),
        ("Latência: média · hardware mínimo: não se aplica", None),
        ("Requer rede", None),
    ]
    ry = y + 60
    for text, style in rows:
        out.append(k.text(tx, ry, text, 14, "bold" if style else "normal", text_c()))
        ry += 22
    bsvg, bw2 = btn(tx, y + 380, "Usar este modelo", "primary", "disabled")
    out.append(bsvg)
    out.append(k.text(tx, y + 380 + 58, "Sem consentimento: permita o envio à nuvem em Provedor e chaves.",
                      12, "normal", muted()))
    out.append(c.banner(tx, y + 462, w - 40, "Mensagens serão enviadas ao provedor escolhido na nuvem.", "warn")[0])
    return "".join(out)


# ---------------------------------------------------------------- 5.6 Personalizados

def build_personalizados():
    x, y, w, h = c.CX, 284, c.HW, 596
    out = [k.card(x, y, w, h, "Adicionar modelo personalizado")]
    tx = x + 20
    fw = w - 40
    fy = y + 52
    out.append(k.text(tx, fy + 13, "Provedor do modelo personalizado", 13, "normal", muted()))
    out.append(k.select(tx, fy + 22, fw, "Ollama (local)"))
    fy += 74
    out.append(k.field(tx, fy, fw, "Identificador do modelo", "exemplo/modelo-8b"))
    fy += 74
    out.append(k.field(tx, fy, fw, "Porta do servidor local, de 1024 a 65535", "8080"))
    fy += 74
    out.append(k.field(tx, fy, fw, "URL https do modelo personalizado", "https://…", placeholder=True))
    fy += 86
    out.append(k.text(tx, fy, "Recursos declarados (não certificados)", 14, "bold", text_c()))
    fy += 16
    half = (fw - 12) / 2.0
    feats = [("Streaming", "Suportado"), ("Tool use", "Desconhecido"),
             ("Visão", "Não suportado"), ("Cancelamento", "Suportado")]
    for i, (lbl, val) in enumerate(feats):
        col, row = i % 2, i // 2
        fx = tx + col * (half + 12)
        ty = fy + row * 74
        out.append(k.text(fx, ty + 13, lbl, 13, "normal", muted()))
        out.append(k.select(fx, ty + 22, half, val))
    fy += 148
    out.append(k.text(tx, fy + 2, "Recursos declarados não são certificados; o selftest é que confirma.",
                      12, "normal", muted()))
    out.append(button_row(tx, y + h - 20 - 40, [("Salvar modelo personalizado", "primary", "normal")]))

    # Right: list of custom models (up to 16)
    x2 = c.RX
    out.append(k.card(x2, y, w, h, "Modelos personalizados"))
    out.append(k.text(x2 + w - 20, y + 34, "2 de 16", 13, "normal", muted(), anchor="end"))
    ly = y + 52
    rows = [("Ollama local · modelo-8b", "Local", "muted", True),
            ("Servidor próprio · exemplo-70b", "Nuvem", "muted", False)]
    for label, kind, tn, sel in rows:
        out.append(k.list_row(x2 + 1, ly, w - 2, label, kind,
                              trailing=(lambda lbl, t: (lambda rx, cy: k.badge(rx - k.badge_w(lbl), cy - 11, lbl, t)))(
                                  "Declarado", tn),
                              h=56, selected=sel))
        ly += 56
    out.append(button_row(x2 + 20, ly + 16, [("Remover", "danger", "normal")]))
    return "".join(out)


# ---------------------------------------------------------------- 5.7 Provedor e chaves

def build_provedor():
    y, h = 324, 430
    x, w = c.CX, c.HW
    out = [k.card(x, y, w, h, "Configuração")]
    tx = x + 20
    fw = w - 40
    fy = y + 52
    out.append(k.text(tx, fy + 13, "Provedor", 13, "normal", muted()))
    out.append(k.select(tx, fy + 22, fw, "OpenRouter"))
    fy += 74
    out.append(k.field(tx, fy, fw, "Modelo: letras, números e . _ : / - (até 128)", "exemplo/modelo-8b"))
    fy += 74
    # hidden key: never echoed back (5.7.4)
    out.append(k.field(tx, fy, fw, "Chave", "•" * 16))
    bw = k.badge_w("Chave configurada")
    out.append(k.badge(tx + fw - bw, fy - 2 + 0, "Chave configurada", "ok"))
    fy += 74
    out.append(button_row(tx, fy, [("Salvar chave", "primary", "normal"),
                                   ("Remover chave", "danger", "normal")]))
    out.append(k.text(tx, fy + 56, "A chave não volta a aparecer depois de enviada.", 12, "normal", muted()))

    x2 = c.RX
    out.append(k.card(x2, y, w, h, "Nuvem e salvar"))
    ty = y + 52
    out.append(k.checkbox(x2 + 20, ty, "Permitir envio de conversas ao provedor na nuvem", checked=False))
    out.append(c.banner(x2 + 20, ty + 34, w - 40, "Mensagens serão enviadas ao provedor escolhido na nuvem.",
                        "warn")[0])
    out.append(k.text(x2 + 20, ty + 120, "Consentimento salvo: não concedido", 14, "normal", text_c()))
    out.append(button_row(x2 + 20, ty + 146, [("Salvar configuração", "primary", "normal")]))

    out.append(k.collapsible(c.CX, 770, c.CW, "Como funciona",
                             "Motor opcional. Sem ele, voz, wake e comandos da Base continuam funcionando."))
    return "".join(out)


# ---------------------------------------------------------------- 5.8 Fallback e hardware

def build_fallback():
    y, h = 324, 500
    x, w = c.CX, c.HW
    out = [k.card(x, y, w, h, "Fallback (opcional)")]
    tx = x + 20
    out.append(k.text(tx, y + 62, "Atual: nenhum fallback configurado", 14, "normal", text_c()))
    rule = ("Usado só depois de erro recuperável do modelo principal (429, 5xx, rede ou tempo esgotado). "
            "Nunca em erro de chave ou permissão.")
    out.append(k.wrap_px(tx, y + 90, rule, w - 40, 13, "normal", muted()))
    out.append(k.text(tx, y + 156, "Escolha um modelo", 13, "normal", muted()))
    options = [("Leve 3B · Local", False), ("Exemplo 8B · Nuvem", True), ("Exemplo Mini · Nuvem", False)]
    for i, (lbl, sel) in enumerate(options):
        out.append(k.radio(tx, y + 172 + i * 30, lbl, selected=sel))
    out.append(c.banner(tx, y + 276, w - 40, "Mensagens poderão ir para a nuvem se o modelo principal falhar.",
                        "warn")[0])
    out.append(c.banner(tx, y + 326, w - 40,
                        "Para fallback na nuvem, marque o consentimento em Provedor e chaves.", "warn")[0])
    out.append(button_row(tx, y + 390, [("Usar como fallback", "secondary", "disabled"),
                                        ("Remover fallback", "secondary", "disabled")]))
    out.append(k.text(tx, y + 452, "Sem consentimento: marque o envio à nuvem em Provedor e chaves.", 12,
                      "normal", muted()))
    out.append(k.text(tx, y + 478, "O fallback ainda não respondeu nesta sessão.", 12, "normal", muted()))

    x2 = c.RX
    out.append(k.card(x2, y, w, h, "Hardware e plugin"))
    out.append(k.text(x2 + 20, y + 62, "CPU: 8 núcleos · RAM: 16 GB · GPU: desconhecida", 14, "normal", text_c()))
    out.append(k.text(x2 + 20, y + 90, "Plugin: llm_engine · em execução", 14, "normal", text_c()))
    out.append(k.text(x2 + 20, y + 142, "Apaga só os dados guardados pelo plugin. Não altera o Core.", 13,
                      "normal", muted()))
    out.append(button_row(x2 + 20, y + 160, [("Apagar dados do plugin", "danger", "normal")]))
    return "".join(out)


def main():
    c.write("b04-modelos-atual", frame("Modelo atual") + build_atual())
    c.write("b04-modelos-catalogo", frame("Catálogo") + build_catalogo())
    c.write("b04-modelos-personalizados", frame("Personalizados") + build_personalizados())
    c.write("b04-modelos-provedor-e-chaves", frame("Provedor e chaves") + build_provedor())
    c.write("b04-modelos-fallback-hardware", frame("Fallback e hardware") + build_fallback())
    return 0


if __name__ == "__main__":
    sys.exit(main())
