import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    objectName: "mainWindow"
    visible: true
    width: 840; height: 620
    minimumWidth: 480; minimumHeight: 520
    title: "Gideon"
    color: "#101923"
    Dialog {
        id: preferences; objectName: "preferencesDialog"
        title: "Preferências da Base"; modal: true
        anchors.centerIn: parent; width: Math.min(420, window.width - 32)
        standardButtons: Dialog.Close
        onOpened: { audible.checked = core.audibleFeedback; timeout.value = core.sessionTimeout }
        ColumnLayout {
            anchors.fill: parent
            Label { objectName: "configurationMessage"; visible: core.configurationMessage.length > 0; text: core.configurationMessage; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Button { objectName: "recoverConfigurationButton"; visible: core.configurationStatus === "safe_mode"; text: "Preservar arquivo e restaurar padrões"; enabled: core.recoveryAvailable; onClicked: core.recoverConfiguration(); Accessible.name: text }
            CheckBox { id: audible; objectName: "audiblePreference"; text: core.voiceAvailable ? "Resposta por voz (saída virtual)" : "Resposta por voz indisponível"; enabled: core.preferencesAvailable && core.voiceAvailable }
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
    ColumnLayout {
        objectName: "mainColumn"
        anchors.fill: parent; anchors.margins: 28; spacing: 18
        RowLayout {
            Layout.fillWidth: true
            Label { text: "Gideon"; font.pixelSize: 30; font.bold: true; color: "#e6edf4" }
            Item { Layout.fillWidth: true }
            Button { objectName: "settingsButton"; text: "Preferências"; enabled: core.connected; onClicked: preferences.open() }
            Label { text: core.connected ? "Conectado" : "Offline"; color: core.connected ? "#70d6b0" : "#ffc674"; Accessible.name: text }
        }
        RowLayout {
            spacing: 16
            Rectangle { width: 18; height: 18; radius: 9; color: core.connected ? (core.state === "idle" ? "#70d6b0" : "#73b7ff") : "#ffc674"; Accessible.name: "Estado do Gideon" }
            Label { objectName: "aura"; text: ({idle:"Em espera",capturing:"Ouvindo",transcribing:"Transcrevendo",executing:"Executando",speaking:"Respondendo",offline:"Core indisponível",safe_mode:"Modo seguro",restart_required:"Reinício necessário"})[core.state] || "Erro"; color: "#e6edf4"; font.pixelSize: 24; Accessible.name: text }
        }
        Label { text: "Conversa atual"; color: "#9bb0c5"; font.pixelSize: 16 }
        ScrollView {
            objectName: "transcriptViewport"
            Layout.minimumHeight: 48
            Layout.fillWidth: true; Layout.fillHeight: true
            TextArea {
                objectName: "subtitle"
                text: core.subtitle; readOnly: true; selectByMouse: true
                wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText
                color: "#e6edf4"; font.pixelSize: 21
                placeholderText: "A transcrição aparecerá aqui."
                Accessible.name: core.partial ? "Transcrição parcial" : "Transcrição final"
                background: Rectangle { color: "#192735"; radius: 12 }
            }
        }
        Label { text: core.partial ? "Parcial" : "Final"; visible: core.subtitle.length > 0; color: "#9bb0c5" }
        Label { objectName: "result"; text: core.result; Layout.fillWidth: true; wrapMode: Text.WordWrap; textFormat: Text.PlainText; color: core.resultVerified ? "#70d6b0" : "#ffc674"; Accessible.name: "Resultado: " + text }
        RowLayout {
            Button { objectName: "cancelButton"; text: "Cancelar"; enabled: core.connected && core.sessionId.length > 0; onClicked: core.cancel(); Accessible.name: "Cancelar sessão" }
            Label { text: "Saída virtual · validação física pendente"; color: "#9bb0c5"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        RowLayout {
            Layout.fillWidth: true
            TextField { id: input; objectName: "textInput"; Layout.fillWidth: true; enabled: core.textAvailable; placeholderText: "Comando de texto no perfil de teste"; maximumLength: 512; Accessible.name: "Comando de texto"; onAccepted: if (core.textAvailable) { core.submitText(text); text = ""; } }
            Button { objectName: "sendButton"; text: "Enviar"; enabled: core.textAvailable && input.text.trim().length > 0; onClicked: { core.submitText(input.text); input.text = ""; } }
        }
        Label { text: "Voz e dispositivos / Plugins: indisponíveis nesta etapa"; color: "#9bb0c5"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Label { objectName: "diagnostics"; text: core.diagnostic; color: "#9bb0c5"; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.name: "Diagnóstico: " + text }
    }
}
