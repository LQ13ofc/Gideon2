pragma Singleton
import QtQuick

// Window-wide state the pages share: per-plugin drafts (plain JS, not reactive by design), the approval targets of
// open dialogs, the toast queue, and the one write path to the app settings (`ui`).
QtObject {
    id: state

    // Drafts survive delegate recreation (keyed by plugin id, consent key or page name).
    property var drafts: ({})
    // Bumped after a consent toggle so bindings that read the drafts re-evaluate.
    property int connDraftRevision: 0
    // The skill whose permissions are shown; a copy of the snapshot row, so it reads as shown when it was picked.
    property var skillSelected: null
    property var reviewPlugin: null
    property string reviewRevision: ""
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
}
