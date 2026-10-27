import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/PermRows.js" as P

// Permissões > Concessões (docs/ui-spec/30-permissoes.md §6): one table with everything plugins, skills and accounts
// can use. Filter and grouping are kept for the session (AppState). Decisions open the shared dialogs (DPermDialogs).
PageFrame {
    id: page
    objectName: "page_perm_concessoes"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "perm_concessoes"

    // Table columns in px. The table is at least minTable wide and scrolls sideways inside its own box (30 §10).
    readonly property int wNum: 44
    readonly property int wOrig: 100
    readonly property int wItem: 208
    readonly property int wAcc: 100
    readonly property int wState: 140
    readonly property int wAct: 176  // wide enough for the longest translated action label
    readonly property int wDate: 96
    readonly property int minTable: 1080
    readonly property int tableWidth: Math.max(tableScroll.width, minTable)
    readonly property int wPerm: tableWidth - 24 - wNum - wOrig - wItem - wAcc - wDate - wState - wAct

    // Título do filtro (a chave do filtro é o id de AppState, sem texto).
    function filterLabel(id) {
        switch (id) {
        case "plugins": return qsTr("Plugins")
        case "skills": return qsTr("Skills")
        case "conexoes": return qsTr("Conexões")
        }
        return qsTr("Concessões")
    }
    function itemsText(n) { return n === 1 ? qsTr("%1 item").arg(n) : qsTr("%1 itens").arg(n) }
    function pendingText(n) { return n === 1 ? qsTr("%1 pendente").arg(n) : qsTr("%1 pendentes").arg(n) }

    function grantFlags() {
        var voice = core.sessionId.length > 0
        return {
            online: core.connected,
            hubOk: core.hubApprovalAvailable,
            pluginsOk: core.pluginsAvailable,
            connAvailable: core.connectionsAvailable,
            connBusy: core.connectionsBusy,
            skillsOk: core.skillsAvailable,
            pluginsBlockedTip: !core.connected ? qsTr("Core desconectado.") : voice ? qsTr("Indisponível durante a sessão de voz.") : qsTr("Indisponível agora.")
        }
    }
    readonly property var rows: P.grantRows({hub: core.hubEntries, plugins: core.pluginItems, skills: core.skillsItems,
                                             conns: core.connectionsItems, providers: core.connectionsProviders,
                                             labelOf: function (p) { return core.permissionLabel(p) }, flags: grantFlags()})
    readonly property var filtered: P.filterRows(rows, AppState.permFilter)
    readonly property var shown: P.groupRows(filtered, AppState.permGroup)
    readonly property int pendingShown: P.pendingIn(filtered)

    function runAction(row) {
        if (!row || !row.action || !row.action.enabled) return
        switch (row.action.kind) {
        case "review": dialogs.reviewPlugin(row.ref); break
        case "revoke": dialogs.revokePlugin(row.ref); break
        case "skill": Window.window.goPage("skills"); break
        case "consent": dialogs.consent(row.ref); break
        case "revokeAccount": dialogs.revokeAccount(row.ref); break
        case "revokeScope": dialogs.revokeScope(row.ref, row.scope); break
        case "trust": dialogs.trustTool(row.ref, row.tool); break
        }
    }
    function actionName(row) {
        switch (row.action.kind) {
        case "review": return qsTr("Revisar permissões de %1").arg(row.ref.plugin_id)
        case "revoke": return qsTr("Revogar permissões de %1").arg(row.ref.plugin_id)
        case "skill": return qsTr("Ver em Skills: %1").arg(row.item)
        case "consent": return qsTr("Consentir escopos de %1").arg(row.ref.label)
        case "revokeAccount": return qsTr("Revogar acesso da conta %1").arg(row.ref.label)
        case "revokeScope": return qsTr("Revogar escopo %1 da conta %2").arg(row.perm).arg(row.ref.label)
        case "trust": return qsTr("Confiar na ferramenta %1").arg(row.tool)
        }
        return row.action.text
    }

    DPermDialogs { id: dialogs }

    PageHeader {
        title: qsTr("Concessões")
        subtitle: qsTr("Tudo o que plugins, skills e contas podem usar, com a sua decisão.")
    }
    Banner {
        objectName: "permBanner"
        kind: core.connected ? "warn" : "error"
        text: !core.connected ? qsTr("Core desconectado. Mostrando o último estado conhecido; nada pode ser alterado.")
            : core.sessionId.length > 0 ? qsTr("Sessão de voz ativa: mudanças em plugins bloqueadas.") : ""
    }

    // A wrapping row: at 600 px the count and the grouping select go to a second line instead of leaving the window.
    Flow {
        Layout.fillWidth: true
        spacing: Theme.space(12)
        Segmented {
            objectName: "grantFilter"
            model: [{id: "todas", text: qsTr("Todas")}, {id: "plugins", text: qsTr("Plugins")}, {id: "skills", text: qsTr("Skills")}, {id: "conexoes", text: qsTr("Conexões")}]
            currentId: AppState.permFilter
            onActivated: function (id) { AppState.permFilter = id; AppState.permFocusKey = "" }
        }
        Text {
            objectName: "grantCount"
            topPadding: 9  // centred on the 36 px controls of the row
            text: qsTr("%1 · %2").arg(page.itemsText(page.filtered.length)).arg(page.pendingText(page.pendingShown))
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp
        }
        Select {
            id: groupBox
            objectName: "grantGroup"
            width: 216
            textRole: "text"; valueRole: "id"
            model: [{id: "origem", text: qsTr("Agrupar por: Origem")}, {id: "item", text: qsTr("Agrupar por: Item")}]
            currentIndex: Math.max(0, indexOfValue(AppState.permGroup))
            onActivated: AppState.permGroup = currentValue
        }
    }

    Flickable {
        id: tableScroll
        objectName: "grantTable"
        visible: page.rows.length > 0 && page.filtered.length > 0
        Layout.fillWidth: true
        implicitHeight: tableCol.implicitHeight
        contentWidth: page.tableWidth
        contentHeight: tableCol.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            id: tableCol
            width: page.tableWidth
            spacing: 0

            // Column headers (12 px, semibold, muted).
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: Theme.space(12)
                Layout.rightMargin: Theme.space(12)
                Layout.preferredHeight: 32
                spacing: 0
                Repeater {
                    model: [{t: qsTr("Nº"), w: page.wNum}, {t: qsTr("Origem"), w: page.wOrig}, {t: qsTr("Item"), w: page.wItem}, {t: qsTr("Permissão ou escopo"), w: page.wPerm},
                            {t: qsTr("Acesso"), w: page.wAcc}, {t: qsTr("Concedido em"), w: page.wDate}, {t: qsTr("Estado"), w: page.wState}, {t: qsTr("Ação"), w: page.wAct}]
                    delegate: Text {
                        required property var modelData
                        text: modelData.t
                        textFormat: Text.PlainText
                        color: Theme.textMuted
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; font.weight: 600
                        Layout.preferredWidth: modelData.w
                        Layout.minimumWidth: modelData.w
                        Accessible.role: Accessible.ColumnHeader
                        Accessible.name: modelData.t
                    }
                }
            }

            // Group headers and rows.
            Repeater {
                model: page.shown
                delegate: Item {
                    id: line
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: modelData.header ? 34 : body.implicitHeight + Theme.space(16)

                    // Group header: a band, not a box.
                    Rectangle {
                        visible: line.modelData.header
                        anchors.fill: parent
                        color: Theme.surfaceVariant
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: Theme.space(12)
                            text: line.modelData.header ? (line.modelData.count ? qsTr("%1 · %2").arg(line.modelData.text).arg(line.modelData.count) : line.modelData.text) : ""
                            textFormat: Text.PlainText
                            color: Theme.textMuted
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; font.weight: 600
                        }
                    }

                    // One row. Risk rows carry a quiet marker: a thin bar and a faint tint, never a filled box.
                    Rectangle {
                        id: rowBox
                        visible: !line.modelData.header
                        anchors.fill: parent
                        objectName: line.modelData.header ? "" : "grant_" + String(line.modelData.key).replace(/:/g, "_")
                        readonly property bool focused: !line.modelData.header && AppState.permFocusKey !== "" && line.modelData.key === AppState.permFocusKey
                        color: focused ? Theme.tint : (line.modelData.risk ? Qt.alpha(Theme.error, 0.08) : (rowHover.containsMouse ? Theme.hover : "transparent"))
                        activeFocusOnTab: !line.modelData.header
                        Accessible.role: Accessible.ListItem
                        Accessible.name: line.modelData.header ? "" : qsTr("%1, %2, %3").arg(line.modelData.item).arg(line.modelData.perm).arg(line.modelData.state.text)
                        Keys.onReturnPressed: page.runAction(line.modelData)
                        Keys.onEnterPressed: page.runAction(line.modelData)

                        MouseArea { id: rowHover; anchors.fill: parent; hoverEnabled: true }
                        Rectangle {
                            visible: line.modelData.risk === true
                            anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
                            width: 3
                            color: Theme.error
                        }
                        Rectangle {
                            anchors.fill: parent
                            color: "transparent"
                            border.width: 2; border.color: Theme.focusRing
                            visible: rowBox.activeFocus
                        }
                        Rectangle {
                            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                            height: 1
                            color: Theme.hairline
                        }
                    }
                    RowLayout {
                        id: body
                        visible: !line.modelData.header
                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                        anchors.leftMargin: Theme.space(12); anchors.rightMargin: Theme.space(12); anchors.topMargin: Theme.space(8)
                        spacing: 0

                        Text {
                            text: String(line.modelData.number || "")
                            textFormat: Text.PlainText
                            color: Theme.textMuted
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                            Layout.preferredWidth: page.wNum; Layout.alignment: Qt.AlignTop
                        }
                        Item {
                            Layout.preferredWidth: page.wOrig; Layout.minimumWidth: page.wOrig
                            Layout.preferredHeight: badgeOrig.implicitHeight
                            Layout.alignment: Qt.AlignTop
                            Badge { id: badgeOrig; text: line.modelData.originText || ""; tone: line.modelData.originTone || "neutral" }
                        }
                        ColumnLayout {
                            Layout.preferredWidth: page.wItem; Layout.minimumWidth: page.wItem
                            Layout.alignment: Qt.AlignTop
                            spacing: 2
                            Text {
                                text: line.modelData.item || ""
                                textFormat: Text.PlainText
                                color: Theme.text
                                font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Text {
                                visible: (line.modelData.sub || "").length > 0
                                text: line.modelData.sub || ""
                                textFormat: Text.PlainText
                                color: Theme.textMuted
                                font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                        ColumnLayout {
                            Layout.preferredWidth: page.wPerm; Layout.minimumWidth: 200
                            Layout.alignment: Qt.AlignTop
                            spacing: 2
                            Text {
                                text: line.modelData.perm || ""
                                textFormat: Text.PlainText
                                color: line.modelData.permTone === "success" ? Theme.success : line.modelData.permTone === "warning" ? Theme.warning : Theme.text
                                font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Text {
                                visible: (line.modelData.permNote || "").length > 0
                                text: line.modelData.permNote || ""
                                textFormat: Text.PlainText
                                color: Theme.warning
                                font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Text {
                                visible: Theme.advanced && (line.modelData.permIds || []).length > 0
                                text: (line.modelData.permIds || []).join(", ")
                                textFormat: Text.PlainText
                                color: Theme.textMuted
                                font.family: "monospace"; font.pixelSize: Theme.fontCaption
                                wrapMode: Text.WrapAnywhere
                                Layout.fillWidth: true
                            }
                        }
                        Text {
                            text: line.modelData.access || "—"
                            textFormat: Text.PlainText
                            color: line.modelData.risk ? Theme.error : Theme.text
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                            font.weight: line.modelData.risk ? 700 : 400
                            Layout.preferredWidth: page.wAcc; Layout.minimumWidth: page.wAcc
                            Layout.alignment: Qt.AlignTop
                        }
                        // Date of the grant (Core Unix ms, shown as dd/mm/aaaa); "—" when the Core has no date for the row.
                        Text {
                            objectName: "grantDate_" + String(line.modelData.key || "").replace(/:/g, "_")
                            text: line.modelData.granted || "—"
                            textFormat: Text.PlainText
                            color: Theme.textMuted
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                            Layout.preferredWidth: page.wDate; Layout.minimumWidth: page.wDate
                            Layout.alignment: Qt.AlignTop
                        }
                        Item {
                            Layout.preferredWidth: page.wState; Layout.minimumWidth: page.wState
                            Layout.preferredHeight: badgeState.implicitHeight
                            Badge {
                                id: badgeState
                                text: line.modelData.state ? line.modelData.state.text : ""
                                tone: line.modelData.state ? line.modelData.state.tone : "neutral"
                            }
                        }
                        Item {
                            Layout.preferredWidth: page.wAct; Layout.minimumWidth: page.wAct
                            Layout.alignment: Qt.AlignTop
                            implicitHeight: actionButton.visible ? actionButton.implicitHeight : actionNote.implicitHeight
                            GButton {
                                id: actionButton
                                objectName: "grantAction_" + String(line.modelData.key || "").replace(/:/g, "_")
                                visible: !!line.modelData.action && line.modelData.action.kind !== "none"
                                text: line.modelData.action ? line.modelData.action.text : ""
                                variant: line.modelData.action && line.modelData.action.danger ? "danger" : "secondary"
                                enabled: !!line.modelData.action && line.modelData.action.enabled
                                Accessible.name: line.modelData.action ? page.actionName(line.modelData) : ""
                                Accessible.description: line.modelData.action ? line.modelData.action.tip : ""
                                onClicked: page.runAction(line.modelData)
                            }
                            Text {
                                id: actionNote
                                visible: !actionButton.visible
                                width: parent.width
                                text: line.modelData.action ? line.modelData.action.text : ""
                                textFormat: Text.PlainText
                                color: Theme.textMuted
                                font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }
        }
    }

    EmptyState {
        objectName: "grantEmptyAll"
        visible: page.rows.length === 0
        iconName: "shield"
        message: qsTr("Nenhum plugin, skill ou conta pede permissão ainda.\nInstale ou conecte em Extensões para ver as permissões aqui.")
        actionText: qsTr("Abrir Extensões")
        onActionRequested: Window.window.goPage("plugins")
    }
    EmptyState {
        objectName: "grantEmptyFilter"
        visible: page.rows.length > 0 && page.filtered.length === 0
        iconName: "shield"
        message: qsTr("Nenhum item em %1 aqui.").arg(page.filterLabel(AppState.permFilter))
    }
}
