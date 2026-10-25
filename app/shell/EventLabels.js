.pragma library
// Event kind -> Portuguese phrase. Single source: docs/ui-spec/50-diagnostico.md §4 (phrase, category, A/P/E flags).
// Permissões › Auditoria reads the P flag, its origin column (Plugin · Skill · Conexão · Comando, docs/ui-spec/30-permissoes.md
// §7.6, decision D6) and its Resultado column (30 §7.6). Rows marked "30" come from 30-permissoes §7.6 only: the Core emits
// them, 50 does not list them. The raw kind never reaches the screen; an unknown kind is shown as UNKNOWN_PHRASE.
// Row: [kind, phrase ("" = never shown), category (50 filter), A (Atividade), P (Auditoria), E (Últimos erros),
//       origin (Auditoria), result (Resultado: Concluído | Falhou | Negado | Recusado | Cancelado | "—")]

var UNKNOWN_PHRASE = "Evento do Core sem descrição"
var UNKNOWN_ORIGIN = "Core"

var rows = [
    ["session_started", "Sessão de voz iniciada", "Comando", true, true, false, "Comando", "—"],
    ["transcript_partial", "", "", false, false, false, "Comando", "—"],
    ["transcript_final", "Fala reconhecida", "Comando", true, true, false, "Comando", "—"],
    ["capture_completed", "Captura de fala concluída", "Comando", true, true, false, "Comando", "—"],
    ["no_speech", "Nenhuma fala detectada", "Comando", true, true, false, "Comando", "—"],
    ["capture_too_long", "Captura longa demais", "Comando", true, true, true, "Comando", "Falhou"],
    ["cancelled", "Sessão cancelada", "Comando", true, true, false, "Comando", "Cancelado"],
    ["timed_out", "Tempo esgotado na sessão de voz", "Comando", true, true, true, "Comando", "Falhou"],
    ["audio_error", "Erro de áudio na captura", "Comando", true, true, true, "Comando", "Falhou"],
    ["stt_failed", "Falha na transcrição", "Comando", true, true, true, "Comando", "Falhou"],
    ["stt_unavailable", "Transcrição indisponível", "Comando", true, true, true, "Comando", "Falhou"],
    ["speech_started", "Resposta em voz iniciada", "Comando", true, true, false, "Comando", "—"],
    ["speech_completed", "Resposta em voz concluída", "Comando", true, true, false, "Comando", "—"],
    ["tts_failed", "Falha na resposta em voz", "Comando", true, true, true, "Comando", "Falhou"],
    ["wake_failed", "Falha na detecção da frase de despertar", "Plugin", false, true, true, "Plugin", "Falhou"],
    ["command_authorized", "Comando autorizado", "Comando", true, true, false, "Comando", "—"],
    ["command_success", "Comando concluído com efeito verificado", "Comando", true, true, false, "Comando", "Concluído"],
    ["command_failed", "Comando não concluído: efeito não verificado", "Comando", true, true, true, "Comando", "Falhou"],
    ["tool_proposed", "Ferramenta proposta; aguarda sua decisão", "Comando", true, true, false, "Comando", "—"],
    ["tool_authorized", "Ferramenta autorizada por você", "Comando", true, true, false, "Comando", "—"],
    ["tool_denied", "Ferramenta negada", "Comando", true, true, false, "Comando", "Negado"],
    ["tool_executed", "Ferramenta executada", "Comando", true, true, false, "Comando", "Concluído"],
    ["tool_failed", "Ferramenta falhou", "Comando", true, true, true, "Comando", "Falhou"],
    ["agent_started", "Agente iniciado", "Agente", true, true, false, "Comando", "—"],
    ["agent_step", "Passo do agente", "Agente", true, true, false, "Comando", "—"],
    ["agent_tool", "Ferramenta usada pelo agente", "Agente", true, true, false, "Comando", "—"],
    ["agent_done", "Agente concluiu", "Agente", true, true, false, "Comando", "Concluído"],
    ["agent_failed", "Agente falhou", "Agente", true, true, true, "Comando", "Falhou"],
    ["agent_aborted", "Agente abortado", "Agente", true, true, false, "Comando", "—"],
    ["agent_blocked", "Agente bloqueado", "Agente", true, true, true, "Comando", "Recusado"],
    ["skill_validated", "Skill validada", "Skill", true, true, false, "Skill", "Concluído"],
    ["skill_approved", "Skill aprovada", "Skill", true, true, false, "Skill", "Concluído"],
    ["skill_enabled", "Skill habilitada", "Skill", true, true, false, "Skill", "Concluído"],
    ["skill_run_started", "Execução de skill iniciada", "Skill", true, true, false, "Skill", "—"],
    ["skill_step", "Passo de skill executado", "Skill", true, true, false, "Skill", "—"],
    ["skill_run_done", "Execução de skill concluída", "Skill", true, true, false, "Skill", "Concluído"],
    ["skill_run_failed", "Execução de skill falhou", "Skill", true, true, true, "Skill", "Falhou"],
    ["skill_rolled_back", "Skill voltou à versão anterior", "Skill", true, true, false, "Skill", "—"],
    ["skill_service_denied", "Skill bloqueada: serviço não permitido", "Skill", true, true, false, "Skill", "Recusado"],
    ["skill_plugin_validate", "Validação de skill pelo plugin", "Skill", true, false, false, "Skill", "Concluído"],
    ["skill_plugin_dry_run", "Simulação de skill pelo plugin", "Skill", true, false, false, "Skill", "Concluído"],
    ["skill_plugin_list", "Lista de skills do plugin consultada", "Skill", true, false, false, "Skill", "—"],
    ["skill_draft_put", "Rascunho de skill salvo", "Skill", true, true, false, "Skill", "Concluído"],
    ["skill_exported", "Skill exportada", "Skill", true, true, false, "Skill", "Concluído"],
    ["skill_import_previewed", "Prévia de importação de skill", "Skill", true, true, false, "Skill", "—"],
    ["skill_imported", "Skill importada como rascunho", "Skill", true, true, false, "Skill", "Concluído"],
    ["hub_import_started", "Importação de pacote iniciada", "Plugin", false, true, false, "Plugin", "—"],
    ["hub_payload_staged", "Pacote verificado e guardado; não instalado", "Plugin", false, true, false, "Plugin", "Concluído"],
    ["hub_import_cancelled", "Importação de pacote cancelada", "Plugin", false, true, false, "Plugin", "—"],
    ["hub_import_timeout", "Importação de pacote expirou", "Plugin", false, true, true, "Plugin", "Falhou"],
    ["hub_permissions_approved", "Permissões do plugin aprovadas", "Plugin", false, true, false, "Plugin", "Concluído"],
    ["hub_plugin_installed", "Plugin instalado (desativado)", "Plugin", false, true, false, "Plugin", "Concluído"],
    ["hub_plugin_updated", "Plugin atualizado (desativado)", "Plugin", false, true, false, "Plugin", "Concluído"],
    ["hub_plugin_rolled_back", "Plugin voltou à versão anterior", "Plugin", false, true, false, "Plugin", "Concluído"],
    ["hub_plugin_removed", "Plugin removido", "Plugin", false, true, false, "Plugin", "Concluído"],
    ["hub_staged_discarded", "Pacote guardado descartado", "Plugin", false, true, false, "Plugin", "—"],
    ["plugin_enabled", "Plugin ativado (sandbox, sem rede)", "Plugin", false, true, false, "Plugin", "Concluído"],
    ["plugin_disabled", "Plugin desativado", "Plugin", false, true, false, "Plugin", "—"],
    ["plugin_revoked", "Permissões do plugin revogadas", "Plugin", false, true, false, "Plugin", "Concluído"],
    ["plugin_started", "Plugin iniciado", "Plugin", true, true, false, "Plugin", "—"],
    ["plugin_stopped", "Plugin parado", "Plugin", true, true, false, "Plugin", "—"],
    ["plugin_failed", "Plugin falhou", "Plugin", true, true, true, "Plugin", "Falhou"],
    ["plugin_log", "", "", false, false, false, "Plugin", "—"],
    ["capability_invoked", "Capacidade invocada", "Plugin", true, true, false, "Plugin", "—"],
    ["capability_partial", "Resposta parcial recebida", "Plugin", true, true, false, "Plugin", "—"],
    ["llm_fallback_used", "Modelo de reserva respondeu", "Plugin", true, true, false, "Plugin", "—"],
    ["llm_configured", "Motor LLM configurado", "Configuração", false, true, false, "Plugin", "Concluído"],
    ["llm_marked_good", "Configuração do motor marcada como boa", "Configuração", false, true, false, "Plugin", "Concluído"],
    ["llm_rolled_back", "Motor LLM voltou à configuração anterior", "Configuração", false, true, false, "Plugin", "Concluído"],
    ["secret_set", "Chave de provedor salva", "Configuração", false, true, false, "Plugin", "Concluído"],
    ["secret_cleared", "Chave de provedor removida", "Configuração", false, true, false, "Plugin", "Concluído"],
    ["preferences_updated", "Preferências salvas", "Configuração", false, true, false, "Comando", "Concluído"],
    ["live_audio_enabled", "Escuta do microfone ligada (vale após reiniciar o Core)", "Configuração", false, true, false, "Comando", "Concluído"],
    ["live_audio_disabled", "Escuta do microfone desligada (vale após reiniciar o Core)", "Configuração", false, true, false, "Comando", "Concluído"],
    ["configuration_recovered", "Configuração recuperada; reinício necessário", "Configuração", false, true, true, "Comando", "Concluído"],
    ["connection_added", "Conta adicionada", "Conexão", false, true, false, "Conexão", "Concluído"],
    ["connection_connected", "Conta conectada", "Conexão", false, true, false, "Conexão", "Concluído"],
    ["connection_consented", "Escopo concedido", "Conexão", false, true, false, "Conexão", "Concluído"],
    ["connection_refreshed", "Acesso renovado", "Conexão", false, true, false, "Conexão", "Concluído"],
    ["connection_expired", "Acesso expirou", "Conexão", false, true, true, "Conexão", "—"],
    ["connection_disconnected", "Conta desconectada", "Conexão", false, true, false, "Conexão", "Concluído"],
    ["connection_revoked", "Acesso revogado", "Conexão", false, true, false, "Conexão", "Concluído"],
    ["connection_removed", "Conta removida", "Conexão", false, true, false, "Conexão", "Concluído"],
    ["connection_trusted", "Ferramentas da conta confiadas", "Conexão", false, true, false, "Conexão", "Concluído"],
    ["connection_call", "Chamada a conta registrada", "Conexão", true, true, false, "Conexão", "—"],
    ["registry_visual_allowed", "Fallback visual permitido", "Conexão", false, true, false, "Conexão", "Concluído"],
    ["registry_visual_revoked", "Fallback visual revogado", "Conexão", false, true, false, "Conexão", "Concluído"],
    ["registry_visual_run", "Ação visual executada", "Conexão", true, true, false, "Conexão", "—"],
    ["screen_capture", "Captura de tela (percepção)", "Percepção", false, true, false, "Plugin", "—"],
    ["input_action", "Ação de teclado ou mouse", "Percepção", false, true, false, "Plugin", "—"],
    ["audio_action", "Ação de áudio", "Percepção", false, true, false, "Plugin", "—"],
    ["mic_action", "Ação de microfone", "Percepção", false, true, false, "Plugin", "—"],
    ["camera_action", "Ação de câmera", "Percepção", false, true, false, "Plugin", "—"],
    ["synthetic_action", "Ação simulada (sem hardware real)", "Percepção", false, true, false, "Plugin", "—"],
    // Only in docs/ui-spec/30-permissoes.md §7.6 (the Core emits them; 50 does not list them).
    ["command_denied", "Comando negado", "Comando", true, true, false, "Comando", "Negado"],
    ["command_rejected", "Comando recusado", "Comando", true, true, false, "Comando", "Recusado"],
    ["preferences_storage_error", "Falha ao salvar preferências", "Configuração", false, true, true, "Comando", "Falhou"],
    ["configuration_recovery_error", "Falha ao recuperar a configuração", "Configuração", false, true, true, "Comando", "Falhou"]
]

