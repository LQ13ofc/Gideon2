import QtQuick
import QtQuick.Layouts
import "../theme"

// "Como funciona": one 56 px line with a title and a one-line summary; collapsed by default; the body is hidden until opened.
ColumnLayout {
    id: block
    property string title: "Como funciona"
    property string summary: ""
    property bool expanded: false
    default property alias content: body.data
    Layout.fillWidth: true
    spacing: 0

    Rectangle {
        id: head
        Layout.fillWidth: true
        implicitHeight: Math.max(56, Theme.rowHeight)
        radius: Theme.radius
        color: headMouse.containsMouse ? Theme.hover : Theme.surfaceVariant
        border.width: 1
        border.color: Theme.hairline
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: block.title + ": " + block.summary
        Accessible.checked: block.expanded
        Keys.onSpacePressed: block.expanded = !block.expanded
        Keys.onReturnPressed: block.expanded = !block.expanded
        Rectangle {
            anchors.fill: parent; radius: parent.radius; color: "transparent"
            border.width: 2; border.color: Theme.focusRing
            visible: head.activeFocus
        }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.space(14); anchors.rightMargin: Theme.space(14)
            spacing: Theme.space(12)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: block.title
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                }
                Text {
                    visible: block.summary.length > 0
                    text: block.summary
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
            Icon {
                name: block.expanded ? "chevron-down" : "chevron-right"
                size: 18
                color: Theme.textMuted
            }
        }
        MouseArea {
            id: headMouse
            anchors.fill: parent
            hoverEnabled: true
            onClicked: block.expanded = !block.expanded
        }
    }
    ColumnLayout {
        id: body
        visible: block.expanded
        Layout.fillWidth: true
        Layout.topMargin: Theme.space(10)
        spacing: Theme.space(10)
    }
}
