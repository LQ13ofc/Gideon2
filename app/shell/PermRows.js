.pragma library
.import "Labels.js" as L
// Permissões rows and queue (docs/ui-spec/30-permissoes.md §3, §5.4, §6.5, §6.7, §8). Pure functions over snapshot rows:
// the pages pass the bridge lists (hubEntries, pluginItems, skillsItems, connectionsItems, connectionsProviders) and
// core.permissionLabel as labelOf. Nothing here calls the bridge.

var HIGH_RISK = {destructive: true, public: true}

function plural(n, one, many) { return n + " " + (n === 1 ? one : many) }

// Permission labels of a plugin: the first two, then "+N" (30 §3.1).
function permText(ids, labelOf) {
    var labels = (ids || []).map(function (p) { return labelOf(p) })
    if (labels.length === 0) return "nenhuma"
    var head = labels.slice(0, 2).join(", ")
    return labels.length > 2 ? head + " +" + (labels.length - 2) : head
}

// Access column of a scope (30 §3.4).
function accessText(access) {
    switch (access) {
    case "read": return "leitura"
    case "write": return "escrita"
    case "public": return "pública"
    case "destructive": return "destrutiva"
    default: return ""
    }
}

function providerOf(providers, id) {
    for (var i = 0; i < providers.length; i++) if (providers[i].id === id) return providers[i]
    return null
}
// Scope rows of a provider: {id, label, access}. Unknown scope ids keep the id as label.
function scopeInfo(providers, provider, scopeId) {
    var p = providerOf(providers, provider)
    if (p) for (var i = 0; i < p.scopes.length; i++) if (p.scopes[i].id === scopeId) return p.scopes[i]
    return {id: scopeId, label: scopeId, access: ""}
}
function providerName(providers, id) {
    var p = providerOf(providers, id)
    return (p && p.label) ? p.label : L.connProviderName(id)
}
function accountLine(providers, item) { return item.label + " · " + providerName(providers, item.provider) }

// A plugin with permissions that waits for the user (the same rule as the bridge's pending_count).
function pluginPending(entry) {
    return (entry.permissions || []).length > 0 && entry.permissions_approved !== true
        && (entry.status === "installed" || entry.status === "update_available")
}
function pluginApproved(entry) { return entry.permissions_approved === true && (entry.permissions || []).length > 0 }

// Plugin badge text and tone (30 §3.5).
function pluginState(entry) {
    if (entry.permissions_approved === true) return entry.status === "not_installed" ? {text: "Aprovada · não instalado", tone: "success"} : {text: "Aprovada", tone: "success"}
    if (pluginPending(entry)) return {text: "Pendente", tone: "warning"}
    return {text: "Não aprovada", tone: "neutral"}
}

function pluginEntry(entries, id) {
    for (var i = 0; i < entries.length; i++) if (entries[i].plugin_id === id) return entries[i]
    return null
}

// Plugins by plugin_id (pt-BR), with permissions and not incompatible. Used by both the queue and the table.
function sortedByKey(list, keyOf) {
    return list.slice().sort(function (a, b) { return String(keyOf(a)).localeCompare(String(keyOf(b)), "pt-BR") })
}

// The queue of Visão geral (30 §5.4): pending plugins, then accounts awaiting consent, then MCP tools to re-approve.
// Each queue row: {key, kind: "plugin" | "consent" | "tool", origin, originTone, item, sub, ref}.
function queueRows(ctx) {
    var out = []
    var plugins = sortedByKey(ctx.hub.filter(pluginPending), function (e) { return e.plugin_id })
    for (var i = 0; i < plugins.length; i++) {
        var e = plugins[i]
        var sub = "Pede: " + (e.permissions || []).map(function (p) { return ctx.labelOf(p) }).join(", ")
        if (e.status === "update_available") sub += "\nAtualização: a aprovação anterior não vale para esta versão."
        out.push({key: "queue_plugin_" + e.plugin_id, kind: "plugin", origin: "Plugin", originTone: "info",
                  item: e.plugin_id + " " + e.semver + " · publisher não autenticado", sub: sub, ref: e})
    }
    var accounts = sortedByKey(ctx.conns.filter(function (c) { return (c.pending_scopes || []).length > 0 }), function (c) { return c.label })
    for (var j = 0; j < accounts.length; j++) {
        var c = accounts[j]
        out.push({key: "queue_consent_" + c.id, kind: "consent", origin: "Conexão", originTone: "neutral",
                  item: accountLine(ctx.providers, c), sub: "aguardando consentimento: " + plural(c.pending_scopes.length, "escopo", "escopos"), ref: c})
    }
    var tools = []
    var toolAccounts = sortedByKey(ctx.conns.filter(function (c) { return c.provider === "mcp" }), function (c) { return c.label })
    for (var k = 0; k < toolAccounts.length; k++) {
        var t = toolAccounts[k]
        var waiting = (t.tools || []).filter(function (x) { return x.state === "needs_reapproval" }).map(function (x) { return x.name }).sort()
        for (var m = 0; m < waiting.length; m++) tools.push({key: "queue_tool_" + t.id + "_" + waiting[m], kind: "tool", origin: "Conexão", originTone: "neutral",
                  item: t.label + " · MCP", sub: "Ferramenta " + waiting[m] + ": precisa de nova aprovação", ref: t, tool: waiting[m]})
    }
    return out.concat(tools)
}

