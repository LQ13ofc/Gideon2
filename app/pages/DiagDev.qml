import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Diagnóstico > Desenvolvedor (docs/ui-spec/50-diagnostico.md §8): test tools, shown only while the developer mode is on.
// Raw identifiers (engine, plugin, capability, hash) are shown here and only here. Nothing on this page grants a permission.
PageFrame {
    id: page
    objectName: "page_diag_dev"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "diag_dev" && Theme.devMode

    readonly property var pack: core.snapshotPack
    readonly property var engines: pack.engines || {}
    readonly property bool sessionActive: core.sessionId.length > 0
    readonly property string modeId: inputMode.currentId
    readonly property string replayText: core.wakeStatus === "replaying" ? "reproduzindo" : core.wakeStatus === "replay_finished" ? "encerrado" : "não ativo"

    // Capacidades dos plugins em execução (state = running), sem repetição.
    readonly property var capabilities: {
        var out = []
        var items = core.pluginItems
        for (var i = 0; i < items.length; i++) {
            if (items[i].state !== "running") continue
            var caps = items[i].capabilities || []
            for (var j = 0; j < caps.length; j++) if (out.indexOf(caps[j]) < 0) out.push(caps[j])
        }
        return out
    }

    // Bytes UTF-8 de um texto (limites: 512 para comando de texto, 2 048 para JSON).
    function utf8Length(text) {
        var n = 0
        for (var i = 0; i < text.length; i++) {
            var c = text.charCodeAt(i)
            if (c >= 0xd800 && c <= 0xdbff) { n += 4; i++ }
            else n += c < 0x80 ? 1 : c < 0x800 ? 2 : 3
        }
        return n
    }
    readonly property string textProblem: {
        var t = testField.text
        if (t.length === 0) return ""
        if (t.trim().length === 0) return "Texto vazio"
        if (page.utf8Length(t) > 512) return "Texto acima de 512 bytes"
        if (/[\u0000-\u001f\u007f]/.test(t)) return "Texto com quebra de linha ou controle não é aceito"
        return ""
    }
    readonly property string jsonProblem: {
        var t = jsonArea.text
        if (t.trim().length === 0) return ""
        if (page.utf8Length(t) > 2048) return "Entrada acima de 2 048 bytes."
        var value
        try { value = JSON.parse(t) } catch (e) { return "JSON inválido: use um objeto entre chaves." }
        if (value === null || typeof value !== "object" || Array.isArray(value)) return "A entrada deve ser um objeto JSON."
        return ""
    }

    function sendTest() { if (testSend.enabled) core.submitText(testField.text) }

    // Versões, hashes e revisões (V01–V09). Campo que a ponte não expõe: "não informado" (N8, N7).
    readonly property var versionLines: {
        var lines = []
        lines.push("Versão da Base: não informada")
        lines.push("Protocolo do Core: não informado")
        lines.push("Pacote de voz: " + (pack.id || "não informado") + " · escopo " + (pack.scope || "não informado"))
        lines.push("Motores: wake " + (engines.wake || "não informado") + " · stt " + (engines.stt || "não informado") + " · tts " + (engines.tts || "não informado"))
        lines.push("SHA-256 do pacote de voz: não informado")
        lines.push("SHA-256 do catálogo do Hub: não informado")
        var entries = core.hubEntries || []
        var shown = 0
        for (var i = 0; i < entries.length; i++) {
            var e = entries[i]
            if (!(e.status === "installed" || e.status === "update_available" || e.payload_staged === true)) continue
            shown += 1
            lines.push(e.plugin_id + " " + (e.semver || "") + " · manifesto " + String(e.manifest_sha256 || "").slice(0, 12) + "…")
        }
        if (shown === 0) lines.push("Nenhum plugin instalado")
        lines.push("Revisões: preferências " + core.preferencesRevision + " · motor LLM " + core.llmRevision)
        lines.push("Binário e PACKAGE.json: não informado")
        lines.push("SHA-256 da última captura: não informado")
        return lines
    }
    readonly property var badgeLines: [
        "SINTÉTICO — sem hardware real: o resultado é simulado; nenhum dispositivo real foi usado.",
        "SERVIDOR FALSO — sem credenciais reais: a conexão usa um servidor de teste.",
        "UNSUPPORTED — recurso não suportado neste ambiente; nada foi executado.",
        "em desenvolvimento — qualificação de teste; validação física pendente.",
        "requer prova de conceito — frase não qualificada; não pode ser escolhida.",
        "não verificado — o publisher não foi autenticado.",
        "pendente de validação humana — backend real ainda não validado com hardware."
    ]

    PageHeader {
        title: "Desenvolvedor"
        subtitle: "Ferramentas de teste. Não concedem permissões; use somente em desenvolvimento."
    }

    // Aviso da página (o único Banner): o modo está ligado. Desligar não tem diálogo (50 §8.4).
    Banner {
        objectName: "devBanner"
        kind: "warn"
        text: "Modo desenvolvedor ligado: ferramentas de teste. Não concedem permissões."
        actionText: "Desligar modo desenvolvedor"
        onActionRequested: {
            if (page.sessionActive) { AppState.toast("Indisponível: há uma sessão de voz em andamento"); return }
            if (AppState.uiSet("behavior.devMode", false)) AppState.toast("Modo desenvolvedor desligado.")
        }
    }

    GridLayout {
        Layout.fillWidth: true
        columns: page.width >= Theme.narrowWidth ? 2 : 1
        columnSpacing: Theme.space(24)
        rowSpacing: Theme.space(24)

        Section {
            title: "Entrada de teste"
            Layout.alignment: Qt.AlignTop
            Text {
                text: "Comando de texto de teste"
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.weight: 600
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(8)
                GTextField {
                    id: testField
                    objectName: "testTextField"
                    Layout.fillWidth: true
                    placeholderText: "Comando de texto no perfil de teste"
                    enabled: core.textAvailable
                    onAccepted: page.sendTest()
                }
                GButton {
                    id: testSend
                    objectName: "testSendButton"
                    variant: "primary"
                    text: "Enviar"
                    enabled: core.textAvailable && testField.text.length > 0 && page.textProblem.length === 0
                    onClicked: page.sendTest()
                }
            }
            FNote { visible: page.textProblem.length > 0; tone: "error"; small: true; text: page.textProblem }
            FNote {
                visible: !core.textAvailable
                small: true
                text: "Indisponível: " + (page.sessionActive ? "há uma sessão de voz em andamento" : "o Core não tem entrada de texto de teste (exige --virtual-input e --commands-sandbox).")
            }
            Text {
                text: core.textResult.length > 0 ? core.textResult : "Nenhum comando de teste enviado."
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            // O disparo de wake de teste ainda não existe na ponte (N3): desabilitado com o motivo.
            GButton {
                objectName: "virtualWakeButton"
                variant: "secondary"
                text: "Disparar wake de teste"
                enabled: false
            }
            FNote { small: true; text: "Indisponível: a ponte ainda não envia o wake de teste." }
            Text {
                text: "Replay de wake: " + page.replayText
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            FNote { small: true; text: "O replay é iniciado pelo Core com --wake-replay. Não há microfone nesta tela." }
        }

        Section {
            title: "Invocar capacidade"
            Layout.alignment: Qt.AlignTop
            FieldLabel { text: "Capacidade" }
            Select {
                id: capBox
                objectName: "capabilityBox"
                Layout.fillWidth: true
                enabled: page.capabilities.length > 0
                model: page.capabilities
                Accessible.name: "Capacidade"
            }
            FNote {
                visible: page.capabilities.length === 0
                tone: "text"
                text: "Nenhuma capacidade em execução. Ative um plugin em Extensões › Plugins."
            }
            Segmented {
                id: inputMode
                objectName: "capabilityMode"
                model: [{id: "text", text: "Texto"}, {id: "json", text: "JSON"}]
                currentId: "text"
                onActivated: function (id) { inputMode.currentId = id }
            }
            FieldLabel { visible: page.modeId === "text"; text: "Texto para a capacidade" }
            GTextField {
                id: capText
                objectName: "capabilityText"
                visible: page.modeId === "text"
                Layout.fillWidth: true
                maximumLength: 256
                enabled: page.capabilities.length > 0
                Accessible.name: "Texto para a capacidade"
            }
            FieldLabel { visible: page.modeId === "json"; text: "Entrada em JSON (objeto)" }
            TextArea {
                id: jsonArea
                objectName: "capabilityJson"
                visible: page.modeId === "json"
                Layout.fillWidth: true
                Layout.preferredHeight: 120
                placeholderText: "{ }"
                placeholderTextColor: Theme.textMuted
                color: Theme.text
                font.family: "monospace"
                font.pixelSize: Theme.fontHelp
                wrapMode: TextArea.Wrap
                selectByMouse: true
                Accessible.name: "Entrada em JSON (objeto)"
                background: Rectangle {
                    radius: Theme.radius
                    color: Theme.bg
                    border.width: jsonArea.activeFocus ? 2 : 1
                    border.color: jsonArea.activeFocus ? Theme.focusRing : Theme.strongOutline
                }
            }
            FNote { visible: page.modeId === "json" && page.jsonProblem.length > 0; tone: "error"; small: true; text: page.jsonProblem }
            FNote {
                visible: page.modeId === "json"
                small: true
                text: "Indisponível: a ponte ainda não envia objeto JSON para a capacidade."
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(12)
                GButton {
                    objectName: "invokeCapabilityButton"
                    variant: "primary"
                    text: "Invocar"
                    enabled: page.modeId === "text" && page.capabilities.length > 0 && capBox.currentText.length > 0 && core.pluginsAvailable
                    onClicked: core.invokeCapability(capBox.currentText, capText.text)
                }
                FNote { small: true; text: "Prazo: 3 s" }
            }
            FieldLabel { text: "Resultado" }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: resultText.implicitHeight + Theme.space(20)
                radius: Theme.radius
                color: Theme.bg
                border.width: 1
                border.color: Theme.hairline
                Text {
                    id: resultText
                    x: Theme.space(10)
                    y: Theme.space(10)
                    width: parent.width - Theme.space(20)
                    text: core.capabilityResultText.length > 0 ? core.capabilityResultText : "Sem resultado ainda."
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: "monospace"
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WrapAnywhere
                }
            }
        }

        Section {
            Layout.columnSpan: 2
            title: "Versões, hashes e selos"
            GridLayout {
                Layout.fillWidth: true
                columns: page.width >= Theme.narrowWidth ? 2 : 1
                columnSpacing: Theme.space(32)
                rowSpacing: Theme.space(16)
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    spacing: Theme.space(4)
                    Repeater {
                        model: page.versionLines
                        delegate: Text {
                            required property string modelData
                            text: modelData
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.family: "monospace"
                            font.pixelSize: Theme.fontHelp
                            wrapMode: Text.WrapAnywhere
                            Layout.fillWidth: true
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    spacing: Theme.space(6)
                    Text {
                        text: "Selos por extenso"
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        font.weight: 600
                    }
                    Repeater {
                        model: page.badgeLines
                        delegate: FNote {
                            required property string modelData
                            tone: "text"
                            text: modelData
                        }
                    }
                }
            }
        }
    }
}
