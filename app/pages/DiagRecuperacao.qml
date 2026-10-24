import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Diagnóstico > Recuperação: the safe-mode recovery and the last good preferences. Anything that needs a Core restart says so.
PageFrame {
    id: page
    objectName: "page_diag_recuperacao"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "diag_recuperacao"

    PageHeader {
        title: "Recuperação"
        subtitle: "Modo seguro, configuração anterior e o que fazer quando algo não vai bem."
    }
    Section {
        title: "Configuração"
        Text { text: core.configurationStatus === "safe_mode" ? "Modo seguro: o arquivo de configuração não pôde ser lido." : "Configuração normal."; textFormat: Text.PlainText; color: core.configurationStatus === "safe_mode" ? Theme.warning : Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        GButton {
            objectName: "recoverConfigurationButton"
            visible: core.configurationStatus === "safe_mode"
            variant: "danger"
            text: "Preservar arquivo e restaurar padrões"
            enabled: core.recoveryAvailable
            Accessible.name: text
            onClicked: recoverConfirm.open()
        }
        GButton {
            objectName: "rollbackPreferencesButtonRecovery"
            variant: "secondary"
            text: "Restaurar configuração anterior"
            enabled: core.rollbackAvailable
            onClicked: core.rollbackPreferences()
        }
        Text { objectName: "recoveryResult"; visible: text.length > 0; text: core.preferencesResult; textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    }
    Section {
        title: "Reinício e reparo"
        SettingRow { label: "Reiniciar Core"; help: "Necessário ao trocar a frase de wake, o feedback ou os plugins."; disabledReason: "o app ainda não reinicia o Core; use o terminal" }
        SettingRow { label: "Reparar instalação"; help: "Recria os arquivos do pacote."; disabledReason: "use o comando de reparo do terminal" }
    }
    Modal {
        id: recoverConfirm
        objectName: "recoverConfirm"
        title: "Restaurar padrões?"
        onAccepted: core.recoverConfiguration()
        Text {
            text: "O arquivo atual é preservado e a configuração volta aos padrões. Nada é apagado."
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton { objectName: "confirmRecoverButton"; variant: "danger"; text: "Restaurar"; Layout.alignment: Qt.AlignRight; onClicked: recoverConfirm.accept() }
    }
}
