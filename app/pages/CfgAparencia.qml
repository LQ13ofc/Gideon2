import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/CfgSettings.js" as CS

// Configurações > Aparência. The basic part is the preset gallery, the accent colour, the mode, shape and text, with a live
// preview beside it. Everything else is under "Personalizar": the colour of each role with its contrast, animation and
// surface options (advanced), and the theme file import and export. Each choice applies at once to this window.
PageFrame {
    id: page
    objectName: "page_cfg_aparencia"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_aparencia"

    readonly property bool wide: width >= 900
    readonly property bool advancedOn: AppState.uiGet("behavior.advanced", false) === true
    readonly property var presetOptions: AppState.uiSpec("theme.preset") ? AppState.uiSpec("theme.preset").options : []
    readonly property real textMin: Theme.highContrast ? 7 : 4.5
    readonly property var roleRows: CS.themeRoles.map(function (role) { return { role: role } })
    readonly property var pairRows: [
        { label: qsTr("Texto sobre fundo"), fg: "text", bg: "bg", min: textMin },
        { label: qsTr("Texto sobre superfície"), fg: "text", bg: "surface", min: textMin },
        { label: qsTr("Texto secundário / superfície"), fg: "textMuted", bg: "surface", min: textMin },
        { label: qsTr("Texto sobre destaque"), fg: "onAccent", bg: "accent", min: textMin },
        { label: qsTr("Destaque sobre fundo"), fg: "accent", bg: "bg", min: 3 },
        { label: qsTr("Contorno sobre superfície"), fg: "outline", bg: "surface", min: 3 },
        { label: qsTr("Erro como texto"), fg: "error", bg: "bg", min: textMin }
    ]

    // Contrast ratio of a pair of roles, as the settings object measures it (ui.contrast).
    function contrastOf(fg, bg) {
        if (typeof ui === "undefined" || !ui) return 0
        return ui.contrast(Theme.token(fg), Theme.token(bg))
    }
    // True when any theme.* setting differs from its default (enables "Restaurar padrão do tema").
    function themeChanged() {
        var keys = AppState.modifiedKeys()
        for (var i = 0; i < keys.length; i++) if (String(keys[i]).indexOf("theme.") === 0) return true
        return false
    }
    function resetTheme() {
        var keys = AppState.modifiedKeys().slice()
        for (var i = 0; i < keys.length; i++) if (String(keys[i]).indexOf("theme.") === 0) AppState.resetSetting(keys[i])
    }

    PageHeader {
        title: qsTr("Aparência")
        subtitle: qsTr("Tema e cor de destaque, com prévia ao vivo.")
    }
    ECfgSearch {}
    ECfgNotice {}

    GridLayout {
        Layout.fillWidth: true
        columns: page.wide ? 2 : 1
        columnSpacing: Theme.space(32)
        rowSpacing: Theme.space(24)

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: Theme.space(24)

            Section {
                title: qsTr("Tema")
                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    Repeater {
                        model: page.presetOptions
                        delegate: EPresetTile {
                            required property var modelData
                            objectName: "preset_" + modelData.value
                            presetId: modelData.value
                            presetLabel: modelData.label
                            selected: String(AppState.uiGet("theme.preset", "gideon-escuro")) === modelData.value
                            onChosen: function (id) { AppState.setSetting("theme.preset", id) }
                        }
                    }
                }
                FieldLabel { text: qsTr("Modo") }
                ESegmentSetting {
                    objectName: "modeChoice"
                    settingKey: "theme.mode"
                    options: [{ id: "system", text: qsTr("Sistema") }, { id: "dark", text: qsTr("Escuro") }, { id: "light", text: qsTr("Claro") }]
                }
            }

            Section {
                title: qsTr("Cor de destaque")
                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.space(6)
                    Repeater {
                        model: [
                            { value: "", label: qsTr("Padrão do tema"), name: "accentPadrao" },
                            { value: "#7693ff", label: qsTr("Azul"), name: "accentAzul" },
                            { value: "#b386ff", label: qsTr("Violeta"), name: "accentVioleta" },
                            { value: "#66dcf4", label: qsTr("Ciano"), name: "accentCiano" },
                            { value: "#f28bd7", label: qsTr("Rosa"), name: "accentRosa" }
                        ]
                        delegate: EAccentDot {
                            required property var modelData
                            objectName: modelData.name
                            colorValue: modelData.value
                            label: modelData.label
                            selected: String(AppState.uiGet("theme.accent", "")).toLowerCase() === modelData.value
                            onChosen: AppState.setSetting("theme.accent", modelData.value)
                        }
                    }
                }
            }

            Section {
                title: qsTr("Forma e texto")
                SettingRow {
                    settingKey: "theme.density"
                    ESegmentSetting {
                        objectName: "densityChoice"
                        settingKey: "theme.density"
                        options: [{ id: "compact", text: qsTr("Compacta"), value: 0.9 }, { id: "normal", text: qsTr("Normal"), value: 1.0 }, { id: "spacious", text: qsTr("Espaçosa"), value: 1.15 }]
                    }
                }
                SettingRow {
                    settingKey: "theme.radius"
                    ESliderSetting { objectName: "radiusSlider"; settingKey: "theme.radius"; from: 0; to: 16; stepSize: 1; unit: " px" }
                }
                SettingRow {
                    settingKey: "theme.fontSize"
                    ESliderSetting { objectName: "fontSizeSlider"; settingKey: "theme.fontSize"; from: 12; to: 20; stepSize: 1; unit: " px" }
                }
                SettingRow {
                    settingKey: "theme.fontFamily"
                    ESelectSetting { settingKey: "theme.fontFamily" }
                }
                SettingRow {
                    settingKey: "theme.contrast"
                    ESegmentSetting {
                        settingKey: "theme.contrast"
                        options: [{ id: "normal", text: qsTr("Normal") }, { id: "high", text: qsTr("Alto contraste") }]
                    }
                }
            }

            Section {
                title: qsTr("Presença")
                SettingRow {
                    settingKey: "theme.orb"
                    EToggleSetting { settingKey: "theme.orb" }
                }
                SettingRow {
                    settingKey: "core.visualFeedback"
                    EToggleSetting { objectName: "visualPagePreference"; settingKey: "core.visualFeedback" }
                }
                SettingRow {
                    settingKey: "theme.orbSize"
                    ESegmentSetting {
                        settingKey: "theme.orbSize"
                        options: [{ id: "small", text: qsTr("Pequeno") }, { id: "medium", text: qsTr("Médio") }]
                    }
                }
            }
        }

        ColumnLayout {
            Layout.alignment: Qt.AlignTop
            Layout.fillWidth: true
            Layout.preferredWidth: page.wide ? 340 : -1
            EPreviewCard {}
        }
    }

    Collapsible {
        objectName: "customizeBlock"
        title: qsTr("Personalizar")
        summary: qsTr("Cores por papel, contraste dos pares, animação, sombra e arquivo do tema.")
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space(24)

            ColumnLayout {
                visible: page.advancedOn
                Layout.fillWidth: true
                spacing: Theme.space(24)

                Section {
                    title: qsTr("Cores por papel")
                    Text {
                        text: qsTr("Cada cor é conferida com o fundo onde aparece. Hex inválido é recusado; uma cor que precisa de correção mostra a correção antes de valer.")
                        textFormat: Text.PlainText
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontHelp
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: page.wide ? 2 : 1
                        columnSpacing: Theme.space(32)
                        rowSpacing: Theme.space(12)
                        Repeater {
                            model: page.roleRows
                            delegate: EColorRole {
                                required property var modelData
                                role: modelData.role
                                roleLabel: CS.roleLabel(modelData.role)
                            }
                        }
                    }
                }

                Section {
                    title: qsTr("Contraste dos pares")
                    Text {
                        text: qsTr("Mínimo: texto %1 · contornos e destaques 3:1.").arg(CS.ratioText(page.textMin))
                        textFormat: Text.PlainText
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontHelp
                        Layout.fillWidth: true
                    }
                    Repeater {
                        model: page.pairRows
                        delegate: RowLayout {
                            required property var modelData
                            readonly property real ratio: page.contrastOf(modelData.fg, modelData.bg)
                            Layout.fillWidth: true
                            spacing: Theme.space(12)
                            Text {
                                text: modelData.label
                                textFormat: Text.PlainText
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontBody
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Text {
                                text: CS.ratioText(ratio)
                                textFormat: Text.PlainText
                                color: Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontBody
                                font.weight: 600
                                Layout.preferredWidth: 72
                                horizontalAlignment: Text.AlignRight
                            }
                            Badge {
                                text: ratio >= modelData.min ? qsTr("OK") : qsTr("Abaixo")
                                tone: ratio >= modelData.min ? "success" : "error"
                            }
                        }
                    }
                }

                Section {
                    title: qsTr("Animação, translucidez e sombra")
                    SettingRow {
                        settingKey: "theme.animation"
                        ESegmentSetting {
                            settingKey: "theme.animation"
                            options: [{ id: "off", text: qsTr("Desligada") }, { id: "reduced", text: qsTr("Reduzida") }, { id: "normal", text: qsTr("Normal") }]
                        }
                    }
                    SettingRow {
                        settingKey: "theme.translucency"
                        ESliderSetting { settingKey: "theme.translucency"; from: 0; to: 24; stepSize: 1; unit: " px"; zeroText: qsTr("Desligada") }
                    }
                    SettingRow {
                        settingKey: "theme.shadow"
                        ESliderSetting { settingKey: "theme.shadow"; from: 0; to: 100; stepSize: 5; unit: "%" }
                    }
                    SettingRow {
                        settingKey: "theme.titleWeight"
                        ESliderSetting { settingKey: "theme.titleWeight"; from: 500; to: 800; stepSize: 50 }
                    }
                    SettingRow {
                        settingKey: "theme.lineHeight"
                        ESliderSetting { settingKey: "theme.lineHeight"; from: 1.2; to: 1.8; stepSize: 0.05; decimals: 2 }
                    }
                }
            }

            Section {
                title: qsTr("Tema em arquivo")
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    GButton {
                        objectName: "exportThemeButton"
                        variant: "secondary"
                        text: qsTr("Exportar tema…")
                        onClicked: themeExport.open()
                    }
                    GButton {
                        objectName: "importThemeButton"
                        variant: "secondary"
                        text: qsTr("Importar tema…")
                        onClicked: themeImport.open()
                    }
                    GButton {
                        objectName: "resetThemeButton"
                        variant: "ghost"
                        text: qsTr("Restaurar padrão do tema")
                        enabled: page.themeChanged()
                        onClicked: page.resetTheme()
                    }
                }
                Text {
                    text: qsTr("Arquivo JSON versionado, validado ao importar. Exporta e importa todas as opções do app.")
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }
    }

    EAdvancedNote { subtab: "Aparência" }

    Collapsible {
        title: qsTr("Como funciona")
        summary: qsTr("Tema e cor são da janela. A esfera é a única escolha desta aba que o Core guarda hoje.")
        Text {
            text: qsTr("Tema, cor de destaque e forma são da janela e valem na hora. Contraste é checado nos pares de texto e de contorno: um valor que não atende é corrigido e a correção é mostrada antes de valer.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    EJsonDialog {
        id: themeExport
        objectName: "themeExportDialog"
        mode: "export"
    }
    EJsonDialog {
        id: themeImport
        objectName: "themeImportDialog"
        mode: "import"
    }
}
