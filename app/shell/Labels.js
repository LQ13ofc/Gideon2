.pragma library
// Words for Core states and codes shown in the pages (Portuguese is the source language; the catalogs are in
// app/translations). Pure functions: callers pass the snapshot data in. The Core codes themselves go through
// core.codeMessage in the pages, never through this file.
// Tables keep their texts behind QT_TR_NOOP (extracted by lupdate, not translated where they are written). Every lookup
// translates at call time with qsTr, so a language switch shows the new words without a restart.

function QT_TR_NOOP(text) { return text }

var stateLabels = {idle: QT_TR_NOOP("Em espera"), capturing: QT_TR_NOOP("Ouvindo"), transcribing: QT_TR_NOOP("Transcrevendo"), executing: QT_TR_NOOP("Executando"), speaking: QT_TR_NOOP("Respondendo"), offline: QT_TR_NOOP("Core indisponível"), safe_mode: QT_TR_NOOP("Modo seguro"), restart_required: QT_TR_NOOP("Reinício necessário")}
var statusLabels = {unavailable: QT_TR_NOOP("Indisponível"), idle: QT_TR_NOOP("Em espera"), ready: QT_TR_NOOP("Pronto"), starting: QT_TR_NOOP("Iniciando"), replaying: QT_TR_NOOP("Reproduzindo"), replay_finished: QT_TR_NOOP("Reprodução de teste encerrada"), failed: QT_TR_NOOP("Falhou"), completed: QT_TR_NOOP("Concluído"), speaking: QT_TR_NOOP("Respondendo"), muted: QT_TR_NOOP("Mudo"), disabled: QT_TR_NOOP("Desligado"), cancelled: QT_TR_NOOP("Cancelado"), timed_out: QT_TR_NOOP("Tempo esgotado"), audio_error: QT_TR_NOOP("Erro de áudio"), stt_failed: QT_TR_NOOP("Falha na transcrição"), stt_unavailable: QT_TR_NOOP("Transcrição indisponível"), transcript_final: QT_TR_NOOP("Transcrição final"), capture_completed: QT_TR_NOOP("Captura concluída"), no_speech: QT_TR_NOOP("Sem fala detectada"), capture_too_long: QT_TR_NOOP("Captura longa demais")}

// Orb and pill state: idle, listening (ripple), thinking, speaking, error.
var orbStateOf = function (state) {
    switch (state) {
    case "capturing": case "transcribing": return "listening"
    case "executing": return "thinking"
    case "speaking": return "speaking"
    case "offline": case "safe_mode": case "restart_required": return "error"
    default: return "idle"
    }
}

function statusText(status) { return statusLabels[status] ? qsTr(statusLabels[status]) : qsTr("Indisponível") }
function stateText(state) { return stateLabels[state] ? qsTr(stateLabels[state]) : qsTr("Erro") }

// Skills (S4): state words; codes go through core.codeMessage.
function skillStateText(s) { switch (s) { case "draft": return qsTr("rascunho"); case "validated": return qsTr("validada"); case "tested": return qsTr("testada"); case "approved": return qsTr("aprovada"); case "enabled": return qsTr("habilitada"); case "disabled": return qsTr("desabilitada"); case "revised": return qsTr("revisada"); default: return s } }
function skillSourceText(s) { switch (s) { case "created": return qsTr("criada"); case "imported": return qsTr("importada (publisher não verificado)"); case "llm_draft": return qsTr("rascunho do LLM"); default: return s } }
function skillRunText(s) { switch (s) { case "running": return qsTr("executando"); case "awaiting_approval": return qsTr("aguardando sua decisão"); case "done": return qsTr("concluída"); case "failed": return qsTr("falhou"); case "cancelled": return qsTr("cancelada"); case "rolled_back": return qsTr("revertida"); default: return s } }
function skillStepText(s) { switch (s) { case "pending": return qsTr("pendente"); case "running": return qsTr("em execução"); case "awaiting_approval": return qsTr("aguardando sua decisão"); case "done": return qsTr("concluído"); case "failed": return qsTr("falhou"); case "denied": return qsTr("negado"); case "undone": return qsTr("desfeito"); case "cancelled": return qsTr("cancelado"); default: return s } }
function skillRunActive(run) { return !!run && (run.state === "running" || run.state === "awaiting_approval") }
function skillCan(busy, action, s, runActive) {
    if (busy) return false
    switch (action) {
    case "approve": return s === "tested"
    case "enable": return s === "approved" || s === "disabled"
    case "disable": return s === "enabled"
    case "export": return s === "approved" || s === "enabled" || s === "disabled"
    case "run": return s === "enabled" && !runActive
    case "dry": case "rollback": case "remove": return true
    }
    return false
}

