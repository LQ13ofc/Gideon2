.pragma library
// Timeline rows for Assistente > Atividade and the recent list of Hoje (docs/ui-spec/10-assistente.md §6).
// Phrases, categories and result words come from EventLabels.js (table 50-diagnostico §4, shared with Auditoria and
// Diagnóstico); skill and connection rows use Labels.js. Pure functions: the page passes the Core lists in.
// No payload content is shown (no transcript, arguments, answers or skill output).
.import "EventLabels.js" as E
.import "Labels.js" as L

// Row of one Core event, or null when this timeline does not show it.
// Kinds the table does not know are shown as "Evento do Core sem descrição" (Tudo only: no category).
// Kinds the table hides (phrase "") are never shown. Other kinds show in Atividade when A is marked, or always when
// they are error kinds (E), so the Erros filter is never empty of errors the Core reports.
function eventRow(ev) {
    var kind = String(ev.kind || "")
    var e = E.entry(kind)
    if (e !== null) {
        if (E.phrase(kind) === "") return null
        if (!e.a && !e.e) return null
    }
    var failed = ev.outcome === "failed" || (e !== null && e.result === "failed")
    var badge = null
    if (failed) badge = {text: qsTr("Falhou"), tone: "error"}
    else if (e !== null && e.result === "done" && ev.outcome === "ok") badge = {text: qsTr("Concluído"), tone: "success"}
    return {
        key: "e" + ev.sequence,
        seq: Number(ev.sequence) || 0,
        time: E.clockText(ev.at_ms),
        text: E.phrase(kind),
        category: e !== null ? e.cat : "",
        error: failed || E.isErrorKind(kind),
        badge: badge
    }
}

// Event rows, newest first by sequence.
function eventRows(events) {
    var out = []
    for (var i = 0; i < events.length; i++) {
        var row = eventRow(events[i])
        if (row) out.push(row)
    }
    out.sort(function (a, b) { return b.seq - a.seq })
    return out
}

// Filter of the timeline: all | cmd | skill | agent | err. Categories are the keys of EventLabels.js.
function matches(row, filterId) {
    switch (filterId) {
    case "cmd": return row.category === "command"
    case "skill": return row.category === "skill"
    case "agent": return row.category === "agent"
    case "err": return row.error === true
    }
    return true
}

// Skill run row (no Core time: the page orders these by the order it first saw them).
function skillRow(run) {
    var state = String(run.state || "")
    var codes = run.codes || []
    var text = qsTr("%1 v%2 · %3 · passo %4").arg(String(run.skill || "")).arg(String(run.version || ""))
        .arg(L.skillRunText(state)).arg(String(run.step === undefined ? "" : run.step))
    if (codes.length > 0) text += " · " + E.codePhrase(codes[0])
    var badge = null
    if (state === "done") badge = {text: qsTr("Concluída"), tone: "success"}
    else if (state === "failed") badge = {text: qsTr("Falhou"), tone: "error"}
    return {key: "skill:" + String(run.run_id || run.skill || ""), seq: 0, time: "", text: text, category: "skill", error: state === "failed", badge: badge}
}

// Last connection call row (no Core time). Outcome words never show a raw code.
function callRow(call) {
    var ok = call.outcome === "ok"
    var result = call.code ? E.codePhrase(call.code) : (ok ? qsTr("concluída") : qsTr("Resultado desconhecido"))
    var text = qsTr("Última chamada: %1 · %2").arg(L.connOpLabel(String(call.operation || ""))).arg(result)
    if (call.untrusted === true) text += " · " + qsTr("Conteúdo externo não exibido.")
    return {key: "call:" + String(call.operation || "") + ":" + String(call.outcome || "") + ":" + String(call.code || ""), seq: 0, time: "", text: text, category: "connection", error: !ok, badge: null}
}
