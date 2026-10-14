# Agent state — 2026-10-14

- S1/A0–A5 e B1 AUTO_VERIFIED/PHYSICAL_PENDING EN/DEV/sandbox/offscreen. B2 PLANNED; S2 completo ainda não aprovado. B3–S5 não iniciados.
- Branch main; A4 db64f48, A5 f2c1bf7; B1 no commit seguinte. Binário/source: docs/evidence/b1*.json. Sem remoto/push/publicação.
- 28 Rust, 5 nativos; regressões A0–A5 32/44/33/67/138/93 checks, B1 32 checks em 4 cenários. fmt/check/test/clippy/release/diff-check PASS; zero ignored.
- Qt/QML thin: mesmo Core, partial/final/efeito/PCM; Cancel por teclado; kill/restart/reconnect e timeout/SIGSTOP/SIGCONT reais. SO_PEERCRED+root/socket privados, session u64 string, envelopes/correlation/sequence/bounds/watchdog. Connected só depois de handshake válido; snapshots iguais sem delta.
- Entrada texto só em perfil virtual-input+commands-sandbox: mesmo parser/grant/executor, source=user_text, nunca STT fictício. UI não duplica lógica ou oferece modelos/capacidades futuras. Qt Essentials 6.12.0/Shiboken apenas.
- A5 cold first PCM ~8s/pico soma RSS ~1.53GB; após EOF 0% CPU/2s, 434434048 bytes (STT carregado/TTS descarregado; shared pages somadas). Cold start pendente de otimização; Piper/Kokoro/Parakeet antes de freeze. Nenhum vencedor final/model manager/LLM.
- Wake selecionável por catálogo: Hey DEV; Okay STT "K Gideon" recusado, POC_REQUIRED; parser aceita frase customizada via contrato. Nada forced no Core.
- Física/acústica/pt-BR/holdout/Wayland/hotplug: AWAITING_HUMAN_VALIDATION, somente rodada consolidada após S5. Não pedir participação intermediária.
- Legado confirmado intacto: ef0a0f3, 51 dirty, 12 worktrees; modelos/datasets e sessão pessoal preservados. Graphify 0.9.90 AST (488 nós); QML verificado por fonte/runtime offscreen.
- Próximo B2: config validada/persistência/restart/rollback refletida no App; somente opções suportadas/certificadas no escopo real, controles não suportados desabilitados. Fontes S2 em docs/sources/s2.md. Depois B3 Hub, B4 pacote, então S3.
