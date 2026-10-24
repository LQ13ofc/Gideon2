import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../components/BExt.js" as X
import "../shell"
import "../shell/Labels.js" as L

// Extensões > Plugins (B01). A list of 56 px rows; a click opens the detail drawer on the right (360 px). One banner.
// Installing copies a verified package and runs nothing; approving permissions does not install or run; enabling runs
// the plugin in its sandbox. Destructive actions (revoke, remove) confirm in a modal with Cancelar as the default.
PageFrame {
    id: page
    objectName: "pluginsPage"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "plugins"

    property string filter: "todos"
    property string selectedId: ""

    // Motives shown on disabled controls (8.6): Core offline, voice session, or a plain refusal.
    readonly property var ctx: ({
        pluginsAvailable: core.pluginsAvailable,
        hubApprovalAvailable: core.hubApprovalAvailable,
        hubLifecycleAvailable: core.hubLifecycleAvailable,
        blockedText: core.connected ? (core.sessionId ? "Indisponível durante a sessão de voz." : "Indisponível: ação não permitida agora.") : "Core desconectado: nada pode ser alterado agora."
    })
    // One row per plugin: the catalog entry (when there is one), the Core item and the installed record.
    readonly property var rows: {
        var out = []
        var entries = core.hubEntries
        var items = core.pluginItems
        var records = core.hubInstalled
        var seen = {}
        for (var i = 0; i < entries.length; i++) {
            var e = entries[i]
            seen[e.plugin_id] = true
            out.push({plugin_id: e.plugin_id, entry: e, item: L.pluginFor(items, e.plugin_id), record: L.pluginFor(records, e.plugin_id)})
        }
        for (var j = 0; j < items.length; j++) {
            if (seen[items[j].plugin_id]) continue
            out.push({plugin_id: items[j].plugin_id, entry: null, item: items[j], record: L.pluginFor(records, items[j].plugin_id)})
        }
        return out
    }
    readonly property var tally: X.counts(rows)
    readonly property int shown: filter === "instalados" ? tally.instalados : filter === "disponiveis" ? tally.disponiveis
        : filter === "quarentena" ? tally.quarentena : tally.todos
    readonly property var selectedRow: {
        for (var i = 0; i < page.rows.length; i++) if (page.rows[i].plugin_id === page.selectedId) return page.rows[i]
        return null
    }

    function approvalDone() {
        if (!AppState.reviewPlugin) return false
        var e = L.hubEntry(core.hubEntries, AppState.reviewPlugin.plugin_id)
        return !!e && e.manifest_sha256 === AppState.reviewPlugin.manifest_sha256 && e.permissions_approved === true
    }
    function permissionText(p) {
        var label = core.permissionLabel(p)
        return label === p ? "permissão sem rótulo: " + p : label
    }
    function openReview(plugin) { AppState.reviewPlugin = plugin; reviewAck.checked = false; reviewDialog.open() }
    function askRemove(plugin) { removeConfirm.plugin = plugin; removeConfirm.revision = core.hubInstallRevision; removeConfirm.open() }
    function askRevoke(plugin) { revokeConfirm.plugin = plugin; revokeConfirm.revision = core.pluginsRevision; revokeConfirm.open() }
    function askClearData(plugin) { clearDataConfirm.plugin = plugin; clearDataConfirm.open() }

    PageHeader {
        title: "Plugins"
        subtitle: "Instale e ative plugins verificados. Instalar não executa nada e não concede acesso."
    }
    // The one notice of the page: the catalog state (publishers are not authenticated; quarantine when it applies).
    Banner {
        objectName: "hubBanner"
        kind: core.hubDescription.indexOf("quarentena") >= 0 ? "error" : "info"
        text: core.hubDescription
    }
    Collapsible {
        title: "Como funciona"
        summary: "Instalar copia o pacote verificado; nada é executado. Aprovar permissões não instala."
        Text {
            text: "Instalar copia o pacote verificado para o Core; nada é executado. O catálogo não concede acesso ao computador."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: "Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: "Plugins ativos rodam em sandbox, sem rede. Revogar permissões desativa o plugin e encerra o processo."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
    }

    // Results of the last operations (the same text the toast repeats).
    Text {
        objectName: "hubLifecycleResult"
        visible: text.length > 0
        text: core.hubApprovalResult
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        objectName: "pluginLifecycleResult"
        visible: text.length > 0
        text: core.pluginResult
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        objectName: "capabilityResult"
        visible: text.length > 0
        text: core.capabilityResultText
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    RowLayout {
        visible: core.hubImportActive
        Layout.fillWidth: true
        spacing: Theme.space(10)
        Text {
            objectName: "hubImportDescription"
            text: core.hubImportDescription
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "abortHubImportButton"
            enabled: core.hubImportActive
            text: "Cancelar importação"
            variant: "secondary"
            onClicked: core.abortHubImport()
        }
    }

    Segmented {
        objectName: "pluginFilter"
        model: [
            {id: "todos", text: "Todos " + page.tally.todos},
            {id: "instalados", text: "Instalados " + page.tally.instalados},
            {id: "disponiveis", text: "Disponíveis " + page.tally.disponiveis},
            {id: "quarentena", text: "Quarentena " + page.tally.quarentena}
        ]
        currentId: page.filter
        onActivated: function (id) { page.filter = id }
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignTop
        spacing: Theme.space(16)

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: 0

            Text {
                visible: page.rows.length === 0
                text: "Catálogo não configurado"
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSection
                font.weight: 600
                Layout.fillWidth: true
            }
            EmptyState {
                objectName: "hubEmpty"
                visible: page.rows.length === 0
                iconName: "puzzle"
                message: "Nenhum plugin no catálogo ainda. Conecte o Core para carregar o catálogo local."
                actionText: "Atualizar catálogo"
                onActionRequested: core.refresh()
            }
            RowLayout {
                visible: page.rows.length > 0 && page.shown === 0
                Layout.fillWidth: true
                spacing: Theme.space(12)
                Text {
                    text: "Nenhum plugin neste filtro."
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.fillWidth: true
                }
                GButton {
                    text: "Ver todos"
                    variant: "ghost"
                    onClicked: page.filter = "todos"
                }
            }

            Repeater {
                model: page.rows
                delegate: BPluginRow {
                    required property var modelData
                    entry: modelData.entry
                    item: modelData.item
                    record: modelData.record
                    ctx: page.ctx
                    selected: modelData.plugin_id === page.selectedId
                    visible: X.inFilter(modelData, page.filter)
                    onSelectRequested: page.selectedId = modelData.plugin_id
                    onReviewRequested: function (plugin) { page.openReview(plugin) }
                    onRevokeRequested: function (plugin) { page.askRevoke(plugin) }
                    onRemoveRequested: function (plugin) { page.askRemove(plugin) }
                    onClearDataRequested: function (plugin) { page.askClearData(plugin) }
                }
            }
        }

        BPluginDetail {
            visible: page.selectedRow !== null
            entry: page.selectedRow ? page.selectedRow.entry : null
            item: page.selectedRow ? page.selectedRow.item : null
            ctx: page.ctx
            onReviewRequested: function (plugin) { page.openReview(plugin) }
            onCloseRequested: page.selectedId = ""
        }
    }

    // Review (F1): the approval target is captured when the dialog opens; the bridge refuses it if the live record changed.
    Modal {
        id: reviewDialog
        objectName: "hubReviewDialog"
        closeOnly: true
        title: "Revisar permissões"
        onOpened: { core.beginHubReview(); AppState.reviewRevision = core.hubApprovalRevision }
        Text {
            text: AppState.reviewPlugin ? AppState.reviewPlugin.plugin_id + " " + AppState.reviewPlugin.semver + " · " + AppState.reviewPlugin.publisher + " · não verificado" : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            visible: AppState.reviewPlugin !== null
            text: "Permissões declaradas (não aprovadas):"
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; font.weight: 600; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Repeater {
            model: AppState.reviewPlugin ? AppState.reviewPlugin.permissions : []
            delegate: Text {
                required property var modelData
                text: "•  " + page.permissionText(modelData)
                textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
        }
        Text {
            text: "Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GCheckbox {
            id: reviewAck
            objectName: "publisherAcknowledgement"
            text: "Entendo que o publisher não foi autenticado"
            enabled: core.hubApprovalAvailable
        }
        Text {
            visible: !reviewAck.checked
            text: "Marque a confirmação para liberar a aprovação."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "approveHubButton"
            variant: "primary"
            text: "Aprovar estas permissões"
            Layout.fillWidth: true
            Accessible.name: AppState.reviewPlugin ? "Aprovar permissões de " + AppState.reviewPlugin.plugin_id : "Aprovar permissões"
            enabled: core.hubApprovalAvailable && reviewAck.checked && AppState.reviewPlugin !== null && !page.approvalDone()
            onClicked: core.approveHub(AppState.reviewPlugin.plugin_id, AppState.reviewPlugin.manifest_sha256, AppState.reviewPlugin.permissions, reviewAck.checked, AppState.reviewRevision)
        }
        Text {
            objectName: "hubApprovalResult"
            text: core.hubApprovalResult
            textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
    }

    // Confirmations (8.7): Cancelar is the focused default; the verb button is the only way to accept.
    Modal {
        id: removeConfirm
        objectName: "removeConfirm"
        property var plugin: null
        property string revision: ""
        title: "Remover plugin"
        onAccepted: { if (plugin) core.removeHub(plugin.plugin_id, revision) }
        Text {
            text: removeConfirm.plugin ? "Remover " + removeConfirm.plugin.plugin_id + " " + removeConfirm.plugin.semver + " do Core? Nada é executado e o catálogo não muda." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmRemoveButton"; variant: "danger"; text: "Remover"
            Layout.alignment: Qt.AlignRight
            Accessible.name: removeConfirm.plugin ? "Remover " + removeConfirm.plugin.plugin_id : "Remover"
            onClicked: removeConfirm.accept()
        }
    }
    Modal {
        id: revokeConfirm
        objectName: "revokeConfirm"
        property var plugin: null
        property string revision: ""
        title: "Revogar permissões"
        onAccepted: { if (plugin) core.revokePlugin(plugin.plugin_id, revision) }
        Text {
            text: revokeConfirm.plugin ? "Revogar permissões de " + revokeConfirm.plugin.plugin_id + "? O plugin será desativado e o processo encerrado. Reativar exige nova aprovação." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmRevokeButton"; variant: "danger"; text: "Revogar"
            Layout.alignment: Qt.AlignRight
            Accessible.name: revokeConfirm.plugin ? "Revogar permissões de " + revokeConfirm.plugin.plugin_id : "Revogar"
            onClicked: revokeConfirm.accept()
        }
    }
    // Apagar os dados do plugin: only that plugin's own settings file. Cancelar is the default focus.
    Modal {
        id: clearDataConfirm
        objectName: "pluginClearDataConfirm"
        property var plugin: null
        title: "Apagar dados do plugin?"
        onAccepted: { if (plugin) core.clearPluginSettingsOf(plugin.plugin_id) }
        Text {
            text: clearDataConfirm.plugin ? "Apagar as configurações guardadas por " + clearDataConfirm.plugin.plugin_id + "? O plugin, as permissões aprovadas e a configuração do Core não são alterados. Não há volta." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmClearDataButton"; variant: "danger"; text: "Apagar dados"
            Layout.alignment: Qt.AlignRight
            Accessible.name: clearDataConfirm.plugin ? "Apagar dados de " + clearDataConfirm.plugin.plugin_id : "Apagar dados"
            onClicked: clearDataConfirm.accept()
        }
    }
}
