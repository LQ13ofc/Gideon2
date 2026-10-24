import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Configurações > Áudio: the reply volume (a draft until "Aplicar"), the spoken reply and the sound cues. The indicator
// lives in Aparência; here it is only a link. Core values show "Aplicando…" until the Core confirms them.
PageFrame {
    id: page
    objectName: "page_cfg_audio"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_audio"

    // Volume draft: -1 when there is none; the saved value is shown otherwise.
    property int draft: -1
    readonly property int saved: Number(AppState.uiGet("core.responseGain", 100))
    readonly property int shown: draft >= 0 ? draft : saved
    readonly property bool dirty: draft >= 0 && draft !== saved
    readonly property bool gainBlocked: AppState.blockReason("core.responseGain") !== ""
    readonly property bool visualOn: AppState.uiGet("core.visualFeedback", true) === true

    onSavedChanged: draft = -1

    function apply() {
        if (!dirty) return
        AppState.setSetting("core.responseGain", draft)
    }

    PageHeader {
        title: "Áudio"
        subtitle: "Volume e feedback da resposta do Gideon. Vale a partir da próxima sessão."
        GButton {
            objectName: "applyGainButton"
            variant: "primary"
            text: "Aplicar"
            Accessible.name: "Aplicar o volume da resposta por voz"
            enabled: page.dirty && !page.gainBlocked
            onClicked: page.apply()
        }
    }
    ECfgSearch {}
    ECfgNotice {}

    Section {
        title: "Volume da resposta"
        SettingRow {
            settingKey: "core.responseGain"
            RowLayout {
                spacing: Theme.space(12)
                GSlider {
                    id: gain
                    objectName: "gainSlider"
                    from: 0
                    to: 100
                    stepSize: 5
                    value: page.shown
                    enabled: !page.gainBlocked
                    Layout.preferredWidth: 220
                    Accessible.name: "Volume da resposta por voz, por cento"
                    onMoved: page.draft = Math.round(value)
                }
                Binding {
                    target: gain
                    property: "value"
                    value: page.shown
                    when: !gain.pressed
                }
                SpinBox {
                    id: volume
                    objectName: "volumePreference"
                    from: 0
                    to: 100
                    stepSize: 5
                    editable: true
                    value: page.shown
                    enabled: !page.gainBlocked
                    Accessible.name: "Volume da resposta, por cento"
                    onValueModified: page.draft = value
                }
                Binding {
                    target: volume
                    property: "value"
                    value: page.shown
                    when: !volume.activeFocus
                }
            }
        }
        Text {
            visible: page.dirty
            text: "Alterações não aplicadas: " + page.draft + "%. Clique em Aplicar."
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        EValueRow {
            label: "Ganho salvo no Core"
            value: page.saved + "%"
            advanced: true
        }
    }

    Section {
        title: "Resposta"
        SettingRow {
            settingKey: "core.audibleFeedback"
            EToggleSetting {
                objectName: "audiblePreference"
                settingKey: "core.audibleFeedback"
            }
        }
        GButton {
            objectName: "visualPreference"
            variant: "ghost"
            text: "Indicador visual: " + (page.visualOn ? "ligado" : "desligado") + ". Alterar em Aparência ›"
            Accessible.name: "Indicador visual. Alterar em Aparência"
            onClicked: Window.window.goPage("cfg_aparencia")
        }
        EValueRow {
            label: "Resposta"
            value: L.statusText(core.speechStatus)
        }
        EValueRow {
            label: "Código do estado da resposta"
            value: String(core.speechStatus)
            advanced: true
        }
    }

    Section {
        title: "Sons e voz"
        SettingRow {
            settingKey: "audio.cues"
            EToggleSetting { settingKey: "audio.cues" }
        }
        EValueRow {
            label: "Voz da Base: Pocket TTS · Alba · inglês · saída virtual"
        }
        SettingRow {
            label: "Escolha de voz"
            help: "Voz usada nas respostas."
            disabledReason: "escolha de voz não implementada; só a voz do pacote existe"
            Select {
                model: ["Alba"]
                enabled: false
                implicitWidth: 240
                Accessible.name: "Escolha de voz (indisponível)"
            }
        }
        EValueRow {
            label: "Idioma do pacote"
            value: "inglês (EN)"
            advanced: true
        }
    }

    EAdvancedNote { subtab: "Áudio" }

    Collapsible {
        title: "Como funciona"
        summary: "O volume é aplicado ao áudio gerado pelo Gideon antes da saída virtual. Não muda o volume do sistema."
        Text {
            text: "O volume é aplicado ao áudio gerado pelo Gideon antes da saída virtual. Ele não muda o volume do sistema nem do dispositivo. Volume 0 é mudo."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
