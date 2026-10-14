# Navegação local do projeto

CLI Graphify 0.9.90 (`graphifyy` no PyPI), instalado somente em
`target/graphify-venv`. Fonte: https://github.com/Graphify-Labs/graphify e
https://graphiffy.com/docs/cli. O executável global preexistente 0.9.62 e as
configurações pessoais foram preservados.

Uso: `python3 scripts/graph.py` atualiza somente AST, sem clustering/LLM.
`python3 scripts/graph.py query "WakeDescriptor Config" --budget 1000`,
`path` e `explain` consultam `graphify-out/graph.json`. Verificar respostas
contra fonte, principalmente relações inferidas ou resultados truncados.
Índice é local, descartável e ignorado por Git; nenhum hook/background ou
registro global instalado. HOME/cache isolados e chaves de providers removidas
no subprocesso. Não executar o indexador sobre legado/datasets.

Reprodução da instalação em ambiente do projeto:
```
uv venv target/graphify-venv
uv pip install --python target/graphify-venv/bin/python -r scripts/requirements-graphify.txt
python3 scripts/graph.py
```
A versão pesquisada suporta `update --no-cluster`, query/path/explain; o índice
foi gerado e consultado com sucesso. Código Rust/Python modelado; dados de
Cargo.toml e reexports de src/lib.rs não geraram símbolos no extrator.
