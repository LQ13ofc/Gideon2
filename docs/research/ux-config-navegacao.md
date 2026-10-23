# Navegação e configurações em apps de design reconhecido

Pesquisa de referência para o Gideon: como apps bem avaliados organizam navegação e configurações quando têm muitas opções, mantendo a interface simples.

Data da pesquisa: 2026-10-23. Pesquisa somente leitura (WebSearch/WebFetch). Nenhum arquivo do repositório foi alterado além deste.

## 1. Método e limites da verificação

- Foram tentadas 8 fontes principais, escolhidas pela documentação pública disponível: VS Code, Obsidian, Home Assistant, KDE Plasma, GNOME, macOS (System Settings), Notion e Windows 11. Linear entrou como fonte parcial.
- Verificado com leitura direta da página: VS Code (settings), Home Assistant (Quick search), GNOME (dialogs, parcialmente), Obsidian (plugins, via resultado de busca e página oficial).
- Verificado só por resumos de notícia ou busca (sem a página oficial lida): macOS Ventura (imprensa de 2022), KDE "Highlight Changed Settings" (blog e guias), Notion (central de ajuda, sem lista completa de seções), Windows 11 (imprensa e Microsoft Learn de navegação genérica).
- Não consegui verificar: página oficial de settings do Apple HIG (a página abriu só com o título), a página "Preferences" do GNOME HIG (404 na URL tentada), o guia de settings do KDE HIG (a página abriu sem conteúdo de configuração), a documentação atual de atalhos do Linear (a documentação oficial encontrada é antiga, cerca de 5 anos) e a página de Windows Settings na Microsoft Learn.
- Não pesquisei em profundidade: Arc, 1Password, Tailscale, Bitwarden. Ficam fora desta versão.
- Quando algo veio só de terceiros (cheatsheets, blogs), está marcado como tal.

Ponto de atenção: a pesquisa não conseguiu confirmar a versão exata de cada UI. Antes de copiar um padrão literalmente, conferir a versão atual do app.

## 2. Análise por produto

### 2.1 VS Code (Settings editor)

Fonte principal: https://code.visualstudio.com/docs/getstarted/settings (lida diretamente).

Arquitetura de informação:
- Editor de settings com busca no topo, aberto com Ctrl+, (modal por padrão; pode virar aba).
- Escopos em abas: User e Workspace. Há também escopos de pasta e de linguagem. A precedência é explícita: default < user < remote < workspace < pasta < linguagem, com policy acima de tudo.
- Busca com filtros por prefixo: `@ext`, `@feature`, `@lang`, `@tag`, `@id`, `@haspolicy`, `@modified`. A busca aceita filtro e texto livre.

Progressive disclosure:
- Há um atalho para o modo JSON: o usuário pode definir que o menu de settings abra o arquivo `settings.json` diretamente. Ou seja, a UI simples e o modo texto convivem; o JSON é a saída para quem quer controle total.
- Settings de cor com link "Edit in settings.json" dentro do editor visual.

Modificados e reset:
- Barra colorida à esquerda de cada setting alterado. O filtro `@modified` lista tudo que difere do default ou foi definido explicitamente.
- Engrenagem ao passar o mouse, com a ação "Reset Setting". No JSON, apagar a entrada restaura o default.

Perfis:
- Profiles agrupam conjuntos de personalizações e permitem trocar entre eles. Cada profile tem seu próprio arquivo de user settings.
- Settings Sync é separado (sincroniza entre máquinas). Não encontrei exportação/importação manual de settings como recurso dedicado na página lida.

Comandos:
- Ctrl+Shift+P abre a paleta de comandos, que também expõe comandos como "Preferences: Open User Settings (JSON)". Não confirmei Ctrl+K para settings nesta fonte.

Aplicação: instant apply. Não há botão Salvar; a mudança vale ao ser feita.

### 2.2 Obsidian (Settings e community plugins)

