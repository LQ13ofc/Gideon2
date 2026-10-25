import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

// Consent for the live microphone (A6). Opened only when the user turns the switch on. Cancelar has the focus and is the
// default; "Ativar escuta" is the only accepting action and emits agreed(). Nothing is sent to the Core from here: the
// caller sends live_audio_preference with confirmed after agreed(). Esc and Cancelar change nothing.
Modal {
    id: consent
    objectName: "liveAudioConsent"
    title: "Ouvir o microfone?"
    standardButtons: Dialog.NoButton
    signal agreed()
    onOpened: consentCancel.forceActiveFocus()
    onAccepted: consent.agreed()

    Text {
        objectName: "liveAudioConsentText"
        text: "O Gideon vai ouvir continuamente o microfone selecionado, só na memória, para detectar a frase de ativação. Nada é gravado em disco. Você pode desligar a qualquer momento."
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(10)
        Item { Layout.fillWidth: true }
        GButton {
            id: consentCancel
            objectName: "liveAudioConsentCancel"
            variant: "secondary"
            text: "Cancelar"
            onClicked: consent.reject()
        }
        GButton {
            objectName: "liveAudioConsentConfirm"
            variant: "primary"
            text: "Ativar escuta"
            Accessible.name: "Ativar a escuta do microfone"
            onClicked: consent.accept()
        }
    }
}
