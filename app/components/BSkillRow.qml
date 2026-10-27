import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../shell"
import "../shell/Labels.js" as L
import "BExt.js" as X

// One skill as a 56 px row (Minhas). Click selects it for the drawer. The row keeps only the state's primary action
// (Executar, Habilitar, Aprovar or Simular); every other action lives in the drawer. Nothing here grants a permission.
ColumnLayout {
    id: row
    property var skill: ({})
    property var ctx: ({})
    property bool selected: false
    readonly property var act: X.skillPrimary(skill, ctx)
    readonly property string key: skill.id + "_" + skill.version

    signal selectRequested()

    Layout.fillWidth: true
    spacing: 0

    Rectangle {
        id: head
        Layout.fillWidth: true
        implicitHeight: Math.max(Theme.rowHeight, content.implicitHeight + Theme.space(12))
        radius: Theme.radius
        color: row.selected ? Theme.tint : (mouse.containsMouse ? Theme.hover : "transparent")
        Accessible.role: Accessible.ListItem
        Accessible.name: row.skill.name + " · " + row.skill.id + " v" + row.skill.version

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
                    objectName: "skillTitle_" + row.key
                    text: row.skill.name + " · " + row.skill.id + " v" + row.skill.version
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Text {
                    objectName: "skillState_" + row.key
                    text: qsTr("Estado: %1 · origem: %2").arg(L.skillStateText(row.skill.state)).arg(L.skillSourceText(row.skill.source)) + (row.skill.active ? qsTr(" · versão ativa") : "")
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    objectName: "skillDeps_" + row.key
                    visible: !row.skill.deps_ok || !row.skill.permissions_ok
                    text: qsTr("Dependências: %1 · permissões: %2").arg(row.skill.deps_ok ? qsTr("ok") : qsTr("faltando: %1").arg((row.skill.missing || []).join(", "))).arg(row.skill.permissions_ok ? qsTr("aprovadas") : qsTr("pendentes"))
                    textFormat: Text.PlainText
                    color: Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    visible: !row.act.enabled && row.act.reason.length > 0
                    text: row.act.reason
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
            GButton {
                objectName: "skillRun_" + row.skill.id
                visible: row.act.kind === "run"
                text: qsTr("Executar")
                variant: "primary"
                enabled: row.act.kind === "run" && row.act.enabled
                Accessible.name: qsTr("Executar %1").arg(row.skill.id)
                onClicked: core.skillRun(row.skill.id, row.ctx.inputs)
            }
            GButton {
                objectName: "skillDisable_" + row.skill.id
                visible: row.skill.state === "enabled"
                text: qsTr("Desabilitar")
                variant: "secondary"
                enabled: row.skill.state === "enabled" && !row.ctx.busy
                Accessible.name: qsTr("Desabilitar %1").arg(row.skill.id)
                onClicked: core.skillDisable(row.skill.id)
            }
            GButton {
                objectName: "skillEnable_" + row.skill.id
                visible: row.act.kind === "enable"
                text: qsTr("Habilitar")
                variant: "primary"
                enabled: row.act.kind === "enable" && row.act.enabled
                Accessible.name: qsTr("Habilitar %1").arg(row.skill.id)
                onClicked: core.skillEnable(row.skill.id)
            }
            GButton {
                objectName: "skillApprove_" + row.key
                visible: row.act.kind === "approve"
                text: qsTr("Aprovar")
                variant: "primary"
                enabled: row.act.kind === "approve" && row.act.enabled
                Accessible.name: qsTr("Aprovar %1 v%2").arg(row.skill.id).arg(row.skill.version)
                onClicked: core.skillApprove(row.skill.id, row.skill.version)
            }
            GButton {
                objectName: "skillDryRun_" + row.key
                visible: row.act.kind === "dry"
                text: qsTr("Simular")
                variant: "secondary"
                enabled: row.act.kind === "dry" && row.act.enabled
                Accessible.name: qsTr("Simular %1").arg(row.skill.id)
                onClicked: core.skillDryRun(row.skill.id, row.skill.version, row.ctx.inputs)
            }
        }
    }
    Rectangle {
        Layout.fillWidth: true
        implicitHeight: 1
        color: Theme.hairline
    }
}
