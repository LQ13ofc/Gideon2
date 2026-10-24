import QtQuick
import QtQuick.Layouts
import "../theme"

// One terminal command: its name, the command text (monospace, wraps, never cut) and a Copiar button.
// The page does the copy and the feedback; this row only shows and reports the click.
RowLayout {
    id: row
    property string label: ""
    property string command: ""
    signal copyRequested()
    Layout.fillWidth: true
    spacing: Theme.space(12)

    Text {
        text: row.label
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontCaption
        font.weight: 600
        Layout.preferredWidth: Theme.space(110)
        Layout.alignment: Qt.AlignVCenter
        elide: Text.ElideRight
    }
    Text {
        text: row.command
        textFormat: Text.PlainText
        color: Theme.text
        font.family: "monospace"
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WrapAtWordBoundaryOrAnywhere
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignVCenter
    }
    GButton {
        text: "Copiar"
        variant: "secondary"
        Layout.alignment: Qt.AlignVCenter
        Accessible.name: "Copiar comando: " + row.label
        onClicked: row.copyRequested()
    }
}
