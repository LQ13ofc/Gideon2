# Especificação de tela: aba "Extensões" (nível 1) e sub-abas

Status: especificação para implementação. Não altera código. Janela de referência 1380 × 904 px; mínimo 720 × 520.
Estilo: KDE/Plasma (Breeze), tema escuro do Gideon. Segue `docs/UI_IA.md` seção 2 e `docs/ui-spec/00-casca.md`.

Fontes lidas para esta especificação:

- `docs/UI_IA.md` (seção 2, Extensões; regras de unicidade; casca)
- `docs/ui-spec/00-casca.md` (regiões, tamanhos, componentes, teclado, responsivo)
- `docs/UI_NOTION_REQS.md` (regras de estrutura e áreas-alvo)
- `docs/UI_INVENTORY.md` (IDs P6-*, D2-*, D3-*, P8-*, P9-*, P10-*, P11-*, AC-*, NF-*, DU-*)
- `docs/S4.md` (skills: estados, ops, pipeline, import/export)
- `docs/S5.md` (conexões: contas, escopos, MCP, rotas)
- `docs/C2.md` (modelos LLM: catálogo, selftest, LKG, fallback)
- `docs/C4.md` (percepção e ação: backends sintéticos, plugins C4.1 a C4.6)
- `app/bridge.py` e `app/Main.qml` (nomes de propriedades, slots e textos conferidos com grep)

---

## 0. Como ler esta especificação

### 0.1 Convenções

- **ID de elemento**: `EX-<área>-<nn>`. Áreas: `PL` Plugins, `SK` Skills, `CN` Conexões, `MD` Modelos LLM, `PC` Percepção e ação, `FX` diálogos e transversais.
- **Origem**: cada elemento cita o ID do inventário (`P6-C1`, `D2-I4`, `AC-05` etc.) quando existe. Sem ID, é elemento novo e está marcado como `NOVO`.
- **Fonte de dados**: `core.<nome>` é propriedade ou slot da ponte (`app/bridge.py`). `core.<nome>()` é slot. `window.<nome>` é função ou propriedade do QML.
- **`[novo texto]`**: texto que ainda não existe no código. Os demais textos já existem no QML ou no inventário e devem ser copiados literalmente.
- **`NOVO (precisa de mudança na ponte/Core)`**: funcionalidade ou dado que hoje não existe. A descrição diz o que falta.
- **`UI apenas`**: muda só o QML, sem ponte nem Core.
- **Nível**: `Básico` (sempre), `Avançado` (atrás de "Mostrar opções avançadas", em Configurações › Geral), `Desenvolvimento` (atrás de "Modo desenvolvedor", em Diagnóstico › Desenvolvedor).
- **Textos com travessão**: copiar com "—" (U+2014) quando o original tem travessão, e "·" (U+00B7) como separador.

### 0.2 Escala dos wireframes

Os wireframes mostram só a área de conteúdo (x 140 a 1240, y 236 a 880). Escala aproximada: 1 caractere = 16 px na horizontal, 1 linha = 32 px na vertical. As coordenadas exatas valem as tabelas de regiões, não o desenho.

### 0.3 Coordenadas comuns (vêm de `00-casca.md`)

| Região | x | y | largura | altura | Observação |
|---|---|---|---|---|---|
| Barra de abas (nível 1) | 0 | 0 | 1380 | 56 | Fundo #0e1a3a |
| Barra de sub-abas (nível 2) | 0 | 56 | 1380 | 44 | Fundo #0b1530 |
| Cabeçalho da sub-aba | 32 | 116 | 1316 | 60 | Título y 116 (altura 40), subtítulo y 158 (altura 18) |
| Ação primária | 1348 − w | 116 | conforme texto | 40 | Alinhada à direita |
| Faixa de resumo | 32 | 184 | 1316 | 40 | Opcional; só leva texto e badges |
| Área de conteúdo | 140 | 236 | 1100 | 644 | Centralizada porque a janela tem mais de 1240 px |
| Barra de segmentos internos | 140 | 236 | 1100 | 36 | Topo da área de conteúdo |
| Corpo dos segmentos | 140 | 284 | 1100 | 596 | Rola na vertical; cabeçalho fica fixo |
| Grade | 12 colunas, gap 16 | | | | Coluna = 77 px; início da coluna i = 140 + 93·i |

Larguras de grade a usar: 12 colunas = 1100; 8 colunas = 728; 6 = 542; 5 = 449; 4 = 356; 3 = 263.

### 0.4 Reflow abaixo de 900 px

- Abas de nível 1 viram só ícones, com tooltip com o nome.
- Sub-abas rolam na horizontal.
- Cabeçalho empilha: título na primeira linha, ação primária na linha seguinte, à esquerda.
- Margem lateral passa a 16 px (x 16 até largura − 16).
- Toda grade vira 12 colunas de largura total (um cartão por linha).
- Painéis de detalhe em coluna (ver 2.6, 5.2) passam para baixo do conteúdo, não ao lado.
- Nenhum elemento tem largura mínima maior que a tela. Tabelas e wireframes podem rolar em `overflow-x: auto` dentro do próprio bloco.

### 0.5 Estados e cores (tons da casca)

Sucesso `#5ee0a0` · Aviso `#f2c15c` · Erro `#ff7d8a` · Info `#7693ff` · Neutro `#9db0e0`. Cor sempre acompanhada de palavra. Selo discreto: altura 18, raio 9, borda 1 px `#2a3d78`, texto 12 px neutro.

---

## 1. Aba de nível 1 "Extensões"

### 1.1 Visão geral

| Campo | Valor |
|---|---|
| Objetivo | Instalar, ativar e configurar as extensões do Gideon (plugins, skills, contas de serviço, modelo LLM e percepção/ação). Uso ocasional. |
| Posição | 2ª aba na barra de abas: `[Assistente] [Extensões] [Permissões] [Configurações] [Diagnóstico]`. |
| Rótulo e ícone | "Extensões", ícone de peça de quebra-cabeça (Breeze `extension`), 18 px. |
| Atalho | Ctrl+2. |
| Badge | Nenhum na aba. As pendências aparecem como badge da sub-aba (Plugins e Conexões, ver 1.3). |
| Condição de aparecimento | Sempre visível. |
| Nível | Básico. |
| Pílula de estado e Cancelar | Ficam à direita da barra, como na casca. "Cancelar" aqui só aparece para sessão de voz, nunca para operação desta aba (ver 8.4). |

Origem: UI_IA §2 e casca. Substitui a dupla entrada atual "Gideon Hub" + "Plugins" (AC-07, DU-07, SB-05, SB-08, NT-03).

### 1.2 Sub-abas da aba Extensões

Ordem fixa: Plugins · Skills · Conexões · Modelos LLM · Percepção e ação. Texto 14 px; ativa com texto branco bold e sublinhado 2 px de acento; inativa `#9db0e0`; desabilitada `#5a6a95` com tooltip de motivo. Padding horizontal 18; largura da sub-aba = texto + 36 px; primeira sub-aba começa em x = 18.

| # | Sub-aba | Condição de aparecimento | Quando não aparece | Badge | Nível da sub-aba | Origem |
|---|---|---|---|---|---|---|
| 1 | Plugins | Sempre | — | Número de plugins com estado Falhou ou Quarentena (cor Erro). Some se zero. | Básico | P6-*, D2-*, SB-05, SB-08 |
| 2 | Skills | Sempre (ver 8.2 sobre o inventário SB-06) | Desabilitada com tooltip "Core desconectado" quando offline | Nenhum | Básico (elementos marcados Avançado) | P10-*, SB-06 |
| 3 | Conexões | Sempre (ver 8.2 sobre o inventário SB-07) | Desabilitada com tooltip "Core desconectado" quando offline | Número de contas pendentes (status `connecting`, `expired`, `reauth_required` ou com escopo pedido ainda não concedido). Cor Aviso. | Básico (elementos marcados Avançado) | P11-*, SB-07 |
| 4 | Modelos LLM | `core.modelsAvailable` verdadeiro (plugin `llm_engine` em execução com `llm_engine.models`) | Sub-aba não aparece. Se o usuário estava nela, muda para Plugins e mostra o toast da regra 8.1. | Nenhum | Básico | P8-*, SB-09 |
| 5 | Percepção e ação | `core.perceptionAvailable` verdadeiro (algum plugin C4 em execução) | Sub-aba não aparece. Mesmo comportamento da 4. | Nenhum | Avançado (testes em Desenvolvimento) | P9-*, SB-10 |

Regra de exibição das sub-abas condicionais: ao montar a barra, a ordem permanece e a sub-aba ausente simplesmente não ocupa espaço. Nenhuma sub-aba fica como "desabilitada por plugin ausente" (isso é papel do banner de Plugins, ver 8.3).

### 1.3 Cabeçalho por sub-aba

| Sub-aba | Título (24 px bold) | Subtítulo (14 px `#9db0e0`, ≤ 90 caracteres) | Ação primária (botão 40 px) |
|---|---|---|---|
| Plugins | Plugins | Instale e ative plugins verificados. Instalar não executa nada e não concede acesso. | Nenhuma. Cada cartão tem a sua. |
| Skills | Skills | Procedimentos que combinam capacidades instaladas. Nada aqui concede permissão. | "Nova skill" (vai para o segmento Criar; não chama o Core) [novo texto] |
| Conexões | Conexões | Contas de serviços pela API. Você concede cada escopo; escrita pede aprovação. | "Nova conta" (vai para o segmento Nova conta; não chama o Core) [novo texto] |
| Modelos LLM | Modelos LLM | Escolha, teste e configure o modelo do motor LLM instalado. | "Atualizar lista" (`core.listModels(aba atual)`, origem P8-C1) |
| Percepção e ação | Percepção e ação | Sensores e ações simulados nesta build. Nenhum hardware real é acessado. | Nenhuma. |

Origem: P10-T1, P11-T1, P8-T1, P9-T1 (texto ajustado para caber em 90 caracteres) e UI_IA §2.

### 1.4 Faixa de resumo por sub-aba (1 linha, y 184 a 224, largura 1316)

Frase à esquerda (14 px bold); badges à direita (altura 22, raio 11).

| Sub-aba | Frase-resumo | Badges |
|---|---|---|
| Plugins | "Catálogo verificado · N instalados · N ativos · N em quarentena" ou "Catálogo não configurado" ou "Catálogo em quarentena" | "N instalados" (Info); "N ativos" (Sucesso); "N em quarentena" (Erro se N > 0; Neutro se 0) |
| Skills | "N instaladas · N habilitadas · N rascunhos" | Nenhum |
| Conexões | "N contas · N conectadas · N pendentes" | "N pendentes" (Aviso se N > 0) |
| Modelos LLM | "Modelo atual: <provedor> · <modelo>" ou "Nenhum modelo configurado" | Estado do modelo (cor conforme 5.1) · "Nuvem" (Info) ou "Local" (Neutro) |
| Percepção e ação | "N plugins de percepção em execução" | "Microfone: <estado>" · "Câmera: <estado>" (ver PC-I-04) |

Definições: skills "rascunhos" = estados `draft` e `validated`. Conexões "pendentes" = `connecting`, `expired`, `reauth_required`. Conexões "conectadas" = `connected`. Plugins "ativos" = `running`.

Origem: P6-I1 (descrição do Hub, não mostrada aqui), P10-I3..I5, P11-I5..I7, P8-I1, P9-I1..I2.

### 1.5 Área de conteúdo comum

- Cartões: raio 14, padding 20, título 17 px semibold, corpo 14 px, legenda 12 px.
- Cada sub-aba pode ter o bloco "Como funciona" recolhível: linha de altura 56 com título, 1 linha de resumo e ▸/▾ à direita, recolhida por padrão.
- Mensagens transitórias (resultado de operação) vão no topo do corpo, em faixa de altura 32, e são espelhadas em toast de 4 s quando a ação termina (ver 8.5).

---

## 2. Sub-aba "Plugins" (Básico)

### 2.1 Visão e condição

| Campo | Valor |
|---|---|
| Objetivo | Ver o catálogo local de plugins, revisar as permissões de cada um, instalar o pacote verificado, ativar ou desativar e remover. Une "Gideon Hub" (P6) e "Plugins" (D2) em uma só tela (AC-07, NT-03). |
| Condição de aparecimento | Sempre. |
| Nível | Básico. Ações marcadas como Avançado ficam no menu ⋯ e só aparecem com "Mostrar opções avançadas". |
| Controle de filtro | Segmentado com 4 opções: "Todos" · "Instalados" · "Disponíveis" · "Quarentena". Cada uma com badge de contagem. |
| Dados | `core.hubEntries` (catálogo: `plugin_id`, `semver`, `publisher`, `status`, `reason`, `permissions`, `permissions_approved`, `payload_staged`, `staged_error`, `license`, `api_version`, `targets`, `dependencies`, `conflicts`, `download_size`, `capabilities`, `manifest_sha256`, `support_policy`); `core.pluginItems` (`plugin_id`, `semver`, `capabilities`, `state`, `enabled`, `restarts`, `last_error`); `core.hubDescription`; `core.hub.status` via `core.hubEntries` e a propriedade `core.connected`. |

Filtros, definidos sobre a união das duas fontes (uma linha por `plugin_id`):

- Todos: todas as linhas, inclusive incompatíveis.
- Instalados: `status` = `installed` ou `update_available`, ou existe item em `pluginItems`.
- Disponíveis: `status` = `not_installed` ou `update_available`. Incompatíveis não entram aqui.
- Quarentena: `pluginItems.state` = `quarantined`, ou catálogo em quarentena (`hub.status` = `quarantined`).

### 2.2 Layout em grade

Janela 1380 × 904. Corpo do segmento em y 284.

| Região | x | y | largura | altura | Conteúdo |
|---|---|---|---|---|---|
| Barra de filtro | 140 | 236 | 1100 | 36 | Segmentado "Todos · Instalados · Disponíveis · Quarentena" (aproximadamente 560 px de largura) |
| Banner de confiança | 140 | 284 | 1100 | 40 | Texto de 1 linha + "Como funciona ▾" à direita |
| Bloco "Como funciona" (expandido) | 140 | 328 | 1100 | até 120 | Só quando expandido; empurra a grade para baixo |
| Grade de cartões (sem detalhe) | 140 | 340 | 1100 | 540 | 3 cartões por linha (span 4 = 356 px; x = 140, 512, 884) |
| Grade de cartões (com detalhe) | 140 | 340 | 728 | 540 | 2 cartões por linha (span 4; x = 140, 512) |
| Painel de detalhe | 884 | 340 | 356 | 540 | Só com um cartão selecionado; rola na vertical |
| Estado vazio | 140 | 340 | 1100 | 240 | Moldura tracejada, altura mínima 140 |

Altura de cartão: 176 px fixos; intervalo vertical 16. Linhas em y = 340, 532, 724 (a terceira rola).

Reflow < 900 px: grade vira 1 coluna (cartão largura 1316 − 0; x 16). Painel de detalhe abre abaixo do cartão selecionado, com a mesma largura do cartão.

### 2.3 Wireframe

```
 x140                                                                         x1240
 +--------------------------------------------------------------------------+ y236
 | [ Todos 4 ] [ Instalados 2 ] [ Disponíveis 1 ] [ Quarentena 1 ]           |
 +--------------------------------------------------------------------------+ y284
 | Pacotes verificados por checksum · sem rede · publisher não autenticado   |
 |                                                       Como funciona ▾    |
 +------------------------------------+-------------------------------------+ y340
 | cartão 1 (356 px)                   | cartão 2 (356 px)                  |
 | nome + badge                        |                                    |
 | versão · publisher · não verificado |                                    |
 | permissões · aviso                  |                                    |
 | [ação primária]            [ ⋯ ]    |                                    |
 +------------------------------------+-------------------------------------+ y532
 | cartão 3                            | cartão 4                           |
 +------------------------------------+-------------------------------------+ y724
```

Com detalhe aberto, o painel ocupa a faixa direita (x 884 a 1240, y 340 a 880), e a grade mostra 2 colunas à esquerda.

### 2.4 Elementos

Colunas: # (ordem de leitura) · Região (x, y, w, h) · Tipo · Texto exato · Fonte de dados · Ação → resultado · Estados · Nível.

| # | ID | Região | Tipo | Texto exato | Fonte de dados (origem) | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|---|
| 1 | EX-PL-01 | 140,236,~560,36 | Segmentado | "Todos" · "Instalados" · "Disponíveis" · "Quarentena" (badges com contagem) | Filtro local sobre `core.hubEntries` + `core.pluginItems` (P6-I2, D2-I4, D2-I7) | Troca o filtro; sem chamada ao Core | Ativo: texto branco bold + sublinhado | Básico |
| 2 | EX-PL-02 | 140,284,1100,40 | Texto | "Pacotes verificados por checksum · sem rede · publisher não autenticado" [texto de IA §2.1, novo na tela] | Texto fixo | Nenhuma | — | Básico |
| 3 | EX-PL-03 | 1120,292,120,24 | Link | "Como funciona ▾" / "Como funciona ▴" | UI apenas | Expande/recolhe o bloco (texto: ver 2.4.1) | Recolhido por padrão | Básico |
| 4 | EX-PL-04 | 140,340,356,176 (por cartão) | Cartão de plugin | Ver 2.5 | `core.hubEntries` + `core.pluginItems` (P6-I2, D2-I3, D2-I4, D2-I7, D2-I9, D2-I11) | Clique no cartão: abre o detalhe (2.6) | Ver 2.7 | Básico |
| 5 | EX-PL-05 | cartão, ação primária | Botão | Ver 2.5.3 | D2-C2, D2-C3, D2-C6, D2-C7 | Ver 2.5.3 | Ver 2.5.3 | Básico |
| 6 | EX-PL-06 | cartão, canto inferior direito 32×32 | Botão de menu | "Mais ações de <plugin_id>" (rótulo de acessibilidade); visível: "⋯" | UI apenas | Abre menu com itens da 2.5.4 | Habilitado sempre | Básico |
| 7 | EX-PL-07 | Painel de detalhe | Painel | Ver 2.6 | `core.hubEntries`, `core.pluginItems` | Somente leitura, com ações do 2.6 | — | Básico |
| 8 | EX-PL-08 | Estado vazio | Estado vazio | Título "Catálogo não configurado" [novo título; o texto é P6-I3]. Corpo "Nenhum plugin no catálogo ainda. Conecte o Core para carregar o catálogo local." Botão "Atualizar catálogo" | P6-I3; `core.refresh()` (slot existente, faz nova leitura do snapshot) | Botão chama `core.refresh()` | Mostrado quando `hubEntries` vazio | Básico |
| 9 | EX-PL-09 | Resumo (y184) | Badge | Ver 1.4 | `core.hubEntries`, `core.pluginItems` | Nenhuma | Ver 1.4 | Básico |
| 10 | EX-PL-10 | Mensagem de resultado (topo do corpo, y 284) | Faixa | Texto de `core.pluginResult` (D2-I12) e `core.hubApprovalResult` (D2-I8, D4-I4) | `core.pluginResult`, `core.hubApprovalResult` | Nenhuma | Só quando não vazio | Básico |

