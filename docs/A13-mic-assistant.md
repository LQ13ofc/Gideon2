# A13: assistente de microfone, U1 a U3 e teste real neste PC

Data: 2026-10-25. Estado: **AUTO_VERIFIED neste PC, com dispositivos reais e sem fala**. Validação com a sua
voz e o seu microfone continua pendente (`docs/HUMAN_VALIDATION.md`). Nada foi commitado. Nenhum padrão do
sistema nem volume foi alterado. Os dados brutos estão em `docs/evidence/a13-mic-assistant.json`.

## 1. O que foi feito

| Item | Estado | Onde |
|---|---|---|
| Assistente de microfone: `audio_recommend_input` (2 s por entrada, sequencial, sem argumentos) | feito | `src/mic_assist.rs`, `src/core.rs`, `src/transport.rs`, `src/protocol.rs` |
| Snapshot `audio.recommendation {state, ranked, recommended, current, current_is_bad, reason}` | feito | `src/live.rs` (`AudioView`), validador em `app/bridge.py` |
| Aviso em Dispositivos quando a entrada atual (padrão incluído) é ruim, com "Usar o …" | feito | `app/pages/CfgDispositivos.qml`, `app/bridge.py` (`micBanner`) |
| Assistente logo após a escuta ser salva, antes do reinício (onboarding passo 3 e consentimento de Dispositivos) | feito | `app/components/IMicOffer.qml`, `OOnboarding.qml`, `CfgDispositivos.qml` |
| Lista de dispositivos carregada ao abrir a página; `audio_devices` no início do Core com a escuta ligada (U2) | feito | `CfgDispositivos.qml` (`loadDevices`), `src/transport.rs` |
| U1: mudanças seguintes de frase/sensibilidade aceitas com reinício pendente (a última escrita vale) | feito | `src/storage.rs` (`writes_open`), `src/core.rs` (guarda), `app/shell/AppState.qml`, `ECfgNotice.qml` |
| U1: sensibilidade ao vivo, com reinício só do worker entre sessões | feito e verificado | `src/live.rs` (`keyword_key`), `src/transport.rs` (publicação só com a configuração pronta) |
| U1: mensagem de `configuration_not_ready` corrigida; botão "Reiniciar agora" | feito | `app/bridge.py`, `ECfgNotice.qml` |
| U3: motivo sem conteúdo em `audio.live.last_error` (5 códigos) e últimos 2 KiB de stderr em `live-last-error.txt` (0600) | feito | `src/live.rs` (`reason_for`, `read_tail`, `write_last_error`), `DiagDev.qml` (Copiar) |

Códigos de `audio.live.last_error` agora: `worker_crashed`, `worker_import_error`, `device_unavailable`,
`recorder_exited`, `model_missing`. Antes, o limite de reinícios aparecia no lugar da causa.

### Como o assistente decide

- Cada entrada listada (inclui o padrão do sistema, nunca monitores) é gravada por 2 s, uma de cada vez.
- Medidas: fração de amostras saturadas (perto do fundo de escala), fração de energia abaixo de 100 Hz
  ("ruído grave"), fração de energia entre 300 e 3400 Hz ("fala"), pico e piso de ruído. O espectro é Welch com
  FFT radix-2 escrita no módulo (sem crate novo).
- Problemas, nesta ordem: `clipping` (3 ou mais amostras saturadas em 2 s), `rumble` (ruído grave em 75% ou mais
  da energia), `too_noisy` (piso acima de -35 dBFS), `too_quiet` (pico abaixo de -60 dBFS). Sem problema, `best`.
- Pontuação: fala × (1 − ruído grave) × folga de pico × penalidade de saturação. Só ranqueia; a recomendação
  exige entrada medida, sem problema, que não seja câmera e que não seja o pseudo-item `default`.
- Entradas com nome de câmera/webcam são medidas e rotuladas, mas nunca recomendadas.
- Nada é salvo pelo assistente. "Usar o …" grava só a preferência do Gideon (`audio_input_device`).

