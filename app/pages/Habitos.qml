import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Extensões > Hábitos: private procedures that run one enabled Skill with fixed inputs. A habit pins the Skill version
// the user approved; if that version changes, the habit refuses to run until it is reviewed. A habit grants no
// permission of its own: every run goes through the Skills engine.
PageFrame {
    id: page
    objectName: "habitosPage"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "habitos"

    readonly property var personal: core.personal || ({})
    readonly property var habitsBlock: personal.habits || ({})
    readonly property var habits: habitsBlock.habits || []
    readonly property bool ready: core.personalAvailable === true && habitsBlock.revision !== undefined
    readonly property int revision: ready ? habitsBlock.revision : 0
    readonly property var enabledSkills: (core.skillsItems || []).filter(function (i) {
        return i.active === true && i.state === "enabled" && i.deps_ok === true && i.permissions_ok === true
    }).map(function (i) { return {value: i.id, label: i.name + " (" + i.version + ")"} })
    readonly property var statusLabels: ({active: "Ativo", paused: "Pausado"})
    property string pendingId: ""
    property string editId: ""

    function send(payload) {
        core.personalOp("habits", JSON.stringify(Object.assign({version: 1}, payload)))
    }
    // Entradas: a JSON object, checked here before anything is sent. Returns null when invalid.
    function parseInputs(text) {
        var trimmed = text.trim().length > 0 ? text.trim() : "{}"
        try {
            var value = JSON.parse(trimmed)
            return (value !== null && typeof value === "object" && !Array.isArray(value)) ? value : null
        } catch (e) {
            return null
        }
    }
    function splitList(text) {
        return text.split(",").map(function (s) { return s.trim() }).filter(function (s) { return s.length > 0 }).slice(0, 4)
    }
    function outcomeText(outcome) {
        if (!outcome) return "Ainda não executado."
        if (outcome.started) return "Última execução: iniciada. O resultado aparece em Skills › Execuções."
        return "Última execução: " + (core.codeMessage(outcome.code) || "não foi possível iniciar.")
    }

    PageHeader {
        title: "Hábitos"
        subtitle: "Procedimentos privados que executam uma Skill habilitada com entradas fixas."
    }

    Text {
        visible: !page.ready
        text: "Indisponível: o Core não respondeu aos hábitos. Os controles voltam quando a conexão for restabelecida."
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    Section {
        title: "Seus hábitos"
        caption: "Cada hábito guarda a versão da Skill que você aprovou e a versão anterior, para voltar atrás."

        EmptyState {
            visible: page.habits.length === 0
            message: page.enabledSkills.length === 0
                ? "Nenhum hábito. Primeiro habilite uma Skill em Extensões › Skills."
                : "Nenhum hábito ainda. Crie um abaixo com uma Skill habilitada."
        }
        Repeater {
            model: page.habits
            delegate: PItemRow {
                required property var modelData
                title: modelData.name
                detail: "Skill: " + modelData.current.skill_id + " · versão aprovada " + modelData.current.skill_version
                    + (modelData.phrases.length > 0 ? " · frases: " + modelData.phrases.join(", ") : "")
                    + "\n" + page.outcomeText(modelData.outcomes.length > 0 ? modelData.outcomes[modelData.outcomes.length - 1] : null)
                badgeText: page.statusLabels[modelData.status] || ""
                badgeTone: modelData.status === "active" ? "success" : "neutral"
                GButton {
                    objectName: "habitRun"
                    variant: "secondary"
                    text: "Executar"
                    enabled: page.ready && modelData.status === "active"
                    onClicked: page.send({op: "run", id: modelData.id})
                }
                GButton {
                    objectName: "habitStatus"
                    variant: "ghost"
                    text: modelData.status === "active" ? "Pausar" : "Retomar"
                    enabled: page.ready
                    onClicked: page.send({
                        op: "set_status", revision: page.revision, id: modelData.id,
                        status: modelData.status === "active" ? "paused" : "active"
                    })
                }
                GButton {
                    objectName: "habitEdit"
                    variant: "ghost"
                    text: "Editar"
                    enabled: page.ready
                    onClicked: {
                        page.editId = modelData.id
                        editName.text = modelData.name
                        editPhrases.text = modelData.phrases.join(", ")
                        editInputs.text = JSON.stringify(modelData.current.inputs)
                        editDialog.open()
                    }
                }
                GButton {
                    objectName: "habitRollback"
                    variant: "ghost"
                    text: "Versão anterior"
                    visible: modelData.previous !== null && modelData.previous !== undefined
                    enabled: page.ready
                    onClicked: page.send({op: "rollback", revision: page.revision, id: modelData.id})
                }
                GButton {
                    objectName: "habitDelete"
                    variant: "danger"
                    text: "Apagar"
                    enabled: page.ready
                    onClicked: {
                        page.pendingId = modelData.id
                        deleteConfirm.open()
                    }
                }
            }
        }
        PResult { area: "habits" }
    }

    Section {
        title: "Novo hábito"
        caption: "Só Skills habilitadas aparecem aqui. O hábito não dá nenhuma permissão nova."

        FieldLabel { text: "Nome" }
        GTextField {
            id: newName
            objectName: "habitName"
            Layout.fillWidth: true
            maximumLength: 60
            placeholderText: "Ex.: Anotar o dia"
        }
        FieldLabel { text: "Frases de disparo (separadas por vírgula, até 4; dizer uma delas exatamente inicia o hábito)" }
        GTextField {
            id: newPhrases
            objectName: "habitPhrases"
            Layout.fillWidth: true
            maximumLength: 300
        }
        FieldLabel { text: "Skill" }
        Select {
            id: skillBox
            objectName: "habitSkill"
            Layout.fillWidth: true
            textRole: "label"
            model: page.enabledSkills
            enabled: page.ready && page.enabledSkills.length > 0
        }
        FieldLabel { text: "Entradas (objeto JSON, até 2 KB)" }
        GTextField {
            id: newInputs
            objectName: "habitInputs"
            Layout.fillWidth: true
            maximumLength: 2048
            placeholderText: "{}"
        }
        Text {
            visible: newInputs.text.trim().length > 0 && page.parseInputs(newInputs.text) === null
            text: "Entradas precisam ser um objeto JSON, por exemplo {\"pasta\": \"diario\"}."
            textFormat: Text.PlainText
            color: Theme.error
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "habitCreate"
            variant: "primary"
            text: "Criar hábito"
            enabled: page.ready && newName.text.trim().length > 0 && skillBox.count > 0
                && page.parseInputs(newInputs.text) !== null
            onClicked: {
                page.send({
                    op: "create", revision: page.revision, name: newName.text, phrases: page.splitList(newPhrases.text),
                    skill_id: page.enabledSkills[skillBox.currentIndex].value, inputs: page.parseInputs(newInputs.text)
                })
                newName.text = ""
                newPhrases.text = ""
                newInputs.text = ""
            }
        }
        PResult { area: "habits" }
    }

    PConfirm {
        id: deleteConfirm
        message: "O hábito será apagado. A Skill continua instalada."
        actionText: "Apagar hábito"
        onConfirmed: page.send({op: "delete", revision: page.revision, id: page.pendingId})
    }

    Modal {
        id: editDialog
        objectName: "habitEditDialog"
        title: "Editar hábito"
        Text {
            text: "Nome"
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
        }
        GTextField {
            id: editName
            objectName: "habitEditName"
            Layout.fillWidth: true
            maximumLength: 60
        }
        Text {
            text: "Frases de disparo (separadas por vírgula)"
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
        }
        GTextField {
            id: editPhrases
            objectName: "habitEditPhrases"
            Layout.fillWidth: true
            maximumLength: 300
        }
        Text {
            text: "Entradas (objeto JSON). Salvar fixa a versão da Skill habilitada agora."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GTextField {
            id: editInputs
            objectName: "habitEditInputs"
            Layout.fillWidth: true
            maximumLength: 2048
        }
        GButton {
            objectName: "habitEditSave"
            variant: "primary"
            text: "Salvar"
            Layout.alignment: Qt.AlignRight
            enabled: page.parseInputs(editInputs.text) !== null
            onClicked: {
                page.send({
                    op: "edit", revision: page.revision, id: page.editId, name: editName.text,
                    phrases: page.splitList(editPhrases.text), inputs: page.parseInputs(editInputs.text)
                })
                editDialog.close()
            }
        }
    }
}
