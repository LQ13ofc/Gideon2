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
    // Per-plugin drafts survive delegate recreation (keyed by plugin_id). Plain JS, not reactive by design.
    property var drafts: ({})
    property int page: 0
    property int themeIndex: 0
    property color accentColor: "#7693ff"
    readonly property string preferencesSuccess: "Preferências salvas pelo Core"
    readonly property bool spacious: width >= 1080 && height >= 760
    readonly property bool packAvailable: core.wakeChoices.length > 0
    readonly property var navigation: ["Início", "Voz e Wake", "Áudio", "Aparência", "Permissões", "Diagnóstico", "Gideon Hub", "Conversa"]
    readonly property var navIcons: ["home", "voice", "audio", "appearance", "permissions", "diagnostics", "hub", "voice"]
    readonly property var stateLabels: ({idle:"Em espera", capturing:"Ouvindo", transcribing:"Transcrevendo", executing:"Executando", speaking:"Respondendo", offline:"Core indisponível", safe_mode:"Modo seguro", restart_required:"Reinício necessário"})
    readonly property var statusLabels: ({unavailable:"Indisponível", idle:"Em espera", ready:"Pronto", starting:"Iniciando", replaying:"Reproduzindo", replay_finished:"Replay encerrado", failed:"Falhou", completed:"Concluído", speaking:"Respondendo", muted:"Mudo", disabled:"Desligado", cancelled:"Cancelado", timed_out:"Tempo esgotado", audio_error:"Erro de áudio", stt_failed:"Falha na transcrição", stt_unavailable:"Transcrição indisponível", transcript_final:"Transcrição final", capture_completed:"Captura concluída", no_speech:"Sem fala detectada", capture_too_long:"Captura longa demais"})
    function statusText(status) { return statusLabels[status] || "Indisponível"; }
    function draftValue(pluginId, key) { var d = drafts[pluginId]; return d && d[key] !== undefined ? d[key] : ""; }
    function setDraft(pluginId, key, value) { if (!drafts[pluginId]) drafts[pluginId] = {}; drafts[pluginId][key] = value; }
    function syncPreferenceControls() {
        audible.checked = core.audibleFeedback; timeout.value = core.sessionTimeout; visual.checked = core.visualFeedback; volume.value = core.outputVolume
        visualPage.checked = core.visualFeedback; gainSlider.value = core.outputVolume
    }
    function approvalDone() { if (!reviewPlugin) return false; var entries = core.hubEntries; for (var i=0;i<entries.length;i++) if (entries[i].plugin_id === reviewPlugin.plugin_id && entries[i].manifest_sha256 === reviewPlugin.manifest_sha256) return entries[i].permissions_approved === true; return false; }
    function pluginFor(pluginId) { var items = core.pluginItems; for (var i=0;i<items.length;i++) if (items[i].plugin_id === pluginId) return items[i]; return null; }
    function pluginEnabledFor(pluginId) { var item = pluginFor(pluginId); return !!item && item.enabled === true; }
    function pluginStateText(item) { switch (item.state) { case "running": return "Ativo (sandbox, sem rede)"; case "starting": return "Iniciando…"; case "failed": return "Falhou: " + (item.last_error || "erro"); case "stopped": return "Parado"; case "quarantined": return "Em quarentena"; default: return "Desativado"; } }
    function pluginInstalled(pluginId) { var entries = core.hubEntries; for (var i=0;i<entries.length;i++) if (entries[i].plugin_id === pluginId) return entries[i].status === "installed"; return false; }
    function pluginApproved(pluginId) { var entries = core.hubEntries; for (var i=0;i<entries.length;i++) if (entries[i].plugin_id === pluginId) return entries[i].permissions_approved === true; return false; }
    function pluginCanEnable(item) { return !item.enabled && (item.state === "disabled" || item.state === "stopped" || item.state === "failed") && pluginInstalled(item.plugin_id) && pluginApproved(item.plugin_id); }
    function toolStateText(state) { switch (state) { case "pending": return "aguardando sua decisão"; case "authorized": return "autorizada; executando"; case "executed": return "executada"; case "denied": return "negada"; case "failed": return "falhou"; case "expired": return "expirada"; case "cancelled": return "cancelada"; default: return state; } }
    function sendChatDraft() { var t = chatInput.text.trim(); if (t.length === 0 || core.chatTextProblem(t) !== "") return; core.sendChat(t) }
    function openLlm() { llmRevisionCaptured = core.llmRevision; llmDialog.open() }
    function wakeText() { var pack = core.snapshotPack; if (!pack.wake_phrases) return "Não configurada"; for (var i=0;i<pack.wake_phrases.length;i++) if (pack.wake_phrases[i].id === pack.active_phrase) return pack.wake_phrases[i].text; return "Não ativa"; }
    // Core-owned state changes resync the controls; a rejected save must not leave the user's unsaved values on screen.
    Connections {
        target: core
        function onPreferencesChanged() { window.syncPreferenceControls() }
        function onPrefsSettled(message) { if (message !== window.preferencesSuccess) window.syncPreferenceControls() }
        function onTextSent(sent) { if (input.text === sent) input.text = "" }
        function onChatSent(sent) { if (chatInput.text.trim() === sent) { chatInput.text = ""; window.setDraft("#chat", "text", "") } }
    }
    Dialog {
        id: preferences; objectName: "preferencesDialog"
        title: "Preferências da Base"; modal: true
        anchors.centerIn: parent; width: Math.min(420, window.width - 32)
        standardButtons: Dialog.Close
        background: GlassCard { theme: window.themeIndex }
        onOpened: window.syncPreferenceControls()
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
                    enabled: core.llmConfigAvailable && modelField.acceptableInput
                    onClicked: core.configureLlm(providerBox.currentValue, modelField.text, providerBox.currentValue === "custom" ? urlField.text : "", consentBox.checked, window.llmRevisionCaptured)
                }
                Label { objectName: "llmResult"; text: core.llmResult; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
        }
    }
    Dialog {
        id: reviewDialog; objectName: "hubReviewDialog"
        // The approval target is captured when the dialog opens; the bridge refuses it if the live record changed.
        onOpened: { core.beginHubReview(); window.reviewRevision = core.hubApprovalRevision }
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
    Rectangle {
        id: sidebar
        width: window.width >= 1000 ? 232 : 64
        anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: window.themeIndex === 2 ? "#131e2c" : window.themeIndex === 1 ? "#1b2c47" : "#142445"
        Rectangle { anchors.right: parent.right; height: parent.height; width: 1; color: "#2b3d6a" }
        ColumnLayout {
            anchors.fill: parent; anchors.margins: sidebar.width > 100 ? 20 : 8; spacing: window.height < 640 ? 4 : 12
            RowLayout {
                Layout.topMargin: window.height < 640 ? 2 : 22; Layout.bottomMargin: window.height < 640 ? 10 : 30
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
                    Layout.fillWidth: true; implicitHeight: window.height < 640 ? 40 : 52
                    padding: sidebar.width < 100 ? 8 : 12
                    text: sidebar.width > 100 ? modelData : ""
                    Accessible.name: modelData
                    image: "assets/" + window.navIcons[index] + ".png"
                    accent: window.accentColor; checked: window.page === index; visible: index !== 7 || core.chatAvailable
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
                        Label { text: window.page === 1 ? "Configure como o Gideon escuta e responde." : window.page === 3 ? "Defina o estilo visual do Gideon." : window.page === 2 ? "Sua voz, seus ajustes de áudio." : window.page === 4 ? "Cada capacidade precisa de autorização." : window.page === 5 ? "Acompanhe o estado real da Base." : window.page === 7 ? "Converse com o motor LLM opcional." : "Capacidades opcionais, em um só lugar."; color: "#b7caf3"; font.pixelSize: 17; wrapMode: Text.WordWrap; Layout.fillWidth: true }
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
