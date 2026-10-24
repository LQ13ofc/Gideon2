import QtQuick
import QtQuick.Layouts
import "../theme"
import "../shell"

// One setting row: label, one line of help (13 px), the control on the right, a 3 px bar on the left when the value differs
// from the default, "Restaurar padrão", and "Aplicando…" while the Core confirms a change.
// settingKey is a key of the settings object `ui`; with an empty label or help, both come from its schema.
// Advanced rows (schema level 'advanced', or advanced: true) stay hidden until "Mostrar opções avançadas" is on. With
// "Somente modificados" on, rows that are at their default are hidden.
// disabledReason set, or a Core state that blocks the key: the control is dimmed and "Indisponível: <motivo>" shows below.
Rectangle {
    id: row
    property string label: ""
    property string help: ""
    property string settingKey: ""
    property string disabledReason: ""
    property bool advanced: false
    readonly property bool hasKey: settingKey.length > 0
    readonly property var spec: AppState.uiSpec(settingKey)
    readonly property string shownLabel: label.length > 0 ? label : (spec ? spec.label : "")
    readonly property string shownHelp: help.length > 0 ? help : (spec ? spec.help : "")
    readonly property bool isAdvanced: advanced || (spec !== null && spec.level === "advanced")
    readonly property bool advancedOn: AppState.uiGet("behavior.advanced", false) === true
    readonly property bool modified: AppState.isModified(settingKey)
    readonly property bool coreKey: settingKey.indexOf("core.") === 0
    readonly property string reason: disabledReason.length > 0 ? disabledReason : AppState.blockReason(settingKey)
    readonly property bool usable: reason.length === 0
    readonly property bool applying: AppState.isApplying(settingKey)
    readonly property bool highlighted: hasKey && AppState.highlightKey === settingKey
    default property alias control: slot.data
    Layout.fillWidth: true
    implicitHeight: column.implicitHeight + Theme.space(16)
    visible: (!isAdvanced || advancedOn) && (!AppState.onlyModified || modified)
    color: highlighted ? Theme.tint : "transparent"

    onHighlightedChanged: if (highlighted) Qt.callLater(reveal)

    // Scrolls the page so this row is visible (the search reveals a row in another sub-tab).
    function reveal() {
        var p = row.parent
        while (p && !(p.contentItem && p.contentItem.contentY !== undefined)) p = p.parent
        if (!p) return
        var y = row.mapToItem(p.contentItem, 0, 0).y
        p.contentItem.contentY = Math.max(0, y - Theme.space(48))
    }

    // Changed-from-default marker: a 3 px bar on the left edge.
    Rectangle {
        visible: row.modified
        x: 0; y: 6
        width: 3; height: row.height - 12
        radius: 2
        color: Theme.accent
    }
    ColumnLayout {
        id: column
        anchors.left: parent.left; anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: Theme.space(16)
        anchors.rightMargin: Theme.space(16)
        spacing: Theme.space(6)
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(16)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: row.shownLabel
                    textFormat: Text.PlainText
                    color: row.usable ? Theme.text : Theme.disabledText
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    visible: row.shownHelp.length > 0
                    text: row.shownHelp
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
            ColumnLayout {
                id: slot
                Layout.alignment: Qt.AlignVCenter
                enabled: row.usable
                opacity: row.usable ? 1 : 0.45
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(8)
            Text {
                visible: !row.usable
                text: "Indisponível: " + row.reason + (row.reason.slice(-1) === "." ? "" : ".")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                visible: row.usable && row.applying
                text: "Aplicando…"
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                Layout.fillWidth: true
            }
            Item { Layout.fillWidth: true; visible: !(!row.usable || row.applying) }
            GButton {
                visible: row.hasKey && row.modified && !row.coreKey
                variant: "ghost"
                text: "Restaurar padrão"
                onClicked: AppState.resetSetting(row.settingKey)
            }
        }
    }
}
