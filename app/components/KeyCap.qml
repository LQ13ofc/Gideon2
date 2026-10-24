import QtQuick
import "../theme"

// A keyboard key label (for example Ctrl+K) in a small monospaced box.
Rectangle {
    id: cap
    property string keys: ""
    implicitWidth: label.implicitWidth + Theme.space(12)
    implicitHeight: Theme.space(22)
    radius: 5
    color: Theme.surface
    border.width: 1
    border.color: Theme.strongOutline
    Text {
        id: label
        anchors.centerIn: parent
        text: cap.keys
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: "monospace"
        font.pixelSize: Theme.fontCaption
    }
}
