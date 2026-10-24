import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Diagnóstico > Estado: the Core connection, the profile and the developer mode switch (behind a confirmation).
PageFrame {
    id: page
    objectName: "diagnosticsPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "diag_estado"

    PageHeader {
        title: "Estado"
        subtitle: "Core, configuração, perfil da Base e o que está acontecendo agora."
    }
    Banner {
        objectName: "diagnostics"
        kind: core.connected ? "info" : "error"
        text: core.configurationMessage || ((core.connected ? "Core conectado" : "Core desconectado") + " · " + core.diagnostic)
    }

    Section {
        title: "Core e configuração"
        Text { text: core.connected ? "Conectado ao Core" : "Core offline"; textFormat: Text.PlainText; color: core.connected ? Theme.success : Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true }
        Text { text: "Estado atual: " + L.stateText(core.state); textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true }
        Text { text: "Sessão de voz: " + (core.sessionId.length > 0 ? core.sessionId : "nenhuma"); textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true }
        Text { text: "Configuração: " + (core.configurationStatus === "safe_mode" ? "modo seguro" : "pronta"); textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true }
    }

    Section {
        title: "Base e privacidade"
        Text { text: core.packDescription || "Pacote de voz não configurado"; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Text { text: "Sem histórico de conversas em disco. Áudio e legendas ficam só em memória."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    }

    Section {
        title: "Últimos erros"
        Text {
            objectName: "lastErrors"
            text: core.result.length > 0 && !core.resultVerified ? core.result : "Nenhum erro recente nesta sessão."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
    }

    Section {
        title: "Modo desenvolvedor"
        SettingRow {
            label: "Modo desenvolvedor"
            help: "Mostra a sub-aba Desenvolvedor, com rótulos técnicos e comandos de teste. Ligar pede confirmação."
            settingKey: "behavior.devMode"
            disabledReason: AppState.uiLive() ? "" : "configurações do app indisponíveis"
            Toggle {
                objectName: "devModeToggle"
                checked: AppState.uiGet("behavior.devMode", false) === true
                onToggled: {
                    if (checked) { checked = false; devConfirm.open() }
                    else AppState.uiSet("behavior.devMode", false)
                }
            }
        }
    }

    Modal {
        id: devConfirm
        objectName: "devModeConfirm"
        title: "Ligar o modo desenvolvedor?"
        onAccepted: AppState.uiSet("behavior.devMode", true)
        Text {
            text: "O modo desenvolvedor mostra rótulos técnicos, comandos de teste e replays. Não muda permissões nem executa nada sozinho."
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton { objectName: "confirmDevMode"; variant: "primary"; text: "Ligar modo desenvolvedor"; Layout.alignment: Qt.AlignRight; onClicked: devConfirm.accept() }
    }
}
