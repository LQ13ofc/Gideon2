# A14 — STT do áudio ao vivo: causa raiz, correção e prova no pacote instalado

Estado: IMPLEMENTADO E TESTADO COM FERRAMENTAS FALSAS E COM O PACOTE INSTALADO EM LABORATÓRIO (PipeWire virtual).
Rótulo: **pendente de validação humana** (sem microfone, alto-falante ou acústica reais).

## Resumo

- Sintoma (pacote 0.10.1, perfil `t`, laboratório): o wake disparava (`session_started`), mas a primeira sessão
  terminava em `stt_failed`, e todas as seguintes em `stt_unavailable`. Nenhum comando rodou.
- Causa raiz: a fila de pedidos do worker de STT tinha limite em **número de mensagens**, com quadros de 20 ms
  (50 mensagens/s). Um atraso do worker de ~0,6 s estourava o buffer, e o estouro era tratado como **falha
  permanente** (`status = failed`, worker abortado, nunca reiniciado).
- Correção: mensagens de até 160 ms no caminho ao vivo, fila limitada em **tempo de áudio** (10 s) que espera em vez
  de falhar, e supervisor que reinicia o worker com backoff (`starting` → `ready`) com motivo sem conteúdo.
- Prova: no pacote 0.10.2 instalado do zero, **todas as sessões que chegaram à captura concluída** tiveram
  `transcript_final` e um desfecho de comando (`command_success` ou `command_rejected`). Zero `stt_failed` e
  `stt_unavailable`; STT `ready` ao fim; nenhum arquivo de diagnóstico. Os positivos que faltaram ficaram antes do
  STT (ver "Resultados e limites").

## Causa raiz (medida)

1. **Taxa e tamanho das mensagens.** O caminho ao vivo entrega um pacote por quadro de 20 ms: 320 amostras, cerca
   de 50 pedidos por segundo. Cada `frame` é um JSON com 320 floats, cerca de 4,5 KB. O buffer do pipe (64 KB) guarda
   só ~14 quadros.
2. **O worker bloqueia periodicamente.** Medido com a biblioteca `moonshine-voice` 0.1.5 instalada no pacote
   (`venvs/stt`, modelo `small-streaming-en-quantized`, clipe de 2,5 s, sem warm-up e com warm-up):
   - carregamento do modelo: 0,23 a 0,25 s;
   - primeiro `add_audio`: 0,07 a 0,14 ms (sem pico de primeira inferência);
   - pausas de 108 a 300 ms a cada ~26 chamadas (~0,52 s de áudio), nas mesmas posições com e sem warm-up;
   - razão tempo-de-processamento/áudio na alimentação: 0,37 a 0,40 (o worker é mais rápido que o tempo real, mas bloqueia).
3. **Buffers em mensagens, não em tempo.** Canal de 16 mensagens (`mpsc::channel(16)`) mais ~14 quadros no pipe:
   cerca de 0,6 s de tolerância. Uma pausa maior (o worker de wake e o worker de STT dividem CPU) estourava o canal,
   e `try_send` falhava. Havia ainda um segundo limite, de 32 pedidos no Core, com a mesma falha.
4. **Estouro tratado como falha permanente.** `src/transport.rs` chamava `core.stt_failed()` e abortava a tarefa,
   e `src/core.rs` fazia o mesmo com 32 pedidos. Nada reiniciava o worker, e o status `failed` valia até o reinício
   do Core. A cada detecção depois disso: `stt_unavailable`.

Observação honesta: o laboratório não registrou o instante exato do estouro. A causa acima é a única que explica
o sintoma com os números medidos. O teste `a_backlog_longer_than_the_old_queue_limit_does_not_fail_the_session`
usa pausas de 0,8 s, acima do limite antigo de ~0,6 s.

Ao aquecer: o aquecimento de 1 s de silêncio **não foi adicionado**. As pausas se repetem em estado quente
(mesmas posições: 25, 51, 78, 104) e o primeiro `add_audio` não é lento. O aquecimento não remove o problema, e o
cold start (0,23 s de carga) fica dentro da fila.

## Correção

### `src/stt.rs` — `Pipe` (dono do worker, fila e supervisor)

