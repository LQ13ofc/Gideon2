# Agent state — 2026-10-14

- B2.1 AUTO_VERIFIED: feedback audível/prazo integrados Core→Qt. B2 IN_PROGRESS; B3 não iniciado. Contratos docs/B2.md; mapa docs/BASE_UI_MAP.md atualizado.
- Branch main; HEAD de código 7e4d241; fix coletor 910efcd. Local somente, sem remoto/push. Auditoria anterior docs/BASE_AUDIT.md preservada.
- PASS fmt/check/test/clippy -D warnings/release/diff-check. 33 Rust, 14 Python nativos/adversariais, 31 checks B2.1. Regressões A0/A1/A2/A3/A4/A5/B1/soak/shutdown 32/44/33/67/138/93/34/8/2 = 451. Zero failed/ignored na rodada final.
- Mesmo SHA release em nove grupos: 140e3365bc12ee16b4fa9557104955dadf6b1f2a640005cc96db9dc251cde2d6. Source→binary e resultados docs/evidence/b2-preferences.json. Imagem offscreen target/evidence/b2-preferences.png inspecionada.
- preferences/rollback_preferences actor-owned: idle, request_id e revisão. Config atômica com anterior no mesmo JSON; CAS/rollback sobrevivem restart/falha. Feedback off mantém execução verificada sem TTS; rollback restaura PCM Pocket. UI mostra estado efetivo, não escreve disco nem gerencia daemon.
- Corrigidos: backup separado podia perder rollback em falha (commit único); ProcessLookupError de child encerrado em /proc/statm (helper compartilhado; A3/A5/soak/shutdown repetidos); resultado de preferências correlacionado à operação IPC.
- Graphify 592 nós/1197 arestas; AST local; QML revisado/testado diretamente. Legado/sessão pessoal não modificados; nenhum dispositivo pessoal usado.
- Limites: config inválida preservada ainda recusa boot; safe mode pendente. Wake/voz/idioma/discovery sem edição pelo App. Hey DEV-qualified; Okay POC_REQUIRED; EN/fixtures, sem holdout/freeze; comparação Parakeet/Piper/Kokoro pendente.
- CPAL/PipeWire/AEC/hotplug/barge-in/pacote relocável são IMPLEMENTAÇÃO pendente. Pocket cold ~8s/RSS pico ~1.5GB na auditoria anterior, não requalificados nesta rodada. AWAITING_HUMAN_VALIDATION física consolidada após S5.
- Próximo B2.2: discovery de pack com IDs/texto explícito/qualificação/preflight, opções realmente compatíveis e safe mode preservando dados corrompidos; testar persist/restart/rollback/permissões/unsupported e regressões antes de B3.
