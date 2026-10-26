# Agent state — 2026-10-16

- S1, S2, S3/C0 and S3/C1 (optional LLM Engine plugin) AUTO_VERIFIED in the virtual environment. Branch main; latest code commit 9666dfd + gate fixes c9e1acd; evidence/docs commit follows. Local only/no remote/push/deploy. Legacy untouched.
- PASS fmt/check/test/clippy -D warnings/release/diff-check: 170 Rust, 232 Python (1 skip); 1835 process checks = 1041 regressions A0–B3.3 + c0-plugins 120 + c1-llm 109 + b4-package 67 + b4-update 129 + s2-final 223 + c0-package 146, release c9cf3a8e02c4…. Evidence docs/evidence/c1-llm.json. Graph AST 2895 nodes/7661 edges.
- C1: Core key vault (secrets.json 0600, write-only), llm-config ledger (cloud_consent default off), Core-brokered HTTP (net_broker.py in bwrap with network, exact host allowlist, no redirects, response caps; key injected by Core, never seen by plugin), plugin streaming partials, error-code pass-through + http_status, Safety-gated tool proposals (fixed registry, user decides state-changing tools), Qt Conversa page + Motor LLM dialog. Live test with owner's keys: Google PASSED, Mistral PASSED (custom provider), OpenRouter EXTERNAL_BLOCKED 403, OpenCode EXTERNAL_BLOCKED 402. Keys live only in a private 0600 temp file outside the repo (scanned: none in repo/evidence). Owner should revoke the pasted keys (they remain in session history and the claude-mem DB).
- Review round (6 read-only agents) fixed: Hub/plugin hardening (cap-drop, tmpfs cap, NPROC headroom+retry, per-invocation CPU, interpreter allowlist, verification cache, staged_error per entry, discard op, crash-leftover quarantine, ledger-deleted detection, revoke fail-closed), Qt hardening (UTF-8 bounds, per-section signals, exception-safe validation, accessibility, confirmations), package tools (repair, verifier pin, fail-closed verify, locks, atomic build), 16 mutation-killing tests, vacuous-gate fixes. Real-Core snapshot contract test added (scripts/test_snapshot_contract.py).
- Limits: no seccomp; exec of /usr binaries allowed in plugin sandbox; residual TOCTOU on path bind; prlimit required; Mistral only via custom provider; host_call permission_denied proven in Rust tests only; wake replay only (no live mic); command worker uses host /usr/bin/python3; physical audio/CPAL/PipeWire/AEC/hotplug/barge-in, real KDE Wayland, Flatpak NOT validated; package update has no UI; publisher unauthenticated; plugin LLM never receives tool results (agent loop is C3).
- Intermittents A1/A3 did not recur; causes unresolved. Matrix policy: affected gates while developing, full matrix once per gate (~40 min).
- Rules for agents (owner): max 1 reviewer + 1 fixer at once, unlimited implementers; Haiku 5.5 team; I orchestrate, verify, commit. Graphify for navigation.
- Physical/human validation consolidated after S5. No personal devices touched.
- Next: C2 — LLM Model Manager ONLY inside the plugin (recommended vs custom, local vs cloud, llama.cpp adapter, certification matrix). Needs owner authorization to download the llama.cpp binary and a small GGUF. No Skills/Connections/Model Manager in Base.

## Handoff (written before a session compaction, 2026-10-16)

