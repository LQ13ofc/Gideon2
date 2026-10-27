.pragma library
// Event kind -> phrase. Single source: docs/ui-spec/50-diagnostico.md §4 (phrase, category, A/P/E flags).
// Permissões › Auditoria reads the P flag, its origin column (Plugin · Skill · Conexão · Comando, docs/ui-spec/30-permissoes.md
// §7.6, decision D6) and its Resultado column (30 §7.6). Rows marked "30" come from 30-permissoes §7.6 only: the Core emits
// them, 50 does not list them. The raw kind never reaches the screen; an unknown kind is shown as UNKNOWN_PHRASE.
// Portuguese is the source language: every phrase is QT_TR_NOOP here and translated at read time with qsTr, so a language
// switch shows the new words without a restart (docs/I18N_GLOSSARY.md, rule 2).
// Row: [kind, phrase ("" = never shown), category key (50 filter), A (Atividade), P (Auditoria), E (Últimos erros),
//       origin key (Auditoria), result key (none | done | failed | denied | rejected | cancelled)]

function QT_TR_NOOP(text) { return text }

var UNKNOWN_PHRASE = QT_TR_NOOP("Evento do Core sem descrição")
var UNKNOWN_ORIGIN = "core"

var rows = [
    ["session_started", QT_TR_NOOP("Sessão de voz iniciada"), "command", true, true, false, "command", "none"],
    ["transcript_partial", "", "", false, false, false, "command", "none"],
    ["transcript_final", QT_TR_NOOP("Fala reconhecida"), "command", true, true, false, "command", "none"],
    ["capture_completed", QT_TR_NOOP("Captura de fala concluída"), "command", true, true, false, "command", "none"],
    ["no_speech", QT_TR_NOOP("Nenhuma fala detectada"), "command", true, true, false, "command", "none"],
    ["capture_too_long", QT_TR_NOOP("Captura longa demais"), "command", true, true, true, "command", "failed"],
    ["cancelled", QT_TR_NOOP("Sessão cancelada"), "command", true, true, false, "command", "cancelled"],
    ["timed_out", QT_TR_NOOP("Tempo esgotado na sessão de voz"), "command", true, true, true, "command", "failed"],
    ["audio_error", QT_TR_NOOP("Erro de áudio na captura"), "command", true, true, true, "command", "failed"],
    ["stt_failed", QT_TR_NOOP("Falha na transcrição"), "command", true, true, true, "command", "failed"],
    ["stt_unavailable", QT_TR_NOOP("Transcrição indisponível"), "command", true, true, true, "command", "failed"],
    ["speech_started", QT_TR_NOOP("Resposta em voz iniciada"), "command", true, true, false, "command", "none"],
    ["speech_completed", QT_TR_NOOP("Resposta em voz concluída"), "command", true, true, false, "command", "none"],
    ["tts_failed", QT_TR_NOOP("Falha na resposta em voz"), "command", true, true, true, "command", "failed"],
    ["wake_failed", QT_TR_NOOP("Falha na detecção da frase de despertar"), "plugin", false, true, true, "plugin", "failed"],
    ["command_authorized", QT_TR_NOOP("Comando autorizado"), "command", true, true, false, "command", "none"],
    ["command_success", QT_TR_NOOP("Comando concluído com efeito verificado"), "command", true, true, false, "command", "done"],
    ["command_failed", QT_TR_NOOP("Comando não concluído: efeito não verificado"), "command", true, true, true, "command", "failed"],
    ["tool_proposed", QT_TR_NOOP("Ferramenta proposta; aguarda sua decisão"), "command", true, true, false, "command", "none"],
    ["tool_authorized", QT_TR_NOOP("Ferramenta autorizada por você"), "command", true, true, false, "command", "none"],
    ["tool_denied", QT_TR_NOOP("Ferramenta negada"), "command", true, true, false, "command", "denied"],
    ["tool_executed", QT_TR_NOOP("Ferramenta executada"), "command", true, true, false, "command", "done"],
    ["tool_failed", QT_TR_NOOP("Ferramenta falhou"), "command", true, true, true, "command", "failed"],
    ["agent_started", QT_TR_NOOP("Agente iniciado"), "agent", true, true, false, "command", "none"],
    ["agent_step", QT_TR_NOOP("Passo do agente"), "agent", true, true, false, "command", "none"],
    ["agent_tool", QT_TR_NOOP("Ferramenta usada pelo agente"), "agent", true, true, false, "command", "none"],
    ["agent_done", QT_TR_NOOP("Agente concluiu"), "agent", true, true, false, "command", "done"],
    ["agent_failed", QT_TR_NOOP("Agente falhou"), "agent", true, true, true, "command", "failed"],
    ["agent_aborted", QT_TR_NOOP("Agente abortado"), "agent", true, true, false, "command", "none"],
    ["agent_blocked", QT_TR_NOOP("Agente bloqueado"), "agent", true, true, true, "command", "rejected"],
    ["skill_validated", QT_TR_NOOP("Skill validada"), "skill", true, true, false, "skill", "done"],
    ["skill_approved", QT_TR_NOOP("Skill aprovada"), "skill", true, true, false, "skill", "done"],
    ["skill_enabled", QT_TR_NOOP("Skill habilitada"), "skill", true, true, false, "skill", "done"],
    ["skill_run_started", QT_TR_NOOP("Execução de skill iniciada"), "skill", true, true, false, "skill", "none"],
    ["skill_step", QT_TR_NOOP("Passo de skill executado"), "skill", true, true, false, "skill", "none"],
    ["skill_run_done", QT_TR_NOOP("Execução de skill concluída"), "skill", true, true, false, "skill", "done"],
    ["skill_run_failed", QT_TR_NOOP("Execução de skill falhou"), "skill", true, true, true, "skill", "failed"],
    ["skill_rolled_back", QT_TR_NOOP("Skill voltou à versão anterior"), "skill", true, true, false, "skill", "none"],
    ["skill_service_denied", QT_TR_NOOP("Skill bloqueada: serviço não permitido"), "skill", true, true, false, "skill", "rejected"],
    ["skill_plugin_validate", QT_TR_NOOP("Validação de skill pelo plugin"), "skill", true, false, false, "skill", "done"],
    ["skill_plugin_dry_run", QT_TR_NOOP("Simulação de skill pelo plugin"), "skill", true, false, false, "skill", "done"],
    ["skill_plugin_list", QT_TR_NOOP("Lista de skills do plugin consultada"), "skill", true, false, false, "skill", "none"],
    ["skill_draft_put", QT_TR_NOOP("Rascunho de skill salvo"), "skill", true, true, false, "skill", "done"],
    ["skill_exported", QT_TR_NOOP("Skill exportada"), "skill", true, true, false, "skill", "done"],
    ["skill_import_previewed", QT_TR_NOOP("Prévia de importação de skill"), "skill", true, true, false, "skill", "none"],
    ["skill_imported", QT_TR_NOOP("Skill importada como rascunho"), "skill", true, true, false, "skill", "done"],
    ["hub_import_started", QT_TR_NOOP("Importação de pacote iniciada"), "plugin", false, true, false, "plugin", "none"],
    ["hub_payload_staged", QT_TR_NOOP("Pacote verificado e guardado; não instalado"), "plugin", false, true, false, "plugin", "done"],
    ["hub_import_cancelled", QT_TR_NOOP("Importação de pacote cancelada"), "plugin", false, true, false, "plugin", "none"],
    ["hub_import_timeout", QT_TR_NOOP("Importação de pacote expirou"), "plugin", false, true, true, "plugin", "failed"],
    ["hub_permissions_approved", QT_TR_NOOP("Permissões do plugin aprovadas"), "plugin", false, true, false, "plugin", "done"],
    ["hub_plugin_installed", QT_TR_NOOP("Plugin instalado (desativado)"), "plugin", false, true, false, "plugin", "done"],
    ["hub_plugin_updated", QT_TR_NOOP("Plugin atualizado (desativado)"), "plugin", false, true, false, "plugin", "done"],
    ["hub_plugin_rolled_back", QT_TR_NOOP("Plugin voltou à versão anterior"), "plugin", false, true, false, "plugin", "done"],
    ["hub_plugin_removed", QT_TR_NOOP("Plugin removido"), "plugin", false, true, false, "plugin", "done"],
    ["hub_staged_discarded", QT_TR_NOOP("Pacote guardado descartado"), "plugin", false, true, false, "plugin", "none"],
    ["plugin_enabled", QT_TR_NOOP("Plugin ativado (sandbox, sem rede)"), "plugin", false, true, false, "plugin", "done"],
    ["plugin_disabled", QT_TR_NOOP("Plugin desativado"), "plugin", false, true, false, "plugin", "none"],
    ["plugin_revoked", QT_TR_NOOP("Permissões do plugin revogadas"), "plugin", false, true, false, "plugin", "done"],
    ["plugin_started", QT_TR_NOOP("Plugin iniciado"), "plugin", true, true, false, "plugin", "none"],
    ["plugin_stopped", QT_TR_NOOP("Plugin parado"), "plugin", true, true, false, "plugin", "none"],
    ["plugin_failed", QT_TR_NOOP("Plugin falhou"), "plugin", true, true, true, "plugin", "failed"],
    ["plugin_log", "", "", false, false, false, "plugin", "none"],
    ["capability_invoked", QT_TR_NOOP("Capacidade invocada"), "plugin", true, true, false, "plugin", "none"],
    ["capability_partial", QT_TR_NOOP("Resposta parcial recebida"), "plugin", true, true, false, "plugin", "none"],
    ["llm_fallback_used", QT_TR_NOOP("Modelo de reserva respondeu"), "plugin", true, true, false, "plugin", "none"],
    ["llm_configured", QT_TR_NOOP("Motor LLM configurado"), "config", false, true, false, "plugin", "done"],
    ["llm_marked_good", QT_TR_NOOP("Configuração do motor marcada como boa"), "config", false, true, false, "plugin", "done"],
    ["llm_rolled_back", QT_TR_NOOP("Motor LLM voltou à configuração anterior"), "config", false, true, false, "plugin", "done"],
    ["secret_set", QT_TR_NOOP("Chave de provedor salva"), "config", false, true, false, "plugin", "done"],
    ["secret_cleared", QT_TR_NOOP("Chave de provedor removida"), "config", false, true, false, "plugin", "done"],
    ["preferences_updated", QT_TR_NOOP("Preferências salvas"), "config", false, true, false, "command", "done"],
    ["live_audio_enabled", QT_TR_NOOP("Escuta do microfone ligada (vale após reiniciar o Core)"), "config", false, true, false, "command", "done"],
    ["live_audio_disabled", QT_TR_NOOP("Escuta do microfone desligada (vale após reiniciar o Core)"), "config", false, true, false, "command", "done"],
    ["configuration_recovered", QT_TR_NOOP("Configuração recuperada; reinício necessário"), "config", false, true, true, "command", "done"],
    ["connection_added", QT_TR_NOOP("Conta adicionada"), "connection", false, true, false, "connection", "done"],
    ["connection_connected", QT_TR_NOOP("Conta conectada"), "connection", false, true, false, "connection", "done"],
    ["connection_consented", QT_TR_NOOP("Escopo concedido"), "connection", false, true, false, "connection", "done"],
    ["connection_refreshed", QT_TR_NOOP("Acesso renovado"), "connection", false, true, false, "connection", "done"],
    ["connection_expired", QT_TR_NOOP("Acesso expirou"), "connection", false, true, true, "connection", "none"],
    ["connection_disconnected", QT_TR_NOOP("Conta desconectada"), "connection", false, true, false, "connection", "done"],
    ["connection_revoked", QT_TR_NOOP("Acesso revogado"), "connection", false, true, false, "connection", "done"],
    ["connection_removed", QT_TR_NOOP("Conta removida"), "connection", false, true, false, "connection", "done"],
    ["connection_trusted", QT_TR_NOOP("Ferramentas da conta confiadas"), "connection", false, true, false, "connection", "done"],
    ["connection_call", QT_TR_NOOP("Chamada a conta registrada"), "connection", true, true, false, "connection", "none"],
    ["registry_visual_allowed", QT_TR_NOOP("Fallback visual permitido"), "connection", false, true, false, "connection", "done"],
    ["registry_visual_revoked", QT_TR_NOOP("Fallback visual revogado"), "connection", false, true, false, "connection", "done"],
    ["registry_visual_run", QT_TR_NOOP("Ação visual executada"), "connection", true, true, false, "connection", "none"],
    ["screen_capture", QT_TR_NOOP("Captura de tela (percepção)"), "perception", false, true, false, "plugin", "none"],
    ["input_action", QT_TR_NOOP("Ação de teclado ou mouse"), "perception", false, true, false, "plugin", "none"],
    ["audio_action", QT_TR_NOOP("Ação de áudio"), "perception", false, true, false, "plugin", "none"],
    ["mic_action", QT_TR_NOOP("Ação de microfone"), "perception", false, true, false, "plugin", "none"],
    ["camera_action", QT_TR_NOOP("Ação de câmera"), "perception", false, true, false, "plugin", "none"],
    ["synthetic_action", QT_TR_NOOP("Ação simulada (sem hardware real)"), "perception", false, true, false, "plugin", "none"],
    // Only in docs/ui-spec/30-permissoes.md §7.6 (the Core emits them; 50 does not list them).
    ["command_denied", QT_TR_NOOP("Comando negado"), "command", true, true, false, "command", "denied"],
    ["command_rejected", QT_TR_NOOP("Comando recusado"), "command", true, true, false, "command", "rejected"],
    ["preferences_storage_error", QT_TR_NOOP("Falha ao salvar preferências"), "config", false, true, true, "command", "failed"],
    ["configuration_recovery_error", QT_TR_NOOP("Falha ao recuperar a configuração"), "config", false, true, true, "command", "failed"]
]

