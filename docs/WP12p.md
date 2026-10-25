# WP-12p — percepção e dispositivos reais (backends no PC do dono)

Escopo: substituir os backends só sintéticos dos plugins C4 (`screen_observe`, `computer_control`,
`audio_advanced`, `mic_advanced`, `camera_gesture`, `display_manipulate`) por backends reais, e acrescentar
`shortcut_global` (atalho global para pressionar-para-falar e alternar). Itens da auditoria: DISP-01, DISP-02,
PERC-01 a PERC-06 (ver `docs/GAP_AUDIT.md`). Autorização do dono: testes reais no PC com restauração.

Não tocado (regra do pacote): `src/core.rs`, `src/protocol.rs`, `src/transport.rs`, `app/bridge.py`, `src/world.rs`,
`src/plugins.rs`, `app/pages/*` de Percepção e Dispositivos. A integração que falta está na seção 6.

## 1. Arquivos

| Arquivo | Papel |
|---|---|
| `scripts/perception_worker.py` | Payload único dos sete plugins (protocolo C0 JSON-lines v1, sem `host_call`). Responde só às capabilities do `plugin_id` recebido em `hello`. |
| `scripts/make_c4_catalog.py` | Gerador. `--real` grava `tests/fixtures/hub-perception.json`; sem flag (ou `--synthetic`) grava `hub-c4.json` como antes. |
| `tests/fixtures/hub-perception.json` | Catálogo real, 7 plugins, mesmo payload. |
| `scripts/test_perception_worker.py` | 24 testes offline (sem efeito no desktop). |
| `scripts/perception_live.py` | Testes ao vivo no PC (`--confirm`). Gera `docs/evidence/perception-live.json`. |
| `scripts/perception_testwindow.py` | Janela Qt de teste que o próprio teste abre e fecha. |
| `docs/evidence/perception-live.json` | Evidência da última execução ao vivo. |

Catálogo real: sha256 do arquivo `757f3784e522667ca39b393b67fd85c1c87be9e5f7dd3102437fa1ad63e5738e`;
sha256 do payload `scripts/perception_worker.py` é gravado como `worker_sha256` em `docs/evidence/perception-live.json`.
Catálogo sintético (`hub-c4.json`) regenerado por `make_c4_catalog.py` sem flag: byte a byte igual ao anterior
(`git diff` vazio).

## 2. Ambiente medido neste PC (2026-10-25)

- Sessão: `XDG_SESSION_TYPE=wayland`, `XDG_CURRENT_DESKTOP=KDE`, KWin Wayland (`kwin_wayland`), Plasma 6.
- PipeWire 1.6.10 com WirePlumber; `wpctl`, `pw-dump`, `pw-cli`, `pw-cat`, `pw-record` disponíveis.
- xdg-desktop-portal com `xdg-desktop-portal-kde` ativo. Interfaces presentes: Screenshot, ScreenCast,
  RemoteDesktop, GlobalShortcuts, InputCapture, Camera.
- AT-SPI ativo (`/run/user/1000/at-spi/bus_0`); `libei` instalado (`libei.so.1.6.0`).
- Webcam `Full HD webcam` (`uvcvideo`) em `/dev/video0` (captura) e `/dev/video1` (metadados).
- Monitor `DP-1` 1920x1080, escala 1, brilho 95 % (`kscreen-doctor` com controle de brilho).
- Ausentes: `ydotool`, `dotool`, `wlr-randr`, `grim`. `/dev/uinput` existe e NÃO foi usado (seção 5).
- Usuário nos grupos `input`, `video`, `audio`.

## 3. Backends e resultado ao vivo

Todos os resultados abaixo vieram do worker real, pelo protocolo C0, no PC. "Verificado" = o worker
releu o efeito pelo próprio sistema.

