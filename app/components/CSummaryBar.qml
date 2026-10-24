import QtQuick
import QtQuick.Layouts
import "../theme"

// Summary line of a sub-tab: one sentence on the left, badges on the right. Only for data the page does not show elsewhere.
Rectangle {
    id: bar
    property string text: ""
    default property alias badges: badgeRow.data
    Layout.fillWidth: true
    implicitHeight: row.implicitHeight + Theme.space(12)
    radius: Theme.radius
    color: Theme.surface
    border.width: 1
    border.color: Theme.hairline
    Accessible.role: Accessible.StaticText
    Accessible.name: text

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: Theme.space(14)
        anchors.rightMargin: Theme.space(10)
        anchors.topMargin: Theme.space(6)
        anchors.bottomMargin: Theme.space(6)
        spacing: Theme.space(12)
        Text {
            text: bar.text
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            font.weight: 600
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        RowLayout {
            id: badgeRow
            spacing: Theme.space(8)
        }
    }
}
