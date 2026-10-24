import QtQuick
import QtQuick.Controls
import "../theme"

// Thin progress line for a running operation (indeterminate unless value is given). Name is GProgressBar.
ProgressBar {
    id: bar
    implicitHeight: 4
    background: Rectangle {
        radius: 2
        color: Theme.strongOutline
    }
    contentItem: Item {
        implicitHeight: 4
        Rectangle {
            visible: !bar.indeterminate
            width: bar.visualPosition * parent.width
            height: parent.height
            radius: 2
            color: Theme.accent
        }
        Rectangle {
            id: slide
            visible: bar.indeterminate
            width: parent.width * 0.3
            height: parent.height
            radius: 2
            color: Theme.accent
            SequentialAnimation on x {
                running: bar.indeterminate && bar.visible && Theme.animDuration > 0
                loops: Animation.Infinite
                NumberAnimation { from: -slide.width; to: bar.width; duration: 1200 }
            }
        }
    }
}