// Suffixes of agent_blocked:<motivo> (50 §4, EV-R1 and the row note).
var suffixText = {
    loop_blocked: QT_TR_NOOP("o modelo repetiu a mesma ação"),
    stale_screen: QT_TR_NOOP("a tela mudou desde a observação")
}

var table = {}
for (var i = 0; i < rows.length; i++) {
    var r = rows[i]
    table[r[0]] = {kind: r[0], phrase: r[1], cat: r[2], a: r[3], p: r[4], e: r[5], origin: r[6], result: r[7]}
}

// The table entry for a kind, or null when the Core sent a kind the table does not know. A kind with a suffix
// (agent_blocked:loop_blocked) is looked up by the part before the colon.
function entry(kind) {
    if (typeof kind !== "string" || kind.length === 0) return null
    var base = kind.split(":")[0]
    return table[base] || null
}

// Phrase: the base phrase, then " · <motivo>" for the suffixes that have one (50 EV-R1). Empty when the table hides the kind.
function phrase(kind) {
    var e = entry(kind)
    if (!e) return qsTr(UNKNOWN_PHRASE)
    if (e.phrase.length === 0) return ""
    var colon = String(kind).indexOf(":")
    if (colon < 0) return qsTr(e.phrase)
    var suffix = String(kind).substring(colon + 1)
    if (e.kind === "agent_blocked")
        return qsTr("%1 · %2").arg(qsTr(e.phrase)).arg(suffixText[suffix] ? qsTr(suffixText[suffix]) : qsTr("motivo não informado"))
    return qsTr(e.phrase)
}

