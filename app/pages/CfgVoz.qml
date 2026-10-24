import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Configurações > Voz e Wake: the wake phrase (only the qualified phrases of the pack; a change needs a Core restart), the
// session limit (numbers are saved with "Salvar prazo") and the detection settings. Core values go through `ui` and show
// "Aplicando…" until the Core confirms them.
PageFrame {
    id: page
    objectName: "page_cfg_voz"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_voz"

    readonly property var choices: core.wakeChoices
    readonly property string savedPhrase: String(AppState.uiGet("core.wakePhrase", ""))
    readonly property string activePhrase: String(core.snapshotPack.active_phrase || "")
    readonly property bool canChange: AppState.blockReason("core.wakePhrase") === ""
    property var picked: null

    function choiceFor(id) {
        for (var i = 0; i < choices.length; i++) if (choices[i].id === id) return choices[i]
        return null
    }

    ECfgSearch {}
    PageHeader {
        title: "Voz e Wake"
        subtitle: "Frase de despertar certificada, prazo da sessão e estado do wake."
    }
    ECfgNotice {}

    Section {
        title: "Frase de despertar"
        Text {
            text: "Só frases qualificadas podem ser escolhidas. A troca vale depois de reiniciar o Core."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            visible: page.choices.length === 0
            text: "Nenhum pacote de voz configurado. Reparo só pela linha de comando (gideon-install repair)."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Flow {
            Layout.fillWidth: true
            spacing: Theme.space(12)
            visible: page.choices.length > 0
            Repeater {
                model: page.choices
                delegate: Rectangle {
                    id: tile
                    required property var modelData
                    objectName: "wakeCard_" + modelData.id
                    readonly property bool certified: modelData.qualification === "dev_qualified"
                    readonly property bool saved: page.savedPhrase === modelData.id
                    readonly property bool active: page.activePhrase === modelData.id
                    enabled: certified && page.canChange
                    opacity: enabled ? 1 : 0.5
                    width: 300
                    implicitHeight: tileBody.implicitHeight + Theme.space(28)
                    radius: Theme.radiusCard
                    color: tileMouse.containsMouse && tile.enabled ? Theme.hover : Theme.surfaceVariant
                    border.width: saved ? 2 : 1
                    border.color: saved ? Theme.accent : Theme.strongOutline
                    activeFocusOnTab: tile.enabled
                    Accessible.role: Accessible.Button
                    Accessible.name: modelData.text + ", " + modelData.qualification_label
                    Keys.onSpacePressed: if (tile.enabled) { page.picked = tile.modelData; wakeConfirm.open() }
                    Keys.onReturnPressed: if (tile.enabled) { page.picked = tile.modelData; wakeConfirm.open() }
                    Rectangle {
                        visible: tile.activeFocus
                        anchors.fill: parent
                        radius: parent.radius
                        color: "transparent"
                        border.width: 2
                        border.color: Theme.focusRing
                    }
                    ColumnLayout {
                        id: tileBody
                        anchors.left: parent.left; anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.space(14)
                        spacing: Theme.space(6)
                        Text {
                            text: tile.modelData.text
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSection
                            font.weight: 600
                            Layout.fillWidth: true
                        }
                        Badge {
                            text: tile.modelData.qualification_label
                            tone: tile.certified ? "info" : "warning"
                        }
                        Text {
                            visible: text.length > 0
                            text: (tile.saved ? "Salva" : "") + (tile.saved && tile.active ? " · " : "") + (tile.active ? "Ativa neste processo" : "")
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontHelp
                            Layout.fillWidth: true
                        }
                        Text {
                            text: tile.certified ? "Qualificada em desenvolvimento; validação física pendente" : "Bloqueada: sem qualidade aprovada"
                            textFormat: Text.PlainText
                            color: Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontHelp
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Text {
                            visible: !tile.certified
                            text: "Requer prova de conceito: frase sem qualidade aprovada"
                            textFormat: Text.PlainText
                            color: Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontCaption
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                    MouseArea {
                        id: tileMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: tile.enabled
                        onClicked: { page.picked = tile.modelData; wakeConfirm.open() }
                    }
                }
            }
        }
        Text {
            text: "Comprovado: a frase 'Hey Gideon' foi reconhecida em corpus de desenvolvimento, com verificação automática. Não comprovado: uso com microfone físico, em ambientes reais e com outras vozes. Não há reconhecimento comprovado em português (pt-BR). Não é certificação acústica. 'Okay Gideon' não tem qualidade aprovada e fica bloqueada."
            visible: page.choices.length > 0
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            lineHeight: 1.3
            Layout.fillWidth: true
        }
        SettingRow {
            settingKey: "core.wakePhrase"
            RowLayout {
                spacing: Theme.space(10)
                Select {
                    id: wakeChoice
                    objectName: "wakeChoice"
                    model: page.choices
                    textRole: "text"
                    valueRole: "id"
                    implicitWidth: 240
                    currentIndex: Math.max(0, indexOfValue(page.savedPhrase || page.activePhrase))
                    enabled: page.canChange && page.choices.length > 0
                    Accessible.name: "Frase de despertar do pacote"
                }
                GButton {
                    objectName: "selectWakeButton"
                    variant: "secondary"
                    text: "Trocar frase…"
                    Accessible.name: "Trocar a frase de despertar"
                    enabled: page.canChange && wakeChoice.currentIndex >= 0 && page.choices.length > 0 && page.choices[wakeChoice.currentIndex].qualification === "dev_qualified"
                    onClicked: { page.picked = page.choices[wakeChoice.currentIndex]; wakeConfirm.open() }
                }
            }
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
            label: "Sensibilidade"
            help: "Quão parecida a fala precisa ser com a frase para ser aceita."
            disabledReason: "limiar fixo no pacote; o Core não tem ajuste de sensibilidade"
            GSlider {
                enabled: false
                value: 0.5
                implicitWidth: 220
                Accessible.name: "Sensibilidade (indisponível)"
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
        summary: "A frase de despertar muda só entre as opções certificadas do pacote. Trocar exige reiniciar o Core."
        Text {
            text: "A frase de despertar muda só entre as opções certificadas do pacote. Trocar exige reiniciar o Core. O prazo da sessão vale na próxima sessão de voz."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    Modal {
        id: wakeConfirm
        objectName: "wakeConfirm"
        title: "Trocar frase de despertar?"
        Text {
            text: "Frase atual: " + (page.choiceFor(page.savedPhrase) ? page.choiceFor(page.savedPhrase).text : "padrão do pacote")
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            text: "Nova frase: " + (page.picked ? page.picked.text + " · " + page.picked.qualification_label : "")
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            text: "A troca só vale depois que o Core for reiniciado. Até lá, a frase atual continua ativa."
            textFormat: Text.PlainText
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmWakeButton"
            variant: "primary"
            text: "Trocar frase"
            Layout.alignment: Qt.AlignRight
            enabled: page.picked !== null && page.picked.qualification === "dev_qualified"
            onClicked: {
                AppState.setSetting("core.wakePhrase", page.picked.id)
                wakeConfirm.close()
            }
        }
    }
}
