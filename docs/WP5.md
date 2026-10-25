# WP-5: Hub and Skills publisher verification (EXT-01, EXT-03, SKILL-02, SKILL-03)

Scope: `src/hub.rs`, `src/skills.rs`, `tests/hub.rs`, `tests/skills_share.rs` (run only). One change outside
the package, flagged in section 6: `ring` added to `Cargo.toml` and `Cargo.lock`.

## 1. What is implemented

### Publisher signatures (Ed25519, `ring` 0.17.14)

- `hub::publisher_trust(message, signature, publisher, trust)` returns `Trust::Unsigned`,
  `Trust::Unverified` (key not pinned), `Trust::Verified`, or `Err("bad_signature")`.
- A signature is `{"key_id": "...", "algorithm": "ed25519", "signature": "<128 lowercase hex>"}`.
- A signature counts only when its `key_id` is pinned **and** the pinned publisher equals the publisher named in the
  manifest or package. Verification is against the bytes of the message, as UTF-8.
- Pinned keys: `hub::pinned_publisher_keys()` in `src/hub.rs`. Owner-managed, it holds public keys only.
  **It is empty today**, so no publisher verifies in production until the owner adds the key (see section 5).

### Plugin catalog (EXT-01, hub.rs)

- `Manifest.signature` is now `Option<PublisherSignature>` (was free text).
- Signed message: lowercase SHA-256 of the compact JSON of the manifest with `signature` set to null and keys
  sorted (`manifest_signing_message`). Serde's `Value` map is a `BTreeMap` in this build (no `preserve_order`).
- `load` (and `load_trusted` for tests) checks every manifest:
  - unsigned or unknown key: loads, `publisher_verified` false;
  - malformed signature, a valid-format signature that does not verify, or a key of another publisher:
    the whole catalog fails closed (`Snapshot` becomes `quarantined`, same as any invalid catalog).
- `Snapshot.publisher_verified` is now computed: true only when the catalog has at least one plugin and every plugin
  verifies. It was hard-coded `false` (hub.rs:239 and :560).
- `Entry.publisher_verified` exists but is `#[serde(skip)]`: the bridge's `ENTRY_KEYS` is an exact set, so a new
  wire key would break the snapshot. The aggregate is the only value on the wire.

### Skill packages (SKILL-02, skills.rs)

- `Package.signature` is `Option<PublisherSignature>`. The Core still exports unsigned packages (no private key here).
- `package_digest` now blanks `signature` as well as `package_sha256`, so a signature never signs itself.
- Signed message: the package's `package_sha256` (hex text). A valid signature counts only when the stored hash
  equals the recomputed hash.
- `publisher_checks` (pure function, unit-tested):
  - unsigned or unknown key: `unverified`, not blocked;
  - forged signature or key of another publisher: blocking finding `skill_invalid:hash_mismatch` (field `signature`);
  - malformed signature field: blocking finding `skill_invalid:corrupt_package` (field `signature`);
  - `ImportView.unverified` = `!verified`. It was hard-coded `true`.

### GitHub index (SKILL-03, skills.rs)

Format 1, file `<data>/skill-imports/index.json` (the same private import folder; `read_import_file`, 0600 rules,
64 KiB cap, no symlink):

```json
{
  "format": 1,
  "repository": "https://github.com/<owner>/<repo>",
  "skills": [
    {
      "name": "fixture-note",
      "version": "1.0.0",
      "sha256": "<64 lowercase hex: package_sha256 of fixture-note.gskill>",
      "url": "https://github.com/<owner>/<repo>/releases/download/<tag>/fixture-note.gskill",
      "signature": {"key_id": "owner", "algorithm": "ed25519", "signature": "<128 hex>"}
    }
  ]
}
```

Rules (`parse_index`; any violation refuses the whole index):

- `format` is 1; `repository` and every `url` are `https://github.com/...` with no spaces or control characters,
  at most 512 bytes; at most 64 entries; `name` is a valid import name and unique; `version` is `x.y.z`;
  `sha256` is 64 lowercase hex; unknown fields are refused.
- `name` is the file stem of the package in the same folder (`<name>.gskill`).
- When a package is imported and its name is in the index: `entry.sha256` must equal the package hash and
  `entry.version` must equal the manifest version. `entry.signature`, if present, signs `entry.sha256` with the same
  rules as above. A package with no index entry keeps the local behaviour (unverified).
- The Core never fetches `url`. Downloading packages is outside this change (see section 5).

## 2. Signing procedure for the owner (no private key in the repo or the Core)

```
openssl genpkey -algorithm ed25519 -out publisher.pem        # keep offline, never in the repo
openssl pkey -in publisher.pem -pubout -outform DER | tail -c 32 | od -An -tx1 | tr -d ' \n'   # public key hex
```

Pin the public hex (with `key_id` and publisher name) in `pinned_publisher_keys()`.

Skill package: `printf '%s' "<package_sha256>" > msg.txt`, then
`openssl pkeyutl -sign -inkey publisher.pem -rawin -in msg.txt -out sig.bin` and
`od -An -tx1 sig.bin | tr -d ' \n'` gives the 128-hex `signature`. Put the same object in the package's
`signature` field and, for the index, in the entry's `signature`.

