import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../shell"
import "BExt.js" as X

// Details of the selected plugin (EX-PL-07): an inline drawer on the right, 360 px wide, next to the list.
// Read-only except the primary action (same rule as the row). Destructive actions stay in the row's more menu.
Rectangle {
    id: panel
    property var entry: null
    property var item: null
    property var ctx: ({})
    readonly property string pid: entry ? entry.plugin_id : (item ? item.plugin_id : "")
    readonly property string semver: entry ? entry.semver : (item ? item.semver : "")
    readonly property var act: X.primary(entry, item, ctx)
    readonly property var badge: X.exceptionBadge(entry, item)
    readonly property string line: X.stateLine(entry, item, function (c) { return core.codeMessage(c) })
    readonly property var caps: item ? item.capabilities : (entry ? entry.capabilities : [])

    signal reviewRequested(var plugin)
    signal closeRequested()

    Layout.preferredWidth: 360
    Layout.minimumWidth: 300
    Layout.alignment: Qt.AlignTop
    implicitHeight: body.implicitHeight + 2 * Theme.space(20)
    radius: Theme.radiusCard
    color: Theme.surfaceVariant
    border.width: 1
    border.color: Theme.strongOutline

    function toneColor(t) {
        return t === "error" ? Theme.error : t === "warning" ? Theme.warning : t === "success" ? Theme.success
            : t === "info" ? Theme.info : Theme.textMuted
    }
    function permissionText(p) {
        var label = core.permissionLabel(p)
        return label === p ? "permissão sem rótulo: " + p : label
    }
    function runPrimary() {
        if (!panel.act.enabled) return
        if (panel.act.kind === "review") panel.reviewRequested({plugin_id: panel.pid, semver: panel.semver, publisher: panel.entry ? panel.entry.publisher : "", permissions: panel.entry ? panel.entry.permissions : [], manifest_sha256: panel.entry ? panel.entry.manifest_sha256 : ""})
        else if (panel.act.kind === "install" && panel.entry) core.installHub(panel.entry.plugin_id, panel.entry.manifest_sha256)
        else if (panel.act.kind === "enable") core.enablePlugin(panel.pid)
        else if (panel.act.kind === "disable") core.disablePlugin(panel.pid)
    }

    Accessible.role: Accessible.Pane
    Accessible.name: "Detalhe de " + panel.pid

    ColumnLayout {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.space(20)
        spacing: Theme.space(10)

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(8)
            Text {
                text: panel.pid
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSection
                font.weight: 600
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Badge {
                visible: panel.badge !== null
                text: panel.badge ? panel.badge.text : ""
                tone: panel.badge ? panel.badge.tone : "neutral"
            }
            IconButton {
                iconName: "close"
                size: 16
                ToolTip.text: "Fechar detalhe"
                onClicked: panel.closeRequested()
            }
        }
        Text {
            text: "v" + panel.semver + " · publisher " + (panel.entry ? panel.entry.publisher : "—") + " · não verificado"
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            visible: panel.entry !== null
            text: "Publisher: " + (panel.entry ? panel.entry.publisher : "") + " (não autenticado)"
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            text: "Versão: " + panel.semver
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.hairline }

        Text {
            visible: panel.entry !== null
            text: panel.entry && panel.entry.permissions_approved === true ? "Permissões aprovadas para este manifesto:" : "Permissões declaradas (não aprovadas):"
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            font.weight: 600
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Repeater {
            model: panel.entry ? panel.entry.permissions : []
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Theme.space(8)
                Rectangle {
                    implicitWidth: 6
                    implicitHeight: 6
                    radius: 3
                    color: Theme.accent
                    Layout.alignment: Qt.AlignTop
                    Layout.topMargin: 6
                }
                Text {
                    text: panel.permissionText(modelData)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }
        Text {
            visible: panel.entry !== null && (panel.entry.permissions || []).length === 0
            text: "nenhuma"
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
        }
        GButton {
            variant: "ghost"
            text: "Ver em Permissões"
            Accessible.name: "Ver em Permissões"
            onClicked: { if (Window.window && Window.window.goPage) Window.window.goPage("perm_concessoes") }
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.hairline }

        Text {
            objectName: "pluginDetailState"
            text: "Estado técnico: " + panel.line
            textFormat: Text.PlainText
            color: panel.toneColor(X.stateTone(panel.entry, panel.item))
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            font.weight: 600
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            visible: panel.item !== null && panel.item.last_error !== undefined && panel.item.last_error !== null && String(panel.item.last_error).length > 0
            text: "Último erro: " + (panel.item ? (core.codeMessage(panel.item.last_error) || "erro") : "")
            textFormat: Text.PlainText
            color: Theme.error
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            visible: panel.entry !== null && panel.entry.status === "incompatible"
            text: panel.entry ? "Incompatível: " + X.reasonText(panel.entry.reason) : ""
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        ColumnLayout {
            visible: Theme.advanced
            Layout.fillWidth: true
            spacing: Theme.space(6)
            Text {
                text: "Hash do manifest (SHA-256): " + (panel.entry ? panel.entry.manifest_sha256 : "—")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
            }
            Text {
                text: "Capacidades: " + ((panel.caps || []).length ? panel.caps.join(", ") : "nenhuma")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                visible: panel.entry !== null
                text: "Dependências: " + (panel.entry && (panel.entry.dependencies || []).length ? panel.entry.dependencies.join(", ") : "nenhuma")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                visible: panel.entry !== null
                text: "Licença: " + (panel.entry ? panel.entry.license : "") + " · Tamanho do pacote: " + (panel.entry ? panel.entry.download_size : "") + " bytes"
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        GButton {
            objectName: "drawerPrimaryAction"
            visible: panel.act.kind !== "none" || panel.act.text.length > 0
            Layout.fillWidth: true
            text: panel.act.text
            variant: panel.act.kind === "install" || panel.act.kind === "enable" ? "primary" : "secondary"
            enabled: panel.act.enabled
            Accessible.name: panel.act.text + " " + panel.pid
            onClicked: panel.runPrimary()
        }
        Text {
            visible: !panel.act.enabled && panel.act.reason.length > 0
            text: panel.act.reason
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