// Category names (the filter keys of the table) as the user reads them.
function categoryName(key) {
    switch (key) {
    case "command": return qsTr("Comando")
    case "agent": return qsTr("Agente")
    case "skill": return qsTr("Skill")
    case "plugin": return qsTr("Plugin")
    case "config": return qsTr("Configuração")
    case "connection": return qsTr("Conexão")
    case "perception": return qsTr("Percepção")
    case "core": return qsTr("Core")
    }
    return key
}

// Origin key of the Auditoria filter: command | plugin | skill | connection | config | perception | agent (decision D6).
// Unknown kinds: core.
function originKey(kind) {
    var e = entry(kind)
    return e ? e.origin : UNKNOWN_ORIGIN
}
// Origin column as the user reads it.
function origin(kind) { return categoryName(originKey(kind)) }

// Result key: none | done | failed | denied | rejected | cancelled. "none" is the table's "—" (no result, not a failure).
function resultKey(kind) {
    var e = entry(kind)
    return e ? e.result : "none"
}
// Resultado column as the user reads it. "—" when the event has no result (that is not a failure).
function resultName(key) {
    switch (key) {
    case "done": return qsTr("Concluído")
    case "failed": return qsTr("Falhou")
    case "denied": return qsTr("Negado")
    case "rejected": return qsTr("Recusado")
    case "cancelled": return qsTr("Cancelado")
    }
    return "—"
}
function result(kind) { return resultName(resultKey(kind)) }

