import QtQuick
import QtQuick.Layouts
import "../theme"

// Page title (24 bold), one short subtitle (14, at most one line) and the primary action on the right.
// Pass buttons as children: they sit at the right of the title row.
ColumnLayout {
    id: header
    property string title: ""
    property string subtitle: ""
    default property alias actions: actionRow.data
    Layout.fillWidth: true
    Layout.topMargin: Theme.space(20)
    spacing: Theme.space(4)

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(12)
        Text {
            objectName: "pageTitle"
            text: header.title
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontTitle
            font.weight: Theme.titleWeight
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        RowLayout {
            id: actionRow
            spacing: Theme.space(8)
        }
    }
    Text {
        objectName: "pageSubtitle"
        visible: header.subtitle.length > 0
        text: header.subtitle
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        elide: Text.ElideRight
        Layout.fillWidth: true
    }
}
