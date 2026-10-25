# WP-4: configurações desativadas, Hub, diagnóstico e ponte (pacote de UI)

Itens: CFG-01, CFG-02, CFG-03, CFG-04, CFG-05 (`docs/GAP_AUDIT.md`, seção 3); DIAG-02, DIAG-03, DIAG-05; HUD-03;
N-5; bridge `valid_skill_import`; rótulos "não autenticado"; importação de pacote do Hub; confirmação da troca de
frase de despertar; caminho do log de auditoria; textos da cópia de segurança (`config.json.bak`); Aparência
(tema, cor e "mostrar opções avançadas") e modo desenvolvedor.

Nada foi commitado. Nenhum arquivo de `src/` foi alterado por este pacote. Nenhum download foi feito.

## Estado por item

| Item | Estado | O que está pronto | O que falta e por quê |
|---|---|---|---|
| CFG-01 | PARCIAL | Escolha de voz ligada ao Core (`CfgAudio.qml`, `voiceSelect`): lista só as vozes instaladas do idioma de fala (`core.languageTtsItems`); troca grava com `setLanguages`. | Só existe uma voz instalada (Alba, inglês). Outras vozes dependem de CFG-03. |
| CFG-02 | PARCIAL | "Idioma da fala" em Geral (`speechLanguageSelect`) é escolha real do Core, só com idiomas instalados. | A interface continua em português: traduzir a interface inteira não foi feito (tamanho L, decisão do dono). |
| CFG-03 | NÃO FEITO | Botões seguem desativados, com o motivo que o Core informa. | Precisa de operação de instalação no Core (`src/languages.rs`, fora do pacote) e da aprovação do download pelo dono (regra do projeto). |
| CFG-04 | PARCIAL | Controle `historyRetentionSelect` em Privacidade: 7 dias, 30 dias, 90 dias, não guardar, ligado a `setHistoryRetention`. Padrão mostrado: 30 dias. | Expurgo de `skill-runs.json` não é chamado por `purge_history_now` (`src/core.rs`, fora do pacote; ver WP15). |
| CFG-05 | FEITO | Botões Salvar e Cancelar removidos do cartão de prévia. | Nenhum. A prévia já diz que não grava nada. |
| DIAG-02 | FEITO | `app/Main.qml` usa `core.developerMode`. `behavior.devMode` virou chave do Core em `uisettings.py`, então Configurações, Estado e Desenvolvedor leem a mesma fonte. | Nenhum. |
| DIAG-03 | FEITO | Linha "Resposta de reserva" em Diagnóstico › Motores, lida de `llmFallbackUsed`. | Nenhum. |
| DIAG-05 | FEITO | Estado › "Desempenho e recursos": `coreLatency`, `diagResources` (Core, auxiliares e janela). Motores › "Latência da resposta em voz": `speechLatency`. | DIAG-01 (`packHash`) não é deste pacote; ver "Restos". |
| HUD-03 | NÃO FEITO | Nada. Ctrl+M segue com o comportamento antigo. | O Core não tem operação para o cliente iniciar captura real. `VirtualWake` só existe com `--virtual-input` (teste). Precisa de operação nova no Core. |
| N-5 | PARCIAL | Conversa e Agente continuam na tela durante a sessão de voz. Só o campo de envio fica bloqueado, com o aviso "Indisponível: uma sessão de voz está em andamento." | O Core recusa `capability_invoke` durante a sessão (`busy`, `src/core.rs`). Enviar durante a voz exige mudança no Core. |
| Importação do Hub | FEITO (UI e ponte) | Botão "Importar pacote…" (linha e gaveta de Plugins) para plugin com permissões aprovadas e sem pacote guardado. Seletor de arquivo (`hubImportDialog`). A ponte envia `hub_begin`, `hub_chunk` (1 KiB) e `hub_finish`, uma requisição por vez, e nunca instala. | O botão só aparece com entrada elegível no catálogo; o Core de teste não tinha nenhuma, então o seletor não foi aberto na tela. A cobertura é por teste (ver abaixo). |
| Confirmação da frase de despertar | FEITO (código) | Trocar a frase (ligar ou desligar) abre "Salvar a frase de despertar?" (ou "Desativar…") com Cancelar como padrão. O aviso diz que vale no próximo início do Core. | Não foi aberto na tela: o explorador não clica em interruptores. Carrega sem erro na página Voz e Wake. |
| Caminho do log de auditoria | FEITO | `Bridge.auditLogPath` (raiz do Core + `audit.log`); Permissões › Auditoria › Detalhes técnicos usa essa propriedade. | Nenhum. |
| Textos da cópia de segurança | FEITO | Falha de `preferences_restore_defaults` com `preferences_storage_error` mostra "Padrões não restaurados: não foi possível gravar a cópia config.json.bak nem trocar a configuração; os valores atuais continuam". | Nenhum. |
| `valid_skill_import` | FEITO | Aceita `unverified` `true` e `false` (qualquer booleano). Teste de contrato atualizado. | Nenhum. |
| Rótulos "não autenticado" | FEITO | Lidos de `hubPublisherVerified` (snapshot `hub.publisher_verified`) em `PermRows.js`, `BPluginDetail.qml`, `DPermDialogs.qml`, `Plugins.qml`. Lidos de `skillImportPreview.unverified` em `Skills.qml`. | Nenhum. Com chave não fixada o Core diz `false`, então o texto continua "não autenticado". |
| Aparência e opções avançadas | FEITO (já era app-side) | Tema, cor de destaque e "Mostrar opções avançadas" ficam no arquivo do perfil (`$XDG_CONFIG_HOME/gideon-app/<core>/<perfil>.json`, 0600). Cobertos por `test_persistence_is_atomic_private_and_reloads`. | Não são gravados pelo Core. Isso segue `docs/ui-spec/40` §10 (são preferências da janela). |

