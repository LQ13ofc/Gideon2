import QtQuick
import "../theme"
import "../shell"

// Switch bound to one key of the settings object. Saves at once (AppState.setSetting). After the click the switch goes back to
// the stored value, so a Core-backed switch shows its new state only when the Core confirms it.
Toggle {
    id: sw
    property string settingKey: ""
    readonly property bool stored: AppState.uiGet(settingKey, false) === true
    checked: stored
    Accessible.name: AppState.uiSpec(settingKey) ? AppState.uiSpec(settingKey).label : settingKey
    onToggled: {
        AppState.setSetting(sw.settingKey, sw.checked)
        sw.checked = Qt.binding(function () { return sw.stored })
    }
}
