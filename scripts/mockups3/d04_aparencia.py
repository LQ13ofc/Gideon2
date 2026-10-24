#!/usr/bin/env python3
"""d04: Configurações > Aparência, three views (docs/ui-spec/40-configuracoes.md, 7.4 and 10).

  (a) basic view, gideon-escuro         -> d04-aparencia.png
  (b) advanced view open (Mostrar opções avançadas ON) -> d04-aparencia-avancado.png
  (c) the basic view again in gideon-claro and mocha-like (catppuccin theme)
      -> d04-aparencia-claro.png, d04-aparencia-catppuccin.png

Extra decisions vs spec 7.4 (see report): 8 presets from docs/research/ux-temas.md 6.4 replace the
three dark variants, density/radius/font controls come from ux-temas 6.2, accent swatches use the
spec values (AP-9 to AP-12).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg_common as c  # noqa: E402

k = c.k
PRESET_LABEL = dict((key, name) for name, key in c.PRESETS)
DRAFT_TEXT_MUTED = "#5C6672"  # draft typed in the editor, below the 4.5:1 threshold


def ratio_text(r):
    return f"{r:.1f}".replace(".", ",") + ":1"


def fix_contrast(fg, bg, target):
    """Move fg toward white (dark bg) or black (light bg) until target contrast; return (hex, ratio)."""
    toward = "#FFFFFF" if k.contrast("#FFFFFF", bg) > k.contrast("#000000", bg) else "#000000"
    t = 0.0
    while t <= 1.0:
        cand = k.mix(fg, toward, t)
        r = k.contrast(cand, bg)
        if r >= target:
            return cand, r
        t = round(t + 0.01, 4)
    return toward, k.contrast(toward, bg)


def basic(theme_key, mode):
    c.use_theme(theme_key)
    preset = PRESET_LABEL[theme_key]
    parts = [c.shell(3, "Aparência", "Tema e cor de destaque desta janela, com prévia imediata.",
                     f"Tema: {preset} · Destaque: Azul · Esfera: ligada · Não salvo ao reabrir",
                     badges=[("Esfera: ligada", "ok")])]

    # Card 1: presets (8 thumbnails, 4 x 2) and mode. Spec: (140, 236, 542, 330).
    parts.append(k.card(c.LX, 236, c.HALF, 330, "Tema"))
    parts.append(c.note(160, 292, "Oito presets, todos com contraste verificado (WCAG AA)."))
    pitch = (502 - 116) / 3.0
    for i, (name, key) in enumerate(c.PRESETS):
        col, row = i % 4, i // 4
        parts.append(c.preset_thumb(160 + col * pitch, 306 + row * 98, name, key,
                                    selected=(key == theme_key)))
    parts.append(c.label(160, 512, "Modo"))
    parts.append(c.segmented(160, 520, ["Sistema", "Escuro", "Claro"], mode))

    # Card 2: accent swatches, density, radius, font size. Spec: (698, 236, 542, 330).
    parts.append(k.card(c.RX, 236, c.HALF, 330, "Cor de destaque e forma"))
    parts.append(c.note(718, 292, "Usada em destaques, botões e foco. Não fica salva ao reabrir."))
    for i, (name, hexv) in enumerate(c.ACCENTS):
        parts.append(c.accent_tile(718 + i * 128, 306, 116, name, hexv, selected=(hexv == c.ACCENT_DEFAULT)))
    parts.append(c.label(718, 400, "Densidade"))
    parts.append(c.segmented(718, 410, c.DENSITY_STEPS, "Normal"))
    parts.append(c.slider_row(718, 478, 232, "Raio dos cantos", 0.5, "8 px", "0 px", "16 px"))
    parts.append(c.slider_row(982, 478, 236, "Tamanho da fonte", 0.25, "14 px", "12 px", "20 px"))

    # Card 3: live preview and the activity orb switch. Spec: (140, 582, 1100, 190).
    parts.append(k.card(c.CX, 582, c.CW, 190, "Prévia ao vivo e esfera"))
    parts.append(c.live_preview(160, 634, 560, 130, radius=8, font=14, pad=12))
    parts.append(c.toggle(748, 640, "Mostrar esfera e indicador de atividade", on=True))
    parts.append(c.note_wrap(748, 700, "O indicador é salvo pelo Core. Estado textual, legendas "
                                       "e Cancelar continuam disponíveis.", 492))
    parts.append(c.note(748, 748, "A prévia não grava nada. Só a esfera é salva."))

    parts.append(c.como(788, "Tema e cor são da janela. A esfera é a única escolha desta aba que o Core guarda hoje."))
    return k.canvas("".join(parts))


def advanced():
    c.use_theme("gideon-escuro")
    t = c.T
    parts = [c.shell(3, "Aparência", "Cores, contraste e efeitos do tema. Valores são validados ao digitar.",
                     "Tema: Gideon escuro · Destaque: Azul · 1 cor alterada · Opções avançadas: ligadas",
                     badges=[("Opções avançadas: ligadas", "muted")])]

    # Card 1 (8 cols): per-role editor, two columns of six. Spec: (140, 236, 728, 340).
    parts.append(k.card(c.CX, 236, 728, 340, "Cores por papel"))
    parts.append(c.note(160, 292, "Cada cor é conferida com o fundo onde aparece. Hex inválido é recusado."))
    roles = [
        ("Fundo da janela", t("bg"), None),
        ("Superfície", t("surface"), None),
        ("Superfície variante", t("surfaceVariant"), None),
        ("Contorno", t("outline"), None),
        ("Texto", t("text"), None),
        ("Texto secundário", DRAFT_TEXT_MUTED, "warn"),
        ("Destaque", t("accent"), "accent"),
        ("Texto sobre destaque", t("onAccent"), None),
        ("Sucesso", t("success"), None),
        ("Aviso", t("warning"), None),
        ("Erro", t("error"), None),
        ("Informação", t("info"), None),
    ]
    for i, (name, value, mark) in enumerate(roles):
        col, row = i // 6, i % 6
        x = 160 + col * 344
        y = 306 + row * 40
        if mark:
            parts.append(c.modified(x - 12, y, 30, "warn" if mark == "warn" else None))
        parts.append(k.rect(x, y + 3, 24, 24, rx=6, fill=value, stroke=t("border")))
        parts.append(k.text(x + 36, y + 21, name, 14, "normal", t("text")))
        parts.append(k.input_box(x + 196, y + 1, 116, 30, value.upper()))

    # Card 2 (4 cols): pair contrast and the automatic correction. Spec: (884, 236, 356, 340).
    parts.append(k.card(884, 236, 356, 340, "Contraste dos pares"))
    parts.append(c.note(904, 292, "Mínimo: texto 4,5:1 · contornos e destaques 3:1."))
    pairs = [
        ("Texto sobre fundo", t("text"), t("bg"), 4.5),
        ("Texto secundário / superfície", DRAFT_TEXT_MUTED, t("surface"), 4.5),
        ("Texto sobre destaque", t("onAccent"), t("accent"), 4.5),
        ("Destaque sobre fundo", t("accent"), t("bg"), 3.0),
        ("Contorno sobre superfície", t("outline"), t("surface"), 3.0),
        ("Erro como texto", t("error"), t("bg"), 4.5),
    ]
    failing = None
    for i, (name, fg, bg, need) in enumerate(pairs):
        y = 306 + i * 26
        r = k.contrast(fg, bg)
        ok = r >= need
        if not ok:
            failing = (fg, bg, need, r)
        parts.append(k.text(904, y + 16, name, 12, "normal", t("text")))
        parts.append(k.text(1160, y + 16, ratio_text(r), 12, "bold", t("text"), anchor="end"))
        parts.append(k.badge(1174, y + 2, "OK" if ok else "Abaixo", "ok" if ok else "err"))
    fg, bg, need, r0 = failing
    fixed, r1 = fix_contrast(fg, bg, need)
    by = 470
    parts.append(k.rect(904.5, by + 0.5, 315, 96, rx=10, fill=t("surfaceVariant"), stroke=t("border")))
    parts.append(k.text(920, by + 20, "Corrigido automaticamente", 12, "bold", t("accent")))
    parts.append(k.rect(920, by + 30, 14, 14, rx=3, fill=fg, stroke=t("border")))
    parts.append(k.text(942, by + 42, f"{fg.upper()}  →", 12, "normal", t("text")))
    parts.append(k.rect(1058, by + 30, 14, 14, rx=3, fill=fixed, stroke=t("border")))
    parts.append(k.text(1080, by + 42, fixed.upper(), 12, "normal", t("text")))
    parts.append(k.text(920, by + 60, f"{ratio_text(r0)} → {ratio_text(r1)} (mínimo {ratio_text(need)})",
                        12, "normal", t("textMuted")))
    parts.append(k.button(920, by + 66, 100, "Aceitar", variant="primary", h=26))
    parts.append(k.button(1030, by + 66, 128, "Manter o meu", variant="secondary", h=26))

    # Card 3 (12 cols): motion, translucency, shadow, import and export. Spec: (140, 592, 1100, 180).
    parts.append(k.card(c.CX, 592, c.CW, 180, "Animação, translucidez e sombra"))
    parts.append(c.label(160, 658, "Animação"))
    parts.append(c.segmented(160, 666, ["Desligada", "Reduzida", "Normal"], "Normal"))
    parts.append(c.slider_row(520, 658, 300, "Translucidez (desfoque)", 0.0, "Desligada", "0 px", "24 px"))
    parts.append(c.slider_row(880, 658, 340, "Intensidade da sombra", 0.3, "30%", "0%", "100%"))
    bx = 160
    for lab, variant in (("Importar tema…", "secondary"), ("Exportar tema…", "secondary"),
                         ("Restaurar padrão do tema", "ghost")):
        w = c.bw(lab)
        parts.append(k.button(bx, 728, w, lab, variant=variant))
        bx += w + 12
    parts.append(c.note(bx + 8, 752, "Arquivo JSON versionado, validado ao importar."))

    parts.append(c.como(788, "Cores por papel validam o contraste ao digitar. Hex inválido é recusado "
                             "e o valor anterior fica."))
    return k.canvas("".join(parts))


def main():
    jobs = [
        ("d04-aparencia", basic("gideon-escuro", "Escuro")),
        ("d04-aparencia-avancado", advanced()),
        ("d04-aparencia-claro", basic("gideon-claro", "Claro")),
        ("d04-aparencia-catppuccin", basic("catppuccin", "Escuro")),
    ]
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
