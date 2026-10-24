import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

// Level 1 bar, 56 px: logo and name, the five tabs (icon + name + count), then on the right the Ctrl+K button,
// the state pill and Cancelar (shown only while the Core session can be cancelled). Below 900 px the tabs are icons only.
Rectangle {
    id: bar
    property var tabs: []           // [{id, label, icon, count}]
    property string currentTab: ""
    property bool narrow: false     // below 900 px: tabs are icons only
    property bool compact: false    // below 1100 px: no wordmark, the palette button shows only its icon
    property string stateText: ""
    property string stateTone: "idle"   // idle | working | error | offline
    property bool orbOn: false
    property string orbState: "idle"
    property bool cancellable: false
    signal tabPicked(string id)
    signal paletteRequested()
    signal cancelRequested()

    implicitHeight: 56
    color: Theme.surface
    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width; height: 1
        color: Theme.hairline
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space(16)
        anchors.rightMargin: Theme.space(16)
        spacing: Theme.space(4)

        Image {
            id: logo
            source: Qt.resolvedUrl("../assets/gideon-orb.png")
            sourceSize.width: 28; sourceSize.height: 28
            Layout.preferredWidth: 28; Layout.preferredHeight: 28
            Layout.rightMargin: Theme.space(bar.narrow ? 6 : 10)
            fillMode: Image.PreserveAspectFit
            Accessible.role: Accessible.Graphic
            Accessible.name: "Gideon"
        }
        Text {
            visible: !bar.narrow && !bar.compact
            text: "Gideon"
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 16
            font.weight: Theme.titleWeight
            Layout.rightMargin: Theme.space(8)
        }

        Repeater {
            model: bar.tabs
            delegate: Rectangle {
                id: tabButton
                required property var modelData
                readonly property bool on: modelData.id === bar.currentTab
                objectName: "tab_" + modelData.id
                Layout.preferredHeight: 40
                Layout.preferredWidth: row.implicitWidth + (bar.narrow ? 24 : 28)
                radius: Theme.radius
                color: on ? Theme.tint : (tabMouse.containsMouse ? Theme.hover : "transparent")
                activeFocusOnTab: true
                Accessible.role: Accessible.PageTab
                Accessible.name: modelData.label
                Accessible.checked: on
                ToolTip.visible: bar.narrow && tabMouse.containsMouse
                ToolTip.text: modelData.label
                Keys.onSpacePressed: bar.tabPicked(modelData.id)
                Keys.onReturnPressed: bar.tabPicked(modelData.id)

                Rectangle {
                    anchors.fill: parent; radius: parent.radius; color: "transparent"
                    border.width: 2; border.color: Theme.focusRing
                    visible: tabButton.activeFocus
                }
                RowLayout {
                    id: row
                    anchors.centerIn: parent
                    spacing: Theme.space(8)
                    Icon {
                        name: tabButton.modelData.icon
                        size: 18
                        color: tabButton.on ? Theme.accent : Theme.textMuted
                    }
                    Text {
                        visible: !bar.narrow
                        text: tabButton.modelData.label
                        textFormat: Text.PlainText
                        color: tabButton.on ? Theme.text : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        font.weight: tabButton.on ? 600 : 400
                    }
                    Badge {
                        visible: !bar.narrow && (tabButton.modelData.count || 0) > 0
                        text: String(tabButton.modelData.count || "")
                        tone: "neutral"
                    }
                }
                // The accent underline of the active tab.
                Rectangle {
                    visible: tabButton.on
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left; anchors.right: parent.right
                    height: 3
                    color: Theme.accent
                }
                MouseArea {
                    id: tabMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: bar.tabPicked(tabButton.modelData.id)
                }
            }
        }

        Item { Layout.fillWidth: true }

        // Ctrl+K: the command palette (pages, settings, commands).
        Rectangle {
            id: paletteButton
            objectName: "paletteButton"
            Layout.preferredWidth: bar.narrow || bar.compact ? 36 : 128
            Layout.preferredHeight: 30
            radius: Theme.radius
            color: palMouse.containsMouse ? Theme.hover : Theme.bg
            border.width: 1
            border.color: Theme.strongOutline
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: "Abrir a paleta de comandos, Ctrl+K"
            Keys.onSpacePressed: bar.paletteRequested()
            Keys.onReturnPressed: bar.paletteRequested()
            RowLayout {
                anchors.centerIn: parent
                spacing: Theme.space(8)
                Icon { name: "search"; size: 15; color: Theme.textMuted }
                Text {
                    visible: !bar.narrow && !bar.compact
                    text: "Ctrl+K"
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: "monospace"
                    font.pixelSize: Theme.fontCaption
                }
            }
            MouseArea {
                id: palMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: bar.paletteRequested()
            }
            Rectangle {
                anchors.fill: parent; radius: parent.radius; color: "transparent"
                border.width: 2; border.color: Theme.focusRing
                visible: paletteButton.activeFocus
            }
        }

        // State pill: the Core state in words with a dot. The orb shows only when theme.orb is on.
        Rectangle {
            id: pill
            objectName: "statePill"
            Layout.preferredHeight: 30
            Layout.preferredWidth: pillRow.implicitWidth + 24
            radius: 15
            color: Theme.bg
            border.width: 1
            border.color: Theme.strongOutline
            RowLayout {
                id: pillRow
                anchors.centerIn: parent
                spacing: Theme.space(8)
                Orb {
                    visible: bar.orbOn
                    size: 18
                    mode: bar.orbState
                    Layout.preferredWidth: 18; Layout.preferredHeight: 18
                    objectName: "activityIndicator"
                }
                Rectangle {
                    Layout.preferredWidth: 8; Layout.preferredHeight: 8
                    radius: 4
                    color: bar.stateTone === "error" ? Theme.error
                        : bar.stateTone === "offline" ? Theme.warning
                        : bar.stateTone === "working" ? Theme.accent
                        : Theme.success
                }
                Text {
                    objectName: "aura"
                    text: bar.stateText
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    Accessible.role: Accessible.StaticText
                    Accessible.name: "Estado do Gideon"
                    Accessible.description: text
                }
            }
        }

        // Cancelar: only while a session, a reply or a capture can be cancelled.
        GButton {
            objectName: "cancelButton"
            visible: bar.cancellable
            enabled: bar.cancellable
            text: "Cancelar"
            variant: "secondary"
            implicitHeight: 30
            Layout.leftMargin: Theme.space(4)
            Accessible.name: "Cancelar sessão"
            onClicked: bar.cancelRequested()
        }
    }
}