- Caminho ao vivo (`coalesce = live_audio`): quadros consecutivos da mesma sessão se fundem em mensagens de até
  2560 amostras (160 ms). Um quadro isolado espera no máximo 100 ms para ganhar par. Ordem e `end_us` são preservados.
- Caminho de replay (`coalesce = false`): sem fusão e sem espera, como antes.
- Fila limitada em tempo: canal de 16 mensagens (~2,5 s de áudio ao vivo) e backlog de até 10 s
  (`MAX_BACKLOG_SAMPLES`). Um backlog transitório espera; nada é descartado. Só passar de 10 s conta como
  worker travado (`worker_backlog`).
- Supervisor: falha de worker reinicia com backoff de 0,5 s, 1 s e 2 s, no máximo 3 reinícios em 60 s. Depois disso,
  `failed` permanente, como antes.
- Motivos de falha determinísticos (`worker_import_error`, `model_missing`) não reiniciam: falhariam de novo.
- O worker agora roda com `stderr` em pipe; os últimos 2 KiB vão para `stt-last-error.txt` (0600, no diretório do
  Core), nunca no snapshot.

### `src/core.rs`

- Removido o limite de 32 pedidos que falhava o STT. A fila do Core é esvaziada a cada passo do laço; o limite
  agora é do `Pipe`.
- `stt_restarting(reason)`: encerra a sessão com `stt_failed`, revoga a transcrição, status `starting`. O `Ready` do
  novo worker leva a `ready` pelo caminho já existente.
- `stt_failed_with(reason)`: falha permanente com motivo.
- Snapshot: `stt_last_error` (opcional; vocabulário fechado: `worker_crashed`, `worker_import_error`,
  `model_missing`, `worker_unavailable`, `worker_timeout`, `worker_backlog`).

### `src/transport.rs`, `src/live.rs`

- `stt_down()` centraliza a falha: grava a cauda, aborta o worker, agenda o reinício ou falha de forma permanente.
  O `pending_replay` continua tratado como antes quando não há reinício.
- `live::write_private_file` (0600, `O_NOFOLLOW`) passou a ser compartilhado com o STT. `read_tail` ficou
  `pub(crate)`.
- `reason_for`: a classificação de hash agora casa com `artifact hash` (o worker imprime `artifact hash mismatch`).

### `scripts/stt_worker.py`

- Aceita até 2560 amostras por mensagem (era 1280). A linha JSON continua abaixo de 64 KiB.

### `scripts/wake_worker.py` (somente manifesto de teste)

- O detector de energia de teste (`test_only`) ganhou um campo de fala pela mesma regra RMS e não carrega VAD.
  Manifestos de produção não mudam (`vad` continua sendo carregado quando não é `test_only`).

### `app/bridge.py`

- `stt_last_error` é aceito no snapshot, com o vocabulário fechado.
- `liveLastErrorText` (Diagnóstico › Desenvolvedor, botão Copiar, sem mudança de QML) mostra a cauda do worker de wake
  e a do STT, com cabeçalhos. Não foi conferido na interface gráfica; só no código Python.

## Testes

Unitários (`src/stt.rs`, 7): fusão em uma mensagem de 160 ms na ordem; quadro isolado retido e depois enviado;
sessão ou controle interrompe a fusão; replay não funde; canal cheio não perde áudio; só backlog acima do limite
falha; reinícios com backoff e orçamento por janela.

Unitários (`src/core.rs`, 2): backlog nunca encerra a sessão nem perde áudio (teste reescrito; antes afirmava o
defeito); reinício passa de `starting` a `ready` e mantém o motivo.

Integração com o binário real (`tests/live_stt.rs`, 2, com gravador falso, detector de energia de teste e worker de
STT lento/que cai, `tests/fixtures/live_audio/fake_stt_worker.py`):
- `a_backlog_longer_than_the_old_queue_limit_does_not_fail_the_session`: três mensagens com pausa de 0,8 s; a sessão
  termina com `transcript_final`, sem `stt_failed`, sem `stt-last-error.txt`.
