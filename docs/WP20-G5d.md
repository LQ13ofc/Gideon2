# WP-20 · Grupo G5d: fim da tradução da ponte (`app/bridge.py`)

Estado: **concluído** na ponte, nos catálogos EN/FR e nos testes de idioma. Pendências honestas em §6: `test_ui_offscreen.py`
não roda sem o gate (Core real). Nada foi commitado nem enviado.

## 1. Pendências do G5c resolvidas

| Pendência (WP20-G5c §5) | Estado antes | Estado agora |
|---|---|---|
| 1. Literais de `class Bridge` e das 21 funções de texto | 151 ocorrências no filtro de `test_i18n.py`; a leitura ampla achou mais literais de código que o filtro não via (`Cancelamento enviado`, `Aguarde o envio anterior`, `Em espera`, `Desconhecido`, `PENDING_MODELS`, `CHAT_ERROR_ACTION`). Contagem exata desses extras não feita. | 0 ocorrências no filtro. Sobram só docstrings, comentários e nomes de marca/protocolo (`PipeWire (pactl)`, `llama.cpp`, `OpenAI-compatível`, `https://...`). |
| 2. Mensagens guardadas já traduzidas (results, recusas) | Traduzidas no momento do evento: não mudavam ao trocar o idioma. | Guardadas como fonte (`QT_TRANSLATE_NOOP`), como código (`functools.partial(code_message, code)`) ou como fonte com argumentos (`_later(...)`). Leitura pelo `_Results` (dict) e por `_out()`. Teste novo (§3). |
| 2b. `PENDING` e `OPS` | Guardavam o texto português cru (ex.: "Enviando texto ao Core" aparecia em pt em qualquer idioma). | Traduzidos na leitura, como os demais. |
| 3. "em desenvolvimento" | `InicioHoje.qml:126` e `EventLabels.js:310`. | Trocados pelo estado real: "qualificada em corpus sintético; microfone real não validado". Catálogos EN/FR atualizados. `DiagMotores.qml` **não tocado** (outro agente). |
| 3b. Google / Home Assistant "aguardando credenciais" | Não havia texto de estado desses conectores na ponte: o snapshot não traz esse campo (WP-11). | Nada a trocar na ponte. O único texto é `DiagDev.qml:102` ("aguardando credenciais — Google e Home Assistant só são testados com credenciais reais."), coerente com `src/connections.rs:127` (`pronto, aguardando credenciais`). |
| 4. `CfgDispositivos.qml` com `problems === "sem problemas"` | Comparava com texto da ponte. | `msgs_audio.recommendation_view` expõe `problemsOk` (bool) por linha; a tela compara `problemsOk === true` (2 pontos). Arquivo saiu de `PENDING_FILES`. |

## 2. Mudanças principais

- **`app/translations.py`**: `_Messages.raw(key)` devolve a fonte de uma tabela sem traduzir (para guardar e traduzir na leitura).
- **`app/bridge.py`**:
  - `_out(value)`: texto no idioma ativo (chama um callable; traduz uma fonte).
  - `_later(text, *args)`: mensagem com argumentos traduzidos na leitura.
  - `class _Results(dict)`: `__getitem__`, `get`, `values`, `items` passam por `_out`. Os testes e as propriedades que leem `results` continuam iguais.
  - Validadores (`text_problem`, `chat_problem`, `agent_goal_problem`, `custom_form_problem`, `conn_label_problem`, `skill_json`,
    `skill_id_problem`, `skill_description_problem`, `capability_request`, `perception_input_problem`) devolvem a fonte. Os slots de QML
    que devolvem texto traduzem com `_tr` (`chatTextProblem`, `commandProblem`, `agentGoalProblem`, `customFormProblem`, `connectionLabelProblem`).
  - Propriedades calculadas na leitura usam `QCoreApplication.translate` ou `_tr`. `packageInfo` e `registryVisualWarning` passaram de
    `constant=True` para `notify=retranslated`, para reler na troca de idioma.
  - Dados gravados no Core: `license` de modelo personalizado passou de `'Não informada'` para `'-'` (a tela mostra "Licença: -"); o
    rótulo de protocolo `OpenAI-compatível` continua como está (nome técnico, lista `TECHNICAL` no teste).
  - Bug introduzido e corrigido nesta rodada: uma variável local `partial` em `_chat_observe` sombreava `functools.partial` e quebrava o
    caminho de erro do chat (pego por `test_bridge_protocol.py`).
- **`app/msgs_audio.py`**: `problemsOk` em `recommendation_view`.
- **`app/msgs_skills_hub.py`**: progresso do envio passou para `%1`/`%2` (padrão do `_tr`).
- **`app/pages/CfgDispositivos.qml`**, **`app/pages/InicioHoje.qml`**, **`app/shell/EventLabels.js`**: ver §1.
- **Catálogos**: `app/translations/{en,fr}/bridge.py.ts` com 160 mensagens por idioma (154 novas traduzidas nos dois; 6 mantidas);
  `msgs_skills_hub.py.ts` (1 nova por idioma); `InicioHoje.qml.ts` e `EventLabels.js.ts` (1 nova por idioma).
  O `lupdate` (`i18n_tools.py update`) reescreveu as linhas `<location>` de todos os catálogos; é o comportamento esperado da ferramenta.

## 3. Testes

| Comando | Resultado |
|---|---|
| `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_i18n.py` | 15 OK (eram 13; novos: `RecommendationRows` e `StoredMessages`) |
| `... scripts/test_bridge_protocol.py` | 265 OK (1 expectativa ajustada: `Wp20Language` lê o idioma em uso, `translations._tr(OPS[...])`) |
| `target/ui-venv/bin/python scripts/test_snapshot_contract.py` | 20 OK |
| `target/ui-venv/bin/python scripts/test_ui_settings.py` | 25 OK |
| `... scripts/test_languages_qml.py` | 4 OK |
| `... scripts/test_hud_qml.py` | 13 OK |
| `... scripts/test_ui_offscreen.py` | **Não executado com resultado** (ver §6) |

`StoredMessages` (novo): recusas de texto, de LLM e de modelos, e um código do Core (`busy`) são lidos em pt-BR → en → fr → pt-BR,
com `switchLanguage` e sem nenhum evento novo entre as trocas.

## 4. Pacote

- `scripts/build_package.py <dir de teste>`: pacote `gideon-base-0.1.0` montado com sucesso (em diretório de rascunho; apagado depois).
- `scripts/package_closure_check.py <pacote>`: **OK** (10 scripts).
- Verificação extra do `app/` empacotado: 12 módulos, nenhum import local ausente (inclui `msgs_*`, `translations`, `uisettings`, `visual`).

## 5. Limites conhecidos

- Textos de docstring e comentário não são de tela e não são traduzidos.
- `lupdate` avisa de textos iguais em `bridge.py.ts` e `msgs_*.ts` (mesma tradução); `lrelease` mantém uma cópia. Já existia antes desta rodada.
- Os textos de `DiagMotores.qml` (`em desenvolvimento; validação física pendente`) continuam; o arquivo é de outro agente.

## 6. Pendências

- **`test_ui_offscreen.py` não roda aqui.** Ele só executa dentro do namespace bwrap do gate, com um Core real e fases (`--root`, `--artifacts`,
  `--phase`). Sem argumentos sai com erro de uso (exit 2). Precisa ser rodado pelo gate (`scripts/verify_*.py`) em ambiente próprio.
- Textos de conectores (Google/Home Assistant) em tela com estado real dependem do snapshot, que não traz o campo; não foi criado.
