# Robustez do wake word em microfones reais

Data: 2026-10-25. Escopo: pesquisa somente leitura. Nenhum arquivo do repositorio foi alterado, exceto este documento. Nada foi commitado.

Observacao sobre caminhos: a raiz do projeto Gideon com `docs/` e `src/` esta em `/home/lucas/Documentos/Gideon/base/`. Por isso este arquivo fica em `base/docs/research/`.

## Resumo executivo

O problema descrito (98% em clipes sinteticos limpos, quase zero em microfone real) e o padrao classico de **incompatibilidade acustica e de nivel**, nao de falta de modelo. Os projetos maduros (openWakeWord, microWakeWord, Home Assistant/Wyoming) resolvem isso em quatro frentes, nesta ordem de impacto por custo:

1. Escolher o dispositivo certo e medir o nivel real que chega ao KWS (zero custo).
2. Desligar o AGC do dispositivo e normalizar o ganho de forma fixa e previsivel no pipeline (custo baixo).
3. Treinar ou calibrar o modelo com audio real do dono (ruido, reverberacao, ganho, distancia). E a alavanca de maior impacto, com custo alto.
4. Diagnosticar com instrumentacao (medidor de nivel, gravacao "o que o modelo ouve", traco de score), para nao tunar as cegas.

O que nao resolve sozinho: baixar o threshold. Isso aumenta falsos positivos sem curar a causa, e o proprio repositorio ja mostra que o threshold e a unica alavanca do engine (ver secao 1.2).

Ponto de honestidade: a evidencia publicada em `base/docs/evidence/wake-live-acoustic.json` (status `NO_ACOUSTIC_PICKUP`) diz que a taxa de acerto e a de falsos disparos em acustica real ainda **nao foram medidas**. Qualquer numero de "quanto melhora" abaixo e estimativa ou heuristica, salvo quando marcado como fonte.

---

## 1. O que o repositorio ja faz (verificado por leitura de codigo)

### 1.1 Captura e conversao

- `base/src/live.rs`, funcao `recorder_args`: a captura usa `arecord --raw --rate=16000 --channels=1 --format=s16le`, com `--device` quando nao e `default`. Logo, a conversao de taxa, a reducao de canais e a formatacao ficam na camada ALSA (plug) ou no servidor de audio (PipeWire/Pulse). O app nao faz downmix, reamostragem, HPF, ganho nem medicao de nivel. Isso e uma hipotese a verificar, nao um fato medido.
- Frames de 20 ms vao do Core para `scripts/wake_worker.py` por stdin (`FRAME_SAMPLES`).

### 1.2 Engine de keyword spotting

- `scripts/wake_worker.py`, linha de `sherpa_onnx.KeywordSpotter(...)`: `keywords_threshold=dev_threshold`, `keywords_score=1.0` fixo. Os boosts por frase podem vir do arquivo de keywords (`:boost`, aceito de 0 a 10, validado no worker). O threshold por frase (`#threshold`) tambem e aceito pelo formato.
- O comentario do worker diz que "o engine nao reporta score, entao o threshold e a unica alavanca". Logo, o `accept_threshold` de `src/wake.rs` so se aplica a deteccoes com score, que o KWS nao emite. Confirmar isso no codigo antes de qualquer tuning.
- `src/wake.rs`: `BASE_KEYWORDS_THRESHOLD = 0.25`, faixa segura `[0.1, 0.5]`, formula `BASE * (2 - sensitivity)`. O valor citado de 0.22 corresponde a sensibilidade de aproximadamente 1.12 (`0.25 * (2 - s) = 0.22`). Confirmar qual valor de fato roda na maquina do dono.
- Aquecimento: `WARM_UP_SAMPLES = 3 s` de silencio, para inicializar o stream de keywords.
- Pre-roll de 1 s e cooldown que so conta deteccoes aceitas (`src/wake.rs`).

### 1.3 VAD

- `wake_worker.py`, `VadEngine`: Silero VAD (sherpa), `threshold=0.5`, `min_speech_duration=0.1`, `min_silence_duration=0.1`, janela 512.
- Na funcao `live()`, a KWS recebe **todos** os frames, e o VAD so gera o campo `speech` na saida. Ou seja, **o VAD nao bloqueia a deteccao no worker**. A hipotese "VAD cortando o inicio da fala" nao se aplica ao worker. Ainda falta verificar se o Core usa o campo `speech` para descartar algo (nao verificado).

