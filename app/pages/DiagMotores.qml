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
    readonly property bool llmFallbackUsed: {
        var events = core.events || []
        for (var i = 0; i < events.length; i++) if (events[i].kind === "llm_fallback_used") return true
        return false
    }

    PageHeader {
        title: "Motores"
        subtitle: "Wake, transcrição e resposta em voz: o que cada motor está fazendo agora."
    }

    Section {
        title: "Motores de voz"
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
                    text: "Wake (frase de despertar)"
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSection
                    font.weight: 600
                    Layout.fillWidth: true
                }
                Badge { text: E.wakePhrase(core.wakeStatus); tone: E.toneOf(core.wakeStatus) }
                Text {
                    text: "Frase: " + (!page.linked ? page.offlineText : page.activeWake ? page.activeWake.text + " · " + E.wakeQualificationLabel(page.activeWake.qualification) : "não configurada")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    text: "Motor: " + (page.linked ? E.engineLabel(page.engines.wake) : page.offlineText)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.fillWidth: true
                }
                Text {
                    text: "Entrada: " + (page.linked ? E.audioInputLabel(page.pack.audio_input) : page.offlineText)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.fillWidth: true
                }
                FNote { small: true; text: "Reprodução de teste; sem microfone ao vivo." }
                FNote { visible: core.wakeStatus === "replay_finished"; tone: "warn"; small: true; text: "Reprodução de teste encerrada: o wake não está armado para ouvir." }
                FNote { visible: core.wakeStatus === "failed"; tone: "error"; small: true; text: "Falhou. Reinicie o Core em Recuperação." }
                GButton {
                    visible: core.wakeStatus === "failed"
                    variant: "ghost"
                    text: "Abrir Recuperação"
                    onClicked: Window.window.goPage("diag_recuperacao")
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: Theme.space(6)
                Text {
                    text: "Transcrição (STT)"
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSection
                    font.weight: 600
                    Layout.fillWidth: true
                }
                Badge { text: E.sttPhrase(core.sttStatus); tone: E.toneOf(core.sttStatus) }
                Text {
                    text: "Motor: " + (page.linked ? E.engineLabel(page.engines.stt) : page.offlineText) + " · idioma " + (page.linked ? E.languageLabel(page.pack.language) : page.offlineText)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                FNote { small: true; text: "Português não está comprovado para transcrição." }
                FNote { visible: core.sttStatus === "failed"; tone: "error"; small: true; text: "Falhou. Reinicie o Core em Recuperação." }
                GButton {
                    visible: core.sttStatus === "failed"
                    variant: "ghost"
                    text: "Abrir Recuperação"
                    onClicked: Window.window.goPage("diag_recuperacao")
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: Theme.space(6)
                Text {
                    text: "Resposta em voz (TTS)"
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSection
                    font.weight: 600
                    Layout.fillWidth: true
                }
                Badge { text: E.speechPhrase(core.speechStatus); tone: E.toneOf(core.speechStatus) }
                Text {
                    text: "Voz: " + (page.linked ? (page.pack.voice || "não informada") + " · " + E.engineLabel(page.engines.tts) + " · " + E.languageLabel(page.pack.language) : page.offlineText)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    text: "Saída: " + (page.linked ? E.audioOutputLabel(page.pack.audio_output) : page.offlineText)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.fillWidth: true
                }
                FNote { small: true; text: "Sem alto-falante físico comprovado." }
            }
        }

        // Motor LLM (plugin): only when an installed plugin offers the chat capability.
        ColumnLayout {
            visible: page.llmItem !== null
            Layout.fillWidth: true
            Layout.topMargin: Theme.space(8)
            spacing: Theme.space(6)
            Text {
                text: "Motor LLM (plugin)"
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
                text: "Configurado: " + (core.modelsSelected.provider ? core.providerLabel(core.modelsSelected.provider) + " · " + core.modelsSelected.model : "Nenhum modelo configurado")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                text: "Resposta de reserva: " + (page.llmFallbackUsed ? "nesta sessão" : "não usada nesta sessão")
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
                text: "Falhou: " + (page.llmItem && page.llmItem.last_error ? E.codePhrase(page.llmItem.last_error) : "motivo não informado")
            }
            FNote { visible: Theme.advanced && page.llmItem !== null && !!page.llmItem.last_error; small: true; text: "código: " + (page.llmItem ? page.llmItem.last_error : "") }
        }
    }

    GridLayout {
        Layout.fillWidth: true
        columns: page.width >= Theme.narrowWidth ? 2 : 1
        columnSpacing: Theme.space(24)
        rowSpacing: Theme.space(24)

        Section {
            title: "Pacote de voz"
            Layout.alignment: Qt.AlignTop
            Text {
                text: "Verificação: " + (!page.linked ? page.offlineText : page.pack.preflight === "verified" ? "Verificado" : "Não verificado")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: "Entrada: " + (page.linked ? E.audioInputLabel(page.pack.audio_input) : page.offlineText)
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: "Saída: " + (page.linked ? E.audioOutputLabel(page.pack.audio_output) : page.offlineText)
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: "Qualificação: " + (!page.linked ? page.offlineText : page.pack.scope === "dev_virtual_en" ? "em desenvolvimento; validação física pendente" : "não informada")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            FNote { text: "Trocar a voz ou a frase exige reinício do Core." }
        }

        Section {
            title: "Última captura e resposta"
            Layout.alignment: Qt.AlignTop
            // A captura e a resposta do Core ainda não chegam à interface (N7): a linha diz o motivo.
            Text {
                text: "Captura: " + page.offlineText
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: "Resposta: " + page.offlineText
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            FNote { text: "Indisponível: a ponte ainda não informa a última captura nem a última resposta." }
            FNote { visible: Theme.advanced; small: true; text: "Confiança da transcrição: não medida" }
        }
    }

    Collapsible {
        title: "Como funciona"
        summary: "O que cada motor está fazendo. O resumo curto fica no Assistente."
        FNote {
            tone: "text"
            text: "Reprodução de teste encerrada e em andamento não indicam microfone armado. Trocar frase, voz ou dispositivo exige reinício do Core."
        }
    }
}