Fontes: https://obsidian.md/help/plugin-security e https://obsidian.md/help/community-plugins (via busca; a página mudou de help.obsidian.md para obsidian.md/help). Verificado por snippet de busca, não pela página inteira.

Arquitetura de informação:
- Settings tem menu lateral; a seção "Community plugins" fica nele (confirmado pela documentação). Não verifiquei a lista completa de seções.

Segurança como progressive disclosure:
- Restricted mode vem ativo por padrão. Plugins instalados continuam no cofre, mas são ignorados enquanto o modo está ativo.
- Para liberar, há um botão "Turn on community plugins" na seção própria. A documentação avisa que plugins rodam código de terceiros e pede cautela.
- O próprio Obsidian afirma que não consegue restringir plugins a permissões específicas. Isso justifica uma tela de aviso honesta, não uma falsa sensação de sandbox.

Aplicação: uma ação de "liberar código de terceiros" é separada da configuração comum e exige passo explícito.

### 2.3 Home Assistant (Quick search)

Fonte: https://www.home-assistant.io/docs/tools/quick-search/ (lida diretamente).

- Um único ponto de entrada: Ctrl+K (Windows/Linux) ou Cmd+K (macOS) abre a busca rápida.
- Atalhos de filtro por letra: "e" para entidades, "d" para dispositivos, "c" para a paleta de comandos, "m" para My links, "a" para Assist. Cada um abre a busca já filtrada.
- Resultados: entidade abre o diálogo "More info"; dispositivo abre a página de detalhes.
- A lista de comandos depende das configurações do usuário e das integrações carregadas. Comandos e navegação para itens da barra lateral e para settings aparecem na mesma lista.
- Há opção para desligar todos os atalhos de teclado por navegador em "User profile > This browser". Isso é um detalhe útil: atalhos globais precisam de um interruptor.
- Observação: uma fonte secundária (How-To Geek) diz que na versão 2026.2 a "Quick bar" virou "Quick search" com abas (Navegar, Comandos, Entidades, Dispositivos, Áreas). Não verifiquei a versão exata da mudança na documentação oficial.

Aplicação: a paleta única com prefixos de filtro é o padrão mais próximo do que o Gideon precisa para "ir para qualquer página ou configuração".

### 2.4 KDE Plasma (System Settings)

Fontes: https://kde.org/announcements/plasma/6/6.3.0/ , https://pointieststick.com/2020/08/14/this-week-in-kde-highlight-changed-settings-and-much-much-more/ , https://www.howtogeek.com/i-stopped-getting-lost-in-kdes-settings-after-finding-these-simple-shortcuts/ , https://userbase.kde.org/System_Settings (busca; lidos parcialmente). O guia de HIG do KDE (https://develop.kde.org/hig/) não trouxe conteúdo sobre settings.

- Sidebar com categorias (módulos) e páginas dentro de cada módulo. A barra lateral é o mecanismo principal de navegação.
- "Highlight Changed Settings": opção no menu principal que marca módulos, páginas e settings que diferem do default. A marca é um ponto preenchido ao lado do item. Presente desde o Plasma 5.20 (2020); no Plasma 6 o suporte está sendo estendido página a página.
- Limitação conhecida: houve correção de categoria vazia na sidebar quando o destaque estava ativo (changelog do Plasma 6.6.5). Ou seja, o recurso é útil mas ainda tem arestas.
- Busca global de settings existe, mas não confirmei o comportamento exato da busca no Plasma 6.

Aplicação: o "destaque de alterados" aparece em três níveis (módulo, página, item). Isso ajuda a achar algo que você mudou há meses.

### 2.5 GNOME (Settings / preferências)

Fontes: https://developer-old.gnome.org/hig/stable/dialogs.html.en (resultado de busca) e https://developer.gnome.org/hig/patterns/feedback/dialogs.html (lida parcialmente). A página "Preferences" atual não foi acessível.

