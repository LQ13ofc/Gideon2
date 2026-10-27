import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L
import "../components/Reveal.js" as Reveal

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
    // Recommended list state from the paged output (B14): loaded so far against the Core total.
    readonly property bool recommendedMoreLeft: core.modelsRecommended.length < core.modelsRecommendedTotal
    readonly property bool recommendedNotLoaded: core.modelsRecommendedTotal === 0 && core.modelsRecommended.length === 0
    readonly property var allModels: core.modelsRecommended.concat(core.modelsCustom)
    readonly property var fallbackPicked: L.modelById(allModels, fallbackPick.currentValue)
    readonly property bool fallbackIsCloud: L.isCloudProvider(core.modelsFallback.provider) || (!!fallbackPicked && fallbackPicked.kind === "cloud")
    readonly property bool fallbackAllowed: !!fallbackPicked && (fallbackPicked.kind !== "cloud" || core.llmConfig.cloud_consent === true)
    readonly property var selected: AppState.selectedModel

    function keyOf(provider) { return core.llmSecretsConfigured[provider] === true }
    function kindText(kind) { return kind === "local" ? qsTr("Local") : qsTr("Nuvem") }
    function currentModel() {
        var sel = core.modelsSelected
        if (!sel || !sel.provider) return null
        for (var i = 0; i < allModels.length; i++) if (allModels[i].provider === sel.provider && allModels[i].model === sel.model) return allModels[i]
        return null
    }
    function currentTitle() {
        var m = currentModel()
        return m ? qsTr("%1 · %2 · %3 · %4").arg(m.label).arg(kindText(m.kind)).arg(core.providerLabel(m.provider)).arg(m.model) : ""
    }
    function isCustom(m) { for (var i = 0; i < core.modelsCustom.length; i++) if (core.modelsCustom[i].id === m.id) return true; return false }
    function lkgText() {
        var lkg = core.llmConfig.lkg
        if (!lkg || !lkg.provider) return qsTr("Nenhum modelo marcado como bom ainda.")
        return qsTr("Último bom: %1 · %2").arg(core.providerLabel(lkg.provider)).arg(lkg.model)
    }
    // The Core snapshot gives the model status as a code (core.modelsStatusCode); the label is translated here.
    function statusLabel(code) {
        switch (code) {
        case "testing": return qsTr("Em teste")
        case "no_config": return qsTr("Sem modelo selecionado")
        case "no_key": return qsTr("Sem chave")
        case "no_consent": return qsTr("Sem consentimento")
        case "no_model_data": return qsTr("Sem dados do modelo")
        case "tool_use_unsupported": return qsTr("Indisponível: uso de ferramenta não suportado")
        case "available": return qsTr("Disponível")
        default: return ""
        }
    }
    function statusTone(code) {
        switch (code) {
        case "available": return "success"
        case "no_key": case "no_consent": return "warning"
        case "testing": return "info"
        case "tool_use_unsupported": return "error"
        default: return "neutral"
        }
    }
    function selectModel(m) { AppState.selectedModel = m; AppState.modelsRevisionCaptured = core.llmRevision }
    function useReason() {
        if (core.modelsBusy) return qsTr("Aguarde: a operação de modelo anterior ainda está em andamento.")
        if (!selected) return qsTr("Escolha um modelo na lista.")
        if (selected.kind === "cloud" && !keyOf(selected.provider)) return qsTr("Sem chave: salve a chave do provedor em Provedor e chaves.")
        if (selected.kind === "cloud" && core.llmConfig.cloud_consent !== true) return qsTr("Sem consentimento: permita o envio à nuvem em Provedor e chaves.")
        return ""
    }
    function fallbackReason() {
        if (core.modelsBusy) return qsTr("Aguarde: operação de modelo em andamento.")
        if (!fallbackPicked) return ""
        if (fallbackPicked.kind === "cloud" && !keyOf(fallbackPicked.provider)) return qsTr("Sem chave: salve a chave do provedor em Provedor e chaves.")
        if (fallbackPicked.kind === "cloud" && core.llmConfig.cloud_consent !== true) return qsTr("Sem consentimento: marque o envio à nuvem em Provedor e chaves.")
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
    // A saved custom model is listed below the form, out of sight at a small window: once the Core lists it, its row is scrolled into view.
    property var customBefore: []
    property bool revealCustom: false
    function revealNewCustom() {
        var fresh = core.modelsCustom.filter(function (m) { return page.customBefore.indexOf(m.id) < 0 })
        if (core.modelsBusy) return
        page.revealCustom = false
        if (fresh.length === 0) return
        Qt.callLater(function () {
            for (var i = 0; i < modelRows.count; i++) {
                var row = modelRows.itemAt(i)
                if (row && row.modelData && row.modelData.id === fresh[0].id) { Reveal.revealItem(row); return }
            }
        })
    }
    Connections {
        target: core
        function onModelsStateChanged() {
            if (!core.modelsBusy) AppState.modelsRevisionCaptured = core.llmRevision
            if (page.revealCustom) page.revealNewCustom()
        }
    }
    Component.onCompleted: { AppState.modelsRevisionCaptured = core.llmRevision }

    PageHeader {
        title: qsTr("Modelos LLM")
        subtitle: qsTr("Escolha, teste e configure o modelo do motor LLM instalado.")
        GButton {
            objectName: "modelsRefresh"
            variant: "primary"
            text: qsTr("Atualizar lista")
            Accessible.name: qsTr("Atualizar lista de modelos")
            enabled: core.modelsAvailable && !core.modelsBusy
            onClicked: core.listModels(page.customTab ? "custom" : "recommended")
        }
    }
    // The one notice of the page: why only the provider part is left.
    Banner {
        objectName: "modelsStatusBanner"
        kind: "info"
        text: core.modelsAvailable ? "" : qsTr("Só Provedor e chaves está disponível: o plugin llm_engine não está ativo. Modelos LLM aparece completo quando o plugin estiver ativo.")
        actionText: qsTr("Instalar em Extensões › Plugins")
        onActionRequested: Window.window.goPage("plugins")
    }
    CSummaryBar {
        text: page.hasCurrent ? qsTr("Modelo atual: %1 · %2").arg(core.providerLabel(core.modelsSelected.provider)).arg(core.modelsSelected.model) : qsTr("Nenhum modelo configurado")
        Badge {
            visible: page.hasCurrent
            text: page.statusLabel(core.modelsStatusCode)
            tone: page.statusTone(core.modelsStatusCode)
        }
        Badge {
            visible: page.hasCurrent
            text: L.isCloudProvider(core.modelsSelected.provider) ? qsTr("Nuvem") : qsTr("Local")
            tone: L.isCloudProvider(core.modelsSelected.provider) ? "info" : "neutral"
        }
    }
    GProgressBar {
        objectName: "modelsProgress"
        visible: core.modelsBusy
        indeterminate: true
        Layout.fillWidth: true
        Accessible.name: qsTr("Operação de modelo em andamento")
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
        Accessible.name: qsTr("Resultado do modelo: %1").arg(text)
    }
    Segmented {
        objectName: "modelParts"
        model: core.modelsAvailable
            ? [{id: "atual", text: qsTr("Modelo atual")}, {id: "catalogo", text: qsTr("Catálogo")}, {id: "personalizados", text: qsTr("Personalizados")}, {id: "provedor", text: qsTr("Provedor e chaves")}, {id: "fallback", text: qsTr("Fallback e hardware")}]
            : [{id: "provedor", text: qsTr("Provedor e chaves")}]
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
            title: qsTr("Configurado")
            Layout.alignment: Qt.AlignTop
            Text {
                objectName: "modelsSelectedLabel"
                text: page.hasCurrent ? qsTr("Configurado: %1 · %2").arg(core.providerLabel(core.modelsSelected.provider)).arg(core.modelsSelected.model) : qsTr("Nenhum modelo configurado")
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
                    text: qsTr("Estado do modelo atual:")
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                }
                Badge {
                    objectName: "modelsStatus"
                    visible: page.hasCurrent
                    text: page.statusLabel(core.modelsStatusCode)
                    tone: page.statusTone(core.modelsStatusCode)
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
                text: page.currentModel() && page.currentModel().offline ? qsTr("Funciona offline") : qsTr("Requer rede")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                Layout.fillWidth: true
            }
            Flow {
                Layout.fillWidth: true
                spacing: Theme.space(8)
                GButton { objectName: "testModelButton"; variant: "secondary"; text: qsTr("Testar"); enabled: core.llmTestAvailable; Accessible.name: qsTr("Testar modelo atual"); onClicked: core.llmSelftest() }
                GButton { objectName: "rollbackModelButton"; variant: "secondary"; text: qsTr("Voltar ao último bom"); enabled: core.llmRollbackAvailable; Accessible.name: qsTr("Voltar ao último bom"); onClicked: core.llmRollback() }
                GButton { objectName: "otherModelButton"; variant: "secondary"; text: qsTr("Usar outro modelo"); enabled: core.modelsAvailable; Accessible.name: qsTr("Usar outro modelo"); onClicked: page.part = "catalogo" }
            }
            Text {
                objectName: "testModelReason"
                text: !page.hasCurrent ? qsTr("Configure um modelo antes de testar.")
                    : !core.modelsAvailable ? qsTr("Teste indisponível: o plugin llm_engine não está ativo.")
                    : core.modelsBusy ? qsTr("Aguarde a operação de modelo em andamento.")
                    : qsTr("O resultado do teste aparece acima. Voltar ao último bom usa a configuração marcada como boa.")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        Card {
            title: qsTr("Detalhes do modelo atual")
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
                text: qsTr("Detalhes indisponíveis: carregue o catálogo para ver este modelo.")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            // B14 (P8-C5): shown only while the recommended list is incomplete (or not loaded yet); a complete list hides it.
            GButton {
                visible: page.hasCurrent && page.currentModel() === null && (page.recommendedMoreLeft || page.recommendedNotLoaded)
                variant: "secondary"
                text: qsTr("Carregar mais")
                Accessible.name: qsTr("Carregar mais modelos")
                enabled: core.modelsAvailable && !core.modelsBusy
                onClicked: core.loadMoreModels("recommended")
            }
        }
    }

    // Personalizados: the form for a model the user adds (the Core keeps the rules; the form only reports problems).
    Section {
        objectName: "customForm"
        visible: page.activePart === "personalizados"
        title: qsTr("Adicionar modelo personalizado")
        FieldLabel { text: qsTr("Provedor do modelo personalizado") }
        Select {
            id: customProvider
            objectName: "customProvider"
            Layout.fillWidth: true
            textRole: "text"
            valueRole: "id"
            Accessible.name: qsTr("Provedor do modelo personalizado")
            model: [{id: "local", text: qsTr("Local (llama.cpp)")}, {id: "ollama", text: qsTr("Ollama (local)")}, {id: "custom", text: qsTr("Personalizado (https)")}, {id: "openrouter", text: qsTr("OpenRouter (nuvem)")}, {id: "opencode", text: qsTr("OpenCode (nuvem)")}, {id: "google", text: qsTr("Google AI Studio (nuvem)")}]
        }
        FieldLabel { text: qsTr("Identificador do modelo: letras, números e . _ : / - (até 128)") }
        GTextField {
            id: customModelId
            objectName: "customModelId"
            Layout.fillWidth: true
            maximumLength: 128
            placeholderText: qsTr("Identificador do modelo")
            Accessible.name: qsTr("Identificador do modelo personalizado")
            validator: RegularExpressionValidator { regularExpression: /[A-Za-z0-9._:\/-]{1,128}/ }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(12)
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: qsTr("Porta do servidor local, de 1024 a 65535") }
                SpinBox {
                    id: customPort
                    objectName: "customPort"
                    from: 1024; to: 65535; value: 8080; editable: true
                    enabled: customProvider.currentValue === "local" || customProvider.currentValue === "ollama"
                    Accessible.name: qsTr("Porta do servidor local, de 1024 a 65535")
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: qsTr("URL https do modelo personalizado") }
                GTextField {
                    id: customUrl
                    objectName: "customUrl"
                    Layout.fillWidth: true
                    maximumLength: 200
                    placeholderText: "https://"
                    enabled: customProvider.currentValue === "custom"
                    Accessible.name: qsTr("URL https do modelo personalizado")
                }
            }
        }
        FieldLabel { text: qsTr("Recursos declarados (não certificados)") }
        GridLayout {
            Layout.fillWidth: true
            columns: page.wide ? 2 : 1
            columnSpacing: Theme.space(12)
            rowSpacing: Theme.space(8)
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: qsTr("Streaming") }
                Select { id: customStreaming; objectName: "customStreaming"; Layout.fillWidth: true; model: L.featureChoices(); textRole: "text"; valueRole: "id"; Accessible.name: qsTr("Streaming declarado") }
            }
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: qsTr("Tool use") }
                Select { id: customToolUse; objectName: "customToolUse"; Layout.fillWidth: true; model: L.featureChoices(); textRole: "text"; valueRole: "id"; Accessible.name: qsTr("Tool use declarado") }
            }
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: qsTr("Visão") }
                Select { id: customVision; objectName: "customVision"; Layout.fillWidth: true; model: L.featureChoices(); textRole: "text"; valueRole: "id"; Accessible.name: qsTr("Visão declarada") }
            }
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: qsTr("Cancelamento") }
                Select { id: customCancel; objectName: "customCancel"; Layout.fillWidth: true; model: L.featureChoices(); textRole: "text"; valueRole: "id"; Accessible.name: qsTr("Cancelamento declarado") }
            }
        }
        Text {
            text: qsTr("Recursos declarados não são certificados; o selftest é que confirma.")
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
            text: qsTr("Salvar modelo personalizado")
            Accessible.name: qsTr("Salvar modelo personalizado")
            enabled: core.modelsAvailable && !core.modelsBusy && core.customFormProblem(page.customForm()) === ""
            onClicked: { page.customBefore = core.modelsCustom.map(function (m) { return m.id }); page.revealCustom = true; core.saveCustomModel(page.customForm()) }
        }
    }

    // Catálogo and the custom list share one list: the tabs pick which one is shown.
    Section {
        objectName: "catalogSection"
        visible: page.activePart === "catalogo" || page.activePart === "personalizados"
        title: page.activePart === "catalogo" ? qsTr("Catálogo") : qsTr("Modelos personalizados")
        TabBar {
            id: modelsTabs
            objectName: "modelsTabs"
            Layout.fillWidth: true
            onCurrentIndexChanged: core.listModels(currentIndex === 0 ? "recommended" : "custom")
            background: Rectangle { color: "transparent" }
            TabButton {
                objectName: "modelsTabRecommended"; text: qsTr("Recomendados"); Accessible.name: qsTr("Aba Recomendados")
                background: Rectangle { color: parent.checked ? Theme.tint : "transparent"; radius: Theme.radius; border.width: 1; border.color: Theme.strongOutline }
                contentItem: Text { text: parent.text; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: parent.checked ? 600 : 400; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
            }
            TabButton {
                objectName: "modelsTabCustom"; text: qsTr("Personalizados"); Accessible.name: qsTr("Aba Personalizados")
                background: Rectangle { color: parent.checked ? Theme.tint : "transparent"; radius: Theme.radius; border.width: 1; border.color: Theme.strongOutline }
                contentItem: Text { text: parent.text; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: parent.checked ? 600 : 400; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Text { text: qsTr("Mostrar:"); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp }
            Select { id: modelsFilter; objectName: "modelsFilter"; model: [qsTr("Todos"), qsTr("Local"), qsTr("Nuvem")]; Accessible.name: qsTr("Filtro por local ou nuvem") }
        }
        Text {
            objectName: "modelsCount"
            text: page.customTab ? qsTr("%1 de %2").arg(core.modelsCustom.length).arg(core.modelsCustomTotal) : qsTr("%1 de %2").arg(core.modelsRecommended.length).arg(core.modelsRecommendedTotal)
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
            Accessible.name: qsTr("Modelos carregados: %1").arg(text)
        }
        EmptyState {
            visible: modelRows.count === 0
            iconName: "cpu"
            message: page.customTab ? qsTr("Nenhum modelo personalizado. Adicione um no formulário acima.") : qsTr("Nenhum modelo nesta lista.")
        }
        Repeater {
            id: modelRows
            model: L.filteredModels(page.customTab ? core.modelsCustom : core.modelsRecommended, modelsFilter.currentIndex)
            delegate: ListRow {
                required property var modelData
                objectName: "model_" + modelData.id
                title: modelData.label
                detail: page.kindText(modelData.kind)
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
            text: qsTr("Carregar mais")
            visible: page.customTab ? core.modelsCustom.length < core.modelsCustomTotal : core.modelsRecommended.length < core.modelsRecommendedTotal
            enabled: core.modelsAvailable && !core.modelsBusy
            Accessible.name: qsTr("Carregar mais modelos")
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
            Text {
                objectName: "modelDescribed"
                visible: page.selected !== null && core.modelDescription.id === page.selected.id
                text: visible ? qsTr("Descrição do plugin: %1 · certificação: %2").arg(core.modelDescription.label).arg(core.modelDescription.certification ? core.modelDescription.certification.state : qsTr("desconhecida")) + (core.modelDescription.sha256 ? qsTr(" · sha256 %1…").arg(String(core.modelDescription.sha256).slice(0, 12)) : "") : ""
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
                    text: qsTr("Usar este modelo")
                    Accessible.name: page.selected ? qsTr("Usar este modelo: %1").arg(page.selected.label) : qsTr("Usar este modelo")
                    enabled: core.modelsAvailable && page.selected !== null && page.useReason() === ""
                    onClicked: core.useModel(page.selected.id, AppState.modelsRevisionCaptured)
                }
                GButton {
                    objectName: "describeModelButton"
                    variant: "secondary"
                    text: qsTr("Descrever")
                    Accessible.name: page.selected ? qsTr("Descrever modelo %1").arg(page.selected.id) : qsTr("Descrever modelo")
                    enabled: core.modelsAvailable && page.selected !== null && !core.modelsBusy
                    onClicked: core.describeModel(page.selected.id)
                }
                Item { Layout.fillWidth: true }
                GButton {
                    objectName: "removeCustomButton"
                    visible: page.customTab && page.selected !== null && page.isCustom(page.selected)
                    variant: "danger"
                    text: qsTr("Remover")
                    Accessible.name: page.selected ? qsTr("Remover modelo personalizado %1").arg(page.selected.id) : qsTr("Remover")
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
                title: qsTr("Configuração")
                Layout.alignment: Qt.AlignTop
                FieldLabel { text: qsTr("Provedor") }
                Select {
                    id: providerBox
                    objectName: "llmProvider"
                    Layout.fillWidth: true
                    enabled: core.llmConfigAvailable
                    textRole: "text"; valueRole: "id"
                    Accessible.name: qsTr("Provedor do motor LLM")
                    model: [{id: "openrouter", text: "OpenRouter"}, {id: "opencode", text: "OpenCode"}, {id: "google", text: "Google AI Studio"}, {id: "custom", text: qsTr("Personalizado")}]
                }
                FieldLabel { text: qsTr("Modelo: letras, números e . _ : / - (até 128)") }
                GTextField {
                    id: modelField
                    objectName: "llmModel"
                    Layout.fillWidth: true
                    maximumLength: 128
                    enabled: core.llmConfigAvailable
                    placeholderText: qsTr("ex.: gemini-3.5-flash-lite")
                    Accessible.name: qsTr("Modelo do motor LLM")
                    validator: RegularExpressionValidator { regularExpression: /[A-Za-z0-9._:\/-]{1,128}/ }
                }
                FieldLabel { visible: providerBox.currentValue === "custom"; text: qsTr("URL personalizada: somente https (http apenas em loopback de teste)") }
                GTextField {
                    id: urlField
                    objectName: "llmUrl"
                    Layout.fillWidth: true
                    maximumLength: 200
                    enabled: providerBox.currentValue === "custom" && core.llmConfigAvailable
                    placeholderText: "https://"
                    Accessible.name: qsTr("URL do provedor personalizado")
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    FieldLabel { text: qsTr("Chave"); Layout.fillWidth: true }
                    Badge {
                        objectName: "llmKeyStatus"
                        visible: page.keyOf(providerBox.currentValue)
                        text: page.keyOf(providerBox.currentValue) ? qsTr("Chave configurada") : qsTr("Sem chave")
                        tone: "success"
                        Accessible.name: qsTr("Estado da chave: %1").arg(text)
                    }
                }
                GTextField {
                    id: keyField
                    objectName: "llmKey"
                    Layout.fillWidth: true
                    echoMode: TextInput.Password
                    maximumLength: 256
                    inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                    placeholderText: qsTr("Chave de API (somente escrita)")
                    enabled: core.llmConfigAvailable
                    Accessible.name: qsTr("Chave de API do provedor")
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    GButton {
                        objectName: "saveKeyButton"
                        variant: "primary"
                        text: qsTr("Salvar chave")
                        Accessible.name: qsTr("Salvar chave do provedor")
                        enabled: core.llmConfigAvailable && keyField.text.length > 0
                        // The field is cleared at once: the key leaves QML with this call.
                        onClicked: { core.setApiKey(providerBox.currentValue, keyField.text); keyField.text = "" }
                    }
                    GButton {
                        objectName: "clearKeyButton"
                        variant: "danger"
                        text: qsTr("Remover chave")
                        Accessible.name: qsTr("Remover chave do provedor")
                        enabled: core.llmConfigAvailable && page.keyOf(providerBox.currentValue)
                        onClicked: clearKeyConfirm.open()
                    }
                }
                Text {
                    text: qsTr("A chave não volta a aparecer depois de enviada.")
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
            Section {
                title: qsTr("Nuvem e salvar")
                Layout.alignment: Qt.AlignTop
                GCheckbox {
                    id: consentBox
                    objectName: "llmConsent"
                    checked: false
                    text: qsTr("Permitir envio de conversas ao provedor na nuvem")
                    enabled: core.llmConfigAvailable
                    Accessible.name: qsTr("Consentimento para envio à nuvem")
                    Accessible.description: qsTr("Mensagens serão enviadas ao provedor escolhido na nuvem")
                }
                Text {
                    objectName: "llmConsentWarning"
                    text: qsTr("Mensagens serão enviadas ao provedor escolhido na nuvem")
                    textFormat: Text.PlainText
                    color: Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    text: qsTr("Consentimento salvo: %1").arg(core.llmConfig.cloud_consent === true ? qsTr("concedido") : qsTr("não concedido"))
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
                    text: qsTr("Salvar configuração")
                    Accessible.name: qsTr("Salvar configuração do Motor LLM")
                    enabled: core.llmConfigAvailable && modelField.acceptableInput && core.llmConfig.provider !== "local" && core.llmConfig.provider !== "ollama"
                    onClicked: core.configureLlm(providerBox.currentValue, modelField.text, providerBox.currentValue === "custom" ? urlField.text : "", consentBox.checked, AppState.llmRevisionCaptured)
                }
                // A local provider is configured through the catalog; this form would otherwise overwrite it.
                Text {
                    objectName: "llmLocalNotice"
                    visible: core.llmConfig.provider === "local" || core.llmConfig.provider === "ollama"
                    text: qsTr("Configuração local ativa: %1 · %2. Troque em Catálogo.").arg(core.providerLabel(core.llmConfig.provider)).arg(core.llmConfig.model || "")
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
            title: qsTr("Como funciona")
            summary: qsTr("Motor opcional. Sem ele, voz, wake e comandos da Base continuam funcionando.")
            Text {
                text: qsTr("Provedor, modelo, URL e consentimento são gravados pelo Core. A chave é só de escrita: nunca é mostrada de volta.")
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
            title: qsTr("Tem certeza?")
            Text {
                text: qsTr("Remover a chave do provedor %1? As chamadas a este provedor param até você salvar outra chave.").arg(providerBox.displayText)
                textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            GButton {
                objectName: "confirmClearKeyButton"
                variant: "danger"
                text: qsTr("Remover chave")
                Layout.alignment: Qt.AlignRight
                Accessible.name: qsTr("Remover chave do provedor")
                onClicked: clearKeyConfirm.accept()
            }
            onAccepted: core.clearApiKey(providerBox.currentValue)
        }
    }

    // Fallback e hardware.
    Section {
        visible: page.activePart === "fallback"
        title: qsTr("Fallback (opcional)")
        Text {
            objectName: "fallbackCurrent"
            text: core.modelsFallback.provider ? qsTr("Atual: %1 · %2").arg(core.providerLabel(core.modelsFallback.provider)).arg(core.modelsFallback.model) : qsTr("Nenhum fallback configurado")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            text: qsTr("Usado só depois de erro recuperável do modelo principal (429, 5xx, rede ou tempo esgotado). Nunca em erro de chave ou permissão.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        FieldLabel { text: qsTr("Modelo para fallback") }
        Select { id: fallbackPick; objectName: "fallbackModel"; Layout.fillWidth: true; model: page.allModels; textRole: "label"; valueRole: "id"; Accessible.name: qsTr("Modelo para fallback") }
        Text {
            objectName: "fallbackCloudWarning"
            visible: page.fallbackIsCloud
            text: qsTr("Mensagens poderão ir para a nuvem se o modelo principal falhar")
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: qsTr("Aviso: envio à nuvem no fallback")
        }
        Text {
            objectName: "fallbackConsentNeeded"
            visible: page.fallbackIsCloud && core.llmConfig.cloud_consent !== true
            text: qsTr("Para fallback na nuvem, marque o consentimento em Provedor e chaves.")
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
            GButton { objectName: "setFallbackButton"; variant: "primary"; text: qsTr("Usar como fallback"); Accessible.name: qsTr("Usar o modelo escolhido como fallback"); enabled: core.modelsAvailable && !core.modelsBusy && fallbackPick.currentIndex >= 0 && page.fallbackAllowed; onClicked: core.setFallback(fallbackPick.currentValue, AppState.modelsRevisionCaptured) }
            GButton { objectName: "clearFallbackButton"; variant: "secondary"; text: qsTr("Remover fallback"); Accessible.name: qsTr("Remover fallback"); enabled: core.modelsAvailable && !core.modelsBusy && !!core.modelsFallback.provider; onClicked: core.clearFallback(AppState.modelsRevisionCaptured) }
        }
    }
    Section {
        visible: page.activePart === "fallback"
        title: qsTr("Hardware e plugin")
        Text {
            objectName: "modelsHardware"
            text: core.modelsHardware.cpu_cores
                ? qsTr("CPU: %1 núcleos · RAM: %2 · GPU: %3").arg(core.modelsHardware.cpu_cores).arg(core.modelsHardware.ram_gb === null ? qsTr("desconhecida") : qsTr("%1 GB").arg(core.modelsHardware.ram_gb)).arg(core.modelsHardware.gpu === "unknown" ? qsTr("desconhecido") : core.modelsHardware.gpu)
                : qsTr("Hardware: aguardando catálogo")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            text: qsTr("Apaga só os dados guardados pelo plugin. Não altera o Core.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton { objectName: "clearPluginSettingsButton"; variant: "danger"; text: qsTr("Apagar dados do plugin"); Accessible.name: qsTr("Apagar dados do plugin LLM"); enabled: core.connected && !core.modelsBusy; onClicked: clearPluginConfirm.open() }
    }

    Modal {
        id: removeCustomConfirm
        objectName: "removeCustomConfirm"
        property var entry: null
        title: qsTr("Tem certeza?")
        onAccepted: { if (entry) core.deleteCustomModel(entry.id) }
        Text { text: removeCustomConfirm.entry ? qsTr("Remover %1 da lista de modelos personalizados? O modelo no provedor não é apagado.").arg(removeCustomConfirm.entry.label) : ""; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        GButton { objectName: "confirmRemoveCustomButton"; variant: "danger"; text: qsTr("Remover"); Layout.alignment: Qt.AlignRight; Accessible.name: removeCustomConfirm.entry ? qsTr("Remover modelo %1").arg(removeCustomConfirm.entry.id) : qsTr("Remover"); onClicked: removeCustomConfirm.accept() }
    }
    Modal {
        id: clearPluginConfirm
        objectName: "clearPluginConfirm"
        title: qsTr("Tem certeza?")
        onAccepted: core.clearPluginSettings()
        Text { text: qsTr("Apagar as configurações guardadas pelo plugin LLM, inclusive modelos personalizados? O plugin e a configuração do Core (provedor, modelo e chaves) não são alterados."); textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        GButton { objectName: "confirmClearPluginButton"; variant: "danger"; text: qsTr("Apagar dados"); Accessible.name: qsTr("Apagar dados do plugin LLM"); Layout.alignment: Qt.AlignRight; onClicked: clearPluginConfirm.accept() }
    }
}
