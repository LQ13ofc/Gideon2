import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L
import "../shell/ActivityRows.js" as A

// Assistente > Hoje: the state of the Gideon in one sentence (orb + phrase), the oldest pending proposal, one command
// line, the last interaction and the recent activity. Every value is a Core property; nothing here is decorative.
PageFrame {
    id: page
    objectName: "page_hoje"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "hoje"

    property var cachedEvents: []
    readonly property var pending: core.toolProposals.filter(function (p) { return p.state === "pending" })
    readonly property var oldest: pending.length > 0 ? pending[0] : ({})
    readonly property var wakeChoice: L.activeWake(core.wakeChoices, core.snapshotPack.active_phrase)
    readonly property bool textTypeable: core.connected && core.textAvailable && core.sessionId.length === 0
    readonly property string typeReason: {
        if (!core.connected) return "Indisponível: Core desconectado."
        if (core.sessionId.length > 0) return "Indisponível: uma sessão de voz está em andamento."
        if (core.state === "safe_mode" || core.state === "restart_required") return "Indisponível: o Core precisa de atenção."
        if (!core.textAvailable) return "Indisponível: a entrada de texto só existe no perfil de teste."
        return ""
    }
    // B13: the Core rule for the command line (1..512 UTF-8 bytes, no control characters); a problem disables Enviar and says why.
    readonly property string inputProblem: input.text.length > 0 ? core.commandProblem(input.text) : ""
    readonly property bool canSend: textTypeable && input.text.trim().length > 0 && inputProblem.length === 0

    // WakeDetected: the Core's last wake detection (audio.live.last_detection, Core clock in ms) is younger than 2.5 s and
    // no words of this session are on screen yet. `nowMs` is re-read 4 times a second while the Core captures.
    property real nowMs: Date.now()
    Timer {
        interval: 250
        repeat: true
        running: core.state === "capturing"
        triggeredOnStart: true
        onTriggered: page.nowMs = Date.now()
    }
    readonly property var lastDetection: (core.audioLive && core.audioLive.last_detection) ? core.audioLive.last_detection : null
    readonly property bool wakeFresh: lastDetection !== null && core.subtitle.length === 0
        && lastDetection.at_ms > nowMs - 2500 && lastDetection.at_ms <= nowMs + 1000
    // Acting: the agent step the Core marks as running (its tool name is the Core's own).
    readonly property var runningStep: {
        var steps = core.agentSteps
        for (var i = steps.length - 1; i >= 0; i--) {
            if (steps[i].state === "running" && steps[i].tool) return steps[i]
        }
        return null
    }
    // A command that finished without a verified receipt is an error until the next action (10-assistente.md §2.3).
    readonly property bool commandFailed: core.result.length > 0 && !core.resultVerified

    function hudOf(mode, phrase, sub, tone, opts) {
        var o = opts || {}
        return {mode: mode, phrase: phrase, sub: sub, tone: tone, dim: o.dim === true, cancel: o.cancel || "",
                tool: o.tool || "", progress: o.progress === undefined ? -1 : o.progress, steps: o.steps || "",
                transcript: o.transcript === true, receipt: o.receipt || null}
    }
    // The HUD in one value: a mode for the orb and the words of the state. Order = the priorities of 10-assistente.md §2.2
    // with the nine Notion states (first true wins). Every field comes from a Core property; nothing is invented.
    function describeHud() {
        var budget = core.agentBudget || {}
        var agentRun = core.agentActive
        var progress = (agentRun && budget.max_steps > 0) ? Math.min(1, budget.steps / budget.max_steps) : -1
        var steps = (agentRun && budget.max_steps > 0) ? "Passo " + budget.steps + " de " + budget.max_steps : ""
        var step = page.runningStep
        var toolName = step ? String(step.tool) : ""
        var cancelAgent = agentRun ? "agent" : ""
        if (!core.connected) return hudOf("idle", "Core desconectado", "Tentando reconectar…", "muted", {dim: true})
        var s = core.state
        if (s === "safe_mode") return hudOf("error", "Modo seguro", "Abra Diagnóstico › Recuperação para reparar.", "warning")
        if (s === "restart_required") return hudOf("error", "Reinício necessário", "Reinicie o Core para aplicar a alteração.", "warning")
        if (s === "capturing") {
            if (page.wakeFresh) return hudOf("wake", "Gideon ativado", "Pode falar. Cancelar encerra a sessão.", "info", {cancel: "session"})
            return hudOf("listening", "Ouvindo…", "Fale agora. Cancelar encerra a sessão.", "info", {cancel: "session", transcript: true})
        }
        if (s === "transcribing") return hudOf("transcribing", "Transcrevendo…", "Processando o que você disse.", "info", {cancel: "session", transcript: true})
        if (s === "executing") return hudOf("acting", "Executando…", core.agentState === "waiting_tool" ? "Ferramenta do agente em execução." : "Executando o comando.", "info",
                                            {cancel: "session", tool: toolName, progress: progress, steps: steps, transcript: true})
        if (s === "speaking") return hudOf("speaking", "Falando…", "Resposta em voz alta. Cancelar interrompe.", "info", {cancel: "session", transcript: true})
        if (s !== "idle") return hudOf("error", "Erro", "Estado do Core não reconhecido.", "error")
        if (page.pending.length > 0 || core.agentState === "awaiting_approval") {
            var asked = page.pending.length > 0 ? "Ferramenta " + (page.oldest.tool || "") + " precisa da sua decisão." : "O agente aguarda a sua decisão."
            return hudOf("confirm", "Aguardando sua aprovação", asked, "warning", {cancel: cancelAgent})
        }
        if (core.agentState === "waiting_tool") return hudOf("acting", "Executando…", "Ferramenta do agente em execução.", "info",
                                                              {cancel: cancelAgent, tool: toolName, progress: progress, steps: steps})
        if (core.chatState === "waiting" || core.chatState === "streaming" || core.agentState === "thinking") {
            var waiting = core.chatState === "waiting" ? "Aguardando o motor LLM." : core.chatState === "streaming" ? "Recebendo a resposta." : "O agente planeja o próximo passo."
            return hudOf("thinking", "Pensando…", waiting, "info", {cancel: agentRun ? "agent" : "chat", progress: progress, steps: steps})
        }
        if (core.chatState === "error") return hudOf("error", "Erro", core.chatResult.length > 0 ? core.chatResult : "A última resposta falhou.", "error",
                                                    {receipt: {text: "Falhou", ok: false}})
        if (core.agentState === "failed" || core.agentState === "blocked") return hudOf("error", "Erro", core.agentStateLabel, "error",
                                                                                        {receipt: {text: "Falhou", ok: false}})
        if (page.commandFailed) return hudOf("error", "Erro", core.result, "error", {receipt: {text: "Falhou", ok: false}})
        var receipt = null
        if (core.resultVerified) receipt = {text: "Concluído · " + core.result, ok: true}
        else if (core.agentState === "done") receipt = {text: "Concluído", ok: true}
        return hudOf("idle", "Pronto para ouvir", "Diga 'Hey Gideon' ou digite um comando.", "normal", {receipt: receipt})
    }
    readonly property var hud: describeHud()
    readonly property color hudColor: hud.tone === "warning" ? Theme.warning : hud.tone === "error" ? Theme.error : hud.tone === "muted" ? Theme.textMuted : Theme.text

    // The Cancel of the HUD: the one live thing the Core can stop in this state (voice session, chat reply or agent run).
    function cancelActive() {
        if (hud.cancel === "session") core.cancel()
        else if (hud.cancel === "agent") core.agentAbort()
        else if (hud.cancel === "chat") core.cancelChat()
    }

    // Recent activity: the three newest rows of the timeline (same rules as Atividade, filter Tudo).
    readonly property var recent: A.eventRows(cachedEvents).slice(0, 3)

    function submit() { if (page.canSend) core.submitText(input.text) }

    // Keeps the last list the Core sent while it is away (Atividade keeps the same rule).
    function remember() { if (core.connected) cachedEvents = core.events }
    Component.onCompleted: remember()
    Connections {
        target: core
        function onTextSent(sent) { if (input.text === sent) input.text = "" }
        function onEventsChanged() { page.remember() }
    }

    PageHeader {
        title: "Hoje"
        subtitle: "Como o Gideon está agora e um comando para ele."
    }

    // Status chips: each one opens the setting that owns the value. The pending count is the only text on this line.
    Flow {
        Layout.fillWidth: true
        spacing: Theme.space(8)
        Text {
            objectName: "pendingCount"
            visible: page.pending.length > 0
            text: page.pending.length === 1 ? "1 proposta pendente" : page.pending.length + " propostas pendentes"
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            font.weight: 600
        }
        Chip {
            objectName: "chipWake"
            text: !core.snapshotPack.active_phrase ? "Wake: indisponível"
                : "Wake: " + L.wakeText(core.snapshotPack) + (page.wakeChoice ? (page.wakeChoice.qualification === "dev_qualified" ? " · em desenvolvimento" : " · requer prova de conceito") : "")
            onClicked: Window.window.goPage("cfg_voz")
        }
        Chip {
            objectName: "chipEntrada"
            // B16: the real device name only while the live microphone listens (A6 consent); otherwise the virtual PCM the wake uses.
            text: core.wakeChoices.length === 0 ? "Entrada: indisponível"
                : (core.audioLive.enabled === true ? "Entrada: " + core.audioInputLabel : "Entrada: PCM virtual")
            onClicked: Window.window.goPage("cfg_dispositivos")
        }
        Chip {
            objectName: "chipModo"
            text: !core.chatAvailable ? "Modo: Base, sem LLM"
                : "Modo: Base + LLM (" + ((core.modelsSelected && core.modelsSelected.model) ? core.modelsSelected.model : "sem modelo") + ")"
            onClicked: Window.window.goPage(core.chatAvailable ? "modelos" : "plugins")
        }
    }

    // B12: the last chat turn failed with a Core code the user can fix in Provedor e chaves.
    Banner {
        objectName: "hojeChatError"
        kind: "warn"
        text: core.chatErrorBanner.text || ""
        actionText: core.chatErrorBanner.action || ""
        onActionRequested: Window.window.openLlm()
    }

    // The state: orb and phrase. Not a box: it is the first thing of the page.
    RowLayout {
        objectName: "heroRow"
        Layout.fillWidth: true
        spacing: Theme.space(20)
        Orb {
            objectName: "hudOrb"
            mode: page.hud.mode
            progress: page.hud.progress
            size: 72
            opacity: page.hud.dim ? 0.4 : 1
            Accessible.description: core.micActive ? "Microfone ativo" : ""
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: 72
            Layout.preferredHeight: 72
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space(4)
            // HUD-02: the microphone notice is visible text in every state while the Core's recorder is on (micActive).
            Badge {
                objectName: "hojeMicBadge"
                visible: core.micActive
                text: "Microfone ativo"
                tone: "warning"
                Accessible.name: "Aviso: microfone ativo"
            }
            Text {
                objectName: "heroPhrase"
                text: page.hud.phrase
                textFormat: Text.PlainText
                color: page.hudColor
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontTitle + 4
                font.weight: Theme.titleWeight
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                Accessible.role: Accessible.StaticText
                Accessible.name: "Estado do Gideon, " + text
            }
            Text {
                objectName: "heroSub"
                text: page.hud.sub
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            // The words of the session: what the Core heard (partial or final) while a voice session runs.
            Text {
                objectName: "hudTranscript"
                visible: page.hud.transcript && core.subtitle.length > 0
                text: (core.partial ? "Você (parcial): " : "Você: ") + core.subtitle
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                Accessible.name: core.partial ? "Transcrição parcial" : "Transcrição final"
            }
            // The running tool (Core agent step) and the run's progress (steps used of the Core's limit).
            Text {
                objectName: "hudTool"
                visible: page.hud.tool.length > 0
                text: "Ferramenta: " + page.hud.tool
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                objectName: "hudProgress"
                visible: page.hud.progress >= 0
                Layout.fillWidth: true
                spacing: Theme.space(10)
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 6
                    radius: 3
                    color: Theme.surfaceVariant
                    Rectangle {
                        objectName: "hudProgressFill"
                        width: parent.width * Math.max(0, page.hud.progress)
                        height: parent.height
                        radius: 3
                        color: Theme.accent
                        Behavior on width {
                            enabled: Theme.animDuration > 0
                            NumberAnimation { duration: Theme.animDuration }
                        }
                    }
                }
                Text {
                    objectName: "hudProgressText"
                    text: page.hud.steps
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                }
            }
            // Verified success or failure of the last action: the Core's receipt, never a guess.
            Text {
                objectName: "hudReceipt"
                visible: page.hud.receipt !== null
                text: page.hud.receipt ? page.hud.receipt.text : ""
                textFormat: Text.PlainText
                color: page.hud.receipt && page.hud.receipt.ok ? Theme.success : Theme.error
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                font.weight: 600
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                Accessible.name: text
            }
            GButton {
                objectName: "hudCancel"
                visible: page.hud.cancel.length > 0
                variant: "secondary"
                text: "Cancelar"
                Layout.alignment: Qt.AlignLeft
                Accessible.name: "Cancelar"
                onClicked: page.cancelActive()
            }
            // A6: while the Core does not listen to the microphone, one quiet line says how to turn it on.
            Text {
                objectName: "hojeLiveHint"
                visible: core.audioLive.enabled !== true
                text: core.liveAudioEnabled ? "Microfone será ativado ao reiniciar o Core." : "Microfone desligado: ative em Dispositivos para usar a voz"
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                Accessible.name: text
            }
            // A9: while the Core listens, a compact level meter and one state line: speech heard but no phrase recognised
            // says so, with the phrase to say. Numbers come from audio.live only.
            ILevelMeter {
                objectName: "hojeLevelMeter"
                compact: true
                visible: core.audioLevel.capturing === true
                view: core.audioLevel
            }
            Text {
                objectName: "hojeListenState"
                visible: core.liveStateView.line !== undefined && core.liveStateView.line.length > 0
                text: core.liveStateView.line || ""
                textFormat: Text.PlainText
                color: core.audioLevel.unmatched === true ? Theme.warning : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                Accessible.name: text
            }
            Text {
                objectName: "hojeListenHint"
                visible: (core.liveStateView.hint || "").length > 0
                text: core.liveStateView.hint || ""
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

    // The one decision on this page: the oldest pending proposal (the same card as Conversa and Agente).
    AProposalCard {
        objectName: "hojeProposal"
        visible: page.pending.length > 0
        idPrefix: "hoje_"
        proposal: page.oldest
        sending: decision.sentId === page.oldest.proposal_id
        onDecide: function (proposalId, choice) {
            decision.sentId = proposalId
            core.decideTool(proposalId, choice)
        }
    }
    QtObject {
        id: decision
        property string sentId: ""
    }
    Connections {
        target: core
        function onToolResultChanged() { decision.sentId = "" }
    }

    Section {
        title: "Comando"
        Text {
            text: "Texto segue o mesmo caminho da voz. Até 512 bytes, em uma linha."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            GTextField {
                id: input
                objectName: "textInput"
                Layout.fillWidth: true
                // Characters are bounded here only against a huge paste; the limit that counts is the byte counter below.
                maximumLength: 2048
                placeholderText: "Diga ou digite um comando"
                enabled: page.textTypeable
                Accessible.name: "Comando para o Gideon"
                onAccepted: page.submit()
            }
            GButton {
                objectName: "sendButton"
                variant: "primary"
                text: "Enviar"
                Accessible.name: "Enviar comando"
                enabled: page.canSend
                onClicked: page.submit()
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(12)
            Text {
                objectName: "commandCounter"
                text: L.byteCounter(input.text, 512)
                textFormat: Text.PlainText
                color: page.inputProblem.length > 0 ? Theme.warning : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                Accessible.name: "Tamanho do comando: " + text
            }
            Text {
                objectName: "commandProblem"
                visible: page.inputProblem.length > 0
                text: page.inputProblem
                textFormat: Text.PlainText
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                Accessible.name: "Motivo: " + text
            }
        }
        Text {
            objectName: "typeReason"
            visible: text.length > 0
            text: page.typeReason
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            objectName: "textResult"
            visible: text.length > 0
            text: core.textResult
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    Section {
        title: "Última interação"
        // The last words of the session: what the user said (partial or final) and the receipt of the last command.
        // Turns heard while the microphone is off come from the boot replay or the virtual PCM: they are test audio.
        Text {
            objectName: "interactionTestLabel"
            visible: core.lastInteractionIsTestAudio && core.subtitle.length > 0
            text: "(áudio de teste)"
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
        }
        Rectangle {
            objectName: "transcriptViewport"
            Layout.fillWidth: true
            Layout.minimumHeight: 48
            implicitHeight: Math.max(48, subtitleText.implicitHeight + Theme.space(20))
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.hairline
            Text {
                id: subtitleText
                objectName: "subtitle"
                anchors.left: parent.left; anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: Theme.space(12); anchors.rightMargin: Theme.space(12)
                text: core.subtitle.length > 0 ? (core.partial ? "Você (parcial): " : "Você: ") + core.subtitle : "Sua conversa aparecerá aqui."
                textFormat: Text.PlainText
                color: core.subtitle.length > 0 ? Theme.text : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Accessible.name: core.partial ? "Transcrição parcial" : "Transcrição final"
            }
        }
        RowLayout {
            objectName: "result"
            visible: core.result.length > 0
            Layout.fillWidth: true
            spacing: Theme.space(6)
            Text {
                text: "Gideon ·"
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
            }
            Text {
                text: core.resultVerified ? "Concluído" : "Falhou"
                textFormat: Text.PlainText
                color: core.resultVerified ? Theme.success : Theme.error
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.weight: 600
            }
            Text {
                text: "· " + core.result
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }

    Section {
        objectName: "recentActivity"
        title: "Atividade recente"
        Repeater {
            model: page.recent
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Theme.space(14)
                Text {
                    text: modelData.time
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    Layout.preferredWidth: Theme.space(64)
                }
                Text {
                    text: modelData.text
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                    Accessible.name: modelData.text
                }
                Badge {
                    visible: modelData.badge !== null
                    text: modelData.badge ? modelData.badge.text : ""
                    tone: modelData.badge ? modelData.badge.tone : "neutral"
                }
            }
        }
        Text {
            visible: page.recent.length === 0
            text: "Nada ainda nesta sessão."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            Layout.fillWidth: true
        }
        GButton {
            objectName: "seeAllActivity"
            Layout.alignment: Qt.AlignRight
            variant: "ghost"
            text: "Ver tudo"
            onClicked: Window.window.goPage("atividade")
        }
    }
}
