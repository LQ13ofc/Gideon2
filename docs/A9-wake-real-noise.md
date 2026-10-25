# A9: wake com ruído real do microfone e condicionamento de entrada

Estado: DEV_MEASURED (offline, fala sintética sobre ruído real gravado) / PHYSICAL_PENDING (voz real do
proprietário a 30 a 60 cm não foi medida).
Dados completos: `docs/evidence/wake-real-noise.json`.
Gravações privadas (não versionadas): `/tmp/gideon-wake-lab/real-noise/`. Harness (não versionado):
`/tmp/gideon-wake-lab/realnoise/` (`eval_realnoise.py`, `summarize.py`, `build_evidence.py`).

## Por que este teste

A7 e A8 usaram clipes TTS limpos sobre uma fonte virtual silenciosa. O microfone padrão do proprietário é uma
webcam com ruído de fundo de cerca de -23 dBFS RMS, o fifine idle fica perto de -50 dBFS e a entrada onboard
perto de -44 dBFS. Este teste mede o wake nessas condições, com ruído gravado dos próprios microfones. Ninguém
falou durante as gravações, e nenhum volume ou dispositivo padrão foi alterado.

## Ruído medido

Gravado com `pw-record --raw` em 16 kHz mono s16 (o formato do caminho ao vivo). 90 s por microfone para as
misturas e 22 min por microfone para o teste de ruído puro.

| Microfone | RMS 90 s | Quadros de 20 ms (p10 / p50 / p90 / p99) | Pico | Amostras >= 0,99 (90 s) |
|---|---|---|---|---|
| fifine USB | -29,0 dBFS | -55,8 / -49,1 / -29,2 / -15,0 | 0 dBFS | 11 |
| webcam ASD 650 (padrão) | -21,4 dBFS | -30,8 / -25,5 / -20,2 / -13,0 | 0 dBFS | 2434 |
| onboard analógica | -44,0 dBFS | -44,5 / -44,0 / -43,4 / -43,2 | -32,6 dBFS | 0 |

Em 22 min: fifine -47,0 dBFS RMS (pico -3 dBFS), webcam -23,0 dBFS (5098 amostras >= 0,99), onboard -44,1 dBFS.
A webcam tem cliques a fundo de escala; eles estão no ruído real e ficam no teste.

Conversão do gravador: a captura nativa `pw-record` em 48 kHz estéreo s24 (contêiner int32, 4 bytes por amostra),
decimada 3:1, fica a até 0,2 dB do que a captura 16 kHz dá para os três microfones. O caminho de 16 kHz não
altera o nível.

O filtro de graves (100 Hz) remove pouco do fifine (-0,7 dB), 6,1 dB da webcam e 12,3 dB da onboard, medido sobre
o mesmo trecho de 89 s: o ruído da webcam é majoritariamente grave.

## Protocolo

- Fala: os 51 positivos e os 54 negativos de `/tmp/gideon-wake-lab/clips.json` (TTS Kokoro e Pocket, não voz humana).
- Mistura: cada clipe é escalado para que o RMS da fala ativa fique SNR dB acima do RMS do ruído real do microfone
  (bed de 90 s). SNR em -5, 0, 5, 10 e 20 dB. O -5 dB foi acrescentado ao pedido (0, 5, 10, 20): a webcam a
  distância não tem SNR positivo plausível. Posição aleatória (semente fixa) no bed, 1,0 s de lead e 1,5 s de cauda.
- Cada tentativa começa com um stream novo do motor de produção (`WakeEngine`, sherpa 1.13.8, modelo competitivo),
  com 3 s de aquecimento como no worker ao vivo, e segue frame a frame pelo mesmo módulo de condicionamento.
- Linha de palavra-chave: a do Core no sensibilidade 1,0 (`HH EY1 G IH1 D IY0 AH0 N :1.2 #0.22 @HEY_GIDEON`).
  O limiar global de 0,25 passado ao motor não se aplica à frase, porque a linha tem `#0.22`.
- Ruído puro: 22 min de cada microfone em um stream contínuo (66 min no total) por variante.
- Acerto: qualquer evento `hey_gideon` na tentativa. Falso disparo: qualquer `hey_gideon` em um negativo ou no ruído puro.

Nível de fala implícito (mediana do pico da fala escalada, dBFS). Faixa plausível para pessoa a 30 a 60 cm:
-30 a -8 dBFS sem clipping.