- `a_crashed_stt_worker_restarts_and_the_next_session_transcribes`: o primeiro worker cai; a sessão termina com
  `stt_failed`; o status passa por `starting`; `stt_last_error = worker_crashed`; `stt-last-error.txt` tem 0600 e
  contém "fake stt crash"; a sessão seguinte tem `transcript_final`.

Comando executado: aparece na verificação do pacote (`command_success`), não nesse teste de integração.

Gate `scripts/verify_a3.py` (replay, 67 verificações): passou. O cenário `kill_worker` foi **ajustado** de propósito:
antes exigia `failed` permanente depois de matar o worker; agora exige revogação da sessão e da transcrição, depois
`starting` → `ready` com `stt_last_error = worker_crashed`. O cenário `bad_model` continua `failed` permanente.
A verificação de arquivos aceita `stt-last-error.txt` apenas quando há falha de worker (a cauda pode ser vazia
após SIGKILL).

Demais gates, todos passando no estado final:
- `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` (todas as suítes);
- `scripts/test_wake_live.py` (5), `scripts/test_wake_worker.py` (`target/a1-venv`, 9), `scripts/test_bridge_protocol.py`
  (`target/ui-venv`, 244), `scripts/test_snapshot_contract.py` (`target/ui-venv`, 18), `scripts/test_stt_lifecycle.py`
  (`target/stt-venv`, 2).

## Ferramenta de verificação ao vivo: `scripts/verify_live_package.py`

Uso: `python3 scripts/verify_live_package.py --install-root ROOT [--profile t] [--positives 8] [--negatives 4]
[--wake-sensitivity 1.0] [--clips /tmp/gideon-wake-lab/clips]`

- Cria o perfil com `gideon-install profile create` e renderiza os manifestos com o `gideon-configure` do próprio
  pacote, se faltarem; depois inicia `current/bin/gideon-launch` (processo próprio, encerrado no fim).
- Carrega dois módulos PipeWire de laboratório (`gideon_verify_sink`, `gideon_verify_mic`). Se já existirem, recusa
  e não toca em nada. Descarrega exatamente os que carregou.
- Altera só as preferências do perfil de teste (microfone e saída de laboratório, sem sons de retorno, timeout de
  9 s). Não altera os padrões do dono, os dispositivos padrão do sistema nem volumes.
- Positivos (≥ 6): `session_started`, `transcript_final` e desfecho `command_success` ou `command_rejected` da mesma
  sessão. Negativos (≥ 3): nenhuma `session_started` (sem sessão falsa).
- Verifica que `live-last-error.txt` e `stt-last-error.txt` não existem e que o STT está `ready` ao fim.
- Usa recortes de laboratório que não estão no repositório (`/tmp/gideon-wake-lab/clips`).

## Resultados no pacote instalado

Pacote `gideon-base-0.10.2` construído por `scripts/build_package.py` a partir do código final, instalado com
`gideon-install` em `/home/lucas/GideonTesteLive2` (instalação nova, perfil `t` criado e configurado pela própria
ferramenta). Sensibilidade padrão 1.0. Execução final de 4 rodadas (ver histórico abaixo).

| Clipe | Esperado | Sessão | Transcrição final | Desfecho do comando | Resultado |
|---|---|---|---|---|---|
| pos-hey_brave-af_bella-clean | positivo | sim | sim | command_success | PASS |
| pos-hey_plain-af_bella-clean | positivo | sim | não (`no_speech`) | — | FAIL |
| pos-hey_time-af_bella-clean | positivo | sim | sim | command_success | PASS |
| pos-hey_brave-am_michael-clean | positivo | sim | sim | command_success | PASS |
| pos-hey_plain-am_michael-clean | positivo | sim | não (`no_speech`) | — | FAIL |
| pos-hey_time-am_michael-clean | positivo | sim | sim | command_success | PASS |
| pos-hey_brave-bf_emma-clean | positivo | sim | sim | command_success | PASS |
| pos-hey_plain-bf_emma-clean | positivo | sim | não (`no_speech`) | — | FAIL |
| neg-babble-10s | negativo | não | — | — | PASS |
| neg-gideon_alone-af_bella | negativo | não | — | — | PASS |
| neg-hey_giddy-af_bella | negativo | não | — | — | PASS |
| neg-hey_julian-af_bella | negativo | não | — | — | PASS |

