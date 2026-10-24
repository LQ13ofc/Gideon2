import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/ActivityRows.js" as A

// Assistente > Atividade: one timeline of what the assistant did, with no content (no transcript, arguments, answers
// or skill output). Rows come from the Core events (with their time), the skill history and the last connection call.
// While the Core is away the last list received stays on screen with a notice.
PageFrame {
    id: page
    objectName: "page_atividade"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "atividade"

    property string filter: "all"
    property var cachedEvents: []
    property var cachedSkills: []
    property var cachedCall: ({})

    // Rows that have no Core time keep the order in which this page first saw them (newest first).
    QtObject {
        id: seen
        property var order: ({})
    }
    function seenOrder(key) {
        if (seen.order[key] === undefined) seen.order[key] = Object.keys(seen.order).length + 1
        return seen.order[key]
    }

    readonly property var rows: {
        var untimed = []
        for (var i = 0; i < page.cachedSkills.length; i++) {
            var sk = A.skillRow(page.cachedSkills[i])
            sk.seen = seenOrder(sk.key)
            untimed.push(sk)
        }
        if (page.cachedCall && page.cachedCall.operation) {
            var cl = A.callRow(page.cachedCall)
            cl.seen = seenOrder(cl.key)
            untimed.push(cl)
        }
        untimed.sort(function (a, b) { return b.seen - a.seen })
        return untimed.concat(A.eventRows(page.cachedEvents)).filter(function (r) { return A.matches(r, page.filter) })
    }

    function remember() {
        if (!core.connected) return
        cachedEvents = core.events
        cachedSkills = core.skillHistory
        cachedCall = core.connectionLastCall
    }
    Component.onCompleted: remember()
    Connections {
        target: core
        function onEventsChanged() { page.remember() }
        function onSkillsChanged() { page.remember() }
        function onConnectionsChanged() { page.remember() }
    }

    PageHeader {
        title: "Atividade"
        subtitle: "O que aconteceu nesta sessão, sem conteúdo sensível."
    }
    Banner {
        objectName: "activityStale"
        kind: "warn"
        visible: !core.connected
        text: "Core desconectado · mostrando a última leitura"
    }

    // Count of the rows of this filter, and the filter itself (one segmented control, neutral count).
    Flow {
        Layout.fillWidth: true
        spacing: Theme.space(12)
        Text {
            objectName: "activityCount"
            topPadding: 9  // centred on the 36 px filter next to it
            text: page.rows.length === 0 ? "Nada ainda nesta sessão" : page.rows.length === 1 ? "1 evento nesta sessão" : page.rows.length + " eventos nesta sessão"
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            font.weight: 600
        }
        Segmented {
            objectName: "activityFilter"
            model: [{id: "all", text: "Tudo"}, {id: "cmd", text: "Comandos"}, {id: "skill", text: "Skills"}, {id: "agent", text: "Agente"}, {id: "err", text: "Erros"}]
            currentId: page.filter
            onActivated: function (id) { page.filter = id }
        }
    }

    ColumnLayout {
        objectName: "activityList"
        Layout.fillWidth: true
        spacing: 0
        Accessible.role: Accessible.List
        Accessible.name: "Linha do tempo da atividade"
        visible: page.rows.length > 0

        Repeater {
            model: page.rows
            delegate: Rectangle {
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: Theme.space(40)
                color: "transparent"
                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.text + (modelData.badge ? ", " + modelData.badge.text : "")
                RowLayout {
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: Theme.space(8); anchors.rightMargin: Theme.space(8)
                    spacing: Theme.space(16)
                    Text {
                        visible: modelData.time.length > 0
                        text: modelData.time
                        textFormat: Text.PlainText
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontHelp
                        Layout.preferredWidth: Theme.space(64)
                    }
                    Text {
                        text: modelData.text
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Badge {
                        visible: modelData.badge !== null
                        text: modelData.badge ? modelData.badge.text : ""
                        tone: modelData.badge ? modelData.badge.tone : "neutral"
                    }
                }
                Rectangle {
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 1
                    color: Theme.hairline
                }
            }
        }
    }

    EmptyState {
        objectName: "activityEmpty"
        visible: page.rows.length === 0
        iconName: "activity"
        message: page.filter === "all" ? "Nada ainda nesta sessão." : "Nada neste filtro."
        actionText: "Ir para Hoje"
        onActionRequested: Window.window.goPage("hoje")
    }
}
