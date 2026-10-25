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

## Revisão: variância, causa e nova medição (2026-10-25, depois de A13)

Esta revisão responde à queda de A13 (37/51) e mede o caminho ao vivo de HEAD (4165709) com o mesmo laboratório.
Dados: `docs/evidence/wake-live-matrix.json`. Clipes fixados por sha256 em `docs/evidence/wake-live-pins.json`
(o áudio não é versionado). Verificação: `scripts/wake_live_regression.py check`.

### Não houve regressão de acerto comprovada

| Execução (HEAD, sensibilidade 1.0, 105 clipes) | Condicionamento | Contagem | Positivos | Falsos nos 54 negativos |
|---|---|---|---|---|
| auto r1 | auto | sessões (STT ok) | 43/51 | 0 |
| auto r2b | auto | detecções | 43/51 | 0 |
| off r2 | off | detecções | 44/51 | 0 |
| off r1b | off | detecções | 39/51 | 0 |
| auto r2, off r1 | | sessões (STT falhou) | 2 e 4 (inválidas) | 0 |

- Contagem por detecção: `live.last_detection` do snapshot, com ou sem sessão. Contagem por sessão só vê
  sessões que aparecem em uma amostragem; quando o STT falha, a sessão termina antes e a contagem cai (2 e 4 acima).
  Por isso as execuções inválidas não entram na taxa. O harness passou a contar por detecção.
- O STT do laboratório travou (`worker_crashed`, reinícios e depois `failed`) em todas as execuções por detecção.
  O acerto do wake não depende do STT, mas as sessões seguintes terminam como `stt_failed`. Causa não encontrada
  nesta rodada (o traceback do worker não é guardado). Ver a seção de limites.
- Offline, a mesma configuração (`scripts/wake_live_regression.py`, fluxo contínuo na ordem do laboratório) dá
  43, 44 e 44 em três repetições; ao vivo deu 39 a 44. O modelo offline reproduz o ao vivo.
- O número 37/51 de A13 não pode ser reproduzido com os dados guardados: o harness de A13 usava janela de 2,5 s e
  contagem por sessão, e não há como saber se o STT falhou naquela execução.

### Quais mudanças custam acertos (medido, offline, mesmos clipes e ordem)

Três repetições por célula. A coluna "pareado" é a diferença repetição a repetição com a configuração de HEAD.

| Célula | Acertos por repetição | Média | Falsos (negativos) | Pareado vs HEAD |
|---|---|---|---|---|
| HEAD: boost 1,2, limiar de frase 0,22, auto, aquecimento 3 s | 44, 44, 43 | 43,7 | 0 | - |
| pacote (A7): sem boost, limiar 0,25, auto, 3 s | 40, 42, 42 | 41,3 | 0 | -2,3 (todas <0) |
| HEAD sem condicionamento (off) | 44, 45, 43 | 44,0 | 1 (babble, rep. 0) | +0,3 |
| HEAD sem aquecimento (0 s) | 36, 41, 47 | 41,3 | 1 (okay, rep. 1) | -2,3 (sinal misto: +8, +3, -4) |
| pacote, sem condicionamento, sem aquecimento | 38, 44, 48 | 43,3 | 0 | - |
| sem os concorrentes (só a linha "hey") | 44, 44, 43 | 43,7 | 2 a 4 (okay, hi, babble) | - |
| linha extra de variante "HEY" | 44, 44, 43 | 43,7 | 0 | 0 |

Conclusões de A7 que mudam:

- A tabela de A7 (41/51, 50/51, 44/51) mistura execuções diferentes. A média da mesma configuração, medida
  agora, é 41 a 44 de 51. Diferenças menores que cerca de 5 acertos entre execuções de uma só configuração não
  são sinal (ver variância abaixo).
- O número "51/51 com boost 1,2" de `docs/evidence/wake-phrases.json` não foi reproduzido. Foi retirado
  como evidência e a justificativa está no próprio arquivo.
