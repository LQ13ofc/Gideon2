import QtQuick
import QtQuick.Controls
import "../theme"

// Button with four variants: primary (the one action of a page), secondary, danger (always behind a confirmation),
// ghost (inline text action). Minimum height 36 px. Name is GButton so it never shadows QtQuick.Controls.Button.
Button {
    id: control
    property string variant: "secondary"
    property string iconName: ""
    readonly property color labelColor: variant === "primary" ? Theme.onAccent
        : variant === "danger" ? Theme.error
        : variant === "ghost" ? Theme.accent
        : Theme.text

    implicitHeight: Math.max(36, Theme.controlHeight)
    leftPadding: Theme.space(14)
    rightPadding: Theme.space(14)
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    Accessible.name: text
    Accessible.role: Accessible.Button

    background: Rectangle {
        radius: Theme.radius
        color: {
            if (control.variant === "primary") return control.down ? Qt.darker(Theme.primary, 1.2) : (control.hovered ? Qt.lighter(Theme.primary, 1.1) : Theme.primary)
            if (control.down) return Theme.pressed
            return control.hovered ? Theme.hover : "transparent"
        }
        border.width: control.variant === "primary" || control.variant === "ghost" ? 0 : 1
        border.color: control.variant === "danger" ? Theme.error : Theme.strongOutline
        opacity: control.enabled ? 1 : 0.45
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: "transparent"
            border.width: 2
            border.color: Theme.focusRing
            visible: control.activeFocus
        }
    }
    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight
        Row {
            id: row
            anchors.centerIn: parent
            spacing: Theme.space(8)
            Icon {
                visible: control.iconName !== ""
                name: control.iconName
                size: 16
                color: control.labelColor
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                visible: control.text !== ""
                text: control.text
                textFormat: Text.PlainText
                color: control.enabled ? control.labelColor : Theme.disabledText
                font: control.font
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
