# WP-7c: wake PT/FR por transcrição (medido; abaixo do chão)

Estado: **NÃO FEITO (abaixo do chão)**. O wake por transcrição foi implementado, medido no laboratório offline,
com ruído real (A9) e no laboratório PipeWire. Nenhum dos três cumpre o critério do dono (≥80% de acertos com
0 falso disparo nos negativos do laboratório e no ruído). O catálogo mantém `unsupported` para PT e FR, com o
número medido. Nada foi commitado. O Core não seleciona este motor (ver seção 6).

## 1. Critério e resultado em uma tabela

Chão (definido antes das medições): ≥ 0,80 dos 14 positivos limpos do laboratório e 0 falso disparo em todos os
negativos e em todo o ruído. `scripts/wake_pt_fr_regression.py` implementa o chão (`FLOOR = 0.80`).

| Medição | Acertos | Falsos | Resultado |
|---|---|---|---|
| Laboratório, fluxo limpo (14 positivos, 18 negativos) | **11/14 (79%)** | 0 | abaixo do chão (79% < 80%) |
| Laboratório, misturas com ruído real (3 microfones x SNR 5, 10, 20 dB) | 54% médio (6 a 9 de 14) | **1** (webcam, 5 dB) | falha: 1 falso |
| Laboratório, ruído puro (180 s por microfone) | n/a | 0 | ok |
| Laboratório PipeWire (sink e mic virtuais, toca e grava, worker ao vivo) | **6/14 (43%)** | 0 de 18 | abaixo do chão |
| Held-out (13 positivos, 10 negativos, frases novas), fluxo limpo | 11/13 (85%) | 0 | acima do chão no limpo (n pequeno) |
| Held-out, misturas (3 microfones x 3 SNR) | 51% médio (4 a 10 de 13) | 0 | sem falso; acerto baixo |

Leitura honesta: o motor acerta cerca de metade dos casos com ruído e no caminho de áudio real, e o único
número que passa o chão (held-out limpo, 11/13) tem amostra pequena. O número de laboratório (11/14) foi o
melhor de uma varredura de um parâmetro (pré-rolagem, seção 3), então está otimista. O held-out não foi usado
para escolher nada, e dá 0 falso em todas as condições.

## 2. O que foi implementado

- `scripts/wake_transcript.py` (novo): motor `TranscriptEngine` com a mesma interface do `WakeEngine`
  (`accept`, `speech`, `last_end`). Dois estágios, ambos locais:
  1. porta: silero VAD v5 (o mesmo modelo do pacote, `target/a2-assets`), limiar 0,5, silêncio mínimo 0,3 s;
  2. decodificação: Parakeet-TDT v3 int8 (`target/stt-pt-fr-assets`, o mesmo do STT PT/FR) em cada segmento
     fechado: o segmento inteiro, e as janelas de 1,6 s e 2,4 s do início. Cada janela tem pré-rolagem de 0,6 s
     (ver seção 3) e preenchimento de silêncio.
  Regra do nome (`name_word`): palavra forte com até 2 de distância (Levenshtein, após dobrar acentos e
  j/c/k→g, v/p→b, t→d) e pelo menos 4 letras, por exemplo "Gidon", "Gedon", "Gédéon", "Jidon", "Bidon". Palavra
  fraca, com até 3 de distância, só logo depois de saudação ("olá", "oi", "ei", "bonjour", "salut", "hey", "hé").
  Sem saudação, "Deu" e "Dom" nunca disparam. Risco conhecido: "bidon" (palavra comum em francês) casa como
  nome forte, e "Olá, judeu" casa pela regra da saudação. No held-out ("Bidon de lait vide...") nenhum disparo
  ocorreu, mas a regra não impede isso em outras frases.
- `scripts/wake_worker.py`: `make_engine` escolhe `TranscriptEngine` quando o manifesto tem `engine` começando
  com `transcript-`. O motor de palavra-chave (KWS) não mudou. O VAD do manifesto não é criado no caminho novo
  (o motor tem o próprio), e a conversão de condicionamento não se aplica a ele.
- `scripts/wake_pt_fr_regression.py` (novo): regressão com conjuntos fixados por sha256 (`pins`), chão e
  código de saída (`check`): 0 = chão atingido e zero falso; 1 = chão não atingido ou falso; 2 = clipes
  alterados ou ausentes. Mesmo modelo de fluxo contínuo de `scripts/wake_live_regression.py` (lead 1,0 s,
  clipe, cauda 1,5 s, intervalo 0,8 s), cooldown de 2 s do `src/wake.rs`.
- `scripts/measure_pt_fr.py`: subcomandos `heldout` (sintetiza 23 frases novas com os perfis Pocket
  PT/FR) e `lab-wake` (laboratório PipeWire com o worker ao vivo).
- `scripts/test_wake_transcript.py` (novo, 10 testes, sem modelos): regra do nome, contrato de quadros,
  validação de manifesto, despacho do worker.
