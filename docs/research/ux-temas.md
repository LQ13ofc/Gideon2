# Pesquisa UX: sistemas de temas flexíveis e coerentes

Status: pesquisa de leitura. Nenhum arquivo do repositório foi alterado, exceto este documento. Data da pesquisa: outubro de 2026.

Legenda de confiança:
- **[F]** verificado em fonte que abri nesta sessão.
- **[S]** visto só em resultado de busca (trecho da página, não o texto completo).
- **[K]** conhecimento prévio, não verificado nesta sessão. Conferir antes de usar.

---

## 1. Resumo executivo

Os sistemas de tema mais elogiados por equilibrar flexibilidade e coerência têm três traços comuns:

1. Definem cores por **papel semântico** (fundo, superfície, texto, destaque, erro), não por cor bruta. Mudar o papel muda tudo que o usa.
2. Expõem **poucos controles básicos** (modo, cor de destaque, densidade, fonte) e deixam o resto em um nível avançado.
3. Validam o resultado: o tema é recalculado ou rejeitado quando não atinge o contraste mínimo.

Os 5 padrões mais valiosos para o Gideon:

1. **Tokens por papel** (`bg`, `surface`, `text`, `accent`, `onAccent`...), com `on*` sempre emparelhado ao papel que ele cobre. Ver seção 6.
2. **Acento como único controle de cor básico**; o resto da paleta é derivado ou vem de preset. Reduz combinações inválidas.
3. **Validação de contraste na entrada** (WCAG 2.1 AA): texto 4,5:1, componentes e bordas 3:1. Reprovar ou corrigir automaticamente. Ver seção 6.3.
4. **Níveis de configuração** separados em básico e avançado, com faixas numéricas fixas. Ver seção 6.2.
5. **Tema como arquivo JSON versionado** (`schemaVersion`), importável e exportável, com preview ao vivo antes de salvar. Ver seção 5.

---

## 2. Como cada sistema define um tema

### 2.1 Material 3 / Material You (dynamic color)

