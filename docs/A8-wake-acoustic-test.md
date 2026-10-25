# A8 — teste acústico do wake ao vivo (hardware real)

Estado: **NO_ACOUSTIC_PICKUP**. Nenhum par (alto-falante, microfone) testado captou o som do alto-falante
de forma mensurável nos níveis permitidos. Por isso não há taxa de acerto nem de falso disparo medida com
som acústico real. Dados sem áudio: `docs/evidence/wake-live-acoustic.json`.

Escopo: alto-falantes e microfones reais do proprietário, Core real, ativação do modo ao vivo pela
preferência do app (ledger `live_audio=true`, consentimento confirmado, `core_restart`), sem a flag
`--live-audio`. O Core ouviu o microfone real e o áudio de teste saiu pelo alto-falante real.

## Estado de áudio do proprietário (antes e depois)

- Registrado em `/tmp/gideon-wake-lab/acoustic/audio-defaults-before.txt` e `audio-restore.json`.
- Padrão de saída: HDMI `alsa_output.pci-0000_03_00.1.hdmi-stereo-extra4` (65%, raw 42598).
- Padrão de entrada: webcam `alsa_input.usb-ASD_650_Camera_Full_HD_webcam_200901010001-02.analog-stereo`.
- Volumes de saída alterados só durante o teste (25%, depois 45%) e restaurados com os valores brutos:
  HDMI 42598, fifine saída 26214, áudio interno 38011. Lidos de volta: iguais. Mudo: "não" nas três
  saídas, antes e depois.
- Padrões de saída e entrada não foram alterados. Nenhum fluxo do proprietário tocava durante o teste
  (`pactl list short sink-inputs` vazio antes de cada reprodução).
- Volume de reprodução: 25% primeiro; subiu para 45% (teto) porque 25% não mostrou captação. Nada acima de 45%.
- Tempo de teste acústico: cerca de 12 minutos no total, dentro do limite de 25 minutos.

## Pares testados (sondagem, `probe.py` e `probe_noise.py`)

Medida: diferença em dB entre a potência de 1 kHz durante o tom e o ruído ambiente da mesma gravação
(positivo = algo captado). Ambiente medido com nada tocando, 3 s por fonte. Variação típica entre
medições: cerca de ±5 dB, então valores abaixo disso não significam nada.

Tom de 1 kHz (1 s), 25% de volume de saída:

| Saída \ Entrada | fifine mic | webcam ASD | entrada interna |
|---|---|---|---|
| HDMI (VG2791R) | +1,1 | +2,6 | +3,4 |
| Áudio interno | +4,9 | −5,2 | +53,8 (elétrico) |
| Saída da fifine | +3,3 | −17,1 | +7,5 |

Tom de 1 kHz, 45% (teto):

| Saída \ Entrada | fifine mic | webcam ASD | entrada interna |
|---|---|---|---|
| HDMI (VG2791R) | −3,7 | −4,4 | +10,8 |
| Áudio interno | −5,0 | −14,6 | +71,0 (elétrico) |
| Saída da fifine | +3,1 | −24,8 | +10,1 |

Ruído branco (1 s), 45%, pico de RMS em janelas de 50 ms sobre o ambiente:

| Saída \ Entrada | fifine mic | webcam ASD | entrada interna |
|---|---|---|---|
| HDMI | +1,9 | +0,9 | +0,2 |
| Áudio interno | +2,7 | −1,4 | +10,7 (elétrico) |
| Saída da fifine | +4,8 | −0,2 | +0,3 |

Leitura:
- O +53,8 e +71,0 dB de "áudio interno → entrada interna" aparecem com o ambiente no piso digital. É caminho
  elétrico entre a saída e a entrada analógica da placa, não captação acústica. Não conta como teste.
  Não usar a entrada interna como microfone sem verificar isso.
- Nenhum par acústico passou de +5 dB, e o único com valor positivo (saída da fifine → fifine mic) é o
  próprio conector de saída do microfone, não um alto-falante da sala.
- A webcam tem ruído ambiente alto (RMS cerca de −10 dBFS, contra −46 dBFS do fifine). Não é um bom microfone
  de voz para este teste.
- O resultado indica que, na configuração atual da mesa, o microfone não ouve os alto-falantes com o volume
  permitido. Pode ser distância, posição, mudo físico do microfone, ou o alto-falante não ser o da saída
  escolhida. Não foi possível verificar nada disso sem o proprietário.

## Core com dispositivos reais (sem captação acústica)

Par: entrada `alsa_input.usb-MV-SILICON_fifine_Microphone_20190808-00.analog-stereo`, saída HDMI
(`alsa_output.pci-0000_03_00.1.hdmi-stereo-extra4`). Reprodução de clipes a 45%, 30 s de sala sem reprodução
por sensibilidade. Clipes do laboratório (vozes sintéticas Kokoro e Pocket), sorteados com semente fixa.

