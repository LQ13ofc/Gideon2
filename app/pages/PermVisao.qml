import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/PermRows.js" as P

// Permissões > Visão geral (docs/ui-spec/30-permissoes.md §5): what waits for the user's decision now, and what is
// already granted. The decisions open the shared dialogs (DPermDialogs); nothing is decided on this page directly.
PageFrame {
    id: page
    objectName: "page_perm_visao"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "perm_visao"

    function makeCtx() {
        return {hub: core.hubEntries, conns: core.connectionsItems, providers: core.connectionsProviders,
                publisherVerified: core.hubPublisherVerified,
                labelOf: function (p) { return core.permissionLabel(p) }}
    }
    readonly property var queue: P.queueRows(makeCtx())
    readonly property var active: P.activeRows(makeCtx())

    // Enabled state of a queue row and the reason when it is closed (30 §5.4, §5.8).
    function queueEnabled(row) {
        if (row.kind === "plugin") return core.hubApprovalAvailable
        return core.connectionsAvailable && !core.connectionsBusy
    }
    function queueTip(row) {
        if (!core.connected) return "Core desconectado."
        if (queueEnabled(row)) return ""
        if (row.kind === "plugin" && core.sessionId.length > 0) return "Indisponível durante a sessão de voz."
        return "Indisponível agora."
    }
    function openItem(row) {
        if (!row || !queueEnabled(row)) return
        if (row.kind === "plugin") dialogs.reviewPlugin(row.ref)
        else if (row.kind === "consent") dialogs.consent(row.ref)
        else dialogs.trustTool(row.ref, row.tool)
    }
    function openList(filter, key) {
        AppState.permFilter = filter
        AppState.permFocusKey = key
        Window.window.goPage("perm_concessoes")
    }
    function rowActionName(row) {
        if (row.kind === "plugin") return "Revisar permissões de " + row.ref.plugin_id
        if (row.kind === "consent") return "Revisar escopos de " + row.ref.label
        return "Revisar ferramenta " + row.tool
    }

    DPermDialogs { id: dialogs }

    PageHeader {
        title: "Visão geral"
        subtitle: "O que precisa da sua decisão agora e o que já está concedido."
        GButton {
            objectName: "reviewNextButton"
            variant: "primary"
            text: "Revisar próxima"
            enabled: page.queue.length > 0 && page.queueEnabled(page.queue[0])
            Accessible.description: page.queue.length === 0 ? "Nada pendente." : page.queueTip(page.queue[0])
            onClicked: page.openItem(page.queue[0])
        }
    }
    Banner {
        objectName: "permBanner"
        kind: core.connected ? "warn" : "error"
        text: !core.connected ? "Core desconectado. Mostrando o último estado conhecido; nada pode ser alterado."
            : core.sessionId.length > 0 ? "Sessão de voz ativa: mudanças em plugins bloqueadas." : ""
    }

    // Pendências: the decisions waiting now, in the order of 30 §5.4.
    Section {
        title: page.queue.length > 0 ? "Pendências · " + page.queue.length + " aguardando sua decisão" : "Pendências"
        Repeater {
            model: page.queue
            delegate: Rectangle {
                id: queueRow
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: Math.max(Theme.rowHeight, queueContent.implicitHeight + Theme.space(12))
                radius: Theme.radius
                color: queueHover.containsMouse ? Theme.hover : "transparent"
                objectName: "queue_" + modelData.key.replace(/:/g, "_")
                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.item

                MouseArea { id: queueHover; anchors.fill: parent; hoverEnabled: true }
                RowLayout {
                    id: queueContent
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: Theme.space(12); anchors.rightMargin: Theme.space(12)
                    spacing: Theme.space(12)
                    Badge {
                        text: queueRow.modelData.origin
                        tone: queueRow.modelData.originTone
                        Layout.alignment: Qt.AlignVCenter
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            text: queueRow.modelData.item
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Text {
                            text: queueRow.modelData.sub
                            textFormat: Text.PlainText
                            color: queueRow.modelData.kind === "plugin" && queueRow.modelData.sub.indexOf("Atualização") >= 0 ? Theme.warning : Theme.textMuted
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                    GButton {
                        objectName: "queueReview_" + queueRow.modelData.key.replace(/:/g, "_")
                        text: "Revisar"
                        variant: "secondary"
                        enabled: page.queueEnabled(queueRow.modelData)
                        Accessible.name: page.rowActionName(queueRow.modelData)
                        Accessible.description: enabled ? "" : page.queueTip(queueRow.modelData)
                        Layout.alignment: Qt.AlignVCenter
                        onClicked: page.openItem(queueRow.modelData)
                    }
                }
            }
        }
        EmptyState {
            visible: page.queue.length === 0
            iconName: "shield"
            message: "Nada pendente.\nPlugins, skills e contas aparecem aqui quando precisarem da sua decisão."
        }
    }

    // Concessões ativas: what is already granted (30 §5.6, items 15-18).
    Section {
        title: "Concessões ativas"
        Repeater {
            model: page.active
            delegate: Rectangle {
                id: activeRow
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: Math.max(Theme.rowHeight - Theme.space(16), activeContent.implicitHeight + Theme.space(12))
                radius: Theme.radius
                color: activeHover.containsMouse ? Theme.hover : "transparent"
                objectName: "active_" + modelData.key.replace(/:/g, "_")

                MouseArea { id: activeHover; anchors.fill: parent; hoverEnabled: true }
                RowLayout {
                    id: activeContent
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: Theme.space(12); anchors.rightMargin: Theme.space(12)
                    spacing: Theme.space(12)
                    Badge {
                        text: activeRow.modelData.origin
                        tone: activeRow.modelData.originTone
                        Layout.alignment: Qt.AlignVCenter
                    }
                    Text {
                        text: activeRow.modelData.item
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                    }
                    Badge {
                        text: activeRow.modelData.state.text
                        tone: activeRow.modelData.state.tone
                        Layout.alignment: Qt.AlignVCenter
                    }
                    // "Ver ›": a text link (30 §5.6, item 16), opens Concessões with this row selected.
                    Text {
                        id: openLink
                        objectName: "activeOpen_" + activeRow.modelData.key.replace(/:/g, "_")
                        text: "Ver ›"
                        textFormat: Text.PlainText
                        color: Theme.accent
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600
                        Layout.alignment: Qt.AlignVCenter
                        Accessible.role: Accessible.Link
                        Accessible.name: "Ver " + activeRow.modelData.item
                        activeFocusOnTab: true
                        Keys.onReturnPressed: page.openList(activeRow.modelData.filter, activeRow.modelData.key)
                        Keys.onSpacePressed: page.openList(activeRow.modelData.filter, activeRow.modelData.key)
                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -6
                            cursorShape: Qt.PointingHandCursor
                            onClicked: page.openList(activeRow.modelData.filter, activeRow.modelData.key)
                        }
                        Rectangle {
                            anchors.fill: parent; anchors.margins: -4; radius: Theme.radius; color: "transparent"
                            border.width: 2; border.color: Theme.focusRing
                            visible: openLink.activeFocus
                        }
                    }
                }
            }
        }
        EmptyState {
            visible: page.active.length === 0
            iconName: "shield"
            message: "Nenhuma permissão concedida ainda.\nAprove um plugin ou consinta escopos de uma conta para vê-los aqui."
        }
        GButton {
            objectName: "allGrantsLink"
            variant: "ghost"
            text: "Ver todas em Concessões ›"
            Layout.alignment: Qt.AlignLeft
            onClicked: page.openList("todas", "")
        }
    }

    Collapsible {
        objectName: "howItWorks"
        title: "Como funciona"
        Text {
            text: "Permissões são decisões suas. Aprovar não instala nem executa nada. Revogar desativa o plugin e encerra o processo. Skills não concedem permissão: usam capacidades de plugins já aprovados. Contas só usam os escopos que você consentiu."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
