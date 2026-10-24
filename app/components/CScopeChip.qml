import QtQuick
import QtQuick.Controls
import "../theme"

// A scope the account holds, shown as a tag. When revocable, a click or Enter opens one menu item: "Revogar este escopo".
// The page asks for the confirmation; the chip only reports the request.
Rectangle {
    id: chip
    property string text: ""
    property bool revocable: false
    signal revokeRequested()
    function openMenu() { if (chip.revocable) scopeMenu.open() }
    implicitWidth: label.implicitWidth + Theme.space(20)
    implicitHeight: Theme.space(26)
    radius: height / 2
    color: Qt.alpha(Theme.text, 0.06)
    border.width: chip.activeFocus ? 2 : 1
    border.color: chip.activeFocus ? Theme.focusRing : Theme.strongOutline
    activeFocusOnTab: chip.revocable
    Accessible.role: chip.revocable ? Accessible.Button : Accessible.StaticText
    Accessible.name: chip.revocable ? chip.text + ", escopo concedido: revogar" : chip.text
    Accessible.onPressAction: chip.openMenu()
    Keys.onReturnPressed: chip.openMenu()
    Keys.onSpacePressed: chip.openMenu()
    MouseArea {
        anchors.fill: parent
        enabled: chip.revocable
        cursorShape: Qt.PointingHandCursor
        onClicked: chip.openMenu()
    }
    Menu {
        id: scopeMenu
        y: chip.height
        MenuItem {
            objectName: "scopeRevokeItem"
            text: "Revogar este escopo"
            onTriggered: chip.revokeRequested()
        }
    }

    Text {
        id: label
        anchors.centerIn: parent
        text: chip.text
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
    }
}
