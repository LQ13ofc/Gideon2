# Agent state — 2026-10-16

- B4.2 versioned install/update/rollback/profiles AUTO_VERIFIED; B3/S2 and B4 IN_PROGRESS. Branch main; code HEAD 4bf8a01; evidence/docs commit follows. Local only/no remote/push/deploy. Legacy untouched.
- PASS fmt/check/test/clippy -D warnings/release/diff-check: 67 Rust, 20 Python + 31 installer unit tests; 1212 process checks = 126 new (b4-update) + 66 (b4-package) + 1020 regressions on release 488e1bb6fb123511c766a0951da56c750e7ad6cdd40562357695e0b0fd65bd5b (unchanged since B4.1). Evidence docs/evidence/b4-update.json. Graph AST 1231 nodes/3044 edges.
- gideon-install (install/update/rollback/list/profile) under private INSTALL_ROOT: ledger CAS + flock, relative-symlink atomic switch, max current+previous, profile_active refusal, fail-closed layout, failure injection. gideon-launch verifies then execs per-profile Core. Gate under bwrap without repo/uv/net: S1, prefs+Hub survive update/rollback, profile isolation, tamper/crash/ledger-corruption refusal.
- Distribution decision: native user-level package; Flatpak deferred pending portal/audio/nested-bwrap evidence.
- Limits: power loss between symlink switch and ledger commit needs manual repair; orphans removed by hand; no hot update/delta/signing/channel/autostart; command worker uses host /usr/bin/python3; wake replay only; gideon-app not exercised; no UI for package update.
- Intermittents A1 early-worker and A3 idle CPU did not recur; causes unresolved.
- Workflow: graphify navigation; Haiku 5.5 agents implement; I review, run gates, commit.
- Scope: EN/DEV; Hey DEV-qualified/Okay POC_REQUIRED. Physical audio/Wayland pending; human validation only in consolidated round after S5. No personal devices touched.
- Next: S2 final gate (install in namespace → feedback/wake change → S1 via virtual PCM with real UI→Core → Hub dummy → restart+rollback → repeat S1, hashes+commit), then S3 only after S2 gate passes. No LLM/Skills/Connections/Model Manager.
