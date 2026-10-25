# Plano: frases de ativação e idiomas (fala e transcrição)

Pedido do dono (2026-10-24): depois do teste real do wake, abrir em paralelo (1) escolha de frase de ativação (uma ou mais) e (2) escolha de idiomas em que a IA FALA (TTS) e em que ela ENTENDE/TRANSCREVE (STT).
Os dois só começam quando o teste de wake ao vivo (docs/A7-wake-live-test.md) terminar, porque mexem no mesmo pipeline.

## Estado de partida (verificado nos manifests do pacote)
| Peça | Motor hoje | Idiomas |
|---|---|---|
| Wake (KWS) | sherpa-onnx zipformer **zh-en** 3M (vocabulário aberto: aceita lista de frases em `keywords.txt`) | inglês e chinês |
| STT | Moonshine Small Streaming **EN** quantizado | só inglês |
| TTS | Pocket TTS **EN** + voz Alba | só inglês, 1 voz |
| Frase de wake na UI | 2 certificadas: "Hey Gideon" (dev) e "Okay Gideon" (requer prova de conceito, bloqueada) | — |

Regras do projeto que continuam: nunca prometer "Hey Gideon" ou qualquer frase como comprovada sem evidência; frase nova = **experimental** até medir; nada de download de modelo sem autorização do dono; UI em português; sem fingir texto arbitrário treinado (Notion S2 B2).

## Frente 1 — Frases de ativação (agente W-FRASES)
Objetivo: o usuário escolhe uma ou mais frases; cada uma com qualificação honesta.
1. **Catálogo de frases** no pack: id, texto exibido, transcrição de tokens para o KWS, idioma, qualificação (`dev_qualified`, `poc_required`, `experimental`, `custom`), limiar sugerido, evidência (arquivo de medição).
2. **Várias frases ativas ao mesmo tempo** (lista limitada, ex.: até 5) em vez de uma só; o Core gera o `keywords.txt` do worker a partir da lista e reinicia o worker com troca segura (rollback se falhar).
3. **Frase personalizada** (campo de texto, validação estrita: letras/espaços/apóstrofo, 2–4 palavras, ≥ 6 fonemas/tokens, sem frases genéricas como "hey"/"ok" sozinhas): tokenização pelo vocabulário do modelo; **bloqueia** se algum token não existir; entra como `custom/experimental` com aviso fixo "não testada: pode falhar ou disparar à toa" e **teste guiado automático**: gera áudio TTS da frase e de negativas, mede acerto/falso disparo no próprio pacote antes de ativar (medição sintética, rótulo "sintético").
4. UI: Configurações › Voz e Wake: lista de frases com interruptor por frase, selos de qualificação, botão "Adicionar frase", "Testar frase" (resultado da medição), restaurar padrão; sensibilidade por frase (limiar) com padrão global.
5. Core: ledger de preferências `wake_phrases: [{id, active, sensitivity?}]` (+ frases custom em arquivo próprio com hash), snapshot, ops estritas, auditoria sem conteúdo sensível; testes de replay/medição; gates A1/A4/A5 e os de UI continuam verdes.
6. Segurança: frase custom é dado do usuário, nunca vai ao LLM nem ao Hub; limites de tamanho; nada de execução.

## Frente 2 — Idiomas (agente W-IDIOMAS) — escopo fechado: EN, PT, FR
Objetivo: escolher (a) em que idiomas a IA **fala** e (b) em que idiomas ela **transcreve**, de forma honesta com o que existe.
1. **Pesquisa (somente leitura, com fontes)**: modelos abertos viáveis em CPU local, com licença, tamanho, qualidade e suporte de streaming, para STT (família Moonshine, Whisper/faster-whisper, sherpa-onnx streaming zipformer multilíngue, Parakeet, etc.) e TTS (Piper, Kokoro, Pocket e outros) em **inglês, português e francês** (decisão do dono, 2026-10-24: estes são os três idiomas que devem ser compatíveis; português = pt-BR como alvo principal, verificar também pt-PT). Entregar tabela com recomendação e custos.
2. **Arquitetura de idiomas** (independe de baixar modelos): `LanguageCatalog` no pack: idiomas por motor (stt/tts/wake), estado (`bundled`, `available_not_installed`, `unsupported`), hash/tamanho/licença, avaliação medida; preferências `stt_languages: [..]` (lista, 1..N, com "detectar automaticamente" só se o motor suportar), `tts_language` + voz; troca segura com reinício do worker e rollback; o Core recusa idioma não instalado; snapshot e UI refletem.
3. **UI**: Configurações › Idiomas (nova sub-aba) com duas seções: "A IA fala em…" e "A IA entende em…"; cada idioma mostra estado (instalado / disponível para instalar / não suportado), tamanho, licença, qualidade medida e selo "validação humana pendente" quando só medido por áudio sintético. Idiomas não instalados aparecem desativados com o motivo. Idioma da interface continua separado (hoje só português).
4. **Instalação de idiomas**: pelo Hub/pack verificado por hash (mesmo fluxo de plugins), **sem baixar nada sem autorização explícita do dono** — o agente prepara a lista exata (URL, tamanho, hash, licença) e o dono aprova antes de qualquer download.
5. Só entra como "suportado" o que passar numa avaliação medida (WER em um conjunto sintético por idioma gerado pelo TTS correspondente + conjunto negativo) registrada em `docs/evidence/`; o restante fica `experimental` ou `não suportado`.
6. Testes: manifests de idioma, preferências inválidas, troca com rollback, UI; gates existentes verdes.

## Organização (ordem e dependências)
1. (em andamento) Teste real do wake ao vivo com áudio gerado — docs/A7-wake-live-test.md.
2. Tornar o áudio ao vivo uma opção do app (preferência, não flag) e fechar defeitos do teste real.
3. **Em paralelo**: W-FRASES (frente 1) e W-IDIOMAS (frente 2, fase de pesquisa + arquitetura + UI; downloads só após aprovação).
4. Reunião de integração: conciliar o ledger de preferências (um único esquema de versão), a UI de Voz e Wake com Idiomas, rodar a matriz de gates uma vez e publicar.
5. Validação humana (microfone/caixas reais, voz de verdade, idiomas): checklist em docs/HUMAN_VALIDATION.md.

## Decisões que dependem do dono
- Aprovar downloads de modelos de STT/TTS de outros idiomas (lista exata virá do agente de pesquisa).
- ~~Quais idiomas~~ DECIDIDO: inglês, português e francês. Falta confirmar se português = pt-BR (alvo assumido) ou também pt-PT.
- Se frases personalizadas podem ser ativadas sem medição prévia (recomendado: não).

## Escopo de idiomas decidido (2026-10-24)
- Compatíveis: **inglês (já empacotado), português e francês**. Outros idiomas ficam fora de escopo.
- Cada um precisa de três coisas: wake (frase "Hey Gideon" e equivalentes naquele idioma, testada), STT e TTS. O KWS atual é zh-en: para português e francês a frase será tokenizada pelo vocabulário disponível ou exigirá outro modelo de KWS — o agente deve medir e reportar, sem prometer.
- A pesquisa de modelos cobre só EN/PT/FR (STT streaming em CPU e TTS), com a lista exata de downloads para aprovação do dono.
