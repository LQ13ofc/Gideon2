import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Configurações > Dispositivos: the virtual input and output that exist today. Physical devices show their reason; camera and screen belong to Percepção.
PageFrame {
    id: page
    objectName: "page_cfg_dispositivos"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_dispositivos"

    PageHeader {
        title: "Dispositivos"
        subtitle: "Entrada e saída virtuais. Dispositivos físicos ainda não estão disponíveis."
    }
    Section {
        title: "Entrada"
        SettingRow {
            label: "Entrada de áudio"
            help: "PCM virtual: o único caminho de captura nesta build."
            Text { text: core.packAvailable ? "PCM virtual" : "Indisponível"; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody }
        }
        SettingRow {
            label: "Microfone físico"
            help: "Entrada do microfone do computador."
            disabledReason: "pendente de validação humana"
        }
    }
    Section {
        title: "Saída"
        SettingRow {
            label: "Saída de áudio"
            help: "Saída virtual para a resposta por voz."
            Text { text: core.voiceAvailable ? "Saída virtual" : "Indisponível"; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody }
        }
        SettingRow {
            label: "Alto-falante físico"
            help: "Saída de som do computador."
            disabledReason: "pendente de validação humana"
        }
    }
    Section {
        title: "Câmera e tela"
        Text {
            text: "Câmera e tela são simuladas pelos plugins de Percepção e ação. Nenhum deles acessa hardware real nesta build."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            variant: "ghost"
            text: "Ver em Extensões › Percepção e ação"
            enabled: core.perceptionAvailable
            onClicked: Window.window.goPage("percepcao")
        }
    }
}
