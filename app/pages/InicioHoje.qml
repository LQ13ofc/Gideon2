import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Assistente > Hoje: state, one command line, the last interaction, and three chips that lead to the setting that owns each value.
PageFrame {
    id: page
    objectName: "page_hoje"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "hoje"

    // Phrase of the state: the Core state first, then the chat wait.
    readonly property string heroPhrase: {
        if (!core.connected) return "Core desconectado"
        switch (core.state) {
        case "capturing": return "Ouvindo…"
        case "transcribing": return "Transcrevendo…"
        case "executing": return "Executando…"
        case "speaking": return "Falando…"
        case "offline": return "Core indisponível"
        case "safe_mode": return "Modo seguro"
        case "restart_required": return "Reinício necessário"
        }
        return core.chatState === "waiting" || core.chatState === "streaming" ? "Pensando…" : "Pronto para ouvir"
    }
    readonly property var wakeChoice: L.activeWake(core.wakeChoices, core.snapshotPack.active_phrase)
    readonly property bool canSend: core.textAvailable && input.text.trim().length > 0

    function submit() { if (page.canSend) core.submitText(input.text) }

    Connections {
        target: core
        function onTextSent(sent) { if (input.text === sent) input.text = "" }
    }

    PageHeader {
        title: "Hoje"
        subtitle: "Como o Gideon está agora e um comando para ele."
    }

    // Status chips: one line, each one opens the setting that owns the value.
    Flow {
        Layout.fillWidth: true
        spacing: Theme.space(8)
        Chip {
            objectName: "chipWake"
            text: "Wake: " + L.wakeText(core.snapshotPack) + (page.wakeChoice ? (page.wakeChoice.qualification === "dev_qualified" ? " · em desenvolvimento" : " · requer prova de conceito") : "")
            onClicked: Window.window.goPage("cfg_voz")
        }
        Chip {
            objectName: "chipEntrada"
            text: "Entrada: " + (core.packAvailable ? "PCM virtual" : "indisponível")
            onClicked: Window.window.goPage("cfg_dispositivos")
        }
        Chip {
            objectName: "chipModo"
            text: "Modo: " + (core.chatAvailable ? "Base + LLM (" + ((core.llmConfig && core.llmConfig.model) || "modelo") + ")" : "Base, sem LLM")
            onClicked: Window.window.goPage(core.chatAvailable ? "modelos" : "plugins")
        }
    }

    // The state, in words, with the orb.
    RowLayout {
        objectName: "heroRow"
        Layout.fillWidth: true
        spacing: Theme.space(16)
        Orb {
            mode: L.orbStateOf(core.connected ? core.state : "offline")
            size: Theme.space(40)
            Layout.preferredWidth: size; Layout.preferredHeight: size
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                objectName: "heroPhrase"
                text: page.heroPhrase
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontTitle - 4
                font.weight: Theme.titleWeight
                Layout.fillWidth: true
                Accessible.role: Accessible.StaticText
                Accessible.name: "Estado: " + text
            }
            Text {
                text: core.connected ? (core.state === "capturing" ? "Microfone ativo. Diga o comando." : "Diga 'Hey Gideon' ou digite um comando.") : "Vamos reconectar ao Gideon."
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
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
                enabled: core.textAvailable
                Accessible.name: "Comando de texto"
                onAccepted: page.submit()
            }
            GButton {
                objectName: "sendButton"
                variant: "primary"
                text: "Enviar"
                Accessible.name: "Enviar comando de texto"
                enabled: page.canSend
                onClicked: page.submit()
            }
        }
        Text {
            visible: !core.textAvailable
            text: "Indisponível: o Core ainda não aceita texto neste perfil."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            Layout.fillWidth: true
        }
    }

    Section {
        title: "Última interação"
        ScrollView {
            id: transcript
            objectName: "transcriptViewport"
            Layout.fillWidth: true
            Layout.minimumHeight: 48
            Layout.preferredHeight: 90
            clip: true
            TextArea {
                objectName: "subtitle"
                text: core.subtitle
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                textFormat: TextEdit.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                placeholderText: "Sua conversa aparecerá aqui."
                placeholderTextColor: Theme.textMuted
                Accessible.name: core.partial ? "Transcrição parcial" : "Transcrição final"
                background: Rectangle { color: Theme.bg; radius: Theme.radius; border.width: 1; border.color: Theme.strongOutline }
            }
        }
        Text {
            objectName: "result"
            visible: core.result.length > 0
            text: core.result
            textFormat: Text.PlainText
            color: core.resultVerified ? Theme.success : Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: "Resultado: " + text
        }
        Text {
            objectName: "textResult"
            visible: text.length > 0
            text: core.textResult
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
