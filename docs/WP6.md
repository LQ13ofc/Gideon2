# WP-6: adaptador LLM local (llama.cpp), agente com LLM real e rascunho de Skill por LLM

Itens do docs/GAP_AUDIT.md: LLM-01, LLM-02, LLM-03, SKILL-01.

| Item | Status | Evidência |
|---|---|---|
| LLM-01 adaptador llama.cpp/GGUF | FEITO (neste PC, CPU) | gate R1 a R6, docs/evidence/wp6-llm.json |
| LLM-02 loop do agente com LLM real | FEITO no escopo de ferramenta somente leitura | gate R9 |
| SKILL-01 rascunho de Skill por LLM | PARCIAL: Core e plugin FEITOS; aba "Criar" da UI ainda não ligada (WP-17) | gate R7 |
| LLM-03 provedores remotos (OpenAI-compatível e Anthropic) | PARCIAL: Anthropic NÃO feito; nova rodada ao vivo bloqueada (chaves do dono ausentes nesta sessão) | ver seção 6 |

## 1. Downloads aprovados pelo dono (hash conferido)

Autorização do dono: llama.cpp (build CPU) e um GGUF pequeno de instrução. Ambos foram baixados para
uma pasta nova e vazia, conferidos pelo hash publicado antes de qualquer uso, e ficam FORA do repositório:
`/home/lucas/.local/share/gideon-llm/` (`dl/`, `bin/`, `run/`). Manifesto: `scripts/llm_manifest.json`.

| Item | Origem | Tamanho (bytes) | sha256 (publicado) | Licença |
|---|---|---|---|---|
| llama.cpp b11552, `llama-b11552-bin-ubuntu-x64.tar.gz` (CPU, x86_64, GCC 11.4) | https://github.com/ggml-org/llama.cpp/releases/tag/b11552 (publicado em 2026-10-10) | 17824766 | `a45a6afda05d08028bd37998072ab602c96799bccde126835941623cb99bb727` (digest do asset na API do GitHub) | MIT |
| Qwen2.5-1.5B-Instruct, GGUF Q4_K_M, `qwen2.5-1.5b-instruct-q4_k_m.gguf` | https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF | 1117320736 | `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e` (LFS oid do repositório) | Apache-2.0 (README e LICENSE do repositório) |

Comandos de download e conferência (executados nesta sessão):

    curl -sSL -o llama-b11552-bin-ubuntu-x64.tar.gz https://github.com/ggml-org/llama.cpp/releases/download/b11552/llama-b11552-bin-ubuntu-x64.tar.gz
    sha256sum llama-b11552-bin-ubuntu-x64.tar.gz          # a45a6afd... (igual ao publicado)
    curl -sSL -o qwen2.5-1.5b-instruct-q4_k_m.gguf https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf
    sha256sum qwen2.5-1.5b-instruct-q4_k_m.gguf           # 6a1a2eb6... (igual ao LFS oid)

Escolha da versão: a build 11552 é de 2026-10-10 (mais de duas semanas antes desta entrega). A release
"latest" da API era um placeholder (`nightly-tag.txt`), por isso não foi usada.

## 2. O que foi implementado

- `scripts/llm_local.py` (stdlib): `verify` (sha256 do pacote e do GGUF contra o manifesto), `extract`
  (extração segura: rejeita caminhos absolutos, `..`, hard links e links que saem do destino; links
  relativos internos são aceitos, o llama.cpp os usa), `start` (verifica o modelo, sobe
  `llama-server` em `127.0.0.1:PORTA` com `--no-webui`, espera `/health`), `stop` (SIGTERM ao pid
  registrado, só se a linha de comando for o nosso servidor e a porta for a nossa; SIGKILL após 15 s),
  `status`.
