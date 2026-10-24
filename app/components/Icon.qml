import QtQuick
import QtQuick.Effects
import "../theme"

// Monochrome icon from app/icons, tinted with a Theme colour.
Image {
    id: icon
    property string name: ""
    property int size: 18
    property color color: Theme.text
    source: name !== "" ? Qt.resolvedUrl("../icons/" + name + ".svg") : ""
    sourceSize.width: size
    sourceSize.height: size
    width: size; height: size
    fillMode: Image.PreserveAspectFit
    smooth: true
    layer.enabled: true
    layer.effect: MultiEffect {
        colorization: 1.0
        colorizationColor: icon.color
    }
}
