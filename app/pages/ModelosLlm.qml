import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Extensões > Modelos LLM (needs the models plugin). Parts: Modelo atual, Catálogo, Personalizados, Provedor e chaves
// (the form is the Motor LLM dialog, opened from here or from Configurações > Privacidade), Fallback e hardware.
PageFrame {
    id: page
    objectName: "modelsPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "modelos" && core.modelsAvailable

    property string part: "atual"
    readonly property var allModels: core.modelsRecommended.concat(core.modelsCustom)
    readonly property var fallbackPicked: L.modelById(allModels, fallbackPick.currentValue)
    readonly property bool fallbackIsCloud: L.isCloudProvider(core.modelsFallback.provider) || (!!fallbackPicked && fallbackPicked.kind === "cloud")
    readonly property bool fallbackAllowed: !!fallbackPicked && (fallbackPicked.kind !== "cloud" || core.llmConfig.cloud_consent === true)
    readonly property var selected: AppState.selectedModel

    function selectModel(m) { AppState.selectedModel = m; AppState.modelsRevisionCaptured = core.llmRevision }
    function customForm() {
        var prov = customProvider.currentValue
        var local = prov === "local" || prov === "ollama"
        return { provider: prov, model: customModelId.text, custom_url: prov === "custom" ? customUrl.text : "", local_port: local ? customPort.value : null,
                 features: { streaming: customStreaming.currentValue, tool_use: customToolUse.currentValue, vision: customVision.currentValue, cancel: customCancel.currentValue } }
    }

    onPartChanged: {
        if (part === "catalogo") modelsTabs.currentIndex = 0
        if (part === "personalizados") modelsTabs.currentIndex = 1
    }
    Connections {
        target: core
        function onModelsStateChanged() { if (!core.modelsBusy) AppState.modelsRevisionCaptured = core.llmRevision }
    }
    Component.onCompleted: { AppState.modelsRevisionCaptured = core.llmRevision }

    PageHeader {
        title: "Modelos LLM"
        subtitle: "Escolha, teste e configure o modelo do motor LLM opcional."
    }
    Banner {
        objectName: "modelsStatusBanner"
        kind: "info"
        text: core.modelsAvailable ? "" : "Indisponível: o plugin de modelos não está ativo."
    }
    Text {
        objectName: "modelsStatus"
        text: "Estado do modelo atual: " + core.modelsStatus
        textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        Accessible.name: "Estado do modelo atual: " + core.modelsStatus
    }
    Segmented {
        objectName: "modelParts"
        model: [{id: "atual", text: "Modelo atual"}, {id: "catalogo", text: "Catálogo"}, {id: "personalizados", text: "Personalizados"}, {id: "provedor", text: "Provedor e chaves"}, {id: "fallback", text: "Fallback e hardware"}]
        currentId: page.part
        onActivated: function (id) { page.part = id }
    }

    // Modelo atual.
    Section {
        visible: page.part === "atual"
        title: "Modelo atual"
        Text { objectName: "modelsSelectedLabel"; text: core.modelsSelected.provider ? "Configurado: " + core.providerLabel(core.modelsSelected.provider) + " · " + core.modelsSelected.model : "Nenhum modelo configurado"; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        GProgressBar { objectName: "modelsProgress"; visible: core.modelsBusy; indeterminate: true; Layout.fillWidth: true; Accessible.name: "Operação de modelo em andamento" }
        Text { objectName: "modelsResult"; visible: text.length > 0; text: core.modelsResult; textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Resultado do modelo: " + text }
        GButton { objectName: "modelsRefresh"; variant: "secondary"; text: "Atualizar lista"; Accessible.name: "Atualizar lista de modelos"; enabled: core.modelsAvailable && !core.modelsBusy; onClicked: core.listModels(modelsTabs.currentIndex === 0 ? "recommended" : "custom") }
    }

    // Catálogo: recommended models, with the detail of the picked one.
    Section {
        visible: page.part === "catalogo" || page.part === "personalizados"
        title: page.part === "catalogo" ? "Catálogo" : "Modelos personalizados"
        TabBar {
            id: modelsTabs
            objectName: "modelsTabs"
            Layout.fillWidth: true
            onCurrentIndexChanged: core.listModels(currentIndex === 0 ? "recommended" : "custom")
            background: Rectangle { color: "transparent" }
            TabButton {
                objectName: "modelsTabRecommended"; text: "Recomendados"; Accessible.name: "Aba Recomendados"
                background: Rectangle { color: parent.checked ? Theme.tint : "transparent"; radius: Theme.radius; border.width: 1; border.color: Theme.strongOutline }
                contentItem: Text { text: parent.text; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: parent.checked ? 600 : 400; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
            }
            TabButton {
                objectName: "modelsTabCustom"; text: "Personalizados"; Accessible.name: "Aba Personalizados"
                background: Rectangle { color: parent.checked ? Theme.tint : "transparent"; radius: Theme.radius; border.width: 1; border.color: Theme.strongOutline }
                contentItem: Text { text: parent.text; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: parent.checked ? 600 : 400; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Text { text: "Mostrar:"; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp }
            Select { id: modelsFilter; objectName: "modelsFilter"; model: ["Todos", "Local", "Nuvem"]; Accessible.name: "Filtro por local ou nuvem" }
        }
        Text { objectName: "modelsCount"; text: (modelsTabs.currentIndex === 0 ? core.modelsRecommended.length + " de " + core.modelsRecommendedTotal : core.modelsCustom.length + " de " + core.modelsCustomTotal); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true; Accessible.name: "Modelos carregados: " + text }
        EmptyState { visible: modelRows.count === 0; iconName: "cpu"; message: "Nenhum modelo nesta lista." }
        Repeater {
            id: modelRows
            model: L.filteredModels(modelsTabs.currentIndex === 0 ? core.modelsRecommended : core.modelsCustom, modelsFilter.currentIndex)
            delegate: ListRow {
                required property var modelData
                objectName: "model_" + modelData.id
                title: modelData.label
                detail: modelData.kind === "local" ? "Local" : "Nuvem"
                selected: page.selected !== null && page.selected.id === modelData.id
                onClicked: page.selectModel(modelData)
                Badge {
                    objectName: "badge_" + modelData.id
                    text: core.certificationBadge(modelData.certification.state)
                    tone: modelData.certification.state === "certified" ? "success" : "warning"
                }
            }
        }
        GButton { objectName: "modelsLoadMore"; variant: "secondary"; text: "Carregar mais"; visible: modelsTabs.currentIndex === 0 ? core.modelsRecommended.length < core.modelsRecommendedTotal : core.modelsCustom.length < core.modelsCustomTotal; enabled: core.modelsAvailable && !core.modelsBusy; Accessible.name: "Carregar mais modelos"; onClicked: core.loadMoreModels(modelsTabs.currentIndex === 0 ? "recommended" : "custom") }
        Card {
            objectName: "modelDetails"
            visible: page.selected !== null
            Text { objectName: "modelDetailTitle"; text: page.selected ? page.selected.label : ""; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSection; font.weight: 600; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
            Text { text: page.selected ? (page.selected.kind === "local" ? "Local" : "Nuvem") + " · provedor " + page.selected.provider + " · " + page.selected.model : ""; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
            Text { objectName: "modelDetailCertification"; text: page.selected ? "Certificação: " + core.certificationBadge(page.selected.certification.state) + (page.selected.certification.evidence ? " · evidência: " + page.selected.certification.evidence : "") + (page.selected.certification.date ? " · data " + page.selected.certification.date : "") : ""; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { text: page.selected ? "Licença: " + page.selected.license + "\nQuantização: " + (page.selected.quantization || "não se aplica") + "\nHash (SHA-256): " + (page.selected.sha256 || "não se aplica") + "\nBackend: " + page.selected.backend : ""; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
            Repeater {
                model: ["streaming", "tool_use", "vision", "cancel"]
                delegate: Text {
                    required property string modelData
                    text: "Recurso " + modelData + ": " + core.featureLabel(page.selected ? page.selected.features[modelData] : "unknown")
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true; wrapMode: Text.WordWrap
                }
            }
            Text { text: page.selected ? "Contexto: " + (page.selected.features.context_tokens === null ? "não informado" : page.selected.features.context_tokens + " tokens") : ""; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            Text { text: page.selected ? (page.selected.cost.currency === null ? "Custo: não informado" : "Custo (USD por milhão de tokens): entrada " + page.selected.cost.input_per_mtok + " · saída " + page.selected.cost.output_per_mtok) : ""; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            Text { text: page.selected ? "Latência: " + L.latencyText(page.selected.latency_hint) + " · hardware mínimo: RAM " + (page.selected.min_hardware.ram_gb === null ? "não informada" : page.selected.min_hardware.ram_gb + " GB") + ", GPU " + L.gpuText(page.selected.min_hardware.gpu) : ""; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            Text { text: page.selected ? (page.selected.offline ? "Funciona offline" : "Requer rede") : ""; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(10)
                GButton { objectName: "useModelButton"; variant: "primary"; text: "Usar este modelo"; Accessible.name: page.selected ? "Usar este modelo: " + page.selected.label : "Usar este modelo"; enabled: core.modelsAvailable && !core.modelsBusy && page.selected !== null; onClicked: core.useModel(page.selected.id, AppState.modelsRevisionCaptured) }
                Item { Layout.fillWidth: true }
                GButton { objectName: "removeCustomButton"; visible: modelsTabs.currentIndex === 1 && page.selected !== null; variant: "danger"; text: "Remover"; Accessible.name: page.selected ? "Remover modelo personalizado " + page.selected.id : "Remover"; enabled: core.modelsAvailable && !core.modelsBusy; onClicked: { removeCustomConfirm.entry = page.selected; removeCustomConfirm.open() } }
            }
        }
    }

    // Personalizados: the form for a model the user adds (keeps the Core rules; the form only reports problems).
    Card {
        objectName: "customForm"
        visible: page.part === "personalizados"
        title: "Adicionar modelo personalizado"
        FieldLabel { text: "Provedor" }
        Select { id: customProvider; objectName: "customProvider"; Layout.fillWidth: true; textRole: "text"; valueRole: "id"; Accessible.name: "Provedor do modelo personalizado"; model: [{id: "local", text: "Local (llama.cpp)"}, {id: "ollama", text: "Ollama (local)"}, {id: "custom", text: "Personalizado (https)"}, {id: "openrouter", text: "OpenRouter (nuvem)"}, {id: "opencode", text: "OpenCode (nuvem)"}, {id: "google", text: "Google AI Studio (nuvem)"}] }
        FieldLabel { text: "Identificador do modelo: letras, números e . _ : / - (até 128)" }
        GTextField { id: customModelId; objectName: "customModelId"; Layout.fillWidth: true; maximumLength: 128; placeholderText: "Identificador do modelo"; Accessible.name: "Identificador do modelo personalizado"; validator: RegularExpressionValidator { regularExpression: /[A-Za-z0-9._:\/-]{1,128}/ } }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            SpinBox { id: customPort; objectName: "customPort"; from: 1024; to: 65535; value: 8080; editable: true; enabled: customProvider.currentValue === "local" || customProvider.currentValue === "ollama"; Accessible.name: "Porta do servidor local, de 1024 a 65535" }
            GTextField { id: customUrl; objectName: "customUrl"; Layout.fillWidth: true; maximumLength: 200; placeholderText: "https://"; enabled: customProvider.currentValue === "custom"; Accessible.name: "URL https do modelo personalizado" }
        }
        FieldLabel { text: "Recursos declarados (não certificados)" }
        GridLayout {
            Layout.fillWidth: true
            columns: page.width > 900 ? 2 : 1
            columnSpacing: Theme.space(12)
            Select { id: customStreaming; objectName: "customStreaming"; Layout.fillWidth: true; model: L.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Streaming declarado" }
            Select { id: customToolUse; objectName: "customToolUse"; Layout.fillWidth: true; model: L.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Tool use declarado" }
            Select { id: customVision; objectName: "customVision"; Layout.fillWidth: true; model: L.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Visão declarada" }
            Select { id: customCancel; objectName: "customCancel"; Layout.fillWidth: true; model: L.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Cancelamento declarado" }
        }
        Text { objectName: "customFormProblem"; visible: text.length > 0; text: core.customFormProblem(page.customForm()); textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        GButton { objectName: "saveCustomButton"; variant: "primary"; text: "Salvar modelo personalizado"; Accessible.name: "Salvar modelo personalizado"; enabled: core.modelsAvailable && !core.modelsBusy && core.customFormProblem(page.customForm()) === ""; onClicked: core.saveCustomModel(page.customForm()) }
    }

    // Provedor e chaves: the Motor LLM form is a dialog (shared with Configurações > Privacidade and the Conversa notice).
    Card {
        visible: page.part === "provedor"
        title: "Provedor e chaves"
        Text { text: "Provedor, modelo, URL, consentimento de nuvem e chave de API. A chave é só de escrita: nunca é mostrada de volta."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Text { text: "Consentimento salvo: " + (core.llmConfig.cloud_consent === true ? "concedido" : "não concedido") + " · chave: " + (core.llmSecretsConfigured[core.llmConfig.provider] === true ? "configurada" : "não configurada"); textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        GButton { objectName: "llmOpenButtonModels"; variant: "primary"; text: "Configurar provedor e chaves"; Accessible.name: "Abrir configuração do Motor LLM"; enabled: core.connected; onClicked: Window.window.openLlm() }
    }

    // Fallback e hardware.
    Section {
        visible: page.part === "fallback"
        title: "Fallback (opcional)"
        Text { objectName: "fallbackCurrent"; text: core.modelsFallback.provider ? "Atual: " + core.modelsFallback.provider + " · " + core.modelsFallback.model : "Nenhum fallback configurado"; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Select { id: fallbackPick; objectName: "fallbackModel"; Layout.fillWidth: true; model: page.allModels; textRole: "label"; valueRole: "id"; Accessible.name: "Modelo para fallback" }
        Banner { objectName: "fallbackCloudWarning"; kind: "warn"; visible: page.fallbackIsCloud; text: "Mensagens poderão ir para a nuvem se o modelo principal falhar" ; Accessible.name: "Aviso: envio à nuvem no fallback" }
        Text { objectName: "fallbackConsentNeeded"; visible: page.fallbackIsCloud && core.llmConfig.cloud_consent !== true; text: "Para fallback na nuvem, marque o consentimento em Provedor e chaves."; textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            GButton { objectName: "setFallbackButton"; variant: "primary"; text: "Usar como fallback"; Accessible.name: "Usar o modelo escolhido como fallback"; enabled: core.modelsAvailable && !core.modelsBusy && fallbackPick.currentIndex >= 0 && page.fallbackAllowed; onClicked: core.setFallback(fallbackPick.currentValue, AppState.modelsRevisionCaptured) }
            GButton { objectName: "clearFallbackButton"; variant: "danger"; text: "Remover fallback"; Accessible.name: "Remover fallback"; enabled: core.modelsAvailable && !core.modelsBusy && !!core.modelsFallback.provider; onClicked: core.clearFallback(AppState.modelsRevisionCaptured) }
        }
    }
    Section {
        visible: page.part === "fallback"
        title: "Hardware e plugin"
        Text { objectName: "modelsHardware"; text: core.modelsHardware.cpu_cores ? "CPU: " + core.modelsHardware.cpu_cores + " núcleos · RAM: " + (core.modelsHardware.ram_gb === null ? "desconhecida" : core.modelsHardware.ram_gb + " GB") + " · GPU: " + (core.modelsHardware.gpu === "unknown" ? "desconhecido" : core.modelsHardware.gpu) : "Hardware: aguardando catálogo"; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        GButton { objectName: "clearPluginSettingsButton"; variant: "danger"; text: "Apagar dados do plugin"; Accessible.name: "Apagar dados do plugin LLM"; enabled: core.connected && !core.modelsBusy; onClicked: clearPluginConfirm.open() }
    }

    Modal {
        id: removeCustomConfirm
        objectName: "removeCustomConfirm"
        property var entry: null
        title: "Remover modelo personalizado"
        onAccepted: { if (entry) core.deleteCustomModel(entry.id) }
        Text { text: removeCustomConfirm.entry ? "Remover " + removeCustomConfirm.entry.label + " da lista de modelos personalizados? O modelo no provedor não é apagado." : ""; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        GButton { objectName: "confirmRemoveCustomButton"; variant: "danger"; text: "Remover"; Layout.alignment: Qt.AlignRight; Accessible.name: removeCustomConfirm.entry ? "Remover modelo " + removeCustomConfirm.entry.id : "Remover"; onClicked: removeCustomConfirm.accept() }
    }
    Modal {
        id: clearPluginConfirm
        objectName: "clearPluginConfirm"
        title: "Apagar dados do plugin"
        onAccepted: core.clearPluginSettings()
        Text { text: "Apagar as configurações guardadas pelo plugin LLM, inclusive modelos personalizados? O plugin e a configuração do Core (provedor, modelo e chaves) não são alterados."; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        GButton { objectName: "confirmClearPluginButton"; variant: "danger"; text: "Apagar dados"; Accessible.name: "Apagar dados do plugin LLM"; Layout.alignment: Qt.AlignRight; onClicked: clearPluginConfirm.accept() }
    }
}
