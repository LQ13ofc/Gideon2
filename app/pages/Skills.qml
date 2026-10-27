import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"
import "../components"
import "../components/BExt.js" as X
import "../shell"
import "../shell/Labels.js" as L

// Extensões > Skills (B02). Four segments: Minhas (a list of 56 px rows with the drawer on the right), Criar,
// Importar/Exportar and Execuções. Every value is the Core snapshot 'skills' block. Nothing here grants a permission.
PageFrame {
    id: page
    objectName: "skillsPanel"
    anchors.fill: parent
    visible: Window.window && Window.window.pageId === "skills" && core.skillsAvailable

    property string part: "minhas"
    property string selectedKey: ""
    readonly property bool runActive: L.skillRunActive(core.skillCurrentRun)

    // Entradas (JSON de objeto, até 16 KiB): a local value, checked here before Simular and Executar.
    function inputsValid(text) {
        if (text.length > 16384) return false
        try {
            var v = JSON.parse(text)
            return v !== null && typeof v === "object" && !Array.isArray(v)
        } catch (e) { return false }
    }
    readonly property bool inputsOk: inputsValid(skillInputs.text)
    readonly property var ctx: ({
        skillsAvailable: core.skillsAvailable,
        busy: core.skillsBusy,
        runActive: page.runActive,
        inputsOk: page.inputsOk,
        inputs: skillInputs.text,
        blockedText: core.connected ? qsTr("Indisponível agora.") : qsTr("Core desconectado: nada pode ser alterado agora.")
    })
    readonly property var exportables: {
        var out = []
        var items = core.skillsItems
        for (var i = 0; i < items.length; i++) if (X.exportable(items[i].state)) out.push(items[i])
        return out
    }
    readonly property var selectedSkill: {
        var items = core.skillsItems
        for (var i = 0; i < items.length; i++) if (items[i].id + "_" + items[i].version === page.selectedKey) return items[i]
        return null
    }
    readonly property string summary: {
        var items = core.skillsItems
        var enabled = 0
        var drafts = 0
        for (var i = 0; i < items.length; i++) {
            if (items[i].state === "enabled") enabled++
            if (items[i].state === "draft" || items[i].state === "validated") drafts++
        }
        return qsTr("%1 · %2 · %3").arg(page.countText(items.length, qsTr("%1 instalada"), qsTr("%1 instaladas")))
            .arg(page.countText(enabled, qsTr("%1 habilitada"), qsTr("%1 habilitadas")))
            .arg(page.countText(drafts, qsTr("%1 rascunho"), qsTr("%1 rascunhos")))
    }

    // "1 pacote" or "3 pacotes": the singular and plural texts are chosen by the count.
    function countText(n, one, many) { return (n === 1 ? one : many).arg(n) }
    function permissionText(p) {
        var label = core.permissionLabel(p)
        return label === p ? qsTr("permissão sem rótulo: %1").arg(p) : label
    }
    function labelsOf(list) {
        return (list || []).length ? list.map(function (p) { return page.permissionText(p) }).join(", ") : qsTr("nenhuma")
    }
    function askRemove(skill) { removeSkillConfirm.skill = skill; removeSkillConfirm.open() }
    // Write-only clipboard for the folder paths the Core reports (skills.paths). Nothing is read or executed.
    function copyFolder(path, label) {
        if (path && core.copyText(path)) AppState.toast(qsTr("Pasta copiada."))
        else AppState.toast(qsTr("Não foi possível copiar a pasta %1.").arg(label))
    }

    PageHeader {
        title: qsTr("Skills")
        subtitle: qsTr("Procedimentos que combinam capacidades instaladas. Nada aqui concede permissões.")
        GButton {
            objectName: "skillNewButton"
            text: qsTr("Nova skill")
            variant: "primary"
            Accessible.name: qsTr("Nova skill: abrir o segmento Criar")
            onClicked: page.part = "criar"
        }
    }
    Text {
        objectName: "skillsSummary"
        text: page.summary
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        font.weight: 600
        Layout.fillWidth: true
    }
    Text {
        objectName: "skillsResult"
        visible: text.length > 0
        text: core.skillsResult
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Accessible.name: qsTr("Resultado das skills: %1").arg(text)
    }
    GProgressBar {
        objectName: "skillsProgress"
        visible: core.skillsBusy
        indeterminate: true
        Layout.fillWidth: true
        Accessible.name: qsTr("Operação de skill em andamento")
    }
    Segmented {
        objectName: "skillParts"
        model: [{id: "minhas", text: qsTr("Minhas")}, {id: "criar", text: qsTr("Criar")}, {id: "importar", text: qsTr("Importar/Exportar")}, {id: "execucoes", text: qsTr("Execuções")}]
        currentId: page.part
        onActivated: function (id) { page.part = id }
    }

    // Minhas: the list of installed skills, the drawer of the picked one, and the JSON inputs for Simular and Executar.
    ColumnLayout {
        visible: page.part === "minhas"
        Layout.fillWidth: true
        spacing: Theme.space(12)

        Collapsible {
            title: qsTr("Como funciona")
            summary: qsTr("Nada aqui concede permissão.")
            Text {
                text: qsTr("Validar não grava. Simular não chama capacidades. Executar pede sua aprovação em cada passo que muda estado.")
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
        }
        Collapsible {
            objectName: "skillInputsBlock"
            title: qsTr("Entradas (JSON)")
            summary: qsTr("Entradas (JSON de objeto, até 16 KiB) para Simular e Executar")
            TextArea {
                id: skillInputs
                objectName: "skillInputs"
                Layout.fillWidth: true
                Layout.preferredHeight: 120
                text: "{}"
                textFormat: TextEdit.PlainText
                wrapMode: TextEdit.Wrap
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                placeholderText: qsTr("{ \"campo\": \"valor\" }")
                placeholderTextColor: Theme.textMuted
                Accessible.name: qsTr("Entradas da skill em JSON")
                background: Rectangle { color: Theme.bg; radius: Theme.radius; border.width: 1; border.color: Theme.strongOutline }
            }
            Text {
                visible: !page.inputsOk
                text: qsTr("Entradas inválidas: use um objeto JSON de até 16 KiB.")
                textFormat: Text.PlainText
                color: Theme.error
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontHelp
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: Theme.space(16)

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: 0
                EmptyState {
                    objectName: "skillsEmpty"
                    visible: core.skillsItems.length === 0
                    iconName: "puzzle"
                    message: qsTr("Nenhuma skill no Core ainda.")
                    actionText: qsTr("Nova skill")
                    onActionRequested: page.part = "criar"
                }
                Repeater {
                    model: core.skillsItems
                    delegate: BSkillRow {
                        required property var modelData
                        skill: modelData
                        ctx: page.ctx
                        selected: (modelData.id + "_" + modelData.version) === page.selectedKey
                        onSelectRequested: page.selectedKey = modelData.id + "_" + modelData.version
                    }
                }
            }

            BSkillDetail {
                visible: page.selectedSkill !== null
                skill: page.selectedSkill
                ctx: page.ctx
                onRemoveRequested: function (s) { page.askRemove(s) }
                onCloseRequested: page.selectedKey = ""
            }
        }
    }

    // Criar: manifest JSON by hand; the LLM only drafts (never enabled here).
    RowLayout {
        visible: page.part === "criar"
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignTop
        spacing: Theme.space(16)

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: Theme.space(10)
            FieldLabel { text: qsTr("Manifesto da skill em JSON") }
            TextArea {
                id: skillManifest
                objectName: "skillManifest"
                Layout.fillWidth: true
                Layout.preferredHeight: 320
                textFormat: TextEdit.PlainText
                wrapMode: TextEdit.Wrap
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                placeholderText: qsTr("Cole o manifesto JSON da skill (até 16 KiB).")
                placeholderTextColor: Theme.textMuted
                Accessible.name: qsTr("Manifesto da skill em JSON")
                background: Rectangle { color: Theme.bg; radius: Theme.radius; border.width: 1; border.color: Theme.strongOutline }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space(10)
                GButton {
                    objectName: "skillValidate"
                    variant: "secondary"
                    text: qsTr("Validar")
                    Accessible.name: qsTr("Validar manifest da skill")
                    enabled: !core.skillsBusy && skillManifest.text.trim().length > 0
                    onClicked: core.skillValidate(skillManifest.text)
                }
                GButton {
                    objectName: "skillSaveDraft"
                    variant: "primary"
                    text: qsTr("Salvar rascunho")
                    Accessible.name: qsTr("Salvar rascunho da skill")
                    enabled: !core.skillsBusy && skillManifest.text.trim().length > 0
                    onClicked: core.skillSaveDraft(skillManifest.text)
                }
                Item { Layout.fillWidth: true }
            }
        }

        ColumnLayout {
            Layout.preferredWidth: 360
            Layout.alignment: Qt.AlignTop
            spacing: Theme.space(12)
            Card {
                title: qsTr("Gerar com LLM")
                FieldLabel { text: qsTr("Descrição da skill para o LLM") }
                GTextField {
                    id: skillDescription
                    objectName: "skillDescription"
                    Layout.fillWidth: true
                    maximumLength: 1024
                    placeholderText: qsTr("Descreva o que a skill deve fazer (até 1024 bytes).")
                    Accessible.name: qsTr("Descrição da skill para o LLM")
                }
                GButton {
                    objectName: "skillDraftWithLlm"
                    variant: "primary"
                    text: qsTr("Gerar com LLM")
                    Accessible.name: qsTr("Gerar skill com o LLM")
                    enabled: core.skillLlmAvailable && !core.skillsBusy && skillDescription.text.trim().length > 0
                    onClicked: core.skillDraftWithLlm(skillDescription.text)
                }
                Text {
                    objectName: "skillLlmUnavailable"
                    visible: !core.skillLlmAvailable
                    text: qsTr("Gerar com LLM indisponível: o plugin llm_engine não está ativo.")
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
                GButton {
                    visible: !core.skillLlmAvailable
                    variant: "ghost"
                    text: qsTr("Instalar em Extensões › Plugins")
                    Accessible.name: qsTr("Instalar em Extensões › Plugins")
                    onClicked: { if (Window.window && Window.window.goPage) Window.window.goPage("plugins") }
                }
                Text {
                    text: qsTr("O rascunho nunca fica habilitado. Você valida, simula e aprova antes de usar.")
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
            }
            Card {
                objectName: "skillDraftOutput"
                visible: !!core.skillDraftOutput.draft_id
                title: visible ? qsTr("Rascunho %1 · v%2 · %3 · nada foi habilitado").arg(core.skillDraftOutput.draft_id).arg(core.skillDraftOutput.version).arg(L.skillStateText(core.skillDraftOutput.state)) : ""
                Text { text: qsTr("Requisitos: %1").arg((core.skillDraftOutput.requirements || []).join(", ") || qsTr("nenhum")); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { text: qsTr("Ambiguidades: %1").arg((core.skillDraftOutput.ambiguities || []).join("; ") || qsTr("nenhuma")); textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { text: qsTr("Passos previstos:\n%1").arg((core.skillDraftOutput.preview || []).map(function (p) { return p.id + " → " + p.call }).join("\n") || qsTr("nenhum")); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { visible: !!core.skillDraftOutput.diff; text: qsTr("Diferença:\n%1").arg(core.skillDraftOutput.diff || ""); textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
            }
        }
    }

    // Importar/Exportar: the Core reads only <home>/skill-imports/<name>.gskill and previews it; nothing installs until confirmed.
    ColumnLayout {
        visible: page.part === "importar"
        Layout.fillWidth: true
        spacing: Theme.space(16)

        // WP-15 / SKILL-03: what the Core reports about packages: the base pack digest, the last export and the
        // listed index (the UI never fetches the index URLs; "baixar" stays off until the owner approves a source).
        Card {
            objectName: "skillPackageCard"
            Layout.fillWidth: true
            title: qsTr("Pacotes e índice")
            Text {
                objectName: "skillPackHash"
                text: qsTr("Hash do pacote base (SHA-256): %1").arg(core.packHash.length > 0 ? core.packHash : qsTr("não informado pelo Core"))
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                Accessible.name: qsTr("Hash do pacote base: %1").arg(core.packHash)
            }
            Text {
                objectName: "skillLastExport"
                text: core.skillLastExport.path
                      ? qsTr("Último pacote exportado: %1 v%2 em %3").arg(core.skillLastExport.id).arg(core.skillLastExport.version).arg(core.skillLastExport.path)
                      : qsTr("Nenhum pacote exportado nesta sessão.")
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
            }
            Text {
                objectName: "skillIndexSummary"
                visible: !!core.skillIndex.repository
                text: core.skillIndex.error
                      ? qsTr("Índice de %1 recusado: %2").arg(core.skillIndex.repository).arg(core.skillIndex.error)
                      : qsTr("Índice de %1: %2.").arg(core.skillIndex.repository).arg(page.countText(core.skillIndex.entries ? core.skillIndex.entries.length : 0, qsTr("%1 pacote listado"), qsTr("%1 pacotes listados")))
                textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Repeater {
                model: core.skillIndex.entries || []
                delegate: Text {
                    required property var modelData
                    objectName: "skillIndexEntry_" + modelData.name
                    text: qsTr("%1 v%2 · SHA-256 %3 · %4 · %5").arg(modelData.name).arg(modelData.version).arg(modelData.sha256)
                          .arg(modelData.signed ? qsTr("assinado") : qsTr("sem assinatura"))
                          .arg(modelData.present ? qsTr("já está na pasta de importação") : qsTr("não baixado (download depende de aprovação)"))
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: Theme.space(16)

            Card {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                title: qsTr("Importar pacote")
                Text {
                    text: qsTr("Coloque o arquivo .gskill na pasta de importação e informe o nome, sem caminho e sem extensão.")
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    Text {
                        objectName: "skillImportFolder"
                        text: qsTr("Pasta: %1").arg(core.skillPaths.imports || qsTr("pasta de importação não informada"))
                        textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                    }
                    GButton {
                        objectName: "skillCopyImportFolder"
                        variant: "secondary"
                        text: qsTr("Copiar")
                        enabled: !!core.skillPaths.imports
                        Accessible.name: qsTr("Copiar a pasta de importação")
                        onClicked: page.copyFolder(core.skillPaths.imports, qsTr("de importação"))
                    }
                }
                FieldLabel { text: qsTr("Nome do pacote, sem caminho") }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    GTextField {
                        id: skillImportName
                        objectName: "skillImportName"
                        Layout.fillWidth: true
                        maximumLength: 64
                        placeholderText: "resumo_semanal"
                        validator: RegularExpressionValidator { regularExpression: /[A-Za-z0-9._-]{1,64}/ }
                        Accessible.name: qsTr("Nome do pacote para importar")
                    }
                    GButton {
                        objectName: "skillImport"
                        variant: "primary"
                        text: qsTr("Pré-visualizar")
                        Accessible.name: qsTr("Pré-visualizar importação de skill")
                        enabled: !core.skillsBusy && skillImportName.acceptableInput
                        onClicked: core.skillImport(skillImportName.text)
                    }
                }
                Text {
                    visible: skillImportName.text.length > 0 && !skillImportName.acceptableInput
                    text: qsTr("Nome inválido: use letras, números, ponto, traço ou sublinhado (até 64).")
                    textFormat: Text.PlainText; color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
            }

            Card {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                title: qsTr("Exportar skill")
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space(10)
                    Text {
                        objectName: "skillExportFolder"
                        text: qsTr("Pasta: %1").arg(core.skillPaths.exports || qsTr("pasta de exportação não informada"))
                        textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                    }
                    GButton {
                        objectName: "skillCopyExportFolder"
                        variant: "secondary"
                        text: qsTr("Copiar")
                        enabled: !!core.skillPaths.exports
                        Accessible.name: qsTr("Copiar a pasta de exportação")
                        onClicked: page.copyFolder(core.skillPaths.exports, qsTr("de exportação"))
                    }
                }
                Text {
                    visible: page.exportables.length === 0
                    text: qsTr("Nenhuma skill exportável. Aprove uma skill em Minhas.")
                    textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
                Repeater {
                    model: page.exportables
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Theme.space(10)
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: modelData.id + " v" + modelData.version
                                textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; elide: Text.ElideRight; Layout.fillWidth: true
                            }
                            Text {
                                text: L.skillStateText(modelData.state)
                                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true
                            }
                        }
                        GButton {
                            objectName: "skillExport_" + modelData.id
                            variant: "secondary"
                            text: qsTr("Exportar")
                            Accessible.name: qsTr("Exportar %1 v%2").arg(modelData.id).arg(modelData.version)
                            enabled: !core.skillsBusy
                            onClicked: core.skillExport(modelData.id, modelData.version)
                        }
                    }
                }
            }
        }

        Card {
            objectName: "skillImportPreview"
            visible: !!core.skillImportPreview.name
            Layout.fillWidth: true
            title: visible ? qsTr("Pacote %1: %2 v%3").arg(core.skillImportPreview.name).arg(core.skillImportPreview.id).arg(core.skillImportPreview.version) : ""
            Text {
                // SKILL-02: the flag is the Core's signature check (src/skills.rs publisher_checks), never a fixed text.
                text: qsTr("Publisher: %1%2").arg(core.skillImportPreview.publisher).arg(core.skillImportPreview.unverified === false ? qsTr(" · assinatura verificada") : qsTr(" · não verificado"))
                textFormat: Text.PlainText; color: core.skillImportPreview.unverified === false ? Theme.success : Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                Accessible.name: qsTr("Publisher %1%2").arg(core.skillImportPreview.publisher).arg(core.skillImportPreview.unverified === false ? qsTr(", assinatura verificada") : qsTr(", não verificado"))
            }
            Text {
                text: qsTr("Permissões exigidas: %1").arg(page.labelsOf(core.skillImportPreview.permissions_required))
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Text {
                text: qsTr("Novas nesta versão: %1").arg(page.labelsOf(core.skillImportPreview.permission_delta))
                textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Text {
                visible: core.skillImportPreview.permissions_escalated === true
                text: qsTr("Escalada de permissões: esta versão pede mais que a anterior; aprove de novo antes de usar.")
                textFormat: Text.PlainText; color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Text {
                text: qsTr("Dependências faltando: %1").arg((core.skillImportPreview.missing_deps || []).join(", ") || qsTr("nenhuma"))
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Text {
                visible: core.skillImportPreview.duplicate === true
                text: qsTr("Já existe uma skill com este id no Core.")
                textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Repeater {
                model: core.skillImportPreview.findings || []
                delegate: Text {
                    required property var modelData
                    objectName: "skillFinding_" + modelData.code
                    text: qsTr("Achado: %1").arg(core.codeMessage(modelData.code)) + (modelData.field ? " (" + modelData.field + ")" : "")
                    textFormat: Text.PlainText; color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
            }
            Text {
                text: qsTr("Importar instala como rascunho e nunca concede permissões. Valide, simule e aprove antes de usar.")
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            GButton {
                id: importConfirm
                objectName: "skillImportConfirm"
                variant: "primary"
                text: qsTr("Instalar como rascunho")
                Accessible.name: qsTr("Instalar como rascunho o pacote %1").arg(core.skillImportPreview.name)
                enabled: !core.skillsBusy && (core.skillImportPreview.findings || []).length === 0 && core.skillImportPreview.duplicate !== true
                onClicked: core.skillImportConfirm(core.skillImportPreview.name)
            }
            Text {
                visible: !importConfirm.enabled && (core.skillImportPreview.findings || []).length > 0
                text: qsTr("Corrija os achados antes de instalar.")
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
        }
        Text {
            visible: !core.skillImportPreview.name
            text: qsTr("Nenhum pacote pré-visualizado.")
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; Layout.fillWidth: true
        }
    }

    // Execuções: the current run; each step that changes state waits for the user's decision here.
    // A run that waits for a decision is shown on any part: the user starts runs from Minhas and must see the step's buttons.
    ColumnLayout {
        visible: page.part === "execucoes" || core.skillCurrentRun.state === "awaiting_approval"
        Layout.fillWidth: true
        spacing: Theme.space(16)

        Card {
            objectName: "skillRunView"
            visible: !!core.skillCurrentRun.run_id
            Layout.fillWidth: true
            title: ""
            Text {
                objectName: "skillRunState"
                text: qsTr("Execução %1 · %2 · %3").arg(core.skillCurrentRun.run_id).arg(core.skillCurrentRun.skill).arg(L.skillRunText(core.skillCurrentRun.state)) + (core.skillCurrentRun.step ? qsTr(" · passo %1").arg(core.skillCurrentRun.step) : "")
                textFormat: Text.PlainText; color: core.skillCurrentRun.state === "failed" ? Theme.error : Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: 600; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                Accessible.name: qsTr("Estado da execução: %1").arg(text)
            }
            Repeater {
                model: core.skillCurrentRun.steps || []
                delegate: ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: Theme.space(6)
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space(10)
                        Text {
                            objectName: "skillStep_" + modelData.id
                            text: qsTr("Passo %1 · %2").arg(modelData.id).arg(L.skillStepText(modelData.state)) + (modelData.code ? " · " + core.codeMessage(modelData.code) : "")
                            textFormat: Text.PlainText
                            color: modelData.state === "failed" || modelData.state === "denied" ? Theme.error : modelData.state === "awaiting_approval" ? Theme.warning : Theme.text
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
                        }
                        GButton {
                            objectName: "skillDeny_" + modelData.id
                            visible: modelData.state === "awaiting_approval"
                            text: qsTr("Negar passo")
                            variant: "secondary"
                            Accessible.name: qsTr("Negar o passo %1").arg(modelData.id)
                            onClicked: core.skillDecide(core.skillCurrentRun.run_id, modelData.id, "deny")
                        }
                        GButton {
                            objectName: "skillAuthorize_" + modelData.id
                            visible: modelData.state === "awaiting_approval"
                            text: qsTr("Autorizar passo")
                            variant: "primary"
                            Accessible.name: qsTr("Autorizar o passo %1").arg(modelData.id)
                            onClicked: core.skillDecide(core.skillCurrentRun.run_id, modelData.id, "authorize")
                        }
                    }
                    // The decision's call: its effect and risk (same vocabulary as tool proposals; absent fields say so).
                    Text {
                        objectName: "skillDecision_" + modelData.id
                        visible: modelData.state === "awaiting_approval"
                        text: qsTr("Efeito: %1 · Risco: %2").arg(core.effectText(modelData.effect || {id: modelData.effect_id || ""}) || qsTr("não informado pelo plugin")).arg(core.riskText(modelData.risk || "") || qsTr("não declarado"))
                        textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                    Text {
                        visible: modelData.state === "awaiting_approval"
                        text: qsTr("Passo %1 aguarda sua decisão.").arg(modelData.id)
                        textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                }
            }
            Text {
                objectName: "skillOutputs"
                visible: !!core.skillCurrentRun.outputs
                text: qsTr("Saídas: %1").arg(JSON.stringify(core.skillCurrentRun.outputs || {}))
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
            }
            GButton {
                objectName: "skillCancel"
                variant: "danger"
                text: qsTr("Cancelar execução")
                Accessible.name: qsTr("Cancelar a execução da skill")
                enabled: page.runActive
                onClicked: cancelRunConfirm.open()
            }
        }
        Text {
            objectName: "skillRunEmpty"
            visible: !core.skillCurrentRun.run_id
            text: qsTr("Nenhuma execução em andamento.")
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true
        }

        Text {
            text: qsTr("Histórico de execuções")
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSection; font.weight: 600; Layout.fillWidth: true
        }
        Text {
            objectName: "skillHistoryEmpty"
            visible: core.skillHistory.length === 0
            text: qsTr("Nenhuma execução registrada.")
            textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true
        }
        Repeater {
            model: core.skillHistory
            delegate: Text {
                required property var modelData
                required property int index
                objectName: "skillHistory_" + index
                text: qsTr("%1 · %2 v%3 · %4").arg(modelData.run_id).arg(modelData.skill).arg(modelData.version).arg(L.skillRunText(modelData.state)) + (modelData.step ? qsTr(" · passo %1").arg(modelData.step) : "") + (modelData.codes.length ? " · " + modelData.codes.map(function (c) { return core.codeMessage(c) }).join("; ") : "")
                textFormat: Text.PlainText; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontHelp; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
            }
        }
    }

    // Confirmations (8.7): Cancelar is the focused default; the verb button is the only way to accept.
    Modal {
        id: removeSkillConfirm
        objectName: "removeSkillConfirm"
        property var skill: null
        title: qsTr("Remover skill")
        onAccepted: { if (skill) core.skillRemove(skill.id) }
        Text {
            text: removeSkillConfirm.skill ? qsTr("Remover %1 v%2 do Core? Nada é executado.").arg(removeSkillConfirm.skill.id).arg(removeSkillConfirm.skill.version) : ""
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmRemoveSkillButton"; variant: "danger"; text: qsTr("Remover")
            Layout.alignment: Qt.AlignRight
            Accessible.name: removeSkillConfirm.skill ? qsTr("Remover skill %1").arg(removeSkillConfirm.skill.id) : qsTr("Remover skill")
            onClicked: removeSkillConfirm.accept()
        }
    }
    Modal {
        id: cancelRunConfirm
        objectName: "cancelRunConfirm"
        title: qsTr("Cancelar execução")
        onAccepted: core.skillCancel(core.skillCurrentRun.run_id)
        Text {
            text: qsTr("Cancelar a execução %1? Os passos concluídos serão desfeitos.").arg(core.skillCurrentRun.run_id)
            textFormat: Text.PlainText; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        GButton {
            objectName: "confirmCancelRunButton"; variant: "danger"; text: qsTr("Cancelar execução")
            Layout.alignment: Qt.AlignRight
            Accessible.name: qsTr("Cancelar a execução da skill")
            onClicked: cancelRunConfirm.accept()
        }
    }
}