// Suffixes of agent_blocked:<motivo> (50 §4, EV-R1 and the row note).
var suffixText = {
    loop_blocked: " · o modelo repetiu a mesma ação",
    stale_screen: " · a tela mudou desde a observação"
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

// Frase: the base phrase, then " · <motivo>" for the suffixes that have one (50 EV-R1). Empty when the table hides the kind.
function phrase(kind) {
    var e = entry(kind)
    if (!e) return UNKNOWN_PHRASE
    if (e.phrase.length === 0) return ""
    var colon = String(kind).indexOf(":")
    if (colon < 0) return e.phrase
    var suffix = String(kind).substring(colon + 1)
    if (e.kind === "agent_blocked") return e.phrase + (suffixText[suffix] || " · motivo não informado")
    return e.phrase
}

// Origin column of the Auditoria filter: Plugin · Skill · Conexão · Comando (decision D6). Unknown kinds: Core.
function origin(kind) {
    var e = entry(kind)
    return e ? e.origin : UNKNOWN_ORIGIN
}

// Resultado column. "—" when the event has no result (that is not a failure).
function result(kind) {
    var e = entry(kind)
    return e ? e.result : "—"
}

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
    return text === UNKNOWN_PHRASE ? "" : text
}

// Linha de Últimos erros (50 §5.6, R-S1): tipo com a coluna E marcada.
function isErrorKind(kind) {
    var e = entry(kind)
    return !!e && e.e === true && e.phrase.length > 0
}

