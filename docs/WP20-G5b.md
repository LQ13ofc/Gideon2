# WP-20 · Grupo G5b: textos da ponte, acoplamentos de tela e explorador en/fr

Estado: **PARCIAL**. Feitos e verificados: acoplamentos frágeis (códigos estáveis na ponte, QML sem texto em português),
mapeamento de campos do catálogo de idiomas, `explore_setup.py --ui-language`, correção da expectativa de `CfgVoz`, e
explorador em inglês e francês com capturas vistas. **Não feito:** a migração das mensagens de `app/bridge.py` para o
auxiliar de tradução. Restam cerca de 640 textos em português (ver §3). Nada foi commitado. Nenhum download foi feito.

## 1. Acoplamentos corrigidos (codigos estáveis ao lado do texto)

| Antes (QML comparava texto em português) | Agora | Onde |
|---|---|---|
| `core.hubDescription.indexOf("quarentena")` decide o banner | `core.hubQuarantined` (bool), a partir de `hub.status == 'quarantined'` e do Core online | `app/bridge.py` (propriedade nova), `app/pages/Plugins.qml` (1 linha) |
| `ModelosLlm.statusLabel/statusTone(core.modelsStatus)` com `QT_TR_NOOP` de texto | `core.modelsStatusCode`: `testing`, `no_config`, `no_key`, `no_consent`, `no_model_data`, `tool_use_unsupported`, `available` | `bridge.py` (`model_status_code`; `model_status` continua devolvendo o texto), `ModelosLlm.qml` |
| `Percepcao.indicatorWord/indicatorTone/indicatorColor` com `QT_TR_NOOP("ligado")` etc. | `core.perceptionMicState` / `perceptionCameraState`: `on`, `off`, `unread`, `plugin_inactive` | `bridge.py` (`_indicator_state`), `Percepcao.qml` (troca de nome nas chamadas e funções) |

Os textos (`modelsStatus`, `perceptionMicIndicator`, `perceptionCameraIndicator`, `hubDescription`) continuam existindo
e são traduzidos no momento da leitura (`MODEL_STATUS_TEXTS`, `PERCEPTION_INDICATOR_TEXTS`, `QCoreApplication.translate`).
Os testes da ponte que comparam esses textos em pt-BR passam sem alteração.

## 2. Catálogo de idiomas (`src/languages_catalog.json`)

- `license`, `quality`, `reason` e `size_note` são texto livre do Core, em português. A UI agora os traduz pelo
  texto exato: `app/shell/CfgSettings.js` tem `catalogFacts` (19 textos, com `QT_TR_NOOP`) e `catalogFact(text)`.
  Um texto que não está na lista é mostrado como o Core enviou.
- `app/pages/CfgIdiomas.qml` (fora do G5b, mudança mínima): importa `CfgSettings.js as CS` e usa `CS.catalogFact` em
  `sizeText` e `detailText`.
- Limite: a chave é o texto do Core. Se o catálogo mudar uma vírgula, o texto volta ao português (não quebra).
  O certo, a longo prazo, é o Core mandar um código por campo.

## 3. Mensagens da ponte (`app/bridge.py`): pendente

Pelo varredor de `scripts/test_i18n.py`, `bridge.py` tem 687 ocorrências de português em 649 textos distintos.
Nesta rodada, só as partes acima foram migradas: `model_status` (7 códigos), indicadores de percepção (4), `hubDescription`
(4 textos). O arquivo continua em `PENDING_FILES`, como deve ser.

Para migrar o resto é preciso: (a) trocar cada literal por `QCoreApplication.translate("Bridge", "...")` no ponto de uso,
ou por `QT_TRANSLATE_NOOP("Bridge", ...)` em tabela lida por `_Messages` (dicionário que traduz na leitura, como em
`uisettings.py`); (b) manter códigos do Core sem tradução; (c) escrever EN e FR de cada texto nos catálogos
`app/translations/{en,fr}/bridge.py.ts`. São cerca de 1.300 traduções. A ordem sugerida: `CODE_MESSAGES`, `OPS`/`PENDING`,
`DIAG_LABELS`, `AGENT_STATE_LABELS`, `FEATURE_LABELS`, `PERSONAL_MESSAGES`, `PERCEPTION_*`, depois as frases de f-string.