#### 2.4.1 Texto do bloco "Como funciona" (expandido)

"Instalar copia o pacote verificado para o Core; nada é executado. O catálogo não concede acesso ao computador." (D2-T1, P6-T1)

"Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto." (D4-I3)

"Plugins ativos rodam em sandbox, sem rede. Revogar permissões desativa o plugin e encerra o processo." [novo texto; baseado em D2-C8 e D6]

#### 2.4.2 Atalho para Plugins (regra 8.3)

O atalho "Instalar em Extensões › Plugins" não aparece nesta sub-aba. Ele é mostrado na sub-aba de destino de outras telas. Ver 8.3.

### 2.5 Anatomia do cartão de plugin (w 356 × h 176, padding 20)

Coordenadas relativas ao canto do cartão.

| Linha | y (relativo) | Conteúdo | Tipografia | Origem |
|---|---|---|---|---|
| L1 | 20 a 40 | `plugin_id` à esquerda (x 20). Nome amigável não existe no snapshot: NOVO (precisa de campo `name` no catálogo do Hub; até lá, usa `plugin_id`). Badge de estado à direita (altura 22, alinhado à direita, x = 336 − largura). | 17 px semibold | EX-PL-04 (D2-I3) |
| L2 | 46 a 62 | "v<semver> · publisher <publisher>" + selo "não verificado" (selo discreto à direita da linha). | 12 px neutro | D2-I3, AC-07 |
| L3 | 68 a 84 | "Permissões aprovadas" (Sucesso) ou "Permissões não aprovadas" (Aviso). Texto novo derivado de `permissions_approved`. | 12 px | D2-I5 (booleano) |
| L4 | 90 a 108 | Só quando o estado exige: "Aprove novamente as permissões para ativar" (Aviso) para instalado sem aprovação atual; "Falhou: <código>" (Erro) para `failed`, com o código traduzido por `core.codeMessage(code)`; "Incompatível: <motivo>" para `incompatible` (motivo: ver 2.9, regra R-PL-4). | 12 px | D2-I11, D2-I9, D2-I4 |
| L5 | 116 a 156 | Linha de ações: botão primário (ou secundário) à esquerda; botão de menu ⋯ (32×32) à direita. Altura do botão: 40. | 14 px | Ver 2.5.3 |
| Margem inferior | 156 a 176 | Sem conteúdo (folga). | — | — |

Borda do cartão: 1 px `#263a73`; fundo `#0e1a3a`; cartão selecionado: borda 2 px de acento. Tudo clicável abre o detalhe; o clique no botão ou no menu não abre o detalhe.

#### 2.5.1 Badge de estado (canto superior direito de L1)

Fonte: `status` de `hubEntries`, `state` de `pluginItems`. Prioridade: `pluginItems.state` quando existe; senão `hubEntries.status`.

| Condição | Palavra | Tom |
|---|---|---|
| `hubEntries.status` = `not_installed` e sem item em `pluginItems` | Disponível | Neutro |
| `hubEntries.status` = `update_available` | Atualização disponível | Info |
| `hubEntries.status` = `installed`, sem item em `pluginItems` ou `enabled` = false e `state` = `disabled` | Instalado | Info |
| `state` = `starting` | Iniciando | Info |
| `state` = `running` | Ativo | Sucesso |
| `state` = `stopped` | Parado | Neutro |
| `state` = `failed` | Falhou | Erro |
| `state` = `quarantined` ou catálogo em quarentena | Quarentena | Erro |
| `hubEntries.status` = `incompatible` | Incompatível | Aviso |

#### 2.5.2 Selo "não verificado"

Texto: "não verificado". Aparece ao lado do publisher em todo cartão, porque a assinatura não existe (S4 e D2 usam o mesmo princípio: `publisher_verified`). Selo discreto, nunca parágrafo.

#### 2.5.3 Ação primária do cartão (botão na linha L5)

| Estado do cartão | Botão primário | Estado do botão | Texto exato | Ação → resultado |
|---|---|---|---|---|
| Disponível, `permissions_approved` = false | Secundário | Habilitado se `core.hubApprovalAvailable` | "Revisar permissões" (D2-C2) | Abre o diálogo "Revisar permissões" (fluxo F1) |
| Disponível, `permissions_approved` = true | Primário | Habilitado se `core.hubLifecycleAvailable` e `payload_staged` = true | "Instalar pacote verificado" (D2-C3) | `core.installHub(plugin_id, manifest_sha256)` → instala desativado |
| Disponível, aprovado, sem pacote em staging | Primário | Desabilitado | "Instalar pacote verificado" | Motivo na linha abaixo: "Pacote não verificado em staging: importe pela linha de comando." [novo texto; o estado de staging vem de `payload_staged`] |
| Atualização disponível | Mesma lógica de "Disponível" | — | "Revisar permissões" ou "Instalar pacote verificado" | Idem |
| Instalado, não aprovado | Secundário | Habilitado se `core.hubApprovalAvailable` | "Revisar permissões" | Abre o diálogo |
| Instalado, aprovado, desativado | Primário | Habilitado se `core.pluginsAvailable` e `pluginCanEnable` (instalado, aprovado, `disabled`, `stopped` ou `failed`) | "Ativar" (D2-C6) | `core.enablePlugin(plugin_id)` → sandbox sem rede; estado vai para `starting` e depois `running` |
| Ativo | Secundário | Habilitado se `core.pluginsAvailable` | "Desativar" (D2-C7) | `core.disablePlugin(plugin_id)` → `disabled` |
| Iniciando | Desabilitado | — | "Aguarde o plugin iniciar" [novo texto] | Sem ação |
| Parado | Primário | Igual a "Ativar" | "Ativar" | Igual a "Ativar" |
| Falhou | Primário | Igual a "Ativar" | "Ativar" | Igual a "Ativar" (o erro aparece em L4) |
| Quarentena | Desabilitado | — | "Em quarentena: não pode ser ativado." [novo texto] | Sem ação |
| Incompatível | Desabilitado | — | "Indisponível: <motivo>" [novo texto; `reason` traduzido, ver R-PL-4] | Sem ação |

Observação: se `core.hubLifecycleAvailable` for falso por sessão de voz, o botão mostra o motivo da regra 8.6.

#### 2.5.4 Menu ⋯ do cartão

Rótulo de acessibilidade: "Mais ações de <plugin_id>". Ordem fixa:

| # | Item | Texto exato | Nível | Habilitado quando | Desabilitado: motivo | Ação → resultado / confirmação |
|---|---|---|---|---|---|---|
| 1 | Ver detalhes | "Ver detalhes" [novo texto] | Básico | Sempre | — | Abre o painel de detalhe (2.6) |
| 2 | Reverter versão | "Reverter versão" (D2-C4) | Avançado | Há versão anterior e estado `installed` | "Indisponível: não há versão anterior" [novo texto] | `core.rollbackHub(plugin_id)` |
| 3 | Revogar permissões | "Revogar permissões" (D2-C8) | Avançado | `core.pluginsAvailable` e não quarentena | "Indisponível: plugin em quarentena" [novo texto] | Confirmação D6 (ver 8.7), depois `core.revokePlugin(plugin_id, revisão)` |
| 4 | Remover plugin | "Remover plugin" (D2-C5) | Avançado | `core.hubLifecycleAvailable` | "Indisponível durante a sessão de voz" (8.6) | Confirmação D5 (8.7), depois `core.removeHub(plugin_id, revisão)` |
| 5 | Apagar dados do plugin | "Apagar dados do plugin" [novo texto] | Avançado | Plugin instalado | "Indisponível: plugin não instalado" [novo texto] | IMPLEMENTADO (WP8): `core.clearPluginSettingsOf(pluginId)` (`app/bridge.py:2245`, `plugin_settings_clear {plugin_id}`), usado em `app/pages/Plugins.qml:340`. `core.clearPluginSettings()` continua só para `llm_engine` (P8-C20, NF-24). Confirmação D8 adaptada (8.7). |

Itens 2 a 5 aparecem com "Mostrar opções avançadas" ligado. Com a opção desligada, o menu tem só "Ver detalhes".

Origem do menu: D2-C4, D2-C5, D2-C8, P8-C20 (generalizado), UI_IA §2.1.1.

### 2.6 Painel de detalhe (w 356 × h 540 à direita; padding 20)

Ordem vertical:

| Ordem | Campo | Texto exato | Fonte de dados | Nível |
|---|---|---|---|---|
| 1 | Título | `plugin_id` (17 px semibold) e badge de estado | `hubEntries`, `pluginItems` | Básico |
| 2 | Linha de identificação | "v<semver> · publisher <publisher> · não verificado" | D2-I3, AC-07 | Básico |
| 3 | Publisher | "Publisher: <publisher> (não autenticado)" [novo texto] | `hubEntries.publisher` | Básico |
| 4 | Versão | "Versão: <semver>" | `hubEntries.semver` | Básico |
| 5 | Hash | "Hash do manifest (SHA-256): <64 caracteres>" | `hubEntries.manifest_sha256` (P8-I11 para hash de modelo; aqui é do plugin) | Avançado |
| 6 | Capacidades | "Capacidades: <lista separada por vírgula>" | `pluginItems.capabilities` ou `hubEntries.capabilities` (D2-I10) | Avançado |
| 7 | Permissões | Cabeçalho "Permissões aprovadas para este manifesto:" ou "Permissões declaradas (não aprovadas):" (D2-I5), seguido de lista de rótulos: `core.permissionLabel(id)` por item | `hubEntries.permissions`, `hubEntries.permissions_approved`, `core.permissionLabel` | Básico |
| 8 | Link de Permissões | "Ver em Permissões" [novo texto; depende da aba Permissões, IA §3] | UI apenas | Básico |
| 9 | Dependências | "Dependências: <lista>" ou "Dependências: nenhuma" [novo texto] | `hubEntries.dependencies` | Avançado |
| 10 | Licença e tamanho | "Licença: <license> · Tamanho do pacote: <download_size> bytes" [novo texto] | `hubEntries.license`, `hubEntries.download_size` | Avançado |
| 11 | Estado técnico | Linha do estado do plugin: "Ativo (sandbox, sem rede)", "Iniciando…", "Falhou: <código>", "Parado", "Em quarentena", "Desativado" (texto de `window.pluginStateText`) | `pluginItems.state`, `last_error` (D2-I9) | Básico |
| 12 | Último erro | "Último erro: <mensagem traduzida>" | `pluginItems.last_error` via `core.codeMessage` | Básico |
| 13 | Incompatibilidade | "Incompatível: <motivo traduzido>" (ver R-PL-4) | `hubEntries.reason` | Básico |
| 14 | Botão primário | Mesma regra de 2.5.3, em largura total | — | Básico |
| 15 | Bloco de teste | Título "Testes de capacidade (modo desenvolvedor)" [novo texto]; campo "Texto para a capability" (máx. 256; D2-C9); botão "Invocar" por capability (D2-C10); botão "Cancelar invocação de teste" (D2-C11) com texto do resultado (D2-I13) | Só com plugin `running` | Desenvolvimento |

Painel fecha com "×" (rótulo "Fechar detalhe") ou com Esc.

#### 2.6.1 Bloco de teste (Desenvolvimento)

- "Invocar" é `core.invokeCapability(cap, texto)`, prazo 3 s; habilitado com plugin `running`.
- "Cancelar invocação de teste" (D2-C11, rótulo novo para evitar o "Cancelar" ambíguo, AC-08) chama `core.cancelCapability(cap)`; habilitado só se for a capability ativa.
- Resultado em `core.capabilityResultText` (D2-I13), até 512 caracteres, PlainText.

### 2.7 Estados do plugin (cor + palavra)

| Estado | Palavra no badge | Tom | Cartão | Ação primária | Texto de apoio |
|---|---|---|---|---|---|
| Disponível | Disponível | Neutro | Padrão | Revisar permissões ou Instalar | — |
| Atualização disponível | Atualização disponível | Info | Padrão | Revisar permissões ou Instalar | — |
| Instalado (desativado) | Instalado | Info | Padrão | Ativar ou Revisar permissões | "Aprove novamente as permissões para ativar" se não aprovado |
| Ativo | Ativo | Sucesso | Padrão | Desativar | "Ativo (sandbox, sem rede)" no detalhe |
| Iniciando | Iniciando | Info | Padrão | Desabilitado | "Iniciando…" |
| Parado | Parado | Neutro | Padrão | Ativar | — |
| Falhou | Falhou | Erro | Borda Erro | Ativar | "Falhou: <código traduzido>" |
| Quarentena | Quarentena | Erro | Borda Erro | Desabilitado | "Em quarentena: não pode ser ativado." |
| Incompatível | Incompatível | Aviso | Esmaecido | Desabilitado | "Indisponível: <motivo>" |
| Catálogo em quarentena | Quarentena (no resumo) | Erro | — | — | "Catálogo em quarentena; Base continua disponível" (bridge, `hub.status`) |

Origem dos estados: `PLUGIN_STATES` (`disabled`, `starting`, `running`, `failed`, `stopped`, `quarantined`) e `pluginStateText` do QML; `status` do catálogo (`not_installed`, `update_available`, `installed`, `incompatible`).

### 2.8 Estado vazio e erros

| Caso | Texto | Ação |
|---|---|---|
| Catálogo vazio | Ver EX-PL-08 | "Atualizar catálogo" → `core.refresh()` |
| Core desconectado | Banner acima da grade (faixa Aviso): "Core desconectado: nada pode ser alterado agora." [novo texto] | Todos os botões desabilitados, tooltip "Core desconectado" |
| Filtro sem resultado | "Nenhum plugin neste filtro." [novo texto] | Botão "Ver todos" muda o filtro para "Todos" |
| Catálogo em quarentena | Faixa Erro: "Catálogo em quarentena; Base continua disponível" (bridge, texto existente) | Sem ação |

### 2.9 Regras da sub-aba Plugins

- **R-PL-1 Revisar é obrigatório antes de instalar.** A ação "Instalar pacote verificado" só fica habilitada depois de `permissions_approved` = true (D2-C3). Não há atalho que pule a revisão.
- **R-PL-2 Aprovar permissões não instala.** Após aprovar (D4-C2), o cartão continua "Disponível" até instalar. Texto de D4-I3 acompanha o diálogo.
- **R-PL-3 Pacote em staging.** A importação de pacote por esta tela não existe (NF-01): só a CLI `scripts/hub_import.py` coloca o pacote em staging. Por isso o botão "Instalar pacote verificado" fica desabilitado quando `payload_staged` é falso. NOVO (precisa de mudança na ponte/Core): importar pacote pela interface (hub_begin, hub_chunk, hub_finish; seletor de arquivo) e descartar staging (`hub_discard_staged`, NF-02). Fora desta especificação até decisão do dono; a linha desativada mostra o comando da CLI.
- **R-PL-4 Motivos de incompatibilidade.** `hubEntries.reason` chega como código (`api_version`, `target`, `dependencies_unresolved`) e hoje aparece cru (`Main.qml:894`). Textos novos: `api_version` = "versão de API incompatível"; `target` = "plataforma incompatível"; `dependencies_unresolved` = "dependências não resolvidas". Mudança só de QML (UI apenas).
- **R-PL-5 Revogar desativa e encerra.** O texto de D6 é o que o usuário lê antes de confirmar (8.7).
- **R-PL-6 Permissões em português.** Nunca mostrar IDs crus (`network.llm`, AC-04). Quando `permissionLabel` devolve o próprio ID (sem rótulo cadastrado), mostrar "permissão sem rótulo: <ID>" [novo texto] e registrar a lacuna (NOVO: completar `PERMISSION_LABELS` em `app/bridge.py` para cada permissão do catálogo).
- **R-PL-7 Nada de SINTÉTICO aqui.** Plugins da percepção (C4) aparecem nesta grade com o mesmo cartão; o selo "SINTÉTICO" só aparece na sub-aba Percepção e ação (6).
- **R-PL-8 Desenvolvimento.** Entrada de texto de teste e invocação (D2-C9..C11) só com modo desenvolvedor.
- **R-PL-9 Sem "Explorar catálogo" como botão de diálogo.** O botão P6-C1 "Explorar catálogo" some: a própria sub-aba é o catálogo. Seu papel ficou com "Atualizar catálogo" (`core.refresh()`) no estado vazio (UI apenas; rótulo novo).

---

## 3. Sub-aba "Skills" (Básico; elementos marcados Avançado)

### 3.1 Visão e condição

| Campo | Valor |
|---|---|
| Objetivo | Ver as skills instaladas (procedimentos declarativos que combinam capacidades já instaladas e aprovadas), validar, simular, aprovar, habilitar, executar com aprovação por passo, importar e exportar, e acompanhar o histórico. |
| Condição de aparecimento | Sempre (inventário SB-06 torna a página condicional a `core.skillsAvailable`; ver 8.2). |
| Nível da sub-aba | Básico. Elementos Avançados: ver tabelas. |
| Regra central | Nada aqui concede permissão. A linha de apoio é P10-T2 (texto exato em 3.5.4). |
| Segmentos | Minhas · Criar · Importar/Exportar · Execuções (ordem fixa; sem badge). |
| Dados gerais | `core.skillsItems` (`id`, `name`, `version`, `state`, `source`, `active`, `deps_ok`, `permissions_ok`, `missing`); `core.skillCurrentRun`; `core.skillHistory`; `core.skillImportPreview`; `core.skillDraftOutput`; `core.skillsResult`; `core.skillsBusy`; `core.skillLlmAvailable`; `core.skillsAvailable`. |

### 3.2 Estados e palavras

Estado da skill (`state`), com texto de `window.skillStateText`:

| `state` | Palavra | Tom |
|---|---|---|
| `draft` | Rascunho | Neutro |
| `validated` | Validada | Info |
| `tested` | Testada | Info |
| `approved` | Aprovada | Info |
| `enabled` | Habilitada | Sucesso |
| `disabled` | Desabilitada | Neutro |
| `revised` | Revisada | Aviso |