- `scripts/llm_engine_plugin.py`: plugin `llm_engine` 1.3.0 de produção. É a cópia do fixture
  `tests/fixtures/llm_engine.py` sem o modo roteirizado (`agent_script` é ignorado e o código foi
  removido), com o catálogo real (entrada `local-qwen2.5-1.5b-q4km`, sha256 e licença do manifesto,
  certificação `certified` somente para este PC e este build, com evidência). Mudanças em relação ao
  fixture:
  - decodificação gulosa (temperatura 0) quando a chamada traz ferramentas ou é rascunho de Skill;
  - rascunho de Skill com `response_format: json_object` e um prompt com o esquema exato do Core e as
    três ferramentas somente leitura conhecidas (`tool:get_time`, `tool:get_date`, `tool:get_status`);
  - normalização determinística do rascunho (`_normalize_skill`): mantém só passos com essas
    ferramentas, recalcula `dependency_capabilities` e registra cada remoção em `ambiguities`. O Core
    continua validando tudo (`skills.validate`); nada é aprovado.
- `tests/fixtures/llm_hub_prod.json`: catálogo Hub com o sha256 e o tamanho do plugin de produção.
  O gate confere esse hash (R1). A URL do binário aponta para o caminho do arquivo no repositório
  (`https://github.com/LQ13ofc/Gideon2/blob/main/scripts/llm_engine_plugin.py`); NÃO existe release com
  esse binário ainda (ver seção 7).
- `scripts/llm_bench.py`: medidas independentes: TTFT do cliente e tok/s de decodificação e de prompt
  com os `timings` do próprio llama.cpp.
- `scripts/llm_gate.py`: gate real. Usa o Core de release sem flags de teste, o plugin instalado pelo
  Hub, o servidor real e o modelo real. Escreve `docs/evidence/wp6-llm.json` com `--write-evidence`.
- `scripts/llm_test_plugin.py`: 17 testes unitários (normalização, formato de requisição, hash do
  catálogo, extração segura, resumo das medidas).
- `docs/evidence/wp6-llm.json`: evidência do gate final.

Não alterados (não foram necessários): `src/*.rs`, `src/broker.rs`, `src/llmcfg.rs`,
`scripts/net_broker.py`, `src/skills.rs`. O provedor local já roteia `127.0.0.1` sem chave e sem
consentimento (`src/broker.rs` `target`, `src/llmcfg.rs` `validate`), e o caminho de skills já existe
(`skills.validate`, `skills.draft_put`, `skills.dry_run`).

## 3. Comandos executados (com resultado)

    python3 -I scripts/llm_local.py verify --manifest scripts/llm_manifest.json --archive <pacote> --model <gguf>
    -> {"ok": true, checks: archive_sha256 a45a6afd..., model_sha256 6a1a2eb6...}

    python3 -I scripts/llm_local.py extract --manifest scripts/llm_manifest.json --archive <pacote> --bin-dir <bin>
    -> {"members": 61, "ok": true}; <bin>/llama-b11552/llama-server --version -> 0.6.0-dev (build 11552)
    (a primeira versão rejeitava os links simbólicos do pacote; corrigido e coberto pelos testes)

    python3 -I scripts/llm_local.py start --manifest ... --bin-dir <bin> --model <gguf> --run-dir <run> --port 8080 --threads 8
    python3 -I scripts/llm_local.py stop --run-dir <run>        -> sigterm, port_closed true

    python3 -I scripts/llm_bench.py --port 8080 --runs 5 --max-tokens 128   (uma execução por número de threads)

| Threads | Decodificação (tok/s, mediana) | TTFT mediana (s) | Observação |
|---|---|---|---|
| 4 | 31.6 | 0.203 | |
| 6 | 30.8 | 0.211 | |
| 8 | 36.0 (1ª execução) | 0.172 | = núcleos físicos (i9-9900K: 8 núcleos, 16 threads) |
| 16 | 1.2 | 1.128 | SMT satura: queda de ~30 vezes |

Os números de 4, 6 e 16 threads vieram da saída do console desta sessão e não foram arquivados. Os
números do gate final estão em `docs/evidence/wp6-llm.json`.

    python3 -I scripts/llm_test_plugin.py   -> Ran 17 tests, OK
    python3 -I scripts/llm_gate.py --write-evidence   -> PASSED, rc 0, 16 checagens, sem processo remanescente

## 4. Resultados do gate final (docs/evidence/wp6-llm.json)

