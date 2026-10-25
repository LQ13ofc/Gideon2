import QtQuick
import QtQuick.Layouts
import "../theme"

// Live preview of the theme as it is now: a sample card with text, buttons and the state colours. Nothing is saved from here.
Rectangle {
    id: preview
    Layout.fillWidth: true
    implicitHeight: body.implicitHeight + 2 * Theme.space(20)
    radius: Theme.radiusCard
    color: Theme.surface
    border.width: 1
    border.color: Theme.hairline

    ColumnLayout {
        id: body
        anchors.fill: parent
        anchors.margins: Theme.space(20)
        spacing: Theme.space(14)
        Text {
            text: "Prévia ao vivo"
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            Layout.fillWidth: true
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: sample.implicitHeight + Theme.space(32)
            radius: Theme.radius
            color: Theme.surfaceVariant
            border.width: 1
            border.color: Theme.strongOutline
            ColumnLayout {
                id: sample
                anchors.left: parent.left; anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.margins: Theme.space(16)
                spacing: Theme.space(10)
                Text {
                    text: "Exemplo de cartão"
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSection
                    font.weight: 600
                    Layout.fillWidth: true
                }
                Text {
                    text: "Texto de apoio no tamanho escolhido."
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                // CFG-05: no Salvar/Cancelar here. Every choice of Aparência is saved as it is made, so the preview has nothing to confirm.
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(8)
            Badge { text: "Concluído"; tone: "success" }
            Badge { text: "Atenção"; tone: "warning" }
            Badge { text: "Erro"; tone: "error" }
            Badge { text: "Informação"; tone: "info" }
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 1
            color: Theme.hairline
        }
        Text {
            text: "A prévia não grava nada. Cada escolha já vale nesta janela."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