Origem (`source`, `window.skillSourceText`): `created` = "criada"; `imported` = "importada (publisher não verificado)"; `llm_draft` = "rascunho do LLM".

Estado de execução (`skillRunText`): `running` = executando (Info); `awaiting_approval` = aguardando sua decisão (Aviso); `done` = concluída (Sucesso); `failed` = falhou (Erro); `cancelled` = cancelada (Neutro); `rolled_back` = revertida (Aviso).

Estado de passo (`skillStepText`): `pending` = pendente; `running` = em execução (Info); `awaiting_approval` = aguardando sua decisão (Aviso); `done` = concluído (Sucesso); `failed` = falhou (Erro); `denied` = negado (Erro); `undone` = desfeito (Neutro); `cancelled` = cancelado (Neutro).

### 3.3 Layout geral da sub-aba

Corpo a partir de y 284. Barra de progresso indeterminada (`core.skillsBusy`, 4 px, P10-I2) em y 280, largura 1100, só enquanto ocupado. Faixa de resultado (`core.skillsResult`, P10-I1) em y 284, altura 32, só com texto. Com resultado, o conteúdo do segmento começa em y 324; sem resultado, começa em y 284.

### 3.4 Segmento "Minhas" (Básico, com ações Avançadas)

#### 3.4.1 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Bloco "Entradas (JSON)" | 140 | 284 | 1100 | 40 (recolhido) / 180 (aberto) | Disclosure ▸/▾ "Entradas (JSON)" com campo de texto (P10-C1) |
| Lista de skills | 140 | 340 (ou 484 se aberto) | 1100 | até 540 | Cartões de largura total, altura 176, intervalo 16 |
| Estado vazio | 140 | 340 | 1100 | 140 mín. | Ver 3.4.6 |

Cartões de skill: largura total (1100), altura 176, linhas: L1 y 20–40, L2 y 46–62, L3 y 68–84, L4 y 90–108 (painel "Permissões" fica aberto abaixo, expande o cartão), linha de ações y 116–156.

#### 3.4.2 Wireframe

```
 x140                                                                    x1240
 +------------------------------------------------------------------------+ y284
 | ▸ Entradas (JSON)                                                      |
 +------------------------------------------------------------------------+ y340
 | minha_skill · minha_skill v1.0.0                       [ Habilitada ]  |
 | origem: criada · versão ativa                                          |
 | Dependências: ok · permissões aprovadas                                |
 | Permissões                                                             |
 | [ Simular ] [ Aprovar ] [ Executar ]               [ Remover ]  [ ⋯ ]   |
 +------------------------------------------------------------------------+ y532
 | outra_skill ...                                                        |
 +------------------------------------------------------------------------+
```

#### 3.4.3 Anatomia do cartão de skill (w 1100 × h 176, padding 20)

| Linha | y relativo | Conteúdo exato | Origem |
|---|---|---|---|
| L1 | 20–40 | "<nome> · <id> v<versão>" (17 px semibold) à esquerda; badge de estado (Rascunho, Validada, Testada, Aprovada, Habilitada, Desabilitada, Revisada) à direita; badge "Ativa" (Info) se `active` | P10-I3, P10-I4 |
| L2 | 46–62 | "origem: <origem>" + " · versão ativa" se `active`. Origem exata: "criada", "importada (publisher não verificado)", "rascunho do LLM". | P10-I4 (`skillSourceText`) |
| L3 | 68–84 | "Dependências: ok" (Sucesso) ou "Dependências: faltando: <lista>" (Aviso); " · " e "permissões aprovadas" (Sucesso) ou "permissões pendentes" (Aviso) | P10-I5 (`deps_ok`, `missing`, `permissions_ok`) |
| L4 | 90–108 | Link/botão "Permissões" (abre painel 3.4.4) | P10-C8 |
| Ações | 116–156 | Botões na ordem da 3.4.5 | P10-C2..C10 |

#### 3.4.4 Painel "Permissões de <id> v<versão>" (dentro do cartão)

| Linha | Texto exato | Origem |
|---|---|---|
| Título | "Permissões de <id> v<versão>" | P10-T1 |
| Aprovadas | "Aprovadas no Core: sim" ou "Aprovadas no Core: não" + " · Faltando: <lista>" | P10-I6 |
| Necessárias | "Necessárias: <lista de rótulos>" [Obsoleto (WP8): `skillsItems` já traz `permissionsRequired` a partir de `permissions_required` do snapshot (`app/bridge.py:2919`, `app/components/BSkillDetail.qml:130`)] | IMPLEMENTADO (WP8, S4 D1) |
| Nota | "Aprovar permissões não concede nada à skill: ela só usa capacidades já instaladas e aprovadas." | P10-I7 |
| Ação | "Fechar" | UI apenas |

Esta é a forma do "× aprovadas × faltando" do IA §2.2: necessárias (NOVO), aprovadas, faltando.

#### 3.4.5 Ações do cartão (ordem da esquerda para a direita)

Regra: todas as ações ficam desabilitadas com motivo quando `core.skillsBusy` é verdadeiro (texto do motivo: "Aguarde: outra operação de skill em andamento." [novo texto]).

| Ação | Rótulo exato | Nível | Habilitado quando (QML `skillCan`) | Desabilitado: motivo exato | Ação → resultado |
|---|---|---|---|---|---|
| Simular | "Simular" (P10-C2) | Avançado | Sempre (exceto ocupado) | Só ocupado | `core.skillDryRun(id, versão, entradas)`: valida dependências e prévia; não chama capacidades; sucesso marca "Testada" |
| Aprovar | "Aprovar" (P10-C3) | Avançado | Estado `tested` | "Simule a skill antes de aprovar." [novo texto] | `core.skillApprove(id, versão)`: "Aprovada" |
| Habilitar | "Habilitar" (P10-C4) | Básico | Estado `approved` ou `disabled` | "Aprove a skill antes de habilitar ou executar." (SKILL_OP_MESSAGES, existente) para draft, validated, tested, revised | `core.skillEnable(id)`: "Habilitada" |
| Desabilitar | "Desabilitar" (P10-C5) | Básico | Estado `enabled` | "A skill não está habilitada." [novo texto] | `core.skillDisable(id)`: "Desabilitada" |
| Executar | "Executar" (P10-C6) | Básico | Estado `enabled` e sem execução ativa | Sem execução ativa: "Habilite a skill antes de executar." [novo]; com execução ativa: "Já existe uma skill em execução; aguarde ou cancele." (SKILL_OP_MESSAGES, existente) | `core.skillRun(id, entradas)`: abre a execução no segmento Execuções |
| Reverter versão | "Reverter versão" (P10-C7) | Avançado | Sempre (exceto ocupado) | Só ocupado | `core.skillRollback(id)`. Pendência: o snapshot não diz se há versão anterior (ver 10, P-SK-3). |
| Exportar | "Exportar" (P10-C9) | Avançado | Estado `approved`, `enabled` ou `disabled` | "Aprove a skill antes de exportar." [novo texto] | `core.skillExport(id, versão)`. Mostra o caminho gerado (ver 3.6). |
| Remover | "Remover" (P10-C10) | Avançado | Sempre (exceto ocupado) | Só ocupado | Confirmação D9 (8.7), depois `core.skillRemove(id)` |
| Permissões | "Permissões" (P10-C8) | Avançado | Sempre | — | Abre o painel 3.4.4 |

Nota: o item "Validar" do IA §2.2 não aparece aqui. A validação só existe para texto de manifesto (`core.skillValidate(texto)`), então fica no segmento Criar (ver 10, P-SK-1).

#### 3.4.6 Estado vazio

- Título (14 px bold): "Nenhuma skill no Core ainda." [novo texto: o original diz "Crie uma abaixo.", que não existe mais]
- Botão: "Nova skill" → vai para o segmento Criar.
- Moldura tracejada, ícone 32 px, altura mínima 140 (casca).

Origem: P10-I9 (ajustado).

#### 3.4.7 Entradas (JSON), P10-C1 e P10-I8

- Título do disclosure: "Entradas (JSON)".
- Texto de apoio: "Entradas (JSON de objeto, até 16 KiB) para Simular e Executar" (P10-I8).
- Campo: texto inicial "{}", máximo 16 KiB. Valor local (não grava no Core). Usado por Simular e Executar de qualquer cartão.
- Erro de formato (JSON inválido ou não objeto): "Entradas inválidas: use um objeto JSON de até 16 KiB." [novo texto]; desabilita Simular e Executar.

#### 3.4.8 Estados de skill (resumo)

| Situação | Visual | Botões |
|---|---|---|
| Recém-importada (draft) | Badge Rascunho; origem "importada (publisher não verificado)" | Simular, Remover, Permissões, Reverter |
| Validada (texto salvo em Criar) | Badge Validada | Simular, Remover, Permissões |
| Testada | Badge Testada | Aprovar, Simular, Remover |
| Aprovada | Badge Aprovada | Habilitar, Exportar, Simular, Remover |
| Habilitada | Badge Habilitada | Executar, Desabilitar, Exportar |
| Desabilitada | Badge Desabilitada | Habilitar, Exportar |
| Revisada (nova versão de skill aprovada) | Badge Revisada (Aviso) | Simular, Remover (aprovar exige nova simulação) |
| Escalada de permissões | Faixa Aviso: "Escalada de permissões: esta versão pede mais que a anterior; aprove de novo antes de usar." (P10-I19) | Simular e Aprovar |
| Dependência faltando | Faixa Aviso: "Dependências faltando: <lista>" (P10-I20) | Executar desabilitado: "Dependência ausente: execução bloqueada antes de qualquer passo." (SKILL_OP_MESSAGES, existente) |

### 3.5 Segmento "Criar" (Avançado)

#### 3.5.1 Objetivo e condição

Escrever ou colar o manifesto JSON, validar, salvar como rascunho, e opcionalmente gerar o rascunho com o plugin LLM. Condição: sempre visível no segmento. "Gerar com LLM" só habilitado com plugin `llm_engine` em execução (`core.skillLlmAvailable`).

#### 3.5.2 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Rótulo do editor | 140 | 284 | 635 | 20 | "Manifesto da skill em JSON" (14 bold) |
| Editor | 140 | 308 | 635 | 380 | Campo multilinha (P10-C11), máximo 16 KiB |
| Linha de ações | 140 | 700 | 635 | 40 | "Validar" (secundário, x 140, w 140); "Salvar rascunho" (primário, x 292, w 180) |
| Resultado da validação | 140 | 752 | 635 | 128 | Lista de achados (P10-I22) ou "Manifesto válido; nada foi gravado." [novo texto] |
| Painel "Gerar com LLM" | 791 | 284 | 449 | 300 | Ver 3.5.4 |
| Saída do rascunho | 791 | 600 | 449 | 280 | Ver 3.5.5 |

#### 3.5.3 Elementos

| # | ID | Texto exato | Tipo | Fonte de dados (origem) | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| 1 | EX-SK-CR-01 | "Manifesto da skill em JSON" | Rótulo | Texto fixo (P10-T1 "Criar skill") | — | — | Avançado |
| 2 | EX-SK-CR-02 | Placeholder: "Cole o manifesto JSON da skill (até 16 KiB)." [novo texto] | Campo | `core.skillValidate`, `core.skillSaveDraft` (P10-C11, P10-C12, P10-C13) | Campo local | Vazio: placeholder | Avançado |
| 3 | EX-SK-CR-03 | "Validar" | Botão secundário | `core.skillValidate(texto)` → `skill_validate` (não grava) (P10-C12) | Mostra o resultado: "Manifesto válido; nada foi gravado." [novo] ou o código do primeiro achado traduzido | Desabilitado se texto vazio: "Cole um manifesto para validar." [novo]; ocupado: 3.4.5 | Avançado |
| 4 | EX-SK-CR-04 | "Salvar rascunho" | Botão primário | `core.skillSaveDraft(texto)` → `skill_save_draft` grava como "Validada" (não habilitada) (P10-C13) | Grava; a skill aparece em Minhas como Validada | Ver 3.5.6 | Avançado |
| 5 | EX-SK-CR-05 | Achados: "Achado: <mensagem> (<campo>)" | Lista | Formato P10-I22 (`findings[]` com `code` e `field`, `core.codeMessage`). Hoje `findings[]` só chega na prévia de importação; a validação devolve só texto em `core.skillsResult`. NOVO (precisa de mudança na ponte/Core): achados estruturados também na validação do manifesto. | — | Só com achados | Avançado |
| 6 | EX-SK-CR-06 | "Descrição da skill para o LLM" | Rótulo | P10-C14 | — | — | Avançado |
| 7 | EX-SK-CR-07 | Campo "Descrição da skill para o LLM" (máximo 1024 bytes) | Campo | `window.drafts` (local) (P10-C14) | Texto para Gerar com LLM | Vazio: placeholder "Descreva o que a skill deve fazer (até 1024 bytes)." (P10-T3, existente) | Avançado |
| 8 | EX-SK-CR-08 | "Gerar com LLM" | Botão primário | `core.skillDraftWithLlm(descrição)` → `llm_engine.skill_draft`, prazo 30 s (P10-C15). Nunca habilita nada. | Cria rascunho (estado Rascunho, origem "rascunho do LLM"); mostra saída 3.5.5 | Desabilitado com motivo: "Gerar com LLM indisponível: o plugin llm_engine não está ativo." (P10-I15) + link "Instalar em Extensões › Plugins" (8.3) | Avançado |
| 9 | EX-SK-CR-09 | Aviso de estado de ocupado: "Gerando skill com o LLM…" | Texto | `core.skillsBusy`, PENDING_SKILL_DRAFT (existente) | — | Só durante a chamada | Avançado |

#### 3.5.4 Painel "Gerar com LLM"

- Título: "Gerar com LLM" (17 px semibold).
- Texto de apoio: "Descreva o que a skill deve fazer (até 1024 bytes)." (P10-T3).
- Campo (EX-SK-CR-07), botão (EX-SK-CR-08).
- Aviso de disponibilidade (quando indisponível): "Gerar com LLM indisponível: o plugin llm_engine não está ativo." (P10-I15) + "Instalar em Extensões › Plugins" (link, Plugins).
- Texto de regra fixo: "O rascunho nunca fica habilitado. Você valida, simula e aprova antes de usar." [novo texto; deriva de S4 D3 e P10-I23]

#### 3.5.5 Saída do rascunho (depois de "Gerar com LLM")

| Campo | Texto exato | Fonte (origem) |
|---|---|---|
| Título | "Rascunho <id> · v<versão> · <estado> · nada foi habilitado" | `core.skillDraftOutput` (P10-I10) |
| Requisitos | "Requisitos: <lista>" | `draftOutput.requirements` (P10-I11) |
| Ambiguidades | "Ambiguidades: <lista>" | `draftOutput.ambiguities` (P10-I12) |
| Passos previstos | "Passos previstos:" + uma linha "<id> → <chamada>" por passo | `draftOutput.preview` (P10-I13) |
| Diferença | "Diferença:" + texto | `draftOutput.diff` (P10-I14), só quando há |
| Ação | "Abrir no editor" [novo texto] → copia o manifesto para o campo do segmento Criar (UI apenas) | `draftOutput` |

#### 3.5.6 Estados do segmento Criar

| Estado | Visual |
|---|---|
| Editor vazio | Placeholder; "Validar" e "Salvar rascunho" desabilitados com motivo "Cole um manifesto para validar." [novo texto] |
| Validação com achados | Lista de achados em tom Erro; "Salvar rascunho" desabilitado com motivo "Corrija os achados antes de salvar." [novo texto] |
| Validação ok | "Manifesto válido; nada foi gravado." [novo]; "Salvar rascunho" habilitado |
| Ocupado | Barra indeterminada; campos desabilitados |
| Validação não feita desde a última edição | "Salvar rascunho" fica habilitado só depois de "Validar" com resultado ok para o texto atual [regra de UI, novo] |

Nota: o editor JSON manual sempre existe (S4 UI). A geração pelo LLM é só um complemento.

### 3.6 Segmento "Importar/Exportar" (Avançado)

#### 3.6.1 Objetivo e condição

Trazer um pacote `.gskill` de `<home>/skill-imports`, ver a prévia com achados e delta de permissões, e instalar como rascunho. Exportar uma skill para `<home>/skill-exports`. Sempre visível no segmento.

#### 3.6.2 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Painel Importar | 140 | 284 | 542 | 300 | Campo de nome, pasta, Pré-visualizar |
| Painel Exportar | 698 | 284 | 542 | 300 | Lista de skills exportáveis |
| Prévia | 140 | 600 | 1100 | 280 | Só depois de Pré-visualizar |

#### 3.6.3 Elementos

| # | ID | Texto exato | Tipo | Fonte de dados (origem) | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| 1 | EX-SK-IE-01 | "Importar pacote" (título do painel) [novo] | Título | — | — | — | Avançado |
| 2 | EX-SK-IE-02 | "Coloque o arquivo .gskill na pasta de importação e informe o nome, sem caminho e sem extensão." [novo texto] | Texto | Pasta: IMPLEMENTADO (WP8): caminho exposto em `paths` do snapshot e `skillPaths` (`app/pages/Skills.qml`), NF-20 | — | — | Avançado |
| 3 | EX-SK-IE-03 | Pasta: "<home>/skill-imports" [novo texto] | Texto | IMPLEMENTADO (WP8): `skillPaths` (`app/bridge.py:2921`) | — | Até a ponte expor o caminho, mostrar "pasta de importação não informada" [novo] | Avançado |
| 4 | EX-SK-IE-04 | "Nome do pacote, sem caminho" | Rótulo | P10-C16 (texto existente) | — | — | Avançado |
| 5 | EX-SK-IE-05 | Campo de nome (1 a 64 caracteres, `[A-Za-z0-9._-]`) | Campo | `core.skillImport(nome)` (P10-C16) | Valor local | Inválido: "Nome inválido: use letras, números, ponto, traço ou sublinhado (até 64)." [novo texto] | Avançado |
| 6 | EX-SK-IE-06 | "Pré-visualizar" | Botão primário | `core.skillImport(nome)` → `skill_import`: lê só `<home>/skill-imports/<nome>.gskill`, faz scan, gera prévia. Não instala. (P10-C17) | Preenche a prévia 3.6.4 | Desabilitado se nome inválido ou ocupado | Avançado |
| 7 | EX-SK-IE-07 | "Instalar como rascunho" | Botão primário | `core.skillImportConfirm(nome)` → `skill_import_confirm`; instala como rascunho; nunca concede permissões (P10-C18) | Skill aparece em Minhas com origem importada | Habilitado se prévia sem achados e não ocupado. Motivos: com achados: "Corrija os achados antes de instalar." [novo]; duplicata: "Já existe uma skill com este id no Core." (P10-I21) | Avançado |
| 8 | EX-SK-IE-08 | "Exportar" por skill (lista do painel direito) | Botão | `core.skillExport(id, versão)` → `skill_export` (P10-C9) | Grava o pacote; mostra caminho (NOVO, ver 3.6.5) | Só approved, enabled, disabled | Avançado |
| 9 | EX-SK-IE-09 | "Nenhum pacote pré-visualizado." [novo texto] | Estado vazio | — | — | Sem prévia | Avançado |
| 10 | EX-SK-IE-10 | "Nenhuma skill exportável. Aprove uma skill em Minhas." [novo texto] | Estado vazio | — | — | Sem skill aprovada/habilitada/desabilitada | Avançado |

