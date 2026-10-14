# Agent state — 2026-10-14

- Rodada S1/B1 AUDIT AUTO_VERIFIED em EN/DEV/virtual/offscreen; B2 permanece PLANNED, não iniciado. Mapas docs/BASE_AUDIT.md e docs/BASE_UI_MAP.md.
- Branch main; HEAD de código 2ad4338; fixes Base 82c8783, App 8b16886, harness 2ad4338. Evidência e source→binary em docs/evidence/base-audit.json; nove grupos com MESMO SHA final. Sem remoto/push.
- PASS fmt/check/test/clippy/release/diff-check. 32 Rust, 5 wake nativos, 7 adversariais adicionais; A0–A5 32/44/33/67/138/93 checks, soak 8, shutdown 2, B1 34. Zero failed/ignored.
- Corrigidos: frame 100ms→STT 80ms split sem perda; PCM inválido não enviado; clock Final/Partial; callback STT de sessão antiga/error; hardlinks/descriptor privado; TTS hashes obrigatórios/paths; deadline de executor/feedback timeout; payload IPC/deep JSON; viewport ilegível; ambiente mínimo de workers; sampler /proc de processo encerrado; seed positivo.
- Testes adversariais não substituem inferência/namespace/Qt reais: regressão completa reexecutada, imagem offscreen inspecionada. Legado read-only confirmado ef0a0f3/51 dirty/12 worktrees; datasets/modelos e sessão pessoal preservados.
- Graphify 0.9.90 atualizado (545 nós/1104 arestas); QML revisado diretamente, não indexado. Sem Model Manager/LLM/funções futuras expostas.
- Limites: Pocket cold first PCM em segundos e pico RSS ~1.5GB; números atuais/idle pós EOF no JSON. EN/fixtures sintéticas, sem holdout/pt-BR/freeze; Okay POC_REQUIRED; comparação Parakeet/Piper/Kokoro pendente.
- CPAL/PipeWire/AEC/hotplug/barge-in e pacote relocável são trabalho de IMPLEMENTAÇÃO, não só teste físico. Acústica/periféricos/Wayland: AWAITING_HUMAN_VALIDATION após S5, sem solicitar participação intermediária.
- Próximo: B2 apenas com opções realmente suportadas e discovery/config actor-owned/persistência atômica/restart/rollback, conforme mapa. Não declarar Base para uso físico nem pacote pronto com adapters ausentes. Depois B3 Hub e B4, então S3.
