//! C1 key vault: API keys live only in the private `secrets.json` ledger and in Core memory.
//! Snapshots and IPC carry presence booleans only; `SecretKey` redacts itself in Debug output.
use crate::llmcfg::Provider;
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, fmt};

const MIN_KEY: usize = 8;
const MAX_KEY: usize = 256;
/// S5 connection tokens: provider access and refresh tokens, at most 8 accounts times 2 slots.
const MAX_TOKEN: usize = 1024;
const MAX_CONNECTION_SLOTS: usize = 16;

/// Key submitted by `secret_set`. Write-only: Debug never shows the bytes.
#[derive(Clone, Deserialize)]
#[serde(transparent)]
pub struct SecretKey(String);

impl SecretKey {
    pub(crate) fn expose(&self) -> &str {
        &self.0
    }
}

impl fmt::Debug for SecretKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("SecretKey(<redacted>)")
    }
}

/// 8..=256 printable ASCII bytes without spaces or controls.
pub fn valid_key(key: &str) -> bool {
    (MIN_KEY..=MAX_KEY).contains(&key.len()) && key.bytes().all(|b| b.is_ascii_graphic())
}

/// `secrets.json`: one optional key per provider, strict fields, version 1.
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Secrets {
    pub version: u16,
    #[serde(default)]
    openrouter: Option<String>,
    #[serde(default)]
    opencode: Option<String>,
    #[serde(default)]
    google: Option<String>,
    #[serde(default)]
    custom: Option<String>,
    /// S5 connection tokens, keyed `conn:<account>:access|refresh`. Write-only from the Core.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    connections: BTreeMap<String, String>,
}

/// Presence flags exposed in the snapshot as `llm.secrets`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct Flags {
    pub openrouter: bool,
    pub opencode: bool,
    pub google: bool,
    pub custom: bool,
}

impl Default for Secrets {
    fn default() -> Self {
        Self {
            version: 1,
            openrouter: None,
            opencode: None,
            google: None,
            custom: None,
            connections: BTreeMap::new(),
        }
    }
}

impl fmt::Debug for Secrets {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let flags = self.flags();
        write!(f, "Secrets(configured: {flags:?})")
    }
}

impl Secrets {
    fn slot(&self, provider: Provider) -> &Option<String> {
        match provider {
            Provider::Openrouter => &self.openrouter,
            Provider::Opencode => &self.opencode,
            Provider::Google => &self.google,
            Provider::Custom => &self.custom,
        }
    }
    fn slot_mut(&mut self, provider: Provider) -> &mut Option<String> {
        match provider {
            Provider::Openrouter => &mut self.openrouter,
            Provider::Opencode => &mut self.opencode,
            Provider::Google => &mut self.google,
            Provider::Custom => &mut self.custom,
        }
    }
    /// Core-internal: the key for a provider, used only to build the broker request.
    pub(crate) fn get(&self, provider: Provider) -> Option<&str> {
        self.slot(provider).as_deref()
    }
    pub(crate) fn set(&mut self, provider: Provider, key: Option<String>) {
        *self.slot_mut(provider) = key;
    }
    pub(crate) fn flags(&self) -> Flags {
        Flags {
            openrouter: self.openrouter.is_some(),
            opencode: self.opencode.is_some(),
            google: self.google.is_some(),
            custom: self.custom.is_some(),
        }
    }
    pub(crate) fn validate(&self) -> bool {
        self.version == 1
            && [&self.openrouter, &self.opencode, &self.google, &self.custom]
                .into_iter()
                .all(|k| k.as_deref().is_none_or(valid_key))
            && self.connections.len() <= MAX_CONNECTION_SLOTS
            && self
                .connections
                .iter()
                .all(|(name, token)| connection_slot_ok(name) && token_ok(token))
    }
    /// S5 token for one account slot (`access` or `refresh`). Core-internal only.
    pub(crate) fn connection_token(&self, account: &str, slot: &str) -> Option<&str> {
        self.connections
            .get(&connection_key(account, slot))
            .map(String::as_str)
    }
    pub(crate) fn set_connection_token(
        &mut self,
        account: &str,
        slot: &str,
        token: Option<String>,
    ) {
        let key = connection_key(account, slot);
        match token {
            Some(token) => {
                self.connections.insert(key, token);
            }
            None => {
                self.connections.remove(&key);
            }
        }
    }
    /// Removes both slots of one account.
    pub(crate) fn clear_connection(&mut self, account: &str) {
        self.set_connection_token(account, "access", None);
        self.set_connection_token(account, "refresh", None);
    }
}

