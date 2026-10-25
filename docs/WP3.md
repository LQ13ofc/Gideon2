# WP-3 — Superfície do HUD (HUD-01, HUD-02)

Pacote: `app/components/Orb.qml`, `app/pages/InicioHoje.qml`, teste `scripts/test_hud_qml.py`.
Sem commit (o orquestrador commita). Nenhum arquivo de Rust, `bridge.py`, `Main.qml` ou `TopBar.qml` foi alterado.

## 1. O que foi feito

### HUD-01 — nove estados visuais

O Orb tinha 5 modos. Agora tem 9, cada um com anel e movimento próprios (`Orb.qml`):

| Estado | Anel / movimento (movimento normal) | Movimento reduzido ou desligado |
|---|---|---|
| Idle | anel suave, parado | parado |
| WakeDetected (`wake`) | anel que abre uma vez e some | anel fixo |
| Listening (`listening`) | dois anéis de ondulação | um anel fixo |
| Transcribing (`transcribing`) | arco azul de informação que gira | arco fixo |
| Thinking (`thinking`) | arco acento fixo e corpo girando | arco fixo, corpo parado |
| Acting (`acting`) | arco de progresso (`progress` 0..1) ou arco girando | arco fixo |
| Speaking (`speaking`) | anel fixo e corpo respirando | anel fixo |
| Error (`error`) | anel vermelho, corpo esmaecido | igual |
| AwaitingConfirmation (`confirm`) | anel tracejado âmbar que gira devagar | tracejado fixo |

O nome de acessibilidade do Orb usa palavras em português (`modeWords`), não o identificador do modo.

`InicioHoje.qml` mapeia o estado do Core para o modo (`describeHud()`). A ordem é a de `docs/ui-spec/10-assistente.md` §2.2, com os nove estados:

| Modo | Campo do Core que decide |
|---|---|
| wake | `state` = `capturing` e `audio.live.last_detection.at_ms` com menos de 2,5 s, sem transcrição ainda |
| listening | `state` = `capturing` (o resto da captura) |
| transcribing | `state` = `transcribing` (transcrição em `transcript.raw`, parcial ou final) |
| acting | `state` = `executing`, ou `agentState` = `waiting_tool` (ferramenta do passo com `state` = `running`, progresso de `agentBudget`) |
| speaking | `state` = `speaking` |
| confirm | há proposta com `state` = `pending`, ou `agentState` = `awaiting_approval` |
| thinking | `chatState` em `waiting`/`streaming`, ou `agentState` = `thinking` |
| error | `safe_mode`, `restart_required`, estado desconhecido, `chatState` = `error`, `agentState` em `failed`/`blocked`, ou comando sem recibo verificado |
| idle | o resto (com recibo verificado, se houver) |

Desconectado (`connected` falso) fica em idle esmaecido com "Core desconectado".

### Estados vistos na tela

Na tela, o Hoje mostra, conforme o estado: a frase e a linha de apoio; a transcrição (`hudTranscript`, "Você (parcial): …"); a ferramenta em execução (`hudTool`); a barra de progresso e "Passo n de m" (`hudProgress`); o recibo verificado ou falho (`hudReceipt`, "Concluído · …" em verde, "Falhou" em vermelho); e o botão **Cancelar** (`hudCancel`), que chama `core.cancel()` (sessão de voz), `core.agentAbort()` (run do agente) ou `core.cancelChat()` (resposta do chat), conforme o que está ativo.

### HUD-02 — aviso de microfone ativo

O `Badge` "Microfone ativo" (`hojeMicBadge`) é texto visível sempre que `core.micActive` é verdadeiro, que vem de `audio.live.mic_active` (o gravador do Core captura). Não depende do nome do estado. Antes o aviso era só `Accessible.description` mais o badge da página Percepção.

### Movimento reduzido

`Orb.fullMotion` é `Theme.animationMode === "normal"`. Com `theme.animation` em `reduced` ou `off` (ou modo econômico), nenhum laço, rotação ou escala roda. Cada estado continua distinto só por forma e cor. O teste liga e desliga a configuração real pela `ui.set('theme.animation', …)`.

## 2. Evidência do Core

### Como o Core real foi iniciado

Binário de release já compilado (`target/release/gideon-base`; nenhum arquivo Rust mudou). Raiz privada de 0700 em `$XDG_RUNTIME_DIR` (o caminho do socket precisa ter menos de 108 bytes; em `/tmp/claude-1000/…` não cabe). Argumentos, igual a `scripts/verify_c0_plugins.py`:

```
target/release/gideon-base --root <raiz> --virtual-input --plugin-python /usr/bin/python3 --commands-sandbox \
  --hub-catalog tests/fixtures/hub-c1.json <sha256> --base-pack target/base-pack-dev.json \
  --tts-virtual target/tts-venv/bin/python target/a5-assets/manifest.json \
  --wake-replay target/a1-venv/bin/python target/a3-assets/replay-manifest.json 244
```

Índice `244` = fixture `wake-hey-brave__bf_emma__clean`. Isso é o PCM virtual; o microfone físico não foi usado.

### Teste ao vivo (`HudLive`)

Um Core real, o Shell real (`app/Main.qml` via `main.create`), e comandos enviados pelo `bridge.submitText` quando o Core está quieto. Os modos vistos pela UI em duas execuções seguidas (ordem de aparição):

- Execução 1: idle, listening, wake, listening, transcribing, acting, speaking, idle, acting, speaking, idle, speaking, error
- Execução 2: idle, listening, wake, listening, transcribing, speaking, idle, acting, speaking, idle, speaking, error