// Concessões ativas of Visão geral (30 §5.6, items 16-17): approved plugins, then accounts with granted scopes.
function activeRows(ctx) {
    var out = []
    var plugins = sortedByKey(ctx.hub.filter(pluginApproved), function (e) { return e.plugin_id })
    for (var i = 0; i < plugins.length; i++) {
        var e = plugins[i]
        out.push({key: "plugin:" + e.plugin_id, origin: "Plugin", originTone: "info",
                  item: e.plugin_id + " " + e.semver + " · " + permText(e.permissions, ctx.labelOf),
                  state: pluginState(e), ref: e, filter: "plugins"})
    }
    var accounts = sortedByKey(ctx.conns.filter(function (c) { return (c.granted_scopes || []).length > 0 }), function (c) { return c.label })
    for (var j = 0; j < accounts.length; j++) {
        var c = accounts[j]
        out.push({key: "conn:" + c.id, origin: "Conexão", originTone: "neutral",
                  item: accountLine(ctx.providers, c) + " · " + plural(c.granted_scopes.length, "escopo concedido", "escopos concedidos"),
                  state: {text: "Concedido", tone: "success"}, ref: c, filter: "conexoes"})
    }
    return out
}

// Rows of the Concessões table (30 §6.5). One row per plugin with permissions, per skill, per granted or pending
// scope of an account, and per MCP tool that needs trust or was refused. The action is decided here from `ctx.flags`.
// ctx: {hub, plugins (pluginItems), skills (skillsItems), conns, providers, labelOf, flags}
// flags: {online, hubOk (approve plugin now), pluginsOk (revoke plugin now), connAvailable, connBusy, skillsOk, pluginsBlockedTip}
function grantRows(ctx) {
    var f = ctx.flags
    var rows = []
    var plugins = ctx.hub.filter(function (e) { return (e.permissions || []).length > 0 && e.status !== "incompatible" })
    for (var i = 0; i < plugins.length; i++) {
        var e = plugins[i]
        var approved = e.permissions_approved === true
        var live = L.pluginFor(ctx.plugins, e.plugin_id)
        var quarantined = !!live && live.state === "quarantined"
        var st = pluginState(e)
        var action
        if (approved) {
            var revokeTip = !f.online ? "Core desconectado." : quarantined ? "Plugin em quarentena: não pode mudar de estado." : !f.pluginsOk ? f.pluginsBlockedTip : ""
            action = {kind: "revoke", text: "Revogar", danger: true, enabled: f.pluginsOk && !quarantined, tip: revokeTip}
        } else {
            var reviewTip = !f.online ? "Core desconectado." : !f.hubOk ? f.pluginsBlockedTip : ""
            action = {kind: "review", text: "Revisar", danger: false, enabled: f.hubOk, tip: reviewTip}
        }
        rows.push({key: "plugin:" + e.plugin_id, origin: "plugin", originText: "Plugin", originTone: "info",
                   item: e.plugin_id + " " + e.semver, groupKey: "plugin:" + e.plugin_id, groupLabel: e.plugin_id + " " + e.semver,
                   sub: "", perm: permText(e.permissions, ctx.labelOf), permIds: e.permissions, permTone: "",
                   permNote: "", access: "", risk: false, state: st, pending: pluginPending(e),
                   granted: approved ? L.grantedDate(e.approved_at_ms) : "",
                   rank: st.tone === "warning" ? 0 : approved ? 2 : 1, action: action, ref: e})
    }
    var skills = ctx.skills
    for (var s = 0; s < skills.length; s++) {
        var sk = skills[s]
        var okPerm = sk.permissions_ok === true
        var missing = (sk.missing || []).join(", ")
        var skillAction = {kind: "skill", text: "Ver em Skills", danger: false, enabled: f.skillsOk, tip: f.skillsOk ? "" : "Indisponível agora."}
        rows.push({key: "skill:" + sk.id, origin: "skill", originText: "Skill", originTone: "neutral",
                   item: sk.name + " v" + sk.version, groupKey: "skill:" + sk.id, groupLabel: sk.name + " v" + sk.version,
                   sub: "", perm: okPerm ? "Permissões ok" : "Permissões pendentes", permIds: [],
                   permTone: okPerm ? "success" : "warning", permNote: (!okPerm && missing) ? "Faltando: " + missing : "",
                   access: "", risk: false, state: {text: L.skillStateText(sk.state).replace(/^./, function (c) { return c.toUpperCase() }), tone: "neutral"},
                   pending: false, rank: okPerm ? 2 : 1, action: skillAction, ref: sk})
    }
    var conns = ctx.conns
    for (var c = 0; c < conns.length; c++) {
        var item = conns[c]
        var line = accountLine(ctx.providers, item)
        var groupLabel = line
        var connTip = !f.online ? "Core desconectado." : (f.connAvailable ? "" : "Indisponível agora.")
        var grants = item.granted_scopes || []
        var waits = item.pending_scopes || []
        for (var g = 0; g < grants.length; g++) {
            var sc = scopeInfo(ctx.providers, item.provider, grants[g])
            var canRevoke = f.connAvailable && L.connCan(f.connBusy, "revoke", item)
            rows.push({key: "scope:" + item.id + ":" + sc.id, origin: "connection", originText: "Conexão", originTone: "neutral",
                       item: line, groupKey: "conn:" + item.id, groupLabel: groupLabel, sub: "", perm: sc.label,
                       permIds: [sc.id], permTone: "", permNote: "", access: accessText(sc.access), risk: HIGH_RISK[sc.access] === true,
                       state: {text: "Concedido", tone: "success"}, pending: false, rank: 2,
                       granted: L.grantedDate(item.grantedAtMs),
                       action: {kind: "revokeScope", text: "Revogar escopo", danger: true, enabled: canRevoke,
                                tip: !f.online ? "Core desconectado." : canRevoke ? "" : "Conta sem acesso concedido para revogar."},
                       ref: item, scope: sc.id})
        }
        for (var w = 0; w < waits.length; w++) {
            var sw = scopeInfo(ctx.providers, item.provider, waits[w])
            rows.push({key: "scope:" + item.id + ":" + sw.id, origin: "connection", originText: "Conexão", originTone: "neutral",
                       item: line, groupKey: "conn:" + item.id, groupLabel: groupLabel, sub: "", perm: sw.label,
                       permIds: [sw.id], permTone: "", permNote: "", access: accessText(sw.access), risk: HIGH_RISK[sw.access] === true,
                       state: {text: "Aguardando consentimento", tone: "warning"}, pending: true, rank: 0,
                       action: {kind: "consent", text: "Consentir", danger: false, enabled: f.connAvailable && !f.connBusy, tip: connTip},
                       ref: item, scope: sw.id})
        }
        if (item.provider === "mcp") {
            var tools = (item.tools || []).slice().sort(function (a, b) { return String(a.name).localeCompare(String(b.name), "pt-BR") })
            for (var t = 0; t < tools.length; t++) {
                var tool = tools[t]
                var tState = tool.state === "needs_reapproval" ? {text: "Precisa de nova aprovação", tone: "warning"}
                    : tool.state === "trusted" ? {text: "Confiável", tone: "success"}
                    : tool.state === "rejected" ? {text: "Recusada", tone: "error"} : null
                if (!tState) continue
                var tAction = tool.state === "needs_reapproval" ? {kind: "trust", text: "Confiar", danger: false, enabled: f.connAvailable && !f.connBusy, tip: connTip}
                    : {kind: "none", text: tool.state === "trusted" ? "Cada chamada ainda pede aprovação." : "Recusada pelo Core: nada a fazer.", danger: false, enabled: false, tip: ""}
                rows.push({key: "tool:" + item.id + ":" + tool.name, origin: "connection", originText: "Conexão", originTone: "neutral",
                           item: line, groupKey: "conn:" + item.id, groupLabel: groupLabel, sub: "", perm: "Ferramenta " + tool.name,
                           permIds: [], permTone: "", permNote: "", access: tool.risk === "destructive" ? "destrutiva" : "escrita",
                           risk: tool.risk === "destructive", state: tState, pending: tool.state === "needs_reapproval",
                           rank: tool.state === "needs_reapproval" ? 0 : tool.state === "trusted" ? 2 : 1, action: tAction, ref: item, tool: tool.name})
            }
        }
    }
    return rows
}

