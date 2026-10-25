# A7 — teste do wake ao vivo com dispositivos virtuais

Estado: VIRTUAL_VERIFIED / PHYSICAL_PENDING.
Escopo: o caminho `--live-audio` do Core (captura PipeWire, worker de wake, STT, comando e
fala de saída) foi exercitado de ponta a ponta com dispositivos virtuais criados para este teste.
Nenhum microfone, alto-falante ou dispositivo físico do proprietário foi usado. Os padrões
padrão de saída e entrada do sistema foram verificados antes e depois e permaneceram iguais.
Dados completos: `docs/evidence/wake-live-virtual.json`.

## O que foi montado

- Sink nulo `gideon_lab_sink` e fonte virtual `gideon_lab_mic` (remap do monitor do sink).
  Os módulos foram descarregados ao fim do teste.
- Clipes de 16 kHz mono s16, pico em no máximo -6 dBFS (105 clipes):
  - 51 positivos (Hey Gideon, Hey Gideon open Brave, Hey Gideon what time is it,
    Hey Gideon mute em composição) com 4 vozes Kokoro do corpus QA existente
    (`~/.cache/gideon/phase3.5/kokoro/canonical-corpus-py313-v2`), variantes de ruído,
    sala, volume baixo e alto, e 3 frases Pocket TTS.
  - 54 negativos: sósias (Hey Julian, Hey Giddy, Hi Gideon, Okay Gideon, Gideon sozinho),
    comandos sem a palavra de ativação, frases comuns, Okay Google e Hey Jordan (Pocket TTS),
    silêncio, ruído branco e rosa, e babble.
- Core real com a flag `--live-audio`, raiz privada, preferências `audio_input_device=gideon_lab_mic`
  e `audio_output_device=gideon_lab_sink` definidas pela operação `preferences`.
- Cada clipe tocado com `pw-play --target gideon_lab_sink`; o Core captura de `gideon_lab_mic`.
  O snapshot foi amostrado durante toda a execução (cerca de 20 ms).

## Resultados

Taxa de acerto por sensibilidade (positivos) e falsos disparos (negativos). Cada execução
completa tem os 105 clipes; as três execuções estão listadas porque houve variância entre elas.

| Execução | Código | s=0.5 (limiar 0.375) | s=1.0 (limiar 0.25) | s=1.5 (limiar 0.125) | Falsos disparos (negativos) |
|---|---|---|---|---|---|
| A | captura corrigida (D1, D3) | 41/51 | 41/51 | 44/51 | 0/54 em cada sensibilidade |
| B | + player e gramática (D2, D5) | 41/51 | 50/51 | 45/51 | 0/54 em cada sensibilidade |
| C (final) | + aquecimento do worker (D4) | 42/51 | 44/51 | 44/51 | 0/54 em cada sensibilidade |

Leitura dos números:

- Nenhum falso disparo em nenhuma das 9 passadas. Os negativos somam cerca de 0,86 h de áudio
  (as mesmas 54 amostras repetidas), o que ainda não sustenta uma taxa por hora. Pela regra
  de três, o limite superior de 95% com zero observado é cerca de 3,5 por hora; isso não é uma
  medida real. Falta um teste de horas com negativos.
- A variância entre execuções com a mesma configuração é grande: s=1.0 deu 41/51 (A) e 50/51 (B).
  Essa diferença vem do tempo de reprodução em relação ao stream, não de mudança no caminho do
  wake. Diferenças abaixo de cerca de 10 pontos devem ser tratadas como ruído com esta amostra.
- Latência medida pelo snapshot (incluindo amostragem e IPC):
  - Relativa ao início do clipe: mediana 1,6 s (p10 1,5 s, p90 1,7 s) em s=1.0, final C.
  - Relativa ao fim do clipe, para "Hey Gideon." sozinho (10 casos): mediana -42 ms
    (faixa -246 a +62 ms), isto é, o disparo sai perto do fim da frase. Para frases com
    comando, o disparo sai antes do fim do clipe porque o comando continua sendo falado.
  - Não é medida até o fim da palavra "Gideon", que não foi segmentada.
- Comandos depois do disparo (s=1.0, final C): "open Brave" 13 de 17 disparos executaram
  comando; "what time is it" 12 de 12; "mute" 1 de 5 (ver limitações); "Hey Gideon." sozinho
  não executa comando, como esperado.