pub(crate) fn connection_key(account: &str, slot: &str) -> String {
    format!("conn:{account}:{slot}")
}

/// `conn:<id>:access|refresh` with a valid account id.
fn connection_slot_ok(name: &str) -> bool {
    let parts: Vec<&str> = name.split(':').collect();
    parts.len() == 3
        && parts[0] == "conn"
        && crate::protocol::valid_id(parts[1])
        && matches!(parts[2], "access" | "refresh")
}

/// Tokens are printable ASCII without spaces, 8..=1024 bytes.
fn token_ok(token: &str) -> bool {
    (MIN_KEY..=MAX_TOKEN).contains(&token.len()) && token.bytes().all(|b| b.is_ascii_graphic())
}

#[cfg(test)]
mod tests {
    use super::*;

    const FAKE: &str = "fake-KEY-7f3a9c21d0b84e5f";

    #[test]
    fn debug_and_serde_errors_never_echo_the_key() {
        let key = SecretKey(FAKE.to_owned());
        assert!(!format!("{key:?}").contains(FAKE));
        let wire = format!(
            r#"{{"version":1,"request_id":"a","op":"secret_set","provider":"openrouter","key":"{FAKE}","unexpected":1}}"#
        );
        let error = serde_json::from_str::<crate::protocol::Request>(&wire)
            .expect_err("unknown field must be rejected")
            .to_string();
        assert!(!error.contains(FAKE), "serde error echoed key: {error}");
        let parsed = serde_json::from_str::<crate::protocol::Request>(
            &wire.replace(r#","unexpected":1"#, ""),
        )
        .expect("valid secret_set");
        let debug = format!("{parsed:?}");
        assert!(debug.contains("redacted"));
        assert!(!debug.contains(FAKE));
    }

    #[test]
    fn key_shape_is_printable_ascii_without_spaces() {
        assert!(valid_key("abcdefgh"));
        assert!(valid_key(&"k".repeat(256)));
        assert!(!valid_key("short"));
        assert!(!valid_key(&"k".repeat(257)));
        assert!(!valid_key("has space here"));
        assert!(!valid_key("control\u{1}char"));
        assert!(!valid_key("ação-chave-1234"));
    }

    #[test]
    fn vault_is_strict_and_flags_are_booleans() {
        let mut vault = Secrets::default();
        vault.set(Provider::Google, Some(FAKE.to_owned()));
        vault.set_connection_token("conn_a1", "access", Some(FAKE.to_owned()));
        assert!(vault.validate());
        vault.set_connection_token("bad name", "access", Some(FAKE.to_owned()));
        assert!(!vault.validate());
        vault.set_connection_token("bad name", "access", None);
        assert!(vault.validate());
        vault.set_connection_token("conn_a1", "access", None);
        assert!(vault.validate());
        assert_eq!(
            serde_json::to_value(vault.flags()).unwrap(),
            serde_json::json!({"openrouter": false, "opencode": false, "google": true, "custom": false})
        );
        assert!(!format!("{vault:?}").contains(FAKE));
        let unknown = format!(r#"{{"version":1,"zzz":"{FAKE}"}}"#);
        let error = serde_json::from_str::<Secrets>(&unknown)
            .unwrap_err()
            .to_string();
        assert!(!error.contains(FAKE));
    }
}
