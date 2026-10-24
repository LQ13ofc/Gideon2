import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Configurações > Dispositivos: the input and output in use (virtual today). Physical devices are shown disabled with the
// reason. Camera and screen are synthetic and belong to Percepção e ação.
PageFrame {
    id: page
    objectName: "page_cfg_dispositivos"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_dispositivos"

    ECfgSearch {}
    PageHeader {
        title: "Dispositivos"
        subtitle: "Entrada e saída virtuais. Dispositivos físicos ainda não estão disponíveis."
    }
    ECfgNotice {}

    Section {
        title: "Entrada (microfone)"
        EValueRow {
            label: "Dispositivo em uso"
            value: "PCM virtual"
        }
        Text {
            text: "PCM virtual · pré-roll de 1 segundo · processamento na CPU. Microfone físico, cancelamento de eco e redução de ruído ainda indisponíveis."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        SettingRow {
            label: "Microfone físico"
            help: "Entrada do microfone do computador."
            disabledReason: "adaptador de microfone físico não implementado; validação humana pendente"
            Select {
                model: ["Sem microfone físico"]
                enabled: false
                implicitWidth: 240
                Accessible.name: "Microfone físico (indisponível)"
            }
        }
        EValueRow {
            label: "Formato da entrada"
            value: "PCM mono 16 kHz"
            advanced: true
        }
        EValueRow {
            label: "Código do estado de captura"
            value: String(core.sttStatus)
            advanced: true
        }
    }

    Section {
        title: "Saída (alto-falante)"
        EValueRow {
            label: "Dispositivo em uso"
            value: "Saída virtual"
        }
        Text {
            text: "Sem reprodução física comprovada."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
        }
        SettingRow {
            label: "Alto-falante físico"
            help: "Saída de som do computador."
            disabledReason: "adaptador de saída física não implementado"
            Select {
                model: ["Sem alto-falante físico"]
                enabled: false
                implicitWidth: 240
                Accessible.name: "Alto-falante físico (indisponível)"
            }
        }
        EValueRow {
            label: "Sink"
            value: "virtual (sem ID de dispositivo)"
            advanced: true
        }
    }

    Section {
        title: "Câmera e tela"
        EValueRow {
            label: "Câmera: simulada"
            badge: "SINTÉTICO"
            note: "Indisponível: sem câmera real."
        }
        EValueRow {
            label: "Tela: simulada"
            badge: "SINTÉTICO"
            note: "Indisponível: sem captura de tela real."
        }
        GButton {
            objectName: "perceptionLinkButton"
            variant: "ghost"
            text: "Ver em Extensões › Percepção e ação"
            enabled: core.perceptionAvailable
            onClicked: Window.window.goPage("percepcao")
        }
        Text {
            visible: !core.perceptionAvailable
            text: "Indisponível: nenhum plugin de percepção em execução."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            Layout.fillWidth: true
        }
    }

    Collapsible {
        title: "Como funciona"
        summary: "Entrada e saída são virtuais nesta versão. Dispositivos físicos entram quando o adaptador for validado."
        Text {
            text: "Entrada e saída são virtuais nesta versão. Dispositivos físicos entram quando o adaptador for validado. Nenhum controle desta aba troca de dispositivo hoje."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
