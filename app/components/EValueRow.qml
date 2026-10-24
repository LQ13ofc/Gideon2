import QtQuick
import QtQuick.Layouts
import "../theme"
import "../shell"

// Read-only line: a label, its value, an optional badge (SINTÉTICO, EM MEMÓRIA) and an optional note below.
// advanced: true keeps the line hidden until "Mostrar opções avançadas" is on.
RowLayout {
    id: line
    property string label: ""
    property string value: ""
    property string badge: ""
    property string badgeTone: "neutral"
    property string note: ""
    property bool advanced: false
    visible: !advanced || AppState.uiGet("behavior.advanced", false) === true
    Layout.fillWidth: true
    spacing: Theme.space(12)

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 2
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Text {
                text: line.label
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: line.value.length === 0 && line.badge.length === 0
            }
            Text {
                visible: line.value.length > 0
                text: line.value
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
            }
            Badge {
                visible: line.badge.length > 0
                text: line.badge
                tone: line.badgeTone
            }
            Item {
                Layout.fillWidth: true
                visible: line.value.length > 0 || line.badge.length > 0
            }
        }
        Text {
            visible: line.note.length > 0
            text: line.note
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
