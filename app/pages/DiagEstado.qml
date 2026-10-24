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
            add("—", "Plugin", p.last_error ? E.codePhrase(p.last_error) : E.pluginStatePhrase(p.state), p.last_error || p.state)
        }
        var engines = [{status: wake, kind: "wake_failed", area: "Motores"}, {status: stt, kind: "stt_failed", area: "Voz"}, {status: speech, kind: "tts_failed", area: "Voz"}]
        for (var k = 0; k < engines.length; k++) {
            if (engines[k].status !== "failed" || kinds[engines[k].kind]) continue
            add("—", engines[k].area, E.eventPhrase(engines[k].kind, "failed"), engines[k].kind)
        }
        return rows
    }

    PageHeader {
        title: "Estado"
        subtitle: "Core, configuração, perfil da Base e últimos erros desta sessão."
    }

    GridLayout {
        Layout.fillWidth: true
        columns: page.width >= Theme.narrowWidth ? 2 : 1
        columnSpacing: Theme.space(24)
        rowSpacing: Theme.space(24)

        Section {
            title: "Core e configuração"
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
                    text: core.connected ? "Conectado ao Core" : "Core desconectado"
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                }
            }
            FNote { visible: !core.connected; small: true; text: "Tentando reconectar sozinho (intervalo de 0,5 a 5 s)." }
            Text {
                text: "Estado atual: " + (core.connected ? E.sessionPhrase(core.state) : "Core desconectado")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: "Sessão de voz: " + (page.sessionActive ? "em andamento" : "nenhuma")
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
                    text: "Configuração:"
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
                text: core.configurationMessage.length > 0 ? core.configurationMessage : "Nenhuma ação pendente"
            }
            GButton {
                visible: page.configCode !== "ready"
                variant: "secondary"
                text: "Abrir Recuperação"
                onClicked: Window.window.goPage("diag_recuperacao")
            }
        }

        Section {
            title: "Base e privacidade"
            Layout.alignment: Qt.AlignTop
            Text {
                text: "Perfil: " + (core.connected ? (E.scopeLabel(page.pack.scope) || "não informado") : "—")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: "Idioma da interface: português"
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            Text {
                text: "Idioma da voz: " + (core.connected ? E.languageLabel(page.pack.language) : "—")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            FNote { small: true; text: "Português para voz não está comprovado." }
            Text {
                text: "Pacote de voz: " + (core.connected && page.pack.id ? E.packLabel(page.pack.id) : "—")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                Layout.fillWidth: true
            }
            // B5: versão, commit e data de geração lidos do PACKAGE.json do pacote instalado (a raiz do pacote é o pai de app/).
            Text {
                objectName: "packageVersionText"
                text: "Versão da Base: " + (core.packageInfo.installed ? core.packageInfo.version + (core.packageInfo.commit ? " · commit " + core.packageInfo.commit : "") : "—")
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                visible: core.packageInfo.installed
                text: "Pacote gerado em: " + core.packageInfo.built + " · runtime: " + core.packageInfo.runtime
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            FNote { visible: core.packageInfo.installed && core.packageInfo.dirty; tone: "warn"; small: true; text: "O pacote foi gerado com alterações não commitadas." }
            FNote { visible: !core.packageInfo.installed; small: true; text: "Não é um pacote instalado: checkout de desenvolvimento, sem PACKAGE.json." }
            FNote { text: "Sem histórico de conversas. Áudio e legendas ficam só em memória." }
            SettingRow {
                label: "Modo desenvolvedor"
                help: "Mostra a aba Desenvolvedor, com ferramentas de teste. Não concede permissões."
                settingKey: "behavior.devMode"
                disabledReason: page.sessionActive ? "há uma sessão de voz em andamento" : (AppState.uiLive() ? "" : "configurações do app indisponíveis")
                Toggle {
                    id: devToggle
                    objectName: "devModeToggle"
                    text: checked ? "Ligado" : "Desligado"
                    checked: AppState.uiGet("behavior.devMode", false) === true
                    onToggled: {
                        if (checked) {
                            // Liga só depois da confirmação: o interruptor volta a seguir o valor salvo.
                            checked = Qt.binding(function () { return AppState.uiGet("behavior.devMode", false) === true })
                            devConfirm.open()
                        } else {
                            AppState.uiSet("behavior.devMode", false)
                            AppState.toast("Modo desenvolvedor desligado.")
                        }
                    }
                }
            }
            FNote { visible: page.sessionActive; small: true; text: "Preferências e modo desenvolvedor ficam bloqueados até a sessão terminar." }
        }

        Section {
            Layout.columnSpan: 2
            title: "Últimos erros"
            FNote { small: true; text: "Erros desta sessão, mais recentes primeiro. Máximo de 5." }
            Text {
                objectName: "lastErrors"
                visible: !core.connected
                text: "Sem dados: o Core está desconectado."
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
                    text: "Nenhum erro nesta sessão."
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    Layout.fillWidth: true
                }
                GButton {
                    variant: "ghost"
                    text: "Ver Atividade"
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
                        text: modelData.time + " · " + modelData.area + " · " + modelData.text
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    FNote { visible: Theme.advanced; small: true; text: "código: " + modelData.code }
                }
            }
        }
    }

    Collapsible {
        title: "Como funciona"
        summary: "O que o Core informou e os erros desta sessão."
        FNote {
            tone: "text"
            text: "Esta tela mostra fatos do Core e não muda nada. A configuração fica em Configurações; os motores estão na aba Motores. A lista de erros some quando o Core reinicia."
        }
    }

    Modal {
        id: devConfirm
        objectName: "devModeConfirm"
        title: "Ativar modo desenvolvedor?"
        standardButtons: Dialog.NoButton
        onOpened: devCancel.forceActiveFocus()
        onAccepted: { if (AppState.uiSet("behavior.devMode", true)) AppState.toast("Modo desenvolvedor ligado.") }
        Text {
            text: "Este modo mostra ferramentas de teste na aba Desenvolvedor: comando de texto de teste, wake de teste, invocação de capacidades de plugin com JSON e identificadores técnicos (versões e hashes). Elas não concedem permissões nem mudam o que o Gideon pode fazer no seu computador. Use somente em desenvolvimento ou teste."
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
                text: "Cancelar"
                onClicked: devConfirm.reject()
            }
            GButton {
                objectName: "confirmDevMode"
                variant: "primary"
                text: "Ativar modo desenvolvedor"
                onClicked: devConfirm.accept()
            }
        }
    }
}
