import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Configurações > Aparência: preset, mode, accent, density, corners, font size, and the orb. Each choice applies at once
// to this window (the app settings object `ui` saves it). The HUD switch goes to the Core, as before.
PageFrame {
    id: page
    objectName: "page_cfg_aparencia"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_aparencia"

    readonly property bool canSave: AppState.uiLive()
    readonly property var presets: [
        {id: "gideon-escuro", text: "Gideon escuro"}, {id: "gideon-claro", text: "Gideon claro"},
        {id: "alto-contraste", text: "Alto contraste"}, {id: "breeze-escuro", text: "Breeze escuro"},
        {id: "breeze-claro", text: "Breeze claro"}, {id: "catppuccin", text: "Catppuccin"},
        {id: "nord", text: "Nord"}, {id: "daltonismo", text: "Daltonismo-seguro"}
    ]
    readonly property var accents: [{name: "Azul", color: "#7693ff"}, {name: "Violeta", color: "#b386ff"}, {name: "Ciano", color: "#66dcf4"}, {name: "Rosa", color: "#f28bd7"}]

    function set(key, value) { if (!AppState.uiSet(key, value)) AppState.toast("Configurações do app indisponíveis: nada foi salvo.") }

    PageHeader {
        title: "Aparência"
        subtitle: "Tema e cor de destaque desta janela, com prévia imediata."
    }
    Banner {
        visible: !page.canSave
        kind: "warn"
        text: "Configurações do app indisponíveis nesta execução: o tema não é salvo."
    }

    Section {
        title: "Tema"
        Flow {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Repeater {
                model: page.presets
                delegate: Rectangle {
                    id: tile
                    required property var modelData
                    objectName: "preset_" + modelData.id
                    width: 150; height: 64
                    radius: Theme.radius
                    color: AppState.uiGet("theme.preset", "gideon-escuro") === modelData.id ? Theme.tint : (tileMouse.containsMouse ? Theme.hover : Theme.bg)
                    border.width: AppState.uiGet("theme.preset", "gideon-escuro") === modelData.id ? 2 : 1
                    border.color: AppState.uiGet("theme.preset", "gideon-escuro") === modelData.id ? Theme.accent : Theme.strongOutline
                    activeFocusOnTab: true
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: modelData.text
                    Accessible.checked: AppState.uiGet("theme.preset", "gideon-escuro") === modelData.id
                    Keys.onSpacePressed: page.set("theme.preset", modelData.id)
                    Text {
                        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                        anchors.margins: Theme.space(10)
                        text: tile.modelData.text
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontHelp
                        elide: Text.ElideRight
                    }
                    MouseArea { id: tileMouse; anchors.fill: parent; hoverEnabled: true; onClicked: page.set("theme.preset", tile.modelData.id) }
                }
            }
        }
        FieldLabel { text: "Modo" }
        Segmented {
            objectName: "modeChoice"
            model: [{id: "system", text: "Sistema"}, {id: "dark", text: "Escuro"}, {id: "light", text: "Claro"}]
            currentId: String(AppState.uiGet("theme.mode", "dark"))
            onActivated: function (id) { page.set("theme.mode", id) }
        }
    }

    Section {
        title: "Cor de destaque e forma"
        FieldLabel { text: "Cor de destaque" }
        Flow {
            Layout.fillWidth: true
            spacing: Theme.space(10)
            Repeater {
                model: page.accents
                delegate: GButton {
                    required property var modelData
                    objectName: "accent" + modelData.name
                    text: modelData.name
                    variant: String(AppState.uiGet("theme.accent", "#7693ff")).toLowerCase() === modelData.color ? "primary" : "secondary"
                    Accessible.name: "Cor de destaque " + modelData.name
                    onClicked: page.set("theme.accent", modelData.color)
                }
            }
        }
        FieldLabel { text: "Densidade" }
        Segmented {
            objectName: "densityChoice"
            model: [{id: "compact", text: "Compacta"}, {id: "normal", text: "Normal"}, {id: "spacious", text: "Espaçosa"}]
            currentId: AppState.uiGet("theme.density", 1.0) <= 0.92 ? "compact" : AppState.uiGet("theme.density", 1.0) >= 1.1 ? "spacious" : "normal"
            onActivated: function (id) { page.set("theme.density", id === "compact" ? 0.9 : id === "spacious" ? 1.15 : 1.0) }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(24)
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: "Raio dos cantos: " + Math.round(radiusSlider.value) + " px" }
                GSlider { id: radiusSlider; objectName: "radiusSlider"; from: 0; to: 16; stepSize: 1; value: Number(AppState.uiGet("theme.radius", 10)); Layout.fillWidth: true; onMoved: page.set("theme.radius", Math.round(value)); Accessible.name: "Raio dos cantos" }
            }
            ColumnLayout {
                Layout.fillWidth: true
                FieldLabel { text: "Tamanho da fonte: " + Math.round(fontSlider.value) + " px" }
                GSlider { id: fontSlider; objectName: "fontSizeSlider"; from: 12; to: 20; stepSize: 1; value: Number(AppState.uiGet("theme.fontSize", 14)); Layout.fillWidth: true; onMoved: page.set("theme.fontSize", Math.round(value)); Accessible.name: "Tamanho da fonte" }
            }
        }
    }

    Section {
        title: "Prévia e esfera"
        // Live preview: the controls below use the theme as it is now. Nothing is saved from here.
        Card {
            title: "Exemplo de cartão"
            Text { text: "Texto de apoio no tamanho escolhido."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            RowLayout {
                spacing: Theme.space(10)
                GButton { variant: "primary"; text: "Salvar"; enabled: false }
                GButton { variant: "secondary"; text: "Cancelar"; enabled: false }
            }
        }
        Toggle {
            id: visualPagePreference
            objectName: "visualPagePreference"
            text: "Mostrar esfera e indicador de atividade"
            checked: core.visualFeedback
            enabled: core.preferencesAvailable
            onToggled: core.saveFeedback(checked, core.outputVolume)
        }
        Text { text: "O indicador é salvo pelo Core. A esfera é só visual: estado textual, legendas e Cancelar continuam disponíveis."; textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        SettingRow {
            label: "Tamanho da esfera"
            help: "Pequena ou média, no cabeçalho e em Hoje."
            settingKey: "theme.orbSize"
            disabledReason: page.canSave ? "" : "configurações do app indisponíveis"
            Segmented {
                model: [{id: "small", text: "Pequena"}, {id: "medium", text: "Média"}]
                currentId: String(AppState.uiGet("theme.orbSize", "small"))
                onActivated: function (id) { page.set("theme.orbSize", id) }
            }
        }
    }

    Collapsible {
        title: "Mais opções de aparência"
        summary: "Animações, contraste e fonte. Todas com restaurar padrão."
        SettingRow {
            label: "Animações"
            help: "Desligadas, reduzidas ou normais. Com desligadas, a esfera fica parada."
            settingKey: "theme.animation"
            disabledReason: page.canSave ? "" : "configurações do app indisponíveis"
            Segmented {
                model: [{id: "off", text: "Desligadas"}, {id: "reduced", text: "Reduzidas"}, {id: "normal", text: "Normais"}]
                currentId: String(AppState.uiGet("theme.animation", "normal"))
                onActivated: function (id) { page.set("theme.animation", id) }
            }
        }
        SettingRow {
            label: "Contraste alto"
            help: "Bordas e textos mais fortes em todos os temas."
            settingKey: "theme.contrast"
            disabledReason: page.canSave ? "" : "configurações do app indisponíveis"
            Toggle {
                checked: AppState.uiGet("theme.contrast", "normal") === "high"
                onToggled: page.set("theme.contrast", checked ? "high" : "normal")
            }
        }
    }
}