// A kind is listed in Permissões › Auditoria when the table marks it P. Unknown kinds are listed (shown as UNKNOWN_PHRASE).
function inAudit(kind) {
    var e = entry(kind)
    if (!e) return true
    return e.p === true && e.phrase.length > 0
}

// ---- Diagnóstico (docs/ui-spec/50-diagnostico.md §2-3, §5-8). Added beside the Auditoria table above; the table is not
// changed. Names used by the Diagnóstico pages: eventPhrase, codePhrase, originLabel, eventArea, isErrorKind, clockText,
// the state/tone helpers and the pack labels.

// Frase de evento para Diagnóstico (EV-R1, EV-R2): "" quando o tipo não é exibido ou é desconhecido.
function eventPhrase(kind, outcome) {
    var text = phrase(kind)
    return text === qsTr(UNKNOWN_PHRASE) ? "" : text
}

// Linha de Últimos erros (50 §5.6, R-S1): tipo com a coluna E marcada.
function isErrorKind(kind) {
    var e = entry(kind)
    return !!e && e.e === true && e.phrase.length > 0
}

// Área de uma linha (50 §5.6 S27). Fala e captura = Voz; wake = Motores; LLM = Motor LLM; o resto segue a categoria.
var originLabels = {core: QT_TR_NOOP("Comando"), speech: QT_TR_NOOP("Voz"), tool: QT_TR_NOOP("Ferramenta"), agent: QT_TR_NOOP("Agente"), skill: QT_TR_NOOP("Skill"), plugin: QT_TR_NOOP("Plugin"), hub: QT_TR_NOOP("Plugin"), llm: QT_TR_NOOP("Motor LLM"), config: QT_TR_NOOP("Configuração"), connection: QT_TR_NOOP("Conexão"), registry: QT_TR_NOOP("Conexão")}
function originLabel(origin) { return originLabels.hasOwnProperty(origin) ? qsTr(originLabels[origin]) : qsTr("Comando") }
function eventArea(kind, origin) {
    var base = String(kind || "").split(":")[0]
    if (base === "wake_failed") return qsTr("Motores")
    if (base.indexOf("llm_") === 0) return qsTr("Motor LLM")
    if (/^(stt_|tts_|speech_|transcript_|capture_|no_speech|audio_error)/.test(base)) return qsTr("Voz")
    var e = entry(base)
    if (e && e.cat) return categoryName(e.cat)
    return originLabel(origin)
}

