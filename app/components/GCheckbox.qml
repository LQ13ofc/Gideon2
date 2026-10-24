import QtQuick
import QtQuick.Controls
import "../theme"

// Checkbox with the label on the right. Name is GCheckbox (never shadows Controls.CheckBox).
CheckBox {
    id: box
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    implicitHeight: 36
    Accessible.name: text
    Accessible.role: Accessible.CheckBox
    contentItem: Text {
        text: box.text
        textFormat: Text.PlainText
        color: box.enabled ? Theme.text : Theme.disabledText
        font: box.font
        wrapMode: Text.WordWrap
        verticalAlignment: Text.AlignVCenter
        leftPadding: box.indicator.width + Theme.space(8)
    }
    indicator: Rectangle {
        implicitWidth: 18
        implicitHeight: 18
        x: box.leftPadding
        y: (box.height - height) / 2
        radius: 4
        color: box.checked ? Theme.accent : Theme.bg
        border.width: 1
        border.color: box.activeFocus ? Theme.focusRing : Theme.strongOutline
        Icon {
            visible: box.checked
            anchors.centerIn: parent
            name: "check"
            size: 12
            color: Theme.onAccent
        }
    }
}
