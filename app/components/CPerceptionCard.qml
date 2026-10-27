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
    readonly property var actions: L.perceptionActions()[pid] || []
    // The backend names are Portuguese texts kept as keys (QT_TR_NOOP) and translated when the card reads them (qsTr).
    readonly property var backends: ({
        "screen_observe": QT_TR_NOOP("portal XDG (captura de tela)"),
        "computer_control": QT_TR_NOOP("AT-SPI (árvore) e RemoteDesktop (teclado)"),
        "audio_advanced": QT_TR_NOOP("PipeWire (wpctl, pw-dump)"),
        "mic_advanced": QT_TR_NOOP("PipeWire (ganho e medidor, nada guardado)"),
        "camera_gesture": QT_TR_NOOP("v4l2 (quadro sob acesso ligado)"),
        "display_manipulate": QT_TR_NOOP("KScreen (kscreen-doctor)"),
        "shortcut_global": QT_TR_NOOP("portal GlobalShortcuts, com KGlobalAccel de reserva")
    })

    function stateTone(state) {
        switch (state) {
        case "running": return "success"
        case "starting": return "info"
        case "failed": case "quarantined": return "error"
        default: return "neutral"
        }
    }
    function backendText() {
        var key = card.backends[card.pid]
        return qsTr("Backend: %1").arg(key ? qsTr(key) : qsTr("não informado"))
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
        text: card.backendText()
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
        text: qsTr("Último erro: %1").arg(card.plugin.last_error || "")
        textFormat: Text.PlainText
        color: Theme.error
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        text: qsTr("Permissão exigida: %1").arg((card.plugin.permissions || []).map(function (p) { return core.permissionLabel(p) }).join(", ") || qsTr("nenhuma")) + (card.plugin.approved ? qsTr(" · concedida") : qsTr(" · não concedida"))
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
        text: qsTr("Restaurar escala e brilho")
        enabled: core.connected && card.running && !core.perceptionBusy
        Accessible.name: qsTr("Restaurar a escala e o brilho da tela para os valores anteriores às mudanças")
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
                Accessible.name: qsTr("%1 %2").arg(modelData.label).arg(modelData.capability)
                enabled: core.connected && card.running && !core.perceptionBusy
                onClicked: core.perceptionInvoke(modelData.capability, "{}")
            }
        }
    }
    Text {
        visible: Theme.devMode && !card.running
        text: qsTr("Indisponível: plugin não está em execução.")
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        Layout.fillWidth: true
    }
}
