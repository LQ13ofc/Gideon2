import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/EventLabels.js" as E

// Diagnóstico > Motores (docs/ui-spec/50-diagnostico.md §6): wake, transcription and speech engines, the voice pack, the
// last capture and reply and, when installed, the LLM plugin. Reads the Core only; repair happens in Recuperação.
PageFrame {
    id: page
    objectName: "page_diag_motores"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "diag_motores"

    readonly property var pack: core.snapshotPack
    readonly property var engines: pack.engines || {}
    readonly property bool linked: core.connected
    readonly property string offlineText: "—"

    // The active wake phrase (base_pack.wake_phrases, matched by active_phrase).
    readonly property var activeWake: {
        var list = pack.wake_phrases || []
        for (var i = 0; i < list.length; i++) if (list[i].id === pack.active_phrase) return list[i]
        return null
    }

    // The LLM plugin is the installed plugin that offers the chat capability (the `.chat` suffix, as in the bridge).
    readonly property var llmItem: {
        var items = core.pluginItems
        for (var i = 0; i < items.length; i++) {
            var caps = items[i].capabilities || []
            for (var j = 0; j < caps.length; j++) if (String(caps[j]).slice(-5) === ".chat") return items[i]
        }
        return null
    }
    // B8 formatting. Capture times are microseconds from the Core (shown as ms); peak and RMS are 0 to 1 (shown with a comma, 3 decimals).
    function captureReasonText(code) {
        switch (code) {
        case "capture_completed": return qsTr("captura concluída")
        case "cancelled": return qsTr("cancelada")
        case "audio_error": return qsTr("erro de áudio")
        case "stt_failed": return qsTr("falha na transcrição")
        case "stt_unavailable": return qsTr("transcrição indisponível")
        case "transcript_final": return qsTr("transcrição final")
        case "no_speech": return qsTr("sem fala detectada")
        case "capture_too_long": return qsTr("captura longa demais")
        }
        return ""
    }
    function samplesText(n) { return n === 1 ? qsTr("%1 amostra").arg(n) : qsTr("%1 amostras").arg(n) }
    function chunksText(n) { return n === 1 ? qsTr("%1 pedaço").arg(n) : qsTr("%1 pedaços").arg(n) }
    function msOf(us) { return Math.round(Number(us) / 1000) + " ms" }
    function fixed3(x) { return Number(x).toFixed(3).replace(".", ",") }
    function shortHash(h) { return String(h || "").slice(0, 12) }
    readonly property var captureLines: {
        var c = core.captureSummary
        var t = core.transcriptSummary
        var out = []
        if (c.session_id === undefined) out.push(qsTr("Captura: nenhuma nesta sessão do Core."))
        else {
            out.push(qsTr("Captura: início %1 · fim %2").arg(page.msOf(c.start_us)).arg(page.msOf(c.end_us)))
            out.push(qsTr("Amostras: %1 · SHA-256 %2 · motivo: %3").arg(c.samples).arg(page.shortHash(c.pcm_sha256)).arg(page.captureReasonText(c.reason) || qsTr("não informado")))
        }
        if (t.session_id !== undefined) out.push(qsTr("Transcrição: %1 · revisão %2 · confiança desconhecida").arg(t.is_final ? qsTr("final") : qsTr("parcial")).arg(t.revision))
        return out
    }
    readonly property var speechLines: {
        var s = core.speechSummary
        if (s.session_id === undefined) return [qsTr("Resposta: nenhuma nesta sessão do Core.")]
        return [
            qsTr("Resposta: %1 a %2 Hz · %3").arg(page.samplesText(s.samples)).arg(s.sample_rate).arg(page.chunksText(s.chunks)),
            qsTr("Pico %1 · RMS %2").arg(page.fixed3(s.peak)).arg(page.fixed3(s.rms)),
            qsTr("Primeiro áudio em %1 ms · tempo total %2 ms").arg(s.first_pcm_ms).arg(s.elapsed_ms),
            qsTr("Saída: %1 · SHA-256 %2").arg(E.audioOutputLabel(s.sink)).arg(page.shortHash(s.pcm_sha256))
        ]
    }
    readonly property bool llmFallbackUsed: {
        var events = core.events || []
        for (var i = 0; i < events.length; i++) if (events[i].kind === "llm_fallback_used") return true
        return false
    }
    // "Frase: …" line: the active wake phrase and its qualification, or the offline dash.
    function wakeLine() {
        if (!page.linked) return page.offlineText
        if (!page.activeWake) return qsTr("não configurada")
        return qsTr("%1 · %2").arg(page.activeWake.text).arg(E.wakeQualificationLabel(page.activeWake.qualification))
    }
    // "Voz: …" line of the speech engine: voice, engine and language, or the offline dash.
    function voiceLine() {
        if (!page.linked) return qsTr("Voz: %1").arg(page.offlineText)
        return qsTr("Voz: %1 · %2 · %3").arg(page.pack.voice || qsTr("não informada")).arg(E.engineLabel(page.engines.tts)).arg(E.languageLabel(page.pack.language))
    }

    PageHeader {
        title: qsTr("Motores")
        subtitle: qsTr("Wake, transcrição e resposta em voz: o que cada motor está fazendo agora.")
    }

    Section {
        title: qsTr("Motores de voz")
        GridLayout {
            Layout.fillWidth: true
            columns: page.width >= Theme.narrowWidth ? 3 : 1
            columnSpacing: Theme.space(24)
            rowSpacing: Theme.space(16)

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: Theme.space(6)
                Text {
                    text: qsTr("Wake (frase de despertar)")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSection
                    font.weight: 600
                    Layout.fillWidth: true
                }
                Badge { text: E.wakePhrase(core.wakeStatus); tone: E.toneOf(core.wakeStatus) }
                Text {
                    text: qsTr("Frase: %1").arg(page.wakeLine())
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    text: qsTr("Motor: %1").arg(page.linked ? E.engineLabel(page.engines.wake) : page.offlineText)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.fillWidth: true
                }
                Text {
                    text: qsTr("Entrada: %1").arg(page.linked ? E.audioInputLabel(page.pack.audio_input) : page.offlineText)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.fillWidth: true
                }
                FNote { small: true; text: qsTr("Reprodução de teste; sem microfone ao vivo.") }
                FNote { visible: core.wakeStatus === "replay_finished"; tone: "warn"; small: true; text: qsTr("Reprodução de teste encerrada: o wake não está armado para ouvir.") }
                FNote { visible: core.wakeStatus === "failed"; tone: "error"; small: true; text: qsTr("Falhou. Reinicie o Core em Recuperação.") }
                GButton {
                    visible: core.wakeStatus === "failed"
                    variant: "ghost"
                    text: qsTr("Abrir Recuperação")
                    onClicked: Window.window.goPage("diag_recuperacao")
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: Theme.space(6)
                Text {
                    text: qsTr("Transcrição (STT)")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSection
                    font.weight: 600
                    Layout.fillWidth: true
                }
                Badge { text: E.sttPhrase(core.sttStatus); tone: E.toneOf(core.sttStatus) }
                Text {
                    text: qsTr("Motor: %1 · idioma %2").arg(page.linked ? E.engineLabel(page.engines.stt) : page.offlineText).arg(page.linked ? E.languageLabel(page.pack.language) : page.offlineText)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                FNote { small: true; text: qsTr("Português não está comprovado para transcrição.") }
                FNote { visible: core.sttStatus === "failed"; tone: "error"; small: true; text: qsTr("Falhou. Reinicie o Core em Recuperação.") }
                GButton {
                    visible: core.sttStatus === "failed"
                    variant: "ghost"
                    text: qsTr("Abrir Recuperação")
                    onClicked: Window.window.goPage("diag_recuperacao")
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: Theme.space(6)
                Text {
                    text: qsTr("Resposta em voz (TTS)")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSection
                    font.weight: 600
                    Layout.fillWidth: true
                }
                Badge { text: E.speechPhrase(core.speechStatus); tone: E.toneOf(core.speechStatus) }
                Text {
                    text: page.voiceLine()
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    text: qsTr("Saída: %1").arg(page.linked ? E.audioOutputLabel(page.pack.audio_output) : page.offlineText)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.fillWidth: true
                }
                FNote { small: true; text: qsTr("Sem alto-falante físico comprovado.") }
            }
        }

        // Motor LLM (plugin): only when an installed plugin offers the chat capability.
        ColumnLayout {
            visible: page.llmItem !== null
            Layout.fillWidth: true
            Layout.topMargin: Theme.space(8)
            spacing: Theme.space(6)
            Text {
                text: qsTr("Motor LLM (plugin)")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.weight: 600
            }
            Badge {
                text: page.llmItem ? E.pluginStatePhrase(page.llmItem.state) : ""
                tone: page.llmItem ? E.toneOf(page.llmItem.state) : "neutral"
            }
            Text {
                text: qsTr("Configurado: %1").arg(core.modelsSelected.provider ? qsTr("%1 · %2").arg(core.providerLabel(core.modelsSelected.provider)).arg(core.modelsSelected.model) : qsTr("Nenhum modelo configurado"))
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                text: qsTr("Resposta de reserva: %1").arg(page.llmFallbackUsed ? qsTr("nesta sessão") : qsTr("não usada nesta sessão"))
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            FNote {
                visible: page.llmItem !== null && page.llmItem.state === "failed"
                tone: "error"
                small: true
                text: qsTr("Falhou: %1").arg(page.llmItem && page.llmItem.last_error ? E.codePhrase(page.llmItem.last_error) : qsTr("motivo não informado"))
            }
            FNote { visible: Theme.advanced && page.llmItem !== null && !!page.llmItem.last_error; small: true; text: qsTr("código: %1").arg(page.llmItem ? page.llmItem.last_error : "") }
        }
    }

    GridLayout {
        Layout.fillWidth: true
        columns: page.width >= Theme.narrowWidth ? 2 : 1
        columnSpacing: Theme.space(24)
        rowSpacing: Theme.space(24)

        Section {
            title: qsTr("Pacote de voz")
            Layout.alignment: Qt.AlignTop
            Text {
                text: qsTr("Verificação: %1").arg(!page.linked ? page.offlineText : page.pack.preflight === "verified" ? qsTr("Verificado") : qsTr("Não verificado"))
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: qsTr("Entrada: %1").arg(page.linked ? E.audioInputLabel(page.pack.audio_input) : page.offlineText)
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: qsTr("Saída: %1").arg(page.linked ? E.audioOutputLabel(page.pack.audio_output) : page.offlineText)
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: qsTr("Qualificação: %1").arg(!page.linked ? page.offlineText : page.pack.scope === "dev_virtual_en" ? qsTr("pacote de teste virtual · validação física pendente") : qsTr("não informada"))
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            FNote { text: qsTr("Trocar a voz ou a frase exige reinício do Core.") }
        }

        Section {
            title: qsTr("Última captura e resposta")
            Layout.alignment: Qt.AlignTop
            // B8: the blocks capture, transcript and speech of this Core session, already validated by the bridge. Absent block = nothing this session.
            Repeater {
                model: page.captureLines
                delegate: Text {
                    required property string modelData
                    text: modelData
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
            Repeater {
                model: page.speechLines
                delegate: Text {
                    required property string modelData
                    text: modelData
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
            FNote { visible: Theme.advanced; small: true; text: qsTr("Confiança da transcrição: desconhecida (o motor não informa).") }
        }

        // DIAG-05: latency of the speech answer (Core timing of the last answer of this session).
        Section {
            objectName: "diagSpeechLatency"
            title: qsTr("Latência da resposta em voz")
            Layout.alignment: Qt.AlignTop
            EValueRow {
                objectName: "speechFirstAudio"
                label: qsTr("Primeiro áudio")
                value: core.speechLatency.known ? (core.speechLatency.first_pcm_ms + " ms") : qsTr("sem resposta falada nesta sessão")
            }
            EValueRow {
                label: qsTr("Resposta completa")
                value: core.speechLatency.known ? (core.speechLatency.elapsed_ms + " ms") : "—"
            }
        }

        // DIAG-03 (M27): the answer came from the fallback model. Core event llm_fallback_used; no content is shown.
        Section {
            objectName: "diagFallback"
            title: qsTr("Motor LLM")
            Layout.alignment: Qt.AlignTop
            EValueRow {
                objectName: "fallbackUsedRow"
                label: qsTr("Resposta de reserva")
                value: core.llmFallbackUsed ? qsTr("usada nesta sessão") : qsTr("não usada nesta sessão")
            }
            FNote { small: true; text: qsTr("Quando o modelo principal falha, o Gideon usa o modelo de reserva e avisa na Conversa.") }
        }
    }

    Collapsible {
        title: qsTr("Como funciona")
        summary: qsTr("O que cada motor está fazendo. O resumo curto fica no Assistente.")
        FNote {
            tone: "text"
            text: qsTr("Reprodução de teste encerrada e em andamento não indicam microfone armado. Trocar frase, voz ou dispositivo exige reinício do Core.")
        }
    }
}
