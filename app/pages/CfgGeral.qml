import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Configurações > Geral: the advanced switch and the general options; the first-run guide (again); "Iniciar no login"
// (a real XDG autostart entry, confirmed); the low-power mode; the shortcuts list (read-only); the settings profiles
// (create, duplicate, rename, switch, delete with confirmation); the export and import of the settings; the rollback of the
// Core preferences; and the danger zone (restore the app settings, behind a confirmation that asks for the profile name).
PageFrame {
    id: page
    objectName: "page_cfg_geral"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_geral"
    onVisibleChanged: if (visible) { readAutostart(); refreshProfiles() }

    // The name of the settings profile in use; the danger zone asks for it.
    readonly property string profileName: AppState.uiLive() ? String(ui.activeProfile) : "Padrão"
    readonly property bool safeMode: core.configurationStatus === "safe_mode"

    // Iniciar no login: what the file says now (read on page load and after each change).
    property var autostart: ({supported: false, reason: "configurações do app indisponíveis", enabled: false, exists: false, managed: false, path: ""})
    property bool autostartWanted: false
    // Perfis de configurações: the list as the app reports it now.
    property var profileList: []
    property string profileMode: "create"
    property string profileSource: ""
    property string pendingProfile: ""

    function readAutostart() {
        if (!AppState.uiLive()) return
        autostart = ui.autostartState()
    }
    function askAutostart(want) {
        autostartWanted = want
        autostartConfirm.open()
    }
    function applyAutostart() {
        if (!AppState.uiLive()) return
        var result = ui.setAutostart(autostartWanted)
        AppState.toast(result.ok ? (autostartWanted ? "O Gideon abre no login." : "O Gideon não abre mais no login.") : result.error)
        readAutostart()
    }

    function refreshProfiles() { profileList = AppState.uiLive() ? ui.profiles() : [] }
    function openProfileName(mode, source) {
        profileMode = mode
        profileSource = source
        profileNameField.text = mode === "rename" ? source : ""
        profileNameError.text = ""
        profileNameDialog.open()
    }
    function submitProfileName() {
        if (!AppState.uiLive()) return
        var name = profileNameField.text.trim()
        var result
        if (profileMode === "create") result = ui.createProfile(name)
        else if (profileMode === "duplicate") result = ui.duplicateProfile(profileSource, name)
        else result = ui.renameProfile(profileSource, name)
        if (!result.ok) { profileNameError.text = result.error; return }
        AppState.toast(profileMode === "create" ? "Perfil criado." : profileMode === "duplicate" ? "Perfil duplicado." : "Perfil renomeado.")
        refreshProfiles()
        profileNameDialog.close()
    }
    function switchProfile(name) {
        if (!AppState.uiLive()) return
        var result = ui.switchProfile(name)
        AppState.toast(result.ok ? "Perfil " + name + " em uso." : result.error)
        refreshProfiles()
    }
    function deleteProfile() {
        if (!AppState.uiLive()) return
        var result = ui.deleteProfile(pendingProfile)
        AppState.toast(result.ok ? "Perfil excluído." : result.error)
        refreshProfiles()
        profileDeleteConfirm.close()
    }

    Connections {
        target: AppState.uiLive() ? ui : null
        function onValuesChanged() { page.refreshProfiles() }
    }
    Component.onCompleted: { readAutostart(); refreshProfiles() }

    function restoreApp() {
        if (!AppState.uiLive()) return
        var result = ui.resetAll()
        AppState.toast(result.ok ? "Padrões do app restaurados." : result.error)
        profileConfirm.text = ""
    }

    PageHeader {
        title: "Geral"
        subtitle: "Idioma, inicialização, perfis, atalhos e restauração da configuração."
    }
    ECfgSearch {}
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
        title: "Desempenho"
        SettingRow {
            settingKey: "perf.lowPower"
            EToggleSetting { settingKey: "perf.lowPower" }
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
            help: page.autostart.exists && !page.autostart.managed
                ? "Já existe um atalho de inicialização que o Gideon não criou; ele não será alterado."
                : "Abre o Gideon ao entrar no computador. Cria um atalho do usuário no sistema."
            disabledReason: page.autostart.supported ? "" : page.autostart.reason
            Toggle {
                id: autostartToggle
                objectName: "autostartToggle"
                checked: page.autostart.enabled === true
                Accessible.name: "Iniciar no login"
                onToggled: {
                    var want = autostartToggle.checked
                    autostartToggle.checked = Qt.binding(function () { return page.autostart.enabled === true })
                    page.askAutostart(want)
                }
            }
        }
        Text {
            visible: page.autostart.supported && page.autostart.path.length > 0
            text: "Arquivo: " + page.autostart.path + (page.autostart.enabled ? " (ativo)" : " (inativo)")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            wrapMode: Text.WrapAnywhere
            Layout.fillWidth: true
        }
    }

    Section {
        title: "Introdução"
        SettingRow {
            label: "Refazer introdução"
            help: "Revê os quatro passos: privacidade, frase de despertar, dispositivos e volume, e atalhos."
            disabledReason: AppState.introBlockReason()
            GButton {
                objectName: "redoOnboardingButton"
                variant: "secondary"
                text: "Refazer introdução"
                Accessible.name: "Refazer a introdução"
                enabled: AppState.introBlockReason().length === 0
                onClicked: AppState.openOnboarding()
            }
        }
    }

    Section {
        title: "Atalhos de teclado"
        Text {
            text: AppState.uiGet("behavior.shortcuts", true) === true
                ? "Ligados. Para desligá-los, use o interruptor 'Atalhos de teclado' nesta página."
                : "Desligados neste app: nenhum atalho desta lista responde até você ligá-los de novo."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Repeater {
            model: [
                {keys: "Ctrl+K", text: "Paleta: vá a páginas, configurações e comandos."},
                {keys: "Ctrl+1 … Ctrl+5", text: "Troca de aba de nível 1."},
                {keys: "Ctrl+Tab", text: "Próxima sub-aba. Ctrl+Shift+Tab, a anterior."},
                {keys: "Ctrl+M", text: "Encerra a escuta quando há uma; sem escuta, avisa que o microfone não está disponível."},
                {keys: "Esc", text: "Cancela a escuta, ou fecha a caixa aberta (nunca as duas coisas)."}
            ]
            delegate: Rectangle {
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: Math.max(Theme.rowHeight - Theme.space(12), shortcutRow.implicitHeight + Theme.space(12))
                color: "transparent"
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.hairline }
                RowLayout {
                    id: shortcutRow
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Theme.space(16)
                    KeyCap {
                        keys: modelData.keys
                        Layout.preferredWidth: 170
                    }
                    Text {
                        text: modelData.text
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontHelp
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }

    Section {
        title: "Perfis de configurações"
        Text {
            text: "Cada perfil guarda o seu conjunto de opções do app. Trocar aplica o perfil na hora. Até 20 perfis."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Repeater {
            model: page.profileList
            delegate: ListRow {
                required property var modelData
                objectName: "profileRow_" + modelData.name
                title: modelData.name
                detail: modelData.active ? "Em uso" : (modelData.default ? "Perfil inicial" : "Pronto para usar")
                selected: modelData.active === true
                GButton {
                    objectName: "profileUse_" + modelData.name
                    variant: "ghost"
                    text: "Usar"
                    enabled: !modelData.active
                    Accessible.name: "Usar o perfil " + modelData.name
                    onClicked: page.switchProfile(modelData.name)
                }
                GButton {
                    objectName: "profileDuplicate_" + modelData.name
                    variant: "ghost"
                    text: "Duplicar"
                    Accessible.name: "Duplicar o perfil " + modelData.name
                    onClicked: page.openProfileName("duplicate", modelData.name)
                }
                GButton {
                    objectName: "profileRename_" + modelData.name
                    variant: "ghost"
                    text: "Renomear"
                    enabled: !modelData.default
                    Accessible.name: "Renomear o perfil " + modelData.name
                    onClicked: page.openProfileName("rename", modelData.name)
                }
                GButton {
                    objectName: "profileDelete_" + modelData.name
                    variant: "danger"
                    text: "Excluir"
                    enabled: !modelData.default && !modelData.active
                    Accessible.name: "Excluir o perfil " + modelData.name
                    onClicked: { page.pendingProfile = modelData.name; profileDeleteConfirm.open() }
                }
            }
        }
        GButton {
            objectName: "newProfileButton"
            variant: "secondary"
            text: "Novo perfil…"
            enabled: AppState.uiLive()
            onClicked: page.openProfileName("create", "")
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
            text: "Arquivo JSON sem segredos, do perfil em uso. Importar valida cada opção antes de aplicar; as que não passam são listadas."
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
                    text: "Tema, cores, densidade, fonte, atalhos e avisos do perfil " + page.profileName + " voltam ao padrão. A frase de despertar, o volume e o prazo do Core não mudam. Pede o nome do perfil."
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
            text: "Em modo seguro, o arquivo inválido é preservado antes de ser substituído pelos padrões. Restaurar os padrões do app não apaga o arquivo anterior. Cada perfil tem o seu arquivo; excluir um perfil apaga só o dele."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    Modal {
        id: autostartConfirm
        objectName: "autostartConfirm"
        title: page.autostartWanted ? "Iniciar o Gideon no login?" : "Parar de iniciar no login?"
        Text {
            text: page.autostartWanted
                ? "Cria o arquivo " + page.autostart.path + " para abrir o Gideon ao entrar no computador. Nada mais muda."
                : "Remove o arquivo " + page.autostart.path + ". O Gideon só abre quando você o iniciar."
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WrapAnywhere
            Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmAutostartButton"
            variant: "primary"
            text: page.autostartWanted ? "Iniciar no login" : "Parar no login"
            Layout.alignment: Qt.AlignRight
            onClicked: {
                page.applyAutostart()
                autostartConfirm.close()
            }
        }
    }

    Modal {
        id: profileNameDialog
        objectName: "profileNameDialog"
        title: page.profileMode === "create" ? "Novo perfil"
            : page.profileMode === "duplicate" ? "Duplicar o perfil " + page.profileSource
            : "Renomear o perfil " + page.profileSource
        FieldLabel { text: "Nome do perfil: letras sem acento, números, espaço, _ ou -; até 32 caracteres" }
        TextField {
            id: profileNameField
            objectName: "profileNameField"
            Layout.fillWidth: true
            placeholderText: "Nome do perfil"
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            selectByMouse: true
            Accessible.name: "Nome do perfil"
            onAccepted: page.submitProfileName()
            background: Rectangle {
                radius: Theme.radius
                color: Theme.bg
                border.width: profileNameField.activeFocus ? 2 : 1
                border.color: profileNameField.activeFocus ? Theme.focusRing : Theme.strongOutline
            }
        }
        Text {
            id: profileNameError
            objectName: "profileNameError"
            text: ""
            visible: text.length > 0
            textFormat: Text.PlainText
            color: Theme.error
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmProfileNameButton"
            variant: "primary"
            text: page.profileMode === "create" ? "Criar perfil" : page.profileMode === "duplicate" ? "Duplicar" : "Renomear"
            Layout.alignment: Qt.AlignRight
            enabled: profileNameField.text.trim().length > 0
            onClicked: page.submitProfileName()
        }
    }

    Modal {
        id: profileDeleteConfirm
        objectName: "profileDeleteConfirm"
        title: "Excluir o perfil " + page.pendingProfile + "?"
        Text {
            text: "Os ajustes deste perfil são apagados do disco. Os outros perfis não mudam. Não é possível desfazer."
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmDeleteProfileButton"
            variant: "danger"
            text: "Excluir perfil"
            Layout.alignment: Qt.AlignRight
            onClicked: page.deleteProfile()
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
