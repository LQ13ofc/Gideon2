import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Assistente > Atividade: one timeline of what the assistant did, without content. The Core events are not exposed to the
// window yet (the snapshot carries them, the bridge does not), so the page says so and shows its empty state.
PageFrame {
    id: page
    objectName: "page_atividade"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "atividade"

    PageHeader {
        title: "Atividade"
        subtitle: "Linha do tempo do que o Gideon fez, sem conteúdo sensível."
    }
    Banner {
        kind: "info"
        text: "Indisponível: a ponte ainda não expõe o histórico de eventos do Core."
    }
    Segmented {
        enabled: false
        model: [{id: "all", text: "Tudo"}, {id: "cmd", text: "Comandos"}, {id: "skill", text: "Skills"}, {id: "agent", text: "Agente"}, {id: "err", text: "Erros"}]
        currentId: "all"
    }
    EmptyState {
        iconName: "activity"
        message: "Nada ainda nesta sessão."
    }
}
