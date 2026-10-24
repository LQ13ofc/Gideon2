.pragma library
// Pure helpers for the Plugins and Skills rows and drawers. The caller passes the snapshot values in; nothing here
// reads the Core. Words are Portuguese; Core codes are translated by the caller through core.codeMessage.

var reasonWords = {
    api_version: "versão de API incompatível",
    target: "plataforma incompatível",
    dependencies_unresolved: "dependências não resolvidas"
}
function reasonText(reason) { return reasonWords[reason] || "motivo não reconhecido" }

// A plugin row is installed when the Core has an item for it or the catalog says so.
function isInstalled(entry, item) {
    if (item) return true
    return !!entry && (entry.status === "installed" || entry.status === "update_available")
}
function isAvailable(entry) {
    return !!entry && (entry.status === "not_installed" || entry.status === "update_available")
}
function inFilter(row, filter) {
    if (filter === "instalados") return isInstalled(row.entry, row.item)
    if (filter === "disponiveis") return isAvailable(row.entry)
    if (filter === "quarentena") return !!row.item && row.item.state === "quarantined"
    return true
}
function counts(rows) {
    var out = {todos: rows.length, instalados: 0, disponiveis: 0, quarentena: 0}
    for (var i = 0; i < rows.length; i++) {
        if (isInstalled(rows[i].entry, rows[i].item)) out.instalados++
        if (isAvailable(rows[i].entry)) out.disponiveis++
        if (inFilter(rows[i], "quarentena")) out.quarentena++
    }
    return out
}

// One line that says what the plugin is doing (the row's second line and the drawer's state line).
function stateLine(entry, item, codeMessage) {
    if (item) {
        switch (item.state) {
        case "quarantined": return "Em quarentena: não pode ser ativado."
        case "running": return "Ativo (sandbox, sem rede)"
        case "starting": return "Iniciando…"
        case "failed": return "Falhou: " + (codeMessage(item.last_error) || "erro")
        case "stopped": return "Parado"
        default: return "Desativado"
        }
    }
    if (!entry) return ""
    switch (entry.status) {
    case "not_installed": return "Disponível"
    case "update_available": return "Atualização disponível"
    case "installed": return "Instalado · desativado (sem execução)"
    case "incompatible": return "Incompatível: " + reasonText(entry.reason)
    }
    return ""
}
function stateTone(entry, item) {
    if (item) {
        if (item.state === "quarantined" || item.state === "failed") return "error"
        if (item.state === "running") return "success"
        if (item.state === "starting") return "info"
        return "muted"
    }
    if (entry && entry.status === "incompatible") return "warning"
    return "muted"
}

// Exception badge only (selo só para exceção): quarantine, failure, incompatibility. Returns null otherwise.
function exceptionBadge(entry, item) {
    if (item && item.state === "quarantined") return {text: "Quarentena", tone: "error"}
    if (item && item.state === "failed") return {text: "Falhou", tone: "error"}
    if (!item && entry && entry.status === "incompatible") return {text: "Incompatível", tone: "warning"}
    return null
}

// The row's primary action (EX-PL-05). kind: review | install | enable | disable | none.
// ctx: {pluginsAvailable, hubApprovalAvailable, hubLifecycleAvailable, blockedText}.
function primary(entry, item, ctx) {
    var blocked = ctx.blockedText
    if (item && item.state === "quarantined")
        return {kind: "enable", text: "Ativar", variant: "primary", enabled: false, reason: "Em quarentena: não pode ser ativado."}
    if (item && item.state === "starting")
        return {kind: "none", text: "Aguarde o plugin iniciar", variant: "secondary", enabled: false, reason: "Aguarde o plugin iniciar."}
    if (item && item.state === "running")
        return {kind: "disable", text: "Desativar", variant: "secondary", enabled: ctx.pluginsAvailable, reason: ctx.pluginsAvailable ? "" : blocked}
    if (entry && entry.status === "incompatible")
        return {kind: "none", text: "Indisponível", variant: "secondary", enabled: false, reason: "Indisponível: " + reasonText(entry.reason)}
    if (isAvailable(entry)) {
        if (entry.permissions_approved !== true)
            return {kind: "review", text: "Revisar permissões", variant: "secondary", enabled: ctx.hubApprovalAvailable, reason: ctx.hubApprovalAvailable ? "" : blocked}
        var staged = entry.payload_staged === true
        var canInstall = staged && ctx.hubLifecycleAvailable
        return {kind: "install", text: "Instalar pacote verificado", variant: "primary", enabled: canInstall,
            reason: !staged ? "Pacote não verificado em staging: importe pela linha de comando." : (canInstall ? "" : blocked)}
    }
    if (isInstalled(entry, item)) {
        if (!entry) return {kind: "enable", text: "Ativar", variant: "primary", enabled: false, reason: "Indisponível: plugin fora do catálogo."}
        if (entry.permissions_approved !== true)
            return {kind: "review", text: "Revisar permissões", variant: "secondary", enabled: ctx.hubApprovalAvailable, reason: ctx.hubApprovalAvailable ? "" : blocked}
        var stoppedOk = !item || item.state === "disabled" || item.state === "stopped" || item.state === "failed"
        var canEnable = ctx.pluginsAvailable && stoppedOk
        return {kind: "enable", text: "Ativar", variant: "primary", enabled: canEnable, reason: canEnable ? "" : blocked}
    }
    return {kind: "none", text: "", variant: "secondary", enabled: false, reason: ""}
}