#### 3.6.4 Prévia do pacote (após Pré-visualizar)

| Campo | Texto exato | Fonte (origem) |
|---|---|---|
| Título | "Pacote <nome>: <id> v<versão>" | `core.skillImportPreview` (P10-I16) |
| Publisher | "Publisher: <nome> · não verificado" | `publisher`, `unverified` (P10-I17). Selo "não verificado" discreto (8.4) |
| Nota | "Importar instala como rascunho e nunca concede permissões. Valide, simule e aprove antes de usar." | P10-I23 |
| Permissões exigidas | "Permissões exigidas: <lista de rótulos>" | `permissions_required` (P10-I18) |
| Novas nesta versão | "Novas nesta versão: <lista>" | `permission_delta` (P10-I18) |
| Escalada | "Escalada de permissões: esta versão pede mais que a anterior; aprove de novo antes de usar." | `permissions_escalated` (P10-I19) |
| Dependências faltando | "Dependências faltando: <lista>" | `missing_deps` (P10-I20) |
| Duplicata | "Já existe uma skill com este id no Core." | `duplicate` (P10-I21) |
| Achados | "Achado: <mensagem do código> (<campo>)", um por linha | `findings[]`, `core.codeMessage` (P10-I22) |

#### 3.6.5 Exportação: resultado e caminho

- Texto de sucesso: "Pacote exportado; publisher não verificado" (texto existente sem caminho).
- Caminho: "Arquivo: <caminho>" [novo texto]. NOVO (precisa de mudança na ponte/Core): `skill_export` deve devolver o caminho gerado `<home>/skill-exports/<id>-<versão>.gskill` no resultado (NF-19, AC-13). Sem isso, a linha não aparece e fica "Arquivo gerado na pasta de exportação." [novo texto].
- Campo de assinatura: nenhum. A assinatura não existe (S4 D4: `signature` sempre `null`); a UI mostra "não verificado", nunca "assinado".

### 3.7 Segmento "Execuções" (Avançado)

#### 3.7.1 Objetivo e condição

Acompanhar a execução atual, aprovar ou negar passos que mudam estado, cancelar, e ver o histórico. Sempre visível no segmento. Não tem botão "Executar": a execução começa em Minhas.

#### 3.7.2 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Execução atual | 140 | 284 | 1100 | até 340 | Cartão com linha de título, passos, saídas e ações |
| Histórico | 140 | 644 | 1100 | até 236 | Título "Histórico de execuções" e lista; rola |
| Estado vazio da execução | 140 | 284 | 1100 | 140 | "Nenhuma execução em andamento." [novo texto] |

#### 3.7.3 Elementos

| # | ID | Texto exato | Tipo | Fonte de dados (origem) | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| 1 | EX-SK-EX-01 | Título: "Execução <run> · <skill> · <estado> · passo <id>" | Texto | `core.skillCurrentRun` (P10-I24) | — | Estado em palavra (3.2) | Avançado |
| 2 | EX-SK-EX-02 | Linha por passo: "Passo <id> · <estado> (· <mensagem do código>)" | Lista | `skillCurrentRun.steps[]` (P10-I25), `core.codeMessage` | — | Cor do estado de passo (3.2) | Avançado |
| 3 | EX-SK-EX-03 | "Autorizar passo" (um por passo aguardando) | Botão primário | `core.skillDecide(run, passo, "authorize")` (P10-C20) | Passo segue | Visível só em `awaiting_approval` | Avançado |
| 4 | EX-SK-EX-04 | "Negar passo" (um por passo aguardando) | Botão secundário | `core.skillDecide(run, passo, "deny")` (P10-C19) | Passo negado | Visível só em `awaiting_approval` | Avançado |
| 5 | EX-SK-EX-05 | "Cancelar execução" | Botão perigo | `core.skillCancel(run)` → `skill_cancel`: aborta o passo em voo e desfaz passos concluídos (P10-C21). Confirmação (8.7). | Estado `cancelled` ou `rolled_back` | Habilitado se `running` ou `awaiting_approval` | Avançado |
| 6 | EX-SK-EX-06 | "Saídas: <JSON>" | Texto | `skillCurrentRun.outputs` (P10-I26) | — | Só se houver | Avançado |
| 7 | EX-SK-EX-07 | "Histórico de execuções" | Título | P10-I27 | — | — | Avançado |
| 8 | EX-SK-EX-08 | "Nenhuma execução registrada." | Estado vazio | P10-I27 (texto existente) | — | Histórico vazio | Avançado |
| 9 | EX-SK-EX-09 | Linha de histórico: "<run> · <skill> v<versão> · <estado> · passo <id> · <códigos>" | Lista | `core.skillHistory` (P10-I28; sem conteúdo) | — | Por execução | Avançado |

#### 3.7.4 Passos que pedem decisão

Passos de risco `state_changing` pedem decisão (`skill_decide`). Passos de leitura rodam sem pedir. A decisão de cada passo mostra:

- Alvo: "Alvo: <capability ou tool>" [NOVO: precisa de campo no snapshot de passo; hoje só `id` e `state`; AC-14, S4 D2].
- Efeito: "Efeito: <descrição>" [NOVO: mesma razão].
- Risco: "Risco: escrita (pede aprovação)" ou "Risco: destrutiva (aprovação forte)" (textos de `connRiskText`, reutilizados) [NOVO: mesmo motivo].

Sem esses campos, o segmento mostra só o id do passo, como hoje, e a faixa "Passo <id> aguarda sua decisão." [novo texto]. Isto é uma lacuna declarada (AC-14).

#### 3.7.5 Cancelar execução: efeito e confirmação

- Efeito (texto na confirmação): "Cancelar a execução <run>? Os passos concluídos serão desfeitos." [novo texto; S4 D2: cancel roda undo]
- Esta ação não é "Cancelar" global. Rótulo distinto: "Cancelar execução" (AC-08).

### 3.8 Estados e textos de resultado da sub-aba Skills

| Situação | Texto exato | Origem |
|---|---|---|
| Operação de skill bem-sucedida | Texto do código traduzido (ex.: "Skill habilitada.") [novo; o Core não envia texto de sucesso] | UI apenas |
| Core recusou (stale) | "Skills mudaram no Core; atualize e tente de novo" | SKILL_OP_MESSAGES `stale_skill_revision` |
| Skill desconhecida | "Skill desconhecida ou já removida" | SKILL_OP_MESSAGES `unknown_skill` |
| Import inválido | "Pacote de importação inválido" | `invalid_import` |
| Pacote não encontrado | "Pacote não encontrado na pasta de importação" | `import_not_found` |
| Prévia desatualizada | "A pré-visualização mudou; importe de novo" | `stale_import` |
| Execução revertida | "Execução revertida: os passos concluídos foram desfeitos" | `rolled_back` |
| Falha de desfazer | "Desfazer um passo falhou; confira o efeito manualmente" | `undo_failed` |
| Permissão negada | "Permissão negada: o plugin precisa da permissão aprovada no Gideon Hub" | PERCEPTION_MESSAGES/CODE_MESSAGES (existente) |

Todas as mensagens de código passam por `core.codeMessage(code)`, nunca mostram o código cru.

### 3.9 Regras da sub-aba Skills

- R-SK-1: nada nesta sub-aba concede permissão. Aprovar a skill não aprova permissões do plugin dono (P10-I7).
- R-SK-2: "Validar" não grava; "Simular" não chama capacidades; "Executar" pede decisão em cada passo que muda estado (P10-T2).
- R-SK-3: a origem `llm_draft` nunca vem habilitada; o botão de habilitar só existe depois da aprovação do usuário (S4 D3).
- R-SK-4: nenhum caminho de arquivo é mostrado para o usuário sem o campo novo (NOVO, 3.6.5); a pasta de importação só aparece quando a ponte a expuser (NOVO, EX-SK-IE-03).
- R-SK-5: skill importada entra como rascunho; nenhuma permissão nova é concedida (P10-I23).
- R-SK-6: publisher sempre "não verificado" (S4 D4; `signature` sempre `null`).

---

## 4. Sub-aba "Conexões" (Básico; elementos marcados Avançado)

### 4.1 Visão e condição

| Campo | Valor |
|---|---|
| Objetivo | Conectar contas de serviços (GitHub, Google, Home Assistant, MCP) pela API autorizada, consentir escopo a escopo, ver operações e riscos, revogar e remover contas, escolher a rota por finalidade. |
| Condição | Sempre (inventário SB-07 torna a página condicional a `core.connectionsAvailable`; ver 8.2). |
| Nível da sub-aba | Básico. Elementos Avançados: rotas, operações, MCP, última chamada, ações de manutenção (atualizar, desconectar, revogar, remover). |
| Segmentos | Contas · Rotas · Nova conta (ordem fixa). |
| Dados gerais | `core.connectionsItems` (`id`, `provider`, `label`, `account_ref`, `status`, `granted_scopes`, `pending_scopes`, `user_code`, `fake`, `tools`); `core.connectionsProviders` (`id`, `scopes[]` com `label`, `operations[]` com `name`, `scope`, `risk`); `core.connectionLastCall`; `core.connectionsResult`; `core.connectionsBusy`; `core.connectionsRevision`. |
| Regra central | Nenhum escopo é concedido pela UI sem clique do usuário, por escopo (S5 UI). |

### 4.2 Estados da conta (badge e texto)

Badge (palavras do UI_IA §2.3) e texto de estado (`window.connStatusText`):

| `status` | Badge | Tom | Texto de estado (linha "Estado: …") |
|---|---|---|---|
| `connected` | Conectado | Sucesso | "Estado: conectada" |
| `connecting` | Conectando | Info | "Estado: conectando (aguardando confirmação)" |
| `expired` | Expirado | Aviso | "Estado: expirada" |
| `reauth_required` | Reautenticar | Aviso | "Estado: reautenticação necessária" |
| `offline` | Offline | Neutro | "Estado: offline" |
| `error` | Erro | Erro | "Estado: erro" |
| `disconnected` | Desconectado | Neutro | "Estado: desconectada" |

Selo "SERVIDOR FALSO — sem credenciais reais" (discreto, `item.fake` = true) fica ao lado do nome da conta.

### 4.3 Layout geral

Segmentos y 236. Corpo a partir de y 284.

### 4.4 Segmento "Contas" (Básico, com ações Avançadas)

#### 4.4.1 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Resultado | 140 | 284 | 1100 | 32 | Faixa de `core.connectionsResult` (P11-I1), só com texto |
| Cartões (coluna esquerda, span 6) | 140 | 324 | 542 | auto (mín. 200) | Contas com índice ímpar |
| Cartões (coluna direita, span 6) | 698 | 324 | 542 | auto (mín. 200) | Contas com índice par |
| Estado vazio | 140 | 324 | 1100 | 140 mín. | Ver 4.4.5 |

Cartões em 2 colunas. Altura automática; a linha da grade usa a maior altura. Máximo: 8 contas (P11-C3, CONN_ITEMS_LIMIT). A grade rola na vertical.

#### 4.4.2 Wireframe

```
 x140                          x698                               x1240
 +----------------------------+ +----------------------------------+ y324
 | minha casa · Home Assistant| | Acesso GitHub · GitHub           |
 | [Conectado]                | | [Conectando]                     |
 | Estado: conectada          | | Código para confirmar: AB12-CD34 |
 | Escopos concedidos         | | Escopos pedidos, aguardando seu  |
 | [estados.read]             | | consentimento:                   |
 |                            | | [ ] repositórios (repo:read)     |
 | [Atualizar] [Desconectar]  | | [Consentir escopos marcados]     |
 +----------------------------+ +----------------------------------+
```

#### 4.4.3 Anatomia do cartão de conta (largura 542, padding 20, altura automática)

Ordem vertical:

| Linha | Conteúdo exato | Nível | Origem |
|---|---|---|---|
| 1 | "<nome> · <provedor>" (17 px semibold; provedor = `connProviderName`: GitHub, Google, Home Assistant, MCP). Badge de status à direita (4.2). | Básico | P11-I5, P11-I7 |
| 2 | Selo "SERVIDOR FALSO — sem credenciais reais" (só `fake`) | Básico | P11-I6, AC-11 (selo discreto) |
| 3 | "Estado: <texto do 4.2>" | Básico | P11-I7 |
| 4 | "Conta no serviço: <account_ref>" (só com `account_ref`) | Básico | P11-I8 |
| 5 | "Código para confirmar no servidor: <código>" (só `connecting` com `user_code`) | Básico | P11-I9 |
| 6 | "Escopos concedidos: <lista>" ou "Escopos concedidos: nenhum" [novo texto para vazio] | Básico | P11-I10 |
| 7 | "Escopos pedidos, aguardando seu consentimento:" + caixas (uma por escopo) com rótulo "<rótulo> (<escopo>)" | Básico | P11-I11, P11-C4, P11-I12 |
| 8 | Campo de token (só Home Assistant em `connecting`): rótulo "Token de longa duração do Home Assistant", campo oculto (16 a 256 caracteres), botão "Enviar token" | Básico | P11-C5, P11-C6 |
| 9 | Botões de ação (4.4.4) | Básico/Avançado | P11-C3..C12 |
| 10 | Bloco "Ferramentas descobertas (a descrição vem do servidor e é só texto)" (só MCP com ferramentas) | Avançado | P11-T2, P11-I13, P11-I14, P11-C13 |
| 11 | Bloco "Operações" (lista de operações do provedor com risco) | Avançado | P11-T2, P11-I15 |
| 12 | "Última chamada: <operação> · <resultado>" | Avançado | P11-I16 |

Texto de apoio do bloco de operações (quando vazio): "Nenhuma operação disponível para este provedor." [novo texto]

#### 4.4.4 Ações do cartão

| Ação | Rótulo exato | Nível | Habilitado quando (`connCan`) | Desabilitado: motivo | Ação → resultado / confirmação |
|---|---|---|---|---|---|
| Conectar | "Conectar" (P11-C8) | Básico | Desconectada, erro, offline, expirada ou reautenticação | "Indisponível: já há uma operação de conexão em andamento." [novo] quando `connectionsBusy`; senão "Indisponível durante a sessão de voz." (8.6) | `core.connectionConnect(id)` → `connecting` |
| Consentir escopos marcados | "Consentir escopos marcados" (P11-C7) | Básico | Visível se há escopo pendente; habilitado se ao menos um marcado | "Marque ao menos um escopo para consentir." [novo] | `core.connectionConsent(id, JSON dos marcados)`: concede só os marcados; os não marcados continuam pendentes |
| Atualizar | "Atualizar" (P11-C9) | Avançado | Não MCP e (conectada, expirada, reautenticação ou erro) | "Indisponível: esta conta não tem credencial para atualizar." [novo] | `core.connectionRefresh(id)` |
| Desconectar | "Desconectar" (P11-C10) | Avançado | Conectando, conectada, MCP com erro, expirada, reautenticação | "Indisponível: a conta já está desconectada." [novo] | `core.connectionDisconnect(id)`: apaga segredos locais; status `disconnected` |
| Revogar | "Revogar" (P11-C11), Perigo | Avançado | Conectada, expirada ou reautenticação | "Indisponível: só é possível revogar conta conectada, expirada ou com reautenticação." [novo] | Confirmação (8.7). Depois `core.connectionRevoke(id)`: revoga no servidor e apaga. Hoje executa sem confirmação (AC-05). |
| Remover | "Remover" (P11-C12), Perigo | Avançado | Qualquer status exceto `connecting` | "Indisponível enquanto a conta está conectando." [novo] | Confirmação (8.7). Depois `core.connectionRemove(id)`. Hoje sem confirmação (AC-05). |
| Confiar (por ferramenta MCP) | "Confiar" (P11-C13) | Avançado | Só ferramenta com estado `needs_reapproval` | — | Confirmação curta (8.7). Depois `core.connectionTrustTools(id, [nome])`. Cada chamada ainda pede aprovação. |

Layout dos botões: os Básicos aparecem na linha de ações; os Avançados (Atualizar, Desconectar, Revogar, Remover) ficam no menu ⋯ do cartão (rótulo "Mais ações de <nome>") para caber em 542 px. Revogar e Remover são itens com cor Perigo no menu.

Nota: menu ⋯ é uma decisão de layout (UI apenas). Com "Mostrar opções avançadas" desligado, o menu ⋯ não aparece e ficam só Conectar e Consentir.

#### 4.4.5 Estado vazio e textos

- "Nenhuma conta ainda. Adicione uma em Nova conta." [novo texto; adapta P11-I4 "Nenhuma conta ainda. Adicione uma acima."]
- Botão: "Nova conta" → segmento Nova conta.

#### 4.4.6 Consentimento por escopo, passo a passo (visual)

1. Conta criada: "Desconectada" (Neutro).
2. "Conectar" → "Conectando (aguardando confirmação)" (Info).
3. Para GitHub e Google: aparece "Código para confirmar no servidor: <código>". O usuário confirma no site do provedor. O Gideon não abre o site (sem navegador).
4. Escopos pedidos aparecem como caixas. Nenhuma está marcada por padrão (regra: `connDraftRevision`, nunca marcada sozinha).
5. O usuário marca e clica "Consentir escopos marcados". O Core grava só os escopos marcados.
6. Com escopo concedido, a conta fica "Conectado" (Sucesso). Escopos pedidos não marcados continuam em "pendentes".
7. Escopo de escrita ou público/destrutivo ganha rótulo de risco na lista de operações (4.4.3, linha 11).

Home Assistant: "Conectar" → passo de consentimento primeiro (escopos) → depois o campo de token (`consent_required` se o token vier antes) → "Enviar token" faz uma sonda e depois mostra "Conectado" ou "Reautenticação necessária".

