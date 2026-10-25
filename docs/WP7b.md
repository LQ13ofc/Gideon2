# WP-7b: PT/FR no Core, pacote, tolerância do nome, captura pós-wake e troca quente

Estado: **PARCIAL**. Feito e medido: seleção de PT/FR no Core, modelos empacotados com hash, troca de idioma sem
reinício (CFG-07), captura pós-"Hey Gideon", tolerância das grafias do nome nos comandos, e ferramenta ao vivo
rodada em EN, PT e FR. Não feito: wake PT/FR (medido, abaixo da meta). Nada foi commitado.

## 1. Decisões do dono aplicadas

| Decisão | Aplicação | Resultado |
|---|---|---|
| (1) Export ONNX do sherpa-onnx do Parakeet v3 aceito | `target/stt-pt-fr-assets` (int8, revisão `2bda32ec…`) é o artefato do STT PT/FR | aceito; hashes em `docs/evidence/wp7-stt-pt-fr-manifest.json` |
| (2) Licenças de rafael e estelle | registradas na licença do catálogo (`src/languages_catalog.json`, PT e FR) e aqui | **ainda NÃO VERIFICADAS** (texto no catálogo diz "NÃO VERIFICADA") |
| (3) "Hey Gideon" sozinho termina como transcrição rejeitada | `src/capture.rs` `speech_before_wake` + `src/core.rs` | medido: `command_rejected` nas 5 vezes em que o wake disparou com fala só do nome (ver seção 4) |
| (4) Wake PT/FR: frases fonéticas primeiro; se <80%, transcrição | medido nas duas rotas (seção 3) | **<80% nas duas: transcrição NÃO implementada (ver seção 6)** |

## 2. Status por item

| Item | Estado | Evidência |
|---|---|---|
| Seleção PT/FR no Core (`stt_languages`, `tts_language`) | FEITO | catálogo: `pt-BR` e `fr` em `stt` e `tts` com estado `bundled`; `tests/preferences.rs` (aceitar fr, recusar voz inválida, recusar reversão para idioma fora do catálogo); `cargo test` |
| Modelos PT/FR no pacote, com hash | FEITO | `scripts/build_package.py` copia `target/stt-pt-fr-assets` (4 arquivos), `target/tts-pt-assets` e `target/tts-fr-assets` (3 binários + config reescrito com `@ROOT@`), com verificação de hash contra os manifestos; `gideon-install` verificou 31053 entradas (`docs/evidence/wp7b-verify-*.txt`, `gideon-verify: OK`) |
| Fala PT/FR no Core | FEITO (worker direto) | o Core copia os binários para o estado com hash verificado (`src/languages.rs` `install_tts`); o worker instalado sintetiza PT (26 blocos PCM) e FR (37 blocos) a partir do manifesto gerado (seção 5) |
| Transcrição PT/FR no Core | FEITO | `src/transport.rs` `engines_for`: idioma não inglês usa Parakeet (`venvs/a1`, arquivos lidos no pacote, hash do worker) |
| Tolerância do nome nos comandos (Gedon, Lagdon, Gidon, Gidéon) | FEITO | `src/commands.rs` `unify_wake_name` + teste `wake_name_spellings_from_stt_are_accepted_only_in_the_name_slot` (positivos e negativos: "Gideonish", "Dom", "Okay Gidon", "open Gidon") |
| Captura após o wake: grace window (hey_plain) | FEITO; meta de 7/8 cumprida em 1 de 2 rodadas EN | `src/capture.rs` `speech_before_wake` (janela 1,5 s; fala antes do wake conta como fala do próprio wake); teste `wake_grace_window_turns_a_bare_wake_phrase_into_a_short_capture`; seção 4 |
| CFG-07 troca quente de workers | FEITO | `src/transport.rs` (bloco `lang_task`, reinício do STT só quando muda a família de motor), `src/stt.rs` `Pipe::reconfigure`, `src/core.rs` `languages_applied`; `language_hot_swap_ready` verdadeiro em PT e FR ao vivo |
| Coordenação WP-15: `purge_runs` | FEITO | `src/core.rs` `purge_history_now` chama `self.skills.purge_runs` com 7/30/90 dias ou `None` (Never) |
| Coordenação WP-15: catálogo ativo do Hub no boot | FEITO | `src/transport.rs` (início de `serve`): se `hub::active_catalog(<pasta do --hub-catalog>)` devolver um catálogo aplicado, ele substitui o do lançador; estado danificado cai no catálogo do lançador |
| Wake PT/FR | **NÃO FEITO** | seções 3 e 6 |
| Verificação ao vivo EN, PT, FR | FEITO (rodado); PT/FR positivos 0% | seção 4 |

