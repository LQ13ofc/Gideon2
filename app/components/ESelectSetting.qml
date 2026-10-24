import QtQuick
import "../shell"

// Drop-down bound to one key; its options are the schema options of that key. Saves when the user picks one.
Select {
    id: box
    property string settingKey: ""
    readonly property var entries: AppState.uiSpec(settingKey) ? AppState.uiSpec(settingKey).options : []
    model: entries
    textRole: "label"
    valueRole: "value"
    currentIndex: indexOfValue(AppState.uiGet(settingKey, ""))
    implicitWidth: 240
    Accessible.name: AppState.uiSpec(settingKey) ? AppState.uiSpec(settingKey).label : settingKey
    onActivated: {
        AppState.setSetting(box.settingKey, box.currentValue)
        box.currentIndex = Qt.binding(function () { return box.indexOfValue(AppState.uiGet(box.settingKey, "")) })
    }
}
