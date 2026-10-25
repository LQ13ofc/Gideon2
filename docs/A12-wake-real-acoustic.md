# A12: wake ao vivo com microfone real, após levantar o teto de volume

Data: 2026-10-25. Estado: **NO_AIR_PICKUP_AT_90PCT**. Nenhum microfone real ouviu os alto-falantes
do ambiente, nem com o volume em 90 %. O único par que levou o clipe ao Core foi uma **malha elétrica**
(saída de linha interna para a entrada "microfone traseiro" da mesma placa), não ar. Os dados brutos
sem áudio estão em `docs/evidence/wake-real-acoustic.json`. Nada foi commitado.

Taxa de acerto e de falso disparo **em acústica real: não medidas** (0 de 20 positivos com o alto-falante
do ambiente; ver seção 3).

## 1. Estado do áudio do proprietário

Gravado antes em `/tmp/gideon-wake-lab/real/audio-state-before.json`. Restaurado com
`/tmp/gideon-wake-lab/real/restore.py` (valores brutos do pactl, leitura de volta, sem problemas).

| Item | Antes | Depois |
|---|---|---|
| Saída padrão | HDMI VG2791R (`alsa_output.pci-0000_03_00.1.hdmi-stereo-extra4`) | igual |
| Entrada padrão | webcam ASD (`alsa_input.usb-ASD_650_Camera_Full_HD_webcam_200901010001-02.analog-stereo`) | igual |
| Volume brutos das saídas | HDMI 42598 (65 %), fifine 26214 (40 %), interno 38011 (58 %) | igual |
| Volume brutos das entradas | 65536 (100 %) nas três | igual |
| Mudo | não, em todos | igual |
| Fluxos ativos (`sink-inputs`) | nenhum | nenhum |
| Controles ALSA (mic boost, AGC, loopback) | lidos com `amixer` | não alterados (somente leitura) |

Volume de saída subiu para 45, 60, 75 e 90 % só durante a sondagem e os testes, e voltou ao valor original.

Tempo com alto-falante ligado: cerca de **8 minutos** (limite de 40), em bursts de no máximo 4 s para os
estímulos de sondagem e de clipes curtos.

## 2. Portas e jacks

| Dispositivo | Achado |
|---|---|
| HDMI (VG2791R) | porta `hdmi-output-4` disponível; ELD anuncia alto-falantes FL/FR |
| Saída interna | `Line Out Front` detectada (plugada); fones não disponíveis |
| Saída da fifine | `analog-output-speaker`, disponibilidade desconhecida (saída de fone do microfone USB) |
| Fifine (entrada) | `analog-input-mic`, sem mudo, piso de ruído presente (não mudo nem desconectado) |
| Webcam (entrada) | `analog-input-mic`, sem mudo, piso de ruído alto (não mudo) |
| Microfone traseiro interno | `Rear Mic Jack` detectado (plugado): é o mesmo caminho da malha elétrica |

## 3. Sondagem em rampa (ar, sem Core)

Estímulos: varredura 200 a 4000 Hz (3 s), ruído rosa (2 s), fala de um clipe (1,65 s). Cada gravação foi
comparada com o estímulo conhecido (correlação cruzada normalizada), contra um nulo de 6 s sem reprodução.
Um par "pega" se `r_pico >= max(0,1; 3 x nulo)`.

Margem (`r_pico` − `nulo`), melhor valor sobre níveis 45 a 90 % e os três estímulos:

| Saída \ Entrada | fifine | webcam | microfone traseiro interno |
|---|---|---|---|
| HDMI | +0,011 (0 de 12) | +0,013 (0 de 12) | +0,001 (0 de 12) |
| Saída interna | +0,005 (0 de 12) | −0,003 (0 de 12) | **+0,599 (12 de 12)** |
| Saída da fifine | +0,001 (0 de 12) | +0,001 (0 de 12) | +0,000 (0 de 12) |

Fala (clipe) a 90 %:

| Par | r_pico | nulo | Pega |
|---|---|---|---|
| HDMI → fifine | 0,072 | 0,065 | não |
| HDMI → webcam | 0,022 | 0,039 | não |
| Interna → traseiro | 0,327 | 0,006 | sim (elétrico) |

