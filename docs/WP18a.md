# WP-18a: percepção real dentro do sandbox do Core

Estado: **FEITO com pendências declaradas** (§7). Os nove leituras somente-leitura, a captura de tela, o quadro da
câmera (com opt-in), a restauração de tela e o atalho passam pelo Core real, com a sessão real do PC. Nenhum dado
sintético foi usado.

## 1. Causa isolada (com evidência)

Reproduzi o argv que `src/plugins.rs` monta para cada plugin de percepção (`sandbox_command_profiled` com o perfil de
`perception_profile_in`) em `bwrap`, com `scratchpad/probe.sh`, e capturei stderr e código de saída.

Dois ambientes, medidos antes das correções desta WP (mesmo argv, código de antes):

| Ambiente do Core | screen status | computer status | audio state | mic state | camera state | camera gestures | display status | shortcut status | shortcut events |
|---|---|---|---|---|---|---|---|---|---|
| Harness de teste (`XDG_RUNTIME_DIR` privado, sem barramento) | backend_unavailable | rc 134 (AT-SPI aborta) | plugin_error | plugin_error | ok | ok | plugin_error | backend_unavailable | ok |
| Sessão real do PC (`/run/user/1000`, `DBUS_SESSION_BUS_ADDRESS`, `WAYLAND_DISPLAY`) | ok | ok | ok | ok | ok | ok | plugin_error (rc 134) | ok | ok |

O ambiente privado reproduz exatamente o padrão da WP-17 (3 de 9 válidos). Causas:

1. **Ambiente do harness.** `scripts/test_snapshot_contract.py` roda o Core com `XDG_RUNTIME_DIR` privado e sem
   `DBUS_SESSION_BUS_ADDRESS`. Sem o barramento, o portal e o KDE respondem `backend_unavailable`; sem o socket do
   PipeWire, `wpctl` falha com erro genérico. Não é um bug do sandbox: é o isolamento de teste.
2. **AT-SPI derruba o worker.** Sem barramento de acessibilidade, `Atspi.init()` aborta o processo (stderr:
   `Couldn't connect to accessibility bus`, rc 134). O Core via isso como `plugin_error`. Corrigido: o worker pergunta
   `org.a11y.Bus.GetAddress` antes de inicializar e responde `backend_unavailable`.
3. **KScreen precisa do socket Wayland.** Com a sessão real, `kscreen-doctor -j` aborta (rc 134) porque não alcança o
   KWin sem `WAYLAND_DISPLAY`. Medido: com o socket `wayland-1` ligado e `WAYLAND_DISPLAY` definido, sai JSON. Corrigido:
   o perfil `display_manipulate` liga somente esse socket e define a variável; sem ela o worker responde
   `backend_unavailable`.
4. **Câmera invisível no sysfs.** `/sys/class/video4linux/video0` é um link para `../../devices/...`, fora do sandbox.
   O worker lia `index` e não achava o nó de captura: `present: false` sem erro. Medido. Corrigido: o perfil liga,
   somente leitura, o diretório sysfs resolvido de cada `/dev/videoN`.
5. **Captura da câmera falhava (plugin_error).** ffmpeg não abre o encoder com o limite de espaço de endereço do
   sandbox (512 MiB): rc 245 em `ff_frame_thread_encoder_init`. Com 1 GiB, a captura passa (medido, 160x120). O
   limite de 1 GiB vale só para o perfil da câmera; os demais continuam em 512 MiB (`CAMERA_ADDRESS_SPACE`).
6. **Bind de atalho recusado por contrato.** A ponte envia `shortcut_global.bind` com `{id, trigger}`; o worker exigia
   `description` e respondia `invalid_input` em todo bind do atalho de pressionar para falar. Corrigido: a descrição
   tem valor padrão.
7. **Status do AT-SPI fora do contrato.** A saída do worker trazia `input_session`, que a regra de disponibilidade da
   ponte recusa. Corrigido: só `backend`, `available`, `reason`.

Com isso o worker passa a responder, sem exceção, nos dois ambientes; o que não há no ambiente é reportado com código.

## 2. Mudanças

- `src/plugins.rs`
  - `SessionEnv`, `session_bus_path` (usa `DBUS_SESSION_BUS_ADDRESS` com `unix:path=`; senão `$XDG_RUNTIME_DIR/bus`),
    `wayland_socket_name`, `video_sysfs_dirs`, `perception_session` (ao vivo), `perception_profile_in(plugin_id, &SessionEnv)`.
  - `Profile.address_space` e `CAMERA_ADDRESS_SPACE` (1 GiB, só câmera); `sandbox_command_profiled` usa o limite do perfil.
  - `Session::restore_display`: antes de parar um plugin `display_manipulate` (parada do plugin, desativação ou saída do
    Core), o Core envia `display_manipulate.restore` e espera a resposta por até 3 s; depois segue o `shutdown` como antes.
  - Testes: `each_perception_plugin_gets_only_its_own_sockets` (novo formato, Wayland, câmera, limite), `session_bus_comes_from...`,
    `wayland_name_must_be_a_plain_socket_name`, `video_nodes_map_to_their_sysfs_directories_only`.
