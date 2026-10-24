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
    readonly property bool canSend: textTypeable && input.text.trim().length > 0

    // The state shown in words and by the orb. Order = the priorities of 10-assistente.md §2.2 (first true wins).
    readonly property var hud: {
        if (!core.connected) return {phrase: "Core desconectado", sub: "Tentando reconectar…", mode: "idle", tone: "muted", dim: true, badge: ""}
        var s = core.state
        if (s === "safe_mode") return {phrase: "Modo seguro", sub: "Abra Diagnóstico › Recuperação para reparar.", mode: "error", tone: "warning", dim: false, badge: ""}
        if (s === "restart_required") return {phrase: "Reinício necessário", sub: "Reinicie o Core para aplicar a alteração.", mode: "error", tone: "warning", dim: false, badge: ""}
        if (s === "capturing") return {phrase: "Ouvindo…", sub: "Fale agora. Cancelar encerra a sessão.", mode: "listening", tone: "info", dim: false, badge: "Microfone ativo"}
        if (s === "transcribing") return {phrase: "Transcrevendo…", sub: core.subtitle.length > 0 ? core.subtitle : "Processando o que você disse.", mode: "listening", tone: "info", dim: false, badge: ""}
        if (s === "executing") return {phrase: "Executando…", sub: core.agentState === "waiting_tool" ? "Ferramenta do agente em execução." : "Executando o comando.", mode: "thinking", tone: "info", dim: false, badge: ""}
        if (s === "speaking") return {phrase: "Falando…", sub: "Resposta em voz alta. Cancelar interrompe.", mode: "speaking", tone: "info", dim: false, badge: ""}
        if (s !== "idle") return {phrase: "Erro", sub: "Estado do Core não reconhecido.", mode: "error", tone: "error", dim: false, badge: ""}
        if (core.chatState === "waiting" || core.chatState === "streaming" || core.agentState === "thinking") {
            var waiting = core.chatState === "waiting" ? "Aguardando o motor LLM." : core.chatState === "streaming" ? "Recebendo a resposta." : "O agente planeja o próximo passo."
            return {phrase: "Pensando…", sub: waiting, mode: "thinking", tone: "info", dim: false, badge: ""}
        }
        if (page.pending.length > 0) return {phrase: "Aguardando sua aprovação", sub: "Ferramenta " + (page.oldest.tool || "") + " precisa da sua decisão.", mode: "idle", tone: "warning", dim: false, badge: ""}
        if (core.chatState === "error") return {phrase: "Erro", sub: core.chatResult.length > 0 ? core.chatResult : "A última resposta falhou.", mode: "error", tone: "error", dim: false, badge: ""}
        if (core.agentState === "failed" || core.agentState === "blocked") return {phrase: "Erro", sub: core.agentStateLabel, mode: "error", tone: "error", dim: false, badge: ""}
        return {phrase: "Pronto para ouvir", sub: "Diga 'Hey Gideon' ou digite um comando.", mode: "idle", tone: "normal", dim: false, badge: ""}
    }
    readonly property color hudColor: hud.tone === "warning" ? Theme.warning : hud.tone === "error" ? Theme.error : hud.tone === "muted" ? Theme.textMuted : Theme.text

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
            text: core.wakeChoices.length > 0 ? "Entrada: PCM virtual" : "Entrada: indisponível"
            onClicked: Window.window.goPage("cfg_dispositivos")
        }
        Chip {
            objectName: "chipModo"
            text: !core.chatAvailable ? "Modo: Base, sem LLM"
                : "Modo: Base + LLM (" + ((core.modelsSelected && core.modelsSelected.model) ? core.modelsSelected.model : "sem modelo") + ")"
            onClicked: Window.window.goPage(core.chatAvailable ? "modelos" : "plugins")
        }
    }

    // The state: orb and phrase. Not a box: it is the first thing of the page.
    RowLayout {
        objectName: "heroRow"
        Layout.fillWidth: true
        spacing: Theme.space(20)
        Orb {
            objectName: "hudOrb"
            mode: page.hud.mode
            size: 72
            opacity: page.hud.dim ? 0.4 : 1
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: 72
            Layout.preferredHeight: 72
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space(4)
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
            Badge {
                visible: page.hud.badge.length > 0
                text: page.hud.badge
                tone: "info"
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
                maximumLength: 512
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
