import QtQuick
import "../theme"

// A scope the account holds, shown as a tag. Plain text, not clickable.
Rectangle {
    id: chip
    property string text: ""
    implicitWidth: label.implicitWidth + Theme.space(20)
    implicitHeight: Theme.space(26)
    radius: height / 2
    color: Qt.alpha(Theme.text, 0.06)
    border.width: 1
    border.color: Theme.strongOutline
    Accessible.role: Accessible.StaticText
    Accessible.name: text

    Text {
        id: label
        anchors.centerIn: parent
        text: chip.text
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
    }
}
