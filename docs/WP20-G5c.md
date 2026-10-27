# WP-20 · Grupo G5c: mensagens de `app/bridge.py` em módulos `msgs_*` e tradução EN/FR

Estado: **PARCIAL**. Feito e verificado: separação em módulos (com prova de equivalência), empacotamento, teste de
varredura, catálogos EN/FR e tradução das mensagens movidas (650 mensagens por idioma). **Não feito:** as literais
dentro de `class Bridge` e nas funções que ficaram no `bridge.py` (151 ocorrências, 130 textos distintos), a
re-tradução das mensagens guardadas em `results` no momento do evento, e os textos "em desenvolvimento" em três telas
QML. `app/bridge.py` continua em `PENDING_FILES`. Nada foi commitado nem enviado.

## 1. Ferramenta de separação (rodada única)

`scripts/tools/split_bridge_messages.py` (AST, cópia verbatim de cada objeto, sem `sed`/heredoc). Modos:

- `plan`: lista os módulos, as cadeias de importação e os nomes sem resolução (não escreve nada);
- `split`: escreve `app/msgs_*.py`, remove os objetos de `bridge.py`, move `CONTEXT`, `_tr`, `_fill` e `_Messages` para
  `app/translations.py`;
- `verify SNAPSHOT`: compara, objeto por objeto, o `bridge.py` anterior à separação com o novo `bridge.py` e os módulos.

A tabela `OPS` e `PENDING` (dicts) e os `OPS.update(...)` / `PENDING.update(...)` foram divididos por chave de operação,
cada entrada copiada como texto-fonte. Uma função que precisa de um nome que ficou no `bridge.py` (limite, validador)
**não é movida**; a ferramenta a deixa no `bridge.py` (21 funções, ver §3).

Correção feita durante a rodada: uma primeira versão repetia a linha `RESTART_*` três vezes em `msgs_misc.py` (a
ferramenta incluía a instrução anterior na mesma linha). O valor era igual, então a prova passou, mas o módulo foi
reescrito à mão com um único bloco.

## 2. Módulos (7 em vez de 6)

Sete módulos, para que a divisão por tema fique perto de 100 mensagens cada, mas o `llm_models` e o `perception` ficaram
pequenos, porque as funções de texto com validadores ficaram no `bridge.py`.

| Módulo | Textos PT movidos (plan) | Mensagens EN = FR (catálogo) | Conteúdo |
|---|---|---|---|
| `msgs_errors.py` | 100 | 107 | códigos do Core (`CODE_MESSAGES`), `CAPABILITY_MESSAGES`, texto genérico |
| `msgs_audio.py` | 86 | 100 | microfone, saída, escuta ao vivo, assistente de microfone, ações no computador |
| `msgs_connections.py` | 82 | 90 | contas, rotas, permissões, efeitos, operações `connection_*` |
| `msgs_skills_hub.py` | 92 | 110 | skills, Hub, importação, capacidades, operações `skill_*`/`hub_*`/`plugin_*` |
| `msgs_llm_models.py` | 23 | 39 | estados de modelo, agente, chat, operações `secret_*`/`llm_*`/`agent_*` |
| `msgs_perception.py` | 32 | 77 | rótulos e valores de percepção, mensagens de percepção |
| `msgs_misc.py` | 115 | 127 | diagnóstico, frases de ativação, áreas pessoais, idioma, reinício, operações gerais |

Total: 650 mensagens por idioma. `msgs_misc` contém o `OPS={}`/`PENDING={}` e as operações que não pertencem a outro tema.
Dependências entre módulos (sem ciclo): `msgs_errors` ← `msgs_misc` (`PREFS_DONE`), `msgs_misc` ← demais (`OPS`, `PENDING`),
`translations` ← todos.

## 3. O que ficou no `bridge.py`

Vinte e uma funções de texto precisam de nomes que ficaram no `bridge.py` (limites como `TEXT_LIMIT`, validadores como
`llm_url_ok`, `normal_form`, `utf8_len`): `agent_goal_problem`, `bounded_output`, `capability_request`, `chat_problem`,
`code_message`, `conn_label_problem`, `custom_form_problem`, `custom_model`, `devices_status`, `display_effect`,
`json_depth_ok`, `level_view`, `llm_config_problem`, `package_info`, `perception_input_problem`, `recommendation_banner`,
`skill_description_problem`, `skill_id_problem`, `skill_json`, `target_for`, `text_problem`. Mover essas funções exigiria
trazer lógica de validação para os módulos de mensagem.

Além delas, a classe `Bridge` tem 151 ocorrências em 143 linhas (130 textos distintos). **Não traduzidas nesta rodada.**

## 4. Tradução e uso no `bridge.py`

- Tabelas: valores `QT_TRANSLATE_NOOP('Bridge', ...)`, tabelas em `_Messages` (traduzem a cada leitura).
- Constantes de texto (`DEFAULT_DEVICE_LABEL`, `RESTART_*`, `GENERIC_FAILURE`, `STALE_MESSAGE`, `PENDING_SKILL_DRAFT`,
  `REG_VISUAL_WARNING`, `SENSITIVITY_RANGE_TEXT`, `DEVICE_INVALID_TEXT`, ...): traduzidas com `_tr(...)` nos pontos de uso
  do `bridge.py` (21 trocas feitas).
- Funções de texto de `msgs_audio`, `msgs_perception`, `msgs_connections`, `msgs_skills_hub`: `QCoreApplication.translate`
  e `_fill` no ponto de retorno.
- Valores de `OPS`/`PENDING` continuam como texto-fonte e só são traduzidos quando o `bridge.py` os usa (ver §5).

## 5. Pendências (não feitas)