Recibos reais: "Concluído · Processo do app verificado no sandbox: com.brave.Browser.desktop" (`open brave`, verificado); "Falhou" com "Comando não entendido; nada foi executado" (`open nosuchapp`, `unsupported` do Core).

Transcribing e acting duram poucas centenas de milissegundos no Core e nem sempre caem numa amostra de 20 ms; por isso o teste não os exige, mas registra os que apareceram.

### Snapshots no contrato (`HudContract`)

Para os estados que o PCM virtual não alcança de forma confiável (thinking, confirm, acting pelo agente, safe mode, desconectado, recibo verificado), o teste lê um snapshot real do Core, altera só os campos do estado e passa o resultado por `validate_snapshot` antes de `bridge._apply`. A UI só lê a ponte. Um laço de reconexão do bridge esvaziava o snapshot injetado, então o shell de teste fica "congelado" (`freeze()`), sem tentativas de socket.

## 3. Comandos executados e resultados

Todos em `/home/lucas/Documentos/Gideon/base`, com `QT_QPA_PLATFORM=offscreen` onde indicado.

| Comando | Resultado |
|---|---|
| `target/ui-venv/bin/python scripts/test_hud_qml.py` (execução 1) | 13 testes OK (12 `HudContract` + 1 `HudLive`), rc 0, 32,7 s |
| `target/ui-venv/bin/python scripts/test_hud_qml.py` (execução 2) | 13 testes OK, rc 0, 33,9 s |
| `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_bridge_protocol.py` | 251 testes OK, rc 0 |
| `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_snapshot_contract.py` | 18 testes OK |
| `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_languages_qml.py` | 4 testes OK |
| `python3 scripts/graph.py` (AGENTS.md, após editar QML) | rc 0, `graphify-out` atualizado |

Durante o desenvolvimento rodei também `test_hud_qml.py HudContract` e `HudLive` separadamente, com correções até o verde (validação de transcrição `source`, `audio.live.last_error`, reconexão do bridge, debounce do `nowMs`, envio de texto só com Core quieto).

Não foram rodadas as demais gates (`verify_*`, matriz completa), conforme a orientação de tempo do dono; a matriz fica para o fim.

### Capturas

Em `target/evidence/wp3/` (PNG de 640×900, HiDPI não usado):

- Contrato: `01-idle.png`, `02-wake-detected.png`, `03-listening.png`, `04-transcribing.png`, `05-speaking.png`, `06-acting.png`, `07-thinking.png`, `08-awaiting-confirmation.png`, `09-error.png`
- Ao vivo (Core real): `live-idle.png`, `live-wake.png`, `live-listening.png`, `live-transcribing.png`, `live-speaking.png`, `live-acting.png`, `live-error.png`
- Movimento reduzido: `reduced-off-confirm.png`, `reduced-reduced-confirm.png`

Revisei as capturas. Cada estado tem forma e cor próprias: tracejado âmbar em aprovação, anel vermelho e "Falhou" em erro, barra e "Passo 2 de 6" em execução, badge "Microfone ativo" em escuta. Em movimento reduzido o tracejado continua visível e fixo.

## 4. Limites e o que resta

- **Microfone físico não testado.** O aviso "Microfone ativo" foi exercitado pelo `audio.live.mic_active` nos snapshots de contrato. No Core ao vivo o microfone estava desligado (PCM virtual). A captura física e o aviso real dependem do dono (`docs/HUMAN_VALIDATION.md`).
- **Thinking, AwaitingConfirmation e acting pelo agente não rodaram com LLM real.** Foram exercitados por snapshots de contrato validados. Um teste com `llm_engine` e proposta real de ferramenta fica para a gate C3/UI.
- **Cancelar não foi clicado.** Os três caminhos chamam slots que já existem (`cancel`, `agentAbort`, `cancelChat`), mas nenhum teste pressiona o botão `hudCancel`. Isso precisa de um clique real numa sessão de voz.
- **Cancelar duplicado na tela.** Durante uma sessão de voz, o Hoje mostra o "Cancelar" do HUD e o da barra superior (`cancelButton` em `app/shell/TopBar.qml`, que não é deste pacote). O dono da barra decide se o da barra some nesta página.
- **Orb da barra superior.** `TopBar.qml` usa o mesmo `Orb` com 18 px. O modo `thinking` agora mostra um arco fixo também ali. Não é regressão visual, mas é uma mudança visível fora do Hoje.
- **Transcribing e acting** só aparecem em algumas execuções do teste ao vivo (são transitórios; ver seção 2).
- **Movimento do sistema não testado.** A configuração `behavior.reduceMotionFollowSystem` (GNOME) não foi ligada no teste; só `theme.animation` foi.
- **Fora do pacote, visto durante o teste:** `app/pages/CfgPrivacidade.qml:211` lança `TypeError: Property 'retentionIndex' … is not a function` ao carregar `Main.qml`. Não é deste pacote; o teste continua passando, mas a mensagem aparece no log.
- **Sem commit.** As mudanças estão no working tree.

## 5. Arquivos

- `app/components/Orb.qml` (nove modos, movimento reduzido, nomes de acessibilidade)
- `app/pages/InicioHoje.qml` (`describeHud`, transcrição, ferramenta, progresso, recibo, Cancelar, aviso de microfone)
- `scripts/test_hud_qml.py` (13 testes: `HudContract` e `HudLive`)
- `docs/GAP_AUDIT.md` (linhas HUD-01 e HUD-02 marcadas `[WP3 FEITO]`)
- `docs/WP3.md` (este arquivo)
