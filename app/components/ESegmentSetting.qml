import QtQuick
import "../shell"

// Segmented choice bound to one key. options: [{id, text, value}]; value (optional) is what is stored, id is what the
// segment is named by. A number is stored as the nearest option; with no near option nothing is shown as chosen.
Segmented {
    id: seg
    property string settingKey: ""
    property var options: []
    model: options
    currentId: idOf(AppState.uiGet(settingKey, ""))

    function sameValue(a, b) {
        if (typeof a === "number" || typeof b === "number") return Math.abs(Number(a) - Number(b)) < 0.001
        return String(a) === String(b)
    }
    function idOf(stored) {
        var best = "", distance = Infinity
        for (var i = 0; i < options.length; i++) {
            var option = options[i]
            var candidate = option.value !== undefined ? option.value : option.id
            if (typeof candidate === "number" || typeof stored === "number") {
                var gap = Math.abs(Number(candidate) - Number(stored))
                if (gap < distance) { distance = gap; best = option.id }
            } else if (sameValue(candidate, stored)) return option.id
        }
        return distance < 0.06 ? best : ""
    }
    onActivated: function (id) {
        for (var i = 0; i < options.length; i++) {
            if (options[i].id === id) {
                AppState.setSetting(seg.settingKey, options[i].value !== undefined ? options[i].value : options[i].id)
                return
            }
        }
    }
}
