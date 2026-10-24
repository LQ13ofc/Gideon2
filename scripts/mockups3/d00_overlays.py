#!/usr/bin/env python3
"""d00: overlays on the new shell (docs/ui-spec/00-casca.md, 40 section 4 and APP_DESCRICAO 6).

  d00-busca.png    settings search for 'volume', over Configurações > Áudio
  d00-paleta.png   Ctrl+K command palette with the p: / s: / c: prefixes, over Configurações > Áudio

Writes docs/ui-mockups-v3/*.svg and .png.  python3 -B scripts/mockups3/d00_overlays.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg_common as c  # noqa: E402
import d02_audio  # noqa: E402

k = c.k


def busca():
    base = d02_audio.build()
    px, pw = 140, 1100
    py, ph = 112, 404
    parts = [base, c.scrim(0.6)]
    parts.append(k.rect(px + 0.5, py + 0.5, pw - 1, ph - 1, rx=14, fill=c.T("surface"), stroke=c.T("border")))
    # Search field with 'volume' typed and the Esc hint.
    parts.append(c.search_field(px + 20, py + 18, pw - 40, "volume", focus=True, h=44))
    parts.append(k.kbd(px + pw - 20 - k.kbd_w("Esc") - 10, py + 30, "Esc"))
    parts.append(c.note(px + 20, py + 90, "3 resultados para 'volume' em Configurações"))
    # Filter: only changed options.
    parts.append(k.checkbox(px + pw - 20 - 230, py + 78, "Somente modificados", checked=False))

    rows = [
        ("Volume da resposta", "Ganho da resposta por voz na saída virtual. 0% = mudo.",
         "Áudio › Volume da resposta", "Básico", None),
        ("Ganho salvo no Core", "Ganho salvo no Core: 80%. Aparece com Mostrar opções avançadas.",
         "Áudio › Ganho salvo no Core", "Avançado", "muted"),
        ("Como funciona", "O volume é aplicado ao áudio gerado pelo Gideon antes da saída virtual.",
         "Áudio › Como funciona", None, None),
    ]
    ry = py + 116
    for i, (title, snippet, crumb, tag, tone) in enumerate(rows):
        y = ry + i * 84
        selected = i == 0
        if selected:
            parts.append(k.rect(px + 12, y, pw - 24, 76, rx=10, fill=c.T("tint")))
            parts.append(c.modified(px + 12, y + 14, 48, None))
        parts.append(k.text(px + 32, y + 28, title, 15, "bold", c.T("text")))
        if tag:
            parts.append(k.badge(px + 32 + k.text_w(title, 15, "bold") + 12, y + 14, tag, tone or "muted"))
        parts.append(k.text(px + 32, y + 50, snippet, 13, "normal", c.T("text")))
        parts.append(k.text(px + 32, y + 68, crumb, 12, "normal", c.T("accent")))
        if selected:
            kw = k.kbd_w("Enter")
            parts.append(k.kbd(px + pw - 32 - kw, y + 26, "Enter"))
            parts.append(k.text(px + pw - 32 - kw - 10, y + 41, "abre a opção", 12, "normal", c.T("textMuted"),
                                anchor="end"))
    parts.append(c.note(px + 20, py + ph - 26, "Enter abre a opção em Áudio, com ela destacada. "
                                               "Esc fecha a busca."))
    return k.canvas("".join(parts))


def paleta():
    base = d02_audio.build()
    px, pw = 370, 640
    py, ph = 104, 628
    parts = [base, c.scrim(0.6)]
    parts.append(k.rect(px + 0.5, py + 0.5, pw - 1, ph - 1, rx=14, fill=c.T("surface"), stroke=c.T("border")))
    # Input: placeholder, focused.
    parts.append(c.search_field(px + 16, py + 16, pw - 32, "Buscar páginas, configurações ou comandos",
                                focus=True, h=48))
    # Prefix chips.
    cx = px + 16
    for lab, icon_name, active in (("p: páginas", "home", False), ("s: configurações", "gear", False),
                                   ("c: comandos", "sparkles", False)):
        parts.append(k.chip(cx, py + 82, lab, icon_name, active=active))
        cx += k.chip_w(lab, icon_name) + 8

    groups = [
        ("Páginas  p:", [
            ("Assistente › Hoje", "Como o Gideon está agora", "chat", "Ctrl+1"),
            ("Configurações", "Voz e Wake, áudio, aparência e geral", "gear", "Ctrl+4"),
            ("Diagnóstico", "Estado técnico e registros", "activity", "Ctrl+5"),
        ]),
        ("Configurações  s:", [
            ("Volume da resposta", "Áudio · 80%", "speaker", None),
            ("Mostrar opções avançadas", "Geral · desligado", "gear", None),
        ]),
        ("Comandos  c:", [
            ("Abrir Permissões", "Ir para a aba Permissões", "shield", "Ctrl+3"),
        ]),
    ]
    y = py + 128
    first = True
    for head, items in groups:
        parts.append(k.text(px + 16, y + 14, head, 12, "bold", c.T("textMuted")))
        y += 26
        for title, sub, icon_name, shortcut in items:
            if first:
                parts.append(k.rect(px + 8, y, pw - 16, 52, rx=10, fill=c.T("tint")))
                first = False
            parts.append(k.icon(icon_name, px + 20, y + 14, 22, c.T("accent")))
            parts.append(k.text(px + 56, y + 23, title, 14, "bold", c.T("text")))
            parts.append(k.text(px + 56, y + 41, sub, 12, "normal", c.T("textMuted")))
            if shortcut:
                kw = k.kbd_w(shortcut)
                parts.append(k.kbd(px + pw - 24 - kw, y + 16, shortcut))
            y += 56
        y += 10
    parts.append(c.note(px + 16, py + ph - 26, "↑ ↓ para escolher · Enter abre · Esc fecha"))
    return k.canvas("".join(parts))


def main():
    c.use_theme("gideon-escuro")
    jobs = [("d00-busca", busca()), ("d00-paleta", paleta())]
    for name, svg in jobs:
        os.makedirs(c.OUT_DIR, exist_ok=True)
        svg_path = os.path.join(c.OUT_DIR, name + ".svg")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg)
        print("wrote", svg_path)
        import subprocess
        subprocess.run([c.PY, "-I", "-B", c.RENDER, svg_path,
                        os.path.join(c.OUT_DIR, name + ".png"), str(c.W), str(c.H)], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