// Relógio HH:MM:SS (24 h) de um instante Unix em ms; "—" sem dado (EV-R3).
function clockText(ms) {
    var n = Number(ms)
    if (!n || n <= 0) return "—"
    var d = new Date(n)
    function two(v) { return v < 10 ? "0" + v : "" + v }
    return two(d.getHours()) + ":" + two(d.getMinutes()) + ":" + two(d.getSeconds())
}

// Tabela de códigos (50 §3.3, §3.4, §3.6). Código sem frase: "Core recusou a ação." (R-03); o código vai só para Avançado.
var codeTable = {
    plugin_crashed: QT_TR_NOOP("Plugin encerrou com falha"),
    plugin_not_runnable: QT_TR_NOOP("Plugin não pode ser executado"),
    plugin_cpu_exceeded: QT_TR_NOOP("Plugin passou do limite de processamento"),
    plugin_output_invalid: QT_TR_NOOP("Plugin devolveu uma resposta inválida"),
    plugin_start_failed: QT_TR_NOOP("Plugin não conseguiu iniciar"),
    plugin_quarantined: QT_TR_NOOP("Plugin em quarentena"),
    handshake_timeout: QT_TR_NOOP("Plugin não respondeu ao iniciar"),
    handshake_mismatch: QT_TR_NOOP("Plugin não é a versão esperada"),
    ledger_missing: QT_TR_NOOP("Registro de instalação ausente"),
    ledger_invalid: QT_TR_NOOP("Registro de instalação inválido"),
    hub_import_busy: QT_TR_NOOP("Importação do catálogo em andamento"),
    hub_storage_error: QT_TR_NOOP("Falha ao gravar o registro do catálogo."),
    plugin_storage_error: QT_TR_NOOP("Falha ao gravar o registro dos plugins."),
    preferences_storage_error: QT_TR_NOOP("Falha ao gravar as preferências."),
    preferences_unavailable: QT_TR_NOOP("Preferências indisponíveis no momento."),
    configuration_not_ready: QT_TR_NOOP("Configuração ainda não está pronta."),
    hub_import_timeout: QT_TR_NOOP("Importação expirou antes de terminar."),
    busy: QT_TR_NOOP("Core ocupado; tente novamente em instantes"),
    input_disabled: QT_TR_NOOP("Entrada de texto indisponível no momento"),
    no_lkg: QT_TR_NOOP("Não há configuração anterior salva para restaurar"),
    stale_llm_revision: QT_TR_NOOP("Configuração do motor mudou; reabra o diálogo"),
    stale_hub_revision: QT_TR_NOOP("Catálogo mudou; atualize e tente de novo"),
    stale_plugin_revision: QT_TR_NOOP("Estado do plugin mudou; atualize e tente de novo"),
    llm_storage_error: QT_TR_NOOP("Falha ao gravar a configuração do motor"),
    secrets_storage_error: QT_TR_NOOP("Falha ao gravar o cofre de chaves"),
    virtual_input_disabled: QT_TR_NOOP("Entrada de teste não ativa no Core"),
    unknown_capability: QT_TR_NOOP("Capacidade do motor LLM desconhecida"),
    capability_timeout: QT_TR_NOOP("Plugin não respondeu no prazo"),
    timed_out: QT_TR_NOOP("Tempo esgotado")
}
var fallbackCodePhrase = QT_TR_NOOP("Core recusou a ação.")
function codePhrase(code) {
    var key = String(code || "")
    return codeTable.hasOwnProperty(key) ? qsTr(codeTable[key]) : qsTr(fallbackCodePhrase)
}

