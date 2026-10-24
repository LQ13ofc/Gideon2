import QtQuick
import QtQuick.Layouts
import "../theme"
import "Reveal.js" as Reveal

// One 56 px list row: optional leading icon, title, one line of detail, and actions on the right.
// Clicking the text area emits clicked; the trailing actions keep their own clicks.
// The row is also reachable by Tab; Enter and Space activate it the same way a click does, and it shows a focus ring.
// Taking keyboard focus scrolls the row into view of its page (Reveal.js), so a row below the fold is never focused out of sight.
Rectangle {
    id: row
    property string title: ""
    property string detail: ""
    property string iconName: ""
    property bool selected: false
    property bool dim: false
    default property alias trailing: trailingRow.data
    signal clicked()
    Layout.fillWidth: true
    implicitHeight: Math.max(Theme.rowHeight, contentRow.implicitHeight + Theme.space(12))
    radius: Theme.radius
    color: selected ? Theme.tint : (mouse.containsMouse ? Theme.hover : "transparent")
    opacity: dim ? 0.6 : 1
    activeFocusOnTab: true
    onActiveFocusChanged: if (activeFocus) Reveal.revealItem(row)
    Accessible.role: Accessible.ListItem
    Accessible.name: row.title
    Keys.onReturnPressed: function (event) { row.clicked(); event.accepted = true }
    Keys.onEnterPressed: function (event) { row.clicked(); event.accepted = true }
    Keys.onSpacePressed: function (event) { row.clicked(); event.accepted = true }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        onClicked: row.clicked()
    }
    Rectangle {
        anchors.fill: parent
        radius: row.radius
        color: "transparent"
        border.width: 2
        border.color: Theme.focusRing
        visible: row.activeFocus
    }
    RowLayout {
        id: contentRow
        anchors.left: parent.left; anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: Theme.space(12); anchors.rightMargin: Theme.space(12)
        spacing: Theme.space(12)
        Icon {
            visible: row.iconName !== ""
            name: row.iconName
            size: 20
            color: Theme.textMuted
            Layout.alignment: Qt.AlignVCenter
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                text: row.title
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.weight: 600
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Text {
                visible: row.detail.length > 0
                text: row.detail
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        RowLayout {
            id: trailingRow
            spacing: Theme.space(8)
            Layout.alignment: Qt.AlignVCenter
        }
    }
}
