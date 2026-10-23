//! C1/C2 LLM configuration: provider ids, endpoint rules, and the `llm-config.json` ledger with a
//! revision CAS, a last-known-good copy (LKG) and an optional fallback route. Plugins never see
//! secrets: `HostAuth` is the Core snapshot the plugin host uses to gate `llm.http`, and `Access`
//! redacts its key in Debug output.
use crate::{
    secrets::{Flags, Secrets},
    storage::Storage,
};
use serde::{de::Error as _, Deserialize, Deserializer, Serialize, Serializer};
use std::{fmt, net::IpAddr};

/// Hub permission id for brokered LLM HTTP. The Hub accepts only `[a-z0-9_-]` ids, so the
/// contract name `network.llm` is spelled with an underscore.
pub const NETWORK_PERMISSION: &str = "network_llm";
/// Hub permission id for the plugin's own settings store (`settings.get` / `settings.put`).
pub const SETTINGS_PERMISSION: &str = "storage_settings";
/// Loopback address of the local providers. Exact literal: local routes never resolve names.
pub const LOCAL_HOST: &str = "127.0.0.1";
/// Lowest port a local provider may use; privileged ports are refused.
pub const MIN_LOCAL_PORT: u16 = 1024;
const MAX_MODEL: usize = 128;
const MAX_URL: usize = 200;
const BAD_CONFIG: &str = "invalid_config";

/// Remote providers. Their keys live in the vault; `custom` takes a configured https URL.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Provider {
    Openrouter,
    Opencode,
    Google,
    Custom,
}

impl Provider {
    pub fn parse(id: &str) -> Option<Self> {
        match id {
            "openrouter" => Some(Self::Openrouter),
            "opencode" => Some(Self::Opencode),
            "google" => Some(Self::Google),
            "custom" => Some(Self::Custom),
            _ => None,
        }
    }
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Openrouter => "openrouter",
            Self::Opencode => "opencode",
            Self::Google => "google",
            Self::Custom => "custom",
        }
    }
    /// Fixed base URL of a built-in provider; `custom` uses the configured URL instead.
    pub fn fixed_base(self) -> Option<&'static str> {
        match self {
            Self::Openrouter => Some("https://openrouter.ai/api/v1"),
            Self::Opencode => Some("https://opencode.ai/zen/v1"),
            Self::Google => Some("https://generativelanguage.googleapis.com/v1beta/openai"),
            Self::Custom => None,
        }
    }
}

/// Every provider id the Core accepts: the remote ones plus the keyless loopback `local` and
/// `ollama` providers. Kept apart from `Provider` so the vault never needs a slot for them.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProviderId {
    Cloud(Provider),
    Local,
    Ollama,
}

impl ProviderId {
    pub fn parse(id: &str) -> Option<Self> {
        match id {
            "local" => Some(Self::Local),
            "ollama" => Some(Self::Ollama),
            other => Provider::parse(other).map(Self::Cloud),
        }
    }
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Cloud(provider) => provider.as_str(),
            Self::Local => "local",
            Self::Ollama => "ollama",
        }
    }
    /// Keyless, consentless, loopback-only providers.
    pub fn is_local(self) -> bool {
        !matches!(self, Self::Cloud(_))
    }
    pub fn cloud(self) -> Option<Provider> {
        match self {
            Self::Cloud(provider) => Some(provider),
            Self::Local | Self::Ollama => None,
        }
    }
}

impl Serialize for ProviderId {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(self.as_str())
    }
}

impl<'de> Deserialize<'de> for ProviderId {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let text = String::deserialize(deserializer)?;
        Self::parse(&text).ok_or_else(|| D::Error::custom("unknown provider"))
    }
}

/// One provider route as the user chose it. Never holds a key.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Route {
    pub provider: ProviderId,
    pub model: String,
    #[serde(default)]
    pub custom_url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub local_port: Option<u16>,
}

