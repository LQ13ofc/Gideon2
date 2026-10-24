import QtQuick
import QtQuick.Layouts
import "../theme"
import "../shell"
import "../shell/CfgSettings.js" as CS

// The quiet line at the foot of a Configurações page: how many advanced options are hidden. Shows nothing when they are on.
Text {
    id: note
    property string subtab: ""
    readonly property int hiddenCount: AppState.advancedHidden(subtab)
    visible: hiddenCount > 0
    text: CS.advancedHiddenText(hiddenCount)
    textFormat: Text.PlainText
    color: Theme.textMuted
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontCaption
    wrapMode: Text.WordWrap
    Layout.fillWidth: true
}