- IN PROGRESS: S3/C2 (LLM Model Manager, plugin-only). Contract: docs/C2.md (latest commit e3b5c50). Work in the tree is UNCOMMITTED: Core C2.1 (src/llmcfg.rs, broker.rs, plugins.rs, storage.rs, protocol.rs, core.rs, scripts/net_broker.py, tests/llm2.rs: providers local/ollama + local_port, LKG ops llm_mark_good/llm_rollback, fallback target, settings.get/put host services, plugin_settings_clear), plugin llm_engine 1.1.0 (tests/fixtures/llm_engine.py, llm_models.json, fake_llama_server.py, hub-c1.json regenerated, make_c1_catalog.py, test_c2_fixtures.py, test_c2_contract.py), Qt page Modelos LLM (app/bridge.py, Main.qml, test_bridge_protocol.py, test_ui_offscreen.py phase `models`), gates scripts/verify_c2_models.py and verify_c2_live.py.
- A fixer agent (a45e07bde3c607109) was running: paginate `llm_engine.models list` (tab/offset/limit/total, 16 customs reachable), bridge/QML paging, update verify_c2_models.py (local_port in rows, paging) and verify_c1_llm.py (1.1.0 permissions/capabilities), wire the Qt `models` phase into the gate. Its report is the next thing to read; then: verify (cargo fmt/test/clippy/release, bridge tests, c1/c2 fixtures + contract tests, snapshot contract), commit in batches, run the full matrix (`bash target/run-matrix-c1.sh`, ~40 min; add c2models and the Qt models phase), run verify_c2_live.py with GIDEON_LIVE_KEYS_FILE, write docs/evidence/c2-models.json (generator pattern: target/mkevc1.py), update docs, commit. Known: 187 Rust tests green at C2.1; bridge 99; hub approval survives hub_remove by design (documented).
- Private keys file (NOT in repo, 0600): /tmp/claude-1000/-home-lucas-Documentos-Gideon/5fd6f0b3-714b-4e76-9110-b1db87d89aef/scratchpad/k/keys.json and live.json (google 3, mistral 2, openrouter 3, opencode 3, deepseek 1, zenmux 2). It lives in the session scratchpad and can vanish on restart; the owner must re-supply keys if needed and should REVOKE them after the tests. Usable providers: Google (key 0 and 2; key 1 denied) and Mistral (ministral-3b-latest via custom https://api.mistral.ai/v1). OpenRouter 403 and OpenCode 402 blocked externally; DeepSeek 402; ZenMux 403.
- Owner rules: (1) agents: max 1 reviewer + 1 fixer at once, unlimited implementers, Haiku 5.5 team, I orchestrate/verify/commit; (2) use graphify for navigation; (3) do not stop between steps, keep going; (4) run affected gates while developing and the full matrix once per stage; (5) never write files with bash heredocs in agent prompts (two stuck 2h30 tasks); (6) llama.cpp binary and a small GGUF require explicit owner authorization to download (none on this machine); (7) unresolved: whether to use Sonnet for risky Rust pieces.
- Planned infra sprint (~1.5 h, after C2): JSON schemas in docs/schemas shared by Core/plugin/bridge with generated validators and contract tests; scripts/gatelib.py shared gate harness; scripts/affected_gates.py (changed files -> gates) and a 3-way sharded full matrix; fixed agent-prompt preamble; reuse agents via SendMessage; review contracts before code.
- Remaining roadmap after C2: C3 Agent Runtime (observe-plan-act-verify), C4.1-C4.6 perception/action plugins (screen, computer control, audio, mic, camera gestures, display manipulation; UNSUPPORTED where the host cannot), S3 final gate, S4 Skills mechanism (no catalog of official skills), S5 Connections, final integrated package, then the consolidated human validation round (physical audio, KDE Wayland, Flatpak) that only the owner can do. Estimate 30-50 h of agent work.
- Matrix commands: full = target/run-matrix-c1.sh (resumable via START=<gate>); evidence generators = target/mkev*.py (not versioned: recreate from the pattern in docs/evidence/*.json if lost). Package gates need a clean git tree (build_package flags dirty).

## 2026-10-16 — C2 CLOSED (AUTO_VERIFIED)
- C2 committed (7933749, efc00ae, deadline change after). Full matrix green (rerun from c0plugins after commit), live Google+Mistral PASSED, evidence docs/evidence/c2-models.json. Handoff section above is superseded for C2.
- Next: infra sprint (optional, awaiting owner ok) or C3 Agent Runtime. Local llama.cpp certification still needs owner authorization to download binary + GGUF.

## 2026-10-16 — C3 CLOSED (AUTO_VERIFIED)
- C3 Agent Runtime committed, full matrix green (target/run-matrix-c3.sh), evidence docs/evidence/c3-agent.json. Next: C4.1 screen.observe (needs contract doc docs/C4.md).

## 2026-10-16 — C4 / S3 final CLOSED (AUTO_VERIFIED, synthetic only)
- Evidence docs/evidence/c4.json; matrix script target/run-matrix-c4.sh. Next: S4 Skills (needs contract docs/S4.md; read Notion S4 page first), then S5 Connections.

## 2026-10-18 — S4 CLOSED (AUTO_VERIFIED)
- Evidence docs/evidence/s4.json; matrix script target/run-matrix-s4b.sh. Next: S5 Connections (read Notion S5 page, write docs/S5.md), then final integrated package and owner human validation round.

## 2026-10-18 — E2.2 google (AUTO_VERIFIED against the fake, UNCOMMITTED)
- Descriptor google (7 scopes, 7 ops), calendar_list_events / gmail_list_messages / calendar_create_event (fake flag only), scope loss at refresh -> reauth_required with reduced grant, reauth keeps granted scopes (github too). Gate scripts/verify_e22_google.py 111/0 (4 documented skips); evidence target/evidence/e22-google.json. Regression: verify_e1_connections 119/0; cargo test 323/0; snapshot contract 10/10; bridge protocol 156/0; fixtures 129 + 86 green. Wire differences: docs/S5.md "Resultado E2.2 google".
- Next: E2.3 homeassistant (needs its own fake contract review first).

## 2026-10-18 — E2.3 homeassistant (AUTO_VERIFIED against the fake, UNCOMMITTED)

- Descriptor homeassistant (3 scopes, 3 operations), connection_set_token (one GET /api/states probe, token only in the vault), dangerous services (lock.unlock, lock.open, alarm_control_panel.*, cover.open_cover, cover.close_cover) destructive with services.dangerous, agent tools ha_get_state / ha_call_service with the fake flag. Gate scripts/verify_e23_ha.py 101/0 (4 documented skips); evidence target/evidence/e23-ha.json. Regression: verify_e1_connections 119/0, verify_e22_google 111/0, cargo test green (fmt, clippy -D warnings), snapshot contract 11/11, bridge protocol 156, fixtures 129 + 86.
- Open point for the owner: garage_door.* is not in the dangerous list (five patterns requested). Details and wire differences: docs/S5.md "Resultado E2.3 homeassistant".
- Next: E3 registry (src/registry.rs) or E2.4 mcp, per owner order.

## 2026-10-18 — E2.4 mcp (AUTO_VERIFIED against the fake, UNCOMMITTED)

- Sandboxed fake stdio MCP server managed by the Core (fixed registration `--connections-fake-mcp`), mcp.discover with schema validation and per-tool sha256, per-call approval, untrusted prefixed output, connection_trust_tools, mcp_call agent tool. Gate scripts/verify_e24_mcp.py 188/0 (4 skips); details and wire differences: docs/S5.md "Resultado E2.4 mcp".
- Next: E3 registry (src/registry.rs).

## 2026-10-23 — E3 registry and E4 total integration (AUTO_VERIFIED, UNCOMMITTED)

- E3 evidence unchanged (`verify_e3_registry.py` 129/0, 3 skips, earlier run). E4 (`verify_e4_integration.py`): one full run 288/0, 3 skips, 603 s, evidence `target/evidence/e4-integration.json`, copy in `docs/evidence/`. Packages built from the uncommitted tree (`package_dirty_flag: true`).
- Fixed: bridge `TOOL_ITEMS` 4 to 8 (Core history limit; page went offline with 5+ proposals); UI consent retries on busy; gate ledger, netns, profile-scoped process and sentinel-mode defects.
- Checks at the end: cargo fmt --check OK, clippy -D warnings OK, cargo test 375 passed 0 failed, test_bridge_protocol 169 OK, test_package_core_args 9 OK, test_package_hardening 52 OK.
- Owner rules kept: no commit, no push; E4 gate run once in full plus partial runs while debugging; no other gate script run. Remaining: owner validation per docs/HUMAN_VALIDATION.md (READY_FOR_HUMAN_VALIDATION).

## 2026-10-23 — S5 + E4 CLOSED, READY_FOR_HUMAN_VALIDATION
- Final full matrix (target/run-matrix-final.sh) green except e3 gate expectation updated afterwards (130/0); verify_e4_integration 288/0 on a clean tree. Security review of connectors: 9 findings fixed (docs/S5.md). Next: owner runs docs/HUMAN_VALIDATION.md. Open decisions: Flatpak scope, package signing/update channel/autostart, worker python path.

## 2026-10-24 — UI v3 integrated (tabs + sub-tabs, themes, UI settings, Core-connected)
- New app shell/pages (docs/ui-spec/*, docs/UI_IA.md, docs/APP_DESCRICAO.md), UI settings store (app/uisettings.py), Core additions: events with at_ms, risk/effect on proposals, grants, core_restart (exit 75 + launcher supervisor), agent budget, llm last_chat, skills paths/permissions, connection revoke_scope/granted_at.
- UI gates green (design, b2feedback, c1, c2, c3, c4, s4final, e1, e24, e3, s2final); package gates s2final/b4package/e4 green on clean tree. Published to https://github.com/LQ13ofc/Gideon2 (public).
- Open: onboarding (not built), plugin grant dates in UI (approved_at_ms not sent), Core-side restore of preferences, live microphone path, real backends. See docs/HUMAN_VALIDATION.md.

## 2026-10-24 — pendências implementadas (docs/PENDENCIAS_IMPLEMENTACAO.md)
- Onboarding, autostart, modo econômico, perfis de config, atalhos, diagnóstico completo, efeitos com argumentos, banners de erro, limites em bytes; Core: sensibilidade do wake, restaurar padrões, preferências e listagem de dispositivos, áudio ao vivo opt-in. 16 gates verdes (design, b2feedback, a1, a4, a5, c1, c2, c3, c4, s4final, e1, e24, e3, s2final, b4package, e4).

## 2026-10-25 — Frente 2 Idiomas (EN/PT/FR), fase de pesquisa e arquitetura (NÃO COMMITADO)
- Pesquisa com fontes e lista exata de downloads, sem nada baixado: docs/research/idiomas-stt-tts.md. Resultado: Moonshine 0.1.5 não tem PT nem FR (verificado localmente); TTS PT/FR viável com Pocket TTS (mesmo motor do inglês); STT PT/FR sem candidato streaming confiável; KWS zh-en carrega frases PT/FR tokenizadas à mão, mas detecção não medida; sherpa aborta (rc 255) com token desconhecido.
- Core: src/languages.rs + src/languages_catalog.json (estado bundled / available_not_installed / unsupported), op `language_preference`, bloco snapshot `languages`, preferências `stt_languages`/`tts_language`/`tts_voice` com defaults serde (ledger antigo carrega), rollback recusa idioma não instalado.
- UI: sub-aba Configurações › Idiomas (app/pages/CfgIdiomas.qml), botões Instalar desativados com "Aguardando aprovação do download pelo dono"; docs/ui-spec/40-configuracoes.md §7.1A.
- Gates rodados: cargo fmt --check, clippy -D warnings, cargo test (todos), test_bridge_protocol 228, test_snapshot_contract 16, test_ui_settings 24, test_languages_qml 4 (novo).
- Limites: troca de idioma só vale no próximo início do Core (sem troca quente de worker); idioma da busca de configurações (app/uisettings.py) não indexa Idiomas; nenhum modelo PT/FR instalado nem medido.

## 2026-10-25 — wake ao vivo, frases, idiomas
- Causa do "wake não funciona": o pacote nunca abria o microfone (só tocava áudio de teste). Agora: preferência `live_audio` (Configurações › Dispositivos, com consentimento), áudio ao vivo testado com dispositivos virtuais (docs/A7-wake-live-test.md) e 5 defeitos corrigidos. Teste acústico real inconclusivo (docs/A8): nenhum par caixa/microfone captou o som; validação com voz real continua com o dono.
- Frases: várias ativas (até 5), personalizadas com medição sintética, boost 1.2 (96,05% -> 98,68% no protocolo A1, 0 falsos). Léxico en.phone empacotado.
- Idiomas: catálogo + UI; só EN instalado; PT/FR dependem de download aprovado (docs/research/idiomas-stt-tts.md).
- Gates verdes: design, b2feedback, a1..a5, c1..c4, s4final, e1, e24, e3, s2final(216), b4package, e4(290).

## 2026-10-25 — A11 ações reais no computador (NÃO COMMITADO)
- Preferência `real_actions` (off por padrão, consentimento com `confirmed`, `busy` com sessão/job). Ligada: "open brave/kcalc" abre o app pelo lançador do sistema, "set volume/mute/unmute/volume up/down" muda o sink padrão via `wpctl`; cada efeito só vira recibo depois de observado (processo novo que sobrevive 1 s; volume relido). Desligada: executor de sandbox como antes.
- Código: src/host.rs (novo), src/commands.rs, src/core.rs, src/storage.rs, src/protocol.rs, src/transport.rs, src/tts.rs; app/bridge.py, app/pages/CfgPrivacidade.qml, app/components/RealActionsConsent.qml.
- Teste ao vivo neste PC (scripts/verify_a11_real_actions.py): 47/0. Evidência docs/evidence/real-actions.json; relatório docs/A11-real-actions-test.md.
- Desvio: XAUTHORITY no ambiente do host (Brave sai sem ele). Janela não é verificada pelo Core.
- Gates: fmt OK, clippy -D warnings OK, cargo test OK, test_bridge_protocol 238 OK, test_snapshot_contract 18 OK, test_ui_settings 25 OK.
- Não feito: voz/wake ao vivo nesta rodada, pacote instalado, onboarding, ferramentas com ação real ao vivo.

## 2026-10-25 — A13 assistente de microfone e U1 a U3 (NÃO COMMITADO)
- Assistente (`audio_recommend_input`, `src/mic_assist.rs`): 2 s por entrada, ranking, `audio.recommendation`, aviso em Dispositivos, oferta no onboarding e no consentimento. Relatório: docs/A13-mic-assistant.md; dados: docs/evidence/a13-mic-assistant.json.
- U1: escritas de preferência aceitas com reinício pendente; sensibilidade ao vivo reinicia só o worker entre sessões (verificado com o Core real).
- U3: motivo sem conteúdo em `audio.live.last_error`; stderr em `live-last-error.txt` (0600), copiar em Diagnóstico › Desenvolvedor.
- Ajuste com dado real: limiar de ruído grave 0,5 → 0,75 (fifine 0,34 a 0,50; webcam 0,88 a 0,98).
- Pendência: regressão do laboratório caiu para 37/51 positivos (A7: 41 a 50); não investigada. Validação com voz e microfone do dono continua pendente.
- Gates: fmt OK, clippy -D warnings OK, cargo test OK (498), test_bridge_protocol 243 OK, test_snapshot_contract 18 OK, test_ui_settings 25 OK, test_wake_live 5 OK, test_wake_worker 9 OK.

## 2026-10-25 — revisão da taxa de acerto do wake ao vivo (NÃO COMMITADO)
- Causa da variância: alinhamento do clipe com a grade de quadros do encoder (varredura de 320 ms); não é rotação, limiar nem defeito do Core. Causa da queda de 37/51 não reproduzível; contagem por sessão subconta quando o STT falha (3 de 3 execuções por detecção com `worker_crashed`, causa não encontrada).
- Padrões mantidos: boost 1.2, limiar de frase 0.22, condicionamento auto, aquecimento 3 s (boost 1.4 admite babble; ver docs/A7 seção de revisão).
- Código: `scripts/wake_live_regression.py` (offline, grade e `check` com chão 0,82), `scripts/test_wake_live_regression.py`, `scripts/wake_phrase_evidence.py` (números de laboratório corrigidos).
- Evidência: docs/evidence/wake-live-matrix.json, docs/evidence/wake-live-pins.json; docs/A7 (revisão), docs/A9 (revisão), docs/A13 (nota). Nenhum código Rust mudou.
- Gates: test_wake_live_regression 9 OK, test_wake_live 5 OK, test_audio_conditioning 10 OK, test_wake_worker 9 OK (rodar sem `-I`).

## 2026-10-26 — WP-19 (gates vermelhos, describe, SKILL-03, pacote) — sem commit
- Gates corrigidos por causa real (E1 e E24 Qt: "Testar leitura" só para operações sem argumentos; C1/C2: chave `anthropic`), e expectativas antigas atualizadas (A3, A5, E4; S2 final continua com 2 falhas de árvore limpa). Teste de cargo em paralelo: `flock` herdado por fork, espera limitada no teste.
- `describe(id)`: op `llm_describe` no Core, ponte e página Modelos LLM; checado no Core real (C2).
- SKILL-03: `skills-index.json` no repositório e `skill_index_fetch` pelo broker; gate loopback 11/11; ao vivo 404 até o push do dono.
- Pacote `0.1.0-wp19` instalado em `~/GideonWp19`; Hub do pacote verificado com 7 entradas do catálogo de percepção.
- Bloqueado: verify_live_package (sem clipes de voz em inglês). S2 final: 2 falhas de árvore limpa (sem commit).
- Detalhes, comandos e números: docs/WP19.md.
