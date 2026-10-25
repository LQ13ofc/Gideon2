import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Configurações > Idiomas (Frente 2 de docs/PLANO_FRASES_IDIOMAS.md): em que idiomas a IA fala (TTS) e entende (STT).
// Só idioma instalado pode ser escolhido. Português e francês aparecem como "não instalado", com tamanho, licença e motivo.
// Nada é baixado daqui: a instalação espera a aprovação do dono (botões desativados). A troca vale no próximo início do Core.
PageFrame {
    id: page
    objectName: "page_cfg_idiomas"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "cfg_idiomas"

    // Draft of the choice; null (or "") means the saved value is shown.
    property var draftStt: null
    property string draftTts: ""
    property string draftVoice: ""

    readonly property var sttItems: core.languageSttItems
    readonly property var ttsItems: core.languageTtsItems
    readonly property var savedStt: core.languageSttSelected
    readonly property string savedTts: core.languageTtsSelected
    readonly property string savedVoice: core.languageTtsVoice
    readonly property var shownStt: draftStt !== null ? draftStt : savedStt
    readonly property string shownTts: draftTts !== "" ? draftTts : savedTts
    readonly property string shownVoice: draftVoice !== "" ? draftVoice : savedVoice
    readonly property bool dirty: JSON.stringify(shownStt) !== JSON.stringify(savedStt) || shownTts !== savedTts
    readonly property bool sttCountOk: shownStt.length >= 1 && shownStt.length <= 3
    readonly property bool restartNeeded: core.languageRestartStt || core.languageRestartTts

    // One voice at a time: the TTS radios share this group across their delegates.
    ButtonGroup { id: ttsGroup; exclusive: true }

    // A new saved choice from the Core replaces the draft.
    onSavedSttChanged: draftStt = null
    onSavedTtsChanged: draftTts = ""

    function toggleStt(id, on) {
        var list = shownStt.slice()
        var at = list.indexOf(id)
        if (on && at < 0) list.push(id)
        if (!on && at >= 0) list.splice(at, 1)
        draftStt = list
    }

    // The voice follows the language: the first voice the catalog lists for it.
    function chooseTts(item) {
        draftTts = item.id
        draftVoice = item.voices.length > 0 ? item.voices[0] : ""
    }

    function apply() {
        if (!dirty || !sttCountOk) return
        core.setLanguages(JSON.stringify(shownStt), shownTts, shownVoice)
    }

    // Portuguese state word for the badge and the detail line.
    function stateText(item) {
        if (item.state === "bundled") return "Instalado"
        if (item.state === "available_not_installed") return "Não instalado"
        return "Não suportado"
    }
    function stateTone(item) {
        if (item.state === "bundled") return "success"
        if (item.state === "available_not_installed") return "neutral"
        return "warning"
    }
    function sizeText(item) {
        if (item.size_bytes === null || item.size_bytes === undefined) return item.size_note || "tamanho não informado"
        var mb = Math.round(item.size_bytes / 1000000)
        return "cerca de " + mb + " MB" + (item.size_partial ? " (parcial)" : "")
    }
    function detailText(item) {
        var parts = ["Tamanho: " + sizeText(item), "Licença: " + (item.license || "não informada"),
                     "Qualidade: " + item.quality]
        if (item.reason) parts.push(item.reason)
        return parts.join(" · ")
    }

    PageHeader {
        title: "Idiomas"
        subtitle: "Em que idiomas a IA fala e entende. Só idiomas instalados podem ser escolhidos."
        GButton {
            objectName: "applyLanguagesButton"
            variant: "primary"
            text: "Aplicar"
            Accessible.name: "Aplicar a escolha de idiomas"
            enabled: page.dirty && page.sttCountOk
            onClicked: page.apply()
        }
    }

    Text {
        objectName: "languagesRestartNote"
        visible: page.restartNeeded
        Layout.fillWidth: true
        text: "Idioma salvo. Reinicie o Core para aplicar."
        wrapMode: Text.WordWrap
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
    }

    Section {
        title: "A IA entende em…"
        caption: "Você pode escolher de 1 a 3 idiomas. A transcrição usa o primeiro que casar com a fala."
        Text {
            objectName: "sttCountText"
            visible: !page.sttCountOk
            text: "Escolha de 1 a 3 idiomas para entender a fala."
            color: Theme.error
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
        }
        Repeater {
            model: page.sttItems
            delegate: ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Theme.space(2)
                GCheckbox {
                    objectName: "sttLanguage_" + modelData.id
                    text: modelData.label
                    checked: page.shownStt.indexOf(modelData.id) >= 0
                    enabled: modelData.selectable
                    Accessible.name: "Entender em " + modelData.label
                    onClicked: page.toggleStt(modelData.id, checked)
                }
                Text {
                    objectName: "sttDetail_" + modelData.id
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.space(26)
                    text: stateText(modelData) + " · " + page.detailText(modelData)
                    wrapMode: Text.WordWrap
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                }
                GButton {
                    objectName: "installStt_" + modelData.id
                    visible: modelData.state === "available_not_installed"
                    Layout.leftMargin: Theme.space(26)
                    text: "Instalar"
                    enabled: false
                    Accessible.name: "Instalar " + modelData.label + ": " + core.languageInstallReason
                }
            }
        }
    }

    Section {
        title: "A IA fala em…"
        caption: "Uma voz por vez. Idioma não instalado não aparece como escolha ativa."
        Repeater {
            model: page.ttsItems
            delegate: ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Theme.space(2)
                GRadio {
                    objectName: "ttsLanguage_" + modelData.id
                    ButtonGroup.group: ttsGroup
                    text: modelData.label
                    checked: page.shownTts === modelData.id
                    enabled: modelData.selectable
                    Accessible.name: "Falar em " + modelData.label
                    onClicked: page.chooseTts(modelData)
                }
                Text {
                    objectName: "ttsDetail_" + modelData.id
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.space(26)
                    text: stateText(modelData) + " · " + page.detailText(modelData)
                    wrapMode: Text.WordWrap
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                }
                GButton {
                    objectName: "installTts_" + modelData.id
                    visible: modelData.state === "available_not_installed"
                    Layout.leftMargin: Theme.space(26)
                    text: "Instalar"
                    enabled: false
                    Accessible.name: "Instalar voz em " + modelData.label + ": " + core.languageInstallReason
                }
            }
        }
    }

    Text {
        objectName: "installReasonText"
        Layout.fillWidth: true
        text: core.languageInstallReason + ". Os idiomas que aparecem como não instalados ainda não têm arquivos neste pacote."
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontCaption
    }

    Text {
        objectName: "uiLanguageNote"
        Layout.fillWidth: true
        text: "O idioma da interface é outra configuração e continua em português."
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontCaption
    }
}