Estado do catálogo de `bridge.py`: 16 mensagens em en e fr, todas finalizadas (`Core offline`, `Catálogo ...`, `ligado`...).

### Textos em português que ainda aparecem nas telas (vistos no explorador)

- Percepção e ação: `Escuta do microfone: desligado` (vem de `bridge.py`).
- Modelos LLM: `personalizado · fake/model-1` (nome de provedor do Core/ponte).
- Voz e réveil (Frases): `em desenvolvimento`, `requer prova de conceito`, e o texto de confirmação longo.
- Conversa de teste: `Resposta roteirizada do motor de teste...` (dado do teste, não é bug).

## 4. Voz e wake: `CfgVoz.qml` ('1,00' contra '1,0')

- **Intenção.** O valor da sensibilidade tem duas casas (`1,00`, como em `docs/A10-ui-e2e-owner-path.md`: "1,00 para 1,05").
  A marca do padrão tem uma casa (`padrão 1,0`), como no teste committed em `ee0daf1` ("padrão 1,0"). Então o esperado
  é `'1,00 · padrão 1,0'`.
- **Estado.** A árvore de trabalho já produz `1,00 · padrão 1,0` (`oneDecimal(1.0)` para o padrão, `sensText` para o valor).
  O teste `AudioQml`, na checagem da linha 3427 (`wakeSensitivityValue`), passa. Não editei `CfgVoz.qml` nem o teste.
- O `AudioQml` continua falhando em outra checagem, `hojeLiveHint` ("Microfone desligado: ative em Dispositivos..."), que é
  de `InicioHoje.qml` (outro grupo).

## 5. Explorador com Core real em inglês e francês

`scripts/explore_setup.py` ganhou `--ui-language {pt-BR,en,fr}`. Ele envia a preferência `ui_language` ao Core pela própria
op (com `revision` do snapshot), e confere que o snapshot trouxe o idioma. Um ambiente limpo não tem `LANG`, então sem a
op o Core começaria em pt-BR.

| Idioma | Comando | Páginas | Avisos | Exceções | Geometria |
|---|---|---|---|---|---|
| en | `explore_setup.py --ui-language en` + `explore_ui.py` | 27 de 28 | 0 | 0 | 0 |
| fr | `explore_setup.py --ui-language fr` + `explore_ui.py` | 27 de 28 | 0 | 0 | 0 |

Capturas em `scratchpad/g5b/shots-en/` e `scratchpad/g5b/shots-fr/`. Vistas: en `06-plugins`, `10-modelos`,
`11-percepcao`, `17-cfg_idiomas`; fr `17-cfg_idiomas` (400 e 600 px), `10-modelos`, `11-percepcao`, `16-cfg_voz`.

Achados:
- Navegação, títulos, botões e os textos de catálogo (licença, qualidade) aparecem no idioma escolhido, sem corte.
- Banner do Hub em inglês e modo "info" (sem quarentena): o flag `hubQuarantined` funciona.
- Pílula de estado do modelo "No model data" / "Pas de données du modèle" e os indicadores "not read" / "non lu" saem dos códigos.
- Em 600 px, o subtítulo da página Idiomas é cortado com reticências (já era assim); a barra de abas rola na horizontal
  (já era assim). Nenhum botão cortado.
- Os textos em português listados em §3 aparecem; são pendência, não regressão.

## 6. Testes executados

