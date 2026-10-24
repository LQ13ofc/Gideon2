import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Assistente > Agente (needs the LLM plugin): the goal, the steps with their state, the budget, the final answer and
// the approvals the agent is waiting for. Abortar asks first: it cancels the chat in flight and the pending proposals.
PageFrame {
    id: page
    objectName: "agentPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "agente" && core.chatAvailable

    readonly property bool chatInFlight: core.chatState === "waiting" || core.chatState === "streaming"
    readonly property var agentProposals: core.toolProposals.filter(function (p) { return p.run_id !== undefined })
    readonly property int agentPending: agentProposals.filter(function (p) { return p.state === "pending" }).length
    readonly property string goalProblem: agentGoal.text.length > 0 ? core.agentGoalProblem(agentGoal.text) : ""
    readonly property bool canStart: core.chatAvailable && !core.agentActive && !page.chatInFlight && core.agentGoalProblem(agentGoal.text) === ""
    readonly property string startReason: {
        if (page.goalProblem.length > 0) return page.goalProblem
        if (core.agentActive) return "Já existe um agente em execução; aguarde ou aborte."
        if (page.chatInFlight) return "Aguarde a conversa terminar."
        return ""
    }

    function stepColor(state) {
        switch (state) {
        case "done": return Theme.success
        case "running": case "awaiting_approval": return Theme.info
        case "denied": case "failed": case "blocked": case "cancelled": case "stale": return Theme.error
        }
        return Theme.textMuted
    }

    Connections {
        target: core
        function onToolResultChanged() { decisions.sentId = "" }
    }
    QtObject {
        id: decisions
        property string sentId: ""
    }

    PageHeader {
        title: "Agente"
        subtitle: "Descreva um objetivo; o Gideon propõe passos e pede sua aprovação."
    }

    // The run state in words. Without a run, the page says so and nothing else is shown.
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(12)
        Text {
            text: "Estado:"
            visible: core.agentState.length > 0
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
        }
        Text {
            objectName: "agentBanner"
            visible: core.agentState.length > 0
            text: core.agentStateLabel
            textFormat: Text.PlainText
            color: core.agentState === "failed" || core.agentState === "blocked" ? Theme.error : Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            font.weight: 600
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: "Estado do agente: " + text
        }
        Text {
            objectName: "agentIdle"
            visible: core.agentState.length === 0
            text: "Nenhum agente ativo"
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            Layout.fillWidth: true
        }
        Text {
            visible: page.agentPending > 0
            text: page.agentPending === 1 ? "1 proposta pendente" : page.agentPending + " propostas pendentes"
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            font.weight: 600
        }
    }

    Section {
        title: "Objetivo"
        GTextField {
            id: agentGoal
            objectName: "agentGoal"
            Layout.fillWidth: true
            maximumLength: 1024
            placeholderText: "Descreva o objetivo em uma frase"
            Accessible.name: "Objetivo para o agente"
            enabled: !core.agentActive
            Component.onCompleted: text = AppState.draftValue("#agent", "goal")
            onTextEdited: AppState.setDraft("#agent", "goal", text)
            onAccepted: if (page.canStart) core.agentStart(agentGoal.text)
        }
        // B13 counter for the goal (1024 UTF-8 bytes, trimmed by the Core rule).
        Text {
            objectName: "agentGoalCounter"
            text: L.byteCounter(agentGoal.text, 1024)
            textFormat: Text.PlainText
            color: page.goalProblem.length > 0 ? Theme.warning : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
            Accessible.name: "Tamanho do objetivo: " + text
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Text {
                objectName: "agentGoalProblem"
                visible: text.length > 0
                text: page.startReason
                textFormat: Text.PlainText
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            GButton {
                objectName: "agentAbort"
                variant: "danger"
                text: "Abortar"
                Accessible.name: "Abortar agente"
                enabled: core.agentActive
                onClicked: abortDialog.open()
            }
            GButton {
                objectName: "agentStart"
                variant: "primary"
                text: "Iniciar"
                Accessible.name: "Iniciar agente"
                enabled: page.canStart
                onClicked: core.agentStart(agentGoal.text)
            }
        }
        Text {
            objectName: "agentResult"
            visible: core.agentResult.length > 0
            text: core.agentResult
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: "Aviso do agente: " + text
        }
    }

    // Budget line: steps, clocks and tokens of the live run (the Core's budget; the clock is the run's own deadline).
    function clock(ms) {
        if (ms === undefined || ms === null || ms < 0) return "--:--"
        var s = Math.floor(ms / 1000), m = Math.floor(s / 60)
        s = s % 60
        return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s
    }
    function budgetLine() {
        var b = core.agentBudget
        return "Passos " + (b.steps || 0) + "/" + (b.max_steps || 6)
            + " · Tempo " + page.clock(b.elapsed_ms !== undefined ? b.elapsed_ms : 0) + "/" + page.clock(b.max_run_ms)
            + " · Tokens " + (b.tokens_used || 0) + "/" + (b.tokens_max || 4096)
    }
    Section {
        title: "Passos e orçamento"
        Text {
            objectName: "agentBudget"
            text: page.budgetLine()
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
        }
        Text {
            visible: core.agentSteps.length === 0
            text: "Descreva um objetivo; o Gideon propõe passos e pede sua aprovação."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Repeater {
            model: core.agentSteps
            delegate: RowLayout {
                required property var modelData
                objectName: "agentStep_" + modelData.n + "_" + modelData.kind
                Layout.fillWidth: true
                spacing: Theme.space(14)
                Text {
                    text: String(modelData.n)
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.preferredWidth: Theme.space(24)
                }
                Text {
                    text: modelData.kind === "tool" ? "Ferramenta" : "Conversa"
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.preferredWidth: Theme.space(110)
                }
                Text {
                    visible: Theme.advanced
                    text: modelData.kind === "tool" ? (modelData.tool || "—") : "—"
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Text {
                    visible: Theme.advanced
                    text: L.agentRiskText(modelData.risk)
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    Layout.preferredWidth: Theme.space(110)
                }
                Text {
                    text: L.agentStepText(modelData.state)
                    textFormat: Text.PlainText
                    color: page.stepColor(modelData.state)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                    Layout.fillWidth: !Theme.advanced
                    Accessible.name: "Passo " + modelData.n + ", " + (modelData.kind === "tool" ? "ferramenta" : "conversa") + ", " + text
                }
                Text {
                    visible: Theme.advanced && modelData.code
                    text: modelData.code ? core.codeMessage(String(modelData.code)) : ""
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }
    }

    // The final answer (plain text only; it exists only once the run is done) and the approvals of the agent.
    Section {
        title: "Resposta final"
        Text {
            objectName: "agentAnswerEmpty"
            visible: core.agentAnswer.length === 0
            text: "A resposta aparece aqui quando o agente concluir."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            objectName: "agentAnswer"
            visible: core.agentAnswer.length > 0
            text: core.agentAnswer
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            Accessible.name: "Resposta final do agente"
        }
    }

    Section {
        title: "Aprovações do agente"
        visible: page.agentProposals.length > 0
        Repeater {
            model: page.agentProposals
            delegate: AProposalCard {
                required property var modelData
                proposal: modelData
                sending: decisions.sentId === modelData.proposal_id
                onDecide: function (proposalId, choice) {
                    decisions.sentId = proposalId
                    core.decideTool(proposalId, choice)
                }
            }
        }
    }

    // Abortar: the confirmation keeps Cancelar as the default; only the second button aborts.
    Modal {
        id: abortDialog
        objectName: "agentAbortDialog"
        title: "Abortar o agente?"
        Text {
            text: "O chat em andamento e as propostas pendentes deste agente serão cancelados. Ações já executadas não são desfeitas."
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
                objectName: "agentAbortConfirm"
                variant: "danger"
                text: "Abortar agente"
                Accessible.name: "Confirmar aborto do agente"
                onClicked: abortDialog.accept()
            }
        }
        onAccepted: core.agentAbort()
    }
}
