import QtQuick
import "../theme"
import "../shell"

// One preset of the gallery: a mini preview drawn from the preset's own tokens (ui.presetTokens) and its name.
Item {
    id: tile
    property string presetId: ""
    property string presetLabel: ""
    property bool selected: false
    readonly property var tokens: (typeof ui !== "undefined" && ui) ? ui.presetTokens(presetId) : ({})
    signal chosen(string id)

    function tok(name, fallback) { return tokens && tokens[name] ? tokens[name] : fallback }

    implicitWidth: 168
    implicitHeight: 124
    activeFocusOnTab: true
    Accessible.role: Accessible.RadioButton
    Accessible.name: presetLabel
    Accessible.checked: selected
    Keys.onSpacePressed: tile.chosen(tile.presetId)
    Keys.onReturnPressed: tile.chosen(tile.presetId)

    Rectangle {
        id: frame
        anchors.fill: parent
        radius: Theme.radius
        color: pick.containsMouse ? Theme.hover : "transparent"
        border.width: tile.selected || tile.activeFocus ? 2 : 1
        border.color: tile.selected ? Theme.accent : (tile.activeFocus ? Theme.focusRing : Theme.hairline)

        Rectangle {
            id: thumb
            anchors.left: parent.left; anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Theme.space(8)
            height: 66
            radius: 6
            color: tile.tok("bg", "#121417")
            border.width: 1
            border.color: Qt.alpha(tile.tok("text", "#e6e9ee"), 0.2)

            Rectangle {
                x: 8; y: 8
                width: thumb.width - 16
                height: thumb.height - 16
                radius: 4
                color: tile.tok("surface", "#1b1f24")
                Column {
                    x: 8; y: 8
                    spacing: 4
                    Rectangle { width: 54; height: 4; radius: 2; color: tile.tok("accent", "#7aa2f7") }
                    Rectangle { width: 40; height: 4; radius: 2; color: tile.tok("text", "#e6e9ee") }
                    Rectangle { width: 26; height: 4; radius: 2; color: tile.tok("textMuted", "#a7b0bc") }
                }
                Row {
                    anchors.left: parent.left; anchors.leftMargin: 8
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                    spacing: 4
                    Repeater {
                        model: [tile.tok("accent", "#7aa2f7"), tile.tok("success", "#6bcb8b"), tile.tok("warning", "#e8b04b"), tile.tok("error", "#f07178"), tile.tok("info", "#6cb6ff")]
                        delegate: Rectangle {
                            required property var modelData
                            width: 6; height: 6; radius: 3
                            color: modelData
                        }
                    }
                }
            }
            Icon {
                visible: tile.selected
                anchors.top: parent.top; anchors.right: parent.right
                anchors.margins: 4
                name: "check"
                size: 14
                color: tile.tok("accent", "#7aa2f7")
            }
        }
        Text {
            anchors.left: parent.left; anchors.right: parent.right
            anchors.top: thumb.bottom
            anchors.leftMargin: Theme.space(10); anchors.rightMargin: Theme.space(10)
            anchors.topMargin: Theme.space(8)
            text: tile.presetLabel
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            font.weight: tile.selected ? 600 : 400
            elide: Text.ElideRight
        }
    }
    MouseArea {
        id: pick
        anchors.fill: parent
        hoverEnabled: true
        onClicked: tile.chosen(tile.presetId)
    }
}