| Microfone | -5 dB | 0 dB | 5 dB | 10 dB | 20 dB |
|---|---|---|---|---|---|
| fifine | -19,4 | -14,4 | -9,4 | -4,4 | +5,6 (0,5% clipado) |
| webcam | -11,8 | -6,8 | -1,8 | +3,2 | +13,2 (6,1% clipado) |
| onboard | -34,3 | -29,3 | -24,3 | -19,3 | -9,3 |

Células com pico implícito fora da faixa (ou clipadas) são mantidas na tabela principal, mas são marcadas como
não plausíveis e aparecem à parte no subtotal.

## Variantes avaliadas (condicionamento antes do detector)

Todas rodam `scripts/audio_conditioning.py` (numpy, streaming, quadros de 20 ms). Nenhuma biblioteca nova.

| Variante | Estágios |
|---|---|
| `off` (atual) | nenhum |
| `hpf` | FIR de 257 taps em 100 Hz (remove DC e grave), atraso de 8 ms |
| `hpf_agc` | `hpf` + AGC (alvo -23 dBFS, ganho máximo +24 dB, ataque e liberação) |
| `hpf_agc_gate` | `hpf_agc` + porta suave (até 12 dB abaixo do piso) |
| `hpf_gate` | `hpf` + porta suave |
| `hpf_ns` | `hpf` + supressão espectral (STFT 320/160, piso de ruído por quadros silenciosos, ganho mínimo -20 dB) |
| `hpf_ns_agc_gate` | `hpf_ns` + AGC + porta |
| `hpf_agc_gate_preemph` | `hpf_agc_gate` + pré-ênfase 0,97 |

## Resultados

Acertos em 51 positivos e falsos disparos em 54 negativos, por microfone e SNR:

| Variante | fifine -5 | fifine 0 | fifine 5 | fifine 10 | fifine 20 | webcam -5 | webcam 0 | webcam 5 | webcam 10 | webcam 20 | onboard -5 | onboard 0 | onboard 5 | onboard 10 | onboard 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `off` | 32 (0) | 44 (0) | 48 (0) | 49 (0) | 48 (0) | 27 (0) | 43 (0) | 41 (0) | 44 (0) | 10 (1) | 13 (0) | 40 (1) | 50 (0) | 51 (0) | 51 (0) |
| `hpf` | 31 (0) | 44 (0) | 49 (0) | 50 (0) | 51 (0) | 29 (0) | 42 (0) | 42 (0) | 46 (0) | 10 (0) | 18 (0) | 46 (0) | 51 (0) | 51 (0) | 51 (0) |
| `hpf_agc` | 31 (0) | 40 (0) | 46 (0) | 44 (0) | 48 (0) | 22 (0) | 40 (0) | 40 (1) | 45 (1) | 8 (0) | 33 (1) | 45 (0) | 50 (0) | 51 (0) | 49 (0) |
| `hpf_agc_gate` | 29 (0) | 41 (0) | 44 (0) | 45 (0) | 47 (0) | 23 (0) | 37 (0) | 39 (1) | 47 (1) | 8 (0) | 30 (0) | 42 (0) | 48 (0) | 51 (0) | 49 (0) |
| `hpf_gate` | 32 (0) | 45 (0) | 49 (0) | 48 (0) | 51 (0) | 27 (0) | 44 (0) | 44 (0) | 48 (1) | 9 (0) | 26 (0) | 47 (0) | 51 (0) | 51 (0) | 51 (0) |
| `hpf_ns` | 25 (0) | 40 (1) | 43 (0) | 48 (0) | 49 (0) | 18 (0) | 34 (0) | 39 (0) | 44 (0) | 7 (0) | 13 (0) | 33 (0) | 47 (0) | 51 (0) | 51 (0) |
| `hpf_ns_agc_gate` | 24 (0) | 33 (1) | 34 (0) | 43 (0) | 46 (0) | 16 (0) | 31 (0) | 39 (0) | 44 (0) | 7 (0) | 28 (0) | 37 (0) | 43 (0) | 48 (0) | 48 (0) |
| `hpf_agc_gate_preemph` | 31 (0) | 38 (0) | 38 (1) | 41 (1) | 45 (1) | 18 (0) | 33 (1) | 34 (0) | 41 (1) | 2 (0) | 22 (0) | 39 (0) | 48 (0) | 48 (0) | 49 (0) |

Totais (765 positivos, 810 negativos, 66 min de ruído puro por variante):

