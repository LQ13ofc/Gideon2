import QtQuick
import QtQuick.Layouts
import "../theme"

// One-of-N choice shown as a joined control. model: [{id, text}]. Emits activated(id) when the user picks one.
Rectangle {
    id: seg
    property var model: []
    property string currentId: ""
    property int currentIndex: {
        for (var i = 0; i < model.length; i++) if (model[i].id === currentId) return i
        return -1
    }
    signal activated(string id)
    implicitHeight: 36
    implicitWidth: row.implicitWidth + 4
    radius: Theme.radius
    color: Theme.bg
    border.width: 1
    border.color: Theme.strongOutline
    Accessible.role: Accessible.PageTabList

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: 2
        spacing: 2
        Repeater {
            model: seg.model
            delegate: Rectangle {
                id: segment
                required property var modelData
                required property int index
                readonly property bool on: modelData.id === seg.currentId
                implicitWidth: label.implicitWidth + Theme.space(24)
                implicitHeight: 30
                Layout.fillHeight: true
                radius: Theme.radius - 2
                color: on ? Theme.accent : (picker.containsMouse ? Theme.hover : "transparent")
                activeFocusOnTab: true
                Accessible.role: Accessible.PageTab
                Accessible.name: modelData.text
                Accessible.checked: on
                Keys.onSpacePressed: seg.activated(modelData.id)
                Keys.onReturnPressed: seg.activated(modelData.id)
                Rectangle {
                    anchors.fill: parent; radius: parent.radius; color: "transparent"
                    border.width: 2; border.color: Theme.focusRing
                    visible: segment.activeFocus
                }
                Text {
                    id: label
                    anchors.centerIn: parent
                    text: segment.modelData.text
                    textFormat: Text.PlainText
                    color: segment.on ? Theme.onAccent : Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: segment.on ? 600 : 400
                }
                MouseArea {
                    id: picker
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: seg.activated(segment.modelData.id)
                }
            }
        }
    }
}