- Os concorrentes (linhas OKAY e REJECT) são necessários. Sem eles, "Okay Gideon" e "Hi Gideon" disparam.
- O aquecimento de 3 s foi mantido pela medição de cold start de A7 (D4: 28/51 com 1 s de antecedência, 47/51 com
  4 s, em clipe isolado logo após o início do worker). Em fluxo contínuo o efeito médio (+2,3) não separa do efeito de
  alinhamento; ele muda a fase de rotação de todos os clipes.

### Variância: de onde vem

- Mesma configuração, seis repetições offline: 42 a 49 (desvio-padrão 2,4). Ao vivo: 39 a 44.
- Não é a fase da rotação do stream: positivos por posição desde a última rotação dão 85% a 88% em
  cada faixa de 2 s (0 a 8 s; a rotação ocorre a cada 8 s, pois o worker rotaciona aos 10 s e reinicia com 2 s de
  sobreposição).
- Não é o limiar: clipes borderline disparam mesmo com limiar 0,35 quando estão isolados (traço de limiar de
  cinco clipes), e 0,15 a 0,22 dão os mesmos acertos.
- É o alinhamento do clipe com a grade de quadros do encoder (varredura de 320 ms em passos de 10 ms, motor isolado):
  "hey brave af_bella clean" acerta 13 de 32 posições; "hey time am_michael room" 16 de 32; "hey plain am_michael clean"
  8 de 32; "hey plain bf_emma snr20" 32 de 32. Cada execução ao vivo coloca cada clipe em outra posição da grade.
  Os clipes que mudam entre repetições são cerca de 16 dos 51.
- Portanto a variância entre execuções é intrínseca ao modelo de streaming (zipformer em blocos), não é um
  defeito do Core. Não há um limiar que a elimine sem falsos disparos (ver a grade abaixo).

### Ajuste de padrões: nenhum

Grade de boost x limiar de frase (auto, 3 s, sensibilidade 1,0, 6 repetições, 66 min de ruído):

| Boost | Limiar de frase | Acertos por repetição | Média | Falsos nos negativos | Falsos no ruído |
|---|---|---|---|---|---|
| 1,0 | 0,22 | 42, 42, 42, 44, 40, 48 | 43,0 | 0 | 0 |
| 1,2 | 0,15 a 0,22 (padrão 0,22) | 44, 44, 43, 44, 42, 49 | 44,3 | 0 | 0 |
| 1,2 | 0,26 | 42, 44, 42, 44, 42, 49 | 43,8 | 0 | 0 |
| 1,4 | 0,22 | 43, 46, 45, 45, 43, 49 | 45,2 | 1 (babble, 1 de 6) | 0 |
| 1,6 | 0,22 | 42, 46, 45, 47, 43, 49 | 45,3 | 3 de 6 repetições | 0 |

O maior número de acertos com zero falso disparo é boost 1,2 com limiar 0,22 (padrão de HEAD, sem mudança). Boost 1,4
ganha cerca de um acerto e admite o clipe de babble de 10 s. Limiar abaixo de 0,22 não muda nada nesta faixa.
Pareado contra boost 1,0: +1,3 acertos (2, 2, 1, 0, 2, 1), mas isso é uma medição feita sobre o mesmo conjunto que
escolheu o padrão: não há holdout. Os 66 min de ruído real não deram falso disparo em nenhuma célula.

### Regressão

`scripts/wake_live_regression.py check` (chão 0,82 = 42 de 51, mínimo de três repetições e ruído de 66 min):
- configuração de HEAD: PASS, mínimo 43/51 (0,843), 0 falsos.
- controle negativo (pacote, sem condicionamento, sem aquecimento): FAIL, saída 1.

### Limites desta revisão

- Os clipes são os mesmos que escolheram o padrão (sem holdout). Medição física com a voz do proprietário continua pendente.
- O STT do laboratório falha durante as execuções ao vivo (`worker_crashed`). A causa não foi encontrada; o
  acerto do wake foi contado por detecção. Esse problema é separado e precisa de investigação própria.
- Execuções ao vivo: cinco com contagem válida ou parcial, nove minutos cada. Não é amostra estatística do microfone do proprietário.
- O traço de limiar e a varredura de fase usam o motor isolado; não são uma medida ao vivo.
