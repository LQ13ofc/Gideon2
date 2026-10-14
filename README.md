# Gideon Base — reconstrução

Core novo Rust, desenvolvido por gates A0→A5 numa única linha. Planejamento: [docs/A0.md](docs/A0.md); checkpoint: [docs/AGENT_STATE.md](docs/AGENT_STATE.md).

```sh
cargo test --offline
cargo build --release --offline
python3 scripts/verify_a0.py
```

Daemon headless: `target/release/gideon-base --root /caminho/privado/isolado [--virtual-input]`. IPC JSON-lines v1 no core.sock dessa raiz. Wake virtual apenas testa infraestrutura. Não abre dispositivos, não executa comandos do desktop e não instala serviço.

Destino futuro: [LQ13ofc/Gideon2](https://github.com/LQ13ofc/Gideon2). Somente commits locais; legado separado e preservado.


A1: adapter experimental de KWS CPU conectado ao mesmo Core, disponível apenas
por replay explícito em namespace bwrap. Não certificado: falsos wakes no DEV
impedem A2. Contrato, resultados e limites: [docs/A1.md](docs/A1.md).

Dependências do worker ficam em venv local, pinadas em
`scripts/requirements-a1.txt`; assets/fixtures privados não são distribuídos.
CLI de desenvolvimento: `--wake-replay ABS_PYTHON ABS_MANIFEST FIXTURE_INDEX`.
Nenhuma seleção de modelo, download ou treinamento no runtime.

Verificação A1 com assets já preparados:
```sh
target/a1-venv/bin/python scripts/test_wake_worker.py
python3 scripts/verify_a1.py
target/a1-venv/bin/python scripts/evaluate_wake.py target/a1-assets/manifest.json target/evidence/a1-quality.json
```
O exit code do avaliador indica execução do experimento; o campo `quality`
indica o resultado do gate. `FAILED` impede avanço, mesmo que o comando termine.
