# A11 — ações reais no computador (teste ao vivo neste PC)

Estado: REAL_VERIFIED nesta máquina (KDE Plasma Wayland, PipeWire), com 47 checagens ao vivo, 0 falhas.
Não commitado. Responde ao achado U5 de `docs/A10-ui-e2e-owner-path.md`: "open brave" só rodava o executor
simulado de sandbox e a UI dizia "verificado" sem abrir nada.

## O que mudou

Preferência `real_actions` (bool, padrão `false`, `serde(default)`, estrita). Desligada, tudo continua como
antes: o comando passa pelo executor de sandbox (efeito simulado, sem tocar no computador).

- Core (`src/storage.rs`, `src/protocol.rs`, `src/core.rs`): operação `real_actions_preference{revision, enabled,
  confirmed}`. Mesmo padrão de `live_audio`: `consent_required` sem `confirmed`; `busy` com sessão de voz,
  comando ou ferramenta em andamento; `stale_preferences` com revisão velha. Eventos sem conteúdo:
  `real_actions_enabled` / `real_actions_disabled`, e `host_action` (outcome `ok` ou `failed`) para cada ação real.
- Snapshot: `preferences.real_actions` e `actions.real {enabled, last_action}`. `last_action` traz `kind`, `app`
  (só para `open_app`: `brave`, `steam` ou `kcalc`), `ok`, `verified` e `at_ms`. Não é persistido.
- Executor do host (`src/host.rs`, novo; `src/commands.rs` `execute_for`/`execute_host`):
  - Abrir app: resolve o id da lista fixa nas pastas XDG padrão (`/usr/local/share/applications`,
    `/usr/share/applications`, exports do Flatpak e `~/.local/share/applications`). O alias `brave` vira
    `brave-browser.desktop` quando `com.brave.Browser.desktop` não existe. Lançador: `gtk-launch <id>`, senão
    `gio launch <arquivo>`, senão `kioclient6 exec <arquivo>` (caminhos fixos, sem PATH, sem shell). Tempo máximo 5 s
    para o lançador e 5 s para observar o processo. O processo novo (nome igual ao `Exec=`) precisa continuar vivo
    1 s depois, senão não conta.
  - Volume: `wpctl set-volume @DEFAULT_AUDIO_SINK@ N%`, `wpctl set-mute @DEFAULT_AUDIO_SINK@ 1|0`. Toda mudança é
    relida com `wpctl get-volume` antes do recibo; se não bater (tolerância de 1 ponto), o resultado é
    `volume_unverified`. Limites 0–100; `volume up`/`volume down` andam 10 pontos dentro de 0–100.
  - Ambiente limpo, só com `WAYLAND_DISPLAY`, `DISPLAY`, `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`,
    `XDG_CURRENT_DESKTOP`, `HOME`, `XAUTHORITY` e `PATH=/usr/bin:/bin`. `kill_on_drop` em todos os passos.
- Recibo: só existe com efeito observado. Texto em português, ex.: `Abriu: kcalc (processo 496169 observado) ·
  iniciado, sem confirmação de janela`; `Volume em 30% · verificado com wpctl`.
- Gramática (`src/commands.rs`): novas frases fixas `open kcalc` / `abra kcalc` / `open calculator`,
  `unmute` / `unmute audio` / `desmutar`, `volume up` / `aumentar volume`, `volume down` / `diminuir volume`.
  Essas três últimas só existem com consentimento; sem ele, a frase é `unsupported`, como qualquer frase não
  reconhecida.
- Interface: Configurações › Privacidade, seção "Ações no computador" (`app/pages/CfgPrivacidade.qml`), com
  interruptor, linha de estado e diálogo de consentimento (`app/components/RealActionsConsent.qml`, Cancelar é
  o padrão). A linha de estado mostra a última ação confirmada (ex.: "Abriu: brave às 14:32 · confirmado").
  Hoje mostra o texto do recibo, como já fazia. Ponte: `setRealActions`, `realActionsEnabled`,
  `realActionStateText`, validadores estritos de `actions` e de `preferences.real_actions`, tabela
  `COMMAND_CODE_MESSAGES` e `REAL_ACTION_MESSAGES` (português para cada código).

## Desvios e decisões

1. `XAUTHORITY` entrou na lista de ambiente. Sem ele, o Brave escolhe o caminho X11 (XWayland) e sai na hora com
   "Missing X server or $DISPLAY" (provado na sondagem `gtk-launch`, sem o Core). É a única variável além da lista.
2. O Core não verifica janelas. Neste PC não há `kdotool`, e o `qdbus6` não lista janelas sem um script de KWin;
   o Core não carrega esse script. O script de KWin (só leitura, pid e classe) foi usado apenas como verificação externa. Por isso todo recibo de app diz
   "sem confirmação de janela". Quem confirma a janela é o teste, pelo KWin (ver abaixo).
3. `last_action` traz `app` e `verified` além de `kind`, `ok`, `at_ms` (a linha de estado precisa do nome e da
   confirmação). Não há conteúdo de recibo nem caminho.
4. Ferramentas (propostas do modelo, `src/tools.rs`) continuam com a autorização de sandbox (só Brave, volume
   0–100). Com consentimento, a execução delas vai ao host; não foi testada ao vivo.
5. Onboarding (passo 4) não recebeu o aviso: opcional e fora desta entrega.
6. `volume 150` é recusado pela gramática (`unsupported`), antes de chegar ao `denied` do host. O `denied`
   existe como defesa em profundidade e tem teste unitário.

