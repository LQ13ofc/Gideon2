import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../shell"

// Export or import of the app settings as JSON (ui.exportJson / ui.importJson). Export shows the text to copy. Import checks
// every option: the valid ones apply, a rejected one is named in the toast, and a file that is not a settings file is refused here.
Modal {
    id: dialog
    property string mode: "export"
    property string outcome: ""
    property bool outcomeIsError: false
    width: Math.min(560, (parent ? parent.width : 560) - 32)
    title: mode === "export" ? "Exportar configurações" : "Importar configurações"

    onOpened: {
        outcome = ""
        outcomeIsError = false
        area.text = (mode === "export" && typeof ui !== "undefined" && ui) ? ui.exportJson() : ""
        if (mode === "import") area.forceActiveFocus()
    }

    function runImport() {
        if (typeof ui === "undefined" || !ui) return
        var result = ui.importJson(area.text)
        if (!result.ok) {
            outcome = result.error
            outcomeIsError = true
            return
        }
        var rejected = result.rejected || []
        var text = result.applied + (result.applied === 1 ? " opção aplicada." : " opções aplicadas.")
        if (rejected.length > 0) text += " " + rejected.length + " recusada(s): " + rejected[0].key + " (" + rejected[0].error + ")."
        AppState.toast(text)
        dialog.close()
    }

    Text {
        text: dialog.mode === "export"
            ? "Arquivo JSON com as opções do app. Não contém segredos nem valores guardados pelo Core."
            : "Cole o conteúdo de um arquivo JSON exportado. Cada opção é validada antes de aplicar."
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    ScrollView {
        Layout.fillWidth: true
        Layout.preferredHeight: 220
        TextArea {
            id: area
            objectName: dialog.mode === "export" ? "exportSettingsText" : "importSettingsText"
            readOnly: dialog.mode === "export"
            selectByMouse: true
            wrapMode: TextArea.WrapAnywhere
            font.family: "monospace"
            font.pixelSize: Theme.fontCaption
            color: Theme.text
            placeholderText: dialog.mode === "import" ? "{ \"schemaVersion\": 1, \"values\": { } }" : ""
            placeholderTextColor: Theme.textMuted
            background: Rectangle {
                radius: Theme.radius
                color: Theme.bg
                border.width: 1
                border.color: Theme.strongOutline
            }
        }
    }
    Text {
        visible: dialog.outcome.length > 0
        text: dialog.outcome
        textFormat: Text.PlainText
        color: dialog.outcomeIsError ? Theme.error : Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(8)
        GButton {
            visible: dialog.mode === "export"
            variant: "secondary"
            text: "Selecionar tudo"
            onClicked: { area.selectAll(); area.forceActiveFocus() }
        }
        Item { Layout.fillWidth: true }
        GButton {
            visible: dialog.mode === "import"
            objectName: "importSettingsButton"
            variant: "primary"
            text: "Importar"
            enabled: area.text.trim().length > 0
            onClicked: dialog.runImport()
        }
    }
}
