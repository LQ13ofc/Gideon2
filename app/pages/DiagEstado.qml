import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/EventLabels.js" as E

// Diagnóstico > Estado (docs/ui-spec/50-diagnostico.md §5): the Core connection and configuration, the voice pack and privacy,
// the developer-mode switch (behind a confirmation) and the last errors of this session. Reads the Core; only navigates.
PageFrame {
    id: page
    objectName: "diagnosticsPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "diag_estado"

    readonly property var pack: core.snapshotPack
    readonly property bool sessionActive: core.sessionId.length > 0
    // DIAG-05 formatting: a missing sample reads as a dash, never as zero.
    function cpuText(value) { return value === null || value === undefined ? "—" : Number(value).toFixed(1).replace(".", ",") + " %" }
    function mbText(kb) { return Math.round(Number(kb || 0) / 1024) + " MB" }
    function requestsText(n) { return n === 1 ? qsTr("%1 pedido").arg(n) : qsTr("%1 pedidos").arg(n) }
    function processesText(n) { return n === 1 ? qsTr("%1 processo").arg(n) : qsTr("%1 processos").arg(n) }
    // Versão da Base as the Core's package file reports it (installed packages only).
    function versionText(pkg) { return pkg.commit ? qsTr("%1 · commit %2").arg(pkg.version).arg(pkg.commit) : String(pkg.version) }
    // Idioma da interface: the endonym of the language the Core saved (names stay in their own language).
    function uiLanguageName() {
        switch (core.uiLanguage) {
        case "en": return "English"
        case "fr": return "Français"
        }
        return "Português (Brasil)"
    }
    readonly property string configCode: core.connected ? core.configurationStatus : "offline"

    // Últimos erros (§5.6 R-S1): error events newest first, then plugins that failed, then voice engines that failed
    // without an event. At most five rows; one row per kind and area; a row without time shows "—".
    readonly property var errorRows: collectErrors(core.events, core.pluginItems, core.wakeStatus, core.sttStatus, core.speechStatus, core.connected)
    function collectErrors(events, plugins, wake, stt, speech, connected) {
        var rows = []
        if (!connected) return rows
        var seen = {}
        function add(time, area, text, code) {
            var key = code + "|" + area
            if (seen[key] || rows.length >= 5 || text.length === 0) return
            seen[key] = true
            rows.push({time: time, area: area, text: text, code: code})
        }
        var sorted = (events || []).slice().sort(function (a, b) { return b.sequence - a.sequence })
        var kinds = {}
        for (var i = 0; i < sorted.length; i++) kinds[sorted[i].kind] = true
        for (var i = 0; i < sorted.length; i++) {
            var ev = sorted[i]
            if (!E.isErrorKind(ev.kind)) continue
            add(E.clockText(ev.at_ms), E.eventArea(ev.kind, ev.origin), E.eventPhrase(ev.kind, ev.outcome), ev.kind)
        }
        var items = plugins || []
        for (var j = 0; j < items.length; j++) {
            var p = items[j]
            if (p.state !== "failed" && p.state !== "quarantined") continue
            add("—", qsTr("Plugin"), p.last_error ? E.codePhrase(p.last_error) : E.pluginStatePhrase(p.state), p.last_error || p.state)
        }
        var engines = [{status: wake, kind: "wake_failed", area: qsTr("Motores")}, {status: stt, kind: "stt_failed", area: qsTr("Voz")}, {status: speech, kind: "tts_failed", area: qsTr("Voz")}]
        for (var k = 0; k < engines.length; k++) {
            if (engines[k].status !== "failed" || kinds[engines[k].kind]) continue
            add("—", engines[k].area, E.eventPhrase(engines[k].kind, "failed"), engines[k].kind)
        }
        return rows
    }

    PageHeader {
        title: qsTr("Estado")
        subtitle: qsTr("Core, configuração, perfil da Base e últimos erros desta sessão.")
    }

    GridLayout {
        Layout.fillWidth: true
        columns: page.width >= Theme.narrowWidth ? 2 : 1
        columnSpacing: Theme.space(24)
        rowSpacing: Theme.space(24)

        Section {
            title: qsTr("Core e configuração")
            Layout.alignment: Qt.AlignTop
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(8)
                Rectangle {
                    Layout.alignment: Qt.AlignVCenter
                    implicitWidth: 8; implicitHeight: 8; radius: 4
                    color: core.connected ? Theme.success : Theme.textMuted
                }
                Text {
                    text: core.connected ? qsTr("Conectado ao Core") : qsTr("Core desconectado")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                }
            }
            FNote { visible: !core.connected; small: true; text: qsTr("Tentando reconectar sozinho (intervalo de 0,5 a 5 s).") }
            Text {
                text: qsTr("Estado atual: %1").arg(core.connected ? E.sessionPhrase(core.state) : qsTr("Core desconectado"))
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: qsTr("Sessão de voz: %1").arg(page.sessionActive ? qsTr("em andamento") : qsTr("nenhuma"))
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(8)
                Text {
                    text: qsTr("Configuração:")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                }
                Badge {
                    text: E.configPhrase(page.configCode)
                    tone: E.toneOf(page.configCode)
                }
            }
            FNote {
                visible: core.connected
                tone: "muted"
                text: core.configurationMessage.length > 0 ? core.configurationMessage : qsTr("Nenhuma ação pendente")
            }
            GButton {
                visible: page.configCode !== "ready"
                variant: "secondary"
                text: qsTr("Abrir Recuperação")
                onClicked: Window.window.goPage("diag_recuperacao")
            }
        }

        Section {
            title: qsTr("Base e privacidade")
            Layout.alignment: Qt.AlignTop
            Text {
                text: qsTr("Perfil: %1").arg(core.connected ? (E.scopeLabel(page.pack.scope) || qsTr("não informado")) : "—")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: qsTr("Idioma da interface: %1").arg(page.uiLanguageName())
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: qsTr("Idioma da voz: %1").arg(core.connected ? E.languageLabel(page.pack.language) : "—")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            FNote { small: true; text: qsTr("Português para voz não está comprovado.") }
            Text {
                text: qsTr("Pacote de voz: %1").arg(core.connected && page.pack.id ? E.packLabel(page.pack.id) : "—")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            // B5: versão, commit e data de geração lidos do PACKAGE.json do pacote instalado (a raiz do pacote é o pai de app/).
            Text {
                objectName: "packageVersionText"
                text: qsTr("Versão da Base: %1").arg(core.packageInfo.installed ? page.versionText(core.packageInfo) : "—")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                visible: core.packageInfo.installed
                text: qsTr("Pacote gerado em: %1 · runtime: %2").arg(core.packageInfo.built).arg(core.packageInfo.runtime)
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            FNote { visible: core.packageInfo.installed && core.packageInfo.dirty; tone: "warn"; small: true; text: qsTr("O pacote foi gerado com alterações não commitadas.") }
            FNote { visible: !core.packageInfo.installed; small: true; text: qsTr("Não é um pacote instalado: checkout de desenvolvimento, sem PACKAGE.json.") }
            FNote { text: qsTr("Sem histórico de conversas. Áudio e legendas ficam só em memória.") }
            SettingRow {
                label: qsTr("Modo desenvolvedor")
                help: qsTr("Mostra a aba Desenvolvedor, com ferramentas de teste. Não concede permissões.")
                settingKey: "behavior.devMode"
                disabledReason: page.sessionActive ? qsTr("há uma sessão de voz em andamento") : (AppState.uiLive() ? "" : qsTr("configurações do app indisponíveis"))
                Toggle {
                    id: devToggle
                    objectName: "devModeToggle"
                    text: checked ? qsTr("Ligado") : qsTr("Desligado")
                    checked: AppState.uiGet("behavior.devMode", false) === true
                    onToggled: {
                        if (checked) {
                            // Liga só depois da confirmação: o interruptor volta a seguir o valor salvo.
                            checked = Qt.binding(function () { return AppState.uiGet("behavior.devMode", false) === true })
                            devConfirm.open()
                        } else {
                            AppState.uiSet("behavior.devMode", false)
                            AppState.toast(qsTr("Modo desenvolvedor desligado."))
                        }
                    }
                }
            }
            FNote { visible: page.sessionActive; small: true; text: qsTr("Preferências e modo desenvolvedor ficam bloqueados até a sessão terminar.") }
        }

        // DIAG-05: the round trip of the bridge to the Core and the resources of the Core processes (Linux /proc, sampled each second).
        Section {
            objectName: "diagPerformance"
            title: qsTr("Desempenho e recursos")
            Layout.alignment: Qt.AlignTop
            EValueRow {
                objectName: "coreLatencyRow"
                label: qsTr("Resposta do Core")
                value: core.coreLatency.known ? qsTr("%1 ms agora · média %2 ms em %3").arg(core.coreLatency.last_ms).arg(core.coreLatency.average_ms).arg(page.requestsText(core.coreLatency.samples)) : qsTr("ainda sem medidas")
            }
            EValueRow {
                objectName: "coreResourcesRow"
                label: qsTr("Processo do Core")
                value: core.diagResources.known ? qsTr("%1 de CPU · %2 de memória").arg(page.cpuText(core.diagResources.core_cpu_percent)).arg(page.mbText(core.diagResources.core_rss_kb)) : qsTr("indisponível neste sistema")
            }
            EValueRow {
                label: qsTr("Processos auxiliares")
                value: core.diagResources.workers_known === true
                    ? qsTr("%1 · %2 de CPU · %3 de memória").arg(page.processesText(core.diagResources.workers_count)).arg(page.cpuText(core.diagResources.workers_cpu_percent)).arg(page.mbText(core.diagResources.workers_rss_kb))
                    : qsTr("não medido")
                advanced: true
            }
            EValueRow {
                label: qsTr("Esta janela")
                value: core.diagResources.known ? qsTr("%1 de CPU · %2 de memória").arg(page.cpuText(core.diagResources.bridge_cpu_percent)).arg(page.mbText(core.diagResources.bridge_rss_kb)) : "—"
                advanced: true
            }
            FNote { small: true; text: qsTr("Medido a cada segundo. CPU é percentual de um núcleo; a primeira leitura ainda não tem CPU.") }
        }

        Section {
            Layout.columnSpan: 2
            title: qsTr("Últimos erros")
            FNote { small: true; text: qsTr("Erros desta sessão, mais recentes primeiro. Máximo de 5.") }
            Text {
                objectName: "lastErrors"
                visible: !core.connected
                text: qsTr("Sem dados: o Core está desconectado.")
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            RowLayout {
                visible: core.connected && page.errorRows.length === 0
                Layout.fillWidth: true
                spacing: Theme.space(12)
                Text {
                    text: qsTr("Nenhum erro nesta sessão.")
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.fillWidth: true
                }
                GButton {
                    variant: "ghost"
                    text: qsTr("Ver Atividade")
                    onClicked: Window.window.goPage("atividade")
                }
            }
            Repeater {
                model: page.errorRows
                delegate: ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: qsTr("%1 · %2 · %3").arg(modelData.time).arg(modelData.area).arg(modelData.text)
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    FNote { visible: Theme.advanced; small: true; text: qsTr("código: %1").arg(modelData.code) }
                }
            }
        }
    }

    Collapsible {
        title: qsTr("Como funciona")
        summary: qsTr("O que o Core informou e os erros desta sessão.")
        FNote {
            tone: "text"
            text: qsTr("Esta tela mostra fatos do Core e não muda nada. A configuração fica em Configurações; os motores estão na aba Motores. A lista de erros some quando o Core reinicia.")
        }
    }

    Modal {
        id: devConfirm
        objectName: "devModeConfirm"
        title: qsTr("Ativar modo desenvolvedor?")
        standardButtons: Dialog.NoButton
        onOpened: devCancel.forceActiveFocus()
        onAccepted: { if (AppState.uiSet("behavior.devMode", true)) AppState.toast(qsTr("Modo desenvolvedor ligado.")) }
        Text {
            text: qsTr("Este modo mostra ferramentas de teste na aba Desenvolvedor: comando de texto de teste, wake de teste, invocação de capacidades de plugin com JSON e identificadores técnicos (versões e hashes). Elas não concedem permissões nem mudam o que o Gideon pode fazer no seu computador. Use somente em desenvolvimento ou teste.")
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Item { Layout.fillWidth: true }
            GButton {
                id: devCancel
                variant: "secondary"
                text: qsTr("Cancelar")
                onClicked: devConfirm.reject()
            }
            GButton {
                objectName: "confirmDevMode"
                variant: "primary"
                text: qsTr("Ativar modo desenvolvedor")
                onClicked: devConfirm.accept()
            }
        }
    }
}
