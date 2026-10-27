import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../shell"
import "../shell/CfgSettings.js" as CS

// Search of the settings (ui.search), at the top of every Configurações page. A result opens its sub-tab, reveals the row
// and highlights it for a moment. "Somente modificados" limits the results and the rows to the settings changed from default.
ColumnLayout {
    id: search
    Layout.fillWidth: true
    spacing: Theme.space(8)

    readonly property var found: (typeof ui !== "undefined" && ui && field.text.trim().length > 0) ? ui.search(field.text) : []
    readonly property var shown: {
        var out = []
        for (var i = 0; i < found.length && out.length < 6; i++) {
            if (!AppState.onlyModified || AppState.isModified(found[i].key)) out.push(found[i])
        }
        return out
    }

    function pick(item) {
        Window.window.goPage(CS.pageForSubtab(item.subtab))
        AppState.highlightKey = item.key
        clearHighlight.restart()
        field.text = ""
        field.focusReset()
    }

    Timer {
        id: clearHighlight
        interval: 2400
        onTriggered: AppState.highlightKey = ""
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(16)
        SearchField {
            id: field
            objectName: "cfgSearchField"
            Layout.fillWidth: true
            placeholderText: qsTr("Buscar configurações")
            Keys.onReturnPressed: if (search.shown.length > 0) search.pick(search.shown[0])
            Keys.onEnterPressed: if (search.shown.length > 0) search.pick(search.shown[0])
            Keys.onEscapePressed: field.text = ""
            function focusReset() { field.focus = false }
        }
        GCheckbox {
            id: onlyBox
            objectName: "onlyModifiedCheck"
            text: qsTr("Somente modificados")
            checked: AppState.onlyModified
            onToggled: {
                AppState.onlyModified = onlyBox.checked
                onlyBox.checked = Qt.binding(function () { return AppState.onlyModified })
            }
        }
    }

    Repeater {
        model: search.shown
        delegate: Rectangle {
            id: result
            required property var modelData
            readonly property var spec: AppState.uiSpec(modelData.key)
            objectName: "cfgSearchResult_" + modelData.key
            Layout.fillWidth: true
            implicitHeight: resultRow.implicitHeight + Theme.space(16)
            radius: Theme.radius
            color: resultMouse.containsMouse ? Theme.hover : Theme.surfaceVariant
            border.width: 1
            border.color: Theme.hairline
            Accessible.role: Accessible.Button
            Accessible.name: modelData.label + ", " + modelData.subtab
            RowLayout {
                id: resultRow
                anchors.left: parent.left; anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: Theme.space(14); anchors.rightMargin: Theme.space(14)
                spacing: Theme.space(12)
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: result.modelData.label
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        font.weight: 600
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Text {
                        text: result.modelData.subtab + " › " + result.modelData.section
                        textFormat: Text.PlainText
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontCaption
                        Layout.fillWidth: true
                    }
                }
                Badge {
                    text: result.spec && result.spec.level === "advanced" ? qsTr("Avançado") : qsTr("Básico")
                    tone: "neutral"
                }
            }
            MouseArea {
                id: resultMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: search.pick(result.modelData)
            }
        }
    }
    Text {
        visible: field.text.trim().length > 0 && search.shown.length === 0
        text: qsTr("Nenhuma configuração encontrada para “%1”.").arg(field.text.trim())
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
}