MCP: "Conectar" inicia o servidor (sandbox, sem rede) e executa `initialize`. Depois aparecem os escopos pedidos (`mcp.discover`, `mcp.call`, `mcp.call_destructive`). Consentir conecta. Depois, "Testar leitura: listar ferramentas" (mcp.discover) lista as ferramentas com estado; ferramenta nova ou alterada fica "precisa de nova aprovação" com botão "Confiar".

#### 4.4.7 Estados vazios de chamada

| Caso | Texto exato [novo] |
|---|---|
| Conta sem escopo concedido | "Escopo não concedido: conceda o escopo antes de usar esta operação; nenhuma chamada foi feita" (existente em CONN_MESSAGES `scope_not_granted`) |
| Consentimento recusado | "Consentimento recusado no servidor; nada foi concedido" (existente, `consent_denied`) |
| Código expirou | "Código de confirmação expirou; conecte a conta de novo" (existente, `device_expired`) |
| Limite | "Limite de 8 contas atingido; remova uma conta antes" (existente, `connection_limit`) |

### 4.5 Segmento "Rotas" (Avançado)

#### 4.5.1 Objetivo e condição

Ver, por finalidade, qual rota o Gideon escolheria (API da conta ou fallback visual) e por que as outras foram descartadas. Planejar não executa nada. Disponível quando `core.registryAvailable` é verdadeiro; senão mostra "Rotas indisponíveis agora." (REG_MESSAGES `registry_unavailable`, existente).

#### 4.5.2 Layout

Cartões em largura total (span 12), altura automática, uma linha por finalidade (3 finalidades: `create_issue`, `list_events`, `read_state`; vindos de `core.registryPurposes`).

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Cartão da finalidade | 140 | 284 | 1100 | auto | Ver 4.5.3 |
| Espaço entre cartões | — | — | — | 16 | |

#### 4.5.3 Anatomia do cartão de finalidade

| Linha | Conteúdo exato | Origem |
|---|---|---|
| L1 | "<label da finalidade>" (17 px semibold; vem de `purposes[].label`) e "Planejar" (botão secundário, à direita) | P11-C15 |
| L2 | "<finalidade> · rota escolhida: <rota>" ou "<finalidade> · nenhuma rota disponível" | P11-I18 |
| L3 | Tabela de candidatos: colunas "Situação" · "Rota" · "Estado" · "Motivo" | P11-I19 |
| L4 | Interruptor "Permitir fallback visual" (só `create_issue`); estado: "Fallback visual: desligado (padrão)" ou "Fallback visual: ligado por você" [novo rótulo do switch] | P11-C16, P11-I20 |
| L5 | Aviso do fallback visual (só `create_issue`), texto fixo abaixo | P11-I21 |

Tabela de candidatos (P11-I19), uma linha por candidato, "Escolhida" ou "Descartada" (texto novo para a coluna):

- "Escolhida": tom Sucesso.
- "Descartada": tom Neutro.
- Rota traduzida: `connection` = "API da conta"; `visual` = "Visual (tela sintética)" [novo; UI apenas].
- Estado traduzido: `available` = "disponível" (Sucesso); `not_connected` = "não conectada" (Aviso); `expired` = "expirada" (Erro); `scope_not_granted` = "escopo não concedido" (Erro); `no_api` = "sem API" (Neutro); `visual_not_allowed` = "fallback visual desligado" (Neutro); `disabled` = "desativada" (Neutro). [novo; UI apenas]
- Motivo: o texto que vem do Core (`reason`, já em português).

Texto de apoio fixo acima dos cartões: "Rotas: o Gideon escolhe a API autorizada quando há conta conectada com escopo. Nunca troca de rota para contornar token expirado, reautenticação ou escopo negado." [novo texto; deriva de S5 E3 e REG_VISUAL_WARNING]

Mensagem de rota indisponível (REG_MESSAGES `route_unavailable`): "Nenhuma rota disponível para esta finalidade; veja os motivos. Nada foi executado" (existente).

#### 4.5.4 Elementos

| # | ID | Texto exato | Tipo | Fonte de dados (origem) | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| 1 | EX-CN-RT-01 | "Planejar" | Botão secundário | `core.registryPlan(finalidade)` → `registry_plan` (não executa) (P11-C15) | Atualiza a linha L2 e L3 | Desabilitado enquanto `core.registryBusy` | Avançado |
| 2 | EX-CN-RT-02 | "Permitir fallback visual" | Interruptor | `core.registryAllowVisual(finalidade, ligado)` (P11-C16) | Liga ou desliga. Ligar pede confirmação (8.7); desligar não. | Desligado por padrão; só `create_issue` | Avançado |
| 3 | EX-CN-RT-03 | REG_VISUAL_WARNING (texto integral, ver 4.5.5) | Aviso | `core.registryVisualWarning` (P11-I21) | — | Sempre visível em `create_issue` | Avançado |
| 4 | EX-CN-RT-04 | Resultado: `core.registryResult` (P11-I17) | Faixa | — | — | Só com texto | Avançado |

#### 4.5.5 Texto do fallback visual (exato, do bridge)

"Atenção: o fallback visual dirige uma tela por cliques e digitação, é menos seguro que a API e só vale quando não há conta conectada. Nunca contorna token expirado, reautenticação ou escopo negado. A publicação ainda pede sua aprovação."

### 4.6 Segmento "Nova conta" (Básico)

#### 4.6.1 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Formulário | 140 | 284 | 542 | 320 | Provedor, nome, botão |
| Passo a passo | 698 | 284 | 542 | 320 | Texto explicativo (4.6.4) |
| Resultado | 140 | 620 | 1100 | 32 | Faixa de `core.connectionsResult` |

#### 4.6.2 Elementos

| # | ID | Texto exato | Tipo | Fonte de dados (origem) | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| 1 | EX-CN-NC-01 | "Provedor" | Rótulo | P11-C1 | — | — | Básico |
| 2 | EX-CN-NC-02 | Opções: "GitHub" · "Google" · "Home Assistant" · "MCP" | Seletor | Local (`connProviderChoices`); valor enviado: `github`, `google`, `homeassistant`, `mcp` | Define o provedor | Padrão: GitHub | Básico |
| 3 | EX-CN-NC-03 | "Nome da conta (ex.: Casa)" | Campo | `core.connectionLabelProblem(texto)` (P11-I3); máximo 64 | Valor local | Problema: texto do bridge | Básico |
| 4 | EX-CN-NC-04 | "Adicionar conta" | Botão primário | `core.connectionAdd(provedor, nome)` → cria conta desconectada (P11-C3) | Conta aparece em Contas como "Desconectado" | Desabilitado (ver 4.6.3) | Básico |
| 5 | EX-CN-NC-05 | Problema do nome | Texto | `core.connectionLabelProblem(texto)` | — | Só com problema | Básico |

#### 4.6.3 Motivos de desabilitado do botão "Adicionar conta"

| Condição | Texto exato [novo, exceto o limite] |
|---|---|
| Nome vazio | "Digite um nome para a conta." |
| Nome inválido | Texto de `connectionLabelProblem` |
| Operação de conexão em andamento | "Aguarde: outra operação de conexão está em andamento." |
| 8 contas | "Limite de 8 contas atingido; remova uma conta antes" (existente, `connection_limit`) |
| Sessão de voz | "Indisponível durante a sessão de voz." (8.6) |

#### 4.6.4 Texto explicativo do passo a passo (painel direito)

Título: "Como conectar" [novo]

1. "Escolha o provedor e dê um nome à conta." [novo]
2. "Clique em Conectar. Para GitHub e Google, confirme o código no site do provedor." [novo]
3. "Marque só os escopos que você quer conceder e clique em Consentir escopos marcados." [novo]
4. "Escrita e ações públicas pedem aprovação a cada uso." [novo; deriva de P11-T1]

Bloco "Como funciona" (recolhido): "Gideon usa a API autorizada de cada serviço. Você concede cada escopo; escrita e ações públicas pedem aprovação. Neste ambiente, todas as contas são servidores falsos." (P11-T1, texto existente, integral)

### 4.7 Elementos da aba (transversais)

| Campo | Valor |
|---|---|
| Contador de pendências (badge) | Número de contas em `connecting`, `expired`, `reauth_required` ou com escopo pendente (1.2). |
| Barra de progresso | Indeterminada (4 px) em y 280 quando `core.connectionsBusy` (P11-I2). Acessibilidade: "Operação de conexão em andamento". |
| Nota de origem | Os IDs P11-* deste segmento estão em 4.4 a 4.6. |
| Ocupado | Desabilita a criação e as ações de conta (regra de `connectionsBusy`). |

---

## 5. Sub-aba "Modelos LLM" (Básico; condicional)

### 5.1 Visão e condição

| Campo | Valor |
|---|---|
| Objetivo | Escolher o modelo do motor LLM a partir do catálogo do plugin, testar, voltar ao último bom, configurar provedor e chaves, e definir o fallback. Nada aqui muda wake, STT ou TTS (C2). |
| Condição | `core.modelsAvailable` (plugin `llm_engine` em execução com `llm_engine.models`). Sem isso, a sub-aba não aparece (1.2). |
| Nível da sub-aba | Básico. Elementos Avançados: personalizados, fallback, hardware, detalhes técnicos do modelo. |
| Segmentos | Modelo atual · Catálogo · Personalizados · Provedor e chaves · Fallback e hardware. |
| Ponto de atenção | "Provedor e chaves" (D3) funciona sem o plugin (AC-09). Ver 10, P-MD-1. |

### 5.2 Estado do modelo (texto e cor)

Vem de `core.modelsStatus` (P8-I1; `model_status` no bridge). Textos exatos e tons:

| Texto do bridge | Texto exibido | Tom | Significado |
|---|---|---|---|
| "Disponível" | Disponível | Sucesso | Modelo configurado, com recursos suportados |
| "Sem chave" | Sem chave | Aviso | Provedor de nuvem sem chave salva |
| "Sem consentimento" | Sem consentimento | Aviso | Provedor de nuvem sem consentimento de nuvem |
| "INDISPONÍVEL: tool_use não suportado" | Indisponível: uso de ferramenta não suportado [novo; traduz `tool_use`] | Erro | Modelo não suporta ferramenta exigida |
| "Sem dados do modelo" | Sem dados do modelo [novo] | Neutro | Modelo configurado não está no catálogo carregado |
| "Em teste" | Em teste | Info | Selftest em andamento (PENDING_MODELS, existente) |
| "Sem modelo selecionado" | Nenhum modelo configurado | Neutro | Sem configuração |

Origem: P8-I1 (formato "Estado do modelo atual: <texto>"). Rótulo completo na linha: "Estado do modelo atual: <texto exibido>" [mantém P8-I1].

### 5.3 Layout geral

Segmentos y 236. Corpo a partir de y 284. Barra de progresso (`core.modelsBusy`, P8-I3) em y 280. Faixa de resultado (`core.modelsResult`, P8-I4) em y 284, altura 32, só com texto.

### 5.4 Segmento "Modelo atual" (Básico)

#### 5.4.1 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Cartão "Configurado" | 140 | 324 | 542 | 260 | Modelo atual e ações |
| Cartão "Detalhes do modelo atual" | 698 | 324 | 542 | 520 | Detalhes técnicos (Avançado) |

#### 5.4.2 Wireframe

```
 x140                          x698                               x1240
 +----------------------------+ +----------------------------------+ y324
 | Configurado: OpenRouter ·  | | Detalhes (Avançado)              |
 | modelo-x                   | | Licença · Quantização · Hash     |
 | Estado do modelo atual:    | | Recursos · Contexto · Custo      |
 | [Disponível]               | | Latência e hardware mínimo       |
 | Último bom: <modelo>       | | Funciona offline / Requer rede   |
 | [Testar] [Voltar ao último | |                                  |
 |  bom] [Usar outro modelo]  | |                                  |
 +----------------------------+ +----------------------------------+
```

#### 5.4.3 Elementos

| # | ID | Texto exato | Tipo | Fonte de dados (origem) | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| 1 | EX-MD-AT-01 | "Configurado: <provedor> · <modelo>" ou "Nenhum modelo configurado" | Texto | `core.modelsSelected` (P8-I2) | — | Dois textos | Básico |
| 2 | EX-MD-AT-02 | "Estado do modelo atual: <texto>" + badge (5.2) | Texto + badge | `core.modelsStatus` (P8-I1) | — | Ver 5.2 | Básico |
| 3 | EX-MD-AT-03 | "Último bom: <provedor> · <modelo>" ou "Nenhum modelo marcado como bom ainda." [novo] | Texto | IMPLEMENTADO (WP8): `llm.config.lkg` vai em `core.llmConfig` e aparece em `app/pages/ModelosLlm.qml:49` | — | Sem LKG: texto acima | Avançado |
| 4 | EX-MD-AT-04 | "Testar" | Botão secundário | IMPLEMENTADO (WP8): `core.llmSelftest()` (`app/bridge.py:2023`, `manual_selftest` via `llm_engine.models` `selftest {}`), sem trocar o modelo | Executa o teste; mostra "Modelo testado: funciona." [novo] ou o código de erro traduzido (`model_selftest_failed`) | Desabilitado se `core.modelsBusy` ou sem configuração: "Configure um modelo antes de testar." [novo] | Básico |
| 5 | EX-MD-AT-05 | "Voltar ao último bom" | Botão secundário | IMPLEMENTADO (WP8): `core.llmRollback()` (`app/bridge.py:2032`, op `llm_rollback` com a revisão atual), `ModelosLlm.qml` | Restaura o último bom | Desabilitado sem LKG: "Nenhum modelo marcado como bom ainda." [novo] | Básico |
| 6 | EX-MD-AT-06 | "Usar outro modelo" | Link/botão secundário | UI apenas | Vai para o segmento Catálogo | — | Básico |
| 7 | EX-MD-AT-07 | "Funciona offline" ou "Requer rede" | Texto | `selectedModel.offline` (P8-I16) | — | Só com modelo carregado | Básico |
| 8 | EX-MD-AT-08 | Progresso | Barra | `core.modelsBusy` (P8-I3) | — | Visível se ocupado | Básico |
| 9 | EX-MD-AT-09 | Resultado | Faixa | `core.modelsResult` (P8-I4) | — | Só com texto | Básico |

#### 5.4.4 Detalhes do modelo atual (cartão direito)

Fonte: linha do catálogo com o mesmo `provider` e `model` de `modelsSelected`, dentro das páginas já carregadas em `modelsRecommended`/`modelsCustom`. Se não estiver carregado: "Detalhes indisponíveis: carregue o catálogo para ver este modelo." [novo texto] e botão "Carregar mais" (P8-C5). NOVO (precisa de mudança na ponte/Core): `describe {id}` (NF-07) para buscar um modelo por id sem paginar.

| Campo | Texto exato | Origem | Nível |
|---|---|---|---|
| Título | "<rótulo> · Local|Nuvem · <provedor> · <modelo>" (P8-I9) | `selectedModel` | Avançado |
| Certificação | "Certificação: <selo> · <evidência> · <data>" (P8-I10) | `selectedModel.certification` | Avançado |
| Licença | "Licença: <licença>" (P8-I11) | `selectedModel.license` | Avançado |
| Quantização | "Quantização: <valor>" (P8-I11) | `selectedModel.quantization` | Avançado |
| Hash | "Hash (SHA-256): <hash>" (P8-I11) | `selectedModel.sha256` | Avançado |
| Backend | "Backend: <valor>" (P8-I11) | `selectedModel.backend` | Avançado |
| Recursos | "Recurso streaming: <Suportado|Não suportado|Desconhecido>", "Recurso tool_use: …", "Recurso vision: …", "Recurso cancel: …" (P8-I12). Texto traduzido: "uso de ferramenta" no lugar de tool_use [novo; UI apenas]. | `core.featureLabel` | Avançado |
| Contexto | "Contexto: <N> tokens" ou "Contexto: não informado" (P8-I13) | `features.context_tokens` | Avançado |
| Custo | "Custo (USD por milhão de tokens): entrada <X> · saída <Y>" ou "Custo: não informado" (P8-I14) | `selectedModel.cost` | Avançado |
| Latência | "Latência: <baixa|média|alta|desconhecida> · hardware mínimo: RAM <X> GB, GPU <…>" (P8-I15) | `latency_hint`, `min_hardware` | Avançado |
| Offline | "Funciona offline" ou "Requer rede" (P8-I16) | `selectedModel.offline` | Básico |

Os textos "Local" e "Nuvem" vêm de `kind`. "Desconhecido", "Suportado", "Não suportado" vêm de `FEATURE_LABELS`.

### 5.5 Segmento "Catálogo" (Básico)

#### 5.5.1 Objetivo e condição

Ver os modelos recomendados pelo plugin, filtrar por Local ou Nuvem, ver detalhes e usar um modelo (fluxo F4). Visível quando `core.modelsAvailable`.

#### 5.5.2 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Filtro "Mostrar:" | 140 | 284 | 449 | 36 | Segmentado "Todos" · "Local" · "Nuvem" (P8-C3) |
| Contagem | 605 | 284 | 635 | 36 | Texto "N de M" (P8-I5) alinhado à esquerda do painel de detalhe (x 605) |
| Lista | 140 | 332 | 449 | 472 | Linhas de 56 px; rola |
| Detalhe | 605 | 284 | 635 | 596 | Painel do modelo selecionado (5.5.4) |
| Carregar mais | 140 | 812 | 449 | 40 | Botão "Carregar mais" (P8-C5), só se há mais itens |

Largura 449 = span 5; detalhe começa na coluna 5 (x 605) e tem span 7 (635).

#### 5.5.3 Linha do modelo (h 56)

| Parte | Conteúdo exato | Origem |
|---|---|---|
| Nome | "<rótulo>" (14 px semibold) | `label` (P8-C4, P8-I8) |
| Tipo | "Local" ou "Nuvem" (12 px) | `kind` |
| Selo | "Certificado", "Testado", "Declarado" ou "Candidato" (badge; tons: Certificado Sucesso, Testado Info, Declarado Neutro, Candidato Aviso) | `certificationBadge(certification.state)` (P8-I7) |
| Seleção | Linha inteira clicável; selecionada = fundo acento 18% | UI apenas |

Textos da lista vazia: "Nenhum modelo nesta lista." (P8-I6).

#### 5.5.4 Painel de detalhe do modelo

Mostra os mesmos campos de 5.4.4 e mais:

| Elemento | ID | Texto exato | Fonte | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|
| Botão "Usar este modelo" | EX-MD-CT-01 | "Usar este modelo" (P8-C6) | `core.useModel(id, revisão capturada)` → `llm_configure` → `selftest` → `llm_mark_good` ou `llm_rollback` (fluxo F4) | Ver F4 | Desabilitado com motivo 5.5.5 | Básico |
| Aviso de nuvem | EX-MD-CT-02 | "Mensagens serão enviadas ao provedor escolhido na nuvem" (D3-I3) — só para modelo de nuvem | `kind` = cloud | — | Só nuvem | Básico |

