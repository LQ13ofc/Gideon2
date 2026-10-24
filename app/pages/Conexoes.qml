import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Extensões > Conexões. Three parts: Contas (one card per account: scopes, consent, actions), Rotas (which route each
// purpose uses; planning runs nothing) and Nova conta. Nothing here grants a scope: consent is the user's own click, per scope.
PageFrame {
    id: page
    objectName: "connectionsPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "conexoes" && core.connectionsAvailable

    property string part: "contas"
    readonly property var purposesUsed: core.registryPurposes
    readonly property var visualPurposes: ["create_issue"]

    function opsFor(item) { var p = L.connProvider(core.connectionsProviders, item.provider); return p ? p.operations : [] }
    function scopeLabel(provider, scope) { return L.connScopeLabel(core.connectionsProviders, provider, scope) }
    function consentList(item) {
        // Reading the revision makes every binding that calls this re-evaluate after a checkbox toggle.
        var rev = AppState.connDraftRevision
        var out = []
        var pending = item.pending_scopes || []
        for (var i = 0; i < pending.length; i++) if (AppState.draftValue("#conn:" + item.id, pending[i]) === true) out.push(pending[i])
        return out
    }
    function visualOn(id) { return core.registryVisualAllowed.indexOf(id) >= 0 }

    PageHeader {
        title: "Conexões"
        subtitle: "Contas de serviços. Você concede cada escopo; escrita e ações públicas pedem aprovação."
    }
    Collapsible {
        title: "Como funciona"
        summary: "Gideon usa a API autorizada de cada serviço. Neste ambiente as contas são servidores falsos."
        Text {
            text: "Gideon usa a API autorizada de cada serviço. Você concede cada escopo; escrita e ações públicas pedem aprovação. Neste ambiente, todas as contas são servidores falsos."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
    }
    Text {
        objectName: "connectionsResult"
        visible: text.length > 0
        text: core.connectionsResult
        textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        Accessible.name: "Resultado das conexões: " + text
    }
    GProgressBar { objectName: "connectionsProgress"; visible: core.connectionsBusy; indeterminate: true; Layout.fillWidth: true; Accessible.name: "Operação de conexão em andamento" }
    Segmented {
        model: [{id: "contas", text: "Contas"}, {id: "rotas", text: "Rotas"}, {id: "nova", text: "Nova conta"}]
        currentId: page.part
        onActivated: function (id) { page.part = id }
    }

    // Nova conta: provider and a short label; the consent steps follow on the account card.
    Section {
        visible: page.part === "nova"
        title: "Nova conta"
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Select {
                id: connProviderPick
                objectName: "connectionProvider"
                model: L.connProviderChoices
                textRole: "text"
                valueRole: "id"
                Accessible.name: "Provedor da nova conta"
            }
            GTextField {
                id: connLabel
                objectName: "connectionLabel"
                Layout.fillWidth: true
                maximumLength: 64
                placeholderText: "Nome da conta (ex.: Casa)"
                Accessible.name: "Nome da nova conta"
            }
            GButton {
                objectName: "connectionAdd"
                variant: "primary"
                text: "Adicionar conta"
                Accessible.name: "Adicionar conta"
                enabled: !core.connectionsBusy && core.connectionLabelProblem(connLabel.text) === "" && core.connectionsItems.length < 8
                onClicked: core.connectionAdd(connProviderPick.currentValue, connLabel.text)
            }
        }
        Text {
            objectName: "connectionLabelProblem"
            visible: connLabel.text.length > 0 && core.connectionLabelProblem(connLabel.text).length > 0
            text: core.connectionLabelProblem(connLabel.text)
            textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
    }

    // Contas: one card per account.
    Section {
        visible: page.part === "contas"
        title: "Contas"
        Text {
            objectName: "connectionsEmpty"
            visible: core.connectionsItems.length === 0
            text: "Nenhuma conta ainda. Adicione uma na aba Nova conta."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Repeater {
            model: core.connectionsItems
            delegate: Card {
                id: connCard
                required property var modelData
                readonly property string cid: modelData.id
                Text { objectName: "connTitle_" + connCard.cid; text: modelData.label + " · " + L.connProviderName(modelData.provider); textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Badge { objectName: "connFake_" + connCard.cid; visible: modelData.fake === true; text: "SERVIDOR FALSO"; tone: "warning" }
                Text { objectName: "connStatus_" + connCard.cid; text: "Estado: " + L.connStatusText(modelData.status); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Estado da conta " + modelData.label + ": " + text }
                Text { objectName: "connAccount_" + connCard.cid; visible: !!modelData.account_ref; text: "Conta no serviço: " + (modelData.account_ref || ""); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { objectName: "connUserCode_" + connCard.cid; visible: modelData.status === "connecting" && !!modelData.user_code; text: "Código para confirmar no servidor: " + (modelData.user_code || ""); textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true; Accessible.name: "Código de confirmação: " + (modelData.user_code || "") }
                Text { objectName: "connGranted_" + connCard.cid; text: "Escopos concedidos: " + L.connScopeNames(modelData.granted_scopes); textFormat: Text.PlainText; color: Theme.success; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { objectName: "connPending_" + connCard.cid; visible: (modelData.pending_scopes || []).length > 0; text: "Escopos pedidos, aguardando seu consentimento: " + L.connScopeNames(modelData.pending_scopes); textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                // Consent is per scope. Nothing is pre-checked; the Core records only what is checked and sent.
                Repeater {
                    model: modelData.pending_scopes || []
                    delegate: GCheckbox {
                        required property string modelData
                        objectName: "connScope_" + connCard.cid + "_" + modelData
                        text: page.scopeLabel(connCard.modelData.provider, modelData) + " (" + modelData + ")"
                        checked: AppState.draftValue("#conn:" + connCard.cid, modelData) === true
                        onToggled: { AppState.setDraft("#conn:" + connCard.cid, modelData, checked); AppState.connDraftRevision++ }
                        Accessible.name: "Consentir escopo " + modelData + " de " + connCard.modelData.label
                    }
                }
                // Home Assistant: the long-lived token is typed once into a hidden field and sent to the Core; the field is cleared right after.
                RowLayout {
                    visible: connCard.modelData.provider === "homeassistant" && connCard.modelData.status === "connecting"
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    GTextField {
                        id: connTokenField
                        objectName: "connToken_" + connCard.cid
                        echoMode: TextInput.Password
                        inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoAutoUppercase | Qt.ImhNoPredictiveText
                        maximumLength: 256
                        Layout.fillWidth: true
                        placeholderText: "Token de longa duração do Home Assistant"
                        Accessible.name: "Token do Home Assistant de " + connCard.modelData.label
                    }
                    GButton {
                        objectName: "connSetToken_" + connCard.cid
                        variant: "primary"
                        text: "Enviar token"
                        Accessible.name: "Enviar token de " + connCard.modelData.label
                        enabled: !core.connectionsBusy && connTokenField.text.length >= 16 && connTokenField.text.length <= 256
                        onClicked: { core.connectionSetToken(connCard.cid, connTokenField.text); connTokenField.clear() }
                    }
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.space(8)
                    GButton { objectName: "connConsent_" + connCard.cid; visible: (modelData.pending_scopes || []).length > 0; variant: "primary"; text: "Consentir escopos marcados"; Accessible.name: "Consentir escopos marcados de " + modelData.label; enabled: !core.connectionsBusy && page.consentList(connCard.modelData).length > 0; onClicked: core.connectionConsent(connCard.cid, JSON.stringify(page.consentList(connCard.modelData))) }
                    GButton { objectName: "connConnect_" + connCard.cid; variant: "secondary"; text: "Conectar"; Accessible.name: "Conectar " + modelData.label; enabled: L.connCan(core.connectionsBusy, "connect", modelData); onClicked: core.connectionConnect(connCard.cid) }
                    GButton { objectName: "connRefresh_" + connCard.cid; variant: "ghost"; text: "Atualizar"; Accessible.name: "Atualizar " + modelData.label; enabled: L.connCan(core.connectionsBusy, "refresh", modelData); onClicked: core.connectionRefresh(connCard.cid) }
                    GButton { objectName: "connDisconnect_" + connCard.cid; variant: "secondary"; text: "Desconectar"; Accessible.name: "Desconectar " + modelData.label; enabled: L.connCan(core.connectionsBusy, "disconnect", modelData); onClicked: core.connectionDisconnect(connCard.cid) }
                    GButton { objectName: "connRevoke_" + connCard.cid; variant: "danger"; text: "Revogar"; Accessible.name: "Revogar acesso de " + modelData.label; enabled: L.connCan(core.connectionsBusy, "revoke", modelData); onClicked: core.connectionRevoke(connCard.cid) }
                    GButton { objectName: "connRemove_" + connCard.cid; variant: "danger"; text: "Remover"; Accessible.name: "Remover " + modelData.label; enabled: L.connCan(core.connectionsBusy, "remove", modelData); onClicked: core.connectionRemove(connCard.cid) }
                }
                // Tools the MCP server listed. The description is server text, shown as PlainText and never sent to the model.
                Text { objectName: "connToolsTitle_" + connCard.cid; visible: (modelData.tools || []).length > 0; text: "Ferramentas descobertas (a descrição vem do servidor e é só texto)"; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; font.weight: 600; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Repeater {
                    model: modelData.tools || []
                    delegate: ColumnLayout {
                        id: toolRow
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 2
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space(8)
                            Text { objectName: "connTool_" + connCard.cid + "_" + toolRow.modelData.name; text: toolRow.modelData.name + " · " + L.connToolRiskText(toolRow.modelData.risk) + " · " + L.connToolStateText(toolRow.modelData.state) + (toolRow.modelData.reason ? " (" + toolRow.modelData.reason + ")" : ""); textFormat: Text.PlainText; color: toolRow.modelData.state === "trusted" ? Theme.success : Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            GButton { objectName: "connTrust_" + connCard.cid + "_" + toolRow.modelData.name; visible: toolRow.modelData.state === "needs_reapproval"; variant: "secondary"; text: "Confiar"; Accessible.name: "Confiar na ferramenta " + toolRow.modelData.name + " de " + connCard.modelData.label; enabled: !core.connectionsBusy; onClicked: core.connectionTrustTools(connCard.cid, JSON.stringify([toolRow.modelData.name])) }
                        }
                        Text { objectName: "connToolDesc_" + connCard.cid + "_" + toolRow.modelData.name; visible: toolRow.modelData.description.length > 0; text: "Descrição do servidor: " + toolRow.modelData.description; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                Text { text: "Operações"; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; font.weight: 600; Layout.fillWidth: true }
                Repeater {
                    model: page.opsFor(connCard.modelData)
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Theme.space(8)
                        Text { objectName: "connOp_" + connCard.cid + "_" + modelData.name; text: modelData.name + " (" + L.connOpLabel(modelData.name) + ") · " + L.connRiskText(modelData.risk) + (L.connGranted(connCard.modelData, modelData.scope) ? "" : " · escopo não concedido"); textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        GButton { objectName: "connTest_" + connCard.cid + "_" + modelData.name; visible: modelData.risk === "read" && modelData.name !== "state.get"; variant: "ghost"; text: "Testar leitura"; Accessible.name: "Testar leitura " + modelData.name + " de " + connCard.modelData.label; enabled: L.connCanTest(core.connectionsBusy, connCard.modelData, modelData); onClicked: core.connectionCall(connCard.cid, modelData.name, "{}") }
                    }
                }
            }
        }
        Text {
            objectName: "connLastCall"
            visible: core.connectionLastCall.operation !== undefined
            text: "Última chamada: " + (core.connectionLastCall.operation || "") + " · " + (core.connectionLastCall.code ? core.codeMessage(core.connectionLastCall.code) : (core.connectionLastCall.outcome === "ok" ? "concluída" : core.connectionLastCall.outcome))
            textFormat: Text.PlainText; color: Theme.success; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            Accessible.name: "Última chamada de conexão: " + text
        }
    }

    // Rotas: the chosen route per purpose, the discarded ones with their reasons, and the visual-fallback switch (off by default).
    Section {
        objectName: "routesPanel"
        visible: page.part === "rotas" && core.registryAvailable
        title: "Rotas"
        Text {
            text: "Para cada finalidade o Core escolhe o melhor caminho por: autorização, segurança, suporte oficial, confiabilidade, privacidade e menos efeitos colaterais. Planejar não executa nada."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text { objectName: "routesResult"; visible: text.length > 0; text: core.registryResult; textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Resultado das rotas: " + text }
        Repeater {
            model: core.registryPurposes
            delegate: Card {
                id: routeCard
                required property var modelData
                readonly property string rid: modelData.id
                readonly property bool visualAllowed: page.visualPurposes.indexOf(rid) >= 0
                Text {
                    objectName: "routePurpose_" + routeCard.rid
                    text: routeCard.modelData.label + " · " + L.regChosenText(routeCard.modelData)
                    textFormat: Text.PlainText; color: routeCard.modelData.route_chosen ? Theme.success : Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; wrapMode: Text.WordWrap; Layout.fillWidth: true
                    Accessible.name: "Finalidade: " + text
                }
                Repeater {
                    model: routeCard.modelData.candidates
                    delegate: Text {
                        required property var modelData
                        objectName: "routeCandidate_" + routeCard.rid + "_" + modelData.route
                        text: (routeCard.modelData.route_chosen === modelData.route ? "Escolhida · " : "Descartada · ") + L.regRouteText(modelData.route) + " · " + L.regStatusText(modelData.status) + " · " + modelData.reason
                        textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                        Accessible.name: text
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    GButton { objectName: "routePlan_" + routeCard.rid; variant: "secondary"; text: "Planejar"; Accessible.name: "Planejar rota de " + routeCard.modelData.label; enabled: !core.registryBusy; onClicked: core.registryPlan(routeCard.rid) }
                    GButton {
                        objectName: "routeVisual_" + routeCard.rid
                        visible: routeCard.visualAllowed
                        variant: "ghost"
                        text: page.visualOn(routeCard.rid) ? "Desligar fallback visual (revogar)" : "Ligar fallback visual"
                        Accessible.name: text + " de " + routeCard.modelData.label
                        enabled: !core.registryBusy
                        onClicked: core.registryAllowVisual(routeCard.rid, !page.visualOn(routeCard.rid))
                    }
                }
                Text { objectName: "routeVisualState_" + routeCard.rid; visible: routeCard.visualAllowed; text: "Fallback visual: " + (page.visualOn(routeCard.rid) ? "ligado por você" : "desligado (padrão)"); textFormat: Text.PlainText; color: page.visualOn(routeCard.rid) ? Theme.warning : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true }
                Text { objectName: "routeVisualWarning_" + routeCard.rid; visible: routeCard.visualAllowed; text: core.registryVisualWarning; textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
        }
    }
}
