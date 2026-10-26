import QtQuick
import QtQuick.Layouts
import "../theme"
import "../shell/Labels.js" as L

// One perception plugin (C4): its state, the permission it asks for and, in developer mode only, its read-only test buttons.
// Each card names the real backend of its plugin (WP-17). display_manipulate changes scale and brightness and can put them back.
Card {
    id: card
    property var plugin: ({})
    readonly property string pid: plugin.plugin_id || ""
    readonly property bool running: plugin.state === "running"
    readonly property bool isDisplay: pid === "display_manipulate"
    readonly property var actions: L.perceptionActions[pid] || []
    readonly property var backends: ({
        "screen_observe": "portal XDG (captura de tela)",
        "computer_control": "AT-SPI (árvore) e RemoteDesktop (teclado)",
        "audio_advanced": "PipeWire (wpctl, pw-dump)",
        "mic_advanced": "PipeWire (ganho e medidor, nada guardado)",
        "camera_gesture": "v4l2 (quadro sob acesso ligado)",
        "display_manipulate": "KScreen (kscreen-doctor)",
        "shortcut_global": "portal GlobalShortcuts, com KGlobalAccel de reserva"
    })

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
    Text {
        objectName: "perceptionBackend_" + card.pid
        text: "Backend: " + (card.backends[card.pid] || "não informado")
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
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
    // display_manipulate: the change is real and reversible; restore puts back what the worker saw before the first change.
    GButton {
        objectName: "displayRestoreButton"
        visible: card.isDisplay
        variant: "secondary"
        text: "Restaurar escala e brilho"
        enabled: core.connected && card.running && !core.perceptionBusy
        Accessible.name: "Restaurar a escala e o brilho da tela para os valores anteriores às mudanças"
        onClicked: core.perceptionInvoke("display_manipulate.restore", "{}")
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
