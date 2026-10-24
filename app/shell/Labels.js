.pragma library
// Portuguese words for Core states and codes shown in the pages. Pure functions: callers pass the snapshot data in.
// The Core codes themselves go through core.codeMessage in the pages, never through this file.

var stateLabels = {idle: "Em espera", capturing: "Ouvindo", transcribing: "Transcrevendo", executing: "Executando", speaking: "Respondendo", offline: "Core indisponível", safe_mode: "Modo seguro", restart_required: "Reinício necessário"}
var statusLabels = {unavailable: "Indisponível", idle: "Em espera", ready: "Pronto", starting: "Iniciando", replaying: "Reproduzindo", replay_finished: "Reprodução de teste encerrada", failed: "Falhou", completed: "Concluído", speaking: "Respondendo", muted: "Mudo", disabled: "Desligado", cancelled: "Cancelado", timed_out: "Tempo esgotado", audio_error: "Erro de áudio", stt_failed: "Falha na transcrição", stt_unavailable: "Transcrição indisponível", transcript_final: "Transcrição final", capture_completed: "Captura concluída", no_speech: "Sem fala detectada", capture_too_long: "Captura longa demais"}

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

function statusText(status) { return statusLabels[status] || "Indisponível" }
function stateText(state) { return stateLabels[state] || "Erro" }

// Skills (S4): state words; codes go through core.codeMessage.
function skillStateText(s) { switch (s) { case "draft": return "rascunho"; case "validated": return "validada"; case "tested": return "testada"; case "approved": return "aprovada"; case "enabled": return "habilitada"; case "disabled": return "desabilitada"; case "revised": return "revisada"; default: return s } }
function skillSourceText(s) { switch (s) { case "created": return "criada"; case "imported": return "importada (publisher não verificado)"; case "llm_draft": return "rascunho do LLM"; default: return s } }
function skillRunText(s) { switch (s) { case "running": return "executando"; case "awaiting_approval": return "aguardando sua decisão"; case "done": return "concluída"; case "failed": return "falhou"; case "cancelled": return "cancelada"; case "rolled_back": return "revertida"; default: return s } }
function skillStepText(s) { switch (s) { case "pending": return "pendente"; case "running": return "em execução"; case "awaiting_approval": return "aguardando sua decisão"; case "done": return "concluído"; case "failed": return "falhou"; case "denied": return "negado"; case "undone": return "desfeito"; case "cancelled": return "cancelado"; default: return s } }
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

// Connections (S5).
var connProviderChoices = [{id: "github", text: "GitHub"}, {id: "google", text: "Google"}, {id: "homeassistant", text: "Home Assistant"}, {id: "mcp", text: "MCP"}]
function connProviderName(id) { for (var i = 0; i < connProviderChoices.length; i++) if (connProviderChoices[i].id === id) return connProviderChoices[i].text; return id }
function connStatusText(s) { switch (s) { case "disconnected": return "desconectada"; case "connecting": return "conectando (aguardando confirmação)"; case "connected": return "conectada"; case "expired": return "expirada"; case "offline": return "offline"; case "error": return "erro"; case "reauth_required": return "reautenticação necessária"; default: return s } }
function connOpLabel(name) { switch (name) { case "repos.list": return "listar repositórios"; case "repo.get": return "ver repositório"; case "issues.create": return "criar issue"; case "issues.update": return "editar issue"; case "pulls.get": return "ver pull request"; case "pulls.comment": return "comentar pull request"; case "actions.list": return "listar actions"; case "gmail.messages.list": return "listar e-mails"; case "gmail.send": return "enviar e-mail"; case "gmail.messages.delete": return "apagar e-mail"; case "calendar.events.list": return "listar eventos"; case "calendar.events.create": return "criar evento"; case "drive.files.list": return "listar arquivos"; case "drive.files.create": return "criar arquivo"; case "states.list": return "listar estados"; case "state.get": return "ver estado"; case "service.call": return "chamar serviço"; case "mcp.discover": return "listar ferramentas"; case "mcp.call": return "chamar ferramenta (aprovação a cada chamada)"; default: return name } }
function connToolRiskText(r) { return r === "destructive" ? "destrutiva (aprovação forte)" : "escrita (pede aprovação)" }
function connToolStateText(s) { switch (s) { case "trusted": return "confiável"; case "needs_reapproval": return "precisa de nova aprovação"; case "rejected": return "recusada"; default: return s } }
function connRiskText(r) { switch (r) { case "read": return "leitura"; case "write": return "escrita (pede aprovação)"; case "destructive": return "destrutiva (aprovação forte)"; case "public": return "pública (aprovação explícita)"; default: return r } }
function connProvider(list, id) { for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i]; return null }
function connScopeLabel(list, providerId, scope) { var p = connProvider(list, providerId); if (p) for (var i = 0; i < p.scopes.length; i++) if (p.scopes[i].id === scope) return p.scopes[i].label; return scope }
function connScopeNames(list) { return (list && list.length) ? list.join(", ") : "nenhum" }
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
function connOutcomeText(call, codeMessage) { if (call.code) return codeMessage(call.code); return call.outcome === "ok" ? "concluída" : call.outcome }

