import QtQuick
import QtQuick.Layouts
import "../theme"

// One row of a personal-data list: title and detail as plain text, one badge (colour and word), and the row's
// actions at the right. Actions are children and call the Core only through the page's handlers.
Rectangle {
    id: row
    property string title: ""
    property string detail: ""
    property string badgeText: ""
    property string badgeTone: "neutral"
    default property alias trailing: trailingRow.data

    Layout.fillWidth: true
    implicitHeight: Math.max(Theme.rowHeight, content.implicitHeight + Theme.space(24))
    radius: Theme.radius
    color: Theme.surfaceVariant
    border.width: 1
    border.color: Theme.hairline

    RowLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Theme.space(12)
        spacing: Theme.space(12)

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: Theme.space(4)
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(8)
                Text {
                    objectName: "rowTitle"
                    text: row.title
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Badge {
                    visible: row.badgeText.length > 0
                    text: row.badgeText
                    tone: row.badgeTone
                }
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
            Layout.alignment: Qt.AlignVCenter
            spacing: Theme.space(6)
        }
    }
}
