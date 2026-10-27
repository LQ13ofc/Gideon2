import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Extensões > Conexões. Parts: Contas (one card per account: scopes, consent, actions), Rotas (which route each purpose
// uses; planning runs nothing) and Nova conta. Nothing here grants a scope: consent is the user's own click, per scope.
PageFrame {
    id: page
    objectName: "connectionsPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "conexoes" && core.connectionsAvailable

    property string part: "contas"
    readonly property var accounts: core.connectionsItems
    readonly property int fakeCount: accounts.filter(function (c) { return c.fake === true }).length
    readonly property bool mixedFake: fakeCount > 0 && fakeCount < accounts.length
    readonly property int connectedCount: accounts.filter(function (c) { return c.status === "connected" }).length
    readonly property int pendingCount: accounts.filter(function (c) { return c.status === "connecting" || c.status === "expired" || c.status === "reauth_required" }).length
    readonly property bool wide: width > 900
    readonly property var visualPurposes: ["create_issue"]

    function visualOn(id) { return core.registryVisualAllowed.indexOf(id) >= 0 }
    // "1 conta" or "3 contas": the singular and plural texts are chosen by the count.
    function countText(n, one, many) { return (n === 1 ? one : many).arg(n) }
    function askRevoke(account) { revokeConfirm.account = account; revokeConfirm.open() }
    function askScopeRevoke(account, scope) { scopeRevokeConfirm.account = account; scopeRevokeConfirm.scope = scope; scopeRevokeConfirm.open() }
    function askRemove(account) { removeConfirm.account = account; removeConfirm.open() }
    function askTrust(account, tool) { trustConfirm.account = account; trustConfirm.tool = tool; trustConfirm.open() }
    function askVisual(purpose) { visualConfirm.purpose = purpose; visualConfirm.open() }
    function addReason() {
        if (core.connectionsBusy) return qsTr("Aguarde: outra operação de conexão está em andamento.")
        if (accounts.length >= 8) return qsTr("Limite de 8 contas atingido; remova uma conta antes.")
        if (connLabel.text.trim().length === 0) return qsTr("Digite um nome para a conta.")
        return ""
    }

    PageHeader {
        title: qsTr("Conexões")
        subtitle: qsTr("Contas de serviços pela API. Você concede cada escopo; escrita pede aprovação.")
        GButton {
            objectName: "connectionsNewAccount"
            variant: "primary"
            text: qsTr("Nova conta")
            Accessible.name: qsTr("Nova conta")
            onClicked: page.part = "nova"
        }
    }
    // The one notice of the page: the fake-server label is said once here, not on every card.
    Banner {
        kind: "warn"
        text: page.fakeCount === 0 ? "" : (page.mixedFake ? qsTr("SERVIDOR FALSO — sem credenciais reais. Contas com o selo usam servidores falsos.") : qsTr("SERVIDOR FALSO — sem credenciais reais. Neste ambiente, todas as contas são servidores falsos."))
    }
    CSummaryBar {
        text: qsTr("%1 · %2 · %3").arg(page.countText(page.accounts.length, qsTr("%1 conta"), qsTr("%1 contas"))).arg(page.countText(page.connectedCount, qsTr("%1 conectada"), qsTr("%1 conectadas"))).arg(page.countText(page.pendingCount, qsTr("%1 pendente"), qsTr("%1 pendentes")))
        Badge {
            visible: page.pendingCount > 0
            text: page.countText(page.pendingCount, qsTr("%1 pendente"), qsTr("%1 pendentes"))
            tone: "warning"
        }
    }
    Text {
        objectName: "connectionsResult"
        visible: text.length > 0
        text: core.connectionsResult
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Accessible.name: qsTr("Resultado das conexões: %1").arg(text)
    }
    GProgressBar {
        objectName: "connectionsProgress"
        visible: core.connectionsBusy
        indeterminate: true
        Layout.fillWidth: true
        Accessible.name: qsTr("Operação de conexão em andamento")
    }
    Segmented {
        model: [{id: "contas", text: qsTr("Contas")}, {id: "rotas", text: qsTr("Rotas")}, {id: "nova", text: qsTr("Nova conta")}]
        currentId: page.part
        onActivated: function (id) { page.part = id }
    }

    // Contas: one card per account, two columns when the window is wide.
    ColumnLayout {
        visible: page.part === "contas"
        Layout.fillWidth: true
        spacing: Theme.space(16)
        EmptyState {
            objectName: "connectionsEmpty"
            visible: page.accounts.length === 0
            iconName: "plug"
            message: qsTr("Nenhuma conta ainda. Adicione uma em Nova conta.")
            actionText: qsTr("Nova conta")
            onActionRequested: page.part = "nova"
        }
        GridLayout {
            visible: page.accounts.length > 0
            Layout.fillWidth: true
            columns: page.wide ? 2 : 1
            columnSpacing: Theme.space(16)
            rowSpacing: Theme.space(16)
            Repeater {
                model: page.accounts
                delegate: CAccountCard {
                    required property var modelData
                    account: modelData
                    showFake: page.mixedFake
                    onRevokeRequested: page.askRevoke(modelData)
                    onScopeRevokeRequested: function (scope) { page.askScopeRevoke(modelData, scope) }
                    onRemoveRequested: page.askRemove(modelData)
                    onTrustRequested: function (tool) { page.askTrust(modelData, tool) }
                }
            }
        }
    }

    // Rotas: the chosen route per purpose and the discarded ones with their reasons. Planning runs nothing.
    ColumnLayout {
        objectName: "routesPanel"
        visible: page.part === "rotas"
        Layout.fillWidth: true
        spacing: Theme.space(20)
        Text {
            visible: !core.registryAvailable
            text: qsTr("Rotas indisponíveis agora.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            Layout.fillWidth: true
        }
        Text {
            objectName: "routesIntro"
            visible: core.registryAvailable
            text: qsTr("Rotas: o Gideon escolhe a API autorizada quando há conta conectada com escopo. Nunca troca de rota para contornar token expirado, reautenticação ou escopo negado.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            objectName: "routesResult"
            visible: text.length > 0
            text: core.registryResult
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: qsTr("Resultado das rotas: %1").arg(text)
        }
        Repeater {
            model: core.registryAvailable ? core.registryPurposes : []
            delegate: ColumnLayout {
                id: purposeBlock
                required property var modelData
                readonly property string rid: modelData.id
                readonly property bool visualAllowed: page.visualPurposes.indexOf(rid) >= 0
                Layout.fillWidth: true
                spacing: Theme.space(8)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(12)
                    Text {
                        objectName: "routePurpose_" + purposeBlock.rid
                        text: purposeBlock.modelData.label + " · " + L.regChosenText(purposeBlock.modelData)
                        textFormat: Text.PlainText
                        color: purposeBlock.modelData.route_chosen ? Theme.text : Theme.warning
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSection
                        font.weight: 600
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                        Accessible.name: qsTr("Finalidade: %1").arg(text)
                    }
                    GButton {
                        objectName: "routePlan_" + purposeBlock.rid
                        variant: "secondary"
                        text: qsTr("Planejar")
                        Accessible.name: qsTr("Planejar rota de %1").arg(purposeBlock.modelData.label)
                        enabled: !core.registryBusy
                        onClicked: core.registryPlan(purposeBlock.rid)
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 1
                    color: Theme.hairline
                }
                // The visual fallback is off by default. Turning it on asks first; the switch keeps the Core's state until the Core answers.
                RowLayout {
                    visible: purposeBlock.visualAllowed
                    Layout.fillWidth: true
                    spacing: Theme.space(12)
                    Text {
                        objectName: "routeVisualState_" + purposeBlock.rid
                        text: qsTr("Fallback visual: %1").arg(page.visualOn(purposeBlock.rid) ? qsTr("ligado por você") : qsTr("desligado (padrão)"))
                        textFormat: Text.PlainText
                        color: page.visualOn(purposeBlock.rid) ? Theme.warning : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontHelp
                        Layout.fillWidth: true
                    }
                    Toggle {
                        objectName: "routeVisual_" + purposeBlock.rid
                        checked: page.visualOn(purposeBlock.rid)
                        enabled: !core.registryBusy
                        Accessible.name: qsTr("Permitir fallback visual de %1").arg(purposeBlock.modelData.label)
                        onClicked: {
                            var want = !page.visualOn(purposeBlock.rid)
                            checked = Qt.binding(function () { return page.visualOn(purposeBlock.rid) })
                            if (want) page.askVisual(purposeBlock.rid)
                            else core.registryAllowVisual(purposeBlock.rid, false)
                        }
                    }
                }
                Text {
                    objectName: "routeVisualWarning_" + purposeBlock.rid
                    visible: purposeBlock.visualAllowed
                    text: core.registryVisualWarning
                    textFormat: Text.PlainText
                    color: Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                // Candidates: chosen or discarded, with the Core's reason as written.
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(12)
                    Text { text: qsTr("Situação"); Layout.preferredWidth: 110; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption }
                    Text { text: qsTr("Rota"); Layout.preferredWidth: 180; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption }
                    Text { text: qsTr("Estado"); Layout.preferredWidth: 190; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption }
                    Text { text: qsTr("Motivo"); Layout.fillWidth: true; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption }
                }
                Repeater {
                    model: purposeBlock.modelData.candidates
                    delegate: RowLayout {
                        required property var modelData
                        readonly property bool chosen: purposeBlock.modelData.route_chosen === modelData.route
                        objectName: "routeCandidate_" + purposeBlock.rid + "_" + modelData.route
                        Layout.fillWidth: true
                        spacing: Theme.space(12)
                        Badge {
                            Layout.preferredWidth: 110
                            text: chosen ? qsTr("Escolhida") : qsTr("Descartada")
                            tone: chosen ? "success" : "neutral"
                        }
                        Text {
                            text: L.regRouteText(modelData.route)
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontHelp
                            wrapMode: Text.WordWrap
                            Layout.preferredWidth: 180
                        }
                        Text {
                            text: L.regStatusText(modelData.status)
                            textFormat: Text.PlainText
                            color: modelData.status === "available" ? Theme.success : Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontHelp
                            wrapMode: Text.WordWrap
                            Layout.preferredWidth: 190
                        }
                        Text {
                            text: modelData.reason
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontHelp
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                            Accessible.name: text
                        }
                    }
                }
            }
        }
    }

    // Nova conta: the provider and a short name; the consent steps follow on the account card.
    GridLayout {
        visible: page.part === "nova"
        Layout.fillWidth: true
        columns: page.wide ? 2 : 1
        columnSpacing: Theme.space(16)
        rowSpacing: Theme.space(16)
        Section {
            title: qsTr("Adicionar conta")
            Layout.alignment: Qt.AlignTop
            FieldLabel { text: qsTr("Provedor") }
            Select {
                id: connProviderPick
                objectName: "connectionProvider"
                Layout.fillWidth: true
                model: L.connProviderChoices
                textRole: "text"
                valueRole: "id"
                Accessible.name: qsTr("Provedor da nova conta")
            }
            FieldLabel { text: qsTr("Nome da conta (ex.: Casa)") }
            GTextField {
                id: connLabel
                objectName: "connectionLabel"
                Layout.fillWidth: true
                maximumLength: 64
                placeholderText: qsTr("ex.: Casa")
                Accessible.name: qsTr("Nome da nova conta")
            }
            Text {
                objectName: "connectionLabelProblem"
                visible: connLabel.text.length > 0 && core.connectionLabelProblem(connLabel.text).length > 0
                text: core.connectionLabelProblem(connLabel.text)
                textFormat: Text.PlainText
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(12)
                Text {
                    objectName: "connectionAddReason"
                    visible: text.length > 0
                    text: page.addReason()
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                GButton {
                    objectName: "connectionAdd"
                    variant: "primary"
                    text: qsTr("Adicionar conta")
                    Accessible.name: qsTr("Adicionar conta")
                    enabled: !core.connectionsBusy && core.connectionLabelProblem(connLabel.text) === "" && page.accounts.length < 8
                    onClicked: core.connectionAdd(connProviderPick.currentValue, connLabel.text)
                }
            }
        }
        Section {
            title: qsTr("Como conectar")
            Layout.alignment: Qt.AlignTop
            Repeater {
                model: [qsTr("Escolha o provedor e dê um nome à conta."), qsTr("Clique em Conectar. Para GitHub e Google, confirme o código no site do provedor."), qsTr("Marque só os escopos que você quer conceder e clique em Consentir escopos marcados."), qsTr("Escrita e ações públicas pedem aprovação a cada uso.")]
                delegate: RowLayout {
                    required property string modelData
                    required property int index
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    Text {
                        text: (index + 1) + "."
                        textFormat: Text.PlainText
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        Layout.alignment: Qt.AlignTop
                    }
                    Text {
                        text: modelData
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }

    Collapsible {
        title: qsTr("Como funciona")
        summary: qsTr("Gideon usa a API autorizada de cada serviço. Você concede cada escopo.")
        Text {
            text: qsTr("Gideon usa a API autorizada de cada serviço. Você concede cada escopo; escrita e ações públicas pedem aprovação. Neste ambiente, todas as contas são servidores falsos.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
    Text {
        objectName: "connLastCall"
        visible: core.connectionLastCall.operation !== undefined
        text: qsTr("Última chamada: %1 · %2").arg(core.connectionLastCall.operation || "").arg(core.connectionLastCall.code ? core.codeMessage(core.connectionLastCall.code) : (core.connectionLastCall.outcome === "ok" ? qsTr("concluída") : core.connectionLastCall.outcome))
        textFormat: Text.PlainText
        color: Theme.success
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Accessible.name: qsTr("Última chamada de conexão: %1").arg(text)
    }

    // Confirmations for the actions that change an account or a route. Cancelar is the default focus.
    Modal {
        id: revokeConfirm
        objectName: "connRevokeConfirm"
        property var account: null
        title: qsTr("Tem certeza?")
        Text {
            text: revokeConfirm.account ? qsTr("Revogar a conta %1? O acesso é revogado no servidor e as credenciais são apagadas do Gideon. Conectar de novo exige nova autorização.").arg(revokeConfirm.account.label) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "connRevokeConfirmButton"
            variant: "danger"
            text: qsTr("Revogar")
            Layout.alignment: Qt.AlignRight
            Accessible.name: qsTr("Revogar acesso")
            onClicked: revokeConfirm.accept()
        }
        onAccepted: { if (account) core.connectionRevoke(account.id) }
    }
    // One granted scope of an account. The token stays; the calls that need this scope are refused until it is granted again.
    Modal {
        id: scopeRevokeConfirm
        objectName: "connScopeRevokeConfirm"
        property var account: null
        property string scope: ""
        title: qsTr("Revogar este escopo?")
        Text {
            text: scopeRevokeConfirm.account ? qsTr("Revogar o escopo %1 da conta %2? As chamadas que precisam dele ficam recusadas até você conceder de novo. Os outros escopos não mudam.").arg(L.connScopeLabel(core.connectionsProviders, scopeRevokeConfirm.account.provider, scopeRevokeConfirm.scope)).arg(scopeRevokeConfirm.account.label) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "connScopeRevokeConfirmButton"
            variant: "danger"
            text: qsTr("Revogar escopo")
            Layout.alignment: Qt.AlignRight
            Accessible.name: qsTr("Revogar este escopo")
            onClicked: scopeRevokeConfirm.accept()
        }
        onAccepted: { if (account && scope) core.connectionRevokeScope(account.id, scope) }
    }
    Modal {
        id: removeConfirm
        objectName: "connRemoveConfirm"
        property var account: null
        title: qsTr("Tem certeza?")
        Text {
            text: removeConfirm.account ? qsTr("Remover a conta %1 do Gideon? A conta sai da lista.").arg(removeConfirm.account.label) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "connRemoveConfirmButton"
            variant: "danger"
            text: qsTr("Remover")
            Layout.alignment: Qt.AlignRight
            Accessible.name: qsTr("Remover conta")
            onClicked: removeConfirm.accept()
        }
        onAccepted: { if (account) core.connectionRemove(account.id) }
    }
    Modal {
        id: trustConfirm
        objectName: "connTrustConfirm"
        property var account: null
        property string tool: ""
        title: qsTr("Tem certeza?")
        Text {
            text: trustConfirm.tool ? qsTr("Confiar na ferramenta %1? Cada chamada ainda pede a sua aprovação.").arg(trustConfirm.tool) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "connTrustConfirmButton"
            variant: "primary"
            text: qsTr("Confiar")
            Layout.alignment: Qt.AlignRight
            Accessible.name: qsTr("Confiar na ferramenta %1").arg(trustConfirm.tool)
            onClicked: trustConfirm.accept()
        }
        onAccepted: { if (account && tool) core.connectionTrustTools(account.id, JSON.stringify([tool])) }
    }
    Modal {
        id: visualConfirm
        objectName: "routeVisualConfirm"
        property string purpose: ""
        title: qsTr("Tem certeza?")
        Text {
            text: qsTr("Permitir o fallback visual para criar issue? Ele dirige a tela só quando não há conta conectada. A publicação ainda pede sua aprovação.")
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "routeVisualConfirmButton"
            variant: "primary"
            text: qsTr("Permitir")
            Layout.alignment: Qt.AlignRight
            Accessible.name: qsTr("Permitir fallback visual")
            onClicked: visualConfirm.accept()
        }
        onAccepted: { if (purpose) core.registryAllowVisual(purpose, true) }
    }
}
