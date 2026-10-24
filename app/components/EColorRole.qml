import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../shell"
import "../shell/CfgSettings.js" as CS

// One colour role of the palette: a swatch, its name, and a hex field. The value is checked against the contrast pairs
// first (ui.validateTheme): a value that needs a correction is shown with the correction, and only applies when accepted.
// settingKey: "theme.accent" for the accent, otherwise the role goes into "theme.colors".
ColumnLayout {
    id: editor
    property string role: ""
    property string roleLabel: ""
    property string settingKey: role === "accent" ? "theme.accent" : "theme.colors"
    property string message: ""
    property bool messageIsError: false
    property var proposal: null
    Layout.fillWidth: true
    spacing: Theme.space(6)

    function tokensNow() {
        var all = {}
        for (var i = 0; i < CS.themeRoles.length; i++) all[CS.themeRoles[i]] = Theme.token(CS.themeRoles[i])
        return all
    }
    function apply(hex) {
        if (settingKey === "theme.accent") {
            AppState.setSetting("theme.accent", hex)
        } else {
            var map = {}, stored = AppState.uiGet("theme.colors", {})
            for (var k in stored) map[k] = stored[k]
            map[role] = hex
            AppState.setSetting("theme.colors", map)
        }
        proposal = null
        message = ""
    }
    function commit(text) {
        var hex = CS.normalizeHex(text)
        proposal = null
        message = ""
        messageIsError = false
        if (hex === "") {
            message = "Hex inválido: use #rrggbb. O valor anterior foi mantido."
            messageIsError = true
            return
        }
        if (hex === Theme.token(role)) return
        var tokens = tokensNow()
        tokens[role] = hex
        var result = ui.validateTheme(tokens)
        if (!result.ok) {
            message = result.errors[0]
            messageIsError = true
            return
        }
        if (result.fixes.length > 0) {
            proposal = { color: hex }
            message = "Corrigido automaticamente: " + CS.fixText(result.fixes[0])
                + (result.fixes.length > 1 ? " e mais " + (result.fixes.length - 1) + " ajuste(s)" : "") + "."
            return
        }
        apply(hex)
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space(10)
        Rectangle {
            Layout.preferredWidth: 28
            Layout.preferredHeight: 28
            radius: 14
            color: Theme.token(editor.role)
            border.width: 1
            border.color: Theme.strongOutline
        }
        Text {
            text: editor.roleLabel
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            elide: Text.ElideRight
            Layout.preferredWidth: 170
        }
        TextField {
            id: field
            objectName: "colorField_" + editor.role
            Layout.preferredWidth: 112
            font.family: "monospace"
            font.pixelSize: Theme.fontBody
            color: Theme.text
            selectByMouse: true
            maximumLength: 7
            Accessible.name: editor.roleLabel + " em hexadecimal"
            background: Rectangle {
                radius: Theme.radius
                color: Theme.bg
                border.width: field.activeFocus ? 2 : 1
                border.color: field.activeFocus ? Theme.focusRing : Theme.strongOutline
            }
            onEditingFinished: editor.commit(text)
        }
        Binding {
            target: field
            property: "text"
            value: Theme.token(editor.role).toUpperCase()
            when: !field.activeFocus && editor.proposal === null
        }
    }
    ColumnLayout {
        visible: editor.message.length > 0
        Layout.fillWidth: true
        Layout.leftMargin: Theme.space(38)
        spacing: Theme.space(6)
        Text {
            text: editor.message
            textFormat: Text.PlainText
            color: editor.messageIsError ? Theme.error : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        RowLayout {
            visible: editor.proposal !== null
            spacing: Theme.space(8)
            GButton {
                objectName: "acceptFixButton_" + editor.role
                variant: "primary"
                text: "Aceitar correção"
                onClicked: editor.apply(editor.proposal.color)
            }
            GButton {
                variant: "secondary"
                text: "Cancelar"
                onClicked: { editor.proposal = null; editor.message = "" }
            }
        }
    }
}
