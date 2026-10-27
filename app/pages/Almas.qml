import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Configurações > Almas: communication profiles the user declares or allows the Gideon to read from their own text.
// A Soul never changes the assistant's identity, authentication or safety rules. Influência suggests a style;
// Simulação is labelled as an imitation of the user's own style. Provenance is shown and cannot be edited.
PageFrame {
    id: page
    objectName: "almasPage"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "almas"

    readonly property var personal: core.personal || ({})
    readonly property var soulsBlock: personal.souls || ({})
    readonly property var souls: soulsBlock.souls || []
    readonly property bool ready: core.personalAvailable === true && soulsBlock.revision !== undefined
    readonly property int revision: ready ? soulsBlock.revision : 0
    readonly property var reply: core.personalReply || ({})
    readonly property var preview: (reply.area === "souls" && reply.reply && reply.reply.guidance) ? reply.reply : null
    readonly property var modeOptions: [{id: "influence", text: qsTr("Influência")}, {id: "simulation", text: qsTr("Simulação")}]
    readonly property var provenanceOptions: [
        {id: "declared", text: qsTr("Declarada por mim")},
        {id: "inferred_from_chat", text: qsTr("Inferida das minhas mensagens")},
        {id: "user_documents", text: qsTr("De documentos meus")}
    ]
    readonly property var provenanceLabels: ({
        declared: qsTr("declarada por você"),
        inferred_from_chat: qsTr("inferida das suas mensagens (confiança até 0,8)"),
        user_documents: qsTr("de documentos seus (confiança até 0,8)")
    })
    property string mode: "influence"
    property string provenance: "declared"
    property string pendingId: ""
    property string activeId: soulsBlock.active || ""

    function send(payload) {
        core.personalOp("souls", JSON.stringify(Object.assign({version: 1}, payload)))
    }
    function splitList(text) {
        return text.split(",").map(function (s) { return s.trim() }).filter(function (s) { return s.length > 0 }).slice(0, 5)
    }

    PageHeader {
        title: qsTr("Almas")
        subtitle: qsTr("Estilo de comunicação que você declara. Não muda a identidade nem a segurança do assistente.")
    }

    Text {
        visible: !page.ready
        text: qsTr("Indisponível: o Core não respondeu às almas. Os controles voltam quando a conexão for restabelecida.")
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    Section {
        title: qsTr("Suas almas")
        caption: page.activeId.length > 0 ? qsTr("Uma alma ativa por vez.") : qsTr("Nenhuma alma ativa.")

        EmptyState {
            visible: page.souls.length === 0
            message: qsTr("Nenhuma alma criada. Crie uma abaixo: ela fica guardada até você apagar.")
        }
        Repeater {
            model: page.souls
            delegate: PItemRow {
                required property var modelData
                title: modelData.name
                detail: qsTr("%1 · %2 · %3").arg(modelData.description).arg(modelData.mode_label)
                    .arg(page.provenanceLabels[modelData.provenance.kind] || modelData.provenance.kind)
                badgeText: modelData.active ? qsTr("Ativa") : ""
                badgeTone: "success"
                GButton {
                    objectName: "soulActivate"
                    variant: modelData.active ? "ghost" : "secondary"
                    text: modelData.active ? qsTr("Desativar") : qsTr("Usar")
                    enabled: page.ready
                    onClicked: modelData.active
                        ? page.send({op: "deactivate", revision: page.revision})
                        : page.send({op: "activate", revision: page.revision, id: modelData.id})
                }
                GButton {
                    objectName: "soulPreview"
                    variant: "ghost"
                    text: qsTr("Prévia")
                    enabled: page.ready
                    onClicked: page.send({op: "preview", id: modelData.id})
                }
                GButton {
                    objectName: "soulDelete"
                    variant: "danger"
                    text: qsTr("Apagar")
                    enabled: page.ready
                    onClicked: {
                        page.pendingId = modelData.id
                        deleteConfirm.open()
                    }
                }
            }
        }
        ColumnLayout {
            visible: page.preview !== null
            Layout.fillWidth: true
            spacing: Theme.space(4)
            Text {
                objectName: "soulPreviewLabel"
                text: page.preview !== null ? page.preview.label + " · " + page.preview.mode_label : ""
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.weight: 600
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                text: page.preview !== null ? page.preview.guidance : ""
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                text: page.preview !== null ? page.preview.note : ""
                textFormat: Text.PlainText
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        Text {
            text: qsTr("Sem plugin LLM, a alma ativa não altera as respostas: ela só fica disponível como dica para o motor LLM.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        PResult { area: "souls" }
    }

    Section {
        title: qsTr("Nova alma")
        caption: qsTr("Modo e origem ficam visíveis em cada alma. Origem não pode ser trocada depois de criada.")

        FieldLabel { text: qsTr("Nome") }
        GTextField {
            id: nameField
            objectName: "soulName"
            Layout.fillWidth: true
            maximumLength: 40
            placeholderText: qsTr("Ex.: Calmo")
        }
        FieldLabel { text: qsTr("Descrição") }
        GTextField {
            id: descField
            objectName: "soulDescription"
            Layout.fillWidth: true
            maximumLength: 280
            placeholderText: qsTr("Para que você usa esta alma")
        }
        FieldLabel { text: qsTr("Estilo") }
        GTextField {
            id: styleField
            objectName: "soulStyle"
            Layout.fillWidth: true
            maximumLength: 280
            placeholderText: qsTr("Ex.: frases curtas, sem rodeios")
        }
        FieldLabel { text: qsTr("Prioridades (separadas por vírgula, até 5)") }
        GTextField {
            id: prioField
            objectName: "soulPriorities"
            Layout.fillWidth: true
            maximumLength: 200
            placeholderText: qsTr("Ex.: clareza, segurança")
        }
        FieldLabel { text: qsTr("Modo") }
        Segmented {
            objectName: "soulMode"
            model: page.modeOptions
            currentId: page.mode
            onActivated: function (id) { page.mode = id }
        }
        Text {
            text: page.mode === "simulation"
                ? qsTr("Simulação: o texto é rotulado como imitação do seu estilo, nunca como você.")
                : qsTr("Influência: sugere um estilo; quem decide a resposta continua sendo o assistente.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        FieldLabel { text: qsTr("Origem") }
        Segmented {
            objectName: "soulProvenance"
            model: page.provenanceOptions
            currentId: page.provenance
            onActivated: function (id) { page.provenance = id }
        }
        FieldLabel {
            visible: page.provenance !== "declared"
            text: qsTr("Evidência (onde isso aparece no seu texto; obrigatório)")
        }
        GTextField {
            id: evidenceField
            objectName: "soulEvidence"
            visible: page.provenance !== "declared"
            Layout.fillWidth: true
            maximumLength: 120
            placeholderText: qsTr("Ex.: mensagens de março sobre o projeto")
        }
        GCheckbox {
            id: docsConsent
            objectName: "soulDocsConsent"
            visible: page.provenance === "user_documents"
            text: qsTr("Autorizo o Gideon a ler os documentos citados acima para montar esta alma.")
        }
        GButton {
            objectName: "soulCreate"
            variant: "primary"
            text: qsTr("Criar alma")
            enabled: page.ready && nameField.text.trim().length > 0 && descField.text.trim().length > 0
                && styleField.text.trim().length > 0
            onClicked: {
                var evidence = page.provenance === "declared" ? [] : [evidenceField.text.trim()]
                var confidence = page.provenance === "declared" ? 1.0 : 0.6
                page.send({
                    op: "create", revision: page.revision, name: nameField.text, description: descField.text,
                    style: styleField.text, priorities: page.splitList(prioField.text), mode: page.mode,
                    provenance: {kind: page.provenance, evidence: evidence, confidence: confidence},
                    consent_documents: docsConsent.checked
                })
                nameField.text = ""
                descField.text = ""
                styleField.text = ""
                prioField.text = ""
                evidenceField.text = ""
                docsConsent.checked = false
            }
        }
        Text {
            visible: page.provenance !== "declared"
            text: qsTr("Origem: %1").arg(page.provenanceLabels[page.provenance] || "")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    PConfirm {
        id: deleteConfirm
        message: qsTr("A alma será apagada. Se ela estiver ativa, nenhuma alma fica ativa.")
        actionText: qsTr("Apagar alma")
        onConfirmed: page.send({op: "delete", revision: page.revision, id: page.pendingId})
    }
}
