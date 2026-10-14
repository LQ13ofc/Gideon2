# Agent state — 2026-10-14

- B2.2b AUTO_VERIFIED: pack interno versionado/preflight/discovery e seleção de wake qualificado Core→Qt. B2 IN_PROGRESS; B3 não iniciado. Contratos docs/B2.md, mapa docs/BASE_UI_MAP.md.
- Branch main; HEAD de código 3d8a858; anteriores a2e765c/0db2270 e B2.1 preservados. Local somente; sem remoto/push/deploy.
- PASS fmt/check/test/clippy -D warnings/release/diff-check. 37 Rust, 16 Python nativos/adversariais, 36 checks B2.2b. Regressões A0/A1/A2/A3/A4/A5/B1/soak/shutdown/B2.1/safe 32/44/33/67/138/93/34/8/2/31/96 = 578. Zero failed/ignored na rodada final.
- Mesmo SHA release em onze grupos: df44535e0cb59c75fad6bb99827198ddd320126ec14809efa9c5e31da6f0fe6d. Source→binary/inputs/commits/resultados docs/evidence/b2-pack.json. Screenshot mínimo target/evidence/b2-pack.png inspecionado.
- --base-pack usa perfis/qualificação por hash; verifica modelos/keywords/VAD/STT/TTS antes de workers. Catálogo sem paths, texto explícito separado de IDs/labels; defaults/ativo/salvo distintos. Hey DEV-qualified; Okay POC_REQUIRED bloqueado no Core/App. Alba/EN candidato somente.
- SelectWake exige idle/revisão/ID qualificado; alteração/rollback completos no mesmo JSON atômico→restart_required. Config não compatível→safe mode; recuperação/reinício com S1 nativo real passou. Teste ID opaco/texto Activate Atlas cerca Core genérico, sem alegar KWS arbitrário treinado.
- Corrigidos: aliases públicos de modelos resolvidos+hash guard sem modificar assets; checksum de evidência calculado antes de apagar fixture; RangeInclusive clippy. Config privada continua recusando symlink/hardlink. Snapshot/preflight não prova readiness física/assinatura publisher.
- Graphify 670 nós/1391 arestas, AST local; QML/testes runtime diretos. Legado/sessão pessoal não alterados; nenhum device pessoal usado. Sem Model Manager/LLM na Base.
- Limites: EN/DEV sintético, sem holdout/freeze; Parakeet/Piper/Kokoro comparação pendente. CPAL/PipeWire/AEC/hotplug/barge-in/pacote relocável são IMPLEMENTAÇÃO pendente. AWAITING_HUMAN_VALIDATION física consolidada após S5.
- Próximo B2.3: fechar matriz das preferências suportadas (feedback visual/ganho real da saída virtual/privacy/retention); devices/sensibilidade/performance/login só configuráveis quando houver backend comprovado. Depois gate B2 completo antes de B3.