// Área de uma linha (50 §5.6 S27). Fala e captura = Voz; wake = Motores; LLM = Motor LLM; o resto segue a categoria.
var originLabels = {core: "Comando", speech: "Voz", tool: "Ferramenta", agent: "Agente", skill: "Skill", plugin: "Plugin", hub: "Plugin", llm: "Motor LLM", config: "Configuração", connection: "Conexão", registry: "Conexão"}
function originLabel(origin) { return originLabels.hasOwnProperty(origin) ? originLabels[origin] : "Comando" }
function eventArea(kind, origin) {
    var base = String(kind || "").split(":")[0]
    if (base === "wake_failed") return "Motores"
    if (base.indexOf("llm_") === 0) return "Motor LLM"
    if (/^(stt_|tts_|speech_|transcript_|capture_|no_speech|audio_error)/.test(base)) return "Voz"
    var e = entry(base)
    if (e && e.cat) return e.cat
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
    plugin_crashed: "Plugin encerrou com falha",
    plugin_not_runnable: "Plugin não pode ser executado",
    plugin_cpu_exceeded: "Plugin passou do limite de processamento",
    plugin_output_invalid: "Plugin devolveu uma resposta inválida",
    plugin_start_failed: "Plugin não conseguiu iniciar",
    plugin_quarantined: "Plugin em quarentena",
    handshake_timeout: "Plugin não respondeu ao iniciar",
    handshake_mismatch: "Plugin não é a versão esperada",
    ledger_missing: "Registro de instalação ausente",
    ledger_invalid: "Registro de instalação inválido",
    hub_import_busy: "Importação do catálogo em andamento",
    hub_storage_error: "Falha ao gravar o registro do catálogo.",
    plugin_storage_error: "Falha ao gravar o registro dos plugins.",
    preferences_storage_error: "Falha ao gravar as preferências.",
    preferences_unavailable: "Preferências indisponíveis no momento.",
    configuration_not_ready: "Configuração ainda não está pronta.",
    hub_import_timeout: "Importação expirou antes de terminar.",
    busy: "Core ocupado; tente novamente em instantes",
    input_disabled: "Entrada de texto indisponível no momento",
    no_lkg: "Não há configuração anterior salva para restaurar",
    stale_llm_revision: "Configuração do motor mudou; reabra o diálogo",
    stale_hub_revision: "Catálogo mudou; atualize e tente de novo",
    stale_plugin_revision: "Estado do plugin mudou; atualize e tente de novo",
    llm_storage_error: "Falha ao gravar a configuração do motor",
    secrets_storage_error: "Falha ao gravar o cofre de chaves",
    virtual_input_disabled: "Entrada de teste não ativa no Core",
    unknown_capability: "Capacidade do motor LLM desconhecida",
    capability_timeout: "Plugin não respondeu no prazo",
    timed_out: "Tempo esgotado"
}
var fallbackCodePhrase = "Core recusou a ação."
function codePhrase(code) {
    var key = String(code || "")
    return codeTable.hasOwnProperty(key) ? codeTable[key] : fallbackCodePhrase
}

