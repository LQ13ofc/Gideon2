import QtQuick
import QtQuick.Controls
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
    // The risk is decided on the Core's own key (read, state_changing, destructive, public), never on the translated word.
    readonly property string riskKey: isConnection ? "" : String(p.risk || "")
    readonly property bool highRisk: riskKey === "destructive" || riskKey === "public"
    readonly property bool mediumRisk: riskKey === "state_changing"
    readonly property string riskWord: riskKey === "read" ? qsTr("baixo") : mediumRisk ? qsTr("médio") : highRisk ? qsTr("alto") : ""
    readonly property string effectWord: isConnection ? "" : core.effectText(p.effect || ({}))
    readonly property color riskColor: highRisk ? Theme.error : mediumRisk ? Theme.warning : Theme.success

    function requestAuthorize() {
        if (highRisk) confirm.open()
        else card.decide(String(p.proposal_id), "authorize")
    }

    title: (isConnection ? qsTr("Conexão · %1").arg(L.connOpLabel(p.operation)) : qsTr("Ferramenta %1").arg(p.tool || ""))
        + " · " + (card.sending ? qsTr("enviando decisão ao Core") : L.toolStateText(p.state))

    Text {
        text: card.isConnection ? card.connectionText : qsTr("Alvo: %1").arg(p.plugin_id ? p.plugin_id : "Base")
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: !card.isConnection
        text: qsTr("Efeito: %1").arg(card.effectWord.length > 0 ? card.effectWord : qsTr("não informado pelo plugin"))
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
            text: qsTr("Risco:")
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
        }
        Badge {
            visible: card.isConnection === false && card.riskWord.length > 0
            text: card.riskWord
            tone: card.highRisk ? "error" : card.mediumRisk ? "warning" : "success"
        }
        Text {
            visible: card.isConnection || card.riskWord.length === 0
            text: card.isConnection ? L.connRiskText(p.risk) : qsTr("não declarado")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
        }
    }
    Text {
        visible: Theme.advanced && !card.isConnection
        text: qsTr("Argumentos: %1").arg(JSON.stringify(p.args || {}))
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WrapAnywhere
        Layout.fillWidth: true
    }
    Text {
        visible: p.reason !== null && p.reason !== undefined && String(p.reason).length > 0
        text: qsTr("Motivo: %1").arg(core.codeMessage(String(p.reason || "")))
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: p.result !== null && p.result !== undefined && String(p.result).length > 0
        text: qsTr("Resultado: %1").arg(String(p.result || ""))
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
            text: qsTr("Negar")
            enabled: !card.sending
            Accessible.name: qsTr("Negar %1 %2").arg(p.tool || "").arg(p.proposal_id)
            onClicked: card.decide(String(p.proposal_id), "deny")
        }
        GButton {
            objectName: card.idPrefix + "authorize_" + p.proposal_id
            visible: card.pending
            variant: "primary"
            text: qsTr("Autorizar")
            enabled: !card.sending
            Accessible.name: qsTr("Autorizar %1 %2").arg(p.tool || "").arg(p.proposal_id)
            onClicked: card.requestAuthorize()
        }
    }

    // High-risk confirmation (Q-3): Cancelar is the default focus; Escape cancels.
    Modal {
        id: confirm
        title: qsTr("Autorizar a ferramenta %1?").arg(p.tool || "")
        Text {
            text: qsTr("%1. Esta ação pode alterar dados.").arg(card.effectWord.length > 0 ? card.effectWord : qsTr("Efeito não informado pelo plugin"))
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
                text: qsTr("Autorizar")
                onClicked: confirm.accept()
            }
        }
        onAccepted: card.decide(String(card.p.proposal_id), "authorize")
    }
}
