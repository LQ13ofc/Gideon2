import QtQuick
import QtQuick.Layouts
import "../theme"

// A box, used only for objects (a plugin, an account, a model, an approval proposal) and dialogs.
Rectangle {
    id: card
    property bool selected: false
    property string title: ""
    default property alias content: body.data
    Layout.fillWidth: true
    implicitHeight: body.implicitHeight + 2 * Theme.space(20)
    radius: Theme.radiusCard
    color: Theme.surfaceVariant
    border.width: selected || card.activeFocus ? 2 : 1
    border.color: selected ? Theme.accent : Theme.strongOutline

    ColumnLayout {
        id: body
        anchors.fill: parent
        anchors.margins: Theme.space(20)
        spacing: Theme.space(12)
        Text {
            visible: card.title.length > 0
            text: card.title
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSection
            font.weight: 600
            Layout.fillWidth: true
        }
    }
}
