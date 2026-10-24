import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../shell"
import "BExt.js" as X

// One plugin as a 56 px row (EX-PL-04). The row click selects it for the drawer. The primary action (EX-PL-05) sits on
// the right; the more button (EX-PL-06) opens the advanced actions in place. The capability test is developer-only.
// The four primary buttons all exist and only the one for the current state is visible, so every control keeps its
// objectName for scripts.
ColumnLayout {
    id: row
    property var entry: null
    property var item: null
    property var record: null
    property var ctx: ({})
    property bool selected: false
    property bool expanded: false
    readonly property string pid: entry ? entry.plugin_id : item.plugin_id
    readonly property string semver: entry ? entry.semver : item.semver
    readonly property var act: X.primary(entry, item, ctx)
    readonly property var badge: X.exceptionBadge(entry, item)
    readonly property string line: X.stateLine(entry, item, function (c) { return core.codeMessage(c) })
    readonly property string tone: X.stateTone(entry, item)
    readonly property bool needsApproval: entry !== null && X.isInstalled(entry, item) && entry.permissions_approved !== true
    readonly property var rollbackS: X.rollbackState(record, ctx)
    readonly property var revokeS: X.revokeState(item, ctx)
    readonly property var removeS: X.removeState(record, ctx)

    signal selectRequested()
    signal reviewRequested(var plugin)
    signal revokeRequested(var plugin)
    signal removeRequested(var plugin)

    Layout.fillWidth: true
    spacing: 0

    function toneColor(t) {
        return t === "error" ? Theme.error : t === "warning" ? Theme.warning : t === "success" ? Theme.success
            : t === "info" ? Theme.info : Theme.textMuted
    }

    Rectangle {
        id: head
        Layout.fillWidth: true
        implicitHeight: Math.max(Theme.rowHeight, content.implicitHeight + Theme.space(12))
        radius: Theme.radius
        color: row.selected ? Theme.tint : (mouse.containsMouse ? Theme.hover : "transparent")
        Accessible.role: Accessible.ListItem
        Accessible.name: row.pid + " v" + row.semver

        // Behind the controls: clicks on the text area select the plugin; buttons above keep their own clicks.
        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            onClicked: row.selectRequested()
        }
        RowLayout {
            id: content
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: Theme.space(12)
            anchors.rightMargin: Theme.space(8)
            spacing: Theme.space(10)

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: row.pid + " · v" + row.semver
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Text {
                    objectName: "status_" + row.pid
                    visible: row.item === null && row.line.length > 0
                    text: row.line
                    textFormat: Text.PlainText
                    color: row.toneColor(row.tone)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    objectName: "pluginStatus_" + row.pid
                    visible: row.item !== null
                    text: row.line
                    textFormat: Text.PlainText
                    color: row.toneColor(row.tone)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    objectName: "reapprovalHint_" + row.pid
                    visible: row.needsApproval
                    text: "Aprove novamente as permissões para ativar"
                    textFormat: Text.PlainText
                    color: Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    visible: !act.enabled && act.reason.length > 0
                    text: row.act.reason
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            Badge {
                visible: row.badge !== null
                text: row.badge ? row.badge.text : ""
                tone: row.badge ? row.badge.tone : "neutral"
            }
            RowLayout {
                visible: row.item !== null && row.item.state === "running"
                spacing: Theme.space(6)
                Rectangle {
                    implicitWidth: 8
                    implicitHeight: 8
                    radius: 4
                    color: Theme.success
                }
                Text {
                    text: "Ativo"
                    textFormat: Text.PlainText
                    color: Theme.success
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                }
            }
            GButton {
                objectName: "review_" + row.pid
                visible: row.act.kind === "review"
                text: row.act.text
                variant: "secondary"
                enabled: row.act.enabled
                Accessible.name: "Revisar permissões de " + row.pid
                onClicked: row.reviewRequested({plugin_id: row.pid, semver: row.semver, publisher: row.entry ? row.entry.publisher : "", permissions: row.entry ? row.entry.permissions : [], manifest_sha256: row.entry ? row.entry.manifest_sha256 : ""})
            }
            GButton {
                objectName: "install_" + row.pid
                visible: row.act.kind === "install"
                text: row.act.text
                variant: "primary"
                enabled: row.act.enabled
                Accessible.name: "Instalar pacote verificado de " + row.pid
                onClicked: { if (row.entry) core.installHub(row.entry.plugin_id, row.entry.manifest_sha256) }
            }
            GButton {
                objectName: "enable_" + row.pid
                visible: row.act.kind === "enable"
                text: "Ativar"
                variant: "primary"
                enabled: row.act.kind === "enable" && row.act.enabled
                Accessible.name: "Ativar " + row.pid
                onClicked: core.enablePlugin(row.pid)
            }
            GButton {
                objectName: "disable_" + row.pid
                visible: row.act.kind === "disable"
                text: "Desativar"
                variant: "secondary"
                enabled: row.act.kind === "disable" && row.act.enabled
                Accessible.name: "Desativar " + row.pid
                onClicked: core.disablePlugin(row.pid)
            }
            GButton {
                visible: row.act.kind === "none" && row.act.text.length > 0
                text: row.act.text
                variant: "secondary"
                enabled: false
                Accessible.name: row.act.text + " " + row.pid
            }
            IconButton {
                objectName: "moreActions_" + row.pid
                iconName: "more"
                ToolTip.text: "Mais ações de " + row.pid
                Accessible.checked: row.expanded
                onClicked: row.expanded = !row.expanded
            }
        }
    }

    // More actions (EX-PL-06, advanced): rollback, revoke and remove. Destructive ones confirm in the page.
    ColumnLayout {
        id: strip
        visible: row.expanded
        Layout.fillWidth: true
        Layout.leftMargin: Theme.space(12)
        Layout.rightMargin: Theme.space(12)
        Layout.bottomMargin: Theme.space(8)
        spacing: Theme.space(8)

        Text {
            visible: !Theme.advanced
            text: "Mais ações aparecem com 'Mostrar opções avançadas' em Configurações › Geral."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Flow {
            visible: Theme.advanced
            Layout.fillWidth: true
            spacing: Theme.space(8)
            GButton {
                objectName: "rollback_" + row.pid
                text: "Reverter versão"
                variant: "secondary"
                enabled: row.rollbackS.enabled
                Accessible.name: "Reverter versão de " + row.pid
                onClicked: core.rollbackHub(row.pid)
            }
            GButton {
                objectName: "revoke_" + row.pid
                text: "Revogar permissões"
                variant: "danger"
                enabled: row.revokeS.enabled
                Accessible.name: "Revogar permissões de " + row.pid
                onClicked: row.revokeRequested({plugin_id: row.pid, semver: row.semver})
            }
            GButton {
                objectName: "remove_" + row.pid
                text: "Remover plugin"
                variant: "danger"
                enabled: row.removeS.enabled
                Accessible.name: "Remover " + row.pid
                onClicked: row.removeRequested({plugin_id: row.pid, semver: row.semver})
            }
        }
        Text {
            visible: Theme.advanced && (!row.rollbackS.enabled || !row.revokeS.enabled || !row.removeS.enabled)
            text: [row.rollbackS.reason, row.revokeS.reason, row.removeS.reason].filter(function (r) { return r.length > 0 }).join(" · ")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    // Developer capability test (R-PL-8): only for a running plugin with developer mode on.
    ColumnLayout {
        visible: Theme.devMode && row.item !== null && row.item.state === "running"
        Layout.fillWidth: true
        Layout.leftMargin: Theme.space(12)
        Layout.rightMargin: Theme.space(12)
        Layout.bottomMargin: Theme.space(8)
        spacing: Theme.space(8)

        Text {
            text: "Testes de capacidade (modo desenvolvedor)"
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            font.weight: 600
            Layout.fillWidth: true
        }
        GTextField {
            id: capabilityInput
            objectName: "capabilityInput_" + row.pid
            placeholderText: "Texto para a capability"
            Accessible.name: "Texto para a capability de " + row.pid
            maximumLength: 256
            enabled: core.pluginsAvailable && row.item !== null && row.item.state === "running"
            Layout.fillWidth: true
            Component.onCompleted: text = AppState.draftValue(row.pid, "text")
            onTextEdited: AppState.setDraft(row.pid, "text", text)
        }
        Repeater {
            model: row.item ? row.item.capabilities : []
            delegate: RowLayout {
                required property var modelData
                readonly property string capName: modelData
                Layout.fillWidth: true
                spacing: Theme.space(10)
                GButton {
                    objectName: "invoke_" + capName
                    text: "Invocar"
                    variant: "secondary"
                    Accessible.name: "Invocar " + capName
                    enabled: core.pluginsAvailable && row.item !== null && row.item.state === "running"
                    onClicked: { AppState.setDraft(row.pid, "capability", capName); core.invokeCapability(capName, capabilityInput.text) }
                }
                GButton {
                    objectName: "cancelCapability_" + row.pid
                    text: "Cancelar invocação de teste"
                    variant: "secondary"
                    Accessible.name: "Cancelar invocação de teste de " + capName
                    enabled: core.pluginsAvailable && AppState.draftValue(row.pid, "capability") === capName
                    onClicked: core.cancelCapability(capName)
                }
            }
        }
    }

    Rectangle {
        Layout.fillWidth: true
        implicitHeight: 1
        color: Theme.hairline
    }
}
