import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Extensões > Percepção e ação (needs a perception plugin). Parts: Privacidade (mic and camera indicators, always visible),
// Plugins (one card per plugin, read-only test buttons, SINTÉTICO label) and Último resultado. Nothing here touches hardware.
PageFrame {
    id: page
    objectName: "perceptionPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "percepcao" && core.perceptionAvailable

    property string part: "privacidade"
    function badgeTone(state) {
        switch (state) {
        case "running": return "success"
        case "starting": return "info"
        case "failed": case "quarantined": return "error"
        default: return "neutral"
        }
    }

    PageHeader {
        title: "Percepção e ação"
        subtitle: "Testes de sensores e ações simulados; nada age no seu computador."
    }
    Banner {
        kind: "warn"
        text: "Backends simulados: nenhum hardware pessoal é acessado nesta build."
    }
    Segmented {
        model: [{id: "privacidade", text: "Privacidade"}, {id: "plugins", text: "Plugins"}, {id: "resultado", text: "Último resultado"}]
        currentId: page.part
        onActivated: function (id) { page.part = id }
    }

    Section {
        visible: page.part === "privacidade"
        title: "Indicadores"
        objectName: "privacyCard"
        Text { objectName: "micIndicator"; text: "Microfone · indicador: " + core.perceptionMicIndicator; textFormat: Text.PlainText; color: core.perceptionMicIndicator === "ligado" ? Theme.warning : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Indicador do microfone: " + core.perceptionMicIndicator }
        Text { objectName: "cameraIndicator"; text: "Câmera · indicador: " + core.perceptionCameraIndicator; textFormat: Text.PlainText; color: core.perceptionCameraIndicator === "ligado" ? Theme.warning : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Indicador da câmera: " + core.perceptionCameraIndicator }
    }

    Section {
        visible: page.part === "plugins"
        title: "Plugins de percepção"
        Repeater {
            model: core.perceptionPlugins
            delegate: Card {
                id: perceptionCard
                required property var modelData
                objectName: "perceptionCard_" + modelData.plugin_id
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(12)
                    Text {
                        objectName: "perceptionTitle_" + perceptionCard.modelData.plugin_id
                        text: perceptionCard.modelData.plugin_id + " " + perceptionCard.modelData.semver
                        textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                    }
                    Badge {
                        objectName: "perceptionState_" + perceptionCard.modelData.plugin_id
                        text: L.perceptionStateText(perceptionCard.modelData.state)
                        tone: page.badgeTone(perceptionCard.modelData.state)
                    }
                }
                Text { objectName: "perceptionError_" + perceptionCard.modelData.plugin_id; visible: !!perceptionCard.modelData.last_error; text: "Último erro: " + perceptionCard.modelData.last_error; textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Badge {
                    objectName: "perceptionBadge_" + perceptionCard.modelData.plugin_id
                    text: perceptionCard.modelData.plugin_id === "display_manipulate" ? "UNSUPPORTED" : "SINTÉTICO — sem hardware real"
                    tone: perceptionCard.modelData.plugin_id === "display_manipulate" ? "warning" : "success"
                }
                Text { text: "Permissão exigida: " + (perceptionCard.modelData.permissions.map(function (p) { return core.permissionLabel(p) }).join(", ") || "nenhuma") + (perceptionCard.modelData.approved ? " · concedida" : " · não concedida"); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { text: "Backend real: não suportado / pendente de validação humana"; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.space(8)
                    Repeater {
                        model: L.perceptionActions[perceptionCard.modelData.plugin_id] || []
                        delegate: GButton {
                            required property var modelData
                            objectName: "perception_" + modelData.capability
                            variant: "secondary"
                            text: modelData.label
                            Accessible.name: modelData.label + " " + modelData.capability
                            enabled: core.connected && perceptionCard.modelData.state === "running" && !core.perceptionBusy
                            onClicked: core.perceptionInvoke(modelData.capability, "{}")
                        }
                    }
                }
            }
        }
    }

    Section {
        visible: page.part === "resultado"
        title: "Último resultado"
        Text { objectName: "perceptionResult"; text: core.perceptionResult; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Resultado da percepção: " + text }
    }
}
