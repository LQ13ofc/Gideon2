# Pesquisa: idiomas para fala (TTS) e transcrição (STT), e wake em PT/FR

Escopo fechado pelo dono (2026-10-24): **inglês (já empacotado), português (alvo pt-BR, com nota de pt-PT) e francês**.
Data da pesquisa: 2026-10-25. Pesquisa somente leitura: **nenhum modelo foi baixado, nenhum pacote foi instalado**.
Testes locais feitos apenas com arquivos já presentes no repositório e com as venvs existentes.

Legenda de evidência: **[medido local]** = executado nesta máquina; **[fonte]** = lido em página oficial (link);
**[não verificado]** = afirmação de terceiros ou de memória, sem confirmação. Tudo o que não tiver a marca [medido local] não é medido pelo projeto.

## 0. Resumo executivo

- **STT streaming em CPU para PT e FR, com licença clara e qualidade conhecida, não existe pronto neste ecossistema.** O Moonshine instalado (0.1.5) não tem PT nem FR. O único zipformer streaming francês da sherpa-onnx é de 2023 e tem queixa pública de muitos erros. Não encontrei zipformer streaming português.
- **TTS é o ponto mais viável**: Pocket TTS (mesmo motor que já roda o inglês aqui) tem pesos para português e francês. Piper pt_BR/fr_FR são alternativas leves e com licença clara por voz.
- **Wake em PT/FR não está resolvido**: o KWS zh-en aceita frases tokenizadas à mão em PT/FR (medido), mas isso só prova que o arquivo carrega, não que a frase é detectada. Sem medição sintética ou humana, PT/FR wake permanece **não suportado**.
- **Downloads**: nenhum foi feito. A lista exata está na seção 6, para aprovação do dono.

## 1. Verificações locais [medido local]

### 1.1 Moonshine instalado (stt-venv, moonshine-voice 0.1.5)
Comando de listagem (sem download): `moonshine_voice.supported_languages()` retornou
`['ar','es','de','en','ja','ko','vi','uk','zh','tl']`. **Não há pt nem fr.**
`moonshine_voice.list_tts_languages()` retornou, entre outros, `fr-fr`, `pt-br`, `pt-pt`. Isso é o caminho de TTS do pacote, separado do STT, com licença e downloads próprios (não verificados aqui).

### 1.2 Tokenização do KWS zh-en (a1-venv, sherpa-onnx 1.13.8)
- `tokens.txt` tem 262 entradas: **fonemas ARPAbet em maiúsculas** (AA0…ZH, EN CMU) e **sílabas pinyin em minúsculas** (ei, o, i, s, a, l, t, y, ou, ong…).
- Vocabulário **não tem** `oi`, `salut`, `ü` isolado, `ola`, `bonjour`, `gideon`.
- O `text2token` da sherpa **não roda** nesta venv (exige `sentencepiece` e `pypinyin`; `pypinyin` não está instalado em nenhuma venv). Não instalei nada. Tokenização feita à mão.
- Teste de carga com `KeywordSpotter` (mesmos argumentos de `scripts/wake_worker.py`, modelo int8 do repo, keywords em arquivo temporário no scratchpad):

| Frase (tokens à mão) | OOV | Resultado de carga |
|---|---|---|
| `HH EY1 G IH1 D IY0 AH0 N @HEY_GIDEON` (base EN) | nenhum | carregou |
| `ei G IH1 D IY0 AH0 N` | nenhum | carregou |
| `o i G IH1 D IY0 AH0 N` (oi) | nenhum | carregou (aproximação fonética: "oi" não é um token) |
| `s a l y t G IH1 D IY0 AH0 N` (salut) | nenhum | carregou (aproximação: "salut" tem vogal /y/ que aqui vira `y`) |
| `o l a G IH1 ...` (olá) | nenhum | carregou (aproximação) |
| `b o n j o u r G IH1 ...` (bonjour) | nenhum | carregou (aproximação) |

