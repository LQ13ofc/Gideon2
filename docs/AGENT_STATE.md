# Agent state — 2026-10-14

- Gate atual A1 INTEGRATED / FAILED (qualidade do candidato); A0 AUTO_VERIFIED confirmado por regressão. A2 NÃO INICIADO.
- Branch main; HEAD de código 2ae148ce81a19598051395a2ed3774991d210f5c; A0 f737824; checkpoint de evidência é commit posterior, identificar por `git log -1`. Sem remoto/push/deploy.
- PASS: fmt/check/clippy/release/diff-check; 11 testes Rust, 3 nativos, 32 checks de processo A0 e 25 A1. Zero testes ignorados. A1 candidato FAILED: 73/76 positivos e 29/320 negativos ativados. DEV threshold 0.5: 35/76 positivos, 16 falsos wakes; rejeitado.
- Build release SHA-256 198f17a7613c65a04dc3334967f9f11bb9838071bfb32983068b8f7fc3d8151d; worker SHA-256 139b0644ecd4e6865c4041bf2a203300d96eb9a29bfb456207fa752460e56990; fontes/modelos/corpus e resultados em docs/evidence/a1-*.json. PCM privado fora do Git.
- Recursos: Core sem engine idle 0.0%, RSS 3207168 bytes; avaliador KWS VmHWM 92393472 bytes, RTF 0.0250; replay 3600s de silêncio sem wake. Não prova FAR ambiental, qualidade física ou listener de produção. ru_maxrss discrepante excluído da medição.
- Correções: timestamp native após reset, validação de hashes/frase/PCM, falha fechada/cleanup de worker, namespaces privados e stream em janelas com sobreposição. Teste real na fronteira de 10s PASS. Nenhum microfone/speaker/bus pessoal usado.
- Legado só leitura, 12 worktrees/alterações preservados; nenhuma importação de código. Modelos/datasets antigos não certificados nem redistribuídos.
- Bloqueio técnico A1: discriminar Hey/Okay/Hi Gideon; fonte DEV sintética insuficiente para certificação; direitos dos pesos ainda não fechados. Não mascarar falha técnica como pendência física.
- Próximo slice: permanecer A1, desenvolver/avaliar KWS específico com proveniência e corpus independente autorizado; repetir gates atuais antes de A2. AWAITING_HUMAN_VALIDATION apenas para física, rodada consolidada após S5; nenhuma participação humana solicitada agora.
