import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Extensões > Percepção e ação (needs a perception plugin). Parts: Privacidade (mic and camera indicators, also in the
// summary bar, always visible), Plugins (one card per plugin; test buttons in developer mode only) and Último resultado
// (developer mode only). Nothing here touches hardware: every backend is synthetic in this build.
PageFrame {
    id: page
    objectName: "perceptionPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "percepcao" && core.perceptionAvailable

    property string part: "privacidade"
    readonly property bool wide: width > 900
    readonly property int runningCount: core.perceptionPlugins.filter(function (p) { return p.state === "running" }).length
    readonly property string shownPart: (part === "resultado" && !Theme.devMode) ? "privacidade" : part

    function indicatorTone(value) { return value === "ligado" ? "error" : "neutral" }
    function indicatorColor(value) { return value === "ligado" ? Theme.error : Theme.textMuted }

    PageHeader {
        title: "Percepção e ação"
        subtitle: "Sensores e ações simulados nesta build. Nenhum hardware real é acessado."
    }
    // The one notice of the page: every backend here is synthetic, and display_manipulate is not supported.
    Banner {
        kind: "info"
        text: "Backends simulados: nenhum hardware pessoal é acessado nesta build. Backend real: não suportado / pendente de validação humana."
    }
    // The privacy indicators are always in view, whatever the part.
    CSummaryBar {
        text: page.runningCount + (page.runningCount === 1 ? " plugin de percepção em execução" : " plugins de percepção em execução")
        Badge {
            objectName: "micBadge"
            text: "Microfone: " + core.perceptionMicIndicator
            tone: page.indicatorTone(core.perceptionMicIndicator)
        }
        Badge {
            objectName: "cameraBadge"
            text: "Câmera: " + core.perceptionCameraIndicator
            tone: page.indicatorTone(core.perceptionCameraIndicator)
        }
    }
    GProgressBar {
        objectName: "perceptionProgress"
        visible: core.perceptionBusy
        indeterminate: true
        Layout.fillWidth: true
        Accessible.name: "Operação de percepção em andamento"
    }
    Segmented {
        model: Theme.devMode
            ? [{id: "privacidade", text: "Privacidade"}, {id: "plugins", text: "Plugins"}, {id: "resultado", text: "Último resultado"}]
            : [{id: "privacidade", text: "Privacidade"}, {id: "plugins", text: "Plugins"}]
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
            title: "Indicadores"
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(10)
                Rectangle { Layout.alignment: Qt.AlignVCenter; implicitWidth: 8; implicitHeight: 8; radius: 4; color: page.indicatorColor(core.perceptionMicIndicator) }
                Text {
                    objectName: "micIndicator"
                    text: "Microfone · indicador: " + core.perceptionMicIndicator
                    textFormat: Text.PlainText
                    color: page.indicatorColor(core.perceptionMicIndicator)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                    Accessible.name: "Indicador do microfone: " + core.perceptionMicIndicator
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(10)
                Rectangle { Layout.alignment: Qt.AlignVCenter; implicitWidth: 8; implicitHeight: 8; radius: 4; color: page.indicatorColor(core.perceptionCameraIndicator) }
                Text {
                    objectName: "cameraIndicator"
                    text: "Câmera · indicador: " + core.perceptionCameraIndicator
                    textFormat: Text.PlainText
                    color: page.indicatorColor(core.perceptionCameraIndicator)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                    Accessible.name: "Indicador da câmera: " + core.perceptionCameraIndicator
                }
            }
            Text {
                text: "Os indicadores mostram o último estado lido. Só a leitura de estado atualiza esta tela."
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        Section {
            title: "O que não é gravado"
            Text {
                text: "Nada é gravado em disco. Áudio e legendas ficam só em memória."
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
            title: "Plugins de percepção"
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
            text: "Nenhuma ação altera o computador nesta build."
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
        title: "Último resultado"
        Text {
            objectName: "perceptionResultEmpty"
            visible: core.perceptionResult.length === 0
            text: "Nenhuma ação executada nesta sessão."
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
            Accessible.name: "Resultado da percepção: " + text
        }
    }
}