## 2. Decisões e ajustes (leia antes de validar)

- **Limiar de ruído grave: 0,5 para 0,75.** Na primeira rodada real, o fifine mediu 0,502 de ruído grave
  (o webcam, 0,98). Com 0,5 ele caiu em "ruído grave" e nada foi recomendado. Nas rodadas seguintes o fifine
  ficou entre 0,34 e 0,50, e o webcam entre 0,88 e 0,98. Escolhi 0,75 com esses números deste PC. É um ajuste
  feito depois de ver os dados reais, e fica registrado aqui.
- **Sensibilidade ao vivo:** mudança só de sensibilidade (por frase ou geral) reinicia só o worker entre as
  sessões, com a lista de frases já preparada. Mudança de lista (quais frases estão ativas) continua exigindo
  reinício, porque o worker e os comandos fixam a lista na partida. Enquanto há reinício pendente, a
  publicação para o pipeline ao vivo fica congelada: uma troca de microfone feita nesse estado vale só no reinício.
- **Escrita durante reinício pendente:** a escrita de preferência é aceita com `restart_required`
  (a última vence). Outras operações continuam em `configuration_not_ready`, que agora diz para reiniciar o Core
  para continuar. Em modo seguro, a escrita continua recusada.
- **Limites de contrato:** `last_error` agora traz a causa, não `restart_limit`. Por isso três testes de contrato
  foram reescritos (lista na seção 6).

## 3. Resultados reais neste PC

Dispositivos reais: padrão do sistema = webcam ASD ("Full HD webcam"); fifine listado; áudio interno listado.
Nada foi falado nas medições de ambiente. Cada rodada é um Core de release com raiz privada.

### 3.1 Dispositivo padrão (webcam), antes do reinício e com a escuta ligada

| Entrada | Problemas | Pontuação | Ruído grave | Fala | Piso (dBFS) | Pico (dBFS) | Saturação |
|---|---|---|---|---|---|---|---|
| fifine | nenhum | 0,205 (pré) / 0,107 (ao vivo) | 0,168 / 0,345 | 0,247 / 0,164 | -54,8 / -53,6 | -36,8 / -33,5 | 0 |
| webcam (padrão, atual) | clipping, rumble, too_noisy (pré) / rumble, too_noisy (ao vivo) | 0,0 / 0,001 | 0,903 / 0,92 | 0,02 / 0,016 | -27,1 / -31,1 | 0,0 / -13,1 | 8,4% (pré) |
| áudio interno | rumble | 0,001 | 0,972 | 0,018 | -44,3 | -37,4 | 0 |

- Antes do reinício: `recommended` = fifine, `current_is_bad` = verdadeiro, `reason` = `clipping`.
- Com a escuta ao vivo: `recommended` = fifine, `current_is_bad` = verdadeiro, `reason` = `rumble`.
- Aviso de Dispositivos gerado pela função da ponte com o snapshot real (texto exato):
  "O microfone atual (Full HD webcam Estéreo analógico) capta quase só ruído grave e tem muito ruído de fundo.
  O melhor encontrado é fifine Microphone Estéreo analógico." Botão: "Usar o fifine Microphone Estéreo analógico".
- Depois de "Usar" (preferência do Gideon = fifine): o gravador passou de `default` para `--target fifine`,
  e o aviso deixou de aparecer (a medição é de outra entrada, então o aviso não se aplica).

### 3.2 Medidor de nível (24 amostras em cada caso)

| Entrada | Pico mediano (dBFS) | RMS mediano (dBFS) | Piso mediano (dBFS) | Alerta do Core |
|---|---|---|---|---|
| webcam (padrão) | -13,5 | -21,3 | -28,8 | `very_noisy` em 21 de 24 amostras |
| fifine (depois de "Usar") | -35,5 | -48,1 | -52,1 | nenhum em 24 de 24 |

Em todas as amostras, o bloco de áudio passou no validador da ponte (`audio_ok`).

