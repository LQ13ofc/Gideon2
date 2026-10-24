import QtQuick
import QtQuick.Controls
import "../theme"

// On/off switch with its label at the left. Help text goes in SettingRow, not here.
Switch {
    id: toggle
    implicitHeight: 36
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    Accessible.name: text
    Accessible.role: Accessible.CheckBox
    contentItem: Text {
        text: toggle.text
        textFormat: Text.PlainText
        color: toggle.enabled ? Theme.text : Theme.disabledText
        font: toggle.font
        verticalAlignment: Text.AlignVCenter
        leftPadding: toggle.indicator.width + Theme.space(10)
    }
    indicator: Rectangle {
        implicitWidth: 40
        implicitHeight: 22
        x: toggle.leftPadding
        y: (toggle.height - height) / 2
        radius: height / 2
        color: toggle.checked ? Theme.accent : Theme.surface
        border.width: 1
        border.color: toggle.checked ? Theme.accent : Theme.strongOutline
        opacity: toggle.enabled ? 1 : 0.5
        Rectangle {
            width: 16; height: 16; radius: 8
            y: 3
            x: toggle.checked ? parent.width - width - 3 : 3
            color: toggle.checked ? Theme.onAccent : Theme.textMuted
            Behavior on x { NumberAnimation { duration: Theme.animDuration } }
        }
    }
}
