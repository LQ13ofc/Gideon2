# Agent state — 2026-10-14

- B2.2a AUTO_VERIFIED: modo seguro/recuperação de config privada no Core + Qt. B2 IN_PROGRESS; catálogo/troca de wake pendentes; B3 não iniciado. Contratos docs/B2.md, mapa docs/BASE_UI_MAP.md.
- Branch main; HEAD de código a2e765c. B2.1 7e4d241/929afe8 preservados; testkit 910efcd. Local somente, sem remoto/push/deploy.
- PASS fmt/check/test/clippy -D warnings/release/diff-check. 36 Rust, 15 Python nativos/adversariais, 96 checks B2.2a. Regressões A0/A1/A2/A3/A4/A5/B1/soak/shutdown/B2.1 32/44/33/67/138/93/34/8/2/31 = 482. Zero failed/ignored.
- Mesmo SHA release em dez grupos: e68b94e92b255b1cc6cb749a05d2b2993aeb1d1f12fe1903815c514ba313f901. Source→binary/commits/resultados docs/evidence/b2-safe-mode.json. Imagem offscreen mínima target/evidence/b2-safe-mode.png inspecionada.
- Conteúdo/schema/ranges inválidos entram safe_mode sem engines/sessões/executores, até com flags apontando packs inexistentes. IPC privado preservado; sem payload inválido em snapshot/audit. Arquivos inseguros continuam recusando boot.
- RecoverConfiguration exige revisão/epoch do boot e request_id; preserva bytes privados, recusa config alterada/artefato inseguro/falha de escrita; commit atômico→restart_required. Depois de reinício real: Wake/STT/comando verificado/Pocket PCM funcionando com Qt. Core cerca wake nativo mesmo em chamadas internas.
- Limites recuperação: arquivo >4096 bytes preservado, sem recuperação automática; config.invalid.json preexistente diferente/insegura bloqueia sobrescrita. UI informa reinício, não controla daemon. Compatibilidade de wake/voz/pack ainda é próximo gate.
- Graphify 629 nós/1281 arestas; AST local e Qt/QML revisado diretamente. Helpers offscreen compartilhados; legado/sessão pessoal não modificados, nenhum dispositivo pessoal usado.
- Hey DEV-qualified, Okay POC_REQUIRED; EN/fixtures, sem holdout/freeze; comparação Parakeet/Piper/Kokoro pendente. CPAL/PipeWire/AEC/hotplug/barge-in/pacote relocável continuam IMPLEMENTAÇÃO pendente. AWAITING_HUMAN_VALIDATION física consolidada após S5.
- Próximo B2.2b: discovery versionado de pack, IDs/texto explícito/qualificação e preflight; só opções compatíveis/certificadas DEV no App. Testar unsupported/permissões/persist/restart/rollback, fluxo real e regressões antes de B3. Sem Model Manager/LLM na Base.
