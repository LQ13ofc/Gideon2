# Especificação de UI — Aba "Assistente" (Hoje · Conversa · Agente · Atividade)

Estado: proposta para validação do dono. Idioma: português (textos exatos entre aspas).
Base: `docs/UI_IA.md` §1 (seguido à risca; trechos com divergência estão marcados em §10),
`docs/ui-spec/00-casca.md` (geometria da casca), `docs/UI_DESIGN.md` (tokens e orçamento de conteúdo),
`docs/UI_NOTION_REQS.md` (estados do HUD, aprovação com alvo/efeito/risco), `docs/UI_INVENTORY.md` (IDs de origem),
`app/bridge.py` (nomes de propriedades e slots verificados por grep), `src/protocol.rs` (enum `State`, struct `Event`),
`app/Main.qml` (textos exatos já existentes, citados por linha).

---

## 0. Convenções

- **Janela de referência:** 1380 × 904 px. Mínimo 720 × 520 (abaixo disso não é suportado).
- **Origem:** canto superior esquerdo da janela. Coordenadas em px `(x, y, largura, altura)`.
- **Coluna de conteúdo:** em 1380 px, `x 140 → 1240` (largura 1100), por `max 1100` centralizada quando a janela tem 1240 px ou mais (`(W − 1100) / 2`). Entre 900 e 1239 px: `x 32 → W − 32`. Cabeçalho, faixa de resumo e conteúdo usam **a mesma coluna** (interpretação: `00-casca.md` diz "x 32" para o cabeçalho; ver pendência P-1).
- **Grade:** 12 colunas, gap 16. Em 1100 px cada coluna tem 77 px. Medidas úteis: 6 colunas = 542 px; 8 = 728 px; 4 = 356 px. **Todos os cartões desta aba ocupam 12/12 colunas** (uma coluna de cartões).
- **"Abaixo de 900 px"** é lido como **largura da janela < 900 px** (coerente com `00-casca.md`: "< 900 px as abas viram só ícones"). Altura menor que 904 não muda a largura da coluna; a área de conteúdo rola na vertical.
- **Escala dos wireframes:** 1 caractere = 10 px horizontal, 1 linha = 20 px vertical. Origem do desenho: `x 140`, `y 236` (início da área de conteúdo). A coluna da esquerda mostra o `y` absoluto de cada linha. Texto dentro das caixas é truncado no desenho; o texto completo está na tabela de elementos.
- **Níveis:** **Básico** (sempre visível) · **Avançado** (só com "Mostrar opções avançadas" ligado em Configurações › Geral) · **Dev** (só com "Modo desenvolvedor" ligado em Diagnóstico › Estado).
- **Fontes de dados:** `core.<prop>` = `@Property` de `app/bridge.py`; `core.<slot>()` = `@Slot`. Os IDs do inventário (`SB-`, `HD-`, `P0-`…`P11-`, `NF-`, `AC-`) indicam a origem atual.
- **Marcações de implementação:**
  - `EXISTE` — dado ou ação já disponível na ponte/QML.
  - `NOVO (ponte/Core)` — exige mudança em `app/bridge.py` e/ou no Core (com o que precisa ser feito).
  - `NOVO (QML)` — só muda a tela, usando dados que já existem.
- **Textos:** "Texto exato" é a string a usar. Partes entre `< >` ou `{ }` são substituídas por dados. Textos já existentes no código estão citados com a linha de origem.
- **Status = cor + palavra.** Nenhum estado é transmitido só por cor.

### 0.1 Tokens usados (de `docs/UI_DESIGN.md` e `00-casca.md`)

| Uso | Valor |
|---|---|
| Fundo da janela | `#0b1530` |
| Barra de abas | `#0e1a3a`, borda inferior 1 px `#263a73` |
| Barra de sub-abas | `#0b1530` |
| Cartão | gradiente `#14224a → #101c40`, borda `#263a73`, raio 14, padding 20 |
| Texto principal | `#e8eeff` |
| Texto secundário | `#9db0e0` (contraste aprox. 8,4:1 sobre `#0b1530`) |
| Acento | `#7693ff` (anel de foco 2 px; aba ativa a 18 %) |
| Sucesso | `#5ee0a0` |
| Aviso | `#f2c15c` |
| Erro | `#ff7d8a` |
| Info | `#7693ff` |
| Neutro | `#9db0e0` |
| Violeta (Pensando) | `#b386ff` |
| Ciano (Falando) | `#66dcf4` |
| Botão primário | fundo `#3a5bd9`, texto branco, altura 40, raio 10 |
| Botão secundário | contorno `#2a3d78`, altura 40, raio 10 |
| Botão perigo | contorno e texto `#ff7d8a`, altura 40, raio 10 |
| Badge | altura 22, raio 11, cor + palavra |
| Tipografia | Noto Sans. Título de página 24 bold; frase do HUD 28 bold (decisão desta spec); título de cartão 17 semibold; corpo 14; legenda 12 |

**Atenção de contraste:** o cinza do estado "Core desconectado" (`#5a6a95`) tem contraste aprox. 3,4:1 sobre `#0b1530`, abaixo de 4,5:1. Por isso **o texto** desse estado usa `#9db0e0`; `#5a6a95` fica só no ponto/anel decorativo.

---

## 1. Casca vista pela aba Assistente (`00-casca.md` aplicado)

### 1.1 Geometria (1380 × 904)

| Região | Posição / tamanho | Conteúdo nesta aba |
|---|---|---|
| Barra de abas (nível 1) | `y 0–56`, largura total | Logo + 5 abas + pílula + Cancelar |
| Barra de sub-abas (nível 2) | `y 56–100` | Hoje · Conversa · Agente · Atividade (sub-abas condicionais somem) |
| Cabeçalho da sub-aba | título `y 116–148`; subtítulo `y 152–172`; coluna `x 140 → 1240` | Título + subtítulo. **Sem ação primária** nesta aba (o botão de ação fica dentro do cartão) |
| Faixa de resumo | `y 184–224` (altura 40), coluna `x 140 → 1240` | Frase-resumo à esquerda + badges/chips à direita |
| Área de conteúdo | `y 236 → 880` (altura 644), coluna `x 140 → 1240` | Cartões (máx. 3 por sub-aba) |
| Rodapé | não existe | Mensagens transitórias como toast no canto inferior direito, 4 s, `x 1040 → 1348`, `y 828 → 868` |

### 1.2 Elementos da casca (comuns às quatro sub-abas)

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| S-01 | Aba "Assistente": `x 128–250`, `y 8–48` (aprox. ±6 px) | Aba nível 1 (ícone 18 px + rótulo) | "Assistente" | estática | Ativa; `Ctrl+1` leva a ela | ativa: fundo acento 18 %, barra inferior 3 px `#7693ff`, texto branco bold. Inativa: `#9db0e0` | Básico |
| S-02 | Pílula de estado: borda direita em `x 1364`, `y 13–43` (altura 30) | Pílula (ponto + texto), não clicável | Texto da seção 2 (ex.: "Em espera") | derivado de `core.state`, `core.connected`, `core.configurationStatus`, `core.chatState`, `core.agentState` (ver §2) | Nenhuma. Accessible name "Estado do Gideon"; description = texto da pílula | Ver §2 | Básico |
| S-03 | Botão "Cancelar": à esquerda da pílula, `altura 30`, `y 13–43`, 8 px de espaço | Botão secundário | "Cancelar" (accessible name conforme §2.4) | `core.sessionCancellable` (`Main.qml:41`, EXISTE) e `core.chatState` | Sessão de voz ativa → `core.cancel()` (`bridge.py:1239`). Resposta do chat em andamento → `core.cancelChat()` (`bridge.py:1330`). Nenhum outro caso | Oculto quando não há nada a cancelar. Desabilitado com texto "Cancelando…" enquanto houver cancelamento na fila | Básico |
| S-04 | Sub-aba "Hoje": `x 18–90`, `y 56–100` | Sub-aba | "Hoje" | estática | Abre Hoje | ativa: texto branco bold + sublinhado 2 px `#7693ff`. Inativa: `#9db0e0` | Básico |
| S-05 | Sub-aba "Conversa": `x 90–192` | Sub-aba condicional | "Conversa" | `core.chatAvailable` (ver §7.1) | Abre Conversa | Oculta sem plugin LLM e (hoje) durante sessão de voz (AC-01, §7.2) | Básico |
| S-06 | Sub-aba "Agente": `x 192–278` | Sub-aba condicional | "Agente" | `core.chatAvailable` | Abre Agente | Igual a S-05 | Básico |
| S-07 | Sub-aba "Atividade": `x 278–384` | Sub-aba | "Atividade" | estática | Abre Atividade | Igual a S-04 | Básico |
| S-08 | Título da sub-aba: `x 140`, `y 116` | Texto 24 bold | Hoje: "Hoje" · Conversa: "Conversa" · Agente: "Agente" · Atividade: "Atividade" | estática | — | — | Básico |
| S-09 | Subtítulo: `x 140`, `y 152` | Texto 14, `#9db0e0`, 1 linha | Hoje: "Como o Gideon está agora e um comando para ele." · Conversa: "Converse com o motor LLM. Respostas e propostas aparecem aqui." · Agente: "Descreva um objetivo; o Gideon propõe passos e pede sua aprovação." · Atividade: "O que aconteceu nesta sessão, sem conteúdo sensível." | estática | — | — | Básico |

**Sub-abas condicionais:** quando uma sub-aba some, as vizinhas se reposicionam (sem espaço vazio). Se o usuário estava nela, a tela muda para **Hoje** (regra em §7.1).

**Atalhos de sub-aba:** `Ctrl+Tab` avança, `Ctrl+Shift+Tab` volta, pulando as ocultas (ver §8).

---

## 2. HUD: estados, prioridade e o que muda na tela

Este bloco define o **estado principal** mostrado em três lugares: pílula (S-02), orbe + frase grande (H-06 a H-08) e, quando pertinente, o estado da conversa e do agente. A regra é única e vale para todas as sub-abas.

### 2.1 Fontes de entrada

| Entrada | Propriedade / slot | Origem | Observação |
|---|---|---|---|
| Estado do Core | `core.state` (`bridge.py:1797`) | Core: `idle`, `capturing`, `transcribing`, `executing`, `speaking` (enum `State` em `src/protocol.rs`). A ponte acrescenta `offline`, `safe_mode`, `restart_required` | O Core **não tem** estado "pensando" nem "erro" nem "aguardando aprovação" |
| Conectado | `core.connected` (`bridge.py:1795`) | `online` | Falso = Core desconectado |
| Sessão | `core.sessionId` (`bridge.py:1799`) | Não vazio = sessão de voz ativa | |
| Chat | `core.chatState` (`bridge.py:1283`) | `idle`, `waiting`, `streaming`, `done`, `error`, `cancelled` | `waiting`/`streaming` = resposta do LLM em curso |
| Agente | `core.agentState` (`bridge.py:1370`), `core.agentActive` (`bridge.py:1372`) | `thinking`, `waiting_tool`, `awaiting_approval`, `done`, `failed`, `aborted`, `blocked` | |
| Propostas | `core.toolProposals` (`bridge.py:1337`) | Lista; `state` = `pending` quando aguarda decisão | |
| Configuração | `core.configurationStatus` (`bridge.py:1662`) | `ready`, `safe_mode`, `restart_required`… | |
| Feedback visual | `core.visualFeedback` (`bridge.py:1652`) | Liga/desliga orbe | |
| Transcrição | `core.subtitle` (`bridge.py:1801`), `core.partial` (`bridge.py:1803`) | Texto da sessão atual | |
| Recibo | `core.result` (`bridge.py:1805`), `core.resultVerified` (`bridge.py:1809`) | Ver AC-19 em §10 | |
| Últimos erros | `core.chatResult` (`bridge.py:1293`), `core.agentStateLabel` (`bridge.py:1374`) | Textos de erro | |

### 2.2 Prioridade (a primeira condição verdadeira vence)

