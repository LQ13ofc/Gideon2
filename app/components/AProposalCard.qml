import QtQuick
import QtQuick.Layouts
import "../theme"
import "../components"
import "../shell/Labels.js" as L

// One tool proposal as an object (Card): target, effect, risk, and Negar / Autorizar while it is pending.
// Autorizar on a high-risk proposal asks first in a dialog whose default focus is Cancelar. The card never talks
// to the bridge: it emits decide(proposalId, decision) and the page sends it through core.decideTool.
// idPrefix keeps objectNames unique when the same proposal is also shown on another page.
Card {
    id: card
    property var proposal: ({})
    property string idPrefix: ""
    property bool sending: false
    property string connectionText: ""
    signal decide(string proposalId, string decision)

    readonly property var p: proposal || ({})
    readonly property bool isConnection: p.kind === "connection"
    readonly property bool pending: p.state === "pending"
    readonly property string riskWord: isConnection ? "" : core.riskText(String(p.risk || ""))
    readonly property string effectWord: isConnection ? "" : core.effectText(p.effect || ({}))
    readonly property color riskColor: riskWord === "alto" ? Theme.error : riskWord === "médio" ? Theme.warning : Theme.success

    function requestAuthorize() {
        if (riskWord === "alto") confirm.open()
        else card.decide(String(p.proposal_id), "authorize")
    }

    title: (isConnection ? "Conexão · " + L.connOpLabel(p.operation) : "Ferramenta " + (p.tool || "")) + " · " + (card.sending ? "enviando decisão ao Core" : L.toolStateText(p.state))

    Text {
        text: card.isConnection ? card.connectionText : "Alvo: " + (p.plugin_id ? p.plugin_id : "Base")
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: !card.isConnection
        text: "Efeito: " + (card.effectWord.length > 0 ? card.effectWord : "não informado pelo plugin")
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(8)
        Text {
            text: "Risco:"
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
        }
        Badge {
            visible: card.isConnection === false && card.riskWord.length > 0
            text: card.riskWord
            tone: card.riskWord === "alto" ? "error" : card.riskWord === "médio" ? "warning" : "success"
        }
        Text {
            visible: card.isConnection || card.riskWord.length === 0
            text: card.isConnection ? L.connRiskText(p.risk) : "não declarado"
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
        }
    }
    Text {
        visible: Theme.advanced && !card.isConnection
        text: "Argumentos: " + JSON.stringify(p.args || {})
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WrapAnywhere
        Layout.fillWidth: true
    }
    Text {
        visible: p.reason !== null && p.reason !== undefined && String(p.reason).length > 0
        text: "Motivo: " + core.codeMessage(String(p.reason || ""))
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: p.result !== null && p.result !== undefined && String(p.result).length > 0
        text: "Resultado: " + String(p.result || "")
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    RowLayout {
        visible: card.pending
        Layout.fillWidth: true
        spacing: Theme.space(10)
        Item { Layout.fillWidth: true }
        GButton {
            objectName: card.idPrefix + "deny_" + p.proposal_id
            visible: card.pending
            variant: "danger"
            text: "Negar"
            enabled: !card.sending
            Accessible.name: "Negar " + (p.tool || "") + " " + p.proposal_id
            onClicked: card.decide(String(p.proposal_id), "deny")
        }
        GButton {
            objectName: card.idPrefix + "authorize_" + p.proposal_id
            visible: card.pending
            variant: "primary"
            text: "Autorizar"
            enabled: !card.sending
            Accessible.name: "Autorizar " + (p.tool || "") + " " + p.proposal_id
            onClicked: card.requestAuthorize()
        }
    }

    // High-risk confirmation (Q-3): Cancelar is the default focus; Escape cancels.
    Modal {
        id: confirm
        title: "Autorizar a ferramenta " + (p.tool || "") + "?"
        Text {
            text: (card.effectWord.length > 0 ? card.effectWord : "Efeito não informado pelo plugin") + ". Esta ação pode alterar dados."
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton {
                objectName: card.idPrefix + "confirmAuthorize_" + p.proposal_id
                variant: "primary"
                text: "Autorizar"
                onClicked: confirm.accept()
            }
        }
        onAccepted: card.decide(String(card.p.proposal_id), "authorize")
    }
}
