import QtQuick
import QtQuick.Controls
import "../theme"

// Text field (36 px). Put a FieldLabel above it: the label is never placeholder text.
// Name is GTextField so it never shadows QtQuick.Controls.TextField.
TextField {
    id: field
    implicitHeight: Math.max(36, Theme.controlHeight)
    leftPadding: Theme.space(12)
    rightPadding: Theme.space(12)
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    color: Theme.text
    placeholderTextColor: Theme.textMuted
    selectByMouse: true
    Accessible.name: placeholderText
    background: Rectangle {
        radius: Theme.radius
        color: Theme.bg
        border.width: field.activeFocus ? 2 : 1
        border.color: field.activeFocus ? Theme.focusRing : Theme.strongOutline
        opacity: field.enabled ? 1 : 0.5
    }
}