- `src/languages_catalog.json`: PT e FR continuam `unsupported`; motivo e qualidade com o número medido,
  evidência `docs/WP7c.md`.
- Não tocados (fora da lista): `src/core.rs`, `src/protocol.rs`, `src/transport.rs`, `app/bridge.py`,
  `app/Main.qml`, `src/wake.rs`, `src/stt.rs` (não precisou de mudança).

## 3. Como o motor chegou aqui (medições de exploração, em sessão de rascunho)

Todas com o Parakeet direto sobre os 32 clipes do laboratório (fora do repositório):

| Tentativa | Acertos (de 14) | Observação |
|---|---|---|
| Decodificação do clipe inteiro, regra do nome | 8 | ponto de partida: as variantes "Gidon", "Gedon", "Bidon" são o que sai |
| Janelas de cabeça (1,2 a 3,2 s) e pad 0,1/0,5 s, união | 8 | sem ganho sobre o clipe inteiro |
| `modified_beam_search` (4 caminhos), mesmas janelas | 8 | sem ganho |
| Ensemble de velocidade 0,9/1,0/1,1 | 8 | sem ganho |
| Pré-rolagem antes do início do VAD: 0 s, 0,2 s, 0,4 s, 0,6 s, 0,8 s | 6, 10, 9, **11**, 7 | a fala ganha a consoante inicial que o VAD corta ("Deu", "idon", "didon" viraram "Gideon"); o ganho oscila de 7 a 11 entre valores próximos |

Os 6 positivos que faltam no limpo não têm token de nome em nenhuma decodificação ("Olá Gideon." sai vazio,
"Gideon, pare a música" sai "Pare a música", "Dis donc" e "Bis donc" no francês). Não há regra de nome que
cubra isso sem aceitar "Deu" ou "Bis" sozinhos, que são palavras comuns. Por isso o teto deste STT, com regra
segura, é cerca de 11 de 14. A escolha da pré-rolagem (0,6 s) foi feita no laboratório; o held-out não a
alterou.

## 4. Comandos executados e resultados

Todos na raiz `/home/lucas/Documentos/Gideon/base`. `target/a1-venv` (sherpa-onnx 1.13.8, numpy 2.3.3).

| Comando | Resultado |
|---|---|
| `target/a1-venv/bin/python -I -B scripts/measure_pt_fr.py heldout` | 23 WAVs em `target/wp7c-heldout/{pt,fr}/{positive,negative}/` (13 positivos, 10 negativos) |
| `target/a1-venv/bin/python -I -B scripts/wake_pt_fr_regression.py pins lab` | 14 positivos, 18 negativos; `docs/evidence/wake-pt-fr-pins.json` |
| `target/a1-venv/bin/python -I -B scripts/wake_pt_fr_regression.py pins heldout` | 13 positivos, 10 negativos; `docs/evidence/wake-pt-fr-heldout-pins.json` |
| `target/a1-venv/bin/python -I -B scripts/wake_pt_fr_regression.py check lab --noise-seconds 180` | **rc 1** (chão não atingido). clean 11/14, 0 falso; misturas 6 a 9 de 14 com 1 falso (webcam 5 dB); ruído puro 0 falso em 180 s por microfone; 230 s de parede. `docs/evidence/wake-pt-fr-lab-regression.json` |
| `target/a1-venv/bin/python -I -B scripts/wake_pt_fr_regression.py check heldout --skip-noise` | **rc 0**. clean 11/13 (84,6%), 0 falso; misturas 4 a 10 de 13, 0 falso; 171 s. `docs/evidence/wake-pt-fr-heldout-regression.json` |
| `target/a1-venv/bin/python -B scripts/measure_pt_fr.py lab-wake --set lab` | laboratório PipeWire: 6/14 positivos, 0/18 negativos, 0 detecções fora dos clipes; `lab_modules_left` 0. `docs/evidence/wake-pt-fr-lab-live.json` |
| `target/a1-venv/bin/python -B scripts/test_wake_transcript.py` | 10 OK |
| `target/a1-venv/bin/python -B scripts/test_wake_worker.py` | 9 OK |
| `target/a1-venv/bin/python -B scripts/test_wake_live.py` | 5 OK |
| `target/a1-venv/bin/python -B scripts/test_wake_live_regression.py` | 9 OK |
| `cargo test --offline --lib languages` | 8 passed (após ajustar o texto do catálogo ao limite de 120/200 bytes) |

Não rodados: `cargo fmt`/`cargo clippy` (nenhum arquivo Rust foi alterado, só `src/languages_catalog.json`),
`cargo test` completo, `build_package.py` (o pacote não inclui o motor novo, ver seção 6).

Custo de CPU (medido na regressão lab): 230 s de parede para cerca de 2 236 s de áudio (aprox. 0,10 do tempo
real, 2 threads, incluindo recarga de modelos por condição). Latência: a decisão sai quando o segmento fecha
(silêncio de 0,3 s) mais a decodificação, cerca de 0,3 a 0,6 s por janela. A medição de RAM não foi feita.