- Regra geral: instant apply é o padrão preferido. Explicit apply (botão Aplicar/OK) só quando várias mudanças precisam valer juntas para não deixar o sistema em estado instável, ou quando a aplicação leva tempo perceptível.
- Switches para opções binárias; checkboxes para seleção em listas. Quando um recurso está indisponível, o switch fica insensível, não escondido.
- Diálogos de ação: botão de ação com verbo específico (ex.: "Remover conta"), e não "OK" ou "Concluído". O botão de cancelar vem primeiro e Esc o ativa.
- Preferências devem persistir entre sessões (orientação do wiki de planejamento de configuração).

Aplicação: esta é a referência mais forte para o modelo "instant apply por padrão, com exceção documentada".

### 2.6 macOS (System Settings, Ventura+)

Fontes: https://www.macrumors.com/2022/06/06/macos-ventura-system-settings-app/ e https://9to5mac.com/2022/06/06/macos-13-ventura-system-settings-first-look/ (imprensa, 2022). Página oficial do Apple HIG sobre settings abriu só com o título, então o que está aqui é de imprensa.

- Sidebar à esquerda com as categorias; painel à direita. Modelo copiado do Settings do iPhone/iPad.
- Busca movida para o topo da sidebar; os resultados aparecem na própria sidebar, não destacando a seção como no System Preferences antigo. O resultado escolhido fica visível e a busca não precisa ser refeita.
- Muitos itens foram reagrupados (ex.: Itens de Início de Sessão foram para Geral). Críticos dizem que isso prejudica usuários antigos. Lição: reorganizar sem transição custa confiança.
- Checkboxes trocados por toggles em muitos casos.
- Limitação: não dá para reordenar ou remover itens do painel.

Aplicação: a busca na própria sidebar, com resultados que não somem ao clicar, é o padrão a copiar.

### 2.7 Notion (Settings e Members)

Fontes: https://www.notion.com/help/workspace-settings e https://www.notion.com/help/add-members-admins-guests-and-groups (busca; lidos parcialmente).

- Settings fica na sidebar, com abas (General, Members, Guests etc.).
- Muitas opções só aparecem para quem tem permissão (admin/owner) ou em planos específicos. Membros não veem o que não podem mudar.
- A página de settings do workspace tem busca que casa palavras exatas no nome, na descrição ou na página onde o item está.
- Os nomes da seção mudam conforme plano e idade do doc (Settings & members, Settings → People, Settings → Members). Isso é um aviso sobre nomenclatura inconsistente.

Aplicação: esconder o que o perfil não pode alterar, em vez de mostrar tudo desabilitado. Ao mostrar desabilitado, dizer o motivo.

### 2.8 Windows 11 (Settings)

