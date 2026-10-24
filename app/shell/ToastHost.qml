import QtQuick
import QtQuick.Layouts
import "../theme"
import "../components"

// Toast area: bottom right, newest last, never more than three. Leaves the window alone otherwise (no footer).
ColumnLayout {
    id: host
    objectName: "toastHost"
    width: Math.min(400, parent ? parent.width - 32 : 400)
    spacing: Theme.space(8)
    Repeater {
        model: AppState.toasts
        delegate: Toast {
            required property var modelData
            objectName: "toast_" + modelData.id
            Layout.fillWidth: true
            text: modelData.text
            onDismissed: AppState.dismissToast(modelData.id)
        }
    }
}