- Papéis de cor: `primary`, `onPrimary`, `primaryContainer`, `onPrimaryContainer` (o mesmo para `secondary` e `tertiary`), `error`/`onError`/`errorContainer`, `background`/`onBackground`, `surface`, `surfaceVariant`, `onSurfaceVariant`, `outline`, `outlineVariant`, `inverseSurface`, `inverseOnSurface`, `inversePrimary`, `surfaceTint`, `scrim`, e a família `surfaceContainerLowest`, `surfaceContainerLow`, `surfaceContainer`, `surfaceContainerHigh`, `surfaceContainerHighest`. [S] Fontes: [Flutter, nota de migração de papéis](https://docs.flutter.dev/release/breaking-changes/new-color-scheme-roles) e [Android, Color.md](https://github.com/material-components/material-components-android/blob/master/docs/theming/Color.md).
- O Flutter marca `background`, `onBackground` e `surfaceVariant` como depreciados e manda migrar para a família `surfaceContainer*`. [S] Mesma fonte.
- Cada papel é um **tom** de uma paleta tonal (escala 0 a 100, por matiz e croma). Valores de referência citados no Android: `onSurfaceVariant` tom 30 no claro e 80 no escuro; `surfaceContainer` tom 94 no claro e 12 no escuro. [S] Mesma fonte Android.
- Padrão geral citado em guia secundário: primário no tom 40 (claro) e 80 (escuro); superfícies neutras nos tons 99 e 10. [S] [guia softaai](https://softaai.com/material-3-colorscheme-explained-how-dynamic-color-works/). Conferir com a referência oficial de tokens.
- Papel de contorno: `outline` para bordas que precisam ser vistas; `outlineVariant` para divisores decorativos. [S] Mesmo guia secundário.
- Não consegui abrir a página oficial m3.material.io (a leitura voltou só o título). Valores de tom ficam como [S].

**Lição para o Gideon:** o nome do papel já diz para que serve (`onSurfaceVariant` = texto sobre `surfaceVariant`). Adotar essa convenção de par `on*`.

### 2.2 VS Code (workbench colors e token colors)

- Duas camadas separadas: **cores de workbench** (chave pontilhada, ex.: `editor.background`, `sideBar.background`, `focusBorder`, `button.background`) e **cores de token** (sintaxe, vindas do tema ativo). [F] [VS Code, theme color](https://code.visualstudio.com/api/references/theme-color)
- Valores em hexadecimal `#RGB`, `#RGBA`, `#RRGGBB` ou `#RRGGBBAA`. Algumas chaves são cores-base que valem só quando o componente não define a sua (ex.: `focusBorder`, `foreground`). [F] Mesma fonte.
- Personalização do usuário por `workbench.colorCustomizations` (sobrescreve o tema ativo) e `editor.tokenColorCustomizations`. As cores também viram variáveis CSS em webviews. [F] Mesma fonte.
- Limitação observada: `window.activeBorder` e `window.inactiveBorder` só valem em macOS e Linux com barra de título customizada. [F] Mesma fonte. Padrão útil: documentar exceções por plataforma.

**Lição:** o tema é um mapa de chaves para valores, com sobrescrita parcial. Isso permite que um tema de terceiros mude só algumas chaves.

### 2.3 Obsidian (CSS variables e snippets)

- A interface é construída sobre variáveis CSS. Sobrescrever essas variáveis é o caminho recomendado. Variáveis gerais em `body`, variáveis de cor em `.theme-light` / `.theme-dark`. [S] [Theme guidelines](https://docs.obsidian.md/Themes/App+themes/Theme+guidelines)
- O guia desaconselha `!important`, porque ele impede que snippets do usuário sobrescrevam o tema. [S] Mesma fonte.
- Snippets são arquivos `.css` locais, ativados em Configurações → Aparência → Snippets CSS. Como CSS inválido falha em silêncio, a ajuda recomenda validar. [S] [Ajuda: snippets](https://obsidian.md/help/snippets)
- Escopo por nota com `cssclasses` no frontmatter. [S] [Fórum Obsidian](https://forum.obsidian.md/t/using-cssclasses-in-snippets/100577)
- Não encontrei a lista completa de variáveis na página oficial dentro desta sessão. Um resumo gerado por terceiros está em [DeepWiki](https://deepwiki.com/obsidianmd/obsidian-developer-docs/3.3-css-variables-reference) e deve ser conferido.

**Lição:** a extensão é uma camada de variáveis públicas e estáveis. Quem quer ir além escreve CSS. Para o Gideon, o equivalente é expor tokens documentados e não deixar o usuário mexer em seletores internos.

### 2.4 KDE Plasma (color schemes, Breeze, accent, Global Themes)

- Esquema de cores é um arquivo de seções como `Colors:Window`, `Colors:View`, `Colors:Selection`, `Colors:Tooltip`. [K] Não consegui abrir a página de referência com o texto; a página aberta era um índice. Confirmar nomes exatos em `develop.kde.org`.
- Uma cor de destaque pode vir do papel de parede. A partir do Plasma 5.25, há opção de gerar o destaque a partir do papel de parede e trocá-lo quando o papel muda. [S] [Debug Point, Plasma 5.25](https://debugpointnews.com/plasma-accent-colour-wallpaper-5-25/)
- Autor de papel de parede pode definir uma cor de destaque por metadado (`X-KDE-PlasmaImageWallpaper-AccentColor`), com valores separados para claro e escuro. [S] Trecho de busca em [wallpapers do KDE](https://develop.kde.org/docs/plasma/wallpapers/); não abri a página completa.
- Problema relatado: ao definir a cor de destaque por linha de comando, o cálculo a partir do papel de parede pode não ocorrer, diferente da interface gráfica. [S] [KDE Discuss](https://discuss.kde.org/t/set-the-type-of-accent-color-via-cli-from-theme-wallpaper-custom/3770)
- Relatado em bug: o destaque pode não aparecer em painéis e widgets se o estilo do Plasma não "segue o esquema de cores". [S] [KDE bug 444043](https://bugs.kde.org/show_bug.cgi?id=444043)
- Global Themes agrupam esquema, estilo do Plasma, ícones, cursor e papel de parede. [K] Não verificado nesta sessão.

**Lição:** o acento pode ser fixo ou derivado de uma fonte externa (papel de parede). A opção "derivar" precisa ser explícita e ter fallback.

### 2.5 GNOME / libadwaita (accent e modo claro/escuro)

- [F] As duas páginas de diretrizes de cor de destaque do GNOME devolveram 404 (não foram lidas). Não consegui verificar a lista oficial de cores de destaque nem a regra de contraste.
- [K] libadwaita oferece preferência de esquema (claro, escuro ou seguir o sistema) e um conjunto nomeado de cores de destaque (azul, verde, amarelo, laranja, vermelho, roxo, rosa, cinza). Confirmar antes de citar.

### 2.6 macOS (accent e highlight)

- [K] `NSColor.controlAccentColor` é uma cor dinâmica escolhida pelo usuário nas Preferências do Sistema. Apps devem usar essa cor e não um azul fixo, e redesenhar quando a aparência muda. A cor de realce (highlight) é uma configuração separada, usada para seleções.
- [F] A página da Apple abriu só com o título; o texto acima não foi confirmado na fonte.
- Ponto de contraste: o usuário pode escolher acento de baixo contraste. A diretriz geral é não depender só da cor para transmitir significado. [K]

### 2.7 Arc (spaces e boosts)

- Cada Space tem paleta própria (cor ou gradiente), editável pelo ícone de pincel ao lado do nome ou por "Editar tema" no comando rápido. [S] [página de Arc](https://start.arc.net/paint-the-internet) e [SlashGear](https://www.slashgear.com/1634601/best-arc-browser-features/)
- Boosts restilizam um site específico (cores e fontes), e um site pode ter mais de um boost, ligados ou desligados com um clique. [S] [TechCrunch](https://techcrunch.com/?p=2549048) e SlashGear.
- Observação: as fontes são antigas (o SlashGear tem cerca de dois anos e o TechCrunch fala em acesso por convite). Tratar como padrão de interação, não como estado atual do produto.

**Lição:** a cor de contexto (espaço/projeto) é uma camada separada da cor global. Útil para o Gideon se houver múltiplos contextos (ex.: projetos ou cadernos).

### 2.8 Discord e Slack

- Não pesquisei a fundo nesta sessão. Sei de forma geral que ambos têm tema claro/escuro e temas personalizados por CSS ou JSON de terceiros, sem API oficial estável de tokens [K]. Não usar como base de decisão até verificar.

### 2.9 Famílias de paleta: Catppuccin, Nord, Rosé Pine, Dracula

- **Catppuccin** tem 4 variantes chamadas *flavors*: Latte (claro) e Frappé, Macchiato e Mocha (escuros). Cada uma tem os mesmos 26 nomes: 14 acentos (Rosewater, Flamingo, Pink, Mauve, Red, Maroon, Peach, Yellow, Green, Teal, Sky, Sapphire, Blue, Lavender), 3 tons de texto (Text, Subtext 1, Subtext 0) e a escala neutra (Overlay 2/1/0, Surface 2/1/0, Base, Mantle, Crust). [F] [catppuccin.com/palette](https://catppuccin.com/palette/)
- Valores verificados na página: Mocha Base `#1e1e2e`, Mocha Text `#cdd6f4`, Mocha Blue `#89b4fa`; Latte Base `#eff1f5`, Latte Text `#4c4f69`, Latte Blue `#1e66f5`. [F] Mesma fonte.
- A escala neutra é ordenada do fundo para o primeiro plano (Crust, Mantle, Base, Surface 0-2, Overlay 0-2). [K] Padrão de nomes; a página não explica a lógica.
- **Nord** [K]: 16 cores em 4 grupos (nord0–3 de polar night para superfícies, nord4–6 de snow storm para texto, nord7–10 frost para acento e informação, nord11–15 aurora para erro, aviso, sucesso e destaque). Não verificado nesta sessão.
- **Rosé Pine** e **Dracula** [K]: mesma ideia, paleta nomeada com papéis (base, surface, overlay, muted, subtle, text). Não verificado.

**Lição:** as famílias de paleta são bons modelos de *nomenclatura* (escala neutra de 3 a 5 níveis + acentos nomeados + tons de texto). Nenhuma delas valida contraste para o usuário, então o Gideon precisa validar por conta própria.

---

## 3. Contraste: fórmula, limiares e validação

### 3.1 Fórmula (WCAG 2.1)

Luminância relativa de uma cor sRGB, com canais em 8 bits:

1. Para cada canal `C` em `[0, 1]` (valor / 255):
   - se `C <= 0,04045`, então `C_lin = C / 12,92`;
   - caso contrário, `C_lin = ((C + 0,055) / 1,055) ^ 2,4`.
2. `L = 0,2126 * R_lin + 0,7152 * G_lin + 0,0722 * B_lin`.
3. Razão de contraste entre duas cores, com `L1` a mais clara e `L2` a mais escura:
   `(L1 + 0,05) / (L2 + 0,05)`, de 1:1 a 21:1.

[F] [WCAG 2.1, 1.4.3](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html)

### 3.2 Limiares

| Critério | Uso | Mínimo AA | Observação |
|---|---|---|---|
| 1.4.3 | texto normal | 4,5:1 | [F] |
| 1.4.3 | texto grande (18 pt, ou 14 pt negrito) | 3:1 | [F] |
| 1.4.11 | componentes de interface e partes gráficas necessárias | 3:1 | [F] [WCAG 1.4.11](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html) |
| 1.4.6 (AAA) | texto normal | 7:1 | [K] usar no preset de alto contraste |

Regras da fonte que valem para o Gideon: o valor não é arredondado (4,499 reprova), e o foco precisa de 3:1 mesmo quando o controle não precisa de borda. [F] Mesmas fontes.

### 3.3 Como apps validam tema customizado

- VS Code, Obsidian e KDE **não** validam contraste de forma geral: aplicam a cor e deixam o usuário responsável. [K] Não encontrei validação embutida nas fontes que abri.
- Material 3 **gera** os tons com garantia de contraste pela escala tonal: `on*` sempre fica num tom distante do papel que cobre. [S] Padrão descrito na documentação de papéis.
- O Gideon pode ser melhor que os referenciados: validar na entrada e corrigir automaticamente. Ver seção 7.

---

## 4. Modo de sistema, redução de movimento e translucidez

- **Seguir o sistema no KDE/Wayland** [K]: o modo claro/escuro é informado pelo portal de desktop (`org.freedesktop.appearance`, chave `color-scheme`, com valores 0 sem preferência, 1 escuro, 2 claro). Não verifiquei nesta sessão. Para o Gideon: ler o portal quando disponível, cair para `prefers-color-scheme` (se web) ou para o modo escolhido pelo usuário, e reagir à mudança sem reiniciar.
- **Movimento reduzido** [K]: no CSS é `prefers-reduced-motion`; no GNOME existe `enable-animations` nas configurações de interface. WCAG 2.3.3 (AAA) pede controle de animação por interação. Padrão para o Gideon: nível de animação com três valores (desligada, reduzida, normal), e "reduzida" = transições de opacidade e nada de deslocamento.
- **Translucidez e blur** [K]: são caros em GPU e pioram o contraste sobre fundos variáveis. Padrão: opção desligável; ao desligar, usar superfície opaca com o mesmo papel.

---

## 5. Preview, importação, exportação e persistência

- **Preview ao vivo**: aplicar os tokens no próprio app enquanto o usuário arrasta o controle, com "Reverter" e "Aplicar" explícitos. [K] Padrão observado em editores de tema (VS Code e Obsidian mostram o efeito ao alterar).
- **Formato**: JSON com `schemaVersion`, `name`, `mode`, `tokens` e `options`. Importar valida cada campo e reporta o que foi corrigido.
- **Compartilhar**: o arquivo de tema é o único formato de troca. Não compartilhar binário nem estado interno. Obsidian compartilha pasta de snippets; VS Code compartilha extensão. [S] para Obsidian.
- **Persistência**: arquivo de configuração do usuário, em diretório de configuração padrão do sistema (XDG no Linux). Nada de estado em sessão para tema. [K]
- **Versão**: ao carregar um tema de versão antiga, migrar; se um token desconhecido aparecer, ignorar e avisar.

---

## 6. Padrões a adotar no Gideon

### 6.1 Schema de tokens (nomes e padrões)

Nomes em inglês no JSON (como nos sistemas citados), rótulos em português na interface. Valores são padrões do preset "Gideon Escuro" e "Gideon Claro". Todos os pares foram verificados com o script da seção 8.

| Token | Papel | Escuro (padrão) | Claro (padrão) |
|---|---|---|---|
| `bg` | fundo da janela | `#121417` | `#FBFBFD` |
| `surface` | painel/cartão | `#1B1F24` | `#FFFFFF` |
| `surfaceVariant` | campo, cabeçalho, linha alternada | `#262C33` | `#EEF1F5` |
| `outline` | borda de controle, separador forte | `#7D8794` | `#7A8491` |
| `text` | texto principal | `#E6E9EE` | `#1A1D21` |
| `textMuted` | texto secundário | `#A7B0BC` | `#4B5563` |
| `accent` | ação principal, foco, seleção | `#7AA2F7` | `#2F5FD0` |
| `onAccent` | texto/ícone sobre `accent` | `#0B1020` | `#FFFFFF` |
| `success` | estado ok | `#6BCB8B` | `#1E7A3F` |
| `warning` | aviso | `#E8B04B` | `#8A5A00` |
| `error` | erro | `#F07178` | `#B42318` |
| `info` | informação | `#6CB6FF` | `#1D5FA8` |

Regras de nomenclatura:
- `on<Papel>` sempre é a cor de conteúdo sobre `<papel>`. Só existe `onAccent` por enquanto; adicionar `onSuccess` etc. só se a interface precisar de fundo colorido com texto.
- Derivados (hover, pressed, foco de 2 px) são calculados a partir de `accent` e não ficam no schema do usuário. Se o usuário quiser mexer, vira avançado.

### 6.2 Opções configuráveis pelo usuário

Básico (sempre visível):

| Opção | Valores | Padrão | Observação |
|---|---|---|---|
| Modo | `sistema`, `escuro`, `claro` | `sistema` | segue o portal de desktop |
| Cor de destaque | preset de acento ou hex | `#7AA2F7` (escuro) / `#2F5FD0` (claro) | só altera `accent`; `onAccent` é recalculado |
| Densidade | 0,85 a 1,25 (multiplicador) | 1,0 | ajusta padding e altura de linha |
| Raio de canto | 0 a 16 px | 8 px | 0 = quadrado |
| Tamanho de fonte | 12 a 20 px | 14 px | base; escala o restante |
| Família de fonte | sistema ou lista fechada | sistema | nunca livre; só fontes instaladas |
| Contraste | normal, alto | normal | "alto" troca para os tokens do preset Alto contraste e exige 7:1 |

Avançado (oculto, com aviso e botão "restaurar"):

| Opção | Faixa | Padrão |
|---|---|---|
| Cada token de cor | hex válido, passa na validação | ver 6.1 |
| Animação | desligada, reduzida, normal | normal |
| Translucidez (blur) | 0 a 24 px, ou desligada | desligada |
| Intensidade de sombra | 0 a 100% | 30% |
| Peso de fonte de título | 500 a 800 | 700 |
| Altura de linha | 1,2 a 1,8 | 1,5 |

Não expor: seletores CSS, caminhos de arquivo de ícones, expressões. Sem "CSS livre" no MVP.

### 6.3 Regras de validação de tema customizado

Aplicar sempre na entrada (ao digitar um hex, ao importar um arquivo e antes de salvar).

Pares obrigatórios e limiares:

| Par (texto/fundo) | Limiar | Regra |
|---|---|---|
| `text` sobre `bg` e sobre `surface` | 4,5:1 | obrigatório |
| `textMuted` sobre `surface` | 4,5:1 | obrigatório |
| `onAccent` sobre `accent` | 4,5:1 | obrigatório; se falhar, trocar `onAccent` para preto ou branco, o que tiver maior razão |
| `success`, `warning`, `error`, `info` como texto sobre `bg` | 4,5:1 | obrigatório se usados como texto |
| `accent` sobre `bg` e sobre `surface` | 3:1 | componente e foco |
| `outline` sobre `surface` | 3:1 | borda que identifica controle |

Ação ao falhar (ordem):

1. **Hex inválido** (formato): rejeitar a entrada e manter o valor anterior.
2. **Par abaixo do limiar**: corrigir automaticamente. Para o elemento de primeiro plano, mover a luminância em passos pequenos (ex.: 1% de HSL, ou tom no espaço de paleta) na direção que aumenta o contraste (para o branco se o fundo é escuro, para o preto se é claro), até atingir o limiar. Mostrar ao usuário o valor original e o corrigido, com opção de aceitar a correção ou forçar.
3. **Correção impossível** (ex.: fundo e primeiro plano ambos no meio-cinza e o caminho não atinge o limiar): rejeitar o token e mostrar o motivo.
4. **Preset "Alto contraste"**: exigir 7:1 em texto e 3:1 em componentes, sem correção automática para baixo desse nível. Se o usuário tentar sair do preset com uma cor que não atende, reprovar.

Regras adicionais:
- Não validar cor só por ser bonita: validar sempre o par que a usa.
- Validar também ao trocar o modo (escuro para claro), porque o par pode mudar.
- Teste automatizado: a suíte de presets deve passar sempre que um token de preset mudar.

### 6.4 Presets sugeridos (8)

Os oito presets abaixo foram calculados com o script da seção 8. Todos passam nos limiares da seção 6.3. Os valores de Catppuccin-like e Nord-like são **inspirados** nas famílias; os hex do Catppuccin foram conferidos só para Base, Text e Blue, o restante é [K]. Os de Breeze também são [K].

| # | Preset | bg | surface | surfaceVariant | outline | text | textMuted | accent | onAccent | success | warning | error | info |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Gideon Escuro | `#121417` | `#1B1F24` | `#262C33` | `#7D8794` | `#E6E9EE` | `#A7B0BC` | `#7AA2F7` | `#0B1020` | `#6BCB8B` | `#E8B04B` | `#F07178` | `#6CB6FF` |
| 2 | Gideon Claro | `#FBFBFD` | `#FFFFFF` | `#EEF1F5` | `#7A8491` | `#1A1D21` | `#4B5563` | `#2F5FD0` | `#FFFFFF` | `#1E7A3F` | `#8A5A00` | `#B42318` | `#1D5FA8` |
| 3 | Alto contraste | `#000000` | `#0A0A0A` | `#1A1A1A` | `#FFFFFF` | `#FFFFFF` | `#D0D0D0` | `#FFD400` | `#000000` | `#00E676` | `#FFB300` | `#FF5252` | `#40C4FF` |
| 4 | Breeze-like escuro | `#232629` | `#31363B` | `#3B4045` | `#7F8C8D` | `#FCFCFC` | `#BDC3C7` | `#3DAEE9` | `#0B0F13` | `#27AE60` | `#F67400` | `#F26D7E` | `#3DAEE9` |
| 5 | Breeze-like claro | `#EFF0F1` | `#FCFCFC` | `#E3E5E7` | `#7F8C8D` | `#232629` | `#4D5358` | `#1D6FA8` | `#FFFFFF` | `#1E7A45` | `#8A4500` | `#B3261E` | `#1D6FA8` |
| 6 | Catppuccin-like (Mocha) | `#1e1e2e` | `#313244` | `#45475a` | `#7f849c` | `#cdd6f4` | `#a6adc8` | `#89b4fa` | `#1e1e2e` | `#a6e3a1` | `#f9e2af` | `#f38ba8` | `#89dceb` |
| 7 | Nord-like | `#2E3440` | `#3B4252` | `#434C5E` | `#939EB2` | `#ECEFF4` | `#D8DEE9` | `#88C0D0` | `#2E3440` | `#A3BE8C` | `#EBCB8B` | `#E38A92` | `#81A1C1` |
| 8 | Daltonismo-seguro | `#15171C` | `#1E2228` | `#2A2F37` | `#8A93A0` | `#EDEFF2` | `#B5BCC6` | `#56B4E9` | `#000000` | `#2BB594` | `#E69F00` | `#E8743B` | `#56B4E9` |

Notas:
- Daltonismo-seguro usa a paleta Okabe-Ito (azul, laranja, verde-azulado, vermelhão, azul-céu) [K], que é desenhada para distinguir cores em daltonismo. Não usa só cor para estado: o app deve sempre ter ícone ou texto junto.
- Breeze-like claro usa acento mais escuro (`#1D6FA8`) que o Breeze original para passar 3:1 sobre branco. Foi uma correção deliberada.
- Os presets Catppuccin-like e Nord-like são inspiração de paleta, não cópia. Não usar o nome de marca na interface; chamar de "Frappé-like" etc. se for mostrar o nome.

---

## 7. Trabalho para a próxima etapa

- Confirmar o conteúdo das diretrizes do GNOME e da Apple (páginas que não abriram).
- Verificar os nomes oficiais dos grupos de cor do KDE Plasma (`Colors:*`) com o código-fonte ou a página de referência.
- Verificar a referência de tokens do Material 3 em material.io ou no repositório Android.
- Definir o formato exato do arquivo (JSON ou TOML) e o campo `schemaVersion`.
- Decidir se o "seguir o sistema" usa o portal de desktop no Linux do Gideon. Testar em Wayland e X11.

---

## 8. Validação dos presets

Script de verificação (Python, fórmula da seção 3.1), rodado nesta sessão. Os pares testados são os da seção 6.3. Os resultados dos 8 presets finais passam em todos os limiares. Dois valores foram ajustados após a primeira rodada, que reprovou:
- Gideon Escuro: `outline` de `#5A6470` para `#7D8794` (2,75:1 para ~3:1).
- Breeze-like escuro: `error` de `#DA4453` para `#F26D7E` (3,57:1 para 4,5:1).
- Catppuccin-like: `outline` de `#6c7086` para `#7f849c` (2,57:1 para 3:1).
- Nord-like: `error` de `#BF616A` para `#E38A92` (3,05:1 para 4,5:1) e `outline` de `#4C566A` para `#939EB2` (1,36:1 para 3:1).

O script não está no repositório (é arquivo temporário da sessão). Ele deve virar teste unitário no Gideon, com os mesmos pares.

---

## 9. O que não consegui verificar

- Páginas de diretriz do GNOME (404 nas duas tentativas).
- Página da Apple sobre `controlAccentColor` (só o título veio).
- Página oficial do Material 3 (m3.material.io): só o título veio. Valores de tom vêm de fonte secundária.
- Referência de CSS variables do Obsidian (apenas resumo de terceiros).
- Documentação de Global Themes e nomes `Colors:*` do KDE (índice apenas).
- Discord e Slack: não pesquisei.
- Comportamento real de "seguir o sistema" no KDE sob Wayland: não testado.
- Nomes e valores completos de Nord, Rosé Pine, Dracula e Breeze: vêm de conhecimento prévio, não de fonte aberta nesta sessão.
- Arc: status atual do produto (fontes podem estar desatualizadas).

---

## 10. Fontes

Abertas com leitura de conteúdo:
- https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
- https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html
- https://code.visualstudio.com/api/references/theme-color
- https://catppuccin.com/palette/

Abertas com trecho ou só busca:
- https://docs.flutter.dev/release/breaking-changes/new-color-scheme-roles
- https://github.com/material-components/material-components-android/blob/master/docs/theming/Color.md
- https://softaai.com/material-3-colorscheme-explained-how-dynamic-color-works/
- https://docs.obsidian.md/Themes/App+themes/Theme+guidelines
- https://obsidian.md/help/snippets
- https://forum.obsidian.md/t/using-cssclasses-in-snippets/100577
- https://deepwiki.com/obsidianmd/obsidian-developer-docs/3.3-css-variables-reference
- https://debugpointnews.com/plasma-accent-colour-wallpaper-5-25/
- https://develop.kde.org/docs/plasma/wallpapers/
- https://discuss.kde.org/t/set-the-type-of-accent-color-via-cli-from-theme-wallpaper-custom/3770
- https://bugs.kde.org/show_bug.cgi?id=444043
- https://pointieststick.com/2022/04/22/this-week-in-kde-major-accent-color-and-global-theme-improvements/
- https://start.arc.net/paint-the-internet
- https://www.slashgear.com/1634601/best-arc-browser-features/
- https://techcrunch.com/?p=2549048

Tentativas sem conteúdo (404 ou só título): GNOME HIG (2 URLs), página da Apple `controlAccentColor`, m3.material.io, develop.kde.org/docs/plasma/theme/ (índice).
