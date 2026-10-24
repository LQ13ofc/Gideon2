#!/usr/bin/env python3
"""Mockups b05: Extensoes > Percepcao e acao (segments Privacidade, Plugins, Ultimo resultado).

Spec: docs/ui-spec/20-extensoes.md section 6 (6.3 to 6.6), with 00-casca.md.
All backends are synthetic in this build; nothing real is accessed. The Plugins segment shows the
Desenvolvimento test buttons (modo desenvolvedor on) so the safe actions are visible; no write action
has a button (R-PC-2). display_manipulate is UNSUPPORTED (R-PC-4).
Writes docs/ui-mockups-v3/b05-percepcao-privacidade, -plugins, -resultado (.svg and .png), theme gideon-escuro.
  target/ui-venv/bin/python -I -B scripts/mockups3/b05_percepcao.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ext_common as c  # noqa: E402
import mockup_kit3 as k  # noqa: E402

SUB = "Percepção e ação"
TITLE = "Percepção e ação"
SUBTITLE = "Sensores e ações simulados nesta build. Nenhum hardware real é acessado."
SEGMENTS = ["Privacidade", "Plugins", "Último resultado"]
SUMMARY = "3 plugins de percepção em execução"
SUMMARY_BADGES = [("Microfone: desligado", "muted"), ("Câmera: não lido", "muted")]
SYNTH = "Backends simulados: nenhum hardware pessoal é acessado nesta build."


def frame(seg):
    return c.frame(SUB, TITLE, SUBTITLE, SEGMENTS, seg, action=None,
                   summary_text=SUMMARY, summary_badges=SUMMARY_BADGES)


def muted():
    return k.T["textMuted"]


def text_c():
    return k.T["text"]


# ---------------------------------------------------------------- 6.3 Privacidade

def build_privacidade():
    x, w = c.CX, c.CW
    out = [k.card(x, 284, w, 180, "Indicadores")]
    # Two indicators: dot + text with the state word (6.3.2 EX-PC-PV-01/02)
    out.append(c.indicator(x + 20, 336, "Microfone · indicador: desligado", "desligado", "muted"))
    out.append(c.indicator(x + 20, 372, "Câmera · indicador: não lido", "não lido", "muted"))
    out.append(k.text(x + 20, 418, "Os indicadores mostram o último estado lido. Só a leitura de estado "
                      "atualiza esta tela.", 13, "normal", muted()))
    out.append(k.text(x + 20, 440, SYNTH, 13, "normal", muted()))
    out.append(k.card(x, 480, w, 120, "O que não é gravado"))
    out.append(k.text(x + 20, 548, "Nada é gravado em disco. Áudio e legendas ficam só em memória.", 14,
                      "normal", text_c()))
    return "".join(out)


# ---------------------------------------------------------------- 6.4 Plugins

PLUGINS = [
    dict(id="screen_observe", state="em execução", tn="ok", sealed="SINTÉTICO — sem hardware real",
         seal_tn="muted", perm="ver a tela", granted=False,
         buttons=[("Capturar", "secondary", "normal"), ("Estado", "secondary", "normal")], reason=None, err=None),
    dict(id="computer_control", state="em execução", tn="ok", sealed="SINTÉTICO — sem hardware real",
         seal_tn="muted", perm="controlar o computador", granted=False,
         buttons=[("Árvore", "secondary", "normal"), ("Estado", "secondary", "normal")], reason=None, err=None),
    dict(id="audio_advanced", state="parado", tn="muted", sealed="SINTÉTICO — sem hardware real",
         seal_tn="muted", perm="ouvir áudio", granted=False,
         buttons=[("Estado", "secondary", "disabled")],
         reason="Indisponível: plugin não está em execução.", err=None),
    dict(id="mic_advanced", state="falhou", tn="err", sealed="SINTÉTICO — sem hardware real",
         seal_tn="muted", perm="microfone", granted=False,
         buttons=[("Estado", "secondary", "disabled")],
         reason="Indisponível: plugin não está em execução.",
         err="Último erro: dispositivo de áudio indisponível nesta build."),
    dict(id="camera_gesture", state="desativado", tn="muted", sealed="SINTÉTICO — sem hardware real",
         seal_tn="muted", perm="câmera", granted=False,
         buttons=[("Estado", "secondary", "disabled")],
         reason="Indisponível: plugin não está em execução.", err=None),
    dict(id="display_manipulate", state="em execução", tn="ok", sealed="UNSUPPORTED",
         seal_tn="warn", perm="alterar monitores", granted=False,
         buttons=[("Estado", "secondary", "normal")], reason=None,
         err="Nenhuma ação de manipulação existe; produto não é bloqueado."),
]

CARD_H = 184
GAP = 12


def plugin_card(x, y, w, p):
    parts = []
    parts.append(k.text(x + 20, y + 34, p["id"] + " 0.1.0", 17, "bold", text_c()))
    bw = k.badge_w(p["state"])
    parts.append(k.badge(x + w - 20 - bw, y + 17, p["state"], p["tn"]))
    seal, _ = c.tag(x + 20, y + 42, p["sealed"], p["seal_tn"])
    parts.append(seal)
    perm_state = "concedida" if p["granted"] else "não concedida"
    parts.append(k.text(x + 20, y + 84, "Permissão exigida: %s · %s" % (p["perm"], perm_state), 13, "normal",
                        text_c()))
    parts.append(k.text(x + 20, y + 102, "Backend real: não suportado / pendente de validação humana", 12,
                        "normal", muted()))
    if p["err"]:
        err_tn = "err" if p["tn"] == "err" else "warn"
        parts.append(k.text(x + 20, y + 120, p["err"], 12, "normal", c.tone(err_tn)))
    by = y + 132
    bx = x + 20
    for lbl, var, state in p["buttons"]:
        bwid = k.button_w(lbl)
        parts.append(k.button(bx, by, bwid, lbl, variant=var, state=state))
        bx += bwid + 8
    if p["reason"]:
        parts.append(k.text(bx + 4, by + 25, p["reason"], 12, "normal", muted()))
    return k.card(x, y, w, CARD_H, None) + "".join(parts)


def build_plugins():
    out = []
    xs = [c.CX, c.RX]
    for i, p in enumerate(PLUGINS):
        col, row = i % 2, i // 2
        y = 284 + row * (CARD_H + GAP)
        out.append(plugin_card(xs[col], y, c.HW, p))
    # card footer: the spec line for the segment (6.4.2 texto de rodapé)
    out.append(k.text(c.CX, 872, "Nenhuma ação altera o computador nesta build.", 12, "normal", muted()))
    return "".join(out)


# ---------------------------------------------------------------- 6.5 Ultimo resultado

def build_resultado():
    x, y, w = c.CX, 284, c.CW
    h = 200
    out = [k.card(x, y, w, h, "Último resultado")]
    seal, _ = c.tag(x + w - 20 - c.tag(0, 0, "SINTÉTICO")[1], y + 19, "SINTÉTICO")
    out.append(seal)
    out.append(k.rect(x + 20, y + 52, w - 40, 96, rx=10, fill=k.T["surfaceVariant"], stroke=k.T["border"]))
    out.append(k.text(x + 36, y + 80, "screen_observe.capture · concluída", 14, "bold", text_c()))
    out.append(k.text(x + 36, y + 104,
                      "Captura sintética gerada em memória (640 × 360). Nada foi salvo.", 14, "normal", text_c()))
    out.append(k.text(x + 36, y + 128, "Nenhum conteúdo de tela é mostrado; a captura não altera o computador.",
                      13, "normal", muted()))
    return "".join(out)


def main():
    c.write("b05-percepcao-privacidade", frame("Privacidade") + build_privacidade())
    c.write("b05-percepcao-plugins", frame("Plugins") + build_plugins())
    c.write("b05-percepcao-resultado", frame("Último resultado") + build_resultado())
    return 0


if __name__ == "__main__":
    sys.exit(main())
