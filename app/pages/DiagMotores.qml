import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Diagnóstico > Motores: the state of wake, speech-to-text and text-to-speech, and the voice pack.
PageFrame {
    id: page
    objectName: "page_diag_motores"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "diag_motores"

    PageHeader {
        title: "Motores"
        subtitle: "Wake, transcrição e voz: estado de cada motor e o pacote de voz."
    }
    Section {
        title: "Motores"
        Repeater {
            model: [{name: "Wake", status: core.wakeStatus}, {name: "STT · transcrição", status: core.sttStatus}, {name: "TTS · voz", status: core.speechStatus}]
            delegate: ListRow {
                required property var modelData
                title: modelData.name
                detail: modelData.status === "unavailable" ? "Indisponível neste perfil" : "Estado reportado pelo Core"
                iconName: "cpu"
                Badge {
                    text: L.statusText(modelData.status)
                    tone: modelData.status === "unavailable" ? "neutral" : (modelData.status === "failed" || modelData.status === "stt_failed" || modelData.status === "audio_error") ? "error" : "success"
                }
            }
        }
    }
    Section {
        title: "Pacote de voz"
        Text { text: core.packDescription || "Pacote de voz não configurado"; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Text { text: core.diagnostic; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    }
}
