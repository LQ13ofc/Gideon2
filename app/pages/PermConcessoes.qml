import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Permissões > Concessões: one list of what was granted, by origin (plugins, skills, connections). The action opens the place that decides.
PageFrame {
    id: page
    objectName: "page_perm_concessoes"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "perm_concessoes"

    property string filter: "todas"
    readonly property var plugins: core.hubEntries.filter(function (e) { return e.permissions_approved === true || e.status === "installed" })
    readonly property var skills: core.skillsItems
    readonly property var connections: core.connectionsItems

    PageHeader {
        title: "Concessões"
        subtitle: "Tudo o que você concedeu, em português, com a ação de revisar ou revogar."
    }
    Segmented {
        objectName: "grantFilter"
        model: [{id: "todas", text: "Todas"}, {id: "plugins", text: "Plugins"}, {id: "skills", text: "Skills"}, {id: "conexoes", text: "Conexões"}]
        currentId: page.filter
        onActivated: function (id) { page.filter = id }
    }
    Section {
        title: "Concessões"
        Text {
            visible: page.plugins.length + page.skills.length + page.connections.length === 0
            text: "Nada concedido ainda."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true
        }
        Repeater {
            model: page.filter === "todas" || page.filter === "plugins" ? page.plugins : []
            delegate: ListRow {
                required property var modelData
                objectName: "grant_plugin_" + modelData.plugin_id
                title: modelData.plugin_id + " " + modelData.semver
                detail: "Plugins · " + (modelData.permissions_approved ? "permissões aprovadas" : "permissões não aprovadas") + " · " + (modelData.permissions.map(function (p) { return core.permissionLabel(p) }).join(", ") || "nenhuma")
                iconName: "puzzle"
                GButton { text: "Revisar"; variant: "secondary"; onClicked: Window.window.goPage("plugins") }
            }
        }
        Repeater {
            model: page.filter === "todas" || page.filter === "skills" ? page.skills : []
            delegate: ListRow {
                required property var modelData
                objectName: "grant_skill_" + modelData.id
                title: modelData.id + " v" + modelData.version
                detail: "Skills · necessárias e aprovadas: " + (modelData.permissions_ok ? "tudo aprovado" : "faltando " + (modelData.missing.join(", ") || "—"))
                iconName: "sparkles"
                GButton { text: "Revisar"; variant: "secondary"; onClicked: Window.window.goPage("skills") }
            }
        }
        Repeater {
            model: page.filter === "todas" || page.filter === "conexoes" ? page.connections : []
            delegate: ListRow {
                required property var modelData
                objectName: "grant_conn_" + modelData.id
                title: modelData.label + " · " + L.connProviderName(modelData.provider)
                detail: "Conexões · concedido: " + L.connScopeNames(modelData.granted_scopes) + ((modelData.pending_scopes || []).length ? " · pendente: " + modelData.pending_scopes.join(", ") : "")
                iconName: "plug"
                GButton { text: "Revisar"; variant: "secondary"; onClicked: Window.window.goPage("conexoes") }
            }
        }
    }
}
