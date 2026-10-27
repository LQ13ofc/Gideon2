import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import QtQuick.Dialogs
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
        hubImportPickable: core.hubImportPickable,
        blockedText: core.connected ? (core.sessionId ? qsTr("Indisponível durante a sessão de voz.") : qsTr("Indisponível: ação não permitida agora.")) : qsTr("Core desconectado: nada pode ser alterado agora.")
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
        return label === p ? qsTr("permissão sem rótulo: %1").arg(p) : label
    }
    function openReview(plugin) { AppState.reviewPlugin = plugin; reviewAck.checked = false; reviewDialog.open() }
    function askRemove(plugin) { removeConfirm.plugin = plugin; removeConfirm.revision = core.hubInstallRevision; removeConfirm.open() }
    function askRevoke(plugin) { revokeConfirm.plugin = plugin; revokeConfirm.revision = core.pluginsRevision; revokeConfirm.open() }
    function askClearData(plugin) { clearDataConfirm.plugin = plugin; clearDataConfirm.open() }
    // WP-4 Hub import: the plugin whose payload the file dialog is choosing. The Core verifies and stages the file; nothing installs.
    property string importPid: ""
    function askImport(plugin) { importPid = plugin.plugin_id; importDialog.open() }

    PageHeader {
        title: qsTr("Plugins")
        subtitle: qsTr("Instale e ative plugins verificados. Instalar não executa nada e não concede acesso.")
    }
    // The one notice of the page: the catalog state (publishers are not authenticated; quarantine when it applies).
    Banner {
        objectName: "hubBanner"
        kind: core.hubQuarantined ? "error" : "info"
        text: core.hubDescription
    }
    Collapsible {
        title: qsTr("Como funciona")
        summary: qsTr("Instalar copia o pacote verificado; nada é executado. Aprovar permissões não instala.")
        Text {
            text: qsTr("Instalar copia o pacote verificado para o Core; nada é executado. O catálogo não concede acesso ao computador.")
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: qsTr("Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto.")
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: qsTr("Plugins ativos rodam em sandbox, sem rede. Revogar permissões desativa o plugin e encerra o processo.")
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
            text: qsTr("Cancelar importação")
            variant: "secondary"
            onClicked: core.abortHubImport()
        }
    }

    Segmented {
        objectName: "pluginFilter"
        model: [
            {id: "todos", text: qsTr("Todos %1").arg(page.tally.todos)},
            {id: "instalados", text: qsTr("Instalados %1").arg(page.tally.instalados)},
            {id: "disponiveis", text: qsTr("Disponíveis %1").arg(page.tally.disponiveis)},
            {id: "quarentena", text: qsTr("Quarentena %1").arg(page.tally.quarentena)}
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
                text: qsTr("Catálogo não configurado")
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
                message: qsTr("Nenhum plugin no catálogo ainda. Conecte o Core para carregar o catálogo local.")
                actionText: qsTr("Atualizar catálogo")
                onActionRequested: core.refresh()
            }
            RowLayout {
                visible: page.rows.length > 0 && page.shown === 0
                Layout.fillWidth: true
                spacing: Theme.space(12)
                Text {
                    text: qsTr("Nenhum plugin neste filtro.")
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.fillWidth: true
                }
                GButton {
                    text: qsTr("Ver todos")
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
                    onImportRequested: function (plugin) { page.askImport(plugin) }
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
            onImportRequested: function (plugin) { page.askImport(plugin) }
            onCloseRequested: page.selectedId = ""
        }
    }

    // WP-4: pick the package file of an approved plugin. The bridge reads it in chunks and refuses a size that differs from the catalog.
    FileDialog {
        id: importDialog
        objectName: "hubImportDialog"
        title: qsTr("Pacote do plugin %1").arg(page.importPid)
        fileMode: FileDialog.OpenFile
        onAccepted: {
            var message = core.importHubPayload(page.importPid, String(selectedFile))
            if (message.length > 0) AppState.toast(message)
        }
    }

    // Review (F1): the approval target is captured when the dialog opens; the bridge refuses it if the live record changed.
    Modal {
        id: reviewDialog
        objectName: "hubReviewDialog"
        closeOnly: true
        title: qsTr("Revisar permissões")
        onOpened: { core.beginHubReview(); AppState.reviewRevision = core.hubApprovalRevision }
        Text {
            text: AppState.reviewPlugin ? qsTr("%1 %2 · %3%4").arg(AppState.reviewPlugin.plugin_id).arg(AppState.reviewPlugin.semver).arg(AppState.reviewPlugin.publisher).arg(core.hubPublisherVerified ? qsTr(" · publisher verificado") : qsTr(" · não verificado")) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            visible: AppState.reviewPlugin !== null
            text: qsTr("Permissões declaradas (não aprovadas):")
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; font.weight: 600; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Repeater {
            model: AppState.reviewPlugin ? AppState.reviewPlugin.permissions : []
            delegate: Text {
                required property var modelData
                text: qsTr("•  %1").arg(page.permissionText(modelData))
                textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
        }
        Text {
            text: qsTr("Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto.")
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GCheckbox {
            id: reviewAck
            objectName: "publisherAcknowledgement"
            text: core.hubPublisherVerified ? qsTr("Entendo as permissões deste plugin") : qsTr("Entendo que o publisher não foi autenticado")
            enabled: core.hubApprovalAvailable
        }
        Text {
            visible: !reviewAck.checked
            text: qsTr("Marque a confirmação para liberar a aprovação.")
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "approveHubButton"
            variant: "primary"
            text: qsTr("Aprovar estas permissões")
            Layout.fillWidth: true
            Accessible.name: AppState.reviewPlugin ? qsTr("Aprovar permissões de %1").arg(AppState.reviewPlugin.plugin_id) : qsTr("Aprovar permissões")
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
        title: qsTr("Remover plugin")
        onAccepted: { if (plugin) core.removeHub(plugin.plugin_id, revision) }
        Text {
            text: removeConfirm.plugin ? qsTr("Remover %1 %2 do Core? Nada é executado e o catálogo não muda.").arg(removeConfirm.plugin.plugin_id).arg(removeConfirm.plugin.semver) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmRemoveButton"; variant: "danger"; text: qsTr("Remover")
            Layout.alignment: Qt.AlignRight
            Accessible.name: removeConfirm.plugin ? qsTr("Remover %1").arg(removeConfirm.plugin.plugin_id) : qsTr("Remover")
            onClicked: removeConfirm.accept()
        }
    }
    Modal {
        id: revokeConfirm
        objectName: "revokeConfirm"
        property var plugin: null
        property string revision: ""
        title: qsTr("Revogar permissões")
        onAccepted: { if (plugin) core.revokePlugin(plugin.plugin_id, revision) }
        Text {
            text: revokeConfirm.plugin ? qsTr("Revogar permissões de %1? O plugin será desativado e o processo encerrado. Reativar exige nova aprovação.").arg(revokeConfirm.plugin.plugin_id) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmRevokeButton"; variant: "danger"; text: qsTr("Revogar")
            Layout.alignment: Qt.AlignRight
            Accessible.name: revokeConfirm.plugin ? qsTr("Revogar permissões de %1").arg(revokeConfirm.plugin.plugin_id) : qsTr("Revogar")
            onClicked: revokeConfirm.accept()
        }
    }
    // Apagar os dados do plugin: only that plugin's own settings file. Cancelar is the default focus.
    Modal {
        id: clearDataConfirm
        objectName: "pluginClearDataConfirm"
        property var plugin: null
        title: qsTr("Apagar dados do plugin?")
        onAccepted: { if (plugin) core.clearPluginSettingsOf(plugin.plugin_id) }
        Text {
            text: clearDataConfirm.plugin ? qsTr("Apagar as configurações guardadas por %1? O plugin, as permissões aprovadas e a configuração do Core não são alterados. Não há volta.").arg(clearDataConfirm.plugin.plugin_id) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmClearDataButton"; variant: "danger"; text: qsTr("Apagar dados")
            Layout.alignment: Qt.AlignRight
            Accessible.name: clearDataConfirm.plugin ? qsTr("Apagar dados de %1").arg(clearDataConfirm.plugin.plugin_id) : qsTr("Apagar dados")
            onClicked: clearDataConfirm.accept()
        }
    }
}