- `scripts/perception_worker.py`: verificação do barramento de acessibilidade antes do AT-SPI; `WAYLAND_DISPLAY` obrigatório
  para o KScreen; `wpctl`/`pw-dump`/`pw-record` só com o socket do PipeWire (senão `backend_unavailable`); status do
  AT-SPI só com as chaves do contrato; descrição padrão do atalho.
- `scripts/perception_live.py`: `--core` (as 9 leituras, captura, câmera com opt-in, escala/brilho com restauração,
  atalho com disparo e evento, restauração na saída do Core), `--core-serve SEGUNDOS` (Core ativo para a checagem de
  interface). Evidência: `docs/evidence/perception-core-live.json`.
- `tests/fixtures/hub-perception.json`: regenerado por `scripts/make_c4_catalog.py --real` (payload mudou).
  Novo sha256 do catálogo: `b0478b3e8f7c85efbacc913e8afaac39fc4197f751573dc7f51416b98ca967ef`. `hub-c4.json`
  regenerado sem flag: sem diferença.
- `scripts/build_package.py`: copia `catalog/hub-perception.json` e `catalog/hub-perception.sha256` para o pacote.
- `scripts/test_perception_worker.py`: removida a chave `input_session` do teste de formato de status.
- `app/*`, `src/broker.rs`, `src/llmcfg.rs`, `src/secrets.rs`, `scripts/net_broker.py`, `app/bridge.py` e demais
  alterações em `git status` não são desta WP. Não foram tocados.

## 3. Leituras reais pelo Core (live, sessão do PC)

Comando: `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/perception_live.py --confirm --core`.
Core: `target/release/gideon-base` (release, compilado com estas mudanças), catálogo `tests/fixtures/hub-perception.json`,
sete plugins aprovados, instalados e em execução pelo Hub. Cada saída passou pela regra de saída de `app/bridge.py`
(`PERCEPTION_OUTPUTS`) e pela regra de entrada (`perception_input_problem`).

Resultado final: **28 passam, 0 falham, 1 informativo** (`docs/evidence/perception-core-live.json`).

- As 9 leituras somente-leitura: 9 de 9 válidas.
- Captura de tela (`screen_observe.capture`): 1920x1080, sha256 registrado, nenhum PNG deixado em `~/Imagens`.
- Câmera: recusada sem opt-in (`opt_in_required`); com opt-in, quadro 160x120, luminância média registrada; opt-in
  devolvido a desligado.
- Escala e brilho: 100 → 125 (verificado), brilho 95 → 90 (verificado); `display_manipulate.restore` restaurou 2 alterações
  (verificado). Estado final igual ao inicial: DP-1, escala 100, brilho 95.
- Atalho: `shortcut_global.bind` com `{id: wp18a_probe, trigger: CTRL+ALT+G}` registrado pelo portal; disparo por
  `invokeShortcut` do KGlobalAccel; `shortcut_global.events` devolveu o evento `wp18a_probe`.
- Restauração na saída do Core: escala 125, parada do Core (SIGTERM, sem `restore` explícito), tela de volta a 100 e 95.

## 4. Interface

`scripts/explore_ui.py` contra o Core real (`--core-serve 900`), páginas "Percepção e ação" e "Dispositivos":
2 páginas visitadas, 0 mensagens de aviso, 0 exceções, 0 problemas de geometria.

- Capturas (lidas): `scratchpad/ui2/11-percepcao.png` e `scratchpad/ui2/19-cfg_dispositivos-after-clicks.png`
  (caminhos completos: `/tmp/claude-1000/-home-lucas-Documentos-Gideon/5fd6f0b3-714b-4e76-9110-b1db87d89aef/scratchpad/ui2/`).
- Percepção mostra "Microfone: não lido" e "Câmera: não lido": o explorador não aperta o botão de leitura da subaba
  Plugins, então a leitura real dos cartões **não** aparece nessa captura. Declarado; não foi capturado.
- Dispositivos: a seção Câmera e tela fica abaixo da dobra e não foi capturada.
- Os textos "sem leitura ainda", "Indisponível: plugin não está em execução" e "Ainda não verificado" são estados reais,
  não rótulos de simulado; ficaram.

## 5. Comandos e resultados

