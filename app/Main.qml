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
        {id: "assistente", label: qsTr("Assistente"), icon: "chat"},
        {id: "extensoes", label: qsTr("Extensões"), icon: "puzzle"},
        {id: "permissoes", label: qsTr("Permissões"), icon: "shield"},
        {id: "configuracoes", label: qsTr("Configurações"), icon: "gear"},
        {id: "diagnostico", label: qsTr("Diagnóstico"), icon: "activity"}
    ]
    readonly property var pageDefs: [
        {id: "hoje", tab: "assistente", label: qsTr("Hoje")},
        {id: "conversa", tab: "assistente", label: qsTr("Conversa")},
        {id: "conversas", tab: "assistente", label: qsTr("Histórico")},
        {id: "agente", tab: "assistente", label: qsTr("Agente")},
        {id: "atividade", tab: "assistente", label: qsTr("Atividade")},
        {id: "automacoes", tab: "assistente", label: qsTr("Automações")},
        {id: "plugins", tab: "extensoes", label: qsTr("Plugins")},
        {id: "skills", tab: "extensoes", label: qsTr("Skills")},
        {id: "habitos", tab: "extensoes", label: qsTr("Hábitos")},
        {id: "conexoes", tab: "extensoes", label: qsTr("Conexões")},
        {id: "modelos", tab: "extensoes", label: qsTr("Modelos LLM")},
        {id: "percepcao", tab: "extensoes", label: qsTr("Percepção e ação")},
        {id: "perm_visao", tab: "permissoes", label: qsTr("Visão geral")},
        {id: "perm_concessoes", tab: "permissoes", label: qsTr("Concessões")},
        {id: "perm_auditoria", tab: "permissoes", label: qsTr("Auditoria")},
        {id: "memoria", tab: "permissoes", label: qsTr("Memória")},
        {id: "cfg_voz", tab: "configuracoes", label: qsTr("Voz e Wake")},
        {id: "cfg_idiomas", tab: "configuracoes", label: qsTr("Idiomas")},
        {id: "cfg_audio", tab: "configuracoes", label: qsTr("Áudio")},
        {id: "cfg_dispositivos", tab: "configuracoes", label: qsTr("Dispositivos")},
        {id: "cfg_aparencia", tab: "configuracoes", label: qsTr("Aparência")},
        {id: "cfg_privacidade", tab: "configuracoes", label: qsTr("Privacidade")},
        {id: "almas", tab: "configuracoes", label: qsTr("Almas")},
        {id: "cfg_geral", tab: "configuracoes", label: qsTr("Geral")},
        {id: "diag_estado", tab: "diagnostico", label: qsTr("Estado")},
        {id: "diag_motores", tab: "diagnostico", label: qsTr("Motores")},
        {id: "diag_recuperacao", tab: "diagnostico", label: qsTr("Recuperação")},
        {id: "diag_dev", tab: "diagnostico", label: qsTr("Desenvolvedor")}
    ]
    // Conditional sub-tabs: a page is offered only when its plugin or mode is there (docs/UI_IA.md).
    readonly property var availability: ({
        hoje: true, atividade: true, plugins: true, perm_visao: true, perm_concessoes: true, perm_auditoria: true,
        cfg_voz: true, cfg_idiomas: true, cfg_audio: true, cfg_dispositivos: true, cfg_aparencia: true, cfg_privacidade: true, cfg_geral: true,
        diag_estado: true, diag_motores: true, diag_recuperacao: true,
        // WP-10a: the personal pages show "Indisponível" while the Core does not answer, so they need no plugin condition.
        conversas: true, automacoes: true, habitos: true, memoria: true, almas: true,
        conversa: core.chatAvailable, agente: core.chatAvailable,
        skills: core.skillsAvailable, conexoes: core.connectionsAvailable,
        modelos: core.modelsAvailable || core.llmConfigAvailable, percepcao: core.perceptionAvailable,
        // DIAG-02: the developer mode is the Core preference (preferences.developer_mode), not an app-side flag.
        diag_dev: core.developerMode
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
    readonly property string pillText: !core.connected ? qsTr("Offline") : ((core.state === "idle" && (core.chatState === "waiting" || core.chatState === "streaming")) ? qsTr("Pensando") : L.stateText(core.state))
    readonly property string pillTone: !core.connected ? "offline"
        : (core.state === "offline" || core.state === "safe_mode" || core.state === "restart_required") ? "offline"
        : (core.state === "capturing" || core.state === "transcribing" || core.state === "executing" || core.state === "speaking" || core.chatState === "waiting" || core.chatState === "streaming") ? "working"
        : core.state === "error" ? "error" : "idle"

    // ---- Palette -----------------------------------------------------------------------------------------------
    readonly property var palettePages: pageDefs.filter(function (d) { return availability[d.id] === true }).map(function (d) {
        return {label: d.label, detail: tabDefs.filter(function (t) { return t.id === d.tab })[0].label, target: "page:" + d.id}
    })
    readonly property var paletteCommands: [
        {label: qsTr("Cancelar sessão"), target: "cmd:cancel"},
        {label: qsTr("Abrir Motor LLM"), target: "cmd:llm"},
        {label: qsTr("Restaurar padrões do app"), target: "page:cfg_geral"},
        {label: qsTr("Ligar modo desenvolvedor"), target: "page:diag_estado"},
        {label: qsTr("Trocar tema ou cor"), target: "page:cfg_aparencia"},
        {label: qsTr("Refazer introdução"), target: "cmd:intro"}
    ]
    // The theme singleton, for the QML tests (scripts/test_bridge_protocol.py reads the effective effects through it).
    readonly property var themeRef: Theme
    function settingPage(key) {
        if (key.indexOf("theme.") === 0) return "cfg_aparencia"
        if (key.indexOf("voice.") === 0 || key.indexOf("wake") >= 0) return "cfg_voz"
        if (key === "core.audioInput" || key === "core.audioOutput") return "cfg_dispositivos"
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
            out.push({label: label, detail: qsTr("Configuração"), target: "page:" + settingPage(String(key))})
        }
        return out
    }
    function runTarget(target) {
        if (target.indexOf("page:") === 0) goPage(target.substring(5))
        else if (target === "cmd:cancel") core.cancel()
        else if (target === "cmd:llm") openLlm()
        else if (target === "cmd:intro") AppState.openOnboarding()
    }

    // ---- Shortcuts ---------------------------------------------------------------------------------------------
    // All of them follow behavior.shortcuts (Theme.shortcutsOn). While the first-run guide is up, the shell keys wait.
    readonly property bool shortcutsEnabled: Theme.shortcutsOn && !onboarding.visible
    Shortcut { sequences: ["Ctrl+1"]; enabled: window.shortcutsEnabled; onActivated: window.pickTab("assistente") }
    Shortcut { sequences: ["Ctrl+2"]; enabled: window.shortcutsEnabled; onActivated: window.pickTab("extensoes") }
    Shortcut { sequences: ["Ctrl+3"]; enabled: window.shortcutsEnabled; onActivated: window.pickTab("permissoes") }
    Shortcut { sequences: ["Ctrl+4"]; enabled: window.shortcutsEnabled; onActivated: window.pickTab("configuracoes") }
    Shortcut { sequences: ["Ctrl+5"]; enabled: window.shortcutsEnabled; onActivated: window.pickTab("diagnostico") }
    Shortcut { sequences: ["Ctrl+Tab"]; enabled: window.shortcutsEnabled; onActivated: window.cycleSub(1) }
    Shortcut { sequences: ["Ctrl+Shift+Tab"]; enabled: window.shortcutsEnabled; onActivated: window.cycleSub(-1) }
    Shortcut { sequences: ["Ctrl+K"]; enabled: window.shortcutsEnabled; onActivated: palette.open() }
    // Ctrl+M (HUD-03): starts a listening session through the Core (`listen_start`), or ends the running one. The Core
    // refuses with a reason when live audio is off or the capture is not running; that reason comes back as a toast.
    Shortcut { sequences: ["Ctrl+M"]; enabled: window.shortcutsEnabled; onActivated: window.toggleListening() }
    function toggleListening() {
        if (core.connected && core.sessionId.length > 0) {
            core.cancel()
            AppState.toast(qsTr("Escuta encerrada."))
        } else if (core.connected) {
            core.listenStart()
        } else {
            AppState.toast(qsTr("Core desconectado: nada pode ser iniciado agora"))
        }
    }
    // Esc cancels a running capture. It is handled by the shell layout, which is the focus chain of the pages: when a
    // dialog or the palette is open the focus is inside it, the key stops there, and nothing is cancelled (one action only).
    function escapeCancels() {
        if (!Theme.shortcutsOn || onboarding.visible) return false
        if (!core.connected || core.state !== "capturing") return false
        core.cancel()
        return true
    }

    // ---- Core -------------------------------------------------------------------------------------------------
    Connections {
        target: core
        // A page whose plugin left falls back to Hoje (the same rule as before the redesign).
        function onChanged() { if (!window.availability[window.pageId]) window.pageId = "hoje" }
        // Core answers to preference saves become short toasts.
        function onPrefsSettled(message) { if (message && message.length > 0) AppState.toast(message) }
    }

    // ---- Layout ------------------------------------------------------------------------------------------------
    ColumnLayout {
        id: shellLayout
        anchors.fill: parent
        spacing: 0
        focus: true
        Keys.onEscapePressed: function (event) { event.accepted = window.escapeCancels() }

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
            micActive: core.micActive
            // On Hoje the voice session has its own Cancelar (InicioHoje), so the top bar one is held back there (no duplicate).
            cancellable: window.sessionCancellable && window.pageId !== "hoje"
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
            Conversas {}
            Agente {}
            Atividade {}
            Automacoes {}
            Plugins {}
            Skills {}
            Habitos {}
            Conexoes {}
            ModelosLlm { id: modelsPage }
            Percepcao {}
            PermVisao {}
            PermConcessoes {}
            PermAuditoria {}
            Memoria {}
            CfgVoz {}
            CfgIdiomas {}
            CfgAudio {}
            CfgDispositivos {}
            CfgAparencia {}
            CfgPrivacidade {}
            Almas {}
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

    // First-run guide: above the shell, below nothing. Shown once per profile (behavior.onboardingDone), suppressed by
    // GIDEON_UI_NO_ONBOARDING=1 (explorers and gates), never while the Core is offline or a voice session runs.
    OOnboarding {
        id: onboarding
    }

    Component.onCompleted: {
        if (!window.availability[window.pageId]) window.pageId = "hoje"
        AppState.onboardingOpen = AppState.uiLive() && !ui.noOnboarding && ui.values["behavior.onboardingDone"] !== true
        // WP-17: push-to-talk stays on across launches only when the owner turned it on (consent was given then).
        if (AppState.uiGet("shortcut.pushToTalk", false) === true)
            core.setPushToTalk(true, AppState.uiGet("shortcut.pushToTalkTrigger", "CTRL+ALT+G"))
    }
}
