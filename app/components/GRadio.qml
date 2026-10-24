import QtQuick
import QtQuick.Controls
import "../theme"

// Radio button with the label on the right. Name is GRadio (never shadows Controls.RadioButton).
RadioButton {
    id: radio
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    implicitHeight: 36
    Accessible.name: text
    contentItem: Text {
        text: radio.text
        textFormat: Text.PlainText
        color: radio.enabled ? Theme.text : Theme.disabledText
        font: radio.font
        verticalAlignment: Text.AlignVCenter
        leftPadding: radio.indicator.width + Theme.space(8)
    }
    indicator: Rectangle {
        implicitWidth: 18
        implicitHeight: 18
        x: radio.leftPadding
        y: (radio.height - height) / 2
        radius: 9
        color: Theme.bg
        border.width: radio.checked ? 2 : 1
        border.color: radio.checked ? Theme.accent : Theme.strongOutline
        Rectangle {
            visible: radio.checked
            anchors.centerIn: parent
            width: 8; height: 8; radius: 4
            color: Theme.accent
        }
    }
}
