# UX de assistentes de voz e apps de comando: padrões para o Gideon

Pesquisa somente leitura feita em outubro de 2026 com busca e leitura de páginas públicas. Não há
capturas de tela nem testes de uso dos produtos. Onde a fonte é secundária (blog, imprensa, teardown de APK),
isso está marcado. Padrões marcados como **proposta** são sugestões minhas, sem fonte direta, e devem ser
validados nos mockups (`docs/ui-mockups/`) antes de virar requisito.

## 1. Produtos analisados (7)

| Produto | Por que entrou | Qualidade da fonte |
|---|---|---|
| Raycast (AI Chat) | Referência de janela de comando com teclado primeiro e chat | Oficial (manual) |
| Alfred (Universal Actions, Large Type) | Ações contextuais e exibição grande de texto | Oficial (site/ajuda) |
| macOS Spotlight | Barra de busca central e controle de sugestões | Oficial (suporte Apple) |
| Siri (Apple Intelligence) | Brilho de borda como estado de escuta/processamento | Mista: notícia e fóruns; HIG sem texto verificado |
| Gemini (Google) | Sistema visual de "pensando" e "ouvindo" | Oficial (design.google) e teardowns |
| Home Assistant Assist | Estados formais do satélite de voz (enum) | Oficial (contributors docs) |
| Alexa app / Alexa+ | Cartões de resposta e sugestões de prompt | Oficial (Amazon, design guide) |
| KRunner (Plasma 6) | Busca de comando no teclado com categorias | Oficial (anúncios de versão) |

Citados como contraste, não como modelo: Humane AI Pin e Rabbit R1 (lições de falha). Não encontrei fonte
boa sobre OVOS/Mycroft/Rhasspy para indicadores visuais (ver seção 6).

## 2. Padrões concretos por produto

