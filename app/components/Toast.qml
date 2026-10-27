import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

// One transient message (bottom right). Leaves by itself after behavior.toastSeconds; the close button dismisses it.
Rectangle {
    id: toast
    property string text: ""
    property int seconds: Theme.toastSeconds
    signal dismissed()
    width: Math.min(400, parent ? parent.width : 400)
    implicitHeight: row.implicitHeight + Theme.space(20)
    radius: Theme.radiusCard
    color: Theme.surfaceVariant
    border.width: 1
    border.color: Theme.strongOutline
    Accessible.role: Accessible.AlertMessage
    Accessible.name: text

    Timer {
        interval: toast.seconds * 1000
        running: true
        onTriggered: toast.dismissed()
    }
    RowLayout {
        id: row
        anchors.left: parent.left; anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: Theme.space(14); anchors.rightMargin: Theme.space(8)
        spacing: Theme.space(8)
        Text {
            text: toast.text
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        IconButton {
            iconName: "close"
            size: 14
            ToolTip.text: qsTr("Fechar aviso")
            onClicked: toast.dismissed()
        }
    }
}
