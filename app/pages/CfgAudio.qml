import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Configurações > Áudio: the reply volume (applies at once with Aplicar), voice and the audible and visual feedback switches.
PageFrame {
    id: page
    objectName: "page_cfg_audio"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_audio"

    function syncControls() { audible.checked = core.audibleFeedback; visualPreference.checked = core.visualFeedback; volumePreference.value = core.outputVolume; gainSlider.value = core.outputVolume }
    Connections {
        target: core
        function onPreferencesChanged() { page.syncControls() }
        function onPrefsSettled(message) { if (message !== "Preferências salvas pelo Core") page.syncControls() }
    }
    Component.onCompleted: syncControls()

    PageHeader {
        title: "Áudio"
        subtitle: "Volume e feedback da resposta do Gideon."
    }

    Section {
        objectName: "gainCardPanel"
        title: "Volume da resposta"
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(12)
            FieldLabel { text: "Ganho da resposta por voz" }
            Text { objectName: "gainCurrent"; text: "Ganho atual: " + core.outputVolume + "%"; textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600 }
        }
        GSlider {
            id: gainSlider
            objectName: "gainSlider"
            from: 0; to: 100; stepSize: 5
            value: core.outputVolume
            enabled: core.preferencesAvailable && core.voiceAvailable
            Layout.fillWidth: true
            Accessible.name: "Ganho da resposta por voz"
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            GButton { objectName: "applyGainButton"; variant: "primary"; text: "Aplicar"; Accessible.name: "Aplicar ganho da resposta por voz"; enabled: core.preferencesAvailable && core.voiceAvailable; onClicked: core.saveFeedback(core.visualFeedback, Math.round(gainSlider.value)) }
        }
    }

    Section {
        title: "Feedback"
        Toggle {
            id: audible
            objectName: "audiblePreference"
            text: core.voiceAvailable ? "Resposta por voz (saída virtual)" : "Resposta por voz indisponível"
            enabled: core.preferencesAvailable && core.voiceAvailable
        }
        Toggle {
            id: visualPreference
            objectName: "visualPreference"
            text: "Indicador visual de atividade"
            enabled: core.preferencesAvailable
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            FieldLabel { text: "Ganho da saída virtual, por cento (0 = mudo)" }
            SpinBox { id: volumePreference; objectName: "volumePreference"; from: 0; to: 100; stepSize: 5; editable: true; enabled: core.preferencesAvailable && core.voiceAvailable; Accessible.name: "Ganho da saída virtual, por cento" }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton { objectName: "saveAudibleButton"; variant: "secondary"; text: "Salvar resposta por voz"; enabled: core.preferencesAvailable; onClicked: core.savePreferences(audible.checked, core.sessionTimeout) }
            GButton { objectName: "saveFeedbackButton"; variant: "primary"; text: "Salvar indicador e ganho"; enabled: core.preferencesAvailable; onClicked: core.saveFeedback(visualPreference.checked, volumePreference.value) }
        }
        Text { text: "Alterações se aplicam à próxima sessão. Voz e dispositivos dependem do pack e dos adaptadores disponíveis."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    }

    Section {
        objectName: "speechCardPanel"
        title: "Voz da resposta"
        Text { text: "Pocket TTS · Alba · inglês · saída virtual. Outras vozes e dispositivos físicos ainda indisponíveis."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Text { objectName: "speechStatusLine"; text: "Resposta: " + L.statusText(core.speechStatus); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true }
        Toggle { objectName: "sfxSwitch"; text: "Sons de início e fim de escuta"; enabled: false }
        Text { text: "Indisponível: sons de escuta ainda não existem no app."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; Layout.fillWidth: true }
    }
}
