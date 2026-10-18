//! S5 E3 CapabilityRegistry: which route serves a purpose. The table of purposes is fixed in this file.
//! A purpose has an API route (`connection`, through the Connection Manager) and, for `create_issue`
//! only, a `visual` route (scripted clicks and typing on the fake site of the synthetic world).
//!
//! Routes are ranked by authorization, then security (lower risk), official support, reliability (the
//! last result of the route, kept in memory), privacy and the fewest side effects. Ranking only orders
//! routes that can run. The rules that decide whether a route may run are not rankings:
//! - the visual route runs only when the provider has no connection at all (no backend, no account, or
//!   only disconnected accounts), the user allowed the visual fallback for the purpose, and the owner of
//!   the screen-control capability is running;
//! - an expired, reauth-required or scope-less connection is never worked around: the purpose answers
//!   `route_unavailable` with the reason and nothing else runs.
//!
//! Neither a model nor a tool argument reaches the table, the visual permission or the grants: the
//! permission changes only through the user's `registry_allow_visual` operation.
use crate::{connections::Standing, core::Core, storage::Storage, tools, world};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{collections::BTreeMap, path::Path};

/// Agent tool of the purpose `create_issue`; exists only while the github fake is configured.
pub const TOOL: &str = "route_create_issue";
/// Fixed target of the tool: the model never names a repository.
pub const TARGET_REPO: &str = "demo/public-repo";
pub const CREATE_ISSUE: &str = "create_issue";
/// Longest title or body the visual route can type (one `ui_type` call takes at most 64 bytes).
pub const VISUAL_TEXT_MAX: usize = 64;
const TITLE_MAX: usize = 256;
const BODY_MAX: usize = 4096;
const LEDGER_VERSION: u16 = 1;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Route {
    Connection,
    Visual,
}

impl Route {
    pub fn name(self) -> &'static str {
        match self {
            Route::Connection => "connection",
            Route::Visual => "visual",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Available,
    NotConnected,
    Expired,
    ScopeNotGranted,
    NoApi,
    VisualNotAllowed,
    Disabled,
}

/// One purpose of the fixed table. `operation` is the connection operation that serves it.
pub struct Purpose {
    pub id: &'static str,
    pub label: &'static str,
    pub provider: &'static str,
    pub provider_label: &'static str,
    pub operation: &'static str,
    /// Whether a visual route exists for the purpose.
    pub visual: bool,
}

pub const PURPOSES: [Purpose; 3] = [
    Purpose {
        id: CREATE_ISSUE,
        label: "Criar issue",
        provider: "github",
        provider_label: "GitHub",
        operation: "issues.create",
        visual: true,
    },
    Purpose {
        id: "list_events",
        label: "Listar eventos da agenda",
        provider: "google",
        provider_label: "Google",
        operation: "calendar.events.list",
        visual: false,
    },
    Purpose {
        id: "read_state",
        label: "Ler estado da casa",
        provider: "homeassistant",
        provider_label: "Home Assistant",
        operation: "state.get",
        visual: false,
    },
];

pub fn purpose(id: &str) -> Option<&'static Purpose> {
    PURPOSES.iter().find(|p| p.id == id)
}

impl Purpose {
    /// Scope the connection route needs, read from the provider descriptor.
    pub fn scope(&self) -> &'static str {
        crate::connections::provider_by_id(self.provider)
            .and_then(|provider| crate::connections::operation(provider, self.operation))
            .map_or("", |op| op.scope)
    }
}

/// Facts the Core gathers for one plan. Nothing here comes from a model.
pub struct Facts<'a> {
    pub standing: Standing,
    /// The synthetic world (`--agent-synthetic`) is enabled.
    pub synthetic: bool,
    /// Whether the owner of the screen-control capability is running with its permission. Asked only when
    /// the visual route is otherwise possible.
    pub owners: &'a dyn Fn() -> bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct Candidate {
    pub route: Route,
    pub status: Status,
    pub reason: String,
}

/// Result of planning one purpose. It executes nothing.
#[derive(Clone, Debug)]
pub struct Plan {
    pub candidates: Vec<Candidate>,
    pub chosen: Option<Route>,
    /// Closed code of why nothing can run (the standing of the connection), set only when `chosen` is `None`.
    pub denial: &'static str,
}