| Prio | Condição | Pílula (S-02) | Frase grande (H-07) | Subtítulo (H-08) | Cor (texto + ponto/orbe) | O que muda na tela |
|---|---|---|---|---|---|---|
| 1 | `core.connected` = falso | "Core desconectado" | "Core desconectado" | "Tentando reconectar…" | cinza: ponto `#5a6a95`, **texto** `#9db0e0` | Orbe em tons de cinza (ou oculto se `visualFeedback` = falso). Cancelar some. Campo de comando desabilitado com motivo (§3.9). Sub-abas Conversa e Agente somem (§7.3). Atividade mostra última leitura com aviso (§6) |
| 2 | `core.state` = `safe_mode` | "Modo seguro" | "Modo seguro" | "Abra Diagnóstico › Recuperação para reparar." | aviso `#f2c15c` | Orbe em aviso. Nenhuma ação de sessão disponível |
| 3 | `core.state` = `restart_required` | "Reinício necessário" | "Reinício necessário" | "Reinicie o Core para aplicar a alteração." | aviso `#f2c15c` | Igual à prioridade 2. Sem botão de reinício aqui (NF-22: reinício não tem ação na UI) |
| 4 | `core.state` fora de `idle`, `capturing`, `transcribing`, `executing`, `speaking` | "Erro" | "Erro" | "Estado do Core não reconhecido." | erro `#ff7d8a` | Igual ao fallback de `Main.qml:647` (`|| "Erro"`) |
| 5 | `core.state` = `capturing` | "Ouvindo" | "Ouvindo…" | "Fale agora. Cancelar encerra a sessão." | azul `#7693ff` | Badge "Microfone ativo" aparece (H-09). Cancelar visível (S-03). Campo de comando desabilitado (sessão) |
| 6 | `core.state` = `transcribing` | "Transcrevendo" | "Transcrevendo…" | `core.subtitle` se não vazio; senão "Processando o que você disse." | azul `#7693ff` | Transcrição parcial aparece no bloco "Você" (H-24). Cancelar visível |
| 7 | `core.state` = `executing` | "Executando" | "Executando…" | Se `core.agentState` = `waiting_tool`: "Ferramenta do agente em execução."; senão "Executando o comando." | azul `#7693ff` | Cancelar visível. Campo de comando desabilitado |
| 8 | `core.state` = `speaking` | "Falando" | "Falando…" | "Resposta em voz alta. Cancelar interrompe." | ciano `#66dcf4` | Cancelar visível. Campo de comando desabilitado |
| 9 | `core.state` = `idle` e (`core.chatState` ∈ {`waiting`, `streaming`} ou `core.agentState` = `thinking`) | "Pensando" | "Pensando…" | `waiting`: "Aguardando o motor LLM."; `streaming`: "Recebendo a resposta."; agente: "O agente planeja o próximo passo." | violeta `#b386ff` | Cancelar (S-03) aparece e cancela a resposta do chat (`cancelChat`). Campo de comando **continua habilitado** (é o caminho de voz/comando, não o chat). Nota: com o chat em curso, o agente fica "Pensando" também |
| 10 | `core.state` = `idle` e há proposta com `state` = `pending` | "Aguardando aprovação" | "Aguardando sua aprovação" | "Ferramenta {tool} precisa da sua decisão." | aviso `#f2c15c` | Cartão B de Hoje aparece (H-10). Estado **extra** (o Notion pede `AwaitingConfirmation`, `UI_NOTION_REQS.md`); não é um dos sete da lista do dono, mas é derivado de dados existentes |
| 11 | `core.state` = `idle` e último resultado falhou (ver §2.3) | "Erro" | "Erro" | Texto do erro (§2.3) | erro `#ff7d8a` | Persiste até a próxima ação (enviar chat, iniciar agente ou enviar comando) |
| 12 | Demais casos | "Em espera" | "Pronto para ouvir" | "Diga 'Hey Gideon' ou digite um comando." | neutro `#9db0e0` | Estado vazio do HUD |

**Nota sobre os sete estados pedidos:** Em espera (12), Ouvindo (5), Transcrevendo (6), Pensando (9), Executando (7), Falando (8), Erro (4 e 11). Prioridades 1–3 e 10 são estados de borda acrescentados com a mesma anatomia.

### 2.3 Regra de "Erro" (prioridade 11) — NOVO (QML)

Considera-se que o último resultado falhou quando **uma** destas condições é verdadeira e ainda não houve nova ação:
- `core.chatState` = `error` → texto = `core.chatResult` (ex.: "Erro HTTP do provedor"; `bridge.py:1293`).
- `core.agentState` ∈ {`failed`, `blocked`} → texto = `core.agentStateLabel` (ex.: "Falhou · Tempo do provedor esgotado").
- `core.result` não vazio e `core.resultVerified` = falso e o recibo veio de um código de erro → texto = `core.result`.

"Nova ação" = enviar mensagem no chat, iniciar agente ou enviar comando de texto. Essa limpeza é feita pela QML (guardando o último marcador); o Core não precisa de mudança.

### 2.4 Cancelar (S-03): nomes e alvo

| Estado | Rótulo visível | Nome acessível | Chamada | Feedback |
|---|---|---|---|---|
| Sessão de voz (prioridades 5–8) | "Cancelar" | "Cancelar sessão" (`Main.qml:651`, EXISTE) | `core.cancel()` | Pílula muda para "Em espera" quando o Core confirma |
| Chat em curso (prioridade 9, sem sessão) | "Cancelar" | "Cancelar resposta" | `core.cancelChat()` | `core.chatResult` = "Cancelamento na fila" (`bridge.py:1332`) ou `PENDING['capability_cancel']` = "Cancelando capability…" (`bridge.py:1078`) |
| Agente em execução | **não aparece** no cabeçalho | — | Abortar fica dentro de Agente (AG-06) | Decisão: evitar abortar agente por um botão de cabeçalho sem contexto |

Decisão desta spec (NOVO QML): o botão do cabeçalho passa a cobrir também a resposta do chat (hoje ele só cobre a sessão; AC-08). Os rótulos internos permanecem diferentes (ver §10).

---

## 3. Hoje

### 3.1 Objetivo
Ver como o Gideon está agora e dar um comando, sem sair da tela. Este é o lugar de uso diário.

### 3.2 Condição de aparecimento
Sempre visível (é a primeira sub-aba e está sempre presente).

### 3.3 Nível
Básico. Itens **Avançado** e **Dev** aparecem como indicado em §3.7.

### 3.4 Layout em grade (1380 × 904)

| Região | x | y | largura | altura | Colunas | Conteúdo |
|---|---|---|---|---|---|---|
| Faixa de resumo | 140 | 184 | 1100 | 40 | 12 | H-01 (texto) + H-02, H-03, H-04 (chips) |
| Cartão A — Estado | 140 | 236 | 1100 | 168 | 12 | Orbe, frase, subtítulo, badge de microfone |
| Cartão B — Proposta (condicional) | 140 | 420 | 1100 | 180 | 12 | Proposta pendente |
| Cartão C — Comando e última interação | 140 | 616 com B; **420** sem B | 1100 | 264 | 12 | Campo, Enviar, última interação |
| Área vazia abaixo do C (só sem B) | 140 | 684 | 1100 | 196 | — | Vazia (não há cartão) |

Posições dentro dos cartões:
- Cartão A: orbe `x 160, y 256, 72 × 72`; frase `x 256, y 262, 820 × 36`; subtítulo `x 256, y 298, 820 × 22`; badge `x 256, y 330, 150 × 22`.
- Cartão B: título `x 160, y 436`; linhas `y 458`, `y 480`, `y 502`; `Argumentos` (Avançado) `y 524`; botões `Negar x 1000, Autorizar x 1112`, `y 544`, `40 px` de altura.
- Cartão C (com B, base `y 616`): título `y 632`; legenda `y 652`; campo `x 160, y 672, 920 × 44`; Enviar `x 1092, y 672, 128 × 44`; motivo `y 724`; "Última interação" `y 748`; bolha Você `x 160, y 768, 1060 × 40`; recibo `y 820`.

**Reflow abaixo de 900 px de largura** (coluna = `W − 64`):
- Chips da faixa quebram em segunda linha; faixa cresce para 2 linhas (altura 64) e todo o conteúdo desce 24 px.
- Botões Negar e Autorizar ficam alinhados à direita **abaixo** do texto da proposta (linha própria).
- Campo e Enviar: lado a lado se a coluna for ≥ 760 px; senão o Enviar fica abaixo do campo, ocupando a largura toda.
- Cartões continuam em uma coluna; a área rola na vertical.

### 3.5 Wireframe (área de conteúdo, escala 1 col = 10 px, 1 linha = 20 px)

```
 236 |+- A. Estado (HUD) ------------------------------------------------------------------------------------------+
 256 || +- or-+   Pronto para ouvir                                                                                |
 276 || |     |                                                                                                    |
 296 || |     |   Diga 'Hey Gideon' ou digite um comando.                                                          |
 316 || +-----+                                                                                                    |
 336 ||           [Microfone ativo]                                                                                |
 356 ||                                                                                                            |
 376 |+------------------------------------------------------------------------------------------------------------+
 396 |
 416 |+- B. Proposta pendente (so se houver) ----------------------------------------------------------------------+
 436 || Ferramenta <nome> - aguardando sua decisao                                                                 |
 456 || Alvo: <ferramenta> (<plugin>)                                                                              |
 476 || Efeito: <descricao do efeito>                                                                              |
 496 || Risco: <baixo | medio | alto>                                                                              |
 516 ||                                                                                                            |
 536 ||                                                                                     +- Negar-+ +- Autori-+ |
 556 ||                                                                                     +--------+ +---------+ |
 576 |+------------------------------------------------------------------------------------------------------------+
 596 |
 616 |+- C. Comando e ultima interacao ----------------------------------------------------------------------------+
 636 || Comando                                                                                                    |
 656 || Texto segue o mesmo caminho da voz. 1 a 512 bytes, uma linha.                                              |
 676 || +- Diga ou digite um comando --------------------------------------------------------------+ +- Enviar --+ |
 696 || +------------------------------------------------------------------------------------------+ +-----------+ |
 716 || Indisponivel: a entrada de texto so existe no perfil de teste.                                             |
 736 ||                                                                                                            |
 756 || Ultima interacao                                                                                           |
 776 || +- Voce: transcricao da sessao --------------------------------------------------------------------------+ |
 796 || +--------------------------------------------------------------------------------------------------------+ |
 816 || Gideon - Concluido - texto do recibo                                                                       |
 836 ||                                                                                                            |
 856 |+------------------------------------------------------------------------------------------------------------+
```

Sem proposta (B oculto), o cartão C começa em `y 420` e termina em `y 684`; o espaço de `y 684` a `880` fica vazio.

### 3.6 Elementos de Hoje

Faixa de resumo (`y 184–224`):

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| H-01 | `x 156, y 196`, até `x 620` | Texto 14 bold | Sem proposta: `{pílula}` (ex.: "Em espera"). Com proposta: `{pílula} · {N} proposta(s) pendente(s)` (ex.: "Aguardando aprovação · 1 proposta pendente") | pílula (§2); `len(core.toolProposals where state=pending)` | — | Normal | Básico |
| H-02 | Chip Wake: `x 634, y 191, 200 × 26` | Chip (botão) | `Wake: {frase ativa} · {qualificação}`. Ex.: "Wake: Hey Gideon · em desenvolvimento". Sem pacote: "Wake: indisponível" | `core.snapshotPack.active_phrase` (`bridge.py:1701`, P0-I7); qualificação via `core.wakeChoices` (`bridge.py:1638`, P1-I2) | Clique → Configurações › Voz e Wake | Normal; sem pacote (texto "Wake: indisponível", ainda clicável); desabilitado nunca | Básico |
| H-03 | Chip Entrada: `x 842, y 191, 170 × 26` | Chip (botão) | "Entrada: PCM virtual". Sem pacote: "Entrada: indisponível" | `core.wakeChoices` não vazio (P0-I8). O texto "PCM virtual" ainda é fixo (AC-18) | Clique → Configurações › Dispositivos | Normal; indisponível | Básico |
| H-04 | Chip Modo: `x 1020, y 191, 200 × 26` | Chip (botão) | Sem plugin LLM: "Modo: Base, sem LLM". Com plugin e modelo: "Modo: Base + LLM ({modelo})". Com plugin sem modelo: "Modo: Base + LLM (sem modelo)" | `core.modelsAvailable` (`bridge.py:1611`, EXISTE) e `core.modelsSelected.model` (`bridge.py:1630`, EXISTE). Substitui o texto fixo de AC-02 | Sem plugin: → Extensões › Plugins (tooltip: "Instalar em Extensões › Plugins"). Com plugin: → Extensões › Modelos LLM | Normal | Básico |