| Check | Resultado |
|---|---|
| R1 sha256 do pacote e do GGUF iguais aos publicados | PASS |
| R1 hash e tamanho do catálogo Hub iguais ao plugin | PASS |
| R2 `llama-server` sobe em 127.0.0.1 com `/health` ok | PASS |
| R3 medida direta: 5 execuções com timings do servidor | PASS: TTFT mediana 0.146 s; decodificação 37.6 tok/s; prompt 167 tok/s |
| R4 plugin `llm_engine` 1.3.0 em execução pelo Hub | PASS |
| R4 rota local configurada, sem chave e sem consentimento | PASS |
| R4 entrada Qwen listada por `llm_engine.models` | PASS |
| R4 `describe` devolve a entrada com certificação e sha256 | PASS (certified) |
| R5 selftest pelo Core: streaming ok | PASS (220 ms) |
| R5 tool_use sondado (valor medido: supported) | PASS |
| R6 cinco turnos de chat pelo Core, respostas não vazias, parciais vistos | PASS |
| R7 rascunho de Skill pelo modelo: validado e guardado como `draft` | PASS (8.3 s) |
| R7 Core registrou `skill_draft_put`; nada aprovado, ativado ou executado | PASS |
| R9 loop do agente com o modelo: chamada `get_time` executada pelo Core, resposta final | PASS |
| R8 servidor parado, porta fechada; pasta temporária do Core removida | PASS |

Medidas pelo Core (cliente): TTFT entre 0.123 e 0.164 s nos cinco turnos; turnos completos de 0.2 a 2.8 s
(conforme o tamanho da resposta). Chat de exemplo: "A capital do Brasil é Brasília." Rascunho gerado:
`say_current_time_portuguese@1.0.0`, um passo `tool:get_time`, sem ambiguidades. Loop do agente: passos
`chat`, `tool` (get_time, risco read, done), `chat`; resposta final com a hora real do Core.

## 5. Decisões técnicas e medidas que as justificam

- Decodificação gulosa para ferramentas e rascunhos. Medido com o prompt do agente do Core, em streaming:
  temperatura 0 gerou a chamada `get_time` em 4 de 4 execuções; amostragem padrão em 0 de 4 e 1 de 4 (outra
  rodada). Sem isso o loop do agente terminava com texto ("[get_time]") em vez de chamada de ferramenta.
- Normalização do rascunho. Em uma execução real o modelo inventou `tool:translate_time` e
  `tool:say_time`; o Core recusou com `skill_invalid`. A normalização remove esses passos antes da
  validação do Core e deixa registrado em `ambiguities`. O Core ainda valida tudo.
- Limite de ferramentas do rascunho. O plugin só conhece as três ferramentas somente leitura. Uma skill que
  altera o computador não é gerada pelo LLM neste pacote.
- Esquema no prompt. Sem o esquema exato (campos, regras de slug/semver, `min_runtime`), a primeira
  tentativa do modelo falhou com `model_output_invalid`.

## 6. Limites honestos

- `llama-server` NÃO roda dentro do bwrap. Roda como processo local supervisionado, escuta só em
  127.0.0.1 e com a interface web desligada. O plugin, que trata os dados do usuário, roda no bwrap do Core
  sem rede (o contrato de plugins já existente). Envolver o servidor no bwrap exigiria ponte de socket
  (o broker usa TCP) e gestão de árvore de processos; não foi feito.
- O Core NÃO inicia nem para o servidor. Hoje é preciso rodar `scripts/llm_local.py start` (WP-17, seção 7).
- Fallback: a lógica do plugin continua coberta pelos testes do gate C2 (com servidor falso). Não foi
  exercitada com o modelo real.
- LLM-02: só ferramenta de leitura. Uma ação que altera o computador com o modelo real não foi testada;
  a aprovação de ferramentas continua coberta pelo gate C3 com LLM roteirizado.
- Qualidade do modelo: 1.5B, Q4_K_M. As chamadas de ferramenta só foram confiáveis com decodificação gulosa;
  os rascunhos precisam da normalização. Não avaliei qualidade de resposta além dos exemplos do gate.
- Temperatura 0 também vale para chamadas com ferramentas enviadas a provedores de nuvem (respostas mais
  determinísticas). Não reexecutei provedores de nuvem depois dessa mudança.