/// Ranking key, lower is better, compared in this order: authorization, security, official support,
/// reliability, privacy, side effects.
type Key = (u8, u8, u8, u8, u8, u8);

fn key(route: Route, memory: Option<bool>) -> Key {
    let reliability = match memory {
        Some(true) => 0,
        None => 1,
        Some(false) => 2,
    };
    match route {
        // Authorized by the user's consent per scope; the operation risk (write, public) is the same
        // for every route, so the API route adds none; official API; projected fields only; one call.
        Route::Connection => (0, 0, 0, reliability, 0, 0),
        // Authorized only by a standing exception; drives a screen (highest security risk); not an
        // official channel; content passes through the screen; several UI actions.
        Route::Visual => (1, 1, 1, reliability, 1, 1),
    }
}

fn provider_note(purpose: &Purpose, standing: Standing) -> (Status, String) {
    let name = purpose.provider_label;
    match standing {
        Standing::NoBackend => (
            Status::NoApi,
            format!("Sem API de {name} neste ambiente: nenhum servidor configurado"),
        ),
        Standing::NoAccount => (
            Status::NotConnected,
            format!("Nenhuma conta {name} conectada"),
        ),
        Standing::Disconnected => (
            Status::NotConnected,
            format!("A conta {name} está desconectada"),
        ),
        Standing::Usable => (
            Status::Available,
            format!("Conta {name} conectada com o escopo concedido"),
        ),
        Standing::Expired => (
            Status::Expired,
            format!("O token da conta {name} expirou: renove a conta"),
        ),
        Standing::Reauth => (
            Status::Expired,
            format!("A conta {name} precisa autenticar de novo"),
        ),
        Standing::ScopeNotGranted => (
            Status::ScopeNotGranted,
            format!("A conta {name} não concedeu o escopo desta finalidade"),
        ),
        Standing::Unavailable => (
            Status::Disabled,
            format!("A conta {name} está conectando, offline ou com erro agora"),
        ),
    }
}

fn last_note(memory: Option<bool>) -> &'static str {
    match memory {
        Some(true) => " (último resultado: ok)",
        Some(false) => " (último resultado: falhou)",
        None => "",
    }
}

fn visual_candidate(
    purpose: &Purpose,
    standing: Standing,
    allowed: bool,
    facts: &Facts,
    memory: Option<bool>,
) -> Candidate {
    let (status, reason) = if !purpose.visual {
        (
            Status::Disabled,
            "Esta finalidade não tem rota visual".to_owned(),
        )
    } else if !allowed {
        (
            Status::VisualNotAllowed,
            "Fallback visual desligado para esta finalidade (padrão); só você pode ligar"
                .to_owned(),
        )
    } else if standing == Standing::Usable {
        (
            Status::Disabled,
            "A API está disponível: o visual só entra quando não há conexão".to_owned(),
        )
    } else if !standing.fallback_eligible() {
        (
            Status::Disabled,
            "A conta existe com token expirado, reautenticação ou escopo negado: o visual nunca contorna a credencial"
                .to_owned(),
        )
    } else if !facts.synthetic {
        (
            Status::Disabled,
            "O site sintético não está habilitado neste ambiente".to_owned(),
        )
    } else if !(facts.owners)() {
        (
            Status::Disabled,
            "O controle de tela (computer_control) não está ativo com permissão".to_owned(),
        )
    } else {
        (
            Status::Available,
            format!(
                "Permitido por você; sem conexão; a publicação ainda exige sua aprovação{}",
                last_note(memory)
            ),
        )
    };
    Candidate {
        route: Route::Visual,
        status,
        reason,
    }
}

