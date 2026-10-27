import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../shell"
import "../shell/Labels.js" as L

// One service account (S5): status, granted scopes as tags, the scopes waiting for consent (one checkbox each), the
// Home Assistant token field, and the actions. Consent is the user's own click per scope; revoke, remove and trust only
// ask for a confirmation: the page shows it and calls the Core after the user confirms.
Card {
    id: card
    property var account: ({})
    property bool showFake: false
    readonly property string cid: account.id || ""
    readonly property string label: account.label || ""
    readonly property string status: account.status || ""
    readonly property var pending: account.pending_scopes || []
    readonly property var granted: account.granted_scopes || []
    // WP-18b: `core` is a context property that is null when the card loads alone (the QML test host).
    readonly property bool connBusy: !!core && core.connectionsBusy === true
    // The live item by id from the Core snapshot: a refresh that discovers MCP tools replaces the item, and the delegate's
    // account object is not always re-bound to it. Reading core.connectionsItems re-evaluates on every connections change.
    readonly property var live: {
        var items = core.connectionsItems
        for (var i = 0; i < items.length; i++) if (items[i].id === cid) return items[i]
        return account
    }
    readonly property var tools: live.tools || []
    readonly property var ops: {
        var p = L.connProvider(core.connectionsProviders, account.provider)
        return p ? p.operations : []
    }
    property bool moreOpen: false
    signal revokeRequested()
    signal removeRequested()
    signal trustRequested(string tool)
    signal scopeRevokeRequested(string scope)

    // Reading AppState.connDraftRevision makes the consent bindings re-evaluate after a checkbox toggle.
    function consentList() {
        AppState.connDraftRevision
        var out = []
        for (var i = 0; i < pending.length; i++) if (AppState.draftValue("#conn:" + cid, pending[i]) === true) out.push(pending[i])
        return out
    }
    function badgeText(s) {
        switch (s) {
        case "connected": return qsTr("Conectado")
        case "connecting": return qsTr("Conectando")
        case "expired": return qsTr("Expirado")
        case "reauth_required": return qsTr("Reautenticar")
        case "offline": return qsTr("Offline")
        case "error": return qsTr("Erro")
        case "disconnected": return qsTr("Desconectado")
        default: return qsTr("Desconhecido")
        }
    }
    function badgeTone(s) {
        switch (s) {
        case "connected": return "success"
        case "connecting": return "info"
        case "expired": case "reauth_required": return "warning"
        case "error": return "error"
        default: return "neutral"
        }
    }
    // The highest risk among the operations that need this scope.
    function scopeRisk(scope) {
        var rank = {read: 0, write: 1, public: 2, destructive: 3}
        var best = "read"
        for (var i = 0; i < ops.length; i++) if (ops[i].scope === scope && rank[ops[i].risk] > rank[best]) best = ops[i].risk
        return best
    }
    function connectReason() {
        if (L.connCan(card.connBusy, "connect", account)) return ""
        if (card.connBusy) return qsTr("Aguarde: outra operação de conexão está em andamento.")
        if (status === "connected") return qsTr("Indisponível: a conta já está conectada.")
        return qsTr("Indisponível: conexão em andamento.")
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(10)
        Text {
            objectName: "connTitle_" + card.cid
            text: card.label + " · " + L.connProviderName(card.account.provider)
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSection
            font.weight: 600
            wrapMode: Text.WrapAnywhere
            Layout.fillWidth: true
        }
        Badge {
            objectName: "connFake_" + card.cid
            visible: card.showFake && card.account.fake === true
            text: qsTr("SERVIDOR FALSO")
            tone: "neutral"
        }
        Badge {
            objectName: "connStatusBadge_" + card.cid
            text: card.badgeText(card.status)
            tone: card.badgeTone(card.status)
        }
    }
    Text {
        objectName: "connStatus_" + card.cid
        text: qsTr("Estado: %1").arg(L.connStatusText(card.status))
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Accessible.name: qsTr("Estado da conta %1: %2").arg(card.label).arg(text)
    }
    Text {
        objectName: "connAccount_" + card.cid
        visible: !!card.account.account_ref
        text: qsTr("Conta no serviço: %1").arg(card.account.account_ref || "")
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        objectName: "connUserCode_" + card.cid
        visible: card.status === "connecting" && !!card.account.user_code
        text: qsTr("Código para confirmar no servidor: %1").arg(card.account.user_code || "")
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        font.weight: 600
        wrapMode: Text.WrapAnywhere
        Layout.fillWidth: true
        Accessible.name: qsTr("Código de confirmação: %1").arg(card.account.user_code || "")
    }

    // Granted scopes: tags. The plain line with the same scope ids is kept as the account's text record.
    Text {
        objectName: "connGranted_" + card.cid
        visible: false
        text: qsTr("Escopos concedidos: %1").arg(L.connScopeNames(card.granted))
    }
    Text {
        text: qsTr("Escopos concedidos:")
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        font.weight: 600
        Layout.fillWidth: true
    }
    Flow {
        Layout.fillWidth: true
        spacing: Theme.space(8)
        visible: card.granted.length > 0
        Repeater {
            model: card.granted
            delegate: CScopeChip {
                required property string modelData
                text: L.connScopeLabel(core.connectionsProviders, card.account.provider, modelData) + " (" + modelData + ")"
                revocable: L.connCan(card.connBusy, "revoke", card.account)
                onRevokeRequested: card.scopeRevokeRequested(modelData)
            }
        }
    }
    // When the Core granted the scopes (granted_at_ms, Unix ms); absent for older ledgers.
    Text {
        objectName: "connGrantedAt_" + card.cid
        visible: card.granted.length > 0 && L.grantedDate(card.account.grantedAtMs) !== ""
        text: qsTr("Concedido em %1").arg(L.grantedDate(card.account.grantedAtMs))
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontCaption
        Layout.fillWidth: true
    }
    Text {
        visible: card.granted.length === 0
        text: qsTr("Nenhum escopo concedido.")
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        Layout.fillWidth: true
    }

    // Consent: nothing is ticked by default; each scope is its own decision.
    Text {
        objectName: "connPending_" + card.cid
        visible: card.pending.length > 0
        text: qsTr("Escopos pedidos, aguardando seu consentimento:")
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Repeater {
        model: card.pending
        delegate: RowLayout {
            required property string modelData
            Layout.fillWidth: true
            spacing: Theme.space(12)
            GCheckbox {
                objectName: "connScope_" + card.cid + "_" + modelData
                Layout.fillWidth: true
                text: L.connScopeLabel(core.connectionsProviders, card.account.provider, modelData) + " (" + modelData + ")"
                checked: { AppState.connDraftRevision; return AppState.draftValue("#conn:" + card.cid, modelData) === true }
                onToggled: { AppState.setDraft("#conn:" + card.cid, modelData, checked); AppState.connDraftRevision++ }
                Accessible.name: qsTr("Consentir escopo %1 de %2").arg(modelData).arg(card.label)
            }
            Text {
                text: L.connRiskText(card.scopeRisk(modelData))
                textFormat: Text.PlainText
                color: card.scopeRisk(modelData) === "read" ? Theme.textMuted : Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
            }
        }
    }

    // Home Assistant: the long-lived token is typed once into a hidden field and sent to the Core; the field is cleared right after.
    FieldLabel {
        visible: card.account.provider === "homeassistant" && card.status === "connecting"
        text: qsTr("Token de longa duração do Home Assistant")
    }
    RowLayout {
        visible: card.account.provider === "homeassistant" && card.status === "connecting"
        Layout.fillWidth: true
        spacing: Theme.space(10)
        GTextField {
            id: tokenField
            objectName: "connToken_" + card.cid
            echoMode: TextInput.Password
            inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoAutoUppercase | Qt.ImhNoPredictiveText
            maximumLength: 256
            Layout.fillWidth: true
            placeholderText: qsTr("Cole o token aqui")
            Accessible.name: qsTr("Token do Home Assistant de %1").arg(card.label)
        }
        GButton {
            objectName: "connSetToken_" + card.cid
            variant: "primary"
            text: qsTr("Enviar token")
            Accessible.name: qsTr("Enviar token de %1").arg(card.label)
            enabled: !card.connBusy && tokenField.text.length >= 16 && tokenField.text.length <= 256
            onClicked: { core.connectionSetToken(card.cid, tokenField.text); tokenField.clear() }
        }
    }

    // Main actions. Advanced ones sit behind the ⋯ button (only with "Mostrar opções avançadas").
    Flow {
        Layout.fillWidth: true
        spacing: Theme.space(8)
        GButton {
            objectName: "connConsent_" + card.cid
            visible: card.pending.length > 0
            variant: "primary"
            text: qsTr("Consentir escopos marcados")
            Accessible.name: qsTr("Consentir escopos marcados de %1").arg(card.label)
            enabled: !card.connBusy && card.consentList().length > 0
            onClicked: core.connectionConsent(card.cid, JSON.stringify(card.consentList()))
        }
        GButton {
            objectName: "connConnect_" + card.cid
            variant: card.status === "connected" ? "secondary" : "primary"
            text: qsTr("Conectar")
            Accessible.name: qsTr("Conectar %1").arg(card.label)
            enabled: L.connCan(card.connBusy, "connect", card.account)
            onClicked: core.connectionConnect(card.cid)
        }
        IconButton {
            objectName: "connMore_" + card.cid
            visible: Theme.advanced
            iconName: "more"
            ToolTip.text: qsTr("Mais ações de %1").arg(card.label)
            onClicked: card.moreOpen = !card.moreOpen
        }
    }
    Text {
        objectName: "connConsentReason_" + card.cid
        visible: card.pending.length > 0 && card.consentList().length === 0
        text: qsTr("Marque ao menos um escopo para consentir.")
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        Layout.fillWidth: true
    }
    Text {
        objectName: "connConnectReason_" + card.cid
        visible: text.length > 0
        text: card.connectReason()
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    // Tools the MCP server listed. Outside the advanced column: the trust decision is needed whenever the Core holds tools.
    // The description is server text, shown as plain text and never sent to the model.
    Text {
        objectName: "connToolsTitle_" + card.cid
        visible: card.tools.length > 0
        text: qsTr("Ferramentas descobertas (a descrição vem do servidor e é só texto)")
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        font.weight: 600
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Repeater {
        model: card.tools
        delegate: ColumnLayout {
            id: toolRow
            required property var modelData
            Layout.fillWidth: true
            spacing: 2
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(8)
                Text {
                    objectName: "connTool_" + card.cid + "_" + toolRow.modelData.name
                    text: toolRow.modelData.name + " · " + L.connToolRiskText(toolRow.modelData.risk) + " · " + L.connToolStateText(toolRow.modelData.state) + (toolRow.modelData.reason ? " (" + toolRow.modelData.reason + ")" : "")
                    textFormat: Text.PlainText
                    color: toolRow.modelData.state === "trusted" ? Theme.success : Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                GButton {
                    objectName: "connTrust_" + card.cid + "_" + toolRow.modelData.name
                    visible: toolRow.modelData.state === "needs_reapproval"
                    variant: "secondary"
                    text: qsTr("Confiar")
                    Accessible.name: qsTr("Confiar na ferramenta %1 de %2").arg(toolRow.modelData.name).arg(card.label)
                    enabled: !card.connBusy
                    onClicked: card.trustRequested(toolRow.modelData.name)
                }
            }
            Text {
                objectName: "connToolDesc_" + card.cid + "_" + toolRow.modelData.name
                visible: (toolRow.modelData.description || "").length > 0
                text: qsTr("Descrição do servidor: %1").arg(toolRow.modelData.description || "")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }

    ColumnLayout {
        visible: Theme.advanced && card.moreOpen
        Layout.fillWidth: true
        spacing: Theme.space(10)
        Flow {
            Layout.fillWidth: true
            spacing: Theme.space(8)
            GButton { objectName: "connRefresh_" + card.cid; variant: "ghost"; text: qsTr("Atualizar"); Accessible.name: qsTr("Atualizar %1").arg(card.label); enabled: L.connCan(card.connBusy, "refresh", card.account); onClicked: core.connectionRefresh(card.cid) }
            GButton { objectName: "connDisconnect_" + card.cid; variant: "secondary"; text: qsTr("Desconectar"); Accessible.name: qsTr("Desconectar %1").arg(card.label); enabled: L.connCan(card.connBusy, "disconnect", card.account); onClicked: core.connectionDisconnect(card.cid) }
            GButton { objectName: "connRevoke_" + card.cid; variant: "danger"; text: qsTr("Revogar"); Accessible.name: qsTr("Revogar acesso de %1").arg(card.label); enabled: L.connCan(card.connBusy, "revoke", card.account); onClicked: card.revokeRequested() }
            GButton { objectName: "connRemove_" + card.cid; variant: "danger"; text: qsTr("Remover"); Accessible.name: qsTr("Remover %1").arg(card.label); enabled: L.connCan(card.connBusy, "remove", card.account); onClicked: card.removeRequested() }
        }

        Text {
            text: qsTr("Operações")
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            font.weight: 600
            Layout.fillWidth: true
        }
        Text {
            visible: card.ops.length === 0
            text: qsTr("Nenhuma operação disponível para este provedor.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
        }
        Repeater {
            model: card.ops
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Theme.space(8)
                Text {
                    objectName: "connOp_" + card.cid + "_" + modelData.name
                    text: qsTr("%1 (%2) · %3%4").arg(modelData.name).arg(L.connOpLabel(modelData.name)).arg(L.connRiskText(modelData.risk)).arg(L.connGranted(card.account, modelData.scope) ? "" : qsTr(" · escopo não concedido"))
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                GButton {
                    objectName: "connTest_" + card.cid + "_" + modelData.name
                    visible: modelData.risk === "read" && modelData.name !== "state.get" && modelData.needs_args === false
                    variant: "ghost"
                    text: qsTr("Testar leitura")
                    Accessible.name: qsTr("Testar leitura %1 de %2").arg(modelData.name).arg(card.label)
                    enabled: L.connCanTest(card.connBusy, card.account, modelData)
                    onClicked: core.connectionCall(card.cid, modelData.name, "{}")
                }
            }
        }
    }
}