// Secondary actions (Avançado): rollback, revoke, remove. Each returns {enabled, reason}.
function rollbackState(record, ctx) {
    if (!ctx.hubLifecycleAvailable) return {enabled: false, reason: ctx.blockedText}
    if (!record || !record.previous || record.state !== "installed") return {enabled: false, reason: "Indisponível: não há versão anterior"}
    return {enabled: true, reason: ""}
}
function revokeState(item, ctx) {
    if (!item) return {enabled: false, reason: "Indisponível: plugin não está no Core"}
    if (item.state === "quarantined") return {enabled: false, reason: "Indisponível: plugin em quarentena"}
    if (!ctx.pluginsAvailable) return {enabled: false, reason: ctx.blockedText}
    return {enabled: true, reason: ""}
}
function removeState(record, ctx) {
    if (!record) return {enabled: false, reason: "Indisponível: plugin não instalado"}
    if (!ctx.hubLifecycleAvailable) return {enabled: false, reason: ctx.blockedText}
    return {enabled: true, reason: ""}
}

// Skills (S4). Primary action per state of the row; the rest of the actions live in the drawer.
function skillPrimary(skill, ctx) {
    var s = skill.state
    var none = {kind: "none", text: "", enabled: false, reason: ""}
    if (!ctx.skillsAvailable) return {kind: "none", text: "", enabled: false, reason: ctx.blockedText}
    if (ctx.busy) return {kind: s === "enabled" ? "run" : "none", text: s === "enabled" ? "Executar" : "", enabled: false, reason: "Aguarde: outra operação de skill em andamento."}
    switch (s) {
    case "enabled":
        if (!ctx.inputsOk) return {kind: "run", text: "Executar", enabled: false, reason: "Entradas inválidas: use um objeto JSON de até 16 KiB."}
        if (ctx.runActive) return {kind: "run", text: "Executar", enabled: false, reason: "Já existe uma skill em execução; aguarde ou cancele."}
        return {kind: "run", text: "Executar", enabled: true, reason: ""}
    case "approved":
    case "disabled":
        return {kind: "enable", text: "Habilitar", enabled: true, reason: ""}
    case "tested":
        return {kind: "approve", text: "Aprovar", enabled: true, reason: ""}
    case "draft":
    case "validated":
    case "revised":
        return {kind: "dry", text: "Simular", enabled: ctx.inputsOk, reason: ctx.inputsOk ? "" : "Entradas inválidas: use um objeto JSON de até 16 KiB."}
    }
    return none
}
function skillStateText(s) { switch (s) { case "draft": return "Rascunho"; case "validated": return "Validada"; case "tested": return "Testada"; case "approved": return "Aprovada"; case "enabled": return "Habilitada"; case "disabled": return "Desabilitada"; case "revised": return "Revisada"; default: return s } }
function skillStateTone(s) { switch (s) { case "enabled": return "success"; case "tested": case "approved": case "validated": return "info"; case "revised": return "warning"; default: return "neutral" } }
function skillSourceText(s) { switch (s) { case "created": return "criada"; case "imported": return "importada (publisher não verificado)"; case "llm_draft": return "rascunho do LLM"; default: return s } }
function exportable(state) { return state === "approved" || state === "enabled" || state === "disabled" }
