import QtQuick
import "../theme"

// The Gideon orb with its state: idle (still), listening (radial ripple), thinking (slow turn), speaking (soft pulse),
// error (red ring). Animations follow theme.animation; with it off the orb is still. Hidden when theme.orb is off.
Item {
    id: orb
    property string mode: "idle"   // idle | listening | thinking | speaking | error
    property int size: Theme.orbSize
    readonly property bool moving: Theme.animDuration > 0 && mode !== "idle" && mode !== "error"
    readonly property color ringColor: mode === "error" ? Theme.error : mode === "speaking" ? Theme.info : Theme.accent
    visible: Theme.orbVisible
    width: size; height: size
    implicitWidth: size; implicitHeight: size
    Accessible.role: Accessible.Graphic
    Accessible.name: "Estado do Gideon: " + mode

    // Ripple rings for listening.
    Repeater {
        model: 2
        delegate: Rectangle {
            required property int index
            anchors.centerIn: parent
            width: orb.size; height: orb.size; radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: Qt.alpha(orb.ringColor, 0.6)
            visible: orb.mode === "listening" && orb.moving
            SequentialAnimation on scale {
                running: parent.visible
                loops: Animation.Infinite
                PauseAnimation { duration: index * 700 }
                NumberAnimation { from: 0.9; to: 1.5; duration: 1400; easing.type: Easing.OutQuad }
            }
            SequentialAnimation on opacity {
                running: parent.visible
                loops: Animation.Infinite
                PauseAnimation { duration: index * 700 }
                NumberAnimation { from: 0.7; to: 0; duration: 1400 }
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.width: orb.mode === "error" ? 2 : 0
        border.color: Theme.error
    }

    Image {
        id: body
        anchors.fill: parent
        source: Qt.resolvedUrl("../assets/gideon-orb.png")
        sourceSize.width: orb.size * 2
        sourceSize.height: orb.size * 2
        fillMode: Image.PreserveAspectFit
        smooth: true
        opacity: orb.mode === "error" ? 0.6 : 1
        RotationAnimator on rotation {
            running: orb.mode === "thinking" && orb.moving
            from: 0; to: 360; duration: 6000; loops: Animation.Infinite
        }
        SequentialAnimation on scale {
            running: orb.mode === "speaking" && orb.moving
            loops: Animation.Infinite
            NumberAnimation { from: 1.0; to: 1.06; duration: 500; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1.06; to: 1.0; duration: 500; easing.type: Easing.InOutSine }
        }
    }
}
