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
    readonly property string replayText: core.wakeStatus === "replaying" ? qsTr("reproduzindo") : core.wakeStatus === "replay_finished" ? qsTr("encerrado") : qsTr("não ativo")

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
        if (t.trim().length === 0) return qsTr("Texto vazio")
        if (page.utf8Length(t) > 512) return qsTr("Texto acima de 512 bytes")
        if (/[\u0000-\u001f\u007f]/.test(t)) return qsTr("Texto com quebra de linha ou controle não é aceito")
        return ""
    }
    readonly property string jsonProblem: {
        var t = jsonArea.text
        if (t.trim().length === 0) return ""
        if (page.utf8Length(t) > 2048) return qsTr("Entrada acima de 2 048 bytes.")
        var value
        try { value = JSON.parse(t) } catch (e) { return qsTr("JSON inválido: use um objeto entre chaves.") }
        if (value === null || typeof value !== "object" || Array.isArray(value)) return qsTr("A entrada deve ser um objeto JSON.")
        return ""
    }

    // B7: a JSON object within the limits (the same refusals as the bridge, shown before the send).
    readonly property bool jsonReady: jsonArea.text.trim().length > 0 && page.jsonProblem.length === 0

    function sendTest() { if (testSend.enabled) core.submitText(testField.text) }

    // Versões, hashes e revisões (V01–V09). Campo que a ponte não expõe: "não informado" (N8, N7).
    function baseVersion(pkg) {
        if (!pkg.installed) return qsTr("não é um pacote instalado")
        return pkg.commit ? qsTr("%1 · commit %2").arg(pkg.version).arg(pkg.commit) : String(pkg.version)
    }
    readonly property var versionLines: {
        var lines = []
        var pkg = core.packageInfo
        var notInformed = qsTr("não informado")
        lines.push(qsTr("Versão da Base: %1").arg(page.baseVersion(pkg)))
        lines.push(qsTr("Protocolo do Core: não informado"))
        lines.push(qsTr("Pacote de voz: %1 · escopo %2").arg(pack.id || notInformed).arg(pack.scope || notInformed))
        lines.push(qsTr("Motores: wake %1 · stt %2 · tts %3").arg(engines.wake || notInformed).arg(engines.stt || notInformed).arg(engines.tts || notInformed))
        lines.push(qsTr("SHA-256 do pacote de voz: não informado"))
        lines.push(qsTr("SHA-256 do catálogo do Hub: %1").arg(core.hubStorage.catalogSha ? core.hubStorage.catalogSha + "…" : notInformed))
        var entries = core.hubEntries || []
        var shown = 0
        for (var i = 0; i < entries.length; i++) {
            var e = entries[i]
            if (!(e.status === "installed" || e.status === "update_available" || e.payload_staged === true)) continue
            shown += 1
            lines.push(qsTr("%1 %2 · manifesto %3…").arg(e.plugin_id).arg(e.semver || "").arg(String(e.manifest_sha256 || "").slice(0, 12)))
        }
        if (shown === 0) lines.push(qsTr("Nenhum plugin instalado"))
        lines.push(qsTr("Revisões: preferências %1 · motor LLM %2").arg(core.preferencesRevision).arg(core.llmRevision))
        lines.push(qsTr("PACKAGE.json: %1").arg(pkg.installed ? qsTr("versão %1 · commit %2 · runtime %3").arg(pkg.version).arg(pkg.commit || notInformed).arg(pkg.runtime) : qsTr("não é um pacote instalado")))
        var sha = String(core.captureSummary.pcm_sha256 || "")
        lines.push(qsTr("SHA-256 da última captura: %1").arg(sha.length > 0 ? sha.slice(0, 12) + "…" : qsTr("nenhuma captura nesta sessão")))
        return lines
    }
    readonly property var badgeLines: [
        qsTr("SINTÉTICO — sem hardware real: o resultado é simulado; nenhum dispositivo real foi usado."),
        qsTr("SERVIDOR FALSO — sem credenciais reais: a conexão usa um servidor de teste."),
        qsTr("UNSUPPORTED — recurso não suportado neste ambiente; nada foi executado."),
        qsTr("aguardando credenciais — Google e Home Assistant só são testados com credenciais reais."),
        qsTr("não ativado: precisa de gravações da sua voz — o despertar nativo em português e francês."),
        qsTr("não verificado — o publisher não foi autenticado."),
        qsTr("pendente de validação humana — backend real ainda não validado com hardware.")
    ]

    PageHeader {
        title: qsTr("Desenvolvedor")
        subtitle: qsTr("Ferramentas de teste. Não concedem permissões; use somente em desenvolvimento.")
    }

    // Aviso da página (o único Banner): o modo está ligado. Desligar não tem diálogo (50 §8.4).
    Banner {
        objectName: "devBanner"
        kind: "warn"
        text: qsTr("Modo desenvolvedor ligado: ferramentas de teste. Não concedem permissões.")
        actionText: qsTr("Desligar modo desenvolvedor")
        onActionRequested: {
            if (page.sessionActive) { AppState.toast(qsTr("Indisponível: há uma sessão de voz em andamento")); return }
            if (AppState.uiSet("behavior.devMode", false)) AppState.toast(qsTr("Modo desenvolvedor desligado."))
        }
    }

    GridLayout {
        Layout.fillWidth: true
        columns: page.width >= Theme.narrowWidth ? 2 : 1
        columnSpacing: Theme.space(24)
        rowSpacing: Theme.space(24)

        Section {
            title: qsTr("Entrada de teste")
            Layout.alignment: Qt.AlignTop
            Text {
                text: qsTr("Comando de texto de teste")
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
                    placeholderText: qsTr("Comando de texto no perfil de teste")
                    enabled: core.textAvailable
                    onAccepted: page.sendTest()
                }
                GButton {
                    id: testSend
                    objectName: "testSendButton"
                    variant: "primary"
                    text: qsTr("Enviar")
                    enabled: core.textAvailable && testField.text.length > 0 && page.textProblem.length === 0
                    onClicked: page.sendTest()
                }
            }
            FNote { visible: page.textProblem.length > 0; tone: "error"; small: true; text: page.textProblem }
            FNote {
                visible: !core.textAvailable
                small: true
                text: page.sessionActive ? qsTr("Indisponível: há uma sessão de voz em andamento") : qsTr("Indisponível: o Core não tem entrada de texto de teste (exige --virtual-input e --commands-sandbox).")
            }
            Text {
                text: core.textResult.length > 0 ? core.textResult : qsTr("Nenhum comando de teste enviado.")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            // B6: envia virtual_wake. O Core só aceita com --virtual-input; a recusa aparece na linha de resultado.
            GButton {
                objectName: "virtualWakeButton"
                variant: "secondary"
                text: qsTr("Disparar wake de teste")
                enabled: core.virtualWakeAvailable && !page.sessionActive
                onClicked: core.virtualWake()
            }
            Text {
                objectName: "wakeResult"
                visible: text.length > 0
                text: core.wakeResult
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            FNote { small: true; text: qsTr("Exige o Core iniciado com --virtual-input; sem ele, o Core recusa o wake de teste.") }
            Text {
                text: qsTr("Replay de wake: %1").arg(page.replayText)
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            FNote { small: true; text: qsTr("O replay é iniciado pelo Core com --wake-replay. Não há microfone nesta tela.") }
        }

        Section {
            title: qsTr("Invocar capacidade")
            Layout.alignment: Qt.AlignTop
            FieldLabel { text: qsTr("Capacidade") }
            Select {
                id: capBox
                objectName: "capabilityBox"
                Layout.fillWidth: true
                enabled: page.capabilities.length > 0
                model: page.capabilities
                Accessible.name: qsTr("Capacidade")
            }
            FNote {
                visible: page.capabilities.length === 0
                tone: "text"
                text: qsTr("Nenhuma capacidade em execução. Ative um plugin em Extensões › Plugins.")
            }
            Segmented {
                id: inputMode
                objectName: "capabilityMode"
                model: [{id: "text", text: qsTr("Texto")}, {id: "json", text: "JSON"}]
                currentId: "text"
                onActivated: function (id) { inputMode.currentId = id }
            }
            FieldLabel { visible: page.modeId === "text"; text: qsTr("Texto para a capacidade") }
            GTextField {
                id: capText
                objectName: "capabilityText"
                visible: page.modeId === "text"
                Layout.fillWidth: true
                maximumLength: 256
                enabled: page.capabilities.length > 0
                Accessible.name: qsTr("Texto para a capacidade")
            }
            FieldLabel { visible: page.modeId === "json"; text: qsTr("Entrada em JSON (objeto)") }
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
                Accessible.name: qsTr("Entrada em JSON (objeto)")
                background: Rectangle {
                    radius: Theme.radius
                    color: Theme.bg
                    border.width: jsonArea.activeFocus ? 2 : 1
                    border.color: jsonArea.activeFocus ? Theme.focusRing : Theme.strongOutline
                }
            }
            FNote { visible: page.modeId === "json" && page.jsonProblem.length > 0; tone: "error"; small: true; text: page.jsonProblem }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(12)
                GButton {
                    objectName: "invokeCapabilityButton"
                    variant: "primary"
                    text: qsTr("Invocar")
                    enabled: page.capabilities.length > 0 && capBox.currentText.length > 0 && core.pluginsAvailable && !core.capabilityPending
                             && (page.modeId === "text" || page.jsonReady)
                    onClicked: page.modeId === "text" ? core.invokeCapability(capBox.currentText, capText.text)
                                                      : core.invokeCapabilityJson(capBox.currentText, jsonArea.text)
                }
                GButton {
                    objectName: "cancelCapabilityButton"
                    variant: "secondary"
                    text: qsTr("Cancelar invocação")
                    visible: core.capabilityPending
                    enabled: core.capabilityInFlight.length > 0 && core.pluginsAvailable
                    onClicked: core.cancelCapability(core.capabilityInFlight)
                }
                FNote { small: true; text: page.modeId === "text" ? qsTr("Prazo: 3 s") : qsTr("Prazo: 10 s (30 s no selftest do modelo)") }
            }
            Text {
                objectName: "capabilityStatus"
                visible: text.length > 0
                text: core.pluginResult
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            FieldLabel { text: qsTr("Resultado") }
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
                    text: core.capabilityResultText.length > 0 ? core.capabilityResultText : qsTr("Sem resultado ainda.")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: "monospace"
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WrapAnywhere
                }
            }
        }

        // A13: the last stderr tail of the wake worker. It can name paths, so it lives here only (0600 file in the Core data
        // dir, read on demand). The snapshot carries the content-free reason code alone.
        Section {
            id: devTail
            Layout.columnSpan: 2
            title: qsTr("Último erro do wake (diagnóstico)")
            property string tailText: ""
            function refreshTail() { tailText = core.connected ? core.liveLastErrorText() : "" }
            Component.onCompleted: refreshTail()
            Text {
                text: qsTr("Motivo (sem conteúdo): %1").arg(core.audioLive.last_error ? String(core.audioLive.last_error) : qsTr("nenhum registrado"))
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            TextEdit {
                id: liveTail
                objectName: "liveLastErrorText"
                text: devTail.tailText.length > 0 ? devTail.tailText : qsTr("Sem saída de erro guardada.")
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.WrapAnywhere
                color: Theme.text
                font.family: "monospace"
                font.pixelSize: Theme.fontHelp
                Layout.fillWidth: true
                Accessible.name: qsTr("Diagnóstico do worker de wake")
            }
            RowLayout {
                spacing: Theme.space(10)
                GButton {
                    objectName: "copyLiveLastError"
                    variant: "secondary"
                    text: qsTr("Copiar")
                    Accessible.name: qsTr("Copiar o diagnóstico do worker de wake")
                    onClicked: { liveTail.selectAll(); liveTail.copy() }
                }
                GButton {
                    objectName: "refreshLiveLastError"
                    variant: "ghost"
                    text: qsTr("Atualizar")
                    onClicked: devTail.refreshTail()
                }
            }
        }
        Section {
            Layout.columnSpan: 2
            title: qsTr("Versões, hashes e selos")
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
                        text: qsTr("Selos por extenso")
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