| Sensibilidade | Limiar | Positivos (acertos) | Negativos (falsos) | Sala 30 s (sessões) | Saída do reinício |
|---|---|---|---|---|---|
| 0,5 | 0,375 | 4 (0) | 4 (0) | 0 | 75 |
| 1,0 | 0,25 | 20 (0) | 20 (0) | 0 | 75 |
| 1,5 | 0,125 | 4 (0) | 4 (0) | 0 | 75 |

- Latência: não medida (nenhum disparo). Transcrições STT e comandos: nenhum, porque nenhuma sessão abriu.
- Erros ao vivo (`last_error`): nenhum. O gravador e o worker subiram com o dispositivo escolhido e
  `mic_active` ficou verdadeiro. O processo saiu com 75 após `core_restart`, como o esperado.
- Como o alto-falante não chega ao microfone (ver acima), 0 acertos aqui não diz nada sobre o wake com voz real.
  Os 0 falsos disparos mostram só que o ambiente silencioso não disparou em 30 s por sensibilidade. Não é taxa.

Amostra pequena: 28 positivos e 28 negativos no total, com 20 só na sensibilidade 1,0. Não sustenta taxa
por hora nem comparação entre sensibilidades.

## Defeito encontrado e corrigido (D6)

- Sintoma: a lista de dispositivos mostrava rótulos com sublinhados: "Est__reo anal__gico",
  "__udio interno", "_HDMI 5_". Visto com o binário real pelo `audio_devices`.
- Causa: `src/devices.rs` `sanitize_label` trocava cada byte fora de ASCII por `_` (um "é" vira dois `_`).
  O rótulo é só texto de exibição; o id (valor de preferência) mantém o charset ASCII, então a troca não
  afeta a segurança.
- Correção: letras e dígitos Unicode são mantidos; `._:@/+ -` também; cada outro caractere vira `_`
  (controles e marcas de direção bidi são trocados); o corte é de 128 bytes em fronteira de caractere.
  Testes atualizados: `labels_keep_unicode_letters_and_replace_the_rest` (unitário) e
  `pactl_json_lists_inputs_outputs_defaults_and_sanitized_labels` (`tests/audio_devices.rs`, agora "Mic _Built-in_ ação").
- Verificado com o Core de release reconstruído (`target/release/gideon-base`, 01:17): a op `audio_devices`
  devolve "fifine Microphone Estéreo analógico", "Áudio interno Estéreo analógico" e "... HDMI 5 ... VG2791R".
  Só listagem; nada foi tocado nem gravado.

## Defeitos checados e não encontrados

- Formato do gravador para dispositivo real (fifine e webcam em S24 48 kHz estéreo): `pw-record --raw --rate 16000
  --channels 1 --format s16 --target <id>` entrega quadros sem erro (sondagem e Core). A conversão de formato
  e de taxa do PipeWire é suficiente; nenhuma mudança no argv.
- Saída de fala: não foi exercitada (`audible_feedback` desligado nas execuções para evitar eco). Sem prova acústica.
- Ganho/AGC: não adicionado. Não há fala captada para medir o nível; uma correção sem dado seria palpite.

## Pendente (só o proprietário pode fazer)

1. Colocar o microfone próximo do alto-falante escolhido (ou usar fone e microfone de ouvido do dispositivo
   fifine), desligar o mudo físico do microfone, e repetir `probe.py` (tom de 1 kHz) com 25% e, se preciso, 45%.
2. Só então medir acertos e falsos disparos com voz real: 20 tentativas por classe, por sensibilidade.
3. Confirmar que a sala e o ambiente habitual não disparam com a sensibilidade escolhida.
4. Decidir se a webcam deve ser o padrão de entrada: o ruído dela é alto para escuta contínua.

## Recomendação de sensibilidade

Manter o padrão 1,0 (limiar 0,25). Não há dado acústico que justifique mudar: nenhum par captou a fala de
alto-falante, e os 0 falsos disparos em 30 s de sala valem para os três níveis, mas não são taxa. Revisar
depois do passo 2 acima.

## Gates

- `cargo fmt --check`: OK.
- `cargo clippy --all-targets -- -D warnings`: OK.
- `cargo test --test audio_devices` (7 testes) e `cargo test --lib devices` (3 testes): OK.
- `cargo test` completo: 440 testes, 0 falhas (depois da correção D6).
- `target/a1-venv/bin/python scripts/test_wake_worker.py` (6 testes): OK.
  O comando com `/usr/bin/python3` falha por falta do `sherpa_onnx`; o teste precisa do venv do a1.
- `python3 scripts/test_wake_live.py` (4 testes): OK.

## Arquivos

- `src/devices.rs`: `sanitize_label` (D6) e teste.
- `tests/audio_devices.rs`: expectativa do rótulo.
- `docs/A6-live-audio.md`: frase sobre o charset dos rótulos.
- `docs/evidence/wake-live-acoustic.json`: dados do teste (sem áudio, sem segredos).
- `docs/A8-wake-acoustic-test.md`: este relatório.
- `target/wake-lab-home` (hard links, reconstruído para o laboratório): não versionado.
- `/tmp/gideon-wake-lab/acoustic/`: scripts de sondagem, execução e restauração; resultados brutos. Sem áudio gravado.

Nada foi commitado.
