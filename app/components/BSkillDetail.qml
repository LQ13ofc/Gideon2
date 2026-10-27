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
    Accessible.name: has ? qsTr("Detalhe da skill %1").arg(skill.id) : qsTr("Detalhe da skill")

    function reasonFor(action) {
        if (!has) return ""
        if (busy) return qsTr("Aguarde: outra operação de skill em andamento.")
        if (action === "approve" && skill.state !== "tested") return qsTr("Simule a skill antes de aprovar.")
        if (action === "enable" && !(skill.state === "approved" || skill.state === "disabled")) return qsTr("Aprove a skill antes de habilitar ou executar.")
        if (action === "disable" && skill.state !== "enabled") return qsTr("A skill não está habilitada.")
        if (action === "run" && skill.state !== "enabled") return qsTr("Habilite a skill antes de executar.")
        if (action === "run" && runActive) return qsTr("Já existe uma skill em execução; aguarde ou cancele.")
        if (action === "export" && !X.exportable(skill.state)) return qsTr("Aprove a skill antes de exportar.")
        if (action === "dry" && !ctx.inputsOk) return qsTr("Entradas inválidas: use um objeto JSON de até 16 KiB.")
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
                ToolTip.text: qsTr("Fechar detalhe")
                onClicked: panel.closeRequested()
            }
        }
        Text {
            text: panel.has ? qsTr("%1 v%2 · origem: %3").arg(panel.skill.id).arg(panel.skill.version).arg(L.skillSourceText(panel.skill.source)) + (panel.skill.active ? qsTr(" · versão ativa") : "") : ""
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WrapAnywhere
            Layout.fillWidth: true
        }
        Text {
            text: panel.has ? (panel.skill.deps_ok ? qsTr("Dependências: ok") : qsTr("Dependências: faltando: %1").arg((panel.skill.missing || []).join(", "))) + " · " + (panel.skill.permissions_ok ? qsTr("permissões aprovadas") : qsTr("permissões pendentes")) : ""
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
                text: panel.has ? qsTr("Permissões de %1 v%2").arg(panel.skill.id).arg(panel.skill.version) : ""
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                font.weight: 600
                wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
            }
            Text {
                text: panel.has ? qsTr("Aprovadas no Core: %1 · Faltando: %2").arg(panel.skill.permissions_ok ? qsTr("sim") : qsTr("não")).arg((panel.skill.missing || []).length ? panel.skill.missing.join(", ") : qsTr("nada")) : ""
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            // The manifest's permissions_required, as labels (the Core's list; never a grant).
            Text {
                objectName: "skillRequired"
                visible: panel.has
                text: panel.has ? qsTr("Necessárias: %1").arg((panel.skill.permissionsRequired || []).length ? panel.skill.permissionsRequired.map(function (p) { return core.permissionLabel(p) }).join(", ") : qsTr("nenhuma")) : ""
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                text: qsTr("Aprovar permissões não concede nada à skill: ela só usa capacidades já instaladas e aprovadas.")
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
                text: qsTr("Simular")
                variant: "secondary"
                enabled: panel.enabledFor("dry")
                Accessible.name: qsTr("Simular %1").arg(panel.has ? panel.skill.id : "")
                onClicked: core.skillDryRun(panel.skill.id, panel.skill.version, panel.ctx.inputs)
            }
            GButton {
                text: qsTr("Aprovar")
                variant: "secondary"
                enabled: panel.enabledFor("approve")
                Accessible.name: qsTr("Aprovar %1").arg(panel.has ? panel.skill.id : "")
                onClicked: core.skillApprove(panel.skill.id, panel.skill.version)
            }
            GButton {
                text: qsTr("Habilitar")
                variant: "secondary"
                enabled: panel.enabledFor("enable")
                Accessible.name: qsTr("Habilitar %1").arg(panel.has ? panel.skill.id : "")
                onClicked: core.skillEnable(panel.skill.id)
            }
            GButton {
                text: qsTr("Desabilitar")
                variant: "secondary"
                enabled: panel.enabledFor("disable")
                Accessible.name: qsTr("Desabilitar %1").arg(panel.has ? panel.skill.id : "")
                onClicked: core.skillDisable(panel.skill.id)
            }
            GButton {
                text: qsTr("Executar")
                variant: "primary"
                enabled: panel.enabledFor("run")
                Accessible.name: qsTr("Executar %1").arg(panel.has ? panel.skill.id : "")
                onClicked: core.skillRun(panel.skill.id, panel.ctx.inputs)
            }
            GButton {
                text: qsTr("Reverter versão")
                variant: "secondary"
                enabled: canDo && !runActive
                Accessible.name: qsTr("Reverter versão de %1").arg(panel.has ? panel.skill.id : "")
                onClicked: core.skillRollback(panel.skill.id)
            }
            GButton {
                text: qsTr("Exportar")
                variant: "secondary"
                enabled: panel.enabledFor("export")
                Accessible.name: qsTr("Exportar %1").arg(panel.has ? panel.skill.id : "")
                onClicked: core.skillExport(panel.skill.id, panel.skill.version)
            }
            GButton {
                text: qsTr("Remover")
                variant: "danger"
                enabled: panel.canDo
                Accessible.name: qsTr("Remover %1").arg(panel.has ? panel.skill.id : "")
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
