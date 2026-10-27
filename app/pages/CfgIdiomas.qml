import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/CfgSettings.js" as CS

// Configurações > Idiomas (Frente 2 de docs/PLANO_FRASES_IDIOMAS.md): em que idiomas a IA fala (TTS) e entende (STT).
// Só idioma instalado pode ser escolhido. Português e francês aparecem como "não instalado", com tamanho, licença e motivo.
// Nada é baixado daqui: o Core só verifica e ativa modelos que já vêm no pacote (hash). Idiomas extras seguem sem download. A troca vale na próxima fala.
// WP-20: a primeira seção escolhe o idioma da própria interface; a troca vale na hora (preference ui_language, sem reiniciar).
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
    // The catalog labels are Core data (Portuguese); the three languages get their names in the interface language here.
    readonly property var sttNamed: named(sttItems)
    readonly property var ttsNamed: named(ttsItems)
    function langName(item) {
        if (item.id === "en") return qsTr("Inglês")
        if (item.id === "fr") return qsTr("Francês")
        return item.label
    }
    function named(list) {
        return list.map(function (item) { var copy = Object.assign({}, item); copy.label = langName(item); return copy })
    }
    readonly property var savedStt: core.languageSttSelected
    readonly property string savedTts: core.languageTtsSelected
    readonly property string savedVoice: core.languageTtsVoice
    readonly property var shownStt: draftStt !== null ? draftStt : savedStt
    readonly property string shownTts: draftTts !== "" ? draftTts : savedTts
    readonly property string shownVoice: draftVoice !== "" ? draftVoice : savedVoice
    readonly property bool dirty: JSON.stringify(shownStt) !== JSON.stringify(savedStt) || shownTts !== savedTts
    readonly property bool sttCountOk: shownStt.length >= 1 && shownStt.length <= 3
    readonly property bool restartNeeded: core.languageRestartStt || core.languageRestartTts

    // WP-20 interface language. The names are written in their own language (endonyms), so they never translate.
    readonly property var uiLanguageOptions: [
        {id: "pt-BR", text: "Português (Brasil)"},
        {id: "en", text: "English"},
        {id: "fr", text: "Français"}
    ]
    readonly property int uiLanguageIndex: Math.max(0, uiLanguageOptions.findIndex(function (o) { return o.id === core.uiLanguage }))

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

    // Word for the badge and the detail line (the state comes from the catalog).
    function stateText(item) {
        if (item.state === "bundled") return qsTr("Instalado")
        if (item.state === "available_not_installed") return qsTr("Não instalado")
        return qsTr("Não suportado")
    }
    function stateTone(item) {
        if (item.state === "bundled") return "success"
        if (item.state === "available_not_installed") return "neutral"
        return "warning"
    }
    function sizeText(item) {
        if (item.size_bytes === null || item.size_bytes === undefined) return CS.catalogFact(item.size_note) || qsTr("tamanho não informado")
        var mb = Math.round(item.size_bytes / 1000000)
        return (item.size_partial ? qsTr("cerca de %1 MB (parcial)") : qsTr("cerca de %1 MB")).arg(mb)
    }
    function detailText(item) {
        var parts = [qsTr("Tamanho: %1").arg(sizeText(item)), qsTr("Licença: %1").arg(CS.catalogFact(item.license) || qsTr("não informada")),
                     qsTr("Qualidade: %1").arg(CS.catalogFact(item.quality))]
        if (item.reason) parts.push(CS.catalogFact(item.reason))
        return parts.join(" · ")
    }

    PageHeader {
        title: qsTr("Idiomas")
        subtitle: qsTr("Em que idiomas a IA fala e entende. Só idiomas instalados podem ser escolhidos.")
        GButton {
            objectName: "applyLanguagesButton"
            variant: "primary"
            text: qsTr("Aplicar")
            Accessible.name: qsTr("Aplicar a escolha de idiomas")
            enabled: page.dirty && page.sttCountOk
            onClicked: page.apply()
        }
    }

    Section {
        title: qsTr("Idioma da interface")
        caption: qsTr("A tela inteira muda na hora. A escolha é salva no Core e vale para este perfil.")
        Select {
            id: uiLanguageSelect
            objectName: "uiLanguageSelect"
            Layout.fillWidth: true
            Layout.maximumWidth: 360
            model: page.uiLanguageOptions
            textRole: "text"
            valueRole: "id"
            currentIndex: page.uiLanguageIndex
            Accessible.name: qsTr("Idioma da interface")
            onActivated: function (index) { core.setUiLanguage(page.uiLanguageOptions[index].id) }
        }
    }

    Text {
        objectName: "languagesRestartNote"
        visible: page.restartNeeded
        Layout.fillWidth: true
        text: qsTr("Idioma salvo. A troca vale na próxima fala, sem reiniciar o Core.")
        wrapMode: Text.WordWrap
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
    }

    Section {
        title: qsTr("A IA entende em…")
        caption: qsTr("Você pode escolher de 1 a 3 idiomas. A transcrição usa o primeiro que casar com a fala.")
        Text {
            objectName: "sttCountText"
            visible: !page.sttCountOk
            text: qsTr("Escolha de 1 a 3 idiomas para entender a fala.")
            color: Theme.error
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
        }
        Repeater {
            model: page.sttNamed
            delegate: ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Theme.space(2)
                GCheckbox {
                    objectName: "sttLanguage_" + modelData.id
                    text: modelData.label
                    checked: page.shownStt.indexOf(modelData.id) >= 0
                    enabled: modelData.selectable
                    Accessible.name: qsTr("Entender em %1").arg(modelData.label)
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
                    text: qsTr("Instalar")
                    enabled: false
                    Accessible.name: qsTr("Instalar %1: %2").arg(modelData.label).arg(core.languageInstallReason)
                }
                // CFG-03: pacotes que já vêm no Gideon (português e francês) são conferidos pelo hash e ativados no Core.
                GButton {
                    objectName: "verifyLanguage_" + modelData.id
                    visible: modelData.state === "bundled" && modelData.id !== "en"
                    Layout.leftMargin: Theme.space(26)
                    text: qsTr("Verificar e ativar")
                    enabled: core.languagesAvailable
                    Accessible.name: qsTr("Verificar e ativar os modelos de %1 no Core").arg(modelData.label)
                    onClicked: core.installLanguage(modelData.id)
                }
            }
        }
    }

    Section {
        title: qsTr("A IA fala em…")
        caption: qsTr("Uma voz por vez. Idioma não instalado não aparece como escolha ativa.")
        Repeater {
            model: page.ttsNamed
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
                    Accessible.name: qsTr("Falar em %1").arg(modelData.label)
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
                    text: qsTr("Instalar")
                    enabled: false
                    Accessible.name: qsTr("Instalar voz em %1: %2").arg(modelData.label).arg(core.languageInstallReason)
                }
            }
        }
    }

    Section {
        title: qsTr("Frase de despertar em português e francês")
        caption: qsTr("Como o Gideon é acordado em cada idioma.")
        Text {
            objectName: "wakeLanguageText"
            Layout.fillWidth: true
            text: qsTr("Em português e francês, a frase de despertar é \"Hey Gideon\" (o detector de palavra-chave é o inglês, e a frase funciona com ele) e também vale o atalho global de pressionar para falar. Despertar por transcrição em português e francês: não ativado; precisa de gravações da sua voz. Medido: 11 de 14 frases no laboratório limpo, 6 de 14 pelo áudio do sistema, 1 falso disparo com ruído de webcam a 5 dB; a meta era 80% com zero falso disparo. Para ativar, grave a sua voz com a frase em cada idioma: as medições com voz sintética não bastam para decidir.")
            wrapMode: Text.WordWrap
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
        }
    }

    Text {
        objectName: "installReasonText"
        Layout.fillWidth: true
        text: qsTr("%1 Os idiomas incluídos são verificados pelo hash antes de serem ativados.").arg(core.languageInstallReason)
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontCaption
    }

    Text {
        objectName: "uiLanguageNote"
        Layout.fillWidth: true
        text: qsTr("O idioma da interface vale na hora. Os idiomas da fala e da transcrição são escolhidos nas seções acima.")
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontCaption
    }
}