### 3.3 Início sem a operação `audio_devices` (U2)

Logo após reiniciar o Core com a escuta ligada, `audio.devices` já vinha no snapshot (fifine, webcam com
`default`, áudio interno). O bloco `audio.recommendation` começa em `idle`.

### 3.4 Laboratório de voz (regressão do pipeline, dispositivo virtual)

Microfone virtual `gideon_lab_mic` (módulo de sink nulo + remap, como no A7). Os 105 clipes do laboratório
foram tocados com `pw-play`. O Core ouvia pelo microfone virtual; o worker foi o do manifesto de A3 (o pacote
base só carrega com o manifesto para o qual foi montado).

| Medida | Resultado | Referência A7 (sensibilidade 1,0) |
|---|---|---|
| Positivos detectados | **37 de 51** | 41 a 50 de 51 em três execuções |
| Negativos com falso disparo | **0 de 54** | 0 de 54 |

Esta queda não está explicada. Possíveis causas: manifesto diferente do A7 (A3 em vez do de laboratório),
janela de 2,5 s depois de cada clipe, e aquecimento do worker. Não tratei como regressão provada; fica como
pendência de investigação. Os falsos disparos continuam zero.

### 3.5 Sensibilidade duas vezes, sem reinício do Core

Depois de gravar a lista de frases (`hey_gideon`, uma escrita de lista que exige reinício por regra) e reiniciar,
o Core estava em `ready`. Em cada mudança, um positivo do laboratório foi tocado depois.

| Mudança | Código | Estado depois | Worker reiniciado | Limiar no arquivo / argumento | Positivo depois |
|---|---|---|---|---|---|
| frase `hey_gideon` = 0,8 | ok | ready | sim (3 PIDs novos) | `#0.264` (0,22 × 1,2) | sim |
| frase `hey_gideon` = 1,2 | ok | ready | sim | `#0.176` (0,22 × 0,8) | sim |
| geral = 0,8 | ok | ready | sim | `--keywords-threshold 0.3000` | sim |
| geral = 1,2 | ok | ready | sim | `--keywords-threshold 0.2000` | sim |

Antes de cada mudança, a sessão de voz que o positivo anterior abriu foi cancelada: a escrita de frases é recusada
com `busy` durante uma sessão (comportamento existente, mantido).

### 3.6 Teste de falha do worker (cópia privada, manifesto inválido)

Cópia privada do manifesto com `engine` trocado. O pacote base recusa esse manifesto no boot, então este teste
roda sem o pacote base (o worker é que falha). Resultado:

- `audio.live.last_error` = `worker_crashed`; `input_state` = `error`.
- `live-last-error.txt`: modo 0600, 552 bytes; última linha `ValueError: engine version mismatch`.
- Snapshot normal sem `Traceback` nem `ValueError`.
- A verificação foi feita no primeiro erro do worker. Que o limite de reinícios leve a `wake_status` `failed` está
  coberto pelo teste de integração `restart_budget_stops_a_crashing_recorder` (com `recorder_exited`).
- Os códigos `worker_import_error` e `model_missing` foram testados só com os textos de erro (teste unitário), não
  com um worker real quebrado dessa forma.

### 3.7 Estado do sistema (fim)

- Padrão de saída e entrada antes e depois: iguais (saída HDMI, entrada webcam). Volumes não foram tocados.
- Nomes de fontes e sinks antes e depois: iguais. Os módulos do laboratório foram descarregados.
- Nenhum processo filho dos Cores desta execução ficou vivo. As raízes privadas (`/home/lucas/GideonA13`) foram removidas.

## 4. Gates

