import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Permissões > Memória: the facts the user allowed the Gideon to keep, by source, with a time limit, search, edit
// and deletion. Every change goes to the Core as a versioned request with the current revision (compare-and-set).
PageFrame {
    id: page
    objectName: "memoriaPage"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "memoria"

    readonly property var personal: core.personal || ({})
    readonly property var mem: personal.memory || ({})
    readonly property var consent: mem.consent || ({})
    readonly property var facts: mem.facts || []
    readonly property bool ready: core.personalAvailable === true && mem.revision !== undefined
    readonly property int revision: ready ? mem.revision : 0
    readonly property var reply: core.personalReply || ({})
    // Search results arrive as the reply of the last `search` request; a null means "show the stored facts".
    readonly property var hits: (reply.area === "memory" && reply.reply && reply.reply.hits) ? reply.reply.hits : null
    readonly property var kindOptions: [
        {value: "fact", label: "Fato"}, {value: "decision", label: "Decisão"},
        {value: "preference", label: "Preferência"}, {value: "context", label: "Contexto"}
    ]
    readonly property var ttlOptions: [
        {value: 0, label: "Sem prazo"}, {value: 7, label: "7 dias"}, {value: 30, label: "30 dias"}, {value: 365, label: "1 ano"}
    ]
    readonly property var kindLabels: ({fact: "Fato", decision: "Decisão", preference: "Preferência", context: "Contexto"})
    readonly property var sourceLabels: ({user_typed: "digitado por você", conversation: "conversa"})
    readonly property bool historyNever: core.historyRetention === "never"
    property string pendingSource: ""
    property string pendingFactId: ""

    function send(payload) {
        core.personalOp("memory", JSON.stringify(Object.assign({version: 1}, payload)))
    }
    function factCount(source) {
        var n = 0
        for (var i = 0; i < facts.length; i++) if (facts[i].source === source) n++
        return n
    }
    function setConsent(source, granted) {
        // Turning a source off deletes what it stored, so the user confirms first.
        if (!granted && factCount(source) > 0) {
            pendingSource = source
            revokeConfirm.open()
            return
        }
        send({op: "consent", revision: revision, source: source, granted: granted})
    }
    function when(ms) {
        return ms ? Qt.formatDateTime(new Date(ms), "dd/MM/yyyy HH:mm") : ""
    }
    function detailOf(fact) {
        var parts = []
        if (fact.kind) parts.push(kindLabels[fact.kind] || fact.kind)
        if (fact.source) parts.push("fonte: " + (sourceLabels[fact.source] || fact.source))
        if (fact.expires_ms) parts.push("expira em " + when(fact.expires_ms))
        return parts.join(" · ")
    }

    PageHeader {
        title: "Memória"
        subtitle: "Fatos que você autorizou o Gideon a guardar, com fonte, prazo e exclusão."
        GButton {
            objectName: "memoryRefresh"
            variant: "secondary"
            text: "Atualizar"
            enabled: core.connected
            onClicked: core.refresh()
        }
    }

    Text {
        visible: !page.ready
        text: "Indisponível: o Core não respondeu à memória. Os controles voltam quando a conexão for restabelecida."
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    Section {
        title: "Fontes autorizadas"
        caption: "Cada fonte só guarda fatos depois que você liga. Desligar apaga os fatos dessa fonte."

        Toggle {
            id: userTypedToggle
            objectName: "consentUserTyped"
            text: "Fatos que eu digitar ou confirmar"
            checked: page.consent.user_typed === true
            enabled: page.ready
            onToggled: {
                page.setConsent("user_typed", checked)
                checked = Qt.binding(function () { return page.consent.user_typed === true })
            }
        }
        Toggle {
            id: conversationToggle
            objectName: "consentConversation"
            text: "Fatos tirados das conversas"
            checked: page.consent.conversation === true
            enabled: page.ready && !page.historyNever
            onToggled: {
                page.setConsent("conversation", checked)
                checked = Qt.binding(function () { return page.consent.conversation === true })
            }
        }
        Text {
            visible: page.historyNever
            text: "Indisponível: o histórico de conversas não é guardado (Privacidade). Fatos das conversas dependem dele."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        PRetentionNote {
            Layout.fillWidth: true
        }
    }

    Section {
        title: "Guardar um fato"
        caption: "O fato fica com a fonte \"digitado por você\". Você pode editar ou apagar a qualquer momento."

        FieldLabel { text: "Texto do fato" }
        GTextField {
            id: newText
            objectName: "memoryNewText"
            Layout.fillWidth: true
            placeholderText: "Ex.: Prefiro reuniões pela manhã"
            maximumLength: 400
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(12)
            ColumnLayout {
                FieldLabel { text: "Tipo" }
                Select {
                    id: kindBox
                    objectName: "memoryKind"
                    textRole: "label"
                    model: page.kindOptions
                    enabled: page.ready
                }
            }
            ColumnLayout {
                FieldLabel { text: "Prazo" }
                Select {
                    id: ttlBox
                    objectName: "memoryTtl"
                    textRole: "label"
                    model: page.ttlOptions
                    enabled: page.ready
                }
            }
            Item { Layout.fillWidth: true }
            GButton {
                objectName: "memoryAdd"
                variant: "primary"
                text: "Guardar fato"
                enabled: page.ready && page.consent.user_typed === true && newText.text.trim().length > 0
                onClicked: {
                    var ttl = page.ttlOptions[ttlBox.currentIndex].value
                    var payload = {
                        op: "add", revision: page.revision, text: newText.text, kind: page.kindOptions[kindBox.currentIndex].value,
                        source: "user_typed"
                    }
                    if (ttl > 0) payload.ttl_days = ttl
                    page.send(payload)
                    newText.text = ""
                }
            }
        }
        PResult { area: "memory" }
    }

    Section {
        title: "Fatos guardados"
        caption: page.hits !== null ? "Resultado da busca no Core." : "Os fatos mais recentes; a busca percorre todos."

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space(8)
            GTextField {
                id: searchText
                objectName: "memorySearch"
                Layout.fillWidth: true
                placeholderText: "Buscar nos fatos"
                onAccepted: page.send({op: "search", query: searchText.text})
            }
            GButton {
                objectName: "memorySearchButton"
                variant: "secondary"
                text: "Buscar"
                enabled: page.ready
                onClicked: page.send({op: "search", query: searchText.text})
            }
            GButton {
                variant: "ghost"
                text: "Mostrar todos"
                enabled: page.ready
                visible: page.hits !== null
                onClicked: {
                    searchText.text = ""
                    page.send({op: "search", query: ""})
                }
            }
        }

        EmptyState {
            visible: (page.hits !== null ? page.hits.length : page.facts.length) === 0
            message: page.hits !== null ? "Nenhum fato corresponde à busca." : "Nenhum fato guardado. Ligue uma fonte e guarde um fato acima."
        }
        Repeater {
            model: page.hits !== null ? page.hits : page.facts
            delegate: PItemRow {
                required property var modelData
                title: modelData.text
                detail: page.detailOf(modelData)
                GButton {
                    objectName: "memoryEdit"
                    variant: "ghost"
                    text: "Editar"
                    visible: modelData.id !== undefined && page.ready
                    onClicked: {
                        editDialog.factId = modelData.id
                        editText.text = modelData.text
                        editDialog.open()
                    }
                }
                GButton {
                    objectName: "memoryForget"
                    variant: "danger"
                    text: "Apagar"
                    enabled: page.ready
                    onClicked: {
                        page.pendingFactId = modelData.id
                        forgetConfirm.open()
                    }
                }
            }
        }
        PResult { area: "memory" }
    }

    Section {
        title: "Apagar dados"
        caption: "Apagar tudo remove os fatos e desliga as fontes. Não é possível desfazer."
        GButton {
            objectName: "memoryForgetAll"
            variant: "danger"
            text: "Apagar toda a memória"
            enabled: page.ready
            onClicked: forgetAllConfirm.open()
        }
    }

    PConfirm {
        id: revokeConfirm
        objectName: "memoryRevokeConfirm"
        message: "Os fatos vindos desta fonte serão apagados e a fonte fica desligada."
        actionText: "Desligar e apagar"
        onConfirmed: page.send({op: "consent", revision: page.revision, source: page.pendingSource, granted: false})
    }
    PConfirm {
        id: forgetConfirm
        message: "Este fato será apagado do Core. Não é possível desfazer."
        actionText: "Apagar fato"
        onConfirmed: page.send({op: "forget", revision: page.revision, id: page.pendingFactId})
    }
    PConfirm {
        id: forgetAllConfirm
        message: "Todos os fatos serão apagados e todas as fontes ficam desligadas."
        actionText: "Apagar tudo"
        onConfirmed: page.send({op: "forget_all", revision: page.revision, confirm: true})
    }

    Modal {
        id: editDialog
        objectName: "memoryEditDialog"
        property string factId: ""
        title: "Editar fato"
        Text {
            text: "Texto do fato"
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
        }
        GTextField {
            id: editText
            objectName: "memoryEditText"
            Layout.fillWidth: true
            maximumLength: 400
        }
        GButton {
            objectName: "memoryEditSave"
            variant: "primary"
            text: "Salvar"
            Layout.alignment: Qt.AlignRight
            onClicked: {
                page.send({op: "edit", revision: page.revision, id: editDialog.factId, text: editText.text})
                editDialog.close()
            }
        }
    }
}