#### 5.5.5 Motivos de desabilitado de "Usar este modelo"

| Condição | Texto exato [novo] |
|---|---|
| Nenhum modelo selecionado | "Escolha um modelo na lista." |
| Ocupado | "Aguarde: a operação de modelo anterior ainda está em andamento." |
| Modelo de nuvem sem chave | "Sem chave: salve a chave do provedor em Provedor e chaves." |
| Modelo de nuvem sem consentimento | "Sem consentimento: permita o envio à nuvem em Provedor e chaves." |
| Sessão de voz | "Indisponível durante a sessão de voz." (8.6) |

As duas últimas condições são checadas na UI (`core.llmSecretsConfigured`, `core.llmConfig.cloud_consent`). Elas evitam um teste que o Core recusaria de qualquer forma (`key_missing`, `cloud_not_authorized`). Regra de UI apenas.

### 5.6 Segmento "Personalizados" (Avançado)

#### 5.6.1 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Formulário | 140 | 284 | 542 | 596 | Campos da 5.6.2 e botão |
| Lista | 698 | 284 | 542 | 596 | Modelos personalizados (até 16), contagem e Remover |

#### 5.6.2 Formulário (ordem)

| # | ID | Texto exato | Tipo | Fonte (origem) | Regras | Nível |
|---|---|---|---|---|---|---|
| 1 | EX-MD-PS-01 | "Provedor do modelo personalizado" | Rótulo | P8-C8 | Opções (texto exato): "Local (llama.cpp)" · "Ollama (local)" · "Personalizado (https)" · "OpenRouter (nuvem)" · "OpenCode (nuvem)" · "Google AI Studio (nuvem)" | Avançado |
| 2 | EX-MD-PS-02 | "Identificador do modelo" | Campo | P8-C9 | Letras, números, . _ : / - (máx. 128) | Avançado |
| 3 | EX-MD-PS-03 | "Porta do servidor local, de 1024 a 65535" | Spin (padrão 8080) | P8-C10 | Habilitado só para "Local (llama.cpp)" e "Ollama (local)" | Avançado |
| 4 | EX-MD-PS-04 | "URL https do modelo personalizado" | Campo (máx. 200) | P8-C11 | Habilitado só para "Personalizado (https)" | Avançado |
| 5 | EX-MD-PS-05 | "Recursos declarados (não certificados)" | Subtítulo | P8-T2 | — | Avançado |
| 6 | EX-MD-PS-06 | "Streaming" · "Tool use" · "Visão" · "Cancelamento" (cada um com Desconhecido, Suportado, Não suportado) | Quatro seletores | P8-C12..C15 | Sempre; valor declarado | Avançado |
| 7 | EX-MD-PS-07 | "Salvar modelo personalizado" | Botão primário | `core.saveCustomModel(form)` (P8-C16) | Grava (máximo 16) | Avançado |
| 8 | EX-MD-PS-08 | Problema do formulário | Texto | `core.customFormProblem(form)` (P8-I21) | Mostra só com texto | Avançado |

Motivo de desabilitado do botão 7: "Indisponível: …" com `customFormProblem` ou "Aguarde: operação de modelo em andamento." [novo].

Declarar recurso não certifica nada. Texto abaixo dos seletores: "Recursos declarados não são certificados; o selftest é que confirma." [novo texto; S C2: declarado não é certificado]

#### 5.6.3 Lista de personalizados

- Cabeçalho da lista: "Modelos personalizados" [novo texto]. O título "Adicionar modelo personalizado" (P8-T1) fica no cabeçalho do formulário à esquerda.
- Contagem: "N de 16" (P8-I5 custom).
- Linha: "<rótulo> · Local|Nuvem" + selo "Declarado" (5.5.3).
- Botão "Remover" (P8-C7) só com um modelo selecionado; Perigo; Avançado; confirmação D7 (8.7); depois `core.deleteCustomModel(id)`. Texto de D7: "Remover <rótulo> da lista de modelos personalizados? O modelo no provedor não é apagado."
- Vazio: "Nenhum modelo personalizado. Adicione um à esquerda." [novo texto]

### 5.7 Segmento "Provedor e chaves" (Básico)

#### 5.7.1 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Cartão "Configuração" | 140 | 324 | 542 | 430 | Provedor, modelo, URL, chave, status da chave |
| Cartão "Nuvem e salvar" | 698 | 324 | 542 | 430 | Consentimento, aviso, Salvar configuração, consentimento salvo, resultado |
| Faixa "Como funciona" | 140 | 770 | 1100 | 56 | Recolhida: "Motor opcional. Sem ele, voz, wake e comandos da Base continuam funcionando." |

#### 5.7.2 Elementos

| # | ID | Texto exato | Tipo | Fonte de dados (origem) | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| 1 | EX-MD-PK-01 | "Provedor" | Rótulo | D3-T2 | — | — | Básico |
| 2 | EX-MD-PK-02 | Opções: "OpenRouter" · "OpenCode" · "Google AI Studio" · "Personalizado" | Seletor | `core.llmConfig.provider` (valor inicial), D3-C1 | Define o provedor | Habilitado se `core.llmConfigAvailable` | Básico |
| 3 | EX-MD-PK-03 | "Modelo: letras, números e . _ : / - (até 128)" | Rótulo + campo | D3-C2, D3-T2 | Valor local | Habilitado se `llmConfigAvailable` | Básico |
| 4 | EX-MD-PK-04 | "URL personalizada: somente https (http apenas em loopback de teste)" | Rótulo + campo | D3-C3, D3-T2 | Valor local | Só se "Personalizado" e `llmConfigAvailable` | Avançado |
| 5 | EX-MD-PK-05 | "Chave" + campo oculto (máx. 256) | Campo | `core.setApiKey(provedor, chave)` (D3-C4) | Campo limpa após envio; nunca exibe valor de volta (`Main.qml:330-331`) | Habilitado se `llmConfigAvailable` | Básico |
| 6 | EX-MD-PK-06 | "Chave configurada" ou "Sem chave" | Badge | `core.llmSecretsConfigured[provedor]` (D3-I1) | — | Tons: Sucesso / Aviso | Básico |
| 7 | EX-MD-PK-07 | "Salvar chave" | Botão primário | `core.setApiKey` (D3-C5) | Grava no cofre do Core; limpa o campo | Habilitado se disponível e campo não vazio | Básico |
| 8 | EX-MD-PK-08 | "Remover chave" | Botão Perigo | `core.clearApiKey(provedor)` (D3-C6) | Confirmação (8.7); depois apaga a chave | Habilitado se disponível e chave configurada. Hoje sem confirmação (AC-05). | Avançado |
| 9 | EX-MD-PK-09 | "Permitir envio de conversas ao provedor na nuvem" | Caixa | D3-C7; valor salvo em `core.llmConfig.cloud_consent` | Local; gravado por "Salvar configuração". Nunca ligado sozinho. | Habilitado se `llmConfigAvailable` | Básico |
| 10 | EX-MD-PK-10 | "Mensagens serão enviadas ao provedor escolhido na nuvem" | Aviso | D3-I3 (texto fixo) | Sempre visível | — | Básico |
| 11 | EX-MD-PK-11 | "Consentimento salvo: concedido" ou "Consentimento salvo: não concedido" | Texto | D3-I2 (`core.llmConfig.cloud_consent`) | — | — | Básico |
| 12 | EX-MD-PK-12 | "Salvar configuração" | Botão primário | `core.configureLlm(provedor, modelo, url, consentimento, revisão)` → `llm_configure` (D3-C8) | Grava provedor, modelo, URL e consentimento | Habilitado se `llmConfigAvailable`, modelo válido e provedor não local | Básico |
| 13 | EX-MD-PK-13 | "Configuração local ativa: <provedor> · <modelo>. Troque em Catálogo." [adapta D3-I4] | Aviso | `core.llmConfig.provider` (local/ollama) | Link para Catálogo | Só se local salvo | Básico |
| 14 | EX-MD-PK-14 | Resultado | Faixa | `core.llmResult` (D3-I5) | — | Só com texto | Básico |
| 15 | EX-MD-PK-15 | "Motor opcional. Sem ele, voz, wake e comandos da Base continuam funcionando." | Texto | D3-T1 | — | — | Básico |

#### 5.7.3 Motivos de desabilitado (campos e botões)

| Condição | Texto exato [novo] |
|---|---|
| `core.connected` falso | "Core desconectado." |
| Sessão de voz ativa | "Indisponível durante a sessão de voz." (8.6) |
| Modo seguro ou reinício pendente | "Reinicie o Core para aplicar a configuração." [novo; NF-22 e `configurationStatus`] |
| Modelo vazio | "Digite o modelo para salvar." [novo] |

#### 5.7.4 Regras de chave

- A chave sai do QML na mesma chamada e o campo é limpo; nunca é exibida de volta (D3 regra).
- Campo de chave: `echoMode` de senha; tamanho máximo 256.
- "Chave configurada" só quando existe no cofre (`llmSecretsConfigured`).

### 5.8 Segmento "Fallback e hardware" (Avançado)

#### 5.8.1 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Cartão "Fallback (opcional)" | 140 | 324 | 542 | 500 | Atual, seleção, avisos, ações |
| Cartão "Hardware e plugin" | 698 | 324 | 542 | 500 | Hardware, apagar dados do plugin |

#### 5.8.2 Elementos

| # | ID | Texto exato | Tipo | Fonte de dados (origem) | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| 1 | EX-MD-FB-01 | Título "Fallback (opcional)" | Título | P8-T1 | — | — | Avançado |
| 2 | EX-MD-FB-02 | "Atual: <provedor> · <modelo>" ou "Nenhum fallback configurado" | Texto | `core.modelsFallback` (P8-I18) | — | Dois textos | Avançado |
| 3 | EX-MD-FB-03 | Texto de regra: "Usado só depois de erro recuperável do modelo principal (429, 5xx, rede ou tempo esgotado). Nunca em erro de chave ou permissão." [novo texto; C2] | Texto | — | — | — | Avançado |
| 4 | EX-MD-FB-04 | Seletor de fallback: lista de todos os modelos (recomendados e personalizados) com "Local" ou "Nuvem" | Seletor | `core.modelsRecommended`, `core.modelsCustom` (P8-C17) | Escolhe | Sempre | Avançado |
| 5 | EX-MD-FB-05 | "Mensagens poderão ir para a nuvem se o modelo principal falhar" | Aviso | `window.fallbackIsCloud()` (P8-I19) | — | Só com fallback de nuvem | Avançado |
| 6 | EX-MD-FB-06 | "Para fallback na nuvem, marque o consentimento em Provedor e chaves." | Aviso | `core.llmConfig.cloud_consent` (P8-I20; texto ajustado: o original diz "Motor LLM") | Link para Provedor e chaves | Só fallback de nuvem sem consentimento | Avançado |
| 7 | EX-MD-FB-07 | "Usar como fallback" | Botão secundário | `core.setFallback(id, revisão)` (P8-C18) | Grava | Desabilitado se não permitido (5.8.3) | Avançado |
| 8 | EX-MD-FB-08 | "Remover fallback" | Botão secundário | `core.clearFallback(revisão)` (P8-C19) | Remove | Só com fallback atual | Avançado |
| 9 | EX-MD-FB-09 | "Último uso do fallback: <modelo> em <hora>" ou "O fallback ainda não respondeu nesta sessão." [novo] | Texto | NOVO (precisa de mudança na ponte/Core): evento `llm_fallback_used` sem conteúdo (NF-10, AC-16) | — | Sem dado: texto da segunda frase | Avançado |
| 10 | EX-MD-FB-10 | "CPU: <N> núcleos · RAM: <X> GB · GPU: <valor>" ou "Hardware: aguardando catálogo" | Texto | `core.modelsHardware` (P8-I17) | — | GPU "desconhecida" quando `unknown` [novo texto] | Avançado |
| 11 | EX-MD-FB-11 | "Apagar dados do plugin" | Botão Perigo | `core.clearPluginSettings()` (P8-C20) → `plugin_settings_clear` (apaga configurações do `llm_engine`, inclusive modelos personalizados) | Confirmação D8 (8.7) | Desabilitado se `core.connected` falso ou ocupado | Avançado |

Texto exato do D8 (confirmação): "Apagar as configurações guardadas pelo plugin LLM, inclusive modelos personalizados? O plugin e a configuração do Core (provedor, modelo e chaves) não são alterados."

Texto de apoio do botão 11: "Apaga só os dados guardados pelo plugin. Não altera o Core." [novo texto; deriva de D8]

#### 5.8.3 Motivos de desabilitado de "Usar como fallback"

| Condição | Texto exato [novo] |
|---|---|
| Fallback de nuvem sem consentimento | "Sem consentimento: marque o envio à nuvem em Provedor e chaves." |
| Fallback de nuvem sem chave | "Sem chave: salve a chave do provedor em Provedor e chaves." |
| Ocupado | "Aguarde: operação de modelo em andamento." |
| Sessão de voz | "Indisponível durante a sessão de voz." |

Nota: `core.fallbackAllowed()` (QML, `Main.qml:141`) checa só o consentimento. A chave é checada pelo Core (`key_missing`). A UI checa as duas para mostrar o motivo antes.

---

## 6. Sub-aba "Percepção e ação" (Avançado; condicional; testes em Desenvolvimento)

### 6.1 Visão e condição

| Campo | Valor |
|---|---|
| Objetivo | Ver os sensores e ações simulados (C4) e a privacidade de microfone e câmera. Os testes de leitura só existem para desenvolvimento. Nenhuma ação altera o computador: todos os backends são sintéticos nesta build. |
| Condição | `core.perceptionAvailable` (algum dos 6 plugins C4 em execução). Sem nenhum, a sub-aba não aparece (1.2). |
| Nível da sub-aba | Avançado (aparece com plugin em execução; a leitura visível depende de "Mostrar opções avançadas"). Botões de teste: Desenvolvimento. |
| Segmentos | Privacidade · Plugins · Último resultado. |
| Dados gerais | `core.perceptionPlugins` (linhas do hub com `plugin_id`, `state`, `last_error`, `permissions`, `approved`, `capabilities`); `core.perceptionMicIndicator`; `core.perceptionCameraIndicator`; `core.perceptionResult`; `core.perceptionBusy`; `core.perceptionInvoke(capacidade, "{}")` (só leituras). |

Plugins C4 (6 ids): `screen_observe`, `computer_control`, `audio_advanced`, `mic_advanced`, `camera_gesture`, `display_manipulate` (C4.1 a C4.6).

### 6.2 Layout e texto da sub-aba

- Corpo: segmentos y 236; conteúdo a partir de y 284.
- "Backends simulados: nenhum hardware pessoal é acessado nesta build." (P9-T1) aparece no topo do segmento Privacidade e, como linha de rodapé, no segmento Plugins.

### 6.3 Segmento "Privacidade" (Básico)

#### 6.3.1 Layout

| Região | x | y | w | h | Conteúdo |
|---|---|---|---|---|---|
| Cartão "Indicadores" | 140 | 284 | 1100 | 180 | Dois indicadores e nota |
| Cartão "O que não é gravado" | 140 | 480 | 1100 | 120 | Texto fixo |

#### 6.3.2 Elementos

| # | ID | Texto exato | Tipo | Fonte de dados (origem) | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| 1 | EX-PC-PV-01 | "Microfone · indicador: <estado>" | Indicador (ponto colorido + texto) | `core.perceptionMicIndicator` (P9-I1) | — | "ligado" (Erro: indica captura) · "desligado" (Neutro) · "não lido" (Neutro) · "plugin inativo" (Neutro) [estados de P9-I1] | Básico |
| 2 | EX-PC-PV-02 | "Câmera · indicador: <estado>" | Indicador | `core.perceptionCameraIndicator` (P9-I2) | — | Idem | Básico |
| 3 | EX-PC-PV-03 | "Backends simulados: nenhum hardware pessoal é acessado nesta build." | Texto | P9-T1 | — | — | Básico |
| 4 | EX-PC-PV-04 | "Os indicadores mostram o último estado lido. Só a leitura de estado atualiza esta tela." [novo texto] | Texto | — | — | — | Básico |

Regra: os dois indicadores ficam visíveis em qualquer segmento desta sub-aba, no cabeçalho da faixa de resumo (1.4) e neste segmento. Nunca ficam ocultos (IA §2.5).

Estado "ligado" de microfone ou câmera usa a cor de Erro, com a palavra "ligado". Motivo: privacidade do usuário; não é erro de sistema. A escolha de tom é deliberada. [nota de desenho]

#### 6.3.3 Texto fixo do segmento

"Nada é gravado em disco. Áudio e legendas ficam só em memória." [novo texto; deriva de UI_IA §4.5 e de P0-T4 "Sem histórico de conversas. Áudio e legendas em memória."]

### 6.4 Segmento "Plugins" (Avançado; testes em Desenvolvimento)

#### 6.4.1 Layout

Grade de cartões em 2 colunas (span 6: x 140 e 698), altura automática (mín. 200), 3 linhas para 6 plugins. Rola na vertical. Se a lista está vazia (sem plugin C4 instalado), não aparece a sub-aba (regra 1.2).

#### 6.4.2 Anatomia do cartão (largura 542)

| Linha | Conteúdo exato | Origem | Nível |
|---|---|---|---|
| L1 | "<plugin_id> <versão>" (17 px semibold, origem P9-I3, `perceptionTitle_<id>`) à esquerda. Badge de estado à direita (4 palavras: "em execução", "iniciando", "desativado", "falhou", "parado", "em quarentena" — `perceptionStateText`). | P9-I3, P9-I4 | Avançado |
| L2 | Selo: "SINTÉTICO — sem hardware real" (screen_observe, computer_control, audio_advanced, mic_advanced, camera_gesture) ou "UNSUPPORTED" (display_manipulate) | P9-I6, AC-11 (selo discreto) | Avançado |
| L3 | "Permissão exigida: <rótulos> · concedida" ou "Permissão exigida: <rótulos> · não concedida" | P9-I7 (`permissions`, `approved`) | Avançado |
| L4 | "Backend real: não suportado / pendente de validação humana" | P9-T2 | Avançado |
| L5 | "Último erro: <mensagem traduzida>" só com erro | P9-I5, `core.codeMessage` | Avançado |
| L6 | Botões de teste (Desenvolvimento), uma linha: "Capturar", "Árvore", "Estado" (da lista abaixo) | P9-C1..C8 | Desenvolvimento |

