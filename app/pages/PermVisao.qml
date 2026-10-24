import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Permissões > Visão geral: what waits for the user's decision now, with a way to each place. Decisions are made there.
PageFrame {
    id: page
    objectName: "page_perm_visao"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "perm_visao"

    readonly property int pendingTools: {
        var n = 0
        for (var i = 0; i < core.toolProposals.length; i++) if (core.toolProposals[i].state === "pending") n++
        return n
    }
    readonly property int pendingScopes: {
        var n = 0
        for (var i = 0; i < core.connectionsItems.length; i++) n += (core.connectionsItems[i].pending_scopes || []).length
        return n
    }
    readonly property int pendingSkillSteps: core.skillCurrentRun && core.skillCurrentRun.steps ? core.skillCurrentRun.steps.filter(function (s) { return s.state === "awaiting_approval" }).length : 0
    readonly property int pendingTotal: pendingTools + pendingScopes + pendingSkillSteps

    PageHeader {
        title: "Visão geral"
        subtitle: "Decisões que esperam você e o que já foi concedido."
    }
    Section {
        title: "Fila de pendências"
        visible: page.pendingTotal > 0
        ListRow {
            visible: page.pendingTools > 0
            objectName: "pendingTools"
            title: "Propostas de ferramenta"
            detail: page.pendingTools + " aguardando sua decisão"
            iconName: "chat"
            onClicked: Window.window.goPage("conversa")
            GButton { text: "Revisar"; variant: "secondary"; onClicked: Window.window.goPage("conversa") }
        }
        ListRow {
            visible: page.pendingScopes > 0
            objectName: "pendingScopes"
            title: "Escopos de conexão"
            detail: page.pendingScopes + " aguardando seu consentimento"
            iconName: "plug"
            onClicked: Window.window.goPage("conexoes")
            GButton { text: "Revisar"; variant: "secondary"; onClicked: Window.window.goPage("conexoes") }
        }
        ListRow {
            visible: page.pendingSkillSteps > 0
            objectName: "pendingSkillSteps"
            title: "Passos de skill"
            detail: page.pendingSkillSteps + " aguardando sua decisão"
            iconName: "sparkles"
            onClicked: Window.window.goPage("skills")
            GButton { text: "Revisar"; variant: "secondary"; onClicked: Window.window.goPage("skills") }
        }
    }
    EmptyState {
        visible: page.pendingTotal === 0
        iconName: "shield"
        message: "Nada pendente."
    }

    Section {
        title: "Concedido recentemente"
        Text {
            visible: core.hubEntries.length === 0 && core.connectionsItems.length === 0 && core.skillsItems.length === 0
            text: "Nenhuma permissão concedida ainda."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Repeater {
            model: core.hubEntries.filter(function (e) { return e.permissions_approved === true })
            delegate: ListRow {
                required property var modelData
                title: modelData.plugin_id + " " + modelData.semver
                detail: "Plugin · permissões aprovadas para este manifesto"
                iconName: "puzzle"
            }
        }
        Repeater {
            model: core.connectionsItems.filter(function (c) { return (c.granted_scopes || []).length > 0 })
            delegate: ListRow {
                required property var modelData
                title: modelData.label
                detail: "Conexão · escopos: " + modelData.granted_scopes.join(", ")
                iconName: "plug"
            }
        }
    }

    Collapsible {
        title: "Como funciona"
        summary: "Plugins, skills e conexões pedem sua permissão; esta tela só lista o que espera decisão."
        Text {
            text: "O Hub declara permissões e registra aprovação por manifesto. Plugins instalados e aprovados podem ser ativados em sandbox sem rede. Comandos da Base não dependem de plugins."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
    }
}