| Plugin / capability | Backend real | Resultado no PC |
|---|---|---|
| `screen_observe.capture` | portal `Screenshot` (interactive=false); PNG hasheado e apagado | 1920x1080, sha256 registrado; nenhum arquivo deixado em `~/Imagens`. Imagem inspecionada visualmente na fase de probe (conteúdo privado, não guardado). |
| `screen_observe.status` | existência da interface do portal | `available: true` |
| `computer_control.tree` | AT-SPI, janela com foco | janela "Gideon perception test window", 3 elementos (rótulo, campo de texto) |
| `computer_control.act` `type` | RemoteDesktop (teclado) + leitura do texto focado por `Atspi.Text` | `gid` injetado em 3 teclas, **verified: true** |
| `computer_control.act` `key` | RemoteDesktop (`BackSpace`) | injetado (1), verified false por desenho (tecla não tem leitura de volta) |
| `computer_control.act` com época velha | — | `stale_screen` (sem efeito) |
| `audio_advanced.state` | `pw-dump` (metadados default, nós) + `wpctl get-volume` | saída padrão 55, sinks, streams |
| `audio_advanced.act` `app_volume` | `wpctl set-volume` só em streams (`Stream/Output/Audio`) | stream de laboratório 100 → 40 → 100 (**verified**); sink padrão recusada com `unknown_app` |
| `audio_advanced.act` `route` | `wpctl set-default` | para um sink de laboratório e de volta à saída original (**verified**); sink inexistente: `unknown_route` |
| `audio_advanced` `eq` / `denoise` | — | `invalid_input` (não existe no contrato desta capability; não há backend) |
| `mic_advanced.state` / `configure` | `wpctl` na fonte padrão, ganho 0–150 % | 100 → 80 → 100 (**verified**) |
| `mic_advanced.record` start/stop | `pw-record` para arquivo temporário, medidor RMS/pico, arquivo apagado | 2,5 s medidos (RMS 11, pico ~40 em 100); nenhum áudio guardado; limite 10 s automático |
| `mic_advanced.monitor` | recusado por desenho | `supported: false` (realimentação nos alto-falantes) |
| `camera_gesture.optin` / `state` | opt-in em memória, padrão desligado | `capture` sem opt-in: `opt_in_required` |
| `camera_gesture.capture` | ffmpeg v4l2, um quadro 160x120 cinza, hash e luminância média | 160x120, luminância média 23–30 (sala escura); nenhum quadro guardado; opt-in restaurado a desligado |
| `camera_gesture.gestures` | — | `supported: false`, `no_gesture_model_installed` (não há modelo de gesto) |
| `display_manipulate.status` | `kscreen-doctor -j` | DP-1, escala 100, brilho 95 |
| `display_manipulate.act` escala | `kscreen-doctor output.DP-1.scale.1.25` | 100 → 125, verificado; depois restaurado a 100 |
| `display_manipulate.act` brilho | `kscreen-doctor output.DP-1.brightness.90` | 95 → 90, verificado; depois restaurado a 95 |
| `display_manipulate.restore` | pilha de desfazer (também no encerramento do worker) | restaurou 2 alterações, verificado |
| `shortcut_global.bind` (portal) | `org.freedesktop.portal.GlobalShortcuts` (`BindShortcuts`) | `CTRL+ALT+G` registrado, `backend: portal` |
| `shortcut_global.events` | sinal `Activated` do portal | disparo por `invokeShortcut` do KDE chegou ao worker (`ptt_toggle`) |
| `shortcut_global.bind` (fallback) | KGlobalAccel direto (`doRegister`, `setShortcut`, sinal `globalShortcutPressed`) | `CTRL+ALT+H` registrado, disparado, evento recebido, desregistrado; nada sobrou |

### Execução ao vivo (comando exato)

```
python3 -I scripts/perception_live.py --confirm
```

Resultado da execução final (com a evidência gravada): **8 pass, 0 fail, 0 blocked**.
Cada item: `screen_capture`, `camera_frame`, `mic_gain_and_meter`, `display_scale_brightness`,
`audio_stream_and_route`, `shortcut_trigger`, `shortcut_kglobalaccel_fallback`, `computer_tree_and_type` (todos pass).

