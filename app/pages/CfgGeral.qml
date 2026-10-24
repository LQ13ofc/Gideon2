import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Configurações > Geral: the advanced switch and the general options, the items this version does not have (each with its
// reason), the export and import of the settings, the rollback of the Core preferences, and the danger zone (restore the
// app settings, behind a confirmation that asks for the profile name).
PageFrame {
    id: page
    objectName: "page_cfg_geral"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_geral"

    // This version has one profile; the danger zone asks for its name, as the profile would be named.
    readonly property string profileName: "Principal"
    readonly property bool safeMode: core.configurationStatus === "safe_mode"

    function restoreApp() {
        if (!AppState.uiLive()) return
        var result = ui.resetAll()
        AppState.toast(result.ok ? "Padrões do app restaurados." : result.error)
        profileConfirm.text = ""
    }

    ECfgSearch {}
    PageHeader {
        title: "Geral"
        subtitle: "Idioma, inicialização, opções avançadas e restauração da configuração."
    }
    ECfgNotice {}

    Section {
        title: "Opções"
        SettingRow {
            settingKey: "behavior.advanced"
            EToggleSetting { settingKey: "behavior.advanced" }
        }
        SettingRow {
            settingKey: "behavior.devMode"
            Toggle {
                id: devToggle
                objectName: "devModeToggle"
                readonly property bool stored: AppState.uiGet("behavior.devMode", false) === true
                checked: stored
                Accessible.name: "Modo desenvolvedor"
                onToggled: {
                    if (devToggle.checked) devModeConfirm.open()
                    else AppState.setSetting("behavior.devMode", false)
                    devToggle.checked = Qt.binding(function () { return devToggle.stored })
                }
            }
        }
        SettingRow {
            settingKey: "behavior.shortcuts"
            EToggleSetting { settingKey: "behavior.shortcuts" }
        }
        SettingRow {
            settingKey: "behavior.startTab"
            ESelectSetting { settingKey: "behavior.startTab" }
        }
        SettingRow {
            settingKey: "behavior.rememberWindow"
            EToggleSetting { settingKey: "behavior.rememberWindow" }
        }
        SettingRow {
            settingKey: "behavior.tips"
            EToggleSetting { settingKey: "behavior.tips" }
        }
        SettingRow {
            label: "Somente modificados"
            help: "Mostra nas telas de Configurações só as opções diferentes do padrão."
            Toggle {
                id: onlyToggle
                objectName: "onlyModifiedToggle"
                checked: AppState.onlyModified
                Accessible.name: "Somente modificados"
                onToggled: {
                    AppState.onlyModified = onlyToggle.checked
                    onlyToggle.checked = Qt.binding(function () { return AppState.onlyModified })
                }
            }
        }
    }

    Section {
        title: "Avisos e movimento"
        SettingRow {
            settingKey: "behavior.toastSeconds"
            ESliderSetting { settingKey: "behavior.toastSeconds"; from: 2; to: 10; stepSize: 1; unit: " s" }
        }
        SettingRow {
            settingKey: "behavior.confirmWrites"
            EToggleSetting { settingKey: "behavior.confirmWrites" }
        }
        SettingRow {
            settingKey: "behavior.reduceMotionFollowSystem"
            EToggleSetting { settingKey: "behavior.reduceMotionFollowSystem" }
        }
    }

    Section {
        title: "Idioma e inicialização"
        EValueRow {
            label: "Idioma da interface"
            value: "Português (fixo)"
        }
        SettingRow {
            label: "Outros idiomas"
            help: "Reconhecimento e voz usam inglês, fixo no pacote."
            disabledReason: "só o português existe na interface"
            Select {
                model: ["Português"]
                enabled: false
                implicitWidth: 240
                Accessible.name: "Outros idiomas (indisponível)"
            }
        }
        SettingRow {
            label: "Iniciar no login"
            help: "Abrir o Gideon ao entrar no computador."
            disabledReason: "inicialização automática no login não existe neste pacote"
            Toggle {
                enabled: false
                checked: false
                Accessible.name: "Iniciar no login (indisponível)"
            }
        }
        SettingRow {
            label: "Desempenho"
            help: "Controle de uso do processador."
            disabledReason: "não há controle de desempenho; o processamento usa CPU fixa"
        }
        SettingRow {
            label: "Perfis de configuração"
            help: "Um conjunto de opções por perfil."
            disabledReason: "só existe um perfil nesta versão"
        }
    }

    Section {
        title: "Arquivo de configurações"
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            GButton {
                objectName: "openExportSettingsButton"
                variant: "secondary"
                text: "Exportar configurações…"
                onClicked: settingsExport.open()
            }
            GButton {
                objectName: "openImportSettingsButton"
                variant: "secondary"
                text: "Importar configurações…"
                onClicked: settingsImport.open()
            }
        }
        Text {
            text: "Arquivo JSON sem segredos. Importar valida cada opção antes de aplicar; as que não passam são listadas."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    Section {
        title: "Configuração do Core"
        visible: page.safeMode
        Text {
            text: "Em modo seguro, o arquivo inválido é preservado antes de ser substituído pelos padrões. A recuperação fica em Diagnóstico › Recuperação."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "openRecoveryButton"
            variant: "secondary"
            text: "Abrir Diagnóstico › Recuperação"
            onClicked: Window.window.goPage("diag_recuperacao")
        }
    }

    Section {
        title: "Revisão e anterior"
        SettingRow {
            advanced: true
            label: "Restaurar anterior"
            help: "Desfaz a última alteração de preferências do Core (uma etapa). Se a frase mudar, reinicie o Core."
            disabledReason: core.rollbackAvailable ? "" : "não há configuração anterior"
            GButton {
                objectName: "rollbackPreferencesButton"
                variant: "secondary"
                text: "Restaurar anterior"
                Accessible.name: "Restaurar a configuração anterior do Core"
                enabled: core.rollbackAvailable
                onClicked: core.rollbackPreferences()
            }
        }
        EValueRow {
            label: "Revisão da configuração"
            value: core.preferencesRevision
            advanced: true
        }
    }

    Section {
        title: "Zona de perigo"
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: dangerBody.implicitHeight + Theme.space(32)
            radius: Theme.radiusCard
            color: "transparent"
            border.width: 1
            border.color: Theme.error
            ColumnLayout {
                id: dangerBody
                anchors.left: parent.left; anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Theme.space(16)
                spacing: Theme.space(10)
                Text {
                    text: "Restaurar padrões do app"
                    textFormat: Text.PlainText
                    color: Theme.error
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                    Layout.fillWidth: true
                }
                Text {
                    text: "Tema, cores, densidade, fonte, atalhos e avisos voltam ao padrão. A frase de despertar, o volume e o prazo do Core não mudam. Pede o nome do perfil."
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                GButton {
                    objectName: "restoreAppSettings"
                    variant: "danger"
                    text: "Restaurar padrões…"
                    Accessible.name: "Restaurar padrões do app"
                    enabled: AppState.uiLive()
                    onClicked: restoreConfirm.open()
                }
            }
        }
    }

    EAdvancedNote { subtab: "Geral" }

    Collapsible {
        title: "Como funciona"
        summary: "Em modo seguro, o arquivo inválido é preservado antes de ser substituído pelos padrões."
        Text {
            text: "Em modo seguro, o arquivo inválido é preservado antes de ser substituído pelos padrões. Restaurar os padrões do app não apaga o arquivo anterior."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    Modal {
        id: restoreConfirm
        objectName: "restoreConfirm"
        title: "Restaurar padrões do perfil " + page.profileName + "?"
        Text {
            text: "Estes valores voltam ao padrão do app. A frase de despertar, o volume e o prazo do Core não mudam."
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        FieldLabel { text: "Digite o nome do perfil para confirmar" }
        TextField {
            id: profileConfirm
            objectName: "restoreProfileName"
            Layout.fillWidth: true
            placeholderText: page.profileName
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            selectByMouse: true
            Accessible.name: "Nome do perfil para confirmar"
            background: Rectangle {
                radius: Theme.radius
                color: Theme.bg
                border.width: profileConfirm.activeFocus ? 2 : 1
                border.color: profileConfirm.activeFocus ? Theme.focusRing : Theme.strongOutline
            }
        }
        Text {
            text: "Digite " + page.profileName + " exatamente. O botão libera depois."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmRestoreAppSettings"
            variant: "danger"
            text: "Restaurar padrões"
            Layout.alignment: Qt.AlignRight
            enabled: profileConfirm.text === page.profileName
            onClicked: {
                page.restoreApp()
                restoreConfirm.close()
            }
        }
    }

    Modal {
        id: devModeConfirm
        objectName: "devModeConfirm"
        title: "Ligar modo desenvolvedor?"
        Text {
            text: "Mostra ferramentas de desenvolvimento em Diagnóstico. Não muda a conexão com o Core nem os dados."
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmDevModeButton"
            variant: "primary"
            text: "Ligar modo desenvolvedor"
            Layout.alignment: Qt.AlignRight
            onClicked: {
                AppState.setSetting("behavior.devMode", true)
                devModeConfirm.close()
            }
        }
    }

    EJsonDialog {
        id: settingsExport
        objectName: "settingsExportDialog"
        mode: "export"
    }
    EJsonDialog {
        id: settingsImport
        objectName: "settingsImportDialog"
        mode: "import"
    }
}