/// Plans one purpose. Pure: reads its inputs and returns the choice.
pub fn plan(
    purpose: &Purpose,
    facts: &Facts,
    visual_allowed: bool,
    memory: &BTreeMap<(&'static str, Route), bool>,
) -> Plan {
    let remembered = |route| memory.get(&(purpose.id, route)).copied();
    let (status, mut reason) = provider_note(purpose, facts.standing);
    if status == Status::Available {
        reason.push_str(last_note(remembered(Route::Connection)));
    }
    let connection = Candidate {
        route: Route::Connection,
        status,
        reason,
    };
    let visual = visual_candidate(
        purpose,
        facts.standing,
        visual_allowed,
        facts,
        remembered(Route::Visual),
    );
    let candidates = vec![connection, visual];
    let chosen = choose(&candidates, remembered);
    Plan {
        denial: if chosen.is_some() {
            ""
        } else {
            facts.standing.code()
        },
        candidates,
        chosen,
    }
}

/// Best available candidate by the ranking key; ties keep the table order.
fn choose(candidates: &[Candidate], memory: impl Fn(Route) -> Option<bool>) -> Option<Route> {
    candidates
        .iter()
        .filter(|c| c.status == Status::Available)
        .min_by_key(|c| key(c.route, memory(c.route)))
        .map(|c| c.route)
}

/// `route_create_issue` arguments: exactly `title` and an optional `body`. Anything else is refused,
/// so a model cannot pass a route, a grant or a visual switch through the tool.
pub fn parse_args(args: &Value) -> Result<(String, Option<String>), &'static str> {
    let object = args.as_object().ok_or("invalid_args")?;
    if object.keys().any(|k| k != "title" && k != "body") {
        return Err("invalid_args");
    }
    let text = |value: &Value, max: usize| {
        value
            .as_str()
            .filter(|s| {
                s.len() <= max && s.chars().all(|c| !c.is_control() || c == '\n' || c == '\t')
            })
            .map(str::to_owned)
    };
    let title = object
        .get("title")
        .and_then(|v| text(v, TITLE_MAX))
        .filter(|t| !t.trim().is_empty())
        .ok_or("invalid_args")?;
    let body = match object.get("body") {
        None => None,
        Some(v) => Some(text(v, BODY_MAX).ok_or("invalid_args")?),
    };
    Ok((title, body))
}

/// Whether the visual route can type this text: one control-free line within the `ui_type` limit.
pub fn visual_text_ok(title: &str, body: &str) -> bool {
    let line = |s: &str| s.len() <= VISUAL_TEXT_MAX && !s.chars().any(char::is_control);
    !title.is_empty() && line(title) && line(body)
}

/// `registry.json`: version 1, strict, CAS on `revision`, 0600 (written by the storage layer).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Ledger {
    pub version: u16,
    pub revision: u64,
    /// Purposes for which the user allowed the visual fallback.
    #[serde(default)]
    pub visual_allowed: Vec<String>,
}

impl Default for Ledger {
    fn default() -> Self {
        Self {
            version: LEDGER_VERSION,
            revision: 0,
            visual_allowed: Vec::new(),
        }
    }
}

impl Ledger {
    fn validate(&self) -> bool {
        self.version == LEDGER_VERSION
            && self.visual_allowed.iter().enumerate().all(|(i, id)| {
                purpose(id).is_some_and(|p| p.visual) && !self.visual_allowed[..i].contains(id)
            })
    }
}

#[derive(Debug, Serialize)]
pub struct PurposeView {
    pub id: &'static str,
    pub label: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub route_chosen: Option<Route>,
    pub candidates: Vec<Candidate>,
}

/// Snapshot block `registry`. Names, statuses and fixed texts only: no account, token or content.
#[derive(Debug, Serialize)]
pub struct View {
    pub revision: u64,
    pub purposes: Vec<PurposeView>,
    pub visual_allowed: Vec<String>,
}

/// Registry state owned by the Core: the user's visual permission (persisted) and route results (memory).
#[derive(Default)]
pub struct Registry {
    ledger: Ledger,
    storage_error: bool,
    /// Last result per purpose and route; `true` means the last run succeeded.
    memory: BTreeMap<(&'static str, Route), bool>,
    /// Proposals of the connection route waiting for their result, with the purpose they serve.
    waiting: BTreeMap<String, &'static str>,
}

impl Registry {
    /// Loads `registry.json`. A damaged file leaves the fallback off and refuses changes.
    pub fn configure(&mut self, storage: &Storage) {
        match storage.registry_ledger() {
            Ok(ledger) if ledger.validate() => self.ledger = ledger,
            _ => self.storage_error = true,
        }
    }

