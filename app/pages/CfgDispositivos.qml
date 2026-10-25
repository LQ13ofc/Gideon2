import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Configurações > Dispositivos (B16): the microphone and the speaker the Core lists from the system (pactl or pw-dump), the
// choice saved in the Core ("Padrão do sistema" by default), the live capture status and the camera and screen (synthetic).
// Changes take effect in the next voice session. Nothing here proves a physical device works: that is a human validation.
PageFrame {
    id: page
    objectName: "page_cfg_dispositivos"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_dispositivos"

    // The text of the saved choice in a list ("Padrão do sistema" when the choice is the system default).
    function choiceText(list, value) {
        for (var i = 0; i < list.length; i++) if (list[i].value === value) return list[i].text
        return "Padrão do sistema"
    }
    // The row of the saved value (0 when the list has no such row). It reads the list itself, so the row follows a new list.
    function indexFor(list, value) {
        for (var i = 0; i < list.length; i++) if (list[i].value === value) return i
        return 0
    }
    // Shown under a list: why there is nothing to choose, or "" when the list has entries.
    function emptyText(kind) {
        if (!core.audioDevices.known || core.audioDevices.source === "none") return ""
        return core.audioDevices[kind].length === 0 ? (kind === "inputs" ? "Nenhum microfone listado pelo sistema." : "Nenhum alto-falante listado pelo sistema.") : ""
    }

    PageHeader {
        title: "Dispositivos"
        subtitle: "Microfone e alto-falante usados pelo Gideon. A lista vem do sistema; a troca vale na próxima sessão de voz."
        GButton {
            objectName: "refreshAudioDevicesButton"
            variant: "secondary"
            text: "Atualizar lista"
            Accessible.name: "Atualizar a lista de dispositivos de áudio"
            enabled: core.connected
            onClicked: core.refreshAudioDevices()
        }
    }
    ECfgSearch {}
    ECfgNotice {}

    // A13: the saved input (the system default included) measured bad by the microphone assistant, and a clean one exists.
    // The Core text names the problems; "Usar o …" saves the other input as Gideon's own choice (never the system default).
    Banner {
        objectName: "micBannerWarning"
        kind: "warn"
        text: core.micBanner.text || ""
        actionText: core.micBanner.action || ""
        onActionRequested: core.useAudioInput(core.micBanner.device)
    }

    // U2 and A13: the device list loads when the page opens. The assistant runs by itself once per Core session, only
    // while the live microphone is on (consent already given); otherwise the owner presses "Verificar microfones".
    function loadDevices() {
        if (!core.connected) return
        core.refreshAudioDevices()
        if (core.audioLive.enabled === true && core.micRecommendation.state === "idle") core.recommendMicrophones()
    }
    onVisibleChanged: if (visible) loadDevices()
    Component.onCompleted: if (visible) loadDevices()

    // The list state as the Core reports it: unknown until the first refresh, unsupported when no tool answers, else empty.
    Text {
        objectName: "audioDevicesStatus"
        visible: text.length > 0
        text: core.audioDevices.status
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        objectName: "audioRefreshResult"
        visible: text.length > 0
        text: core.audioResult
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    // A6 consent for the live microphone. The switch shows the saved choice; turning it on opens the consent first, and
    // the Core starts listening at its next start (Reiniciar agora applies it now, when no voice session runs).
    Section {
        title: "Escuta do microfone"
        Text {
            text: "Desligada, o Gideon não abre o microfone. Ligada, ele ouve o microfone escolhido abaixo só para detectar a frase de ativação. O áudio fica na memória e nada é gravado em disco. A troca vale depois de reiniciar o Core."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Toggle {
            id: liveSwitch
            objectName: "liveAudioSwitch"
            text: "Ouvir o microfone (ativação por voz)"
            Accessible.name: "Ouvir o microfone para a ativação por voz"
            checked: core.liveAudioEnabled
            enabled: core.preferencesAvailable
            onToggled: {
                if (checked) consent.open()
                else core.setLiveAudio(false)
                // The switch follows the Core only: a click is not a change until the Core saves it.
                checked = Qt.binding(function () { return core.liveAudioEnabled })
            }
        }
        Text {
            objectName: "liveInputStatus"
            text: core.audioLiveText
            textFormat: Text.PlainText
            color: core.micActive || core.liveAudioRestartRequired ? Theme.warning : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: "Estado da escuta do microfone: " + text
        }
        RowLayout {
            objectName: "liveAudioRestartRow"
            visible: core.liveAudioRestartRequired
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Text {
                text: "A escolha só vale no próximo início do Core. Sessões de voz em andamento bloqueiam o reinício."
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            GButton {
                objectName: "liveAudioRestartButton"
                variant: "primary"
                text: "Reiniciar agora"
                Accessible.name: "Reiniciar o Core agora para aplicar a escuta do microfone"
                enabled: core.coreRestartAvailable
                onClicked: core.coreRestart()
            }
        }
    }

    // A9: the level the Core hears from the live input (numbers only, 5 updates a second at most). The meter names every
    // zone in words; without the listening on, it says how to see it.
    Section {
        title: "Nível do microfone"
        Text {
            text: "Mostra o nível do microfone escolhido enquanto a escuta está ligada: o sinal, o ruído de fundo e alertas. Não grava nada."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        ILevelMeter {
            objectName: "dispositivosLevelMeter"
            view: core.audioLevel
        }
    }

    // Opened by the switch; Cancelar (the default) leaves the saved value as it was. A13: after the Core saves the
    // switch on, the microphone assistant runs (before the restart) so the banner above is current.
    property bool assistantArmed: false
    Connections {
        target: core
        function onPreferencesChanged() {
            if (page.assistantArmed && core.liveAudioEnabled) {
                page.assistantArmed = false
                core.recommendMicrophones()
            }
        }
    }
    LiveAudioConsent {
        id: consent
        onAgreed: { core.setLiveAudio(true); page.assistantArmed = true }
    }

    Section {
        title: "Entrada (microfone)"
        Text {
            text: "Em uso agora: " + (core.audioLive.enabled === true
                ? "captura ao vivo pelo dispositivo escolhido."
                : "entrada virtual (PCM de teste). O microfone entra em uso com a escuta ligada e o Core reiniciado.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        SettingRow {
            settingKey: "core.audioInput"
            RowLayout {
                spacing: Theme.space(10)
                Select {
                    id: inputSelect
                    objectName: "audioInputSelect"
                    model: core.audioInputChoices
                    textRole: "text"
                    valueRole: "value"
                    implicitWidth: 320
                    currentIndex: page.indexFor(core.audioInputChoices, core.audioInputSaved)
                    enabled: AppState.blockReason("core.audioInput") === ""
                    Accessible.name: "Microfone de entrada"
                    onActivated: {
                        AppState.setSetting("core.audioInput", currentValue)
                        currentIndex = Qt.binding(function () { return page.indexFor(core.audioInputChoices, core.audioInputSaved) })
                    }
                }
                GButton {
                    objectName: "restoreAudioInput"
                    variant: "ghost"
                    text: "Restaurar padrão"
                    Accessible.name: "Restaurar o microfone para o padrão do sistema"
                    enabled: AppState.blockReason("core.audioInput") === "" && core.audioInputSaved !== "default"
                    onClicked: AppState.setSetting("core.audioInput", "default")
                }
            }
        }
        Text {
            objectName: "audioInputEmpty"
            visible: text.length > 0
            text: page.emptyText("inputs")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        EToggleSetting { settingKey: "core.inputConditioning" }
        EValueRow {
            label: "Escolha salva"
            value: page.choiceText(core.audioInputChoices, core.audioInputSaved)
        }
        EValueRow {
            label: "Formato da entrada"
            value: "PCM mono 16 kHz"
            advanced: true
        }
        EValueRow {
            label: "Código do estado de captura"
            value: String(core.sttStatus)
            advanced: true
        }
    }

    Section {
        title: "Saída (alto-falante)"
        Text {
            text: "A resposta por voz sai pelo dispositivo escolhido quando a escuta do microfone está ligada e o Core foi reiniciado; sem isso, a saída é virtual."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        SettingRow {
            settingKey: "core.audioOutput"
            RowLayout {
                spacing: Theme.space(10)
                Select {
                    id: outputSelect
                    objectName: "audioOutputSelect"
                    model: core.audioOutputChoices
                    textRole: "text"
                    valueRole: "value"
                    implicitWidth: 320
                    currentIndex: page.indexFor(core.audioOutputChoices, core.audioOutputSaved)
                    enabled: AppState.blockReason("core.audioOutput") === ""
                    Accessible.name: "Alto-falante de saída"
                    onActivated: {
                        AppState.setSetting("core.audioOutput", currentValue)
                        currentIndex = Qt.binding(function () { return page.indexFor(core.audioOutputChoices, core.audioOutputSaved) })
                    }
                }
                GButton {
                    objectName: "restoreAudioOutput"
                    variant: "ghost"
                    text: "Restaurar padrão"
                    Accessible.name: "Restaurar o alto-falante para o padrão do sistema"
                    enabled: AppState.blockReason("core.audioOutput") === "" && core.audioOutputSaved !== "default"
                    onClicked: AppState.setSetting("core.audioOutput", "default")
                }
            }
        }
        Text {
            objectName: "audioOutputEmpty"
            visible: text.length > 0
            text: page.emptyText("outputs")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        EValueRow {
            label: "Escolha salva"
            value: page.choiceText(core.audioOutputChoices, core.audioOutputSaved)
        }
        Text {
            objectName: "liveOutputStatus"
            text: core.audioOutputText
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    // A13 assistant: 2 s per listed input, one after another. Ranks them; never saves a choice by itself.
    function recommendationText() {
        var rec = core.micRecommendation
        if (rec.state === "running") return "Verificando os microfones (2 s cada), um de cada vez…"
        if (rec.state === "failed") return "Não foi possível verificar: " + (rec.error || "erro desconhecido") + "."
        if (rec.state !== "done") return "Ainda não verificado. Verifique para comparar os microfones da lista."
        var best = ""
        for (var i = 0; i < rec.rows.length; i++) if (rec.rows[i].recommended) best = rec.rows[i].label
        var head = rec.currentIsBad ? "O microfone atual não capta bem: " + rec.reason + "." : "O microfone atual está bom."
        return head + (best.length > 0 ? " Melhor encontrado: " + best + "." : " Nenhum microfone limpo foi encontrado.")
    }
    Section {
        title: "Assistente do microfone"
        Text {
            text: "Grava 2 segundos de cada microfone da lista, um de cada vez, e compara o sinal: saturação, ruído grave, ruído de fundo e nível. Não grava em disco e não muda o padrão do sistema. Escolher um microfone só acontece quando você clica em \"Usar este\"."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "micRecommendButton"
            variant: "secondary"
            text: "Verificar microfones"
            Accessible.name: "Verificar os microfones da lista por 2 segundos cada"
            enabled: core.connected && core.micRecommendation.state !== "running" && core.sessionId.length === 0
            onClicked: core.recommendMicrophones()
        }
        Text {
            objectName: "micRecommendStatus"
            text: page.recommendationText()
            textFormat: Text.PlainText
            color: core.micRecommendation.currentIsBad === true ? Theme.warning : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: "Resultado da verificação dos microfones: " + text
        }
        Repeater {
            model: core.micRecommendation.rows
            delegate: RowLayout {
                objectName: "micRecommendRow"
                Layout.fillWidth: true
                spacing: Theme.space(10)
                Text {
                    text: modelData.label + (modelData.current ? " (atual)" : "") + (modelData.camera ? " · câmera" : "")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    text: modelData.error !== "" ? "não medido" : modelData.problems
                    textFormat: Text.PlainText
                    color: modelData.problems === "sem problemas" ? Theme.success : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                    wrapMode: Text.WordWrap
                }
                GButton {
                    objectName: "micRecommendUse"
                    variant: "ghost"
                    text: "Usar este"
                    Accessible.name: "Usar " + modelData.label + " como microfone do Gideon"
                    enabled: core.preferencesAvailable && !modelData.camera && modelData.problems === "sem problemas" && !modelData.current
                    onClicked: core.useAudioInput(modelData.id)
                }
            }
        }
    }

    // A9: each listed input is recorded for 3 s, one after another; the result table ranks them. Nothing is saved unless "Usar este".
    Section {
        title: "Testar microfones"
        Text {
            text: "Cada teste usa o microfone por 3 segundos. Os microfones são testados um de cada vez, com ou sem a escuta ligada."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            objectName: "micProbeEmpty"
            visible: (core.audioDevices.inputs || []).length === 0
            text: "Atualize a lista de dispositivos antes de testar."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        IMicProbe {}
    }

    Section {
        title: "Câmera e tela"
        EValueRow {
            label: "Câmera: simulada"
            badge: "SINTÉTICO"
            note: "Indisponível: sem câmera real."
        }
        EValueRow {
            label: "Tela: simulada"
            badge: "SINTÉTICO"
            note: "Indisponível: sem captura de tela real."
        }
        GButton {
            objectName: "perceptionLinkButton"
            variant: "ghost"
            text: "Ver em Extensões › Percepção e ação"
            enabled: core.perceptionAvailable
            onClicked: Window.window.goPage("percepcao")
        }
        Text {
            visible: !core.perceptionAvailable
            text: "Indisponível: nenhum plugin de percepção em execução."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            Layout.fillWidth: true
        }
    }

    Collapsible {
        title: "Como funciona"
        summary: "Os dispositivos vêm da lista do sistema. A troca vale na próxima sessão de voz."
        Text {
            text: "Os dispositivos são listados pelo sistema (pactl, depois pw-dump). Monitores de saída não aparecem. A troca vale na próxima sessão de voz. A captura ao vivo só existe com a escuta do microfone ligada e o Core reiniciado depois disso. Nada aqui prova o microfone ou o alto-falante reais: a validação com hardware continua pendente."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