Lista de botões de teste (`perceptionActions`):

| Plugin | Botões exatos |
|---|---|
| screen_observe | "Capturar" (`screen_observe.capture`), "Estado" (`screen_observe.status`) |
| computer_control | "Árvore" (`computer_control.tree`), "Estado" (`computer_control.status`) |
| audio_advanced | "Estado" (`audio_advanced.state`) |
| mic_advanced | "Estado" (`mic_advanced.state`) |
| camera_gesture | "Estado" (`camera_gesture.state`) |
| display_manipulate | "Estado" (`display_manipulate.status`) → sempre UNSUPPORTED |

Habilitado: plugin `running`, sem leitura em andamento (`core.perceptionBusy` falso), conectado. Motivos de desabilitado: "Plugin não está em execução." [novo] e "Aguarde: outra leitura em andamento." [novo].

Texto de linha de rodapé do segmento: "Backend real: não suportado / pendente de validação humana" (P9-T2) em cada cartão; "Nenhuma ação altera o computador nesta build." [novo].

#### 6.4.3 Estados de cartão de percepção

| Estado | Badge | Tom |
|---|---|---|
| running | em execução | Sucesso |
| starting | iniciando | Info |
| disabled | desativado | Neutro |
| failed | falhou | Erro |
| stopped | parado | Neutro |
| quarantined | em quarentena | Erro |

Cores do tom de cada estado: conforme `perceptionStateColor` (QML): running `#78debc`, starting `#8fb4ff`, failed e quarantined `#ff9a9a`; os demais usam a cor neutra padrão do QML (valor a conferir em `app/Main.qml`). A palavra sempre acompanha a cor.

### 6.5 Segmento "Último resultado" (Desenvolvimento)

#### 6.5.1 Layout

Cartão largura total (1100), altura automática (mín. 140).

#### 6.5.2 Elementos

| # | ID | Texto exato | Fonte (origem) | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|
| 1 | EX-PC-UR-01 | Título: "Último resultado" (P9-T3) | Texto | — | — | Desenvolvimento |
| 2 | EX-PC-UR-02 | Texto puro de `core.perceptionResult` | P9-I8 | — | Só com texto | Desenvolvimento |
| 3 | EX-PC-UR-03 | "Nenhuma ação executada nesta sessão." [novo texto] | — | — | Quando vazio | Desenvolvimento |

PlainText. Nenhum conteúdo de tela ou de áudio é mostrado (AC-12; C4.1: screenshot é evidência, nunca instrução).

### 6.6 Regras da sub-aba Percepção e ação

- R-PC-1: todo resultado mostra "SINTÉTICO" (C4.1 a C4.5) ou "UNSUPPORTED" (C4.6). Nenhum backend real é alegado (C4 "Honestidade de backend").
- R-PC-2: as ações de escrita (`computer_control.act`, `audio_advanced.act`, `mic_advanced.configure`, `mic_advanced.record`, `camera_gesture.optin` e outras da allowlist) não têm botão nesta tela (NF-11). Não criar botão sem decisão (10, P-PC-1).
- R-PC-3: "Capturar" nunca grava; a captura gera evento de auditoria sem conteúdo (C4.1).
- R-PC-4: display_manipulate aparece sempre como "UNSUPPORTED", com o texto "Nenhuma ação de manipulação existe; produto não é bloqueado." [novo texto; C4.6] no cartão.
- R-PC-5: os testes (Desenvolvimento) não aparecem sem modo desenvolvedor (AC-17).

---

## 7. Fluxos passo a passo

Convenções: cada passo mostra a tela (sub-aba e segmento), o elemento (ID), e o resultado observável. Estados visuais seguem 2.7, 3.2, 4.2 e 5.2.

### F1. Instalar plugin com revisão de permissões

| Passo | Tela (segmento) | Ação (ID) | Resultado observável |
|---|---|---|---|
| 1 | Plugins, cartão "Disponível" | Clique em "Revisar permissões" (EX-PL-05) | Abre o diálogo "Revisar permissões" (D4). Só se `core.hubApprovalAvailable`. |
| 2 | Diálogo "Revisar permissões" | Lê o cabeçalho "<id> <versão> · <publisher>" (D4-I1) e a lista de permissões com rótulos (`core.permissionLabel`, R-PL-6) | Nenhuma permissão é aprovada ainda. |
| 3 | Diálogo | Lê "Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto." (D4-I3) | — |
| 4 | Diálogo | Marca "Entendo que o publisher não foi autenticado" (D4-C1) | "Aprovar estas permissões" fica habilitado. |
| 5 | Diálogo | "Aprovar estas permissões" (D4-C2) → `core.approveHub(plugin, manifest, permissions, reconhecido, revisão)` | Faixa de resultado (D4-I4 / D2-I8). O diálogo fecha. O cartão mostra "Permissões aprovadas". |
| 6 | Plugins, cartão "Disponível" (aprovado) | "Instalar pacote verificado" (D2-C3) | Só habilitado se `payload_staged` = true (R-PL-3). Senão, motivo abaixo do botão. |
| 7 | Cartão | Instalação concluída | Badge "Instalado". Plugin fica desativado (sem execução). Resultado em D2-I12. |
| 8 | Cartão "Instalado" | "Ativar" (D2-C6) → `core.enablePlugin` | Estado `starting` ("Iniciando") e depois `running` ("Ativo"), em sandbox sem rede. |
| 9 | Falha | Estado `failed` | Badge "Falhou" e "Falhou: <código traduzido>" (L4). "Ativar" continua disponível (retry). |

Confirmação: não há confirmação nesta sequência (nada é destrutivo). A aprovação de permissões é o consentimento explícito.

### F2. Criar skill: validar, salvar, simular, aprovar, habilitar, executar com aprovação por passo

| Passo | Tela (segmento) | Ação (ID) | Resultado observável |
|---|---|---|---|
| 1 | Skills › Criar | Cola o manifesto no editor (EX-SK-CR-02) | Botões "Validar" e "Salvar rascunho" ficam habilitados. |
| 2 | Criar | "Validar" (EX-SK-CR-03) → `core.skillValidate(texto)` | Sem achados: "Manifesto válido; nada foi gravado." Com achados: lista EX-SK-CR-05. Nada é gravado. |
| 3 | Criar | "Salvar rascunho" (EX-SK-CR-04) → `core.skillSaveDraft(texto)` | A skill aparece em Minhas com badge "Validada". Não habilitada. |
| 4 | Minhas, cartão "Validada" | "Simular" (P10-C2) com entradas (3.4.7) → `core.skillDryRun(id, versão, entradas)` | Não chama capacidades. Sucesso: badge "Testada". Erro: código traduzido. |
| 5 | Minhas, cartão "Testada" | "Aprovar" (P10-C3) → `core.skillApprove(id, versão)` | Badge "Aprovada". Nenhuma permissão é concedida (R-SK-1). |
| 6 | Minhas, cartão "Aprovada" | "Habilitar" (P10-C4) → `core.skillEnable(id)` | Badge "Habilitada". Só o usuário faz esse passo (R-SK-3). |
| 7 | Minhas, cartão "Habilitada" | "Executar" (P10-C6) com entradas → `core.skillRun(id, entradas)` | Abre a execução em Execuções. Passos de leitura rodam. Passos que mudam estado param em "aguardando sua decisão". |
| 8 | Execuções | "Autorizar passo" (EX-SK-EX-03) ou "Negar passo" (EX-SK-EX-04) para cada passo parado | `core.skillDecide(run, passo, "authorize" ou "deny")`. Passo segue ou fica "negado". |
| 9a | Execuções, sucesso | Todos os passos "concluído" | Título com estado "concluída" (Sucesso). Saídas em "Saídas: <JSON>". |
| 9b | Execuções, falha no passo N | Passo falha | Mensagem do código; passos concluídos são desfeitos (rollback); estado "revertida" (Aviso) com texto "Execução revertida: os passos concluídos foram desfeitos". |
| 9c | Execuções, cancelamento | "Cancelar execução" (EX-SK-EX-05) → confirmação (8.7) → `core.skillCancel(run)` | Estado "cancelada" ou "revertida". |

Todo passo que muda estado exige decisão individual. A decisão não é herdada entre passos nem entre execuções (P10-T2).

### F3. Conectar conta com consentimento por escopo

| Passo | Tela (segmento) | Ação (ID) | Resultado observável |
|---|---|---|---|
| 1 | Conexões › Nova conta | Escolhe o provedor (EX-CN-NC-02) e digita o nome (EX-CN-NC-03) | "Adicionar conta" habilitado (4.6.3). |
| 2 | Nova conta | "Adicionar conta" (EX-CN-NC-04) → `core.connectionAdd(provedor, nome)` | Conta aparece em Contas como "Desconectado" (Neutro). |
| 3 | Contas, cartão "Desconectado" | "Conectar" (P11-C8) → `core.connectionConnect(id)` | Badge "Conectando" (Info); texto "Estado: conectando (aguardando confirmação)". |
| 4 | Contas, cartão "Conectando" (GitHub ou Google) | Lê "Código para confirmar no servidor: <código>" (P11-I9) e confirma no site do provedor (fora do Gideon) | O Gideon não confirma por conta própria. |
| 5 | Cartão | Escopos pedidos aparecem como caixas (P11-I11, P11-C4); nenhuma marcada | — |
| 6 | Cartão | Marca só os escopos desejados e clica "Consentir escopos marcados" (P11-C7) → `core.connectionConsent(id, JSON)` | Conta "Conectado" (Sucesso). Escopos concedidos aparecem como chips (P11-I10). Os não marcados ficam pendentes. |
| 7 | Cartão (escopo de escrita ou público) | Lista de operações (P11-I15) mostra "escrita (pede aprovação)" ou "destrutiva (aprovação forte)" | Cada uso pede aprovação no Assistente (Conversa/Agente, fora desta tela). |
| 8 | Cartão | Erro de consentimento ("Consentimento recusado no servidor; nada foi concedido") | Badge "Erro" ou "Desconectado". Pode repetir "Conectar". |

Home Assistant: no passo 3 aparece o consentimento de escopos antes do token; sem consentimento, "Enviar token" devolve `consent_required` (texto existente: "Consinta os escopos antes de enviar o token; nada foi enviado ao servidor"). Depois: campo de token oculto → "Enviar token" (P11-C6) → sonda → "Conectado" ou "Reautenticação necessária".

MCP: "Conectar" → `initialize` → escopos pedidos → consentimento conecta → "Testar leitura: listar ferramentas" (mcp.discover; P11-C14, Desenvolvimento) → lista de ferramentas com estado. Ferramenta nova fica "precisa de nova aprovação" e só é chamável depois de "Confiar" (P11-C13, com confirmação 8.7).

### F4. Usar este modelo, com selftest e rollback

| Passo | Tela (segmento) | Ação (ID) | Resultado observável |
|---|---|---|---|
| 1 | Modelos LLM › Catálogo | Seleciona um modelo na lista (5.5.3) | Painel de detalhe mostra o modelo (5.5.4). |
| 2 | Detalhe | Verifica o motivo de "Usar este modelo" (5.5.5) | Se habilitado, o botão está ativo; se não, o motivo aparece abaixo. |
| 3 | Detalhe | "Usar este modelo" (EX-MD-CT-01) → `core.useModel(id, revisão capturada)` | Texto "Testando modelo…" (PENDING_MODELS 'selftest', existente) e barra de progresso. |
| 4 | Bridge | `llm_configure` grava provedor, modelo e consentimento; `selftest` faz 1 chat curto em streaming e 1 sonda de tool use (C2) | — |
| 5a | Sucesso | `llm_mark_good` promove a configuração a "último bom" | Resultado em `core.modelsResult`: "Modelo testado e marcado como bom." [novo texto]. Estado do modelo atual: "Disponível". |
| 5b | Falha | `llm_rollback` restaura o último bom | Resultado: código traduzido (`model_selftest_failed` → texto por `codeMessage`) + "Configuração anterior restaurada." [novo texto]. |
| 6 | Modelo atual | Confirma o estado | "Estado do modelo atual: Disponível" ou o motivo. |

Regras do fluxo: nada é trocado sem teste; o modelo só fica como "bom" depois de passar pelo selftest; a falha sempre volta ao último bom. O modelo não é descartado silenciosamente.

### F5. Importar skill com prévia

| Passo | Tela (segmento) | Ação (ID) | Resultado observável |
|---|---|---|---|
| 1 | Skills › Importar/Exportar | Digita o nome do pacote, sem caminho e sem extensão (EX-SK-IE-05) | "Pré-visualizar" habilitado se o nome for válido. |
| 2 | Importar/Exportar | "Pré-visualizar" (EX-SK-IE-06) → `core.skillImport(nome)` | Prévia (3.6.4). Nada é instalado. |
| 3 | Prévia | Lê publisher "não verificado", permissões exigidas, novas, escalada, dependências, duplicata e achados | "Instalar como rascunho" só habilitado sem achados e sem duplicata. |
| 4 | Prévia | "Instalar como rascunho" (EX-SK-IE-07) → `core.skillImportConfirm(nome)` | Skill em Minhas, badge "Rascunho", origem "importada (publisher não verificado)". Sem permissões concedidas (P10-I23). |
| 5 | Minhas | Segue F2 a partir de "Simular" | Mesmo fluxo. A aprovação é separada. |

### F6. Exportar skill (complementar)

| Passo | Tela | Ação | Resultado |
|---|---|---|---|
| 1 | Minhas ou Importar/Exportar, skill aprovada, habilitada ou desabilitada | "Exportar" (P10-C9) → `core.skillExport(id, versão)` | "Pacote exportado; publisher não verificado" + caminho (NOVO, 3.6.5). |

---

## 8. Regras transversais

### 8.1 O que some quando o plugin não está instalado ou ativo

| Plugin ausente ou parado | O que some | Onde o usuário vê o efeito | Regra |
|---|---|---|---|
| `llm_engine` não está em execução (`core.modelsAvailable` falso) | Sub-aba "Modelos LLM" | Barra de sub-abas sem "Modelos LLM" | Se o usuário estava nela, muda para Plugins e mostra toast: "Modelos LLM deixou de estar disponível: o plugin llm_engine não está ativo." [novo texto] |
| `llm_engine` ausente | Botão "Gerar com LLM" (Skills › Criar) | Desabilitado com motivo P10-I15 e atalho | Ver 8.3 |
| Nenhum plugin C4 em execução (`core.perceptionAvailable` falso) | Sub-aba "Percepção e ação" | Barra de sub-abas sem a sub-aba | Se o usuário estava nela, muda para Plugins e mostra toast: "Percepção e ação deixou de estar disponível: nenhum plugin de percepção está ativo." [novo texto] |
| Plugin revogado no meio de uma execução de skill | Execução falha com `missing_dependency` e faz rollback | Estado "revertida" | S4 D2 |

A aba "Extensões" nunca some. Nenhum plugin ausente remove a aba inteira.

### 8.2 Inventário x IA: página condicional ou fixa

O inventário marca Skills (SB-06) e Conexões (SB-07) como condicionais (`skillsAvailable`, `connectionsAvailable`). O UI_IA §2 as lista como sub-abas fixas. Esta especificação segue a IA: fixas. Quando o Core não responde (`core.connected` falso), as duas ficam desabilitadas com tooltip "Core desconectado". Ver 10, P-EX-1.

### 8.3 Atalho "Instalar em Extensões › Plugins"

Mostra-se nestes lugares, e só neles:

1. Skills › Criar, painel "Gerar com LLM", quando indisponível: "Gerar com LLM indisponível: o plugin llm_engine não está ativo." (P10-I15) + link "Instalar em Extensões › Plugins".
2. Plugins, faixa do topo, quando "Modelos LLM" ou "Percepção e ação" estão ausentes e há plugin correspondente instalável ou parado: "Modelos LLM aparece quando o plugin LLM estiver ativo. Instalar em Extensões › Plugins" [novo texto]. Mesmo texto para percepção: "Percepção e ação aparece quando um plugin de percepção estiver ativo. Instalar em Extensões › Plugins" [novo texto].
3. Telas de outras abas (Assistente, Conversa; fora desta especificação) usam o mesmo texto, mas o atalho aponta para Extensões › Plugins.

O atalho é um link de texto de 12 px (acento); não é botão primário. Ele não instala nada.

### 8.4 Selos de honestidade (discretos)

| Selo | Onde | Aparência | Regra |
|---|---|---|---|
| "não verificado" | Publisher de plugin, skill importada, publisher da prévia | Selo discreto ao lado do publisher | Nunca "assinado" (S4 D4) |
| "SINTÉTICO — sem hardware real" | Cartões de percepção (C4.1 a C4.5) | Selo discreto (L2 do cartão) | Não aparece em Plugins da aba Extensões (R-PL-7) |
| "UNSUPPORTED" | display_manipulate (C4.6) | Selo discreto | Sempre |
| "SERVIDOR FALSO — sem credenciais reais" | Contas com `fake` = true | Selo discreto ao lado do nome | Selo curto "SERVIDOR FALSO" sempre. O texto integral "SERVIDOR FALSO — sem credenciais reais" (P11-I6) aparece na linha 2 do cartão (4.4.3). Ver decisão P-EX-4 em 10.1. |
| "Atenção: fallback visual…" | Rotas (aviso) | Faixa de aviso | Texto integral do bridge (4.5.5) |

### 8.5 Mensagens transitórias

- Resultado de cada operação aparece na faixa do topo do corpo (32 px) e, ao terminar, vira toast no canto inferior direito por 4 s (casca).
- O toast repete o mesmo texto que a faixa. Não há duas mensagens diferentes para o mesmo evento.
- Erros aparecem com o código traduzido (`core.codeMessage`), nunca cru.

### 8.6 Sessão de voz e Core desconectado

- Durante a sessão de voz (`core.sessionId` não vazio), todo controle que escreve no Core fica desabilitado, com o motivo "Indisponível durante a sessão de voz." (AC-01 explica por que: `preferencesAvailable` exige `not sessionId`). Vale para plugins (instalar, ativar, desativar, remover, revogar), contas, modelos e configuração de LLM.
- Leituras continuam: listas, detalhes, estados.
- Core desconectado (`core.connected` falso): todo controle desabilitado; banner "Core desconectado: nada pode ser alterado agora." [novo texto]; motivo do tooltip "Core desconectado".