    pub fn revision(&self) -> u64 {
        self.ledger.revision
    }

    pub fn visual_allowed(&self, id: &str) -> bool {
        !self.storage_error && self.ledger.visual_allowed.iter().any(|p| p == id)
    }

    pub fn plan(&self, purpose: &Purpose, facts: &Facts) -> Plan {
        plan(
            purpose,
            facts,
            self.visual_allowed(purpose.id),
            &self.memory,
        )
    }

    /// Snapshot block. `gather` returns, for a purpose and whether its visual fallback is allowed, the
    /// standing of the provider, whether the synthetic world is on and whether the screen owner runs.
    pub fn view(&self, gather: impl Fn(&Purpose, bool) -> (Standing, bool, bool)) -> View {
        let purposes = PURPOSES
            .iter()
            .map(|p| {
                let (standing, synthetic, owners) = gather(p, self.visual_allowed(p.id));
                let owners = move || owners;
                let plan = self.plan(
                    p,
                    &Facts {
                        standing,
                        synthetic,
                        owners: &owners,
                    },
                );
                PurposeView {
                    id: p.id,
                    label: p.label,
                    route_chosen: plan.chosen,
                    candidates: plan.candidates,
                }
            })
            .collect();
        View {
            revision: self.ledger.revision,
            purposes,
            visual_allowed: if self.storage_error {
                Vec::new()
            } else {
                self.ledger.visual_allowed.clone()
            },
        }
    }

    pub fn check_revision(&self, revision: Option<u64>) -> Result<(), &'static str> {
        if self.storage_error {
            return Err("registry_storage_error");
        }
        match revision {
            Some(seen) if seen != self.ledger.revision => Err("stale_registry_revision"),
            _ => Ok(()),
        }
    }

    /// The user's switch for one purpose. Setting the value it already has changes nothing.
    pub fn allow_visual(
        &mut self,
        storage: &Storage,
        id: &str,
        enabled: bool,
        revision: Option<u64>,
    ) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let Some(found) = purpose(id) else {
            return "unknown_purpose";
        };
        if !found.visual {
            return "no_visual_route";
        }
        if self.visual_allowed(id) == enabled {
            return "ok";
        }
        let mut next = self.ledger.clone();
        if enabled {
            next.visual_allowed.push(found.id.to_owned());
            next.visual_allowed.sort();
        } else {
            next.visual_allowed.retain(|p| p != id);
        }
        let Some(revision) = next.revision.checked_add(1) else {
            return "registry_revision_exhausted";
        };
        next.revision = revision;
        if !next.validate() || storage.save_registry_ledger(&next).is_err() {
            return "registry_storage_error";
        }
        self.ledger = next;
        "ok"
    }

    /// A connection-route proposal now waits for its outcome.
    pub fn expect(&mut self, proposal: &str, purpose: &'static str) {
        if self.waiting.len() >= 16 {
            self.waiting.clear();
        }
        self.waiting.insert(proposal.to_owned(), purpose);
    }

    /// The outcome of a proposal of the connection route (executed or failed). Other proposals are ignored.
    pub fn settled(&mut self, proposal: &str, ok: bool) {
        if let Some(purpose) = self.waiting.remove(proposal) {
            self.memory.insert((purpose, Route::Connection), ok);
        }
    }

    pub fn record(&mut self, purpose: &'static str, route: Route, ok: bool) {
        self.memory.insert((purpose, route), ok);
    }
}

