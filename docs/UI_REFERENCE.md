# Interface Qt — referências visuais aprovadas

O usuário aprovou aplicar as três imagens à interface Qt existente, mantendo
estados reais e controles sem backend indisponíveis. Fontes locais em docs/design.
Este trabalho adapta a S2 existente; não antecipa o instalador B3.2 nem reinventa
sessões, autorização, áudio ou modelos na UI.

- Sidebar com Início, Voz e Wake, Áudio, Aparência, Permissões, Diagnóstico e Hub.
- Azul/violeta, cards, esfera e textura reais, fontes locais Noto Sans, ícones
  Breeze com SVG fonte/PNG/aviso e licença em app/assets. Esfera/textura Image Gen
  guiadas pelas imagens do usuário, sem screenshot usado como UI funcional.
- Navegação de teclado, foco/hover/seleção. Janela ampla 1380x904 e compacta 480x520.
- Core continua dono do catálogo de wake, qualification, status, preferências,
  gain e rollback. Hey não é codificado como única frase na apresentação.
- Ajuste de ganho em Áudio usa FeedbackPreferences; templates de resposta continuam
  no Core. Sem acessar mixer/device/config do host. Física continua indisponível.
- Aparência: tema/cor são escolhas desta janela; indicador persistido pelo Core.
  Sem presets fictícios de engine, locutor, redução de ruído, idiomas ou hardware.
- Legenda/resultado da conversa concluída ficam no Início. Sessão ativa mantém
  legenda e Cancel em qualquer rota; estado/erros essenciais sempre disponíveis.
- Superfícies raster arredondadas usam QQuickPaintedItem/QPainter, compatíveis
  com renderer software; nenhum shader, timer de animação ou novo polling.

Gate: QA visual comparada às referências, navegação/viewport/cores/temas, native
wake→STT→comando→Pocket, ganho 50% e rollback acionados pela UI real, invalid config,
pack/Hub, cancel/offline/reconnect, regressões GUI anteriores, idle UI CPU medido.
Sem abrir sessão pessoal, microfone, saída física ou servidor/browser do usuário.

O redesign não representa conclusão física de S1/S2. B3.2 e demais gates seguem
na ordem anterior após esta adaptação visual solicitada pelo usuário.


## Resultado

AUTO_VERIFIED, commit 13cf997. QA visual design-qa.md: passed. Zero erros QML.
44 Rust/17 Python; 44 checks novos (incluindo navegação durante PCM real) e 305
regressões GUI/Core, zero failed/ignored. SHA release/Rust inalterados versus
B3.1: 5a1158a133128d80c66b4b91a6f30bbe78da1921ddb82c66fd2ed25f482d09dc.
Evidências/source/assets/refs em docs/evidence/ui-reference.json.

UI em repouso final: 0% CPU no intervalo de 3s e RSS 210.276.352 bytes, renderer
software/HiDPI após capturas. Não é limite garantido ou benchmark físico. Rodada
com três inferências simultâneas excedeu prazos em pack/Hub; repetição serial
passou, sem ampliar deadlines do Core. Essa contenção segue limitação conhecida.

Correções: Flow tinha implicitHeight read-only (usado Layout.preferredHeight),
contraste de campo desativado, viewport de configurações, clipping arredondado
software, agrupamento Tema/Cor e hierarquia de títulos. Harness usa árvore visual
para delegates QML e setas do Slider; não tenta transformar Home key em reset.

Nenhum Core/modelo/manifest de voz mudou. Próximo trabalho funcional permanece
B3.2, sem publicar ou executar código não confiável no host.
