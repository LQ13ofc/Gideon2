import QtQuick
import QtQuick.Controls
import "../theme"

// Drop-down (36 px). Put a FieldLabel above it. Name is Select (ComboBox styled to the theme).
ComboBox {
    id: box
    implicitHeight: Math.max(36, Theme.controlHeight)
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    leftPadding: Theme.space(12)
    rightPadding: Theme.space(32)
    Accessible.name: displayText
    background: Rectangle {
        radius: Theme.radius
        color: Theme.bg
        border.width: box.activeFocus ? 2 : 1
        border.color: box.activeFocus ? Theme.focusRing : Theme.strongOutline
        opacity: box.enabled ? 1 : 0.5
    }
    contentItem: Text {
        leftPadding: 0
        text: box.displayText
        textFormat: Text.PlainText
        color: box.enabled ? Theme.text : Theme.disabledText
        font: box.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Icon {
        x: box.width - width - Theme.space(10)
        y: (box.height - height) / 2
        name: "chevron-down"
        size: 16
        color: Theme.textMuted
    }
    popup.background: Rectangle {
        radius: Theme.radius
        color: Theme.surfaceVariant
        border.width: 1
        border.color: Theme.strongOutline
    }
    delegate: ItemDelegate {
        required property var model
        required property int index
        width: box.width
        highlighted: box.highlightedIndex === index
        contentItem: Text {
            text: box.textRole !== "" ? model[box.textRole] : model.modelData
            textFormat: Text.PlainText
            color: Theme.text
            font: box.font
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle { color: highlighted ? Theme.tint : "transparent" }
    }
}