/// Client input for the optional fallback route; the same rules as the primary route apply.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FallbackInput {
    pub provider: String,
    pub model: String,
    #[serde(default)]
    pub custom_url: Option<String>,
    #[serde(default)]
    pub local_port: Option<u16>,
}

/// Core-owned configuration, persisted in `llm-config.json` (no secrets).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LlmConfig {
    pub provider: ProviderId,
    pub model: String,
    #[serde(default)]
    pub custom_url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub local_port: Option<u16>,
    #[serde(default)]
    pub cloud_consent: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fallback: Option<Route>,
}

/// Versioned ledger with a CAS revision; `config: null` means nothing configured yet.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LlmLedger {
    pub version: u16,
    pub revision: u64,
    #[serde(default)]
    pub config: Option<LlmConfig>,
    /// Last-known-good primary route, recorded by `llm_mark_good`; never carries a fallback.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lkg: Option<LlmConfig>,
}

impl Default for LlmLedger {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            config: None,
            lkg: None,
        }
    }
}

impl LlmLedger {
    pub(crate) fn validate(&self) -> bool {
        self.version == 1
    }
}

fn valid_model(model: &str) -> bool {
    (1..=MAX_MODEL).contains(&model.len())
        && model
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b':' | b'/' | b'-'))
}

/// Base URL of a local provider; the only place the loopback literal and `/v1` are joined.
pub fn local_base(port: u16) -> String {
    format!("http://{LOCAL_HOST}:{port}/v1")
}

impl Route {
    /// Client input to a route. `local_port` is required for local providers and ignored for the
    /// rest, so a cloud route can never carry a port.
    fn from_input(
        provider: &str,
        model: &str,
        custom_url: Option<String>,
        local_port: Option<u16>,
    ) -> Result<Self, &'static str> {
        let provider = ProviderId::parse(provider).ok_or(BAD_CONFIG)?;
        let local_port = match (provider.is_local(), local_port) {
            (true, Some(port)) => Some(port),
            (true, None) => return Err(BAD_CONFIG),
            (false, _) => None,
        };
        Ok(Self {
            provider,
            model: model.to_owned(),
            custom_url,
            local_port,
        })
    }
    /// Shape rules shared by the primary and the fallback route. Cloud routes take no port; local
    /// routes take no URL and need a port of at least `MIN_LOCAL_PORT`; `custom` needs a valid URL.
    pub fn validate(&self, allow_loopback: bool) -> Result<(), &'static str> {
        if !valid_model(&self.model) {
            return Err(BAD_CONFIG);
        }
        match self.provider {
            ProviderId::Cloud(Provider::Custom) => {
                let url = self.custom_url.as_deref().ok_or(BAD_CONFIG)?;
                parse_endpoint(url, allow_loopback).map_err(|_| BAD_CONFIG)?;
                if self.local_port.is_some() {
                    return Err(BAD_CONFIG);
                }
                Ok(())
            }
            ProviderId::Cloud(_) => {
                if self.custom_url.is_some() || self.local_port.is_some() {
                    return Err(BAD_CONFIG);
                }
                Ok(())
            }
            ProviderId::Local | ProviderId::Ollama => {
                let port_ok = self.local_port.is_some_and(|port| port >= MIN_LOCAL_PORT);
                if self.custom_url.is_some() || !port_ok {
                    return Err(BAD_CONFIG);
                }
                Ok(())
            }
        }
    }
}

impl LlmConfig {
    /// The primary route, without its fallback.
    pub fn route(&self) -> Route {
        Route {
            provider: self.provider,
            model: self.model.clone(),
            custom_url: self.custom_url.clone(),
            local_port: self.local_port,
        }
    }
    pub fn validate(&self, allow_loopback: bool) -> Result<(), &'static str> {
        self.route().validate(allow_loopback)?;
        match &self.fallback {
            Some(fallback) => fallback.validate(allow_loopback),
            None => Ok(()),
        }
    }
}

