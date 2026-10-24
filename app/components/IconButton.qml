import QtQuick
import QtQuick.Controls
import "../theme"

// Icon-only button (36 px target). The tooltip is its accessible name.
AbstractButton {
    id: control
    property string iconName: ""
    property int size: 18
    implicitWidth: 36
    implicitHeight: 36
    hoverEnabled: true
    text: ""
    Accessible.name: ToolTip.text
    Accessible.role: Accessible.Button
    ToolTip.visible: hovered && ToolTip.text.length > 0
    ToolTip.delay: 500

    background: Rectangle {
        radius: Theme.radius
        color: control.down ? Theme.pressed : (control.hovered ? Theme.hover : "transparent")
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: "transparent"
            border.width: 2
            border.color: Theme.focusRing
            visible: control.activeFocus
        }
    }
    contentItem: Icon {
        anchors.centerIn: parent
        name: control.iconName
        size: control.size
        color: control.enabled ? Theme.text : Theme.disabledText
    }
}
