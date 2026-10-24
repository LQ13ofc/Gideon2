import QtQuick
import "../theme"

// Colour and word together (never colour alone). tone: success | warning | error | info | neutral.
Rectangle {
    id: badge
    property string text: ""
    property string tone: "neutral"
    readonly property color toneColor: tone === "success" ? Theme.success
        : tone === "warning" ? Theme.warning
        : tone === "error" ? Theme.error
        : tone === "info" ? Theme.info
        : Theme.textMuted
    implicitWidth: label.implicitWidth + Theme.space(20)
    implicitHeight: Theme.space(22)
    radius: height / 2
    color: Qt.alpha(toneColor, 0.16)
    border.width: 1
    border.color: Qt.alpha(toneColor, 0.5)
    Accessible.role: Accessible.StaticText
    Accessible.name: text

    Text {
        id: label
        anchors.centerIn: parent
        text: badge.text
        textFormat: Text.PlainText
        color: badge.toneColor
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontCaption
        font.weight: 600
    }
}
