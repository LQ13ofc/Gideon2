import QtQuick
import "../theme"
import "../shell"

// One accent colour as a real circle with its name under it. colorValue "" is the preset's own accent (Padrão do tema).
Item {
    id: dot
    property string colorValue: ""
    property string label: ""
    property bool selected: false
    readonly property string shade: colorValue.length > 0 ? colorValue : String(Theme.presetTokens.accent || "#7693ff")
    signal chosen()

    implicitWidth: 84
    implicitHeight: 62
    activeFocusOnTab: true
    Accessible.role: Accessible.RadioButton
    Accessible.name: label
    Accessible.checked: selected
    Keys.onSpacePressed: dot.chosen()
    Keys.onReturnPressed: dot.chosen()

    Rectangle {
        id: circle
        width: 36; height: 36; radius: 18
        anchors.horizontalCenter: parent.horizontalCenter
        color: dot.shade
        border.width: dot.selected ? 3 : 1
        border.color: dot.selected ? Theme.text : Theme.strongOutline
        Rectangle {
            visible: dot.activeFocus
            anchors.fill: parent
            anchors.margins: -4
            radius: 22
            color: "transparent"
            border.width: 2
            border.color: Theme.focusRing
        }
        Icon {
            visible: dot.selected
            anchors.centerIn: parent
            name: "check"
            size: 16
            color: AppState.bestOn(dot.shade)
        }
    }
    Text {
        anchors.top: circle.bottom
        anchors.topMargin: Theme.space(6)
        anchors.horizontalCenter: parent.horizontalCenter
        text: dot.label
        textFormat: Text.PlainText
        color: dot.selected ? Theme.text : Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        font.weight: dot.selected ? 600 : 400
    }
    MouseArea {
        anchors.fill: parent
        onClicked: dot.chosen()
    }
}
