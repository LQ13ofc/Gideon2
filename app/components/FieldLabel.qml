import QtQuick
import QtQuick.Layouts
import "../theme"

// Small label above a field or a value group (13 px, muted).
Text {
    textFormat: Text.PlainText
    color: Theme.textMuted
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontHelp
    wrapMode: Text.WordWrap
    Layout.fillWidth: true
}
