# Gideon App — direção de design (v2)

Objetivo: cada página diz o que importa, na ordem certa, e nada além. Hoje há páginas que falam demais
(Hub, Skills, Conexões, Modelos LLM, Permissões com texto corrido) e páginas que quase não dizem nada
(Voz e Wake, Áudio, Aparência, Percepção); o Início mistura marketing, status duplicado e conversa.

## Princípios

1. **Uma pergunta por página**: o título + subtítulo respondem "o que é isto"; o cartão do topo responde "como está agora"
   (faixa de resumo de 1 linha com badges); o resto responde "o que posso fazer".
2. **Orçamento de conteúdo**: no máximo 3 cartões visíveis por página; texto explicativo longo vai para um bloco
   recolhível "Como funciona" (recolhido por padrão, 1 linha de resumo visível). Nenhum parágrafo com mais de 2 linhas fora dele.
3. **Páginas esparsas ganham dados úteis já existentes** (nunca funções inventadas): valores atuais, estado, última ação, atalhos.
4. **Estados vazios com ação**: ícone + 1 frase + botão do próximo passo.
5. **Status = cor + palavra** (nunca só cor). Rótulos obrigatórios de honestidade ficam: SINTÉTICO, UNSUPPORTED, "não verificado",
   "SERVIDOR FALSO", "requer prova de conceito", "em desenvolvimento".
6. **Mesma anatomia**: cabeçalho (título, subtítulo, pílula de estado) → faixa de resumo → cartões → rodapé de ajuda. Ação primária à direita do cartão.
7. Tudo em português, PlainText para dados do Core, sem funções novas: só reorganizar o que existe.

## Tokens (iguais ao app atual)

Fundo #0b1530 / cartões #14224a→#101c40 com borda #263a73 (raio 14), texto #e8eeff, texto secundário #9db0e0,
acento #7693ff (variações violeta #b386ff, ciano #66dcf4, rosa #f28bd7), sucesso #5ee0a0, aviso #f2c15c, erro #ff7d8a.
Tipografia: Noto Sans; título de página 24 bold; título de cartão 17 semibold; corpo 14; legenda 12.
Sidebar 232 px (rail 60 px abaixo de 980 px de largura); área útil máx. 1100 px.

## Orçamento por página (o que mostrar / o que cortar)

1. **Início** — hierarquia única, de cima para baixo:
   (a) Faixa de estado: orbe pequeno (72 px) + frase grande do estado ("Pronto para ouvir", "Ouvindo…", "Falando…") + 1 linha
   "Wake: Hey Gideon · Entrada: PCM virtual · Modo: Base, sem LLM" como 3 chips clicáveis (levam às páginas);
   (b) Campo de comando em destaque ("Diga ou digite um comando", Enviar primário) com 1 dica de exemplo;
   (c) "Conversa recente": bolha Você / bolha Gideon + linha de resultado (cores de sucesso/erro);
   (d) Atalhos: 3 tiles (Voz e Wake, Áudio, Gideon Hub) com ícone e 1 linha;
   (e) nota de privacidade de 1 linha. CORTAR: texto de marketing do hero, cartão "Estado do sistema" (vai para Diagnóstico), três cartões com "Abrir".
2. **Conversa** — chat em tela cheia (mensagens + entrada), painel lateral recolhível "Agente" e "Propostas de ferramenta"; estado vazio com sugestões.
3. **Voz e Wake** — resumo (frase ativa + qualificação + estado); cartão "Frase de despertar" (opções como cartões selecionáveis lado a lado
   com badge de qualificação); cartão "Captura" (entrada, pré-roll, estado, limites honestos em 1 linha); "Como funciona" recolhível.
4. **Áudio** — resumo (saída, voz, volume); cartão "Volume da resposta" (slider grande + valor + Aplicar); cartão "Voz" (voz atual, estado); limites em "Como funciona".
5. **Aparência** — cartões lado a lado: Tema, Cor de destaque (amostras grandes), HUD visual; prévia ao vivo.
6. **Permissões** — resumo "N aprovadas · M pendentes"; lista tabela (capacidade, quem declarou, estado com badge, ação); estado vazio claro; texto corrido sai (vai para "Como funciona").
7. **Diagnóstico** — resumo (Core conectado, motores); cartão "Motores" (Wake, STT, TTS com badge); cartão "Estado do sistema" (movido do Início); log curto.
8. **Gideon Hub** — resumo (catálogo carregado / não configurado, N plugins); cartão catálogo em grade de cartões de plugin (nome, versão, badge de estado, ação primária); aviso de segurança em 1 linha + "Como funciona"; estado vazio com "Explorar catálogo".
9. **Skills** — resumo (N instaladas, N habilitadas); lista de skills (linha: nome, versão, badge estado, deps, ação); "Criar" e "Importar/Exportar" como botões no cabeçalho do cartão abrindo seções recolhíveis; execução e histórico em cartão próprio; "Como funciona" recolhível.
10. **Conexões** — resumo (N contas, N conectadas); cartões de conta (provedor, status, escopos como chips, ações); "Nova conta" recolhível; rotas em cartão separado; rótulo "SERVIDOR FALSO".
11. **Modelos LLM** — resumo (modelo atual + estado); lista de modelos como linhas com badge de certificação, filtro Local/Nuvem em segmentos; detalhes à direita ao selecionar; "Adicionar personalizado", "Fallback", "Hardware" recolhíveis.
12. **Percepção e ação** — cartão "Privacidade" no topo (indicadores mic/câmera); grade de cartões de plugin (estado, SINTÉTICO, permissão, ações de teste); resultado em painel inferior; C4.6 com selo UNSUPPORTED.

## Entrega em etapas

1. Mockups (SVG → PNG em `docs/ui-mockups/`, 1380×904) de cada página seguindo este documento.
2. Revisão dos mockups pelo dono.
3. Divisão de `app/Main.qml` em arquivos por página (mantendo objectName/ids/índices de página).
4. Implementação imitando cada mockup, com exploração visual real para comparar.