### 1.4 Evidencia acustica existente

`base/docs/evidence/wake-live-acoustic.json` (2026-10-25):
- Ambiente medido: fifine -46.4 dBFS, webcam ASD -10.6 dBFS, microfone interno -43.9 dBFS (RMS, sob 25% de volume do sink). Isso difere do relato do dono (webcam -23, fifine -50). Provavelmente condicoes diferentes. Repetir a medicao com o mesmo protocolo antes de comparar.
- Status `NO_ACOUSTIC_PICKUP`: nao houve acoplamento alto-falante-microfone mensuravel em nenhum par, com volume seguro. O teste nao produziu nenhum acerto real.

Conclusao: o caminho alto-falante -> microfone ainda nao foi exercitado de forma valida. Nao ha dado de taxa de acerto real nem de falsos disparos reais.

---

## 2. Tecnicas, impacto esperado, custo e viabilidade

Legenda de custo: B = baixo (uma tarde), M = medio (alguns dias), A = alto (semanas ou dados e GPU).
"Dependencia pesada" = biblioteca nativa grande ou runtime de treino no caminho de execucao do Rust/Python.

| # | Tecnica | Impacto esperado no "nao dispara" | Custo | Licenca / origem | Cabe no pipeline Rust+Python sem dependencia pesada? | Fonte |
|---|---|---|---|---|---|---|
| 1 | Escolher o dispositivo certo e confirmar qual fonte o app grava | Alto (pode ser a causa unica) | B | n/a | Sim. Ja existe `input_device`. Falta mostrar a fonte ativa na UI | repo |
| 2 | Medidor de nivel (RMS, pico, piso de ruido, clipping, DC) | Diagnostico. Sem impacto direto | B | n/a | Sim, em Rust puro, poucas linhas | heuristica |
| 3 | Desligar AGC e ganho automatico no dispositivo/servidor (alsamixer, pavucontrol, PipeWire) | Alto para webcams com AGC; evita "bombeamento" | B | n/a | Sim, e configuracao de sistema (fazer somente pelo dono) | [HA kiosk-satellite #1111](https://github.com/jxlarrea/kiosk-satellite/issues/1111); [voicute](https://www.voicute.com/articles/openwakeword-not-detecting-troubleshooting.html) |
| 4 | Ganho digital fixo calibrado (por dispositivo, com teto e limitador) antes do KWS | Alto quando o nivel e baixo ou alto demais | B | n/a | Sim, Rust puro | heuristica; openWakeWord recomenda 16 bit 16 kHz, nivel nao especificado ([README](https://github.com/dscripka/openWakeWord)) |
| 5 | Filtro passa-alta (HPF) 80 a 100 Hz, 2a ordem, para DC e rumble | Medio: tira DC de webcam barata e ruido grave | B | n/a | Sim, biquad em Rust | WebRTC APM tem HPF ([header](https://webrtc.googlesource.com/src/+/0695df1a5990ffd02cff4f7b49a865d7085f9d0b/modules/audio_processing/include/audio_processing.h)) |
| 6 | Downmix estereo com escolha de canal ou soma verificada (checar fase e canal morto) | Medio a alto se um canal estiver morto ou em oposicao de fase | B | n/a | Sim | heuristica |
| 7 | Reamostragem de qualidade (com filtro anti-alias) em vez de decimacao ingenua, a partir de 48 kHz | Medio, sobretudo com estereo S24 | B a M | depende da biblioteca | Sim, com crate de reamostragem (ex.: `rubato`, licenca a confirmar) | heuristica |
| 8 | WebRTC APM (AGC2, NS, HPF) | Alto em ruido estacionario; AGC2 ajuda, mas pode bombear | M | BSD (WebRTC). Port puro em Rust: [sonora](https://github.com/dignifiedquire/sonora) (licenca a confirmar); binding C++: [webrtc-audio-processing-config](https://docs.rs/webrtc-audio-processing-config) | Parcial: o port Rust evita C++, mas e dependencia nova grande | [sonora](https://github.com/dignifiedquire/sonora); [gstreamer webrtcdsp](https://gstreamer.freedesktop.org/documentation/webrtcdsp/webrtcdsp.html) |
| 9 | RNNoise (supressao de ruido em banda, pequena e rapida) | Medio a alto em ruido de fundo constante (ventilador, ar) | M | RNNoise (BSD). Plugin LADSPA: [noise-suppression-for-voice](https://github.com/werman/noise-suppression-for-voice) | Parcial. Crate de port puro existe, mas nao verifiquei licenca nem maturidade | [Gentoo](https://wiki.gentoo.org/wiki/PipeWire/Microphone_Noise_Suppression) |
| 10 | Speex noise suppression (opcao do openWakeWord) | Medio em ruido constante | M | speexdsp (BSD) | Nao: openWakeWord so suporta x86 e arm64 Linux, e exige libspeexdsp | [README](https://github.com/dscripka/openWakeWord) |
| 11 | Filtrar o KWS com VAD (Silero) como porta | Baixo para o recall; ajuda contra falsos com ruido sem voz. Risco de cortar o inicio da fala | B | MIT (Silero) | Ja existe o VAD no worker; usar so como metrica ou porta leve | [README openWakeWord](https://github.com/dscripka/openWakeWord) |
| 12 | Variantes de grafia/fonetica da frase (ex.: "hey gideon", "hei gideon", "ei gideon", "hey gidion") no mesmo rotulo | Alto para sotaque. Suportado pelo worker (varias linhas com um rotulo) | B | n/a | Sim, so arquivo de keywords | repo (`keywords` validado); sherpa KWS ([docs](https://k2-fsa.github.io/sherpa/onnx/kws/index.html)) |
| 13 | Calibracao por usuario: gravar a propria frase em varios ganhos e distancias, ajustar boost e threshold | Alto | M | n/a | Sim | heuristica; sherpa KWS suporta boost e threshold por frase |
| 14 | Treino/fine-tuning com audio real do dono + augmentation (ruido, RIR, ganho, SNR) | Muito alto. E a pratica padrao em openWakeWord e microWakeWord | A | openWakeWord (Apache-2.0); microWakeWord (Apache-2.0, a confirmar) | Nao no runtime. Ferramenta de treino offline, dependencia pesada, fora do caminho de execucao | [openWakeWord](https://github.com/dscripka/openWakeWord); [config de terceiros](https://github.com/Yuuzulight/Mana/pull/629) |
| 15 | Verificador de segundo estagio (verifier) por voz | Alto para falsos positivos. Custa recall fora da voz treinada | A | openWakeWord | Nao no runtime do sherpa. Precisaria de modelo proprio | [README](https://github.com/dscripka/openWakeWord) |
| 16 | Dupla limiar (shadow): rodar um segundo KWS com threshold mais baixo so para log | Diagnostico forte: mostra "quase disparou" | M | n/a | Sim, custo de CPU dobrado no teste | heuristica |
| 17 | Chunk/frame maior (multiplos de 80 ms no openWakeWord) | Baixo. Mais latencia | B | n/a | Sim | [README](https://github.com/dscripka/openWakeWord) |
| 18 | PipeWire filter-chain com rnnoise (e echo-cancel) em nivel de sistema | Medio, mas afeta todo o audio do sistema | M | depende do plugin | Nao e codigo do app. Configuracao de sistema, so por instrucao do dono | [filter-chain](https://docs.pipewire.org/page_module_filter_chain.html) |

Notas sobre a tabela:
- Itens 1 a 7 sao os primeiros a fazer. Custam pouco, nao adicionam dependencia e sao independentes do modelo.
- Itens 8 a 10 sao processamento de sinal pesado. So valem se os itens 1 a 7 nao bastarem.
- Itens 14 e 15 sao o caminho de qualidade maxima. Exigem dados do dono e um ciclo de treino.

---

## 3. Checklist de solucao de problemas: "nao dispara no microfone real"

Ordenado por probabilidade estimada para este caso (webcam como padrao, fifine ocioso em -50 dBFS). As probabilidades sao julgamento, nao medicao.

1. **Fonte errada.** O app grava a webcam ou outra fonte, nao o fifine. Confirmar com o medidor qual fonte e a ativa e se o sinal sobe quando a pessoa fala perto dela. Esta e a hipotese mais barata de testar.
2. **Nivel baixo demais.** Voz a 1 a 2 m da webcam pode chegar a -30 dBFS ou menos, com piso em -23. SNR de 5 a 10 dB ja e ruim para um KWS treinado com limpo. Meta: pico de fala entre -12 e -6 dBFS, sem clipping.
3. **AGC da webcam.** O AGC sobe o piso de ruido ao nivel de fala e puxa o ganho para baixo no meio da frase. Isso gera "bombeamento" e corta a frase-chave. Desligar o AGC e repetir o teste.
4. **Canal estereo morto ou em oposicao de fase.** Se um canal e silencio ou ruido, a soma cai cerca de 6 dB. Se estao em fase oposta, a soma pode cancelar. Medir L e R separadamente.
5. **Reamostragem de 48 kHz S24 para 16 kHz s16.** Decimacao sem filtro anti-alias gera aliasing, que o modelo nao viu no treino. Confirmar a formato real que `arecord` entrega com um tom de 1 kHz (ver secao 6).
6. **DC offset.** Webcams baratas tem offset de centenas de LSB. Aplicar HPF e checar a media das amostras.
7. **Clipping.** Um fifine perto da boca com ganho alto satura. Clipping tira a informacao espectral da frase. Contar amostras em +-32767.
8. **Distancia e reverberacao.** Sala reverberante e distancia de 2 m mudam o espectro. Modelo treinado com voz limpa e perto falha. Solucao: augmentation com RIR (secao 5).
9. **Tokenizacao da frase.** O texto "hey gideon" pode gerar tokens fora do vocabulario ou tokens raros no zh-en. O worker valida que os tokens existem em `tokens.txt`, mas nao garante que a sequencia seja facil de reconhecer. Rodar `sherpa-onnx-cli text2token` e comparar com variantes.
10. **Sotaque.** O dono fala portugues. "Gideon" com fonemas ingleses e portugueses diverge. Adicionar variantes (secao 2, item 12). Isso e um dos ajustes de maior retorno para o caso.
11. **Stream travado depois da primeira deteccao.** Relatos de Home Assistant (Assist Microphone) descrevem deteccao so na primeira ou segunda vez, ate reiniciar o add-on. Verificar se o app chama reset do stream apos cada deteccao (o exemplo do sherpa faz isso). Esta e uma hipotese de codigo a verificar, nao um fato.
12. **Threshold ou sensibilidade altos.** Com 0.22 e boost 1.2, o alvo pode ser estrito para um microfone de qualidade inferior. Testar sensibilidade mais alta antes de mudar o modelo.
13. **VAD cortando o inicio da fala.** Hipotese descartada no worker, porque a KWS recebe todos os frames (secao 1.3). Ainda checar o uso do campo `speech` no Core.
14. **Aquecimento insuficiente.** 3 s de silencio costumam bastar. Se o primeiro teste falha logo apos o inicio, testar com aquecimento maior. Baixa probabilidade.

---

## 4. Ferramentas de diagnostico para adicionar ao app

1. **Medidor de nivel ao vivo.** Mostra, por janela de 1 s e por fonte ativa: RMS e pico em dBFS, piso de ruido (percentil 10), contagem de amostras em clipping, media (DC), e razao de canais L/R. E barato e e o diagnostico de maior valor. Sem dependencia nova.
2. **"O que o modelo ouve".** Ao pedido do usuario, gravar os ultimos N segundos do sinal que entra no KWS (depois de qualquer DSP), em WAV 16 kHz mono s16, com marcacao do instante de deteccao. Permite ouvir e comparar com a fala real. Armazenar localmente e so com consentimento explicito. Respeitar as regras do projeto sobre dados pessoais.
3. **Traco de score.** O sherpa nao expoe score por deteccao (secao 1.2). Alternativas: (a) rodar um segundo spotter com threshold mais baixo (ex.: 0.10) em modo sombra e registrar as deteccoes "quase" com timestamp; (b) registrar o momento de cada deteccao com o nivel medido nos 2 s anteriores. Confirmar na API do sherpa se algum campo de probabilidade e exposto.
4. **Matriz de confusao com frases proximas.** Usar os `rejection_labels` do manifesto (o worker ja suporta) com frases parecidas ("okay gideon", "hey guidion", "hei gideao", "hey gideon" em outro tom). Medir quais disparam e com que frequencia.
5. **Taxa de falso disparo por hora.** Rodar o app em silencio e em ruido de fundo por tempo fixo (ex.: 60 min) e contar deteccoes. Picovoice recomenda medir a taxa de falsa aceitacao (FAR) fixa, como 1 por hora, e comparar a taxa de falsa rejeicao (FRR) nesse ponto ([guia](https://picovoice.ai/blog/complete-guide-to-wake-word/)).
6. **Teste de reproducao acustica.** Tocar a frase gravada pelo dono por alto-falante em volumes definidos, com o mesmo microfone. Isso reproduz o caminho real e tira a variabilidade da fala. Cuidado com o acoplamento de volume ja documentado em `wake-live-acoustic.json`.

---

## 5. Parametros recomendados (faixas iniciais)

Marcado como "fonte" quando ha referencia, e "heuristica" quando e julgamento a validar com medicao.

| Parametro | Faixa sugerida | Base |
|---|---|---|
| Pico de fala no ponto do KWS | -12 a -6 dBFS | heuristica |
| RMS de fala | -24 a -18 dBFS | heuristica |
| Piso de ruido | -55 a -45 dBFS | heuristica |
| SNR minimo para o teste | >= 15 dB | heuristica; Picovoice mede a precisao com ruido de 10 dB SNR (dado de fornecedor, [produto](https://picovoice.ai/products/voice/wake-word/)) |
| Amostras em clipping | 0 | heuristica |
| Ganho digital maximo | +20 a +30 dB, com limitador | heuristica |
| HPF | 2a ordem, 80 a 100 Hz | heuristica; WebRTC tem HPF ([header](https://webrtc.googlesource.com/src/+/0695df1a5990ffd02cff4f7b49a865d7085f9d0b/modules/audio_processing/include/audio_processing.h)) |
| Threshold do KWS | 0.15 a 0.30, com clamp [0.10, 0.50] do repo | repo; sherpa usa 0 a 1, menor = mais disparos ([docs](https://k2-fsa.github.io/sherpa/onnx/kws/index.html)) |
| Boost por frase | 1.0 a 2.0 (teto de 3 como cautela) | sherpa exemplifica 1.0 e 1.5 ([docs](https://k2-fsa.github.io/sherpa/onnx/kws/index.html)); teto e heuristica |
| Threshold por frase | opcional, ex.: 0.20 a 0.30 para frases dificeis | sherpa `#threshold` ([docs](https://k2-fsa.github.io/sherpa/onnx/kws/index.html)) |
| Aquecimento | 3 s | repo |
| Cooldown apos deteccao | 1 a 2 s | heuristica |
| Tamanho de frame | 20 ms no app; multiplos de 80 ms se o modelo exigir | repo; [openWakeWord](https://github.com/dscripka/openWakeWord) |
| VAD threshold (Silero) | 0.5 (padrao); 0.5 a 0.7 em sala ruidosa | repo; openWakeWord cita 0.5 para ambiente ruidoso, e 0.7 como sugestao de comunidade ([README](https://github.com/dscripka/openWakeWord)) |
| Patience (frames acima do limiar) | 3 frames de 80 ms | projeto de terceiro, nao recomendacao oficial (openWakeWord nao especifica) |
| Augmentation: SNR de ruido | -5 a +10 dB | config de terceiro com background SNR; [PR Yuuzulight/Mana](https://github.com/Yuuzulight/Mana/pull/629) |
| Augmentation: ganho | +10 a -40 dB | citado em um artigo de wake word, nao localizado com certeza |
| Augmentation: RIR | probabilidade 0.5 | config de terceiro, RIR do MIT ([PR Yuuzulight/Mana](https://github.com/Yuuzulight/Mana/pull/629)) |

Sobre falsos disparos por hora: nenhuma fonte oficial desta pesquisa define um alvo. Picovoice publica uma referencia de marketing (menos de 1 falso alarme em 10 horas, com sensibilidade nao informada), que nao deve ser usada como meta sem reproduzir as condicoes ([Picovoice FAQ](https://picovoice.ai/docs/faq/porcupine/)). Sugestao para o projeto: escolher a meta de FAR (ex.: 1 por hora em silencio e ruido de fundo) e buscar o threshold que atinja FRR aceitavel nessa meta, medido com o audio do proprio dono.

---

## 6. PipeWire filter-chain (rnnoise e echo-cancel), somente por leitura

Nao alterei nem consultei a configuracao do sistema. Nao executei `pw-cli ls Module` nem listei plugins. A informacao abaixo e da documentacao.

- Modulo: `libpipewire-module-filter-chain`. Opcoes principais: `node.description`, `filter.graph` (nos, links, entradas e saidas, `capture.volumes`, `playback.volumes`), `capture.props`, `playback.props`. Fonte: [docs.pipewire.org](https://docs.pipewire.org/page_module_filter_chain.html).
- O exemplo oficial mostra uma fonte virtual de supressao de ruido com o plugin LADSPA de rnnoise (`noise_suppressor_stereo`). Com `capture.props` e `playback.props` em `node.passive` e `media.class = Audio/Source`. Fonte: mesma pagina.
- Plugin de rnnoise para PipeWire: [werman/noise-suppression-for-voice](https://github.com/werman/noise-suppression-for-voice). Guias citam parametros "VAD Threshold (%)", "VAD Grace Period (ms)" e "Retroactive VAD Grace (ms)", com faixa de 85 a 95% em alguns guias. Esse dado e de guias secundarios, e a faixa precisa ser confirmada no plugin instalado. Fonte: [Gentoo wiki](https://wiki.gentoo.org/wiki/PipeWire/Microphone_Noise_Suppression).
- Echo-cancel: o ArchWiki descreve um arquivo em `/etc/pipewire/pipewire.conf.d/` usando o motor WebRTC AEC. Nao consegui ler a pagina (acesso bloqueado durante a pesquisa). O nome do arquivo de exemplo citado em fontes secundarias e `60-echo-cancel.conf`, nao confirmado. Fonte: [ArchWiki](https://wiki.archlinux.org/title/PipeWire/Examples).

Uso possivel, se o dono quiser e se o sistema oferecer os plugins:
- Um filter-chain com rnnoise como fonte virtual, apontado pelo app como `input_device`, resolveria ruido estacionario sem mudar o codigo de KWS. Custo: configuracao de sistema, que so o dono deve fazer.
- Echo-cancel e util se o alto-falante do proprio Gideon toca durante a escuta (TTS). Com TTS ativo, a deteccao pode disparar com a propria voz. Isso e um risco real e precisa de teste.
- Risco: o filter-chain muda o sinal para todo o audio do sistema, nao so para o app. Avaliar antes.

---

## 7. Lacunas e o que nao foi verificado

- **Snowboy e Mycroft Precise:** a pagina do Precise foi lida, mas o README nao traz audio, threshold ou augmentation. Os detalhes estao em um wiki de treino que nao foi lido. Snowboy nao foi pesquisado.
- **microWakeWord:** nao encontrei documentacao oficial. As referencias de augmentation vem de repositorios de terceiros ([arslansadiq87/microwakeword-training](https://github.com/arslansadiq87/microwakeword-training), [Yuuzulight/Mana](https://github.com/Yuuzulight/Mana/pull/629)).
- **Rhasspy e OVOS:** nao pesquisados. A issue do Wyoming satellite sobre USB mic foi lida apenas pelo resumo de busca ([rhasspy/wyoming-satellite #43](https://github.com/rhasspy/wyoming-satellite/issues/43)).
- **WebRTC AGC2 e NS:** os valores e a ordem de processamento vem de fontes secundarias e de headers de versoes diferentes. A ordem citada e HPF, AEC3, NS, AGC2. Confirmar na fonte atual antes de implementar.
- **sherpa-onnx KWS:** a pagina oficial foi lida. Nao encontrei referencia de "acoustic mismatch", tamanho de chunk ou numero maximo de tokens por frase. Issues de referencia: [#1371](https://github.com/k2-fsa/sherpa-onnx/issues/1371) (ajuste para a propria voz), [#920](https://github.com/k2-fsa/sherpa-onnx/issues/920) (nao lido em detalhe).
- **Porcupine:** a FAQ foi resumida por busca. Nao ha mapeamento de sensibilidade para falsos por hora.
- **Estimativas de impacto:** todos os numeros de impacto da tabela sao julgamento. Nenhum foi medido neste projeto.
- **Medicao real:** a evidencia atual nao mede acerto nem falso disparo em acustica real. Um teste com a propria voz do dono e o unico dado que resolve a duvida.

---

## 8. As 8 recomendacoes mais valiosas

1. **Medir antes de mudar.** Adicionar o medidor de nivel e mostrar a fonte ativa. Sem isso, qualquer ajuste de threshold e um tiro no escuro (secao 4, item 1).
2. **Desligar o AGC da webcam** e testar. Se o pico de fala sobe e o piso se mantem, o problema era AGC (secao 3, item 3).
3. **Normalizar o ganho de forma fixa e calibrada** por dispositivo, com teto e limitador, em vez de depender do AGC do sistema (secao 2, item 4).
4. **Corrigir o caminho estereo e de conversao:** medir L e R, escolher o canal ou a soma verificada, e reamostrar com filtro anti-alias. Hoje o `arecord` faz isso sem controle (secao 1.1).
5. **Adicionar variantes de grafia e fonetica para "hey gideon"** no mesmo rotulo, e testar com o sotaque do dono (secao 2, item 12). E barato e costuma ter grande efeito para sotaque.
6. **Gravar o proprio dono em varias distancias e niveis** e usar para calibrar boost e threshold, ou para fine-tuning com augmentation (RIR, ruido, ganho). Esta e a pratica padrao em openWakeWord e microWakeWord (secao 2, itens 13 e 14).
7. **Instrumentar a deteccao com um segundo limiar em modo sombra** e com a gravacao "o que o modelo ouve". Isso mostra os quase-disparos e separa falha de nivel de falha de modelo (secao 4, itens 2 e 3).
8. **Definir a meta de falsos por hora antes de ajustar o threshold** e medir FRR nessa meta com o audio real. Nao reduzir o threshold sem essa medicao (secao 5 e secao 4, item 5).

---

## Fontes

- openWakeWord (README): https://github.com/dscripka/openWakeWord
- openWakeWord, guia de troubleshooting de terceiros: https://www.voicute.com/articles/openwakeword-not-detecting-troubleshooting.html
- sherpa-onnx, documentacao de KWS: https://k2-fsa.github.io/sherpa/onnx/kws/index.html
- sherpa-onnx, issue sobre ajuste para a propria voz: https://github.com/k2-fsa/sherpa-onnx/issues/1371
- sherpa-onnx, issue sobre KWS silabico: https://github.com/k2-fsa/sherpa-onnx/issues/920
- Home Assistant / Wyoming satellite, USB mic: https://github.com/rhasspy/wyoming-satellite/issues/43
- Home Assistant / kiosk-satellite, AGC e distancia: https://github.com/jxlarrea/kiosk-satellite/issues/1111
- Home Assistant Community, wake word nao reconhecido: https://community.home-assistant.io/t/wake-word-not-recognized-using-assist-microphone/627432
- Home Assistant core, Assist Microphone dispara uma vez: https://github.com/home-assistant/core/issues/110351
- PipeWire, filter-chain: https://docs.pipewire.org/page_module_filter_chain.html
- PipeWire, exemplos (ArchWiki; pagina bloqueada na leitura): https://wiki.archlinux.org/title/PipeWire/Examples
- noise-suppression-for-voice (RNNoise, PipeWire): https://github.com/werman/noise-suppression-for-voice
- Gentoo wiki, supressao de ruido no PipeWire: https://wiki.gentoo.org/wiki/PipeWire/Microphone_Noise_Suppression
- WebRTC, header do APM (HPF e ordem): https://webrtc.googlesource.com/src/+/0695df1a5990ffd02cff4f7b49a865d7085f9d0b/modules/audio_processing/include/audio_processing.h
- sonora (port Rust do APM do WebRTC): https://github.com/dignifiedquire/sonora
- webrtc-audio-processing-config (crate): https://docs.rs/webrtc-audio-processing-config
- GStreamer webrtcdsp: https://gstreamer.freedesktop.org/documentation/webrtcdsp/webrtcdsp.html
- Picovoice, FAQ do Porcupine: https://picovoice.ai/docs/faq/porcupine/
- Picovoice, guia de wake word: https://picovoice.ai/blog/complete-guide-to-wake-word/
- Mycroft Precise (README): https://github.com/MycroftAI/mycroft-precise
- microWakeWord, treino (terceiro): https://github.com/arslansadiq87/microwakeword-training
- Config de augmentation de terceiro (PR): https://github.com/Yuuzulight/Mana/pull/629
- StoRIR, geracao de RIR estocastica (artigo): https://arxiv.org/pdf/2008.07231
- Evidencia local: `/home/lucas/Documentos/Gideon/base/docs/evidence/wake-live-acoustic.json`
- Codigo local: `/home/lucas/Documentos/Gideon/base/scripts/wake_worker.py`, `/home/lucas/Documentos/Gideon/base/src/wake.rs`, `/home/lucas/Documentos/Gideon/base/src/live.rs`