## Mudanças por arquivo

- `app/bridge.py`
  - `valid_skill_import`: `unverified` aceita booleano.
  - Validação de `hub`: `publisher_verified` aceita `true` quando o catálogo tem plugins; `hubPublisherVerified`, `hubDescription` leem a flag.
  - `chatAvailable` deixou de depender de preferências (N-5); novos `chatInputAvailable` e `chatBlockedText`.
  - `auditLogPath`.
  - Upload do Hub: `importHubPayload(plugin_id, location)`, `hubImportPickable`, `_hub_upload_pump` (chamado após cada resposta do Core), `_hub_upload_send`, `_hub_upload_done`, `_hub_upload_drop`; constantes `HUB_CHUNK_BYTES` e `HUB_UPLOAD_MESSAGES`. `abortHubImport` também cancela o upload em curso.
  - `preferences_restore_defaults` com `preferences_storage_error`: `RESTORE_BACKUP_TEXT`.
- `app/uisettings.py`: `behavior.devMode` é chave do Core (`developerMode` / `setDeveloperMode`).
- `app/Main.qml`: `diag_dev: core.developerMode`; `cfg_idiomas` entra em `availability` (a página Idiomas não era alcançável; antes ela não aparecia na barra de sub-abas); `cancellable` do topo não aparece na aba Hoje, onde o Cancelar do HUD já existe.
- `app/pages/CfgAudio.qml`, `CfgGeral.qml`, `CfgPrivacidade.qml`: controles reais (CFG-01, CFG-02, CFG-04).
- `app/components/EPreviewCard.qml`: sem Salvar e Cancelar (CFG-05).
- `app/pages/Conversa.qml`, `Agente.qml`: entrada usa `chatInputAvailable`; aviso de sessão de voz.
- `app/pages/Plugins.qml`: `FileDialog` (`QtQuick.Dialogs`), `askImport`, rótulo de publisher pela flag, texto de confirmação conforme a flag.
- `app/components/BExt.js`: ação `import` quando o pacote ainda não está guardado (antes apenas dizia "importe pela linha de comando").
- `app/components/BPluginRow.qml`, `BPluginDetail.qml`: botão e sinal `importRequested`; `BPluginDetail` e `BPluginRow` com rótulos da flag.
- `app/components/DPermDialogs.qml`, `app/shell/PermRows.js`, `app/pages/PermVisao.qml`: rótulos da flag.
- `app/pages/Skills.qml`: publicador da prévia de importação com a flag `unverified`.
- `app/pages/CfgVoz.qml`: `wakeChangeConfirm` (propriedade `pickedChange`).
- `app/pages/PermAuditoria.qml`: caminho do log vem de `core.auditLogPath`.
- `app/pages/DiagEstado.qml`: seção "Desempenho e recursos" (`cpuText`, `mbText`).
- `app/pages/DiagMotores.qml`: "Latência da resposta em voz" e "Motor LLM › Resposta de reserva".
- Testes: `scripts/test_bridge_protocol.py` (classe `Wp4Bridge`, 7 testes; caso "import not unverified" virou
  "import unverified not bool"; caso "publisher verified" virou "publisher verified without plugins"),
  `scripts/test_ui_settings.py` (`CORE_EXPECTED` inclui `behavior.devMode`),
  `scripts/test_snapshot_contract.py` (novo `test_hub_payload_import_through_the_bridge_reaches_the_real_core`).
- `docs/GAP_AUDIT.md`: linhas CFG-01 a CFG-05, DIAG-02, DIAG-03, DIAG-05, HUD-03.

## Comandos executados e resultados

Todos na raiz `/home/lucas/Documentos/Gideon/base`.

1. `python3 -m py_compile app/bridge.py app/uisettings.py`: OK.
2. `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_bridge_protocol.py Wp4Bridge -v`: 7 de 7 OK
   (depois de corrigir `hubDescription` exigir `online`).
