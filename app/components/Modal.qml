import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

// Dialog box for a decision. Cancelar is the default focus; the explicit action is a child button that calls accept().
// closeOnly: a dialog with nothing to accept (review of permissions, plugin details) gets a single Fechar button.
Dialog {
    id: modal
    property bool closeOnly: false
    property string closeText: qsTr("Fechar")
    default property alias content: body.data
    parent: Overlay.overlay
    modal: true
    anchors.centerIn: parent
    width: Math.min(440, (parent ? parent.width : 440) - 32)
    standardButtons: closeOnly ? Dialog.Close : Dialog.Cancel
    padding: Theme.space(20)
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    background: Rectangle {
        radius: Theme.radiusCard
        color: Theme.surfaceVariant
        border.width: 1
        border.color: Theme.strongOutline
    }
    header: Text {
        visible: modal.title.length > 0
        text: modal.title
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSection
        font.weight: 600
        leftPadding: Theme.space(20)
        topPadding: Theme.space(18)
        rightPadding: Theme.space(20)
    }
    onOpened: {
        var cancel = standardButton(closeOnly ? Dialog.Close : Dialog.Cancel)
        if (cancel) {
            cancel.text = closeOnly ? closeText : qsTr("Cancelar")
            cancel.forceActiveFocus()
        }
    }
    contentItem: ColumnLayout {
        id: body
        width: modal.availableWidth
        spacing: Theme.space(12)
    }
}
