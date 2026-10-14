# Agent state — 2026-10-14

- Gate A3 AUTO_VERIFIED/PHYSICAL_PENDING (EN/DEV); A0–A2 regressão PASS. Próximo A4 PLANNED. Ainda sem execução de comandos/TTS/UI/LLM.
- Branch main; HEAD de código bf7d5acbec3b1a48148fe74cc714c2ebed082155; commits novos 8db34cf Graphify, 545c751 wake selecionável, b2bad7d captura, bf7d5ac STT; checkpoints de evidência posteriores no Git.
- PASS fmt/check/test/clippy/release/diff-check; 18 Rust, 5 nativos; 32 checks A0, 44 A1, 33 A2, 67 A3; zero ignored. 4/4 vozes finalizam open Brave, partial antes de EOF, cancel/late/revision/early-final/model-hash/worker-death/fila cheia.
- Release SHA-256 014c9054cb5c2fdf9d6e8adec65b749e0e68fba546d0eefe12edb002e56e824b; source/worker/helper/model pins em docs/evidence/a3*.json e scripts/requirements-stt.txt. STT carregado idle 0%/2s, soma RSS até 431108096 bytes após fixture EOF; não medida de listener físico contínuo.
- Corrigido EOF perdido por sender retido no Core após adicionar STT; regressão específica e A0–A2 reexecutadas. Modelo/SDK CPU em worker supervisionado, VAD interno da SDK desativado, final só após endpoint do Core; partial nunca concede ação.
- Wake genérico por catálogo + config wake_phrase: Hey padrão qualificado DEV; Okay funciona mas POC_REQUIRED. Nenhuma frase fixa no Core nem escolha definitiva de modelo. Parakeet permanece candidato antes de freeze.
- Graphify 0.9.90 isolado, scripts/graph.py; índice AST atualizado e consultado, sem LLM/hook/config global. Legado, modelos/datasets/alterações e sessão pessoais preservados; nada publicado ou enviado.
- Limites: inglês e fixtures sintéticas; sem holdout independente, pt-BR ou qualidade física comprovados. Human validation apenas rodada consolidada após S5; não solicitar testes/instalação ao usuário.
- Próximo slice A4: parser determinístico → Safety/capability/grant → executor tipado sandbox → receipt/verify; negar negação/hipótese/ambiguidade, duplicatas/partials e resultados tardios; depois A5 Pocket TTS virtual.
