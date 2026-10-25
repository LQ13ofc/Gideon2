.pragma library
// Shared text and small rules of the Configurações pages (Portuguese, as the user reads them).

var themeRoles = ["bg", "surface", "surfaceVariant", "outline", "text", "textMuted", "accent", "onAccent", "success", "warning", "error", "info"]

var roleNames = {
    bg: "Fundo da janela", surface: "Superfície", surfaceVariant: "Superfície variante", outline: "Contorno",
    text: "Texto", textMuted: "Texto secundário", accent: "Destaque", onAccent: "Texto sobre destaque",
    success: "Sucesso", warning: "Aviso", error: "Erro", info: "Informação"
}

// Sub-tab labels (schema `subtab`) to the page ids of the Configurações tab.
var subtabPages = {
    "Voz e Wake": "cfg_voz", "Idiomas": "cfg_idiomas", "Áudio": "cfg_audio", "Dispositivos": "cfg_dispositivos",
    "Aparência": "cfg_aparencia", "Privacidade": "cfg_privacidade", "Geral": "cfg_geral"
}

function roleLabel(token) { return roleNames[token] || token }

function pageForSubtab(label) { return subtabPages[label] || "cfg_geral" }

// Contrast ratio with the Portuguese decimal comma, e.g. 4,5:1.
function ratioText(value) { return Number(value).toFixed(1).replace(".", ",") + ":1" }

// '#rgb' or '#rrggbb' in any case, normalised to '#rrggbb' lower case; "" when it is not a colour.
function normalizeHex(text) {
    var match = /^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec(String(text || "").trim())
    if (!match) return ""
    var digits = match[1].toLowerCase()
    if (digits.length === 3) digits = digits[0] + digits[0] + digits[1] + digits[1] + digits[2] + digits[2]
    return "#" + digits
}

function advancedHiddenText(count) { return count === 1 ? "1 opção avançada oculta" : count + " opções avançadas ocultas" }

// One automatic contrast correction, as the user reads it.
function fixText(fix) {
    return roleLabel(fix.token) + ": " + String(fix.from).toUpperCase() + " → " + String(fix.to).toUpperCase()
        + " (" + ratioText(fix.ratio_before) + " → " + ratioText(fix.ratio_after) + ", mínimo " + ratioText(fix.minimum) + ")"
}
