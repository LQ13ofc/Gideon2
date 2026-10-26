import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

// Ctrl+K palette. Prefixes: p: pages, s: settings, c: commands. Without a prefix the three are searched together.
// pages and commands are static lists from the window; settings come from settingsProvider(query) (the settings object `ui`).
// activated(item) with item {kind, label, detail, target} is handled by the window.
Popup {
    id: palette
    property var pages: []
    property var commands: []
    property var settingsProvider: null
    signal activated(var item)
    parent: Overlay.overlay
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    width: Math.min(560, (parent ? parent.width : 560) - 32)
    height: Math.min(460, (parent ? parent.height : 460) - 80)
    x: parent ? (parent.width - width) / 2 : 0
    y: parent ? 72 : 72
    padding: Theme.space(16)
    background: Rectangle {
        radius: Theme.radiusCard
        color: Theme.surfaceVariant
        border.width: 1
        border.color: Theme.strongOutline
    }
    onOpened: { query.text = ""; query.forceActiveFocus(); list.currentIndex = 0 }

    // The result list for the current query.
    readonly property var results: {
        var q = query.text
        var kind = ""
        var m = q.match(/^\s*([pscPSC]):\s*(.*)$/)
        if (m) { kind = m[1].toLowerCase(); q = m[2] }
        q = q.trim().toLowerCase()
        var out = []
        function hit(s) { return q.length === 0 || String(s).toLowerCase().indexOf(q) >= 0 }
        if (kind === "" || kind === "p") for (var i = 0; i < pages.length; i++) if (hit(pages[i].label)) out.push({kind: "p", label: pages[i].label, detail: pages[i].detail || qsTr("Página"), target: pages[i].target})
        if (kind === "" || kind === "c") for (var j = 0; j < commands.length; j++) if (hit(commands[j].label)) out.push({kind: "c", label: commands[j].label, detail: qsTr("Comando"), target: commands[j].target})
        if ((kind === "" && q.length >= 2) || kind === "s") {
            var found = settingsProvider ? settingsProvider(q) : []
            for (var k = 0; k < found.length && k < 30; k++) out.push({kind: "s", label: found[k].label, detail: found[k].detail || qsTr("Configuração"), target: found[k].target})
        }
        return out
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space(12)
        SearchField {
            id: query
            objectName: "paletteField"
            Layout.fillWidth: true
            placeholderText: qsTr("Digite para ir a uma página, configuração ou comando")
            Keys.onDownPressed: list.incrementCurrentIndex()
            Keys.onUpPressed: list.decrementCurrentIndex()
            Keys.onReturnPressed: list.activate()
            Keys.onEnterPressed: list.activate()
        }
        Text {
            text: qsTr("Prefixos: p: páginas · s: configurações · c: comandos")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            Layout.fillWidth: true
        }
        ListView {
            id: list
            objectName: "paletteList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: palette.results
            currentIndex: 0
            function activate() {
                if (currentIndex >= 0 && currentIndex < count) {
                    palette.activated(palette.results[currentIndex])
                    palette.close()
                }
            }
            delegate: Rectangle {
                id: entry
                required property var modelData
                required property int index
                objectName: "paletteResult_" + index
                width: list.width
                height: 44
                radius: Theme.radius
                color: index === list.currentIndex ? Theme.tint : (entryMouse.containsMouse ? Theme.hover : "transparent")
                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.label
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space(12); anchors.rightMargin: Theme.space(12)
                    spacing: Theme.space(12)
                    Text {
                        text: entry.modelData.label
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Text {
                        text: entry.modelData.detail
                        textFormat: Text.PlainText
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontCaption
                    }
                }
                MouseArea {
                    id: entryMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onEntered: list.currentIndex = entry.index
                    onClicked: { list.currentIndex = entry.index; list.activate() }
                }
            }
        }
        Text {
            visible: palette.results.length === 0
            text: qsTr("Nada encontrado.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
        }
    }
}