// Estados de motor, sessão, configuração e plugin (50 §3.1–3.3).
var wakeLabels = {unavailable: QT_TR_NOOP("Indisponível"), starting: QT_TR_NOOP("Iniciando"), replaying: QT_TR_NOOP("Reproduzindo"), replay_finished: QT_TR_NOOP("Reprodução de teste encerrada"), failed: QT_TR_NOOP("Falhou")}
var sttLabels = {unavailable: QT_TR_NOOP("Indisponível"), starting: QT_TR_NOOP("Iniciando"), ready: QT_TR_NOOP("Pronto"), failed: QT_TR_NOOP("Falhou")}
var speechLabels = {unavailable: QT_TR_NOOP("Indisponível"), idle: QT_TR_NOOP("Em espera"), speaking: QT_TR_NOOP("Respondendo"), completed: QT_TR_NOOP("Concluído"), failed: QT_TR_NOOP("Falhou"), muted: QT_TR_NOOP("Mudo"), disabled: QT_TR_NOOP("Desligado"), cancelled: QT_TR_NOOP("Cancelado"), timed_out: QT_TR_NOOP("Tempo esgotado"), audio_error: QT_TR_NOOP("Erro de áudio"), stt_failed: QT_TR_NOOP("Falha na transcrição"), stt_unavailable: QT_TR_NOOP("Transcrição indisponível"), transcript_final: QT_TR_NOOP("Transcrição final"), capture_completed: QT_TR_NOOP("Captura concluída"), no_speech: QT_TR_NOOP("Sem fala detectada"), capture_too_long: QT_TR_NOOP("Captura longa demais")}
var sessionLabels = {idle: QT_TR_NOOP("Em espera"), capturing: QT_TR_NOOP("Ouvindo"), transcribing: QT_TR_NOOP("Transcrevendo"), executing: QT_TR_NOOP("Executando"), speaking: QT_TR_NOOP("Respondendo"), safe_mode: QT_TR_NOOP("Modo seguro"), restart_required: QT_TR_NOOP("Reinício necessário")}
var configLabels = {ready: QT_TR_NOOP("Pronta"), safe_mode: QT_TR_NOOP("Modo seguro"), restart_required: QT_TR_NOOP("Reinício necessário")}
var pluginStateLabels = {disabled: QT_TR_NOOP("Desativado"), starting: QT_TR_NOOP("Iniciando"), running: QT_TR_NOOP("Ativo (sandbox, sem rede)"), failed: QT_TR_NOOP("Falhou"), stopped: QT_TR_NOOP("Parado"), quarantined: QT_TR_NOOP("Em quarentena")}
function wakePhrase(status) { return wakeLabels.hasOwnProperty(status) ? qsTr(wakeLabels[status]) : qsTr("Indisponível") }
function sttPhrase(status) { return sttLabels.hasOwnProperty(status) ? qsTr(sttLabels[status]) : qsTr("Indisponível") }
function speechPhrase(status) { return speechLabels.hasOwnProperty(status) ? qsTr(speechLabels[status]) : qsTr("Indisponível") }
function sessionPhrase(state) { return sessionLabels.hasOwnProperty(state) ? qsTr(sessionLabels[state]) : qsTr("Core desconectado") }
function configPhrase(status) { return configLabels.hasOwnProperty(status) ? qsTr(configLabels[status]) : qsTr("Indisponível") }
function pluginStatePhrase(state) { return pluginStateLabels.hasOwnProperty(state) ? qsTr(pluginStateLabels[state]) : qsTr("Desativado") }

