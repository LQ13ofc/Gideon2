import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Gideon.Visual 1.0

ApplicationWindow {
    id: window
    objectName: "mainWindow"
    visible: true
    width: 1380; height: 904
    minimumWidth: 480; minimumHeight: 520
    title: "Gideon"
    color: themeIndex === 2 ? "#101822" : themeIndex === 1 ? "#122039" : "#0c1730"
    font.family: "Noto Sans"
    font.pixelSize: 14
    palette.window: "#142440"; palette.windowText: "#edf2ff"
    palette.button: "#243b66"; palette.buttonText: "#edf2ff"
    palette.base: "#11203a"; palette.text: "#edf2ff"
    palette.highlight: accentColor; palette.highlightedText: "#ffffff"
    property var reviewPlugin: null
    property string reviewRevision: ""
    // Revision captured when the Motor LLM dialog opens; configureLlm refuses it if the live snapshot moved on.
    property string llmRevisionCaptured: ""
    // C2 model manager: the revision is captured when a model is selected and when a models operation settles; useModel and setFallback refuse it if the Core moved on.
    property string modelsRevisionCaptured: ""
    property var selectedModel: null
    readonly property var featureChoices: [{id: "unknown", text: "Desconhecido"}, {id: "supported", text: "Suportado"}, {id: "unsupported", text: "Não suportado"}]
    // Per-plugin drafts survive delegate recreation (keyed by plugin_id). Plain JS, not reactive by design.
    property var drafts: ({})
    property int page: 0
    // Opening Modelos LLM refreshes the catalog once and captures the Core revision the user is looking at. Not a binding, so it cannot loop.
    onPageChanged: { if (page === 8) { modelsRevisionCaptured = core.llmRevision; core.listModels("recommended") } }
    property int themeIndex: 0
    property color accentColor: "#7693ff"
    readonly property string preferencesSuccess: "Preferências salvas pelo Core"
    readonly property bool spacious: width >= 1080 && height >= 760
    readonly property bool packAvailable: core.wakeChoices.length > 0
    readonly property var navigation: ["Início", "Voz e Wake", "Áudio", "Aparência", "Permissões", "Diagnóstico", "Gideon Hub", "Conversa", "Modelos LLM", "Percepção e ação", "Skills", "Conexões"]
    readonly property var navIcons: ["home", "voice", "audio", "appearance", "permissions", "diagnostics", "hub", "voice", "hub", "permissions", "hub", "permissions"]
    // S4 skills: state words live here; codes go through core.codeMessage. Nothing on this page grants a permission.
    function skillStateText(s) { switch (s) { case "draft": return "rascunho"; case "validated": return "validada"; case "tested": return "testada"; case "approved": return "aprovada"; case "enabled": return "habilitada"; case "disabled": return "desabilitada"; case "revised": return "revisada"; default: return s; } }
    function skillSourceText(s) { switch (s) { case "created": return "criada"; case "imported": return "importada (publisher não verificado)"; case "llm_draft": return "rascunho do LLM"; default: return s; } }
    function skillRunText(s) { switch (s) { case "running": return "executando"; case "awaiting_approval": return "aguardando sua decisão"; case "done": return "concluída"; case "failed": return "falhou"; case "cancelled": return "cancelada"; case "rolled_back": return "revertida"; default: return s; } }
    function skillStepText(s) { switch (s) { case "pending": return "pendente"; case "running": return "em execução"; case "awaiting_approval": return "aguardando sua decisão"; case "done": return "concluído"; case "failed": return "falhou"; case "denied": return "negado"; case "undone": return "desfeito"; case "cancelled": return "cancelado"; default: return s; } }
    function skillRunActive() { var r = core.skillCurrentRun; return !!r && (r.state === "running" || r.state === "awaiting_approval") }
    function skillCan(action, s) {
        if (core.skillsBusy) return false
        switch (action) {
        case "approve": return s === "tested"
        case "enable": return s === "approved" || s === "disabled"
        case "disable": return s === "enabled"
        case "export": return s === "approved" || s === "enabled" || s === "disabled"
        case "run": return s === "enabled" && !skillRunActive()
        case "dry": case "rollback": case "remove": return true
        }
        return false
    }
    // S5 connections: state words live here; codes go through core.codeMessage. Nothing on this page grants a scope: consent is the user's own click, per scope.
    readonly property var connProviderChoices: [{id: "github", text: "GitHub"}, {id: "google", text: "Google"}, {id: "homeassistant", text: "Home Assistant"}, {id: "mcp", text: "MCP"}]
    function connProviderName(id) { for (var i = 0; i < connProviderChoices.length; i++) if (connProviderChoices[i].id === id) return connProviderChoices[i].text; return id; }
    function connStatusText(s) { switch (s) { case "disconnected": return "desconectada"; case "connecting": return "conectando (aguardando confirmação)"; case "connected": return "conectada"; case "expired": return "expirada"; case "offline": return "offline"; case "error": return "erro"; case "reauth_required": return "reautenticação necessária"; default: return s; } }
    // S5 E2.2: short Portuguese label of an operation name (the name itself stays visible for the tests and the wire).
    function connOpLabel(name) { switch (name) { case "repos.list": return "listar repositórios"; case "repo.get": return "ver repositório"; case "issues.create": return "criar issue"; case "issues.update": return "editar issue"; case "pulls.get": return "ver pull request"; case "pulls.comment": return "comentar pull request"; case "actions.list": return "listar actions"; case "gmail.messages.list": return "listar e-mails"; case "gmail.send": return "enviar e-mail"; case "gmail.messages.delete": return "apagar e-mail"; case "calendar.events.list": return "listar eventos"; case "calendar.events.create": return "criar evento"; case "drive.files.list": return "listar arquivos"; case "drive.files.create": return "criar arquivo"; case "states.list": return "listar estados"; case "state.get": return "ver estado"; case "service.call": return "chamar serviço"; case "mcp.discover": return "listar ferramentas"; case "mcp.call": return "chamar ferramenta (aprovação a cada chamada)"; default: return name; } }
    function connToolRiskText(r) { return r === "destructive" ? "destrutiva (aprovação forte)" : "escrita (pede aprovação)"; }
    function connToolStateText(s) { switch (s) { case "trusted": return "confiável"; case "needs_reapproval": return "precisa de nova aprovação"; case "rejected": return "recusada"; default: return s; } }
    function connRiskText(r) { switch (r) { case "read": return "leitura"; case "write": return "escrita (pede aprovação)"; case "destructive": return "destrutiva (aprovação forte)"; case "public": return "pública (aprovação explícita)"; default: return r; } }
    function connProvider(id) { var list = core.connectionsProviders; for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i]; return null; }
    function connScopeLabel(providerId, scope) { var p = connProvider(providerId); if (p) for (var i = 0; i < p.scopes.length; i++) if (p.scopes[i].id === scope) return p.scopes[i].label; return scope; }
    function connScopeNames(list) { return (list && list.length) ? list.join(", ") : "nenhum"; }
    function connOperationsFor(item) { var p = connProvider(item.provider); return p ? p.operations : []; }
    function connGranted(item, scope) { return (item.granted_scopes || []).indexOf(scope) >= 0; }
    function connCanTest(item, op) { return !core.connectionsBusy && item.status === "connected" && op.risk === "read" && connGranted(item, op.scope); }
    // Consent drafts live in plain JS; connDraftRevision makes every binding that reads them re-evaluate after a toggle.
    property int connDraftRevision: 0
    function connConsentList(item) { var rev = connDraftRevision; var out = []; var pending = item.pending_scopes || []; for (var i = 0; i < pending.length; i++) if (draftValue("#conn:" + item.id, pending[i]) === true) out.push(pending[i]); return out; }
    function connCan(action, item) {
        if (core.connectionsBusy) return false
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
    function connOutcomeText(call) { if (call.code) return core.codeMessage(call.code); return call.outcome === "ok" ? "concluída" : call.outcome; }
    function connProposalText(p) {
        var items = core.connectionsItems; var item = null
        for (var i = 0; i < items.length; i++) if (items[i].id === p.connection_id) item = items[i]
        var account = item ? (item.account_ref ? item.label + " (" + item.account_ref + ")" : item.label) : "conta desconhecida"
        return "Conexão: " + (item ? connProviderName(item.provider) : "provedor desconhecido") + " · conta " + account + " · operação " + p.operation + " (" + connOpLabel(p.operation) + ") · risco " + connRiskText(p.risk)
    }
    // S5 E3 CapabilityRegistry: words for routes and statuses. Choices come from the Core snapshot 'registry'; this page only asks for a plan or flips the user's visual switch.
    readonly property var regVisualPurposes: ["create_issue"]
    function regRouteText(r) { return r === "connection" ? "API autorizada (conexão)" : r === "visual" ? "Visual (cliques e digitação)" : r; }
    function regStatusText(s) { switch (s) { case "available": return "disponível"; case "not_connected": return "não conectada"; case "expired": return "expirada ou reautenticação necessária"; case "scope_not_granted": return "escopo não concedido"; case "no_api": return "sem API neste ambiente"; case "visual_not_allowed": return "fallback visual desligado"; case "disabled": return "indisponível"; default: return s; } }
    function regVisualOn(id) { return core.registryVisualAllowed.indexOf(id) >= 0; }
    function regChosenText(p) { return p.route_chosen ? "rota escolhida: " + regRouteText(p.route_chosen) : "nenhuma rota disponível (route_unavailable)"; }
    // The skill whose permissions are shown; a copy of the snapshot row, so it reads as shown when it was picked.
    property var skillSelected: null
    // C4 test buttons: reads only. Each entry is one allowlisted capability (bridge PERCEPTION_CAPABILITIES) sent with the empty object.
    readonly property var perceptionActions: ({"screen_observe": [{capability: "screen_observe.capture", label: "Capturar"}, {capability: "screen_observe.status", label: "Estado"}], "computer_control": [{capability: "computer_control.tree", label: "Árvore"}, {capability: "computer_control.status", label: "Estado"}], "audio_advanced": [{capability: "audio_advanced.state", label: "Estado"}], "mic_advanced": [{capability: "mic_advanced.state", label: "Estado"}], "camera_gesture": [{capability: "camera_gesture.state", label: "Estado"}], "display_manipulate": [{capability: "display_manipulate.status", label: "Estado"}]})
    function perceptionStateText(state) { return ({running: "em execução", starting: "iniciando", disabled: "desativado", failed: "falhou", stopped: "parado", quarantined: "em quarentena"})[state] || state }
    readonly property var stateLabels: ({idle:"Em espera", capturing:"Ouvindo", transcribing:"Transcrevendo", executing:"Executando", speaking:"Respondendo", offline:"Core indisponível", safe_mode:"Modo seguro", restart_required:"Reinício necessário"})
    readonly property var statusLabels: ({unavailable:"Indisponível", idle:"Em espera", ready:"Pronto", starting:"Iniciando", replaying:"Reproduzindo", replay_finished:"Replay encerrado", failed:"Falhou", completed:"Concluído", speaking:"Respondendo", muted:"Mudo", disabled:"Desligado", cancelled:"Cancelado", timed_out:"Tempo esgotado", audio_error:"Erro de áudio", stt_failed:"Falha na transcrição", stt_unavailable:"Transcrição indisponível", transcript_final:"Transcrição final", capture_completed:"Captura concluída", no_speech:"Sem fala detectada", capture_too_long:"Captura longa demais"})
    function statusText(status) { return statusLabels[status] || "Indisponível"; }
    function draftValue(pluginId, key) { var d = drafts[pluginId]; return d && d[key] !== undefined ? d[key] : ""; }
    function setDraft(pluginId, key, value) { if (!drafts[pluginId]) drafts[pluginId] = {}; drafts[pluginId][key] = value; }
    function syncPreferenceControls() {
        audible.checked = core.audibleFeedback; timeout.value = core.sessionTimeout; visual.checked = core.visualFeedback; volume.value = core.outputVolume
        visualPage.checked = core.visualFeedback; gainSlider.value = core.outputVolume
    }
    // Qt's standard Close button is English by default; the client is Portuguese.
    function localizeClose(d) { var b = d.standardButton(Dialog.Close); if (b) b.text = "Fechar" }
    function approvalDone() { if (!reviewPlugin) return false; var entries = core.hubEntries; for (var i=0;i<entries.length;i++) if (entries[i].plugin_id === reviewPlugin.plugin_id && entries[i].manifest_sha256 === reviewPlugin.manifest_sha256) return entries[i].permissions_approved === true; return false; }
    function pluginFor(pluginId) { var items = core.pluginItems; for (var i=0;i<items.length;i++) if (items[i].plugin_id === pluginId) return items[i]; return null; }
    function pluginEnabledFor(pluginId) { var item = pluginFor(pluginId); return !!item && item.enabled === true; }
    function pluginStateText(item) { switch (item.state) { case "running": return "Ativo (sandbox, sem rede)"; case "starting": return "Iniciando…"; case "failed": return "Falhou: " + (item.last_error || "erro"); case "stopped": return "Parado"; case "quarantined": return "Em quarentena"; default: return "Desativado"; } }
    function pluginInstalled(pluginId) { var entries = core.hubEntries; for (var i=0;i<entries.length;i++) if (entries[i].plugin_id === pluginId) return entries[i].status === "installed"; return false; }
    function pluginApproved(pluginId) { var entries = core.hubEntries; for (var i=0;i<entries.length;i++) if (entries[i].plugin_id === pluginId) return entries[i].permissions_approved === true; return false; }
    function pluginCanEnable(item) { return !item.enabled && (item.state === "disabled" || item.state === "stopped" || item.state === "failed") && pluginInstalled(item.plugin_id) && pluginApproved(item.plugin_id); }
    function toolStateText(state) { switch (state) { case "pending": return "aguardando sua decisão"; case "authorized": return "autorizada; executando"; case "executed": return "executada"; case "denied": return "negada"; case "failed": return "falhou"; case "expired": return "expirada"; case "cancelled": return "cancelada"; default: return state; } }
    // C3 agent labels: the state words live here; the Core codes go through core.codeMessage.
    function agentStepText(state) { switch (state) { case "running": return "em execução"; case "done": return "concluído"; case "awaiting_approval": return "aguardando sua decisão"; case "denied": return "negado pelo usuário"; case "failed": return "falhou"; case "stale": return "tela desatualizada"; case "blocked": return "bloqueado"; case "cancelled": return "cancelado"; default: return state; } }
    function agentRiskText(risk) { switch (risk) { case "read": return "leitura"; case "state_changing": return "muda estado"; case "destructive": return "destrutiva"; default: return "—"; } }
    function sendChatDraft() { var t = chatInput.text.trim(); if (t.length === 0 || core.chatTextProblem(t) !== "") return; core.sendChat(t) }
    function openLlm() { llmRevisionCaptured = core.llmRevision; llmDialog.open() }
    function filteredModels(list, filter) { var out = []; for (var i = 0; i < list.length; i++) { var m = list[i]; if (filter === 1 && m.kind !== "local") continue; if (filter === 2 && m.kind !== "cloud") continue; out.push(m); } return out; }
    function allModels() { return core.modelsRecommended.concat(core.modelsCustom); }
    function modelById(ident) { var list = allModels(); for (var i = 0; i < list.length; i++) if (list[i].id === ident) return list[i]; return null; }
    function selectModel(m) { selectedModel = m; modelsRevisionCaptured = core.llmRevision; }
    function isCloudProvider(p) { return p === "openrouter" || p === "opencode" || p === "google" || p === "custom"; }
    function fallbackPicked() { return modelById(fallbackPick.currentValue); }
    function fallbackIsCloud() { var m = fallbackPicked(); return isCloudProvider(core.modelsFallback.provider) || (!!m && m.kind === "cloud"); }
    function fallbackAllowed() { var m = fallbackPicked(); return !!m && (m.kind !== "cloud" || core.llmConfig.cloud_consent === true); }
    function latencyText(v) { switch (v) { case "low": return "baixa"; case "medium": return "média"; case "high": return "alta"; default: return "desconhecida"; } }
    function gpuText(v) { switch (v) { case "none": return "não requer"; case "optional": return "opcional"; case "required": return "obrigatória"; default: return "desconhecida"; } }
    function customForm() { var prov = customProvider.currentValue; var local = prov === "local" || prov === "ollama"; return { provider: prov, model: customModelId.text, custom_url: prov === "custom" ? customUrl.text : "", local_port: local ? customPort.value : null, features: { streaming: customStreaming.currentValue, tool_use: customToolUse.currentValue, vision: customVision.currentValue, cancel: customCancel.currentValue } }; }
    function wakeText() { var pack = core.snapshotPack; if (!pack.wake_phrases) return "Não configurada"; for (var i=0;i<pack.wake_phrases.length;i++) if (pack.wake_phrases[i].id === pack.active_phrase) return pack.wake_phrases[i].text; return "Não ativa"; }
    // Core-owned state changes resync the controls; a rejected save must not leave the user's unsaved values on screen.
    Connections {
        target: core
        function onPreferencesChanged() { window.syncPreferenceControls() }
        function onPrefsSettled(message) { if (message !== window.preferencesSuccess) window.syncPreferenceControls() }
        function onTextSent(sent) { if (input.text === sent) input.text = "" }
        function onChatSent(sent) { if (chatInput.text.trim() === sent) { chatInput.text = ""; window.setDraft("#chat", "text", "") } }
        // The captured model revision follows the user's own operations: refreshed when one settles, never on background changes.
        function onModelsStateChanged() { if (!core.modelsBusy) window.modelsRevisionCaptured = core.llmRevision }
        function onChanged() { if (window.page === 8 && !core.modelsAvailable) window.page = 0; if (window.page === 9 && !core.perceptionAvailable) window.page = 0; if (window.page === 10 && !core.skillsAvailable) window.page = 0; if (window.page === 11 && !core.connectionsAvailable) window.page = 0 }
    }
    Dialog {
        id: preferences; objectName: "preferencesDialog"
        title: "Preferências da Base"; modal: true
        anchors.centerIn: parent; width: Math.min(420, window.width - 32)
        standardButtons: Dialog.Close
        background: GlassCard { theme: window.themeIndex }
        onOpened: { window.syncPreferenceControls(); window.localizeClose(preferences) }
        contentItem: ScrollView {
            implicitHeight: Math.min(settingsColumn.implicitHeight, window.height - 120)
            clip: true
        ColumnLayout {
            id: settingsColumn
            width: preferences.availableWidth
            Label { objectName: "configurationMessage"; visible: core.configurationMessage.length > 0; text: core.configurationMessage; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Button { objectName: "recoverConfigurationButton"; visible: core.configurationStatus === "safe_mode"; text: "Preservar arquivo e restaurar padrões"; enabled: core.recoveryAvailable; onClicked: core.recoverConfiguration(); Accessible.name: text }
            Label { objectName: "packDescription"; visible: core.packDescription.length > 0; text: core.packDescription; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            RowLayout {
                visible: core.wakeChoices.length > 0
                Layout.fillWidth: true
                ComboBox { id: wakeChoice; objectName: "wakeChoice"; Layout.fillWidth: true; model: core.wakeChoices; textRole: "text"; valueRole: "id"; enabled: core.preferencesAvailable; Accessible.name: "Frase de wake do pack" }
                Button { objectName: "selectWakeButton"; text: "Selecionar"; enabled: core.preferencesAvailable && wakeChoice.currentIndex >= 0 && core.wakeChoices[wakeChoice.currentIndex].qualification === "dev_qualified"; onClicked: core.selectWake(wakeChoice.currentValue); Accessible.name: "Selecionar frase de wake"}
            }
            Label { objectName: "wakeQualification"; visible: core.wakeChoices.length > 0; text: wakeChoice.currentIndex >= 0 ? (core.wakeChoices[wakeChoice.currentIndex].qualification === "dev_qualified" ? "Qualificada em DEV; validação física pendente" : "POC_REQUIRED: frase sem qualidade aprovada") : ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            CheckBox { id: audible; objectName: "audiblePreference"; text: core.voiceAvailable ? "Resposta por voz (saída virtual)" : "Resposta por voz indisponível"; enabled: core.preferencesAvailable && core.voiceAvailable }
            CheckBox { id: visual; objectName: "visualPreference"; text: "Indicador visual de atividade"; enabled: core.preferencesAvailable }
            Label { text: "Ganho da saída virtual: " + core.outputVolume + "% (0% = mudo)"; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            SpinBox { id: volume; objectName: "volumePreference"; from: 0; to: 100; stepSize: 5; editable: true; enabled: core.preferencesAvailable && core.voiceAvailable; Accessible.name: "Ganho da saída virtual, por cento" }
            Button { objectName: "saveFeedbackButton"; text: "Salvar indicador e ganho"; enabled: core.preferencesAvailable; onClicked: core.saveFeedback(visual.checked, volume.value) }
            Label { text: "Privacidade: capturas e legendas em memória; sem histórico persistente. Entrada/saída virtuais. CPU e sensibilidade fixas. Dispositivos físicos, outras vozes/idiomas e login automático indisponíveis."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { text: "Prazo da sessão em milissegundos"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            SpinBox { id: timeout; objectName: "timeoutPreference"; from: 50; to: 60000; stepSize: 1000; editable: true; enabled: core.preferencesAvailable; Accessible.name: "Prazo da sessão em milissegundos" }
            RowLayout {
                Button { objectName: "savePreferencesButton"; text: "Salvar"; enabled: core.preferencesAvailable; onClicked: core.savePreferences(audible.checked, timeout.value) }
                Button { objectName: "rollbackPreferencesButton"; text: "Restaurar anterior"; enabled: core.rollbackAvailable; onClicked: core.rollbackPreferences() }
            }
            Label { text: (core.configurationStatus === "safe_mode" ? "Padrões de recuperação: " : "Atual no Core: ") + (core.audibleFeedback ? "voz ligada" : "voz desligada") + " · " + core.sessionTimeout + " ms"; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { objectName: "preferencesResult"; text: core.preferencesResult; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            GlowButton { objectName: "llmOpenButton"; text: "Motor LLM"; Accessible.name: "Abrir configuração do Motor LLM"; enabled: core.connected; onClicked: { preferences.close(); window.openLlm() } }
            Label { text: "Alterações se aplicam à próxima sessão. Voz, frases e dispositivos dependem do pack e dos adaptadores disponíveis."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        }
    }
    Dialog {
        id: hubDialog; objectName: "hubDialog"
        title: "Plugins — Gideon Hub"; modal: true
        anchors.centerIn: parent; width: Math.min(420, window.width - 32)
        standardButtons: Dialog.Close
        onOpened: window.localizeClose(hubDialog)
        background: GlassCard { theme: window.themeIndex }
        contentItem: ScrollView {
            implicitHeight: Math.min(hubColumn.implicitHeight, window.height - 120); clip: true
            ColumnLayout {
                id: hubColumn; width: hubDialog.availableWidth
                Label { objectName: "hubDescription"; text: core.hubDescription; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Label { text: core.hubImportDescription; visible: core.hubImportActive; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                GlowButton { objectName: "abortHubImportButton"; text: "Cancelar importação"; visible: core.hubImportActive; enabled: core.hubImportActive; onClicked: core.abortHubImport() }
                Repeater {
                    model: core.hubEntries
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Label { text: modelData.plugin_id + " " + modelData.semver + " · " + modelData.publisher; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { objectName: "status_" + modelData.plugin_id; text: (modelData.status === "installed" ? (window.pluginEnabledFor(modelData.plugin_id) ? "Instalado · ativo (sandbox, sem rede)" : "Instalado · desativado (sem execução)") : modelData.status === "update_available" ? "Atualização disponível" : modelData.status === "not_installed" ? (modelData.payload_staged ? "Pacote verificado em staging; não instalado" : "Não instalado") : "Incompatível: " + modelData.reason) + " · " + modelData.license; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { text: (modelData.permissions_approved ? "Permissões aprovadas para este manifest: " : "Permissões declaradas (não aprovadas): ") + (modelData.permissions.join(", ") || "nenhuma") + "\n" + modelData.support_policy; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        GlowButton { objectName: "review_" + modelData.plugin_id; text: modelData.permissions_approved ? "Permissões aprovadas" : "Revisar permissões"; Accessible.name: (modelData.permissions_approved ? "Permissões aprovadas de " : "Revisar permissões de ") + modelData.plugin_id; enabled: core.hubApprovalAvailable && (modelData.status === "not_installed" || modelData.status === "update_available" || modelData.status === "installed") && !modelData.permissions_approved; onClicked: { window.reviewPlugin = modelData; reviewAck.checked = false; reviewDialog.open() } }
                        GlowButton { objectName: "install_" + modelData.plugin_id; text: "Instalar pacote verificado"; Accessible.name: "Instalar pacote verificado de " + modelData.plugin_id; enabled: core.hubLifecycleAvailable && modelData.payload_staged === true && modelData.permissions_approved === true && (modelData.status === "not_installed" || modelData.status === "update_available"); onClicked: core.installHub(modelData.plugin_id, modelData.manifest_sha256) }
                    }
                }
                Label { text: "Instalados no Core"; visible: core.hubInstalled.length > 0; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Repeater {
                    model: core.hubInstalled
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Label { text: modelData.plugin_id + " " + modelData.semver + " · " + (modelData.state === "quarantined" ? "Em quarentena" : window.pluginEnabledFor(modelData.plugin_id) ? "Instalado · ativo" : "Instalado · desativado (sem execução)"); textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        GlowButton { objectName: "rollback_" + modelData.plugin_id; text: "Reverter versão"; Accessible.name: "Reverter versão de " + modelData.plugin_id; enabled: core.hubLifecycleAvailable && !!modelData.previous && modelData.state === "installed"; onClicked: core.rollbackHub(modelData.plugin_id) }
                        GlowButton { objectName: "remove_" + modelData.plugin_id; text: "Remover plugin"; Accessible.name: "Remover " + modelData.plugin_id; enabled: core.hubLifecycleAvailable; onClicked: { removeConfirm.plugin = modelData; removeConfirm.revision = core.hubInstallRevision; removeConfirm.open() } }
                    }
                }
                Label { objectName: "hubLifecycleResult"; text: core.hubApprovalResult; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Label { text: "Plugins no Core"; visible: core.pluginItems.length > 0; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Repeater {
                    model: core.pluginItems
                    delegate: ColumnLayout {
                        id: pluginEntry
                        required property var modelData
                        // Restored from the window draft map so a rebuilt delegate keeps the active capability.
                        property string activeCapability: window.draftValue(modelData.plugin_id, "capability")
                        property var inputField: capabilityInput
                        Layout.fillWidth: true
                        Label { objectName: "pluginStatus_" + pluginEntry.modelData.plugin_id; text: pluginEntry.modelData.plugin_id + " " + pluginEntry.modelData.semver + " · " + window.pluginStateText(pluginEntry.modelData); textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { text: "Capacidades: " + (pluginEntry.modelData.capabilities.length ? pluginEntry.modelData.capabilities.join(", ") : "nenhuma"); textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { objectName: "reapprovalHint_" + pluginEntry.modelData.plugin_id; visible: window.pluginInstalled(pluginEntry.modelData.plugin_id) && !window.pluginApproved(pluginEntry.modelData.plugin_id); text: "Aprove novamente as permissões para ativar"; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        GlowButton { objectName: "enable_" + pluginEntry.modelData.plugin_id; text: "Ativar"; Accessible.name: "Ativar " + pluginEntry.modelData.plugin_id; enabled: core.pluginsAvailable && window.pluginCanEnable(pluginEntry.modelData); onClicked: core.enablePlugin(pluginEntry.modelData.plugin_id) }
                        GlowButton { objectName: "disable_" + pluginEntry.modelData.plugin_id; text: "Desativar"; Accessible.name: "Desativar " + pluginEntry.modelData.plugin_id; enabled: core.pluginsAvailable && pluginEntry.modelData.enabled === true; onClicked: core.disablePlugin(pluginEntry.modelData.plugin_id) }
                        GlowButton { objectName: "revoke_" + pluginEntry.modelData.plugin_id; text: "Revogar permissões"; Accessible.name: "Revogar permissões de " + pluginEntry.modelData.plugin_id; enabled: core.pluginsAvailable && pluginEntry.modelData.state !== "quarantined"; onClicked: { revokeConfirm.plugin = pluginEntry.modelData; revokeConfirm.revision = core.pluginsRevision; revokeConfirm.open() } }
                        TextField {
                            id: capabilityInput; objectName: "capabilityInput_" + pluginEntry.modelData.plugin_id
                            placeholderText: "Texto para a capability"; Accessible.name: "Texto para a capability de " + pluginEntry.modelData.plugin_id
                            maximumLength: 256; enabled: core.pluginsAvailable && pluginEntry.modelData.state === "running"; Layout.fillWidth: true
                            Component.onCompleted: text = window.draftValue(pluginEntry.modelData.plugin_id, "text")
                            onTextEdited: window.setDraft(pluginEntry.modelData.plugin_id, "text", text)
                        }
                        Repeater {
                            model: pluginEntry.modelData.capabilities
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                GlowButton { objectName: "invoke_" + modelData; text: "Invocar"; Accessible.name: "Invocar " + modelData; enabled: core.pluginsAvailable && pluginEntry.modelData.state === "running"; onClicked: { pluginEntry.activeCapability = modelData; window.setDraft(pluginEntry.modelData.plugin_id, "capability", modelData); core.invokeCapability(modelData, pluginEntry.inputField.text) } }
                                GlowButton { objectName: "cancelCapability_" + pluginEntry.modelData.plugin_id; text: "Cancelar"; Accessible.name: "Cancelar capability " + modelData; enabled: core.pluginsAvailable && pluginEntry.activeCapability === modelData; onClicked: core.cancelCapability(modelData) }
                            }
                        }
                    }
                }
                Label { objectName: "pluginLifecycleResult"; text: core.pluginResult; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Label { objectName: "capabilityResult"; text: core.capabilityResultText; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Label { text: "Instalar copia o pacote verificado para o Core; nada é executado. O catálogo não concede acesso ao computador."; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
        }
    }
    Dialog {
        id: llmDialog; objectName: "llmDialog"
        // Provider, model and consent start from the Core snapshot; no saved config means consent unchecked. The key field always starts empty.
        title: "Motor LLM"; modal: true
        anchors.centerIn: parent; width: Math.min(440, window.width - 32)
        standardButtons: Dialog.Close
        background: GlassCard { theme: window.themeIndex }
        onOpened: {
            window.localizeClose(llmDialog)
            window.llmRevisionCaptured = core.llmRevision
            providerBox.currentIndex = Math.max(0, providerBox.indexOfValue(core.llmConfig.provider || "openrouter"))
            modelField.text = core.llmConfig.model || ""; urlField.text = core.llmConfig.custom_url || ""
            // Reflects the saved consent; never auto-enabled. Only a user click changes it before save.
            consentBox.checked = core.llmConfig.cloud_consent === true; keyField.text = ""
        }
        onClosed: keyField.text = ""
        contentItem: ScrollView {
            implicitHeight: Math.min(llmColumn.implicitHeight, window.height - 120); clip: true
            ColumnLayout {
                id: llmColumn; width: llmDialog.availableWidth
                Label { text: "Motor opcional. Sem ele, voz, wake e comandos da Base continuam funcionando."; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Label { text: "Provedor"; textFormat: Text.PlainText; Layout.fillWidth: true }
                ComboBox {
                    id: providerBox; objectName: "llmProvider"; Layout.fillWidth: true; enabled: core.llmConfigAvailable
                    textRole: "text"; valueRole: "id"; Accessible.name: "Provedor do motor LLM"
                    model: [{id: "openrouter", text: "OpenRouter"}, {id: "opencode", text: "OpenCode"}, {id: "google", text: "Google AI Studio"}, {id: "custom", text: "Personalizado"}]
                }
                Label { text: "Modelo: letras, números e . _ : / - (até 128)"; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                TextField {
                    id: modelField; objectName: "llmModel"; Layout.fillWidth: true; maximumLength: 128; enabled: core.llmConfigAvailable
                    placeholderText: "ex.: gemini-3.5-flash-lite"; Accessible.name: "Modelo do motor LLM"
                    validator: RegularExpressionValidator { regularExpression: /[A-Za-z0-9._:\/-]{1,128}/ }
                }
                Label { visible: providerBox.currentValue === "custom"; text: "URL personalizada: somente https (http apenas em loopback de teste)"; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                TextField {
                    id: urlField; objectName: "llmUrl"; Layout.fillWidth: true; maximumLength: 200; enabled: providerBox.currentValue === "custom" && core.llmConfigAvailable
                    placeholderText: "https://"; Accessible.name: "URL do provedor personalizado"
                }
                Label { objectName: "llmKeyStatus"; text: core.llmSecretsConfigured[providerBox.currentValue] === true ? "Chave configurada" : "Sem chave"; textFormat: Text.PlainText; Layout.fillWidth: true; Accessible.name: "Estado da chave: " + text }
                TextField {
                    id: keyField; objectName: "llmKey"; Layout.fillWidth: true; echoMode: TextInput.Password; maximumLength: 256
                    inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                    placeholderText: "Chave de API (somente escrita)"; enabled: core.llmConfigAvailable; Accessible.name: "Chave de API do provedor"
                }
                RowLayout {
                    Layout.fillWidth: true
                    GlowButton {
                        objectName: "saveKeyButton"; text: "Salvar chave"; Accessible.name: "Salvar chave do provedor"
                        enabled: core.llmConfigAvailable && keyField.text.length > 0
                        // The field is cleared at once: the key leaves QML with this call and is never shown again.
                        onClicked: { core.setApiKey(providerBox.currentValue, keyField.text); keyField.text = "" }
                    }
                    GlowButton { objectName: "clearKeyButton"; text: "Remover chave"; Accessible.name: "Remover chave do provedor"; enabled: core.llmConfigAvailable && core.llmSecretsConfigured[providerBox.currentValue] === true; onClicked: core.clearApiKey(providerBox.currentValue) }
                }
                CheckBox { id: consentBox; objectName: "llmConsent"; checked: false; text: "Permitir envio de conversas ao provedor na nuvem"; enabled: core.llmConfigAvailable; Accessible.name: "Consentimento para envio à nuvem"; Accessible.description: "Mensagens serão enviadas ao provedor escolhido na nuvem" }
                Label { objectName: "llmConsentWarning"; text: "Mensagens serão enviadas ao provedor escolhido na nuvem"; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Label { text: "Consentimento salvo: " + (core.llmConfig.cloud_consent === true ? "concedido" : "não concedido"); textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                GlowButton {
                    objectName: "saveLlmConfigButton"; text: "Salvar configuração"; Accessible.name: "Salvar configuração do Motor LLM"
                    enabled: core.llmConfigAvailable && modelField.acceptableInput && core.llmConfig.provider !== "local" && core.llmConfig.provider !== "ollama"
                    onClicked: core.configureLlm(providerBox.currentValue, modelField.text, providerBox.currentValue === "custom" ? urlField.text : "", consentBox.checked, window.llmRevisionCaptured)
                }
                // A local provider is configured only through Modelos LLM; this dialog would otherwise overwrite it.
                Label { objectName: "llmLocalNotice"; visible: core.llmConfig.provider === "local" || core.llmConfig.provider === "ollama"; text: "Configuração local ativa: altere em Modelos LLM."; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Label { objectName: "llmResult"; text: core.llmResult; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
        }
    }
    Dialog {
        id: reviewDialog; objectName: "hubReviewDialog"
        // The approval target is captured when the dialog opens; the bridge refuses it if the live record changed.
        onOpened: { core.beginHubReview(); window.reviewRevision = core.hubApprovalRevision; window.localizeClose(reviewDialog) }
        title: "Revisar permissões"; modal: true; anchors.centerIn: parent
        width: Math.min(440, window.width - 32); standardButtons: Dialog.Close
        background: GlassCard { theme: window.themeIndex }
        contentItem: ScrollView {
            implicitHeight: Math.min(reviewColumn.implicitHeight, window.height - 120); clip: true
        ColumnLayout {
            id: reviewColumn; width: reviewDialog.availableWidth
            Label { text: window.reviewPlugin ? window.reviewPlugin.plugin_id + " " + window.reviewPlugin.semver + " · " + window.reviewPlugin.publisher : ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { text: window.reviewPlugin ? "Permissões: " + (window.reviewPlugin.permissions.join(", ") || "nenhuma") : ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { text: "Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifest."; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            CheckBox { id: reviewAck; objectName: "publisherAcknowledgement"; text: "Entendo que o publisher não foi autenticado"; enabled: core.hubApprovalAvailable }
            GlowButton { objectName: "approveHubButton"; text: "Aprovar estas permissões"; Accessible.name: window.reviewPlugin ? "Aprovar permissões de " + window.reviewPlugin.plugin_id : "Aprovar permissões"; enabled: core.hubApprovalAvailable && reviewAck.checked && window.reviewPlugin !== null && !window.approvalDone(); onClicked: core.approveHub(window.reviewPlugin.plugin_id, window.reviewPlugin.manifest_sha256, window.reviewPlugin.permissions, reviewAck.checked, window.reviewRevision) }
            Label { objectName: "hubApprovalResult"; text: core.hubApprovalResult; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        }
    }
    // Destructive confirmations: Cancel is the focused default; the explicit action button is the only way to accept.
    Dialog {
        id: removeConfirm; objectName: "removeConfirm"
        property var plugin: null
        property string revision: ""
        title: "Remover plugin"; modal: true; anchors.centerIn: parent
        width: Math.min(400, window.width - 32)
        standardButtons: Dialog.Cancel
        background: GlassCard { theme: window.themeIndex }
        onOpened: { var cancel = standardButton(Dialog.Cancel); if (cancel) { cancel.text = "Cancelar"; cancel.forceActiveFocus() } }
        onAccepted: { if (plugin) core.removeHub(plugin.plugin_id, revision) }
        contentItem: ColumnLayout {
            width: removeConfirm.availableWidth
            Label { text: removeConfirm.plugin ? "Remover " + removeConfirm.plugin.plugin_id + " " + removeConfirm.plugin.semver + " do Core? Nada é executado e o catálogo não muda." : ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            GlowButton { objectName: "confirmRemoveButton"; text: "Remover"; Accessible.name: removeConfirm.plugin ? "Remover " + removeConfirm.plugin.plugin_id : "Remover"; Layout.alignment: Qt.AlignRight; onClicked: removeConfirm.accept() }
        }
    }
    Dialog {
        id: revokeConfirm; objectName: "revokeConfirm"
        property var plugin: null
        property string revision: ""
        title: "Revogar permissões"; modal: true; anchors.centerIn: parent
        width: Math.min(400, window.width - 32)
        standardButtons: Dialog.Cancel
        background: GlassCard { theme: window.themeIndex }
        onOpened: { var cancel = standardButton(Dialog.Cancel); if (cancel) { cancel.text = "Cancelar"; cancel.forceActiveFocus() } }
        onAccepted: { if (plugin) core.revokePlugin(plugin.plugin_id, revision) }
        contentItem: ColumnLayout {
            width: revokeConfirm.availableWidth
            Label { text: revokeConfirm.plugin ? "Revogar permissões de " + revokeConfirm.plugin.plugin_id + "? O plugin será desativado e o processo encerrado. Reativar exige nova aprovação." : ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            GlowButton { objectName: "confirmRevokeButton"; text: "Revogar"; Accessible.name: revokeConfirm.plugin ? "Revogar permissões de " + revokeConfirm.plugin.plugin_id : "Revogar"; Layout.alignment: Qt.AlignRight; onClicked: revokeConfirm.accept() }
        }
    }
    // Destructive confirmations for the model manager: Cancel is the focused default; the explicit action button is the only way to accept.
    Dialog {
        id: removeCustomConfirm; objectName: "removeCustomConfirm"
        property var entry: null
        title: "Remover modelo personalizado"; modal: true; anchors.centerIn: parent
        width: Math.min(400, window.width - 32)
        standardButtons: Dialog.Cancel
        background: GlassCard { theme: window.themeIndex }
        onOpened: { var cancel = standardButton(Dialog.Cancel); if (cancel) { cancel.text = "Cancelar"; cancel.forceActiveFocus() } }
        onAccepted: { if (entry) core.deleteCustomModel(entry.id) }
        contentItem: ColumnLayout {
            width: removeCustomConfirm.availableWidth
            Label { text: removeCustomConfirm.entry ? "Remover " + removeCustomConfirm.entry.label + " da lista de modelos personalizados? O modelo no provedor não é apagado." : ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            GlowButton { objectName: "confirmRemoveCustomButton"; text: "Remover"; Accessible.name: removeCustomConfirm.entry ? "Remover modelo " + removeCustomConfirm.entry.id : "Remover"; Layout.alignment: Qt.AlignRight; onClicked: removeCustomConfirm.accept() }
        }
    }
    Dialog {
        id: clearPluginConfirm; objectName: "clearPluginConfirm"
        title: "Apagar dados do plugin"; modal: true; anchors.centerIn: parent
        width: Math.min(400, window.width - 32)
        standardButtons: Dialog.Cancel
        background: GlassCard { theme: window.themeIndex }
        onOpened: { var cancel = standardButton(Dialog.Cancel); if (cancel) { cancel.text = "Cancelar"; cancel.forceActiveFocus() } }
        onAccepted: core.clearPluginSettings()
        contentItem: ColumnLayout {
            width: clearPluginConfirm.availableWidth
            Label { text: "Apagar as configurações guardadas pelo plugin LLM, inclusive modelos personalizados? O plugin e a configuração do Core (provedor, modelo e chaves) não são alterados."; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            GlowButton { objectName: "confirmClearPluginButton"; text: "Apagar dados"; Accessible.name: "Apagar dados do plugin LLM"; Layout.alignment: Qt.AlignRight; onClicked: clearPluginConfirm.accept() }
        }
    }
    // Destructive confirmation for a skill: Cancel is the focused default; the explicit action button is the only way to accept.
    Dialog {
        id: removeSkillConfirm; objectName: "removeSkillConfirm"
        property var skill: null
        title: "Remover skill"; modal: true; anchors.centerIn: parent
        width: Math.min(400, window.width - 32)
        standardButtons: Dialog.Cancel
        background: GlassCard { theme: window.themeIndex }
        onOpened: { var cancel = standardButton(Dialog.Cancel); if (cancel) { cancel.text = "Cancelar"; cancel.forceActiveFocus() } }
        onAccepted: { if (skill) core.skillRemove(skill.id) }
        contentItem: ColumnLayout {
            width: removeSkillConfirm.availableWidth
            Label { text: removeSkillConfirm.skill ? "Remover " + removeSkillConfirm.skill.id + " v" + removeSkillConfirm.skill.version + " do Core? Nada é executado." : ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            GlowButton { objectName: "confirmRemoveSkillButton"; text: "Remover"; Accessible.name: removeSkillConfirm.skill ? "Remover skill " + removeSkillConfirm.skill.id : "Remover skill"; Layout.alignment: Qt.AlignRight; onClicked: removeSkillConfirm.accept() }
        }
    }
    Rectangle {
        id: sidebar
        width: window.width >= 1000 ? 232 : 64
        anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: window.themeIndex === 2 ? "#131e2c" : window.themeIndex === 1 ? "#1b2c47" : "#142445"
        Rectangle { anchors.right: parent.right; height: parent.height; width: 1; color: "#2b3d6a" }
        ColumnLayout {
            anchors.fill: parent; anchors.margins: sidebar.width > 100 ? 20 : 8; spacing: window.height < 760 ? 4 : 12
            RowLayout {
                Layout.topMargin: window.height < 760 ? 2 : 22; Layout.bottomMargin: window.height < 760 ? 10 : 30
                Image { source: "assets/gideon-orb.png"; Layout.preferredWidth: 44; Layout.preferredHeight: 44; fillMode: Image.PreserveAspectFit }
                ColumnLayout {
                    visible: sidebar.width > 100; spacing: 2
                    Label { text: "Gideon"; color: "#f3f6ff"; font.pixelSize: 25; font.bold: true }
                    Label { text: "Assistente pessoal"; color: "#aabbe1"; font.pixelSize: 12 }
                }
            }
            Repeater {
                model: window.navigation
                GlowButton {
                    required property int index
                    required property string modelData
                    objectName: "nav" + index
                    Layout.fillWidth: true; implicitHeight: window.height < 760 ? 40 : 52
                    padding: sidebar.width < 100 ? 8 : 12
                    text: sidebar.width > 100 ? modelData : ""
                    Accessible.name: modelData
                    image: "assets/" + window.navIcons[index] + ".png"
                    accent: window.accentColor; checked: window.page === index; visible: index === 7 ? core.chatAvailable : index === 8 ? core.modelsAvailable : index === 9 ? core.perceptionAvailable : index === 10 ? core.skillsAvailable : index === 11 ? core.connectionsAvailable : true
                    onClicked: window.page = index
                    ToolTip.visible: hovered && sidebar.width < 100; ToolTip.text: modelData
                }
            }
            Item { Layout.fillHeight: true }
            Label { visible: sidebar.width > 100; text: "Base local\nEN · perfil virtual"; color: "#8fa5d0"; font.pixelSize: 12; Layout.bottomMargin: 18 }
        }
    }
    ColumnLayout {
        id: mainColumn; objectName: "mainColumn"
        anchors.left: sidebar.right; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
        anchors.margins: window.spacious ? 24 : 14; spacing: window.spacious ? 14 : 8
        RowLayout {
            Layout.fillWidth: true
            Label { text: window.navigation[window.page]; color: "#a7b9df"; font.pixelSize: 14; Layout.fillWidth: true }
            GlowButton { objectName: "hubButton"; text: window.width >= 720 ? "Plugins" : ""; image: "assets/hub.png"; Accessible.name: "Plugins"; enabled: core.connected; onClicked: hubDialog.open() }
            GlowButton { objectName: "settingsButton"; text: window.width >= 720 ? "Preferências" : ""; image: "assets/settings.png"; Accessible.name: "Preferências"; enabled: core.connected; onClicked: preferences.open() }
        }
        RowLayout {
            visible: window.page === 0 && window.spacious
            Layout.fillWidth: true; Layout.preferredHeight: 350; spacing: 14
            GlassCard {
                theme: window.themeIndex
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                RoundedImage { anchors.fill: parent; source: Qt.resolvedUrl("assets/hero-background.png"); opacity: window.themeIndex === 2 ? 0 : 0.55 }
                Image { id: heroOrb; source: "assets/gideon-orb.png"; anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; width: Math.min(parent.width * 0.47, parent.height - 24); height: width; fillMode: Image.PreserveAspectFit; visible: core.visualFeedback }
                ColumnLayout {
                    anchors.left: parent.left; anchors.leftMargin: 30; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.56; spacing: 14
                    Row { spacing: 12
                        Label { text: "Olá,"; color: "#f4f6ff"; font.pixelSize: 60; font.bold: true }
                        Label { text: "Gideon"; color: window.accentColor; font.pixelSize: 60; font.bold: true }
                    }
                    Label { text: core.connected ? "Seu Gideon, em um só lugar." : "Vamos reconectar ao Gideon."; color: "#c3d2f7"; font.pixelSize: 22; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Label { text: "Acompanhe a conversa, ajuste sua voz e conheça as capacidades disponíveis."; color: "#a8bbe2"; font.pixelSize: 16; wrapMode: Text.WordWrap; Layout.fillWidth: true; Layout.maximumWidth: 340 }
                    Label { text: "Base · áudio virtual · validação física pendente"; color: "#a6b9e2"; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                }
            }
            GlassCard {
                theme: window.themeIndex
                Layout.preferredWidth: 245; Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 20; spacing: 16
                    Label { text: "Estado do sistema"; color: "#edf2ff"; font.pixelSize: 18; font.bold: true }
                    Label { text: core.connected ? "Conectado ao Core" : "Core offline"; color: core.connected ? "#78debc" : "#f6c77e"; font.pixelSize: 13 }
                    Repeater {
                        model: ["Wake", "STT", "TTS"]
                        delegate: RowLayout {
                            required property int index
                            required property string modelData
                            Layout.fillWidth: true
                            Label { text: modelData; color: "#d8e3ff"; font.pixelSize: 15; Layout.fillWidth: true }
                            Label { text: window.statusText(index === 0 ? core.wakeStatus : index === 1 ? core.sttStatus : core.speechStatus); textFormat: Text.PlainText; color: (index === 0 ? core.wakeStatus : index === 1 ? core.sttStatus : core.speechStatus) === "unavailable" ? "#b8aaca" : "#78debc"; font.pixelSize: 12 }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#33466c" }
                    Label { text: "Privacidade"; color: "#edf2ff"; font.bold: true; font.pixelSize: 16 }
                    Label { text: "Sem histórico de conversas.\nÁudio e legendas em memória."; color: "#aabde4"; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Item { Layout.fillHeight: true }
                }
            }
        }
        RowLayout {
            visible: window.page === 0 && window.spacious
            Layout.fillWidth: true; Layout.preferredHeight: 104; spacing: 14
            Repeater {
                model: [{title:"Frase de despertar",value:window.wakeText(),icon:"voice",page:1}, {title:"Entrada de áudio",value:window.packAvailable ? "PCM virtual" : "Indisponível",icon:"audio",page:2}, {title:"Modo",value:"Base · sem LLM",icon:"hub",page:6}]
                delegate: GlassCard {
                theme: window.themeIndex
                    required property var modelData
                    Layout.fillWidth: true; Layout.fillHeight: true
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 18
                        Image { source: "assets/" + modelData.icon + ".png"; Layout.preferredWidth: 30; Layout.preferredHeight: 30 }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: modelData.title; color: "#aebfe7"; font.pixelSize: 13 }
                            Label { text: modelData.value; textFormat: Text.PlainText; color: "#f2f5ff"; font.bold: true; font.pixelSize: 17; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                        GlowButton { text: "Abrir"; Accessible.name: "Abrir " + modelData.title; onClicked: window.page = modelData.page }
                    }
                }
            }
        }
        ScrollView {
            id: pageViewport; objectName: "pageViewport"
            visible: window.page !== 0
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            ColumnLayout {
                width: pageViewport.availableWidth; spacing: 16
                GlassCard {
                theme: window.themeIndex
                    Layout.fillWidth: true; implicitHeight: window.width > 900 ? 185 : 150; clip: true
                    RoundedImage { anchors.fill: parent; source: Qt.resolvedUrl("assets/hero-background.png"); opacity: window.themeIndex === 2 ? 0 : 0.4 }
                    Image { source: "assets/gideon-orb.png"; anchors.right: parent.right; anchors.rightMargin: 26; anchors.verticalCenter: parent.verticalCenter; width: 200; height: 200; visible: window.width > 900 && core.visualFeedback }
                    ColumnLayout {
                        anchors.left: parent.left; anchors.leftMargin: 26; anchors.verticalCenter: parent.verticalCenter; width: window.width > 900 ? parent.width - 260 : parent.width - 52; spacing: 10
                        Label { text: window.navigation[window.page]; color: "#f1f5ff"; font.pixelSize: window.width > 900 ? 52 : 24; font.bold: true }
                        Label { text: window.page === 1 ? "Configure como o Gideon escuta e responde." : window.page === 3 ? "Defina o estilo visual do Gideon." : window.page === 2 ? "Sua voz, seus ajustes de áudio." : window.page === 4 ? "Cada capacidade precisa de autorização." : window.page === 5 ? "Acompanhe o estado real da Base." : window.page === 7 ? "Converse com o motor LLM opcional." : window.page === 8 ? "Escolha, teste e configure o modelo do motor LLM." : window.page === 9 ? "Teste sensores e ações simulados; nada age no seu computador." : window.page === 10 ? "Procedimentos sobre capacidades instaladas; não concedem permissões." :"Capacidades opcionais, em um só lugar."; color: "#b7caf3"; font.pixelSize: 17; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 1; Layout.fillWidth: true; implicitHeight: voiceColumn.implicitHeight + 44
                    ColumnLayout {
                        id: voiceColumn; anchors.fill: parent; anchors.margins: 22; spacing: 14
                        Label { text: "Frase de despertar"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Label { text: "Escolha uma frase qualificada do pack. A alteração requer reinício do Core."; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Flow {
                            Layout.fillWidth: true; spacing: 12; Layout.preferredHeight: childrenRect.height
                            Repeater {
                                model: core.wakeChoices
                                GlowButton {
                                    required property var modelData
                                    objectName: "wakeCard_" + modelData.id
                                    text: modelData.text + (modelData.qualification === "dev_qualified" ? " · DEV" : " · POC_REQUIRED")
                                    Accessible.name: "Frase de wake " + modelData.text
                                    checked: window.packAvailable && core.snapshotPack.active_phrase === modelData.id
                                    enabled: core.preferencesAvailable && modelData.qualification === "dev_qualified"
                                    onClicked: core.selectWake(modelData.id)
                                }
                            }
                        }
                        Label { visible: core.wakeChoices.length === 0; text: "Nenhum pack de wake configurado."; color: "#b0c3e9" }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 1 || window.page === 2; Layout.fillWidth: true; implicitHeight: captureColumn.implicitHeight + 44
                    ColumnLayout {
                        id: captureColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: window.page === 1 ? "Captura" : "Resposta por voz"; color: "#f1f5ff"; font.bold: true; font.pixelSize: 21 }
                        Label { text: window.page === 1 ? "Entrada PCM virtual · pré-roll de 1 segundo · CPU. Microfone físico, AEC e redução de ruído ainda indisponíveis." : "Pocket TTS · Alba · inglês · saída virtual. Outras vozes e dispositivos físicos ainda indisponíveis."; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { visible: window.page === 2; text: "Ganho atual: " + core.outputVolume + "%"; textFormat: Text.PlainText; color: "#b0c3e9" }
                        RowLayout {
                            visible: window.page === 2; Layout.fillWidth: true
                            Slider { id: gainSlider; objectName: "gainSlider"; from: 0; to: 100; stepSize: 5; value: core.outputVolume; enabled: core.preferencesAvailable && core.voiceAvailable; Layout.fillWidth: true; Accessible.name: "Ganho da resposta por voz" }
                            GlowButton { objectName: "applyGainButton"; text: "Aplicar"; Accessible.name: "Aplicar ganho da resposta por voz"; enabled: core.preferencesAvailable && core.voiceAvailable; onClicked: core.saveFeedback(core.visualFeedback, Math.round(gainSlider.value)) }
                        }
                        GlowButton { text: "Abrir ajustes da Base"; Accessible.name: "Abrir ajustes da Base"; enabled: core.connected; onClicked: preferences.open() }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 3; Layout.fillWidth: true; implicitHeight: appearanceColumn.implicitHeight + 44
                    ColumnLayout {
                        id: appearanceColumn; anchors.fill: parent; anchors.margins: 22; spacing: 16
                        GridLayout {
                            Layout.fillWidth: true; columns: window.width > 1000 ? 2 : 1; columnSpacing: 24; rowSpacing: 20
                            ColumnLayout { Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; spacing: 16
                        Label { text: "Tema"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Flow {
                            id: themeFlow; Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 12
                            Repeater { model: ["Gideon", "Clássico", "Minimalista"]
                                GlowButton {
                                    required property int index; required property string modelData
                                    objectName: "theme" + index; text: modelData; checked: window.themeIndex === index
                                    implicitWidth: 156; implicitHeight: 138; onClicked: window.themeIndex = index
                                    contentItem: Column {
                                        spacing: 8
                                        Rectangle {
                                            width: parent.width; height: 86; radius: 10; clip: true; color: index === 2 ? "#182233" : "#102044"
                                            Image { anchors.fill: parent; source: index === 0 ? "assets/gideon-orb.png" : "assets/hero-background.png"; fillMode: index === 0 ? Image.PreserveAspectFit : Image.PreserveAspectCrop; opacity: index === 2 ? 0.25 : 1 }
                                        }
                                        Text { text: modelData; color: "#edf2ff"; font.pixelSize: 15; font.bold: true }
                                    }
                                }
                            }
                        }
                            }
                            ColumnLayout { Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; spacing: 16
                        Label { text: "Cor de destaque"; color: "#f1f5ff"; font.pixelSize: 18; font.bold: true }
                        Flow {
                            Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 10
                            Repeater { model: [{name:"Azul",color:"#7693ff"}, {name:"Violeta",color:"#b386ff"}, {name:"Ciano",color:"#66dcf4"}, {name:"Rosa",color:"#f28bd7"}]
                                GlowButton { required property var modelData; objectName: "accent" + modelData.name; text: modelData.name; accent: modelData.color; checked: window.accentColor.toString() === modelData.color; onClicked: window.accentColor = modelData.color }
                            }
                        }
                            }
                        }
                        Label { text: "HUD visual"; color: "#f1f5ff"; font.pixelSize: 18; font.bold: true }
                        CheckBox { id: visualPage; objectName: "visualPagePreference"; text: "Mostrar esfera e indicador de atividade"; checked: core.visualFeedback; enabled: core.preferencesAvailable; onClicked: core.saveFeedback(checked, core.outputVolume) }
                        Label { text: "Estado textual, legendas e cancelamento permanecem disponíveis."; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { text: "Tema e cor se aplicam a esta janela. O indicador é salvo pelo Core."; color: "#a4b8dc"; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 4; Layout.fillWidth: true; implicitHeight: permissionsColumn.implicitHeight + 44
                    ColumnLayout { id: permissionsColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: "Comandos da Base"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Label { text: "O Hub declara permissões e registra aprovação por manifest. Plugins instalados e aprovados podem ser ativados em sandbox sem rede. Comandos da Base não dependem de plugins."; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 5; Layout.fillWidth: true; implicitHeight: diagnosticsColumn.implicitHeight + 44
                    ColumnLayout { id: diagnosticsColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: "Motores e conexão"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Label { text: core.diagnostic; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { text: core.packDescription || "Pack de voz não configurado"; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 6; Layout.fillWidth: true; implicitHeight: hubPageColumn.implicitHeight + 44
                    ColumnLayout { id: hubPageColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: core.hubDescription; color: "#b0c3e9"; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        GlowButton { text: "Explorar catálogo"; enabled: core.connected; onClicked: hubDialog.open() }
                    }
                }
                // Percepção e ação (C4): shown only while a C4 plugin runs. Controls send reads only, through core.perceptionInvoke; the Core and the plugins decide everything else.
                GlassCard {
                objectName: "perceptionPanel"
                theme: window.themeIndex
                    visible: window.page === 9 && core.perceptionAvailable; Layout.fillWidth: true; implicitHeight: perceptionColumn.implicitHeight + 44
                    ColumnLayout {
                        id: perceptionColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: "Backends simulados: nenhum hardware pessoal é acessado nesta build."; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        // Privacy indicators are always on this page: they show the last state read ("não lido" until a read).
                        Label { objectName: "micIndicator"; text: "Microfone · indicador: " + core.perceptionMicIndicator; textFormat: Text.PlainText; color: core.perceptionMicIndicator === "ligado" ? "#ffc674" : "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Indicador do microfone: " + core.perceptionMicIndicator }
                        Label { objectName: "cameraIndicator"; text: "Câmera · indicador: " + core.perceptionCameraIndicator; textFormat: Text.PlainText; color: core.perceptionCameraIndicator === "ligado" ? "#ffc674" : "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Indicador da câmera: " + core.perceptionCameraIndicator }
                        Repeater {
                            model: core.perceptionPlugins
                            delegate: Rectangle {
                                id: perceptionCard
                                required property var modelData
                                Layout.fillWidth: true; radius: 12; color: "#17294b"; border.color: "#354976"
                                implicitHeight: perceptionCardColumn.implicitHeight + 20
                                ColumnLayout {
                                    id: perceptionCardColumn; anchors.fill: parent; anchors.margins: 10; spacing: 4
                                    Label { objectName: "perceptionTitle_" + perceptionCard.modelData.plugin_id; text: perceptionCard.modelData.plugin_id + " " + perceptionCard.modelData.semver; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                    Label { objectName: "perceptionState_" + perceptionCard.modelData.plugin_id; text: "Estado: " + window.perceptionStateText(perceptionCard.modelData.state) + (perceptionCard.modelData.last_error ? " · " + perceptionCard.modelData.last_error : ""); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Label { objectName: "perceptionBadge_" + perceptionCard.modelData.plugin_id; text: perceptionCard.modelData.plugin_id === "display_manipulate" ? "UNSUPPORTED" : "SINTÉTICO — sem hardware real"; textFormat: Text.PlainText; font.bold: true; color: perceptionCard.modelData.plugin_id === "display_manipulate" ? "#ffc674" : "#78debc"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Label { text: "Permissão exigida: " + (perceptionCard.modelData.permissions.join(", ") || "nenhuma") + (perceptionCard.modelData.approved ? " · concedida" : " · não concedida"); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Label { text: "Backend real: não suportado / pendente de validação humana"; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Flow {
                                        Layout.fillWidth: true; spacing: 8
                                        Repeater {
                                            model: window.perceptionActions[perceptionCard.modelData.plugin_id] || []
                                            delegate: GlowButton {
                                                required property var modelData
                                                objectName: "perception_" + modelData.capability
                                                text: modelData.label
                                                Accessible.name: modelData.label + " " + modelData.capability
                                                enabled: core.connected && perceptionCard.modelData.state === "running" && !core.perceptionBusy
                                                onClicked: core.perceptionInvoke(modelData.capability, "{}")
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        Label { objectName: "perceptionResult"; text: core.perceptionResult; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Resultado da percepção: " + text }
                    }
                }
                // Skills (S4): list, manifest editor, LLM draft, dry run, run with per-step decisions, import preview and history. Every value is the Core snapshot 'skills' block; PlainText only.
                GlassCard {
                objectName: "skillsPanel"
                theme: window.themeIndex
                    visible: window.page === 10 && core.skillsAvailable; Layout.fillWidth: true; implicitHeight: skillsColumn.implicitHeight + 44
                    ColumnLayout {
                        id: skillsColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: "Skills"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Label { text: "Validar não grava. Simular não chama capacidades. Executar pede sua aprovação em cada passo que muda estado. Skills não concedem permissões."; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { objectName: "skillsResult"; visible: text.length > 0; text: core.skillsResult; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Resultado das skills: " + text }
                        ProgressBar { objectName: "skillsProgress"; visible: core.skillsBusy; indeterminate: true; Layout.fillWidth: true; Accessible.name: "Operação de skill em andamento" }
                        Label { text: "Entradas (JSON de objeto, até 16 KiB) para Simular e Executar"; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        TextArea {
                            id: skillInputs; objectName: "skillInputs"; Layout.fillWidth: true; text: "{}"
                            textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; color: "#dce7ff"; placeholderTextColor: "#a3b6db"
                            placeholderText: "{ \"campo\": \"valor\" }"; Accessible.name: "Entradas da skill em JSON"
                            background: Rectangle { color: "#132341"; radius: 10; border.color: "#304572" }
                        }
                        Label { text: "Skills instaladas"; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; Layout.fillWidth: true }
                        Label { objectName: "skillsEmpty"; visible: core.skillsItems.length === 0; text: "Nenhuma skill no Core ainda. Crie uma abaixo."; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Repeater {
                            model: core.skillsItems
                            delegate: Rectangle {
                                id: skillRow
                                required property var modelData
                                Layout.fillWidth: true; radius: 12; color: "#17294b"; border.color: "#354976"
                                implicitHeight: skillRowColumn.implicitHeight + 20
                                ColumnLayout {
                                    id: skillRowColumn; anchors.fill: parent; anchors.margins: 10; spacing: 4
                                    Label { objectName: "skillTitle_" + skillRow.modelData.id + "_" + skillRow.modelData.version; text: skillRow.modelData.name + " · " + skillRow.modelData.id + " v" + skillRow.modelData.version; textFormat: Text.PlainText; color: "#edf2ff"; font.bold: true; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                    Label { objectName: "skillState_" + skillRow.modelData.id + "_" + skillRow.modelData.version; text: "Estado: " + window.skillStateText(skillRow.modelData.state) + " · origem: " + window.skillSourceText(skillRow.modelData.source) + (skillRow.modelData.active ? " · versão ativa" : ""); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Label { objectName: "skillDeps_" + skillRow.modelData.id + "_" + skillRow.modelData.version; text: "Dependências: " + (skillRow.modelData.deps_ok ? "ok" : "faltando: " + skillRow.modelData.missing.join(", ")) + " · permissões: " + (skillRow.modelData.permissions_ok ? "aprovadas" : "pendentes"); textFormat: Text.PlainText; color: skillRow.modelData.deps_ok ? "#b0c3e9" : "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Flow {
                                        Layout.fillWidth: true; spacing: 8
                                        GlowButton { objectName: "skillDryRun_" + skillRow.modelData.id + "_" + skillRow.modelData.version; text: "Simular"; Accessible.name: "Simular " + skillRow.modelData.id; enabled: window.skillCan("dry", skillRow.modelData.state); onClicked: core.skillDryRun(skillRow.modelData.id, skillRow.modelData.version, skillInputs.text) }
                                        GlowButton { objectName: "skillApprove_" + skillRow.modelData.id + "_" + skillRow.modelData.version; text: "Aprovar"; Accessible.name: "Aprovar " + skillRow.modelData.id + " v" + skillRow.modelData.version; enabled: window.skillCan("approve", skillRow.modelData.state); onClicked: core.skillApprove(skillRow.modelData.id, skillRow.modelData.version) }
                                        GlowButton { objectName: "skillEnable_" + skillRow.modelData.id; text: "Habilitar"; Accessible.name: "Habilitar " + skillRow.modelData.id; enabled: window.skillCan("enable", skillRow.modelData.state); onClicked: core.skillEnable(skillRow.modelData.id) }
                                        GlowButton { objectName: "skillDisable_" + skillRow.modelData.id; text: "Desabilitar"; Accessible.name: "Desabilitar " + skillRow.modelData.id; enabled: window.skillCan("disable", skillRow.modelData.state); onClicked: core.skillDisable(skillRow.modelData.id) }
                                        GlowButton { objectName: "skillRun_" + skillRow.modelData.id; text: "Executar"; Accessible.name: "Executar " + skillRow.modelData.id; enabled: window.skillCan("run", skillRow.modelData.state); onClicked: core.skillRun(skillRow.modelData.id, skillInputs.text) }
                                        GlowButton { objectName: "skillRollback_" + skillRow.modelData.id; text: "Reverter versão"; Accessible.name: "Reverter versão de " + skillRow.modelData.id; enabled: window.skillCan("rollback", skillRow.modelData.state); onClicked: core.skillRollback(skillRow.modelData.id) }
                                        GlowButton { objectName: "skillPermissions_" + skillRow.modelData.id; text: "Permissões"; Accessible.name: "Ver permissões de " + skillRow.modelData.id; onClicked: window.skillSelected = skillRow.modelData }
                                        GlowButton { objectName: "skillExport_" + skillRow.modelData.id; text: "Exportar"; Accessible.name: "Exportar " + skillRow.modelData.id + " v" + skillRow.modelData.version; enabled: window.skillCan("export", skillRow.modelData.state); onClicked: core.skillExport(skillRow.modelData.id, skillRow.modelData.version) }
                                        GlowButton { objectName: "skillRemove_" + skillRow.modelData.id; text: "Remover"; Accessible.name: "Remover " + skillRow.modelData.id; enabled: window.skillCan("remove", skillRow.modelData.state); onClicked: { removeSkillConfirm.skill = skillRow.modelData; removeSkillConfirm.open() } }
                                    }
                                }
                            }
                        }
                        // Permissões: what the Core reports for the picked row. Required permissions are shown by the import preview, which reads the manifest.
                        ColumnLayout {
                            objectName: "skillPermissions"; visible: window.skillSelected !== null; Layout.fillWidth: true; spacing: 4
                            Label { text: window.skillSelected ? "Permissões de " + window.skillSelected.id + " v" + window.skillSelected.version : ""; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                            Label { text: window.skillSelected ? "Aprovadas no Core: " + (window.skillSelected.permissions_ok ? "sim" : "não") + "\nFaltando: " + (window.skillSelected.missing.length ? window.skillSelected.missing.join(", ") : "nada") : ""; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Label { text: "Aprovar permissões não concede nada à skill: ela só usa capacidades já instaladas e aprovadas."; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        }
                        // Criar: manifest JSON by hand, or a draft from the LLM plugin when it runs. A draft is never enabled here.
                        Label { text: "Criar skill (manifest JSON, até 16 KiB)"; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; Layout.fillWidth: true }
                        TextArea {
                            id: skillManifest; objectName: "skillManifest"; Layout.fillWidth: true
                            textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; color: "#dce7ff"; placeholderTextColor: "#a3b6db"
                            placeholderText: "schema_version 1, id, name, version, publisher, steps..."; Accessible.name: "Manifest da skill em JSON"
                            background: Rectangle { color: "#132341"; radius: 10; border.color: "#304572" }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            GlowButton { objectName: "skillValidate"; text: "Validar"; Accessible.name: "Validar manifest da skill"; enabled: !core.skillsBusy && skillManifest.text.trim().length > 0; onClicked: core.skillValidate(skillManifest.text) }
                            GlowButton { objectName: "skillSaveDraft"; text: "Salvar rascunho"; Accessible.name: "Salvar rascunho da skill"; enabled: !core.skillsBusy && skillManifest.text.trim().length > 0; onClicked: core.skillSaveDraft(skillManifest.text) }
                        }
                        Label { text: "Gerar com LLM: descreva o que a skill deve fazer (até 1024 bytes)"; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        RowLayout {
                            Layout.fillWidth: true
                            TextField {
                                id: skillDescription; objectName: "skillDescription"; Layout.fillWidth: true; maximumLength: 1024
                                color: "#dce7ff"; placeholderTextColor: "#a3b6db"; placeholderText: "Ex.: ler uma nota e salvar um resumo"
                                background: Rectangle { color: "#132341"; radius: 10; border.color: "#304572" }
                                Accessible.name: "Descrição da skill para o LLM"
                            }
                            GlowButton { objectName: "skillDraftWithLlm"; text: "Gerar com LLM"; Accessible.name: "Gerar skill com o LLM"; enabled: core.skillLlmAvailable && !core.skillsBusy && skillDescription.text.trim().length > 0; onClicked: core.skillDraftWithLlm(skillDescription.text) }
                        }
                        Label { objectName: "skillLlmUnavailable"; visible: !core.skillLlmAvailable; text: "Gerar com LLM indisponível: o plugin llm_engine não está ativo."; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        ColumnLayout {
                            objectName: "skillDraftOutput"; visible: !!core.skillDraftOutput.draft_id; Layout.fillWidth: true; spacing: 4
                            Label { text: "Rascunho " + core.skillDraftOutput.draft_id + " · v" + core.skillDraftOutput.version + " · " + window.skillStateText(core.skillDraftOutput.state) + " · nada foi habilitado"; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Label { text: "Requisitos: " + ((core.skillDraftOutput.requirements || []).join(", ") || "nenhum"); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Label { text: "Ambiguidades: " + ((core.skillDraftOutput.ambiguities || []).join("; ") || "nenhuma"); textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Label { text: "Passos previstos:\n" + ((core.skillDraftOutput.preview || []).map(function (p) { return p.id + " → " + p.call }).join("\n") || "nenhum"); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Label { visible: !!core.skillDraftOutput.diff; text: "Diferença:\n" + (core.skillDraftOutput.diff || ""); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                        }
                        // Importar: the Core reads only <home>/skill-imports/<name>.gskill and previews it; nothing is installed until the confirmation.
                        Label { text: "Importar e exportar"; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; Layout.fillWidth: true }
                        RowLayout {
                            Layout.fillWidth: true
                            TextField {
                                id: skillImportName; objectName: "skillImportName"; Layout.fillWidth: true; maximumLength: 64
                                color: "#dce7ff"; placeholderTextColor: "#a3b6db"; placeholderText: "nome do pacote, sem caminho"
                                validator: RegularExpressionValidator { regularExpression: /[A-Za-z0-9._-]{1,64}/ }
                                background: Rectangle { color: "#132341"; radius: 10; border.color: "#304572" }
                                Accessible.name: "Nome do pacote para importar"
                            }
                            GlowButton { objectName: "skillImport"; text: "Pré-visualizar"; Accessible.name: "Pré-visualizar importação de skill"; enabled: !core.skillsBusy && skillImportName.acceptableInput; onClicked: core.skillImport(skillImportName.text) }
                        }
                        ColumnLayout {
                            objectName: "skillImportPreview"; visible: !!core.skillImportPreview.name; Layout.fillWidth: true; spacing: 4
                            Label { text: "Pacote " + core.skillImportPreview.name + ": " + core.skillImportPreview.id + " v" + core.skillImportPreview.version; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                            Label { text: "Publisher: " + core.skillImportPreview.publisher + " · não verificado"; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Publisher " + core.skillImportPreview.publisher + ", não verificado" }
                            Label { text: "Permissões exigidas: " + ((core.skillImportPreview.permissions_required || []).join(", ") || "nenhuma") + "\nNovas nesta versão: " + ((core.skillImportPreview.permission_delta || []).join(", ") || "nenhuma"); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Label { visible: core.skillImportPreview.permissions_escalated === true; text: "Escalada de permissões: esta versão pede mais que a anterior; aprove de novo antes de usar."; textFormat: Text.PlainText; color: "#ff9a9a"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Label { text: "Dependências faltando: " + ((core.skillImportPreview.missing_deps || []).join(", ") || "nenhuma"); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Label { visible: core.skillImportPreview.duplicate === true; text: "Já existe uma skill com este id no Core."; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Repeater {
                                model: core.skillImportPreview.findings || []
                                delegate: Label {
                                    required property var modelData
                                    objectName: "skillFinding_" + modelData.code
                                    text: "Achado: " + core.codeMessage(modelData.code) + (modelData.field ? " (" + modelData.field + ")" : "")
                                    textFormat: Text.PlainText; color: "#ff9a9a"; wrapMode: Text.WordWrap; Layout.fillWidth: true
                                }
                            }
                            Label { text: "Importar instala como rascunho e nunca concede permissões. Valide, simule e aprove antes de usar."; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            GlowButton { objectName: "skillImportConfirm"; text: "Instalar como rascunho"; Accessible.name: "Instalar como rascunho o pacote " + core.skillImportPreview.name; enabled: !core.skillsBusy && (core.skillImportPreview.findings || []).length === 0; onClicked: core.skillImportConfirm(core.skillImportPreview.name) }
                        }
                        // Execução: progress from the Core run; each step that changes state waits for the user's decision here.
                        ColumnLayout {
                            objectName: "skillRunView"; visible: !!core.skillCurrentRun.run_id; Layout.fillWidth: true; spacing: 6
                            Label { objectName: "skillRunState"; text: "Execução " + core.skillCurrentRun.run_id + " · " + core.skillCurrentRun.skill + " · " + window.skillRunText(core.skillCurrentRun.state) + (core.skillCurrentRun.step ? " · passo " + core.skillCurrentRun.step : ""); textFormat: Text.PlainText; color: core.skillCurrentRun.state === "failed" ? "#ff9a9a" : "#f1f5ff"; font.bold: true; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true; Accessible.name: "Estado da execução: " + text }
                            Repeater {
                                model: core.skillCurrentRun.steps || []
                                delegate: Rectangle {
                                    id: stepRow
                                    required property var modelData
                                    Layout.fillWidth: true; radius: 12; color: "#132341"; border.color: "#304572"
                                    implicitHeight: stepColumn.implicitHeight + 16
                                    ColumnLayout {
                                        id: stepColumn; anchors.fill: parent; anchors.margins: 8; spacing: 4
                                        Label { objectName: "skillStep_" + stepRow.modelData.id; text: "Passo " + stepRow.modelData.id + " · " + window.skillStepText(stepRow.modelData.state) + (stepRow.modelData.code ? " · " + core.codeMessage(stepRow.modelData.code) : ""); textFormat: Text.PlainText; color: "#dce7ff"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                        RowLayout {
                                            visible: stepRow.modelData.state === "awaiting_approval"; Layout.fillWidth: true
                                            GlowButton { objectName: "skillDeny_" + stepRow.modelData.id; text: "Negar passo"; Accessible.name: "Negar o passo " + stepRow.modelData.id; onClicked: core.skillDecide(core.skillCurrentRun.run_id, stepRow.modelData.id, "deny") }
                                            GlowButton { objectName: "skillAuthorize_" + stepRow.modelData.id; text: "Autorizar passo"; Accessible.name: "Autorizar o passo " + stepRow.modelData.id; onClicked: core.skillDecide(core.skillCurrentRun.run_id, stepRow.modelData.id, "authorize") }
                                        }
                                    }
                                }
                            }
                            Label { objectName: "skillOutputs"; visible: !!core.skillCurrentRun.outputs; text: "Saídas: " + JSON.stringify(core.skillCurrentRun.outputs || {}); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                            GlowButton { objectName: "skillCancel"; text: "Cancelar execução"; Accessible.name: "Cancelar a execução da skill"; enabled: window.skillRunActive(); onClicked: core.skillCancel(core.skillCurrentRun.run_id) }
                        }
                        // Histórico: ledger of runs without content; codes and the failed step only.
                        Label { text: "Histórico de execuções"; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; Layout.fillWidth: true }
                        Label { objectName: "skillHistoryEmpty"; visible: core.skillHistory.length === 0; text: "Nenhuma execução registrada."; textFormat: Text.PlainText; color: "#b0c3e9"; Layout.fillWidth: true }
                        Repeater {
                            model: core.skillHistory
                            delegate: Label {
                                required property var modelData
                                required property int index
                                objectName: "skillHistory_" + index
                                text: modelData.run_id + " · " + modelData.skill + " v" + modelData.version + " · " + window.skillRunText(modelData.state) + (modelData.step ? " · passo " + modelData.step : "") + (modelData.codes.length ? " · " + modelData.codes.map(function (c) { return core.codeMessage(c) }).join("; ") : "")
                                textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                            }
                        }
                    }
                }
                // Modelos LLM: shown only while llm_engine runs with llm_engine.models; the Base has no models page.
                GlassCard {
                objectName: "modelsPanel"
                theme: window.themeIndex
                    visible: window.page === 8 && core.modelsAvailable; Layout.fillWidth: true; implicitHeight: modelsColumn.implicitHeight + 44
                    ColumnLayout {
                        id: modelsColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: "Modelos LLM"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Label { objectName: "modelsStatus"; text: "Estado do modelo atual: " + core.modelsStatus; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Estado do modelo atual: " + core.modelsStatus }
                        Label { objectName: "modelsSelectedLabel"; text: core.modelsSelected.provider ? "Configurado: " + core.modelsSelected.provider + " · " + core.modelsSelected.model : "Nenhum modelo configurado"; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        ProgressBar { objectName: "modelsProgress"; visible: core.modelsBusy; indeterminate: true; Layout.fillWidth: true; Accessible.name: "Operação de modelo em andamento" }
                        Label { objectName: "modelsResult"; visible: text.length > 0; text: core.modelsResult; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Resultado do modelo: " + text }
                        GlowButton { objectName: "modelsRefresh"; text: "Atualizar lista"; Accessible.name: "Atualizar lista de modelos"; enabled: core.modelsAvailable && !core.modelsBusy; onClicked: core.listModels(modelsTabs.currentIndex === 0 ? "recommended" : "custom") }
                        TabBar {
                            id: modelsTabs; objectName: "modelsTabs"; Layout.fillWidth: true
                            onCurrentIndexChanged: core.listModels(currentIndex === 0 ? "recommended" : "custom")
                            TabButton { objectName: "modelsTabRecommended"; text: "Recomendados"; Accessible.name: "Aba Recomendados" }
                            TabButton { objectName: "modelsTabCustom"; text: "Personalizados"; Accessible.name: "Aba Personalizados" }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "Mostrar:"; textFormat: Text.PlainText }
                            ComboBox { id: modelsFilter; objectName: "modelsFilter"; model: ["Todos", "Local", "Nuvem"]; Layout.fillWidth: true; Accessible.name: "Filtro por local ou nuvem" }
                        }
                        Label { objectName: "modelsEmpty"; visible: modelRows.count === 0; text: "Nenhum modelo nesta lista."; textFormat: Text.PlainText; color: "#b0c3e9"; Layout.fillWidth: true }
                        Label { objectName: "modelsCount"; text: (modelsTabs.currentIndex === 0 ? core.modelsRecommended.length + " de " + core.modelsRecommendedTotal : core.modelsCustom.length + " de " + core.modelsCustomTotal); textFormat: Text.PlainText; color: "#b0c3e9"; Layout.fillWidth: true; Accessible.name: "Modelos carregados: " + text }
                        Repeater {
                            id: modelRows
                            model: window.filteredModels(modelsTabs.currentIndex === 0 ? core.modelsRecommended : core.modelsCustom, modelsFilter.currentIndex)
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                GlowButton { objectName: "model_" + modelData.id; text: modelData.label + " · " + (modelData.kind === "local" ? "Local" : "Nuvem"); Layout.fillWidth: true; Accessible.name: "Selecionar modelo " + modelData.label + " (" + modelData.id + ")"; onClicked: window.selectModel(modelData) }
                                Label { objectName: "badge_" + modelData.id; text: core.certificationBadge(modelData.certification.state); textFormat: Text.PlainText; color: modelData.certification.state === "certified" ? "#78debc" : "#ffc674"; Accessible.name: "Certificação de " + modelData.label + ": " + text }
                            }
                        }
                        GlowButton { objectName: "modelsLoadMore"; text: "Carregar mais"; Layout.fillWidth: true; visible: modelsTabs.currentIndex === 0 ? core.modelsRecommended.length < core.modelsRecommendedTotal : core.modelsCustom.length < core.modelsCustomTotal; enabled: core.modelsAvailable && !core.modelsBusy; Accessible.name: "Carregar mais modelos"; onClicked: core.loadMoreModels(modelsTabs.currentIndex === 0 ? "recommended" : "custom") }
                        GlassCard {
                            objectName: "modelDetails"; theme: window.themeIndex
                            visible: window.selectedModel !== null; Layout.fillWidth: true; implicitHeight: detailColumn.implicitHeight + 44
                            ColumnLayout {
                                id: detailColumn; anchors.fill: parent; anchors.margins: 18; spacing: 6
                                Label { objectName: "modelDetailTitle"; text: window.selectedModel ? window.selectedModel.label : ""; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; font.pixelSize: 18; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                Label { text: window.selectedModel ? (window.selectedModel.kind === "local" ? "Local" : "Nuvem") + " · provedor " + window.selectedModel.provider + " · " + window.selectedModel.model : ""; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                Label { objectName: "modelDetailCertification"; text: window.selectedModel ? "Certificação: " + core.certificationBadge(window.selectedModel.certification.state) + (window.selectedModel.certification.evidence ? " · evidência: " + window.selectedModel.certification.evidence : "") + (window.selectedModel.certification.date ? " · data " + window.selectedModel.certification.date : "") : ""; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                Label { text: window.selectedModel ? "Licença: " + window.selectedModel.license + "\nQuantização: " + (window.selectedModel.quantization || "não se aplica") + "\nHash (SHA-256): " + (window.selectedModel.sha256 || "não se aplica") + "\nBackend: " + window.selectedModel.backend : ""; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                Repeater {
                                    model: ["streaming", "tool_use", "vision", "cancel"]
                                    delegate: Label {
                                        required property string modelData
                                        text: "Recurso " + modelData + ": " + core.featureLabel(window.selectedModel ? window.selectedModel.features[modelData] : "unknown")
                                        textFormat: Text.PlainText; color: "#b0c3e9"; Layout.fillWidth: true; wrapMode: Text.WordWrap
                                    }
                                }
                                Label { text: window.selectedModel ? "Contexto: " + (window.selectedModel.features.context_tokens === null ? "não informado" : window.selectedModel.features.context_tokens + " tokens") : ""; textFormat: Text.PlainText; color: "#b0c3e9"; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                                Label { text: window.selectedModel ? (window.selectedModel.cost.currency === null ? "Custo: não informado" : "Custo (USD por milhão de tokens): entrada " + window.selectedModel.cost.input_per_mtok + " · saída " + window.selectedModel.cost.output_per_mtok) : ""; textFormat: Text.PlainText; color: "#b0c3e9"; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                                Label { text: window.selectedModel ? "Latência: " + window.latencyText(window.selectedModel.latency_hint) + " · hardware mínimo: RAM " + (window.selectedModel.min_hardware.ram_gb === null ? "não informada" : window.selectedModel.min_hardware.ram_gb + " GB") + ", GPU " + window.gpuText(window.selectedModel.min_hardware.gpu) : ""; textFormat: Text.PlainText; color: "#b0c3e9"; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                                Label { text: window.selectedModel ? (window.selectedModel.offline ? "Funciona offline" : "Requer rede") : ""; textFormat: Text.PlainText; color: "#b0c3e9"; Layout.fillWidth: true }
                                RowLayout {
                                    Layout.fillWidth: true
                                    GlowButton { objectName: "useModelButton"; text: "Usar este modelo"; Accessible.name: window.selectedModel ? "Usar este modelo: " + window.selectedModel.label : "Usar este modelo"; enabled: core.modelsAvailable && !core.modelsBusy && window.selectedModel !== null; onClicked: core.useModel(window.selectedModel.id, window.modelsRevisionCaptured) }
                                    GlowButton { objectName: "removeCustomButton"; text: "Remover"; visible: modelsTabs.currentIndex === 1 && window.selectedModel !== null; Accessible.name: window.selectedModel ? "Remover modelo personalizado " + window.selectedModel.id : "Remover"; enabled: core.modelsAvailable && !core.modelsBusy; onClicked: { removeCustomConfirm.entry = window.selectedModel; removeCustomConfirm.open() } }
                                }
                            }
                        }
                        ColumnLayout {
                            objectName: "customForm"; visible: modelsTabs.currentIndex === 1; Layout.fillWidth: true; spacing: 8
                            Label { text: "Adicionar modelo personalizado"; color: "#f1f5ff"; font.bold: true }
                            ComboBox { id: customProvider; objectName: "customProvider"; Layout.fillWidth: true; textRole: "text"; valueRole: "id"; Accessible.name: "Provedor do modelo personalizado"; model: [{id: "local", text: "Local (llama.cpp)"}, {id: "ollama", text: "Ollama (local)"}, {id: "custom", text: "Personalizado (https)"}, {id: "openrouter", text: "OpenRouter (nuvem)"}, {id: "opencode", text: "OpenCode (nuvem)"}, {id: "google", text: "Google AI Studio (nuvem)"}] }
                            TextField { id: customModelId; objectName: "customModelId"; Layout.fillWidth: true; maximumLength: 128; placeholderText: "Identificador do modelo"; Accessible.name: "Identificador do modelo personalizado"; validator: RegularExpressionValidator { regularExpression: /[A-Za-z0-9._:\/-]{1,128}/ } }
                            SpinBox { id: customPort; objectName: "customPort"; from: 1024; to: 65535; value: 8080; editable: true; enabled: customProvider.currentValue === "local" || customProvider.currentValue === "ollama"; Accessible.name: "Porta do servidor local, de 1024 a 65535" }
                            TextField { id: customUrl; objectName: "customUrl"; Layout.fillWidth: true; maximumLength: 200; placeholderText: "https://"; enabled: customProvider.currentValue === "custom"; Accessible.name: "URL https do modelo personalizado" }
                            Label { text: "Recursos declarados (não certificados)"; color: "#b0c3e9"; Layout.fillWidth: true }
                            GridLayout {
                                Layout.fillWidth: true; columns: window.width > 900 ? 2 : 1; columnSpacing: 12
                                ComboBox { id: customStreaming; objectName: "customStreaming"; Layout.fillWidth: true; model: window.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Streaming declarado" }
                                ComboBox { id: customToolUse; objectName: "customToolUse"; Layout.fillWidth: true; model: window.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Tool use declarado" }
                                ComboBox { id: customVision; objectName: "customVision"; Layout.fillWidth: true; model: window.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Visão declarada" }
                                ComboBox { id: customCancel; objectName: "customCancel"; Layout.fillWidth: true; model: window.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Cancelamento declarado" }
                            }
                            Label { objectName: "customFormProblem"; visible: text.length > 0; text: core.customFormProblem(window.customForm()); textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            GlowButton { objectName: "saveCustomButton"; text: "Salvar modelo personalizado"; Accessible.name: "Salvar modelo personalizado"; enabled: core.modelsAvailable && !core.modelsBusy && core.customFormProblem(window.customForm()) === ""; onClicked: core.saveCustomModel(window.customForm()) }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 8
                            Label { text: "Fallback (opcional)"; color: "#f1f5ff"; font.bold: true }
                            Label { objectName: "fallbackCurrent"; text: core.modelsFallback.provider ? "Atual: " + core.modelsFallback.provider + " · " + core.modelsFallback.model : "Nenhum fallback configurado"; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            ComboBox { id: fallbackPick; objectName: "fallbackModel"; Layout.fillWidth: true; model: window.allModels(); textRole: "label"; valueRole: "id"; Accessible.name: "Modelo para fallback" }
                            Label { objectName: "fallbackCloudWarning"; visible: window.fallbackIsCloud(); text: "Mensagens poderão ir para a nuvem se o modelo principal falhar"; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Aviso: envio à nuvem no fallback" }
                            Label { objectName: "fallbackConsentNeeded"; visible: window.fallbackIsCloud() && core.llmConfig.cloud_consent !== true; text: "Para fallback na nuvem, marque o consentimento em Motor LLM."; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            RowLayout {
                                Layout.fillWidth: true
                                GlowButton { objectName: "setFallbackButton"; text: "Usar como fallback"; Accessible.name: "Usar o modelo escolhido como fallback"; enabled: core.modelsAvailable && !core.modelsBusy && fallbackPick.currentIndex >= 0 && window.fallbackAllowed(); onClicked: core.setFallback(fallbackPick.currentValue, window.modelsRevisionCaptured) }
                                GlowButton { objectName: "clearFallbackButton"; text: "Remover fallback"; Accessible.name: "Remover fallback"; enabled: core.modelsAvailable && !core.modelsBusy && !!core.modelsFallback.provider; onClicked: core.clearFallback(window.modelsRevisionCaptured) }
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 6
                            Label { text: "Hardware"; color: "#f1f5ff"; font.bold: true }
                            Label { objectName: "modelsHardware"; text: core.modelsHardware.cpu_cores ? "CPU: " + core.modelsHardware.cpu_cores + " núcleos · RAM: " + (core.modelsHardware.ram_gb === null ? "desconhecida" : core.modelsHardware.ram_gb + " GB") + " · GPU: " + (core.modelsHardware.gpu === "unknown" ? "desconhecido" : core.modelsHardware.gpu) : "Hardware: aguardando catálogo"; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            GlowButton { objectName: "clearPluginSettingsButton"; text: "Apagar dados do plugin"; Accessible.name: "Apagar dados do plugin LLM"; enabled: core.connected && !core.modelsBusy; onClicked: clearPluginConfirm.open() }
                        }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 7 && !core.chatAvailable; Layout.fillWidth: true; implicitHeight: chatOffColumn.implicitHeight + 44
                    ColumnLayout {
                        id: chatOffColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { objectName: "chatUnavailable"; text: "Motor LLM não está ativo. O plugin llm_engine é opcional: instale e ative pelo Gideon Hub. Voz, wake e comandos da Base funcionam sem ele."; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                GlassCard {
                objectName: "chatPanel"
                theme: window.themeIndex
                    visible: window.page === 7 && core.chatAvailable; Layout.fillWidth: true; implicitHeight: chatColumn.implicitHeight + 44
                    ColumnLayout {
                        id: chatColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: "Conversa"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Label { objectName: "chatState"; text: "Estado: " + core.chatStateLabel; textFormat: Text.PlainText; color: "#b0c3e9"; Accessible.name: "Estado da conversa: " + core.chatStateLabel }
                        Label { objectName: "chatConsentHint"; visible: core.llmConfig.cloud_consent !== true; text: "Consentimento de nuvem desativado: envios são recusados até você marcá-lo em Motor LLM."; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { objectName: "chatEmpty"; visible: core.chatMessages.length === 0 && core.chatState === "idle"; text: "Nenhuma mensagem ainda. O motor LLM é opcional: voz, wake e comandos da Base funcionam sem ele."; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Repeater {
                            model: core.chatMessages
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true; radius: 12; color: modelData.role === "user" ? "#243b66" : "#132341"; border.color: "#304572"
                                implicitHeight: bubbleColumn.implicitHeight + 20
                                ColumnLayout {
                                    id: bubbleColumn; anchors.fill: parent; anchors.margins: 10; spacing: 4
                                    Label { text: (modelData.role === "user" ? "Você" : "Gideon") + (modelData.state === "cancelled" ? " · cancelada" : modelData.state === "error" ? " · erro" : ""); textFormat: Text.PlainText; color: "#aebfe7"; font.pixelSize: 12 }
                                    TextEdit { text: modelData.text || "(sem texto)"; readOnly: true; selectByMouse: true; textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; color: "#edf2ff"; Layout.fillWidth: true; Accessible.name: (modelData.role === "user" ? "Mensagem enviada: " : "Resposta: ") + text }
                                }
                            }
                        }
                        Rectangle {
                            objectName: "chatStreaming"
                            visible: core.chatState === "waiting" || core.chatState === "streaming"
                            Layout.fillWidth: true; radius: 12; color: "#132341"; border.color: "#5a73b5"
                            implicitHeight: streamColumn.implicitHeight + 20
                            ColumnLayout {
                                id: streamColumn; anchors.fill: parent; anchors.margins: 10; spacing: 4
                                Label { text: core.chatStateLabel; textFormat: Text.PlainText; color: "#aebfe7"; font.pixelSize: 12 }
                                TextEdit { text: core.chatPartial || "Aguardando resposta…"; readOnly: true; selectByMouse: true; textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; color: "#dce7ff"; Layout.fillWidth: true; Accessible.name: "Resposta em andamento" }
                            }
                        }
                        Repeater {
                            model: core.toolProposals
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true; radius: 12; color: "#17294b"; border.color: "#354976"
                                implicitHeight: toolColumn.implicitHeight + 20
                                ColumnLayout {
                                    id: toolColumn; anchors.fill: parent; anchors.margins: 10; spacing: 6
                                    Label { objectName: "toolTitle_" + modelData.proposal_id; text: "Ferramenta " + modelData.tool + " · " + window.toolStateText(modelData.state); textFormat: Text.PlainText; color: "#edf2ff"; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    // S5: a connection proposal names its provider, account, operation and risk before the user decides (PlainText, from the snapshot).
                                    Label { objectName: "connProposal_" + modelData.proposal_id; visible: modelData.kind === "connection"; text: window.connProposalText(modelData); textFormat: Text.PlainText; color: "#dce7ff"; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Proposta de conexão: " + text }
                                    Label { text: "Argumentos: " + JSON.stringify(modelData.args); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                    Label { visible: modelData.reason !== null; text: "Motivo: " + core.codeMessage(modelData.reason || ""); textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Label { visible: modelData.result !== null; text: "Resultado: " + (modelData.result || ""); textFormat: Text.PlainText; color: "#78debc"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    // Only a pending proposal offers decisions. Negar is listed first: it is the safe choice.
                                    RowLayout {
                                        visible: modelData.state === "pending"; Layout.fillWidth: true
                                        GlowButton { objectName: "deny_" + modelData.proposal_id; text: "Negar"; Accessible.name: "Negar " + modelData.tool + " " + modelData.proposal_id; onClicked: core.decideTool(modelData.proposal_id, "deny") }
                                        GlowButton { objectName: "authorize_" + modelData.proposal_id; text: "Autorizar"; Accessible.name: "Autorizar " + modelData.tool + " " + modelData.proposal_id; onClicked: core.decideTool(modelData.proposal_id, "authorize") }
                                    }
                                }
                            }
                        }
                        Label { objectName: "toolResult"; visible: core.toolResult.length > 0; text: core.toolResult; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { objectName: "chatResult"; visible: core.chatResult.length > 0; text: core.chatResult; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Aviso da conversa: " + text }
                        RowLayout {
                            Layout.fillWidth: true
                            TextField {
                                id: chatInput; objectName: "chatInput"; Layout.fillWidth: true
                                maximumLength: 4096; placeholderText: "Mensagem para o motor LLM"; Accessible.name: "Mensagem para o motor LLM"
                                enabled: core.chatAvailable && core.chatState !== "waiting" && core.chatState !== "streaming"
                                color: "#dce7ff"; placeholderTextColor: "#a3b6db"
                                background: Rectangle { color: "#132341"; radius: 10; border.color: "#304572" }
                                Component.onCompleted: text = window.draftValue("#chat", "text")
                                onTextEdited: window.setDraft("#chat", "text", text)
                                onAccepted: window.sendChatDraft()
                            }
                            GlowButton { objectName: "chatSend"; text: "Enviar"; Accessible.name: "Enviar mensagem ao motor LLM"; enabled: core.chatAvailable && chatInput.enabled && core.chatTextProblem(chatInput.text) === ""; onClicked: window.sendChatDraft() }
                            GlowButton { objectName: "chatCancel"; text: "Cancelar"; Accessible.name: "Cancelar resposta do motor LLM"; enabled: core.chatState === "waiting" || core.chatState === "streaming"; onClicked: core.cancelChat() }
                        }
                        Label { objectName: "chatInputProblem"; visible: chatInput.text.length > 0 && core.chatTextProblem(chatInput.text).length > 0; text: core.chatTextProblem(chatInput.text); textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                // S5 connections: accounts, consent per scope, operations with risk labels, read-only tests and the last call. Everything shown comes from the Core snapshot 'connections' block; PlainText only.
                GlassCard {
                objectName: "connectionsPanel"
                theme: window.themeIndex
                    visible: window.page === 11 && core.connectionsAvailable; Layout.fillWidth: true; implicitHeight: connectionsColumn.implicitHeight + 44
                    ColumnLayout {
                        id: connectionsColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: "Conexões"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Label { text: "Gideon usa a API autorizada de cada serviço. Você concede cada escopo; escrita e ações públicas pedem aprovação. Neste ambiente, todas as contas são servidores falsos."; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { objectName: "connectionsResult"; visible: text.length > 0; text: core.connectionsResult; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Resultado das conexões: " + text }
                        ProgressBar { objectName: "connectionsProgress"; visible: core.connectionsBusy; indeterminate: true; Layout.fillWidth: true; Accessible.name: "Operação de conexão em andamento" }
                        Label { text: "Nova conta"; color: "#f1f5ff"; font.bold: true; Layout.fillWidth: true }
                        Flow {
                            Layout.fillWidth: true; spacing: 10
                            ComboBox { id: connProviderPick; objectName: "connectionProvider"; model: window.connProviderChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Provedor da nova conta" }
                            TextField {
                                id: connLabel; objectName: "connectionLabel"; width: Math.max(160, Math.min(320, connectionsColumn.width - 300))
                                maximumLength: 64; placeholderText: "Nome da conta (ex.: Casa)"; Accessible.name: "Nome da nova conta"
                                color: "#dce7ff"; placeholderTextColor: "#a3b6db"
                                background: Rectangle { color: "#132341"; radius: 10; border.color: "#304572" }
                            }
                            GlowButton { objectName: "connectionAdd"; text: "Adicionar conta"; Accessible.name: "Adicionar conta"; enabled: !core.connectionsBusy && core.connectionLabelProblem(connLabel.text) === "" && core.connectionsItems.length < 8; onClicked: core.connectionAdd(connProviderPick.currentValue, connLabel.text) }
                        }
                        Label { objectName: "connectionLabelProblem"; visible: connLabel.text.length > 0 && core.connectionLabelProblem(connLabel.text).length > 0; text: core.connectionLabelProblem(connLabel.text); textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { objectName: "connectionsEmpty"; visible: core.connectionsItems.length === 0; text: "Nenhuma conta ainda. Adicione uma acima."; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Repeater {
                            model: core.connectionsItems
                            delegate: Rectangle {
                                id: connCard
                                required property var modelData
                                Layout.fillWidth: true; radius: 12; color: "#17294b"; border.color: "#354976"
                                implicitHeight: connColumn.implicitHeight + 20
                                ColumnLayout {
                                    id: connColumn; anchors.fill: parent; anchors.margins: 10; spacing: 5
                                    Label { objectName: "connTitle_" + connCard.modelData.id; text: connCard.modelData.label + " · " + window.connProviderName(connCard.modelData.provider); textFormat: Text.PlainText; color: "#edf2ff"; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Label { objectName: "connFake_" + connCard.modelData.id; visible: connCard.modelData.fake === true; text: "SERVIDOR FALSO — sem credenciais reais"; textFormat: Text.PlainText; color: "#ffc674"; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Label { objectName: "connStatus_" + connCard.modelData.id; text: "Estado: " + window.connStatusText(connCard.modelData.status); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Estado da conta " + connCard.modelData.label + ": " + text }
                                    Label { objectName: "connAccount_" + connCard.modelData.id; visible: !!connCard.modelData.account_ref; text: "Conta no serviço: " + (connCard.modelData.account_ref || ""); textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Label { objectName: "connUserCode_" + connCard.modelData.id; visible: connCard.modelData.status === "connecting" && !!connCard.modelData.user_code; text: "Código para confirmar no servidor: " + (connCard.modelData.user_code || ""); textFormat: Text.PlainText; color: "#edf2ff"; font.bold: true; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true; Accessible.name: "Código de confirmação: " + (connCard.modelData.user_code || "") }
                                    Label { objectName: "connGranted_" + connCard.modelData.id; text: "Escopos concedidos: " + window.connScopeNames(connCard.modelData.granted_scopes); textFormat: Text.PlainText; color: "#78debc"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Label { objectName: "connPending_" + connCard.modelData.id; visible: (connCard.modelData.pending_scopes || []).length > 0; text: "Escopos pedidos, aguardando seu consentimento: " + window.connScopeNames(connCard.modelData.pending_scopes); textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    // Consent is per scope. Nothing is pre-checked; the Core records only what is checked and sent.
                                    Repeater {
                                        model: connCard.modelData.pending_scopes || []
                                        delegate: CheckBox {
                                            required property string modelData
                                            objectName: "connScope_" + connCard.modelData.id + "_" + modelData
                                            text: window.connScopeLabel(connCard.modelData.provider, modelData) + " (" + modelData + ")"
                                            checked: window.draftValue("#conn:" + connCard.modelData.id, modelData) === true
                                            onToggled: { window.setDraft("#conn:" + connCard.modelData.id, modelData, checked); window.connDraftRevision++ }
                                            Accessible.name: "Consentir escopo " + modelData + " de " + connCard.modelData.label
                                        }
                                    }
                                    // S5 E2.3 Home Assistant: the long-lived token is typed once into a hidden field and sent to the Core;
                                    // the field is cleared right after the send. The token is never kept in a property or shown back.
                                    Flow {
                                        Layout.fillWidth: true; spacing: 8
                                        visible: connCard.modelData.provider === "homeassistant" && connCard.modelData.status === "connecting"
                                        TextField {
                                            id: connTokenField; objectName: "connToken_" + connCard.modelData.id; echoMode: TextInput.Password
                                            inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoAutoUppercase | Qt.ImhNoPredictiveText; maximumLength: 256
                                            placeholderText: "Token de longa duração do Home Assistant"; Accessible.name: "Token do Home Assistant de " + connCard.modelData.label
                                            color: "#dce7ff"; placeholderTextColor: "#a3b6db"; width: Math.max(200, Math.min(420, connectionsColumn.width - 160))
                                            background: Rectangle { color: "#132341"; radius: 10; border.color: "#304572" }
                                        }
                                        GlowButton { objectName: "connSetToken_" + connCard.modelData.id; text: "Enviar token"; Accessible.name: "Enviar token de " + connCard.modelData.label; enabled: !core.connectionsBusy && connTokenField.text.length >= 16 && connTokenField.text.length <= 256; onClicked: { core.connectionSetToken(connCard.modelData.id, connTokenField.text); connTokenField.clear() } }
                                    }
                                    Flow {
                                        Layout.fillWidth: true; spacing: 8
                                        GlowButton { objectName: "connConsent_" + connCard.modelData.id; visible: (connCard.modelData.pending_scopes || []).length > 0; text: "Consentir escopos marcados"; Accessible.name: "Consentir escopos marcados de " + connCard.modelData.label; enabled: !core.connectionsBusy && window.connConsentList(connCard.modelData).length > 0; onClicked: core.connectionConsent(connCard.modelData.id, JSON.stringify(window.connConsentList(connCard.modelData))) }
                                        GlowButton { objectName: "connConnect_" + connCard.modelData.id; text: "Conectar"; Accessible.name: "Conectar " + connCard.modelData.label; enabled: window.connCan("connect", connCard.modelData); onClicked: core.connectionConnect(connCard.modelData.id) }
                                        GlowButton { objectName: "connRefresh_" + connCard.modelData.id; text: "Atualizar"; Accessible.name: "Atualizar " + connCard.modelData.label; enabled: window.connCan("refresh", connCard.modelData); onClicked: core.connectionRefresh(connCard.modelData.id) }
                                        GlowButton { objectName: "connDisconnect_" + connCard.modelData.id; text: "Desconectar"; Accessible.name: "Desconectar " + connCard.modelData.label; enabled: window.connCan("disconnect", connCard.modelData); onClicked: core.connectionDisconnect(connCard.modelData.id) }
                                        GlowButton { objectName: "connRevoke_" + connCard.modelData.id; text: "Revogar"; Accessible.name: "Revogar acesso de " + connCard.modelData.label; enabled: window.connCan("revoke", connCard.modelData); onClicked: core.connectionRevoke(connCard.modelData.id) }
                                        GlowButton { objectName: "connRemove_" + connCard.modelData.id; text: "Remover"; Accessible.name: "Remover " + connCard.modelData.label; enabled: window.connCan("remove", connCard.modelData); onClicked: core.connectionRemove(connCard.modelData.id) }
                                    }
                                    // S5 E2.4: tools the MCP server listed. Names, risk and trust come from the Core; the description is server text, shown as PlainText and never sent to the model.
                                    Label { objectName: "connToolsTitle_" + connCard.modelData.id; visible: (connCard.modelData.tools || []).length > 0; text: "Ferramentas descobertas (a descrição vem do servidor e é só texto)"; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Repeater {
                                        model: connCard.modelData.tools || []
                                        delegate: ColumnLayout {
                                            id: toolRow
                                            required property var modelData
                                            Layout.fillWidth: true; spacing: 2
                                            RowLayout {
                                                Layout.fillWidth: true; spacing: 8
                                                Label { objectName: "connTool_" + connCard.modelData.id + "_" + toolRow.modelData.name; text: toolRow.modelData.name + " · " + window.connToolRiskText(toolRow.modelData.risk) + " · " + window.connToolStateText(toolRow.modelData.state) + (toolRow.modelData.reason ? " (" + toolRow.modelData.reason + ")" : ""); textFormat: Text.PlainText; color: toolRow.modelData.state === "trusted" ? "#78debc" : "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                                GlowButton { objectName: "connTrust_" + connCard.modelData.id + "_" + toolRow.modelData.name; visible: toolRow.modelData.state === "needs_reapproval"; text: "Confiar"; Accessible.name: "Confiar na ferramenta " + toolRow.modelData.name + " de " + connCard.modelData.label; enabled: !core.connectionsBusy; onClicked: core.connectionTrustTools(connCard.modelData.id, JSON.stringify([toolRow.modelData.name])) }
                                            }
                                            Label { objectName: "connToolDesc_" + connCard.modelData.id + "_" + toolRow.modelData.name; visible: toolRow.modelData.description.length > 0; text: "Descrição do servidor: " + toolRow.modelData.description; textFormat: Text.PlainText; color: "#a6b9df"; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                        }
                                    }
                                    Label { text: "Operações"; textFormat: Text.PlainText; color: "#f1f5ff"; font.bold: true; Layout.fillWidth: true }
                                    Repeater {
                                        model: window.connOperationsFor(connCard.modelData)
                                        delegate: RowLayout {
                                            required property var modelData
                                            Layout.fillWidth: true; spacing: 8
                                            Label { objectName: "connOp_" + connCard.modelData.id + "_" + modelData.name; text: modelData.name + " (" + window.connOpLabel(modelData.name) + ") · " + window.connRiskText(modelData.risk) + (window.connGranted(connCard.modelData, modelData.scope) ? "" : " · escopo não concedido"); textFormat: Text.PlainText; color: "#dce7ff"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                            GlowButton { objectName: "connTest_" + connCard.modelData.id + "_" + modelData.name; visible: modelData.risk === "read" && modelData.name !== "state.get"; text: "Testar leitura"; Accessible.name: "Testar leitura " + modelData.name + " de " + connCard.modelData.label; enabled: window.connCanTest(connCard.modelData, modelData); onClicked: core.connectionCall(connCard.modelData.id, modelData.name, "{}") }
                                        }
                                    }
                                }
                            }
                        }
                        Label { objectName: "connLastCall"; visible: core.connectionLastCall.operation !== undefined; text: "Última chamada: " + (core.connectionLastCall.operation || "") + " · " + window.connOutcomeText(core.connectionLastCall); textFormat: Text.PlainText; color: "#78debc"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Última chamada de conexão: " + text }
                    }
                }
                // S5 E3 CapabilityRegistry: the chosen route per purpose, the discarded ones with their reasons, and the user's visual-fallback switch (off by default). PlainText only; planning executes nothing.
                GlassCard {
                objectName: "routesPanel"
                theme: window.themeIndex
                    visible: window.page === 11 && core.registryAvailable; Layout.fillWidth: true; implicitHeight: routesColumn.implicitHeight + 44
                    ColumnLayout {
                        id: routesColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: "Rotas"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Label { text: "Para cada finalidade o Core escolhe o melhor caminho por: autorização, segurança, suporte oficial, confiabilidade, privacidade e menos efeitos colaterais. Planejar não executa nada."; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { objectName: "routesResult"; visible: text.length > 0; text: core.registryResult; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Resultado das rotas: " + text }
                        Repeater {
                            model: core.registryPurposes
                            delegate: Rectangle {
                                id: routeCard
                                required property var modelData
                                Layout.fillWidth: true; radius: 12; color: "#17294b"; border.color: "#354976"
                                implicitHeight: routeColumn.implicitHeight + 20
                                ColumnLayout {
                                    id: routeColumn; anchors.fill: parent; anchors.margins: 10; spacing: 5
                                    Label { objectName: "routePurpose_" + routeCard.modelData.id; text: routeCard.modelData.label + " · " + window.regChosenText(routeCard.modelData); textFormat: Text.PlainText; color: routeCard.modelData.route_chosen ? "#78debc" : "#ffc674"; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Finalidade: " + text }
                                    Repeater {
                                        model: routeCard.modelData.candidates
                                        delegate: Label {
                                            required property var modelData
                                            objectName: "routeCandidate_" + routeCard.modelData.id + "_" + modelData.route
                                            text: (routeCard.modelData.route_chosen === modelData.route ? "Escolhida · " : "Descartada · ") + window.regRouteText(modelData.route) + " · " + window.regStatusText(modelData.status) + " · " + modelData.reason
                                            textFormat: Text.PlainText; color: "#dce7ff"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: text
                                        }
                                    }
                                    Flow {
                                        Layout.fillWidth: true; spacing: 10
                                        GlowButton { objectName: "routePlan_" + routeCard.modelData.id; text: "Planejar"; Accessible.name: "Planejar rota de " + routeCard.modelData.label; enabled: !core.registryBusy; onClicked: core.registryPlan(routeCard.modelData.id) }
                                        GlowButton {
                                            objectName: "routeVisual_" + routeCard.modelData.id; visible: window.regVisualPurposes.indexOf(routeCard.modelData.id) >= 0
                                            text: window.regVisualOn(routeCard.modelData.id) ? "Desligar fallback visual (revogar)" : "Ligar fallback visual"
                                            Accessible.name: text + " de " + routeCard.modelData.label; enabled: !core.registryBusy
                                            onClicked: core.registryAllowVisual(routeCard.modelData.id, !window.regVisualOn(routeCard.modelData.id))
                                        }
                                    }
                                    Label { objectName: "routeVisualState_" + routeCard.modelData.id; visible: window.regVisualPurposes.indexOf(routeCard.modelData.id) >= 0; text: "Fallback visual: " + (window.regVisualOn(routeCard.modelData.id) ? "ligado por você" : "desligado (padrão)"); textFormat: Text.PlainText; color: window.regVisualOn(routeCard.modelData.id) ? "#ffc674" : "#a6b9df"; Layout.fillWidth: true }
                                    Label { objectName: "routeVisualWarning_" + routeCard.modelData.id; visible: window.regVisualPurposes.indexOf(routeCard.modelData.id) >= 0; text: core.registryVisualWarning; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                }
                            }
                        }
                    }
                }
                // C3 agent: same visibility rule as the chat, only while the LLM plugin runs. Everything shown comes from the Core snapshot 'agent' block.
                GlassCard {
                objectName: "agentPanel"
                theme: window.themeIndex
                    visible: window.page === 7 && core.chatAvailable; Layout.fillWidth: true; implicitHeight: agentColumn.implicitHeight + 44
                    ColumnLayout {
                        id: agentColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: "Agente"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        // Banner: the run state in words, with the Core code when the run ended on one. Hidden without a run.
                        Label { objectName: "agentBanner"; visible: core.agentState.length > 0; text: core.agentStateLabel; textFormat: Text.PlainText; color: core.agentState === "failed" || core.agentState === "blocked" ? "#ff9a9a" : "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Estado do agente: " + text }
                        Label { objectName: "agentBudget"; visible: core.agentState.length > 0; text: "Tokens: " + (core.agentBudget.tokens_used || 0) + " de " + (core.agentBudget.tokens_max || 0); textFormat: Text.PlainText; color: "#a6b9df"; font.pixelSize: 12; Layout.fillWidth: true }
                        TextField {
                            id: agentGoal; objectName: "agentGoal"; Layout.fillWidth: true
                            maximumLength: 1024; placeholderText: "Objetivo para o agente"; Accessible.name: "Objetivo para o agente"
                            enabled: !core.agentActive
                            color: "#dce7ff"; placeholderTextColor: "#a3b6db"
                            background: Rectangle { color: "#132341"; radius: 10; border.color: "#304572" }
                            Component.onCompleted: text = window.draftValue("#agent", "goal")
                            onTextEdited: window.setDraft("#agent", "goal", text)
                        }
                        Label { objectName: "agentGoalProblem"; visible: agentGoal.text.length > 0 && core.agentGoalProblem(agentGoal.text).length > 0; text: core.agentGoalProblem(agentGoal.text); textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        RowLayout {
                            Layout.fillWidth: true
                            GlowButton { objectName: "agentStart"; text: "Iniciar"; Accessible.name: "Iniciar agente"; enabled: core.chatAvailable && !core.agentActive && core.agentGoalProblem(agentGoal.text) === ""; onClicked: core.agentStart(agentGoal.text) }
                            GlowButton { objectName: "agentAbort"; text: "Abortar"; Accessible.name: "Abortar agente"; enabled: core.agentActive; onClicked: core.agentAbort() }
                        }
                        Repeater {
                            model: core.agentSteps
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true; radius: 12; color: "#17294b"; border.color: "#354976"
                                implicitHeight: stepColumn.implicitHeight + 20
                                ColumnLayout {
                                    id: stepColumn; anchors.fill: parent; anchors.margins: 10; spacing: 4
                                    Label { objectName: "agentStep_" + modelData.n + "_" + modelData.kind; text: "Passo " + modelData.n + " · " + (modelData.kind === "tool" ? "ferramenta " + (modelData.tool || "?") + " · risco " + window.agentRiskText(modelData.risk) : "modelo") + " · " + window.agentStepText(modelData.state) + (modelData.code ? " · " + core.codeMessage(modelData.code) : ""); textFormat: Text.PlainText; color: "#dce7ff"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                }
                            }
                        }
                        // The final answer is model text: PlainText only, never rich text.
                        Text { objectName: "agentAnswer"; visible: core.agentAnswer.length > 0; text: core.agentAnswer; textFormat: Text.PlainText; color: "#edf2ff"; wrapMode: Text.Wrap; Layout.fillWidth: true; Accessible.name: "Resposta final do agente" }
                        Label { objectName: "agentResult"; visible: core.agentResult.length > 0; text: core.agentResult; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Aviso do agente: " + text }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Image { objectName: "activityIndicator"; source: "assets/gideon-orb.png"; visible: core.visualFeedback; Layout.preferredWidth: 38; Layout.preferredHeight: 38; fillMode: Image.PreserveAspectFit; Accessible.name: "Indicador visual do Gideon" }
            // Announce state changes: the description follows the text, so assistive tech reads the new state.
            Label { objectName: "aura"; text: window.stateLabels[core.state] || "Erro"; textFormat: Text.PlainText; color: "#e6edf4"; font.pixelSize: 20; Layout.fillWidth: true; Accessible.role: Accessible.StaticText; Accessible.name: "Estado do Gideon"; Accessible.description: text }
            GlowButton { objectName: "cancelButton"; text: "Cancelar"; enabled: core.connected && core.sessionId.length > 0; onClicked: core.cancel(); Accessible.name: "Cancelar sessão" }
        }
        ScrollView {
            objectName: "transcriptViewport"; visible: window.page === 0 || core.sessionId.length > 0
            Layout.minimumHeight: 48; Layout.preferredHeight: window.page === 0 ? 90 : 56; Layout.fillWidth: true; Layout.fillHeight: window.page === 0
            TextArea { objectName: "subtitle"; text: core.subtitle; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; color: "#dce7ff"; font.pixelSize: 18; placeholderText: "Sua conversa aparecerá aqui."; Accessible.name: core.partial ? "Transcrição parcial" : "Transcrição final"; background: Rectangle { color: "#132341"; radius: 16; border.color: "#304572" } }
        }
        Label { objectName: "result"; visible: core.result.length > 0 && (window.page === 0 || core.sessionId.length > 0); text: core.result; Layout.fillWidth: true; wrapMode: Text.WordWrap; textFormat: Text.PlainText; color: core.resultVerified ? "#78debc" : "#ffc674"; Accessible.name: "Resultado: " + text }
        RowLayout {
            visible: window.page === 0 || core.sessionId.length > 0
            Layout.fillWidth: true
            TextField { id: input; objectName: "textInput"; color: "#dce7ff"; placeholderTextColor: "#a3b6db"; background: Rectangle { color: "#132341"; radius: 10; border.color: "#304572" } Layout.fillWidth: true; enabled: core.textAvailable; placeholderText: "Comando de texto no perfil de teste"; maximumLength: 512; Accessible.name: "Comando de texto"; onAccepted: { if (core.textAvailable && text.trim().length > 0) core.submitText(text) } }
            GlowButton { objectName: "sendButton"; text: "Enviar"; Accessible.name: "Enviar comando de texto"; enabled: core.textAvailable && input.text.trim().length > 0; onClicked: core.submitText(input.text) }
        }
        Label { objectName: "textResult"; visible: text.length > 0 && (window.page === 0 || core.sessionId.length > 0); text: core.textResult; textFormat: Text.PlainText; color: "#ffc674"; wrapMode: Text.WordWrap; Layout.fillWidth: true; font.pixelSize: 12 }
        Label { objectName: "diagnostics"; text: core.configurationMessage || ("Áudio virtual · " + core.diagnostic); textFormat: Text.PlainText; color: "#a6b9df"; wrapMode: Text.WordWrap; Layout.fillWidth: true; font.pixelSize: 12; Accessible.name: "Diagnóstico: " + text }
    }
}
