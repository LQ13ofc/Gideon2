# Agent state — 2026-10-14

- Gate A1 AUTO_VERIFIED/PHYSICAL_PENDING para Hey; A0 regressão PASS; próximo A2 PLANNED. Okay POC_REQUIRED, não certificado (38/52).
- Branch main; source HEAD 545c75181b868853fbae2693e44ebea0276c841a; commits novos 8db34cf (Graphify), 545c751 (catálogo/competição). Checkpoint de evidência posterior identificável no Git.
- PASS: fmt/check/test/clippy/release/diff-check; 12 Rust, 5 nativos, 32 checks A0 + 44 A1, zero ignored. Hey 73/76, 0/320 falsos wakes, 3600s silêncio zero wake. Evidências docs/evidence/a1-selectable-*.json.
- Core release SHA-256 7962ce036363076282790ea87f822a1f0603d2e08796014dc77a4e7dd9944313; worker f484d916f798d6563152c0ac08699ae551a66df5e332028ae489aebeda32c34e. Pico KWS 92532736 bytes, RTF ~0.025; Core sem engine idle 0%, ~3MiB.
- Frase não fixa no Core: catálogo backend + config wake_phrase, seleção validada. Hey padrão; Okay funcional experimental; frases arbitrárias requerem backend/validação. Modelos finais não congelados.
- Graphify 0.9.90 instalado target/graphify-venv, índice local AST; scripts/graph.py; pins scripts/requirements-graphify.txt. Sem LLM, hook, remoto ou alteração de configurações pessoais.
- Autor confirmou Apache-2.0 dos pesos; fonte/hash model card registrados. Distribuição/atribuições pendentes; PCM/corpus sintético DEV fora do Git, sem holdout independente e sem validação física.
- Legado, dispositivos e sessão pessoais preservados; somente commits locais. Próximo slice A2: pre-roll/captura limitada, Silero VAD, endpoint/cancel/EOF/falhas; integrar ao mesmo processo e repetir A0/A1.