| Variante | Acertos | Falsos em negativos | Falsos no ruído puro | Subtotal plausível: acertos / 408 | Falsos plausíveis / 432 |
|---|---|---|---|---|---|
| `off` | 591 | 2 | 0 | 343 | 1 |
| `hpf` | 611 | 0 | 0 | 352 | 0 |
| `hpf_agc` | 592 | 3 | 0 | 334 | 0 |
| `hpf_agc_gate` | 580 | 2 | 0 | 327 | 0 |
| `hpf_gate` | 623 | 1 | 0 | 353 | 0 |
| `hpf_ns` | 542 | 1 | 0 | 308 | 1 |
| `hpf_ns_agc_gate` | 521 | 1 | 0 | 283 | 1 |
| `hpf_agc_gate_preemph` | 527 | 5 | 0 | 309 | 1 |

Contra `off`, pelo mesmo conjunto de clipes e mesmos offsets: `hpf` recupera 38 positivos que `off` perde e
perde 18 que `off` acerta (saldo +20, cerca de 2,6 pontos). A diferença é pequena e não é uma taxa validada.
Os falsos de `off` são `neg-hi_gideon-bf_emma` na webcam a 20 dB (célula não plausível) e
`neg-hey_giddy-bf_emma` na onboard a 0 dB.

## Escolha

Regra escrita antes da leitura dos resultados: maior número de acertos entre as variantes com zero falso
disparo nos negativos e em pelo menos 20 min de ruído puro por microfone. Só `hpf` cumpre a regra (`hpf_gate`
acerta mais, mas tem um falso disparo na célula não plausível da webcam a 20 dB).

Escolhido: **DC removal + passa-alta FIR de 257 taps em 100 Hz** (`AUTO_CHAIN` em `scripts/audio_conditioning.py`).
Sem AGC, porta, supressão espectral nem pré-ênfase: nenhuma delas melhorou o total sem falso disparo, e o AGC
amplifica os cliques da webcam até o fundo de escala.

Se a regra for trocada por "maior acerto no subtotal plausível", `hpf_gate` empata com `hpf` (353 contra 352)
e tem zero falso disparo nesse subtotal. Não foi escolhido por seguir a regra escrita; vale reavaliar com voz real.

## Implementação

- `scripts/audio_conditioning.py`: módulo numpy, sem dependência nova. Só o caminho `hpf` roda em produção.
- `scripts/wake_worker.py --live --conditioning auto|off` (padrão `off` para o worker; o Core passa o valor da
  preferência). Só o detector recebe os quadros condicionados. Os pacotes para o Core, o VAD, a captura e o STT
  continuam com os quadros crus. O detector de teste (`test-energy-detector`) não aplica condicionamento, para
  continuar sem numpy.
- Preferência `input_conditioning` (`auto` padrão, ou `off`), em `src/storage.rs` (`InputConditioning`, enum com
  serde estrito: outro valor não carrega; entra no `previous_preferences` e no rollback; ledgers antigos carregam
  com `auto`). Chega ao Core pelo `preferences` (campo opcional, como `wake_sensitivity`), é validada e aplicada em
  `src/core.rs`, passa por `src/wake.rs::worker_args` e por `live::Settings`. Mudança reinicia o pipeline de voz
  no próximo limite de sessão, como os outros ajustes de entrada.
- Bridge (`app/bridge.py`): validação do snapshot, `inputConditioningOn`, `setInputConditioning(bool)`.
- Configurações › Dispositivos: switch "Melhorar sinal do microfone (automático)" com ajuda (`app/uisettings.py`,
  `app/pages/CfgDispositivos.qml`).
- Custo: cerca de 14 us por quadro de 20 ms (menos de 0,1% do tempo do quadro). Atraso do filtro: 8 ms.

## Testes e gates

- `cargo fmt --check`: OK. `cargo clippy --all-targets -- -D warnings`: OK.
- `cargo test --no-fail-fast`: 474 testes, 0 falhas (inclui `tests/storage.rs` com a preferência nova, `tests/wake_sensitivity.rs` com os argumentos do worker).
- `scripts/test_audio_conditioning.py` (novo, 10 testes sintéticos: identidade com `off`, passa-alta (DC, 30 Hz, 1 kHz), atraso, AGC com teto de ganho, porta, supressão de ruído branco, pré-ênfase, limites): OK.
- `scripts/test_wake_worker.py` (9 testes, inclui 2 novos de quadros condicionados) e `scripts/test_wake_live.py` (5 testes, inclui `--conditioning`): OK.
- `scripts/test_bridge_protocol.py` (236 testes, inclui chave nova e validação): OK.
- `scripts/test_ui_settings.py` (25 testes, inclui a chave nova): OK.
- `scripts/test_snapshot_contract.py` (17 testes contra o Core de release reconstruído): OK.
  Um ajuste de teste: o teste de preferências (B16) agora espera a sessão de voz do wake replay terminar antes
  do pedido, porque o Core recusa preferências com `busy` enquanto a sessão está aberta (confirmado: `wake_1`,
  estado `capturing`, aberta pelo replay no início). Tentei reproduzir a falha no HEAD exportado (`git archive`),
  mas essa execução caiu num erro de loop de links simbólicos do sandbox; por isso não há prova, nesta sessão,
  de que a falha já existia antes das mudanças. O ajuste só espera a sessão terminar; não altera o que é validado.