3. `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_bridge_protocol.py`: 258 testes OK (35,7 s).
4. `target/ui-venv/bin/python scripts/test_ui_settings.py`: 25 de 25 OK.
5. `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_languages_qml.py`: 4 de 4 OK.
6. `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_snapshot_contract.py`: 18 de 18 OK (115,6 s), com o
   binário `target/release/gideon-base` existente (não recompilado).
7. `... scripts/test_snapshot_contract.py SnapshotContract.test_hub_payload_import_through_the_bridge_reaches_the_real_core`:
   1 de 1 OK (2,98 s). Prova o upload real: a ponte enviou hub_begin/hub_chunk/hub_finish ao Core, a entrada ficou
   `payload_staged` e `not_installed`; uma segunda importação foi recusada na ponte com `entry`.
8. `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_hud_qml.py`: 13 testes OK (29,1 s), inclusive o
   teste ao vivo com o Core real. Afetado pela mudança de `cancellable` em `Main.qml`.
9. Carga de QML sem Core, com `/tmp/.../scratchpad/probe_qml.py` (roda `main.create` e troca de página): páginas
   cfg_privacidade, cfg_audio, cfg_geral, cfg_voz, cfg_idiomas, cfg_aparencia, diag_estado, diag_motores, plugins,
   skills, perm_visao, perm_auditoria, conversa, agente, hoje. Sem erro no stderr.
10. Core real populado: `/usr/bin/python3 -I -B scripts/explore_setup.py` (subiu, ROOT em
    `/tmp/gideon-explore-hvoshyov/core`). Depois `scripts/explore_ui.py --root ... --pages ...` com 13 páginas
    (`Conversa, Agente, Plugins, Skills, Visão geral, Auditoria, Voz e Wake, Áudio, Aparência, Privacidade, Geral,
    Estado, Motores`): 0 mensagens de aviso, 0 exceções, 0 problemas de geometria. Capturas em
    `/tmp/claude-1000/-home-lucas-Documentos-Gideon/5fd6f0b3-714b-4e76-9110-b1db87d89aef/scratchpad/shots1/`.
    Idiomas não estava alcançável nessa rodada (corrigido depois, em `Main.qml`).
11. Modo desenvolvedor ligado no Core de teste com `/usr/bin/python3 -I -B <scratchpad>/set_devmode.py /tmp/gideon-explore-hvoshyov/core on`
    (cliente de socket que envia `developer_mode_preference`; resposta `code: ok`). Depois `explore_ui.py --pages "Idiomas,Desenvolvedor,Estado,Permissões,Visão geral"`:
    4 páginas visitadas, 0 avisos, 0 exceções. Capturas em `.../scratchpad/shots2/` (Idiomas, Desenvolvedor, Estado).
12. Core de teste encerrado com SIGTERM; nenhum processo `gideon-base`, `fake_llm_server` ou `github_server` ficou ativo.

Capturas conferidas: Privacidade (cabeçalho, consentimento e início de Retenção), Áudio (Escolha de voz com "alba"),
Geral (topo), Estado (Desempenho e recursos com dados reais), Motores (latência de voz e reserva), Plugins, Aparência
(prévia sem botões), Idiomas, Desenvolvedor.

## Restos e motivos

- HUD-03: exige operação de captura no Core (`src/protocol.rs`, `src/core.rs`), fora do pacote.
- CFG-03: exige operação de instalação no Core e aprovação do download pelo dono.
- CFG-02: tradução da interface inteira. Não foi iniciada.
- CFG-04: expurgo de `skill-runs.json` depende de `src/core.rs` (`purge_history_now`), fora do pacote.
- N-5 completo: o Core recusa chat e agente durante a sessão de voz (`busy`). A UI agora mostra a conversa, mas enviar
  durante a voz exige mudança no Core.
- DIAG-01 (`packHash`): não é deste pacote. O campo `base_pack.pack_sha256` está no escopo de WP15.
- Importação do Hub na tela: o seletor e o botão não foram abertos ao vivo (o Core de teste não tem entrada
  elegível). A cadeia completa foi testada contra o Core real pela ponte (item 7).
- Confirmação da frase de despertar: carrega sem erro, mas o diálogo não foi aberto ao vivo (o explorador não
  clica em interruptores).
- Orbe da barra superior (`app/components/Orb.qml`, outro pacote): não foi revisto no estado "pensando". Esta
  revisão depende de uma sessão de voz ou de chat em andamento.
- Alteração pedida pelo coordenador: a mensagem "TypeError: Property 'retentionIndex' ... is not a function" em
  `CfgPrivacidade.qml` não apareceu nesta árvore (carga sem Core e com Core, 0 avisos). O texto da função está
  declarado na raiz da página. Se reaparecer, ver a linha da função e a ordem das propriedades da página.
- Alteração pedida pelo coordenador: botão Cancelar duplicado em Hoje durante a sessão. Resolvido em `Main.qml`
  (`cancellable` do topo fica falso na aba Hoje). `app/shell/TopBar.qml` não foi editado.
