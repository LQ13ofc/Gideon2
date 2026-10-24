import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../components/BExt.js" as X
import "../shell"
import "../shell/Labels.js" as L

// Extensões > Skills (B02). Four segments: Minhas (a list of 56 px rows with the drawer on the right), Criar,
// Importar/Exportar and Execuções. Every value is the Core snapshot 'skills' block. Nothing here grants a permission.
PageFrame {
    id: page
    objectName: "skillsPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "skills" && core.skillsAvailable

    property string part: "minhas"
    property string selectedKey: ""
    readonly property bool runActive: L.skillRunActive(core.skillCurrentRun)

    // Entradas (JSON de objeto, até 16 KiB): a local value, checked here before Simular and Executar.
    function inputsValid(text) {
        if (text.length > 16384) return false
        try {
            var v = JSON.parse(text)
            return v !== null && typeof v === "object" && !Array.isArray(v)
        } catch (e) { return false }
    }
    readonly property bool inputsOk: inputsValid(skillInputs.text)
    readonly property var ctx: ({
        skillsAvailable: core.skillsAvailable,
        busy: core.skillsBusy,
        runActive: page.runActive,
        inputsOk: page.inputsOk,
        inputs: skillInputs.text,
        blockedText: core.connected ? "Indisponível agora." : "Core desconectado: nada pode ser alterado agora."
    })
    readonly property var exportables: {
        var out = []
        var items = core.skillsItems
        for (var i = 0; i < items.length; i++) if (X.exportable(items[i].state)) out.push(items[i])
        return out
    }
    readonly property var selectedSkill: {
        var items = core.skillsItems
        for (var i = 0; i < items.length; i++) if (items[i].id + "_" + items[i].version === page.selectedKey) return items[i]
        return null
    }
    readonly property string summary: {
        var items = core.skillsItems
        var enabled = 0
        var drafts = 0
        for (var i = 0; i < items.length; i++) {
            if (items[i].state === "enabled") enabled++
            if (items[i].state === "draft" || items[i].state === "validated") drafts++
        }
        return items.length + " instaladas · " + enabled + " habilitadas · " + drafts + " rascunhos"
    }

    function permissionText(p) {
        var label = core.permissionLabel(p)
        return label === p ? "permissão sem rótulo: " + p : label
    }
    function labelsOf(list) {
        return (list || []).length ? list.map(function (p) { return page.permissionText(p) }).join(", ") : "nenhuma"
    }
    function askRemove(skill) { removeSkillConfirm.skill = skill; removeSkillConfirm.open() }

    PageHeader {
        title: "Skills"
        subtitle: "Procedimentos que combinam capacidades instaladas. Nada aqui concede permissões."
        GButton {
            objectName: "skillNewButton"
            text: "Nova skill"
            variant: "primary"
            Accessible.name: "Nova skill: abrir o segmento Criar"
            onClicked: page.part = "criar"
        }
    }
    Text {
        objectName: "skillsSummary"
        text: page.summary
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        font.weight: 600
        Layout.fillWidth: true
    }
    Text {
        objectName: "skillsResult"
        visible: text.length > 0
        text: core.skillsResult
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Accessible.name: "Resultado das skills: " + text
    }
    GProgressBar {
        objectName: "skillsProgress"
        visible: core.skillsBusy
        indeterminate: true
        Layout.fillWidth: true
        Accessible.name: "Operação de skill em andamento"
    }
    Segmented {
        objectName: "skillParts"
        model: [{id: "minhas", text: "Minhas"}, {id: "criar", text: "Criar"}, {id: "importar", text: "Importar/Exportar"}, {id: "execucoes", text: "Execuções"}]
        currentId: page.part
        onActivated: function (id) { page.part = id }
    }

    // Minhas: the list of installed skills, the drawer of the picked one, and the JSON inputs for Simular and Executar.
    ColumnLayout {
        visible: page.part === "minhas"
        Layout.fillWidth: true
        spacing: Theme.space(12)

        Collapsible {
            title: "Como funciona"
            summary: "Nada aqui concede permissão."
            Text {
                text: "Validar não grava. Simular não chama capacidades. Executar pede sua aprovação em cada passo que muda estado."
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
        }
        Collapsible {
            objectName: "skillInputsBlock"
            title: "Entradas (JSON)"
            summary: "Entradas (JSON de objeto, até 16 KiB) para Simular e Executar"
            TextArea {
                id: skillInputs
                objectName: "skillInputs"
                Layout.fillWidth: true
                Layout.preferredHeight: 120
                text: "{}"
                textFormat: TextEdit.PlainText
                wrapMode: TextEdit.Wrap
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                placeholderText: "{ \"campo\": \"valor\" }"
                placeholderTextColor: Theme.textMuted
                Accessible.name: "Entradas da skill em JSON"
                background: Rectangle { color: Theme.bg; radius: Theme.radius; border.width: 1; border.color: Theme.strongOutline }
            }
            Text {
                visible: !page.inputsOk
                text: "Entradas inválidas: use um objeto JSON de até 16 KiB."
                textFormat: Text.PlainText
                color: Theme.error
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: Theme.space(16)

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: 0
                EmptyState {
                    objectName: "skillsEmpty"
                    visible: core.skillsItems.length === 0
                    iconName: "puzzle"
                    message: "Nenhuma skill no Core ainda."
                    actionText: "Nova skill"
                    onActionRequested: page.part = "criar"
                }
                Repeater {
                    model: core.skillsItems
                    delegate: BSkillRow {
                        required property var modelData
                        skill: modelData
                        ctx: page.ctx
                        selected: (modelData.id + "_" + modelData.version) === page.selectedKey
                        onSelectRequested: page.selectedKey = modelData.id + "_" + modelData.version
                    }
                }
            }

            BSkillDetail {
                visible: page.selectedSkill !== null
                skill: page.selectedSkill
                ctx: page.ctx
                onRemoveRequested: function (s) { page.askRemove(s) }
                onCloseRequested: page.selectedKey = ""
            }
        }
    }

    // Criar: manifest JSON by hand; the LLM only drafts (never enabled here).
    RowLayout {
        visible: page.part === "criar"
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignTop
        spacing: Theme.space(16)

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: Theme.space(10)
            FieldLabel { text: "Manifesto da skill em JSON" }
            TextArea {
                id: skillManifest
                objectName: "skillManifest"
                Layout.fillWidth: true
                Layout.preferredHeight: 320
                textFormat: TextEdit.PlainText
                wrapMode: TextEdit.Wrap
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                placeholderText: "Cole o manifesto JSON da skill (até 16 KiB)."
                placeholderTextColor: Theme.textMuted
                Accessible.name: "Manifesto da skill em JSON"
                background: Rectangle { color: Theme.bg; radius: Theme.radius; border.width: 1; border.color: Theme.strongOutline }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(10)
                GButton {
                    objectName: "skillValidate"
                    variant: "secondary"
                    text: "Validar"
                    Accessible.name: "Validar manifest da skill"
                    enabled: !core.skillsBusy && skillManifest.text.trim().length > 0
                    onClicked: core.skillValidate(skillManifest.text)
                }
                GButton {
                    objectName: "skillSaveDraft"
                    variant: "primary"
                    text: "Salvar rascunho"
                    Accessible.name: "Salvar rascunho da skill"
                    enabled: !core.skillsBusy && skillManifest.text.trim().length > 0
                    onClicked: core.skillSaveDraft(skillManifest.text)
                }
                Item { Layout.fillWidth: true }
            }
        }

        ColumnLayout {
            Layout.preferredWidth: 360
            Layout.alignment: Qt.AlignTop
            spacing: Theme.space(12)
            Card {
                title: "Gerar com LLM"
                FieldLabel { text: "Descrição da skill para o LLM" }
                GTextField {
                    id: skillDescription
                    objectName: "skillDescription"
                    Layout.fillWidth: true
                    maximumLength: 1024
                    placeholderText: "Descreva o que a skill deve fazer (até 1024 bytes)."
                    Accessible.name: "Descrição da skill para o LLM"
                }
                GButton {
                    objectName: "skillDraftWithLlm"
                    variant: "primary"
                    text: "Gerar com LLM"
                    Accessible.name: "Gerar skill com o LLM"
                    enabled: core.skillLlmAvailable && !core.skillsBusy && skillDescription.text.trim().length > 0
                    onClicked: core.skillDraftWithLlm(skillDescription.text)
                }
                Text {
                    objectName: "skillLlmUnavailable"
                    visible: !core.skillLlmAvailable
                    text: "Gerar com LLM indisponível: o plugin llm_engine não está ativo."
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
                GButton {
                    visible: !core.skillLlmAvailable
                    variant: "ghost"
                    text: "Instalar em Extensões › Plugins"
                    Accessible.name: "Instalar em Extensões › Plugins"
                    onClicked: { if (Window.window && Window.window.goPage) Window.window.goPage("plugins") }
                }
                Text {
                    text: "O rascunho nunca fica habilitado. Você valida, simula e aprova antes de usar."
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
            }
            Card {
                objectName: "skillDraftOutput"
                visible: !!core.skillDraftOutput.draft_id
                title: visible ? "Rascunho " + core.skillDraftOutput.draft_id + " · v" + core.skillDraftOutput.version + " · " + L.skillStateText(core.skillDraftOutput.state) + " · nada foi habilitado" : ""
                Text { text: "Requisitos: " + ((core.skillDraftOutput.requirements || []).join(", ") || "nenhum"); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { text: "Ambiguidades: " + ((core.skillDraftOutput.ambiguities || []).join("; ") || "nenhuma"); textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { text: "Passos previstos:\n" + ((core.skillDraftOutput.preview || []).map(function (p) { return p.id + " → " + p.call }).join("\n") || "nenhum"); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { visible: !!core.skillDraftOutput.diff; text: "Diferença:\n" + (core.skillDraftOutput.diff || ""); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
            }
        }
    }

    // Importar/Exportar: the Core reads only <home>/skill-imports/<name>.gskill and previews it; nothing installs until confirmed.
    ColumnLayout {
        visible: page.part === "importar"
        Layout.fillWidth: true
        spacing: Theme.space(16)

        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: Theme.space(16)

            Card {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                title: "Importar pacote"
                Text {
                    text: "Coloque o arquivo .gskill na pasta de importação e informe o nome, sem caminho e sem extensão."
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
                Text {
                    objectName: "skillImportFolder"
                    text: "Pasta: pasta de importação não informada"
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                }
                FieldLabel { text: "Nome do pacote, sem caminho" }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    GTextField {
                        id: skillImportName
                        objectName: "skillImportName"
                        Layout.fillWidth: true
                        maximumLength: 64
                        placeholderText: "resumo_semanal"
                        validator: RegularExpressionValidator { regularExpression: /[A-Za-z0-9._-]{1,64}/ }
                        Accessible.name: "Nome do pacote para importar"
                    }
                    GButton {
                        objectName: "skillImport"
                        variant: "primary"
                        text: "Pré-visualizar"
                        Accessible.name: "Pré-visualizar importação de skill"
                        enabled: !core.skillsBusy && skillImportName.acceptableInput
                        onClicked: core.skillImport(skillImportName.text)
                    }
                }
                Text {
                    visible: skillImportName.text.length > 0 && !skillImportName.acceptableInput
                    text: "Nome inválido: use letras, números, ponto, traço ou sublinhado (até 64)."
                    textFormat: Text.PlainText; color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
            }

            Card {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                title: "Exportar skill"
                Text {
                    visible: page.exportables.length === 0
                    text: "Nenhuma skill exportável. Aprove uma skill em Minhas."
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
                Repeater {
                    model: page.exportables
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Theme.space(10)
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: modelData.id + " v" + modelData.version
                                textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; elide: Text.ElideRight; Layout.fillWidth: true
                            }
                            Text {
                                text: L.skillStateText(modelData.state)
                                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true
                            }
                        }
                        GButton {
                            objectName: "skillExport_" + modelData.id
                            variant: "secondary"
                            text: "Exportar"
                            Accessible.name: "Exportar " + modelData.id + " v" + modelData.version
                            enabled: !core.skillsBusy
                            onClicked: core.skillExport(modelData.id, modelData.version)
                        }
                    }
                }
            }
        }

        Card {
            objectName: "skillImportPreview"
            visible: !!core.skillImportPreview.name
            Layout.fillWidth: true
            title: visible ? "Pacote " + core.skillImportPreview.name + ": " + core.skillImportPreview.id + " v" + core.skillImportPreview.version : ""
            Text {
                text: "Publisher: " + core.skillImportPreview.publisher + " · não verificado"
                textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                Accessible.name: "Publisher " + core.skillImportPreview.publisher + ", não verificado"
            }
            Text {
                text: "Permissões exigidas: " + page.labelsOf(core.skillImportPreview.permissions_required)
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Text {
                text: "Novas nesta versão: " + page.labelsOf(core.skillImportPreview.permission_delta)
                textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Text {
                visible: core.skillImportPreview.permissions_escalated === true
                text: "Escalada de permissões: esta versão pede mais que a anterior; aprove de novo antes de usar."
                textFormat: Text.PlainText; color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Text {
                text: "Dependências faltando: " + ((core.skillImportPreview.missing_deps || []).join(", ") || "nenhuma")
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Text {
                visible: core.skillImportPreview.duplicate === true
                text: "Já existe uma skill com este id no Core."
                textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Repeater {
                model: core.skillImportPreview.findings || []
                delegate: Text {
                    required property var modelData
                    objectName: "skillFinding_" + modelData.code
                    text: "Achado: " + core.codeMessage(modelData.code) + (modelData.field ? " (" + modelData.field + ")" : "")
                    textFormat: Text.PlainText; color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
            }
            Text {
                text: "Importar instala como rascunho e nunca concede permissões. Valide, simule e aprove antes de usar."
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            GButton {
                id: importConfirm
                objectName: "skillImportConfirm"
                variant: "primary"
                text: "Instalar como rascunho"
                Accessible.name: "Instalar como rascunho o pacote " + core.skillImportPreview.name
                enabled: !core.skillsBusy && (core.skillImportPreview.findings || []).length === 0 && core.skillImportPreview.duplicate !== true
                onClicked: core.skillImportConfirm(core.skillImportPreview.name)
            }
            Text {
                visible: !importConfirm.enabled && (core.skillImportPreview.findings || []).length > 0
                text: "Corrija os achados antes de instalar."
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
        }
        Text {
            visible: !core.skillImportPreview.name
            text: "Nenhum pacote pré-visualizado."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true
        }
    }

    // Execuções: the current run; each step that changes state waits for the user's decision here.
    // A run that waits for a decision is shown on any part: the user starts runs from Minhas and must see the step's buttons.
    ColumnLayout {
        visible: page.part === "execucoes" || core.skillCurrentRun.state === "awaiting_approval"
        Layout.fillWidth: true
        spacing: Theme.space(16)

        Card {
            objectName: "skillRunView"
            visible: !!core.skillCurrentRun.run_id
            Layout.fillWidth: true
            title: ""
            Text {
                objectName: "skillRunState"
                text: "Execução " + core.skillCurrentRun.run_id + " · " + core.skillCurrentRun.skill + " · " + L.skillRunText(core.skillCurrentRun.state) + (core.skillCurrentRun.step ? " · passo " + core.skillCurrentRun.step : "")
                textFormat: Text.PlainText; color: core.skillCurrentRun.state === "failed" ? Theme.error : Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                Accessible.name: "Estado da execução: " + text
            }
            Repeater {
                model: core.skillCurrentRun.steps || []
                delegate: ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: Theme.space(6)
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space(10)
                        Text {
                            objectName: "skillStep_" + modelData.id
                            text: "Passo " + modelData.id + " · " + L.skillStepText(modelData.state) + (modelData.code ? " · " + core.codeMessage(modelData.code) : "")
                            textFormat: Text.PlainText
                            color: modelData.state === "failed" || modelData.state === "denied" ? Theme.error : modelData.state === "awaiting_approval" ? Theme.warning : Theme.text
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
                        }
                        GButton {
                            objectName: "skillDeny_" + modelData.id
                            visible: modelData.state === "awaiting_approval"
                            text: "Negar passo"
                            variant: "secondary"
                            Accessible.name: "Negar o passo " + modelData.id
                            onClicked: core.skillDecide(core.skillCurrentRun.run_id, modelData.id, "deny")
                        }
                        GButton {
                            objectName: "skillAuthorize_" + modelData.id
                            visible: modelData.state === "awaiting_approval"
                            text: "Autorizar passo"
                            variant: "primary"
                            Accessible.name: "Autorizar o passo " + modelData.id
                            onClicked: core.skillDecide(core.skillCurrentRun.run_id, modelData.id, "authorize")
                        }
                    }
                    Text {
                        visible: modelData.state === "awaiting_approval"
                        text: "Passo " + modelData.id + " aguarda sua decisão."
                        textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                }
            }
            Text {
                objectName: "skillOutputs"
                visible: !!core.skillCurrentRun.outputs
                text: "Saídas: " + JSON.stringify(core.skillCurrentRun.outputs || {})
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
            }
            GButton {
                objectName: "skillCancel"
                variant: "danger"
                text: "Cancelar execução"
                Accessible.name: "Cancelar a execução da skill"
                enabled: page.runActive
                onClicked: cancelRunConfirm.open()
            }
        }
        Text {
            objectName: "skillRunEmpty"
            visible: !core.skillCurrentRun.run_id
            text: "Nenhuma execução em andamento."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true
        }

        Text {
            text: "Histórico de execuções"
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSection; font.weight: 600; Layout.fillWidth: true
        }
        Text {
            objectName: "skillHistoryEmpty"
            visible: core.skillHistory.length === 0
            text: "Nenhuma execução registrada."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true
        }
        Repeater {
            model: core.skillHistory
            delegate: Text {
                required property var modelData
                required property int index
                objectName: "skillHistory_" + index
                text: modelData.run_id + " · " + modelData.skill + " v" + modelData.version + " · " + L.skillRunText(modelData.state) + (modelData.step ? " · passo " + modelData.step : "") + (modelData.codes.length ? " · " + modelData.codes.map(function (c) { return core.codeMessage(c) }).join("; ") : "")
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
            }
        }
    }

    // Confirmations (8.7): Cancelar is the focused default; the verb button is the only way to accept.
    Modal {
        id: removeSkillConfirm
        objectName: "removeSkillConfirm"
        property var skill: null
        title: "Remover skill"
        onAccepted: { if (skill) core.skillRemove(skill.id) }
        Text {
            text: removeSkillConfirm.skill ? "Remover " + removeSkillConfirm.skill.id + " v" + removeSkillConfirm.skill.version + " do Core? Nada é executado." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmRemoveSkillButton"; variant: "danger"; text: "Remover"
            Layout.alignment: Qt.AlignRight
            Accessible.name: removeSkillConfirm.skill ? "Remover skill " + removeSkillConfirm.skill.id : "Remover skill"
            onClicked: removeSkillConfirm.accept()
        }
    }
    Modal {
        id: cancelRunConfirm
        objectName: "cancelRunConfirm"
        title: "Cancelar execução"
        onAccepted: core.skillCancel(core.skillCurrentRun.run_id)
        Text {
            text: "Cancelar a execução " + core.skillCurrentRun.run_id + "? Os passos concluídos serão desfeitos."
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmCancelRunButton"; variant: "danger"; text: "Cancelar execução"
            Layout.alignment: Qt.AlignRight
            Accessible.name: "Cancelar a execução da skill"
            onClicked: cancelRunConfirm.accept()
        }
    }
}
