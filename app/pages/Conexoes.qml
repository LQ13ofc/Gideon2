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
    function countText(n, one, many) { return n + (n === 1 ? " " + one : " " + many) }
    function askRevoke(account) { revokeConfirm.account = account; revokeConfirm.open() }
    function askRemove(account) { removeConfirm.account = account; removeConfirm.open() }
    function askTrust(account, tool) { trustConfirm.account = account; trustConfirm.tool = tool; trustConfirm.open() }
    function askVisual(purpose) { visualConfirm.purpose = purpose; visualConfirm.open() }
    function addReason() {
        if (core.connectionsBusy) return "Aguarde: outra operação de conexão está em andamento."
        if (accounts.length >= 8) return "Limite de 8 contas atingido; remova uma conta antes."
        if (connLabel.text.trim().length === 0) return "Digite um nome para a conta."
        return ""
    }

    PageHeader {
        title: "Conexões"
        subtitle: "Contas de serviços pela API. Você concede cada escopo; escrita pede aprovação."
        GButton {
            objectName: "connectionsNewAccount"
            variant: "primary"
            text: "Nova conta"
            Accessible.name: "Nova conta"
            onClicked: page.part = "nova"
        }
    }
    // The one notice of the page: the fake-server label is said once here, not on every card.
    Banner {
        kind: "warn"
        text: page.fakeCount === 0 ? "" : (page.mixedFake ? "SERVIDOR FALSO — sem credenciais reais. Contas com o selo usam servidores falsos." : "SERVIDOR FALSO — sem credenciais reais. Neste ambiente, todas as contas são servidores falsos.")
    }
    CSummaryBar {
        text: page.countText(page.accounts.length, "conta", "contas") + " · " + page.connectedCount + " conectadas · " + page.pendingCount + " pendentes"
        Badge {
            visible: page.pendingCount > 0
            text: page.countText(page.pendingCount, "pendente", "pendentes")
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
        Accessible.name: "Resultado das conexões: " + text
    }
    GProgressBar {
        objectName: "connectionsProgress"
        visible: core.connectionsBusy
        indeterminate: true
        Layout.fillWidth: true
        Accessible.name: "Operação de conexão em andamento"
    }
    Segmented {
        model: [{id: "contas", text: "Contas"}, {id: "rotas", text: "Rotas"}, {id: "nova", text: "Nova conta"}]
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
            message: "Nenhuma conta ainda. Adicione uma em Nova conta."
            actionText: "Nova conta"
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
            text: "Rotas indisponíveis agora."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            Layout.fillWidth: true
        }
        Text {
            objectName: "routesIntro"
            visible: core.registryAvailable
            text: "Rotas: o Gideon escolhe a API autorizada quando há conta conectada com escopo. Nunca troca de rota para contornar token expirado, reautenticação ou escopo negado."
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
            Accessible.name: "Resultado das rotas: " + text
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
                        Accessible.name: "Finalidade: " + text
                    }
                    GButton {
                        objectName: "routePlan_" + purposeBlock.rid
                        variant: "secondary"
                        text: "Planejar"
                        Accessible.name: "Planejar rota de " + purposeBlock.modelData.label
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
                        text: "Fallback visual: " + (page.visualOn(purposeBlock.rid) ? "ligado por você" : "desligado (padrão)")
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
                        Accessible.name: "Permitir fallback visual de " + purposeBlock.modelData.label
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
                    Text { text: "Situação"; Layout.preferredWidth: 110; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption }
                    Text { text: "Rota"; Layout.preferredWidth: 180; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption }
                    Text { text: "Estado"; Layout.preferredWidth: 190; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption }
                    Text { text: "Motivo"; Layout.fillWidth: true; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption }
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
                            text: chosen ? "Escolhida" : "Descartada"
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
            title: "Adicionar conta"
            Layout.alignment: Qt.AlignTop
            FieldLabel { text: "Provedor" }
            Select {
                id: connProviderPick
                objectName: "connectionProvider"
                Layout.fillWidth: true
                model: L.connProviderChoices
                textRole: "text"
                valueRole: "id"
                Accessible.name: "Provedor da nova conta"
            }
            FieldLabel { text: "Nome da conta (ex.: Casa)" }
            GTextField {
                id: connLabel
                objectName: "connectionLabel"
                Layout.fillWidth: true
                maximumLength: 64
                placeholderText: "ex.: Casa"
                Accessible.name: "Nome da nova conta"
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
                    text: "Adicionar conta"
                    Accessible.name: "Adicionar conta"
                    enabled: !core.connectionsBusy && core.connectionLabelProblem(connLabel.text) === "" && page.accounts.length < 8
                    onClicked: core.connectionAdd(connProviderPick.currentValue, connLabel.text)
                }
            }
        }
        Section {
            title: "Como conectar"
            Layout.alignment: Qt.AlignTop
            Repeater {
                model: ["Escolha o provedor e dê um nome à conta.", "Clique em Conectar. Para GitHub e Google, confirme o código no site do provedor.", "Marque só os escopos que você quer conceder e clique em Consentir escopos marcados.", "Escrita e ações públicas pedem aprovação a cada uso."]
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
        title: "Como funciona"
        summary: "Gideon usa a API autorizada de cada serviço. Você concede cada escopo."
        Text {
            text: "Gideon usa a API autorizada de cada serviço. Você concede cada escopo; escrita e ações públicas pedem aprovação. Neste ambiente, todas as contas são servidores falsos."
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
        text: "Última chamada: " + (core.connectionLastCall.operation || "") + " · " + (core.connectionLastCall.code ? core.codeMessage(core.connectionLastCall.code) : (core.connectionLastCall.outcome === "ok" ? "concluída" : core.connectionLastCall.outcome))
        textFormat: Text.PlainText
        color: Theme.success
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Accessible.name: "Última chamada de conexão: " + text
    }

    // Confirmations for the actions that change an account or a route. Cancelar is the default focus.
    Modal {
        id: revokeConfirm
        objectName: "connRevokeConfirm"
        property var account: null
        title: "Tem certeza?"
        Text {
            text: revokeConfirm.account ? "Revogar a conta " + revokeConfirm.account.label + "? O acesso é revogado no servidor e as credenciais são apagadas do Gideon. Conectar de novo exige nova autorização." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "connRevokeConfirmButton"
            variant: "danger"
            text: "Revogar"
            Layout.alignment: Qt.AlignRight
            Accessible.name: "Revogar acesso"
            onClicked: revokeConfirm.accept()
        }
        onAccepted: { if (account) core.connectionRevoke(account.id) }
    }
    Modal {
        id: removeConfirm
        objectName: "connRemoveConfirm"
        property var account: null
        title: "Tem certeza?"
        Text {
            text: removeConfirm.account ? "Remover a conta " + removeConfirm.account.label + " do Gideon? A conta sai da lista." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "connRemoveConfirmButton"
            variant: "danger"
            text: "Remover"
            Layout.alignment: Qt.AlignRight
            Accessible.name: "Remover conta"
            onClicked: removeConfirm.accept()
        }
        onAccepted: { if (account) core.connectionRemove(account.id) }
    }
    Modal {
        id: trustConfirm
        objectName: "connTrustConfirm"
        property var account: null
        property string tool: ""
        title: "Tem certeza?"
        Text {
            text: trustConfirm.tool ? "Confiar na ferramenta " + trustConfirm.tool + "? Cada chamada ainda pede a sua aprovação." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "connTrustConfirmButton"
            variant: "primary"
            text: "Confiar"
            Layout.alignment: Qt.AlignRight
            Accessible.name: "Confiar na ferramenta " + trustConfirm.tool
            onClicked: trustConfirm.accept()
        }
        onAccepted: { if (account && tool) core.connectionTrustTools(account.id, JSON.stringify([tool])) }
    }
    Modal {
        id: visualConfirm
        objectName: "routeVisualConfirm"
        property string purpose: ""
        title: "Tem certeza?"
        Text {
            text: "Permitir o fallback visual para criar issue? Ele dirige a tela só quando não há conta conectada. A publicação ainda pede sua aprovação."
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "routeVisualConfirmButton"
            variant: "primary"
            text: "Permitir"
            Layout.alignment: Qt.AlignRight
            Accessible.name: "Permitir fallback visual"
            onClicked: visualConfirm.accept()
        }
        onAccepted: { if (purpose) core.registryAllowVisual(purpose, true) }
    }
}