## Teste ao vivo

Script: `scripts/verify_a11_real_actions.py` (cliente em `scripts/a11_client.py`). Usa o binário de release, raiz
privada em `target/a11-real/root` (sem voz e sem microfone: texto pela mesma `dispatch_command` do voice), e o
pacote instalado passa `--commands-sandbox` como este script. Evidência: `docs/evidence/real-actions.json`.

Estado inicial medido: sink HDMI padrão em 0,90 (canal bruto 0,728985), sem mudo; kcalc e Brave não estavam
rodando. Na restauração, o canal voltou a 0,728985 e o mudo a falso (lido de volta pelo PipeWire).

| Passo | Frase | Código | Efeito verificado |
|---|---|---|---|
| consentimento | - | consent_required, depois ok | evento real_actions_enabled |
| volume | set volume to 30 | command_success | wpctl: 30%, verificado |
| mudo | mute | command_success | wpctl: [MUTED] |
| som | unmute | command_success | wpctl: sem mudo |
| volume | volume up / volume down | command_success | 30 → 40 → 30 |
| limite | set volume to 150 | unsupported | sink inalterado |
| app | open kcalc | command_success | processo 496169 novo, janela `org.kde.kcalc` listada pelo KWin; fechado pela janela |
| app | open brave | command_success | 12 processos novos, janela `Brave-browser` listada; fechado pela janela |
| negativo | open foo; open ../../bin/sh; open kcalc; reboot; open kcalc && rm -rf /; mute and open kcalc; open Brave.exe; open brave kcalc | unsupported (todos) | nada executado, sink inalterado, sem kcalc |
| rajada | 5 × mute | ok, busy, busy, busy, busy | um job por vez; sink mudo; depois desmutado |
| consentimento desligado | open kcalc | app_unavailable | nenhum kcalc iniciado |
| consentimento desligado | mute | command_success (scope sandbox) | simulação; sink inalterado |
| consentimento desligado | unmute | unsupported | nada executado |

Auditoria: 6 eventos `host_action`, todos com `kind`, `origin`, `outcome`, `sequence`, `at_ms` e sem app, caminho
ou título. Desligamento limpo do Core com status 0; a raiz privada ficou só com `audit.log`, `config.json` e
`core.lock`.

Ao fechar: o Brave foi fechado pela janela (fechamento normal de janela pelo KWin), sem SIGKILL, e não ficou
`SingletonLock`. Só os pids que o próprio teste viu aparecer foram fechados. Nenhum processo do dono foi tocado.

Diagnóstico durante o teste (corrigido, não é defeito do Core em produção):
- O Brave saía logo após o lançamento porque faltava `XAUTHORITY` (acima). O executor agora exige o processo
  vivo 1 s depois da primeira aparição: antes, um processo que morria no ato contava como aberto.
- O Core derruba conexões paradas por 5 s (`transport.rs`, `peer`). O cliente de teste reconecta sem repetir id.

## Não verificado

- Voz com wake e STT ao vivo (microfone virtual): não foi refeito nesta rodada. O caminho de voz usa a mesma
  `dispatch_command` do texto, mas o teste provou o texto, não o wake.
- Pacote instalado (`gideon-install`) e UI real com clique: não foram usados; a tela Privacidade foi carregada em
  Qt offscreen com o Core simulado no bridge (4 checagens, uma vez, fora do repositório).
- Aplicativo não instalado ao vivo: coberto por teste unitário de resolução em pastas reais temporárias; no PC
  não há app da lista fixa ausente. Steam não foi aberto ao vivo (já estava rodando; evitamos tocar nele).
- Brave abriu com o perfil do dono (o HOME é o real). Um "restaurar sessão" do Brave pode reabrir abas
  antigas na próxima vez que ele abrir sozinho. Não foi observado aqui.
- Ferramentas (propostas do modelo) com ações reais: não testadas ao vivo.
- Janela pelo Core: não implementado (ver desvio 2).

## Gates (sem processos; `cargo` e os três scripts)

- `cargo fmt --check`: OK.
- `cargo clippy --all-targets -- -D warnings`: OK.
- `cargo test`: todos os alvos sem falha (biblioteca 166; alvos de integração todos OK).
- `scripts/test_bridge_protocol.py` (com `target/ui-venv`): 238 OK, com 2 testes novos de consentimento,
  `actions` e textos.
- `scripts/test_snapshot_contract.py`: 18 OK, com o teste novo contra o Core real (consentimento, recusa, `actions`).
- `scripts/test_ui_settings.py`: 25 OK.
- Novo teste unitário em `src/core.rs` (`real_actions_switch_grammar_authority_and_receipts`) e em `src/host.rs`
  (ids, Exec, resolução de alias, leitura de volume, /proc).

## Arquivos

- Rust: `src/host.rs` (novo), `src/commands.rs`, `src/core.rs`, `src/storage.rs`, `src/protocol.rs`,
  `src/transport.rs`, `src/tts.rs`, `src/lib.rs`.
- Ponte e UI: `app/bridge.py`, `app/pages/CfgPrivacidade.qml`, `app/components/RealActionsConsent.qml`.
- Testes: `scripts/test_bridge_protocol.py` (fixtures com `real_actions` e 2 casos novos),
  `scripts/test_snapshot_contract.py` (1 caso novo), `scripts/verify_a11_real_actions.py`, `scripts/a11_client.py`.
- Evidência: `docs/evidence/real-actions.json` (SHA-256 do binário no campo `binary_sha256`).