Restauração conferida depois da execução: escala 1, brilho 0,95, volume da saída padrão 0,65, volume da
fonte 1,00, saída padrão inalterada (id 55), nenhum nó de laboratório, nenhum processo do teste, nenhum
arquivo de captura em `~/Imagens`, nenhum diretório temporário.

### Testes offline (comando exato)

```
python3 -I scripts/test_perception_worker.py    -> Ran 24 tests … OK
python3 -I scripts/test_c4_fixtures_b.py        -> Ran 70 tests … OK   (gate C4 afetado; usa o gerador sem flag)
python3 -m py_compile scripts/perception_worker.py scripts/perception_live.py scripts/perception_testwindow.py \
        scripts/test_perception_worker.py scripts/make_c4_catalog.py   -> OK
python3 scripts/make_c4_catalog.py --real                -> catalog sha256 757f3784…
```

## 4. O que a sessão permite e o que não permite (honesto)

1. **Teclado pelo portal RemoteDesktop depende de consentimento do KDE.** Nas primeiras tentativas o
   `RemoteDesktop.Start` ficou sem resposta (tempo limite de 60 s), nenhum diálogo de consentimento apareceu
   nas capturas de tela, e o log do `xdg-desktop-portal-kde` mostrou `MegaAuth: Failed to lookup permissions:
   "No entry for remote-desktop"`. Nas execuções finais o portal respondeu sem clique do dono, e a digitação foi
   verificada. A causa da mudança não foi identificada. Para o produto: o consentimento vale para a identidade do
   processo; hoje o worker roda sob a identidade `com.anthropic.Claude` (o portal a deriva do cgroup do processo).
   Um app próprio com id de aplicativo (desktop file) dá consentimento e atalhos próprios.
2. **Atalhos do portal aparecem no componente do Claude.** No KDE, o atalho `ptt_toggle` do portal foi
   registrado sob `/component/com_anthropic_Claude`. Depois de fechar a sessão, `allActionsForComponent` ficou
   vazio, mas o nome `ptt_toggle` ainda aparece em `shortcutNames` desse componente. Conferir em Configurações
   do sistema › Atalhos antes de dar por limpo.
3. **Atalho direto no KGlobalAccel (fallback) tem armadilha de ciclo de vida.** A conexão D-Bus precisa ficar
   referenciada pelo processo (uma conexão só em variável local deixou de receber sinais). Assinatura com
   caminho de objeto fixado ou nome de remetente fixado também não entregou o sinal neste KDE; o filtro foi
   feito no callback (`path == /component/gideon_perception`).
4. **Captura de tela** usa o portal `Screenshot` (um quadro). O portal grava o PNG em `~/Imagens`; o worker lê e
   apaga. `ScreenCast` + PipeWire (fluxo contínuo) NÃO foi implementado: não há necessidade do plugin hoje.
   Árvore de regiões da captura vem vazia (`regions: []`); a árvore AT-SPI é a fonte estrutural.
5. **Clique por coordenada não existe** (regra da C4: ações tipadas por id de elemento). Só teclado e texto.
6. **Sem backends para EQ, redução de ruído, monitoração do microfone e gestos da câmera** (recusados
   honestamente, ver tabela). Monitoração do microfone seria realimentação nos alto-falantes; gestos precisam de
   um modelo instalado, decisão do dono.
7. **Brilho** só pelo `kscreen-doctor` (DDC/CI onde o monitor aceita). Não há backlight neste PC.
8. **Consumo de identidade do PipeWire:** a seleção do stream de laboratório usa o nome `pw-play`/`pw-cat` e a
   diferença de ids (não o PID). Na primeira tentativa o teste pegou um stream `pw-play` de outro processo (id
   112) e mudou o volume dele de 100 para 40 e de volta a 100; restaurado exatamente. Nas execuções finais o
   stream é o do próprio teste.
9. **Objetos de outros agentes encontrados e NÃO tocados:** um sink `GideonVerifySink` (id 116) e um
   `pw-record --target gideon_verify_mic`. Na primeira tentativa de rota, o padrão foi trocado para o sink 116 e
   voltou para 55. O sink 116 sumiu depois; os testes finais criam e removem o próprio sink
   `gideon-perception-lab`.
