# Agent state — 2026-10-14

- S1/A0–A5 AUTO_VERIFIED/PHYSICAL_PENDING EN/DEV sandbox; B1 PLANNED, spec S2 lida em docs/sources/s2.md. Nada S3–S5 implementado.
- Branch main; A4 db64f48, A5 código no commit seguinte. Sem remoto/push/publicação. Identidade binário/source em docs/evidence/a5*.json.
- 26 Rust, 5 nativos; A0/A1/A2/A3/A4 regressão 32/44/33/67/138 checks. A5 93 checks, soak dois ciclos 8, shutdown após PCM separado. fmt/check/clippy/release/diff-check PASS; zero ignored.
- Wake→Silero/pre-roll→Moonshine partial/final→parser/grant interno→app fixture verificado→Pocket CPU→PCM paced sink virtual. Cancel/timeout/dup/stale/worker death/hash failure; feedback Failed/NotUnderstood e Core vivo. Sem dispositivo/sessão pessoal.
- Pocket 3.3.0/Torch 2.14.1+cpu/EN 2026-09/Alba local hash-pinned; sem download runtime/clonagem pessoal/Model Manager/LLM. Comparação Piper/Kokoro antes de freeze; Parakeet candidato STT.
- Limites: primeira PCM fria 7.99–8.42s; pico soma RSS própria ~1.53GB; após EOF 0% CPU/2s, RSS 434434048 bytes (STT carregado, TTS descarregado, shared pages duplicadas). Otimização cold start pendente; não qualidade física/pt-BR/holdout independente.
- Wake selecionável por catálogo: Hey DEV; Okay STT "K Gideon" recusado, POC_REQUIRED. Parser também testado com frase customizada. Nada forced no Core.
- Legado/branches/worktrees/dirty/models/datasets preservados. Graphify 0.9.90 AST local atualizado. Human validation só consolidada após S5.
- Próximo B1: UI Qt/QML thin+IPC real autenticado/versionado, estados/texto/resultados/cancel/reconnect; offscreen em HOME/XDG isolado. B2 configurações, B3 Hub, B4 pacote apenas após respectivos gates.