Cartão A (`x 140, y 236, 1100 × 168`, sem título visível; nome acessível "Estado do Gideon"):

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| H-05 | cartão `y 236` | Cartão | (sem título) | — | — | — | Básico |
| H-06 | Orbe `x 160, y 256, 72 × 72` | Imagem (`assets/gideon-orb.png`, já usada em `Main.qml:641`) | Nenhum texto. Accessible name: "Indicador visual do Gideon" | `core.visualFeedback` (`bridge.py:1652`, P3-C8) | Nenhuma | Visível se `visualFeedback`; oculto se não. Em cinza no Core desconectado. Anel de 4 px na cor do estado (decisão desta spec) | Básico |
| H-07 | Frase `x 256, y 262, 820 × 36` | Texto 28 bold | Ver coluna "Frase grande" em §2.2 (ex.: "Pronto para ouvir") | derivado (§2) | Nenhuma | 12 casos de §2.2 | Básico |
| H-08 | Subtítulo `x 256, y 298, 820 × 22` | Texto 14 `#9db0e0` (1 linha, reticências se passar) | Ver §2.2 (ex.: "Diga 'Hey Gideon' ou digite um comando.") | derivado (§2) | Nenhuma | Ver §2.2 | Básico |
| H-09 | Badge `x 256, y 330, 150 × 22` | Badge info | "Microfone ativo" | `core.state` = `capturing` (P0-I9 e P5 de Ouvindo) | Nenhuma | Visível só em Ouvindo | Básico |
| H-09a | Linha Avançado `x 256, y 356` | Texto 12 `#9db0e0` | "Confiança: desconhecida" | `snapshot["transcript"]["confidence"]` (NF-15: validado, não exibido). **NOVO (ponte/Core)**: expor `transcript.confidence` | Nenhuma | Visível só se o Core enviar o campo; "Desconhecido" por design | Avançado |

Cartão B — proposta pendente (`x 140, y 420, 1100 × 180`; visível só se `core.toolProposals` tiver ao menos um item `pending`; se houver mais de um, mostra o **mais antigo** e a legenda "1 de N" em H-10a):

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| H-10 | Cartão `y 420` | Cartão | Título: "Proposta pendente" (17 semibold) | `core.toolProposals` filtrado por `state` = `pending` (`bridge.py:1337`, P7-I7) | — | Oculto sem pendência | Básico |
| H-10a | Legenda `x 900, y 436`, direita | Texto 12 `#9db0e0` | "1 de {N}" (só se N > 1) | contagem de `pending` | — | — | Básico |
| H-11 | `x 160, y 436` | Texto 14 bold | "Ferramenta {tool} · {toolStateText}". Estado `pending` → "aguardando sua decisão" | `item.tool`, `item.state` (`toolStateText`, `Main.qml:128`) | — | Estados de `toolStateText`: "aguardando sua decisão" · "autorizada; executando" · "executada" · "negada" · "falhou" · "expirada" · "cancelada" | Básico |
| H-12 | `x 160, y 458` | Texto 14 | "Alvo: {plugin_id}" (ex.: "Alvo: gideon.calendar") | `item.plugin_id` (`bridge.py:76`, TOOL_KEYS, EXISTE) | — | Sem plugin: "Alvo: Base" | Básico |
| H-13 | `x 160, y 480` | Texto 14 | "Efeito: {effect}". Sem o campo: "Efeito: não informado pelo plugin" | **NOVO (ponte/Core)**: campo `effect` em tool proposals (hoje só AC-14: propostas locais não têm risco nem efeito) | — | Ver texto de ausência | Básico |
| H-14 | `x 160, y 502` | Texto 14 | "Risco: {baixo \| médio \| alto}". Sem o campo: "Risco: não declarado" | **NOVO (ponte/Core)**: campo `risk` em tool proposals. Propostas de conexão já têm `risk` (`valid_conn_proposal`, `bridge.py:349`) | — | Cor do rótulo: baixo `#5ee0a0`, médio `#f2c15c`, alto `#ff7d8a`; a palavra vem sempre junto | Básico |
| H-15 | `x 160, y 524` | Texto 12 `#9db0e0` | "Argumentos: {JSON}" (até 4 KB, rolagem interna) | `item.args` (`bridge.py:76`, EXISTE) | — | Vazio: "Argumentos: nenhum" | Avançado |
| H-16 | Motivo (`x 160, y 524`, se houver e não houver `Argumentos`) | Texto 12 | "Motivo: {codeMessage(reason)}" (ex.: "Negada pelo usuário") | `core.codeMessage(reason)` (`bridge.py:1277`, P7-I10) | — | Só quando `reason` existe | Básico |
| H-17 | "Negar": `x 1000, y 544, 100 × 40` | Botão secundário (perigo: contorno `#ff7d8a`) | "Negar" | `core.decideTool(id, "deny")` (`bridge.py:1341`, P7-C4) | "Negar" → decisão `deny` → `tool_denied` → item fica "negada". Resultado em `core.toolResult` (ex.: "Negada pelo usuário") | Normal; "Enviando decisão ao Core…" (desabilitado, durante o envio); `already_decided` → "Proposta já foi decidida" | Básico |
| H-18 | "Autorizar": `x 1112, y 544, 108 × 40` | Botão primário | "Autorizar" | `core.decideTool(id, "authorize")` (P7-C5) | Se `risk` = `alto`: abre diálogo de confirmação antes (NOVO QML): título "Autorizar a ferramenta {tool}?"; texto "{effect}. Esta ação pode alterar dados."; botões [Cancelar] (foco inicial) e [Autorizar]. Senão: decisão direta → "autorizada; executando" → "executada" + "Resultado: {texto}" | Igual a H-17; expirada: "Expirou sem decisão" (`bridge.py` CODE 'expired') | Básico |

Cartão C — comando e última interação (`x 140, y 616` com B; `y 420` sem B; `1100 × 264`):

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| H-19 | Título `x 160, y 632` | Texto 17 semibold | "Comando" | — | — | — | Básico |
| H-20 | Legenda `x 160, y 652` | Texto 12 `#9db0e0` | "Texto segue o mesmo caminho da voz. Até 512 bytes, em uma linha." | — | — | — | Básico |
| H-21 | Campo `x 160, y 672, 920 × 44` | Campo de texto (1 linha) | Placeholder: "Diga ou digite um comando". Nome acessível: "Comando para o Gideon" | `core.textAvailable` (`bridge.py:1697`, P0-C4), `core.sessionId`, `core.connected` | Enter ou "Enviar" → `core.submitText(texto)` (`bridge.py:1245`). O campo é limpo após envio aceito | Normal; ver §3.9 para desabilitado; durante o envio, somente leitura | Básico (rótulo "Dev" no modo dev: §3.7 H-27) |
| H-22 | "Enviar": `x 1092, y 672, 128 × 44` | Botão primário | "Enviar" (nome: "Enviar comando") | mesmo de H-21 | `submitText` | Desabilitado se campo vazio (tooltip "Digite um comando") | Básico |
| H-23 | Motivo / resultado `x 160, y 724, 1060 × 20` | Texto 12, cor de aviso `#f2c15c` ou secundária | Mostra, nesta ordem: (a) motivo de desabilitado (§3.9); (b) `core.textResult` (resultado do último envio, EXISTE, P0-I11); (c) vazio | `core.textResult` (`bridge.py:1699`), motivos calculados | — | Vazio = nada | Básico |
| H-24 | "Última interação" `x 160, y 748` | Texto 14 bold | "Última interação" | — | — | — | Básico |
| H-25 | Bolha Você `x 160, y 768, 1060 × 40` | Bolha | "Você: {core.subtitle}". Vazio: "Sua conversa aparecerá aqui." | `core.subtitle` (`bridge.py:1801`, P0-I9); `core.partial` (`bridge.py:1803`) | Nenhuma (texto selecionável, somente leitura) | Parcial: prefixo "(parcial)" e nome acessível "Transcrição parcial"; final: "Transcrição final" (texto de `Main.qml:1563`) | Básico |
| H-26 | Recibo `x 160, y 820, 1060 × 24` | Texto 14 | "Gideon · Concluído · {texto}" se `resultVerified`; "Gideon · Falhou · {texto}" se o recibo for de erro. Vazio: nada | `core.result` (`bridge.py:1805`, P0-I10), `core.resultVerified` (`bridge.py:1809`) | — | Concluído `#5ee0a0`; Falhou `#ff7d8a`; a palavra vai sempre junto. Texto cru de código: ver AC-19 | Básico |
| H-27 | Rótulo de desenvolvimento `x 1020, y 632` (linha do título do cartão C, à direita) | Badge | "Entrada de teste (desenvolvedor)" | Modo desenvolvedor ligado (Diagnóstico › Estado) | — | Só com o modo ligado | Dev |

### 3.7 Estados de Hoje (resumo)

| Estado | Faixa | Cartão A | Cartão B | Cartão C |
|---|---|---|---|---|
| Normal, em espera | H-01 "Em espera" | "Pronto para ouvir" | oculto | campo ativo (se `textAvailable`) ou desabilitado com motivo |
| Ouvindo | H-01 "Ouvindo" | "Ouvindo…" + badge H-09 | oculto | campo desabilitado: "Indisponível: uma sessão de voz está em andamento." |
| Transcrevendo | "Transcrevendo" | "Transcrevendo…" | oculto | campo desabilitado (mesmo motivo) |
| Executando | "Executando" | "Executando…" | oculto ou visível | campo desabilitado |
| Falando | "Falando" | "Falando…" | oculto ou visível | campo desabilitado |
| Pensando (chat/agente) | "Pensando" | "Pensando…" | oculto ou visível | campo **ativo** |
| Aguardando aprovação | "Aguardando aprovação" | "Aguardando sua aprovação" | visível | ativo se não há sessão |
| Erro | "Erro" | "Erro" + texto do erro | oculto ou visível | ativo |
| Core desconectado | "Core desconectado" | "Core desconectado" | **oculto** (propostas somem com o snapshot) | desabilitado: "Indisponível: Core desconectado." |
| Modo seguro / reinício | "Modo seguro" / "Reinício necessário" | texto da §2.2 | oculto | desabilitado: "Indisponível: o Core precisa de atenção." |
| Vazio geral | "Pronto para ouvir" | ok | oculto | "Última interação" mostra "Sua conversa aparecerá aqui." |

### 3.8 Textos de desabilitado e de erro (Hoje)

Campo de comando (H-21), motivo mostrado em H-23 quando desabilitado:

| Condição | Texto exato (motivo) | Origem |
|---|---|---|
| Core desconectado | "Indisponível: Core desconectado." | NOVO (QML) |
| Sessão de voz ativa (`sessionId` não vazio) | "Indisponível: uma sessão de voz está em andamento." | NOVO (QML); a regra existe em `bridge.py:1244` |
| Sem entrada de texto no perfil (`textAvailable` falso) | "Indisponível: a entrada de texto só existe no perfil de teste." | NOVO (QML); a causa é `--virtual-input` (`src/core.rs:809-812`, P0-C4) |
| Modo seguro / reinício | "Indisponível: o Core precisa de atenção." | NOVO (QML) |

Mensagens que o slot devolve (aparecem em H-23 após o envio): "Texto vazio" · "Texto acima de 512 bytes" · "Texto com quebra de linha ou controle não é aceito" · "Entrada de texto indisponível agora" · "Aguarde o envio anterior" · "Texto na fila para envio" · "Enviando texto ao Core" (`bridge.py:1078`, `PENDING['text']`). Todas são **texto exato** de `bridge.py:48-56` e `bridge.py:1245-1256`.

Validação ao digitar: **NOVO (ponte/Core)** — expor um slot `commandProblem(texto)` igual a `chatTextProblem` (`bridge.py:1275`) que chame `text_problem`. Até lá, o erro só aparece após o envio.

Erro de envio do Core (`textResult`): texto cru não é mostrado; vale o mapeamento de `CODE_MESSAGES` (`bridge.py:670`). Código desconhecido vira: "Core recusou a ação: {código}" (`bridge.py:780`) — **isso mostra código cru**; ver AC-19.

### 3.9 Fluxos de Hoje

**F-H1 — Autorizar proposta de ferramenta (passo a passo):**
1. O cartão B aparece em `y 420` com título "Proposta pendente". O foco do teclado **não** é movido para ele (nada é aprovado com Enter ao chegar).
2. O usuário lê Ferramenta, Alvo, Efeito, Risco e (Avançado) Argumentos.
3. Clique em "Autorizar" (H-18). Se o risco for `alto`, abre o diálogo de confirmação (ver H-18). Em `baixo` ou `médio`, a decisão vai direto.
4. Enquanto aguarda, os dois botões ficam desabilitados e o texto da linha H-11 vira "Ferramenta {tool} · Enviando decisão ao Core…" (`PENDING['tool_decide']` = "Enviando decisão ao Core…", `bridge.py:1079`).
5. Resultado: a linha H-11 muda para "autorizada; executando" e depois "executada" + "Resultado: {texto}" (vem de `item.result`). O cartão some quando não há mais pendência.
6. Falhas: `already_decided` → "Proposta já foi decidida"; `unknown_proposal` → "Proposta desconhecida ou encerrada"; a proposta chega como `failed` → "falhou" + motivo (`CODE_MESSAGES`: "Plugin indisponível", "Argumentos inválidos; ação recusada", "Ferramenta desconhecida; ação recusada" etc.).
7. Negar: mesmo caminho, sem diálogo. Resultado: "negada" + "Negada pelo usuário".

