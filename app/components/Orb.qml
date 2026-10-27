import QtQuick
import "../theme"

// The Gideon orb: nine HUD states, each with its own ring and motion (Notion HUD states, docs/WP3.md).
//   idle          still, faint accent ring
//   wake          one accent ring that opens once (WakeDetected)
//   listening     two ripple rings (Listening)
//   transcribing  a spinning info arc (Transcribing)
//   thinking      a static accent arc and a body that turns slowly (Thinking)
//   acting        an accent arc: determinate with progress (0..1), spinning when progress is -1 (Acting)
//   speaking      the body breathes with a steady info ring (Speaking)
//   error         red ring, dimmed body (Error)
//   confirm       dashed warning ring that turns slowly (AwaitingConfirmation)
// Motion follows Theme.animationMode: "normal" animates; "reduced" and "off" keep every ring still and only the
// opacity changes (no loops, no rotation, no scale). Hidden when theme.orb is off.
Item {
    id: orb
    property string mode: "idle"   // idle | wake | listening | transcribing | thinking | acting | speaking | error | confirm
    property real progress: -1     // acting only: 0..1 when the Core knows the share done, -1 when it does not
    property int size: Theme.orbSize
    readonly property bool fullMotion: Theme.animationMode === "normal"
    readonly property color ringColor: mode === "error" ? Theme.error
        : mode === "confirm" ? Theme.warning
        : (mode === "speaking" || mode === "transcribing" || mode === "listening") ? Theme.info
        : Theme.accent
    visible: Theme.orbVisible
    width: size; height: size
    implicitWidth: size; implicitHeight: size
    Accessible.role: Accessible.Graphic
    Accessible.name: qsTr("Estado do Gideon: %1").arg(modeWords[mode])
    readonly property var modeWords: ({idle: qsTr("em espera"), wake: qsTr("ativado"), listening: qsTr("ouvindo"), transcribing: qsTr("transcrevendo"),
                                       thinking: qsTr("pensando"), acting: qsTr("executando"), speaking: qsTr("falando"), error: qsTr("erro"),
                                       confirm: qsTr("aguardando sua aprovação")})

    function cssOf(c, alpha) {
        return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + (alpha === undefined ? c.a : alpha) + ")"
    }
    onModeChanged: ring.requestPaint()
    onProgressChanged: ring.requestPaint()
    onRingColorChanged: ring.requestPaint()
    Component.onCompleted: ring.requestPaint()

    // WakeDetected: one ring that opens and fades once; still when motion is reduced.
    Rectangle {
        id: wakeRing
        anchors.centerIn: parent
        width: orb.size; height: orb.size; radius: width / 2
        color: "transparent"
        border.width: 2
        border.color: Qt.alpha(Theme.accent, 0.9)
        visible: orb.mode === "wake"
        SequentialAnimation on scale {
            running: wakeRing.visible && orb.fullMotion
            NumberAnimation { from: 0.8; to: 1.5; duration: 900; easing.type: Easing.OutCubic }
        }
        SequentialAnimation on opacity {
            running: wakeRing.visible && orb.fullMotion
            NumberAnimation { from: 1; to: 0; duration: 900 }
        }
    }

    // Listening: ripple rings. Reduced motion keeps only the first ring, still.
    Repeater {
        model: 2
        delegate: Rectangle {
            required property int index
            anchors.centerIn: parent
            width: orb.size; height: orb.size; radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: Qt.alpha(orb.ringColor, 0.6)
            visible: orb.mode === "listening" && (orb.fullMotion || index === 0)
            SequentialAnimation on scale {
                running: parent.visible && orb.fullMotion
                loops: Animation.Infinite
                PauseAnimation { duration: index * 700 }
                NumberAnimation { from: 0.9; to: 1.5; duration: 1400; easing.type: Easing.OutQuad }
            }
            SequentialAnimation on opacity {
                running: parent.visible && orb.fullMotion
                loops: Animation.Infinite
                PauseAnimation { duration: index * 700 }
                NumberAnimation { from: 0.7; to: 0; duration: 1400 }
            }
        }
    }

    // Speaking: a steady ring around the body (the body breathes only in full motion).
    Rectangle {
        anchors.centerIn: parent
        width: orb.size * 1.12; height: width; radius: width / 2
        color: "transparent"
        border.width: 1
        border.color: Qt.alpha(Theme.info, 0.5)
        visible: orb.mode === "speaking"
    }

    // Transcribing, acting, thinking and confirming: one canvas ring. Its arc or dashes are drawn in onPaint; the spin is an animator.
    Canvas {
        id: ring
        anchors.fill: parent
        renderTarget: Canvas.Image
        visible: orb.mode === "transcribing" || orb.mode === "acting" || orb.mode === "thinking" || orb.mode === "confirm"
        RotationAnimator on rotation {
            running: ring.visible && orb.fullMotion && orb.mode !== "thinking" && (orb.mode !== "acting" || orb.progress < 0)
            from: 0; to: 360
            duration: orb.mode === "confirm" ? 12000 : orb.mode === "transcribing" ? 1200 : 1500
            loops: Animation.Infinite
        }
        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            var cx = width / 2, cy = height / 2, r = width / 2 - 2
            ctx.lineWidth = 2.5
            if (orb.mode === "confirm") {
                ctx.strokeStyle = orb.cssOf(Theme.warning, 0.9)
                ctx.setLineDash([6, 6])
                ctx.beginPath()
                ctx.arc(cx, cy, r, 0, 2 * Math.PI)
                ctx.stroke()
                return
            }
            var span = orb.mode === "transcribing" ? 1.75
                : orb.mode === "thinking" ? 1.2
                : orb.progress >= 0 ? Math.min(1, orb.progress) * 2 * Math.PI
                : 4.71
            ctx.strokeStyle = orb.cssOf(orb.mode === "transcribing" ? Theme.info : Theme.accent, 0.95)
            ctx.beginPath()
            ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + span, false)
            ctx.stroke()
        }
    }

    // Error: a solid red ring.
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
            running: orb.mode === "thinking" && orb.fullMotion
            from: 0; to: 360; duration: 6000; loops: Animation.Infinite
        }
        SequentialAnimation on scale {
            running: orb.mode === "speaking" && orb.fullMotion
            loops: Animation.Infinite
            NumberAnimation { from: 1.0; to: 1.06; duration: 500; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1.06; to: 1.0; duration: 500; easing.type: Easing.InOutSine }
        }
    }
}
