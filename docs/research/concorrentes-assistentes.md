# Concorrentes e referências de assistente de voz (pesquisa de 2026-10-25)

Pesquisa somente leitura. Nenhum arquivo do repositório foi alterado, exceto este documento. Nada foi commitado.

Legenda de marcação:
- **(confirmado na fonte)**: afirmação encontrada no texto da fonte indicada.
- **(inferido)**: conclusão minha a partir de uma ou mais fontes, não afirmada literalmente.
- **(não verificado)**: não consegui acessar a fonte ou ela não respondeu à pergunta.

Data de referência: 2026-10-25. Algumas páginas foram lidas por ferramenta de extração (WebFetch), que resume o texto. Citações entre aspas são trechos devolvidos pela ferramenta, não cópia integral da página.

---

## 1. Resumo executivo

- O Nixi **não usa palavra de ativação** segundo tudo o que consegui ler. A ativação documentada é a **tecla F9**, que abre a barra de chat. Isso aparece nas notas de versão 0.2.1 (GitHub) e no post do blog "Why Nixi lives in one pill". A landing page não diz como se ativa.
- O Nixi não divulga nome de modelo de reconhecimento de fala, nem de LLM. A voz de resposta é uma **gravação pré-feita** em inglês britânico, concatenada por trechos. Não há um motor TTS gerado no sentido usual.
- O concorrente open source mais útil para o nosso problema ("o wake não dispara para o usuário") é o **Nox** (wake "Hey Nox" com openWakeWord, assistente de onboarding que calibra microfone e wake, e um atalho paralelo `Ctrl+Shift+Space`).
- Padrão recorrente nas referências com ativação por voz: **sempre há um caminho que não depende do wake** (tecla, botão, ou comando de estado), e **sempre há um diagnóstico visível** (medidor, teste de microfone, log, gravação de depuração, painel de transcrição).
- Gideon já tem peças importantes (medidor de nível em `src/levels.rs`, enumeração de dispositivos em `src/devices.rs`, sensibilidade do wake, consentimento para áudio ao vivo). O que falta, em termos práticos, é **fechar o ciclo de primeira execução**: escolher o microfone certo, provar que ele entrega áudio, mostrar o que foi ouvido e oferecer um atalho de ativação que não depende do wake.
- Saúde do próprio Nixi: produto beta, instalador sem assinatura digital (SmartScreen), repositório público de releases com 2 commits e 1 estrela, nenhuma issue aberta, nenhuma página de solução de problemas. Avaliação: **pouco testado publicamente**. Não encontrei avaliação independente.

---

## 2. Escopo e método

- Fontes do Nixi: landing page (`https://heynixi.app/`), sitemap, `/privacy`, `/updates`, `/feedback`, `/blog/` e os 4 posts, `https://heynixi.com/` (mesmo conteúdo), releases no GitHub (`xbrxr03/heynixi-releases`, v0.2.0 e v0.2.1), buscas por Product Hunt, Reddit, Hacker News, Microsoft Store e YouTube.
- Concorrentes: 13 referências, listadas na seção 4. Algumas pedidas no briefing não foram possíveis de confirmar (ver seção 9).
- Gideon: leitura de `base/AGENTS.md`, `base/README.md`, `base/docs/AGENT_STATE.md`, `base/docs/A1.md`, `A3.md`, `A5.md`, `A6-live-audio.md`, `A8-wake-acoustic-test.md`, `base/docs/PENDENCIAS_IMPLEMENTACAO.md` e cabeçalhos de `src/levels.rs` e `src/devices.rs`.

---

## 3. Nixi: investigação aprofundada

### 3.1 Fontes e o que cada uma acrescenta