Plugin manifest: the message is the canonical manifest hash of section 1. Compute it with the same rules
(sorted keys, compact, `signature` null) and sign it the same way.

## 3. Tests

Negative and positive cases:

- `tests/hub.rs` (10 new): no pinned key yet; every plugin signed and pinned: verified; one unsigned plugin keeps
  the catalog unverified; unpinned key id: unverified and loads; forged signature under a pinned id: refused;
  tampered signed manifest: refused; flipped signature byte: refused; key pinned to another publisher: refused;
  malformed signature fields (algorithm, length, extra field): refused; `publisher_trust` states and hex decoding.
- `src/skills.rs` `publisher_tests` (8 new): unsigned; signed by pinned key; tampered package with an old signature
  is not verified; forged signature blocks; corrupt signature field; unknown key unverified and other-publisher key
  blocks; index entry must match hash and version and can carry a signature; malformed index refused (duplicate
  names, traversal name, bad hash, http url, foreign URL, unknown field, bad version, too many entries, wrong format,
  foreign repository).
- Cross-implementation check (OpenSSL signature, Core verification): a one-off test file signed by
  `openssl pkeyutl -sign -rawin` verified with `publisher_trust` (`Verified`), and a one-character change to the
  message was refused (`Err("bad_signature")`). The temporary test file was deleted afterwards and the scratch key
  removed.

## 4. Commands run and results

Run from `/home/lucas/Documentos/Gideon/base`:

| Command | Result |
|---|---|
| `cargo check --offline --lib --tests` | OK (after the `ring` addition; one lint fixed: `manifest_signing_message` made private) |
| `cargo fmt` then `cargo fmt -- --check` | OK |
| `cargo clippy --offline --all-targets -- -D warnings` | exit 0 (two `format!`-collect lints fixed) |
| `cargo test --offline --lib publisher_tests` | 8 passed, 0 failed |
| `cargo test --offline --test hub` | 37 passed, 0 failed (27 existing, 10 new) |
| `cargo test --offline --test skills_share --test skills` | 21 passed and 15 passed, 0 failed (existing D4 import/export suites) |
| one-off OpenSSL interop test (deleted afterwards) | 1 passed |

Not run: the full `cargo test` and the Python process gates (`scripts/verify_s4_share.py`,
`scripts/test_bridge_protocol.py`, `scripts/test_snapshot_contract.py`). Other agents are editing `src/core.rs`,
`src/protocol.rs`, `src/storage.rs` and the bridge in parallel. The default snapshot is unchanged while no key is
pinned (`publisher_verified` stays false, `unverified` stays true), but the bridge's contract on a verified
package is not exercised. Running those gates is the orchestrator's call, once the tree settles.

## 5. What remains, and why

- **EXT-01 and SKILL-02 activation (owner decision):** the pinned key list is empty. The owner must generate the
  Ed25519 key (section 2) and pin the public key. Until then, verification code is complete and tested, but nothing
  is verified in production. This is the only change needed to turn it on. Status: code FEITO, activation blocked by
  owner key.
- **EXT-03 (partial):** the signature part is done. The update channel is not in this package. Autostart already
  exists (B2).
- **SKILL-03 (partial):** the index format, validation, and verification are done. Not done: fetching `url` (needs a
  download path through the broker and an owner decision on where the index is fetched from), a Core op or UI to
  list and select index entries, and `skill_import` previews for index-only skills.
- **Bridge contract (app/bridge.py, not in this package):**
  - `valid_skill_import` requires `unverified is True`; a verified package now reports `unverified: false`, which the
    bridge rejects. The bridge must accept `False`.
  - `Skills.qml`, `PermRows.js`, `BPluginDetail.qml` hard-code "não autenticado". Once a key is pinned, these labels
    should read the snapshot flags (`hub.publisher_verified`, skill import `unverified`) and the hard-coded text
    should go.
- **Approval ack:** approval still requires `publisher_unverified_ack` even for a verified publisher. Whether a
  verified publisher can skip the acknowledgement is an owner decision; the current behaviour is the conservative one.
- **Pinned key rotation and revocation** are not implemented. A compromised key needs a Core update that removes it
  from `pinned_publisher_keys()`.

## 6. Changes outside the package (for the orchestrator)

- `Cargo.toml`: added `ring = "=0.17.14"` under `[dependencies]`. The crate is already in the local cargo registry
  and in `Cargo.lock` as a transitive dependency. `cargo ... --offline` resolves it, and it adds `cc` and
  `getrandom 0.2` to the lock. This is the only way to get real Ed25519 verification without hand-written crypto.
  Revert only together with `src/hub.rs` and `src/skills.rs`.
- `Cargo.lock`: updated by the line above (`cargo` rewrote it).
- No change to `protocol.rs`, `core.rs`, `transport.rs`, `app/`, or `scripts/`.

## 7. Gap audit

`docs/GAP_AUDIT.md` rows updated: EXT-01 and SKILL-02 (code FEITO, activation pending the owner key), EXT-03
(PARCIAL), SKILL-03 (PARCIAL). Each row names this document.
