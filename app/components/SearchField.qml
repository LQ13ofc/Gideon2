import QtQuick
import QtQuick.Controls
import "../theme"

// Search box with a leading magnifier. Typing filters the page or the palette; it never submits anything.
TextField {
    id: field
    implicitHeight: Math.max(36, Theme.controlHeight)
    leftPadding: Theme.space(36)
    rightPadding: Theme.space(12)
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    color: Theme.text
    placeholderText: "Buscar"
    placeholderTextColor: Theme.textMuted
    selectByMouse: true
    Accessible.name: placeholderText
    Accessible.role: Accessible.EditableText
    background: Rectangle {
        radius: Theme.radius
        color: Theme.bg
        border.width: field.activeFocus ? 2 : 1
        border.color: field.activeFocus ? Theme.focusRing : Theme.strongOutline
    }
    Icon {
        x: Theme.space(12)
        anchors.verticalCenter: parent.verticalCenter
        name: "search"
        size: 16
        color: Theme.textMuted
    }
}