**F-H2 — Enviar comando de texto:**
1. O campo fica ativo se `textAvailable`.
2. Enter ou "Enviar". Se o campo estiver vazio ou inválido, nada é enviado e H-23 mostra a mensagem da validação.
3. `submitText` aceito: campo fica somente leitura por 1 ciclo (`PENDING['text']` = "Enviando texto ao Core"), depois limpa e H-25/H-26 atualizam com o resultado.

**F-H3 — Chip de estado:** clique leva à sub-aba correspondente em Configurações ou Extensões (ver H-02, H-03, H-04). Não cria nenhuma pendência.

### 3.10 Regras de Hoje
- Os chips e o cartão de estado não editam nada: são leituras e atalhos.
- Cartão B nunca fica "preso" na tela: sumiu do snapshot (proposta decidida ou expirada) → some na mesma atualização.
- A frase grande muda sem animação de texto (troca direta). O orbe tem pulso de 1,2 s apenas em "Ouvindo" e "Falando"; com efeitos desligados (máquina fraca, Notion §Direção) fica estático.

### 3.11 Acessibilidade de Hoje
- Ordem de foco (após as abas e sub-abas): H-02 → H-03 → H-04 → H-17 (Negar, se B) → H-18 (Autorizar, se B) → H-21 → H-22 → H-25 (leitura) → H-26 (leitura).
- Nomes acessíveis: H-06 "Indicador visual do Gideon"; H-07 é lido como "Estado do Gideon, {frase}"; H-21 "Comando para o Gideon"; H-22 "Enviar comando".
- Mudança de estado: anunciar a nova frase (H-07) por leitor de tela. Qt pode anunciar por `Accessible.description`; **não verificado** (ver §11).
- Foco visível: anel de 2 px `#7693ff` em todo controle.

---

## 4. Conversa (condicional: plugin LLM com capacidade `*.chat` em execução)

### 4.1 Objetivo
Conversar por texto com o motor LLM instalado. Mostrar respostas, propostas de ferramenta e avisos do motor.

### 4.2 Condição de aparecimento
- Alvo (regra correta): a sub-aba aparece quando há um plugin **em execução** com capacidade `.chat` (`_chat_target()`, `bridge.py:1263`).
- Hoje (atual, AC-01): a sub-aba também depende de `core.chatAvailable` (`bridge.py:1272-1273`), que exige `pluginsAvailable` → `hubLifecycleAvailable` → `preferencesAvailable`, que exige **não** haver sessão de voz (`bridge.py:1683-1684`). Resultado: a sub-aba **some durante a sessão de voz** mesmo com o plugin rodando. Mudança proposta em §7.2 (NOVO ponte/Core).

### 4.3 Nível
Básico (mensagens, campo, Enviar/Cancelar, propostas, avisos). Avançado: "Estado" técnico do chat e código de erro bruto (nunca exibir código cru sem mapear).

### 4.4 Layout em grade (1380 × 904)

| Região | x | y | largura | altura | Colunas | Conteúdo |
|---|---|---|---|---|---|---|
| Faixa de resumo | 140 | 184 | 1100 | 40 | 12 | CV-01 (texto + badges) |
| Cartão único "Conversa" | 140 | 236 | 1100 | 644 | 12 | Banner (cond.), mensagens, entrada |
| Banner (condicional, dentro do cartão) | 160 | 252 | 1060 | 40 | — | CV-02 |
| Área de mensagens (rolagem) | 160 | 300 com banner, **252** sem | 1060 | 472 com banner, **520** sem | — | CV-03..CV-08 |
| Entrada fixa | 160 | 784 | 920 + 128 | 48 | — | CV-09..CV-11 |
| Mensagem de validação | 160 | 836 | 1060 | 20 | — | CV-12 |

**Reflow abaixo de 900 px:** campo ocupa a largura toda; Enviar/Cancelar vai para a linha de baixo, à direita. Balões de mensagem usam até 90 % da largura. Propostas inline ocupam a largura toda; botões Negar/Autorizar alinhados à direita.

### 4.5 Wireframe (escala 1 col = 10 px, 1 linha = 20 px)

```
 236 |+- Conversa: mensagens e entrada -----------------------------------------------------------------------------+
 256 || +- Aviso (condicional) ----------------------------------------------------------------------------------+ |
 276 || +--------------------------------------------------------------------------------------------------------+ |
 296 || +- Mensagens (rolagem) ----------------------------------------------------------------------------------+ |
 316 || |                                                       +- Voce: texto da mensagem --------------+       | |
 336 || |                                                       +----------------------------------------+       | |
 356 || |                                                                                                        | |
 376 || +- Gideon: resposta (texto puro) ----------------------------+                                           | |
 396 || |                                                            |                                           | |
 416 || +------------------------------------------------------------+                                           | |
 436 || |                                                                                                        | |
 456 || +- Proposta de ferramenta (inline) ----------------------------+                             | |
 476 || | Ferramenta <nome> - aguardando sua decisao                               |                             | |
 496 || | Alvo: <ferramenta> - Efeito: <texto> - Risco: <nivel>                    |                             | |
 516 || |                                                                          |                             | |
 536 || |                                                                          |                             | |
 556 || |                                                   +- Negar-+ +- Autori-+ |                             | |
 576 || |                                                   +--------+ +---------+ |                             | |
 596 || +--------------------------------------------------------------------------+                             | |
 616 || |                                                                                                        | |
 636 || | Aguardando resposta... (parcial aparece aqui)                                                          | |
 656 || |                                                                                                        | |
 676 || |                                                                                                        | |
 696 || |                                                                                                        | |
 716 || |                                                                                                        | |
 736 || |                                                                                                        | |
 756 || +--------------------------------------------------------------------------------------------------------+ |
 776 || +- Mensagem para o motor LLM --------------------------------------------------------------+ +- Enviar --+ |
 796 || |                                                                                          | |           | |
 816 || +------------------------------------------------------------------------------------------+ +-----------+ |
 836 || Enter envia - 1 linha - ate 4096 bytes                                                                     |
 856 |+------------------------------------------------------------------------------------------------------------+
```

Nota do desenho: os balões e a proposta ficam dentro da área rolável. Quando a conversa é vazia, a área mostra o estado vazio (CV-03) no lugar das mensagens.

### 4.6 Elementos de Conversa

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| CV-01 | Faixa `y 184–224` | Texto 14 bold (esquerda) + badges (direita) | Esquerda: "Estado da conversa: {chatStateLabel}". Badges: "Modelo: {modelo}" (ou "Modelo: não configurado") e "Nuvem: autorizada" (`Aprovação`) / "Nuvem: não autorizada" (`Aviso`) | `core.chatStateLabel` (`bridge.py:1287`, P7-I1); `core.modelsSelected.model`; `core.llmConfig.cloud_consent` (`bridge.py:1387`) | Badge de nuvem → Extensões › Modelos LLM › Provedor e chaves | Normal | Básico |
| CV-02 | Banner `x 160, y 252, 1060 × 40` (cond.) | Aviso (fundo `#f2c15c` a 12 %, borda `#f2c15c`) | Ver tabela §4.7 (apenas um banner, o de maior prioridade) | `llmConfig.cloud_consent`, `llmSecretsConfigured`, código de `chatResult`, flag de fallback (NOVO) | Link "Abrir Modelos LLM" → Extensões › Modelos LLM › Provedor e chaves | Oculto quando não há aviso | Básico |
| CV-03 | Área de mensagens `x 160, y 300` (ou `252`) | Lista rolável | Vazio: "Nenhuma mensagem ainda. O motor LLM é opcional: voz, wake e comandos da Base funcionam sem ele." (`Main.qml` P7-T2, EXISTE) + duas sugestões em chip: "Que horas são?" e "Abrir o Brave" (NOVO copy) | `core.chatMessages` vazio (`bridge.py:1289`) | Clique em sugestão → preenche o campo CV-09 (**não envia**) | Vazio / com mensagens | Básico |
| CV-04 | Balão Você (`x 720–1140`, alinhado à direita) | Balão | "Você" (12 bold) + texto. Sufixo: "cancelada" ou "erro" (`Main.qml:1433-1442`, P7-I3) | `core.chatMessages` com `role` = `user` | Nenhuma | Normal; cancelada; erro | Básico |
| CV-05 | Balão Gideon (`x 160–780`, alinhado à esquerda) | Balão | "Gideon" (12 bold) + texto. Sufixo "cancelada" ou "erro". Texto em `PlainText` | `core.chatMessages` com `role` = `assistant` | Nenhuma | Normal; cancelada (mantém o trecho parcial); erro (mostra o trecho parcial e o erro abaixo) | Básico |
| CV-06 | Resposta em curso (dentro da lista, abaixo do último balão) | Texto 14 `#dce7ff` | Estado `waiting`: "Aguardando resposta…". Estado `streaming`: texto parcial de `core.chatPartial` (`bridge.py:1291`); sem parcial ainda: "Aguardando resposta…" | `core.chatPartial`, `core.chatState` | Nenhuma | `waiting` / `streaming` | Básico |
| CV-07 | Proposta inline (`x 160, y 448, 760 × 160`) | Cartão de proposta (mesmo modelo de H-10 a H-18) | Título: "Ferramenta {tool} · {toolStateText}". Linha 2: "Alvo: {plugin_id} · Efeito: {effect} · Risco: {risk}" (sem campo: "Efeito: não informado pelo plugin" e "Risco: não declarado") | `core.toolProposals` (EXISTE; efeito e risco são NOVO) | Negar/Autorizar → `core.decideTool` (idêntico a H-17/H-18) | Pendente; decidida (linha de estado, sem botões) | Básico |
| CV-08 | Aviso da conversa (dentro da lista, no fim) | Texto 12 cor de aviso | `core.chatResult`. Exemplos: "Core indisponível; resposta interrompida", "Cancelamento na fila", "Erro HTTP do provedor", "Cancelado" | `core.chatResult` (`bridge.py:1293`, P7-I5) | — | Vazio = nada | Básico |
| CV-09 | Campo `x 160, y 784, 920 × 48` | Campo de texto (1 linha) | Placeholder: "Mensagem para o motor LLM". Nome acessível: "Mensagem para o motor LLM". Enter envia | `core.chatTextProblem(texto)` (`bridge.py:1275`, P7-I6) para validação ao vivo; `core.sendChat(texto)` (`bridge.py:1294`) | Enter ou Enviar → `sendChat` | Normal; desabilitado com motivo (§4.7) enquanto `waiting` ou `streaming`; somente leitura durante o envio | Básico |
| CV-10 | "Enviar" `x 1092, y 784, 128 × 48` | Botão primário | "Enviar" (nome: "Enviar mensagem ao motor LLM") | igual a CV-09 | `sendChat` | Desabilitado se `chatTextProblem` não vazio ou campo vazio | Básico |
| CV-11 | Mesmo lugar de CV-10, quando há resposta em curso | Botão secundário | "Cancelar" (nome: "Cancelar resposta") | `core.chatState` ∈ {`waiting`, `streaming`} | `core.cancelChat()` (`bridge.py:1330`). Texto: "Cancelamento na fila" ou "Cancelando capability…" | Desabilitado após pedido | Básico |
| CV-12 | Validação `x 160, y 836` | Texto 12 `#f2c15c` | Vazio: "Enter envia." Erro: "Mensagem vazia" · "Mensagem acima de 4096 bytes" · "Mensagem com quebra de linha ou controle não é aceita" (textos exatos de `bridge.py:391-400`) | `chatTextProblem` (P7-I6) | — | Vazio / erro | Básico |
| CV-13 | Motivo de "Enviar" desabilitado (mesma linha de CV-12) | Texto 12 | Ver §4.7 | — | — | — | Básico |
| CV-14 | Detalhe de conexão (Avançado) | Texto 12 `#9db0e0` | "Motor: {provedor} · {modelo}" | `core.llmConfig.provider` e `.model` | — | — | Avançado |
| CV-15 | Nota de envio (Avançado) | Texto 12 | "Mensagens não são gravadas em disco." | texto fixo (privacidade, `P0-T4`) | — | — | Avançado |

### 4.7 Avisos e motivos (Conversa)

