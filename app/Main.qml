import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "theme"
import "components"
import "shell"
import "pages"
import "shell/Labels.js" as L

// Window shell: level-1 tabs (Assistente, Extensões, Permissões, Configurações, Diagnóstico), level-2 sub-tabs of the
// active tab, one page at a time, the command palette (Ctrl+K), toasts, and the global Motor LLM form.
// Every page is a file in pages/; every colour and size comes from Theme (theme/Theme.qml).
ApplicationWindow {
    id: window
    objectName: "mainWindow"
    visible: true
    width: 1380; height: 904
    minimumWidth: 480; minimumHeight: 520
    title: "Gideon"
    color: Theme.bg
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    palette.window: Theme.surface; palette.windowText: Theme.text
    palette.button: Theme.surfaceVariant; palette.buttonText: Theme.text
    palette.base: Theme.bg; palette.text: Theme.text
    palette.placeholderText: Theme.textMuted
    palette.highlight: Theme.accent; palette.highlightedText: Theme.onAccent

    // ---- Navigation ------------------------------------------------------------------------------------------
    // The page in view. Pages read it through Window.window.pageId; tests and scripts may set it directly.
    property string pageId: "hoje"
    // Remembers the last sub-tab of each tab, so a tab click returns there.
    property var lastSub: ({})

    readonly property var tabDefs: [
        {id: "assistente", label: "Assistente", icon: "chat"},
        {id: "extensoes", label: "Extensões", icon: "puzzle"},
        {id: "permissoes", label: "Permissões", icon: "shield"},
        {id: "configuracoes", label: "Configurações", icon: "gear"},
        {id: "diagnostico", label: "Diagnóstico", icon: "activity"}
    ]
    readonly property var pageDefs: [
        {id: "hoje", tab: "assistente", label: "Hoje"},
        {id: "conversa", tab: "assistente", label: "Conversa"},
        {id: "agente", tab: "assistente", label: "Agente"},
        {id: "atividade", tab: "assistente", label: "Atividade"},
        {id: "plugins", tab: "extensoes", label: "Plugins"},
        {id: "skills", tab: "extensoes", label: "Skills"},
        {id: "conexoes", tab: "extensoes", label: "Conexões"},
        {id: "modelos", tab: "extensoes", label: "Modelos LLM"},
        {id: "percepcao", tab: "extensoes", label: "Percepção e ação"},
        {id: "perm_visao", tab: "permissoes", label: "Visão geral"},
        {id: "perm_concessoes", tab: "permissoes", label: "Concessões"},
        {id: "perm_auditoria", tab: "permissoes", label: "Auditoria"},
        {id: "cfg_voz", tab: "configuracoes", label: "Voz e Wake"},
        {id: "cfg_audio", tab: "configuracoes", label: "Áudio"},
        {id: "cfg_dispositivos", tab: "configuracoes", label: "Dispositivos"},
        {id: "cfg_aparencia", tab: "configuracoes", label: "Aparência"},
        {id: "cfg_privacidade", tab: "configuracoes", label: "Privacidade"},
        {id: "cfg_geral", tab: "configuracoes", label: "Geral"},
        {id: "diag_estado", tab: "diagnostico", label: "Estado"},
        {id: "diag_motores", tab: "diagnostico", label: "Motores"},
        {id: "diag_recuperacao", tab: "diagnostico", label: "Recuperação"},
        {id: "diag_dev", tab: "diagnostico", label: "Desenvolvedor"}
    ]
    // Conditional sub-tabs: a page is offered only when its plugin or mode is there (docs/UI_IA.md).
    readonly property var availability: ({
        hoje: true, atividade: true, plugins: true, perm_visao: true, perm_concessoes: true, perm_auditoria: true,
        cfg_voz: true, cfg_audio: true, cfg_dispositivos: true, cfg_aparencia: true, cfg_privacidade: true, cfg_geral: true,
        diag_estado: true, diag_motores: true, diag_recuperacao: true,
        conversa: core.chatAvailable, agente: core.chatAvailable,
        skills: core.skillsAvailable, conexoes: core.connectionsAvailable,
        modelos: core.modelsAvailable || core.llmConfigAvailable, percepcao: core.perceptionAvailable,
        diag_dev: Theme.devMode
    })

    function pageDef(id) { for (var i = 0; i < pageDefs.length; i++) if (pageDefs[i].id === id) return pageDefs[i]; return null }
    function tabOf(id) { var d = pageDef(id); return d ? d.tab : "assistente" }
    function subsOf(tab) { return pageDefs.filter(function (d) { return d.tab === tab && availability[d.id] === true }) }
    readonly property string currentTab: tabOf(pageId)

    // Pending decisions of Permissões (docs/ui-spec/30-permissoes.md §8): the Core's count, shown on the tab badge.
    readonly property int pendingCount: core.pendingCount
    readonly property var tabModel: tabDefs.map(function (t) {
        return {id: t.id, label: t.label, icon: t.icon, count: t.id === "permissoes" ? window.pendingCount : 0}
    })
    readonly property var subModel: subsOf(currentTab).map(function (d) {
        return {id: d.id, label: d.label, count: d.id === "plugins" ? core.hubEntries.filter(function (e) { return e.status === "installed" && e.permissions_approved !== true }).length : 0}
    })

    function goPage(id) {
        if (!id || availability[id] !== true) return
        pageId = id
    }
    function pickTab(tab) {
        var subs = subsOf(tab)
        if (subs.length === 0) return
        var last = lastSub[tab]
        var target = (last && availability[last] === true) ? last : subs[0].id
        goPage(target)
    }
    function cycleSub(step) {
        var subs = subsOf(currentTab)
        if (subs.length < 2) return
        var at = 0
        for (var i = 0; i < subs.length; i++) if (subs[i].id === pageId) at = i
        goPage(subs[(at + step + subs.length) % subs.length].id)
    }
    onPageIdChanged: { var t = tabOf(pageId); lastSub[t] = pageId }
    // Every page the Core offers right now (the sub-bar lists only the active tab's pages).
    readonly property var offeredPages: pageDefs.filter(function (d) { return availability[d.id] === true }).map(function (d) { return d.id })

    // Settings from the window (Motor LLM form, dialogs) and the palette.
    // The Motor LLM form lives in Modelos LLM › Provedor e chaves (it works without the models plugin).
    function openLlm() { modelsPage.part = "provedor"; goPage("modelos") }

    // ---- Status pill -------------------------------------------------------------------------------------------
    readonly property bool sessionCancellable: core.connected && core.sessionId.length > 0 && (core.state === "capturing" || core.state === "transcribing" || core.state === "executing" || core.state === "speaking")
    readonly property string pillText: !core.connected ? "Offline" : ((core.state === "idle" && (core.chatState === "waiting" || core.chatState === "streaming")) ? "Pensando" : L.stateText(core.state))
    readonly property string pillTone: !core.connected ? "offline"
        : (core.state === "offline" || core.state === "safe_mode" || core.state === "restart_required") ? "offline"
        : (core.state === "capturing" || core.state === "transcribing" || core.state === "executing" || core.state === "speaking" || core.chatState === "waiting" || core.chatState === "streaming") ? "working"
        : core.state === "error" ? "error" : "idle"

    // ---- Palette -----------------------------------------------------------------------------------------------
    readonly property var palettePages: pageDefs.filter(function (d) { return availability[d.id] === true }).map(function (d) {
        return {label: d.label, detail: tabDefs.filter(function (t) { return t.id === d.tab })[0].label, target: "page:" + d.id}
    })
    readonly property var paletteCommands: [
        {label: "Cancelar sessão", target: "cmd:cancel"},
        {label: "Abrir Motor LLM", target: "cmd:llm"},
        {label: "Restaurar padrões do app", target: "page:cfg_geral"},
        {label: "Ligar modo desenvolvedor", target: "page:diag_estado"},
        {label: "Trocar tema ou cor", target: "page:cfg_aparencia"}
    ]
    function settingPage(key) {
        if (key.indexOf("theme.") === 0) return "cfg_aparencia"
        if (key.indexOf("voice.") === 0 || key.indexOf("wake") >= 0) return "cfg_voz"
        if (key.indexOf("audio.") === 0) return "cfg_audio"
        if (key.indexOf("privacy") === 0) return "cfg_privacidade"
        if (key === "behavior.devMode") return "diag_estado"
        return "cfg_geral"
    }
    function findSettings(q) {
        if (typeof ui === "undefined" || !ui || !q) return []
        var found = ui.search(q)
        var out = []
        for (var i = 0; i < found.length; i++) {
            var r = found[i]
            var key = typeof r === "string" ? r : (r.key || r.id || "")
            var label = typeof r === "string" ? r : (r.label || r.key || r.id || "")
            out.push({label: label, detail: "Configuração", target: "page:" + settingPage(String(key))})
        }
        return out
    }
    function runTarget(target) {
        if (target.indexOf("page:") === 0) goPage(target.substring(5))
        else if (target === "cmd:cancel") core.cancel()
        else if (target === "cmd:llm") openLlm()
    }

    // ---- Shortcuts ---------------------------------------------------------------------------------------------
    Shortcut { sequences: ["Ctrl+1"]; enabled: Theme.shortcutsOn; onActivated: window.pickTab("assistente") }
    Shortcut { sequences: ["Ctrl+2"]; enabled: Theme.shortcutsOn; onActivated: window.pickTab("extensoes") }
    Shortcut { sequences: ["Ctrl+3"]; enabled: Theme.shortcutsOn; onActivated: window.pickTab("permissoes") }
    Shortcut { sequences: ["Ctrl+4"]; enabled: Theme.shortcutsOn; onActivated: window.pickTab("configuracoes") }
    Shortcut { sequences: ["Ctrl+5"]; enabled: Theme.shortcutsOn; onActivated: window.pickTab("diagnostico") }
    Shortcut { sequences: ["Ctrl+Tab"]; enabled: Theme.shortcutsOn; onActivated: window.cycleSub(1) }
    Shortcut { sequences: ["Ctrl+Shift+Tab"]; enabled: Theme.shortcutsOn; onActivated: window.cycleSub(-1) }
    Shortcut { sequences: ["Ctrl+K"]; onActivated: palette.open() }

    // ---- Core -------------------------------------------------------------------------------------------------
    Connections {
        target: core
        // A page whose plugin left falls back to Hoje (the same rule as before the redesign).
        function onChanged() { if (!window.availability[window.pageId]) window.pageId = "hoje" }
        // Core answers to preference saves become short toasts.
        function onPrefsSettled(message) { if (message && message.length > 0) AppState.toast(message) }
    }
    Component.onCompleted: { if (!window.availability[window.pageId]) window.pageId = "hoje" }

    // ---- Layout ------------------------------------------------------------------------------------------------
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        TopBar {
            id: topBar
            Layout.fillWidth: true
            tabs: window.tabModel
            currentTab: window.currentTab
            narrow: window.width < Theme.narrowWidth
            compact: window.width < 1100
            stateText: window.pillText
            stateTone: window.pillTone
            orbOn: Theme.orbVisible && core.visualFeedback
            orbState: L.orbStateOf(core.connected ? core.state : "offline")
            cancellable: window.sessionCancellable
            onTabPicked: function (id) { window.pickTab(id) }
            onPaletteRequested: palette.open()
            onCancelRequested: core.cancel()
        }
        SubBar {
            id: subBar
            Layout.fillWidth: true
            subs: window.subModel
            current: window.pageId
            onPicked: function (id) { window.goPage(id) }
        }

        // One page at a time: each page shows itself when pageId names it.
        Item {
            id: stage
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            InicioHoje {}
            Conversa {}
            Agente {}
            Atividade {}
            Plugins {}
            Skills {}
            Conexoes {}
            ModelosLlm { id: modelsPage }
            Percepcao {}
            PermVisao {}
            PermConcessoes {}
            PermAuditoria {}
            CfgVoz {}
            CfgAudio {}
            CfgDispositivos {}
            CfgAparencia {}
            CfgPrivacidade {}
            CfgGeral {}
            DiagEstado {}
            DiagMotores {}
            DiagRecuperacao {}
            DiagDev {}
        }
    }

    ToastHost {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 16
        anchors.bottomMargin: 16
        z: 50
    }

    CommandPalette {
        id: palette
        pages: window.palettePages
        commands: window.paletteCommands
        settingsProvider: window.findSettings
        onActivated: function (item) { window.runTarget(item.target) }
    }

}