// Connections (S5). Provider names are brands and stay as they are.
var connProviderChoices = [{id: "github", text: "GitHub"}, {id: "google", text: "Google"}, {id: "homeassistant", text: "Home Assistant"}, {id: "mcp", text: "MCP"}]
function connProviderName(id) { for (var i = 0; i < connProviderChoices.length; i++) if (connProviderChoices[i].id === id) return connProviderChoices[i].text; return id }
function connStatusText(s) { switch (s) { case "disconnected": return qsTr("desconectada"); case "connecting": return qsTr("conectando (aguardando confirmação)"); case "connected": return qsTr("conectada"); case "expired": return qsTr("expirada"); case "offline": return qsTr("offline"); case "error": return qsTr("erro"); case "reauth_required": return qsTr("reautenticação necessária"); default: return s } }
function connOpLabel(name) { switch (name) { case "repos.list": return qsTr("listar repositórios"); case "repo.get": return qsTr("ver repositório"); case "issues.create": return qsTr("criar issue"); case "issues.update": return qsTr("editar issue"); case "pulls.get": return qsTr("ver pull request"); case "pulls.comment": return qsTr("comentar pull request"); case "actions.list": return qsTr("listar actions"); case "gmail.messages.list": return qsTr("listar e-mails"); case "gmail.send": return qsTr("enviar e-mail"); case "gmail.messages.delete": return qsTr("apagar e-mail"); case "calendar.events.list": return qsTr("listar eventos"); case "calendar.events.create": return qsTr("criar evento"); case "drive.files.list": return qsTr("listar arquivos"); case "drive.files.create": return qsTr("criar arquivo"); case "states.list": return qsTr("listar estados"); case "state.get": return qsTr("ver estado"); case "service.call": return qsTr("chamar serviço"); case "mcp.discover": return qsTr("listar ferramentas"); case "mcp.call": return qsTr("chamar ferramenta (aprovação a cada chamada)"); default: return name } }
function connToolRiskText(r) { return r === "destructive" ? qsTr("destrutiva (aprovação forte)") : qsTr("escrita (pede aprovação)") }
function connToolStateText(s) { switch (s) { case "trusted": return qsTr("confiável"); case "needs_reapproval": return qsTr("precisa de nova aprovação"); case "rejected": return qsTr("recusada"); default: return s } }
function connRiskText(r) { switch (r) { case "read": return qsTr("leitura"); case "write": return qsTr("escrita (pede aprovação)"); case "destructive": return qsTr("destrutiva (aprovação forte)"); case "public": return qsTr("pública (aprovação explícita)"); default: return r } }
function connProvider(list, id) { for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i]; return null }
function connScopeLabel(list, providerId, scope) { var p = connProvider(list, providerId); if (p) for (var i = 0; i < p.scopes.length; i++) if (p.scopes[i].id === scope) return p.scopes[i].label; return scope }
function connScopeNames(list) { return (list && list.length) ? list.join(", ") : qsTr("nenhum") }
function connGranted(item, scope) { return (item.granted_scopes || []).indexOf(scope) >= 0 }
function connCan(busy, action, item) {
    if (busy) return false
    var s = item.status
    switch (action) {
    case "connect": return s === "disconnected" || s === "error" || s === "offline" || s === "expired" || s === "reauth_required"
    case "refresh": return item.provider !== "mcp" && (s === "connected" || s === "expired" || s === "reauth_required" || s === "error")
    case "disconnect": return s === "connected" || s === "connecting" || (item.provider === "mcp" && s === "error") || s === "expired" || s === "reauth_required"
    case "revoke": return s === "connected" || s === "expired" || s === "reauth_required"
    case "remove": return s !== "connecting"
    }
    return false
}
// Date of a grant (Unix ms from the Core) as dd/mm/aaaa in local time; '' when the Core has no date for it.
function grantedDate(ms) {
    if (typeof ms !== "number" || !(ms > 0)) return ""
    var d = new Date(ms)
    var pad = function (n) { return (n < 10 ? "0" : "") + n }
    return pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + "/" + d.getFullYear()
}
function connCanTest(busy, item, op) { return !busy && item.status === "connected" && op.risk === "read" && connGranted(item, op.scope) }
function connOutcomeText(call, codeMessage) { if (call.code) return codeMessage(call.code); return call.outcome === "ok" ? qsTr("concluída") : call.outcome }

