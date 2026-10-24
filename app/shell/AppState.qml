pragma Singleton
import QtQuick

// Window-wide state the pages share: per-plugin drafts (plain JS, not reactive by design), the approval targets of
// open dialogs, the toast queue, the one write path to the app settings (`ui`), the Core-backed settings still waiting
// for the Core, and the settings search target (highlight and "Somente modificados").
// Item (not QtObject) because it holds Connections elements.
Item {
    id: state
    visible: false
    width: 0
    height: 0

    // Drafts survive delegate recreation (keyed by plugin id, consent key or page name).
    property var drafts: ({})
    // Bumped after a consent toggle so bindings that read the drafts re-evaluate.
    property int connDraftRevision: 0
    // The skill whose permissions are shown; a copy of the snapshot row, so it reads as shown when it was picked.
    property var skillSelected: null
    property var reviewPlugin: null
    property string reviewRevision: ""
    // Permissões > Concessões (session only): the filter and grouping the user chose, and the row "Ver ›" opened.
    property string permFilter: "todas"
    property string permGroup: "origem"
    property string permFocusKey: ""
    // Revision captured when the Motor LLM dialog opens; configureLlm refuses it if the live snapshot moved on.
    property string llmRevisionCaptured: ""
    // Model manager: captured when a model is selected and when a models operation settles.
    property string modelsRevisionCaptured: ""
    property var selectedModel: null

    function draftValue(pluginId, key) {
        var d = drafts[pluginId]
        return d && d[key] !== undefined ? d[key] : ""
    }
    function setDraft(pluginId, key, value) {
        if (!drafts[pluginId]) drafts[pluginId] = {}
        drafts[pluginId][key] = value
    }

    // Toasts: short confirmations at the bottom right. Each one leaves after behavior.toastSeconds.
    property var toasts: []
    property int toastSeq: 0
    function toast(text) {
        if (!text || String(text).length === 0) return
        toastSeq += 1
        toasts = toasts.concat([{ id: toastSeq, text: String(text) }])
        if (toasts.length > 3) toasts = toasts.slice(toasts.length - 3)
    }
    function dismissToast(id) {
        toasts = toasts.filter(function (t) { return t.id !== id })
    }

    // ---- App settings (`ui`) -------------------------------------------------------------------------------------
    // The only write path to the settings object. Without `ui` (not loaded yet) nothing is written and false comes back.
    function uiSet(key, value) {
        if (typeof ui === "undefined" || !ui) return false
        ui.set(key, value)
        return true
    }
    function uiGet(key, fallback) {
        if (typeof ui === "undefined" || !ui || !ui.values) return fallback
        var v = ui.values[key]
        return v === undefined || v === null ? fallback : v
    }
    function uiLive() { return typeof ui !== "undefined" && !!ui }

    // The schema entry of one key (label, help, level, options) or null.
    function uiSpec(key) {
        if (!key || !uiLive()) return null
        var list = ui.schema
        for (var i = 0; i < list.length; i++) if (list[i].key === key) return list[i]
        return null
    }
    function isModified(key) {
        return !!key && uiLive() && ui.modifiedKeys.indexOf(key) >= 0
    }
    function modifiedKeys() { return uiLive() ? ui.modifiedKeys : [] }
    // How many advanced options of a sub-tab are hidden right now (0 when "Mostrar opções avançadas" is on).
    function advancedHidden(subtab) {
        if (!uiLive() || uiGet("behavior.advanced", false) === true) return 0
        var count = 0, list = ui.schema
        for (var i = 0; i < list.length; i++) if (list[i].subtab === subtab && list[i].level === "advanced") count++
        return count
    }
    // Why a setting cannot be changed now ("" when it can). Core-backed keys (core.*) depend on the Core's state.
    function blockReason(key) {
        if (!key) return ""
        if (!uiLive()) return "configurações do app indisponíveis"
        if (key.indexOf("core.") !== 0 || typeof core === "undefined" || !core) return ""
        if (!core.connected) return "Core desconectado"
        if (core.configurationStatus === "safe_mode") return "modo seguro"
        if (core.configurationStatus === "restart_required") return "reinício do Core pendente"
        if (String(core.sessionId || "").length > 0) return "sessão de voz em andamento; tente quando o Gideon estiver em espera"
        if (!core.preferencesAvailable) return "o Core está ocupado com outra alteração"
        if ((key === "core.responseGain" || key === "core.audibleFeedback") && !core.voiceAvailable) return "motor de voz não está disponível no Core"
        return ""
    }
    // Writes one setting through `ui`. Core-backed keys stay "applying" until the Core confirms the new value.
    function setSetting(key, value) {
        if (!uiLive()) { toast("Configurações do app indisponíveis: nada foi salvo."); return false }
        var result = ui.set(key, value)
        if (!result.ok) { toast(result.error); return false }
        if (result.corrected && result.corrected.length > 0) toast("Cor ajustada para manter o contraste mínimo.")
        if (result.pending) markPending(key, value)
        return true
    }
    function resetSetting(key) {
        if (!uiLive()) return false
        var result = ui.reset(key)
        if (!result.ok) { toast(result.error); return false }
        return true
    }
    function bestOn(hex) {
        if (!uiLive() || !hex) return "#000000"
        return ui.contrast(hex, "#ffffff") >= ui.contrast(hex, "#000000") ? "#ffffff" : "#000000"
    }

    // Core-backed writes sent and not yet confirmed: key -> requested value.
    property var corePending: ({})
    property int corePendingRev: 0
    function isApplying(key) {
        var rev = corePendingRev
        return !!key && rev >= 0 && corePending.hasOwnProperty(key)
    }
    function markPending(key, value) {
        var next = {}
        for (var k in corePending) next[k] = corePending[k]
        next[key] = value
        corePending = next
        corePendingRev += 1
    }
    function clearPending() {
        if (Object.keys(corePending).length === 0) return
        corePending = ({})
        corePendingRev += 1
    }
    function settlePending() {
        var keys = Object.keys(corePending)
        if (keys.length === 0 || !uiLive()) return
        var now = ui.values, left = {}, changed = false
        for (var i = 0; i < keys.length; i++) {
            var key = keys[i]
            if (now[key] === corePending[key]) changed = true
            else left[key] = corePending[key]
        }
        if (changed) { corePending = left; corePendingRev += 1 }
    }
    Connections {
        target: (typeof ui !== "undefined" && ui) ? ui : null
        function onValuesChanged() { state.settlePending() }
    }
    Connections {
        target: (typeof core !== "undefined" && core) ? core : null
        function onPrefsSettled(message) {
            state.clearPending()
            state.toast(message)
        }
    }

    // Settings search target: the row to reveal and highlight, and the "Somente modificados" filter.
    property string highlightKey: ""
    property bool onlyModified: false

    // The state notice of the Configurações tab ("" when nothing to say).
    function configNotice() {
        if (typeof core === "undefined" || !core) return ""
        if (core.configurationStatus === "safe_mode" || core.configurationStatus === "restart_required") return core.configurationMessage
        if (!core.connected) return "Indisponível: Core desconectado. Os valores mostrados são os últimos conhecidos."
        if (String(core.sessionId || "").length > 0) return "Indisponível agora: sessão de voz em andamento. Tente quando o Gideon estiver em espera."
        return ""
    }
}
