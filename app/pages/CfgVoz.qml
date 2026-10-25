import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Configurações > Voz e Wake: até 5 frases de despertar ativas ao mesmo tempo (cada uma com interruptor, qualificação e
// sensibilidade), frases personalizadas com teste sintético, e os ajustes de sessão e detecção. Trocar a lista vale depois
// de reiniciar o Core. Valores do Core passam por `ui` e mostram "Aplicando…" até o Core confirmar.
PageFrame {
    id: page
    objectName: "page_cfg_voz"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_voz"

    readonly property var rows: core.wakePhraseRows
    readonly property var testState: core.wakePhraseTest
    readonly property bool canEdit: core.preferencesAvailable
    readonly property bool testing: testState.state === "running"
    property var pickedWeak: null
    property var pickedRemove: null

    // B16 sensitivity (global): the saved value, or the value on its way to the Core while "Aplicando…" shows.
    readonly property real sensStored: Number(AppState.uiGet("core.wakeSensitivity", 1.0))
    readonly property real sensShown: AppState.isApplying("core.wakeSensitivity") ? Number(AppState.corePending["core.wakeSensitivity"]) : sensStored
    function sensText(v) { return Number(v).toFixed(2).replace(".", ",") }
    // Saved on release (or on a key press), in steps of 0.05; the Core answers through the ui settings.
    function saveSensitivity(v) { AppState.setSetting("core.wakeSensitivity", Number(Number(v).toFixed(2))) }

    function measurementText(m) {
        if (!m) return ""
        var text = "Teste sintético (rótulo sintético): " + m.hits + " de " + m.positives + " acertos · "
            + m.false_wakes + " falsos em " + m.negatives + " negativas"
        if (m.latency_ms !== undefined) text += " · " + m.latency_ms + " ms"
        return text
    }

    PageHeader {
        title: "Voz e Wake"
        subtitle: "Frases de despertar (até 5 ativas), testes sintéticos e prazo da sessão."
    }
    ECfgSearch {}
    ECfgNotice {}

    Section {
        title: "Frases de despertar"
        Text {
            text: "Escolha até 5 frases ativas. Frases do pacote usam a qualificação aprovada. Frases personalizadas ficam não testadas até o teste sintético. A troca vale depois de reiniciar o Core."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            visible: page.rows.length === 0
            text: "Nenhum pacote de voz configurado. Reparo só pela linha de comando (gideon-install repair)."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Repeater {
            model: page.rows
            delegate: Rectangle {
                id: row
                required property var modelData
                objectName: "wakeRow_" + modelData.id
                readonly property bool canSwitchOn: modelData.selectable && page.canEdit
                Layout.fillWidth: true
                implicitHeight: rowBody.implicitHeight + Theme.space(24)
                radius: Theme.radiusCard
                color: Theme.surfaceVariant
                border.width: modelData.active ? 2 : 1
                border.color: modelData.active ? Theme.accent : Theme.strongOutline
                Accessible.role: Accessible.Pane
                Accessible.name: modelData.text + ", " + modelData.qualification_label

                ColumnLayout {
                    id: rowBody
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.space(12)
                    spacing: Theme.space(6)
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space(10)
                        Switch {
                            id: rowSwitch
                            objectName: "wakeSwitch_" + row.modelData.id
                            checked: row.modelData.active
                            enabled: page.canEdit && (row.modelData.active || row.canSwitchOn) && !page.testing
                            Accessible.name: "Ativar " + row.modelData.text
                            onToggled: {
                                var id = row.modelData.id
                                if (checked && row.modelData.custom && row.modelData.measurement && !row.modelData.measurement.passed) {
                                    page.pickedWeak = row.modelData
                                    weakConfirm.open()
                                } else {
                                    core.setWakePhraseActive(id, checked, false)
                                }
                                // The switch follows the Core snapshot, not the click: a refused change never sticks.
                                checked = Qt.binding(function () { return row.modelData.active })
                            }
                        }
                        Text {
                            text: row.modelData.text
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSection
                            font.weight: 600
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                        }
                        Badge {
                            objectName: "wakeBadge_" + row.modelData.id
                            text: row.modelData.qualification_label
                            tone: (row.modelData.qualification === "dev_qualified" || (row.modelData.measurement && row.modelData.measurement.passed)) ? "info" : "warning"
                        }
                    }
                    Text {
                        visible: row.modelData.custom && !row.modelData.measurement
                        text: "Não testada: pode falhar ou disparar à toa. Teste antes de ativar."
                        textFormat: Text.PlainText
                        color: Theme.warning
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontHelp
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Text {
                        visible: row.modelData.measurement !== null && row.modelData.measurement !== undefined
                        objectName: "wakeMeasurement_" + row.modelData.id
                        text: page.measurementText(row.modelData.measurement)
                        textFormat: Text.PlainText
                        color: row.modelData.measurement && row.modelData.measurement.passed ? Theme.textMuted : Theme.warning
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontCaption
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Text {
                        visible: row.modelData.qualification === "poc_required"
                        text: "Requer prova de conceito: frase sem qualidade aprovada, bloqueada."
                        textFormat: Text.PlainText
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontCaption
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        visible: row.modelData.active
                        Layout.fillWidth: true
                        spacing: Theme.space(10)
                        Text {
                            text: "Sensibilidade desta frase"
                            textFormat: Text.PlainText
                            color: Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontCaption
                        }
                        GSlider {
                            objectName: "wakePhraseSensitivity_" + row.modelData.id
                            from: 0.5
                            to: 1.5
                            stepSize: 0.05
                            Layout.fillWidth: true
                            value: row.modelData.sensitivity !== null && row.modelData.sensitivity !== undefined ? row.modelData.sensitivity : page.sensShown
                            enabled: page.canEdit && !page.testing
                            Accessible.name: "Sensibilidade da frase " + row.modelData.text
                            onPressedChanged: if (!pressed) core.setWakePhraseSensitivity(row.modelData.id, value)
                            onMoved: if (!pressed) core.setWakePhraseSensitivity(row.modelData.id, value)
                        }
                    }
                    RowLayout {
                        visible: row.modelData.custom
                        Layout.fillWidth: true
                        spacing: Theme.space(10)
                        GButton {
                            objectName: "testWakePhrase_" + row.modelData.id
                            variant: "secondary"
                            text: "Testar frase"
                            Accessible.name: "Testar a frase " + row.modelData.text + " com áudio sintético"
                            enabled: core.preferencesAvailable && !page.testing
                            onClicked: core.testWakePhrase(row.modelData.id)
                        }
                        GButton {
                            objectName: "removeWakePhrase_" + row.modelData.id
                            variant: "ghost"
                            text: "Remover"
                            Accessible.name: "Remover a frase personalizada " + row.modelData.text
                            enabled: !row.modelData.active && page.canEdit
                            onClicked: { page.pickedRemove = row.modelData; deleteConfirm.open() }
                        }
                    }
                }
            }
        }
        Text {
            visible: page.testing
            objectName: "wakeTestProgress"
            text: "Testando a frase com áudio sintético… pode levar alguns segundos."
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            visible: page.testState.state === "failed" || page.testState.state === "done"
            objectName: "wakeTestResult"
            text: page.testState.state === "done" ? "Teste concluído: o resultado está na frase." : (page.testState.message || "O teste não concluiu.")
            textFormat: Text.PlainText
            color: page.testState.state === "done" ? Theme.textMuted : Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            visible: core.wakePhraseResult.length > 0
            objectName: "wakePhraseResult"
            text: core.wakePhraseResult
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            GButton {
                objectName: "addWakePhrase"
                variant: "primary"
                text: "Adicionar frase…"
                Accessible.name: "Adicionar uma frase de despertar personalizada"
                enabled: page.canEdit && core.wakePhraseCustomCount < 8
                onClicked: { phraseField.text = ""; core.checkWakePhrase(""); addDialog.open() }
            }
            GButton {
                objectName: "restoreWakeDefaults"
                variant: "ghost"
                text: "Restaurar padrão"
                Accessible.name: "Restaurar a frase de despertar padrão"
                enabled: page.canEdit && !page.testing
                onClicked: core.restoreWakePhraseDefaults()
            }
        }
        Text {
            text: "Comprovado: 'Hey Gideon' foi reconhecida em corpus sintético de desenvolvimento (75 de 76, sem falso disparo em 320 negativas e silêncio de 1 h). Não comprovado: microfone físico, ambientes reais e outras vozes. 'Okay Gideon' não tem qualidade aprovada. Frases personalizadas são sempre não testadas até o teste sintético."
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            lineHeight: 1.3
            Layout.fillWidth: true
        }
    }

    Section {
        title: "Sessão e estado"
        EValueRow {
            label: "Prazo máximo da sessão"
            value: Math.round(core.sessionTimeout / 1000) + " s"
        }
        EValueRow {
            label: "Estado do wake"
            value: L.statusText(core.wakeStatus)
        }
        EValueRow {
            label: "Captura"
            value: L.statusText(core.sttStatus)
        }
        SettingRow {
            settingKey: "core.sessionTimeoutMs"
            RowLayout {
                spacing: Theme.space(10)
                SpinBox {
                    id: timeout
                    objectName: "timeoutPreference"
                    from: 50
                    to: 60000
                    stepSize: 1000
                    editable: true
                    value: core.sessionTimeout
                    enabled: AppState.blockReason("core.sessionTimeoutMs") === ""
                    Accessible.name: "Prazo da sessão em milissegundos"
                    Connections {
                        target: core
                        function onPreferencesChanged() { timeout.value = core.sessionTimeout }
                    }
                }
                GButton {
                    objectName: "savePreferencesButton"
                    variant: "primary"
                    text: "Salvar prazo"
                    Accessible.name: "Salvar prazo da sessão"
                    enabled: AppState.blockReason("core.sessionTimeoutMs") === "" && timeout.value !== core.sessionTimeout
                    onClicked: AppState.setSetting("core.sessionTimeoutMs", timeout.value)
                }
            }
        }
    }

    Section {
        title: "Ajustes de detecção"
        SettingRow {
            settingKey: "core.wakeSensitivity"
            RowLayout {
                spacing: Theme.space(12)
                ColumnLayout {
                    spacing: 2
                    Layout.preferredWidth: 240
                    GSlider {
                        id: wakeSens
                        objectName: "wakeSensitivitySlider"
                        from: 0.5
                        to: 1.5
                        stepSize: 0.05
                        Layout.fillWidth: true
                        value: page.sensShown
                        Accessible.name: "Sensibilidade do wake: menos sensível a mais sensível"
                        onPressedChanged: if (!pressed) page.saveSensitivity(value)
                        onMoved: if (!pressed) page.saveSensitivity(value)
                    }
                    Binding {
                        target: wakeSens
                        property: "value"
                        value: page.sensShown
                        when: !wakeSens.pressed
                    }
                    Text {
                        objectName: "wakeSensitivityScale"
                        text: "Menos sensível ↔ Mais sensível"
                        textFormat: Text.PlainText
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontCaption
                        Layout.fillWidth: true
                    }
                }
                Text {
                    objectName: "wakeSensitivityValue"
                    text: page.sensText(wakeSens.pressed ? wakeSens.value : page.sensShown) + " · padrão 1,0"
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                    Layout.preferredWidth: 150
                    Accessible.name: "Sensibilidade atual " + page.sensText(page.sensShown) + ", padrão 1,0"
                }
                GButton {
                    objectName: "restoreWakeSensitivity"
                    variant: "ghost"
                    text: "Restaurar padrão"
                    Accessible.name: "Restaurar a sensibilidade do wake para o padrão 1,0"
                    enabled: AppState.blockReason("core.wakeSensitivity") === "" && Math.abs(page.sensShown - 1.0) > 0.001
                    onClicked: page.saveSensitivity(1.0)
                }
            }
        }
        SettingRow {
            settingKey: "voice.partials"
            EToggleSetting { settingKey: "voice.partials" }
        }
        SettingRow {
            settingKey: "voice.showConfidence"
            EToggleSetting { settingKey: "voice.showConfidence" }
        }
    }

    EAdvancedNote { subtab: "Voz e Wake" }

    Collapsible {
        title: "Como funciona"
        summary: "Até 5 frases ativas. Trocar a lista exige reiniciar o Core. Frases personalizadas precisam de teste sintético."
        Text {
            text: "Cada frase ativa tem a própria sensibilidade e o próprio limiar; a sensibilidade geral vale para as demais. O teste de frase personalizada usa áudio gerado pela voz de teste e rotula o resultado como sintético: ele não prova reconhecimento com a sua voz nem com o microfone. O prazo da sessão vale na próxima sessão de voz."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    Modal {
        id: addDialog
        objectName: "wakeAddDialog"
        title: "Adicionar frase de despertar"
        Text {
            text: "Use de 2 a 4 palavras, só letras e espaços. A frase é testada com áudio sintético antes de ser ativada."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GTextField {
            id: phraseField
            objectName: "wakePhraseField"
            placeholderText: "Ex.: Light Gideon"
            maximumLength: 40
            Layout.fillWidth: true
            onTextChanged: checkTimer.restart()
        }
        Timer {
            id: checkTimer
            interval: 300
            onTriggered: core.checkWakePhrase(phraseField.text)
        }
        Text {
            objectName: "wakePhraseCheckText"
            text: core.wakePhraseCheck.ok ? "Sons do detector: " + (core.wakePhraseCheck.tokens || "") : (core.wakePhraseCheck.message || "")
            textFormat: Text.PlainText
            color: core.wakePhraseCheck.ok ? Theme.textMuted : Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            text: "Não testada: pode falhar ou disparar à toa. Depois de salvar, teste a frase antes de ativá-la."
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmAddWakePhrase"
            variant: "primary"
            text: "Salvar frase"
            Layout.alignment: Qt.AlignRight
            enabled: core.wakePhraseCheck.ok === true && phraseField.text.trim().split(/\s+/).join(" ") === core.wakePhraseCheck.text && page.canEdit
            onClicked: { core.addWakePhrase(phraseField.text); addDialog.close() }
        }
    }

    Modal {
        id: weakConfirm
        objectName: "wakeWeakConfirm"
        title: "Ativar frase que falhou no teste?"
        Text {
            text: "O teste sintético desta frase não passou: ela pode não ser detectada, ou disparar sem você falar. Esse resultado não foi medido com a sua voz nem com o microfone."
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmWeakActivation"
            variant: "primary"
            text: "Ativar mesmo assim"
            Layout.alignment: Qt.AlignRight
            onClicked: { core.setWakePhraseActive(page.pickedWeak.id, true, true); weakConfirm.close() }
        }
    }

    Modal {
        id: deleteConfirm
        objectName: "wakeDeleteConfirm"
        title: "Remover frase personalizada?"
        Text {
            text: page.pickedRemove ? "A frase “" + page.pickedRemove.text + "” e o resultado do teste serão apagados. Esta ação não pode ser desfeita." : ""
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmDeleteWakePhrase"
            variant: "primary"
            text: "Remover frase"
            Layout.alignment: Qt.AlignRight
            onClicked: { core.removeWakePhrase(page.pickedRemove.id); deleteConfirm.close() }
        }
    }
}
