import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Assistente > Automações: scheduled runs of one enabled Skill. An automation keeps the Skill version the user
// approved; if the Skill changes or stops being enabled, the automation pauses and says why. Each run goes through the
// Skills engine, which applies its own permission and busy checks.
PageFrame {
    id: page
    objectName: "automacoesPage"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "automacoes"

    readonly property var personal: core.personal || ({})
    readonly property var autoBlock: personal.automations || ({})
    readonly property var automations: autoBlock.automations || []
    readonly property bool ready: core.personalAvailable === true && autoBlock.revision !== undefined
    readonly property int revision: ready ? autoBlock.revision : 0
    readonly property var enabledSkills: (core.skillsItems || []).filter(function (i) {
        return i.active === true && i.state === "enabled" && i.deps_ok === true && i.permissions_ok === true
    }).map(function (i) { return {value: i.id, label: i.name + " (" + i.version + ")"} })
    readonly property var repeatOptions: [
        {value: 300000, label: "A cada 5 minutos"}, {value: 3600000, label: "A cada hora"}, {value: 86400000, label: "Todo dia"}
    ]
    readonly property var onceOptions: [
        {value: 300000, label: "Em 5 minutos"}, {value: 3600000, label: "Em 1 hora"}, {value: "tomorrow9", label: "Amanhã às 9h"}
    ]
    readonly property var statusLabels: ({active: "Ativa", paused: "Pausada", done: "Concluída"})
    readonly property var statusTones: ({active: "success", paused: "warning", done: "neutral"})
    readonly property var codeHints: ({
        skill_version_changed: "Pausada: a Skill mudou ou deixou de estar habilitada desde a sua aprovação. Revise em Skills.",
        needs_review: "Pausada: o Skills engine recusou a execução. Revise a Skill antes de retomar."
    })
    property string scheduleKind: "once"
    property string pendingId: ""

    function send(payload) {
        core.personalOp("automations", JSON.stringify(Object.assign({version: 1}, payload)))
    }
    // Entradas: a JSON object, checked before anything is sent. Returns null when invalid.
    function parseInputs(text) {
        var trimmed = text.trim().length > 0 ? text.trim() : "{}"
        try {
            var value = JSON.parse(trimmed)
            return (value !== null && typeof value === "object" && !Array.isArray(value)) ? value : null
        } catch (e) {
            return null
        }
    }
    function when(ms) {
        return ms ? Qt.formatDateTime(new Date(ms), "dd/MM/yyyy HH:mm") : "—"
    }
    function tomorrowNine() {
        var d = new Date()
        d.setDate(d.getDate() + 1)
        d.setHours(9, 0, 0, 0)
        return d.getTime()
    }
    function detailOf(auto) {
        var parts = ["Skill: " + auto.skill_id + " (" + auto.skill_version + ")"]
        if (auto.status !== "done") parts.push("próxima: " + (auto.next_run_ms ? when(auto.next_run_ms) : "—"))
        parts.push("execuções: " + auto.runs)
        if (auto.last_code) {
            var hint = codeHints[auto.last_code]
            parts.push(hint ? hint : (core.codeMessage(auto.last_code) || "último resultado registrado"))
        }
        return parts.join(" · ")
    }

    PageHeader {
        title: "Automações"
        subtitle: "Rotinas que executam uma Skill habilitada no horário combinado."
    }

    Text {
        visible: !page.ready
        text: "Indisponível: o Core não respondeu às automações. Os controles voltam quando a conexão for restabelecida."
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    Section {
        title: "Suas automações"
        caption: "Automações rodam enquanto o Gideon estiver aberto. Horários perdidos não são repetidos em rajada."

        EmptyState {
            visible: page.automations.length === 0
            message: page.enabledSkills.length === 0
                ? "Nenhuma automação. Primeiro habilite uma Skill em Extensões › Skills."
                : "Nenhuma automação ainda. Crie uma abaixo."
        }
        Repeater {
            model: page.automations
            delegate: PItemRow {
                required property var modelData
                title: modelData.name
                detail: page.detailOf(modelData)
                badgeText: page.statusLabels[modelData.status] || ""
                badgeTone: page.statusTones[modelData.status] || "neutral"
                GButton {
                    objectName: "autoRunNow"
                    variant: "secondary"
                    text: "Executar agora"
                    enabled: page.ready && modelData.status === "active"
                    onClicked: page.send({op: "run_now", id: modelData.id})
                }
                GButton {
                    objectName: "autoStatus"
                    variant: "ghost"
                    text: modelData.status === "active" ? "Pausar" : "Retomar"
                    visible: modelData.status !== "done"
                    enabled: page.ready
                    onClicked: page.send({
                        op: "set_status", revision: page.revision, id: modelData.id,
                        status: modelData.status === "active" ? "paused" : "active"
                    })
                }
                GButton {
                    objectName: "autoDelete"
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
        PResult { area: "automations" }
        PRetentionNote {
            Layout.fillWidth: true
        }
    }

    Section {
        title: "Nova automação"
        caption: "Só Skills habilitadas aparecem aqui. A automação usa a versão aprovada agora."

        FieldLabel { text: "Nome" }
        GTextField {
            id: newName
            objectName: "autoName"
            Layout.fillWidth: true
            maximumLength: 60
            placeholderText: "Ex.: Relatório da manhã"
        }
        FieldLabel { text: "Skill" }
        Select {
            id: skillBox
            objectName: "autoSkill"
            Layout.fillWidth: true
            textRole: "label"
            model: page.enabledSkills
            enabled: page.ready && page.enabledSkills.length > 0
        }
        FieldLabel { text: "Entradas (objeto JSON, até 2 KB)" }
        GTextField {
            id: newInputs
            objectName: "autoInputs"
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
        FieldLabel { text: "Quando" }
        Segmented {
            objectName: "autoScheduleKind"
            model: [{id: "once", text: "Uma vez"}, {id: "repeat", text: "Repetir"}]
            currentId: page.scheduleKind
            onActivated: function (id) { page.scheduleKind = id }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(12)
            Select {
                id: whenBox
                objectName: "autoWhen"
                textRole: "label"
                model: page.scheduleKind === "once" ? page.onceOptions : page.repeatOptions
            }
            Item { Layout.fillWidth: true }
            GButton {
                objectName: "autoCreate"
                variant: "primary"
                text: "Criar automação"
                enabled: page.ready && newName.text.trim().length > 0 && skillBox.count > 0
                    && page.parseInputs(newInputs.text) !== null
                onClicked: {
                    var now = Date.now()
                    var skill = page.enabledSkills[skillBox.currentIndex].value
                    var choice = page.scheduleKind === "once" ? page.onceOptions[whenBox.currentIndex] : page.repeatOptions[whenBox.currentIndex]
                    var schedule
                    if (page.scheduleKind === "once") {
                        var at = choice.value === "tomorrow9" ? page.tomorrowNine() : now + choice.value
                        schedule = {kind: "once", at_ms: at}
                    } else {
                        schedule = {kind: "every", start_ms: now + choice.value, every_ms: choice.value}
                    }
                    page.send({
                        op: "create", revision: page.revision, name: newName.text, skill_id: skill,
                        inputs: page.parseInputs(newInputs.text), schedule: schedule
                    })
                    newName.text = ""
                    newInputs.text = ""
                }
            }
        }
        PResult { area: "automations" }
    }

    PConfirm {
        id: deleteConfirm
        message: "A automação será cancelada e apagada. A Skill continua instalada."
        actionText: "Apagar automação"
        onConfirmed: page.send({op: "delete", revision: page.revision, id: page.pendingId})
    }
}