/// A configuration request from the client, before validation.
#[derive(Debug, Clone)]
pub struct ConfigInput {
    pub provider: String,
    pub model: String,
    pub custom_url: Option<String>,
    pub local_port: Option<u16>,
    pub fallback: Option<FallbackInput>,
    pub cloud_consent: bool,
}

impl ConfigInput {
    fn build(self) -> Result<LlmConfig, &'static str> {
        let primary = Route::from_input(
            &self.provider,
            &self.model,
            self.custom_url,
            self.local_port,
        )?;
        let fallback = match self.fallback {
            Some(input) => Some(Route::from_input(
                &input.provider,
                &input.model,
                input.custom_url,
                input.local_port,
            )?),
            None => None,
        };
        Ok(LlmConfig {
            provider: primary.provider,
            model: primary.model,
            custom_url: primary.custom_url,
            local_port: primary.local_port,
            cloud_consent: self.cloud_consent,
            fallback,
        })
    }
}

/// Validated network target of an endpoint URL (no userinfo, query or fragment).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Endpoint {
    pub https: bool,
    pub host: String,
    pub port: u16,
    /// Base path without trailing slash; `/chat/completions` is appended by the broker.
    pub path: String,
    pub loopback: bool,
}

fn port_of(text: &str) -> Option<u16> {
    if text.is_empty() || !text.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    text.parse().ok().filter(|p| *p != 0)
}

/// Parses an endpoint base URL. Loopback (IP or `localhost`) needs `allow_loopback` (test mode);
/// `http` is accepted only for loopback; IP literals are accepted only for loopback.
pub fn parse_endpoint(url: &str, allow_loopback: bool) -> Result<Endpoint, &'static str> {
    if url.len() > MAX_URL || !url.bytes().all(|b| b.is_ascii_graphic()) {
        return Err(BAD_CONFIG);
    }
    let (https, rest) = if let Some(rest) = url.strip_prefix("https://") {
        (true, rest)
    } else if let Some(rest) = url.strip_prefix("http://") {
        (false, rest)
    } else {
        return Err(BAD_CONFIG);
    };
    if rest
        .bytes()
        .any(|b| matches!(b, b'@' | b'?' | b'#' | b'\\'))
    {
        return Err(BAD_CONFIG);
    }
    let (authority, path) = match rest.find('/') {
        Some(index) => rest.split_at(index),
        None => (rest, ""),
    };
    let default_port = if https { 443 } else { 80 };
    let (host, port) = if let Some(inner) = authority.strip_prefix('[') {
        let end = inner.find(']').ok_or(BAD_CONFIG)?;
        let after = &inner[end + 1..];
        let port = match after {
            "" => default_port,
            tail => tail.strip_prefix(':').and_then(port_of).ok_or(BAD_CONFIG)?,
        };
        (&inner[..end], port)
    } else {
        match authority.rsplit_once(':') {
            Some((host, port)) => (host, port_of(port).ok_or(BAD_CONFIG)?),
            None => (authority, default_port),
        }
    };
    if host.is_empty() || host.len() > 253 {
        return Err(BAD_CONFIG);
    }
    let ip: Option<IpAddr> = host.parse().ok();
    if ip.is_none() {
        let labels_ok = host.split('.').all(|label| {
            !label.is_empty()
                && label.len() <= 63
                && !label.starts_with('-')
                && !label.ends_with('-')
        });
        let charset_ok = host
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'-' | b'.'));
        // A numeric last label is an IPv4 spelling in disguise (e.g. decimal integers).
        let numeric_tail = host
            .rsplit('.')
            .next()
            .is_some_and(|tail| tail.bytes().all(|b| b.is_ascii_digit()));
        if !labels_ok || !charset_ok || numeric_tail {
            return Err(BAD_CONFIG);
        }
    }
    let loopback = ip.is_some_and(|ip| ip.is_loopback()) || host == "localhost";
    if ip.is_some() && !loopback {
        return Err(BAD_CONFIG);
    }
    if loopback && !allow_loopback {
        return Err(BAD_CONFIG);
    }
    if !https && !loopback {
        return Err(BAD_CONFIG);
    }
    if path.split('/').any(|segment| segment == "..") || path.contains("//") {
        return Err(BAD_CONFIG);
    }
    Ok(Endpoint {
        https,
        host: host.to_owned(),
        port,
        path: path.trim_end_matches('/').to_owned(),
        loopback,
    })
}

