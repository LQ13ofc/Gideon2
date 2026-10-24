import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

// Level 2 bar, 44 px: the sub-tabs of the active tab. Text only; the active one has a 2 px underline in the accent.
// Sub-tabs that depend on a plugin are not in the list at all (the page of the tab explains how to get them).
Rectangle {
    id: bar
    property var subs: []           // [{id, label, count}]
    property string current: ""
    signal picked(string id)
    implicitHeight: 44
    color: Theme.bg
    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width; height: 1
        color: Theme.hairline
    }
    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: strip.implicitWidth
        contentHeight: height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded; height: 4 }
        Row {
            id: strip
            height: parent.height
            Repeater {
                model: bar.subs
                delegate: Rectangle {
                    id: sub
                    required property var modelData
                    readonly property bool on: modelData.id === bar.current
                    objectName: "subtab_" + modelData.id
                    width: label.implicitWidth + 36
                    height: strip.height
                    color: "transparent"
                    activeFocusOnTab: true
                    Accessible.role: Accessible.PageTab
                    Accessible.name: modelData.label
                    Accessible.checked: on
                    Keys.onSpacePressed: bar.picked(modelData.id)
                    Keys.onReturnPressed: bar.picked(modelData.id)
                    Rectangle {
                        anchors.fill: parent; anchors.margins: 4; radius: Theme.radius
                        color: "transparent"; border.width: 2; border.color: Theme.focusRing
                        visible: sub.activeFocus
                    }
                    RowLayout {
                        anchors.centerIn: parent
                        spacing: Theme.space(8)
                        Text {
                            id: label
                            text: sub.modelData.label
                            textFormat: Text.PlainText
                            color: sub.on ? Theme.text : Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontBody
                            font.weight: sub.on ? 700 : 400
                        }
                        Badge {
                            visible: (sub.modelData.count || 0) > 0
                            text: String(sub.modelData.count || "")
                            tone: "neutral"
                        }
                    }
                    Rectangle {
                        visible: sub.on
                        anchors.bottom: parent.bottom
                        anchors.left: parent.left; anchors.right: parent.right
                        anchors.leftMargin: 18; anchors.rightMargin: 18
                        height: 2
                        color: Theme.accent
                    }
                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: bar.picked(sub.modelData.id)
                    }
                }
            }
        }
    }
}