1. **`class Bridge` e funções de §3** (151 ocorrências, 130 textos): trocar por `QCoreApplication.translate('Bridge', ...)`
   e escrever EN/FR. Até lá `app/bridge.py` segue em `PENDING_FILES` e os textos desses pontos saem em português.
2. **Mensagens guardadas em `results` / recusas** (`self.results[...]=...`, `_refuse(...)`): guardam o texto já traduzido
   no momento do evento. Ao trocar o idioma, o texto só muda no próximo evento. Para cumprir "a ponte re-emite ao trocar
   o idioma", o texto deve ser guardado como fonte e traduzido na leitura (propriedade). Não feito.
3. **Textos "em desenvolvimento" em QML** (o relato do Core já diz o estado real, mas as telas não):
   - `app/pages/InicioHoje.qml:126` (`dev_qualified` → "em desenvolvimento");
   - `app/shell/EventLabels.js:310` (`wakeQualificationLabels`, mesmo caso);
   - `app/pages/DiagMotores.qml:307` (pacote `dev_virtual_en` → "em desenvolvimento; validação física pendente").
   Devem dizer o estado real ("qualificada em corpus sintético; microfone real não validado", "pacote de teste virtual ·
   validação física pendente"), com catálogos QML atualizados. Não feito.
4. **Google e Home Assistant "aguardando credenciais"**: o texto existe em `app/pages/DiagDev.qml:102`. No `bridge.py` não há
   texto de estado do Google, então não havia o que trocar do lado da ponte.
5. **`scripts/build_package.py`**: os módulos foram incluídos na lista de arquivos; a verificação de fechamento
   (`scripts/package_closure_check.py`) **não foi executada** sobre um pacote montado nesta rodada.
6. **`scripts/test_ui_settings.py`** e **`scripts/test_ui_offscreen.py`**: não executados nesta rodada.

## 6. Catálogos e lupdate

- Catálogos `app/translations/{en,fr}/msgs_*.py.ts` escritos à mão (EN e FR, 650 mensagens cada). `i18n_tools.py update`
  foi rodado várias vezes, e o `lupdate` regravou os arquivos com `<location>`.
- Perda registrada: ao mover as mensagens do G5b, o `lupdate` (com `-no-obsolete`) removeu do `bridge.py.ts` as 45
  traduções já feitas (DIAG, HUB_UPLOAD, MODEL_STATUS, PERCEPTION_INDICATOR, WAKE). Foram refeitas nos catálogos dos módulos
  novos, com os mesmos textos.
- `scripts/test_i18n.py`: `PENDING_FILES` agora contém só `app/bridge.py` e `app/pages/CfgDispositivos.qml`. A varredura
  inclui os módulos `msgs_*`. O padrão `QT_TEXT_CALL` passou a aceitar contexto entre aspas simples
  (`QT_TRANSLATE_NOOP('Bridge', ...)`), que é o estilo usado.

## 7. Prova de equivalência

- Contra o `bridge.py` anterior à separação (snapshot da árvore de trabalho): **465 objetos, 0 diferenças** (`verify`,
  executado logo após o `split`). Funções e lambdas são comparados pelo bytecode; sentinelas `object()` são tratadas como
  iguais.
- Contra `git show HEAD:app/bridge.py`: **5 diferenças**, todas do trabalho G5b ainda não commitado
  (`WAKE_QUALIFICATION_LABELS`, `model_status`, `PERCEPTION_UNREAD`, a classe `Bridge`). A separação não introduziu
  diferença em relação ao snapshot.
- Depois da tradução, `verify` mostra as diferenças esperadas: 15 funções com chamadas de tradução e 2 lambdas de `OPS`
  (`wake_phrase_validate`, `hub_approve`). As tabelas de dados têm os mesmos valores-fonte que o snapshot.

## 8. Testes (nesta rodada)

| Comando | Resultado |
|---|---|
| `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_i18n.py` | 13 OK |
| `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_bridge_protocol.py` | 265 OK (antes: 1 falha em `AudioQml`) |
| `target/ui-venv/bin/python scripts/test_snapshot_contract.py` | 20 OK |

Alterações nos testes para corrigir a falha de `AudioQml` (`hojeLiveHint`), que é do `InicioHoje.qml`:
- o texto "Microfone desligado: ative em Dispositivos para usar a voz." tem ponto final (`docs/WP20-G2.md` §80 diz isso);
  o teste esperava sem ponto. Corrigido o teste.
- o texto da escuta consentida é "O microfone será ativado ao reiniciar o Core." (QML). O teste esperava sem o "O". Corrigido
  o teste.

## 9. Arquivos alterados

- Novos: `scripts/tools/split_bridge_messages.py`, `app/msgs_errors.py`, `app/msgs_audio.py`, `app/msgs_connections.py`,
  `app/msgs_skills_hub.py`, `app/msgs_llm_models.py`, `app/msgs_perception.py`, `app/msgs_misc.py`,
  `app/translations/{en,fr}/msgs_*.py.ts` (14 arquivos), `docs/WP20-G5c.md`.
- Alterados: `app/bridge.py` (separação e 21 trocas por `_tr`), `app/translations.py` (helpers movidos, `QCoreApplication`),
  `scripts/build_package.py` (lista de arquivos), `scripts/i18n_tools.py` (`PYTHON_SOURCES`), `scripts/test_i18n.py`
  (varredura, `PENDING_FILES`, padrão de contexto), `scripts/test_bridge_protocol.py` (2 expectativas de `hojeLiveHint`).
- Gerados: `app/translations/gideon_{en,fr}.qm`, `graphify-out` (`scripts/graph.py`, somente AST).