Estado ao fim: STT `ready`, `stt_last_error` ausente, `live-last-error.txt` e `stt-last-error.txt` ausentes, módulos
de laboratório descarregados (dois módulos `gideon_lab_*` de outro processo, PID 606687, permaneceram intactos).

Sumário: 5 de 8 positivos passam; 4 de 4 negativos passam; **`passed: false`** (a verificação sai com código 1).

### Leitura dos resultados

- **O STT funcionou em todas as sessões que chegaram à captura concluída.** Em cada uma: `transcript_partial`
  várias vezes, `capture_completed`, `transcript_final`, `command_authorized` e `command_success` ou
  `command_rejected`. Nenhum `stt_failed` e nenhum `stt_unavailable` em qualquer rodada.
- **Os três positivos que faltam ficam antes do STT ou no VAD da captura.** Nos três, a sessão começa, aparecem
  parciais (o STT recebe o áudio), e a captura termina com `no_speech`: o VAD não marca fala nos 3 s seguintes à
  detecção. Esse limite é da captura (`src/capture.rs`), fora deste trabalho, e o código do VAD e da captura não
  foi alterado.
- **O wake varia de uma rodada para outra.** Em rodadas anteriores, algumas detecções de `hey_plain` e de `brave`
  na voz `bf_emma` não dispararam nenhuma sessão, e na rodada seguinte dispararam. Essa é a taxa de detecção do
  detector de palavra-chave, já documentada em `docs/A7-wake-live-test.md` (não é o STT).

### Histórico (seis execuções, rodadas de avaliação dentro do limite de cinco)

1. Primeira tentativa: nenhum negativo, porque o glob antigo (`*clean*`) não casava com `neg-*.wav`. Corrigido.
2. Segunda tentativa: recusada, porque módulos `gideon_lab_*` de outro processo já existiam (não tocados). A
   ferramenta passou a usar `gideon_verify_*`.
3. Rodada 1 (pacote 0.10.2 construído antes dos ajustes finais de Python): 5 de 8 positivos; 4 de 4 negativos.
4. Rodada 2 (mesmo pacote, repetição): 5 de 8; as falhas mudam de clipe, e `brave bf_emma` falha desta vez.
5. Rodada 3 (experimento de diagnóstico, perfil de teste): `--wake-sensitivity 1.5`. Os `plain` passam a disparar
   (2 de 3), mas caem em `no_speech`. Negativos continuam limpos. Não é correção: o padrão do dono não foi alterado.
6. Rodada final: pacote recém-construído a partir do código final, instalação nova, criação e configuração do perfil
   pela própria ferramenta, sensibilidade padrão. 5 de 8 positivos; 4 de 4 negativos. A tabela acima é desta rodada.

## Pendências e limites

- **Três positivos `hey_plain` terminam em `no_speech`** (captura, VAD). Para fechar, é preciso medir o VAD em
  falas curtas e decidir limiar ou tempo de silêncio. Isso muda o comportamento para o dono e precisa de avaliação
  acústica própria, fora deste escopo. Sugestão: tarefa separada.
- **Aquecimento do STT não adicionado** (mede-se sem efeito, ver acima).
- **Não validado com microfone ou alto-falante reais.** Tudo roda com PipeWire virtual e recortes de laboratório.
- **Botão Copiar**: a cauda do STT aparece no mesmo texto, mas não foi verificado na interface gráfica.
- **Caminho de replay**: sem fusão. O gate `verify_a3.py` passou. Os gates `s2final` e `e4` não foram executados
  nesta rodada (o pedido exigia só o a3).

## Arquivos

- `src/stt.rs` (novo supervisor e fila), `src/core.rs`, `src/transport.rs`, `src/live.rs`, `src/protocol.rs`.
- `scripts/stt_worker.py`, `scripts/wake_worker.py`, `scripts/verify_a3.py`, `scripts/verify_live_package.py` (novo).
- `app/bridge.py`.
- `tests/live_stt.rs` (novo), `tests/fixtures/live_audio/fake_stt_worker.py` (novo).
