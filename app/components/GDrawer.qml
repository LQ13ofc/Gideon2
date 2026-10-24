import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

// Detail panel on the right (360 px). Opens on a selection; Esc or the close button dismisses it.
// Name is GDrawer so it never shadows QtQuick.Controls.Drawer.
Popup {
    id: drawer
    property string title: ""
    default property alias content: body.data
    signal closed()
    parent: Overlay.overlay
    modal: true
    dim: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    width: Math.min(360, (parent ? parent.width : 360))
    height: parent ? parent.height : 600
    x: parent ? parent.width - width : 0
    y: 0
    padding: 0
    onClosed: drawer.closed()
    background: Rectangle {
        color: Theme.surfaceVariant
        border.width: 1
        border.color: Theme.strongOutline
    }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.space(16)
            Text {
                text: drawer.title
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSection
                font.weight: 600
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            IconButton {
                iconName: "close"
                size: 16
                ToolTip.text: "Fechar detalhes"
                onClicked: drawer.close()
            }
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ColumnLayout {
                id: body
                width: drawer.width - 32
                x: 16
                spacing: Theme.space(12)
            }
        }
    }
}