// Capability registry (S5 E3): route words.
function regRouteText(r) { return r === "connection" ? qsTr("API autorizada (conexão)") : r === "visual" ? qsTr("Visual (cliques e digitação)") : r }
function regStatusText(s) { switch (s) { case "available": return qsTr("disponível"); case "not_connected": return qsTr("não conectada"); case "expired": return qsTr("expirada ou reautenticação necessária"); case "scope_not_granted": return qsTr("escopo não concedido"); case "no_api": return qsTr("sem API neste ambiente"); case "visual_not_allowed": return qsTr("fallback visual desligado"); case "disabled": return qsTr("indisponível"); default: return s } }
function regChosenText(p) { return p.route_chosen ? qsTr("rota escolhida: %1").arg(regRouteText(p.route_chosen)) : qsTr("nenhuma rota disponível") }

// Plugins (Hub and Core).
function pluginFor(items, pluginId) { for (var i = 0; i < items.length; i++) if (items[i].plugin_id === pluginId) return items[i]; return null }
function hubEntry(entries, pluginId) { for (var i = 0; i < entries.length; i++) if (entries[i].plugin_id === pluginId) return entries[i]; return null }
function pluginEnabledFor(items, pluginId) { var item = pluginFor(items, pluginId); return !!item && item.enabled === true }
function pluginInstalled(entries, pluginId) { var e = hubEntry(entries, pluginId); return !!e && e.status === "installed" }
function pluginApproved(entries, pluginId) { var e = hubEntry(entries, pluginId); return !!e && e.permissions_approved === true }
function pluginCanEnable(entries, item) { return !item.enabled && (item.state === "disabled" || item.state === "stopped" || item.state === "failed") && pluginInstalled(entries, item.plugin_id) && pluginApproved(entries, item.plugin_id) }
function pluginStateText(item) { switch (item.state) { case "running": return qsTr("Ativo (sandbox, sem rede)"); case "starting": return qsTr("Iniciando…"); case "failed": return qsTr("Falhou: %1").arg(item.last_error || qsTr("erro")); case "stopped": return qsTr("Parado"); case "quarantined": return qsTr("Em quarentena"); default: return qsTr("Desativado") } }
function toolStateText(state) { switch (state) { case "pending": return qsTr("aguardando sua decisão"); case "authorized": return qsTr("autorizada; executando"); case "executed": return qsTr("executada"); case "denied": return qsTr("negada"); case "failed": return qsTr("falhou"); case "expired": return qsTr("expirada"); case "cancelled": return qsTr("cancelada"); default: return state } }

