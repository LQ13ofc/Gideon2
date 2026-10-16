# Design QA — interface Qt Gideon

**Source visual truth:** docs/design/reference-home.png,
reference-voice.png e reference-appearance.png (imagens aprovadas pelo usuário).
**Implementação:** target/evidence/design-home.png, design-voice.png,
design-appearance.png, design-audio.png e design-small_{0,1,3,6}.png.

**Viewport/densidade:** referência 1448x1086, janela ilustrada aproximadamente
1380x904 dentro do wallpaper/chrome; implementação cliente Qt 1380x904 a DPR 2,
2760x1808 pixels, e compacto 480x520 a DPR 2, 960x1040. Comparação por coordenadas
lógicas da área cliente, excluindo wallpaper e chrome ilustrados. Imagens fonte
e finais foram abertas juntas, em pares por tela; nenhuma imagem foi retocada
para simular funcionamento. Renderer Qt software em namespace offscreen privado.

**Estado:** referência conceitual marca motores/microfone ativos; implementação
usa Core real, replay autorizado e resultado verificado. Páginas capturadas após
S1 nativo, tema Gideon/azul e idioma UI PT. Mudanças de conteúdo/controle que
representam ausência de backend são intencionais e foram autorizadas no pedido.

**Findings e histórico de correção**

- [P1 resolvido] Campo desativado tinha placeholder quase preto no fundo azul.
  Corrigidos color/placeholderTextColor/background; home final tem contraste legível.
- [P2 resolvido] Conversa concluída reduzia o espaço de Voz/Aparência.
  Agora fica no Início; conversa ativa/Cancel continuam globais. Capturas finais
  de Voz/Aparência mostram cards completos e pequeno viewport com scroll.
- [P2 resolvido] Textura retangular expunha cantos sobre cards arredondados.
  QQuickPaintedItem recorta raster com QPainter/software, sem shader ou timers;
  cantos de hero/header conferidos nas capturas finais.
- [P2 resolvido] Tema/cor empilhados na janela ampla e títulos pouco destacados.
  Grid de duas colunas na janela ampla, empilhamento na compacta, títulos 60/52px.
  Captura final Aparência confere os grupos lado a lado; navegação small_3 passa.
- Nenhum P0/P1/P2 acionável permanece no escopo visual aprovado.

**Cinco superfícies de fidelidade**

- Tipografia: Noto Sans local verificada, corpo 14–22px, títulos 60/52px e compacto
  24px. Hierarquia/pesos/quebras legíveis; fonte da ilustração não foi declarada,
  logo Noto Sans é a adaptação nativa. Sem texto artístico usado como botão.
- Espaçamento/layout: sidebar 232px ampla/64px compacta, margens 24/14px,
  cards raio 20px, gaps 14–24px. Início reúne hero/estado/atalhos/conversa; Voz
  mantém frase/captura; Aparência tema/cor/HUD. Scroll preserva controles pequenos.
- Cores/tokens: navy #0c1730, superfícies #1c2e56→#111e38, azul #7693ff,
  violeta/ciano/rosa selecionáveis, texto #edf2ff/#b0c3e9. Foco/seleção/hover
  visíveis e controles sem capability ficam indisponíveis.
- Assets: esfera e textura Image Gen derivadas da referência; alpha da esfera
  verificado (canto 0), tamanhos originais preservados. Ícones Breeze licenciados,
  fonte SVG incluída e PNG escalável HiDPI. Nenhum placeholder artístico, shader
  procedural, screenshot como fundo de UI ou wave falsa de áudio ao vivo.
- Copy: greeting e nomenclatura lateral seguem a referência. Status vem do Core;
  sem afirmar microfone físico, resposta inteligente/LLM ou plugin instalado.
  Wake DEV/POC, áudio virtual e escolhas de aparência por janela são explícitos.

**Comparação de regiões**

Além das vistas completas, foram examinados os títulos/hero e bordas de textura,
sidebar/estado, seletores Tema/Cor e viewport compacto. Screenshots HiDPI mantêm
texto/controles legíveis nesses grupos; tema e cor mudam a janela de verdade.
O seletor de wake reflete o pack, com Okay bloqueado; gain por teclado salva no
Core e produz Pocket PCM 50%, seguido de rollback pela UI existente.

**Interações/evidências**

7 rotas por teclado, tema/cor, wake indisponível, ganho 50%/rollback, conversa real,
4 telas compactas com Cancel persistente, zero deltas idle e medição CPU/RSS da UI.
Nenhum erro QML na rodada final de design. Tests/benchmarks e source hashes ficam
em docs/evidence/ui-reference.json. Browser não se aplica à interface Qt; cliente
real capturado e operado com QtTest em HOME/XDG/bwrap privados.

A primeira rodada com três inferências simultâneas apresentou deadlines excedidos
em pack/Hub; limites do produto não foram alterados. A rodada final roda uma
instância nativa por vez. Isso não certifica latência sob contenção ou acústica.

**Follow-up polish (P3)**

- Refinar glow/tipografia multicolorida sem prejudicar renderer software/idle.
- Persistência de temas e alternativas de HUD só quando tiverem contrato próprio.
- Chrome/Wayland e qualidade acústica dependem dos gates físicos, sem teste humano
  intermediário nesta etapa.

**Implementation checklist:** correções aplicadas; referências e assets mantidos;
UI real testada; resultados e limites registrados; sem publicação ou sessão pessoal.

final result: passed


B3.2a review de permissões: diálogo real Qt offscreen/HiDPI em 640x520, scroll
e keyboard; acknowledgement desmarcado, botão bloqueado, aprovação persistida pelo
Core e duplicate desabilitado. Publisher continua não autenticado/nenhum instalado.
Aviso de aprovação separado de preferências e identifica o plugin; não reutiliza
resultado antigo ao abrir review. Screenshot target/evidence/b3-permissions.png.
Restart privado mantém aprovação e repete fluxo wake/STT/comando/Pocket. Nenhuma
qualificação física ou humana foi feita. Resultado: passed.


B3.2b staging: Hub Qt real distingue pacote opaco verificado de instalado;
progresso recebido/esperado e botão Cancelar importação vêm do Core. Cancel via
teclado remove transação e pending no daemon real. CLI offline importa fixture
autorizada, UI acompanha estado; restart privado revalida payload/approval e
repete S1 nativo. Screenshot target/evidence/b3-import.png em 640x520/HiDPI,
scroll sem controles de execução ou publisher autenticado. Browser não se aplica.
Qualidade física/relocação continuam pendentes; cliente gráfico de seleção de
pacotes ainda não é oferecido. Cancel exibe "Enviando cancelamento ao Core"
(antes reutilizava texto de aprovação). Rodada final: staging 76 (UI 9), zero
erros QML, design 44 e regressões Base no mesmo release. Resultado: passed.


B3.3 ciclo: Hub Qt real mostra instalado/desativado, Reverter versão (desabilitado
sem previous) e Remover com diálogo de confirmação; cancelar mantém registro,
confirmar remove no daemon e rótulo "Plugin removido". Restart preserva estado;
S1 nativo antes/depois. Screenshot target/evidence/b3-lifecycle.png. Clique de
instalar via Qt não dirigido ponta a ponta (install via CLI). Nenhuma qualificação
física ou humana. Resultado: passed.