- LLM-03: o adaptador OpenAI-compatível (provedores google, openrouter, opencode, custom) já existe pelo
  broker; o último teste ao vivo foi do C2 (Google e Mistral PASSED; OpenRouter 403, OpenCode 402, DeepSeek
  402, ZenMux 403). Nesta sessão o arquivo de chaves do dono
  (`/tmp/claude-1000/.../scratchpad/k/`) não existia; não houve nova chamada ao vivo.
- LLM-03 Anthropic: NÃO implementado. Exige mudanças em arquivos fora da minha lista (seção 7, item 5).
  Não há chave Anthropic disponível para teste ao vivo.
- Core usado nas medidas: `target/release/gideon-base` com sha256
  `b504756cf85a24fc6b545064bb5ddf6cc535d484bab9513081c0421f2165af83` (compilado às 16:09 por outro agente,
  durante a sessão; eu não recompilei). Nenhum Rust foi alterado neste pacote.
- Outro agente tinha um `gideon-base` de exploração em execução durante o gate (não era meu; não foi
  encerrado).

## 7. Mudanças que o WP-17 precisa fazer (arquivos que eu não toquei)

1. Ciclo de vida do `llama-server`: o Core (ou o launcher) deve iniciar `scripts/llm_local.py start` quando
   a rota local estiver configurada, parar ao sair e expor a saúde no snapshot. Provável: `src/core.rs`,
   `src/transport.rs`, launcher.
2. Catálogo de produção: `tests/fixtures/llm_hub_prod.json` tem nome de fixture. O empacotador
   (`scripts/build_package.py`) deve gerar o catálogo a partir de `scripts/llm_engine_plugin.py` e publicar o
   binário na URL declarada. Hoje essa URL aponta para o caminho do arquivo no repositório, sem release.
3. `app/pages/Skills.qml`, aba "Criar": chamar `llm_engine.skill_draft` com `{description, name?}`, mostrar
   o rascunho e as ambiguidades, e aprovar só pelo fluxo existente (`SkillApprove`). Se a ponte não tiver a
   operação de capability, `app/bridge.py`.
4. `Modelos LLM` (Qt): nada obrigatório, o modelo aparece pelo catálogo. Mostrar a nota de hardware
   ("certificado somente neste PC, CPU i9-9900K") junto do selo "Certificado".
5. Anthropic (completo, ainda não iniciado):
   - `src/plugins.rs`: a checagem `args.path == broker::CHAT_PATH` precisa aceitar o caminho do provedor
     (Anthropic usa `/messages`);
   - `src/secrets.rs`: slot de chave do provedor Anthropic (no cofre de 0600);
   - meus arquivos, ainda não tocados: `src/llmcfg.rs` (provedor, base fixa), `src/broker.rs` e
     `scripts/net_broker.py` (cabeçalhos `x-api-key` e `anthropic-version` em vez de `Authorization`), e um
     tradutor de mensagens e de SSE no plugin;
   - teste: servidor falso Anthropic e, quando houver chave do dono, uma rodada ao vivo.

## 8. Outros pontos

- Nada foi commitado nem enviado. Os arquivos novos estão como não rastreados; quem faz o commit é o
  orquestrador.
- `docs/GAP_AUDIT.md`: linhas LLM-01 (FEITO), LLM-02 (FEITO no escopo indicado), LLM-03 (PARCIAL),
  SKILL-01 (PARCIAL). Nenhuma outra linha foi alterada por mim.
- `docs/AGENT_STATE.md` não foi alterado (é do orquestrador).
- Gates Rust (cargo fmt, clippy, test) e os gates C1/C2/C3 não foram rodados: nenhum arquivo Rust foi
  alterado e o fixture `tests/fixtures/llm_engine.py` não mudou.
- Como reproduzir: baixar os dois arquivos (seção 1), `scripts/llm_local.py extract`, então
  `python3 -I scripts/llm_gate.py --write-evidence` (usa `target/release/gideon-base` e a pasta de execução em
  `~/.local/share/gideon-llm`; sem chaves).
