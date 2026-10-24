# A6 — áudio ao vivo opt-in, dispositivos e sensibilidade

Estado: IMPLEMENTADO COM TESTES FALSOS. Rótulo: **pendente de validação humana**.
Nada aqui prova microfone, alto-falante, PipeWire ou Pulse reais, nem qualidade acústica.

## O que foi implementado

### A4 — `audio_devices`
- Requisição: `{"version":1,"request_id":ID,"op":"audio_devices"}`. Sem outros campos (campo extra é recusado).
- Resposta: `code:"ok"`. O resultado aparece no snapshot em `audio.devices`, e não existe antes da primeira chamada.
- Forma: `audio.devices = {inputs:[{id,label,default}], outputs:[...], source:"pactl"|"pw-dump"|"none", reason?}`.
  `reason` só existe quando `source` é `"none"`: `no_audio_tool` (nenhuma ferramenta no PATH) ou `audio_tool_failed`.
- Ordem: `pactl --format=json list sources|sinks` (+ `info` para o padrão), depois `pactl list short sources|sinks`, depois `pw-dump`.
- Execução: subprocesso direto, sem shell e sem bwrap, ambiente limpo (PATH, LC_ALL=C, HOME e XDG_RUNTIME_DIR), orçamento total de 3 s, saída máxima de 64 KiB por chamada.
- Filtros: monitores (`monitor_of_sink` ou nome `.monitor`) nunca entram. Um nome bruto fora do charset de preferência é descartado, porque um id "sanitizado" apontaria para outro dispositivo. Rótulos são sanitizados para o mesmo charset (`_` por byte fora dele, até 128 bytes). Máximo de 16 por lista.
- Limitação: a chamada é síncrona no Core e pode bloquear até 3 s no pior caso. `pw-dump` não informa o padrão, então `default` fica falso.

### A5 — `--live-audio` (desligado por padrão)
- Flag única. Exige `--wake-replay` (o perfil do worker de wake). Nenhum gate existente, nenhum teste de pacote e nenhum launcher usa a flag. `gideon-launch` e `gideon-core` não foram alterados; a flag só chega ao Core se alguém a passar manualmente.
- Entrada: `pw-record --rate 16000 --channels 1 --format s16 [--target DEV] -` (ou `parecord --raw --rate=16000 --channels=1 --format=s16le [--device=DEV]`). Escolhido pela disponibilidade no PATH.
- Sandbox: bwrap com `--unshare-all` (sem rede e sem IPC compartilhado), `/usr` somente leitura, `/tmp` privado, ambiente limpo. Só entram os sockets `pipewire-0` e `pulse` de `XDG_RUNTIME_DIR` quando existem, o cookie do Pulse somente leitura e, em testes, o diretório do executável. Sem bwrap, a entrada recusa (`sandbox_unavailable`); não há fallback sem sandbox.
- Pipeline: o stdout do gravador é cortado em quadros de 20 ms (320 amostras s16). Cada quadro vai ao worker `scripts/wake_worker.py --live` pelo stdin. Os pacotes do worker entram por `WakeInput` (pre-roll, cooldown, validação) e por `capture_packet`, o mesmo caminho dos demais wakes. O relógio é contínuo entre reinícios (`--start-us`).
- Contrapressão: o canal de pacotes tem capacidade 2. Quando o Core não consome, o leitor para e o pipe do gravador enche.
- Reinícios: falha do gravador ou do worker gera `backoff` de 200 ms, 400 ms e 800 ms. No máximo 3 reinícios em 60 s; o quarto estouro gera `restart_limit`, o wake fica `failed` e o processo não é reiniciado.
- Encerramento: `SIGTERM` ou fim do Core aborta a tarefa; `kill_on_drop` mata o bwrap, e `--die-with-parent` mata o processo dentro dele. O gravador roda enquanto a flag estiver ligada (não por sessão de voz).
- Preferências: `audio_input_device` é passado como `--target`/`--device` (`default` omite o argumento). Mudança de dispositivo ou de sensibilidade só é publicada entre sessões de voz; então o gravador e o worker reiniciam com os novos argumentos.
- Saída: o PCM do TTS (24 kHz, mesmo ganho de volume da saída virtual) também vai para `pw-play --rate 24000 --channels 1 --format s16 [--target DEV] -` (ou `paplay --raw ...`), um processo supervisionado por tarefa de fala. Falha no player não interrompe a fala: a saída virtual continua e o estado vira `error`.
- Snapshot: `audio.live = {enabled, input_state: idle|capturing|error, output_state: idle|playing|error, mic_active, last_error?}`. `mic_active` é verdadeiro somente enquanto o gravador roda (`input_state == "capturing"`). `last_error` usa vocabulário fechado: `recorder_unavailable`, `recorder_exited`, `sandbox_unavailable`, `wake_worker_unavailable`, `wake_worker_failed`, `restart_limit`, `invalid_device`, `player_unavailable`, `player_write_failed`, `player_failed`, `player_timeout`.
- Não existe op `audio_live_set`; ligar ou desligar é só a flag.