Fontes: resultados de busca (https://www.howtogeek.com/738486/heres-what-windows-11s-settings-app-looks-like/ e Microsoft Learn sobre NavigationView: https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/navigationview). Não encontrei a página oficial de design do Settings app. Este item é o mais fraco da lista.

- Sidebar à esquerda com seções; painel à direita. Breadcrumbs para ir em profundidade.
- Busca com popup de resultados; se não couber, "mostrar todos os resultados" abre a lista no painel principal.
- Conta do usuário fica fora da lista normal, acessada pelo nome no canto superior.
- Orientação genérica da Microsoft (fonte de terceiros que espelha o padrão): top navigation para até cinco categorias de mesmo peso, navegação lateral para cinco a dez. Não confirmado na página oficial.

## 3. Padrões transversais (síntese)

| Tema | Padrão mais comum | Exemplo |
|---|---|---|
| Estrutura | Sidebar de categorias + painel | KDE, macOS, Windows 11, Notion |
| Busca | Campo no topo com resultados que levam direto ao item | VS Code, macOS, Notion, Home Assistant |
| Destaque de alterados | Marcador visual + filtro "modificados" | VS Code (barra + `@modified`), KDE (ponto) |
| Reset | Por item (engrenagem/menu) e global via arquivo | VS Code |
| Aplicação | Instant apply por padrão; Aplicar só em exceção | GNOME, VS Code |
| Paleta de comandos | Ctrl+K / Cmd+K ou Ctrl+Shift+P | VS Code, Home Assistant |
| Avançado | JSON como saída, ou seção própria com aviso | VS Code, Obsidian |
| Segurança | Ação separada e explícita para liberar código de terceiros | Obsidian |

## 4. Padrões a adotar no Gideon

1. Campo de busca de configurações no topo da área de settings, com resultados que levam direto ao item (e a seção abre com o item destacado).
2. Paleta Ctrl+K (Cmd+K no macOS) que leva a qualquer página ou setting. Inspirada no Home Assistant, com prefixos de filtro: `p:` página, `s:` setting, `c:` comando.
3. Indicador "modificado" (barra à esquerda, como no VS Code) em cada setting que difere do padrão.
4. Filtro "Somente modificados" na área de settings, para revisão rápida.
5. Reset por item (ação "Restaurar padrão" no menu do setting) e reset global da seção, com confirmação.
6. Toggle "Mostrar avançado" por seção. As opções avançadas ficam ocultas por padrão, e a tela avisa quantas existem ocultas.
7. Descrição curta por setting: rótulo + uma linha de ajuda, sem parágrafo. Se precisar de mais, um link para detalhe.
8. Instant apply para toggles e seleções simples. Botão "Aplicar" só quando um conjunto de mudanças precisa valer junto (ex.: caminho de banco + credenciais). Esse caso deve ser marcado na tela.
9. Mostrar em destaque, perto do título da página, o número de mudanças pendentes quando houver Aplicar pendente, com botão "Descartar".
10. Exportar e importar settings por perfil: arquivo JSON com a seção do perfil. Excluir segredos da exportação e avisar disso na tela.
11. Perfis de configuração: um perfil ativo com a opção de criar, duplicar e trocar, como no VS Code Profiles.
12. Modo "Editar como JSON" para quem quer controle total, com validação no salvar. Só para usuário avançado, escondido atrás de um toggle.
13. Zona de perigo separada no fim da página: apagar dados, redefinir tudo, sair de conta. Ação com nome específico ("Apagar perfil X") e confirmação digitando o nome, não um "OK".
14. Estado vazio útil: quando a busca não acha nada, mostrar a frase exata buscada e sugestões (ex.: "Você quis dizer..."), e um link para os logs ou documentação.
15. Atalhos de teclado com interruptor global (desligar atalhos neste navegador), como no Home Assistant.
16. Navegação por teclado completa: setas na sidebar, Tab para o painel, Esc fecha paleta e volta o foco ao elemento anterior.
17. Permissão antes de mostrar: itens que o perfil não pode mudar ficam ocultos; se estiverem visíveis, mostrar o motivo no próprio item.
18. Badge de "configuração obrigatória pendente" na sidebar, para o que precisa de atenção (como o "destaque" da KDE, mas para o que falta).

## 5. Padrões a evitar

- Reorganizar a lista de settings sem aviso ou transição. A mudança da Apple no Ventura gerou reclamação de usuários antigos.
- Ocultar a busca dentro de um menu. Em todas as fontes lidas, a busca fica visível no topo ou na sidebar.
- Botão "OK" ou "Concluído" em diálogo de ação. Usar verbo específico.
- Misturar Aplicar e instant apply na mesma tela sem marcar qual é qual. Quem muda um campo e não vê efeito perde confiança.
- Mostrar tudo desabilitado sem explicação. Ou esconder, ou explicar.
- Destaque de alterados só em um nível (ex.: só na sidebar). A KDE mostra em módulo, página e item, e mesmo assim ainda tem bugs de categoria vazia.
- Exportar segredos (tokens, senhas) no arquivo de settings.
- Liberar código de terceiros com um único clique em tela de configuração comum. O Obsidian separa isso e avisa.
- Atalho global sem como desligar. Pode conflitar com digitação em campos.
- Confiar em nomes de seção fixos para documentação. A Notion mudou nomes conforme plano; usar identificadores estáveis na URL e no código.

## 6. Pendências e lacunas

- Confirmar na documentação atual do Linear se o atalho Cmd/Ctrl+K abre settings. Só achei fonte antiga e cheatsheets de terceiros.
- Confirmar no Apple HIG (página de Settings) a orientação de instant apply e de quantidade de itens. Só tenho o que a imprensa descreveu e uma paráfrase de conhecimento geral, sem verificação.
- Confirmar a página "Preferences" atual do GNOME HIG. A URL tentada deu 404.
- Confirmar o comportamento da busca de settings no KDE Plasma 6.
- Para Arc, 1Password, Tailscale, Bitwarden: nada verificado nesta rodada.

## 7. Fontes

- VS Code, settings: https://code.visualstudio.com/docs/getstarted/settings
- VS Code, profiles (mencionado na mesma página): https://code.visualstudio.com/docs/getstarted/settings
- Obsidian, plugin security: https://obsidian.md/help/plugin-security
- Obsidian, community plugins: https://obsidian.md/help/community-plugins
- Home Assistant, Quick search: https://www.home-assistant.io/docs/tools/quick-search/
- KDE, Plasma 6.3: https://kde.org/announcements/plasma/6/6.3.0/
- KDE, Highlight Changed Settings (2020): https://pointieststick.com/2020/08/14/this-week-in-kde-highlight-changed-settings-and-much-much-more/
- KDE, guia de usuário (Highlight changed settings, dica): https://www.howtogeek.com/i-stopped-getting-lost-in-kdes-settings-after-finding-these-simple-shortcuts/
- KDE, System Settings (UserBase): https://userbase.kde.org/System_Settings
- GNOME HIG, dialogs: https://developer.gnome.org/hig/patterns/feedback/dialogs.html
- GNOME HIG, dialogs (stable antigo, com instant apply): https://developer-old.gnome.org/hig/stable/dialogs.html.en
- GNOME HIG, switches: https://developer.gnome.org/hig/patterns/controls/switches.html
- GNOME HIG, checkboxes: https://developer.gnome.org/hig/patterns/controls/checkboxes.html
- macOS Ventura, reportagem MacRumors: https://www.macrumors.com/2022/06/06/macos-ventura-system-settings-app/
- macOS Ventura, reportagem 9to5Mac: https://9to5mac.com/2022/06/06/macos-13-ventura-system-settings-first-look/
- Apple HIG, Settings (título apenas, não lido): https://developer.apple.com/design/human-interface-guidelines/settings
- Notion, workspace settings: https://www.notion.com/help/workspace-settings
- Notion, membros e grupos: https://www.notion.com/help/add-members-admins-guests-and-groups
- Windows 11 Settings, visão geral (How-To Geek): https://www.howtogeek.com/738486/heres-what-windows-11s-settings-app-looks-like/
- Microsoft Learn, NavigationView: https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/navigationview
- Linear, "Select issues" (documentação antiga): https://linear.app/docs/select-issues

## 8. Os 5 padrões de maior valor para o Gideon

1. Paleta Ctrl+K com busca de páginas e settings (Home Assistant, VS Code). Um único ponto de entrada resolve o problema de "onde fica isso".
2. Indicador de modificado + filtro "somente modificados" + reset por item (VS Code, KDE). Permite revisar o que o usuário mudou sem vasculhar tudo.
3. Instant apply por padrão, com Aplicar só quando um grupo de mudanças precisa valer junto (GNOME). Reduz botões e explica quando o botão existe.
4. Ação separada e explícita para liberar algo perigoso, como código de terceiros (Obsidian). Serve também para a zona de perigo do Gideon.
5. Exportar/importar por perfil com exclusão de segredos (VS Code Profiles, complementado pela lição do Obsidian sobre segurança).
