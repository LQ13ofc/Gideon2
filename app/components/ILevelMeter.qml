import QtQuick
import QtQuick.Layouts
import "../theme"

// A9 input level meter for the live microphone. The bar is the smoothed level on a -90..0 dBFS scale; a tick marks the
// noise floor and another the peak. Every zone is also named in words beside the bar, so colour is never the only cue.
// `view` is the bridge's audioLevel map (numbers and words only; no audio). Nothing is drawn while not capturing.
ColumnLayout {
    id: meter
    property var view: ({})
    property bool compact: false
    objectName: "ilevelMeter"
    spacing: Theme.space(compact ? 4 : 6)
    Layout.fillWidth: true

    readonly property bool capturing: view.capturing === true
    readonly property var zoneTones: ({ "ok": Theme.success, "low": Theme.warning, "hot": Theme.error, "bad": Theme.error, "warn": Theme.warning })

    // Position of a dBFS value on the bar (0 at the left edge, -90 at the right edge is not used: -90 is the left edge).
    function position(db) {
        return Math.max(0, Math.min(1, ((Number(db) || -90) + 90) / 90))
    }

    Rectangle {
        id: track
        objectName: "ilevelTrack"
        Layout.fillWidth: true
        implicitHeight: meter.compact ? 8 : 14
        radius: 4
        color: Theme.surfaceVariant
        border.width: 1
        border.color: Theme.hairline
        visible: meter.capturing
        Accessible.role: Accessible.ProgressBar
        Accessible.name: qsTr("Nível do microfone: %1").arg(meter.view.rmsText || "")

        Rectangle {
            id: fill
            objectName: "ilevelFill"
            x: 0
            y: 0
            width: track.width * meter.position(meter.view.rms)
            height: track.height
            radius: track.radius
            color: meter.zoneTones[meter.view.zone] || Theme.success
            Behavior on width { NumberAnimation { duration: Theme.animDuration } }
        }
        // Noise floor: a dark tick at the floor's position.
        Rectangle {
            objectName: "ilevelFloorTick"
            x: Math.max(0, track.width * meter.position(meter.view.floor) - 1)
            y: -2
            width: 2
            height: track.height + 4
            color: Theme.text
            visible: !meter.view.calibrating
        }
        // Peak: a thin accent tick.
        Rectangle {
            objectName: "ilevelPeakTick"
            x: Math.max(0, Math.min(track.width - 2, track.width * meter.position(meter.view.peak) - 1))
            y: 0
            width: 2
            height: track.height
            color: Theme.accent
        }
    }

    // Scale in words and numbers, so the bar reads without colour.
    RowLayout {
        objectName: "ilevelReadout"
        visible: meter.capturing
        Layout.fillWidth: true
        spacing: Theme.space(10)
        Text {
            objectName: "ilevelRmsText"
            text: meter.view.zoneText ? qsTr("Sinal: %1 · %2").arg(meter.view.rmsText).arg(meter.view.zoneText) : qsTr("Sinal: %1").arg(meter.view.rmsText)
            textFormat: Text.PlainText
            color: meter.zoneTones[meter.view.zone] || Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: meter.compact ? Theme.fontCaption : Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            objectName: "ilevelPeakText"
            visible: !meter.compact
            text: qsTr("Pico: %1").arg(meter.view.peakText)
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
        }
    }
    Text {
        objectName: "ilevelFloorText"
        visible: meter.capturing && !meter.compact
        text: meter.view.calibrating ? qsTr("Medindo o ruído de fundo…") : meter.view.floorLine
        textFormat: Text.PlainText
        color: meter.zoneTones[meter.view.floorZone] || Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    // Warnings of the Core, with the actionable hint in the same sentence.
    Text {
        objectName: "ilevelWarningText"
        visible: meter.capturing && meter.view.warningText.length > 0
        text: qsTr("Atenção: %1").arg(meter.view.warningText)
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Accessible.name: text
    }
    Text {
        objectName: "ilevelOffText"
        visible: !meter.capturing
        text: qsTr("Sem medição: o medidor aparece quando a escuta do microfone estiver ligada e o Core reiniciado.")
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
}