/// Visual route for `create_issue`: opens the fake site, then clicks and types through the services of the
/// bridge tools (`ui_tree`, `ui_click`, `ui_type`), each with the screen epoch the previous reply returned,
/// and finally reads the world back. `serve` runs one service; the caller checks owners and audits there.
pub fn visual_create_issue(
    dir: &Path,
    title: &str,
    body: &str,
    serve: &mut dyn FnMut(&'static str, Value) -> Result<Value, &'static str>,
) -> Result<Value, &'static str> {
    if !visual_text_ok(title, body) {
        return Err("invalid_args");
    }
    world::open_site(dir)?;
    let tree = serve("input.a11y_tree", json!({}))?;
    let elements = tree["elements"].as_array().ok_or("site_unavailable")?;
    for id in ["issue_title", "issue_body", "issue_submit"] {
        if !elements.iter().any(|e| e["id"] == id) {
            return Err("site_unavailable");
        }
    }
    let mut epoch = tree["epoch"].as_u64().ok_or("site_unavailable")?;
    let mut ui = |service: &'static str, fields: Value| -> Result<Value, &'static str> {
        let mut args = fields;
        args["epoch"] = json!(epoch);
        let reply = serve(service, args)?;
        epoch = reply["epoch"].as_u64().ok_or("site_unavailable")?;
        Ok(reply)
    };
    ui("input.click", json!({"element": "issue_title"}))?;
    ui("input.type", json!({"text": title}))?;
    if !body.is_empty() {
        ui("input.click", json!({"element": "issue_body"}))?;
        ui("input.type", json!({"text": body}))?;
    }
    let submitted = ui("input.click", json!({"element": "issue_submit"}))?;
    let number = submitted["issue"].as_u64().ok_or("verify_failed")?;
    // Post-verify: the issue is on the site with the same title and body.
    match world::site_issue(dir, title, body)? {
        Some(found) if found == number => Ok(json!({
            "route": "visual",
            "number": number,
            "title": title,
            "verified": true,
        })),
        _ => Err("verify_failed"),
    }
}

/// Bridge tools the visual route drives; the owner of each must run with its permission.
const VISUAL_BRIDGES: [&str; 3] = ["ui_tree", "ui_click", "ui_type"];

/// Whether the agent tool of the purpose exists in this run: only while the github fake is configured.
pub fn tool_enabled() -> bool {
    crate::connections::has_fake("github")
}

impl Core {
    /// Owners of the screen-control capabilities are running with their approved permission.
    pub(crate) fn visual_owners(&self) -> bool {
        VISUAL_BRIDGES
            .iter()
            .all(|name| tools::bridge(name).is_some_and(|b| self.bridge_owner(b).is_ok()))
    }

    fn registry_gather(&self, purpose: &Purpose, allowed: bool) -> (Standing, bool, bool) {
        let standing = self.connections.standing(purpose.provider, purpose.scope());
        let synthetic = self.agent.options.synthetic;
        // Asked only when the answer can matter: the owner lookup walks the plugin view.
        let owners = allowed
            && synthetic
            && purpose.visual
            && standing.fallback_eligible()
            && self.visual_owners();
        (standing, synthetic, owners)
    }

    /// Plan of one purpose from the live state of the connections, the world and the plugins.
    pub(crate) fn registry_plan_for(&self, purpose: &Purpose) -> Plan {
        let standing = self.connections.standing(purpose.provider, purpose.scope());
        let owners = || self.visual_owners();
        self.registry.plan(
            purpose,
            &Facts {
                standing,
                synthetic: self.agent.options.synthetic,
                owners: &owners,
            },
        )
    }

    pub(crate) fn registry_view(&self) -> View {
        self.registry
            .view(|purpose, allowed| self.registry_gather(purpose, allowed))
    }

