import QtQuick
import QtQuick.Layouts
import "../theme"
import "../shell"

// Slider bound to one key. The thumb moves freely; the value is saved when the user lets go (or moves it with the keyboard).
// decimals: digits kept when saving (0 saves whole numbers). zeroText replaces the number at 0 (for example "Desligada").
RowLayout {
    id: root
    property string settingKey: ""
    property real from: 0
    property real to: 100
    property real stepSize: 1
    property int decimals: 0
    property string unit: ""
    property string zeroText: ""
    readonly property var stored: AppState.uiGet(settingKey, from)
    readonly property real shownValue: Number(slider.value)
    spacing: Theme.space(12)

    function store(v) {
        var kept = root.decimals > 0 ? Number(Number(v).toFixed(root.decimals)) : Math.round(Number(v))
        AppState.setSetting(root.settingKey, kept)
    }
    function formatted(v) {
        if (root.zeroText.length > 0 && Math.round(v * 1000) === 0) return root.zeroText
        var text = root.decimals > 0 ? Number(v).toFixed(root.decimals).replace(".", ",") : String(Math.round(v))
        return text + root.unit
    }

    GSlider {
        id: slider
        Layout.preferredWidth: 220
        from: root.from
        to: root.to
        stepSize: root.stepSize
        value: Number(root.stored)
        Accessible.name: AppState.uiSpec(root.settingKey) ? AppState.uiSpec(root.settingKey).label : root.settingKey
        onPressedChanged: if (!pressed) root.store(value)
        onMoved: if (!pressed) root.store(value)
    }
    Binding {
        target: slider
        property: "value"
        value: Number(root.stored)
        when: !slider.pressed
    }
    Text {
        text: root.formatted(root.shownValue)
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        font.weight: 600
        horizontalAlignment: Text.AlignRight
        Layout.preferredWidth: 96
    }
}
