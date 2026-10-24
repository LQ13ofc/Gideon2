import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../shell/Labels.js" as L
import "../shell/PermRows.js" as P

// The Permissões decision dialogs (docs/ui-spec/30-permissoes.md §4, D-P1 to D-P5), shared by Visão geral and Concessões.
// Confirmations focus Cancelar; D-P1 focuses its checkbox. Each open captures the revision it will send; the bridge
// refuses a stale one. Call reviewPlugin, revokePlugin, consent, revokeAccount or trustTool; the dialog does the rest.
Item {
    id: host
    visible: false
    width: 0
    height: 0

    property var plugin: null        // hub entry (D-P1, D-P2)
    property var account: null       // connection item (D-P3, D-P4, D-P5)
    property string toolName: ""     // D-P5
    property string revision: ""     // captured when the dialog opened (plugins or hub)
    property int picked: 0           // D-P3: scopes ticked

    function reviewPlugin(entry) { plugin = entry; reviewDlg.open() }
    function revokePlugin(entry) { plugin = entry; revision = core.pluginsRevision; revokeDlg.open() }
    function consent(item) { account = item; consentDlg.open() }
    function revokeAccount(item) { account = item; revokeAccountDlg.open() }
    function trustTool(item, name) { account = item; toolName = name; trustDlg.open() }

    function liveAccount() { return account ? L.connProvider(core.connectionsItems, account.id) : null }
    function liveEntry() { return plugin ? P.pluginEntry(core.hubEntries, plugin.plugin_id) : null }
    function accountName() { return account ? P.accountLine(core.connectionsProviders, account) : "" }
    function grantedLabels(item) {
        var out = []
        var grants = item ? (item.granted_scopes || []) : []
        for (var i = 0; i < grants.length; i++) out.push(P.scopeInfo(core.connectionsProviders, item.provider, grants[i]).label)
        return out
    }
    function reviewState() {
        var e = liveEntry() || plugin
        if (!e) return ""
        var item = L.pluginFor(core.pluginItems, e.plugin_id)
        if (e.status === "installed") return item && item.enabled === true ? "instalado · ativo (sandbox, sem rede)" : "instalado (desativado)"
        if (e.status === "update_available") return "atualização disponível"
        return "não instalado"
    }
    // Why an action is closed right now (shown as hint and in Accessible.description).
    function pluginBlockedText() {
        if (!core.connected) return "Core desconectado."
        if (core.sessionId.length > 0) return "Indisponível durante a sessão de voz."
        return "Indisponível agora."
    }
    function accessName(access) { return P.accessText(access) }
    function quarantinedNow() {
        var live = host.plugin ? L.pluginFor(core.pluginItems, host.plugin.plugin_id) : null
        return !!live && live.state === "quarantined"
    }
    // D-P3 scopes: the delegates report what is ticked (ticked), so the dialog needs no child lookups.
    function countPicked() {
        var n = 0
        for (var i = 0; i < scopeRepeater.count; i++) if (scopeRepeater.itemAt(i) && scopeRepeater.itemAt(i).ticked) n++
        return n
    }
    function chosen() {
        var out = []
        for (var i = 0; i < scopeRepeater.count; i++) if (scopeRepeater.itemAt(i) && scopeRepeater.itemAt(i).ticked) out.push(scopeRepeater.itemAt(i).modelData)
        return out
    }
    function riskyPicked() {
        for (var i = 0; i < scopeRepeater.count; i++) {
            var row = scopeRepeater.itemAt(i)
            if (row && row.ticked && (row.info.access === "public" || row.info.access === "destructive")) return accessName(row.info.access)
        }
        return ""
    }

    // D-P1 · Revisar permissões.
    Modal {
        id: reviewDlg
        objectName: "permReviewDialog"
        title: "Revisar permissões"
        standardButtons: Dialog.NoButton
        onOpened: {
            core.beginHubReview()
            host.revision = core.hubApprovalRevision
            reviewAck.checked = false
            reviewAck.forceActiveFocus()
        }
        Text {
            text: host.plugin ? host.plugin.plugin_id + " " + host.plugin.semver + " · " + host.plugin.publisher : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 700
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: "Estado do plugin: " + host.reviewState()
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: "Permissões que este manifesto pede:"
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600
            Layout.fillWidth: true
        }
        Repeater {
            model: host.plugin ? host.plugin.permissions : []
            delegate: Text {
                required property string modelData
                text: "• " + core.permissionLabel(modelData) + (Theme.advanced ? " (" + modelData + ")" : "")
                textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
        }
        Text {
            visible: host.plugin !== null && (host.plugin.permissions || []).length === 0
            text: "Nenhuma permissão: aprovar não concede acesso a nada."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: "Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            visible: Theme.advanced && host.plugin !== null
            text: host.plugin ? "Manifesto: " + String(host.plugin.manifest_sha256 || "").substring(0, 12) + "…" : ""
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: "monospace"; font.pixelSize: Theme.fontCaption
            Layout.fillWidth: true
        }
        GCheckbox {
            id: reviewAck
            objectName: "permReviewAck"
            text: "Entendo que o publisher não foi autenticado"
            enabled: core.hubApprovalAvailable
            Accessible.description: core.hubApprovalAvailable ? "" : host.pluginBlockedText()
            Layout.fillWidth: true
        }
        Text {
            visible: !core.hubApprovalAvailable
            text: host.pluginBlockedText()
            textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton {
                objectName: "permReviewClose"
                text: "Fechar"
                variant: "secondary"
                onClicked: reviewDlg.close()
            }
            GButton {
                objectName: "permApproveButton"
                variant: "primary"
                text: host.liveEntry() && host.liveEntry().permissions_approved === true ? "Permissões aprovadas" : "Aprovar estas permissões"
                enabled: core.hubApprovalAvailable && reviewAck.checked && host.plugin !== null && !(host.liveEntry() && host.liveEntry().permissions_approved === true)
                Accessible.name: host.plugin ? "Aprovar permissões de " + host.plugin.plugin_id : "Aprovar permissões"
                Accessible.description: enabled ? "" : host.pluginBlockedText()
                onClicked: {
                    core.approveHub(host.plugin.plugin_id, host.plugin.manifest_sha256, host.plugin.permissions, reviewAck.checked, host.revision)
                }
            }
        }
        Text {
            text: core.hubApprovalResult
            textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap; Layout.fillWidth: true
            Accessible.role: Accessible.AlertMessage
            Accessible.name: text
        }
    }

    // D-P2 · Revogar permissões de plugin.
    Modal {
        id: revokeDlg
        objectName: "permRevokeDialog"
        title: "Revogar permissões"
        standardButtons: Dialog.NoButton
        onOpened: revokeCancel.forceActiveFocus()
        Text {
            text: host.plugin ? "Revogar permissões de " + host.plugin.plugin_id + "? O plugin será desativado e o processo encerrado. Reativar exige nova aprovação." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton {
                id: revokeCancel
                objectName: "permRevokeCancel"
                text: "Cancelar"
                variant: "secondary"
                onClicked: revokeDlg.close()
            }
            GButton {
                objectName: "permRevokeConfirm"
                variant: "danger"
                text: "Revogar"
                enabled: core.pluginsAvailable && !!host.plugin && !host.quarantinedNow()
                Accessible.name: host.plugin ? "Revogar permissões de " + host.plugin.plugin_id : "Revogar permissões"
                Accessible.description: enabled ? "" : host.pluginBlockedText()
                onClicked: {
                    core.revokePlugin(host.plugin.plugin_id, host.revision)
                    revokeDlg.close()
                }
            }
        }
    }

    // D-P3 · Consentir escopos de conta.
    Modal {
        id: consentDlg
        objectName: "permConsentDialog"
        title: "Consentir escopos"
        standardButtons: Dialog.NoButton
        onOpened: {
            host.picked = 0
            consentCancel.forceActiveFocus()
        }
        Text {
            text: host.accountName()
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 700
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: "Escolha os escopos que esta conta pode usar. Nada é concedido sem sua marcação."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Repeater {
            id: scopeRepeater
            model: host.account ? (host.account.pending_scopes || []) : []
            delegate: RowLayout {
                id: scopeRow
                required property string modelData
                readonly property var info: P.scopeInfo(core.connectionsProviders, host.account ? host.account.provider : "", modelData)
                readonly property bool risky: info.access === "public" || info.access === "destructive"
                readonly property bool ticked: scopeBox.checked
                Layout.fillWidth: true
                spacing: Theme.space(8)
                GCheckbox {
                    id: scopeBox
                    objectName: "permScope_" + scopeRow.modelData
                    text: scopeRow.info.label + (Theme.advanced ? " (" + scopeRow.modelData + ")" : "")
                    Layout.fillWidth: true
                    onToggled: host.picked = host.countPicked()
                }
                Badge {
                    text: P.accessText(scopeRow.info.access)
                    tone: scopeRow.risky ? "error" : "neutral"
                }
            }
        }
        // Risk line: shown while a risky scope is ticked.
        Text {
            visible: host.picked > 0 && host.riskyPicked().length > 0
            text: "Escopo " + host.riskyPicked() + ": cada chamada pode pedir aprovação forte."
            textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            visible: host.picked === 0
            text: "Marque ao menos um escopo."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton {
                id: consentCancel
                objectName: "permConsentCancel"
                text: "Cancelar"
                variant: "secondary"
                onClicked: consentDlg.close()
            }
            GButton {
                objectName: "permConsentConfirm"
                variant: "primary"
                text: "Consentir escopos marcados"
                enabled: host.picked > 0 && core.connectionsAvailable && !core.connectionsBusy
                onClicked: {
                    core.connectionConsent(host.account.id, JSON.stringify(consentDlg.chosen()))
                    consentDlg.close()
                }
            }
        }
    }

    // D-P4 · Revogar acesso da conta.
    Modal {
        id: revokeAccountDlg
        objectName: "permRevokeAccountDialog"
        title: "Revogar acesso"
        standardButtons: Dialog.NoButton
        onOpened: revokeAccountCancel.forceActiveFocus()
        Text {
            text: host.account ? "Revogar o acesso da conta " + host.account.label + " no servidor? Os segredos locais são apagados, todos os escopos concedidos são retirados e as ferramentas MCP precisam de nova confiança. Para usar a conta de novo, conecte e consinta outra vez." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            visible: host.account !== null
            text: "Escopos que serão retirados: " + (host.account ? (host.grantedLabels(host.account).join(", ") || "nenhum") : "") + "."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton {
                id: revokeAccountCancel
                objectName: "permRevokeAccountCancel"
                text: "Cancelar"
                variant: "secondary"
                onClicked: revokeAccountDlg.close()
            }
            GButton {
                objectName: "permRevokeAccountConfirm"
                variant: "danger"
                text: "Revogar acesso"
                enabled: !!host.liveAccount() && L.connCan(core.connectionsBusy, "revoke", host.liveAccount())
                Accessible.name: host.account ? "Revogar acesso da conta " + host.account.label : "Revogar acesso"
                Accessible.description: enabled ? "" : "Conta sem acesso concedido para revogar."
                onClicked: {
                    core.connectionRevoke(host.account.id)
                    revokeAccountDlg.close()
                }
            }
        }
    }

    // D-P5 · Confiar em ferramenta MCP.
    Modal {
        id: trustDlg
        objectName: "permTrustDialog"
        title: "Confiar na ferramenta"
        standardButtons: Dialog.NoButton
        onOpened: trustCancel.forceActiveFocus()
        Text {
            text: host.account ? "Confiar em " + host.toolName + " do servidor " + host.account.label + "? Cada chamada desta ferramenta ainda pede sua aprovação. A descrição vem do servidor e é só texto." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton {
                id: trustCancel
                objectName: "permTrustCancel"
                text: "Cancelar"
                variant: "secondary"
                onClicked: trustDlg.close()
            }
            GButton {
                objectName: "permTrustConfirm"
                variant: "primary"
                text: "Confiar"
                enabled: core.connectionsAvailable && !core.connectionsBusy && host.toolName.length > 0
                Accessible.name: "Confiar na ferramenta " + host.toolName
                onClicked: {
                    core.connectionTrustTools(host.account.id, JSON.stringify([host.toolName]))
                    trustDlg.close()
                }
            }
        }
    }
}