### 2.1 Raycast: janela de comando e chat
- **Teclado primeiro.** Enter envia, Shift+Enter quebra linha; Cmd/Ctrl+K abre um painel de ações do chat
  (fixar, arquivar, renomear, copiar, ramificar); Esc fecha; Cmd/Ctrl+N inicia conversa nova; Cmd/Ctrl+R
  regenera resposta. Fonte: [manual.raycast.com/ai/ai-chat](https://manual.raycast.com/ai/ai-chat) e
  [manual.raycast.com/keyboard-shortcuts](https://manual.raycast.com/keyboard-shortcuts).
- **Entrada com anexos por `@`** (arquivos, clipboard, aba do navegador, evento de calendário) e microfone
  para ditado no campo vazio (Ctrl+M). Mesma fonte.
- **Rótulo do botão de envio muda durante o streaming** ("Steer" ou "Queue"), para deixar claro o que
  acontece se o usuário enviar agora. Mesma fonte.
- **Resposta longa recolhida.** Mensagens acima de cerca de 10 linhas colapsam com "Mostrar mais". Código com
  rótulo de linguagem e botão copiar. Mesma fonte.
- **Estado de condensação visível.** "Resumindo conversa…" vira "Resumi a conversa": o processo fica legível
  em vez de parecer travamento. Mesma fonte.
- **Permissões de ferramenta em três modos**: Ask (pergunta), Auto (aprova rotinas, pergunta o resto),
  Always Allow. Padrão por chat, com default global. Fonte:
  [manual.raycast.com/ai/ai-chat](https://manual.raycast.com/ai/ai-chat) e
  [developers.raycast.com/api-reference/tool](https://developers.raycast.com/api-reference/tool).
- **Confirmação executada antes da ferramenta**, recebendo a mesma entrada que ela; se o usuário cancela, a
  ferramenta não roda. Mesma fonte (docs de desenvolvedor).
- **Avisos de confirmação com opção "não perguntar de novo"**, ligados por padrão e desligáveis em
  Configurações > AI > Warnings. Fonte: [raycast.com/changelog](https://www.raycast.com/changelog) (indireta).
- **Pergunta inline com múltipla escolha**: o agente pausa e mostra opções dentro do chat; o usuário escolhe
  e a execução continua. Fonte: manual AI Chat.
- **Limitação verificada**: o manual não descreve estado vazio nem sugestões de início. Não afirmo nada sobre isso.

### 2.2 Alfred: ações contextuais e texto grande
- **Painel de ações universal** sobre um item selecionado (texto, URL, arquivo), mostrando só as ações
  relevantes ao tipo do item. Tecla de atalho configurável. Fonte:
  [alfredapp.com/universal-actions](https://www.alfredapp.com/universal-actions/).
- **Large Type**: mostrar texto (ex.: um número de telefone) em tela cheia grande, com atalho direto a partir
  do histórico de clipboard. Fonte: [alfredapp.com/help/why-choose-alfred](https://www.alfredapp.com/help/why-choose-alfred/)
  e [cheatsheet](https://www.alfredapp.com/help/getting-started/cheatsheet/). Atalhos exatos não verifiquei
  na página atual.
- Nota: a página oficial diz que Universal Actions surgiu no Alfred 4.5; uma fonte de terceiros diz que
  veio com a 5. Usei a oficial.

### 2.3 macOS Spotlight
- **Um campo, um atalho** (Cmd+Espaço mostra e esconde). Fonte:
  [support.apple.com, Spotlight on your Mac](https://support.apple.com/guide/imac/spotlight-apd10f8d1038/2024/mac/15).
- **Sugestões externas são opt-out e separadas em categoria.** A Apple descreve que as Sugestões da Siri
  trazem Wikipédia, web, notícias etc.; é possível desmarcar em Ajustes, e a busca passa a ficar só no Mac.
  Fonte: [Turn off Siri Suggestions for Spotlight](https://support.apple.com/en-mide/guide/mac-help/turn-off-siri-suggestions-for-spotlight-mchl62db64f5/15.0/mac/15.0).
  Lição: dados externos entram como categoria controlável pelo usuário, não misturados por padrão.
- Relato de usuário (não oficial): sugestões do navegador continuaram mesmo após desmarcar. Anedota, não usar como fato.

### 2.4 Siri (Apple Intelligence)
- **Brilho de borda como estado.** Segundo notícias e guias de terceiros, a Siri com Apple Intelligence
  usa um brilho colorido nas bordas da tela ao ser ativada; com o botão lateral ele irradia do lado, com
  "Hey Siri" sobe pela base. Em dispositivos sem suporte, mantém o orbe clássico. Fontes:
  [Pocket-lint](https://www.pocket-lint.com/how-to-get-new-siri-look-glowing-border/),
  [Softonic](https://en.softonic.com/articles/how-to-activate-siris-new-look-and-its-colorful-glow).
  Fonte secundária; não vi a especificação da Apple.
- **Fallback por capacidade**: o visual novo some quando o recurso está desligado e volta o original.
- **HIG da Siri**: a página oficial existe ([developer.apple.com, Siri](https://developers.apple.com/design/human-interface-guidelines/technologies/siri/introduction)),
  mas o conteúdo não foi acessível pela ferramenta de leitura. Não resumo detalhes dela. Fontes de terceiros
  sugerem não imitar a Siri e não anunciar dentro dela; trate como não verificado.

### 2.5 Gemini (Google)
- **Sistema de movimento com intenção.** Cada animação tem início e fim definidos e responde a uma ação do
  usuário; movimento interno indica "pensando" e torna o processamento visível. Fonte oficial:
  [design.google/library/gemini-ai-visual-design](https://design.google/library/gemini-ai-visual-design).
- **Ouvir = gradiente radial em ondulação**; gradiente concentrado para transcrição de voz, difuso para os
  outros estados. Mesma fonte.
- **Forma circular e bordas arredondadas** como linguagem geral, com "pensamento" representado por forma
  fluida, não por spinner. Mesma fonte.
- **Princípios declarados**: "perdoar erros", antecipar confusão, linguagem clara, sinais transparentes.
  Mesma fonte.
- **Waveform de voz no Live (beta/teardown)**: a Google testa uma pílula inferior com forma de onda azul no
  lugar do indicador antigo; relatos de teardown dizem que ainda não está ativo para todos. Fontes:
  [Android Authority, teardown](https://www.androidauthority.com/gemini-overlay-live-neural-design-apk-teardown-3690991/),
  [Android Headlines, out/2026](https://www.androidheadlines.com/2026/10/google-tests-gemini-live-interface-mute-button.html).
  Tratar como não lançado.
- **Mapeamento de estados em biblioteca de terceiros** (orb-ui): microfone ativo → ouvindo; fim da fala do
  usuário ou texto do modelo em processamento → pensando; áudio na fila → falando. Útil como referência de
  máquina de estados, não como especificação do app da Google. [orb-ui.com/docs/adapters/gemini-live](https://orb-ui.com/docs/adapters/gemini-live).

### 2.6 Home Assistant Assist
- **Enum formal de quatro estados** do satélite de voz: `idle` (aguardando wake word ou botão), `listening`
  (transmitindo o comando), `processing` (entendendo o comando), `responding` (falando a resposta ou aviso).
  Os estados seguem os eventos pipeline automaticamente; a integração chama `tts_response_finished()` para
  voltar a `idle` após a fala. Fonte oficial:
  [contributors.home-assistant.io/core/entities/assist-satellite](https://contributors.home-assistant.io/core/entities/assist-satellite/).
  Esta é a fonte mais concreta de estados de voz que encontrei.
- **Pipeline visível em estágios** (wake word → STT → agente → TTS), com tela de depuração por etapa em
  Configurações > Assistentes de voz (citado por guia de comunidade, não verifiquei a tela).
  Fonte: [home-assistant.io/voice_control](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/)
  mostra a configuração e a opção "STT/TTS local" sem enviar dados externos; a página não descreve indicadores visuais.
- **Privacidade como escolha de provedor**: o caminho local mantém voz no hardware; a nuvem é alternativa
  explícita. Mesma fonte.

### 2.7 Alexa app e Alexa+
- **Chat como botão flutuante** em todas as telas, abrindo tela cheia com respostas visuais e sugestões de
  prompt. Fonte (imprensa): [aboutamazon.com, redesign do app](https://www.aboutamazon.com/news/devices/alexa-app-redesign).
- **Quatro padrões de componente** do Alexa+ (lista, carrossel, cartão, mapa): não inventar outros, porque o
  usuário aprende a ler esses formatos. Um cartão é uma entidade com imagem e ação opcional; tocar no corpo
  abre a visão detalhada, tocar no botão de ação executa. Botão de ação só para ação que completa uma tarefa
  ou leva adiante. Fonte oficial de desenvolvedor:
  [developer.amazon.com, Design Guide](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-components-and-patterns).
- **Crítica documentada**: um texto de opinião diz que tarefas simples passaram a exigir até seis toques
  (ex.: adicionar item à lista) e que há conteúdo promocional na interface. Opinião, não medição.

### 2.8 KRunner (Plasma 6)
- **Busca a partir do primeiro caractere**, com correspondência difusa (erro de digitação ainda acha o app)
  e ordem de resultados melhorada. Fonte: [kde.org, Plasma 6.5](https://kde.org/announcements/plasma/6/6.5.0/).
- **Navegação entre categorias de resultado** por teclado (PgUp/PgDn e Ctrl+cima/baixo). Fonte: notas da
  Plasma 6.3 citadas em resumo; não abri a nota original.
- **Resultado rico no próprio campo**: no Plasma 6.4, digitar uma cor em hex ou nome CSS mostra a amostra e
  equivalentes em outras notações. Fonte: [kde.org, Plasma 6.4](https://kde.org/announcements/plasma/6/6.4.0/).
- O Plasma Handbook que encontrei é de versão antiga (Plasma 5.20); não usei para padrões atuais.

### 2.9 Contraste: Humane AI Pin e Rabbit R1
- Crítica recorrente: voz como interface principal tinha pouca precisão e pouca confiança; demo prometia
  ações que o produto não fazia de forma confiável; agentes quebravam quando a interface de um app mudava.
  Fontes: [digitalapplied.com](https://www.digitalapplied.com/blog/ai-product-failures-2026-sora-humane-rabbit-lessons),
  [trustedpens.com](https://trustedpens.com/rabbit-r1-and-ai-pin-new-era-of-smart-devices/),
  [swarajyamag.com](https://swarajyamag.com/technology/reviews-are-in-new-age-ai-devices-humane-ai-pin-and-rabbit-r1-are-flopping).
- Números de usuários ativos citados em blogs não verifiquei; não os repito como fato.

## 3. Fatos transversais (com confiança)

- Estados de voz convergem em 4: parado / ouvindo / processando / falando (Home Assistant). Gemini e orb-ui
  seguem a mesma lógica com nomes diferentes.
- Confirmação de ação de risco: rodar a ação só após aprovação, com a entrada visível, e cancelamento sem efeito
  (Raycast).
- Teclado primeiro com Enter para enviar, Esc para sair e uma tecla que abre o painel de ações (Raycast,
  Alfred).
- Sugestões de prompt aparecem no estado vazio de chat (Alexa). Não verificado no Raycast.

## 4. Padrões a adotar no Gideon

Ligados ao `docs/UI_DESIGN.md`. Os valores de tempo são **propostas** para validar em protótipo, não medidas.

1. **Um estado dominante por vez.** A faixa do Início mostra uma frase curta ("Pronto para ouvir",
   "Ouvindo…", "Pensando…", "Falando…") e o orbe; o resto da tela não compete. Base: estados do Home Assistant.
2. **Máquina de estados canônica de 4 estados** (`idle`, `listening`, `processing`, `responding`) no Core e na UI,
   com os mesmos nomes em logs e no QML. Facilita teste e evita estados órfãos. Base: enum HA.
3. **Transição de estado curta.** Proposta: 180–250 ms para troca de cor ou frase, curva de saída (ease-out).
   Nada de animação que não mude informação.
4. **Escuta com ondulação radial, não com spinner.** Proposta: anel ou gradiente radial que expande a partir do
   orbe em ~1,2–1,6 s por ciclo, só enquanto o microfone capta. Base: Gemini (radial para voz).
5. **Processamento com movimento interno lento**, não com giro. Proposta: pulso de 2 s, amplitude pequena.
   Base: Gemini ("movimento interno sugere pensamento").
6. **Ocioso sem animação contínua.** Proposta: orbe parado (ou respiração muito lenta, 6 s+) para não consumir
   atenção nem bateria. Mantém o princípio de "uma pergunta por página".
7. **Atalhos com convenção de launcher.** Enter envia, Shift+Enter quebra linha, Esc fecha ou cancela escuta,
   Ctrl/Cmd+K abre ações do item selecionado, Ctrl+M liga e desliga o microfone. Base: Raycast.
8. **Resposta longa recolhida.** Acima de cerca de 10 linhas, mostrar as primeiras e "Mostrar mais". Base: Raycast.
9. **Tela de resultado como cartão de uma entidade**, com ação de corpo e ação de botão separadas; botão só
   para ação que conclui algo. Base: Alexa+ design guide. Encaixa na "linha de resultado" já prevista.
10. **Confirmação de ação de risco com a entrada visível**: o diálogo mostra exatamente o comando/argumento que
    será executado, com "Executar" e "Cancelar", e cancelar não deixa efeito. Base: Raycast (docs de
    ferramenta). Ações de risco nunca ficam em modo "Sempre permitir" por padrão.
11. **Três modos de permissão por capacidade**: "Perguntar", "Automático" (só rotinas de leitura), "Sempre permitir".
    Padrão "Perguntar". Base: Raycast. Casa com a página Permissões do `UI_DESIGN.md`.
12. **"Não perguntar de novo" ligado por padrão e reversível** em uma tela de avisos. Base: Raycast.
13. **Indicador de microfone ativo sempre visível, com texto.** Enquanto o microfone capta, a faixa de estado
    diz "Ouvindo" e mostra um indicador fixo. Para privacidade, a página Percepção mostra quem usou o mic
    recentemente (padrão da Apple, citado por guias de terceiros). Não verifiquei a especificação oficial da
    Apple sobre o indicador.
14. **Estado vazio com sugestões de comando** ("Tente: abrir Permissões", "Ver conexões"), não com marketing.
    Base: Alexa (chat com sugestões). Sem texto explicativo longo.
15. **Pergunta inline com múltipla escolha** quando o Gideon precisar de decisão, sem abrir modal. Base: Raycast.
    Encaixa em "Propostas de ferramenta".

## 5. Padrões a evitar

- **Clutter de cartões e marketing no início.** O próprio `UI_DESIGN.md` já corta o hero; manter. Alexa e
  Humane mostram o custo de telas que competem.
- **Animações sem informação** (brilho, partículas, orbe girando sem fim). Consomem atenção e bateria e
  não dizem nada sobre o estado.
- **Promessa acima do que funciona.** Humane e Rabbit prometeram ações que não funcionavam de forma confiável.
  Gideon deve manter os rótulos honestos já previstos ("SINTÉTICO", "UNSUPPORTED", "não verificado").
- **Mais toques para tarefa simples** (crítica à Alexa). Atalho e comando por voz devem resolver a tarefa em
  um passo quando possível.
- **Sugestões externas misturadas por padrão.** Sugestões do Spotlight sobre web são opt-out e confundem
  o que é local. No Gideon, dados externos (Wikipédia, web) só entram com ação do usuário e com rótulo.
- **Confirmação por padrão aprovada em massa** ("Sempre permitir" como padrão, ou diálogo que não mostra o
  que será feito). É a forma mais comum de ação indevida.
- **Ação de risco sem cancelamento claro.** O cancelamento tem que impedir a execução, não só fechar a janela.
- **Dark pattern de consentimento**: botão "Aceitar" grande e "Depois" pequeno, ou texto de privacidade
  enterrado. Usar escolha simétrica.
- **Depender só de cor** para estado (já proibido pelo `UI_DESIGN.md`: status = cor + palavra).
- **Voz como único caminho.** Toda ação por voz precisa de equivalente por teclado e por clique.

## 6. O que não consegui verificar

- **Apple HIG da Siri**: a página oficial existe, mas o corpo não foi lido pela ferramenta. Nenhuma regra da
  HIG está citada aqui como fato.
- **Google Assistant e app Alexa (estados visuais de escuta/processamento)**: não encontrei descrição oficial
  dos estados. Alexa aparece só em cartões e chat; a parte de "escutando" não foi verificada.
- **Indicador de microfone da Apple**: a página oficial de suporte não abriu; o que citei vem de guias de
  terceiros com informações conflitantes (ex.: se o ponto verde aparece junto com o laranja em câmera+mic).
- **OVOS, Mycroft e Rhasspy**: busca não trouxe nada sobre indicadores visuais de escuta. Não há padrão
  verificado desses projetos nesta pesquisa.
- **Onboarding e primeira execução** de todos os produtos: não encontrei fonte boa. Não tenho padrão
  documentado para essa parte.
- **Tratamento de erro offline** nos produtos (Raycast, Gemini, Alexa): não verificado.
- **Densidade e tipografia**: só há os tokens do próprio `UI_DESIGN.md`; não medi tipografia de nenhum produto.
- **Detalhes de tempo e animação** (valores da seção 4): são propostas, não copiadas de nenhum produto.
- **Changelogs e teardowns** de Raycast e Gemini mudam rápido; podem estar defasados.

## 7. Fontes consultadas

- Raycast: [manual AI Chat](https://manual.raycast.com/ai/ai-chat), [atalhos](https://manual.raycast.com/keyboard-shortcuts),
  [changelog](https://www.raycast.com/changelog), [API Tool](https://developers.raycast.com/api-reference/tool)
- Alfred: [Universal Actions](https://www.alfredapp.com/universal-actions/),
  [Why Choose Alfred](https://www.alfredapp.com/help/why-choose-alfred/), [cheatsheet](https://www.alfredapp.com/help/getting-started/cheatsheet/)
- Spotlight: [Spotlight on your Mac](https://support.apple.com/guide/imac/spotlight-apd10f8d1038/2024/mac/15),
  [Siri Suggestions](https://support.apple.com/en-mide/guide/mac-help/turn-off-siri-suggestions-for-spotlight-mchl62db64f5/15.0/mac/15.0)
- Siri: [HIG Siri (sem corpo legível)](https://developers.apple.com/design/human-interface-guidelines/technologies/siri/introduction),
  [Pocket-lint](https://www.pocket-lint.com/how-to-get-new-siri-look-glowing-border/),
  [Softonic](https://en.softonic.com/articles/how-to-activate-siris-new-look-and-its-colorful-glow)
- Gemini: [design.google](https://design.google/library/gemini-ai-visual-design),
  [Android Authority teardown](https://www.androidauthority.com/gemini-overlay-live-neural-design-apk-teardown-3690991/),
  [Android Headlines](https://www.androidheadlines.com/2026/10/google-tests-gemini-live-interface-mute-button.html),
  [orb-ui](https://orb-ui.com/docs/adapters/gemini-live)
- Home Assistant: [Assist satellite (contributors)](https://contributors.home-assistant.io/core/entities/assist-satellite/),
  [Assist local](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/)
- Alexa: [redesign (Amazon)](https://www.aboutamazon.com/news/devices/alexa-app-redesign),
  [Design Guide Alexa+](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-components-and-patterns),
  [crítica (fonearena)](https://www.fonearena.com/blog/318400/amazon-alexa-update-new-ui-personalized-suggestions.html)
- KRunner: [Plasma 6.4](https://kde.org/announcements/plasma/6/6.4.0/), [Plasma 6.5](https://kde.org/announcements/plasma/6/6.5.0/)
- Contraste: [digitalapplied](https://www.digitalapplied.com/blog/ai-product-failures-2026-sora-humane-rabbit-lessons),
  [trustedpens](https://trustedpens.com/rabbit-r1-and-ai-pin-new-era-of-smart-devices/),
  [swarajyamag](https://swarajyamag.com/technology/reviews-are-in-new-age-ai-devices-humane-ai-pin-and-rabbit-r1-are-flopping)
- Apple, mic: [TapSmart](https://www.tapsmart.com/tips-and-tricks/privacy-indicators/) (terceiro)