## 3. Wake PT/FR (medição, sem alterar o detector)

Clipes: as 32 frases de `scripts/wp7_sentences.json` sintetizadas pelo TTS (14 positivas com "Gideon", 18 negativas).

| Rota | Resultado | Evidência |
|---|---|---|
| KWS zh-en com palavras fonéticas (`gideon`, `ei gideon`, `olá gideon`, `oi gideon`, `salut gideon`, `bonjour gideon`), limiares 0,25 e 0,1 | **0 de 14** positivos; 0 falsos em 18 | `docs/evidence/wp7b-kws-variants.json` |
| Controle do próprio harness com clipes EN (`hey_plain`, `hey_brave`) | `HEY_GIDEON` nos dois | verificado na sessão (`measure_pt_fr.kws_hits`) |
| Transcrição (Parakeet, frase inteira) + correspondência aproximada de "gideon" (distância <= 1, 2, 3) | **4, 7, 8 de 14**; falsos 0, 0, 1 | `docs/evidence/wp7b-transcript-wake.json`, dados em `docs/evidence/wp7b-stt-hypotheses.json` |

Erros do Parakeet no nome (dados): "Gideon" saiu como Deu, Dedon, Gedon, Lagdon, Gidon, Gédéon, Jidon, Bidon, ou
sumiu ("Pare a música agora"). A grafia "Deu" não pode virar gatilho (falso positivo em frases comuns).

Conclusão: nenhuma rota atinge 80% sem falsos. O detector por transcrição não foi implementado (seção 6).

## 4. Captura pós-wake e verificação ao vivo (lab PipeWire, pacote instalado)

Comando (pacote construído e instalado em `/home/lucas/GideonWp7`, perfis de teste; o perfil do dono não foi tocado):

    python3 scripts/build_package.py target/pkg-wp7b --version 0.1.0-wp7b
    python3 -I -B target/pkg-wp7b/gideon-base-0.1.0-wp7b/bin/gideon-install --install-root /home/lucas/GideonWp7 install <pkg>
    python3 scripts/verify_live_package.py --install-root /home/lucas/GideonWp7 --profile wp7en  --positives 8 --negatives 4 --language en    --clips /tmp/gideon-wake-lab/clips
    python3 scripts/verify_live_package.py --install-root /home/lucas/GideonWp7 --profile wp7en2 --positives 8 --negatives 4 --language en    --clips /tmp/gideon-wake-lab/clips
    python3 scripts/verify_live_package.py --install-root /home/lucas/GideonWp7 --profile wp7pt  --positives 7 --negatives 4 --language pt-BR --clips target/wp7-lab-clips/pt
    python3 scripts/verify_live_package.py --install-root /home/lucas/GideonWp7 --profile wp7fr  --positives 7 --negatives 3 --language fr    --clips target/wp7-lab-clips/fr

| Rodada | Positivos | Negativos (falsos) | Troca quente | Observação |
|---|---|---|---|---|
| EN, 1ª | **6 de 8** (plain: 2 de 3 com sessão, ambas `command_rejected`) | 4 de 4 (0 falsos) | n/a | 2 falhas sem `session_started`: `hey_plain am_michael` e `hey_brave bf_emma`, ou seja, o wake (KWS) não disparou; a captura não chegou a começar |
| EN, 2ª (mesmo pacote) | **8 de 8** (plain: 3 de 3 `command_rejected`) | 4 de 4 (0 falsos) | n/a | variação de wake entre rodadas (mesmo áudio) |
| PT (`pt-BR`, Parakeet + rafael) | **0 de 7** (todos sem sessão: o KWS EN não dispara com "Olá Gideon") | 4 de 4 (0 falsos) | **OK** (`language_hot_swap_ready` true) | wake PT não é detectado (seção 3) |
| FR (`fr`, Parakeet + estelle) | **0 de 7** (sem sessão) | 3 de 3 (0 falsos) | **OK** | idem |

Positivos EN no total das duas rodadas: 14 de 16 (87,5%); meta de 7 de 8 atingida na 2ª rodada, não na 1ª. A
falha da 1ª é de disparo do wake, não de fim de captura (nenhuma das duas tinha sessão). Não rodei mais rodadas por
falta de orçamento. Antes desta mudança, o relatório do dono era 3 de 8 `no_speech` em `hey_plain`; nesta versão
todos os `hey_plain` que dispararam terminaram em `command_rejected`.