Banner CV-02 — prioridade (a primeira vale):

| Prio | Condição | Texto exato | Ação | Origem |
|---|---|---|---|---|
| 1 | `llmConfig.cloud_consent` ≠ verdadeiro | "Consentimento de nuvem desativado: envios são recusados até você marcá-lo em Extensões › Modelos LLM." | Link "Abrir Modelos LLM" | Texto de P7-I2 (`Main.qml:1420`), com o destino corrigido para a forma definida em `UI_IA.md` |
| 2 | Último erro = `key_missing` | "Chave ausente para este provedor." | Link "Configurar chave" → Extensões › Modelos LLM › Provedor e chaves | `CODE_MESSAGES['key_missing']` (`bridge.py:689`) |
| 3 | Último erro = `provider_not_configured` | "Provedor não configurado." | Link "Configurar provedor" | `CODE_MESSAGES['provider_not_configured']` |
| 4 | Fallback respondeu a última resposta | "Respondeu o modelo de reserva: {modelo}." | — | **NOVO (ponte/Core)**: `used_fallback` (NF-10, AC-16). Hoje inexistente |

Motivos de desabilitado em CV-09/CV-10:

| Condição | Texto exato |
|---|---|
| Resposta em curso | "Aguarde a resposta anterior." (`bridge.py:1298`, texto de `sendChat`: "Aguarde a resposta anterior") |
| Sessão de voz ativa (com o alvo de §7.2) | "Indisponível: uma sessão de voz está em andamento." |
| Core desconectado | "Indisponível: Core desconectado." |
| Motor LLM sem plugin (sub-aba já oculta) | "Motor LLM indisponível" (`bridge.py:1297`, mensagem de `sendChat`) |
| Gerenciador de modelos ocupado | "Aguarde o gerenciador de modelos" (`bridge.py:1300`) |
| Contexto grande demais | "Mensagem grande demais para o contexto do motor" (`bridge.py:1302`) |

Erros de envio (CV-08): "Core ocupado; tente novamente em instantes" (`CODE_MESSAGES['busy']`); "Core indisponível" (`bridge.py:1307`); "Erro HTTP do provedor" (`CODE 'http_error'`) com `Erro HTTP {status}` quando o status vem (`bridge.py:1327`); "Resposta do provedor grande demais"; "Rede indisponível para o provedor"; "Tempo do provedor esgotado"; "Permissão de rede do plugin negada".

### 4.8 Estados de Conversa

| Estado | Mensagens | Campo (CV-09) | Botão (CV-10/CV-11) | Faixa (CV-01) |
|---|---|---|---|---|
| Vazio (sem mensagens) | CV-03 com sugestões | ativo | Enviar | "Estado da conversa: Em espera" |
| Enviando | CV-04 aparece ao aceitar o Core (`bridge.py:1309`) | somente leitura | "Enviar" desabilitado | "Estado da conversa: Aguardando resposta" |
| Aguardando resposta | CV-06 "Aguardando resposta…" | desabilitado (motivo) | "Cancelar" (CV-11) | "Estado da conversa: Aguardando resposta" |
| Recebendo | CV-06 com texto parcial | desabilitado | "Cancelar" | "Estado da conversa: Respondendo" |
| Concluída | balão Gideon (CV-05) | ativo | Enviar | "Estado da conversa: Concluída" |
| Cancelada | balão com "cancelada" | ativo | Enviar | "Estado da conversa: Cancelada" |
| Erro | balão com "erro" e CV-08 | ativo | Enviar | "Estado da conversa: Erro" |
| Sem plugin | sub-aba oculta (§4.2) | — | — | — |

Textos de estado vêm de `CHAT_STATE_LABELS` (`bridge.py:779`): "Em espera", "Aguardando resposta", "Respondendo", "Concluída", "Erro", "Cancelada". Não criar outros.

### 4.9 Fluxos de Conversa

**F-C1 — Enviar mensagem:**
1. Digitar em CV-09. CV-12 mostra o problema ao vivo ("Mensagem vazia", etc.).
2. Enter ou Enviar (CV-10). Se válido: `sendChat` → `PENDING['capability_invoke']` = "Invocando capability…" (`bridge.py:1078`). A mensagem do usuário entra na lista quando o Core aceita (`_chat_accepted`, `bridge.py:1309`).
3. Entra o estado `waiting` (CV-06 "Aguardando resposta…"); campo e Enviar desabilitados; aparece "Cancelar" (CV-11).
4. Resposta: balão Gideon, estado "Concluída". Erro: balão de erro com o trecho parcial e CV-08 com o motivo.

**F-C2 — Cancelar resposta:**
1. Clique em "Cancelar" (CV-11) ou no botão do cabeçalho (S-03, §2.4).
2. Se o Core está ocupado, o texto vira "Cancelamento na fila" (`bridge.py:1332`) e o pedido é enviado logo que possível.
3. Resultado: balão Gideon com sufixo "cancelada" e o trecho recebido até então (se houver). Estado "Cancelada".

**F-C3 — Autorizar ou negar proposta inline:** igual a H-17/H-18 (ver §3.9 F-H1), com os textos de CV-07.

### 4.10 Regras de Conversa
- Histórico: até 64 mensagens (`CHAT_MESSAGES_KEPT`, `bridge.py:78`). Não é gravado em disco; some ao fechar o app (`bridge.py:1112`, criado em memória).
- Core cai no meio de uma resposta: a resposta vira "erro" com o texto "Core indisponível; resposta interrompida" (`bridge.py:1269`, `_chat_reset`). O histórico permanece na memória da ponte.
- Enter envia; Shift+Enter não existe (mensagem de uma linha só, controle proibido).

### 4.11 Acessibilidade de Conversa
- Ordem de foco: S-03 (se visível) → sub-abas → CV-02 (link) → proposta inline (Negar, Autorizar) → CV-09 campo → CV-10/CV-11 → leitura da lista.
- A lista usa função de rolagem com leitura por novos balões ("Gideon: …"). A resposta em curso é anunciada uma vez ao fim (não a cada fragmento).
- Nomes: "Mensagem para o motor LLM" (CV-09), "Enviar mensagem ao motor LLM" (CV-10), "Cancelar resposta" (CV-11), "Resposta em andamento" (CV-06, como em `Main.qml:1452`).

---

## 5. Agente (condicional: plugin LLM com capacidade `*.chat`)

### 5.1 Objetivo
Dar um objetivo ao Gideon, acompanhar os passos e aprovar o que o agente pede. É a área de tarefas de vários passos (Notion: "painel de gerenciamento").

### 5.2 Condição de aparecimento
Igual à Conversa (§4.2). Sem plugin, a sub-aba some. Com o plugin e sem sessão de voz, aparece. Durante sessão de voz: some hoje (AC-01); alvo em §7.2.

### 5.3 Nível
Avançado para o detalhe (tabela de passos, orçamento, código). Básico para: objetivo, iniciar, abortar, resposta final, aprovações pendentes.

### 5.4 Layout em grade (1380 × 904)

| Região | x | y | largura | altura | Conteúdo |
|---|---|---|---|---|---|
| Faixa de resumo | 140 | 184 | 1100 | 40 | AG-01 |
| Cartão 1 — Objetivo | 140 | 236 | 1100 | 136 | AG-02..AG-06 |
| Cartão 2 — Passos e orçamento | 140 | 388 | 1100 | 280 | AG-07..AG-11 |
| Cartão 3 — Resposta e aprovações | 140 | 684 | 1100 | 196 | AG-12..AG-14 |

Dentro do cartão 1: título "Objetivo" (`y 252`); campo `x 160, y 276, 920 × 40`; "Iniciar" `x 1092, y 276, 128 × 40`; "Abortar" `x 1092, y 324, 128 × 40`; problema/resultado `x 160, y 326`.

**Reflow abaixo de 900 px:** "Iniciar" e "Abortar" passam para uma linha própria abaixo do campo (alinhados à direita). No cartão 2, as colunas "Risco" e "Código" saem da linha e aparecem na linha de baixo do passo (duas linhas por passo, altura 56).

### 5.5 Wireframe (escala 1 col = 10 px, 1 linha = 20 px)

```
 236 |+- 1. Objetivo ----------------------------------------------------------------------------------------------+
 256 || Objetivo para o agente                                                                                     |
 276 || +- Objetivo para o agente (linha unica) ---------------------------------------------------+ +- Iniciar -+ |
 296 || +------------------------------------------------------------------------------------------+ +-----------+ |
 316 || Objetivo vazio                                                                               +- Abortar -+ |
 336 ||                                                                                              +-----------+ |
 356 |+------------------------------------------------------------------------------------------------------------+
 376 |
 396 |+- 2. Passos e orcamento -------------------------------Tokens: 812 de 4.096 - Passos: 2 de 6----------------+
 416 ||                                                                                                            |
 436 || #   Tipo      Ferramenta   Risco        Estado         Codigo                                              |
 456 || +- Lista de passos (rolagem) ----------------------------------------------------------------------------+ |
 476 || | 1   Conversa   -            Leitura      Concluido                                                     | |
 496 || |                                                                                                        | |
 516 || | 2   Ferramenta <nome>       Leitura      Concluido                                                     | |
 536 || |                                                                                                        | |
 556 || | 3   Ferramenta <nome>       Altera       Aguardando sua decisao                                        | |
 576 || |                                                                                                        | |
 596 || |                                                                                                        | |
 616 || |                                                                                                        | |
 636 || +--------------------------------------------------------------------------------------------------------+ |
 656 |+------------------------------------------------------------------------------------------------------------+
 676 |+- 3. Resposta e aprovacoes ---------------------------------------------------------------------------------+
 696 || Resposta final                                                                                             |
 716 || <texto puro, so quando o agente concluir>                                                                  |
 736 ||                                                                                                            |
 756 || +- Aprovacao pendente do agente -------------------------------------------------------------------------+ |
 776 || | Ferramenta <nome> - aguardando sua decisao                                                             | |
 796 || | Alvo: <ferramenta> - Efeito: <texto> - Risco: <nivel>                                                  | |
 816 || |                                                                                   +- Negar-+ +- Autori-+ |
 836 || +-----------------------------------------------------------------------------------+--------+-+---------+ |
 856 |+------------------------------------------------------------------------------------------------------------+
```

Nota do desenho: a legenda "Tokens … Passos …" fica na linha do título do cartão 2, à direita (`x 700`).

### 5.6 Elementos de Agente

Faixa:

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| AG-01 | Faixa `y 184–224` | Texto 14 bold + badge | "Estado: {agentStateLabel}". Sem run: "Nenhum agente ativo" | `core.agentStateLabel` (`bridge.py:1374`, P7-I13) | — | Sem run / com run | Básico |

Cartão 1 — objetivo:

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| AG-02 | Título `x 160, y 252` | Texto 17 semibold | "Objetivo" | — | — | — | Básico |
| AG-03 | Campo `x 160, y 276, 920 × 40` | Campo de texto (1 linha, máx. 1024 bytes) | Placeholder: "Descreva o objetivo em uma frase". Rótulo acessível: "Objetivo para o agente". Enter inicia | `core.agentGoalProblem(texto)` (`bridge.py:1368`, P7-I18) para validar; texto enviado com `core.agentStart(goal)` (`bridge.py:1354`, P7-C6/C8) | Enter ou "Iniciar" | Normal; desabilitado com run ativo (valor preservado); texto de motivo (AG-04) | Básico |
| AG-04 | Linha de mensagem `x 160, y 326` | Texto 12 `#f2c15c` | Ver §5.7 (validação do objetivo, motivo de desabilitado, resultado do último pedido `core.agentResult`) | `agentGoalProblem`; `core.agentResult` (`bridge.py:1386`, P7-I17) | — | Vazio / texto | Básico |
| AG-05 | "Iniciar" `x 1092, y 276, 128 × 40` | Botão primário | "Iniciar" (nome: "Iniciar agente", `Main.qml:1539`) | `chatAvailable`, `agentActive`, `agentGoalProblem`, `chatState` | `agentStart(goal)` → "Iniciando agente…" (`bridge.py:1078`) → estado `thinking` | Habilitado só com objetivo válido, sem run ativo, sem chat em voo | Básico |
| AG-06 | "Abortar" `x 1092, y 324, 128 × 40` | Botão perigo (contorno `#ff7d8a`) | "Abortar" (nome: "Abortar agente", `Main.qml:1538`) | `core.agentActive` (`bridge.py:1372`, P7-C7) | Diálogo de confirmação (§5.8, F-A2) → `core.agentAbort()` (`bridge.py:1363`) | Habilitado só com run ativo; senão desabilitado com motivo "Nenhum agente em execução." (NOVO QML) | Básico |