| Comando | Resultado |
|---|---|
| `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_i18n.py` | 13 OK |
| `scripts/test_bridge_protocol.py ModelsContract PerceptionBridge Wp4Bridge Wp20Language` | 33 OK |
| `scripts/test_bridge_protocol.py ModelsBridge Wp4Bridge` (QML) | 44 OK |
| `scripts/test_bridge_protocol.py AudioQml` | 1 falha: `hojeLiveHint` (InicioHoje, outro grupo). A checagem de `1,00 · padrão 1,0` passa |
| `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_languages_qml.py` | 4 OK |
| `target/ui-venv/bin/python scripts/test_ui_settings.py` | 25 OK |
| `target/ui-venv/bin/python scripts/i18n_tools.py update` e `release` | catálogos sem `unfinished`: en 2678 e fr 2678 |

Não rodei a suíte completa de `test_bridge_protocol.py` (265) nem `test_ui_offscreen.py`: as classes que tocam os textos
alterados passam, e a suíte inteira fica para o fim do pacote (orçamento de testes).

## 7. Mensagens por arquivo (catálogo, en = fr)

| Arquivo | Mensagens | Sem tradução |
|---|---|---|
| `app/bridge.py` | 16 | 0 (o resto do arquivo não está no catálogo ainda) |
| `app/shell/CfgSettings.js` | 35 (19 novas do catálogo de idiomas) | 0 |
| `app/pages/ModelosLlm.qml` | 152 | 0 |
| `app/pages/Percepcao.qml` | 28 | 0 |
| `app/pages/Plugins.qml` | 46 | 0 |
| `app/pages/CfgIdiomas.qml` | 36 | 0 |

## 8. Processos

- Iniciei dois `explore_setup.py` (en e fr). Parei cada um pelo PID que registrei (`scratchpad/g5b/my-pids.txt`).
- Encontrei outros dois `explore_setup.py` em execução (PIDs 165821 `--ui-language en` e 167144 `--ui-language fr`), que não são
  meus. Não os encerrei. Quem os iniciou deve encerrá-los pelo PID.
- Não usei `pgrep -f`, `pkill` nem `kill` por padrão.

## 9. Segunda rodada: tranche 1 de `bridge.py`

Migrado nesta rodada (37 mensagens, en e fr finalizadas): `DIAG_LABELS` (20), `HUB_UPLOAD_MESSAGES` (11),
`WAKE_QUALIFICATION_LABELS` (3, com o estado real: `dev_qualified` = "qualificada em corpus sintético; microfone real não
validado"; `poc_required` = "não ativado: precisa de gravações da sua voz"), o texto do pacote de teste virtual (antes
"em desenvolvimento · virtual", agora "pacote de teste virtual · validação física pendente").
Helpers novos em `bridge.py`: `_fill` (preenche `%1...`) e `_Messages` (tabela que traduz na leitura).
Testes de texto de qualificação atualizados em `scripts/test_bridge_protocol.py` (DisplayMapping, WakePhrases).

Resultados: `test_i18n.py` 13 OK; `test_bridge_protocol.py` completo 265 rodadas, 1 falha (`AudioQml`, `hojeLiveHint`, de
`InicioHoje`, fora de G5b); `test_snapshot_contract.py` OK; `test_ui_settings.py` 25 OK.

**Pendente: cerca de 610 mensagens** (`CODE_MESSAGES`, `OPS`/`PENDING`, `PENDING_MODELS`, `AGENT_STATE_LABELS`,
`FEATURE_LABELS`, `REC_*`, `LIVE_*`, `COMMAND_CODE_MESSAGES`, `PERCEPTION_*`, `EFFECT_TEXT`, `RISK_TEXT`,
`CHAT_STATE_LABELS`, frases em f-string, e os `update(...)` com texto cru). `bridge.py` continua em `PENDING_FILES`.
Cada tranche precisa de edições em `bridge.py` e de traduções EN/FR em `app/translations/{en,fr}/bridge.py.ts`
(reescritos por inteiro por causa do tamanho).