// C3 agent.
function agentStepText(state) { switch (state) { case "running": return qsTr("em execução"); case "done": return qsTr("concluído"); case "awaiting_approval": return qsTr("aguardando sua decisão"); case "denied": return qsTr("negado pelo usuário"); case "failed": return qsTr("falhou"); case "stale": return qsTr("tela desatualizada"); case "blocked": return qsTr("bloqueado"); case "cancelled": return qsTr("cancelado"); default: return state } }
function agentRiskText(risk) { switch (risk) { case "read": return qsTr("leitura"); case "state_changing": return qsTr("muda estado"); case "destructive": return qsTr("destrutiva"); default: return "—" } }

// C4 perception. A function, so the labels are translated when the page asks for them.
function perceptionActions() {
    return {"screen_observe": [{capability: "screen_observe.capture", label: qsTr("Capturar")}, {capability: "screen_observe.status", label: qsTr("Estado")}], "computer_control": [{capability: "computer_control.tree", label: qsTr("Árvore")}, {capability: "computer_control.status", label: qsTr("Estado")}], "audio_advanced": [{capability: "audio_advanced.state", label: qsTr("Estado")}], "mic_advanced": [{capability: "mic_advanced.state", label: qsTr("Estado")}], "camera_gesture": [{capability: "camera_gesture.state", label: qsTr("Estado")}], "display_manipulate": [{capability: "display_manipulate.status", label: qsTr("Estado")}]}
}
function perceptionStateText(state) { var words = {running: qsTr("em execução"), starting: qsTr("iniciando"), disabled: qsTr("desativado"), failed: qsTr("falhou"), stopped: qsTr("parado"), quarantined: qsTr("em quarentena")}; return words[state] || state }
function perceptionStateColor(s) { switch (s) { case "running": return "#78debc"; case "starting": return "#8fb4ff"; case "failed": case "quarantined": return "#ff9a9a"; default: return "#c9d6f5" } }

// Models (C2). A function: the choices are translated when the page builds its list.
function featureChoices() { return [{id: "unknown", text: qsTr("Desconhecido")}, {id: "supported", text: qsTr("Suportado")}, {id: "unsupported", text: qsTr("Não suportado")}] }
function latencyText(v) { switch (v) { case "low": return qsTr("baixa"); case "medium": return qsTr("média"); case "high": return qsTr("alta"); default: return qsTr("desconhecida") } }
function gpuText(v) { switch (v) { case "none": return qsTr("não requer"); case "optional": return qsTr("opcional"); case "required": return qsTr("obrigatória"); default: return qsTr("desconhecida") } }
function isCloudProvider(p) { return p === "openrouter" || p === "opencode" || p === "google" || p === "custom" }
function filteredModels(list, filter) { var out = []; for (var i = 0; i < list.length; i++) { var m = list[i]; if (filter === 1 && m.kind !== "local") continue; if (filter === 2 && m.kind !== "cloud") continue; out.push(m) } return out }
function modelById(list, ident) { for (var i = 0; i < list.length; i++) if (list[i].id === ident) return list[i]; return null }

// Voz e Wake: the active phrase and its qualification, read from the Core pack.
function wakeText(pack) { if (!pack.wake_phrases) return qsTr("Não configurada"); for (var i = 0; i < pack.wake_phrases.length; i++) if (pack.wake_phrases[i].id === pack.active_phrase) return pack.wake_phrases[i].text; return qsTr("Não ativa") }
function activeWake(choices, id) { for (var i = 0; i < choices.length; i++) if (choices[i].id === id) return choices[i]; return null }
// Input limits are in UTF-8 bytes (Core rule), not characters: the counters under the text fields use this.
function utf8Bytes(text) { var n = 0; for (var i = 0; i < text.length; i++) { var c = text.charCodeAt(i); if (c < 0x80) n += 1; else if (c < 0x800) n += 2; else if (c >= 0xD800 && c <= 0xDBFF) { n += 4; i++ } else n += 3 } return n }
function byteCounter(text, limit) { return qsTr("%1/%2 bytes").arg(utf8Bytes(text)).arg(limit) }