Engine isolado (sem Core, sem PipeWire, worker antes do aquecimento, 1 s de silêncio antes
e depois): 25/51 com limiar 0.375, 28/51 com 0.25 e 28/51 com 0.125.

## Defeitos encontrados e corrigidos

| ID | Etapa | Sintoma | Causa raiz | Correção |
|---|---|---|---|---|
| D1 | gravador (`src/live.rs` `recorder_args`) | captura ativa, nenhum wake | `pw-record ... -` grava um contêiner AU (cabeçalho `.snd` de 24 bytes, amostras big-endian). O worker lia como little-endian: rms 11428 e pico 32768 em vez de rms 1524 e pico 12686 | `--raw` no `pw-record`. Antes e depois: correlação 0,999 com o clipe fonte e disparo de `hey_gideon` |
| D2 | player de fala (`src/live.rs` `player_args`) | fala salva com `player_write_failed` no meio do áudio | `pw-play -` sem `--raw` lê stdin como arquivo de som: "Format not recognised", código 1 | `--raw` no `pw-play`. Antes: `playing -> error`. Depois: `playing -> idle`, sem erro |
| D3 | sandbox do worker vivo (`src/live.rs` `spawn_worker`) | latente: falha ao carregar modelos se os assets ficarem fora do home montado | o worker vivo montava só o manifesto; o replay monta também `asset_root` e o diretório do VAD | `worker_mounts()` monta `asset_root` e o diretório do VAD (campos opcionais, caminhos absolutos). Não foi a causa no pacote, onde os assets ficam sob o home |
| D4 | engine do wake (`scripts/wake_worker.py`, só ao vivo) | fala nos primeiros segundos após o start do worker (boot, troca de preferência, reinício) não dispara | stream de palavra-chave novo não tem histórico do encoder. Com 1 s de lead: 28/51; com 4 s: 47/51 (mesmo áudio, mesmo limiar) | `WakeEngine.warm_up()`: 3 s de silêncio antes do primeiro quadro do Core. Detecções durante o aquecimento são descartadas e a origem do stream recua, então os tempos continuam no relógio do Core |
| D5 | gramática de comando (`src/commands.rs` `parse`) | o wake disparou e a transcrição estava certa, mas nenhum comando rodou ("Hey, Gideon, open brave.") | o STT põe vírgula depois da primeira palavra de ativação; o prefixo literal "hey gideon" não casava com "hey, gideon" | `unify_wake_comma`: uma vírgula depois da primeira palavra vira espaço. As demais vírgulas continuam sendo gramática exata ("open, brave" segue recusado). Execução A: "open Brave" com comando em 7 de 15 disparos; execução B: 19 de 21 |

Cada correção tem teste: `recorder_args` e `player_args` com argv exato; `worker_mounts`;
`stt_comma_after_wake_word_is_the_only_comma_accepted`; `test_warm_up_keeps_the_core_clock_and_emits_nothing`
em `scripts/test_wake_worker.py`.

Prova do aquecimento ao vivo (Core novo por tentativa, clipe tocado 0,3 s depois da captura
começar, mesmo binário, só o worker muda): worker do pacote 0/6 disparos; worker com
aquecimento 6/6, com transcrições como "Hey, Gideon, open brave." e "Hey, Gideon.".

Também foram revisados e não são causa do problema: a fronteira de rotação do stream (10 s)
mostrou apenas falhas marginais do engine, sem padrão monotônico; a conversão de taxa 48 kHz -> 16 kHz
do PipeWire preserva o sinal (correlação 0,999).

## Pacote atual e o que o proprietário precisa saber

- O launcher (`scripts/package_tools/gideon-launch` e `gideon-core`) não passa `--live-audio`. No
  pacote padrão o wake vem do fixture de replay, e o microfone nunca é aberto. Essa é a razão
  principal para "o wake não está funcionando" no uso normal. Ligar a escuta ao vivo é uma
  decisão de produto (A6 mantém a flag opt-in); este teste não altera o launcher.
- Com `--live-audio`, a saída de fala usa `audio_output_device`; o padrão `default` é a saída
  física do sistema. Este teste sempre definiu `gideon_lab_sink`.
- O pacote V8 instalado (`~/GideonV8`) contém D1 e D2 e D4; ele não foi alterado. Os binários e
  scripts corrigidos estão no repositório (`target/release/gideon-base`, `scripts/wake_worker.py`).
- O comando padrão do replay continua igual: `replay_finished`, transcrição "Hey Gideon, open brave.",
  mesmo hash de captura, sem `--live-audio`.

