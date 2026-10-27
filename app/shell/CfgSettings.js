.pragma library
// Shared text and small rules of the Configurações pages. Portuguese is the source language; texts go through qsTr at
// call time so a language switch shows the new words without a restart.

function QT_TR_NOOP(text) { return text }

var themeRoles = ["bg", "surface", "surfaceVariant", "outline", "text", "textMuted", "accent", "onAccent", "success", "warning", "error", "info"]

var roleNames = {
    bg: QT_TR_NOOP("Fundo da janela"), surface: QT_TR_NOOP("Superfície"), surfaceVariant: QT_TR_NOOP("Superfície variante"), outline: QT_TR_NOOP("Contorno"),
    text: QT_TR_NOOP("Texto"), textMuted: QT_TR_NOOP("Texto secundário"), accent: QT_TR_NOOP("Destaque"), onAccent: QT_TR_NOOP("Texto sobre destaque"),
    success: QT_TR_NOOP("Sucesso"), warning: QT_TR_NOOP("Aviso"), error: QT_TR_NOOP("Erro"), info: QT_TR_NOOP("Informação")
}

// Sub-tab labels (schema `subtab`) to the page ids of the Configurações tab. The keys are the schema identifiers
// (uisettings.py), not display text: the display text of a sub-tab comes from the schema's subtabLabel.
var subtabPages = {
    "Voz e Wake": "cfg_voz", "Idiomas": "cfg_idiomas", "Áudio": "cfg_audio", "Dispositivos": "cfg_dispositivos",
    "Aparência": "cfg_aparencia", "Privacidade": "cfg_privacidade", "Geral": "cfg_geral"
}

function roleLabel(token) { return roleNames.hasOwnProperty(token) ? qsTr(roleNames[token]) : token }

function pageForSubtab(label) { return subtabPages[label] || "cfg_geral" }

// Contrast ratio with the decimal separator of the interface language (, in Portuguese and French, . in English), e.g. 4,5:1.
function ratioText(value) { return Number(value).toFixed(1).replace(".", qsTr(",")) + ":1" }

// Texts that src/languages_catalog.json (Core data, Portuguese) ships in its license, quality, reason and size fields.
// The Core sends them as they are; a text listed here is shown in the interface language, any other is shown as sent.
var catalogFacts = [
    QT_TR_NOOP("já incluído no pacote"),
    QT_TR_NOOP("encoder 652.184.281 B + decoder 11.845.275 B + joiner 6.355.277 B + tokens 93.939 B; baixado e verificado (WP-7)"),
    QT_TR_NOOP("mesmo modelo multilíngue do francês; baixado e verificado (WP-7)"),
    QT_TR_NOOP("pesos 219.029.196 B + tokenizador 246.403 B + voz estelle 8.259.384 B; baixado e verificado (WP-7)"),
    QT_TR_NOOP("pesos 219.029.196 B + tokenizador 247.014 B + voz rafael 6.195.000 B; baixado e verificado (WP-7)"),
    QT_TR_NOOP("MIT (página do pacote moonshine-voice; não reverificada no arquivo do modelo)"),
    QT_TR_NOOP("CC-BY-4.0 (NVIDIA parakeet-tdt-0.6b-v3); export ONNX do sherpa-onnx, licença própria não publicada"),
    QT_TR_NOOP("CC-BY-4.0 (pesos, cartão do modelo); licença por voz varia"),
    QT_TR_NOOP("CC-BY-4.0 (pesos, cartão do modelo); licença da voz estelle NÃO VERIFICADA"),
    QT_TR_NOOP("CC-BY-4.0 (pesos, cartão do modelo); licença da voz rafael NÃO VERIFICADA"),
    QT_TR_NOOP("ver docs/research/idiomas-stt-tts.md (não reconferida)"),
    QT_TR_NOOP("medido pelo projeto"),
    QT_TR_NOOP("medido pelo projeto (dev_qualified)"),
    QT_TR_NOOP("sintético (TTS): WER 11,7% em 16 frases FR; não medido com voz humana"),
    QT_TR_NOOP("sintético (TTS): WER 10,1% em 16 frases PT; não medido com voz humana"),
    QT_TR_NOOP("sintético: fala 4,6 s em cerca de 1,5 s após carregar (CPU, 2 threads); qualidade não medida"),
    QT_TR_NOOP("sintético: fala 3,5 s em cerca de 1,3 s após carregar (CPU, 2 threads); qualidade não medida"),
    QT_TR_NOOP("WP-7c, PT+FR: 11/14 no lab limpo, 0 falsos limpos, 1 falso com webcam 5 dB; abaixo de 80%"),
    QT_TR_NOOP("Wake por transcrição abaixo do chão (WP-7c): 11 de 14 no lab limpo, 1 falso com ruído de webcam 5 dB, 6 de 14 no PipeWire.")
]
function catalogFact(text) { return catalogFacts.indexOf(text) >= 0 ? qsTr(text) : text }

// '#rgb' or '#rrggbb' in any case, normalised to '#rrggbb' lower case; "" when it is not a colour.
function normalizeHex(text) {
    var match = /^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec(String(text || "").trim())
    if (!match) return ""
    var digits = match[1].toLowerCase()
    if (digits.length === 3) digits = digits[0] + digits[0] + digits[1] + digits[1] + digits[2] + digits[2]
    return "#" + digits
}

function advancedHiddenText(count) {
    return count === 1 ? qsTr("1 opção avançada oculta") : qsTr("%1 opções avançadas ocultas").arg(count)
}

// One automatic contrast correction, as the user reads it.
function fixText(fix) {
    return qsTr("%1: %2 → %3 (%4 → %5, mínimo %6)").arg(roleLabel(fix.token)).arg(String(fix.from).toUpperCase())
        .arg(String(fix.to).toUpperCase()).arg(ratioText(fix.ratio_before)).arg(ratioText(fix.ratio_after)).arg(ratioText(fix.minimum))
}
