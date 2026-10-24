import QtQuick
import QtQuick.Layouts
import "../theme"
import "../shell/Labels.js" as L

// One perception plugin (C4): its state, the permission it asks for and, in developer mode only, its read-only test buttons.
// display_manipulate is UNSUPPORTED and says so; the synthetic label of the other plugins sits in the page banner.
Card {
    id: card
    property var plugin: ({})
    readonly property string pid: plugin.plugin_id || ""
    readonly property bool running: plugin.state === "running"
    readonly property bool isDisplay: pid === "display_manipulate"
    readonly property var actions: L.perceptionActions[pid] || []

    function stateTone(state) {
        switch (state) {
        case "running": return "success"
        case "starting": return "info"
        case "failed": case "quarantined": return "error"
        default: return "neutral"
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(12)
        Text {
            objectName: "perceptionTitle_" + card.pid
            text: card.pid + " " + (card.plugin.semver || "")
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSection
            font.weight: 600
            wrapMode: Text.WrapAnywhere
            Layout.fillWidth: true
        }
        Badge {
            objectName: "perceptionState_" + card.pid
            text: L.perceptionStateText(card.plugin.state)
            tone: card.stateTone(card.plugin.state)
        }
    }
    // Only the exception carries its own label: display_manipulate. Synthetic plugins are labelled once, in the page banner.
    Badge {
        objectName: "perceptionBadge_" + card.pid
        visible: card.isDisplay
        text: card.isDisplay ? "UNSUPPORTED" : "SINTÉTICO — sem hardware real"
        tone: "warning"
    }
    Text {
        objectName: "perceptionError_" + card.pid
        visible: !!card.plugin.last_error
        text: "Último erro: " + (card.plugin.last_error || "")
        textFormat: Text.PlainText
        color: Theme.error
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        text: "Permissão exigida: " + ((card.plugin.permissions || []).map(function (p) { return core.permissionLabel(p) }).join(", ") || "nenhuma") + (card.plugin.approved ? " · concedida" : " · não concedida")
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: card.isDisplay
        text: "Nenhuma ação de manipulação existe; produto não é bloqueado."
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    // Test buttons are read-only and belong to developer mode (Desenvolvimento); the Core still refuses anything else.
    Flow {
        Layout.fillWidth: true
        spacing: Theme.space(8)
        visible: Theme.devMode && card.actions.length > 0
        Repeater {
            model: card.actions
            delegate: GButton {
                required property var modelData
                objectName: "perception_" + modelData.capability
                variant: "secondary"
                text: modelData.label
                Accessible.name: modelData.label + " " + modelData.capability
                enabled: core.connected && card.running && !core.perceptionBusy
                onClicked: core.perceptionInvoke(modelData.capability, "{}")
            }
        }
    }
    Text {
        visible: Theme.devMode && !card.running
        text: "Indisponível: plugin não está em execução."
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        Layout.fillWidth: true
    }
}