// Tom do selo (Badge.tone): success | warning | error | info | neutral. Cor e palavra juntas (A11-04).
var toneTable = {
    unavailable: "neutral", starting: "info", replaying: "info", replay_finished: "neutral", failed: "error",
    ready: "success", idle: "neutral", speaking: "info", completed: "success", muted: "neutral", disabled: "neutral",
    cancelled: "neutral", timed_out: "error", audio_error: "error", stt_failed: "error", stt_unavailable: "warning",
    transcript_final: "neutral", capture_completed: "neutral", no_speech: "warning", capture_too_long: "warning",
    capturing: "info", transcribing: "info", executing: "info",
    safe_mode: "error", restart_required: "warning", running: "success", stopped: "neutral", quarantined: "error",
    offline: "neutral"
}
function toneOf(code) { return toneTable[code] || "neutral" }

// Pacote de voz (base_pack do Core). ID sem mapeamento: texto de fallback, nunca o ID no Básico (R-M1).
var scopeLabels = {dev_virtual_en: QT_TR_NOOP("Desenvolvimento · áudio virtual · inglês")}
// Chaves = família do ID (sem caminho e sem versão): "pocket-tts-3.3.0/english_2026-09/cpu" -> "pocket-tts".
var packLabels = {"base-en-dev-v1": QT_TR_NOOP("Base de voz virtual"), "base-voz-virtual": QT_TR_NOOP("Base de voz virtual")}
var engineLabels = {"wake-replay": QT_TR_NOOP("detector de frase de teste"), "sherpa-onnx": QT_TR_NOOP("sherpa-onnx"), "moonshine": QT_TR_NOOP("moonshine"), "moonshine-voice": QT_TR_NOOP("moonshine"), "moonshine-en": QT_TR_NOOP("moonshine"), "pocket-tts": QT_TR_NOOP("Pocket TTS")}
var languageLabels = {en: QT_TR_NOOP("inglês")}
var audioInputLabels = {virtual_pcm: QT_TR_NOOP("PCM virtual")}
var audioOutputLabels = {virtual: QT_TR_NOOP("virtual")}
var wakeQualificationLabels = {dev_qualified: QT_TR_NOOP("qualificada em corpus sintético; microfone real não validado"), poc_required: QT_TR_NOOP("não ativado: precisa de gravações da sua voz")}
function scopeLabel(scope) { return scopeLabels.hasOwnProperty(scope) ? qsTr(scopeLabels[scope]) : "" }
function packLabel(id) { return packLabels.hasOwnProperty(id) ? qsTr(packLabels[id]) : qsTr("Pacote de voz da Base") }
function engineFamily(id) { return String(id || "").split("/")[0].replace(/-\d[\d.]*$/, "") }
function engineLabel(id) {
    var key = engineFamily(id)
    return engineLabels.hasOwnProperty(key) ? qsTr(engineLabels[key]) : qsTr("não identificado")
}
function languageLabel(code) {
    var key = String(code || "").toLowerCase()
    return languageLabels.hasOwnProperty(key) ? qsTr(languageLabels[key]) : qsTr("não informado")
}
function audioInputLabel(value) { return audioInputLabels.hasOwnProperty(value) ? qsTr(audioInputLabels[value]) : qsTr("não informada") }
function audioOutputLabel(value) { return audioOutputLabels.hasOwnProperty(value) ? qsTr(audioOutputLabels[value]) : qsTr("não informada") }
function wakeQualificationLabel(q) { return wakeQualificationLabels.hasOwnProperty(q) ? qsTr(wakeQualificationLabels[q]) : qsTr("não informada") }