10. **Privacidade:** capturas de tela e quadros da câmera foram inspecionados visualmente durante a fase de
    probe (o conteúdo da tela inclui conversas de outros aplicativos); nenhum foi guardado. A evidência
    registra só dimensões, hash e luminância média.

## 5. Decisão explícita: sem fallback por `/dev/uinput`

`/dev/uinput` é gravável pelo grupo `input`, mas usá-lo injetaria teclas sem o consentimento que o portal
pede. Isso contorna a barreira de consentimento do usuário. NÃO foi implementado. Se o dono quiser esse
caminho, é uma decisão dele, a ser registrada aqui.

## 6. Integração necessária (fora do pacote, para outros agentes ou para o dono)

### 6.1 Core (`src/plugins.rs`, `src/agent.rs`)

- `PASS_THROUGH_ERRORS` precisa de `backend_unavailable` (o worker usa esse código quando um backend falta).
  Os demais códigos que o worker usa já passam: `permission_denied`, `timeout`, `cancelled`, `invalid_input`,
  `stale_screen`, `opt_in_required`, `no_focus`, `unknown_route`, `unknown_app`, `unknown_element`, `busy`,
  `already_recording`, `not_recording`, `response_too_large`.
- Sandbox dos sete plugins: o worker precisa de (1) socket do barramento de sessão
  (`$XDG_RUNTIME_DIR/bus`) para o portal e KGlobalAccel; (2) socket do AT-SPI (`$XDG_RUNTIME_DIR/at-spi/`);
  (3) socket do PipeWire (`$XDG_RUNTIME_DIR/pipewire-0`); (4) `/dev/video*` e `/sys/class/video4linux` (somente
  leitura) para `camera_gesture`; (5) leitura e remoção em `~/Imagens` (o portal grava a captura ali); (6)
  executáveis `python3` com PyGObject (`gi`, `Gio`, `GLib`, typelib `Atspi`), `wpctl`, `pw-dump`, `pw-record`,
  `ffmpeg`, `kscreen-doctor`. A rede continua proibida (sockets Unix não contam).
- Permissões novas no manifest: `global_shortcut` (plugin `shortcut_global`) e `display_manipulate` (já existe
  como string). `world::PERMISSIONS` continua só para os serviços sintéticos; não precisa mudar.
- Prazos: `computer_control.act` pode levar até 60 s (consentimento do portal) e `screen_observe.capture` até
  30 s, mas o teto de capacidade no bridge é 5 s (`PERCEPTION_DEADLINE_MS`). O prazo precisa ser por capacidade.
- Encerramento: o worker restaura as alterações de tela e fecha sessões quando recebe `shutdown`. Se o Core
  matar o processo (SIGKILL), a restauração não roda. O Core deve enviar `shutdown` e esperar antes de matar,
  ou chamar `display_manipulate.restore` ao parar o plugin.
- Ponte do agente: as ferramentas `screen_capture`, `ui_tree`, `ui_click`, `audio_set_route` etc. ainda executam
  os serviços `synthetic.*`. Para usar o backend real, o executor do agente deve invocar a capability do plugin
  (o mesmo caminho do `perceptionInvoke`), com as mesmas checagens de dono e permissão.

### 6.2 Bridge (`app/bridge.py`, dono: outro agente)

- `PERCEPTION_PLUGINS`: incluir `shortcut_global`.
- `PERCEPTION_NO_INPUT`: incluir `display_manipulate.restore`, `shortcut_global.status`, `shortcut_global.events`,
  `mic_advanced.monitor` (já está em CAPABILITIES; o worker aceita `{}`).