Leitura: o microfone traseiro segue o nível de saída linearmente de 45 a 90 %, com latência fixa de
cerca de 0,7 s, e a correlação não se aproxima do nulo em nenhum nível. Isso é caminho elétrico na
placa, não captação de sala. Os microfones USB não captaram nenhum dos três estímulos em nenhum nível.

## 4. Core ao vivo (preferência `live_audio=true`, sem `--live-audio`)

### 4.1 Par elétrico: saída interna (90 %) → microfone traseiro interno

Esse é o único par com sinal. Não é acústico; mede o pipeline real (PipeWire, Core, worker) com o áudio
passando pela placa.

| Sensibilidade | Limiar | Positivos (acertos) | Negativos (falsos) | Sessões sem clipe | Latência mediana do início do clipe |
|---|---|---|---|---|---|
| 0,5 | 0,375 | 10 (8) | 10 (0) | 0 | 1524 ms |
| 1,0 | 0,25 | 30 (22) | 30 (0) | 0 | 1540 ms |
| 1,5 | 0,125 | 10 (8) | 10 (0) | 0 | 1684 ms |

Comparação com o laboratório virtual (`results/live-s1.0.json`, `final2`, `final`): 41/51, 44/51 e 50/51
de acerto em sensibilidade 1,0. O par real ficou em 22/30 (73 %), dentro da faixa, um pouco abaixo.

Falhas em 1,0 (8 de 30): concentradas em clipes com sala sintética (FIR), ruído SNR 20 dB e volume
extremo (alto e baixo), mais um clipe limpo de voz masculina.

### 4.2 Teto de volume para microfones reais (ar), saída HDMI em 90 %

| Microfone | Positivos (acertos) | Negativos (falsos) | Sessões sem clipe |
|---|---|---|---|
| fifine (sensibilidade 1,0) | 10 (0) | 10 (0) | 0 |
| webcam, padrão (sensibilidade 1,0) | 10 (0) | 10 (0) | 0 |

Taxa de acerto acústica: 0 de 20. Falsos disparos: 0 de 20. Não é taxa: nenhum positivo chegou ao microfone.

### 4.3 TTS (respostas faladas) na saída do par elétrico

Com `audible_feedback=true` e o TTS de laboratório (pocket-tts, voz alba) na mesma saída:

| Positivos (acertos) | Negativos (falsos) | Comandos com sucesso | Eventos de fala |
|---|---|---|---|
| 10 (8) | 10 (0) | 4 (3 de hora, 1 de abrir navegador) | `speech_started` e `speech_completed` em cada resposta |

Latência mediana: 1630 ms desde o início do clipe. Uma resposta leva cerca de 6,4 s e o `sink` volta a
livre ao terminar (`diag_tts`). Nenhum falso disparo com a resposta ativa, mas o eco foi medido só nesse
par elétrico.

Efeito colateral real: um clipe "abre o Brave" executou o comando (`Sandbox app process verified:
com.brave.Browser.desktop`). O processo não estava em execução ao final (`pgrep` vazio). Nada foi fechado.

## 5. Diagnóstico do sinal real (microfones, 90 % HDMI)

Gravação passiva em 2 canais com `pw-record` durante cada corrida (arquivos brutos em
`/tmp/gideon-wake-lab/real/*-2ch.raw`, sem áudio no repositório).

| Medida | fifine | webcam |
|---|---|---|
| RMS (dBFS) | −44,8 | −20,1 (esq.), −20,6 (dir.) |
| Pico | 0,176 | **1,000** |
| Amostras saturadas (|x| >= 0,99), 119 s | 0 | **3475 / 3351** |
| Energia abaixo de 45 Hz | 11,7 % | **86,2 %** (pico em 12,6 Hz) |
| Energia na faixa de fala (300 a 3400 Hz) | 39 % | 1,5 % |
| Correlação L/R | 1,00 (mono duplicado) | 0,976 |
| Clipes do laboratório achados (melhor r) | 0,161 (pos.) / 0,185 (neg.) | 0,184 / 0,183 |

