import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../shell"
import "../shell/Labels.js" as L
import "BExt.js" as X

// Drawer of one skill (Minhas): state, origin, the permissions panel (S4 P10-I6/I7) and every action of the skill.
// Nothing here grants a permission; approving a skill does not approve the permissions of its plugins.
Rectangle {
    id: panel
    property var skill: null
    property var ctx: ({})
    readonly property bool has: skill !== null
    readonly property var primary: has ? X.skillPrimary(skill, ctx) : null
    readonly property bool busy: ctx.busy === true
    readonly property bool runActive: ctx.runActive === true
    readonly property bool canDo: !busy && has

    signal removeRequested(var skill)
    signal closeRequested()

    Layout.preferredWidth: 360
    Layout.minimumWidth: 300
    Layout.alignment: Qt.AlignTop
    implicitHeight: body.implicitHeight + 2 * Theme.space(20)
    radius: Theme.radiusCard
    color: Theme.surfaceVariant
    border.width: 1
    border.color: Theme.strongOutline
    Accessible.role: Accessible.Pane
    Accessible.name: has ? "Detalhe da skill " + skill.id : "Detalhe da skill"

    function reasonFor(action) {
        if (!has) return ""
        if (busy) return "Aguarde: outra operação de skill em andamento."
        if (action === "approve" && skill.state !== "tested") return "Simule a skill antes de aprovar."
        if (action === "enable" && !(skill.state === "approved" || skill.state === "disabled")) return "Aprove a skill antes de habilitar ou executar."
        if (action === "disable" && skill.state !== "enabled") return "A skill não está habilitada."
        if (action === "run" && skill.state !== "enabled") return "Habilite a skill antes de executar."
        if (action === "run" && runActive) return "Já existe uma skill em execução; aguarde ou cancele."
        if (action === "export" && !X.exportable(skill.state)) return "Aprove a skill antes de exportar."
        if (action === "dry" && !ctx.inputsOk) return "Entradas inválidas: use um objeto JSON de até 16 KiB."
        return ""
    }
    function enabledFor(action) { return canDo && reasonFor(action) === "" }

    ColumnLayout {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.space(20)
        spacing: Theme.space(10)
        visible: panel.has

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(8)
            Text {
                text: panel.has ? panel.skill.name : ""
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSection
                font.weight: 600
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Badge {
                text: panel.has ? X.skillStateText(panel.skill.state) : ""
                tone: panel.has ? X.skillStateTone(panel.skill.state) : "neutral"
            }
            IconButton {
                iconName: "close"
                size: 16
                ToolTip.text: "Fechar detalhe"
                onClicked: panel.closeRequested()
            }
        }
        Text {
            text: panel.has ? panel.skill.id + " v" + panel.skill.version + " · origem: " + L.skillSourceText(panel.skill.source) + (panel.skill.active ? " · versão ativa" : "") : ""
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WrapAnywhere
            Layout.fillWidth: true
        }
        Text {
            text: panel.has ? (panel.skill.deps_ok ? "Dependências: ok" : "Dependências: faltando: " + (panel.skill.missing || []).join(", ")) + " · " + (panel.skill.permissions_ok ? "permissões aprovadas" : "permissões pendentes") : ""
            textFormat: Text.PlainText
            color: panel.has && panel.skill.deps_ok ? Theme.success : Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.hairline }

        ColumnLayout {
            objectName: "skillPermissions"
            Layout.fillWidth: true
            spacing: Theme.space(6)
            Text {
                text: panel.has ? "Permissões de " + panel.skill.id + " v" + panel.skill.version : ""
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                font.weight: 600
                wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
            }
            Text {
                text: panel.has ? "Aprovadas no Core: " + (panel.skill.permissions_ok ? "sim" : "não") + " · Faltando: " + ((panel.skill.missing || []).length ? panel.skill.missing.join(", ") : "nada") : ""
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                text: "Aprovar permissões não concede nada à skill: ela só usa capacidades já instaladas e aprovadas."
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.hairline }

        Flow {
            Layout.fillWidth: true
            spacing: Theme.space(8)
            GButton {
                text: "Simular"
                variant: "secondary"
                enabled: panel.enabledFor("dry")
                Accessible.name: "Simular " + (panel.has ? panel.skill.id : "")
                onClicked: core.skillDryRun(panel.skill.id, panel.skill.version, panel.ctx.inputs)
            }
            GButton {
                text: "Aprovar"
                variant: "secondary"
                enabled: panel.enabledFor("approve")
                Accessible.name: "Aprovar " + (panel.has ? panel.skill.id : "")
                onClicked: core.skillApprove(panel.skill.id, panel.skill.version)
            }
            GButton {
                text: "Habilitar"
                variant: "secondary"
                enabled: panel.enabledFor("enable")
                Accessible.name: "Habilitar " + (panel.has ? panel.skill.id : "")
                onClicked: core.skillEnable(panel.skill.id)
            }
            GButton {
                text: "Desabilitar"
                variant: "secondary"
                enabled: panel.enabledFor("disable")
                Accessible.name: "Desabilitar " + (panel.has ? panel.skill.id : "")
                onClicked: core.skillDisable(panel.skill.id)
            }
            GButton {
                text: "Executar"
                variant: "primary"
                enabled: panel.enabledFor("run")
                Accessible.name: "Executar " + (panel.has ? panel.skill.id : "")
                onClicked: core.skillRun(panel.skill.id, panel.ctx.inputs)
            }
            GButton {
                text: "Reverter versão"
                variant: "secondary"
                enabled: canDo && !runActive
                Accessible.name: "Reverter versão de " + (panel.has ? panel.skill.id : "")
                onClicked: core.skillRollback(panel.skill.id)
            }
            GButton {
                text: "Exportar"
                variant: "secondary"
                enabled: panel.enabledFor("export")
                Accessible.name: "Exportar " + (panel.has ? panel.skill.id : "")
                onClicked: core.skillExport(panel.skill.id, panel.skill.version)
            }
            GButton {
                text: "Remover"
                variant: "danger"
                enabled: panel.canDo
                Accessible.name: "Remover " + (panel.has ? panel.skill.id : "")
                onClicked: panel.removeRequested(panel.skill)
            }
        }
        Text {
            visible: panel.has && panel.primary !== null && !panel.primary.enabled && panel.primary.reason.length > 0
            text: panel.has && panel.primary ? panel.primary.reason : ""
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
