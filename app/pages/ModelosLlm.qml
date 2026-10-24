import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Extensões > Modelos LLM. Parts: Modelo atual, Catálogo, Personalizados, Provedor e chaves (the Motor LLM form, which
// also works without the models plugin, since it talks to the Core), Fallback e hardware. Without the plugin only
// Provedor e chaves is left, and a banner says why.
PageFrame {
    id: page
    objectName: "modelsPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "modelos" && (core.modelsAvailable || core.llmConfigAvailable)

    property string part: "atual"
    readonly property string activePart: core.modelsAvailable ? part : "provedor"
    readonly property bool customTab: modelsTabs.currentIndex === 1
    readonly property bool wide: width > 900
    readonly property bool hasCurrent: !!core.modelsSelected.provider
    readonly property var allModels: core.modelsRecommended.concat(core.modelsCustom)
    readonly property var fallbackPicked: L.modelById(allModels, fallbackPick.currentValue)
    readonly property bool fallbackIsCloud: L.isCloudProvider(core.modelsFallback.provider) || (!!fallbackPicked && fallbackPicked.kind === "cloud")
    readonly property bool fallbackAllowed: !!fallbackPicked && (fallbackPicked.kind !== "cloud" || core.llmConfig.cloud_consent === true)
    readonly property var selected: AppState.selectedModel

    function keyOf(provider) { return core.llmSecretsConfigured[provider] === true }
    function currentModel() {
        var sel = core.modelsSelected
        if (!sel || !sel.provider) return null
        for (var i = 0; i < allModels.length; i++) if (allModels[i].provider === sel.provider && allModels[i].model === sel.model) return allModels[i]
        return null
    }
    function currentTitle() {
        var m = currentModel()
        return m ? m.label + " · " + (m.kind === "local" ? "Local" : "Nuvem") + " · " + core.providerLabel(m.provider) + " · " + m.model : ""
    }
    function isCustom(m) { for (var i = 0; i < core.modelsCustom.length; i++) if (core.modelsCustom[i].id === m.id) return true; return false }
    function lkgText() {
        var lkg = core.llmConfig.lkg
        if (!lkg || !lkg.provider) return "Nenhum modelo marcado como bom ainda."
        return "Último bom: " + core.providerLabel(lkg.provider) + " · " + lkg.model
    }
    function statusLabel(s) { return s === "INDISPONÍVEL: tool_use não suportado" ? "Indisponível: uso de ferramenta não suportado" : s }
    function statusTone(s) {
        switch (s) {
        case "Disponível": return "success"
        case "Sem chave": case "Sem consentimento": return "warning"
        case "Em teste": return "info"
        case "Sem dados do modelo": return "neutral"
        default: return s.indexOf("INDISPONÍVEL") === 0 ? "error" : "neutral"
        }
    }
    function selectModel(m) { AppState.selectedModel = m; AppState.modelsRevisionCaptured = core.llmRevision }
    function useReason() {
        if (core.modelsBusy) return "Aguarde: a operação de modelo anterior ainda está em andamento."
        if (!selected) return "Escolha um modelo na lista."
        if (selected.kind === "cloud" && !keyOf(selected.provider)) return "Sem chave: salve a chave do provedor em Provedor e chaves."
        if (selected.kind === "cloud" && core.llmConfig.cloud_consent !== true) return "Sem consentimento: permita o envio à nuvem em Provedor e chaves."
        return ""
    }
    function fallbackReason() {
        if (core.modelsBusy) return "Aguarde: operação de modelo em andamento."
        if (!fallbackPicked) return ""
        if (fallbackPicked.kind === "cloud" && !keyOf(fallbackPicked.provider)) return "Sem chave: salve a chave do provedor em Provedor e chaves."
        if (fallbackPicked.kind === "cloud" && core.llmConfig.cloud_consent !== true) return "Sem consentimento: marque o envio à nuvem em Provedor e chaves."
        return ""
    }
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
        subtitle: "Escolha, teste e configure o modelo do motor LLM instalado."
        GButton {
            objectName: "modelsRefresh"
            variant: "primary"
            text: "Atualizar lista"
            Accessible.name: "Atualizar lista de modelos"
            enabled: core.modelsAvailable && !core.modelsBusy
            onClicked: core.listModels(page.customTab ? "custom" : "recommended")
        }
    }
    // The one notice of the page: why only the provider part is left.
    Banner {
        objectName: "modelsStatusBanner"
        kind: "info"
        text: core.modelsAvailable ? "" : "Só Provedor e chaves está disponível: o plugin llm_engine não está ativo. Modelos LLM aparece completo quando o plugin estiver ativo."
        actionText: "Instalar em Extensões › Plugins"
        onActionRequested: Window.window.goPage("plugins")
    }
    CSummaryBar {
        text: page.hasCurrent ? "Modelo atual: " + core.providerLabel(core.modelsSelected.provider) + " · " + core.modelsSelected.model : "Nenhum modelo configurado"
        Badge {
            visible: page.hasCurrent
            text: page.statusLabel(core.modelsStatus)
            tone: page.statusTone(core.modelsStatus)
        }
        Badge {
            visible: page.hasCurrent
            text: L.isCloudProvider(core.modelsSelected.provider) ? "Nuvem" : "Local"
            tone: L.isCloudProvider(core.modelsSelected.provider) ? "info" : "neutral"
        }
    }
    GProgressBar {
        objectName: "modelsProgress"
        visible: core.modelsBusy
        indeterminate: true
        Layout.fillWidth: true
        Accessible.name: "Operação de modelo em andamento"
    }
    Text {
        objectName: "modelsResult"
        visible: text.length > 0
        text: core.modelsResult
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        font.weight: 600
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Accessible.name: "Resultado do modelo: " + text
    }
    Segmented {
        objectName: "modelParts"
        model: core.modelsAvailable
            ? [{id: "atual", text: "Modelo atual"}, {id: "catalogo", text: "Catálogo"}, {id: "personalizados", text: "Personalizados"}, {id: "provedor", text: "Provedor e chaves"}, {id: "fallback", text: "Fallback e hardware"}]
            : [{id: "provedor", text: "Provedor e chaves"}]
        currentId: page.activePart
        onActivated: function (id) { page.part = id }
    }

    // Modelo atual: the configured model and its test/rollback actions, next to its details.
    GridLayout {
        visible: page.activePart === "atual"
        Layout.fillWidth: true
        columns: page.wide ? 2 : 1
        columnSpacing: Theme.space(16)
        rowSpacing: Theme.space(16)
        Card {
            title: "Configurado"
            Layout.alignment: Qt.AlignTop
            Text {
                objectName: "modelsSelectedLabel"
                text: page.hasCurrent ? "Configurado: " + core.providerLabel(core.modelsSelected.provider) + " · " + core.modelsSelected.model : "Nenhum modelo configurado"
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(10)
                Text {
                    text: "Estado do modelo atual:"
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                }
                Badge {
                    objectName: "modelsStatus"
                    visible: page.hasCurrent
                    text: page.statusLabel(core.modelsStatus)
                    tone: page.statusTone(core.modelsStatus)
                }
            }
            Text {
                objectName: "modelsLkg"
                text: page.lkgText()
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                visible: page.currentModel() !== null
                text: page.currentModel() && page.currentModel().offline ? "Funciona offline" : "Requer rede"
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                Layout.fillWidth: true
            }
            Flow {
                Layout.fillWidth: true
                spacing: Theme.space(8)
                GButton { objectName: "testModelButton"; variant: "secondary"; text: "Testar"; enabled: false; Accessible.name: "Testar modelo atual" }
                GButton { objectName: "rollbackModelButton"; variant: "secondary"; text: "Voltar ao último bom"; enabled: false; Accessible.name: "Voltar ao último bom" }
                GButton { objectName: "otherModelButton"; variant: "secondary"; text: "Usar outro modelo"; enabled: core.modelsAvailable; Accessible.name: "Usar outro modelo"; onClicked: page.part = "catalogo" }
            }
            Text {
                objectName: "testModelReason"
                text: page.hasCurrent ? "Teste isolado e volta ao último bom ainda não estão disponíveis neste build." : "Configure um modelo antes de testar."
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        Card {
            title: "Detalhes do modelo atual"
            Layout.alignment: Qt.AlignTop
            CModelDetail {
                visible: page.currentModel() !== null
                model: page.currentModel()
                prefix: "currentModel"
                titleText: page.currentTitle()
                showCaption: false
            }
            Text {
                visible: page.hasCurrent && page.currentModel() === null
                text: "Detalhes indisponíveis: carregue o catálogo para ver este modelo."
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            GButton {
                visible: page.hasCurrent && page.currentModel() === null
                variant: "secondary"
                text: "Carregar mais"
                Accessible.name: "Carregar mais modelos"
                enabled: core.modelsAvailable && !core.modelsBusy
                onClicked: core.loadMoreModels("recommended")
            }
        }
    }

    // Personalizados: the form for a model the user adds (the Core keeps the rules; the form only reports problems).
    Section {
        objectName: "customForm"
        visible: page.activePart === "personalizados"
        title: "Adicionar modelo personalizado"
        FieldLabel { text: "Provedor do modelo personalizado" }
        Select {
            id: customProvider
            objectName: "customProvider"
            Layout.fillWidth: true
            textRole: "text"
            valueRole: "id"
            Accessible.name: "Provedor do modelo personalizado"
            model: [{id: "local", text: "Local (llama.cpp)"}, {id: "ollama", text: "Ollama (local)"}, {id: "custom", text: "Personalizado (https)"}, {id: "openrouter", text: "OpenRouter (nuvem)"}, {id: "opencode", text: "OpenCode (nuvem)"}, {id: "google", text: "Google AI Studio (nuvem)"}]
        }
        FieldLabel { text: "Identificador do modelo: letras, números e . _ : / - (até 128)" }
        GTextField {
            id: customModelId
            objectName: "customModelId"
            Layout.fillWidth: true
            maximumLength: 128
            placeholderText: "Identificador do modelo"
            Accessible.name: "Identificador do modelo personalizado"
            validator: RegularExpressionValidator { regularExpression: /[A-Za-z0-9._:\/-]{1,128}/ }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(12)
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: "Porta do servidor local, de 1024 a 65535" }
                SpinBox {
                    id: customPort
                    objectName: "customPort"
                    from: 1024; to: 65535; value: 8080; editable: true
                    enabled: customProvider.currentValue === "local" || customProvider.currentValue === "ollama"
                    Accessible.name: "Porta do servidor local, de 1024 a 65535"
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: "URL https do modelo personalizado" }
                GTextField {
                    id: customUrl
                    objectName: "customUrl"
                    Layout.fillWidth: true
                    maximumLength: 200
                    placeholderText: "https://"
                    enabled: customProvider.currentValue === "custom"
                    Accessible.name: "URL https do modelo personalizado"
                }
            }
        }
        FieldLabel { text: "Recursos declarados (não certificados)" }
        GridLayout {
            Layout.fillWidth: true
            columns: page.wide ? 2 : 1
            columnSpacing: Theme.space(12)
            rowSpacing: Theme.space(8)
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: "Streaming" }
                Select { id: customStreaming; objectName: "customStreaming"; Layout.fillWidth: true; model: L.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Streaming declarado" }
            }
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: "Tool use" }
                Select { id: customToolUse; objectName: "customToolUse"; Layout.fillWidth: true; model: L.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Tool use declarado" }
            }
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: "Visão" }
                Select { id: customVision; objectName: "customVision"; Layout.fillWidth: true; model: L.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Visão declarada" }
            }
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: "Cancelamento" }
                Select { id: customCancel; objectName: "customCancel"; Layout.fillWidth: true; model: L.featureChoices; textRole: "text"; valueRole: "id"; Accessible.name: "Cancelamento declarado" }
            }
        }
        Text {
            text: "Recursos declarados não são certificados; o selftest é que confirma."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            objectName: "customFormProblem"
            visible: text.length > 0
            text: core.customFormProblem(page.customForm())
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "saveCustomButton"
            variant: "primary"
            text: "Salvar modelo personalizado"
            Accessible.name: "Salvar modelo personalizado"
            enabled: core.modelsAvailable && !core.modelsBusy && core.customFormProblem(page.customForm()) === ""
            onClicked: core.saveCustomModel(page.customForm())
        }
    }

    // Catálogo and the custom list share one list: the tabs pick which one is shown.
    Section {
        objectName: "catalogSection"
        visible: page.activePart === "catalogo" || page.activePart === "personalizados"
        title: page.activePart === "catalogo" ? "Catálogo" : "Modelos personalizados"
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
        Text {
            objectName: "modelsCount"
            text: (page.customTab ? core.modelsCustom.length + " de " + core.modelsCustomTotal : core.modelsRecommended.length + " de " + core.modelsRecommendedTotal)
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
            Accessible.name: "Modelos carregados: " + text
        }
        EmptyState {
            visible: modelRows.count === 0
            iconName: "cpu"
            message: page.customTab ? "Nenhum modelo personalizado. Adicione um no formulário acima." : "Nenhum modelo nesta lista."
        }
        Repeater {
            id: modelRows
            model: L.filteredModels(page.customTab ? core.modelsCustom : core.modelsRecommended, modelsFilter.currentIndex)
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
                    tone: modelData.certification.state === "certified" ? "success" : (modelData.certification.state === "probed" ? "info" : "warning")
                }
            }
        }
        GButton {
            objectName: "modelsLoadMore"
            variant: "secondary"
            text: "Carregar mais"
            visible: page.customTab ? core.modelsCustom.length < core.modelsCustomTotal : core.modelsRecommended.length < core.modelsRecommendedTotal
            enabled: core.modelsAvailable && !core.modelsBusy
            Accessible.name: "Carregar mais modelos"
            onClicked: core.loadMoreModels(page.customTab ? "custom" : "recommended")
        }
        Card {
            objectName: "modelDetails"
            visible: page.selected !== null
            CModelDetail {
                model: page.selected
                prefix: "modelDetail"
            }
            Text {
                objectName: "useModelReason"
                visible: text.length > 0
                text: page.useReason()
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(10)
                GButton {
                    objectName: "useModelButton"
                    variant: "primary"
                    text: "Usar este modelo"
                    Accessible.name: page.selected ? "Usar este modelo: " + page.selected.label : "Usar este modelo"
                    enabled: core.modelsAvailable && page.selected !== null && page.useReason() === ""
                    onClicked: core.useModel(page.selected.id, AppState.modelsRevisionCaptured)
                }
                Item { Layout.fillWidth: true }
                GButton {
                    objectName: "removeCustomButton"
                    visible: page.customTab && page.selected !== null && page.isCustom(page.selected)
                    variant: "danger"
                    text: "Remover"
                    Accessible.name: page.selected ? "Remover modelo personalizado " + page.selected.id : "Remover"
                    enabled: core.modelsAvailable && !core.modelsBusy
                    onClicked: { removeCustomConfirm.entry = page.selected; removeCustomConfirm.open() }
                }
            }
        }
    }

    // Provedor e chaves: the Motor LLM form (provider, model, URL, cloud consent, key, remove key). Its objects keep the
    // names the tests use. open() and close() are what the Motor LLM entry points call.
    ColumnLayout {
        id: llmDialog
        objectName: "llmDialog"
        visible: page.activePart === "provedor"
        Layout.fillWidth: true
        spacing: Theme.space(16)
        onVisibleChanged: { if (visible) resetForm(); else keyField.text = "" }
        Component.onCompleted: { if (visible) resetForm() }

        // Provider, model and consent start from the Core snapshot; no saved config means consent unchecked. The key never comes back.
        function resetForm() {
            AppState.llmRevisionCaptured = core.llmRevision
            providerBox.currentIndex = Math.max(0, providerBox.indexOfValue(core.llmConfig.provider || "openrouter"))
            modelField.text = core.llmConfig.model || ""
            urlField.text = core.llmConfig.custom_url || ""
            consentBox.checked = core.llmConfig.cloud_consent === true
            keyField.text = ""
        }
        function open() { resetForm() }
        function close() { keyField.text = "" }

        GridLayout {
            Layout.fillWidth: true
            columns: page.wide ? 2 : 1
            columnSpacing: Theme.space(16)
            rowSpacing: Theme.space(16)
            Section {
                title: "Configuração"
                Layout.alignment: Qt.AlignTop
                FieldLabel { text: "Provedor" }
                Select {
                    id: providerBox
                    objectName: "llmProvider"
                    Layout.fillWidth: true
                    enabled: core.llmConfigAvailable
                    textRole: "text"; valueRole: "id"
                    Accessible.name: "Provedor do motor LLM"
                    model: [{id: "openrouter", text: "OpenRouter"}, {id: "opencode", text: "OpenCode"}, {id: "google", text: "Google AI Studio"}, {id: "custom", text: "Personalizado"}]
                }
                FieldLabel { text: "Modelo: letras, números e . _ : / - (até 128)" }
                GTextField {
                    id: modelField
                    objectName: "llmModel"
                    Layout.fillWidth: true
                    maximumLength: 128
                    enabled: core.llmConfigAvailable
                    placeholderText: "ex.: gemini-3.5-flash-lite"
                    Accessible.name: "Modelo do motor LLM"
                    validator: RegularExpressionValidator { regularExpression: /[A-Za-z0-9._:\/-]{1,128}/ }
                }
                FieldLabel { visible: providerBox.currentValue === "custom"; text: "URL personalizada: somente https (http apenas em loopback de teste)" }
                GTextField {
                    id: urlField
                    objectName: "llmUrl"
                    Layout.fillWidth: true
                    maximumLength: 200
                    enabled: providerBox.currentValue === "custom" && core.llmConfigAvailable
                    placeholderText: "https://"
                    Accessible.name: "URL do provedor personalizado"
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    FieldLabel { text: "Chave"; Layout.fillWidth: true }
                    Badge {
                        objectName: "llmKeyStatus"
                        visible: page.keyOf(providerBox.currentValue)
                        text: page.keyOf(providerBox.currentValue) ? "Chave configurada" : "Sem chave"
                        tone: "success"
                        Accessible.name: "Estado da chave: " + text
                    }
                }
                GTextField {
                    id: keyField
                    objectName: "llmKey"
                    Layout.fillWidth: true
                    echoMode: TextInput.Password
                    maximumLength: 256
                    inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                    placeholderText: "Chave de API (somente escrita)"
                    enabled: core.llmConfigAvailable
                    Accessible.name: "Chave de API do provedor"
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    GButton {
                        objectName: "saveKeyButton"
                        variant: "primary"
                        text: "Salvar chave"
                        Accessible.name: "Salvar chave do provedor"
                        enabled: core.llmConfigAvailable && keyField.text.length > 0
                        // The field is cleared at once: the key leaves QML with this call.
                        onClicked: { core.setApiKey(providerBox.currentValue, keyField.text); keyField.text = "" }
                    }
                    GButton {
                        objectName: "clearKeyButton"
                        variant: "danger"
                        text: "Remover chave"
                        Accessible.name: "Remover chave do provedor"
                        enabled: core.llmConfigAvailable && page.keyOf(providerBox.currentValue)
                        onClicked: clearKeyConfirm.open()
                    }
                }
                Text {
                    text: "A chave não volta a aparecer depois de enviada."
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
            Section {
                title: "Nuvem e salvar"
                Layout.alignment: Qt.AlignTop
                GCheckbox {
                    id: consentBox
                    objectName: "llmConsent"
                    checked: false
                    text: "Permitir envio de conversas ao provedor na nuvem"
                    enabled: core.llmConfigAvailable
                    Accessible.name: "Consentimento para envio à nuvem"
                    Accessible.description: "Mensagens serão enviadas ao provedor escolhido na nuvem"
                }
                Text {
                    objectName: "llmConsentWarning"
                    text: "Mensagens serão enviadas ao provedor escolhido na nuvem"
                    textFormat: Text.PlainText
                    color: Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    text: "Consentimento salvo: " + (core.llmConfig.cloud_consent === true ? "concedido" : "não concedido")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                GButton {
                    objectName: "saveLlmConfigButton"
                    variant: "primary"
                    text: "Salvar configuração"
                    Accessible.name: "Salvar configuração do Motor LLM"
                    enabled: core.llmConfigAvailable && modelField.acceptableInput && core.llmConfig.provider !== "local" && core.llmConfig.provider !== "ollama"
                    onClicked: core.configureLlm(providerBox.currentValue, modelField.text, providerBox.currentValue === "custom" ? urlField.text : "", consentBox.checked, AppState.llmRevisionCaptured)
                }
                // A local provider is configured through the catalog; this form would otherwise overwrite it.
                Text {
                    objectName: "llmLocalNotice"
                    visible: core.llmConfig.provider === "local" || core.llmConfig.provider === "ollama"
                    text: "Configuração local ativa: " + core.providerLabel(core.llmConfig.provider) + " · " + (core.llmConfig.model || "") + ". Troque em Catálogo."
                    textFormat: Text.PlainText
                    color: Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    objectName: "llmResult"
                    visible: text.length > 0
                    text: core.llmResult
                    textFormat: Text.PlainText
                    color: Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }
        Collapsible {
            title: "Como funciona"
            summary: "Motor opcional. Sem ele, voz, wake e comandos da Base continuam funcionando."
            Text {
                text: "Provedor, modelo, URL e consentimento são gravados pelo Core. A chave é só de escrita: nunca é mostrada de volta."
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        Modal {
            id: clearKeyConfirm
            objectName: "clearKeyConfirm"
            title: "Tem certeza?"
            Text {
                text: "Remover a chave do provedor " + providerBox.displayText + "? As chamadas a este provedor param até você salvar outra chave."
                textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            GButton {
                objectName: "confirmClearKeyButton"
                variant: "danger"
                text: "Remover chave"
                Layout.alignment: Qt.AlignRight
                Accessible.name: "Remover chave do provedor"
                onClicked: clearKeyConfirm.accept()
            }
            onAccepted: core.clearApiKey(providerBox.currentValue)
        }
    }

    // Fallback e hardware.
    Section {
        visible: page.activePart === "fallback"
        title: "Fallback (opcional)"
        Text {
            objectName: "fallbackCurrent"
            text: core.modelsFallback.provider ? "Atual: " + core.providerLabel(core.modelsFallback.provider) + " · " + core.modelsFallback.model : "Nenhum fallback configurado"
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            text: "Usado só depois de erro recuperável do modelo principal (429, 5xx, rede ou tempo esgotado). Nunca em erro de chave ou permissão."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        FieldLabel { text: "Modelo para fallback" }
        Select { id: fallbackPick; objectName: "fallbackModel"; Layout.fillWidth: true; model: page.allModels; textRole: "label"; valueRole: "id"; Accessible.name: "Modelo para fallback" }
        Text {
            objectName: "fallbackCloudWarning"
            visible: page.fallbackIsCloud
            text: "Mensagens poderão ir para a nuvem se o modelo principal falhar"
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: "Aviso: envio à nuvem no fallback"
        }
        Text {
            objectName: "fallbackConsentNeeded"
            visible: page.fallbackIsCloud && core.llmConfig.cloud_consent !== true
            text: "Para fallback na nuvem, marque o consentimento em Provedor e chaves."
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            objectName: "fallbackReason"
            visible: text.length > 0
            text: page.fallbackReason()
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            GButton { objectName: "setFallbackButton"; variant: "primary"; text: "Usar como fallback"; Accessible.name: "Usar o modelo escolhido como fallback"; enabled: core.modelsAvailable && !core.modelsBusy && fallbackPick.currentIndex >= 0 && page.fallbackAllowed; onClicked: core.setFallback(fallbackPick.currentValue, AppState.modelsRevisionCaptured) }
            GButton { objectName: "clearFallbackButton"; variant: "secondary"; text: "Remover fallback"; Accessible.name: "Remover fallback"; enabled: core.modelsAvailable && !core.modelsBusy && !!core.modelsFallback.provider; onClicked: core.clearFallback(AppState.modelsRevisionCaptured) }
        }
    }
    Section {
        visible: page.activePart === "fallback"
        title: "Hardware e plugin"
        Text {
            objectName: "modelsHardware"
            text: core.modelsHardware.cpu_cores ? "CPU: " + core.modelsHardware.cpu_cores + " núcleos · RAM: " + (core.modelsHardware.ram_gb === null ? "desconhecida" : core.modelsHardware.ram_gb + " GB") + " · GPU: " + (core.modelsHardware.gpu === "unknown" ? "desconhecido" : core.modelsHardware.gpu) : "Hardware: aguardando catálogo"
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            text: "Apaga só os dados guardados pelo plugin. Não altera o Core."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton { objectName: "clearPluginSettingsButton"; variant: "danger"; text: "Apagar dados do plugin"; Accessible.name: "Apagar dados do plugin LLM"; enabled: core.connected && !core.modelsBusy; onClicked: clearPluginConfirm.open() }
    }

    Modal {
        id: removeCustomConfirm
        objectName: "removeCustomConfirm"
        property var entry: null
        title: "Tem certeza?"
        onAccepted: { if (entry) core.deleteCustomModel(entry.id) }
        Text { text: removeCustomConfirm.entry ? "Remover " + removeCustomConfirm.entry.label + " da lista de modelos personalizados? O modelo no provedor não é apagado." : ""; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        GButton { objectName: "confirmRemoveCustomButton"; variant: "danger"; text: "Remover"; Layout.alignment: Qt.AlignRight; Accessible.name: removeCustomConfirm.entry ? "Remover modelo " + removeCustomConfirm.entry.id : "Remover"; onClicked: removeCustomConfirm.accept() }
    }
    Modal {
        id: clearPluginConfirm
        objectName: "clearPluginConfirm"
        title: "Tem certeza?"
        onAccepted: core.clearPluginSettings()
        Text { text: "Apagar as configurações guardadas pelo plugin LLM, inclusive modelos personalizados? O plugin e a configuração do Core (provedor, modelo e chaves) não são alterados."; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        GButton { objectName: "confirmClearPluginButton"; variant: "danger"; text: "Apagar dados"; Accessible.name: "Apagar dados do plugin LLM"; Layout.alignment: Qt.AlignRight; onClicked: clearPluginConfirm.accept() }
    }
}
