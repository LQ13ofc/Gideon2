import QtQuick
import QtQuick.Layouts
import "../theme"

// One app setting: label, one line of help (13 px), the control on the right, a bar at the left when it differs from the
// default, and "Restaurar padrão". settingKey is the key in the settings object `ui`; without `ui` the row is read-only.
// disabledReason set: the control is shown dimmed with the reason below it ("Indisponível: ...").
Rectangle {
    id: row
    property string label: ""
    property string help: ""
    property string settingKey: ""
    property string disabledReason: ""
    readonly property bool hasKey: settingKey.length > 0
    readonly property bool modified: hasKey && typeof ui !== "undefined" && !!ui && !!ui.modifiedKeys && ui.modifiedKeys.indexOf(settingKey) >= 0
    readonly property bool usable: disabledReason.length === 0
    default property alias control: slot.data
    Layout.fillWidth: true
    implicitHeight: column.implicitHeight + Theme.space(16)
    color: "transparent"

    // Changed-from-default marker: a 3 px bar on the left edge.
    Rectangle {
        visible: row.modified
        x: 0; y: 6
        width: 3; height: row.height - 12
        radius: 2
        color: Theme.accent
    }
    ColumnLayout {
        id: column
        anchors.left: parent.left; anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: Theme.space(16)
        spacing: Theme.space(6)
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(16)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: row.label
                    textFormat: Text.PlainText
                    color: row.usable ? Theme.text : Theme.disabledText
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    visible: row.help.length > 0
                    text: row.help
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
            ColumnLayout {
                id: slot
                Layout.alignment: Qt.AlignVCenter
                enabled: row.usable
                opacity: row.usable ? 1 : 0.45
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(8)
            Text {
                visible: !row.usable
                text: "Indisponível: " + row.disabledReason
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Item { Layout.fillWidth: true; visible: row.usable }
            GButton {
                visible: row.hasKey && row.modified
                variant: "ghost"
                text: "Restaurar padrão"
                onClicked: { if (typeof ui !== "undefined" && ui) ui.reset(row.settingKey) }
            }
        }
    }
}