// Estados de motor, sessão, configuração e plugin (50 §3.1–3.3).
var wakeLabels = {unavailable: "Indisponível", starting: "Iniciando", replaying: "Reproduzindo", replay_finished: "Reprodução de teste encerrada", failed: "Falhou"}
var sttLabels = {unavailable: "Indisponível", starting: "Iniciando", ready: "Pronto", failed: "Falhou"}
var speechLabels = {unavailable: "Indisponível", idle: "Em espera", speaking: "Respondendo", completed: "Concluído", failed: "Falhou", muted: "Mudo", disabled: "Desligado", cancelled: "Cancelado", timed_out: "Tempo esgotado", audio_error: "Erro de áudio", stt_failed: "Falha na transcrição", stt_unavailable: "Transcrição indisponível", transcript_final: "Transcrição final", capture_completed: "Captura concluída", no_speech: "Sem fala detectada", capture_too_long: "Captura longa demais"}
var sessionLabels = {idle: "Em espera", capturing: "Ouvindo", transcribing: "Transcrevendo", executing: "Executando", speaking: "Respondendo", safe_mode: "Modo seguro", restart_required: "Reinício necessário"}
var configLabels = {ready: "Pronta", safe_mode: "Modo seguro", restart_required: "Reinício necessário"}
var pluginStateLabels = {disabled: "Desativado", starting: "Iniciando", running: "Ativo (sandbox, sem rede)", failed: "Falhou", stopped: "Parado", quarantined: "Em quarentena"}
function wakePhrase(status) { return wakeLabels[status] || "Indisponível" }
function sttPhrase(status) { return sttLabels[status] || "Indisponível" }
function speechPhrase(status) { return speechLabels[status] || "Indisponível" }
function sessionPhrase(state) { return sessionLabels[state] || "Core desconectado" }
function configPhrase(status) { return configLabels[status] || "Indisponível" }
function pluginStatePhrase(state) { return pluginStateLabels[state] || "Desativado" }

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
var scopeLabels = {dev_virtual_en: "Desenvolvimento · áudio virtual · inglês"}
// Chaves = família do ID (sem caminho e sem versão): "pocket-tts-3.3.0/english_2026-09/cpu" -> "pocket-tts".
var packLabels = {"base-en-dev-v1": "Base de voz virtual", "base-voz-virtual": "Base de voz virtual"}
var engineLabels = {"wake-replay": "detector de frase de teste", "sherpa-onnx": "sherpa-onnx", "moonshine": "moonshine", "moonshine-voice": "moonshine", "moonshine-en": "moonshine", "pocket-tts": "Pocket TTS"}
var languageLabels = {en: "inglês"}
var audioInputLabels = {virtual_pcm: "PCM virtual"}
var audioOutputLabels = {virtual: "virtual"}
var wakeQualificationLabels = {dev_qualified: "em desenvolvimento", poc_required: "requer prova de conceito"}
function scopeLabel(scope) { return scopeLabels[scope] || "" }
function packLabel(id) { return packLabels[id] || "Pacote de voz da Base" }
function engineFamily(id) { return String(id || "").split("/")[0].replace(/-\d[\d.]*$/, "") }
function engineLabel(id) { var key = engineFamily(id); return engineLabels.hasOwnProperty(key) ? engineLabels[key] : "não identificado" }
function languageLabel(code) { return languageLabels[String(code || "").toLowerCase()] || "não informado" }
function audioInputLabel(value) { return audioInputLabels[value] || "não informada" }
function audioOutputLabel(value) { return audioOutputLabels[value] || "não informada" }
function wakeQualificationLabel(q) { return wakeQualificationLabels[q] || "não informada" }
