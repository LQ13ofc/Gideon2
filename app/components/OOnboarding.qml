import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../shell"

// First-run guide (docs/PENDENCIAS_IMPLEMENTACAO.md B1): four short steps over the whole window, one card in the middle.
// Pular, Voltar and Próximo (Concluir on the last step). Esc pauses it like Pular; the arrow keys go back and forward.
// It never shows while the Core is offline or a voice session runs (AppState.introBlockReason); it comes back at the same
// step when that clears. Finishing or skipping saves behavior.onboardingDone for this profile.
Item {
    id: intro
    objectName: "onboarding_root"
    anchors.fill: parent
    z: 80
    visible: AppState.onboardingOpen && AppState.uiLive() && AppState.introBlockReason().length === 0
    focus: visible

    property int step: 0
    readonly property int stepCount: 4
    readonly property var titles: [qsTr("Bem-vindo ao Gideon"), qsTr("Frase de despertar"), qsTr("Dispositivos e volume"), qsTr("Atalhos e paleta")]
    // Only certified phrases can be chosen here; the others are listed with the reason they are blocked.
    readonly property var wakeRows: (typeof core !== "undefined" && core && core.wakeChoices) ? core.wakeChoices : []
    readonly property string wakeChosen: String(AppState.uiGet("core.wakePhrase", ""))

    Connections {
        target: AppState
        function onOnboardingOpenChanged() { if (AppState.onboardingOpen) intro.step = 0 }
    }
    onVisibleChanged: if (visible) Qt.callLater(function () { nextButton.forceActiveFocus() })
    onStepChanged: Qt.callLater(function () { nextButton.forceActiveFocus() })

    function next() {
        if (step < stepCount - 1) step += 1
        else finish()
    }
    function back() { if (step > 0) step -= 1 }
    function finish() {
        AppState.setSetting("behavior.onboardingDone", true)
        AppState.onboardingOpen = false
    }

    Keys.onEscapePressed: function (event) { intro.finish(); event.accepted = true }
    Keys.onRightPressed: function (event) { intro.next(); event.accepted = true }
    Keys.onLeftPressed: function (event) { intro.back(); event.accepted = true }

    // Covers the window: clicks and wheel do not reach the pages behind.
    Rectangle {
        anchors.fill: parent
        color: Theme.bg
    }
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onWheel: function (wheel) { wheel.accepted = true }
    }

    Rectangle {
        id: card
        objectName: "onboarding_card"
        anchors.centerIn: parent
        width: Math.min(640, intro.width - 32)
        height: Math.min(intro.height - 32, cardColumn.implicitHeight + Theme.space(40))
        radius: Theme.radiusCard
        color: Theme.surfaceVariant
        border.width: 1
        border.color: Theme.strongOutline

        ColumnLayout {
            id: cardColumn
            anchors.left: parent.left; anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Theme.space(20)
            spacing: Theme.space(14)

            Text {
                objectName: "onboarding_step"
                text: qsTr("Passo %1 de %2").arg(intro.step + 1).arg(intro.stepCount)
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                Layout.fillWidth: true
            }
            Text {
                objectName: "onboarding_title"
                text: intro.titles[intro.step]
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontTitle
                font.weight: Theme.titleWeight
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }

            ScrollView {
                id: stepScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredHeight: Math.min(stepColumns.implicitHeight, Math.max(160, intro.height - 260))
                clip: true
                contentWidth: availableWidth

                StackLayout {
                    id: stepColumns
                    width: stepScroll.availableWidth
                    currentIndex: intro.step

                    // ---- 1. Boas-vindas e privacidade
                    ColumnLayout {
                        objectName: "onboarding_step1"
                        Layout.fillWidth: true
                        spacing: Theme.space(10)
                        IntroText { text: qsTr("O Gideon é um assistente de voz que roda neste computador. Ele fica em espera e responde quando você diz a frase de despertar.") }
                        IntroText { text: qsTr("Privacidade, em resumo:"); strong: true }
                        IntroText { text: qsTr("•  Nada do que você fala é guardado em disco pela interface."); indent: true }
                        IntroText { text: qsTr("•  O áudio fica só em memória durante a captura. Nenhum arquivo de voz é gravado."); indent: true }
                        IntroText { text: qsTr("•  Não há histórico de conversas salvo. A nuvem só recebe conversas com consentimento."); indent: true }
                        IntroText { text: qsTr("•  A entrada é virtual, salvo se você ligar a escuta do microfone (passo 3 ou Dispositivos)."); indent: true }
                    }

                    // ---- 2. Frase de despertar (só certificadas)
                    ColumnLayout {
                        objectName: "onboarding_step2"
                        Layout.fillWidth: true
                        spacing: Theme.space(6)
                        IntroText { text: qsTr("Escolha a frase que acorda o Gideon. Só aparecem frases do pacote com qualificação. A troca vale depois de reiniciar o Core.") }
                        IntroText {
                            visible: intro.wakeRows.length === 0
                            text: qsTr("O pacote não oferece frases de despertar agora.")
                        }
                        Repeater {
                            model: intro.wakeRows
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 2
                                readonly property bool certified: modelData.qualification === "dev_qualified"
                                GRadio {
                                    id: wakeRadio
                                    objectName: "onboarding_wake_" + modelData.id
                                    Layout.fillWidth: true
                                    text: modelData.qualification_label ? qsTr("%1 · %2").arg(modelData.text).arg(modelData.qualification_label) : modelData.text
                                    enabled: certified && AppState.blockReason("core.wakePhrase").length === 0
                                    checked: intro.wakeChosen === modelData.id
                                    onClicked: {
                                        AppState.setSetting("core.wakePhrase", modelData.id)
                                        wakeRadio.checked = Qt.binding(function () { return intro.wakeChosen === modelData.id })
                                    }
                                }
                                IntroText {
                                    visible: !certified
                                    text: qsTr("Indisponível: frase sem qualidade aprovada no pacote.")
                                    small: true
                                }
                            }
                        }
                        IntroText {
                            visible: AppState.blockReason("core.wakePhrase").length > 0
                            text: qsTr("Indisponível agora: %1.").arg(AppState.blockReason("core.wakePhrase"))
                            small: true
                        }
                    }

                    // ---- 3. Dispositivos e volume
                    ColumnLayout {
                        objectName: "onboarding_step3"
                        Layout.fillWidth: true
                        spacing: Theme.space(10)
                        IntroText { text: qsTr("Sem a escuta do microfone, entrada e saída são virtuais. O volume abaixo é o da resposta por voz, não o do sistema.") }
                        IntroText { objectName: "onboarding_input_virtual"; text: qsTr("Entrada: PCM virtual (em uso)"); strong: true }
                        IntroText { objectName: "onboarding_output_virtual"; text: qsTr("Saída: virtual (em uso)"); strong: true }
                        IntroText {
                            objectName: "onboarding_physical_mic"
                            text: qsTr("Microfone: escolha em Configurações › Dispositivos. A lista vem do sistema.")
                            small: true
                        }
                        // A6: optional and off by default. Turning it on asks for consent; the Core listens after its next start.
                        Toggle {
                            id: onboardingLiveSwitch
                            objectName: "onboardingLiveSwitch"
                            Layout.fillWidth: true
                            text: qsTr("Ouvir o microfone (ativação por voz)")
                            Accessible.name: qsTr("Ouvir o microfone para a ativação por voz")
                            checked: core.liveAudioEnabled
                            enabled: core.preferencesAvailable
                            onToggled: {
                                if (checked) liveConsent.open()
                                else core.setLiveAudio(false)
                                checked = Qt.binding(function () { return core.liveAudioEnabled })
                            }
                        }
                        IntroText {
                            objectName: "onboarding_live_note"
                            visible: core.liveAudioEnabled && core.audioLive.enabled !== true
                            text: qsTr("Será ativado ao reiniciar o Core. Enquanto isso, a entrada segue virtual.")
                            small: true
                        }
                        // A13: the assistant runs right after the consent (before the restart) and offers the cleaner microphone.
                        IMicOffer {
                            id: liveOffer
                            visible: core.liveAudioEnabled
                        }
                        IntroText {
                            objectName: "onboarding_physical_out"
                            text: qsTr("Alto-falante: escolha em Configurações › Dispositivos. A troca vale na próxima sessão de voz.")
                            small: true
                        }
                        IntroText { text: qsTr("Volume da resposta por voz"); strong: true }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space(12)
                            GSlider {
                                id: volumeSlider
                                objectName: "onboarding_volume"
                                Layout.fillWidth: true
                                label: qsTr("Volume da resposta por voz, por cento")
                                from: 0; to: 100; stepSize: 1
                                value: Number(AppState.uiGet("core.responseGain", 100))
                                enabled: AppState.blockReason("core.responseGain").length === 0
                                onMoved: AppState.setSetting("core.responseGain", Math.round(volumeSlider.value))
                            }
                            Text {
                                text: Math.round(volumeSlider.value) + " %"
                                textFormat: Text.PlainText
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontBody
                                Layout.preferredWidth: 56
                            }
                        }
                        IntroText {
                            visible: AppState.blockReason("core.responseGain").length > 0
                            text: qsTr("Indisponível agora: %1.").arg(AppState.blockReason("core.responseGain"))
                            small: true
                        }
                    }

                    // ---- 4. Atalhos e paleta
                    ColumnLayout {
                        objectName: "onboarding_step4"
                        Layout.fillWidth: true
                        spacing: Theme.space(10)
                        IntroText { text: qsTr("Estes atalhos valem em todas as telas. Eles podem ser desligados em Configurações › Geral.") }
                        Repeater {
                            model: [
                                {keys: "Ctrl+K", text: qsTr("Abre a paleta: vá a páginas, configurações e comandos.")},
                                {keys: "Ctrl+1 a Ctrl+5", text: qsTr("Troca de aba (Assistente, Extensões, Permissões, Configurações, Diagnóstico).")},
                                {keys: "Ctrl+Tab", text: qsTr("Próxima sub-aba. Ctrl+Shift+Tab volta.")},
                                {keys: "Ctrl+M", text: qsTr("Encerra a escuta quando ela está ativa.")},
                                {keys: "Esc", text: qsTr("Cancela a escuta ou fecha a janela aberta.")}
                            ]
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: Theme.space(12)
                                KeyCap {
                                    keys: modelData.keys
                                    Layout.preferredWidth: 150
                                }
                                Text {
                                    text: modelData.text
                                    textFormat: Text.PlainText
                                    color: Theme.text
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontHelp
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                        }
                        IntroText { text: qsTr("Dica: Ctrl+K também acha configurações pelo nome."); small: true }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(10)
                GButton {
                    objectName: "onboarding_skip"
                    variant: "ghost"
                    text: qsTr("Pular")
                    Accessible.description: qsTr("Fecha a introdução e não a mostra de novo")
                    onClicked: intro.finish()
                }
                Item { Layout.fillWidth: true }
                GButton {
                    objectName: "onboarding_back"
                    variant: "secondary"
                    text: qsTr("Voltar")
                    enabled: intro.step > 0
                    onClicked: intro.back()
                }
                GButton {
                    id: nextButton
                    objectName: "onboarding_next"
                    variant: "primary"
                    text: intro.step === intro.stepCount - 1 ? qsTr("Concluir") : qsTr("Próximo")
                    onClicked: intro.next()
                }
            }
        }
    }

    // Consent of the optional microphone switch on step 3 (same text and focus rules as Dispositivos).
    LiveAudioConsent {
        id: liveConsent
        onAgreed: { core.setLiveAudio(true); liveOffer.armed = true }
    }

    // Plain paragraph of the guide (13 or 14 px, wrapped). `strong` is the bold lead, `indent` the bullet line.
    component IntroText: Text {
        property bool strong: false
        property bool small: false
        property bool indent: false
        textFormat: Text.PlainText
        color: small ? Theme.textMuted : Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: small ? Theme.fontHelp : Theme.fontBody
        font.weight: strong ? 600 : 400
        wrapMode: Text.WordWrap
        leftPadding: indent ? Theme.space(12) : 0
        Layout.fillWidth: true
    }
}