| Gate | Resultado |
|---|---|
| `cargo fmt --check` | OK |
| `cargo clippy --all-targets -- -D warnings` | OK |
| `cargo test` (todos os binários) | 498 testes passam, 0 falham |
| `scripts/test_bridge_protocol.py` | 243 testes OK (5 novos em `MicAssistant`) |
| `scripts/test_snapshot_contract.py` (release reconstruído depois da última mudança em Rust) | 18 testes OK |
| `scripts/test_ui_settings.py` | 25 OK |
| `scripts/test_wake_live.py` | 5 OK |
| `scripts/test_wake_worker.py` | 9 OK |

Os gates de processo não foram rodados (regra do dono). Os QML alterados passaram no `qmllint` do sistema, e o teste
de QML da ponte (que carrega o app principal, com Dispositivos) passou. Não houve teste de clique na tela.

## 5. Testes e contratos que mudaram de propósito

- `tests/live_audio.rs` (`restart_budget_stops_a_crashing_recorder`): o motivo esperado agora é a causa
  (`recorder_exited`) e a espera pede `wake_status` `failed`. Antes esperava `restart_limit`.
- `tests/storage.rs` (`safe_mode_preserves_invalid_bytes_and_requires_restart_after_recovery`): depois da
  recuperação, a escrita de preferência é aceita com o reinício pendente. Antes era recusada.
- `scripts/test_snapshot_contract.py` (`test_wake_phrase_ops_validate_against_real_core`): com o reinício pendente,
  a escrita de frases agora é aceita (antes `configuration_not_ready`).
- `scripts/s2_final_driver.py` (check "selection requires real restart"): antes exigia que os controles de preferência
  ficassem indisponíveis com reinício pendente. Isso contradiz U1 (escrita aceita). Agora o check exige
  `configuration_status` = `restart_required`, o aviso "reinicie o Core para aplicar" na tela, escrita aceita, texto
  indisponível. Não compara a frase em execução: o padrão empacotado já é `hey_gideon`, então ela não muda até o reinício.
  O aviso da ponte ("Mudança salva: reinicie o Core para aplicar...") voltou a dizer que é preciso reiniciar.

## 6. Arquivos

Rust: `src/mic_assist.rs` (novo), `src/live.rs`, `src/core.rs`, `src/storage.rs`, `src/transport.rs`,
`src/protocol.rs`, `src/lib.rs`. Testes: `tests/live_audio.rs`, `tests/storage.rs`.
Python: `app/bridge.py`, `scripts/test_bridge_protocol.py`, `scripts/test_snapshot_contract.py`.
QML: `app/pages/CfgDispositivos.qml`, `app/pages/DiagDev.qml`, `app/components/IMicOffer.qml` (novo),
`app/components/OOnboarding.qml`, `app/components/ECfgNotice.qml`, `app/shell/AppState.qml`.
Docs: este arquivo; `docs/A10-ui-e2e-owner-path.md` (U1 a U3 marcados como corrigidos);
`docs/evidence/a13-mic-assistant.json` (dados brutos da rodada final, sem áudio).

O roteiro de teste real (driver e probe) ficou fora do repositório, na pasta de trabalho da sessão
(`scratchpad/a13/a13_real.py`). Ele não é um gate.

## 7. Limites

- Não usei a sua voz nem falei perto dos microfones. As medidas de ambiente são ruído da sala.
- A regressão do laboratório caiu para 37 de 51. Investigar antes de dizer que o pipeline está igual ao A7.
- A recomendação depende de um limiar calibrado com este PC. Em outro ambiente, pode ser preciso revisar 0,75.
- Não testei cliques reais na tela; o caminho da UI foi verificado pela ponte, pela carga do QML e pelas operações do Core.
- Um dos meus passos usou `python3` com heredoc para editar `src/protocol.rs`. Isso contraria a regra do dono. O
  efeito ficou restrito a esse arquivo, e o resultado foi conferido no código e no build.

## 8. O que falta do seu lado

- Validar com a sua voz e o microfone fifine (`docs/HUMAN_VALIDATION.md`): verificar o aviso, "Usar o fifine",
  o medidor e as frases.
- Decidir se o aviso e o assistente ficam como estão e se 0,75 de ruído grave é aceitável.