### Sensibilidade do wake (efeito real)
- `wake::keywords_threshold(s) = clamp(0.25 * (2 - s), 0.1, 0.5)`. Mapeamento: 0.5 → 0.375 (mais restrito), 1.0 → 0.25 (padrão, inalterado), 1.5 → 0.125 (mais sensível).
- O worker recebe `--keywords-threshold T` (formatado com 4 casas). O limiar do spotter é fixado na construção, então mudar a preferência reinicia o worker no modo live, na próxima fronteira de sessão.
- Antes desta mudança o worker não reportava score (`confidence` nulo), e o gate `accepts` de `wake.rs` nunca era aplicado; a sensibilidade não tinha efeito. O limiar do spotter passa a ser o mecanismo real.
- Modo replay (fixture, usado pelo pacote atual): o limiar é lido na inicialização do worker. Uma mudança só vale no próximo start do Core, porque reiniciar o replay reexecutaria o fixture.

## O que foi verificado (automatizado, ambiente virtual)

| Verificação | Onde | Prova o quê |
|---|---|---|
| Enumeração pactl JSON, short e pw-dump com ferramentas falsas no PATH | `tests/audio_devices.rs` (7 testes) | Filtro de monitores, nomes inseguros fora, padrão, rótulos sanitizados, fallback, orçamento de 3 s, teto de 64 KiB, `no_audio_tool`, forma do fio e snapshot pelo Core real |
| Gravador falso dentro do bwrap real | `tests/live_audio.rs` | Quadros chegam ao detector (sessão iniciada por sinal), `mic_active` verdadeiro durante a captura, argv com `--target` e `--keywords-threshold 0.3750`, reinício após troca de preferência, morte do gravador no SIGTERM, limite de reinícios com backoff |
| Player falso dentro do bwrap real | `tests/live_audio.rs` | Bytes exatos (sha256 conferido pelo falso), erro quando o hash não confere e quando a ferramenta falha |
| Mapeamento e argumentos do worker | `tests/wake_sensitivity.rs` | Valores 0.375/0.25/0.125, faixa segura, argv de replay e de live |
| Argumentos e quadros do worker sem sherpa | `scripts/test_wake_live.py` (4 testes) | Limites do limiar, exclusão replay/live, relógio contínuo, EOF parcial |
| Validador da ponte | `scripts/test_bridge_protocol.py` (novo teste de `audio`) e `app/bridge.py` | Aceita formas do Core, recusa indicador de microfone falso e lista inválida |

Verificado à parte com o sherpa real (venv de target/a1-venv, sem o Core): `wake_worker.py --live` lendo PCM s16 pelo stdin de um fixture de wake (24 kHz reamostrado por `pcm_fixture`, com silêncio ao redor) produziu 182 pacotes e uma detecção de `hey_gideon`; `scripts/test_wake_worker.py` continua passando (5 testes). Isso prova o caminho de quadros com o modelo real, não o microfone, nem o efeito acústico da sensibilidade. Os testes Rust de integração usam só o detector de energia (`"test_only": true`, engine `test-energy-detector`), porque o venv com sherpa não faz parte dos testes do repositório.

## Pendente de validação humana (NÃO verificado aqui)
- Captura real com PipeWire ou Pulse: se `pw-record` com sockets reais funciona dentro do bwrap, e a latência.
- Qualidade do wake com o microfone real, e se o limiar 0.375/0.125 melhora ou piora em voz real.
- Reprodução audível do TTS pelo `pw-play` ou `paplay`.
- Indicador de microfone na interface: mostra o que o Core reporta, não a captura física.
- Sistema com dispositivos de verdade (listas de `audio_devices`).

## Arquivos
- Core: `src/live.rs` (novo), `src/devices.rs` (novo), `src/transport.rs`, `src/core.rs`, `src/protocol.rs`, `src/wake.rs`, `src/tts.rs`, `src/main.rs`, `src/lib.rs`.
- Worker: `scripts/wake_worker.py` (argparse, `--live`, `--start-us`, `--keywords-threshold`; imports pesados sob demanda).
- Falsos: `tests/fixtures/fake_audio_tools/` (pactl, pw-dump, pw-record, pw-play e variantes) e `tests/fixtures/live_audio/manifest.json`.
- Ponte: `app/bridge.py`, `scripts/test_bridge_protocol.py`, `scripts/test_wake_live.py`.
