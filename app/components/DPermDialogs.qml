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
    property string scopeId: ""      // one granted scope of the account (revoke scope)
    property string revision: ""     // captured when the dialog opened (plugins or hub)
    property int picked: 0           // D-P3: scopes ticked

    function reviewPlugin(entry) { plugin = entry; reviewDlg.open() }
    function revokePlugin(entry) { plugin = entry; revision = core.pluginsRevision; revokeDlg.open() }
    function consent(item) { account = item; consentDlg.open() }
    function revokeAccount(item) { account = item; revokeAccountDlg.open() }
    function trustTool(item, name) { account = item; toolName = name; trustDlg.open() }
    function revokeScope(item, scope) { account = item; scopeId = scope; revokeScopeDlg.open() }

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
        if (e.status === "installed") return item && item.enabled === true ? qsTr("instalado · ativo (sandbox, sem rede)") : qsTr("instalado (desativado)")
        if (e.status === "update_available") return qsTr("atualização disponível")
        return qsTr("não instalado")
    }
    // Why an action is closed right now (shown as hint and in Accessible.description).
    function pluginBlockedText() {
        if (!core.connected) return qsTr("Core desconectado.")
        if (core.sessionId.length > 0) return qsTr("Indisponível durante a sessão de voz.")
        return qsTr("Indisponível agora.")
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
        title: qsTr("Revisar permissões")
        standardButtons: Dialog.NoButton
        onOpened: {
            core.beginHubReview()
            host.revision = core.hubApprovalRevision
            reviewAck.checked = false
            reviewAck.forceActiveFocus()
        }
        Text {
            text: host.plugin ? qsTr("%1 %2 · %3").arg(host.plugin.plugin_id).arg(host.plugin.semver).arg(host.plugin.publisher) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 700
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: qsTr("Estado do plugin: %1").arg(host.reviewState())
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: qsTr("Permissões que este manifesto pede:")
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600
            Layout.fillWidth: true
        }
        Repeater {
            model: host.plugin ? host.plugin.permissions : []
            delegate: Text {
                required property string modelData
                text: Theme.advanced ? qsTr("• %1 (%2)").arg(core.permissionLabel(modelData)).arg(modelData) : qsTr("• %1").arg(core.permissionLabel(modelData))
                textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
        }
        Text {
            visible: host.plugin !== null && (host.plugin.permissions || []).length === 0
            text: qsTr("Nenhuma permissão: aprovar não concede acesso a nada.")
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: qsTr("Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto.")
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            visible: Theme.advanced && host.plugin !== null
            text: host.plugin ? qsTr("Manifesto: %1…").arg(String(host.plugin.manifest_sha256 || "").substring(0, 12)) : ""
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: "monospace"; font.pixelSize: Theme.fontCaption
            Layout.fillWidth: true
        }
        GCheckbox {
            id: reviewAck
            objectName: "permReviewAck"
            text: core.hubPublisherVerified ? qsTr("Entendo as permissões deste plugin") : qsTr("Entendo que o publisher não foi autenticado")
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
                text: qsTr("Fechar")
                variant: "secondary"
                onClicked: reviewDlg.close()
            }
            GButton {
                objectName: "permApproveButton"
                variant: "primary"
                text: host.liveEntry() && host.liveEntry().permissions_approved === true ? qsTr("Permissões aprovadas") : qsTr("Aprovar estas permissões")
                enabled: core.hubApprovalAvailable && reviewAck.checked && host.plugin !== null && !(host.liveEntry() && host.liveEntry().permissions_approved === true)
                Accessible.name: host.plugin ? qsTr("Aprovar permissões de %1").arg(host.plugin.plugin_id) : qsTr("Aprovar permissões")
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
        title: qsTr("Revogar permissões")
        standardButtons: Dialog.NoButton
        onOpened: revokeCancel.forceActiveFocus()
        Text {
            text: host.plugin ? qsTr("Revogar permissões de %1? O plugin será desativado e o processo encerrado. Reativar exige nova aprovação.").arg(host.plugin.plugin_id) : ""
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
                text: qsTr("Cancelar")
                variant: "secondary"
                onClicked: revokeDlg.close()
            }
            GButton {
                objectName: "permRevokeConfirm"
                variant: "danger"
                text: qsTr("Revogar")
                enabled: core.pluginsAvailable && !!host.plugin && !host.quarantinedNow()
                Accessible.name: host.plugin ? qsTr("Revogar permissões de %1").arg(host.plugin.plugin_id) : qsTr("Revogar permissões")
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
        title: qsTr("Consentir escopos")
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
            text: qsTr("Escolha os escopos que esta conta pode usar. Nada é concedido sem sua marcação.")
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
                    text: Theme.advanced ? qsTr("%1 (%2)").arg(scopeRow.info.label).arg(scopeRow.modelData) : scopeRow.info.label
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
            text: qsTr("Escopo %1: cada chamada pode pedir aprovação forte.").arg(host.riskyPicked())
            textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            visible: host.picked === 0
            text: qsTr("Marque ao menos um escopo.")
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
                text: qsTr("Cancelar")
                variant: "secondary"
                onClicked: consentDlg.close()
            }
            GButton {
                objectName: "permConsentConfirm"
                variant: "primary"
                text: qsTr("Consentir escopos marcados")
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
        title: qsTr("Revogar acesso")
        standardButtons: Dialog.NoButton
        onOpened: revokeAccountCancel.forceActiveFocus()
        Text {
            text: host.account ? qsTr("Revogar o acesso da conta %1 no servidor? Os segredos locais são apagados, todos os escopos concedidos são retirados e as ferramentas MCP precisam de nova confiança. Para usar a conta de novo, conecte e consinta outra vez.").arg(host.account.label) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            visible: host.account !== null
            text: host.account ? qsTr("Escopos que serão retirados: %1.").arg(host.grantedLabels(host.account).join(", ") || qsTr("nenhum")) : ""
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
                text: qsTr("Cancelar")
                variant: "secondary"
                onClicked: revokeAccountDlg.close()
            }
            GButton {
                objectName: "permRevokeAccountConfirm"
                variant: "danger"
                text: qsTr("Revogar acesso")
                enabled: !!host.liveAccount() && L.connCan(core.connectionsBusy, "revoke", host.liveAccount())
                Accessible.name: host.account ? qsTr("Revogar acesso da conta %1").arg(host.account.label) : qsTr("Revogar acesso")
                Accessible.description: enabled ? "" : qsTr("Conta sem acesso concedido para revogar.")
                onClicked: {
                    core.connectionRevoke(host.account.id)
                    revokeAccountDlg.close()
                }
            }
        }
    }

    // Revogar um escopo concedido: o token fica; chamadas que precisam dele são recusadas até nova concessão.
    Modal {
        id: revokeScopeDlg
        objectName: "permRevokeScopeDialog"
        title: qsTr("Revogar escopo")
        standardButtons: Dialog.NoButton
        onOpened: revokeScopeCancel.forceActiveFocus()
        Text {
            text: host.account ? qsTr("Revogar o escopo %1 da conta %2? Chamadas que precisam dele ficam recusadas até você conceder de novo.").arg(L.connScopeLabel(core.connectionsProviders, host.account.provider, host.scopeId)).arg(host.account.label) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton {
                id: revokeScopeCancel
                objectName: "permRevokeScopeCancel"
                text: qsTr("Cancelar")
                variant: "secondary"
                onClicked: revokeScopeDlg.close()
            }
            GButton {
                objectName: "permRevokeScopeConfirm"
                variant: "danger"
                text: qsTr("Revogar escopo")
                enabled: !!host.liveAccount() && L.connCan(core.connectionsBusy, "revoke", host.liveAccount()) && host.scopeId.length > 0
                Accessible.name: qsTr("Revogar este escopo")
                onClicked: {
                    core.connectionRevokeScope(host.account.id, host.scopeId)
                    revokeScopeDlg.close()
                }
            }
        }
    }

    // D-P5 · Confiar em ferramenta MCP.
    Modal {
        id: trustDlg
        objectName: "permTrustDialog"
        title: qsTr("Confiar na ferramenta")
        standardButtons: Dialog.NoButton
        onOpened: trustCancel.forceActiveFocus()
        Text {
            text: host.account ? qsTr("Confiar em %1 do servidor %2? Cada chamada desta ferramenta ainda pede sua aprovação. A descrição vem do servidor e é só texto.").arg(host.toolName).arg(host.account.label) : ""
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
                text: qsTr("Cancelar")
                variant: "secondary"
                onClicked: trustDlg.close()
            }
            GButton {
                objectName: "permTrustConfirm"
                variant: "primary"
                text: qsTr("Confiar")
                enabled: core.connectionsAvailable && !core.connectionsBusy && host.toolName.length > 0
                Accessible.name: qsTr("Confiar na ferramenta %1").arg(host.toolName)
                onClicked: {
                    core.connectionTrustTools(host.account.id, JSON.stringify([host.toolName]))
                    trustDlg.close()
                }
            }
        }
    }
}
