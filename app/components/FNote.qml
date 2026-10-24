import QtQuick
import QtQuick.Layouts
import "../theme"

// One line of help or note under a value (13 px; 12 px when small: metadata only). tone: muted | text | warn | error.
// The words carry the meaning; the colour only reinforces them.
Text {
    id: note
    property string tone: "muted"
    property bool small: false
    textFormat: Text.PlainText
    color: tone === "warn" ? Theme.warning : tone === "error" ? Theme.error : tone === "text" ? Theme.text : Theme.textMuted
    font.family: Theme.fontFamily
    font.pixelSize: small ? Theme.fontCaption : Theme.fontHelp
    wrapMode: Text.WordWrap
    Layout.fillWidth: true
}
