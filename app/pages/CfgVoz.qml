import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Configurações > Voz e Wake: the wake phrase (choices come from the Core pack), the session time limit and the capture state.
PageFrame {
    id: page
    objectName: "page_cfg_voz"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_voz"

    readonly property var wakeChoice: L.activeWake(core.wakeChoices, core.snapshotPack.active_phrase)

    function syncControls() { timeout.value = core.sessionTimeout }
    Connections {
        target: core
        function onPreferencesChanged() { page.syncControls() }
        function onPrefsSettled(message) { if (message !== "Preferências salvas pelo Core") page.syncControls() }
    }
    Component.onCompleted: syncControls()

    PageHeader {
        title: "Voz e Wake"
        subtitle: "Frase de despertar, prazo da sessão e estado da captura."
    }
    Banner {
        objectName: "configurationMessage"
        kind: "warn"
        visible: core.configurationMessage.length > 0
        text: core.configurationMessage
    }

    Section {
        objectName: "wakeCardPanel"
        title: "Frase de despertar"
        Text { text: "Escolha uma frase qualificada do pack. A alteração requer reinício do Core."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        FieldLabel { text: "Frase ativa" }
        Text { objectName: "wakeActive"; text: L.wakeText(core.snapshotPack); textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSection; font.weight: 600; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Text {
            objectName: "wakeActiveQualification"
            visible: text.length > 0
            text: !page.wakeChoice ? (core.wakeChoices.length > 0 ? "Frase ativa não encontrada no pack." : "") : page.wakeChoice.qualification === "dev_qualified" ? "Qualificada em desenvolvimento; validação física pendente" : "Requer prova de conceito: frase sem qualidade aprovada"
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text { objectName: "wakeStatusLine"; text: "Estado do wake: " + L.statusText(core.wakeStatus); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true }
        FieldLabel { text: "Frases disponíveis" }
        Flow {
            Layout.fillWidth: true
            spacing: Theme.space(8)
            Repeater {
                model: core.wakeChoices
                delegate: GButton {
                    required property var modelData
                    objectName: "wakeCard_" + modelData.id
                    variant: core.snapshotPack.active_phrase === modelData.id ? "primary" : "secondary"
                    text: modelData.text + " · " + modelData.qualification_label
                    Accessible.name: "Frase de wake " + modelData.text
                    enabled: core.preferencesAvailable && modelData.qualification === "dev_qualified"
                    onClicked: core.selectWake(modelData.id)
                }
            }
        }
        Text { visible: core.wakeChoices.length === 0; text: "Nenhum pack de wake configurado."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true }
        RowLayout {
            visible: core.wakeChoices.length > 0
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Select {
                id: wakeChoice
                objectName: "wakeChoice"
                Layout.fillWidth: true
                model: core.wakeChoices
                textRole: "text"
                valueRole: "id"
                enabled: core.preferencesAvailable
                Accessible.name: "Frase de wake do pack"
            }
            GButton {
                objectName: "selectWakeButton"
                variant: "secondary"
                text: "Selecionar"
                Accessible.name: "Selecionar frase de wake"
                enabled: core.preferencesAvailable && wakeChoice.currentIndex >= 0 && core.wakeChoices[wakeChoice.currentIndex].qualification === "dev_qualified"
                onClicked: core.selectWake(wakeChoice.currentValue)
            }
        }
        Text {
            objectName: "wakeQualification"
            visible: core.wakeChoices.length > 0
            text: wakeChoice.currentIndex >= 0 ? (core.wakeChoices[wakeChoice.currentIndex].qualification === "dev_qualified" ? "Qualificada em desenvolvimento; validação física pendente" : "Requer prova de conceito: frase sem qualidade aprovada") : ""
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
    }

    Section {
        title: "Sessão"
        Text { text: "Prazo da sessão em milissegundos"; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            SpinBox { id: timeout; objectName: "timeoutPreference"; from: 50; to: 60000; stepSize: 1000; editable: true; enabled: core.preferencesAvailable; Accessible.name: "Prazo da sessão em milissegundos" }
            GButton { objectName: "savePreferencesButton"; variant: "primary"; text: "Salvar prazo"; Accessible.name: "Salvar prazo da sessão"; enabled: core.preferencesAvailable; onClicked: core.savePreferences(core.audibleFeedback, timeout.value) }
            GButton { objectName: "rollbackPreferencesButton"; variant: "secondary"; text: "Restaurar anterior"; enabled: core.rollbackAvailable; onClicked: core.rollbackPreferences() }
        }
        Text { text: "Atual no Core: " + (core.audibleFeedback ? "voz ligada" : "voz desligada") + " · " + core.sessionTimeout + " ms"; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Text { objectName: "preferencesResult"; text: core.preferencesResult; textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true; visible: text.length > 0 }
    }

    Section {
        objectName: "captureCardPanel"
        title: "Captura"
        Text { text: "PCM virtual · pré-roll de 1 segundo · processamento na CPU. Microfone físico, AEC e redução de ruído ainda indisponíveis."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Text { objectName: "captureStatusLine"; text: "Captura: " + L.statusText(core.sttStatus) + " · prazo da sessão: " + core.sessionTimeout + " ms"; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    }
}
