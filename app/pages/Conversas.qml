import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"

// Assistente > Histórico: text conversations kept by the Core for the period set in Privacidade. Audio is never kept.
// Open a conversation to read it, rename it, delete it, or export the text of all of them.
PageFrame {
    id: page
    objectName: "conversasPage"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "conversas"

    readonly property var personal: core.personal || ({})
    readonly property var convBlock: personal.conversations || ({})
    readonly property var sessions: convBlock.sessions || []
    readonly property bool recording: convBlock.recording === true
    readonly property bool ready: core.personalAvailable === true && convBlock.revision !== undefined
    readonly property int revision: ready ? convBlock.revision : 0
    readonly property var reply: core.personalReply || ({})
    property string selectedId: ""
    property bool exporting: false
    property string pendingId: ""

    // The opened conversation: the reply of the last `get` for the selected id.
    readonly property var openSession: (reply.area === "conversations" && reply.reply && reply.reply.session
        && reply.reply.session.id === selectedId) ? reply.reply.session : null
    // The export: the reply of the last `export` request made from this page.
    readonly property var exported: (reply.area === "conversations" && exporting && reply.reply && reply.reply.sessions)
        ? reply.reply.sessions : null

    function send(payload) {
        core.personalOp("conversations", JSON.stringify(Object.assign({version: 1}, payload)))
    }
    function when(ms) {
        return ms ? Qt.formatDateTime(new Date(ms), "dd/MM/yyyy HH:mm") : ""
    }
    function openConversation(id) {
        selectedId = id
        exporting = false
        send({op: "get", session_id: id})
    }

    PageHeader {
        title: "Histórico"
        subtitle: "Conversas em texto guardadas pelo prazo escolhido. Áudio nunca é guardado."
        GButton {
            objectName: "conversasExport"
            variant: "secondary"
            text: "Exportar textos"
            enabled: page.ready
            onClicked: {
                page.exporting = true
                page.selectedId = ""
                page.send({op: "export"})
            }
        }
        GButton {
            objectName: "conversasForgetAll"
            variant: "danger"
            text: "Apagar todo o histórico"
            enabled: page.ready && page.sessions.length > 0
            onClicked: forgetAllConfirm.open()
        }
    }

    Text {
        visible: !page.ready
        text: "Indisponível: o Core não respondeu ao histórico. Os controles voltam quando a conexão for restabelecida."
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    Section {
        title: "Conversas"
        caption: "Mais recentes primeiro. Mostramos até 50 aqui."
        PRetentionNote {
            Layout.fillWidth: true
        }
        EmptyState {
            visible: page.sessions.length === 0
            message: page.recording
                ? "Nenhuma conversa guardada ainda. Use a aba Conversa para começar uma."
                : "O histórico não é guardado. Mude o prazo em Privacidade para guardar conversas."
        }
        Repeater {
            model: page.sessions
            delegate: PItemRow {
                required property var modelData
                title: modelData.title
                detail: modelData.turns + (modelData.turns === 1 ? " mensagem" : " mensagens")
                    + " · atualizada em " + page.when(modelData.updated_ms)
                GButton {
                    objectName: "conversaOpen"
                    variant: "secondary"
                    text: "Abrir"
                    enabled: page.ready
                    onClicked: page.openConversation(modelData.id)
                }
                GButton {
                    objectName: "conversaRename"
                    variant: "ghost"
                    text: "Renomear"
                    enabled: page.ready
                    onClicked: {
                        page.pendingId = modelData.id
                        renameText.text = modelData.title
                        renameDialog.open()
                    }
                }
                GButton {
                    objectName: "conversaDelete"
                    variant: "danger"
                    text: "Apagar"
                    enabled: page.ready
                    onClicked: {
                        page.pendingId = modelData.id
                        deleteConfirm.open()
                    }
                }
            }
        }
        PResult { area: "conversations" }
    }

    Section {
        visible: page.openSession !== null
        title: page.openSession !== null ? page.openSession.title : ""
        caption: "Conversa aberta. Somente leitura."
        Repeater {
            model: page.openSession !== null ? page.openSession.turns : []
            delegate: ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Theme.space(2)
                Text {
                    text: modelData.role === "user" ? "Você · " + page.when(modelData.at_ms) : "Gideon · " + page.when(modelData.at_ms)
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                    Layout.fillWidth: true
                }
                Text {
                    text: modelData.text
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }
        GButton {
            objectName: "conversaClose"
            variant: "ghost"
            text: "Fechar conversa"
            onClicked: page.selectedId = ""
        }
    }

    Section {
        visible: page.exported !== null
        title: "Textos exportados"
        caption: "Copie o texto abaixo para guardar um backup. Ele contém suas conversas em texto simples."
        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(320, exportArea.implicitHeight + Theme.space(16))
            clip: true
            TextArea {
                id: exportArea
                objectName: "conversasExportText"
                readOnly: true
                selectByMouse: true
                wrapMode: TextArea.Wrap
                text: page.exported !== null ? JSON.stringify(page.exported, null, 2) : ""
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                background: Rectangle {
                    radius: Theme.radius
                    color: Theme.bg
                    border.width: 1
                    border.color: Theme.strongOutline
                }
            }
        }
    }

    PConfirm {
        id: deleteConfirm
        message: "A conversa será apagada do Core. Não é possível desfazer."
        actionText: "Apagar conversa"
        onConfirmed: {
            if (page.selectedId === page.pendingId) page.selectedId = ""
            page.send({op: "delete", revision: page.revision, session_id: page.pendingId})
        }
    }
    PConfirm {
        id: forgetAllConfirm
        message: "Todas as conversas guardadas serão apagadas. Não é possível desfazer."
        actionText: "Apagar histórico"
        onConfirmed: {
            page.selectedId = ""
            page.send({op: "forget_all", revision: page.revision, confirm: true})
        }
    }

    Modal {
        id: renameDialog
        objectName: "conversaRenameDialog"
        title: "Renomear conversa"
        GTextField {
            id: renameText
            objectName: "conversaRenameText"
            Layout.fillWidth: true
            maximumLength: 80
        }
        GButton {
            objectName: "conversaRenameSave"
            variant: "primary"
            text: "Salvar"
            Layout.alignment: Qt.AlignRight
            onClicked: {
                page.send({op: "rename", revision: page.revision, session_id: page.pendingId, title: renameText.text})
                renameDialog.close()
            }
        }
    }
}
