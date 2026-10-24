import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Permissões > Auditoria: recent decisions, without content. The Core events are not exposed to the window yet.
PageFrame {
    id: page
    objectName: "page_perm_auditoria"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "perm_auditoria"

    PageHeader {
        title: "Auditoria"
        subtitle: "Eventos recentes do Core, sem conteúdo."
    }
    Banner {
        kind: "info"
        text: "Indisponível: a ponte ainda não expõe o feed de eventos do Core. Ele chega com o campo events do snapshot."
    }
    Segmented {
        enabled: false
        model: [{id: "all", text: "Tudo"}, {id: "plugin", text: "Plugin"}, {id: "skill", text: "Skill"}, {id: "conn", text: "Conexão"}, {id: "cmd", text: "Comando"}]
        currentId: "all"
    }
    EmptyState {
        iconName: "shield"
        message: "Nada registrado nesta sessão."
    }
}