// Table order (30 §6.7): state first (pending, then not approved, then ok), then origin (Plugin, Skill, Conexão),
// then the item in pt-BR, then the permission or scope.
var ORIGIN_ORDER = {plugin: 0, skill: 1, connection: 2}
function compareRows(a, b) {
    if (a.rank !== b.rank) return a.rank - b.rank
    if (ORIGIN_ORDER[a.origin] !== ORIGIN_ORDER[b.origin]) return ORIGIN_ORDER[a.origin] - ORIGIN_ORDER[b.origin]
    var byItem = String(a.item).localeCompare(String(b.item), "pt-BR")
    return byItem !== 0 ? byItem : String(a.perm).localeCompare(String(b.perm), "pt-BR")
}

// Keeps the rows of one filter: "todas", "plugins", "skills", "conexoes".
function filterRows(rows, filter) {
    var want = {plugins: "plugin", skills: "skill", conexoes: "connection"}[filter]
    return want ? rows.filter(function (r) { return r.origin === want }) : rows
}

// Group headers: by origin ("Plugins · n", "Skills · n", "Conexões · n") or by item (the item, its count and its pending count).
var ORIGIN_GROUPS = [{origin: "plugin", label: "Plugins"}, {origin: "skill", label: "Skills"}, {origin: "connection", label: "Conexões"}]
function groupRows(rows, groupBy) {
    var out = []
    var n = 0
    if (groupBy === "origem") {
        for (var g = 0; g < ORIGIN_GROUPS.length; g++) {
            var part = rows.filter(function (r) { return r.origin === ORIGIN_GROUPS[g].origin })
            if (part.length === 0) continue
            var sorted = part.slice().sort(compareRows)
            out.push({header: true, text: ORIGIN_GROUPS[g].label + " · " + part.length})
            for (var i = 0; i < sorted.length; i++) out.push(withNumber(sorted[i], ++n))
        }
        return out
    }
    var keys = []
    var byKey = {}
    for (var r = 0; r < rows.length; r++) {
        var k = rows[r].groupKey
        if (!byKey[k]) { byKey[k] = []; keys.push({key: k, label: rows[r].groupLabel}) }
        byKey[k].push(rows[r])
    }
    keys.forEach(function (x) { x.pending = byKey[x.key].filter(function (q) { return q.pending }).length })
    keys.sort(function (a, b) {
        if ((a.pending > 0) !== (b.pending > 0)) return a.pending > 0 ? -1 : 1
        return String(a.label).localeCompare(String(b.label), "pt-BR")
    })
    for (var q = 0; q < keys.length; q++) {
        var members = byKey[keys[q].key].slice().sort(compareRows)
        out.push({header: true, text: keys[q].label, count: members.length + " " + (members.length === 1 ? "linha" : "linhas") + " · " + keys[q].pending + " pendente" + (keys[q].pending === 1 ? "" : "s")})
        for (var m = 0; m < members.length; m++) out.push(withNumber(members[m], ++n))
    }
    return out
}
function withNumber(row, n) {
    var copy = {}
    for (var k in row) copy[k] = row[k]
    copy.header = false
    copy.number = n
    return copy
}

// Counts shown next to the filter: rows that are pending (30 §6.3, "{n} itens · {P} pendentes").
function pendingIn(rows) { return rows.filter(function (r) { return r.pending }).length }
