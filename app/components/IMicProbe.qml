import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../shell"

// A9 "Testar microfones": records 3 s from each listed input, one after another, and ranks the results. The Core owns
// every recording; this component only sends one audio_probe per input and waits for its result in audio.probe.
// The test never changes the system default. "Usar este" saves the choice in Gideon (the same setting as the Select).
ColumnLayout {
    id: probe
    objectName: "imicProbe"
    spacing: Theme.space(8)
    Layout.fillWidth: true

    property var queue: []       // [{id, label}] of the inputs to test, in list order
    property int index: -1       // position in queue; -1 when idle
    property var rows: []        // finished rows, in test order
    property int lastId: 0       // audio.probe id before the current request (a new result has a larger id)
    readonly property bool running: index >= 0

    // Verdict words and zones: the bridge sends them; colour follows the zone and the word says the same thing.
    readonly property var zoneTones: ({ "ok": Theme.success, "warn": Theme.warning, "bad": Theme.error })

    function start() {
        var list = core.audioDevices.inputs || []
        if (list.length === 0) return
        var items = []
        for (var i = 0; i < list.length; i++) items.push({ id: list[i].id, label: list[i].label })
        queue = items
        rows = []
        index = 0
        sendCurrent()
    }

    function sendCurrent() {
        if (index < 0) return
        if (index >= queue.length) { index = -1; timeout.stop(); return }
        lastId = Number(core.audioProbe.id || 0)
        if (!core.probeAudioInput(queue[index].id)) {
            // The Core or the bridge refused the request: the row says so, and the next input is tried.
            addRow({ device: queue[index].id, label: queue[index].label, verdict: "error", verdictText: qsTr("Não testado"),
                     zone: "bad", hint: core.audioResult, rms: null, peak: null, floor: null })
            return
        }
        timeout.restart()
    }

    function addRow(row) {
        var score = (row.peak === null || row.floor === null) ? null : row.peak - row.floor
        var next = rows.slice()
        next.push(Object.assign({}, row, { score: score }))
        rows = next
        index += 1
        if (index < queue.length) sendCurrent(); else index = -1
    }

    // One decimal, with the decimal separator of the interface language (comma in pt-BR and fr, point in en).
    function decimal(value) {
        var text = Number(value).toFixed(1)
        return core.uiLanguage === "en" ? text : text.replace(".", ",")
    }

    // The best input: among those that recorded a usable signal (ok or quiet), the largest peak above its noise floor.
    function bestDevice() {
        var best = ""
        var bestScore = -Infinity
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i]
            if (r.verdict !== "ok" && r.verdict !== "quiet") continue
            if (r.score !== null && r.score > bestScore) { bestScore = r.score; best = r.device }
        }
        return best
    }

    // Called on every snapshot change: the result of the request in flight arrives as audio.probe with a larger id.
    Connections {
        target: core
        function onAudioChanged() {
            if (!probe.running) return
            var p = core.audioProbe
            if (!p || p.done !== true || Number(p.id) <= probe.lastId || p.device !== probe.queue[probe.index].id) return
            timeout.stop()
            probe.addRow({ device: p.device, label: probe.queue[probe.index].label, verdict: p.verdict, verdictText: p.verdictText,
                           zone: p.zone, hint: p.hint, rms: p.rms, peak: p.peak, floor: p.floor })
        }
    }

    // The Core answers within about 3 s; a longer silence means the request never reached a recording.
    Timer {
        id: timeout
        interval: 12000
        onTriggered: probe.addRow({ device: probe.queue[probe.index].id, label: probe.queue[probe.index].label, verdict: "error",
                                    verdictText: qsTr("Sem resposta"), zone: "bad", hint: qsTr("O Core não respondeu ao teste. Tente de novo."),
                                    rms: null, peak: null, floor: null })
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(10)
        GButton {
            objectName: "micProbeStartButton"
            variant: "secondary"
            text: probe.running ? qsTr("Testando…") : qsTr("Testar microfones")
            Accessible.name: qsTr("Testar cada microfone da lista por 3 segundos")
            enabled: core.connected && !probe.running && (core.audioDevices.inputs || []).length > 0
            onClicked: probe.start()
        }
        Text {
            objectName: "micProbeNote"
            text: qsTr("Cada microfone grava 3 segundos. Fale normalmente por 3 s: \"Hey Gideon\". O microfone do sistema não muda.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
    Text {
        objectName: "micProbeProgress"
        visible: probe.running
        text: qsTr("Gravando %1 de %2: %3. O microfone será usado por 3 segundos.")
            .arg(probe.index + 1).arg(probe.queue.length).arg(probe.queue[probe.index] ? probe.queue[probe.index].label : "")
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    GProgressBar {
        visible: probe.running
        Layout.fillWidth: true
        indeterminate: true
    }

    // The table: one row per tested input, the verdict in words, the numbers and the action.
    Repeater {
        objectName: "micProbeRows"
        model: probe.rows
        delegate: ColumnLayout {
            required property var modelData
            required property int index
            Layout.fillWidth: true
            spacing: Theme.space(2)
            readonly property bool recommended: modelData.device === probe.bestDevice()
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(10)
                Text {
                    objectName: "micProbeLabel"
                    text: modelData.label
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Badge {
                    visible: recommended
                    text: qsTr("Recomendado")
                    tone: "info"
                }
                Text {
                    objectName: "micProbeVerdict"
                    text: modelData.verdictText
                    textFormat: Text.PlainText
                    color: probe.zoneTones[modelData.zone] || Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    font.bold: true
                }
                GButton {
                    objectName: "micProbeUse"
                    variant: recommended ? "primary" : "secondary"
                    text: qsTr("Usar este")
                    Accessible.name: qsTr("Usar %1 como microfone do Gideon").arg(modelData.label)
                    // Only an input that recorded a signal can be chosen: errors and silence are not offered.
                    enabled: ["ok", "quiet", "noisy"].indexOf(modelData.verdict) >= 0 && AppState.blockReason("core.audioInput") === ""
                    onClicked: AppState.setSetting("core.audioInput", modelData.device)
                }
            }
            Text {
                objectName: "micProbeNumbers"
                visible: modelData.rms !== null && modelData.verdict !== "silent"
                text: qsTr("Ruído de fundo %1 dBFS · pico %2 dBFS")
                    .arg(probe.decimal(modelData.floor)).arg(probe.decimal(modelData.peak))
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                objectName: "micProbeHint"
                text: modelData.hint
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }
}