- `PERCEPTION_CAPABILITIES`: incluir `display_manipulate.act`, `display_manipulate.restore`, `shortcut_global.bind`.
- `PERCEPTION_OUTPUTS`: os validadores hoje exigem `backend == 'synthetic'` e `real_backend == 'unsupported'`
  (`_synthetic`, `_real_ok`). As saídas reais usam `backend` em {`portal`, `atspi`, `remote_desktop`, `pipewire`,
  `v4l2`, `kscreen`} e status com `available`/`reason`. Formatos (ver `scripts/perception_worker.py`, docstring e
  funções): `screen_observe.capture` = {backend, epoch, width, height, sha256, regions:[]};
  `computer_control.tree` = {backend, epoch, window, elements:[{id, role, name, x, y}]};
  `computer_control.act` = {backend, kind, injected, verified} ou (type) mesma forma;
  `audio_advanced.state` = {backend, default_sink, sinks:[{id,name}], streams:[{id,app,volume}]};
  `audio_advanced.act` = {backend, kind, previous, verified, …};
  `mic_advanced.state` = {backend, source, gain, muted, recording, indicator};
  `mic_advanced.record` = {backend, recording, indicator, seconds, peak, rms, samples} (start: sem métricas);
  `camera_gesture.capture` = {backend, width, height, sha256, mean_luma, indicator};
  `display_manipulate.status` = {backend, outputs:[{name,enabled,scale,brightness}], undo_pending};
  `display_manipulate.act` = {backend, output, op, previous, value, verified};
  `shortcut_global.bind` = {backend, id, trigger, bound}; `shortcut_global.events` = {backend, events:[{id, at_ms}]}.
  Recusas (`supported: false` + `reason`) são saídas válidas, não erros.
- `PERCEPTION_LABELS`, `PERCEPTION_VALUES`, `PERCEPTION_MESSAGES`: rótulos para as chaves novas e mensagens
  para `backend_unavailable`, `unknown_route`, `unknown_app`, `no_focus`, `not_recording`, `already_recording`,
  `timeout`, `busy`. Permissão `global_shortcut` com rótulo "atalho global" em `core.permissionLabel` / tabela
  de permissões.

### 6.3 UI (Qt; arquivos já autorizados mas dependem da ponte)

- `app/components/CPerceptionCard.qml`: remover o selo "SINTÉTICO — sem hardware real" e o selo UNSUPPORTED do
  display quando a saída for real; mostrar `backend` real e `available`/`reason`.
- `app/pages/Percepcao.qml`: remover o aviso de sintético do banner; incluir o cartão de `shortcut_global`.
- `app/pages/CfgDispositivos.qml` (DISP-01/02): trocar "Câmera: simulada" e "Indisponível: sem captura de tela
  real" pelo estado de `camera_gesture.state` (`present`) e `screen_observe.status` (`available`). Hoje o texto é
  fixo; não há dado real chegando à página.

### 6.4 Hub

- O catálogo `tests/fixtures/hub-perception.json` deve ser oferecido pelo caminho de catálogo do Hub (hoje
  só o C0/C4 sintético é carregado). Cada plugin precisa de aprovação própria; nada é concedido por padrão.

## 7. Decisões para o dono

1. Consentimento do portal: aprovar o acesso de teclado para o Gideon quando o KDE perguntar (ou dar um id de
   aplicativo próprio ao Gideon), para que a digitação não dependa do estado do portal.
2. Atalhos: aceitar que o PTT/alternar apareça sob o componente do Claude neste PC, ou dar ao Gideon um desktop
   file próprio.
3. Confirmar que não se quer fallback por `/dev/uinput` (seção 5).
4. Gestos da câmera (instalar modelo) e EQ/redução de ruído (filter-chain): fora do escopo até decisão.
5. Monitoração do microfone: manter recusada (realimentação), ou aceitar com fones de ouvido e indicador.

## 8. Limites deste pacote

- Nenhuma alteração em Rust nem na ponte: `cargo test` e os gates de bridge/UI não foram executados porque
  nada deles mudou. O gate `verify_c4.py` importa `PLUGINS` do gerador; o alias foi mantido e verificado.
- O plugin ainda não roda pelo Core: os testes ao vivo falam com o worker pelo protocolo, como o Core faria, mas
  sem a sandbox do Core (seção 6.1).
- Sem validação de hardware além deste PC e desta sessão KDE/Wayland.
