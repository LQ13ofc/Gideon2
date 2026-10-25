import QtQuick
import QtQuick.Layouts
import "../theme"

// Outcome of the last personal-data request of one area, as the Core reports it. Shows nothing for success or for
// an area that has not been used. Codes are translated by the bridge (codeMessage); an unknown code gets a generic line.
ColumnLayout {
    id: result
    // The area name on the wire: memory, souls, habits, automations or conversations.
    property string area: ""
    readonly property var last: core.personalReply || ({})
    readonly property bool failed: last.area === area && typeof last.code === "string" && last.code.length > 0 && last.code !== "ok"
    readonly property string text: failed ? (core.codeMessage(last.code) || "Não foi possível concluir a ação.") : ""

    Layout.fillWidth: true
    visible: failed

    Text {
        objectName: "personalResultText"
        text: result.text
        textFormat: Text.PlainText
        color: Theme.error
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Accessible.role: Accessible.AlertMessage
        Accessible.name: text
    }
}
