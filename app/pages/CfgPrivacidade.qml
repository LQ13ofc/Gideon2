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
    // CFG-04: the four wire values of src/storage.rs HistoryRetention. The Core default is days_30.
    readonly property var retentionOptions: [
        {value: "days_7", label: "7 dias"}, {value: "days_30", label: "30 dias"},
        {value: "days_90", label: "90 dias"}, {value: "never", label: "Não guardar"}
    ]
    function retentionIndex(value) {
        for (var i = 0; i < retentionOptions.length; i++) if (retentionOptions[i].value === value) return i
        return -1
    }

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
                { tag: "PRIVADO", tone: "success", text: "Histórico de conversas: texto, pelo prazo da Retenção (página Histórico). Áudio nunca é guardado." },
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

    // A11: host actions. Off by default. The switch opens the consent dialog (Cancelar by default); the Core saves the choice
    // and the state line shows the last action it confirmed. Desligado, the fixed commands only run the internal simulation.
    Section {
        title: "Ações no computador"
        Text {
            text: "Quando ligado, o Gideon abre aplicativos da lista fixa e muda o volume deste computador de verdade. Desligado, os comandos só fazem a simulação interna."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Toggle {
            id: realSwitch
            objectName: "realActionsSwitch"
            text: "Executar ações no computador"
            Accessible.name: "Executar ações no computador"
            checked: core.realActionsEnabled
            enabled: core.preferencesAvailable
            onToggled: {
                if (checked) realConsent.open()
                else core.setRealActions(false)
                // The switch follows the Core only: a click is not a change until the Core saves it.
                checked = Qt.binding(function () { return core.realActionsEnabled })
            }
        }
        Text {
            objectName: "realActionsState"
            text: core.realActionStateText
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            font.weight: 600
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: "Última ação no computador: " + text
        }
    }

    RealActionsConsent {
        id: realConsent
        onAgreed: core.setRealActions(true)
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
        // CFG-04: the Core keeps the timeline and the audit trail for this many days (preferences.history_retention).
        // The Core purges what is older at each save and once a minute; "never" keeps nothing on disk.
        SettingRow {
            label: "Retenção do histórico"
            help: "Quanto tempo a linha do tempo e a trilha de auditoria guardam os eventos. Dados mais antigos são apagados pelo Core."
            disabledReason: core.preferencesAvailable ? "" : (core.connected ? "Core ocupado: tente quando o Gideon estiver em espera" : "Core desconectado")
            Select {
                id: retentionBox
                objectName: "historyRetentionSelect"
                implicitWidth: 240
                textRole: "label"
                model: page.retentionOptions
                enabled: core.preferencesAvailable
                currentIndex: page.retentionIndex(core.historyRetention)
                Accessible.name: "Retenção do histórico: " + displayText
                // The box follows the Core value again: a refused or pending save never leaves a choice that Core did not keep.
                onActivated: function (index) {
                    core.setHistoryRetention(page.retentionOptions[index].value)
                    retentionBox.currentIndex = Qt.binding(function () { return page.retentionIndex(core.historyRetention) })
                }
            }
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

    // WP-10a: export and erase of the personal areas (Memória, Almas, Hábitos, Automações, Histórico). The export is a
    // private file written by the Core; the erase needs the confirmation below and the Core also checks it.
    readonly property var personalReply: core.personalReply || ({})
    readonly property bool personalBusy: String(core.sessionId || "").length > 0
    readonly property string personalResultText: {
        var r = page.personalReply
        if (!r.area || r.area === "") return ""
        if (r.code !== "ok") return core.codeMessage(r.code)
        if (r.area === "export") return "Exportação salva em " + (r.reply.path || "") + " (" + (r.reply.bytes || 0) + " bytes). O arquivo é privado: só o seu usuário pode lê-lo."
        if (r.area === "erase") return "Dados pessoais apagados. Memória, Almas, Hábitos, Automações e Histórico estão vazios."
        return ""
    }
    Section {
        title: "Meus dados pessoais"
        caption: "Memória, Almas, Hábitos, Automações e Histórico ficam no computador, em arquivos privados."
        Text {
            text: "Exportar cria um arquivo com tudo o que está guardado. Apagar remove as cinco áreas de uma vez e não pode ser desfeito."
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
                objectName: "personalExportButton"
                text: "Exportar meus dados"
                Accessible.name: "Exportar meus dados pessoais para um arquivo"
                enabled: core.connected && !page.personalBusy
                onClicked: core.personalExport()
            }
            GButton {
                objectName: "personalEraseButton"
                variant: "danger"
                text: "Apagar meus dados pessoais"
                Accessible.name: "Apagar todos os dados pessoais"
                enabled: core.connected && !page.personalBusy
                onClicked: personalEraseConfirm.open()
            }
            Text {
                objectName: "personalStatusText"
                text: page.personalBusy ? "Indisponível agora: sessão de voz em andamento." : page.personalResultText
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }
    PConfirm {
        id: personalEraseConfirm
        objectName: "personalEraseConfirm"
        title: "Apagar todos os dados pessoais?"
        message: "Apaga Memória, Almas, Hábitos, Automações e Histórico. Não pode ser desfeito: exporte antes se quiser guardar uma cópia."
        actionText: "Apagar tudo"
        onConfirmed: core.personalEraseAll(true)
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