// Capability registry (S5 E3): route words.
function regRouteText(r) { return r === "connection" ? "API autorizada (conexão)" : r === "visual" ? "Visual (cliques e digitação)" : r }
function regStatusText(s) { switch (s) { case "available": return "disponível"; case "not_connected": return "não conectada"; case "expired": return "expirada ou reautenticação necessária"; case "scope_not_granted": return "escopo não concedido"; case "no_api": return "sem API neste ambiente"; case "visual_not_allowed": return "fallback visual desligado"; case "disabled": return "indisponível"; default: return s } }
function regChosenText(p) { return p.route_chosen ? "rota escolhida: " + regRouteText(p.route_chosen) : "nenhuma rota disponível" }

// Plugins (Hub and Core).
function pluginFor(items, pluginId) { for (var i = 0; i < items.length; i++) if (items[i].plugin_id === pluginId) return items[i]; return null }
function hubEntry(entries, pluginId) { for (var i = 0; i < entries.length; i++) if (entries[i].plugin_id === pluginId) return entries[i]; return null }
function pluginEnabledFor(items, pluginId) { var item = pluginFor(items, pluginId); return !!item && item.enabled === true }
function pluginInstalled(entries, pluginId) { var e = hubEntry(entries, pluginId); return !!e && e.status === "installed" }
function pluginApproved(entries, pluginId) { var e = hubEntry(entries, pluginId); return !!e && e.permissions_approved === true }
function pluginCanEnable(entries, item) { return !item.enabled && (item.state === "disabled" || item.state === "stopped" || item.state === "failed") && pluginInstalled(entries, item.plugin_id) && pluginApproved(entries, item.plugin_id) }
function pluginStateText(item) { switch (item.state) { case "running": return "Ativo (sandbox, sem rede)"; case "starting": return "Iniciando…"; case "failed": return "Falhou: " + (item.last_error || "erro"); case "stopped": return "Parado"; case "quarantined": return "Em quarentena"; default: return "Desativado" } }
function toolStateText(state) { switch (state) { case "pending": return "aguardando sua decisão"; case "authorized": return "autorizada; executando"; case "executed": return "executada"; case "denied": return "negada"; case "failed": return "falhou"; case "expired": return "expirada"; case "cancelled": return "cancelada"; default: return state } }

// C3 agent.
function agentStepText(state) { switch (state) { case "running": return "em execução"; case "done": return "concluído"; case "awaiting_approval": return "aguardando sua decisão"; case "denied": return "negado pelo usuário"; case "failed": return "falhou"; case "stale": return "tela desatualizada"; case "blocked": return "bloqueado"; case "cancelled": return "cancelado"; default: return state } }
function agentRiskText(risk) { switch (risk) { case "read": return "leitura"; case "state_changing": return "muda estado"; case "destructive": return "destrutiva"; default: return "—" } }

// C4 perception.
var perceptionActions = {"screen_observe": [{capability: "screen_observe.capture", label: "Capturar"}, {capability: "screen_observe.status", label: "Estado"}], "computer_control": [{capability: "computer_control.tree", label: "Árvore"}, {capability: "computer_control.status", label: "Estado"}], "audio_advanced": [{capability: "audio_advanced.state", label: "Estado"}], "mic_advanced": [{capability: "mic_advanced.state", label: "Estado"}], "camera_gesture": [{capability: "camera_gesture.state", label: "Estado"}], "display_manipulate": [{capability: "display_manipulate.status", label: "Estado"}]}
function perceptionStateText(state) { return ({running: "em execução", starting: "iniciando", disabled: "desativado", failed: "falhou", stopped: "parado", quarantined: "em quarentena"})[state] || state }
function perceptionStateColor(s) { switch (s) { case "running": return "#78debc"; case "starting": return "#8fb4ff"; case "failed": case "quarantined": return "#ff9a9a"; default: return "#c9d6f5" } }

// Models (C2).
var featureChoices = [{id: "unknown", text: "Desconhecido"}, {id: "supported", text: "Suportado"}, {id: "unsupported", text: "Não suportado"}]
function latencyText(v) { switch (v) { case "low": return "baixa"; case "medium": return "média"; case "high": return "alta"; default: return "desconhecida" } }
function gpuText(v) { switch (v) { case "none": return "não requer"; case "optional": return "opcional"; case "required": return "obrigatória"; default: return "desconhecida" } }
function isCloudProvider(p) { return p === "openrouter" || p === "opencode" || p === "google" || p === "custom" }
function filteredModels(list, filter) { var out = []; for (var i = 0; i < list.length; i++) { var m = list[i]; if (filter === 1 && m.kind !== "local") continue; if (filter === 2 && m.kind !== "cloud") continue; out.push(m) } return out }
function modelById(list, ident) { for (var i = 0; i < list.length; i++) if (list[i].id === ident) return list[i]; return null }

// Voz e Wake: the active phrase and its qualification, read from the Core pack.
function wakeText(pack) { if (!pack.wake_phrases) return "Não configurada"; for (var i = 0; i < pack.wake_phrases.length; i++) if (pack.wake_phrases[i].id === pack.active_phrase) return pack.wake_phrases[i].text; return "Não ativa" }
function activeWake(choices, id) { for (var i = 0; i < choices.length; i++) if (choices[i].id === id) return choices[i]; return null }
