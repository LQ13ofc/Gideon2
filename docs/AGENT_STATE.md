# Agent state — 2026-10-14

- Gate A2 AUTO_VERIFIED/PHYSICAL_PENDING; A0/A1 regressão PASS. Próximo A3 PLANNED (Moonshine Small streaming, CPU).
- Branch main; source HEAD b2bad7d720561a894fca6b1dc30647be6a393a9e; commits novos 8db34cf Graphify, 545c751 wake selecionável, cd6ec7f gate A1, b2bad7d captura. Checkpoint de evidência é posterior no Git.
- PASS fmt/check/test/clippy/release/diff-check; 16 testes Rust, 5 nativos, 32 checks A0 + 44 A1 + 33 A2; zero ignored. A2 SHA-256 PCM exato, cancel e produtor morto depois do wake, integridade VAD/falhas, silêncio/EOF/fala longa/bounds.
- Core release SHA-256 a55f3d414b95d11600771f9ee808ca4ad53a602af9874a99d1004dce64431b43; worker 6c279774140259985390fa08ef98345d418eca8d9d6f32b2d3de4b037e6ebbcf; evidências docs/evidence/a2*.json; Core replay captura pico 4308992 bytes. Sem arquivos de voz ou ação desktop.
- Wake selecionável por catálogo/Config.wake_phrase; Hey padrão (73/76, zero negativos); Okay funciona mas POC_REQUIRED (38/52), sem freeze de modelos ou frase fixa no Core.
- Silero v5 CPU via adapter nativo; 1s pre-roll, >=600ms silêncio, 3s sem fala, 30s PCM máximo, 1s deadline de produtor. Apenas áudio virtual/fixture; CPAL/PipeWire/AEC físicos pendentes.
- Graphify 0.9.90 isolado, scripts/graph.py (AST sem LLM/network), índice atualizado. Legado e sessão pessoais preservados; sem remoto/push/deploy.
- Próximo slice A3: contrato partial/revision/final, préflight/hash SDK/modelos, integrar STT ao mesmo owner desde captura; resultados tardios/partials nunca executam comandos. Parakeet continua candidato futuro, sem escolha definitiva.
