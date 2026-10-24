import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Extensões > Skills. Four parts: Minhas (list and actions), Criar (manifest and LLM draft), Importar/Exportar, Execuções.
// Every value is the Core snapshot 'skills' block. Nothing on this page grants a permission.
PageFrame {
    id: page
    objectName: "skillsPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "skills" && core.skillsAvailable

    property string part: "minhas"
    readonly property bool runActive: L.skillRunActive(core.skillCurrentRun)

    PageHeader {
        title: "Skills"
        subtitle: "Procedimentos sobre capacidades instaladas. Não concedem permissões."
    }
    Collapsible {
        title: "Como funciona"
        summary: "Validar não grava. Simular não chama capacidades. Executar pede sua aprovação em cada passo que muda estado."
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
        model: [{id: "minhas", text: "Minhas"}, {id: "criar", text: "Criar"}, {id: "importar", text: "Importar e exportar"}, {id: "execucoes", text: "Execuções"}]
        currentId: page.part
        onActivated: function (id) { page.part = id }
    }

    // Minhas: every installed skill with its state, dependencies and actions.
    Section {
        visible: page.part === "minhas"
        title: "Minhas skills"
        Text {
            objectName: "skillsEmpty"
            visible: core.skillsItems.length === 0
            text: "Nenhuma skill no Core ainda. Crie uma na aba Criar."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Repeater {
            model: core.skillsItems
            delegate: Card {
                id: skillCard
                required property var modelData
                Text {
                    objectName: "skillTitle_" + skillCard.modelData.id + "_" + skillCard.modelData.version
                    text: skillCard.modelData.name + " · " + skillCard.modelData.id + " v" + skillCard.modelData.version
                    textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                }
                Text {
                    objectName: "skillState_" + skillCard.modelData.id + "_" + skillCard.modelData.version
                    text: "Estado: " + L.skillStateText(skillCard.modelData.state) + " · origem: " + L.skillSourceText(skillCard.modelData.source) + (skillCard.modelData.active ? " · versão ativa" : "")
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
                Text {
                    objectName: "skillDeps_" + skillCard.modelData.id + "_" + skillCard.modelData.version
                    text: "Dependências: " + (skillCard.modelData.deps_ok ? "ok" : "faltando: " + skillCard.modelData.missing.join(", ")) + " · permissões: " + (skillCard.modelData.permissions_ok ? "aprovadas" : "pendentes")
                    textFormat: Text.PlainText; color: skillCard.modelData.deps_ok ? Theme.textMuted : Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.space(8)
                    GButton { objectName: "skillDryRun_" + skillCard.modelData.id + "_" + skillCard.modelData.version; text: "Simular"; variant: "ghost"; Accessible.name: "Simular " + skillCard.modelData.id; enabled: L.skillCan(core.skillsBusy, "dry", skillCard.modelData.state, page.runActive); onClicked: core.skillDryRun(skillCard.modelData.id, skillCard.modelData.version, skillInputs.text) }
                    GButton { objectName: "skillApprove_" + skillCard.modelData.id + "_" + skillCard.modelData.version; text: "Aprovar"; variant: "ghost"; Accessible.name: "Aprovar " + skillCard.modelData.id + " v" + skillCard.modelData.version; enabled: L.skillCan(core.skillsBusy, "approve", skillCard.modelData.state, page.runActive); onClicked: core.skillApprove(skillCard.modelData.id, skillCard.modelData.version) }
                    GButton { objectName: "skillEnable_" + skillCard.modelData.id; text: "Habilitar"; variant: "ghost"; Accessible.name: "Habilitar " + skillCard.modelData.id; enabled: L.skillCan(core.skillsBusy, "enable", skillCard.modelData.state, page.runActive); onClicked: core.skillEnable(skillCard.modelData.id) }
                    GButton { objectName: "skillDisable_" + skillCard.modelData.id; text: "Desabilitar"; variant: "ghost"; Accessible.name: "Desabilitar " + skillCard.modelData.id; enabled: L.skillCan(core.skillsBusy, "disable", skillCard.modelData.state, page.runActive); onClicked: core.skillDisable(skillCard.modelData.id) }
                    GButton { objectName: "skillRun_" + skillCard.modelData.id; text: "Executar"; variant: "secondary"; Accessible.name: "Executar " + skillCard.modelData.id; enabled: L.skillCan(core.skillsBusy, "run", skillCard.modelData.state, page.runActive); onClicked: core.skillRun(skillCard.modelData.id, skillInputs.text) }
                    GButton { objectName: "skillRollback_" + skillCard.modelData.id; text: "Reverter versão"; variant: "ghost"; Accessible.name: "Reverter versão de " + skillCard.modelData.id; enabled: L.skillCan(core.skillsBusy, "rollback", skillCard.modelData.state, page.runActive); onClicked: core.skillRollback(skillCard.modelData.id) }
                    GButton { objectName: "skillPermissions_" + skillCard.modelData.id; text: "Permissões"; variant: "ghost"; Accessible.name: "Ver permissões de " + skillCard.modelData.id; onClicked: AppState.skillSelected = skillCard.modelData }
                    GButton { objectName: "skillExport_" + skillCard.modelData.id; text: "Exportar"; variant: "ghost"; Accessible.name: "Exportar " + skillCard.modelData.id + " v" + skillCard.modelData.version; enabled: L.skillCan(core.skillsBusy, "export", skillCard.modelData.state, page.runActive); onClicked: core.skillExport(skillCard.modelData.id, skillCard.modelData.version) }
                    GButton { objectName: "skillRemove_" + skillCard.modelData.id; text: "Remover"; variant: "danger"; Accessible.name: "Remover " + skillCard.modelData.id; enabled: L.skillCan(core.skillsBusy, "remove", skillCard.modelData.state, page.runActive); onClicked: { removeSkillConfirm.skill = skillCard.modelData; removeSkillConfirm.open() } }
                }
            }
        }
        // Permissões: what the Core reports for the picked row.
        Card {
            objectName: "skillPermissions"
            visible: AppState.skillSelected !== null
            Text { text: AppState.skillSelected ? "Permissões de " + AppState.skillSelected.id + " v" + AppState.skillSelected.version : ""; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
            Text { text: AppState.skillSelected ? "Aprovadas no Core: " + (AppState.skillSelected.permissions_ok ? "sim" : "não") + "\nFaltando: " + (AppState.skillSelected.missing.length ? AppState.skillSelected.missing.join(", ") : "nada") : ""; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { text: "Aprovar permissões não concede nada à skill: ela só usa capacidades já instaladas e aprovadas."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        FieldLabel { text: "Entradas (JSON de objeto, até 16 KiB) para Simular e Executar" }
        TextArea {
            id: skillInputs
            objectName: "skillInputs"
            Layout.fillWidth: true
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
    }

    // Criar: manifest JSON by hand, or a draft from the LLM plugin when it runs. A draft is never enabled here.
    Section {
        visible: page.part === "criar"
        title: "Criar skill"
        FieldLabel { text: "Manifesto da skill (JSON)" }
        TextArea {
            id: skillManifest
            objectName: "skillManifest"
            Layout.fillWidth: true
            Layout.preferredHeight: 160
            textFormat: TextEdit.PlainText
            wrapMode: TextEdit.Wrap
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            placeholderText: "Cole aqui o manifesto JSON da skill"
            placeholderTextColor: Theme.textMuted
            Accessible.name: "Manifesto da skill em JSON"
            background: Rectangle { color: Theme.bg; radius: Theme.radius; border.width: 1; border.color: Theme.strongOutline }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            GButton { objectName: "skillValidate"; variant: "primary"; text: "Validar"; Accessible.name: "Validar manifest da skill"; enabled: !core.skillsBusy && skillManifest.text.trim().length > 0; onClicked: core.skillValidate(skillManifest.text) }
            GButton { objectName: "skillSaveDraft"; variant: "secondary"; text: "Salvar rascunho"; Accessible.name: "Salvar rascunho da skill"; enabled: !core.skillsBusy && skillManifest.text.trim().length > 0; onClicked: core.skillSaveDraft(skillManifest.text) }
        }
        FieldLabel { text: "Gerar com LLM: descreva o que a skill deve fazer (até 1024 bytes)" }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            GTextField {
                id: skillDescription
                objectName: "skillDescription"
                Layout.fillWidth: true
                maximumLength: 1024
                placeholderText: "Ex.: ler uma nota e salvar um resumo"
                Accessible.name: "Descrição da skill para o LLM"
            }
            GButton { objectName: "skillDraftWithLlm"; variant: "secondary"; text: "Gerar com LLM"; Accessible.name: "Gerar skill com o LLM"; enabled: core.skillLlmAvailable && !core.skillsBusy && skillDescription.text.trim().length > 0; onClicked: core.skillDraftWithLlm(skillDescription.text) }
        }
        Text {
            objectName: "skillLlmUnavailable"
            visible: !core.skillLlmAvailable
            text: "Gerar com LLM indisponível: o plugin llm_engine não está ativo."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Card {
            objectName: "skillDraftOutput"
            visible: !!core.skillDraftOutput.draft_id
            Text { text: "Rascunho " + core.skillDraftOutput.draft_id + " · v" + core.skillDraftOutput.version + " · " + L.skillStateText(core.skillDraftOutput.state) + " · nada foi habilitado"; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { text: "Requisitos: " + ((core.skillDraftOutput.requirements || []).join(", ") || "nenhum"); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { text: "Ambiguidades: " + ((core.skillDraftOutput.ambiguities || []).join("; ") || "nenhuma"); textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { text: "Passos previstos:\n" + ((core.skillDraftOutput.preview || []).map(function (p) { return p.id + " → " + p.call }).join("\n") || "nenhum"); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { visible: !!core.skillDraftOutput.diff; text: "Diferença:\n" + (core.skillDraftOutput.diff || ""); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
        }
    }

    // Importar e exportar: the Core reads only <home>/skill-imports/<name>.gskill and previews it; nothing installs until confirmed.
    Section {
        visible: page.part === "importar"
        title: "Importar e exportar"
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            GTextField {
                id: skillImportName
                objectName: "skillImportName"
                Layout.fillWidth: true
                maximumLength: 64
                placeholderText: "Nome do pacote, sem caminho"
                validator: RegularExpressionValidator { regularExpression: /[A-Za-z0-9._-]{1,64}/ }
                Accessible.name: "Nome do pacote para importar"
            }
            GButton { objectName: "skillImport"; variant: "secondary"; text: "Pré-visualizar"; Accessible.name: "Pré-visualizar importação de skill"; enabled: !core.skillsBusy && skillImportName.acceptableInput; onClicked: core.skillImport(skillImportName.text) }
        }
        Card {
            objectName: "skillImportPreview"
            visible: !!core.skillImportPreview.name
            Text { text: "Pacote " + core.skillImportPreview.name + ": " + core.skillImportPreview.id + " v" + core.skillImportPreview.version; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
            Text { text: "Publisher: " + core.skillImportPreview.publisher + " · não verificado"; textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Publisher " + core.skillImportPreview.publisher + ", não verificado" }
            Text { text: "Permissões exigidas: " + ((core.skillImportPreview.permissions_required || []).join(", ") || "nenhuma") + "\nNovas nesta versão: " + ((core.skillImportPreview.permission_delta || []).join(", ") || "nenhuma"); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { visible: core.skillImportPreview.permissions_escalated === true; text: "Escalada de permissões: esta versão pede mais que a anterior; aprove de novo antes de usar."; textFormat: Text.PlainText; color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { text: "Dependências faltando: " + ((core.skillImportPreview.missing_deps || []).join(", ") || "nenhuma"); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { visible: core.skillImportPreview.duplicate === true; text: "Já existe uma skill com este id no Core."; textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Repeater {
                model: core.skillImportPreview.findings || []
                delegate: Text {
                    required property var modelData
                    objectName: "skillFinding_" + modelData.code
                    text: "Achado: " + core.codeMessage(modelData.code) + (modelData.field ? " (" + modelData.field + ")" : "")
                    textFormat: Text.PlainText; color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
            }
            Text { text: "Importar instala como rascunho e nunca concede permissões. Valide, simule e aprove antes de usar."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            GButton { objectName: "skillImportConfirm"; variant: "primary"; text: "Instalar como rascunho"; Accessible.name: "Instalar como rascunho o pacote " + core.skillImportPreview.name; enabled: !core.skillsBusy && (core.skillImportPreview.findings || []).length === 0; onClicked: core.skillImportConfirm(core.skillImportPreview.name) }
        }
    }

    // Execuções: progress from the Core run; each step that changes state waits for the user's decision here.
    Section {
        visible: page.part === "execucoes"
        title: "Execução e histórico"
        ColumnLayout {
            objectName: "skillRunView"
            visible: !!core.skillCurrentRun.run_id
            Layout.fillWidth: true
            spacing: Theme.space(6)
            Text {
                objectName: "skillRunState"
                text: "Execução " + core.skillCurrentRun.run_id + " · " + core.skillCurrentRun.skill + " · " + L.skillRunText(core.skillCurrentRun.state) + (core.skillCurrentRun.step ? " · passo " + core.skillCurrentRun.step : "")
                textFormat: Text.PlainText; color: core.skillCurrentRun.state === "failed" ? Theme.error : Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                Accessible.name: "Estado da execução: " + text
            }
            Repeater {
                model: core.skillCurrentRun.steps || []
                delegate: ListRow {
                    required property var modelData
                    objectName: "skillStep_" + modelData.id
                    title: "Passo " + modelData.id + " · " + L.skillStepText(modelData.state) + (modelData.code ? " · " + core.codeMessage(modelData.code) : "")
                    GButton { visible: modelData.state === "awaiting_approval"; objectName: "skillDeny_" + modelData.id; text: "Negar passo"; variant: "secondary"; Accessible.name: "Negar o passo " + modelData.id; onClicked: core.skillDecide(core.skillCurrentRun.run_id, modelData.id, "deny") }
                    GButton { visible: modelData.state === "awaiting_approval"; objectName: "skillAuthorize_" + modelData.id; text: "Autorizar passo"; variant: "primary"; Accessible.name: "Autorizar o passo " + modelData.id; onClicked: core.skillDecide(core.skillCurrentRun.run_id, modelData.id, "authorize") }
                }
            }
            Text { objectName: "skillOutputs"; visible: !!core.skillCurrentRun.outputs; text: "Saídas: " + JSON.stringify(core.skillCurrentRun.outputs || {}); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
            GButton { objectName: "skillCancel"; variant: "danger"; text: "Cancelar execução"; Accessible.name: "Cancelar a execução da skill"; enabled: page.runActive; onClicked: core.skillCancel(core.skillCurrentRun.run_id) }
        }
        FieldLabel { text: "Histórico de execuções" }
        Text { objectName: "skillHistoryEmpty"; visible: core.skillHistory.length === 0; text: "Nenhuma execução registrada."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true }
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
}
