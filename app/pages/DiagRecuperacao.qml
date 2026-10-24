import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Diagnóstico > Recuperação (docs/ui-spec/50-diagnostico.md §7): restart, configuration restore (Básico); the last good LLM
// configuration, the catalogue and the terminal commands (Avançado). The page never installs or repairs: it copies commands.
PageFrame {
    id: page
    objectName: "page_diag_recuperacao"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "diag_recuperacao"

    readonly property bool restartNeeded: core.connected && core.configurationStatus === "restart_required"
    readonly property string restartBadge: !core.connected ? "Indisponível" : restartNeeded ? "Necessário agora" : "Não necessário"
    readonly property string restartTone: !core.connected ? "neutral" : restartNeeded ? "warning" : "neutral"
    readonly property var commands: [
        {label: "Instalar", command: "gideon-install --install-root <RAIZ> install <PACOTE>"},
        {label: "Atualizar", command: "gideon-install --install-root <RAIZ> update <PACOTE>"},
        {label: "Reverter", command: "gideon-install --install-root <RAIZ> rollback"},
        {label: "Reparar", command: "gideon-install --install-root <RAIZ> repair"},
        {label: "Criar perfil", command: "gideon-install --install-root <RAIZ> profile create <NOME>"},
        {label: "Abrir perfil", command: "gideon-launch --install-root <RAIZ> <PERFIL>"}
    ]

    function copyCommand(text, label) {
        if (core.copyText(text)) AppState.toast("Comando copiado.")
        else AppState.toast("Não foi possível copiar o comando " + label + ".")
    }

    PageHeader {
        title: "Recuperação"
        subtitle: "Reinício, restauração de configuração e comandos para o terminal."
    }

    GridLayout {
        Layout.fillWidth: true
        columns: page.width >= Theme.narrowWidth && Theme.advanced ? 2 : 1
        columnSpacing: Theme.space(24)
        rowSpacing: Theme.space(24)

        // Bloco 1 (Básico): reinício e restauração de configuração.
        Section {
            title: "Reiniciar e restaurar"
            Layout.alignment: Qt.AlignTop
            Badge { text: page.restartBadge; tone: page.restartTone }
            FNote { tone: "text"; text: "Reinício exigido ao trocar a frase de despertar, mudar o feedback ou alterar plugins." }
            FNote { visible: page.restartNeeded; tone: "warn"; text: "A configuração salva só vale depois do reinício." }
            // Reinício pelo app: o Core responde e sai com código 75; gideon-launch o inicia de novo. Confirmação antes; sessões ativas bloqueiam.
            GButton {
                objectName: "restartCoreButton"
                variant: "secondary"
                text: "Reiniciar Core"
                enabled: core.coreRestartAvailable
                Accessible.name: "Reiniciar o Core"
                onClicked: restartConfirm.open()
            }
            FNote {
                small: true
                visible: !core.coreRestartAvailable && !core.coreRestartBusy
                text: !core.connected ? "Indisponível: Core desconectado."
                    : core.sessionId.length > 0 ? "Indisponível: sessão de voz em andamento."
                    : "Indisponível agora."
            }
            GProgressBar {
                objectName: "restartProgress"
                visible: core.coreRestartBusy
                indeterminate: true
                Layout.fillWidth: true
                Accessible.name: "Reinício do Core em andamento"
            }
            Text {
                objectName: "restartResult"
                visible: text.length > 0
                text: core.coreRestartResult
                textFormat: Text.PlainText
                color: core.coreRestartBusy ? Theme.text : Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                Accessible.name: "Reinício do Core: " + text
            }

            Text {
                text: "Configuração"
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.weight: 600
                Layout.topMargin: Theme.space(8)
            }
            FNote {
                tone: "text"
                text: core.configurationStatus === "safe_mode"
                    ? "Preserva o arquivo inválido e volta aos padrões. Depois, reinicie o Core."
                    : "Volta às preferências anteriores salvas pelo Core."
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(8)
                GButton {
                    objectName: "rollbackPreferencesButtonRecovery"
                    visible: core.rollbackAvailable
                    variant: "secondary"
                    text: "Restaurar anterior"
                    enabled: core.rollbackAvailable
                    onClicked: core.rollbackPreferences()
                }
                GButton {
                    objectName: "recoverConfigurationButton"
                    visible: core.recoveryAvailable
                    variant: "secondary"
                    text: "Preservar arquivo e restaurar padrões"
                    enabled: core.recoveryAvailable
                    Accessible.name: text
                    onClicked: recoverConfirm.open()
                }
            }
            Text {
                objectName: "recoveryResult"
                visible: text.length > 0
                text: core.preferencesResult
                textFormat: Text.PlainText
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        // Bloco 2 (Avançado): última configuração boa do motor LLM e catálogo.
        Section {
            visible: Theme.advanced
            title: "Motor LLM e catálogo"
            Layout.alignment: Qt.AlignTop
            Text {
                text: "Motor LLM"
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.weight: 600
            }
            // The last good config is saved by the Core when a model passes its test; without one the button stays disabled, with the reason.
            FNote { tone: "text"; text: "Guardada quando um modelo passa no teste em Modelos LLM. Voltar troca a configuração do motor." }
            GButton {
                objectName: "rollbackLlmButton"
                variant: "secondary"
                text: "Voltar à última configuração boa"
                enabled: core.llmRollbackAvailable
                Accessible.name: "Voltar à última configuração boa do motor LLM"
                onClicked: core.llmRollback()
            }
            FNote {
                small: true
                visible: !core.llmRollbackAvailable
                text: (core.llmConfig.lkg ? "Indisponível agora: o motor LLM está ocupado ou o Core não responde." : "Indisponível: nenhuma configuração boa foi salva ainda.")
            }
            Text {
                text: "Catálogo de plugins"
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.weight: 600
                Layout.topMargin: Theme.space(8)
            }
            FNote { tone: "text"; text: "Situação de armazenamento: Indisponível: a ponte ainda não informa o armazenamento do catálogo." }
            FNote { small: true; text: "O catálogo é verificado por SHA-256; o valor aparece em Desenvolvedor." }
        }
    }

    // Bloco 3 (Avançado): comandos de terminal. Copiar escreve o texto na área de transferência; nada é executado.
    Section {
        visible: Theme.advanced
        title: "Comandos no terminal"
        FNote {
            tone: "text"
            text: "Rodam fora do aplicativo, no terminal. Troque <RAIZ> pelo caminho absoluto da instalação; <PACOTE> pelo diretório do pacote; <NOME> pelo nome do perfil; <PERFIL> pelo perfil criado."
        }
        Repeater {
            model: page.commands
            delegate: FCommandRow {
                required property var modelData
                label: modelData.label
                command: modelData.command
                onCopyRequested: page.copyCommand(modelData.command, modelData.label)
            }
        }
        FNote { small: true; text: "Com o Core ativo, instalar, atualizar, reverter e reparar são recusados (código de saída 3)." }
        FNote { small: true; text: "Se o terminal mostrar \"run: gideon-install --install-root <RAIZ> repair\", execute o comando de reparo." }
        Collapsible {
            title: "Códigos de saída"
            FNote { small: true; tone: "text"; text: "0 ok · 2 uso incorreto · 3 perfil com Core ativo · 4 verificação do pacote falhou · 5 estado inválido ou reparo necessário · 6 bloqueado ou outro erro" }
        }
        FNote { small: true; text: "Reparo e atualização ficam no terminal: esta tela não executa instalador." }
    }

    Collapsible {
        title: "Como funciona"
        summary: "Reinícios e restaurações não apagam dados do usuário. Instalação e pacotes só pelo terminal."
        FNote {
            tone: "text"
            text: "Reiniciar o Core encerra os plugins em execução e refaz a conexão. A instalação versionada (gideon-install) não é executada por esta tela."
        }
    }

    // Reinício do Core: Cancelar é o foco inicial; confirmar envia core_restart (a ponte cuida da reconexão e do prazo de 30 s).
    Modal {
        id: restartConfirm
        objectName: "restartConfirm"
        title: "Reiniciar o Core agora?"
        standardButtons: Dialog.NoButton
        onOpened: restartCancel.forceActiveFocus()
        onAccepted: core.coreRestart()
        Text {
            text: "O Core será reiniciado. Sessões ativas bloqueiam o reinício."
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton {
                id: restartCancel
                objectName: "cancelRestartButton"
                variant: "secondary"
                text: "Cancelar"
                onClicked: restartConfirm.reject()
            }
            GButton {
                objectName: "confirmRestartButton"
                variant: "primary"
                text: "Reiniciar Core"
                Accessible.name: "Reiniciar o Core"
                onClicked: restartConfirm.accept()
            }
        }
    }
    Modal {
        id: recoverConfirm
        objectName: "recoverConfirm"
        title: "Preservar o arquivo e restaurar os padrões?"
        standardButtons: Dialog.NoButton
        onOpened: recoverCancel.forceActiveFocus()
        onAccepted: core.recoverConfiguration()
        Text {
            text: "O arquivo inválido fica guardado e as preferências voltam aos padrões. Reinicie o Core depois."
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton {
                id: recoverCancel
                variant: "secondary"
                text: "Cancelar"
                onClicked: recoverConfirm.reject()
            }
            GButton {
                objectName: "confirmRecoverButton"
                variant: "primary"
                text: "Restaurar padrões"
                Accessible.name: text
                onClicked: recoverConfirm.accept()
            }
        }
    }
}
