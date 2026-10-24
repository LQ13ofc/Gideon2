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

    Section {
        title: "Entrada (microfone)"
        Text {
            text: "Em uso agora: " + (core.audioLive.enabled === true
                ? "captura ao vivo pelo dispositivo escolhido."
                : "PCM virtual da escuta de teste. A captura pelo microfone só existe com o Core iniciado com --live-audio.")
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
        EValueRow {
            label: "Escolha salva"
            value: page.choiceText(core.audioInputChoices, core.audioInputSaved)
        }
        Text {
            objectName: "liveInputStatus"
            text: core.audioLiveText
            textFormat: Text.PlainText
            color: core.micActive ? Theme.warning : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: "Estado da entrada ao vivo: " + text
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
            text: "A resposta por voz sai pelo dispositivo escolhido quando o Core roda com --live-audio; sem isso, a saída é virtual."
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
            text: "Os dispositivos são listados pelo sistema (pactl, depois pw-dump). Monitores de saída não aparecem. A troca vale na próxima sessão de voz. A captura ao vivo só existe com o Core iniciado com --live-audio. Nada aqui prova o microfone ou o alto-falante reais: a validação com hardware continua pendente."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
