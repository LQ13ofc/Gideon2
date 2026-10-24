import QtQuick
import QtQuick.Layouts
import "../theme"

// The one notice of a page (info | warn | error). A page never shows more than one: the rest is a badge or text.
Rectangle {
    id: banner
    property string kind: "info"
    property string text: ""
    property string actionText: ""
    readonly property color accentColor: kind === "error" ? Theme.error : kind === "warn" ? Theme.warning : Theme.info
    signal actionRequested()
    Layout.fillWidth: true
    visible: text.length > 0
    implicitHeight: row.implicitHeight + Theme.space(20)
    radius: Theme.radius
    color: Qt.alpha(accentColor, 0.12)
    border.width: 1
    border.color: Qt.alpha(accentColor, 0.45)
    Accessible.role: Accessible.AlertMessage
    Accessible.name: text

    RowLayout {
        id: row
        anchors.left: parent.left; anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: Theme.space(14); anchors.rightMargin: Theme.space(14)
        spacing: Theme.space(12)
        Text {
            text: banner.text
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            visible: banner.actionText.length > 0
            text: banner.actionText
            variant: "ghost"
            onClicked: banner.actionRequested()
        }
    }
}
