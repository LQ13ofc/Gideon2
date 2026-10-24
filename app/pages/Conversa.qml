import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Assistente > Conversa (needs the LLM plugin). One list of messages that scrolls, the proposals of the conversation
// inline, and the input row under it. Cancelar (resposta) replaces Enviar only while a reply is in flight.
PageFrame {
    id: page
    objectName: "chatPage"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "conversa"

    readonly property bool inFlight: core.chatState === "waiting" || core.chatState === "streaming"
    readonly property var chatProposals: core.toolProposals.filter(function (p) { return p.run_id === undefined })
    readonly property string inputProblem: chatInput.text.length > 0 ? core.chatTextProblem(chatInput.text) : ""

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
        subtitle: "Converse com o motor LLM. Respostas e propostas aparecem aqui."
    }
    Banner {
        objectName: "chatUnavailable"
        kind: "info"
        visible: !core.chatAvailable
        text: "Motor LLM não está ativo. O plugin llm_engine é opcional: voz, wake e comandos da Base funcionam sem ele."
        actionText: "Ver em Extensões › Plugins"
        onActionRequested: Window.window.goPage("plugins")
    }
    Banner {
        objectName: "chatConsentHint"
        kind: "warn"
        visible: core.chatAvailable && core.llmConfig.cloud_consent !== true
        text: "Consentimento de nuvem desativado: envios são recusados até você marcá-lo em Extensões › Modelos LLM."
        actionText: "Abrir Modelos LLM"
        onActionRequested: Window.window.openLlm()
    }
    // The last answer came from the fallback model (Core flag and time only, no content). The notice lasts 60 s: a clock re-checks it.
    property double nowMs: Date.now()
    readonly property bool fallbackRecent: core.llmLastChat.used_fallback === true && (nowMs - Number(core.llmLastChat.at_ms || 0)) < 60000
    Timer {
        interval: 5000
        repeat: true
        running: page.visible && core.llmLastChat.used_fallback === true
        onTriggered: page.nowMs = Date.now()
    }
    Connections {
        target: core
        function onLlmChanged() { page.nowMs = Date.now() }
    }
    Banner {
        objectName: "chatFallbackNotice"
        kind: "info"
        visible: core.chatAvailable && page.fallbackRecent
        text: "Esta resposta veio do modelo reserva (fallback)."
    }

    // B12: the last turn failed with a Core code the user can fix in Provedor e chaves (the banner names the cause).
    Banner {
        objectName: "chatErrorBanner"
        kind: "warn"
        text: core.chatErrorBanner.text || ""
        actionText: core.chatErrorBanner.action || ""
        onActionRequested: Window.window.openLlm()
    }

    ColumnLayout {
        objectName: "chatPanel"
        visible: core.chatAvailable
        Layout.fillWidth: true
        spacing: Theme.space(12)

        // The state of the conversation, and the model in use. Plain text: no badge unless the cloud consent is missing.
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(12)
            Text {
                objectName: "chatState"
                text: "Estado da conversa: " + core.chatStateLabel
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.weight: 600
                Accessible.name: "Estado da conversa: " + core.chatStateLabel
                Layout.fillWidth: true
            }
            Text {
                text: "Modelo: " + ((core.modelsSelected && core.modelsSelected.model) ? core.modelsSelected.model : "não configurado")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
            }
        }

        ScrollView {
            id: chatScroll
            objectName: "chatMessages"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(260, Window.window ? Window.window.height - 430 : 260)
            clip: true
            ColumnLayout {
                id: messageColumn
                width: chatScroll.availableWidth
                spacing: Theme.space(12)
                // A new or growing message keeps the latest text in view.
                onHeightChanged: Qt.callLater(function () { var f = chatScroll.contentItem; f.contentY = Math.max(0, f.contentHeight - f.height) })

                // Empty conversation: the optional nature of the LLM, and two suggestions that only fill the input.
                ColumnLayout {
                    objectName: "chatEmpty"
                    visible: core.chatMessages.length === 0 && core.chatState === "idle"
                    Layout.fillWidth: true
                    spacing: Theme.space(12)
                    EmptyState {
                        iconName: "chat"
                        message: "Nenhuma mensagem ainda. O motor LLM é opcional: voz, wake e comandos da Base funcionam sem ele."
                    }
                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: Theme.space(8)
                        Chip {
                            objectName: "suggestionTime"
                            text: "Que horas são?"
                            onClicked: { chatInput.text = text; chatInput.forceActiveFocus() }
                        }
                        Chip {
                            objectName: "suggestionBrave"
                            text: "Abrir o Brave"
                            onClicked: { chatInput.text = text; chatInput.forceActiveFocus() }
                        }
                    }
                }

                Repeater {
                    model: core.chatMessages
                    delegate: Item {
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: bubble.implicitHeight
                        Rectangle {
                            id: bubble
                            readonly property bool mine: modelData.role === "user"
                            anchors.right: mine ? parent.right : undefined
                            anchors.left: mine ? undefined : parent.left
                            width: Math.min(parent.width * 0.9, Theme.space(760))
                            implicitHeight: bubbleColumn.implicitHeight + Theme.space(20)
                            radius: Theme.radiusCard
                            color: mine ? Theme.tint : Theme.surfaceVariant
                            border.width: 1
                            border.color: Theme.hairline
                            ColumnLayout {
                                id: bubbleColumn
                                anchors.fill: parent
                                anchors.margins: Theme.space(10)
                                spacing: 4
                                Text {
                                    text: (bubble.mine ? "Você" : "Gideon") + (modelData.state === "cancelled" ? " · cancelada" : modelData.state === "error" ? " · erro" : "")
                                    textFormat: Text.PlainText
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontCaption
                                    font.weight: 600
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
                                    Accessible.name: (bubble.mine ? "Mensagem enviada: " : "Resposta: ") + text
                                }
                            }
                        }
                    }
                }

                // The reply in progress: the partial text when there is one, else the wait.
                Rectangle {
                    objectName: "chatStreaming"
                    visible: page.inFlight
                    Layout.fillWidth: true
                    implicitHeight: streamColumn.implicitHeight + Theme.space(20)
                    radius: Theme.radiusCard
                    color: Theme.surfaceVariant
                    border.width: 1
                    border.color: Theme.hairline
                    ColumnLayout {
                        id: streamColumn
                        anchors.fill: parent
                        anchors.margins: Theme.space(10)
                        spacing: 4
                        Text { text: "Gideon · " + core.chatStateLabel; textFormat: Text.PlainText; color: Theme.textMuted; font.pixelSize: Theme.fontCaption; font.family: Theme.fontFamily; font.weight: 600 }
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

                // Proposals of the conversation (not the agent's: those are on Agente). Negar is listed first.
                Repeater {
                    model: page.chatProposals
                    delegate: AProposalCard {
                        required property var modelData
                        proposal: modelData
                        connectionText: page.connProposalText(modelData)
                        sending: decisions.sentId === modelData.proposal_id
                        onDecide: function (proposalId, choice) {
                            decisions.sentId = proposalId
                            core.decideTool(proposalId, choice)
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
                enabled: core.chatAvailable && !page.inFlight
                Component.onCompleted: text = AppState.draftValue("#chat", "text")
                onTextEdited: AppState.setDraft("#chat", "text", text)
                onAccepted: page.sendDraft()
            }
            GButton {
                objectName: "chatSend"
                visible: !page.inFlight
                variant: "primary"
                text: "Enviar"
                Accessible.name: "Enviar mensagem ao motor LLM"
                enabled: core.chatAvailable && chatInput.enabled && core.chatTextProblem(chatInput.text) === ""
                onClicked: page.sendDraft()
            }
            GButton {
                objectName: "chatCancel"
                visible: page.inFlight
                variant: "secondary"
                text: "Cancelar"
                Accessible.name: "Cancelar resposta"
                enabled: page.inFlight
                onClicked: core.cancelChat()
            }
        }
        // B13 counter for the chat turn (4096 UTF-8 bytes, the Core rule the problem text names).
        Text {
            objectName: "chatCounter"
            text: L.byteCounter(chatInput.text, 4096)
            textFormat: Text.PlainText
            color: page.inputProblem.length > 0 ? Theme.warning : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
            Accessible.name: "Tamanho da mensagem: " + text
        }
        // Enter sends. A problem with the text replaces that hint; while a reply is in flight it says why input is off.
        Text {
            objectName: "chatInputProblem"
            text: page.inputProblem.length > 0 ? page.inputProblem : (page.inFlight ? "Aguarde a resposta anterior." : "Enter envia.")
            textFormat: Text.PlainText
            color: page.inputProblem.length > 0 ? Theme.warning : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    QtObject {
        id: decisions
        property string sentId: ""
    }
    Connections {
        target: core
        function onToolResultChanged() { decisions.sentId = "" }
    }
}