- Ponta a ponta com sherpa real: o mesmo clipe `hey_gideon` do laboratório é detectado com `--conditioning off` e
  `--conditioning auto`, no mesmo quadro (2,28 s).

## Limites

- Fala sintética (TTS Kokoro e Pocket) sobre ruído real. Não há voz humana, sala, distância nem laço acústico.
- O SNR é definido pelo RMS da fala ativa contra o RMS do bed de 90 s. Células da webcam a 5 dB ou mais implicam
  pico acima de -2 dBFS com clipping: não são realistas e estão marcadas.
- A escolha entre 8 variantes usa os mesmos clipes que medem o resultado. Não há holdout. O ganho de 2,6 pontos
  é pequeno, e a vantagem sobre `off` na taxa de falsos é de 2 casos em 810.
- Ruído puro: 66 min sem falso disparo. Pela regra de três (95%), a taxa fica abaixo de cerca de 2,7 por hora.
  Não é uma medida por hora.
- Só a sensibilidade 1,0 e a linha de palavra-chave do Core foram medidas. O limiar por sensibilidade continua
  como antes.
- Os cliques de fundo de escala da webcam (5098 amostras em 22 min) não foram tratados; AGC e limitador não ajudaram.
- Medição física com o proprietário falando continua pendente (A7 PHYSICAL_PENDING). O comportamento real depende
  da distância, da sala e da voz dele.

## Reprodução

```sh
# 1. gravação de ruído (privada; 90 s por microfone, 22 min para o teste de ruído puro)
#    pw-record --target <fonte> --raw --rate 16000 --channels 1 --format s16 -  > arquivo.raw
# 2. avaliação por variante (um processo por variante; ~30 min cada com 8 em paralelo)
/home/lucas/GideonV8/versions/0.8.0-ac074071/venvs/a1/bin/python -I /tmp/gideon-wake-lab/realnoise/eval_realnoise.py hpf
# 3. resumo e evidência
/home/lucas/GideonV8/versions/0.8.0-ac074071/venvs/a1/bin/python -I /tmp/gideon-wake-lab/realnoise/summarize.py
/home/lucas/GideonV8/versions/0.8.0-ac074071/venvs/a1/bin/python -I /tmp/gideon-wake-lab/realnoise/build_evidence.py
```

## Revisão (A7, depois de A13): condicionamento no caminho ao vivo e no laboratório

Esta revisão verifica a escolha de `auto` com o mesmo laboratório de A7 (105 clipes, fluxo contínuo na ordem do
laboratório) e com o Core ao vivo. Detalhes e variância em `docs/A7-wake-live-test.md`; dados em
`docs/evidence/wake-live-matrix.json`.

| Medida (HEAD, boost 1,2, limiar 0,22, aquecimento 3 s, sensibilidade 1,0) | auto | off |
|---|---|---|
| Acertos offline, 3 repetições | 44, 44, 43 | 44, 45, 43 |
| Falso disparo em babble de 10 s (offline, 3 repetições) | 0 | 1 (rep. 0) |
| Falso disparo em babble, aquecimento 0 s (offline, 3 repetições) | 0 | 1 (rep. 2) |
| Acertos ao vivo por detecção | 43 e 43 | 44 e 39 |
| Falsos nos 54 negativos ao vivo | 0 | 0 |
| Falsos no ruído real, 66 min (offline, 16 células) | 0 | 0 |

Leitura: `auto` não custa acertos em nenhuma medida e evita o falso disparo do babble que `off` produziu em
execuções offline. Mantém-se `auto` como padrão. Observação: o falso de `okay gideon` com aquecimento de 0 s
(auto, repetição 1) é um concorrente, não o babble; sem aquecimento o fluxo começa frio e o concorrente
pode ganhar a primeira decisão. Não é motivo para mudar o padrão, pois o aquecimento de 3 s é o padrão.

A ponderação de A9 (`hpf` escolhido pela regra escrita) continua válida. O ganho medido aqui é nulo, então a
escolha se apoia no falso do babble e não em acertos.

Limites da revisão: os clipes são TTS (Kokoro e Pocket) e são os mesmos que escolheram o padrão; sem voz humana e
sem medição física com a voz do proprietário.
