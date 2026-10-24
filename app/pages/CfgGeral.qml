import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Configurações > Geral: advanced options, shortcuts, the items that are not available yet (each with its reason),
// and the reset of the app settings (behind a confirmation).
PageFrame {
    id: page
    objectName: "page_cfg_geral"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_geral"

    readonly property bool canSave: AppState.uiLive()

    PageHeader {
        title: "Geral"
        subtitle: "Opções gerais do app e restauração."
    }

    Section {
        title: "Opções"
        SettingRow {
            label: "Mostrar opções avançadas"
            help: "Mostra campos técnicos nas sub-abas. Continua fora de Diagnóstico › Desenvolvedor."
            settingKey: "behavior.advanced"
            disabledReason: page.canSave ? "" : "configurações do app indisponíveis"
            Toggle { checked: AppState.uiGet("behavior.advanced", false) === true; onToggled: AppState.uiSet("behavior.advanced", checked) }
        }
        SettingRow {
            label: "Atalhos de teclado"
            help: "Ctrl+1 a Ctrl+5 trocam de aba; Ctrl+Tab troca de sub-aba; Ctrl+K abre a paleta."
            settingKey: "behavior.shortcuts"
            disabledReason: page.canSave ? "" : "configurações do app indisponíveis"
            Toggle { checked: AppState.uiGet("behavior.shortcuts", true) === true; onToggled: AppState.uiSet("behavior.shortcuts", checked) }
        }
        SettingRow {
            label: "Duração dos avisos"
            help: "Quantos segundos um aviso fica na tela."
            settingKey: "behavior.toastSeconds"
            disabledReason: page.canSave ? "" : "configurações do app indisponíveis"
            GSlider { from: 2; to: 10; stepSize: 1; value: Number(AppState.uiGet("behavior.toastSeconds", 4)); implicitWidth: 180; onMoved: AppState.uiSet("behavior.toastSeconds", Math.round(value)) }
        }
    }

    Section {
        title: "Indisponível nesta versão"
        SettingRow { label: "Idioma da interface"; help: "Português é o único idioma por enquanto."; disabledReason: "só português nesta versão" }
        SettingRow { label: "Aba inicial ao abrir"; help: "Qual aba abre ao iniciar o app."; disabledReason: "ainda não implementado" }
        SettingRow { label: "Iniciar no login"; help: "Abrir o Gideon ao entrar no computador."; disabledReason: "início automático ainda não existe" }
    }

    Section {
        title: "Restaurar"
        Text {
            objectName: "configurationMessage"
            visible: text.length > 0
            text: core.configurationMessage
            textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "restoreAppSettings"
            variant: "danger"
            text: "Restaurar padrões do app"
            Accessible.name: "Restaurar padrões do app"
            enabled: page.canSave
            onClicked: restoreConfirm.open()
        }
    }

    Modal {
        id: restoreConfirm
        objectName: "restoreConfirm"
        title: "Restaurar padrões do app?"
        onAccepted: { if (typeof ui !== "undefined" && ui) ui.resetAll() }
        Text {
            text: "Tema, cores, densidade, fonte, atalhos e avisos voltam ao padrão. A frase de wake, o volume e os plugins do Core não mudam."
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton { objectName: "confirmRestoreAppSettings"; variant: "danger"; text: "Restaurar"; Layout.alignment: Qt.AlignRight; onClicked: restoreConfirm.accept() }
    }
}