Cartão 2 — passos e orçamento:

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| AG-07 | Cartão `y 388` | Cartão | Título: "Passos e orçamento" | — | — | — | Básico |
| AG-08 | Linha de orçamento `x 700, y 404, 520 × 20`, direita | Texto 12 | "Tokens: {usados} de 4.096 · Passos: {n} de {máx} · Tempo: {mm:ss}" | `core.agentBudget.tokens_used` e `.tokens_max` (`bridge.py:1384`, EXISTE; máximo 4096 = `AGENT_TOTAL_TOKENS`). **Passos** (`step`, `max_steps`) e **Tempo** (`started_ms_ago`) estão no run (`AGENT_RUN_KEYS`, `bridge.py:157`) mas **não são expostos**: NOVO (ponte/Core) | — | Sem run: "Tokens: 0 de 4.096 · Passos: 0 de 6 · Tempo: 00:00" | Básico (Passos e Tempo: Avançado se ocupar muito espaço) |
| AG-09 | Cabeçalho de colunas `x 160, y 436` | Texto 12 `#9db0e0` | "#    Tipo    Ferramenta    Risco    Estado    Código" | — | — | — | Avançado |
| AG-10 | Lista `x 160, y 460, 1060 × 200` | Lista rolável | Vazio (sem run): "Descreva um objetivo; o Gideon propõe passos e pede sua aprovação." | `core.agentSteps` (`bridge.py:1379`, EXISTE) | — | Vazio / com passos | Básico |
| AG-11 | Linha de passo (altura 40, uma por passo) | Linha | "{n}  {tipo}  {ferramenta}  {risco}  {estado}  {código}". Tipo: `chat` → "Conversa"; `tool` → "Ferramenta". Ferramenta: `tool` ou "—". Risco: `read` → "Leitura"; `state_changing` → "Altera estado"; `destructive` → "Destrutiva"; chat → "—". Estado: texto de `agentStepText` (ver §5.7). Código: `codeMessage(code)` se houver | `core.agentSteps` (`n`, `kind`, `tool`, `risk`, `state`, `code`, EXISTE) | — | Estado `awaiting_approval` mostra botões do cartão 3 (AG-13) | Cor do estado: `done` verde, `awaiting_approval`/`running` azul, `denied`/`failed`/`blocked`/`cancelled`/`stale` vermelho ou aviso; sempre com a palavra | Avançado (a linha inteira); Básico: só "n · tipo · estado" |

Cartão 3 — resposta e aprovações:

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| AG-12 | Título e texto `x 160, y 700` | Texto 17 semibold + texto 14 | Título "Resposta final". Corpo: texto da resposta. Vazio: "A resposta aparece aqui quando o agente concluir." (NOVO copy) | `core.agentAnswer` (`bridge.py:1382`, P7-I16; só existe com `done`) | — | Vazio / com resposta | Básico |
| AG-13 | Cartão de aprovação `x 160, y 752, 1060 × 108` | Cartão de proposta | Um cartão por proposta do agente com `run_id` (ver AG-14). Título: "Ferramenta {tool} · {toolStateText}". Linha: "Alvo: {plugin_id} · Efeito: {effect} · Risco: {risk}" | `core.toolProposals` com `run_id`/`step` (`AGENT_PROPOSAL_KEYS`, `bridge.py:157`, EXISTE); efeito e risco NOVO | Negar/Autorizar → `decideTool` (igual a H-17/H-18) | Pendente / decidida | Básico |
| AG-14 | Botões de AG-13: "Negar" `x 1000, y 812, 100 × 40`; "Autorizar" `x 1112, y 812, 108 × 40` | Botões | "Negar", "Autorizar" | igual a AG-13 | igual a AG-13 | Desabilitados durante envio | Básico |

Se há mais de uma aprovação pendente do agente, o cartão 3 rola na vertical; o cartão mostra as propostas em ordem de passo.

### 5.7 Textos do agente

Estados de run (`AGENT_STATE_LABELS`, `bridge.py:155`, EXISTE): "Pensando", "Executando ferramenta", "Aguardando sua aprovação", "Concluído", "Falhou", "Abortado", "Bloqueado". Se houver código de erro: "{rótulo} · {código mapeado}".

Estados de passo (`agentStepText`, `Main.qml:130`, EXISTE — texto exato): "em execução", "concluído", "aguardando sua decisão", "negado pelo usuário", "falhou", "tela desatualizada", "bloqueado", "cancelado".

Validação do objetivo (`agent_goal_problem`, `bridge.py:353-360`, texto exato): "Objetivo vazio" · "Objetivo acima de 1024 bytes" · "Objetivo com quebra de linha ou controle não é aceito".

Motivos de desabilitado de "Iniciar" (AG-05):

| Condição | Texto exato | Origem |
|---|---|---|
| Sem plugin LLM / alvo sem chat | "Indisponível: o motor LLM não está ativo." | NOVO (QML). Ao clicar (se habilitado por erro), o Core responde "Configuração do motor indisponível" (`bridge.py:709`, `llm_unavailable`) |
| Já existe agente em execução | "Já existe um agente em execução; aguarde ou aborte" | `CODE_MESSAGES['agent_busy']` (`bridge.py:724`) |
| Conversa em voo | "Aguarde a conversa terminar" | `bridge.py:1358` |
| Gerenciador de modelos ocupado | "Aguarde o gerenciador de modelos" | `bridge.py:1359` |
| Sessão de voz ativa (alvo de §7.2) | "Indisponível: uma sessão de voz está em andamento." | NOVO (QML) |

Códigos de erro de run (`AGENT_CODES`, `bridge.py:83`) passam por `codeMessage` (`bridge.py:1277`). Exemplos com texto exato: "Execução do agente desconhecida ou já encerrada" (`unknown_run`, `bridge.py:725`); "Tempo esgotado"; "Tempo do provedor esgotado". Código sem texto no mapa: usar o texto de `codeMessage` ("Core recusou a ação: {código}", `bridge.py:780`), que ainda mostra o código (ver AC-19).

### 5.8 Fluxos de Agente

**F-A1 — Iniciar um agente:**
1. Digitar o objetivo em AG-03. AG-04 valida ao vivo.
2. Enter ou "Iniciar" (AG-05). Mensagem "Iniciando agente…" (`bridge.py:1078`).
3. A barra de estado mostra "Pensando"; passos aparecem em AG-10/AG-11 conforme chegam (até 6 passos de agente `AGENT_MAX_STEPS = 6`, `bridge.py:156`; e até 12 de chat e 25 de ferramenta, `AGENT_CHAT_STEPS`, `AGENT_TOOL_STEPS`).
4. Passo de ferramenta que muda estado → `awaiting_approval` → aparece uma aprovação em AG-13. Decisão igual ao cartão de Hoje.
5. Fim: `done` → AG-12 mostra a resposta (texto puro, até 4 KB). `failed`, `aborted`, `blocked` → AG-01 mostra o motivo.

**F-A2 — Abortar agente (passo a passo):**
1. "Abortar" (AG-06) só habilitado com run ativo.
2. Clique → diálogo de confirmação (**NOVO QML**: hoje `Main.qml:1538` chama `agentAbort` direto, sem diálogo; AC-28 em §10):
   - Título: "Abortar o agente?"
   - Texto: "O chat em andamento e as propostas pendentes deste agente serão cancelados. Ações já executadas não são desfeitas."
   - Botões: [Cancelar] (**foco inicial**) e [Abortar agente] (perigo).
   - Texto validado com `docs/C3.md` (abort cancela chat em voo e propostas pendentes; run vai a `aborted`). Confirmar com o dono.
3. Confirmar → `core.agentAbort()` → "Enviando aborto ao Core…" (`bridge.py:1078`).
4. Resultado: estado `Abortado`; propostas pendentes viram "cancelada" (`toolStateText`).
5. `unknown_run` → "Execução do agente desconhecida ou já encerrada" (`CODE_MESSAGES`).

**F-A3 — Aprovar proposta do agente:** igual a F-H1 (cartão AG-13).

### 5.9 Regras de Agente
- Um agente por vez (`agent_busy`).
- Não é possível iniciar durante uma conversa em voo ("Aguarde a conversa terminar", `bridge.py:1358`).
- A troca de provedor/chave que revogue o plugin aborta o run (`docs/C3.md`, regra de revogação): a UI mostra o estado `aborted` com o código correspondente.
- Passos `stale` ("tela desatualizada") vêm do Core; a UI não tenta corrigir.
- Os tokens só sobem: `tokens_used` nunca passa de 4.096.

### 5.10 Acessibilidade de Agente
- Ordem de foco: S-03 → sub-abas → AG-03 (campo) → AG-05 (Iniciar) → AG-06 (Abortar) → lista AG-10 (rolável por teclado) → AG-13/AG-14 (decisão).
- Nomes: AG-03 "Objetivo para o agente"; AG-05 "Iniciar agente"; AG-06 "Abortar agente".
- Passos: cada passo é lido como "Passo {n}, {tipo}, {estado}". Linhas não são clicáveis.

---

## 6. Atividade

### 6.1 Objetivo
Ver o que aconteceu nesta sessão: comandos e recibos, execuções de skill, runs do agente, propostas autorizadas e negadas, erros. **Sem conteúdo sensível** (nada de transcrição, argumentos, respostas do LLM ou JSON de saída).

### 6.2 Condição de aparecimento
Sempre visível.

### 6.3 Nível
Básico (linha do tempo com texto e resultado). Avançado: número da sequência (`#seq`), identificadores (`run_id`), código bruto mapeado, linha "Última chamada" completa.

### 6.4 Layout em grade (1380 × 904)

| Região | x | y | largura | altura | Conteúdo |
|---|---|---|---|---|---|
| Faixa de resumo | 140 | 184 | 1100 | 40 | AT-01 (contagem à esquerda, filtro à direita) |
| Cartão único "Linha do tempo" | 140 | 236 | 1100 | 644 | Lista rolável (AT-02…AT-06) |
| Segmentado de filtro (na faixa) | 770 | 189 | 450 | 30 | 5 segmentos de 90 px |

**Reflow abaixo de 900 px:** o segmentado desce para uma linha própria, abaixo do texto da faixa, ocupando a largura toda (cada segmento com largura igual). A lista continua em um cartão só.

### 6.5 Wireframe (escala 1 col = 10 px, 1 linha = 20 px)

```
 236 |+- Linha do tempo (rolagem) ---------------------------------------------------------------------------------+
 256 || +- Comando autorizado - Concluido -----------------------------------------------------------------------+ |
 276 || +--------------------------------------------------------------------------------------------------------+ |
 296 || +- Ferramenta autorizada --------------------------------------------------------------------------------+ |
 316 || +--------------------------------------------------------------------------------------------------------+ |
 336 ||                                                                                                            |
 356 || +- Falha ao executar ferramenta - Erro ------------------------------------------------------------------+ |
 376 || +--------------------------------------------------------------------------------------------------------+ |
 396 || +- Agente iniciado --------------------------------------------------------------------------------------+ |
 416 || +--------------------------------------------------------------------------------------------------------+ |
 436 ||                                                                                                            |
 456 || +- Skill executada - Concluida --------------------------------------------------------------------------+ |
 476 || +--------------------------------------------------------------------------------------------------------+ |
 496 ||                                                                                                            |
 516 ||                                                                                                            |
 536 ||                                                                                                            |
 556 ||                                                                                                            |
 576 ||                                                                                                            |
 596 ||                                                                                                            |
 616 ||                                                                                                            |
 636 ||                                                                                                            |
 656 ||                                                                                                            |
 676 ||                                                                                                            |
 696 ||                                                                                                            |
 716 ||                                                                                                            |
 736 ||                                                                                                            |
 756 ||                                                                                                            |
 776 ||                                                                                                            |
 796 ||                                                                                                            |
 816 ||                                                                                                            |
 836 ||                                                                                                            |
 856 |+------------------------------------------------------------------------------------------------------------+
```

Vazio: a lista é trocada por um quadro tracejado centralizado (`x 160–1220`, altura mínima 140) com o texto de AT-03.

