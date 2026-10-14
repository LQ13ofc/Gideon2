# Gideon Base — reconstrução

Core novo Rust, desenvolvido por gates A0→A5 numa única linha. Planejamento: [docs/A0.md](docs/A0.md); checkpoint: [docs/AGENT_STATE.md](docs/AGENT_STATE.md).

```sh
cargo test --offline
cargo build --release --offline
python3 scripts/verify_a0.py
```

Daemon headless: `target/release/gideon-base --root /caminho/privado/isolado [--virtual-input]`. IPC JSON-lines v1 no core.sock dessa raiz. Wake virtual apenas testa infraestrutura. Não abre dispositivos, não executa comandos do desktop e não instala serviço.

Destino futuro: [LQ13ofc/Gideon2](https://github.com/LQ13ofc/Gideon2). Somente commits locais; legado separado e preservado.