/// One route plus the key the Core injects for it. Keys never reach a plugin; Debug redacts them.
#[derive(Clone)]
pub struct Access {
    pub route: Route,
    pub key: Option<String>,
}

impl fmt::Debug for Access {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Access")
            .field("route", &self.route)
            .field("key", &self.key.as_ref().map(|_| "<redacted>"))
            .finish()
    }
}

/// Core-side authority for one plugin invocation. Built once at invoke time from the ledger,
/// the vault and the approval state; the key never leaves the Core except inside the broker.
#[derive(Clone, Debug, Default)]
pub struct HostAuth {
    /// Approved `network_llm` grant.
    pub permission: bool,
    /// Approved `storage_settings` grant.
    pub settings: bool,
    pub cloud_consent: bool,
    pub allow_loopback: bool,
    pub primary: Option<Access>,
    pub fallback: Option<Access>,
}

/// Config view in the snapshot: the configuration, plus `lkg` when a last-known-good exists.
#[derive(Debug, Clone, Serialize)]
pub struct ConfigView {
    #[serde(flatten)]
    pub config: LlmConfig,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub lkg: Option<LlmConfig>,
}

/// Snapshot `llm`: booleans for keys, config without secrets, and the CAS revision.
#[derive(Debug, Clone, Serialize)]
pub struct Snapshot {
    pub revision: u64,
    pub config: Option<ConfigView>,
    pub secrets: Flags,
}

/// Core-owned LLM state: loaded once at boot, updated only through CAS-checked operations.
#[derive(Default)]
pub struct LlmState {
    revision: u64,
    config: Option<LlmConfig>,
    lkg: Option<LlmConfig>,
    secrets: Secrets,
    allow_loopback: bool,
    quarantined: bool,
}

