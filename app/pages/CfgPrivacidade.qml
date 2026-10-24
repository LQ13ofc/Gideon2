import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Configurações > Privacidade: what is kept and what is not, cloud consent (read here, edited in the Motor LLM form),
// and the confirmation setting for writes.
PageFrame {
    id: page
    objectName: "page_cfg_privacidade"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_privacidade"

    PageHeader {
        title: "Privacidade"
        subtitle: "O que fica guardado, o consentimento de nuvem e as confirmações."
    }

    Section {
        title: "O que fica guardado"
        Text { text: "Nada de histórico é gravado em disco. Áudio e legendas ficam só em memória, durante a sessão."; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        SettingRow {
            label: "Retenção do histórico de Atividade"
            help: "Quanto tempo a linha do tempo guarda os eventos."
            disabledReason: "o Core não tem controle de retenção ainda"
        }
    }

    Section {
        title: "Nuvem"
        Text {
            objectName: "cloudConsentState"
            text: "Consentimento de nuvem: " + (core.llmConfig.cloud_consent === true ? "concedido" : "não concedido") + ". Mensagens só vão à nuvem com este consentimento."
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "llmOpenButton"
            variant: "secondary"
            text: "Abrir Motor LLM"
            Accessible.name: "Abrir configuração do Motor LLM"
            enabled: core.connected
            onClicked: Window.window.openLlm()
        }
    }

    Section {
        title: "Confirmações"
        SettingRow {
            label: "Pedir confirmação para ações de escrita e públicas"
            help: "Recomendado. Desligar só é permitido para leitura."
            settingKey: "behavior.confirmWrites"
            disabledReason: AppState.uiLive() ? "" : "configurações do app indisponíveis"
            Toggle {
                checked: AppState.uiGet("behavior.confirmWrites", true) === true
                onToggled: AppState.uiSet("behavior.confirmWrites", checked)
            }
        }
    }
}
