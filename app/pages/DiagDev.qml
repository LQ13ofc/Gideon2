import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Diagnóstico > Desenvolvedor: shown only while the developer mode is on. Technical labels live here, in full.
PageFrame {
    id: page
    objectName: "page_diag_dev"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "diag_dev" && Theme.devMode

    PageHeader {
        title: "Desenvolvedor"
        subtitle: "Ferramentas técnicas para depuração. Não use para o dia a dia."
    }
    Banner {
        kind: "warn"
        text: "Modo desenvolvedor ligado: rótulos técnicos completos e comandos de teste."
    }
    Section {
        title: "Comando de teste"
        Text {
            text: core.textAvailable ? "O comando de teste fica em Assistente › Hoje, no campo de comando." : "Indisponível: o perfil atual não aceita comandos de teste."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
    }
    Section {
        title: "Capacidades e replays"
        Text {
            text: "Invocar capabilities fica em Extensões › Plugins (campo de cada plugin ligado). Os rótulos SINTÉTICO e SERVIDOR FALSO aparecem por extenso nas telas de Percepção e Conexões."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        SettingRow { label: "Replay de sessão"; help: "Repete uma sessão gravada."; disabledReason: "ainda não exposto pela ponte" }
    }
}
