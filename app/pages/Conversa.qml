import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Assistente > Conversa (needs the LLM plugin). Messages scroll inside the page; the input row sits under them.
// Tool proposals show their target, effect and risk, with Autorizar and Negar only while pending.
PageFrame {
    id: page
    objectName: "chatPage"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "conversa"

    function sendDraft() {
        var t = chatInput.text.trim()
        if (t.length === 0 || core.chatTextProblem(t) !== "") return
        core.sendChat(t)
    }
    function connProposalText(p) {
        var items = core.connectionsItems
        var item = null
        for (var i = 0; i < items.length; i++) if (items[i].id === p.connection_id) item = items[i]
        var account = item ? (item.account_ref ? item.label + " (" + item.account_ref + ")" : item.label) : "conta desconhecida"
        return "Conexão: " + (item ? L.connProviderName(item.provider) : "provedor desconhecido") + " · conta " + account + " · operação " + p.operation + " (" + L.connOpLabel(p.operation) + ") · risco " + L.connRiskText(p.risk)
    }

    Connections {
        target: core
        function onChatSent(sent) { if (chatInput.text.trim() === sent) { chatInput.text = ""; AppState.setDraft("#chat", "text", "") } }
    }

    PageHeader {
        title: "Conversa"
        subtitle: "Mensagens com o motor LLM. Propostas de ferramenta aparecem no meio da conversa."
    }
    Banner {
        objectName: "chatUnavailable"
        kind: "info"
        text: core.chatAvailable ? "" : "Motor LLM não está ativo. O plugin llm_engine é opcional: voz, wake e comandos da Base funcionam sem ele."
        actionText: "Ver em Extensões › Plugins"
        onActionRequested: Window.window.goPage("plugins")
    }
    Banner {
        objectName: "chatConsentHint"
        kind: "warn"
        visible: core.chatAvailable && core.llmConfig.cloud_consent !== true
        text: "Consentimento de nuvem desativado: envios são recusados até você marcá-lo em Motor LLM."
        actionText: "Abrir Motor LLM"
        onActionRequested: Window.window.openLlm()
    }

    Section {
        objectName: "chatPanel"
        title: "Mensagens"
        visible: core.chatAvailable
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "Estado: " + core.chatStateLabel
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                objectName: "chatState"
                Accessible.name: "Estado da conversa: " + core.chatStateLabel
                Layout.fillWidth: true
            }
        }
        ScrollView {
            id: chatScroll
            objectName: "chatMessages"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(240, Window.window ? Window.window.height - 430 : 240)
            clip: true
            ColumnLayout {
                id: messageColumn
                width: chatScroll.availableWidth
                spacing: Theme.space(12)
                // A new or growing message keeps the latest text in view.
                onHeightChanged: Qt.callLater(function () { var f = chatScroll.contentItem; f.contentY = Math.max(0, f.contentHeight - f.height) })
                Text {
                    objectName: "chatEmpty"
                    visible: core.chatMessages.length === 0 && core.chatState === "idle"
                    text: "Nenhuma mensagem ainda. Sugestões: \"Que horas são?\" ou \"Abrir o Brave\"."
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Repeater {
                    model: core.chatMessages
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        radius: Theme.radiusCard
                        color: modelData.role === "user" ? Theme.tint : Theme.surfaceVariant
                        border.width: 1
                        border.color: Theme.hairline
                        implicitHeight: bubble.implicitHeight + Theme.space(20)
                        ColumnLayout {
                            id: bubble
                            anchors.fill: parent
                            anchors.margins: Theme.space(10)
                            spacing: 4
                            Text {
                                text: (modelData.role === "user" ? "Você" : "Gideon") + (modelData.state === "cancelled" ? " · cancelada" : modelData.state === "error" ? " · erro" : "")
                                textFormat: Text.PlainText
                                color: Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontCaption
                            }
                            TextEdit {
                                text: modelData.text || "(sem texto)"
                                readOnly: true
                                selectByMouse: true
                                textFormat: TextEdit.PlainText
                                wrapMode: TextEdit.Wrap
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontBody
                                Layout.fillWidth: true
                                Accessible.name: (modelData.role === "user" ? "Mensagem enviada: " : "Resposta: ") + text
                            }
                        }
                    }
                }
                Rectangle {
                    objectName: "chatStreaming"
                    visible: core.chatState === "waiting" || core.chatState === "streaming"
                    Layout.fillWidth: true
                    radius: Theme.radiusCard
                    color: Theme.surfaceVariant
                    border.width: 1
                    border.color: Theme.accent
                    implicitHeight: streamColumn.implicitHeight + Theme.space(20)
                    ColumnLayout {
                        id: streamColumn
                        anchors.fill: parent
                        anchors.margins: Theme.space(10)
                        spacing: 4
                        Text { text: core.chatStateLabel; textFormat: Text.PlainText; color: Theme.textMuted; font.pixelSize: Theme.fontCaption; font.family: Theme.fontFamily }
                        TextEdit {
                            text: core.chatPartial || "Aguardando resposta…"
                            readOnly: true
                            selectByMouse: true
                            textFormat: TextEdit.PlainText
                            wrapMode: TextEdit.Wrap
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontBody
                            Layout.fillWidth: true
                            Accessible.name: "Resposta em andamento"
                        }
                    }
                }
            }
        }
        Text {
            objectName: "chatResult"
            visible: core.chatResult.length > 0
            text: core.chatResult
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: "Aviso da conversa: " + text
        }
        FieldLabel { text: "Mensagem" }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            GTextField {
                id: chatInput
                objectName: "chatInput"
                Layout.fillWidth: true
                maximumLength: 4096
                placeholderText: "Mensagem para o motor LLM"
                Accessible.name: "Mensagem para o motor LLM"
                enabled: core.chatAvailable && core.chatState !== "waiting" && core.chatState !== "streaming"
                Component.onCompleted: text = AppState.draftValue("#chat", "text")
                onTextEdited: AppState.setDraft("#chat", "text", text)
                onAccepted: page.sendDraft()
            }
            GButton {
                objectName: "chatSend"
                variant: "primary"
                text: "Enviar"
                Accessible.name: "Enviar mensagem ao motor LLM"
                enabled: core.chatAvailable && chatInput.enabled && core.chatTextProblem(chatInput.text) === ""
                onClicked: page.sendDraft()
            }
            GButton {
                objectName: "chatCancel"
                variant: "secondary"
                text: "Cancelar resposta"
                Accessible.name: "Cancelar resposta do motor LLM"
                enabled: core.chatState === "waiting" || core.chatState === "streaming"
                onClicked: core.cancelChat()
            }
        }
        Text {
            objectName: "chatInputProblem"
            visible: chatInput.text.length > 0 && core.chatTextProblem(chatInput.text).length > 0
            text: core.chatTextProblem(chatInput.text)
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    // Tool proposals: only pending ones offer decisions; Negar is listed first because it is the safe choice.
    Section {
        objectName: "toolPanel"
        title: "Propostas de ferramenta"
        visible: core.chatAvailable && core.toolProposals.length > 0
        Repeater {
            model: core.toolProposals
            delegate: Card {
                required property var modelData
                Text {
                    objectName: "toolTitle_" + modelData.proposal_id
                    text: "Ferramenta " + modelData.tool + " · " + L.toolStateText(modelData.state)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    objectName: "connProposal_" + modelData.proposal_id
                    visible: modelData.kind === "connection"
                    text: page.connProposalText(modelData)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                    Accessible.name: "Proposta de conexão: " + text
                }
                Text {
                    text: "Argumentos: " + JSON.stringify(modelData.args)
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WrapAnywhere
                    Layout.fillWidth: true
                }
                Text {
                    visible: modelData.reason !== null
                    text: "Motivo: " + core.codeMessage(modelData.reason || "")
                    textFormat: Text.PlainText
                    color: Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    visible: modelData.result !== null
                    text: "Resultado: " + (modelData.result || "")
                    textFormat: Text.PlainText
                    color: Theme.success
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                RowLayout {
                    visible: modelData.state === "pending"
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    Item { Layout.fillWidth: true }
                    GButton { objectName: "deny_" + modelData.proposal_id; text: "Negar"; variant: "secondary"; Accessible.name: "Negar " + modelData.tool + " " + modelData.proposal_id; onClicked: core.decideTool(modelData.proposal_id, "deny") }
                    GButton { objectName: "authorize_" + modelData.proposal_id; text: "Autorizar"; variant: "primary"; Accessible.name: "Autorizar " + modelData.tool + " " + modelData.proposal_id; onClicked: core.decideTool(modelData.proposal_id, "authorize") }
                }
            }
        }
        Text {
            objectName: "toolResult"
            visible: core.toolResult.length > 0
            text: core.toolResult
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
