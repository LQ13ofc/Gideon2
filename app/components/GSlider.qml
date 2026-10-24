import QtQuick
import QtQuick.Controls
import "../theme"

// Slider with the value shown on the right of its label row. Name is GSlider (never shadows Controls.Slider).
Slider {
    id: slider
    property string label: ""
    property string valueText: ""
    implicitHeight: 36
    implicitWidth: 240
    Accessible.name: label.length > 0 ? label : "Controle deslizante"
    background: Rectangle {
        x: slider.leftPadding
        y: slider.topPadding + slider.availableHeight / 2 - height / 2
        width: slider.availableWidth
        height: 4
        radius: 2
        color: Theme.strongOutline
        Rectangle {
            width: slider.visualPosition * parent.width
            height: parent.height
            radius: 2
            color: slider.enabled ? Theme.accent : Theme.disabledText
        }
    }
    handle: Rectangle {
        x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
        y: slider.topPadding + slider.availableHeight / 2 - height / 2
        width: 18; height: 18; radius: 9
        color: slider.enabled ? Theme.accent : Theme.disabledText
        border.width: slider.activeFocus ? 2 : 0
        border.color: Theme.focusRing
    }
}