| Fonte | O que traz de útil |
|---|---|
| [heynixi.app](https://heynixi.app/) | Descrição, lista de recursos, requisitos. Não traz ativação. |
| [Blog: Command, Dictate, Write](https://heynixi.app/blog/command-dictate-write) | Os três modos e o comportamento de "pill". |
| [Blog: Why Nixi lives in one pill](https://heynixi.app/blog/why-nixi-lives-in-one-pill) | **F9** como único gatilho nomeado; estados visuais. |
| [Blog: Why Nixi runs on your PC](https://heynixi.app/blog/why-nixi-runs-on-your-pc) | Modelos empacotados, download de ~1.3 GB, opção de modelo maior. |
| [Blog: Why Nixi's voice is recorded](https://heynixi.app/blog/why-nixis-voice-is-recorded) | Voz pré-gravada, respostas por partes, "Sir/Ma'am". |
| [/privacy](https://heynixi.app/privacy) | Dados coletados, retenção, terceiros, conexões. |
| [/updates](https://heynixi.app/updates) | Página de releases sem entradas de changelog. |
| [/feedback](https://heynixi.app/feedback) | Link para o Discord oficial. |
| [Release v0.2.1 (beta)](https://github.com/xbrxr03/heynixi-releases/releases/tag/v0.2.1) | F9, mudanças de microfone, SmartScreen, checksum, "silence defaults". |
| [Release v0.2.0 (beta)](https://github.com/xbrxr03/heynixi-releases/releases/tag/v0.2.0) | Data 18 de outubro (confirmado na fonte), requisitos, SmartScreen, checksum. |
| [Repositório de releases](https://github.com/xbrxr03/heynixi-releases) | 2 commits, 1 estrela, 0 forks, README de uma linha. |
| [Issues do repositório](https://github.com/xbrxr03/heynixi-releases/issues) | Filtro de issues abertas sem resultados (confirmado na fonte). |

### 3.2 Ativação

- **Gatilho de voz (wake word): não há menção.** Nenhuma das páginas lidas, nem as notas de versão, cita wake word. **(inferido: o Nixi não tem wake word; a ausência de menção é a evidência principal, e não consegui confirmar isso de outra forma.)**
- **Tecla F9.** "Press F9 to open chat." (confirmado na fonte: notas de v0.2.1). E no blog: "the only trigger it names is the F9 key (or the 'more' button), which opens the chat bar." (confirmado na fonte: post "Why Nixi lives in one pill", resumo da ferramenta). **(inferido: F9 abre o chat, e o "chat" é a barra de comandos/ditado/escrita. Não confirmei se F9 também inicia a escuta por voz.)**
- **Botão na pill.** O botão "more" abre a mesma barra (confirmado na fonte, mesmo post).
- **Push-to-talk ou hold-to-talk: não há menção.** (confirmado na fonte: ausência em todas as páginas.)
- **A pill nunca pega foco do teclado** quando fechada: "the closed pill never takes keyboard focus, so you can keep working where your cursor is." (confirmado na fonte.)
- **Ação sem voz:** o comando pode ser digitado, pela barra aberta pela F9. (inferido, a partir de "command bar" e "Command typing" nas notas de 0.2.1.)

### 3.3 Engines (ASR, LLM, TTS)

- **ASR (reconhecimento de fala):** "Speech recognition and the AI run on your PC." (confirmado na fonte). **Nome do modelo: não divulgado** (confirmado na fonte: notas de 0.2.0 e 0.2.1 falam só de "the bundled model").
- **LLM:** idem; "bundled AI". Nenhum nome (confirmado na fonte: ausência). **(inferido: é um modelo pequeno local, pela restrição de ~1.3 GB do pacote e pela nota de que computadores antigos ficam mais lentos.)**
- **Modelo maior opcional:** "If your PC is stronger, Settings can download a larger one for you." (confirmado na fonte: post "runs on your PC").
- **Tamanho:** landing page diz "About 4 GB of free space for setup and updates" (confirmado na fonte); blog diz "the download is about 1.3 GB" (confirmado na fonte). A diferença é plausível (download x espaço para instalação e atualizações), mas **não confirmei**.
- **TTS:** **não há motor TTS gerado.** "Nixi uses a single recorded British voice." "A recording sounds the same every time." Falas são montadas com trechos gravados (números, meses, "o'clock"). Se não há gravação, a resposta aparece na pill em vez de ser falada em outra voz. (confirmado na fonte: post "voice is recorded".)
- **LLM na nuvem:** só planejado, como "bring your own key" opcional. (confirmado na fonte.) Versão gratuita: local.

### 3.4 Idiomas

- Não há lista de idiomas em nenhuma página. **(não verificado.)**
- Indícios: voz britânica; comandos de formatação em inglês ("newline", "line break", "enter") nas notas de 0.2.1; "Sir/Ma'am" no setup. **(inferido: somente inglês.)**

### 3.5 UI e estados

- **Pill:** cápsula preta com um rosto. Em repouso fica pequena; ao ativar expande para barra de comando, faixa de ditado ou cartão de resposta, e depois retrai. "one object changing shape," não painéis separados. (confirmado na fonte.)
- **Estados do rosto:** escutando, pensando, pronto. Acompanhados de sons curtos e discretos. (confirmado na fonte.)
- **Perguntas:** botões Sim e Não aparecem na própria pill. (confirmado na fonte.)
- **Transcrição ao vivo:** a linha mostra o fim do que você fala; palavras antigas saem pela esquerda. (confirmado na fonte.)
- **Posição:** arrastável; a posição é lembrada por monitor e fica sempre visível; pode ficar transparente; pode voltar ao topo. (confirmado na fonte.)
- **Modos:** três botões: Command, Dictate e Write. (confirmado na fonte.)
  - Command: "firm rules", e confere se está agindo na janela certa antes de digitar ou clicar. (confirmado na fonte.)
  - Dictate: digita na app ativa, remove palavras de preenchimento, pontua, segue edições faladas, formata listas; pode manter as palavras exatas. Ditado "stays free". (confirmado na fonte.)
  - Write: gera texto na app ativa, "stops if you switch away halfway"; envio fica com o usuário. (confirmado na fonte.) Notas de 0.2.0: "Write works best for short drafts and edits." (confirmado na fonte.)
- **Confirmação:** a maior parte dos comandos roda sem perguntar; ações difíceis de desfazer (ex.: apagar todos os lembretes) pedem confirmação. (confirmado na fonte.)
- **Respostas de conversa:** "Are you there?" tem resposta roteirizada. (confirmado na fonte.)

### 3.6 Configurações, microfone e solução de problemas

- **Seleção de microfone:** notas de 0.2.1 listam "More reliable microphone selection" como melhoria. Não há descrição de tela, nem passo a passo. **(confirmado na fonte: existe melhoria; (não verificado): como se escolhe.)**
- **Teste de microfone / medidor de nível:** não há menção. (confirmado na fonte: ausência.)
- **Configurações listadas:** idioma/voz não; "Shorter silence defaults and better handling of empty listening sessions" (0.2.1); transparência da pill; posição; modelo maior; "Sir/Ma'am". (confirmado na fonte.) Não há caminho de menus.
- **Dados locais:** configurações, histórico, lembretes e arquivos de diagnóstico ficam no PC. (confirmado na fonte: privacidade.)
- **Mensagens de erro quando não ouve nada:** nenhuma documentada. (confirmado na fonte: ausência.)
- **Problemas conhecidos:** "Known issues: None listed." (confirmado na fonte: v0.2.1.)
- **Solução de problemas:** só o caminho do SmartScreen ("More info", depois "Run anyway"). (confirmado na fonte.)
- **Checksum:** o site oferece `Get-FileHash .\heynixi-windows-setup.exe` para conferir o instalador. (confirmado na fonte: v0.2.0 e v0.2.1.)

### 3.7 Onboarding

- Onboarding novo aparece **antes da pill** (confirmado na fonte: v0.2.1). Conteúdo não descrito.
- Escolha "Sir" ou "Ma'am" no setup (confirmado na fonte).
- Sem conta exigida (confirmado na fonte: post "runs on your PC": "No account is required").
- Desinstalação oferece escolher se mantém os dados salvos (confirmado na fonte: v0.2.1).

### 3.8 Privacidade (`/privacy`)

- Analytics do site: Cloudflare Web Analytics, só totais. (confirmado na fonte.)
- Download e waitlist: e-mail, datas, número de pedidos, país. (confirmado na fonte.)
- Feedback: respostas guardadas no Cloudflare KV e **apagadas após um ano**; a equipe lê e pode usar IA para classificar. (confirmado na fonte.)
- App: "In its default local setup, heynixi processes speech and AI requests on your PC." (confirmado na fonte.)
- **Áudio:** "does not automatically upload audio, transcripts, screenshots, history, or diagnostics to Nixi." (confirmado na fonte.) **Prazo de retenção de áudio: não divulgado.** A página remete a um aviso completo `docs/PRIVACY.md` que não está publicado. (confirmado na fonte.)
- **Conexões de internet:** pesquisa web, abrir sites, download de modelos opcional, Discord. (confirmado na fonte.)
- **Erros:** a partir da versão 0.2.11 o app não envia relatório de erro; antes disso, relatórios opcionais, mostrando o conteúdo antes, guardados por até 90 dias. (confirmado na fonte.)
- **Incoerência:** a política cita a versão **0.2.11**, mas o repositório público de releases mostra **0.2.1** como a mais recente. (confirmado na fonte, nas duas páginas.) **(inferido: há versões internas ou não publicadas.)**
- Contato e remoção: por e-mail. Endereço ofuscado no código; não o reproduzi.

### 3.9 Limitações declaradas

- Beta; instalador sem assinatura de código ("This beta isn't code-signed yet"). (confirmado na fonte.)
- Windows 10/11 64 bits apenas. (confirmado na fonte.)
- Requisitos: 8 GB de RAM recomendados; GPU opcional. (confirmado na fonte.)
- PCs antigos rodam mais devagar. (confirmado na fonte.)
- Respostas faladas livres dependem de voz gerada, que só virá no modo "traga sua chave" (planejado). (confirmado na fonte.)
- Pesquisa web e abrir sites exigem internet. (confirmado na fonte.)
- "Core features work offline after setup." (confirmado na fonte.) O vídeo de terceiros fala em "fully offline", o que não bate com a página oficial. (confirmado na fonte: vídeo, resumo de busca.)

### 3.10 Sinais de maturidade e confiança

- Repositório `xbrxr03/heynixi-releases`: público, 2 commits, 1 estrela, 0 forks, README de uma linha, "Releases" sem contagem visível. (confirmado na fonte.)
- Issues: filtro "is:issue state:open" sem resultados (confirmado na fonte). Issues fechadas: não retornou nada na leitura. (não verificado: se o repositório tem histórico de issues.)
- Datas: v0.2.0 em 18 de outubro; posts do blog em 22 de outubro de 2026. (confirmado na fonte.)
- **Verificação de domínio:** a busca retornou dois resumos conflitantes do ScamAdviser. Um diz "likely safe" com domínio muito novo; outro diz "trust score 0". (não verificado: não consegui abrir a página, que devolveu erro 403 ou resumo genérico.) Não tirei conclusão disso.
- Dois domínios: `heynixi.app` (oficial nas notas de versão) e `heynixi.com` (mesmo conteúdo, aparece em buscas). (confirmado na fonte.)
- Discord: `https://discord.gg/TxsDTt8mtu` (confirmado na fonte: `/feedback`).

### 3.11 Lacunas de busca (o que não achei)

- **Product Hunt:** nenhum resultado. (confirmado na busca: ausência.)
- **Reddit e Hacker News:** nenhum resultado específico. A busca não restringiu sites de forma confiável. (não verificado.)
- **Microsoft Store:** nenhum resultado. (confirmado na busca: ausência.)
- **YouTube:** um vídeo promocional ("This FREE AI Assistant Turns Your Windows PC Into JARVIS") com descrição "fully offline". Não li a descrição completa; só o resumo de busca. (não verificado.) Um segundo vídeo ("Finally a Good JARVIS style Ai Assistant for Windows?!") apareceu, mas não li. (não verificado.)
- **Página `/updates`:** só título e frase "Release notes for public Windows builds." Sem entradas. (confirmado na fonte.)

### 3.12 Pontos que servem para o Gideon

- A tecla F9 é uma ativação sem wake word, o que tira do usuário a dependência de palavra de ativação. Isso é o contrário da nossa situação: nosso wake é a única porta de entrada.
- O Nixi trata a escolha de microfone como item de release ("more reliable"), e não como documento. Ou seja, o problema real aparece em produção e é corrigido por versão.
- A página de privacidade é um bom modelo de transparência: diz o que é armazenado localmente, o que não sai do PC e o que sai (pesquisa, sites, download de modelo). A lacuna é a retenção de áudio.

---

## 4. Concorrentes e referências

Cada bloco segue a mesma ordem: ativação, engines, microfone (escolha e teste), ruído e VAD, onboarding, configurações, erro quando não ouve nada, o que faz funcionar "de cara", fontes.

### 4.1 OpenDex (getopendex.com)

- **Fonte:** [getopendex.com](https://getopendex.com/) (só o título veio na leitura; o restante veio de um resumo de busca, não de leitura direta); [wassgha/opendex](https://github.com/wassgha/opendex) (apareceu na busca; página não lida).
- **Ativação:** wake word, depois fala. Vosk para o wake, Whisper local para transcrição. (confirmado na fonte: resumo de busca do site; não verificado diretamente.)
- **Engines:** Vosk (wake), Whisper local (transcrição); modo nuvem via Vercel AI Gateway, com OpenAI, Anthropic, xAI. Apple Intelligence no macOS. (confirmado na fonte: resumo de busca.)
- **Microfone, teste, medidor:** não verificado.
- **Permissões:** ações sensíveis pedem "Allow once / Always / Deny", lembradas por skill. (confirmado na fonte: resumo de busca.)
- **Barge-in:** opcional, para interromper a resposta. (confirmado na fonte: resumo de busca.)
- **Versão:** v1.1.14 listada. Plataformas: macOS, Windows, Linux (AppImage, .deb). (confirmado na fonte: resumo de busca.)
- **Avaliação de terceiros:** um review com nota 6/10 diz que depende de hardware e configuração. (confirmado na fonte: resumo de busca.)
- **Lição:** o modelo "wake + ferramentas + permissão por ação" é o mais próximo do nosso (wake + comandos + plugins). A parte de permissão por skill é diretamente aplicável.

### 4.2 Nox (VeridonNetzwerk/Nox)

- **Fonte:** [github.com/VeridonNetzwerk/Nox](https://github.com/VeridonNetzwerk/Nox) (README lido).
- **Ativação:** wake "Hey Nox", com modelo openWakeWord personalizado, rodando offline. Limiar padrão 0.5. Pode ser desligado no config. (confirmado na fonte.)
- **Atalho paralelo:** `hotkey: Ctrl+Shift+Space` no config. (confirmado na fonte.)
- **Engines:** STT faster-whisper (CUDA por padrão, CPU como fallback), modelo `small`, idioma padrão alemão (`de`). VAD para silêncio. (confirmado na fonte.)
- **TTS:** Edge TTS (nuvem), Kokoro-82M (offline), Piper (offline; é o padrão no config). 27 idiomas listados. (confirmado na fonte.)
- **LLM:** Ollama com streaming; o README cita Qwen3 por VRAM, mas a seção "About" diz "Gemma 4". Incoerência interna. (confirmado na fonte.)
- **Microfone:** onboarding com assistente que cobre microfone, seleção de dispositivo e **calibração do wake**. (confirmado na fonte.)
- **Ruído e VAD:** `vad_silence_duration: 1.0 s`, `vad_timeout: 15.0 s`. (confirmado na fonte.)
- **Erros:** o README não tem seção de solução de problemas. Pede que o usuário abra issue com comportamento esperado x real, versão do Windows, GPU, se usou instalador ou fonte, e logs em `%APPDATA%\Nox\logs\`. (confirmado na fonte.)
- **Instalação:** Windows (`Nox-Setup.exe`, sem assinatura, SmartScreen), Linux (.deb). Primeira execução baixa Electron, dependências Python e pode instalar Ollama. (confirmado na fonte.)
- **Privacidade:** "fully offline", analytics anônimo opcional, desativável nas configurações. (confirmado na fonte.)
- **Lição:** o que mais se parece com o nosso problema é o wizard de calibração do wake e o atalho paralelo. Também é o melhor exemplo de caminho de log explícito.

### 4.3 Nixii (Naveenravi07/nixie)

- **Fonte:** [github.com/Naveenravi07/nixie](https://github.com/Naveenravi07/nixie) (leitura; o nome do repositório é "nixie", o produto se chama "nixii").
- **Ativação:** **sem wake word.** Gatilho manual por tecla ou atalho que chama `nixii-voice trigger`. Razão declarada: "No constant background listening/wake-word overhead." (confirmado na fonte.)
- **Engines:** STT não nomeado; LLM Google Gemini (nuvem); chave `GOOGLE_CLOUD_API_KEY` ou similar. (confirmado na fonte.)
- **Microfone:** não coberto. (confirmado na fonte: ausência.)
- **Configuração:** TOML com ordem de resolução documentada (flag, variável de ambiente, `~/.config/nixii/nixii.toml`, exemplo do repositório). (confirmado na fonte.)
- **Lição:** provar que é possível evitar o wake quando ele não é o diferencial. Mostra a ativação por atalho como caminho de primeira classe, não como plano B.

### 4.4 OpenVoiceOS (OVOS)

- **Fonte:** [openvoiceos.org](https://www.openvoiceos.org/) (leitura da home).
- **Arquitetura:** STT e TTS por plugins. (confirmado na fonte: "plugin-based architecture for both speech recognition (STT) and text-to-speech (TTS)".) Skills vêm de marketplace comunitário. (confirmado na fonte.)
- **Engines:** STT padrão online; offline: Vosk e DeepSpeech. TTS: Mimic3 (local), Google TTS, Amazon Polly. (confirmado na fonte.)
- **Wake word:** personalizável na instalação. Sistema de plugins de wake não confirmado na página. (não verificado.)
- **Privacidade:** "ovos-core does not require a backend internet server to operate." O STT padrão exige internet. (confirmado na fonte.)
- **Lição:** o padrão online de STT é exatamente o que não queremos para nosso caso. Mas o desenho de plugins é um bom modelo para o sistema de skills.

### 4.5 Rhasspy

- **Fonte:** [github.com/rhasspy/rhasspy](https://github.com/rhasspy/rhasspy) (leitura).
- **Status:** **arquivado** pelo dono em 6 de outubro de 2025. Somente leitura. (confirmado na fonte.)
- **Wake e STT/TTS:** a lista de repositórios cita Pocketsphinx, Porcupine, Precise, Raven, Snowboy (wake); Kaldi, Pocketsphinx, DeepSpeech, Vosk (STT); Larynx, WaveNet (TTS). (confirmado na fonte: nomes de repositórios.)
- **Microfone e teste:** não cobertos. Só um ponteiro para a comunidade. (confirmado na fonte.)
- **Interface web:** "configure, program, and test your voice assistant remotely", com página de teste. Não cita medidor de nível. (confirmado na fonte.)
- **Lição:** o projeto mais influente do gênero está arquivado. Não devemos depender de componentes que não recebem mais manutenção.

### 4.6 Home Assistant Assist e OHF linux-voice-assistant

- **Fonte:** [github.com/OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) (leitura); [home-assistant.io troubleshooting de voz](https://www.home-assistant.io/voice_control/troubleshooting/) (leitura).
- **Ativação:** wake local com openWakeWord ou microWakeWord. Modelo padrão `okay_nabu`; modelo de parada `stop`. (confirmado na fonte.)
- **Microfone:** `--audio-input-device` (detecção automática por padrão), `--audio-output-device`, `--music-output-device`, `--list-input-devices`, `--list-output-devices`. Exige **16 kHz mono**. Qualquer microfone que funcione com PipeWire "in theory". (confirmado na fonte.)
- **Inconsistência:** a tabela de parâmetros tem `--audio-input-channels` padrão 2, contra a exigência de mono. (confirmado na fonte.)
- **Teste/medidor:** não descrito no README do satélite. (confirmado na fonte: ausência.)
- **Erros:** README sem seção de solução de problemas; a opção `--debug` imprime mensagens de depuração. (confirmado na fonte.)
- **Home Assistant (Assist):** para sensibilidade e ganho, documentação oficial indica ajustar `noise_suppression_level` (máx. 4), `auto_gain` (máx. 31) e `volume_multiplier`, com cautela para não distorcer. (confirmado na fonte.)
- **Diagnóstico:** `debug_recording_dir` grava `.wav` por comando de voz, e a aba **Debug** mostra o texto reconhecido de cada execução. Advertência: consome espaço. (confirmado na fonte.)
- **Lição:** o par "gravação de depuração em disco + texto reconhecido por execução" é a forma mais direta de descobrir por que o wake não disparou. É o que mais falta no Gideon.

### 4.7 Willow (HeyWillow)

- **Fonte:** [github.com/HeyWillow/willow](https://github.com/HeyWillow/willow) (leitura parcial).
- **Descrição:** "Open source, local, and self-hosted Amazon Echo/Google Home competitive Voice Assistant alternative." (confirmado na fonte.)
- **Engines:** não confirmados. Tags do repositório: esp32, esp-idf, whisper, speech-to-text, privacy. (confirmado na fonte: tags; inferido: Whisper no servidor.)
- **Servidor:** "Willow Inference Server" para STT, TTS e LLM, autohospedado. (confirmado na fonte.)
- **Microfone, teste, ruído:** não cobertos na página lida. (não verificado.)
- **Lição:** arquitetura de dispositivo + servidor separado. Não é nosso caso, mas mostra o custo de depurar microfone em hardware remoto.

### 4.8 Leon

- **Fonte:** [github.com/leon-ai/leon](https://github.com/leon-ai/leon) (leitura).
- **Status:** versão 2.0 em "Developer Preview" no branch `develop`; docs novas "not ready yet". (confirmado na fonte.)
- **Ativação, STT, TTS, microfone:** não cobertos na página lida. (confirmado na fonte: ausência.)
- **LLM:** locais e remotos. (confirmado na fonte.)
- **Requisitos:** Node.js 24 ou superior. (confirmado na fonte.)
- **Lição:** pouca informação aproveitável para voz. Útil como referência de arquitetura agêntica, não de voz.

### 4.9 Dicio (Android)

- **Fonte:** [github.com/Stypox/dicio-android](https://github.com/Stypox/dicio-android) (leitura).
- **Ativação:** wake "Hey Dicio" com OpenWakeWord por padrão. Modelos `.tflite` personalizados importáveis em Settings > Input and output methods. (confirmado na fonte.)
- **STT:** Vosk, modelos pequenos (~50 MB) baixados sob demanda. (confirmado na fonte.)
- **TTS:** não nomeado. (confirmado na fonte: ausência.)
- **Idiomas:** 14. (confirmado na fonte.)
- **Offline:** "when possible"; skills online: busca (DuckDuckGo), clima, letras, tradução. (confirmado na fonte.)
- **Lição:** o caminho para modelo personalizado de wake é uma tela de configuração com importação, não um fluxo técnico. É um bom alvo para o Gideon.

### 4.10 Talon Voice

- **Fonte:** site oficial **não respondeu** (erro de DNS em `talonvoice.com`). Usei resumo de busca com fontes da comunidade. (não verificado para o oficial.)
- **Ativação:** modo "sleep" mantém escuta sem responder; "wake up" ativa. Comando de wake com alternativas separadas por `|` (comunidade). (confirmado nas fontes da comunidade: talon.wiki, blog; não verificado no site oficial.)
- **Engines:** modelos Conformer (b108 e D2) na tela de reconhecimento. Changelog cita rejeição de comandos incorretos. (confirmado na fonte: resumo de changelog em `talonvoice.com/dl/latest/changelog.html`, não lido diretamente.)
- **Lição:** o modo "dormindo" com palavra de despertar, somado à rejeição de comandos incorretos, é o mesmo problema que temos (falso positivo x falso negativo). Vale ler a documentação oficial antes de adotar.

### 4.11 Windows Voice Access (Microsoft)

- **Fonte:** [Get started with voice access (support.microsoft.com)](https://support.microsoft.com/en-us/accessibility/windows/voice-access/get-started-with-voice-access) (leitura); [Voice access command list](https://support.microsoft.com/en-us/topic/voice-access-command-list-dac0f091-87ce-454d-8d57-bef38d3d8563) (busca).
- **Três estados:** Sleep ("does not react to anything you say, except the command to switch it into listening state"), Listening ("listens to everything you say and executes..."), Microphone off ("hears none of your speech. You must click the Microphone button"). (confirmado na fonte.)
- **Controles:** "Voice access wake up" ou "Unmute" (acordar); "Voice access sleep" ou "Mute" (dormir); "Turn off microphone". Atalhos: Alt+Shift+B alterna sleep/listening; Alt+Shift+C liga/desliga microfone. (confirmado na fonte.)
- **Microfone:** "Select default microphone" nas configurações, com link para Som do Windows. Link para "How to set up and test microphones in Windows". (confirmado na fonte.)
- **Requisitos:** Windows 11 22H2 ou superior; funciona sem internet. (confirmado na fonte.)
- **Solução de problemas:** a página oficial **não tem passos**, só links. (confirmado na fonte.)
- **Solução de problemas da comunidade (não oficial):** dispositivo de entrada errado; pacote de fala ausente ("fail silently"); permissão de microfone para apps da Store; desligar "exclusive mode" e aprimoramentos; reiniciar o serviço de reconhecimento de fala do Windows; conflito com outros apps de voz. Códigos de erro citados em fóruns: 2001 e 9001. (confirmado nas fontes de comunidade; não verificado oficialmente.)
- **Lição:** o estado "sleep" com atalho de alternância é o padrão mais claro que encontrei. A página oficial pobre em solução de problemas é o que não copiar.

### 4.12 Nyxa

- **Fonte:** [github.com/varundevarajrvu/nyxa](https://github.com/varundevarajrvu/nyxa) (leitura).
- **Ativação:** wake "hey jarvis" via openWakeWord (ONNX), ~5% de um núcleo. Também palmas (três). Nada é gravado ou transcrito antes do wake. (confirmado na fonte.)
- **Engines:** Parakeet TDT 0.6B int8 via sherpa-onnx (~640 MB, download por script). VAD Silero para fim de fala. (confirmado na fonte.)
- **Latência:** 150–350 ms. (confirmado na fonte.)
- **Segurança:** registro de ações com nível de permissão **vindo do registro, não do modelo**: SAFE-AUTO, NEEDS-CONFIRM (confirmação falada), DENY-BY-DEFAULT (clique). (confirmado na fonte.)
- **Kill switch:** `Ctrl+Shift+Alt+K` ou "jarvis stop"; retomada manual. (confirmado na fonte.)
- **Microfone, teste, medidor, erros:** não cobertos. (confirmado na fonte: ausência.)
- **Plataforma:** Windows 11. MIT. 13 commits, sem releases. (confirmado na fonte.)
- **Lição:** a arquitetura de permissão por registro, com parada de emergência, é diretamente aplicável ao nosso sistema de comandos. Não copio o detalhe de wake: não há calibração.

### 4.13 Wispr Flow e Superwhisper (ditado)

- **Wispr Flow:** [wisprflow.ai](https://wisprflow.ai/) (leitura).
  - Ativação (segurar ou alternar): não descrita. (confirmado na fonte: ausência.)
  - Engine (nuvem ou local): não descrita. "Flow uses the most advanced voice technology available." (confirmado na fonte.)
  - Microfone: "built-in microphone is sufficient"; evitar fones Bluetooth; mic perto da boca ajuda; página de microfones separada. Não há seletor descrito na página. (confirmado na fonte.)
  - Idiomas: 100+; recomenda selecionar só o idioma falado. (confirmado na fonte.)
  - Offline: não mencionado. (confirmado na fonte: ausência.)
  - Ajuda: docs.wisprflow.ai, suporte, "Talk to support". Erro de login: "Something went wrong during sign-in. Please try again." (confirmado na fonte.)
  - Lição: a recomendação sobre fone Bluetooth é concreta e barata para copiar em texto de ajuda.
- **Superwhisper:** [superwhisper.com/docs](https://superwhisper.com/docs) (leitura da introdução).
  - "Local voice models transcribe without an internet connection." "With local models, nothing you say leaves your device." (confirmado na fonte.)
  - IA de formatação offline só com modelo S1-mini, e só em modos Message ou Mail. (confirmado na fonte.)
  - Windows disponível; Linux "coming soon". (confirmado na fonte.)
  - Páginas de Ativação, Solução de problemas e Modos existem, mas não consegui abri-las (404 em tentativa de URL direta). (não verificado.)
  - Lição: separar o que é local do que é nuvem, por modo, com clareza. Isso é melhor do que uma declaração geral de privacidade.

### 4.14 Jan e Open Interpreter

- **Jan** ([github.com/jan-ai/jan](https://github.com/jan-ai/jan)): erro 404 na tentativa de leitura. (não verificado.)
- **Open Interpreter** ([github.com/openinterpreter/open-interpreter](https://github.com/openinterpreter/open-interpreter)): o README lido **não descreve modo de voz**. Não sei se a funcionalidade existe em documentação separada. (confirmado na fonte: ausência no README lido.)

---

## 5. Comparação de funcionalidades com o Gideon

Gideon hoje, conforme `base/README.md`, `base/docs/A1.md`, `A3.md`, `A5.md`, `A6-live-audio.md` e `PENDENCIAS_IMPLEMENTACAO.md`:
- Wake "Hey Gideon" via sherpa-onnx KWS (padrão; "Okay" experimental, gate de qualidade pendente). (confirmado na fonte: `A1.md`.)
- Sensibilidade do wake: preferência `wake_sensitivity` de 0.5 a 1.5, padrão 1.0. Efeito acústico **não validado**. (confirmado na fonte.)
- STT: Moonshine Small Streaming EN (referência experimental). (confirmado na fonte: `A3.md`.)
- TTS: Pocket TTS EN (CPU), uma voz empacotada. (confirmado na fonte: `A5.md`, `PENDENCIAS`.)
- Áudio ao vivo: opt-in com consentimento, via `pw-record`/`parecord` em sandbox. (confirmado na fonte: `A6`.)
- Medidor de nível: módulo `src/levels.rs`, com piso de ruído, detecção de fala e alertas de "sem frames". (confirmado na fonte: cabeçalho do arquivo.)
- Enumeração de dispositivos: `src/devices.rs` via `pactl`/`pw-dump`. (confirmado na fonte: cabeçalho do arquivo.)
- Atalhos: Ctrl+M (liga/desliga microfone), Esc, Ctrl+K, Ctrl+1…5. (confirmado na fonte: `PENDENCIAS`, B15.)
- Plugins, skills, conexões, abas com temas. (confirmado na fonte: `base/README.md` e `AGENT_STATE.md`; detalhes de UI não revisados.)
- Diagnóstico do wake: `docs/A8-wake-acoustic-test.md` registra estado **NO_ACOUSTIC_PICKUP**: nenhum par de alto-falante e microfone captou o som de forma mensurável. (confirmado na fonte.)
- Causa registrada de "wake não funciona": o pacote nunca abria o microfone; agora existe `live_audio` com consentimento. (confirmado na fonte: `docs/AGENT_STATE.md`, entrada de 2026-10-25.)

Legenda: **Tem** = existe; **Parcial** = existe com limite; **Falta** = não encontrei nas fontes; **Gideon**: o estado é o do repositório em 2026-10-25.

| Recurso | Nixi | Nox | OHF/Home Assistant | Dicio | Voice Access (MS) | Gideon hoje | Falta no Gideon? |
|---|---|---|---|---|---|---|---|
| Atalho de ativação alternativo (sem wake) | **Tem** (F9) | **Tem** (`Ctrl+Shift+Space`) | Não confirmado | Não | **Tem** (Alt+Shift+B) | Parcial (Ctrl+M liga/desliga microfone; não é push-to-talk) | **Sim, prioridade 1** |
| Wake word | Não | **Tem** (openWakeWord, "Hey Nox") | **Tem** (openWakeWord/microWakeWord) | **Tem** ("Hey Dicio") | Tem ("Voice access wake up") | **Tem** ("Hey Gideon", sherpa-onnx) | Não |
| Calibração do wake por voz | Não | **Tem** (wizard) | Não confirmado | Não | Não | Parcial (sensibilidade, sem calibração guiada) | **Sim** |
| Estados de escuta (dormir/ouvir/desligado) | Parcial (pill: escutando/pensando/pronto) | Não confirmado | Não confirmado | Não confirmado | **Tem** (3 estados) | Parcial (mockups "hoje-ouvindo") | **Sim** (tri-estado explícito) |
| Medidor de nível / teste de microfone | Não | Parcial (wizard) | Não (só `--debug`) | Não | Não (link para Som do Windows) | **Tem** (`levels.rs`) na Core; não confirmo UI | Verificar UI |
| Seleção de microfone | **Parcial** ("more reliable" em 0.2.1) | **Tem** (wizard) | **Tem** (`--audio-input-device`) | Não confirmado | **Tem** ("Select default microphone") | **Tem** (`devices.rs`; preferência) | Falta o teste de entrega de áudio |
| Transcrição do que foi ouvido (visível) | **Tem** (linha ao vivo) | Não confirmado | **Tem** (aba Debug) | Não confirmado | Não confirmado | Não confirmado | **Sim** |
| Gravação de depuração em disco (opt-in) | Não | Logs em `%APPDATA%` | **Tem** (`debug_recording_dir`) | Não | Não | Não | **Sim** |
| Ganho/supressão de ruído expostos | Não | Não confirmado | **Tem** (`auto_gain`, `noise_suppression_level`) | Não | Não | Não | **Sim** |
| VAD para fim de fala | Não confirmado (há "silence defaults") | **Tem** (VAD, silêncio 1.0 s) | Não confirmado | Não confirmado | Não confirmado | Não confirmado | **Sim** |
| Sons curtos de estado | **Tem** | Não confirmado | Não confirmado | Não confirmado | Não confirmado | Não confirmado | Sim, barato |
| Log local com caminho na UI | Parcial (arquivos locais) | **Tem** (caminho no README) | **Tem** (`--debug`) | Não | Não | Parcial (diagnóstico, pendências) | Sim |
| Pacote de suporte para anexar | **Tem** (manual) | Não | Não | Não | Não | Não confirmado | Sim |
| Permissão por ação com registro de tiers | Parcial (confirmação em ações irreversíveis) | Não | Não | Não | Não | Parcial (permissões, `NEEDS-…` não confirmado) | Verificar |
| Parada de emergência (kill switch) | Não | Não | Não | Não | Não | Não confirmado | Considerar |
| Plugins/skills | Não | Não confirmado | Não | Não | Não | **Tem** | Não |
| Modo offline declarado | **Tem** (núcleo) | **Tem** | Parcial | Parcial | **Tem** | Não confirmado | Verificar |
| Sistema de temas | Parcial (transparência) | Não confirmado | Não | Não | Não | **Tem** | Não |

---

## 6. O que copiar (ordenado por impacto em "o wake não dispara para o usuário")

1. **Atalho de ativação alternativo sem wake.** Uma tecla configurável (ex.: F9 do Nixi, `Ctrl+Shift+Space` do Nox) que abre escuta imediata. Quando o wake falha, o usuário ainda consegue usar o assistente. Hoje o Ctrl+M só liga e desliga o microfone; é preciso mapear push-to-talk.
2. **Teste de primeira execução que prova entrega de áudio.** Antes de liberar o wake, pedir "fale agora", mostrar o medidor (já existe em `src/levels.rs`) e exigir que frames cheguem e que um nível de voz seja detectado. O Nox faz isso no wizard, e a Microsoft manda para o teste de microfone. Isso teria pego a causa registrada em 2026-10-25 (o pacote nunca abria o microfone).
3. **Mensagem explícita de "não estou ouvindo", com causa e ação.** Quando não chegam frames (`NO_FRAMES_AFTER`), ou o piso de ruído é alto, ou o nível não sobe, dizer a causa e oferecer trocar o dispositivo. Nixi fala de "better handling of empty listening sessions", mas não diz o que aparece. Nós temos a base de detecção; falta a mensagem.
4. **Mostrar qual dispositivo está em uso, pelo nome, e reabrir ao trocar.** O Nixi trata a seleção como correção de versão ("more reliable microphone selection"). A Microsoft oferece "Select default microphone". O OHF usa `--list-input-devices`. Em `devices.rs` já há a lista; falta exibir e validar.
5. **Calibração guiada do wake no ambiente real.** Pedir 5 a 10 repetições da frase, mostrar a pontuação de cada uma e sugerir um limiar, com presets (conservador, equilibrado, sensível). O Nox faz isso no wizard, e a documentação do openWakeWord diz para ajustar por ambiente, com o limiar padrão de 0.5 como ponto de partida. Nosso `wake_sensitivity` 0.5–1.5 hoje não tem guia.
6. **Painel "último ouvido", mesmo quando o wake não dispara.** Mostrar pontuação do wake e transcrição do STT para cada tentativa. A aba Debug do Home Assistant faz isso, e é a forma mais rápida de ver se o problema é o wake ou o reconhecimento.
7. **Gravação de depuração opt-in, curta, local e apagável.** Guardar os últimos segundos de áudio em `.wav` quando o usuário ligar a opção, com aviso de espaço e botão para apagar. O Home Assistant usa `debug_recording_dir`. Serve para o usuário anexar a um relato sem nos mandar áudio por padrão.
8. **Ganho de entrada e supressão de ruído expostos, com limites.** O Home Assistant documenta `auto_gain` (máx. 31), `noise_suppression_level` (máx. 4) e alerta contra distorção. Um controle único de ganho, com teste pelo medidor, resolve voz baixa sem mexer no sistema.
9. **Gate de VAD antes do wake e opção de supressão de ruído.** openWakeWord permite `vad_threshold` (Silero) para só aceitar wake quando há fala, e Speex para ruído, com a ressalva de que a supressão só roda em x86 e ARM64 Linux. Reduz falsos disparos sem mexer no limiar do modelo.
10. **Estados de escuta visíveis e explícitos: dormindo, ouvindo, microfone desligado.** A Microsoft separa os três, com atalhos distintos. Gideon já tem mockups "hoje-ouvindo"; deve mostrar em qual estado está, o tempo todo.
11. **Sinal sonoro curto ao ativar, independente da voz de resposta.** O Nixi usa sons discretos para "escutando", "pensando" e "pronto". Confirma para o usuário que o wake disparou, mesmo quando nada é falado.
12. **Timeout de silêncio e tempo máximo de escuta configuráveis, com padrão curto.** Nox: silêncio de 1.0 s e timeout de 15 s; Nixi ajustou "silence defaults" na 0.2.1. Sem isso, a frase termina tarde e o usuário acha que o sistema travou.
13. **Onboarding de três passos, pulável: microfone, palavra de ativação, atalho alternativo.** Nixi mostra onboarding antes da pill; Nox faz o wizard de microfone e calibração. Cada passo com teste e estado.
14. **Pacote de suporte e caminho de logs visível na UI.** O Nox pede logs de `%APPDATA%\Nox\logs\` no relato; o Nixi permite salvar um pacote de suporte e anexar manualmente, sem envio automático. Pedir que o usuário "envie o pacote" é mais fácil do que pedir que ele encontre arquivos.
15. **Troca de palavra de ativação com teste antes de salvar.** Dicio importa modelo personalizado pela tela de configuração; Talon usa alternativas para a mesma intenção. Antes de salvar uma frase nova, rodar o teste com a própria voz. Isso também atende o gate pendente do "Okay".

---

## 7. O que evitar

- **Depender só de wake word.** Nixi e Nixii mostram o caminho sem wake; Nixii escolheu isso de propósito. Um usuário com wake que não dispara fica sem entrada alguma no Gideon.
- **Declarar "totalmente offline" sem medir.** O vídeo de terceiros diz "fully offline"; a página oficial diz "core features work offline after setup". O OVOS usa STT online por padrão. Declarar só depois de testar sem internet.
- **Modelos grandes sem aviso de tamanho e tempo.** Nixi pede ~4 GB de espaço; Nyxa baixa ~640 MB; a primeira execução do Nox baixa Electron e dependências. Mostrar tamanho e progresso antes.
- **Instalador sem assinatura digital e sem verificação.** Nixi e Nox caem no SmartScreen ("Windows protected your PC"). Nixi publica SHA-256, o que ajuda. Não devemos distribuir sem as duas coisas.
- **Retenção de áudio não declarada.** A política do Nixi diz que o áudio não sai do PC, mas não diz por quanto tempo fica guardado. Devemos declarar retenção de áudio, mesmo que seja zero.
- **Idioma padrão errado e documentação incoerente.** Nox tem padrão alemão no config e cita dois LLMs diferentes; OHF documenta 2 canais e exige mono. Quem lê a configuração não sabe o que vale.
- **Depender de projeto arquivado ou em pré-lançamento.** Rhasspy está arquivado (out/2025); Leon está em Developer Preview com docs não prontas. Escolher engines com manutenção ativa.
- **Depender de serviços do Windows sem explicar.** Voice Access quebra quando faltam o pacote de fala e o serviço de reconhecimento. Nosso app deve checar e dizer.
- **Mensagens de erro vazias ou silenciosas.** A comunidade relata "fail silently" no Voice Access. Toda falha de áudio deve gerar uma mensagem com causa.
- **Confirmar tudo.** Nixi confirma só ações irreversíveis, e isso é o equilíbrio certo. Confirmar cada comando trava a fluidez.
- **Logs com conteúdo de voz por padrão.** Nixi evita enviar automaticamente; Nox manda o usuário anexar logs. Nosso diagnóstico deve ficar local, e o áudio só entra se o usuário ligar.
- **Pills ou janelas que roubam foco.** Nixi cuida disso ("never takes keyboard focus"). Nosso overlay, se existir, também não deve.

---

## 8. Plano sugerido em uma linha por item

Não é o plano de implementação; é a ordem em que eu testaria a hipótese "o wake não dispara para o usuário":
1. Atalho alternativo (itens 1 e 13).
2. Teste de entrega de áudio no primeiro uso (itens 2, 3 e 4).
3. Transcrição visível e gravação de depuração opt-in (itens 6 e 7).
4. Calibração guiada e VAD (itens 5 e 9).
5. O resto, por custo.

---

## 9. O que não consegui verificar

- **Ativação do Nixi por voz.** Não encontrei menção a wake word. Não há teste ao vivo com o produto; minha conclusão de "sem wake" é uma inferência pela ausência.
- **Se F9 também inicia escuta por voz**, ou só abre o chat digitado. As notas dizem "open chat", e não "start listening".
- **Nomes dos modelos do Nixi** (ASR e LLM) e o tamanho exato do pacote. Não divulgados.
- **Idiomas do Nixi.** Não divulgados.
- **Como o Nixi escolhe o microfone** e se há medidor de nível. A nota diz só "more reliable".
- **Prazo de retenção de áudio no Nixi.** A política remete a um documento não publicado.
- **Versão atual do Nixi.** O site cita 0.2.11 na política e a última release pública que achei é 0.2.1. Não consegui listar as versões intermediárias.
- **Reputação de domínio.** Resumos conflitantes do ScamAdviser; não consegui abrir a página.
- **Product Hunt, Reddit, Hacker News, Microsoft Store:** sem resultados confiáveis nas buscas.
- **Descrições completas dos vídeos do YouTube.** Só o resumo de busca.
- **OpenDex:** só o título do site foi lido; o resto é resumo de busca. O repositório `wassgha/opendex` não foi lido.
- **Talon Voice:** o site oficial não resolveu (erro de DNS). Dados vêm de fontes da comunidade.
- **Superwhisper:** as páginas de ativação, solução de problemas e modos não abriram.
- **Jan:** 404 na tentativa de leitura do repositório.
- **Wispr Flow:** ativação (segurar ou alternar) não está na página lida.
- **Willow e Leon:** pouca informação sobre voz nas páginas lidas.
- **Microsoft Voice Access, solução de problemas:** a página oficial não tem passos; os passos da comunidade não foram verificados oficialmente.
- **Gideon, UI:** li os documentos e cabeçalhos, mas não rodei o app nem inspecionei a tela de Voz e Wake.

---

## 10. Fontes

Nixi:
- https://heynixi.app/
- https://heynixi.app/privacy
- https://heynixi.app/updates
- https://heynixi.app/feedback
- https://heynixi.app/blog/
- https://heynixi.app/blog/command-dictate-write
- https://heynixi.app/blog/why-nixi-lives-in-one-pill
- https://heynixi.app/blog/why-nixi-runs-on-your-pc
- https://heynixi.app/blog/why-nixis-voice-is-recorded
- https://heynixi.com/
- https://github.com/xbrxr03/heynixi-releases
- https://github.com/xbrxr03/heynixi-releases/releases/tag/v0.2.0
- https://github.com/xbrxr03/heynixi-releases/releases/tag/v0.2.1
- https://github.com/xbrxr03/heynixi-releases/issues
- https://discord.gg/TxsDTt8mtu (link oficial no site)
- https://www.scamadviser.com/check-website/heynixi.com (não lido diretamente)
- https://m.youtube.com/watch?v=9hKL97PA3PA (não lido diretamente)

Concorrentes:
- https://getopendex.com/ (parcial)
- https://github.com/VeridonNetzwerk/Nox
- https://github.com/Naveenravi07/nixie
- https://www.openvoiceos.org/
- https://github.com/rhasspy/rhasspy
- https://github.com/HeyWillow/willow
- https://github.com/leon-ai/leon
- https://github.com/OHF-Voice/linux-voice-assistant
- https://www.home-assistant.io/voice_control/troubleshooting/
- https://github.com/Stypox/dicio-android
- https://support.microsoft.com/en-us/accessibility/windows/voice-access/get-started-with-voice-access
- https://support.microsoft.com/en-us/topic/voice-access-command-list-dac0f091-87ce-454d-8d57-bef38d3d8563
- https://github.com/varundevarajrvu/nyxa
- https://wisprflow.ai/
- https://superwhisper.com/docs
- https://github.com/openinterpreter/open-interpreter
- https://github.com/dscripka/openWakeWord
- https://picovoice.ai/docs/api/porcupine-python/
- https://talon.wiki/Resource%20Hub/Speech%20Recognition/troubleshooting/ (comunidade)
- https://talonvoice.com/dl/latest/changelog.html (busca)
- https://github.com/wassgha/opendex (busca)

Gideon (repositório local):
- /home/lucas/Documentos/Gideon/base/README.md
- /home/lucas/Documentos/Gideon/base/AGENTS.md
- /home/lucas/Documentos/Gideon/base/docs/AGENT_STATE.md
- /home/lucas/Documentos/Gideon/base/docs/A1.md
- /home/lucas/Documentos/Gideon/base/docs/A3.md
- /home/lucas/Documentos/Gideon/base/docs/A5.md
- /home/lucas/Documentos/Gideon/base/docs/A6-live-audio.md
- /home/lucas/Documentos/Gideon/base/docs/A8-wake-acoustic-test.md
- /home/lucas/Documentos/Gideon/base/docs/PENDENCIAS_IMPLEMENTACAO.md
- /home/lucas/Documentos/Gideon/base/src/levels.rs
- /home/lucas/Documentos/Gideon/base/src/devices.rs
