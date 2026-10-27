import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

// Confirmation for a destructive personal-data action (delete, erase, revoke). Cancelar is the default focus; the
// danger button is the only action and it emits confirmed(). Nothing is sent to the Core until confirmed().
Modal {
    id: confirm
    property string message: ""
    property string actionText: qsTr("Apagar")
    signal confirmed()
    title: qsTr("Tem certeza?")

    Text {
        text: confirm.message
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    RowLayout {
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignRight
        spacing: Theme.space(8)
        GButton {
            objectName: "confirmAction"
            variant: "danger"
            text: confirm.actionText
            Accessible.name: confirm.actionText
            onClicked: {
                confirm.close()
                confirm.confirmed()
            }
        }
    }
}