| Comando | Resultado |
|---|---|
| `scratchpad/probe.sh` / replay com `XDG_RUNTIME_DIR` privado e com a sessão real | padrão da tabela da §1 |
| `cargo test --offline --lib perception` | 6 passed |
| `cargo build --release --offline` | OK |
| `python3 -I scripts/make_c4_catalog.py --real` | catálogo `b0478b3e…`; `hub-c4` sem diferença |
| `perception_live.py --confirm --core` (duas vezes, a final após a última mudança) | 28 pass, 0 fail, 1 info |
| `perception_live.py --core-serve 900` + `explore_ui.py --pages "Percepção e ação,Dispositivos"` | 2 páginas, 0 avisos, 0 exceções |
| `cargo fmt --check` | rc 0 |
| `cargo clippy --offline --all-targets -- -D warnings` | rc 0 |
| `cargo test --offline --no-fail-fast` | 587 passed, 4 failed (ver abaixo) |
| `python3 -I -B scripts/test_perception_worker.py` | Ran 24, OK |
| `python3 -I -B scripts/test_c4_fixtures_b.py` | Ran 70, OK |
| `test_snapshot_contract.py SnapshotContract.test_c4_plugin_outputs_validate_against_real_core` | OK (no harness, com ambiente privado: 4 válidas, 5 códigos documentados) |
| `py_compile` de `build_package.py`, `perception_live.py`, `perception_worker.py`, `make_c4_catalog.py` | OK |

Falhas do `cargo test` (4): `tests/llm.rs` (`broker_script_refuses_bad_requests_without_touching_the_network`,
`vault_is_write_only_private_and_strictly_validated`) e `tests/llm2.rs` (`keyless_broker_requests_are_loopback_literals_only`,
`local_and_ollama_stream_without_key_consent_or_authorization_header`). São do broker e do cofre, áreas da WP-18b.
Todas as suítes de plugins, sandbox, hub, C4, skills, storage e agent passam.

Não executados: build completo do pacote (`build_package.py`, pesado; só o trecho novo foi compilado) e
`test_bridge_protocol.py` (a ponte não mudou nesta WP).

## 6. Restauração e resíduos

- Tela: DP-1 em escala 100 e brilho 95 ao fim de cada execução (conferido com `kscreen-doctor` no host).
- Volumes, microfone, rota de áudio: não foram alterados.
- Câmera: opt-in em desligado; nenhum quadro guardado.
- Capturas de tela: apagadas; nenhum arquivo em `~/Imagens`.
- Diretórios temporários do Core: removidos pelo próprio teste.
- Atalho `wp18a_probe`: o KDE ainda lista o nome em `shortcutNames` do componente `com_anthropic_Claude`, embora o
  componente não exista para `getComponent`. Não tentei `cleanUp` porque esse componente é do Claude desktop também.
  Ação do dono: confirmar em Configurações do sistema › Atalhos e remover `wp18a_probe` se aparecer. Os nomes
  `ptt_toggle` e `026A…-Ctrl+Alt+Space` também estavam listados quando verifiquei; não sei a origem deles e não os tocou.

## 7. Pendências e decisões (fora da lista de arquivos desta WP)

1. **Hub do pacote (WP12p 6.4).** `build_package.py` agora põe o catálogo no pacote, mas o lançador
   `scripts/package_tools/gideon-core` não passa `--hub-catalog`. Falta uma linha:
   `--hub-catalog <HERE>/catalog/hub-perception.json <conteúdo de catalog/hub-perception.sha256>`. Sem ela o Hub do pacote
   continua sem catálogo. Arquivo fora desta lista: reportado.
2. **Harness do contrato.** `scripts/test_snapshot_contract.py` ainda usa ambiente privado; por isso passa com 5 códigos
   e não com as 9 leituras. Para as 9 leituras reais no harness, o teste deve passar o ambiente da sessão (como
   `perception_live.py --core`). Arquivo fora desta lista: reportado.
3. **`docs/GAP_AUDIT.md`.** Não editado (fora da lista). Proposta: PERC-01 a PERC-06 e DISP-01/02 para FEITO, com a
   evidência de `docs/evidence/perception-core-live.json`; PERC-06 (`describe`) fica fora.
4. **`app/bridge.py` (WP-18b).** Nenhuma mudança exigida pela WP-18a. O bind `{id, trigger}` agora é aceito pelo worker
   e o status do AT-SPI bate com a regra. Não regredir.
5. **`describe(id)`** de modelos e LLM: não é desta WP.
6. **Restauração em falha.** A restauração roda ao parar ou sair do Core, com o worker vivo. Se o worker morrer
   (crash ou SIGKILL) antes disso, nada a desfaz: o Core não tem como pedir `restore` a um processo morto. Não coberto;
   a alteração de tela fica até o próximo ajuste manual.
7. **Limite de 1 GiB só para a câmera.** Decisão de segurança a registrar: o limite menor continua nos demais plugins.
8. **Checagem dos cartões de leitura na interface.** Não capturada (§4).

## 8. Desvios de processo (declarados)

- Digitei um `sed -i` contra `/dev/null` por engano (ainda na fase de diagnóstico). Não alterou nenhum arquivo, mas
  viola as regras do pacote. Não repeti.
- Usei `Write` para scripts de diagnóstico em `scratchpad/` (não são heredocs) e `kill` por PID (SIGTERM ao Core de teste).
- Não rodei `cargo fmt` para reescrever; só `cargo fmt --check`.
- `scratchpad/` perdeu alguns scripts de diagnóstico no meio da sessão; os resultados que citei foram medidos antes.
