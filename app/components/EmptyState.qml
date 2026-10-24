import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import "../theme"

// Empty state: dashed frame, 32 px icon, one sentence, and the button of the next step. Minimum height 140.
Item {
    id: empty
    property string iconName: "hub"
    property string message: ""
    property string actionText: ""
    signal actionRequested()
    Layout.fillWidth: true
    Layout.minimumHeight: 140
    implicitHeight: Math.max(140, column.implicitHeight + Theme.space(40))

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: Theme.strongOutline
            strokeWidth: 1
            fillColor: "transparent"
            strokeStyle: ShapePath.DashLine
            dashPattern: [4, 3]
            startX: 0.5; startY: 0.5
            PathLine { x: empty.width - 0.5; y: 0.5 }
            PathLine { x: empty.width - 0.5; y: empty.height - 0.5 }
            PathLine { x: 0.5; y: empty.height - 0.5 }
            PathLine { x: 0.5; y: 0.5 }
        }
    }
    ColumnLayout {
        id: column
        anchors.centerIn: parent
        width: Math.min(parent.width - 32, 520)
        spacing: Theme.space(10)
        Icon {
            Layout.alignment: Qt.AlignHCenter
            name: empty.iconName
            size: 32
            color: Theme.textMuted
        }
        Text {
            text: empty.message
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            Layout.alignment: Qt.AlignHCenter
            visible: empty.actionText.length > 0
            text: empty.actionText
            variant: "secondary"
            onClicked: empty.actionRequested()
        }
    }
}