- **Controle negativo [medido local]**: com token inexistente (`zz qq ww`) o processo **aborta com código 255** (`Cannot find ID for token zz … Encode keywords failed`). Consequência para o projeto: **o Core precisa validar cada token contra `tokens.txt` antes de gravar `keywords.txt`**, senão derruba o worker de wake. Isso já entrou na arquitetura (seção 5).
- **Não medido**: se "ei Gideon", "o i Gideon", etc. são **detectados** em áudio. Carregar não é detectar. Para medir é preciso áudio sintético (TTS da frase e negativos) e um conjunto de avaliação, previstos em `docs/PLANO_FRASES_IDIOMAS.md`.

## 2. Pesquisa externa com fontes

### 2.1 (a) STT streaming e não-streaming

| Candidato | Idiomas (PT/FR?) | Streaming CPU | Licença | Tamanho | Qualidade reportada | Fonte |
|---|---|---|---|---|---|---|
| **Moonshine 0.1.5** (já usado para EN) | **Não**: `ar,es,de,en,ja,ko,vi,uk,zh,tl` [medido local] | sim | MIT (página do projeto; legado não-EN é não-comercial) | pequeno | n/a para PT/FR | [pypi moonshine-voice](https://pypi.org/project/moonshine-voice/) |
| **sherpa-onnx zipformer streaming FR** `shaojieli/sherpa-onnx-streaming-zipformer-fr-2023-04-14` | FR | sim (transducer) | **não verificada** (README não lido) | int8 ≈ 128 MB (encoder 126.655.903 B + decoder 1.307.157 B + joiner 259.572 B + tokens 4.819 B) | issue #3144 relata "muitos erros" no int8 | [sherpa docs](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/zipformer-transducer-models.html); [issue #3144](https://github.com/k2-fsa/sherpa-onnx/issues/3144); arquivos [HF API](https://huggingface.co/api/models/shaojieli/sherpa-onnx-streaming-zipformer-fr-2023-04-14/tree/main) |
| sherpa-onnx zipformer streaming **PT** | **não encontrado** | — | — | — | — | lista oficial (12 modelos, bn/zh/ko/en/zh-en; nenhum pt/fr além do FR acima) [fonte](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/zipformer-transducer-models.html) |
| **Vosk small PT 0.3** | PT | sim (Kaldi) | Apache 2.0 | 31 MB (valor da página; bytes não verificados) | CV test 32,60%; coraa dev 68,92% (WER, página) | [vosk models](https://alphacephei.com/vosk/models) |
| **Vosk PT grande (fb v0.1.1)** | PT | sim | **GPLv3** | 1,6 GB | CV 27,70%; coraa 54,34% | [vosk models](https://alphacephei.com/vosk/models) |
| **Vosk small FR 0.22** | FR | sim | Apache 2.0 | 41 MB | CV 23,95%; mtedx 19,30%; podcast 27,25% | [vosk models](https://alphacephei.com/vosk/models) |
| Vosk FR grande 0.22 | FR | sim | Apache 2.0 | 1,4 GB | CV 14,72%; mls 11,64% | [vosk models](https://alphacephei.com/vosk/models) |
| Vosk FR pguyot 0.3 | FR | sim | CC-BY-NC-SA 4.0 (não comercial) | 39 MB | CV 37,04% | [vosk models](https://alphacephei.com/vosk/models) |
| **Whisper** (OpenAI) / faster-whisper | multilíngue (PT, FR) | **não** (chunk com VAD) | MIT | tiny 39 M, base 74 M, small 244 M, medium 769 M, large 1550 M, turbo 809 M | sem WER por idioma coletado aqui | [openai/whisper](https://github.com/openai/whisper) (tabela e MIT); [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT, memória RAM medida pelos autores: small int8 CPU ≈ 1477 MB em benchmark deles) |
| **NVIDIA Parakeet-TDT-0.6B-v3** | **PT e FR** (lista de 25 idiomas) | sim (script NeMo chunked; **não verificado no sherpa-onnx**) | CC-BY-4.0 | 600 M parâmetros (tamanho em disco não coletado) | FLEURS: FR 5,15%, PT 4,76%; MLS FR 4,97%, PT 7,50% (greedy, sem LM; PT é europeu no treino) | [HF nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) |

Leitura honesta:
- **FR**: opção mais simples e leve é **Vosk small FR 0.22** (Apache 2.0, 41 MB, streaming). Alternativa do ecossistema sherpa (zipformer 2023) tem licença não verificada e queixa de qualidade.
- **PT**: não há candidato streaming com boa qualidade confirmada. Vosk PT small tem WER alto (CV 32,6%, coraa 68,9%). Parakeet v3 tem o melhor WER reportado, mas é 600 M e CPU/streaming não verificados aqui. Whisper é multilíngue e MIT, porém não streaming.
- **Nenhuma destas linhas foi medida neste projeto** (latência, RAM, WER). Os números acima são de páginas de terceiros.

### 2.2 (b) KWS / wake

- Modelo atual: `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20`, vocabulário ARPAbet + pinyin (medido, seção 1.2).
- **EN**: "Hey Gideon" já está certificado no projeto (ver `docs/A7-wake-live-test.md`). Não mexer.
- **PT/FR**: frases podem ser *tokenizadas* com aproximações (carregam), mas **não há modelo KWS com fonemas PT/FR** nesta família. Para entregar wake PT/FR de verdade é preciso (i) um KWS treinado em PT/FR, ou (ii) aceitar aproximações, medidas por áudio sintético e rotuladas como experimentais.
- Pesquisa de KWS PT/FR específico não foi completada nesta rodada (sem fonte verificada). **Não reivindico** disponibilidade de KWS PT/FR.

### 2.3 (c) TTS: PT-BR, FR, EN

| Candidato | Idiomas | CPU / latência | Streaming | Licença (código / pesos / dados) | Tamanho dos arquivos | Notas | Fonte |
|---|---|---|---|---|---|---|---|
| **Pocket TTS (Kyutai)** pacote `pocket-tts` 3.3.0 (**já instalado** em `target/tts-venv`) | en, **fr, pt**, de, it, es, (nl) | "~200 ms até o primeiro chunk"; ~6x tempo real em MacBook Air M4; ~2,3–2,5x tempo real em VM x86 de 4 vCPU (números do README do autor) | sim (chunks) | MIT (código, LICENSE do repo) / cc-by-4.0 (cartão do modelo) / **licença por voz varia** (página de vozes com CC0, CC-BY-4.0, CC-BY-NC-4.0) | `languages/portuguese/model.safetensors` 219.029.196 B; `tokenizer.json` 247.014 B; `tokenizer.model` 61.351 B. FR: 219.029.196 B; 246.403 B; 60.690 B | Variante `_24l` (maior, mais lenta) existe. **Qualidade PT/FR não medida.** Licença por voz precisa revisão | [README](https://huggingface.co/kyutai/pocket-tts/blob/main/README.md); [árvore de arquivos](https://huggingface.co/api/models/kyutai/pocket-tts/tree/main/languages/portuguese); [voice licenses](https://huggingface.co/kyutai/tts-voices) |
| **Piper pt_BR-faber-medium** | pt-BR | CPU leve (ONNX VITS), tempo real comum; números não medidos aqui | não nativo (chunk por frase) | MIT (repo) / dados **CC0** (cartão) | `.onnx` 63.201.294 B, sha256 `858555e3…95aa7`; `.onnx.json` 4.855 B | Voz única, medium | [árvore](https://huggingface.co/api/models/rhasspy/piper-voices/tree/main/pt/pt_BR/faber/medium); [cartão](https://huggingface.co/rhasspy/piper-voices/blob/main/pt/pt_BR/faber/medium/MODEL_CARD) |
| Piper pt_BR edresson / cadu / jeff | pt-BR | — | — | não verificado | não verificado | Existem na pasta `pt/pt_BR` | [pasta](https://huggingface.co/rhasspy/piper-voices/tree/main/pt/pt_BR) |
| **Piper fr_FR-siwis-medium** | fr-FR | igual Piper | não nativo | MIT (repo) / dados **CC-BY-4.0** (cartão) | `.onnx` 63.201.294 B, sha256 `641d1ab0…baf99`; `.onnx.json` 4.875 B | Voz única, medium, 22.050 Hz | [árvore](https://huggingface.co/api/models/rhasspy/piper-voices/tree/main/fr/fr_FR/siwis/medium); [cartão](https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD) |
| **Kokoro-82M** (hexgrad; ONNX em onnx-community) | en, **fr** (`ff_siwis`), **pt-BR** (`pf_dora`, `pm_alex`, `pm_santa`) | ONNX int8 92 MB; CPU não medido aqui | não nativo | Apache-2.0 (cartão) / licença do repo ONNX não verificada | `model_quantized.onnx` 92.361.116 B (sha256 `fbae9257…a1478`); `model.onnx` fp32 325.532.232 B (sha256 `8fbea51e…a34cb`); vozes em `voices/` não coletadas | Só 1 voz FR e 3 PT; qualidade PT não avaliada | [VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md); [árvore ONNX](https://huggingface.co/api/models/onnx-community/Kokoro-82M-v1.0-ONNX/tree/main/onnx) |
| **MMS-TTS** (Meta) `facebook/mms-tts-por` | PT | CPU (VITS) | não nativo | **CC-BY-NC-4.0 (não comercial)** | não coletado | Descartado para produto comercial; registrado por completude | [HF mms-tts-por](https://huggingface.co/facebook/mms-tts-por) |
| Moonshine TTS (pacote 0.1.5) | fr-fr, pt-br, pt-pt (listado localmente) | — | — | não verificado (catálogo baixa de CDN) | não verificado | Não consultado para não baixar nada | [pypi](https://pypi.org/project/moonshine-voice/) |

## 3. Recomendação (tabela)

| Função | Idioma | Motor e modelo recomendado | Tamanho | Licença | Qualidade esperada | Riscos |
|---|---|---|---|---|---|---|
| STT | EN | Moonshine small streaming EN quantized (já empacotado) | n/a | MIT (página do projeto) | medida pelo projeto | nenhum novo |
| STT | FR | **Vosk small FR 0.22** (candidato a medir) | 41 MB | Apache 2.0 | CV WER 23,95% (página Vosk, não medido aqui) | qualidade só razoável; medir com conjunto sintético + negativos |
| STT | PT (pt-BR) | **sem recomendação firme**: Vosk PT small 0.3 (Apache, 31 MB, WER alto) ou Parakeet v3 (CC-BY-4.0, 600 M, melhor WER reportado, carga pesada) | 31 MB ou ~600 M+ | Apache 2.0 / CC-BY-4.0 | incerta | Parakeet não validado em CPU/streaming aqui; Vosk PT ruim |
| TTS | EN | Pocket TTS EN + Alba (já empacotado) | — | MIT / CC-BY-4.0 (pesos) | medida pelo projeto | — |
| TTS | PT (pt-BR) | **Pocket TTS `languages/portuguese`** (mesmo motor) ou Piper faber medium (licença mais simples) | 219 MB + tokenizadores (Pocket); 63 MB (Piper) | Pocket: cc-by-4.0 pesos + licença por voz; Piper: MIT + CC0 | não medida | licença por voz; qualidade não medida; Pocket usa PyTorch (dependência pesada, já presente no tts-venv) |
| TTS | FR | **Pocket TTS `languages/french`** ou Piper siwis medium (CC-BY-4.0 dados) | 219 MB (Pocket); 63 MB (Piper) | Piper: MIT + CC-BY-4.0 | não medida | mesmo que PT |
| Wake | EN | "Hey Gideon" (já certificado) | — | licença do modelo zh-en KWS não reconferida nesta rodada | medida pelo projeto | — |
| Wake | PT / FR | **não suportado** por enquanto | — | — | não medido | sem KWS PT/FR; aproximações carregam, mas não foram medidas |

## 4. Lista exata de downloads para aprovação (NADA baixado)

Aprovação necessária: o dono precisa dizer **sim** item a item (ou em bloco). Sem aprovação, nada é baixado. Todo download será verificado por sha256 antes de uso.

| # | Item | URL (resolve) | Tamanho (bytes) | sha256 publicado | Licença |
|---|---|---|---|---|---|
| D1 | Pocket TTS PT pesos | https://huggingface.co/kyutai/pocket-tts/resolve/main/languages/portuguese/model.safetensors | 219.029.196 | **não obtido** (LFS mascarado na API) | cc-by-4.0 (cartão) + licença por voz |
| D2 | Pocket TTS PT tokenizer.json | https://huggingface.co/kyutai/pocket-tts/resolve/main/languages/portuguese/tokenizer.json | 247.014 | não publicado (git) | idem |
| D3 | Pocket TTS PT tokenizer.model | https://huggingface.co/kyutai/pocket-tts/resolve/main/languages/portuguese/tokenizer.model | 61.351 | **não obtido** | idem |
| D4 | Pocket TTS FR pesos | https://huggingface.co/kyutai/pocket-tts/resolve/main/languages/french/model.safetensors | 219.029.196 | **não obtido** | idem |
| D5 | Pocket TTS FR tokenizer.json | https://huggingface.co/kyutai/pocket-tts/resolve/main/languages/french/tokenizer.json | 246.403 | não publicado | idem |
| D6 | Pocket TTS FR tokenizer.model | https://huggingface.co/kyutai/pocket-tts/resolve/main/languages/french/tokenizer.model | 60.690 | **não obtido** | idem |
| D7 | Piper pt_BR faber medium (alternativa leve) | https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx | 63.201.294 | 858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7 | MIT (motor/repo) + dados CC0 |
| D8 | Piper pt_BR faber medium JSON | …/pt_BR-faber-medium.onnx.json | 4.855 | não publicado | idem |
| D9 | Piper fr_FR siwis medium (alternativa leve) | https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx | 63.201.294 | 641d1ab097da2b81128c076810edb052b385decc8be3381814802a64a73baf99 | MIT + dados CC-BY-4.0 |
| D10 | Piper fr_FR siwis JSON | …/fr_FR-siwis-medium.onnx.json | 4.875 | não publicado | idem |
| D11 | Vosk FR small 0.22 (STT) | https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip (padrão do site; confirmar) | ~41 MB (página) | não publicado | Apache 2.0 |
| D12 | Vosk PT small 0.3 (STT, qualidade baixa) | https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip (padrão do site; confirmar) | ~31 MB (página) | não publicado | Apache 2.0 |
| D13 | Kokoro int8 (opcional, TTS alta qualidade) | https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/onnx/model_quantized.onnx | 92.361.116 | fbae9257e1e05ffc727e951ef9b9c98418e6d79f1c9b6b13bd59f5c9028a1478 | Apache-2.0 (cartão; repo ONNX não verificado) |
| D14 | Sherpa FR zipformer 2023 int8 (opcional, STT FR) | …/shaojieli/sherpa-onnx-streaming-zipformer-fr-2023-04-14/resolve/main/{encoder…int8.onnx, decoder…int8.onnx, joiner…int8.onnx, tokens.txt} | 126.655.903 + 1.307.157 + 259.572 + 4.819 | encoder 47a94a7fdc8dff63d708be4ea0535747640224467f91e238311f1ddbdd09327e; decoder e72b2b9ed36355bd0dd43433f7dd258e7226ab54c9ef42b28c73ebb785805623; joiner fc2f3bb851a15a532c6f2422d53eecd1ca949f12b0897e07a852021c30481711 | **licença não verificada: não baixar antes de ler o README** |
| D15 | Parakeet v3 (STT PT/FR, pesado; decisão pendente) | https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 | não coletado | não coletado | CC-BY-4.0 |

Não entram na lista: MMS-TTS PT (CC-BY-NC), Vosk PT grande e Vosk FR pguyot (GPL / NC), Whisper (não solicitado para download nesta rodada; depende de decisão de streaming).

## 5. Consequências para a arquitetura (implementada em Phase 2)

- Catálogo com estado por (motor, idioma): `bundled`, `available_not_installed`, `unsupported`.
- Só `bundled` é selecionável. PT e FR ficam `available_not_installed` (TTS e STT) e `unsupported` (wake).
- O Core valida cada token do wake contra `tokens.txt` antes de escrever `keywords.txt` (sherpa aborta com 255 caso contrário). Isso não entra em produção para PT/FR porque o wake PT/FR fica não suportado.
- Troca de idioma: grava o ledger com CAS, marca `restart_required` por motor e exige reinício do Core para aplicar (sem troca quente de worker).

## 6. Limitações e afirmações não verificadas

- Nenhum modelo PT/FR foi baixado: latência, RAM, qualidade e WER **não medidos** neste projeto.
- Licenças por voz do Pocket TTS e do Kokoro precisam de revisão antes de qualquer uso comercial.
- Vosk: tamanhos são da página (não bytes); sha256 não publicado.
- Pocket TTS: sha256 dos pesos está mascarado na API pública; obter no cabeçalho LFS do download antes de aprovar.
- O zipformer FR 2023 não tem licença confirmada.
- `text2token` do sherpa não rodou (falta pypinyin); tokenização das frases PT/FR foi feita à mão.
- Parakeet v3 em streaming via sherpa-onnx: não verificado.
- Moonshine TTS (fr-fr, pt-br): listado localmente, sem catálogo de voz consultado (evitado para não baixar nada).

## 7. Fontes

- [Moonshine (pypi)](https://pypi.org/project/moonshine-voice/) e listagem local `supported_languages()` / `list_tts_languages()` (stt-venv).
- [sherpa-onnx zipformer transducer models](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/zipformer-transducer-models.html)
- [sherpa-onnx issue #3144 (FR)](https://github.com/k2-fsa/sherpa-onnx/issues/3144)
- [Vosk models](https://alphacephei.com/vosk/models)
- [openai/whisper (MIT, tabela)](https://github.com/openai/whisper)
- [SYSTRAN/faster-whisper (MIT)](https://github.com/SYSTRAN/faster-whisper)
- [NVIDIA parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- [Kyutai pocket-tts README](https://huggingface.co/kyutai/pocket-tts/blob/main/README.md), [árvore languages/](https://huggingface.co/api/models/kyutai/pocket-tts/tree/main/languages), [vozes](https://huggingface.co/kyutai/tts-voices)
- [Piper voices (rhasspy)](https://huggingface.co/rhasspy/piper-voices), cartões e árvores citados na tabela 2.3
- [Kokoro-82M VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md), [onnx-community ONNX](https://huggingface.co/api/models/onnx-community/Kokoro-82M-v1.0-ONNX/tree/main/onnx)
- [MMS-TTS por (CC-BY-NC)](https://huggingface.co/facebook/mms-tts-por)
- Local: `target/a1-assets/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/` (tokens.txt, en.phone, keywords.txt); `target/stt-venv`; `target/tts-venv`; sondas em scratchpad (`kws_probe2.py`).
