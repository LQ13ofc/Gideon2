import QtQuick
import "../theme"

// One line that says how long the history is kept. It reads the Core preference `history_retention` (Privacidade);
// the choice is changed there, never here.
Text {
    readonly property string value: core.historyRetention
    readonly property var labels: ({"days_7": "7 dias", "days_30": "30 dias", "days_90": "90 dias"})
    text: value === "never"
        ? "Histórico não é guardado: a configuração em Privacidade está em \"Não guardar\"."
        : (labels[value] ? "Histórico guardado por " + labels[value] + " (configuração em Privacidade)."
                         : "Prazo do histórico indisponível: confira Privacidade.")
    textFormat: Text.PlainText
    color: Theme.textMuted
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontHelp
    wrapMode: Text.WordWrap
}