## 5. Laboratório PipeWire (medição real do caminho de áudio)

`measure_pt_fr.py lab-wake` carregou só `gideon_wp7_sink` e `gideon_wp7_mic`, tocou os 32 clipes no sink com
`pw-play` (intervalo de 3 s), gravou o mic virtual com `pw-record` (16 kHz mono s16, 165 s), descarregou os dois
módulos (`lab_modules_left` 0), e alimentou o `wake_worker.py --live` com o manifesto do motor, quadro a quadro.
Volumes e dispositivos padrão não foram tocados. Resultado: 6 de 14 positivos, 0 de 18 negativos.

A queda em relação ao offline (11/14 no fluxo limpo) não foi explicada. Hipóteses não medidas: nível de
captura do mic virtual, reamostragem, e o atraso de início de `pw-play`. O arquivo gravado foi apagado após a
leitura, então o nível não pode ser conferido agora. Fica como pendência de medição.

## 6. Mudanças no Core necessárias para ligar o motor (NÃO feitas; só depois de cumprir o chão)

1. `src/transport.rs` e `src/live.rs` (lançamento do wake): para pt-BR e fr, escrever o manifesto do motor
   com `engine` = `transcript-parakeet-tdt-0.6b-v3-int8/silero-v5/sherpa-onnx-1.13.8`, `supported_phrases`
   (1 a 8 entradas), `active_phrase` com exatamente uma frase ativa (o motor recusa mais de uma),
   `model_root`, `encoder`, `decoder`, `joiner`, `tokens` e `hashes` desses quatro arquivos (mesmos do manifesto
   STT de `src/languages.rs::render_nemo_stt`), e `vad` = `{engine: "silero-vad-v5.0/sherpa-onnx-1.13.8", path,
   sha256}` do modelo silero empacotado. Lançar `scripts/wake_worker.py <manifesto> --live --start-us N`.
   Sem `--conditioning` (padrão `off`). O argumento `--keywords-threshold` é aceito mas não se aplica.
2. `src/phrases.rs`: a verificação de palavras-chave (`--check`, geração de `keywords.txt`) não serve ao motor
   de transcrição; a validação precisa ramificar por motor. O `scripts/wp7_kws_pt_fr.txt` deixa de ser usado para
   PT/FR.
3. `src/wake.rs`: sem mudança necessária. O motor produz descritor com o nome do motor, `end_us` igual ao fim do
   quadro que fechou o segmento e `start_us < end_us`, uma detecção por pacote, e o Rust já valida isso.
4. `scripts/build_package.py` (fora da lista do WP-7c): incluir `scripts/wake_transcript.py` na lista de scripts
   do pacote e no fechamento (`package_closure_check.py`); confirmar que o silero v5 vai no pacote.
5. `src/languages.rs` e `src/languages_catalog.json`: o estado do wake PT/FR só passa a `bundled` depois de o
   chão ser cumprido e registrado com a evidência nova. O texto do catálogo já reflete o estado atual.
6. Mensagem de "aguardando" em `app/bridge.py` e `app/pages/CfgIdiomas.qml` (fora da lista do WP-7c): o wake PT/FR
   continua indisponível até a decisão.

## 7. O que não foi feito e por quê

- O chão de 80% com 0 falso não foi atingido (79% no laboratório limpo, 1 falso em ruído, 43% no PipeWire).
  Não há regra de nome segura que leve a 12 de 14 com este STT (seção 3).
- Variedade de vozes: só há uma voz por idioma no pacote (rafael para PT, estelle para FR). Variações de
  velocidade foram testadas na exploração (sem ganho) e não entraram na regressão. Não há voz humana medida.
- Keyword spotting por transdutor (pontuação de forçamento sobre o encoder do Parakeet) não foi implementado.
  É o caminho técnico mais promissor para o nome, mas é uma pesquisa à parte: exige acesso aos estados internos
  do encoder (o Python do sherpa-onnx não expõe) e calibração de limiar com fala real.
- `GAP_AUDIT.md` não foi alterado (fora da lista). Texto sugerido para a linha VOZ-05 (wake): "WP-7c PARCIAL:
  wake por transcrição medido, 11/14 limpo e 6/14 PipeWire, 1 falso no ruído; abaixo do chão; docs/WP7c.md".

## 8. Decisões para o dono

1. Escolher o chão: manter 80% e 0 falso (o motor atual não cumpre), ou aceitar um orçamento de falsos
   explícito (por exemplo, até 1 falso a cada 30 min de ruído) com um chão menor.
2. Autorizar o keyword spotting sobre o Parakeet (pesquisa, sem download novo) ou aceitar que PT/FR fique sem wake
   até haver um modelo de palavra-chave PT/FR (não há no projeto).
3. Fornecer gravações de voz humana do dono (com consentimento) para medir o motor com fala real; o TTS não
   representa a voz do dono.
4. Decidir as licenças de `rafael` e `estelle` (ainda não verificadas, pendência do WP-7).
