import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Gideon.Visual 1.0

ApplicationWindow {
    id: window
    objectName: "mainWindow"
    visible: true
    width: 1380; height: 904
    minimumWidth: 480; minimumHeight: 520
    title: "Gideon"
    color: themeIndex === 2 ? "#101822" : themeIndex === 1 ? "#122039" : "#0c1730"
    font.family: "Noto Sans"
    font.pixelSize: 14
    palette.window: "#142440"; palette.windowText: "#edf2ff"
    palette.button: "#243b66"; palette.buttonText: "#edf2ff"
    palette.base: "#11203a"; palette.text: "#edf2ff"
    palette.highlight: accentColor; palette.highlightedText: "#ffffff"
    property int page: 0
    property int themeIndex: 0
    property color accentColor: "#7693ff"
    readonly property bool spacious: width >= 1080 && height >= 760
    readonly property bool packAvailable: core.wakeChoices.length > 0
    readonly property var navigation: ["Início", "Voz e Wake", "Áudio", "Aparência", "Permissões", "Diagnóstico", "Gideon Hub"]
    readonly property var navIcons: ["home", "voice", "audio", "appearance", "permissions", "diagnostics", "hub"]
    function wakeText() { var pack = core.snapshotPack; if (!pack.wake_phrases) return "Não configurada"; for (var i=0;i<pack.wake_phrases.length;i++) if (pack.wake_phrases[i].id === pack.active_phrase) return pack.wake_phrases[i].text; return "Não ativa"; }
    Dialog {
        id: preferences; objectName: "preferencesDialog"
        title: "Preferências da Base"; modal: true
        anchors.centerIn: parent; width: Math.min(420, window.width - 32)
        standardButtons: Dialog.Close
        background: GlassCard { theme: window.themeIndex }
        onOpened: { audible.checked = core.audibleFeedback; timeout.value = core.sessionTimeout; visual.checked = core.visualFeedback; volume.value = core.outputVolume }
        contentItem: ScrollView {
            implicitHeight: Math.min(settingsColumn.implicitHeight, window.height - 120)
            clip: true
        ColumnLayout {
            id: settingsColumn
            width: preferences.availableWidth
            Label { objectName: "configurationMessage"; visible: core.configurationMessage.length > 0; text: core.configurationMessage; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Button { objectName: "recoverConfigurationButton"; visible: core.configurationStatus === "safe_mode"; text: "Preservar arquivo e restaurar padrões"; enabled: core.recoveryAvailable; onClicked: core.recoverConfiguration(); Accessible.name: text }
            Label { objectName: "packDescription"; visible: core.packDescription.length > 0; text: core.packDescription; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            RowLayout {
                visible: core.wakeChoices.length > 0
                Layout.fillWidth: true
                ComboBox { id: wakeChoice; objectName: "wakeChoice"; Layout.fillWidth: true; model: core.wakeChoices; textRole: "text"; valueRole: "id"; enabled: core.preferencesAvailable; Accessible.name: "Frase de wake do pack" }
                Button { objectName: "selectWakeButton"; text: "Selecionar"; enabled: core.preferencesAvailable && wakeChoice.currentIndex >= 0 && core.wakeChoices[wakeChoice.currentIndex].qualification === "dev_qualified"; onClicked: core.selectWake(wakeChoice.currentValue) }
            }
            Label { objectName: "wakeQualification"; visible: core.wakeChoices.length > 0; text: wakeChoice.currentIndex >= 0 ? (core.wakeChoices[wakeChoice.currentIndex].qualification === "dev_qualified" ? "Qualificada em DEV; validação física pendente" : "POC_REQUIRED: frase sem qualidade aprovada") : ""; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            CheckBox { id: audible; objectName: "audiblePreference"; text: core.voiceAvailable ? "Resposta por voz (saída virtual)" : "Resposta por voz indisponível"; enabled: core.preferencesAvailable && core.voiceAvailable }
            CheckBox { id: visual; objectName: "visualPreference"; text: "Indicador visual de atividade"; enabled: core.preferencesAvailable }
            Label { text: "Ganho da saída virtual: " + core.outputVolume + "% (0% = mudo)"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            SpinBox { id: volume; objectName: "volumePreference"; from: 0; to: 100; stepSize: 5; editable: true; enabled: core.preferencesAvailable && core.voiceAvailable }
            Button { objectName: "saveFeedbackButton"; text: "Salvar indicador e ganho"; enabled: core.preferencesAvailable; onClicked: core.saveFeedback(visual.checked, volume.value) }
            Label { text: "Privacidade: capturas e legendas em memória; sem histórico persistente. Entrada/saída virtuais. CPU e sensibilidade fixas. Dispositivos físicos, outras vozes/idiomas e login automático indisponíveis."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { text: "Prazo da sessão em milissegundos"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            SpinBox { id: timeout; objectName: "timeoutPreference"; from: 50; to: 60000; stepSize: 1000; editable: true; enabled: core.preferencesAvailable }
            RowLayout {
                Button { objectName: "savePreferencesButton"; text: "Salvar"; enabled: core.preferencesAvailable; onClicked: core.savePreferences(audible.checked, timeout.value) }
                Button { objectName: "rollbackPreferencesButton"; text: "Restaurar anterior"; enabled: core.rollbackAvailable; onClicked: core.rollbackPreferences() }
            }
            Label { text: (core.configurationStatus === "safe_mode" ? "Padrões de recuperação: " : "Atual no Core: ") + (core.audibleFeedback ? "voz ligada" : "voz desligada") + " · " + core.sessionTimeout + " ms"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { objectName: "preferencesResult"; text: core.preferencesResult; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { text: "Alterações se aplicam à próxima sessão. Voz, frases e dispositivos dependem do pack e dos adaptadores disponíveis."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        }
    }
    Dialog {
        id: hubDialog; objectName: "hubDialog"
        title: "Plugins — Gideon Hub"; modal: true
        anchors.centerIn: parent; width: Math.min(420, window.width - 32)
        standardButtons: Dialog.Close
        background: GlassCard { theme: window.themeIndex }
        contentItem: ScrollView {
            implicitHeight: Math.min(hubColumn.implicitHeight, window.height - 120); clip: true
            ColumnLayout {
                id: hubColumn; width: hubDialog.availableWidth
                Label { objectName: "hubDescription"; text: core.hubDescription; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Repeater {
                    model: core.hubEntries
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Label { text: modelData.plugin_id + " " + modelData.semver + " · " + modelData.publisher; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { text: (modelData.status === "not_installed" ? "Não instalado" : "Incompatível: " + modelData.reason) + " · " + modelData.license; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { text: "Permissões declaradas (não aprovadas): " + (modelData.permissions.join(", ") || "nenhuma") + "\n" + modelData.support_policy; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                Label { text: "Instalação indisponível nesta etapa. O catálogo não concede acesso ao computador."; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
        }
    }
    Rectangle {
        id: sidebar
        width: window.width >= 1000 ? 232 : 64
        anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: window.themeIndex === 2 ? "#131e2c" : window.themeIndex === 1 ? "#1b2c47" : "#142445"
        Rectangle { anchors.right: parent.right; height: parent.height; width: 1; color: "#2b3d6a" }
        ColumnLayout {
            anchors.fill: parent; anchors.margins: sidebar.width > 100 ? 20 : 8; spacing: window.height < 640 ? 4 : 12
            RowLayout {
                Layout.topMargin: window.height < 640 ? 2 : 22; Layout.bottomMargin: window.height < 640 ? 10 : 30
                Image { source: "assets/gideon-orb.png"; Layout.preferredWidth: 44; Layout.preferredHeight: 44; fillMode: Image.PreserveAspectFit }
                ColumnLayout {
                    visible: sidebar.width > 100; spacing: 2
                    Label { text: "Gideon"; color: "#f3f6ff"; font.pixelSize: 25; font.bold: true }
                    Label { text: "Assistente pessoal"; color: "#aabbe1"; font.pixelSize: 12 }
                }
            }
            Repeater {
                model: window.navigation
                GlowButton {
                    required property int index
                    required property string modelData
                    objectName: "nav" + index
                    Layout.fillWidth: true; implicitHeight: window.height < 640 ? 40 : 52
                    padding: sidebar.width < 100 ? 8 : 12
                    text: sidebar.width > 100 ? modelData : ""
                    Accessible.name: modelData
                    image: "assets/" + window.navIcons[index] + ".png"
                    accent: window.accentColor; checked: window.page === index
                    onClicked: window.page = index
                    ToolTip.visible: hovered && sidebar.width < 100; ToolTip.text: modelData
                }
            }
            Item { Layout.fillHeight: true }
            Label { visible: sidebar.width > 100; text: "Base local\nEN · perfil virtual"; color: "#8fa5d0"; font.pixelSize: 12; Layout.bottomMargin: 18 }
        }
    }
    ColumnLayout {
        id: mainColumn; objectName: "mainColumn"
        anchors.left: sidebar.right; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
        anchors.margins: window.spacious ? 24 : 14; spacing: window.spacious ? 14 : 8
        RowLayout {
            Layout.fillWidth: true
            Label { text: window.navigation[window.page]; color: "#a7b9df"; font.pixelSize: 14; Layout.fillWidth: true }
            GlowButton { objectName: "hubButton"; text: window.width >= 720 ? "Plugins" : ""; image: "assets/hub.png"; Accessible.name: "Plugins"; enabled: core.connected; onClicked: hubDialog.open() }
            GlowButton { objectName: "settingsButton"; text: window.width >= 720 ? "Preferências" : ""; image: "assets/settings.png"; Accessible.name: "Preferências"; enabled: core.connected; onClicked: preferences.open() }
        }
        RowLayout {
            visible: window.page === 0 && window.spacious
            Layout.fillWidth: true; Layout.preferredHeight: 350; spacing: 14
            GlassCard {
                theme: window.themeIndex
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                RoundedImage { anchors.fill: parent; source: Qt.resolvedUrl("assets/hero-background.png"); opacity: window.themeIndex === 2 ? 0 : 0.55 }
                Image { id: heroOrb; source: "assets/gideon-orb.png"; anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; width: Math.min(parent.width * 0.47, parent.height - 24); height: width; fillMode: Image.PreserveAspectFit; visible: core.visualFeedback }
                ColumnLayout {
                    anchors.left: parent.left; anchors.leftMargin: 30; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.56; spacing: 14
                    Row { spacing: 12
                        Label { text: "Olá,"; color: "#f4f6ff"; font.pixelSize: 60; font.bold: true }
                        Label { text: "Lucas"; color: window.accentColor; font.pixelSize: 60; font.bold: true }
                    }
                    Label { text: core.connected ? "Seu Gideon, em um só lugar." : "Vamos reconectar ao Gideon."; color: "#c3d2f7"; font.pixelSize: 22; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Label { text: "Acompanhe a conversa, ajuste sua voz e conheça as capacidades disponíveis."; color: "#a8bbe2"; font.pixelSize: 16; wrapMode: Text.WordWrap; Layout.fillWidth: true; Layout.maximumWidth: 340 }
                    Label { text: "Base · áudio virtual · validação física pendente"; color: "#a6b9e2"; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                }
            }
            GlassCard {
                theme: window.themeIndex
                Layout.preferredWidth: 245; Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 20; spacing: 16
                    Label { text: "Estado do sistema"; color: "#edf2ff"; font.pixelSize: 18; font.bold: true }
                    Label { text: core.connected ? "Conectado ao Core" : "Core offline"; color: core.connected ? "#78debc" : "#f6c77e"; font.pixelSize: 13 }
                    Repeater {
                        model: [{name:"Wake", status:core.wakeStatus}, {name:"STT", status:core.sttStatus}, {name:"TTS", status:core.speechStatus}]
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            Label { text: modelData.name; color: "#d8e3ff"; font.pixelSize: 15; Layout.fillWidth: true }
                            Label { text: ({ready:"Pronto",completed:"Concluído",replay_finished:"Replay encerrado",unavailable:"Indisponível",speaking:"Respondendo",starting:"Iniciando",failed:"Falhou",idle:"Em espera",muted:"Mudo",disabled:"Desligado"})[modelData.status] || modelData.status; textFormat: Text.PlainText; color: modelData.status === "unavailable" ? "#b8aaca" : "#78debc"; font.pixelSize: 12 }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#33466c" }
                    Label { text: "Privacidade"; color: "#edf2ff"; font.bold: true; font.pixelSize: 16 }
                    Label { text: "Sem histórico de conversas.\nÁudio e legendas em memória."; color: "#aabde4"; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Item { Layout.fillHeight: true }
                }
            }
        }
        RowLayout {
            visible: window.page === 0 && window.spacious
            Layout.fillWidth: true; Layout.preferredHeight: 104; spacing: 14
            Repeater {
                model: [{title:"Frase de despertar",value:window.wakeText(),icon:"voice",page:1}, {title:"Entrada de áudio",value:window.packAvailable ? "PCM virtual" : "Indisponível",icon:"audio",page:2}, {title:"Modo",value:"Base · sem LLM",icon:"hub",page:6}]
                delegate: GlassCard {
                theme: window.themeIndex
                    required property var modelData
                    Layout.fillWidth: true; Layout.fillHeight: true
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 18
                        Image { source: "assets/" + modelData.icon + ".png"; Layout.preferredWidth: 30; Layout.preferredHeight: 30 }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: modelData.title; color: "#aebfe7"; font.pixelSize: 13 }
                            Label { text: modelData.value; textFormat: Text.PlainText; color: "#f2f5ff"; font.bold: true; font.pixelSize: 17; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                        GlowButton { text: "Abrir"; onClicked: window.page = modelData.page }
                    }
                }
            }
        }
        ScrollView {
            id: pageViewport; objectName: "pageViewport"
            visible: window.page !== 0
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            ColumnLayout {
                width: pageViewport.availableWidth; spacing: 16
                GlassCard {
                theme: window.themeIndex
                    Layout.fillWidth: true; implicitHeight: window.width > 900 ? 185 : 150; clip: true
                    RoundedImage { anchors.fill: parent; source: Qt.resolvedUrl("assets/hero-background.png"); opacity: window.themeIndex === 2 ? 0 : 0.4 }
                    Image { source: "assets/gideon-orb.png"; anchors.right: parent.right; anchors.rightMargin: 26; anchors.verticalCenter: parent.verticalCenter; width: 200; height: 200; visible: window.width > 900 && core.visualFeedback }
                    ColumnLayout {
                        anchors.left: parent.left; anchors.leftMargin: 26; anchors.verticalCenter: parent.verticalCenter; width: window.width > 900 ? parent.width - 260 : parent.width - 52; spacing: 10
                        Label { text: window.navigation[window.page]; color: "#f1f5ff"; font.pixelSize: window.width > 900 ? 52 : 24; font.bold: true }
                        Label { text: window.page === 1 ? "Configure como o Gideon escuta e responde." : window.page === 3 ? "Defina o estilo visual do Gideon." : window.page === 2 ? "Sua voz, seus ajustes de áudio." : window.page === 4 ? "Cada capacidade precisa de autorização." : window.page === 5 ? "Acompanhe o estado real da Base." : "Capacidades opcionais, em um só lugar."; color: "#b7caf3"; font.pixelSize: 17; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 1; Layout.fillWidth: true; implicitHeight: voiceColumn.implicitHeight + 44
                    ColumnLayout {
                        id: voiceColumn; anchors.fill: parent; anchors.margins: 22; spacing: 14
                        Label { text: "Frase de despertar"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Label { text: "Escolha uma frase qualificada do pack. A alteração requer reinício do Core."; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Flow {
                            Layout.fillWidth: true; spacing: 12; Layout.preferredHeight: childrenRect.height
                            Repeater {
                                model: core.wakeChoices
                                GlowButton {
                                    required property var modelData
                                    objectName: "wakeCard_" + modelData.id
                                    text: modelData.text + (modelData.qualification === "dev_qualified" ? " · DEV" : " · POC_REQUIRED")
                                    checked: window.packAvailable && core.snapshotPack.active_phrase === modelData.id
                                    enabled: core.preferencesAvailable && modelData.qualification === "dev_qualified"
                                    onClicked: core.selectWake(modelData.id)
                                }
                            }
                        }
                        Label { visible: core.wakeChoices.length === 0; text: "Nenhum pack de wake configurado."; color: "#b0c3e9" }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 1 || window.page === 2; Layout.fillWidth: true; implicitHeight: captureColumn.implicitHeight + 44
                    ColumnLayout {
                        id: captureColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: window.page === 1 ? "Captura" : "Resposta por voz"; color: "#f1f5ff"; font.bold: true; font.pixelSize: 21 }
                        Label { text: window.page === 1 ? "Entrada PCM virtual · pré-roll de 1 segundo · CPU. Microfone físico, AEC e redução de ruído ainda indisponíveis." : "Pocket TTS · Alba · inglês · saída virtual. Outras vozes e dispositivos físicos ainda indisponíveis."; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { visible: window.page === 2; text: "Ganho atual: " + core.outputVolume + "%"; color: "#b0c3e9" }
                        RowLayout {
                            visible: window.page === 2; Layout.fillWidth: true
                            Slider { id: gainSlider; objectName: "gainSlider"; from: 0; to: 100; stepSize: 5; value: core.outputVolume; enabled: core.preferencesAvailable && core.voiceAvailable; Layout.fillWidth: true; Accessible.name: "Ganho da resposta por voz" }
                            GlowButton { objectName: "applyGainButton"; text: "Aplicar"; enabled: core.preferencesAvailable && core.voiceAvailable; onClicked: core.saveFeedback(core.visualFeedback, Math.round(gainSlider.value)) }
                        }
                        GlowButton { text: "Abrir ajustes da Base"; enabled: core.connected; onClicked: preferences.open() }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 3; Layout.fillWidth: true; implicitHeight: appearanceColumn.implicitHeight + 44
                    ColumnLayout {
                        id: appearanceColumn; anchors.fill: parent; anchors.margins: 22; spacing: 16
                        GridLayout {
                            Layout.fillWidth: true; columns: window.width > 1000 ? 2 : 1; columnSpacing: 24; rowSpacing: 20
                            ColumnLayout { Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; spacing: 16
                        Label { text: "Tema"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Flow {
                            id: themeFlow; Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 12
                            Repeater { model: ["Gideon", "Clássico", "Minimalista"]
                                GlowButton {
                                    required property int index; required property string modelData
                                    objectName: "theme" + index; text: modelData; checked: window.themeIndex === index
                                    implicitWidth: 156; implicitHeight: 138; onClicked: window.themeIndex = index
                                    contentItem: Column {
                                        spacing: 8
                                        Rectangle {
                                            width: parent.width; height: 86; radius: 10; clip: true; color: index === 2 ? "#182233" : "#102044"
                                            Image { anchors.fill: parent; source: index === 0 ? "assets/gideon-orb.png" : "assets/hero-background.png"; fillMode: index === 0 ? Image.PreserveAspectFit : Image.PreserveAspectCrop; opacity: index === 2 ? 0.25 : 1 }
                                        }
                                        Text { text: modelData; color: "#edf2ff"; font.pixelSize: 15; font.bold: true }
                                    }
                                }
                            }
                        }
                            }
                            ColumnLayout { Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; spacing: 16
                        Label { text: "Cor de destaque"; color: "#f1f5ff"; font.pixelSize: 18; font.bold: true }
                        Flow {
                            Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 10
                            Repeater { model: [{name:"Azul",color:"#7693ff"}, {name:"Violeta",color:"#b386ff"}, {name:"Ciano",color:"#66dcf4"}, {name:"Rosa",color:"#f28bd7"}]
                                GlowButton { required property var modelData; objectName: "accent" + modelData.name; text: modelData.name; accent: modelData.color; checked: window.accentColor.toString() === modelData.color; onClicked: window.accentColor = modelData.color }
                            }
                        }
                            }
                        }
                        Label { text: "HUD visual"; color: "#f1f5ff"; font.pixelSize: 18; font.bold: true }
                        CheckBox { objectName: "visualPagePreference"; text: "Mostrar esfera e indicador de atividade"; checked: core.visualFeedback; enabled: core.preferencesAvailable; onClicked: core.saveFeedback(checked, core.outputVolume) }
                        Label { text: "Estado textual, legendas e cancelamento permanecem disponíveis."; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { text: "Tema e cor se aplicam a esta janela. O indicador é salvo pelo Core."; color: "#a4b8dc"; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 4; Layout.fillWidth: true; implicitHeight: permissionsColumn.implicitHeight + 44
                    ColumnLayout { id: permissionsColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: "Comandos da Base"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Label { text: "Comandos determinísticos passam pela política do Core. No perfil atual, efeitos são verificados em um ambiente isolado. O Hub apenas declara permissões; ainda não aprova nem executa plugins."; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 5; Layout.fillWidth: true; implicitHeight: diagnosticsColumn.implicitHeight + 44
                    ColumnLayout { id: diagnosticsColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: "Motores e conexão"; color: "#f1f5ff"; font.pixelSize: 21; font.bold: true }
                        Label { text: core.diagnostic; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { text: core.packDescription || "Pack de voz não configurado"; textFormat: Text.PlainText; color: "#b0c3e9"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                GlassCard {
                theme: window.themeIndex
                    visible: window.page === 6; Layout.fillWidth: true; implicitHeight: hubPageColumn.implicitHeight + 44
                    ColumnLayout { id: hubPageColumn; anchors.fill: parent; anchors.margins: 22; spacing: 12
                        Label { text: core.hubDescription; color: "#b0c3e9"; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        GlowButton { text: "Explorar catálogo"; enabled: core.connected; onClicked: hubDialog.open() }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Image { objectName: "activityIndicator"; source: "assets/gideon-orb.png"; visible: core.visualFeedback; Layout.preferredWidth: 38; Layout.preferredHeight: 38; fillMode: Image.PreserveAspectFit; Accessible.name: "Estado do Gideon" }
            Label { objectName: "aura"; text: ({idle:"Em espera",capturing:"Ouvindo",transcribing:"Transcrevendo",executing:"Executando",speaking:"Respondendo",offline:"Core indisponível",safe_mode:"Modo seguro",restart_required:"Reinício necessário"})[core.state] || "Erro"; color: "#e6edf4"; font.pixelSize: 20; Layout.fillWidth: true; Accessible.name: text }
            GlowButton { objectName: "cancelButton"; text: "Cancelar"; enabled: core.connected && core.sessionId.length > 0; onClicked: core.cancel(); Accessible.name: "Cancelar sessão" }
        }
        ScrollView {
            objectName: "transcriptViewport"; visible: window.page === 0 || core.sessionId.length > 0
            Layout.minimumHeight: 48; Layout.preferredHeight: window.page === 0 ? 90 : 56; Layout.fillWidth: true; Layout.fillHeight: window.page === 0
            TextArea { objectName: "subtitle"; text: core.subtitle; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; color: "#dce7ff"; font.pixelSize: 18; placeholderText: "Sua conversa aparecerá aqui."; Accessible.name: core.partial ? "Transcrição parcial" : "Transcrição final"; background: Rectangle { color: "#132341"; radius: 16; border.color: "#304572" } }
        }
        Label { objectName: "result"; visible: core.result.length > 0 && (window.page === 0 || core.sessionId.length > 0); text: core.result; Layout.fillWidth: true; wrapMode: Text.WordWrap; textFormat: Text.PlainText; color: core.resultVerified ? "#78debc" : "#ffc674"; Accessible.name: "Resultado: " + text }
        RowLayout {
            visible: window.page === 0 || core.sessionId.length > 0
            Layout.fillWidth: true
            TextField { id: input; objectName: "textInput"; color: "#dce7ff"; placeholderTextColor: "#a3b6db"; background: Rectangle { color: "#132341"; radius: 10; border.color: "#304572" } Layout.fillWidth: true; enabled: core.textAvailable; placeholderText: "Comando de texto no perfil de teste"; maximumLength: 512; Accessible.name: "Comando de texto"; onAccepted: if (core.textAvailable) { core.submitText(text); text = ""; } }
            GlowButton { objectName: "sendButton"; text: "Enviar"; enabled: core.textAvailable && input.text.trim().length > 0; onClicked: { core.submitText(input.text); input.text = ""; } }
        }
        Label { objectName: "diagnostics"; text: core.configurationMessage || ("Áudio virtual · " + core.diagnostic); color: "#a6b9df"; wrapMode: Text.WordWrap; Layout.fillWidth: true; font.pixelSize: 12; Accessible.name: "Diagnóstico: " + text }
    }
}