## Pendente e limitações

- Microfone e alto-falante reais: não testados. Sala, distância, voz do proprietário e ruído
  acústico real não foram medidos.
- Falsos disparos: sem horas de negativos, não há taxa por hora sustentável.
- Vozes: 4 vozes Kokoro sintéticas e 1 voz Pocket. Não há gravações humanas.
- Gramática de comando: "Hey Gideon. Mute." (ponto depois da ativação) continua recusado por
  decisão de gramática; erros de reconhecimento do STT ("A gideon", "Gideons", "Gideon" sozinho) não
  executam comando. Isso é qualidade de reconhecimento, não do caminho do wake.
- Um caso de frase cortada ("Hey, Gideon, what time is") indica que o endpoint da captura pode
  encerrar antes do fim da frase; não investigado a fundo.
- Os clipes são derivados do corpus QA (licença marcada como artefato privado de teste); o áudio
  não foi versionado.

## Gates finais

- `cargo fmt --check`: OK.
- `cargo clippy --all-targets -- -D warnings`: OK.
- `cargo test`: 429 testes, 0 falhas (inclui `tests/live_audio.rs`, `tests/audio_devices.rs`).
- `scripts/test_wake_worker.py`: 6 testes OK. `scripts/test_wake_live.py`: 4 testes OK.

## Como reproduzir

Pré-requisitos: PipeWire com `pw-record`, `pw-play`, `pactl`; `bwrap`; o pacote V8 em
`/home/lucas/GideonV8/versions/0.8.0-ac074071` (somente leitura); repositório compilado com
`cargo build --release --offline`. O laboratório de testes está em `/tmp/gideon-wake-lab`
(não versionado).

```sh
# 1. dispositivos virtuais (anote os ids; descarregue ao fim)
pactl load-module module-null-sink sink_name=gideon_lab_sink rate=48000 channels=2 sink_properties=device.description=GideonLabSink
pactl load-module module-remap-source master=gideon_lab_sink.monitor source_name=gideon_lab_mic source_properties=device.description=GideonLabMic

# 2. clipes (corpus QA existente + Pocket TTS do repositório)
/home/lucas/GideonV8/versions/0.8.0-ac074071/venvs/a1/bin/python -I /tmp/gideon-wake-lab/make_clips.py
/home/lucas/GideonV8/versions/0.8.0-ac074071/venvs/a1/bin/python -I /tmp/gideon-wake-lab/gen_tts.py

# 3. home privado com o worker corrigido (hard links, sem copiar o pacote; manifestos reescritos)
cp -al /home/lucas/GideonV8/versions/0.8.0-ac074071 /home/lucas/Documentos/Gideon/base/target/wake-lab-home
# remova o link antes de copiar: escrever no arquivo compartilhado alteraria o pacote instalado
rm /home/lucas/Documentos/Gideon/base/target/wake-lab-home/scripts/wake_worker.py
cp /home/lucas/Documentos/Gideon/base/scripts/wake_worker.py /home/lucas/Documentos/Gideon/base/target/wake-lab-home/scripts/wake_worker.py

# 4. matriz completa (uma execução por sensibilidade; ~8 min cada)
/home/lucas/GideonV8/versions/0.8.0-ac074071/venvs/a1/bin/python -I /tmp/gideon-wake-lab/matrix.py \
  /home/lucas/Documentos/Gideon/base/target/release/gideon-base \
  /home/lucas/Documentos/Gideon/base/target/wake-lab-home 1.0,0.5,1.5 --tag final2
/home/lucas/GideonV8/versions/0.8.0-ac074071/venvs/a1/bin/python -I /tmp/gideon-wake-lab/analyze.py final2

# 5. aquecimento ao vivo (A/B com o mesmo binário)
/home/lucas/GideonV8/versions/0.8.0-ac074071/venvs/a1/bin/python -I /tmp/gideon-wake-lab/cold_live.py \
  /home/lucas/Documentos/Gideon/base/target/release/gideon-base warmup \
  /home/lucas/Documentos/Gideon/base/target/wake-lab-home "hey_plain-af_bella-clean,hey_plain-am_michael-clean" cold

# 6. encerramento
pactl unload-module <id-do-null-sink>
pactl unload-module <id-do-remap-source>
```

Verificação de cada etapa: `results/<tag>-s<sens>.json` (por clipe: disparo, latência,
transcrição, comando), `results/summary-<tag>.json` (tabelas), e `docs/evidence/wake-live-virtual.json`.