Os PT/FR zerados são do detector (KWS zh-en), não do pacote: os clipes falham antes da captura. Os números de
transcrição PT/FR reais estão em `docs/WP7.md` (WER 10,1% PT e 11,7% FR sintéticos).

Fala direta do pacote instalado (sem Core), com o manifesto gerado pelo Core no perfil de teste:

    printf '{"session_id":5,"text":"Olá Gideon, posso ajudar você?"}\n' | venvs/tts/bin/python -I -B scripts/tts_worker.py <perfil>/core/languages/tts-pt-manifest.json

Resultado: PT 26 blocos PCM e `done`; FR com `Bonjour Gideon, puis-je vous aider ?` 37 blocos e `done`
(`target/wp7b-runs/tts-pt-direct.jsonl`, `tts-fr-direct.jsonl`).

Limpeza: os dois módulos PipeWire de laboratório foram descarregados em cada execução (`lab_modules_left` 0; `pactl`
com 0 módulos `gideon_verify*` ao final). Dispositivos padrão e volumes não foram alterados (padrão de saída e
entrada conferidos depois da última rodada).

## 5. Como a troca de idioma funciona (CFG-07)

- `language_preference` grava a escolha (CAS) e a Core marca `restart_required` até o motor aplicado mudar.
- O laço do transporte compara a escolha salva com a aplicada, fora de sessão de voz. Monta os motores em thread
  de bloqueio (`engines_for`): Parakeet (`venvs/a1`) para qualquer idioma que não seja inglês; para PT/FR, copia a
  voz para `<estado>/core/languages/tts-<pack>/` com hash e renderiza `config.yaml` para esse caminho.
- Reinicia o STT só quando a família muda (Moonshine ↔ Parakeet); PT↔FR não reinicia. A fala seguinte usa a voz nova.
- Pacote sem os arquivos ou manifesto inválido: STT falha com `language_pack_unavailable` (quando é Parakeet) e a
  fala falha com `tts_pack_unavailable`. Nunca cai para outra voz.
- Não medido ao vivo: troca de PT/FR de volta para EN (o caminho existe e foi testado só por compilação e testes de
  unidade).

## 6. Não feito, e por quê

1. **Wake por transcrição para PT/FR (decisão 4)**: não implementado. A meta de 80% não foi atingida por nenhuma rota
   (KWS 0 de 14; transcrição 7 de 14 com 0 falsos). Implementar um detector que ouve o tempo todo e acerta metade
   dos casos sintéticos não atende o critério; é uma decisão sua. Caminho técnico se você quiser: `scripts/wake_worker.py`
   (VAD + Parakeet por trecho, casamento aproximado) com nova medição de falsos disparos.
2. **Fora da minha lista de arquivos (reportado, não alterado)**:
   - `app/bridge.py`: texto de `restart_required` (agora a troca é quente) e `PACK_KEYS` não aceita `base_pack.pack_sha256`
     (WP-15). Efeito: `scripts/test_snapshot_contract.py` falha nos 19 testes com `invalid IPC snapshot`. A causa é o campo
     do WP-15 (presente no snapshot), não esta mudança; mesmo assim o gate está vermelho.
   - `scripts/test_snapshot_contract.py:1092-1093` (`test_languages_block_validates_and_uninstalled_languages_are_refused`)
     espera `language_not_installed` para fr e pt-BR. Agora fr e pt-BR são aceitos; o teste precisa esperar `ok` e
     continuar recusando, por exemplo, voz inválida. Não alterei.
   - `app/pages/CfgIdiomas.qml` e `app/bridge.py`: rótulos "Aguardando aprovação do download" para PT/FR não se aplicam
     mais (os idiomas estão `bundled`).
   - `scripts/package_tools/gideon-configure` não foi tocado: a fala PT/FR é instalada pelo Core no primeiro uso, então o
     instalador não precisou mudar.
   - `src/pack.rs` não foi tocado (nenhuma edição necessária para PT/FR).
