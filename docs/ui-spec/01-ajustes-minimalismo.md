# Ajustes de minimalismo e customização (valem sobre TODAS as especificações e mockups v3)

Origem: crítica dos mockups v3 (design-critique de 2026-10-23). Onde este documento conflitar com `10-…50-*.md` ou com os PNGs, **este vence**.

## 1. Menos peso

1. **Sem faixa de resumo** quando ela repete algo já visível (estado na pílula, contadores nos filtros/badges). Só existe quando traz dado novo.
2. **Selo só para exceção.** O que vale para todos os itens vira UMA faixa de aviso por página ("Publishers não verificados", "Servidor falso: sem credenciais reais"). Nada de selo repetido em cada cartão/linha. Selos individuais só quando o item difere dos demais (ex.: um plugin em quarentena).
3. **Seções, não caixas.** Agrupar por espaço (24 px entre seções) e uma linha fina de 1 px (outline a 40 %). Cartão com borda/preenchimento só para objetos (plugin, conta, modelo, proposta de aprovação) e diálogos.
4. **Um subtítulo curto** (≤ 90 caracteres) por página; nunca repetir no resumo.
5. **Listas em vez de grades densas** (Plugins, Skills): linhas de 56 px com ação à direita; detalhe numa gaveta à direita (360 px) ao clicar.
6. **Aparência:** básico = preset + cor de destaque + modo; todo o resto em "Personalizar" (recolhido) com a prévia fixa ao lado.
7. **Contadores neutros** nas sub-abas; cor só para erro real.
8. Idle da Hoje: o espaço livre mostra "Atividade recente" (3 linhas) em vez de vazio.

## 2. Uma grade para tudo

- Coluna de conteúdo **centralizada, máx. 1100 px**, margens laterais 32 px abaixo de 1164 px de largura. Vale para todas as telas.
- Ritmo de 8 px; blocos separados por 24; padding interno de cartão 20; altura de linha de lista 56; alvos clicáveis ≥ 36 px.
- Tipografia: título de página 24 bold, seção 16 semibold, corpo 14, ajuda **13** (nunca 12), legenda 12 só para metadados não essenciais.
- Texto auxiliar com contraste ≥ 4,5:1 em todos os presets (validar na carga do tema).

## 3. Customização total, ligada ao Core

### 3.1 Esquema único de configurações do app (`uiSchema`)
Toda opção de interface é declarada UMA vez: `{key, section, subtab, type (bool|enum|int|float|color|string|json), default, min, max, options, level (basic|advanced|dev), label, help, restart (bool), keywords}`.
Tudo deriva do esquema: tela de Configurações, busca, marca "modificado", restaurar padrão, filtro "somente modificados", exportar/importar, paleta Ctrl+K.

Chaves (mínimo):
- `theme.mode` (system|dark|light), `theme.preset` (8), `theme.accent` (color), `theme.density` (0.85–1.25), `theme.radius` (0–16), `theme.fontSize` (12–20), `theme.fontFamily` (system|lista fechada), `theme.contrast` (normal|high), `theme.animation` (off|reduced|normal), `theme.translucency` (0–24), `theme.shadow` (0–100), `theme.titleWeight` (500–800), `theme.lineHeight` (1.2–1.8), `theme.colors` (json: overrides por papel, validados), `theme.orb` (bool), `theme.orbSize` (small|medium).
- `behavior.startTab`, `behavior.rememberWindow` (bool), `behavior.tips` (bool), `behavior.shortcuts` (bool), `behavior.advanced` (bool: mostrar avançado), `behavior.devMode` (bool, atrás de confirmação), `behavior.toastSeconds` (2–10), `behavior.confirmWrites` (bool, padrão true), `behavior.reduceMotionFollowSystem` (bool).
- `voice.partials` (mostrar parcial ao vivo), `voice.showConfidence` (avançado), `audio.cues` (som de início/fim).
Persistência: arquivo JSON do app por perfil em `$XDG_CONFIG_HOME/gideon-app/<perfil>.json` (0600, escrita atômica, versão do esquema). **Nunca guarda segredos.** Configurações que o Core já possui (wake, ganho, feedback, indicador visual, prazo da sessão) continuam no Core e aparecem na mesma tela pelo esquema, marcadas `source: core`.

### 3.2 Ligação com o Core (nada de dado de enfeite)
Cada elemento da tela lê uma propriedade real da ponte ou fica **desativado com motivo**. Mudanças necessárias (Rust/ponte), nesta ordem:
1. `events` expostos à UI com horário (campo `at_ms` do Core) → Atividade, Auditoria, Últimos erros.
2. Propostas de ferramenta com `risk` e `effect` (texto curto vindo do registro de ferramentas).
3. Data de cada concessão (`approved_at`) e lista unificada de concessões.
4. Operação "reiniciar Core" (exigida por wake/feedback/plugins).
5. Modos de permissão por capacidade (Perguntar/Automático/Sempre) — SOMENTE se o dono aprovar.
6. Persistência real de tema (item 3.1; só no app).

### 3.3 Temas
Papéis: `bg, surface, surfaceVariant, outline, text, textMuted, accent, onAccent, success, warning, error, info` (+ derivados hover/pressed/focus/tint calculados). 8 presets (docs/research/ux-temas.md §6.4). Validação de contraste na entrada (texto 4,5:1; componentes 3:1; alto contraste 7:1) com autocorreção e explicação. `theme.mode=system` segue o esquema claro/escuro do desktop. Importar/exportar tema em JSON com `schemaVersion`.

## 4. Fluxo de implementação

1. **Alicerce:** esquema + ponte de configurações do app (Python); Tema (singleton QML) + componentes; casca nova (abas, sub-abas, pílula, paleta Ctrl+K); páginas em arquivos separados.
2. **Páginas em paralelo** (um agente por aba), cada uma contra seu `ui-spec` + este documento, comparando capturas reais com os PNGs.
3. **Core/ponte** (Rust): itens 3.2.1–3.2.4.
4. **Qualidade:** exploração visual em Wayland real, gates de interface, empacotamento.
