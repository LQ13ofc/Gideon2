import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/EventLabels.js" as E

// Permissões > Auditoria (docs/ui-spec/30-permissoes.md §7): the Core's recent events, newest first, with no content.
// Phrases, origins and results come from the shared event table (EventLabels.js, spec 50 §4 and 30 §7.6).
PageFrame {
    id: page
    objectName: "page_perm_auditoria"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "perm_auditoria"

    property string filter: "Todos"
    readonly property var filters: ["Todos", "Plugin", "Skill", "Conexão", "Comando"]

    // Rows of the table: only the kinds the table marks for Auditoria (P), plus unknown kinds under "Todos".
    readonly property var rows: {
        var events = core.events.slice().sort(function (a, b) { return b.sequence - a.sequence })
        var out = []
        for (var i = 0; i < events.length; i++) {
            var e = events[i]
            if (!E.inAudit(e.kind)) continue
            var origin = E.origin(e.kind)
            if (page.filter !== "Todos" && origin !== page.filter) continue
            out.push({number: e.sequence, clock: E.clockText(e.at_ms), text: E.phrase(e.kind) || E.UNKNOWN_PHRASE,
                      origin: origin, result: E.result(e.kind), kind: e.kind})
        }
        return out
    }

    function resultTone(result) {
        switch (result) {
        case "Concluído": return "success"
        case "Falhou": case "Negado": return "error"
        case "Recusado": return "warning"
        default: return "neutral"
        }
    }
    function originTone(origin) { return origin === "Plugin" ? "info" : "neutral" }

    PageHeader {
        title: "Auditoria"
        subtitle: "Eventos recentes do Core, sem conteúdo. Até 64, desde o início desta sessão do Core."
    }
    Banner {
        objectName: "auditBanner"
        kind: "error"
        text: core.connected ? "" : "Core desconectado. Mostrando o último estado conhecido."
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(8)
        Repeater {
            model: page.filters
            delegate: Chip {
                required property string modelData
                objectName: "auditFilter_" + modelData
                text: modelData
                active: page.filter === modelData
                onClicked: page.filter = modelData
            }
        }
        Item { Layout.fillWidth: true }
        Text {
            objectName: "auditCount"
            text: page.rows.length + (page.rows.length === 1 ? " evento" : " eventos")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp
        }
    }

    // Table: header, then rows of 44 px with a hairline between them.
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 0
        visible: page.rows.length > 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            Layout.leftMargin: Theme.space(12)
            Layout.rightMargin: Theme.space(12)
            spacing: Theme.space(12)
            Text { text: "Nº"; Layout.preferredWidth: 72; Layout.minimumWidth: 72; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; font.weight: 600 }
            Text { text: "Hora"; Layout.preferredWidth: 88; Layout.minimumWidth: 88; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; font.weight: 600 }
            Text { text: "Tipo"; Layout.fillWidth: true; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; font.weight: 600 }
            Text { text: "Origem"; Layout.preferredWidth: 150; Layout.minimumWidth: 150; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; font.weight: 600 }
            Text { text: "Resultado"; Layout.preferredWidth: 130; Layout.minimumWidth: 130; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; font.weight: 600 }
        }

        Repeater {
            model: page.rows
            delegate: Rectangle {
                id: auditRow
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: Math.max(44, cells.implicitHeight + Theme.space(12))
                color: auditHover.containsMouse ? Theme.hover : "transparent"
                objectName: "audit_" + modelData.number
                Accessible.role: Accessible.Row
                Accessible.name: "#" + modelData.number + " " + modelData.text

                MouseArea { id: auditHover; anchors.fill: parent; hoverEnabled: true }
                RowLayout {
                    id: cells
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: Theme.space(12); anchors.rightMargin: Theme.space(12)
                    spacing: Theme.space(12)
                    Text {
                        text: "#" + auditRow.modelData.number
                        textFormat: Text.PlainText
                        color: Theme.textMuted
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                        Layout.preferredWidth: 72; Layout.minimumWidth: 72
                    }
                    Text {
                        text: auditRow.modelData.clock
                        textFormat: Text.PlainText
                        color: Theme.textMuted
                        font.family: "monospace"; font.pixelSize: Theme.fontHelp
                        Layout.preferredWidth: 88; Layout.minimumWidth: 88
                    }
                    Text {
                        text: auditRow.modelData.text
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Item {
                        Layout.preferredWidth: 150; Layout.minimumWidth: 150
                        Layout.preferredHeight: originBadge.implicitHeight
                        Badge { id: originBadge; text: auditRow.modelData.origin; tone: page.originTone(auditRow.modelData.origin) }
                    }
                    Item {
                        Layout.preferredWidth: 130; Layout.minimumWidth: 130
                        Layout.preferredHeight: resultText.visible ? resultText.implicitHeight : resultBadge.implicitHeight
                        Badge {
                            id: resultBadge
                            visible: auditRow.modelData.result !== "—"
                            text: auditRow.modelData.result
                            tone: page.resultTone(auditRow.modelData.result)
                        }
                        Text {
                            id: resultText
                            visible: auditRow.modelData.result === "—"
                            text: "—"
                            textFormat: Text.PlainText
                            color: Theme.textMuted
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                        }
                    }
                }
                Rectangle {
                    anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                    height: 1
                    color: Theme.hairline
                }
            }
        }
    }

    EmptyState {
        objectName: "auditEmpty"
        visible: page.rows.length === 0
        iconName: "shield"
        message: page.filter === "Todos" ? "Nenhum evento nesta sessão do Core." : "Nenhum evento de " + page.filter + " nesta sessão."
    }

    // B9: the log is <diretório do Core>/audit.log (src/storage.rs). Copiar escreve o caminho na área de transferência.
    readonly property string logPath: core.coreRootPath.length > 0 ? core.coreRootPath + "/audit.log" : ""

    Collapsible {
        objectName: "auditAdvanced"
        visible: Theme.advanced
        title: "Detalhes técnicos (Avançado)"
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(12)
            Text {
                objectName: "auditLogPath"
                text: "Caminho do log: " + (page.logPath.length > 0 ? page.logPath : "não informado")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: "monospace"; font.pixelSize: Theme.fontHelp
                wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
            }
            GButton {
                objectName: "copyAuditLogPath"
                variant: "secondary"
                text: "Copiar"
                enabled: page.logPath.length > 0
                Accessible.name: "Copiar o caminho do log de auditoria"
                onClicked: {
                    if (core.copyText(page.logPath)) AppState.toast("Caminho do log copiado.")
                    else AppState.toast("Não foi possível copiar o caminho do log.")
                }
            }
        }
    }
}
