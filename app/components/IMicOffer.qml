import QtQuick
import QtQuick.Layouts
import "../theme"
import "../shell"

// A13 offer right after the live microphone is turned on (onboarding step 3): the assistant's status while it runs, a note
// when the saved input is fine, and the Banner with "Usar o …" when another input is clean. The Core saves nothing here;
// the button saves the chosen input as Gideon's own preference (the system default never changes).
ColumnLayout {
    id: offer
    objectName: "micOffer"
    Layout.fillWidth: true
    spacing: Theme.space(8)

    readonly property string runState: core.micRecommendation.state

    // Set by the consent ("Ativar escuta"). The assistant runs once the Core has saved the switch on, before the restart.
    property bool armed: false
    Connections {
        target: core
        function onPreferencesChanged() {
            if (offer.armed && core.liveAudioEnabled) {
                offer.armed = false
                core.recommendMicrophones()
            }
        }
    }

    Text {
        objectName: "micOfferStatus"
        visible: text.length > 0
        text: offer.runState === "running" ? qsTr("Verificando os microfones (2 s cada), um de cada vez…")
            : offer.runState === "failed" ? qsTr("Não foi possível verificar os microfones: %1.").arg(core.micRecommendation.error || qsTr("erro desconhecido"))
            : (offer.runState === "done" && core.micRecommendation.currentIsBad === false) ? qsTr("O microfone escolhido está bom: nada a trocar.")
            : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Accessible.name: qsTr("Verificação dos microfones: %1").arg(text)
    }
    Banner {
        objectName: "micOfferBanner"
        kind: "warn"
        text: core.micBanner.text || ""
        actionText: core.micBanner.action || ""
        onActionRequested: core.useAudioInput(core.micBanner.device)
    }
}