Leitura: a webcam satura por ruído de muito baixa frequência (12,6 Hz), que ocupa 86 % da energia, antes do
filtro passa-alta de 100 Hz do worker. Com o sinal saturado, a fala tem só 1,5 % da energia. A fifine não
satura e tem espectro de fala. Nenhum dos dois captou os clipes (`r` dentro do nulo).

Conclusão: na webcam, o limite está na entrada (ganho, rumble, saturação), não no modelo de wake. Com a
fifine, a ausência de pega é de acústica (nenhum sinal do alto-falante chegou ao microfone), não do pipeline.

## 6. Defeitos encontrados

| Id | O que | Causa | Ação |
|---|---|---|---|
| L1 | Core ao vivo sempre em `restart_limit` com `wake unavailable` após a mudança do worker | `target/wake-lab-home/scripts/wake_worker.py` antigo (sem `--conditioning`) e `audio_conditioning.py` ausente | cópia do repositório para o laboratório (não versionado) |
| L2 | `stt failed` no início | `--home` errado (`/tmp/gideon-wake-lab/home` não tem `scripts/`) | usar `target/wake-lab-home` |
| L3 | `tts_failed` | `target/tts-venv` fora do bind do sandbox | usar `target/wake-lab-home/venvs/tts/bin/python` |
| L4 | Corrida de TTS "pulou" o resto da lista | a checagem de sink ocupado pulava sem esperar; a resposta dura cerca de 6 s | esperar o sink ficar livre (até 20 s) antes de cada clipe |
| P1 | Webcam satura em rumble de 12,6 Hz | hardware/ganho; o HPF de 100 Hz do worker chega depois do clipe | sem mudança de código; recomendar a fifine e um aviso de saturação na interface |
| P2 | Falha do worker invisível | o supervisor descarta o stderr do worker (`Stdio::null`), e a falha aparece só como `restart_limit` | sem mudança; recomendado: capturar a última linha de erro em `src/live.rs` com teste |

Nenhum código do repositório foi alterado. L1 a L4 estão no laboratório, e P1 e P2 ficam como
recomendação.

## 7. Recomendações

- **Entrada padrão:** a fifine (`alsa_input.usb-MV-SILICON_fifine_Microphone_20190808-00.analog-stereo`).
  Não é a webcam: rumble e saturação. Não alterei; a decisão é do proprietário.
- **Sensibilidade:** manter 1,0. No par elétrico, 1,0 teve 22/30 com 0 falsos em 30; 0,5 e 1,5 tiveram 8/10
  com 0 falsos em 10. Amostra pequena.
- **Acústica:** não medida. Para medir, colocar um alto-falante perto da fifine (ou usar fone e microfone
  do próprio conjunto), repetir `probe_ramp.py` a 60 e 90 %, e só depois medir 20 positivos e 20 negativos.

## 8. Gates

Nenhum arquivo do repositório de código foi alterado nesta rodada; por isso não rodei `cargo fmt`,
`clippy`, `cargo test` nem os testes Python. O único arquivo novo no repositório é esta documentação e
`docs/evidence/wake-real-acoustic.json`.

## 9. Arquivos

- `docs/evidence/wake-real-acoustic.json`: dados sem áudio.
- `/tmp/gideon-wake-lab/real/probe_ramp.py`, `probe-ramp.json`: sondagem em rampa.
- `/tmp/gideon-wake-lab/acoustic/results/loop-internal-s{0.5,1.0,1.5}.json`: Core no par elétrico.
- `/tmp/gideon-wake-lab/acoustic/results/loop-tts3-s1.0.json`: TTS no par elétrico.
- `/tmp/gideon-wake-lab/acoustic/results/fifine-hdmi-s1.0.json`, `webcam-hdmi-s1.0.json`: Core com microfones reais.
- `/tmp/gideon-wake-lab/real/restore.py`, `audio-state-before.json`: restauração do áudio.
- `/tmp/gideon-wake-lab/real/analyze_rec.py`, `analysis-hdmi.json`: diagnóstico dos dois canais.
- `/tmp/gideon-wake-lab/real/acoustic_run_tts.py`: runner com TTS e espera pelo sink.