Nota: `modelsAvailable` e `skillsAvailable` não dependem da sessão de voz (checam só `online`). O motivo de sessão de voz se aplica aos controles que dependem de `preferencesAvailable`, `hubLifecycleAvailable`, `pluginsAvailable`, `llmConfigAvailable` e `connectionsAvailable` (ver a lista em UI_INVENTORY §0). Para esses casos a UI mostra o mesmo motivo.

### 8.7 Confirmações de ações perigosas

Padrão (casca): diálogo com título "Tem certeza?", descrição com o efeito, botões [Cancelar] [Confirmar]. "Cancelar" é o foco inicial. Esc fecha.

| ID | Ação | Texto exato da descrição | Botão de confirmação | Estado | Origem |
|---|---|---|---|---|---|
| D5 | Remover plugin | "Remover <id> <versão> do Core? Nada é executado e o catálogo não muda." | "Remover" | Existe | D5 |
| D6 | Revogar permissões | "Revogar permissões de <id>? O plugin será desativado e o processo encerrado. Reativar exige nova aprovação." | "Revogar" | Existe | D6 |
| D7 | Remover modelo personalizado | "Remover <rótulo> da lista de modelos personalizados? O modelo no provedor não é apagado." | "Remover" | Existe | D7 |
| D8 | Apagar dados do plugin | "Apagar as configurações guardadas pelo plugin LLM, inclusive modelos personalizados? O plugin e a configuração do Core (provedor, modelo e chaves) não são alterados." | "Apagar dados" | Existe (só llm_engine) | D8 |
| D9 | Remover skill | "Remover <id> v<versão> do Core? Nada é executado." | "Remover" | Existe | D9 |
| C-1 | Revogar conexão | "Revogar a conta <nome>? O acesso é revogado no servidor e as credenciais são apagadas do Gideon. Conectar de novo exige nova autorização." [novo texto] | "Revogar" | NOVO (UI apenas) | AC-05 |
| C-2 | Remover conexão | "Remover a conta <nome> do Gideon? A conta sai da lista." [novo texto] | "Remover" | NOVO (UI apenas) | AC-05 |
| C-3 | Remover chave do provedor | "Remover a chave do provedor <provedor>? As chamadas a este provedor param até você salvar outra chave." [novo texto] | "Remover chave" | NOVO (UI apenas) | AC-05, D3-C6 |
| C-4 | Confiar em ferramenta MCP | "Confiar na ferramenta <nome>? Cada chamada ainda pede a sua aprovação." [novo texto; S5 E2.4] | "Confiar" | NOVO (UI apenas) | P11-C13 |
| C-5 | Ligar fallback visual | "Permitir o fallback visual para criar issue? Ele dirige a tela só quando não há conta conectada. A publicação ainda pede sua aprovação." [novo texto; deriva de REG_VISUAL_WARNING] | "Permitir" | NOVO (UI apenas) | P11-C16 |
| C-6 | Cancelar execução de skill | "Cancelar a execução <run>? Os passos concluídos serão desfeitos." [novo texto] | "Cancelar execução" | NOVO (UI apenas) | P10-C21 |

Regra de texto: os botões de confirmação usam verbo de ação (Remover, Revogar, Apagar dados, Permitir, Confiar), nunca "Sim" ou "OK".

### 8.8 Rótulos "Cancelar" (AC-08)

Nesta aba, a palavra "Cancelar" nunca aparece sozinha. Cada cancelamento tem nome próprio:

| Local | Rótulo |
|---|---|
| Invocação de teste de capability | "Cancelar invocação de teste" (D2-C11) |
| Execução de skill | "Cancelar execução" (P10-C21) |
| Importação de plugin em curso | "Cancelar importação" (D2-C1) |
| Diálogos de confirmação | "Cancelar" (botão do diálogo, sempre com efeito de não fazer nada) |

### 8.9 Motivos de desabilitado: formato

Todo controle desabilitado mostra:

1. O controle com a cor esmaecida (casca: `#5a6a95` no texto de sub-aba; no controle, opacidade reduzida).
2. Um texto de 12 px abaixo ou no tooltip: "Indisponível: <motivo>" ou o texto do motivo sem prefixo quando for ação ("Aprove a skill antes de habilitar ou executar.").
3. O mesmo texto no tooltip do controle.

---

## 9. Acessibilidade

| Tema | Regra |
|---|---|
| Navegação por teclado | Ctrl+2 abre Extensões. Ctrl+Tab percorre sub-abas (casca). Dentro de um segmento, as setas esquerda e direita trocam a aba ativa (`tablist`). |
| Foco visível | Anel de 2 px de acento em todo elemento focável (cartões, botões, campos, disclosures, menus). |
| Ordem de foco | Ordem de leitura (# da tabela): filtro, banner, cartões em ordem, painel de detalhe, depois rodapé. |
| Nomes acessíveis | Todo botão tem `Accessible.name` igual ao rótulo visível, acrescido do alvo quando há vários iguais. Exemplo: "Revisar permissões de <plugin_id>", "Autorizar passo <id>", "Consentir escopos marcados de <conta>". |
| Menu ⋯ | Rótulo "Mais ações de <nome>". Abre com Enter ou Espaço; setas percorrem itens; Esc fecha. |
| Cor e palavra | Todo estado tem palavra. Cor sozinha nunca basta (5.2, 2.5.1, 4.2, 6.4.3). |
| Mensagens | Faixas de resultado com `aria-live` "polite". Erros de validação com `aria-live` "assertive" só quando o usuário acabou de agir. |
| Progresso | Barra indeterminada com nome "Operação em andamento: <tipo>" [novo]. |
| Caixas de escopo | Cada caixa tem rótulo "<rótulo> (<escopo>)", igual ao texto visível (P11-I12). |
| Campos de chave e token | Tipo senha; sem eco; limpa após envio; rótulo claro. |
| Tamanho de alvo | Botões e linhas clicáveis com altura mínima de 40 px (casca), alvo de toque suficiente em 400 px. |
| Contraste | Textos com a cor da casca (`#9db0e0` sobre `#0e1a3a`, etc.) devem atingir pelo menos 4,5 : 1 para texto comum. A exceção é o texto desabilitado (`#5a6a95`), que é só informativo e sempre vem com o motivo em texto. |
| Idioma | Todo texto em português; rótulos nunca em inglês; códigos crus nunca na tela (`core.codeMessage`). |
| Texto livre de terceiros | Descrição de ferramenta MCP e nome de entidade de plugin são só PlainText (C4, S5). Nunca interpretados como HTML. |
| Reflow | Com 400 px de largura, sem rolagem horizontal da página; só tabelas e wireframes rolam em bloco próprio. |
| Movimento | Sem animação obrigatória. Barras de progresso são a única animação. |

---

## 10. Pendências, decisões e lacunas

### 10.1 Decisões a confirmar com o dono

| ID | Assunto | Proposta desta especificação | Alternativa |
|---|---|---|---|
| P-EX-1 | Skills e Conexões fixas ou condicionais (SB-06, SB-07) | Fixas (IA §2). Desabilitadas com motivo quando offline. | Condicionais (inventário). |
| P-MD-1 | "Provedor e chaves" sem o plugin LLM (AC-09) | A sub-aba "Modelos LLM" só aparece com o plugin. Sem o plugin, o provedor e a chave não têm tela em Extensões. Decidir: mostrar Provedor e chaves quando `core.llmConfigAvailable` for verdadeiro, mesmo sem plugin. | Manter tudo atrás do plugin (AC-09 vira bug de regra). |
| P-SK-1 | "Validar" em Minhas | Validar só existe em Criar, porque o Core valida texto de manifesto (`skillValidate(texto)`), não uma skill pelo id. | NOVO: validar skill instalada pelo id (precisa de op no Core). |
| P-SK-2 | Nível de Skills | Sub-aba Básica; ações de Simular, Aprovar, Reverter, Exportar, Remover e JSON são Avançadas. | Sub-aba inteira Avançada (inventário P10). |
| P-SK-3 | "Reverter versão" sem versão anterior | Botão sempre habilitado (como no QML). O Core responde erro se não houver versão anterior. | Snapshot informa se há versão anterior (NOVO na ponte). |
| P-EX-2 | Percepção e ação como Avançada | Sub-aba Avançada e visível quando há plugin. Testes só em Desenvolvimento. | Sub-aba só em Desenvolvimento (inventário SB-10). |
| P-EX-3 | Confirmações novas (C-1 a C-6) | Adicionar (AC-05 pede o freio). | Manter sem confirmação. |
| P-EX-4 | Selo "SERVIDOR FALSO" curto ou por extenso | Texto integral "SERVIDOR FALSO — sem credenciais reais" na linha 2 do cartão (4.4.3) e selo curto no cabeçalho. | Curto sempre, integral só em modo desenvolvedor (menos ruído, menos honesto). |
| P-PL-1 | Botão "Explorar catálogo" | Removido. Substituído por "Atualizar catálogo" (`core.refresh()`). | Manter como abertura de diálogo (não há diálogo mais). |
| P-PC-1 | Botões de escrita de percepção (NF-11) | Não criar agora. | Criar com confirmação, depois de decisão. |

### 10.2 Lacunas que exigem mudança na ponte ou no Core (NOVO)

**Status verificado no WP8 (`docs/WP8.md`):** implementados: NOVO-04, NOVO-06, NOVO-07, NOVO-10, NOVO-11, NOVO-12, NOVO-15, NOVO-16 (textos diferentes em `app/components/BExt.js`). Parciais: NOVO-02 (Core tem `HubDiscardStaged`, a ponte e a UI não expõem), NOVO-01 (Core tem `HubBegin`, `HubChunk`, `HubFinish`; a ponte não tem slots e a UI não tem seletor de arquivo), NOVO-05 (rótulos incompletos, não auditado a fundo), NOVO-08 (`skill_export` grava o arquivo mas devolve só `ok`, sem caminho), NOVO-09 (`risk` e `effect` existem; falta `target`), NOVO-14 (`llm_fallback_used` existe no Core, e o último chat expõe `used_fallback`; sem o texto de último uso). Não implementados: NOVO-03 (o catálogo não traz `name` nem `description`), NOVO-13 (não há slot `describe`), NOVO-17 (não verificado). Implementado também: NOVO-07 (`skillPaths`).

| ID | Lacuna | Onde aparece | O que falta | Referência |
|---|---|---|---|---|
| NOVO-01 | Importar pacote do Hub pela interface | Plugins (R-PL-3) | Slots `hub_begin`, `hub_chunk`, `hub_finish` e seletor de arquivo | NF-01 |
| NOVO-02 | Descartar payload em staging | Plugins | Slot para `hub_discard_staged` | NF-02 |
| NOVO-03 | Nome amigável e descrição de plugin | Cartão e detalhe | Campos `name` e `description` no catálogo do Hub | UI_IA §2.1 |
| NOVO-04 | Apagar dados de um plugin qualquer | Menu do cartão (2.5.4) | `clearPluginSettings(plugin_id)` aceita id; hoje não recebe argumento | P8-C20, NF-24 |
| NOVO-05 | Rótulos de todas as permissões do catálogo | Plugins, Skills, Percepção | Completar `PERMISSION_LABELS` para cada permissão declarada | AC-04, R-PL-6 |
| NOVO-06 | Permissões necessárias de skill instalada | Minhas, painel Permissões | Campo `permissions_required` em `skillsItems` | UI_IA §2.2; S4 D1 |
| NOVO-07 | Caminho da pasta de importação de skill | Importar/Exportar | Propriedade com `<home>/skill-imports` | NF-20 |
| NOVO-08 | Caminho do pacote exportado | Importar/Exportar | `skill_export` devolve o caminho | NF-19, AC-13 |
| NOVO-09 | Alvo, efeito e risco de cada passo de skill | Execuções | Campos `target`, `effect`, `risk` no snapshot de passo | AC-14, NT-34 |
| NOVO-10 | Saldo de LKG ("Último bom") | Modelo atual | Propriedade `llm.config.lkg` na ponte | NF-06 |
| NOVO-11 | Voltar ao último bom | Modelo atual | Slot `rollbackLkg(revisão)` → `llm_rollback` | NF-06 |
| NOVO-12 | Testar o modelo atual sem trocá-lo | Modelo atual | Slot de selftest isolado | NF-09 |
| NOVO-13 | Detalhe de um modelo fora da página carregada | Modelo atual, detalhe | Slot `describe(id)` → `llm_engine.models describe` | NF-07 |
| NOVO-14 | Último uso do fallback | Fallback | Evento `llm_fallback_used` sem conteúdo exposto à ponte | NF-10, AC-16 |
| NOVO-15 | Confirmação "Permitir fallback visual" | Rotas | UI apenas (listado aqui porque o estado vem do Core) | P11-C16 |
| NOVO-16 | Descrição de motivo de incompatibilidade | Plugins (R-PL-4) | UI apenas: textos novos para `api_version`, `target`, `dependencies_unresolved` | UI_IA; D2-I4 |
| NOVO-17 | Tradução de rota e de estado de candidato | Rotas | UI apenas | P11-I19 |

### 10.3 Achados de inventário que esta tela corrige

| ID | Achado | Correção nesta tela | Origem |
|---|---|---|---|
| AC-01 | Conversa e controles somem na sessão de voz | Motivo explícito em cada controle (8.6) | AC-01 |
| AC-03 | Página de permissões vazia | Não é desta tela; aqui cada plugin, skill e conta mostra o estado e leva a Permissões ("Ver em Permissões") | AC-03 |
| AC-04 | IDs crus em revisão de permissões | Rótulos em português (R-PL-6) | AC-04 |
| AC-05 | Ações destrutivas sem confirmação | Confirmações C-1 a C-3 (8.7) | AC-05 |
| AC-07 | Duas entradas para o mesmo catálogo | Uma sub-aba Plugins (1.2) | AC-07, NT-03 |
| AC-08 | "Cancelar" com seis efeitos | Rótulos distintos (8.8) | AC-08 |
| AC-10 | Local (llama.cpp) e Ollama sem teste | Continuam como opção, com selo "Candidato" (5.5.3); "Testar" e "Usar" deixam claro o resultado | AC-10, C2 |
| AC-11 | Percepção exibida como produto | Sub-aba Avançada; selo discreto; testes em Desenvolvimento | AC-11 |
| AC-12 | Teste de leitura sem parâmetros; MCP sem conteúdo | Teste em Desenvolvimento; conteúdo MCP nunca exibido (só resultado) | AC-12 |
| AC-13 | Exportação sem caminho | Caminho previsto (NOVO-08) | AC-13 |
| AC-14 | Aprovação sem risco nem efeito | Campos novos (NOVO-09) | AC-14 |
| AC-15 | Sem divulgação progressiva | Níveis Básico/Avançado/Desenvolvimento em cada elemento | AC-15 |
| AC-16 | Usuário não sabe quando o fallback respondeu | Texto de último uso (NOVO-14) | AC-16 |
| AC-17 | Testes na interface comum | Testes só em Desenvolvimento | AC-17 |
| AC-18 | Textos fixos de voz e hardware | Hardware sai do snapshot (5.8.2); voz não aparece nesta aba | AC-18 |

---

## 11. Cobertura do inventário nesta aba

| Área do inventário | Sub-aba | Elementos cobertos |
|---|---|---|
| P6-C1, P6-I1, P6-I2, P6-I3, P6-T1, P6-T2 | Plugins | EX-PL-01..10 |
| D2-C1..C12, D2-I1..I14, D2-T1, D2-T2 | Plugins (cartão, detalhe, menu, teste) | 2.4, 2.5, 2.6, 2.9 |
| D4-C1..C3, D4-I1..I4 | Plugins (diálogo "Revisar permissões") | F1 |
| D5, D6 | Plugins (confirmações) | 8.7 |
| P10-C1..C21, P10-I1..I28, P10-T1..T3 | Skills | 3.4 a 3.9, F2, F5, F6 |
| D9 | Skills (confirmação) | 8.7 |
| P11-C1..C16, P11-I1..I21, P11-T1, P11-T2 | Conexões | 4.4 a 4.7, F3 |
| D7, D8 | Modelos LLM | 5.6, 5.8 |
| P8-C1..C20, P8-I1..I21, P8-T1..T3 | Modelos LLM | 5.4 a 5.8, F4 |
| D3-C1..C9, D3-I1..I5, D3-T1, D3-T2 | Modelos LLM (Provedor e chaves) | 5.7 |
| P9-C1..C8, P9-I1..I8, P9-T1..T3 | Percepção e ação | 6.3 a 6.6 |
| NF-01..NF-26 | Referenciados como lacunas | 10.2 |
| AC-01..AC-18 | Achados corrigidos | 10.3 |
| SB-06..SB-10 | Condições das sub-abas | 1.2 e 8.2 |
| HD-06, P7-C3, P7-C7 | "Cancelar" do cabeçalho e de Conversa/Agente | Fora desta aba (Assistente e cabeçalho); aqui só 8.8 |
| P7-I2, P8-I20, D3-I3 | Consentimento de nuvem | 5.7, 5.8 (texto do D3 integral) |

Itens do inventário fora desta aba (Assistente, Permissões, Configurações, Diagnóstico) não são tratados aqui: P0..P5, D1, P7 e as regras de unicidade DU-01..DU-17 que os envolvem.

---

## 12. Lista de conferência para a implementação

- [ ] Ctrl+2 abre Extensões; Ctrl+Tab percorre as sub-abas.
- [ ] Sub-aba Modelos LLM e Percepção e ação aparecem só com as condições da 1.2.
- [ ] Mudança de sub-aba ao perder condição mostra o toast da 8.1.
- [ ] Nenhum cartão mostra IDs crus; permissões em português (R-PL-6).
- [ ] Revisar e instalar seguem a ordem F1; nenhuma instalação sem aprovação.
- [ ] Skills: nenhuma permissão é concedida pela UI (R-SK-1).
- [ ] Skill: "Validar" não grava; "Simular" não chama capacidades (R-SK-2).
- [ ] Conexões: nenhum escopo é marcado por padrão; consentimento só por clique, por escopo.
- [ ] Confirmações C-1 a C-6 e D5 a D9 aparecem com "Cancelar" focado.
- [ ] Todo controle desabilitado tem motivo (8.9).
- [ ] Nada de "SINTÉTICO" fora de Percepção e ação; "não verificado" em todo publisher.
- [ ] Testes de Percepção e teste de capability só com modo desenvolvedor.
- [ ] Reflow abaixo de 900 px conforme 0.4; sem rolagem horizontal da página.
- [ ] Textos novos marcados com `[novo texto]` foram revisados pelo dono.
- [ ] NOVO-01 a NOVO-17 têm decisão registrada em 10.1 ou 10.2.
