import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../shell"
import "../shell/Labels.js" as L

// Extensões > Plugins (was the Gideon Hub dialog and the plugin panel). Installing copies a verified package and runs
// nothing; approving permissions does not install or run; enabling runs the plugin in its sandbox.
PageFrame {
    id: page
    objectName: "pluginsPage"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "plugins"

    property var reviewPlugin: AppState.reviewPlugin
    function approvalDone() {
        if (!AppState.reviewPlugin) return false
        var e = L.hubEntry(core.hubEntries, AppState.reviewPlugin.plugin_id)
        return !!e && e.manifest_sha256 === AppState.reviewPlugin.manifest_sha256 && e.permissions_approved === true
    }

    PageHeader {
        title: "Plugins"
        subtitle: "Instale e ative plugins verificados. Instalar não executa nada e não concede acesso."
    }
    Banner {
        objectName: "hubBanner"
        kind: "info"
        text: core.hubDescription
    }

    Section {
        title: "Catálogo"
        Text {
            objectName: "hubImportDescription"
            text: core.hubImportDescription
            visible: core.hubImportActive
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GButton {
            objectName: "abortHubImportButton"
            visible: core.hubImportActive
            enabled: core.hubImportActive
            text: "Cancelar importação"
            variant: "secondary"
            onClicked: core.abortHubImport()
        }
        Repeater {
            model: core.hubEntries
            delegate: Card {
                required property var modelData
                Text {
                    objectName: "hubEntry_" + modelData.plugin_id
                    text: modelData.plugin_id + " " + modelData.semver + " · " + (modelData.status === "installed" ? "instalado" : modelData.status === "update_available" ? "atualização disponível" : modelData.status === "not_installed" ? "não instalado" : "incompatível: " + modelData.reason) + " · " + (modelData.permissions_approved ? "permissões aprovadas" : "permissões não aprovadas")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    objectName: "status_" + modelData.plugin_id
                    text: (modelData.status === "installed" ? (L.pluginEnabledFor(core.pluginItems, modelData.plugin_id) ? "Instalado · ativo (sandbox, sem rede)" : "Instalado · desativado (sem execução)") : modelData.status === "update_available" ? "Atualização disponível" : modelData.status === "not_installed" ? (modelData.payload_staged ? "Pacote verificado em staging; não instalado" : "Não instalado") : "Incompatível: " + modelData.reason) + " · " + modelData.license
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    text: (modelData.permissions_approved ? "Permissões aprovadas para este manifesto: " : "Permissões declaradas (não aprovadas): ") + (modelData.permissions.map(function (p) { return core.permissionLabel(p) }).join(", ") || "nenhuma") + "\n" + modelData.support_policy
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    Item { Layout.fillWidth: true }
                    GButton {
                        objectName: "review_" + modelData.plugin_id
                        text: modelData.permissions_approved ? "Permissões aprovadas" : "Revisar permissões"
                        variant: "secondary"
                        Accessible.name: (modelData.permissions_approved ? "Permissões aprovadas de " : "Revisar permissões de ") + modelData.plugin_id
                        enabled: core.hubApprovalAvailable && (modelData.status === "not_installed" || modelData.status === "update_available" || modelData.status === "installed") && !modelData.permissions_approved
                        onClicked: { AppState.reviewPlugin = modelData; reviewAck.checked = false; reviewDialog.open() }
                    }
                    GButton {
                        objectName: "install_" + modelData.plugin_id
                        visible: modelData.status === "not_installed" || modelData.status === "update_available"
                        text: "Instalar pacote verificado"
                        variant: "primary"
                        Accessible.name: "Instalar pacote verificado de " + modelData.plugin_id
                        enabled: core.hubLifecycleAvailable && modelData.payload_staged === true && modelData.permissions_approved === true && (modelData.status === "not_installed" || modelData.status === "update_available")
                        onClicked: core.installHub(modelData.plugin_id, modelData.manifest_sha256)
                    }
                }
            }
        }
        EmptyState {
            visible: core.hubEntries.length === 0
            iconName: "hub"
            message: "Nenhum plugin no catálogo ainda. Conecte o Core para carregar o catálogo local."
        }
        Text {
            text: "Instalar copia o pacote verificado para o Core; nada é executado. O catálogo não concede acesso ao computador."
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    Section {
        title: "Instalados no Core"
        visible: core.hubInstalled.length > 0
        Repeater {
            model: core.hubInstalled
            delegate: Card {
                required property var modelData
                Text {
                    text: modelData.plugin_id + " " + modelData.semver + " · " + (modelData.state === "quarantined" ? "Em quarentena" : L.pluginEnabledFor(core.pluginItems, modelData.plugin_id) ? "Instalado · ativo" : "Instalado · desativado (sem execução)")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    Item { Layout.fillWidth: true }
                    GButton {
                        objectName: "rollback_" + modelData.plugin_id
                        text: "Reverter versão"
                        variant: "secondary"
                        Accessible.name: "Reverter versão de " + modelData.plugin_id
                        enabled: core.hubLifecycleAvailable && !!modelData.previous && modelData.state === "installed"
                        onClicked: core.rollbackHub(modelData.plugin_id)
                    }
                    GButton {
                        objectName: "remove_" + modelData.plugin_id
                        text: "Remover plugin"
                        variant: "danger"
                        Accessible.name: "Remover " + modelData.plugin_id
                        enabled: core.hubLifecycleAvailable
                        onClicked: { removeConfirm.plugin = modelData; removeConfirm.revision = core.hubInstallRevision; removeConfirm.open() }
                    }
                }
            }
        }
    }
    Text {
        objectName: "hubLifecycleResult"
        visible: text.length > 0
        text: core.hubApprovalResult
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    // Plugins known to the Core: state, capabilities, enable and disable, and the capability test (developer use).
    Section {
        title: "Plugins no Core"
        visible: core.pluginItems.length > 0
        Repeater {
            model: core.pluginItems
            delegate: Card {
                id: pluginCard
                required property var modelData
                readonly property string pid: modelData.plugin_id
                Text {
                    objectName: "pluginStatus_" + pluginCard.pid
                    text: pluginCard.pid + " " + modelData.semver + " · " + L.pluginStateText(modelData)
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: 600
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    text: "Capacidades: " + (modelData.capabilities.length ? modelData.capabilities.join(", ") : "nenhuma")
                    textFormat: Text.PlainText
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    objectName: "reapprovalHint_" + pluginCard.pid
                    visible: L.pluginInstalled(core.hubEntries, pluginCard.pid) && !L.pluginApproved(core.hubEntries, pluginCard.pid)
                    text: "Aprove novamente as permissões para ativar"
                    textFormat: Text.PlainText
                    color: Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontHelp
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    GButton {
                        objectName: "enable_" + pluginCard.pid
                        text: "Ativar"
                        variant: "primary"
                        Accessible.name: "Ativar " + pluginCard.pid
                        enabled: core.pluginsAvailable && L.pluginCanEnable(core.hubEntries, modelData)
                        onClicked: core.enablePlugin(pluginCard.pid)
                    }
                    GButton {
                        objectName: "disable_" + pluginCard.pid
                        text: "Desativar"
                        variant: "secondary"
                        Accessible.name: "Desativar " + pluginCard.pid
                        enabled: core.pluginsAvailable && modelData.enabled === true
                        onClicked: core.disablePlugin(pluginCard.pid)
                    }
                    Item { Layout.fillWidth: true }
                    GButton {
                        objectName: "revoke_" + pluginCard.pid
                        text: "Revogar permissões"
                        variant: "danger"
                        Accessible.name: "Revogar permissões de " + pluginCard.pid
                        enabled: core.pluginsAvailable && modelData.state !== "quarantined"
                        onClicked: { revokeConfirm.plugin = modelData; revokeConfirm.revision = core.pluginsRevision; revokeConfirm.open() }
                    }
                }
                GTextField {
                    id: capabilityInput
                    objectName: "capabilityInput_" + pluginCard.pid
                    placeholderText: "Texto para a capability"
                    Accessible.name: "Texto para a capability de " + pluginCard.pid
                    maximumLength: 256
                    enabled: core.pluginsAvailable && modelData.state === "running"
                    Layout.fillWidth: true
                    Component.onCompleted: text = AppState.draftValue(pluginCard.pid, "text")
                    onTextEdited: AppState.setDraft(pluginCard.pid, "text", text)
                }
                Repeater {
                    model: modelData.capabilities
                    delegate: RowLayout {
                        required property var modelData
                        readonly property string capName: modelData
                        Layout.fillWidth: true
                        spacing: Theme.space(10)
                        GButton {
                            objectName: "invoke_" + capName
                            text: "Invocar"
                            variant: "secondary"
                            Accessible.name: "Invocar " + capName
                            enabled: core.pluginsAvailable && pluginCard.modelData.state === "running"
                            onClicked: { AppState.setDraft(pluginCard.pid, "capability", capName); core.invokeCapability(capName, capabilityInput.text) }
                        }
                        GButton {
                            objectName: "cancelCapability_" + pluginCard.pid
                            text: "Cancelar"
                            variant: "secondary"
                            Accessible.name: "Cancelar capability " + capName
                            enabled: core.pluginsAvailable && AppState.draftValue(pluginCard.pid, "capability") === capName
                            onClicked: core.cancelCapability(capName)
                        }
                    }
                }
            }
        }
    }
    Text {
        objectName: "pluginLifecycleResult"
        visible: text.length > 0
        text: core.pluginResult
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        objectName: "capabilityResult"
        visible: text.length > 0
        text: core.capabilityResultText
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    // Confirmations: Cancelar is the focused default; the explicit button is the only way to accept.
    Modal {
        id: removeConfirm
        objectName: "removeConfirm"
        property var plugin: null
        property string revision: ""
        title: "Remover plugin"
        onAccepted: { if (plugin) core.removeHub(plugin.plugin_id, revision) }
        Text {
            text: removeConfirm.plugin ? "Remover " + removeConfirm.plugin.plugin_id + " " + removeConfirm.plugin.semver + " do Core? Nada é executado e o catálogo não muda." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmRemoveButton"; variant: "danger"; text: "Remover"
            Layout.alignment: Qt.AlignRight
            Accessible.name: removeConfirm.plugin ? "Remover " + removeConfirm.plugin.plugin_id : "Remover"
            onClicked: removeConfirm.accept()
        }
    }
    Modal {
        id: revokeConfirm
        objectName: "revokeConfirm"
        property var plugin: null
        property string revision: ""
        title: "Revogar permissões"
        onAccepted: { if (plugin) core.revokePlugin(plugin.plugin_id, revision) }
        Text {
            text: revokeConfirm.plugin ? "Revogar permissões de " + revokeConfirm.plugin.plugin_id + "? O plugin será desativado e o processo encerrado. Reativar exige nova aprovação." : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmRevokeButton"; variant: "danger"; text: "Revogar"
            Layout.alignment: Qt.AlignRight
            Accessible.name: revokeConfirm.plugin ? "Revogar permissões de " + revokeConfirm.plugin.plugin_id : "Revogar"
            onClicked: revokeConfirm.accept()
        }
    }
    // Review: the approval target is captured when the dialog opens; the bridge refuses it if the live record changed.
    Modal {
        id: reviewDialog
        objectName: "hubReviewDialog"
        closeOnly: true
        title: "Revisar permissões"
        onOpened: { core.beginHubReview(); AppState.reviewRevision = core.hubApprovalRevision }
        Text {
            text: AppState.reviewPlugin ? AppState.reviewPlugin.plugin_id + " " + AppState.reviewPlugin.semver + " · " + AppState.reviewPlugin.publisher : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: AppState.reviewPlugin ? "Permissões: " + (AppState.reviewPlugin.permissions.join(", ") || "nenhuma") : ""
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Text {
            text: "Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto."
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GCheckbox {
            id: reviewAck
            objectName: "publisherAcknowledgement"
            text: "Entendo que o publisher não foi autenticado"
            enabled: core.hubApprovalAvailable
        }
        GButton {
            objectName: "approveHubButton"
            variant: "primary"
            text: "Aprovar estas permissões"
            Layout.fillWidth: true
            Accessible.name: AppState.reviewPlugin ? "Aprovar permissões de " + AppState.reviewPlugin.plugin_id : "Aprovar permissões"
            enabled: core.hubApprovalAvailable && reviewAck.checked && AppState.reviewPlugin !== null && !page.approvalDone()
            onClicked: core.approveHub(AppState.reviewPlugin.plugin_id, AppState.reviewPlugin.manifest_sha256, AppState.reviewPlugin.permissions, reviewAck.checked, AppState.reviewRevision)
        }
        Text {
            objectName: "hubApprovalResult"
            text: core.hubApprovalResult
            textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
    }
}