### 6.6 Elementos de Atividade

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| AT-01 | Faixa, esquerda `x 156, y 196` | Texto 14 bold | "{N} eventos nesta sessão". Zero: "Nada ainda nesta sessão" | contagem dos itens **do filtro atual** | — | Zero / N | Básico |
| AT-01a | Segmentado `x 770–1220, y 189–219` | Controle segmentado (5) | "Tudo" · "Comandos" · "Skills" · "Agente" · "Erros" | — | Clique ou setas → filtra a lista. Padrão "Tudo" | Ativo: fundo acento 18 %; inativo: borda `#2a3d78` | Básico |
| AT-02 | Lista `x 160, y 256, 1060 × 524` | Linhas (altura 40, espaço 8) | Texto da linha (ver §6.7) + badge de resultado à direita, `x 1080–1220` | `core.events` (**NOVO ponte/Core**: expor a lista `events` do snapshot, `bridge.py:31` e `:657`), `core.skillHistory` (`bridge.py:2001`, P10-I28, EXISTE), `core.connectionLastCall` (`bridge.py:2098`, P11-I16, EXISTE) | Clique na linha: não faz nada (somente leitura). Em Avançado, abre o detalhe (tela só de leitura, sem ação) | Normal; filtrado; com erro | Básico |
| AT-03 | Vazio `x 160, y 256, 1060 × 140` | Estado vazio (quadro tracejado, ícone 32 px) | "Nada ainda nesta sessão" + botão "Ir para Hoje" | lista vazia | "Ir para Hoje" → sub-aba Hoje | Vazio / filtrado sem itens: "Nada neste filtro." (NOVO copy) | Básico |
| AT-04 | Banner `x 160, y 252` (cond.) | Aviso (texto 12 `#f2c15c`) | "Core desconectado · mostrando a última leitura" | `core.connected` falso | — | Só com Core desconectado | Básico |
| AT-05 | Linha de skill (dentro da lista) | Linha | "{skill} v{versão} · {estado} · passo {id}". Estado com `skillRunText` (`Main.qml:47`, texto exato: "executando" · "aguardando sua decisão" · "concluída" · "falhou" · "cancelada" · "revertida"). Códigos: `codeMessage` (até 8) | `core.skillHistory` (`run_id`, `skill`, `version`, `state`, `step`, `codes`), `bridge.py:852` | — | Badge: "Concluída" verde; "Falhou" vermelho; outros neutro | Básico; Avançado: `run_id` |
| AT-06 | Linha de última chamada (no topo do grupo "Conexões", ou no fim da lista) | Linha | "Última chamada: {operação} · {resultado}" (P11-I16, texto exato). Resultado: `codeMessage(outcome)` se conhecido; senão "Resultado desconhecido". Conteúdo externo (`untrusted`): "Conteúdo externo não exibido." | `core.connectionLastCall` (`operation`, `outcome`, `code`, `untrusted`), `bridge.py:2098` | — | Sem chamada: não mostra a linha | Básico |

### 6.7 Mapa de eventos → texto (NOVO QML)

A lista de eventos vem do Core como `Event { sequence, request_id, session_id, kind }` (`src/protocol.rs`). **Não há horário** no evento (AC-25). O texto sai só do `kind`. Eventos não listados são **omitidos** (`transcript_partial` e `wake_worker` são internos).

| `kind` | Texto exato | Filtro | Resultado |
|---|---|---|---|
| `session_started` | "Sessão de voz iniciada" | Comandos | — |
| `transcript_final` | "Transcrição final recebida" | Comandos | — |
| `command_authorized` | "Comando autorizado" | Comandos | Concluído |
| `speech_started` | "Resposta por voz iniciada" | Comandos | — |
| `wake_failed` | "Falha no wake" | Erros | Falhou |
| `agent_started` | "Agente iniciado" | Agente | — |
| `agent_step` | "Passo do agente" | Agente | — |
| `agent_tool` | "Ferramenta do agente" | Agente | — |
| `tool_proposed` | "Ferramenta proposta" | Agente | — |
| `tool_authorized` | "Ferramenta autorizada" | Agente | — |
| `tool_denied` | "Ferramenta negada" | Agente | — |
| `tool_executed` | "Ferramenta executada" | Agente | Concluído |
| `tool_failed` | "Falha ao executar ferramenta" | Agente, Erros | Falhou |
| `skill_validated` | "Skill validada" | Skills | — |
| `skill_draft_put` | "Rascunho de skill salvo" | Skills | — |
| `skill_approved` | "Skill aprovada" | Skills | — |
| `skill_enabled` | "Skill habilitada" | Skills | — |
| `skill_rolled_back` | "Skill revertida" | Skills | — |
| `skill_imported` | "Skill importada" | Skills | — |
| `skill_import_previewed` | "Prévia de skill importada" | Skills | — |
| `skill_exported` | "Skill exportada" | Skills | — |
| `skill_run_started` | "Execução de skill iniciada" | Skills | — |
| `skill_step` | "Passo de skill" | Skills | — |
| `skill_service_denied` | "Serviço negado para skill" | Skills, Erros | Falhou |
| `skill_plugin_dry_run` / `skill_plugin_list` / `skill_plugin_validate` | "Ação de plugin em skill" | Skills | — |
| `preferences_updated` | "Preferências salvas" | Tudo | — |
| `configuration_recovered` | "Configuração recuperada" | Tudo | — |
| `llm_configured` | "Motor LLM configurado" | Tudo | — |
| `llm_marked_good` | "Modelo marcado como bom" | Tudo | — |
| `llm_rolled_back` | "Motor LLM revertido" | Tudo | — |
| `secret_set` | "Chave salva" (nunca mostra o valor) | Tudo | — |
| `secret_cleared` | "Chave removida" | Tudo | — |
| `hub_import_started` | "Importação de plugin iniciada" | Tudo | — |
| `hub_payload_staged` | "Pacote de plugin verificado" | Tudo | — |
| `hub_permissions_approved` | "Permissões de plugin aprovadas" | Tudo | — |
| `hub_import_cancelled` | "Importação cancelada" | Tudo | — |
| `hub_import_timeout` | "Importação de plugin expirou" | Tudo, Erros | Falhou |
| `registry_visual_run` | "Execução visual registrada" | Tudo | — |

Lista de eventos: até 64 (anel do Core). A UI mantém a lista como veio. Um evento que chega com `kind` desconhecido aparece como "Evento do Core" (texto genérico, NOVO copy) e fica no filtro Tudo.

### 6.8 Filtros e estados

| Filtro | Inclui |
|---|---|
| Tudo | todos os eventos mapeados; linhas de skill; linha de última chamada |
| Comandos | eventos de Comandos (tabela acima) |
| Skills | eventos de skill; linhas de skill (`skillHistory`) |
| Agente | `agent_*`, `tool_*`; run atual |
| Erros | `wake_failed`, `tool_failed`, `hub_import_timeout`, `skill_service_denied`; skills com estado `failed`; última chamada com resultado de falha |

Badge de resultado: "Concluído" (verde), "Falhou" (vermelho), sem badge para os demais. Sempre texto + cor.

### 6.9 Regras de Atividade
- **Ordem:** do mais recente para o mais antigo, pelo `sequence` dos eventos. Linhas de skill e de última chamada **não têm horário**; entram no topo na ordem em que a UI as viu pela primeira vez (NOVO QML; a solução de verdade é timestamp no Core, AC-25).
- **Sem conteúdo:** Atividade nunca mostra transcrição, argumentos, resposta, saída de skill ou conteúdo MCP.
- **Core cai:** a lista do snapshot some com o snapshot (`bridge.py:1138`). A UI guarda a última lista recebida e mostra AT-04. Ao reconectar, a lista é substituída pelo que o Core enviar.
- **Limite:** o Core guarda 64 eventos. Mais que isso, o mais antigo sai. A UI não guarda histórico próprio.

### 6.10 Acessibilidade de Atividade
- Ordem de foco: S-03 → sub-abas → segmentado AT-01a (setas trocam o filtro) → lista (rolável) → AT-03 ("Ir para Hoje").
- Nome da lista: "Linha do tempo da atividade". Cada linha é lida como "{texto}, {resultado}".

---

## 7. Regras transversais (plugin LLM, sessão de voz e Core)

### 7.1 Plugin LLM não está rodando (sem capacidade `.chat` em execução)

| Elemento | Comportamento |
|---|---|
| Sub-abas Conversa e Agente | Não aparecem (S-05, S-06) |
| Hoje, chip H-04 | "Modo: Base, sem LLM". Clique → Extensões › Plugins. Tooltip: "Instalar em Extensões › Plugins" |
| Hoje, comando (H-21) | Continua funcionando (é o caminho de comando da Base) |
| Usuário estava em Conversa ou Agente quando o plugin parou | A tela muda para **Hoje** e aparece toast: "O motor LLM parou. Conversa indisponível." (NOVO copy; texto de `P7-T3` reescrito sem "Gideon Hub") |
| Texto de estado | `Main.qml` P7-T3 ("Motor LLM não está ativo…") deixa de ser usado. Não existe tela de Conversa sem plugin |

### 7.2 Sessão de voz ativa (`core.sessionId` não vazio)

| Elemento | Comportamento **atual** (AC-01, inferido do código) | Comportamento **alvo** (NOVO ponte/Core) |
|---|---|---|
| Sub-abas Conversa e Agente | Somem (`chatAvailable` falso; `bridge.py:1272-1273`) | Permanecem enquanto o plugin roda |
| Envio de chat (CV-09/CV-10) | Não existe (sub-aba oculta) | Desabilitado com motivo "Indisponível: uma sessão de voz está em andamento." |
| Iniciar agente (AG-05) | Desabilitado (`chatAvailable` falso) | Desabilitado com o mesmo motivo |
| Hoje, comando (H-21) | Desabilitado (`textAvailable` exige não haver sessão, `bridge.py:1244`) | Igual |
| Cancelar (S-03) | Visível (session); pela regra, cancela a sessão | Igual |
| HUD | Segue o Core (§2) | Igual |

Mudança de ponte necessária para o alvo: desacoplar `chatAvailable` de `pluginsAvailable`/`preferencesAvailable` (`bridge.py:1272-1273`, `1683-1684`, `1728-1729`, `1745-1746`), mantendo `sendChat` (`bridge.py:1294-1310`) com o motivo de sessão. **Confirmar com o dono** antes de implementar: o efeito de AC-01 é inferido e não foi visto em execução.

### 7.3 Core cai (`core.connected` falso)

| Elemento | Comportamento |
|---|---|
| Pílula (S-02) e HUD (§2) | "Core desconectado" / "Tentando reconectar…" |
| Cancelar (S-03) | Some (`sessionCancellable` exige `connected`, `Main.qml:41`) |
| Conversa e Agente | Somem (`chatAvailable` exige `online`) |
| Resposta do chat em curso | Vira erro: "Core indisponível; resposta interrompida" (`bridge.py:1269`). O histórico do chat permanece na memória da ponte e volta a aparecer ao reconectar |
| Run do agente | O snapshot é limpo (`bridge.py:1138`). **Não está verificado** se o Core mantém o run após reconectar; ver §11 |
| Propostas pendentes | Somem da tela (`toolProposals` vazio). O Core decide o destino (expira ou fica pendente) |
| Hoje, comando (H-21) | Desabilitado: "Indisponível: Core desconectado." |
| Atividade | Mostra a última lista com AT-04 |
| Reconexão | Automática: 500 ms, dobrando até 5 000 ms (`bridge.py:1138` e `retry`). A UI só mostra a pílula; não há botão de reconectar |

### 7.4 Modo seguro / reinício necessário
Prioridades 2 e 3 de §2.2. Sub-abas de chat e agente continuam conforme plugin e sessão. Não há ação de reinício nesta aba (NF-22).

### 7.5 Feedback visual desligado (`visualFeedback` falso)
Orbe (H-06) oculto. Frase (H-07), subtítulo (H-08), pílula e cores de texto permanecem. A acessibilidade não depende do orbe.

### 7.6 Níveis e Dev
- Avançado: só com "Mostrar opções avançadas" ligado (Configurações › Geral).
- Dev: só com "Modo desenvolvedor" ligado (Diagnóstico › Estado). Hoje: H-27 "Entrada de teste (desenvolvedor)". Atividade: nenhum item dev nesta aba (o `kind` de desenvolvedor, quando existir, entra como "Evento do Core").

---

## 8. Atalhos e navegação por teclado

| Atalho | Ação | Observação |
|---|---|---|
| `Ctrl+1` | Abre a aba Assistente (`Ctrl+1…5` para as demais abas, §00-casca) | |
| `Ctrl+Tab` | Próxima sub-aba visível | Pula Conversa e Agente se ocultas |
| `Ctrl+Shift+Tab` | Sub-aba anterior visível | |
| `Tab` / `Shift+Tab` | Próximo / anterior controle | Ordem de cada sub-aba em §3.11, §4.11, §5.10, §6.10 |
| `Enter` | Envia o campo focado: comando (H-21), mensagem (CV-09), objetivo (AG-03) | Em Hoje e Conversa, só se o botão estiver habilitado |
| `Esc` | Fecha diálogos de confirmação (cancela a ação). Não cancela sessão nem resposta | Cancelar é o foco inicial dos diálogos |
| `←` / `→` | Troca de segmento no filtro AT-01a | |
| `Espaço` / `Enter` em botão | Aciona o botão focado | |