    /// `registry_plan`: `ok` when a route would run, `route_unavailable` when none would. Nothing runs
    /// and no request leaves the Core; the answer is in the snapshot block.
    pub(crate) fn registry_plan_op(&self, id: &str) -> &'static str {
        match purpose(id) {
            None => "unknown_purpose",
            Some(found) if self.registry_plan_for(found).chosen.is_some() => "ok",
            Some(_) => "route_unavailable",
        }
    }

    /// `registry_allow_visual`: only the user's request reaches this; no tool or model call does.
    pub(crate) fn registry_allow_op(
        &mut self,
        request_id: String,
        storage: Option<&Storage>,
        id: &str,
        enabled: bool,
        revision: Option<u64>,
    ) -> &'static str {
        let Some(storage) = storage else {
            return "registry_unavailable";
        };
        let before = self.registry.revision();
        let code = self.registry.allow_visual(storage, id, enabled, revision);
        if code == "ok" && self.registry.revision() != before {
            let kind = if enabled {
                "registry_visual_allowed"
            } else {
                "registry_visual_revoked"
            };
            self.emit(request_id, None, kind);
        }
        code
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn owners_ok() -> bool {
        true
    }

    fn facts(standing: Standing, synthetic: bool) -> Facts<'static> {
        Facts {
            standing,
            synthetic,
            owners: &owners_ok,
        }
    }

    fn create() -> &'static Purpose {
        purpose(CREATE_ISSUE).unwrap()
    }

    fn mem() -> BTreeMap<(&'static str, Route), bool> {
        BTreeMap::new()
    }

    fn statuses(plan: &Plan) -> Vec<Status> {
        plan.candidates.iter().map(|c| c.status).collect()
    }

    #[test]
    fn the_connection_wins_when_it_is_usable_even_if_visual_is_allowed() {
        let plan = plan(create(), &facts(Standing::Usable, true), true, &mem());
        assert_eq!(plan.chosen, Some(Route::Connection));
        assert_eq!(statuses(&plan), [Status::Available, Status::Disabled]);
        assert!(plan.candidates.iter().all(|c| !c.reason.is_empty()));
        assert_eq!(plan.denial, "");
    }

    #[test]
    fn no_connection_means_visual_only_when_the_user_allowed_it() {
        for standing in [
            Standing::NoAccount,
            Standing::Disconnected,
            Standing::NoBackend,
        ] {
            let off = plan(create(), &facts(standing, true), false, &mem());
            assert_eq!(off.chosen, None, "{standing:?}");
            assert_eq!(off.candidates[1].status, Status::VisualNotAllowed);
            let on = plan(create(), &facts(standing, true), true, &mem());
            assert_eq!(on.chosen, Some(Route::Visual), "{standing:?}");
            assert_eq!(on.candidates[1].status, Status::Available);
        }
        let off = plan(create(), &facts(Standing::NoAccount, true), false, &mem());
        assert_eq!(off.denial, "not_connected");
        assert_eq!(off.candidates[0].status, Status::NotConnected);
        let none = plan(create(), &facts(Standing::NoBackend, true), false, &mem());
        assert_eq!(none.candidates[0].status, Status::NoApi);
    }

    #[test]
    fn a_credential_problem_is_never_worked_around() {
        let cases = [
            (Standing::Expired, Status::Expired, "expired"),
            (Standing::Reauth, Status::Expired, "reauth_required"),
            (
                Standing::ScopeNotGranted,
                Status::ScopeNotGranted,
                "scope_not_granted",
            ),
            (Standing::Unavailable, Status::Disabled, "unavailable"),
        ];
        for (standing, status, code) in cases {
            let plan = plan(create(), &facts(standing, true), true, &mem());
            assert_eq!(plan.chosen, None, "{standing:?}");
            assert_eq!(plan.candidates[0].status, status);
            assert_eq!(plan.candidates[1].status, Status::Disabled);
            assert_eq!(plan.denial, code);
        }
    }

    #[test]
    fn visual_needs_the_synthetic_site_and_the_screen_owner() {
        let plan_no_world = plan(create(), &facts(Standing::NoAccount, false), true, &mem());
        assert_eq!(plan_no_world.chosen, None);
        assert_eq!(plan_no_world.candidates[1].status, Status::Disabled);
        let no_owner = Facts {
            standing: Standing::NoAccount,
            synthetic: true,
            owners: &|| false,
        };
        let plan_no_owner = plan(create(), &no_owner, true, &mem());
        assert_eq!(plan_no_owner.chosen, None);
        assert_eq!(plan_no_owner.candidates[1].status, Status::Disabled);
    }

    #[test]
    fn other_purposes_have_no_visual_route() {
        for id in ["list_events", "read_state"] {
            let p = purpose(id).unwrap();
            let plan = plan(p, &facts(Standing::NoAccount, true), true, &mem());
            assert_eq!(plan.chosen, None, "{id}");
            assert_eq!(plan.candidates[1].status, Status::Disabled);
        }
        let p = purpose("read_state").unwrap();
        let plan = plan(p, &facts(Standing::Usable, true), false, &mem());
        assert_eq!(plan.chosen, Some(Route::Connection));
    }

    #[test]
    fn ranking_orders_authorization_security_support_reliability_privacy_effects() {
        // The connection beats the visual route on every criterion, so it wins even with a worse record.
        assert!(key(Route::Connection, Some(false)) < key(Route::Visual, Some(true)));
        // Among equals, a remembered success beats an unknown, which beats a failure.
        assert!(key(Route::Connection, Some(true)) < key(Route::Connection, None));
        assert!(key(Route::Connection, None) < key(Route::Connection, Some(false)));
        // Reliability only breaks ties when the earlier criteria are equal.
        let a: Key = (0, 0, 0, 2, 0, 0);
        let b: Key = (0, 1, 0, 0, 0, 0);
        assert!(a < b, "security outranks reliability");
        let both = [
            Candidate {
                route: Route::Visual,
                status: Status::Available,
                reason: String::new(),
            },
            Candidate {
                route: Route::Connection,
                status: Status::Available,
                reason: String::new(),
            },
        ];
        assert_eq!(choose(&both, |_| None), Some(Route::Connection));
        assert_eq!(choose(&both[..1], |_| Some(false)), Some(Route::Visual));
    }

    #[test]
    fn memory_shows_in_the_reason_of_an_available_route() {
        let mut memory = mem();
        memory.insert((CREATE_ISSUE, Route::Connection), false);
        let plan = plan(create(), &facts(Standing::Usable, true), false, &memory);
        assert!(plan.candidates[0].reason.contains("falhou"));
        assert_eq!(plan.chosen, Some(Route::Connection));
    }

    #[test]
    fn tool_arguments_are_exactly_title_and_body() {
        assert_eq!(
            parse_args(&json!({"title": "a"})),
            Ok(("a".to_owned(), None))
        );
        assert_eq!(
            parse_args(&json!({"title": "a", "body": "b"})),
            Ok(("a".to_owned(), Some("b".to_owned())))
        );
        for bad in [
            json!({}),
            json!({"title": ""}),
            json!({"title": "  "}),
            json!({"title": "a", "visual_allowed": true}),
            json!({"title": "a", "route": "visual"}),
            json!({"title": "a", "repo": "x/y"}),
            json!({"title": 3}),
            json!({"title": "a\u{7}"}),
            json!({"title": "x".repeat(257)}),
            json!({"title": "a", "body": "y".repeat(4097)}),
            json!("a"),
        ] {
            assert_eq!(parse_args(&bad), Err("invalid_args"), "{bad}");
        }
        assert!(visual_text_ok("t", ""));
        assert!(!visual_text_ok("t", &"x".repeat(65)));
        assert!(!visual_text_ok("a\nb", ""));
        assert!(!visual_text_ok("", "b"));
    }

    #[test]
    fn the_ledger_is_strict_and_default_off() {
        let ledger = Ledger::default();
        assert!(ledger.validate());
        assert!(ledger.visual_allowed.is_empty());
        let bad = [
            Ledger {
                visual_allowed: vec!["nope".into()],
                ..Ledger::default()
            },
            Ledger {
                visual_allowed: vec!["list_events".into()],
                ..Ledger::default()
            },
            Ledger {
                visual_allowed: vec![CREATE_ISSUE.into(), CREATE_ISSUE.into()],
                ..Ledger::default()
            },
            Ledger {
                version: 2,
                ..Ledger::default()
            },
        ];
        for ledger in bad {
            assert!(!ledger.validate(), "{ledger:?}");
        }
        assert!(serde_json::from_str::<Ledger>(r#"{"version":1,"revision":0,"extra":1}"#).is_err());
        assert!(serde_json::from_str::<Ledger>(r#"{"version":1,"revision":0}"#).is_ok());
    }

    #[test]
    fn allowing_visual_is_cas_persistent_and_revocable() {
        let temp = tempfile::tempdir().unwrap();
        let dir = temp.path().join("root");
        let storage = Storage::open(&dir).unwrap();
        let mut registry = Registry::default();
        registry.configure(&storage);
        assert!(!registry.visual_allowed(CREATE_ISSUE));
        assert_eq!(
            registry.allow_visual(&storage, "nope", true, None),
            "unknown_purpose"
        );
        assert_eq!(
            registry.allow_visual(&storage, "read_state", true, None),
            "no_visual_route"
        );
        assert_eq!(
            registry.allow_visual(&storage, CREATE_ISSUE, true, Some(5)),
            "stale_registry_revision"
        );
        assert_eq!(
            registry.allow_visual(&storage, CREATE_ISSUE, true, Some(0)),
            "ok"
        );
        assert!(registry.visual_allowed(CREATE_ISSUE));
        assert_eq!(
            registry.allow_visual(&storage, CREATE_ISSUE, true, None),
            "ok"
        );
        assert_eq!(registry.ledger.revision, 1, "the same value does not bump");
        let mut again = Registry::default();
        again.configure(&storage);
        assert!(again.visual_allowed(CREATE_ISSUE));
        assert_eq!(
            registry.allow_visual(&storage, CREATE_ISSUE, false, Some(1)),
            "ok"
        );
        assert!(!registry.visual_allowed(CREATE_ISSUE));
        let mode = {
            use std::os::unix::fs::PermissionsExt;
            std::fs::metadata(dir.join("registry.json"))
                .unwrap()
                .permissions()
                .mode()
        };
        assert_eq!(mode & 0o777, 0o600);
    }

    #[test]
    fn a_damaged_ledger_keeps_the_fallback_off_and_refuses_changes() {
        let temp = tempfile::tempdir().unwrap();
        let dir = temp.path().join("root");
        let storage = Storage::open(&dir).unwrap();
        std::fs::write(
            dir.join("registry.json"),
            br#"{"version":1,"revision":3,"visual_allowed":["x"]}"#,
        )
        .unwrap();
        std::fs::set_permissions(
            dir.join("registry.json"),
            std::os::unix::fs::PermissionsExt::from_mode(0o600),
        )
        .unwrap();
        let mut registry = Registry::default();
        registry.configure(&storage);
        assert!(!registry.visual_allowed("x"));
        assert!(!registry.visual_allowed(CREATE_ISSUE));
        assert_eq!(
            registry.allow_visual(&storage, CREATE_ISSUE, true, None),
            "registry_storage_error"
        );
    }

    #[test]
    fn route_results_are_remembered_per_purpose_and_route() {
        let mut registry = Registry::default();
        registry.expect("tool_1", CREATE_ISSUE);
        registry.settled("tool_2", true);
        assert!(registry.memory.is_empty());
        registry.settled("tool_1", false);
        assert_eq!(
            registry.memory.get(&(CREATE_ISSUE, Route::Connection)),
            Some(&false)
        );
        registry.record(CREATE_ISSUE, Route::Visual, true);
        assert_eq!(
            registry.memory.get(&(CREATE_ISSUE, Route::Visual)),
            Some(&true)
        );
    }

    #[test]
    fn the_visual_script_publishes_and_verifies_or_fails_closed() {
        let dir = tempfile::tempdir().unwrap();
        let mut calls = Vec::new();
        let result = visual_create_issue(dir.path(), "Titulo", "Corpo", &mut |service, args| {
            calls.push(service);
            world::serve(dir.path(), service, &args)
        })
        .unwrap();
        assert_eq!(result["number"], 1);
        assert_eq!(
            calls,
            [
                "input.a11y_tree",
                "input.click",
                "input.type",
                "input.click",
                "input.type",
                "input.click"
            ]
        );
        assert_eq!(
            world::site_issue(dir.path(), "Titulo", "Corpo"),
            Ok(Some(1))
        );
        // A stale screen stops the script before anything is submitted.
        let other = tempfile::tempdir().unwrap();
        let mut bumped = false;
        let err = visual_create_issue(other.path(), "T", "", &mut |service, args| {
            if service == "input.type" && !bumped {
                bumped = true;
                world::mutate(other.path(), |w| {
                    w.screen.epoch += 1;
                    Ok(())
                })?;
            }
            world::serve(other.path(), service, &args)
        })
        .unwrap_err();
        assert_eq!(err, "stale_screen");
        assert_eq!(world::site_issue(other.path(), "T", ""), Ok(None));
        assert_eq!(
            visual_create_issue(other.path(), &"x".repeat(65), "", &mut |_, _| Ok(json!({}))),
            Err("invalid_args")
        );
    }
}
