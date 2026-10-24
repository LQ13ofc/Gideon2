import QtQuick
import QtQuick.Layouts
import "../theme"

// A group on the page: title (16 semibold) over a 1 px hairline; no box. Content goes inside.
ColumnLayout {
    id: section
    property string title: ""
    property string caption: ""
    default property alias content: body.data
    Layout.fillWidth: true
    spacing: Theme.space(8)

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(12)
        Text {
            text: section.title
            visible: section.title.length > 0
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSection
            font.weight: 600
            Layout.fillWidth: true
        }
        Item {
            visible: section.title.length === 0 && section.caption.length > 0
            Layout.fillWidth: true
        }
    }
    Rectangle {
        Layout.fillWidth: true
        implicitHeight: 1
        color: Theme.hairline
    }
    ColumnLayout {
        id: body
        Layout.fillWidth: true
        spacing: Theme.space(12)
        Layout.topMargin: Theme.space(4)
    }
}
