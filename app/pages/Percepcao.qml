import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Extensões > Percepção e ação (needs a perception plugin). Parts: Privacidade (mic and camera indicators, also in the
// summary bar, always visible), Plugins (one card per plugin; test buttons in developer mode only) and Último resultado
// (developer mode only). Every plugin here runs its real backend (scripts/perception_worker.py) in its own sandbox.
PageFrame {
    id: page
    objectName: "perceptionPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "percepcao" && core.perceptionAvailable

    property string part: "privacidade"
    readonly property bool wide: width > 900
    readonly property int runningCount: core.perceptionPlugins.filter(function (p) { return p.state === "running" }).length
    readonly property string shownPart: (part === "resultado" && !Theme.devMode) ? "privacidade" : part

    // The indicator readings come as codes from the bridge (on, off, unread, plugin_inactive); the words are translated here.
    function indicatorTone(state) { return state === "on" ? "error" : "neutral" }
    function indicatorColor(state) { return state === "on" ? Theme.error : Theme.textMuted }
    function indicatorWord(state) {
        switch (state) {
        case "on": return qsTr("ligado")
        case "off": return qsTr("desligado")
        case "unread": return qsTr("não lido")
        case "plugin_inactive": return qsTr("plugin inativo")
        default: return ""
        }
    }

    PageHeader {
        title: qsTr("Percepção e ação")
        subtitle: qsTr("Sensores e ações reais do computador. Cada plugin usa só o acesso que precisa e só funciona com permissão concedida.")
    }
    // The one notice of the page: the backends and what each refusal means.
    Banner {
        kind: "info"
        text: qsTr("Backends reais: portal XDG, AT-SPI, RemoteDesktop, PipeWire, v4l2 e KScreen. Quando um recurso não existe nesta sessão, a resposta diz qual backend faltou e nada é feito.")
    }
    // The privacy indicators are always in view, whatever the part.
    CSummaryBar {
        text: page.runningCount === 1 ? qsTr("%1 plugin de percepção em execução").arg(page.runningCount) : qsTr("%1 plugins de percepção em execução").arg(page.runningCount)
        Badge {
            objectName: "micBadge"
            text: qsTr("Microfone: %1").arg(page.indicatorWord(core.perceptionMicState))
            tone: page.indicatorTone(core.perceptionMicState)
        }
        Badge {
            objectName: "cameraBadge"
            text: qsTr("Câmera: %1").arg(page.indicatorWord(core.perceptionCameraState))
            tone: page.indicatorTone(core.perceptionCameraState)
        }
    }
    GProgressBar {
        objectName: "perceptionProgress"
        visible: core.perceptionBusy
        indeterminate: true
        Layout.fillWidth: true
        Accessible.name: qsTr("Operação de percepção em andamento")
    }
    Segmented {
        model: Theme.devMode
            ? [{id: "privacidade", text: qsTr("Privacidade")}, {id: "plugins", text: qsTr("Plugins")}, {id: "resultado", text: qsTr("Último resultado")}]
            : [{id: "privacidade", text: qsTr("Privacidade")}, {id: "plugins", text: qsTr("Plugins")}]
        currentId: page.shownPart
        onActivated: function (id) { page.part = id }
    }

    // Privacidade: the last state read, and what is never recorded.
    ColumnLayout {
        visible: page.shownPart === "privacidade"
        Layout.fillWidth: true
        spacing: Theme.space(24)
        Section {
            objectName: "privacyCard"
            title: qsTr("Indicadores")
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(10)
                Rectangle { Layout.alignment: Qt.AlignVCenter; implicitWidth: 8; implicitHeight: 8; radius: 4; color: page.indicatorColor(core.perceptionMicState) }
                Text {
                    objectName: "micIndicator"
                    text: qsTr("Microfone · indicador: %1").arg(page.indicatorWord(core.perceptionMicState))
                    textFormat: Text.PlainText
                    color: page.indicatorColor(core.perceptionMicState)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                    Accessible.name: qsTr("Indicador do microfone: %1").arg(page.indicatorWord(core.perceptionMicState))
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(10)
                Rectangle { Layout.alignment: Qt.AlignVCenter; implicitWidth: 8; implicitHeight: 8; radius: 4; color: page.indicatorColor(core.perceptionCameraState) }
                Text {
                    objectName: "cameraIndicator"
                    text: qsTr("Câmera · indicador: %1").arg(page.indicatorWord(core.perceptionCameraState))
                    textFormat: Text.PlainText
                    color: page.indicatorColor(core.perceptionCameraState)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                    Accessible.name: qsTr("Indicador da câmera: %1").arg(page.indicatorWord(core.perceptionCameraState))
                }
            }
            // B16: the live recorder of the Core (A6 consent, Dispositivos); "Microfone ativo" only while it captures.
            Text {
                objectName: "liveInputState"
                text: core.micActive ? qsTr("Microfone ativo · %1").arg(core.audioLiveText) : core.audioLiveText
                textFormat: Text.PlainText
                color: core.micActive ? Theme.warning : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                text: qsTr("Os indicadores mostram o último estado lido. Só a leitura de estado atualiza esta tela.")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        Section {
            title: qsTr("O que não é gravado")
            Text {
                text: qsTr("Nada é gravado em disco. Áudio e legendas ficam só em memória.")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }

    // Plugins: one card per perception plugin.
    ColumnLayout {
        visible: page.shownPart === "plugins"
        Layout.fillWidth: true
        spacing: Theme.space(16)
        Section {
            title: qsTr("Plugins de percepção")
            GridLayout {
                Layout.fillWidth: true
                columns: page.wide ? 2 : 1
                columnSpacing: Theme.space(16)
                rowSpacing: Theme.space(16)
                Repeater {
                    model: core.perceptionPlugins
                    delegate: CPerceptionCard {
                        required property var modelData
                        objectName: "perceptionCard_" + modelData.plugin_id
                        plugin: modelData
                    }
                }
            }
        }
        Text {
            text: qsTr("Nenhuma ação altera o computador nesta build.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
        }
    }

    // Último resultado: developer mode only; nothing from the screen or the microphone is shown here.
    Section {
        visible: page.shownPart === "resultado"
        title: qsTr("Último resultado")
        Text {
            objectName: "perceptionResultEmpty"
            visible: core.perceptionResult.length === 0
            text: qsTr("Nenhuma ação executada nesta sessão.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            objectName: "perceptionResult"
            text: core.perceptionResult
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Accessible.name: qsTr("Resultado da percepção: %1").arg(text)
        }
    }
}
