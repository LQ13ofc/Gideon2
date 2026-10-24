pragma Singleton
import QtQuick

// Every colour, size and motion value the UI uses comes from here. Values come from the app settings object `ui`
// (context property, app/uisettings.py). When `ui` is missing the built-in 'Gideon Escuro' tokens apply, so the app
// still loads. Components and pages never hard-code colours or sizes.
// Item (not QtObject) because it holds a Connections element.
Item {
    id: theme
    visible: false
    width: 0
    height: 0

    // Built-in fallback: Gideon Escuro (docs/ui-spec/00-casca.md).
    readonly property var builtinTokens: ({
        bg: "#0b1530", surface: "#0e1a3a", surfaceVariant: "#17294b", outline: "#263a73",
        text: "#edf2ff", textMuted: "#9db0e0", accent: "#7693ff", onAccent: "#ffffff",
        success: "#5ee0a0", warning: "#f2c15c", error: "#ff7d8a", info: "#7693ff"
    })
    readonly property var builtinDefaults: ({
        "theme.mode": "dark", "theme.preset": "gideon-escuro", "theme.density": 1.0, "theme.radius": 10,
        "theme.fontSize": 14, "theme.fontFamily": "system", "theme.contrast": "normal", "theme.animation": "normal",
        "theme.titleWeight": 700, "theme.lineHeight": 1.4, "theme.orb": true, "theme.orbSize": "small", "theme.shadow": 0,
        "behavior.toastSeconds": 4, "behavior.shortcuts": true, "behavior.devMode": false, "behavior.advanced": false
    })

    // Settings snapshot and the active preset's tokens, refreshed on ui.valuesChanged.
    property var vals: ({})
    property var presetTokens: ({})
    readonly property bool live: typeof ui !== "undefined" && ui !== null

    Connections {
        target: theme.live ? ui : null
        function onValuesChanged() { theme.refresh() }
    }
    Component.onCompleted: refresh()

    function refresh() {
        var snapshot = {}
        var source = theme.live ? ui.values : null
        if (source) for (var k in source) snapshot[k] = source[k]
        theme.vals = snapshot
        var name = theme.val("theme.preset", "gideon-escuro")
        var tokens = {}
        if (theme.live) {
            var got = ui.presetTokens(name)
            if (got) for (var r in got) tokens[r] = got[r]
        }
        theme.presetTokens = tokens
    }

    function val(key, fallback) {
        var v = theme.vals ? theme.vals[key] : undefined
        if (v !== undefined && v !== null && v !== "") return v
        var d = theme.builtinDefaults[key]
        return d !== undefined ? d : fallback
    }
    function colorOverride(role) {
        var map = theme.val("theme.colors", null)
        if (!map) return ""
        if (typeof map === "string") { try { map = JSON.parse(map) } catch (e) { return "" } }
        return map[role] ? String(map[role]) : ""
    }
    function token(role) {
        var o = colorOverride(role)
        if (o !== "") return o
        if (role === "accent") { var a = theme.val("theme.accent", ""); if (a !== "") return String(a) }
        if (theme.presetTokens[role]) return theme.presetTokens[role]
        return theme.builtinTokens[role]
    }

    // Palette roles (hex strings; the derived states are computed from them).
    readonly property color bg: token("bg")
    readonly property color surface: token("surface")
    readonly property color surfaceVariant: token("surfaceVariant")
    readonly property color outline: token("outline")
    readonly property color text: token("text")
    readonly property color textMuted: token("textMuted")
    readonly property color accent: token("accent")
    readonly property color onAccent: token("onAccent")
    readonly property color success: token("success")
    readonly property color warning: token("warning")
    readonly property color error: token("error")
    readonly property color info: token("info")
    // Derived states: hover, pressed, focus ring and accent tint.
    readonly property color hover: Qt.tint(surfaceVariant, Qt.alpha(text, 0.07))
    readonly property color pressed: Qt.tint(surfaceVariant, Qt.alpha(text, 0.14))
    readonly property color focusRing: accent
    readonly property color tint: Qt.alpha(accent, 0.18)
    // Filled primary buttons: darker than the accent so white text keeps 4.5:1.
    readonly property color primary: Qt.darker(accent, 1.45)
    readonly property color hairline: Qt.alpha(outline, 0.4)
    readonly property color disabledText: Qt.alpha(text, 0.4)
    readonly property color danger: error
    readonly property bool highContrast: val("theme.contrast", "normal") === "high"
    readonly property color strongOutline: highContrast ? Qt.alpha(text, 0.7) : outline

    // Density: a number (0.85-1.25) or a name.
    readonly property real density: {
        var d = val("theme.density", 1.0)
        if (typeof d === "string") return ({ compact: 0.9, compacta: 0.9, normal: 1.0, spacious: 1.15, espacosa: 1.15 })[d] || 1.0
        return Math.max(0.85, Math.min(1.25, Number(d)))
    }
    function space(n) { return Math.round(n * density) }

    // Shape, type and motion.
    readonly property real radius: Math.max(0, Math.min(16, Number(val("theme.radius", 10))))
    readonly property real radiusCard: Math.min(20, radius + 4)
    readonly property real fontSize: Math.max(12, Math.min(20, Number(val("theme.fontSize", 14))))
    readonly property string fontFamily: {
        var f = String(val("theme.fontFamily", "system"))
        return (f === "system" || f === "") ? Qt.application.font.family : f
    }
    readonly property int titleWeight: Math.max(500, Math.min(800, Number(val("theme.titleWeight", 700))))
    readonly property real lineHeight: Math.max(1.2, Math.min(1.8, Number(val("theme.lineHeight", 1.4))))
    // Low power ("Modo econômico", perf.lowPower) wins over everything: no animation, no translucency, no shadow.
    // The desktop's reduced-motion request (behavior.reduceMotionFollowSystem) turns animation to the reduced mode.
    readonly property bool lowPower: val("perf.lowPower", false) === true
    // The desktop probe runs only when the user asked to follow the system (short-circuit: the value is read on demand).
    readonly property bool followSystemMotion: val("behavior.reduceMotionFollowSystem", false) === true && theme.live && ui.reducedMotionSystem === true
    readonly property string animationMode: lowPower ? "off"
        : (followSystemMotion && String(val("theme.animation", "normal")) === "normal") ? "reduced"
        : String(val("theme.animation", "normal"))
    readonly property int animDuration: animationMode === "off" ? 0 : animationMode === "reduced" ? 80 : 200
    readonly property int translucency: lowPower ? 0 : Math.max(0, Math.min(24, Number(val("theme.translucency", 0))))
    readonly property real shadowAlpha: lowPower ? 0 : Math.max(0, Math.min(100, Number(val("theme.shadow", 0)))) / 100

    // Type scale: title 24, section 16, body 14, help 13, caption 12 at the default size (scales with fontSize).
    readonly property int fontTitle: Math.round(fontSize * 24 / 14)
    readonly property int fontSection: Math.round(fontSize * 16 / 14)
    readonly property int fontBody: Math.round(fontSize)
    readonly property int fontHelp: Math.round(fontSize * 13 / 14)
    readonly property int fontCaption: Math.round(fontSize * 12 / 14)

    // Layout grid.
    readonly property int contentMax: 1100
    readonly property int narrowWidth: 900
    readonly property int rowHeight: space(56)
    readonly property int controlHeight: space(36)
    readonly property int toastSeconds: Math.max(2, Math.min(10, Number(val("behavior.toastSeconds", 4))))
    readonly property bool shortcutsOn: val("behavior.shortcuts", true) === true
    readonly property bool devMode: val("behavior.devMode", false) === true
    readonly property bool advanced: val("behavior.advanced", false) === true

    // Orb (idle/listening/thinking/speaking/error).
    readonly property bool orbVisible: val("theme.orb", true) === true
    readonly property int orbSize: String(val("theme.orbSize", "small")) === "medium" ? 40 : 28

    // Mode follows the desktop scheme when theme.mode is "system".
    readonly property bool systemDark: Application.styleHints.colorScheme === Qt.ColorScheme.Dark
    readonly property bool isDark: {
        var m = String(val("theme.mode", "dark"))
        return m === "dark" || (m === "system" && systemDark)
    }
}
