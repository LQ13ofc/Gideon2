import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Configurações > Privacidade: what is kept and what is not, the cloud consent (read here, changed in Modelos LLM), and
// the plugin data that can be erased (behind a confirmation). Nothing on this page changes the consent.
PageFrame {
    id: page
    objectName: "page_cfg_privacidade"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_privacidade"

    readonly property bool cloudConsent: core.llmConfig.cloud_consent === true
    readonly property bool clearAvailable: core.modelsAvailable && String(core.sessionId || "").length === 0
    readonly property bool advancedOn: AppState.uiGet("behavior.advanced", false) === true

    PageHeader {
        title: "Privacidade"
        subtitle: "O que o Gideon guarda, onde fica e quem pode receber dados."
    }
    ECfgSearch {}
    ECfgNotice {}

    Section {
        title: "O que fica guardado"
        Repeater {
            model: [
                { tag: "EM MEMÓRIA", tone: "info", text: "Áudio capturado: só em memória durante a captura. Nenhum arquivo de voz é gravado." },
                { tag: "EM MEMÓRIA", tone: "info", text: "Legendas: só em memória, sem histórico." },
                { tag: "NÃO GUARDADO", tone: "success", text: "Histórico de conversas: não há histórico salvo." },
                { tag: "PRIVADO", tone: "neutral", text: "Configurações: guardadas pelo Core em área privada. O caminho não é exibido." }
            ]
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Theme.space(12)
                Badge {
                    Layout.alignment: Qt.AlignTop
                    text: modelData.tag
                    tone: modelData.tone
                }
                Text {
                    text: modelData.text
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }
    }

    // B16: the microphone as the Core reports it. The indicator is the recorder's state, not a physical reading of the device.
    Section {
        title: "Microfone"
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(12)
            Badge {
                objectName: "privacyMicBadge"
                visible: core.micActive
                text: "Microfone ativo"
                tone: "warning"
            }
            Text {
                objectName: "privacyMicState"
                text: core.micActive ? "Captura ao vivo em andamento." : "Microfone inativo."
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.weight: 600
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        Text {
            objectName: "privacyLiveInput"
            text: core.audioLiveText
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            text: "O indicador mostra o estado que o Core informa sobre o gravador ao vivo. Não é uma leitura física do microfone."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    Section {
        title: "Envio à nuvem"
        Text {
            objectName: "cloudConsentState"
            text: "Consentimento salvo: " + (page.cloudConsent ? "concedido" : "não concedido")
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            font.weight: 600
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            text: "Sem consentimento, conversas não são enviadas à nuvem. Você marca o consentimento no provedor do motor LLM."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "llmOpenButton"
            variant: "secondary"
            text: "Abrir Modelos LLM › Provedor e chaves"
            Accessible.name: "Abrir configuração do Motor LLM"
            enabled: core.connected
            onClicked: Window.window.openLlm()
        }
        Text {
            text: core.connected ? "Esta aba só mostra o consentimento. Ele muda em Modelos LLM." : "Indisponível: Core desconectado."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        EValueRow {
            label: "Valor salvo do consentimento"
            value: page.cloudConsent ? "verdadeiro" : "falso"
            advanced: true
        }
    }

    Section {
        title: "Retenção e dados de plugins"
        SettingRow {
            label: "Retenção do histórico"
            help: "Quanto tempo a linha do tempo guarda os eventos."
            disabledReason: "não há controle de retenção; dados em memória deixam de existir quando o Core encerra"
        }
        Text {
            text: "Dados de plugins: configurações guardadas pelo plugin de LLM. O Core e as chaves não são afetados."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(12)
            GButton {
                objectName: "privacyClearPluginButton"
                variant: "danger"
                text: "Apagar dados de plugins"
                Accessible.name: "Apagar dados de plugins de LLM"
                enabled: page.clearAvailable
                onClicked: clearPluginConfirm.open()
            }
            Text {
                text: page.clearAvailable ? "Pede confirmação. Não altera o provedor nem as chaves."
                    : (String(core.sessionId || "").length > 0 ? "Indisponível agora: sessão de voz em andamento." : "Indisponível: nenhum plugin de LLM com dados guardados.")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        Text {
            visible: page.advancedOn
            text: "Inclui modelos personalizados (lista do plugin de LLM)."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    EAdvancedNote { subtab: "Privacidade" }

    Collapsible {
        title: "Como funciona"
        summary: "Nada do que você fala é guardado em disco pela interface. A nuvem só recebe conversas com consentimento."
        Text {
            text: "Nada do que você fala é guardado em disco pela interface. A nuvem só recebe conversas com consentimento. Apagar os dados do plugin não altera o provedor nem as chaves."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    Modal {
        id: clearPluginConfirm
        objectName: "privacyClearPluginConfirm"
        title: "Apagar dados do plugin de LLM?"
        Text {
            text: "Apagar as configurações guardadas pelo plugin LLM, inclusive modelos personalizados? O plugin e a configuração do Core (provedor, modelo e chaves) não são alterados."
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmPrivacyClearButton"
            variant: "danger"
            text: "Apagar dados"
            Layout.alignment: Qt.AlignRight
            onClicked: {
                core.clearPluginSettings()
                clearPluginConfirm.close()
            }
        }
    }
}
