import QtQuick
import "../theme"

// Clickable state chip (one line). Used for the Hoje status line: each chip leads to the setting that owns it.
Rectangle {
    id: chip
    property string text: ""
    property bool active: false
    signal clicked()
    implicitWidth: label.implicitWidth + Theme.space(24)
    implicitHeight: Theme.space(28)
    radius: height / 2
    color: active ? Theme.tint : (mouse.containsMouse ? Theme.hover : "transparent")
    border.width: 1
    border.color: Theme.strongOutline
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: text
    Keys.onSpacePressed: chip.clicked()
    Keys.onReturnPressed: chip.clicked()

    Text {
        id: label
        anchors.centerIn: parent
        text: chip.text
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        onClicked: chip.clicked()
    }
    Rectangle {
        anchors.fill: parent; radius: parent.radius; color: "transparent"
        border.width: 2; border.color: Theme.focusRing
        visible: chip.activeFocus
    }
}
