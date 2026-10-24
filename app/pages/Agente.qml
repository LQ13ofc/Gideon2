import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Assistente > Agente (needs the LLM plugin): goal, the steps with their state, the budget, the final answer.
PageFrame {
    id: page
    objectName: "agentPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "agente" && core.chatAvailable

    PageHeader {
        title: "Agente"
        subtitle: "Descreva um objetivo; o Gideon propõe passos e pede sua aprovação."
    }

    // Banner: the run state in words, with the Core code when the run ended on one. Empty without a run.
    Banner {
        objectName: "agentBanner"
        kind: core.agentState === "failed" || core.agentState === "blocked" ? "error" : "info"
        text: core.agentState.length > 0 ? core.agentStateLabel : ""
        Accessible.name: "Estado do agente: " + text
    }
    Text {
        objectName: "agentBudget"
        visible: core.agentState.length > 0
        text: "Tokens: " + (core.agentBudget.tokens_used || 0) + " de " + (core.agentBudget.tokens_max || 0)
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontCaption
        Layout.fillWidth: true
    }

    Section {
        title: "Objetivo"
        FieldLabel { text: "Objetivo" }
        GTextField {
            id: agentGoal
            objectName: "agentGoal"
            Layout.fillWidth: true
            maximumLength: 1024
            placeholderText: "Objetivo para o agente"
            Accessible.name: "Objetivo para o agente"
            enabled: !core.agentActive
            Component.onCompleted: text = AppState.draftValue("#agent", "goal")
            onTextEdited: AppState.setDraft("#agent", "goal", text)
        }
        Text {
            objectName: "agentGoalProblem"
            visible: agentGoal.text.length > 0 && core.agentGoalProblem(agentGoal.text).length > 0
            text: core.agentGoalProblem(agentGoal.text)
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton { objectName: "agentAbort"; text: "Abortar"; variant: "secondary"; Accessible.name: "Abortar agente"; enabled: core.agentActive; onClicked: core.agentAbort() }
            GButton { objectName: "agentStart"; text: "Iniciar"; variant: "primary"; Accessible.name: "Iniciar agente"; enabled: core.chatAvailable && !core.agentActive && core.agentGoalProblem(agentGoal.text) === ""; onClicked: core.agentStart(agentGoal.text) }
        }
    }

    Section {
        title: "Passos"
        visible: core.agentSteps.length > 0
        Repeater {
            model: core.agentSteps
            delegate: ListRow {
                required property var modelData
                objectName: "agentStep_" + modelData.n + "_" + modelData.kind
                title: "Passo " + modelData.n + " · " + (modelData.kind === "tool" ? "ferramenta " + (modelData.tool || "?") + " · risco " + L.agentRiskText(modelData.risk) : "modelo")
                detail: L.agentStepText(modelData.state) + (modelData.code ? " · " + core.codeMessage(modelData.code) : "")
            }
        }
    }

    // The final answer is model text: PlainText only, never rich text.
    Section {
        title: "Resposta"
        visible: core.agentAnswer.length > 0
        Text {
            objectName: "agentAnswer"
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
