//! C1 LLM configuration: provider ids, endpoint rules and the `llm-config.json` ledger with
//! revision CAS. Plugins never see this module's secrets; `HostAuth` is the Core snapshot the
//! plugin host uses to gate `llm.http` calls, and it redacts its key in Debug output.
use crate::{
    secrets::{Flags, Secrets},
    storage::Storage,
};
use serde::{Deserialize, Serialize};
use std::{fmt, net::IpAddr};

/// Hub permission id for brokered LLM HTTP. The Hub accepts only `[a-z0-9_-]` ids, so the
/// contract name `network.llm` is spelled with an underscore.
pub const NETWORK_PERMISSION: &str = "network_llm";
const MAX_MODEL: usize = 128;
const MAX_URL: usize = 200;
const BAD_CONFIG: &str = "invalid_config";

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

/// Core-owned configuration, persisted in `llm-config.json` (no secrets).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LlmConfig {
    pub provider: Provider,
    pub model: String,
    #[serde(default)]
    pub custom_url: Option<String>,
    #[serde(default)]
    pub cloud_consent: bool,
}

/// Versioned ledger with a CAS revision; `config: null` means nothing configured yet.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LlmLedger {
    pub version: u16,
    pub revision: u64,
    #[serde(default)]
    pub config: Option<LlmConfig>,
}

impl Default for LlmLedger {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            config: None,
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

impl LlmConfig {
    pub fn validate(&self, allow_loopback: bool) -> Result<(), &'static str> {
        if !valid_model(&self.model) {
            return Err(BAD_CONFIG);
        }
        match (self.provider, self.custom_url.as_deref()) {
            (Provider::Custom, Some(url)) => parse_endpoint(url, allow_loopback)
                .map(|_| ())
                .map_err(|_| BAD_CONFIG),
            (Provider::Custom, None) => Err(BAD_CONFIG),
            (_, Some(_)) => Err(BAD_CONFIG),
            (_, None) => Ok(()),
        }
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

/// Core-side authority for one plugin invocation. Built once at invoke time from the ledger,
/// the vault and the approval state; the key never leaves the Core except inside the broker.
#[derive(Clone, Default)]
pub struct HostAuth {
    pub permission: bool,
    pub provider: Option<Provider>,
    pub model: Option<String>,
    pub custom_url: Option<String>,
    pub key: Option<String>,
    pub cloud_consent: bool,
    pub allow_loopback: bool,
}

impl fmt::Debug for HostAuth {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("HostAuth")
            .field("permission", &self.permission)
            .field("provider", &self.provider)
            .field("model", &self.model)
            .field("key", &self.key.as_ref().map(|_| "<redacted>"))
            .field("cloud_consent", &self.cloud_consent)
            .field("allow_loopback", &self.allow_loopback)
            .finish()
    }
}

/// Snapshot `llm`: booleans for keys, config without secrets, and the CAS revision.
#[derive(Debug, Clone, Serialize)]
pub struct Snapshot {
    pub revision: u64,
    pub config: Option<LlmConfig>,
    pub secrets: Flags,
}

/// Core-owned LLM state: loaded once at boot, updated only through CAS-checked operations.
#[derive(Default)]
pub struct LlmState {
    revision: u64,
    config: Option<LlmConfig>,
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
            config: self.config.clone(),
            secrets: self.secrets.flags(),
        }
    }
    pub fn configure(
        &mut self,
        storage: &Storage,
        revision: u64,
        provider: &str,
        model: &str,
        custom_url: Option<String>,
        cloud_consent: bool,
    ) -> Result<(), &'static str> {
        if self.quarantined {
            return Err("llm_storage_error");
        }
        if revision != self.revision {
            return Err("stale_llm_revision");
        }
        let provider = Provider::parse(provider).ok_or(BAD_CONFIG)?;
        let config = LlmConfig {
            provider,
            model: model.to_owned(),
            custom_url,
            cloud_consent,
        };
        config.validate(self.allow_loopback)?;
        let next = LlmLedger {
            version: 1,
            revision: revision.checked_add(1).ok_or("llm_revision_exhausted")?,
            config: Some(config.clone()),
        };
        storage
            .save_llm_ledger(&next)
            .map_err(|_| "llm_storage_error")?;
        self.revision = next.revision;
        self.config = Some(config);
        Ok(())
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
    /// Snapshot for one invocation. `permission` is the approved `network_llm` grant.
    pub fn host_auth(&self, permission: bool) -> HostAuth {
        let config = self.config.as_ref().filter(|_| !self.quarantined);
        HostAuth {
            permission,
            provider: config.map(|c| c.provider),
            model: config.map(|c| c.model.clone()),
            custom_url: config.and_then(|c| c.custom_url.clone()),
            key: config
                .and_then(|c| self.secrets.get(c.provider))
                .map(str::to_owned),
            cloud_consent: config.is_some_and(|c| c.cloud_consent),
            allow_loopback: self.allow_loopback,
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
        assert_eq!(
            Provider::Google.fixed_base(),
            Some("https://generativelanguage.googleapis.com/v1beta/openai")
        );
    }

    #[test]
    fn config_requires_custom_url_only_for_custom() {
        let base = LlmConfig {
            provider: Provider::Openrouter,
            model: "m".into(),
            custom_url: None,
            cloud_consent: false,
        };
        assert!(base.validate(false).is_ok());
        let mut with_url = base.clone();
        with_url.custom_url = Some("https://example.com/v1".into());
        assert!(with_url.validate(false).is_err());
        let custom = LlmConfig {
            provider: Provider::Custom,
            model: "m".into(),
            custom_url: None,
            cloud_consent: false,
        };
        assert!(custom.validate(false).is_err());
    }
}