3. Lista de comandos em PT/FR: a gramática continua a mesma (inclui "que horas são", "abra o brave", "aumentar
   volume"); a tolerância ao nome vale em qualquer idioma. Não houve medição de comandos PT/FR ao vivo.
4. Licenças de `rafael` e `estelle`: **não verificadas** (decisão 2 pede só registrar; registrado).
5. Tamanho: o pacote tem 3,0 GB (STT PT/FR 670 MB; TTS PT e FR cerca de 225 MB cada, copiados para o estado no primeiro uso).
6. Falha antiga que não foi reproduzida nesta rodada: a 1ª rodada EN perdeu 2 wakes (KWS), como antes (A7/A14 documentam
   variância do wake). Não investiguei a causa do KWS.

## 7. Comandos e resultados

Todos na raiz `/home/lucas/Documentos/Gideon/base`.

| Comando | Resultado |
|---|---|
| `cargo fmt --check` | OK (rustfmt aplicado a `src/capture.rs`, `src/commands.rs`, `src/languages.rs`, `src/transport.rs`) |
| `cargo clippy --offline --all-targets -- -D warnings` | OK (um aviso de `redundant_closure` corrigido em `src/transport.rs`) |
| `cargo test --offline --lib` | 207 passed, 0 failed (inclui 4 testes novos: grace, nome, pacote de voz, seleção de motor) |
| `cargo test --offline` (todas as suítes) | todas ok, 0 falhas (inclui `tests/preferences.rs`, 6 passed, reescrito para fr aceito) |
| `cargo build --release --offline` | OK (2 vezes; a 2ª após ajuste de texto do catálogo) |
| `python3 scripts/build_package.py target/pkg-wp7b --version 0.1.0-wp7b` | OK, 3,0 GB; primeira tentativa recusada pelo closure check porque o catálogo citava scripts de provisionamento (corrigido: os caminhos viraram `docs/WP7.md`) |
| `gideon-install ... install` | OK (`ok: true`) |
| `verify_live_package.py` (4 rodadas acima) | EN 6/8 e 8/8; PT 0/7; FR 0/7; negativos 4/4, 4/4, 4/4, 3/3; `lab_modules_left` 0 |
| `target/a1-venv` KWS variantes e harness | `docs/evidence/wp7b-kws-variants.json` |
| `cargo test`, tts_worker direto (PT e FR) | OK |
| `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_snapshot_contract.py` | **19 falhas** (causas na seção 6.2; não corrigidas: fora da minha lista) |

Não rodados: `test_bridge_protocol.py` (depende de `app/bridge.py`, que não alterei), `verify_b4_package.py`,
`verify_e4_integration.py` (matriz completa).

## 8. Arquivos alterados (e por quê)

- `src/capture.rs`: `WAKE_GRACE_US`, `Capture::speech_before_wake`, teste novo.
- `src/commands.rs`: `WAKE_NAME_VARIANTS`, `unify_wake_name`, teste novo.
- `src/core.rs`: `last_speech_us`, uso da janela no wake; `purge_history_now` chama `skills.purge_runs` (WP-15);
  `languages_applied`.
- `src/languages.rs`: `tts_pack`, `needs_nemo_stt`, `render_nemo_stt`, `install_tts` (cópia com hash), testes.
- `src/languages_catalog.json`: PT e FR `bundled`; fontes apontam para `docs/WP7.md`.
- `src/stt.rs`: `Pipe::reconfigure`.
- `src/transport.rs`: `engines_for`, `stt_engine_name`, boot com idioma salvo, bloco `lang_task`, fala com
  voz aplicada; catálogo ativo do Hub no boot (WP-15).
- `tests/preferences.rs`: fr aceito; rollback para idioma fora do catálogo.
- `scripts/build_package.py`: pacotes PT/FR (assets, templates, `@ROOT@`).
- `scripts/verify_live_package.py`: `--language` (en, pt-BR, fr) com troca quente e checagens.
- `docs/GAP_AUDIT.md`: linhas CFG-07 (FEITO) e VOZ-05 (PARCIAL, com o que falta).
- `docs/evidence/wp7b-*`: KWS, transcrição, hipóteses, saídas das verificações.

## 9. Desvios de processo (declarados)

- Usei um comando de shell com heredoc (`python3 - <<EOF`) por engano, sem efeito (só um `print`). A regra do pacote
  proíbe; não houve escrita de arquivo por heredoc. Registro para revisão.
- Os scripts de medição do wake (KWS variantes e transcrição) ficaram no diretório de rascunho da sessão; o resultado
  está em `docs/evidence/`.
- Os 4 clipes PT/FR de laboratório foram gerados com o TTS a partir de `target/wp7-measure/` (cópias em
  `target/wp7-lab-clips/`), não em `/tmp/gideon-wake-lab/clips`.
