import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

// Consent for host actions (A11). Opened only when the user turns the switch on. Cancelar has the focus and is the
// default; "Permitir ações" is the only accepting action and emits agreed(). Nothing is sent to the Core from here: the
// caller sends real_actions_preference with confirmed after agreed(). Esc and Cancelar change nothing.
Modal {
    id: consent
    objectName: "realActionsConsent"
    title: "Executar ações no computador?"
    standardButtons: Dialog.NoButton
    signal agreed()
    onOpened: consentCancel.forceActiveFocus()
    onAccepted: consent.agreed()

    Text {
        objectName: "realActionsConsentText"
        text: "Quando você disser um comando, o Gideon vai abrir aplicativos e mudar o volume do seu computador de verdade. Só comandos da lista fixa. Você pode desligar a qualquer momento."
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
            objectName: "realActionsConsentCancel"
            variant: "secondary"
            text: "Cancelar"
            onClicked: consent.reject()
        }
        GButton {
            objectName: "realActionsConsentConfirm"
            variant: "primary"
            text: "Permitir ações"
            Accessible.name: "Permitir que o Gideon execute ações no computador"
            onClicked: consent.accept()
        }
    }
}