Não existe atalho para **Autorizar** nem **Negar**: aprovação exige foco no botão e ação explícita. Nenhuma tecla aprova algo sozinha.

---

## 9. Fontes de dados e o que é novo

### 9.1 Já existe (EXISTE), por sub-aba

| Propriedade / slot | Linha | Usado em |
|---|---|---|
| `core.state` | `bridge.py:1797` | S-02, §2, H-07 |
| `core.connected` | `bridge.py:1795` | §2, S-03, §7.3 |
| `core.sessionId` | `bridge.py:1799` | §2, S-03, §7.2 |
| `core.subtitle`, `core.partial` | `bridge.py:1801`, `1803` | H-08, H-25 |
| `core.result`, `core.resultVerified` | `bridge.py:1805`, `1809` | H-26 (ver AC-19) |
| `core.wakeStatus`, `sttStatus`, `speechStatus` | `bridge.py:1703-1707` | Não exibidos nesta aba (estão em Diagnóstico e no HUD via `core.state`) |
| `core.visualFeedback` | `bridge.py:1652` | H-06, §7.5 |
| `core.snapshotPack` / `core.wakeChoices` | `bridge.py:1701`, `1638` | H-02, H-03 |
| `core.textAvailable`, `core.textResult`, slot `submitText` | `bridge.py:1697`, `1699`, `1245` | H-21, H-22, H-23 |
| `core.toolProposals`, `core.toolResult`, slot `decideTool` | `bridge.py:1337`, `1339`, `1341` | H-10…H-18, CV-07, AG-13 |
| `core.codeMessage(code)` | `bridge.py:1277` | H-16, AG-11, AT-05 |
| `core.chatState`, `chatStateLabel`, `chatMessages`, `chatPartial`, `chatResult` | `bridge.py:1283`, `1287`, `1289`, `1291`, `1293` | Conversa; §2 |
| slots `sendChat`, `cancelChat`, `chatTextProblem` | `bridge.py:1294`, `1330`, `1275` | CV-08…CV-12 |
| `core.chatAvailable` | `bridge.py:1272` | §4.2, §5.2 (com AC-01) |
| `core.modelsAvailable`, `core.modelsSelected` | `bridge.py:1611`, `1630` | H-04, CV-01 |
| `core.llmConfig` (`cloud_consent`, `provider`, `model`) | `bridge.py:1387` | CV-01, CV-02, CV-14 |
| `core.llmSecretsConfigured` | `bridge.py:1390` | CV-02 (chave) |
| slots `agentStart`, `agentAbort`, `agentGoalProblem` | `bridge.py:1354`, `1363`, `1368` | AG-03…AG-06 |
| `core.agentState`, `agentActive`, `agentStateLabel`, `agentSteps`, `agentAnswer`, `agentBudget`, `agentResult` | `bridge.py:1370`, `1372`, `1374`, `1379`, `1382`, `1384`, `1386` | AG-01, AG-04, AG-08, AG-10…AG-12 |
| `core.skillHistory` | `bridge.py:2001` | AT-05 |
| `core.connectionLastCall` | `bridge.py:2098` | AT-06 |
| `core.cancel()` | `bridge.py:1239` | S-03 |
| `core.sessionCancellable` (QML) | `Main.qml:41` | S-03 |

### 9.2 Não existe — NOVO (ponte/Core)

| # | O que falta | Onde | Por que | Usado em |
|---|---|---|---|---|
| N-1 | Campos `risk` e `effect` (texto curto) em cada tool proposal | Core (`src/tools.rs`); ponte `TOOL_KEYS` (`bridge.py:76`) e `valid_tools` (`bridge.py:328`) | Aprovação precisa mostrar alvo, efeito e risco (AC-14; `UI_NOTION_REQS.md`). Propostas de conexão já têm risco (`bridge.py:349`) | H-13, H-14, H-18, CV-07, AG-13 |
| N-2 | Horário ou timestamp no `Event` | Core (`src/protocol.rs`, struct `Event`) | Hoje só há `sequence` (AC-25); sem horário a linha do tempo fica sem hora real | AT-02, §6.9 |
| N-3 | `@Property events` (lista de eventos) | Ponte (`bridge.py`): o snapshot já traz `events` (`bridge.py:31`, validado em `:657-660`), mas não há propriedade | Atividade (AT-02) | AT-02 |
| N-4 | `@Property` para `step`, `max_steps` e `started_ms_ago` do run | Ponte (`bridge.py:157`, `AGENT_RUN_KEYS`) | Orçamento de passos e de tempo (AG-08) | AG-08, AG-01 |
| N-5 | Desacoplar chat e agente da sessão de voz | Ponte (`bridge.py:1272-1273`, `1683-1684`, `1728-1729`, `1745-1746`) | AC-01: Conversa/Agente somem na sessão de voz (§7.2) | §4.2, §5.2, §7.2 |
| N-6 | Flag de fallback usado (`used_fallback`) | Core (`docs/C2.md`, NF-10) e ponte | Aviso "respondeu o modelo de reserva" (CV-02, prioridade 4) | CV-02 |
| N-7 | Slot de validação do comando (`commandProblem(texto)`) | Ponte (como `chatTextProblem`, `bridge.py:1275`) | Validação ao vivo no campo de comando (H-21) | H-21, §3.9 |
| N-8 | Tradução do recibo de erro | Ponte, `result` (`bridge.py:1805-1808`) | Hoje devolve `command.code` **cru** quando não há recibo (AC-19) | H-26 |
| N-9 | Campo `transcript.confidence` exposto | Ponte (NF-15: validado, sem propriedade) | Avançado (H-09a). Opcional | H-09a |

### 9.3 Só QML (NOVO QML, sem ponte)

| # | O que | Por que |
|---|---|---|
| Q-1 | Cancelar do cabeçalho cobre a resposta do chat (`cancelChat`) além da sessão | §2.4 (AC-08) |
| Q-2 | Diálogo de confirmação antes de "Abortar" (AG-06) | §5.8 F-A2 |
| Q-3 | Diálogo de confirmação antes de "Autorizar" quando `risk` = `alto` (H-18) | §3.9 F-H1 (depende de N-1) |
| Q-4 | Limpeza da marca de "Erro" a cada nova ação | §2.3 |
| Q-5 | Guarda da última lista de eventos enquanto o Core está fora | §6.9 |
| Q-6 | Ordem por chegada para linhas sem horário | §6.9 |
| Q-7 | Texto de HUD em português: "Falando" (não "Respondendo") e "Core desconectado" (não "Core indisponível") | §10 (AC-22, AC-23) |

---

## 10. Achados e decisões desta especificação

### 10.1 Achados já existentes no inventário (confirmados)
- **AC-01**: Conversa e Agente somem na sessão de voz (confirmado no código; efeito em execução não visto). Tratado em §7.2.
- **AC-02**: "Modo: Base · sem LLM" era texto fixo. Substituído por H-04 (EXISTE).
- **AC-08**: "Cancelar" em vários lugares com efeitos diferentes. Tratado em §2.4 e Q-1.
- **AC-14**: propostas locais sem risco nem efeito. Tratado com N-1.
- **AC-16**: sem sinal de fallback. Tratado com N-6.
- **AC-18**: "PCM virtual" fixo no chip H-03.

### 10.2 Achados novos (verificados nesta leitura)
- **AC-19 (novo):** `core.result` devolve `command.code` **cru** quando não há recibo (`bridge.py:1805-1808`: `... else c.get('code','')`), e a tela mostra esse texto (`Main.qml:1565`). Contraria "nunca códigos crus" (`00-casca.md`). Correção: N-8.
- **AC-20 (novo):** o campo de comando de Hoje usa o caminho de texto de teste (`submitText`, `textAvailable` exige `--virtual-input`). Na instalação normal fica desabilitado. A proposta mantém o campo com o motivo escrito (§3.8) em vez de escondê-lo.
- **AC-21 (novo):** o Core não tem estado "pensando". "Pensando" é derivado de `chatState` e `agentState` (§2.2 prioridade 9).
- **AC-22 (novo):** `Main.qml:110` rotula `speaking` como "Respondendo". `UI_IA.md` e `UI_DESIGN.md` usam "Falando". Decisão: **"Falando"**.
- **AC-23 (novo):** `Main.qml:110` rotula `offline` como "Core indisponível". `UI_DESIGN.md` usa "Core desconectado" para a pílula. Decisão: **"Core desconectado"**.
- **AC-24 (novo):** a cor do recibo verificado em `Main.qml:1565` (`#78debc` / `#ffc674`) não é um dos tokens de `UI_DESIGN.md` (`#5ee0a0` / `#f2c15c`). Decisão: usar os tokens.
- **AC-25 (novo):** `Event` não tem horário (`src/protocol.rs`). Tratado com N-2 e Q-6.
- **AC-26 (novo):** `step`, `max_steps` e `started_ms_ago` do run não são expostos (`bridge.py:157`). Tratado com N-4.
- **AC-27 (novo):** `UI_IA.md` §1.4 pede "Orçamento (passos, tempo, tokens)". O tempo não existe na UI nem na ponte: tratado com N-4.
- **AC-28 (novo):** "Abortar" não tem confirmação (`Main.qml:1538`), mas cancela propostas pendentes (`docs/C3.md`). Tratado com Q-2.

### 10.3 Divergências com `UI_IA.md` (decisões desta spec)
- **D-1:** `UI_IA.md` §1.2 diz "Propostas de ferramenta inline". Mantido (CV-07). O cartão B de Hoje é uma **cópia de atalho** da mesma proposta (mesma decisão, sem duplicar a lógica).
- **D-2:** `UI_IA.md` §1.1 pede "Diga ou digite um comando" como campo. Mantido, com motivo explícito quando desabilitado (AC-20).
- **D-3:** `UI_IA.md` §1.2 diz que a sub-aba some sem plugin e Hoje mostra o chip. Mantido (§7.1). Durante a sessão de voz, ver §7.2 (alvo).
- **D-4:** `UI_IA.md` §1.4 cita "tempo" no orçamento do agente. Mantido como NOVO (N-4).
- **D-5:** `UI_IA.md` §1 lista "Erros" entre os filtros da Atividade. Mantido (§6.8).
- **D-6:** o HUD tem 7 estados pedidos. Acrescentei "Aguardando aprovação" (prioridade 10), que o Notion pede (`AwaitingConfirmation`), e "Core desconectado", "Modo seguro" e "Reinício necessário" (prioridades 1–3), que já existem em `Main.qml:110`.
- **D-7:** `00-casca.md` diz que o cabeçalho usa `x 32`. Adotei a coluna de conteúdo para o cabeçalho também (pendência P-1).

---

## 11. Pendências para validação humana

| # | Pendência | Motivo |
|---|---|---|
| P-1 | Cabeçalho na coluna do conteúdo (`x 140` em 1380 px) ou em `x 32` como em `00-casca.md` | Escolha visual; afeta todas as sub-abas |
| P-2 | AC-01 em execução: confirmar que Conversa e Agente somem durante a sessão de voz | Inferido do código |
| P-3 | Após reconectar, o Core mantém o run do agente? | Não verificado. Afeta §7.3 e AG-01 |
| P-4 | O snapshot limpa `transcript` ao fim da sessão? | Afeta H-25 (vazio) |
| P-5 | Confirmar texto do diálogo de "Abortar" com `docs/C3.md` | Q-2 |
| P-6 | Confirmar "Falando" e "Core desconectado" como rótulos | AC-22, AC-23 |
| P-7 | Anúncio de estado para leitor de tela em Qt (`Accessible.description` ou alerta) | Não verificado; precisa de teste com leitor |
| P-8 | Valor do anel do orbe por estado (decisão desta spec, sem token em `UI_DESIGN.md`) | Confirmar |
| P-9 | Frase do HUD em 28 px (decisão desta spec; `UI_DESIGN.md` não define tamanho) | Confirmar |
| P-10 | Sugestões de Conversa "Que horas são?" e "Abrir o Brave" (texto novo) | Confirmar que o Core responde a essas frases |
| P-11 | Texto "Ouvindo" no HUD usa "Fale agora." (decisão desta spec) | Confirmar |
| P-12 | Comportamento do botão Cancelar do cabeçalho com resposta do chat (Q-1) | Decisão de produto |