impl LlmState {
    /// Loads both ledgers. Unreadable ledgers quarantine LLM writes and host calls only.
    /// A config that is invalid in the current mode (e.g. loopback without the flag) is ignored.
    pub fn load(storage: &Storage, allow_loopback: bool) -> Self {
        let mut state = Self {
            allow_loopback,
            ..Self::default()
        };
        match storage.llm_ledger() {
            Ok(ledger) if ledger.validate() => {
                state.revision = ledger.revision;
                state.config = ledger
                    .config
                    .filter(|config| config.validate(allow_loopback).is_ok());
                state.lkg = ledger
                    .lkg
                    .filter(|lkg| lkg.fallback.is_none() && lkg.validate(allow_loopback).is_ok());
            }
            _ => state.quarantined = true,
        }
        match storage.llm_secrets() {
            Ok(secrets) if secrets.validate() => state.secrets = secrets,
            _ => state.quarantined = true,
        }
        state
    }
    pub fn snapshot(&self) -> Snapshot {
        Snapshot {
            revision: self.revision,
            config: self.config.clone().map(|config| ConfigView {
                config,
                lkg: self.lkg.clone(),
            }),
            secrets: self.secrets.flags(),
        }
    }
    /// Persists `next` and only then makes it the in-memory state.
    fn commit(&mut self, storage: &Storage, next: LlmLedger) -> Result<(), &'static str> {
        storage
            .save_llm_ledger(&next)
            .map_err(|_| "llm_storage_error")?;
        self.revision = next.revision;
        self.config = next.config;
        self.lkg = next.lkg;
        Ok(())
    }
    fn check_revision(&self, revision: u64) -> Result<(), &'static str> {
        if self.quarantined {
            return Err("llm_storage_error");
        }
        if revision != self.revision {
            return Err("stale_llm_revision");
        }
        Ok(())
    }
    pub fn configure(
        &mut self,
        storage: &Storage,
        revision: u64,
        input: ConfigInput,
    ) -> Result<(), &'static str> {
        self.check_revision(revision)?;
        let config = input.build()?;
        config.validate(self.allow_loopback)?;
        let next = LlmLedger {
            version: 1,
            revision: revision.checked_add(1).ok_or("llm_revision_exhausted")?,
            config: Some(config),
            lkg: self.lkg.clone(),
        };
        self.commit(storage, next)
    }
    /// Promotes the current primary configuration to last-known-good (the fallback is not part of it).
    pub fn mark_good(&mut self, storage: &Storage, revision: u64) -> Result<(), &'static str> {
        self.check_revision(revision)?;
        let config = self.config.clone().ok_or("no_config")?;
        let lkg = LlmConfig {
            fallback: None,
            ..config.clone()
        };
        let next = LlmLedger {
            version: 1,
            revision: revision.checked_add(1).ok_or("llm_revision_exhausted")?,
            config: Some(config),
            lkg: Some(lkg),
        };
        self.commit(storage, next)
    }
    /// Restores the last-known-good primary; the configured fallback is kept as it is.
    pub fn rollback(&mut self, storage: &Storage, revision: u64) -> Result<(), &'static str> {
        self.check_revision(revision)?;
        let lkg = self.lkg.clone().ok_or("no_lkg")?;
        let config = LlmConfig {
            fallback: self.config.as_ref().and_then(|c| c.fallback.clone()),
            ..lkg
        };
        config.validate(self.allow_loopback)?;
        let next = LlmLedger {
            version: 1,
            revision: revision.checked_add(1).ok_or("llm_revision_exhausted")?,
            config: Some(config),
            lkg: self.lkg.clone(),
        };
        self.commit(storage, next)
    }
    pub fn set_secret(
        &mut self,
        storage: &Storage,
        provider: &str,
        key: &str,
    ) -> Result<(), &'static str> {
        let provider = Provider::parse(provider).ok_or("invalid_provider")?;
        if self.quarantined {
            return Err("secrets_storage_error");
        }
        if !crate::secrets::valid_key(key) {
            return Err("invalid_secret");
        }
        let mut next = self.secrets.clone();
        next.set(provider, Some(key.to_owned()));
        storage
            .save_llm_secrets(&next)
            .map_err(|_| "secrets_storage_error")?;
        self.secrets = next;
        Ok(())
    }
    pub fn clear_secret(&mut self, storage: &Storage, provider: &str) -> Result<(), &'static str> {
        let provider = Provider::parse(provider).ok_or("invalid_provider")?;
        if self.quarantined {
            return Err("secrets_storage_error");
        }
        let mut next = self.secrets.clone();
        next.set(provider, None);
        storage
            .save_llm_secrets(&next)
            .map_err(|_| "secrets_storage_error")?;
        self.secrets = next;
        Ok(())
    }
    /// S5 connection token of one account slot (`access` or `refresh`). Core-internal only.
    pub(crate) fn connection_token(&self, account: &str, slot: &str) -> Option<String> {
        if self.quarantined {
            return None;
        }
        self.secrets
            .connection_token(account, slot)
            .map(str::to_owned)
    }
    /// Replaces the access and refresh slots of one account in `secrets.json` (write-only).
    pub(crate) fn set_connection_tokens(
        &mut self,
        storage: &Storage,
        account: &str,
        access: Option<String>,
        refresh: Option<String>,
    ) -> Result<(), &'static str> {
        if self.quarantined {
            return Err("secrets_storage_error");
        }
        // Tokens exist only for an account of the ledger: a removed account never gets orphan secrets back.
        let ledger = storage
            .connections_ledger()
            .map_err(|_| "connections_storage_error")?;
        if !ledger.accounts.iter().any(|a| a.id == account) {
            return Err("unknown_connection");
        }
        let mut next = self.secrets.clone();
        next.set_connection_token(account, "access", access);
        next.set_connection_token(account, "refresh", refresh);
        if !next.validate() {
            return Err("invalid_token");
        }
        storage
            .save_llm_secrets(&next)
            .map_err(|_| "secrets_storage_error")?;
        self.secrets = next;
        Ok(())
    }
    /// Removes both slots of one account from `secrets.json`.
    pub(crate) fn clear_connection(
        &mut self,
        storage: &Storage,
        account: &str,
    ) -> Result<(), &'static str> {
        if self.quarantined {
            return Err("secrets_storage_error");
        }
        let mut next = self.secrets.clone();
        next.clear_connection(account);
        storage
            .save_llm_secrets(&next)
            .map_err(|_| "secrets_storage_error")?;
        self.secrets = next;
        Ok(())
    }
    /// Snapshot for one invocation. `permission` and `settings` are the approved grants.
    pub fn host_auth(&self, permission: bool, settings: bool) -> HostAuth {
        let config = self.config.as_ref().filter(|_| !self.quarantined);
        let access = |route: Route| Access {
            key: route
                .provider
                .cloud()
                .and_then(|provider| self.secrets.get(provider))
                .map(str::to_owned),
            route,
        };
        HostAuth {
            permission,
            settings,
            cloud_consent: config.is_some_and(|c| c.cloud_consent),
            allow_loopback: self.allow_loopback,
            primary: config.map(|c| access(c.route())),
            fallback: config.and_then(|c| c.fallback.clone()).map(access),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn endpoint_rules_allow_only_fixed_https_or_explicit_loopback() {
        for ok in [
            "https://example.com/v1",
            "https://api.example.com:8443/base/",
            "https://generativelanguage.googleapis.com/v1beta/openai",
        ] {
            assert!(parse_endpoint(ok, false).is_ok(), "{ok}");
        }
        for bad in [
            "http://example.com/v1",
            "https://user:pw@example.com/v1",
            "https://example.com/v1?x=1",
            "https://example.com/v1#frag",
            "https://1.2.3.4/v1",
            "https://[2001:db8::1]/v1",
            "https://2130706433/v1",
            "https://127.0.0.1/v1",
            "https://localhost/v1",
            "http://127.0.0.1:9/v1",
            "https://Example.com/v1",
            "https://example.com/../v1",
            "ftp://example.com/v1",
            "https://example.com:0/v1",
        ] {
            assert!(parse_endpoint(bad, false).is_err(), "{bad}");
        }
        assert!(parse_endpoint("http://127.0.0.1:9/v1", true).is_ok());
        assert!(parse_endpoint("http://localhost:9/v1", true).is_ok());
        assert!(parse_endpoint("http://[::1]:9/v1", true).is_ok());
        assert!(parse_endpoint("http://1.2.3.4/v1", true).is_err());
        assert!(parse_endpoint(&format!("https://{}.example/", "a".repeat(190)), false).is_err());
    }

    #[test]
    fn model_and_provider_ids_are_strict() {
        assert!(valid_model("google/gemini-3.5-flash-lite:free"));
        assert!(!valid_model(""));
        assert!(!valid_model("has space"));
        assert!(!valid_model(&"m".repeat(129)));
        assert_eq!(Provider::parse("google"), Some(Provider::Google));
        assert_eq!(Provider::parse("Google"), None);
        assert_eq!(Provider::parse("local"), None);
        assert_eq!(
            Provider::Google.fixed_base(),
            Some("https://generativelanguage.googleapis.com/v1beta/openai")
        );
        assert_eq!(ProviderId::parse("local"), Some(ProviderId::Local));
        assert_eq!(ProviderId::parse("ollama"), Some(ProviderId::Ollama));
        assert!(ProviderId::Local.is_local() && ProviderId::Ollama.is_local());
        assert!(!ProviderId::Cloud(Provider::Google).is_local());
    }

    fn route(provider: &str, url: Option<&str>, port: Option<u16>) -> Result<Route, &'static str> {
        let built = Route::from_input(provider, "m", url.map(str::to_owned), port)?;
        built.validate(false).map(|()| built)
    }

    #[test]
    fn local_routes_need_a_port_of_at_least_1024_and_no_url() {
        assert!(route("local", None, Some(8080)).is_ok());
        assert!(route("ollama", None, Some(11434)).is_ok());
        assert!(route("local", None, Some(65535)).is_ok());
        assert_eq!(route("local", None, None), Err(BAD_CONFIG));
        assert_eq!(route("local", None, Some(1023)), Err(BAD_CONFIG));
        assert_eq!(route("ollama", None, Some(80)), Err(BAD_CONFIG));
        assert_eq!(route("local", None, Some(0)), Err(BAD_CONFIG));
        assert_eq!(
            route("local", Some("http://127.0.0.1:9000/v1"), Some(9000)),
            Err(BAD_CONFIG)
        );
        assert_eq!(
            route("local", Some("http://localhost:9000/v1"), Some(9000)),
            Err(BAD_CONFIG)
        );
    }

    #[test]
    fn cloud_routes_ignore_local_port_and_custom_needs_its_url() {
        let cloud = Route::from_input("google", "m", None, Some(8080)).unwrap();
        assert_eq!(cloud.local_port, None);
        assert!(cloud.validate(false).is_ok());
        assert_eq!(route("custom", None, None), Err(BAD_CONFIG));
        assert_eq!(
            route("google", Some("https://example.com/v1"), None),
            Err(BAD_CONFIG)
        );
        assert!(route("custom", Some("https://example.com/v1"), None).is_ok());
    }

    #[test]
    fn config_requires_custom_url_only_for_custom() {
        let base = LlmConfig {
            provider: ProviderId::Cloud(Provider::Openrouter),
            model: "m".into(),
            custom_url: None,
            local_port: None,
            cloud_consent: false,
            fallback: None,
        };
        assert!(base.validate(false).is_ok());
        let mut with_url = base.clone();
        with_url.custom_url = Some("https://example.com/v1".into());
        assert!(with_url.validate(false).is_err());
        let custom = LlmConfig {
            provider: ProviderId::Cloud(Provider::Custom),
            model: "m".into(),
            custom_url: None,
            local_port: None,
            cloud_consent: false,
            fallback: None,
        };
        assert!(custom.validate(false).is_err());
    }

    #[test]
    fn fallback_is_validated_like_the_primary_route() {
        let input = ConfigInput {
            provider: "google".into(),
            model: "m".into(),
            custom_url: None,
            local_port: None,
            fallback: Some(FallbackInput {
                provider: "ollama".into(),
                model: "m".into(),
                custom_url: None,
                local_port: Some(80),
            }),
            cloud_consent: false,
        };
        let config = input.build().unwrap();
        assert_eq!(config.validate(false), Err(BAD_CONFIG));
    }

    #[test]
    fn config_wire_shape_omits_absent_optional_fields() {
        let config = LlmConfig {
            provider: ProviderId::Cloud(Provider::Google),
            model: "m".into(),
            custom_url: None,
            local_port: None,
            cloud_consent: false,
            fallback: None,
        };
        assert_eq!(
            serde_json::to_value(&config).unwrap(),
            serde_json::json!({"provider": "google", "model": "m", "custom_url": null, "cloud_consent": false})
        );
        let local = LlmConfig {
            provider: ProviderId::Ollama,
            local_port: Some(11434),
            ..config
        };
        assert_eq!(serde_json::to_value(&local).unwrap()["local_port"], 11434);
    }
}
