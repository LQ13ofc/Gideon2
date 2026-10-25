# 30 · Permissões (aba de nível 1) — especificação de tela

Status: **proposta** para revisão do dono. Nada aqui está implementado. Idioma da interface: português do Brasil.
Janela de referência: 1380 × 904 px (mínimo 720 × 520). Casa visual e geometria: `docs/ui-spec/00-casca.md`.
Arquitetura de informação: `docs/UI_IA.md` §3 (versão atual: sub-abas **Visão geral · Concessões · Auditoria**).
Fundamento: `docs/UI_NOTION_REQS.md` (Permissions) e `docs/UI_INVENTORY.md` (AC-03, AC-04, AC-05, DU-10, NT-04).

Convenções desta spec:
- **NOVO (precisa de mudança na ponte/Core)**: exige código fora da QML. Cada item está listado na seção 11 com o que mudar.
- **(UI)**: muda só a QML, usando slots e propriedades que já existem na ponte.
- Coordenadas: px a partir do canto superior esquerdo da janela. Escala dos wireframes: 1 coluna = 10 px, 1 linha = 20 px (precisão ±20 px vertical). Os números à esquerda dos wireframes são o índice da linha (linha n = y n × 20 px) e não fazem parte da tela.
- "Nível" segue `docs/UI_IA.md` (Básico sempre; Avançado atrás de "Mostrar opções avançadas" em Configurações › Geral).

---

## 0. Escopo, sub-abas e decisões desta spec

A aba **Permissões** (3.ª posição: Assistente · Extensões · **Permissões** · Configurações · Diagnóstico) tem **três** sub-abas:

1. **Visão geral** — o que precisa da sua decisão agora e o que já está concedido.
2. **Concessões** — uma tabela única com tudo o que plugins, skills e contas podem usar. Filtro segmentado: Todas · Plugins · Skills · Conexões.
3. **Auditoria** — eventos recentes do Core, sem conteúdo.

Plugins, Skills e Conexões **não** são sub-abas aqui. Já existem em Extensões. Nesta aba são **origens** (linhas e filtros) da tabela Concessões.

Decisões tomadas nesta spec (cada uma tem motivo; o dono pode mudar):

| # | Decisão | Motivo |
|---|---|---|
| D1 | Aprovação de plugin é por **manifesto**, não por permissão: aprovar ou revogar vale para todas as permissões do plugin de uma vez. | É assim no Core (`hub::approve` e `hub::revoke_approval` em `src/hub.rs`, e `permissions_approved` por entrada). Uma linha por plugin, com as permissões listadas juntas. |
| D2 | O estado **"Revogada"** do IA não existe no snapshot. Depois de revogar, o plugin volta a **"Não aprovada"**. "Revogada" só aparece na Auditoria (evento `plugin_revoked`). | `permissions_approved` é só booleano. Revogada não se distingue de nunca aprovada. Contar revogadas exige NOVO (§11). |
| D3 | "Concedido recentemente" vira **"Concessões ativas"** até existir a data de concessão (NOVO §11.3). Sem data, a ordem é a do Core. | Obsoleto (WP8): a data de aprovação de plugin existe (`approved_at_ms` em `hub.entries`, `src/hub.rs`, usada em `app/shell/PermRows.js`) e a de conta existe (`granted_at_ms` em `connections`, usada em `CAccountCard.qml`). Falta só a data de revogação (`revoked_at`), que não existe no Core. |
| D4 | O contador de pendências conta **só** plugins instalados (ou com atualização) sem aprovação, contas com escopo aguardando consentimento e ferramentas MCP que precisam de confiança. Plugins não instalados e skills ficam de fora. | Plugin não instalado não bloqueia nada. Skill pendente depende do plugin dono: contar os dois duplicaria a mesma decisão (ver §8). |
| D5 | Propostas de ação do Assistente e do agente **não** entram no contador. | São decididas no Assistente (`UI_IA` §1.1 e §1.3), por ação, na hora. Contar aqui acenderia o badge em toda conversa. |
| D6 | Na Auditoria, eventos de propostas, passos e agente entram no filtro **Comando** (como ações pedidas por você). | O filtro da IA tem quatro origens: Plugin · Skill · Conexão · Comando. Não há quinta. |
| D7 | Durante a **sessão de voz** ficam bloqueadas as mudanças de **plugin** (aprovar, revogar). Contas e confiança MCP continuam. | Reproduz o bloqueio atual de `preferencesAvailable` (`app/bridge.py`, exige `not sessionId`). A causa do aviso errado da Conversa (AC-01) é outra e fica fora desta tela. |
| D8 | Revogar conta, confiar em ferramenta MCP e consentir escopos passam a ter **diálogo de confirmação** (D-P3, D-P4, D-P5). | AC-05: hoje `connectionRevoke` e `connectionRemove` não pedem confirmação. Esta aba é a central de grants e não pode ter ação destrutiva sem freio. |

Fora da aba (confira §13): instalar, ativar, desativar, remover plugin; provedor, chave e modelo LLM; remover conta e remover chave.

---

## 1. Aba nível 1 "Permissões" e contador

| Item | Especificação |
|---|---|
| Rótulo | `Permissões` |
| Ícone | escudo (Breeze), 18 px, à esquerda do rótulo |
| Posição | 3.ª aba da barra de abas (altura 40, padding horizontal 14, espaço 4) |
| Badge | ` •P` logo após o rótulo, só quando **P > 0** (ver §8). Ex.: `Permissões •2`. P > 99 mostra `•99+`. |
| Accessible.name | `Permissões, 2 pendências` (ou `Permissões` quando P = 0) |
| Atalho | Ctrl+3 |
| Condição de aparecimento | Sempre. A aba não depende de plugin nem de conta. |
| Sub-aba inicial | Visão geral |
| Sub-aba lembrada | Sim, na sessão de janela (volta à última sub-aba ao trocar de aba) |
| Nível | Básico |
| Core offline | Aba permanece; badge some (P = 0). Conteúdo mostra o banner descrito em §5.6, item 9, e §6.8. |

---

## 2. Fontes de dados

Todas as fontes são propriedades QML da ponte (`app/bridge.py`). Nada aqui lê arquivo direto.

| Dado | Propriedade QML | Origem | Campos usados |
|---|---|---|---|
| Entradas do catálogo (plugins e aprovação) | `core.hubEntries` (`bridge.py`, `hubEntries`) | snapshot `hub.entries` (`src/hub.rs`) | `plugin_id`, `semver`, `publisher`, `status` (`not_installed` · `installed` · `update_available` · `incompatible`), `reason` (`none` · `api_version` · `target` · `dependencies_unresolved`), `permissions` (lista de IDs), `permissions_approved` (bool), `manifest_sha256`, `license`, `payload_staged` |
| Plugins instalados | `core.hubInstalled` | snapshot `hub.installed` | `plugin_id`, `semver`, `state`, `runtime` |
| Estado de execução do plugin | `core.pluginItems` | snapshot `plugins.items` | `plugin_id`, `state` (`running` · `starting` · `failed` · `stopped` · `quarantined`), `enabled`, `last_error` |
| Revisão do catálogo (para aprovar) | `core.hubApprovalRevision` | `hub.approval_revision` | valor enviado em `approveHub` |
| Revisão dos plugins (para revogar) | `core.pluginsRevision` | `plugins.revision` | valor enviado em `revokePlugin` |
| Disponibilidade de aprovar | `core.hubApprovalAvailable` | derivado (`bridge.py`) | `preferencesAvailable` e hub `verified` |
| Disponibilidade de revogar | `core.pluginsAvailable` | derivado (`bridge.py`) | `hubLifecycleAvailable` e seção `plugins` presente |
| Skills | `core.skillsItems` | snapshot `skills.items` (`src/skills.rs`, `Item`) | `id`, `name`, `version`, `state`, `source`, `active`, `deps_ok`, `permissions_ok` (bool), `missing` (lista de dependências faltando) |
| Contas | `core.connectionsItems` (`bridge.py`, `connectionsItems`) | snapshot `connections.items` (`src/connections.rs`) | `id`, `provider`, `label`, `status`, `granted_scopes`, `pending_scopes` (opcional), `account_ref`, `fake` (opcional), `tools` (opcional, só MCP) |
| Revisão das contas | `core.connectionsRevision` | `connections.revision` | enviada em todas as operações de conta |
| Provedores, escopos e operações | `core.connectionsProviders` | snapshot `connections.providers` | `id`, `label`, `scopes[]` (`id`, `label`, `access`), `operations[]` (`name`, `scope`, `risk`) |
| Ferramentas MCP | `item.tools[]` das contas MCP | `connections.items[].tools` | `name`, `risk` (`write` · `destructive`), `state` (`trusted` · `needs_reapproval` · `rejected`), `description` (só texto, nunca instrução) |
| Rótulo de permissão | `core.permissionLabel(id)` | `display_permission` (`bridge.py`) | id desconhecido volta como veio (ver §3.1) |
| Texto de código de erro | `core.codeMessage(code)` | `code_message` (`bridge.py`) | códigos de conta, de Core e de skill |
| Resultado das aprovações | `core.hubApprovalResult` | ack do Core | texto mostrado em D-P1 |
| Resultado das contas | `core.connectionsResult`, `core.connectionsBusy` | ack do Core | toast e barra de progresso |
| Eventos (Auditoria) | **NOVO** `auditEvents` (ver §11.1) | snapshot `events` (anel de 64, `src/core.rs`) | `sequence`, `kind`, `request_id` (não exibido), `session_id` (não exibido) |
| Caminho do log (Avançado) | **NOVO** (§11.6) | caminho do diretório do Core | — |
| Sessão de voz | `core.sessionId` | snapshot `session_id` | vazio = sem sessão |
| Estado do Core | `core.connected` | `online` | — |

Regras gerais de fonte:
- Enquanto `core.connected` for falso: nenhuma ação é habilitada; P = 0; textos vêm do último snapshot, se existir.
- Toda ação chama um slot que **revalida** a revisão (`stale_*`). Revisão diferente = resultado `Estado mudou; reabra a confirmação` (texto existente `STALE_MESSAGE`). Nada é reenviado sem reabrir o diálogo.

---

## 3. Rótulos e textos de permissão (tabelas de referência)

Estas tabelas são a fonte dos textos exatos desta aba. Sempre que aparecer um ID de permissão ou escopo na tela, o texto visível é o **rótulo** daqui. O ID cru só aparece em Avançado.

### 3.1 Permissões de plugin (ID → rótulo)

Fonte do rótulo: `PERMISSION_LABELS` (`app/bridge.py`), via `core.permissionLabel`. Fonte do efeito: `src/world.rs` (`PERMISSIONS`, `SERVICES`), `src/llmcfg.rs` (IDs de rede e de configuração), `src/skills.rs` (`skills_author`).

| ID | Rótulo exibido | O que a permissão libera (Core, hoje) |
|---|---|---|
| `network_llm` | rede do motor LLM | rede brokerada do plugin LLM (`llmcfg.rs:14`) |
| `storage_settings` | armazenamento de configurações | guarda configuração do plugin LLM (`llmcfg.rs:16`; docs/C2.md) |
| `skills_author` | autoria de skills | plugin pode gerar rascunhos de skill, nunca habilitar (`skills.rs`, host services) |
| `screen_observe` | observação de tela | `screen.capture` (simulado nesta build) |
| `input_control` | controle de entrada | `input.a11y_tree`, `input.click`, `input.type`, `input.key`, `input.focus` (simulado) |
| `audio_route` | rota de áudio | `audio.routes`, `audio.set_route`, `audio.app_volume`, `audio.eq`, `audio.denoise`, `audio.state` (simulado) |
| `mic_config` | configuração do microfone | `mic.state`, `mic.configure`, `mic.monitor`, `mic.record_start`, `mic.record_stop` (simulado) |
| `camera_capture` | captura da câmera | `camera.state`, `camera.optin`, `camera.capture`, `camera.gestures` (simulado) |
| `display_manipulate` | ajuste de tela | **nenhum serviço do Core usa esta permissão hoje** (aparece no rótulo e em `docs/evidence/c4.json`). Ver §11.9. |
| qualquer outro ID | o ID como veio do Core, sem tradução, com o selo `não reconhecida` | manifesto de plugin pode declarar IDs fora desta lista (validação só checa formato) |

Textos das listas:
- Lista de permissões de um plugin: rótulos separados por `, ` (vírgula e espaço). Ex.: `rede do motor LLM, armazenamento de configurações`.
- Lista vazia: `nenhuma`.
- Mais de 2 permissões numa linha de Concessões: os 2 primeiros, depois `+N`. Ex.: `rede do motor LLM, armazenamento de configurações +1`.
- Selo para ID desconhecido: `não reconhecida` (Aviso, 12 px).

### 3.2 Escopos de conta (rótulo, acesso)

Fonte do rótulo: `label` em `core.connectionsProviders` (rótulos do Core, em `src/connections.rs`). Fonte do acesso: campo `access` do escopo.

| Provedor | ID do escopo | Rótulo exibido | Acesso |
|---|---|---|---|
| GitHub | `repo:read` | Ler repositórios e actions | leitura |
| GitHub | `issues:write` | Criar e editar issues | escrita |
| GitHub | `pulls:write` | Comentar pull requests | escrita |
| Google | `gmail.read` | Ler lista de e-mails (id, remetente, assunto) | leitura |
| Google | `gmail.send` | Enviar e-mail em seu nome | pública |
| Google | `gmail.delete` | Apagar e-mail | destrutiva |
| Google | `calendar.read` | Ler eventos da agenda | leitura |
| Google | `calendar.write` | Criar eventos na agenda | escrita |
| Google | `drive.read` | Listar arquivos do Drive | leitura |
| Google | `drive.write` | Criar arquivos no Drive | escrita |
| Home Assistant | `states.read` | Ler estados das entidades | leitura |
| Home Assistant | `services.call` | Chamar serviços (ligar, desligar, ajustar) | escrita |
| Home Assistant | `services.dangerous` | Serviços perigosos (fechaduras, alarme, portões) | destrutiva |
| MCP | `mcp.discover` | Listar as ferramentas do servidor MCP | leitura |
| MCP | `mcp.call` | Chamar ferramentas MCP (aprovação a cada chamada) | escrita |
| MCP | `mcp.call_destructive` | Ferramentas que apagam (aprovação a cada chamada) | destrutiva |

Observação: no Google, a conta pede todos os escopos e você concede cada um (`docs/S5.md` E2.2, comentário em `connections.rs`).

### 3.3 Operações de conta (nome → rótulo → escopo → risco)

Rótulo: função `connOpLabel` em `app/Main.qml` (texto da QML, mantido nesta spec). Escopo e risco: `connections.rs` (`*_OPERATIONS`), `effective_risk` (`connections.rs:3244`).

| Operação (nome do Core) | Rótulo | Escopo | Risco |
|---|---|---|---|
| `repos.list` | listar repositórios | `repo:read` | leitura |
| `repo.get` | ver repositório | `repo:read` | leitura |
| `issues.create` | criar issue | `issues:write` | escrita; **pública** se o repositório for público |
| `issues.update` | editar issue | `issues:write` | escrita |
| `pulls.get` | ver pull request | `repo:read` | leitura |
| `pulls.comment` | comentar pull request | `pulls:write` | pública |
| `actions.list` | listar actions | `repo:read` | leitura |
| `gmail.messages.list` | listar e-mails | `gmail.read` | leitura |
| `gmail.send` | enviar e-mail | `gmail.send` | pública |
| `gmail.messages.delete` | apagar e-mail | `gmail.delete` | destrutiva |
| `calendar.events.list` | listar eventos | `calendar.read` | leitura |
| `calendar.events.create` | criar evento | `calendar.write` | escrita |
| `drive.files.list` | listar arquivos | `drive.read` | leitura |
| `drive.files.create` | criar arquivo | `drive.write` | escrita |
| `states.list` | listar estados | `states.read` | leitura |
| `state.get` | ver estado | `states.read` | leitura |
| `service.call` | chamar serviço | `services.call` | escrita; **destrutiva** se o serviço for perigoso |
| `mcp.discover` | listar ferramentas | `mcp.discover` | leitura |
| `mcp.call` | chamar ferramenta (aprovação a cada chamada) | `mcp.call` | escrita; **destrutiva** se a ferramenta for destrutiva |

Nesta aba as operações **não** são listadas. Esta tabela serve de referência para o rótulo de risco que Extensões › Conexões mostra e para os textos de §3.4. D-P4 lista os **escopos** que serão retirados, não as operações.

### 3.4 Textos de acesso e de risco

| Valor do Core | Texto curto (coluna Acesso) | Texto longo (D-P3, Avançado) |
|---|---|---|
| `read` | leitura | leitura |
| `write` | escrita | escrita (pede aprovação) |
| `public` | pública | pública (aprovação explícita) |
| `destructive` | destrutiva | destrutiva (aprovação forte) |

Textos de ferramenta MCP (`connToolRiskText`, `connToolStateText` em `app/Main.qml`): risco `write` → `escrita (pede aprovação)`; `destructive` → `destrutiva (aprovação forte)`.

### 3.5 Textos de estado

Os textos abaixo são exatamente os que vão para a tela. Na **badge**, a primeira letra é maiúscula (`Aprovada`). Dentro de frases, minúscula.

| Entidade | Condição | Texto da badge | Cor |
|---|---|---|---|
| Plugin | `permissions_approved` verdadeiro, status `installed` ou `update_available` | `Aprovada` | Sucesso |
| Plugin | `permissions_approved` verdadeiro, status `not_installed` | `Aprovada · não instalado` | Sucesso |
| Plugin | `permissions_approved` falso, status `installed` ou `update_available` | `Pendente` | Aviso |
| Plugin | `permissions_approved` falso, status `not_installed` | `Não aprovada` | Neutro |
| Plugin | status `incompatible` | `Incompatível: <motivo>` | Erro |
| Plugin | motivo `api_version` | `versão de API não suportada` | (texto NOVO, §11.8) |
| Plugin | motivo `target` | `alvo não suportado nesta build` | (texto NOVO, §11.8) |
| Plugin | motivo `dependencies_unresolved` | `dependências não resolvidas` | (texto NOVO, §11.8) |
| Plugin (cabeçalho de D-P1) | status `installed` | `instalado (desativado)` ou `instalado · ativo (sandbox, sem rede)` se `enabled` | — |
| Plugin (cabeçalho de D-P1) | status `update_available` | `atualização disponível` | — |
| Plugin (cabeçalho de D-P1) | status `not_installed` | `não instalado` | — |
| Skill (permissão) | `permissions_ok` verdadeiro | `Permissões ok` | Sucesso |
| Skill (permissão) | `permissions_ok` falso | `Permissões pendentes` | Aviso |
| Skill (estado) | `state` | `Rascunho`, `Validada`, `Testada`, `Aprovada`, `Habilitada`, `Desabilitada`, `Revisada` | Neutro (Habilitada: Sucesso) |
| Conta (status) | `status` | `Desconectada`, `Conectando (aguardando confirmação)`, `Conectada`, `Expirada`, `Offline`, `Erro`, `Reautenticação necessária` | ver §6.5 |
| Escopo | no `granted_scopes` | `Concedido` | Sucesso |
| Escopo | no `pending_scopes` | `Aguardando consentimento` | Aviso |
| Escopo | em nenhum dos dois | `Não concedido` | Neutro |
| Ferramenta MCP | `state` `trusted` | `Confiável` | Sucesso |
| Ferramenta MCP | `state` `needs_reapproval` | `Precisa de nova aprovação` | Aviso |
| Ferramenta MCP | `state` `rejected` | `Recusada` | Erro |

Notas:
- `Conectando (aguardando confirmação)` é o texto da QML para o status `connecting`. `Reautenticação necessária` vem de `reauth_required`.
- Escopo com `pending_scopes` só existe com conta em `connecting` (o Core só guarda pendência nessa fase). Se aparecer em outro status, a linha mostra `Aguardando consentimento` mesmo assim.

---

## 4. Diálogos de decisão (compartilhados pelas três sub-abas)

Todos os diálogos são modais, centralizados, largura `min(440, janela − 32)`. Esc fecha. Ao fechar, o foco volta ao botão que abriu o diálogo. Confirmações têm **Cancelar** focado por padrão.

### 4.1 D-P1 · Revisar permissões de plugin (existente, texto corrigido)

Base: `hubReviewDialog` (`app/Main.qml`, bloco `reviewDialog`). Ao abrir, a QML chama `core.beginHubReview()` e guarda `core.hubApprovalRevision` (AC-04: texto novo usa rótulos).

Campos, na ordem de leitura:

| # | Campo | Tipo | Texto exato | Regra |
|---|---|---|---|---|
| 1 | Título da janela | título | `Revisar permissões` | fixo |
| 2 | Identificação | texto 14 px bold | `<plugin_id> <versão> · <publisher>` | `plugin_id`, `semver`, `publisher` do entry capturado |
| 3 | Estado do plugin | texto 12 px | `Estado do plugin: <texto da §3.5>` | ver §3.5, "cabeçalho de D-P1" |
| 4 | Título da lista | texto 14 px | `Permissões que este manifesto pede:` | fixo |
| 5 | Lista de permissões | uma linha por permissão, `• <rótulo>` | ex.: `• rede do motor LLM` | rótulo de §3.1. Avançado acrescenta ` (<id>)` em 12 px cinza |
| 5a | Lista vazia | texto | `Nenhuma permissão: aprovar não concede acesso a nada.` | quando `permissions` está vazio (botão de aprovar fica habilitado mesmo assim, para o Core registrar a aprovação do manifesto; se o Core recusar, o resultado diz o motivo) |
| 6 | Explicação fixa | texto 14 px | `Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto.` | fixo (texto existente) |
| 7 | Hash (só Avançado) | texto 12 px | `Manifesto: <primeiros 12 caracteres de manifest_sha256>…` | some em Básico |
| 8 | Confirmação do publisher | checkbox | `Entendo que o publisher não foi autenticado` | habilitado se `hubApprovalAvailable`. Desabilitado: dica `Indisponível durante a sessão de voz.` ou `Core desconectado.` |
| 9 | Aprovar | botão primário 40 px | `Aprovar estas permissões` | habilitado se `hubApprovalAvailable`, checkbox marcado e manifesto ainda não aprovado. Accessible.name: `Aprovar permissões de <plugin_id>`. Já aprovado: texto `Permissões aprovadas`, desabilitado |
| 10 | Resultado | texto 14 px, anunciado | `core.hubApprovalResult` | ex.: `Permissões aprovadas: <plugin_id>`; em revisão antiga: `Estado mudou; reabra a confirmação` |
| 11 | Fechar | botão padrão | `Fechar` | sempre habilitado |

Ação → resultado: **Aprovar estas permissões** envia `approveHub(plugin_id, manifest_sha256, permissions, reconhecido, revisão)` (`bridge.py`, `approveHub`) → Core grava a aprovação do manifesto → a linha vira `Aprovada` (ou `Aprovada · não instalado`). **Não instala e não ativa**: a ativação continua em Extensões › Plugins.

Dica de foco: ao abrir, o foco vai para o checkbox (campo 8).

### 4.2 D-P2 · Revogar permissões de plugin (existente, sem mudança de texto)

Base: `revokeConfirm` (`app/Main.qml`, `D6` em `docs/UI_INVENTORY.md`).

| Campo | Texto exato |
|---|---|
| Título | `Revogar permissões` |
| Texto | `Revogar permissões de <plugin_id>? O plugin será desativado e o processo encerrado. Reativar exige nova aprovação.` |
| Botão 1 (foco inicial) | `Cancelar` |
| Botão 2 (perigo) | `Revogar` · Accessible.name: `Revogar permissões de <plugin_id>` |

Ação → resultado: **Revogar** chama `revokePlugin(plugin_id, revisão_dos_plugins)` (`bridge.py`, `revokePlugin`) → Core remove todas as aprovações do plugin, para o processo e desativa o plugin (`src/plugins.rs`, `revoke`) → resultado `Permissões revogadas; plugin desativado` (texto de `OPS`) → linha vira `Não aprovada`.

Desabilitado quando: `pluginsAvailable` falso (tooltip: `Indisponível durante a sessão de voz.` ou `Core desconectado.`), ou estado `quarantined` (tooltip: `Plugin em quarentena: não pode mudar de estado.`).

### 4.3 D-P3 · Consentir escopos de conta (NOVO na aba, usa slot existente)

Base de dados: `connectionConsent(id, JSON dos escopos marcados)` (`bridge.py`). A ponte recusa escopo fora de `pending_scopes`.

| # | Campo | Tipo | Texto exato | Regra |
|---|---|---|---|---|
| 1 | Título | título | `Consentir escopos` | fixo |
| 2 | Identificação | texto 14 px bold | `<label> · <provedor>` | ex.: `Casa · Home Assistant` |
| 3 | Explicação | texto 14 px | `Escolha os escopos que esta conta pode usar. Nada é concedido sem sua marcação.` | fixo |
| 4 | Uma caixa por escopo pendente | checkbox + badge de acesso | `<rótulo> (<id>)` + badge `leitura` / `escrita` / `pública` / `destrutiva` | desmarcadas por padrão. `(<id>)` só em Avançado. Ordem: a do Core |
| 5 | Aviso de risco | texto 12 px Aviso | se houver escopo `public` ou `destructive` marcado: `Escopo <acesso>: cada chamada pode pedir aprovação forte.` | aparece só com esse escopo marcado |
| 6 | Consentir | botão primário | `Consentir escopos marcados` | habilitado com ≥ 1 marcado. Sem marcação, dica `Marque ao menos um escopo.` |
| 7 | Cancelar | botão (foco inicial) | `Cancelar` | — |
| 8 | Resultado | texto | `Escopos concedidos pelo usuário` (ou o código traduzido por `codeMessage`) | — |

Ação → resultado: envia só os marcados. Core grava os escopos. A linha passa a `Concedido` e some do estado `Aguardando consentimento`.

### 4.4 D-P4 · Revogar acesso da conta (NOVO na aba; confirmação ausente hoje, AC-05)

Base de dados: `connectionRevoke(id)` (`bridge.py`, `connection_revoke`).

| Campo | Texto exato |
|---|---|
| Título | `Revogar acesso` |
| Texto | `Revogar o acesso da conta <label> no servidor? Os segredos locais são apagados, todos os escopos concedidos são retirados e as ferramentas MCP precisam de nova confiança. Para usar a conta de novo, conecte e consinta outra vez.` |
| Lista de escopos afetados (12 px) | `Escopos que serão retirados: <rótulos dos concedidos>.` |
| Botão 1 (foco inicial) | `Cancelar` |
| Botão 2 (perigo) | `Revogar acesso` · Accessible.name: `Revogar acesso da conta <label>` |

Ação → resultado: Core revoga no servidor, apaga segredos e grava status `Desconectada`, sem escopos (`src/connections.rs`, `revoke`). Resultado `Acesso revogado no servidor`. Se o servidor falhar, o resultado é o código traduzido (ex.: `Servidor do provedor inacessível neste ambiente`).

Desabilitado quando a conta não está em `connected`, `expired` ou `reauth_required` (mesmo critério de `connCan("revoke")`). Tooltip: `Conta sem acesso concedido para revogar.`

### 4.5 D-P5 · Confiar em ferramenta MCP (NOVO na aba; confirmação)

Base de dados: `connectionTrustTools(id, [nome])` (`bridge.py`). Aceita só ferramentas em `needs_reapproval`.

| Campo | Texto exato |
|---|---|
| Título | `Confiar na ferramenta` |
| Texto | `Confiar em <nome> do servidor <label>? Cada chamada desta ferramenta ainda pede sua aprovação. A descrição vem do servidor e é só texto.` |
| Botão 1 (foco inicial) | `Cancelar` |
| Botão 2 | `Confiar` · Accessible.name: `Confiar na ferramenta <nome>` |

Ação → resultado: Core marca a ferramenta como `trusted`. Resultado `Ferramentas confiadas pelo usuário; cada chamada ainda pede aprovação`. A linha some da fila.

---

## 5. Sub-aba "Visão geral"

### 5.1 Objetivo
Responder em uma tela: **o que precisa de mim agora** e **o que já está concedido**. Esta é a sub-aba que a aba abre por padrão.

### 5.2 Condição, nível
- Condição: sempre visível.
- Nível: **Básico**. Os textos avançados (IDs, hash, caminho) não existem nesta sub-aba, só nos diálogos.

### 5.3 Layout em grade

Cabeçalho e faixa de resumo seguem a casca (x 32 até 1348). O conteúdo usa a coluna de 1100 px centralizada (x 140 até 1240), grade de 12 colunas e gap 16, conforme `docs/ui-spec/00-casca.md`.

| Região | x | y | largura | altura | Conteúdo |
|---|---|---|---|---|---|
| Barra de abas | 0 | 0 | 1380 | 56 | casca |
| Sub-abas | 0 | 56 | 1380 | 44 | casca: `Visão geral` (ativa), `Concessões`, `Auditoria` |
| Cabeçalho | 32 | 116 | 1316 | 60 | título em y 116 (24 px bold); subtítulo em y 150 (14 px); botão primário à direita, x 1188–1348, y 124–164 |
| Faixa de resumo | 32 | 184 | 1316 | 40 | texto de resumo (14 px bold) à esquerda; badge de aviso à direita |
| Card Pendências | 140 | 236 | 1100 | 300 | cabeçalho de 44 px + até 4 linhas de 56 px; rola se houver mais |
| Card Concessões ativas | 140 | 552 | 1100 | 230 | cabeçalho de 44 px + até 5 linhas de 32 px + link de 20 px |
| Bloco Como funciona | 140 | 798 | 1100 | 56 | recolhido; aberto cresce para baixo dentro da área de rolagem |

Área de rolagem vertical: y 236 a 880.

### 5.4 Fila de pendências (ordem e regra)

A fila mostra **todos** os itens que compõem P (§8), nesta ordem:
1. Plugins pendentes, por `plugin_id` (ordem alfabética, pt-BR).
2. Contas com escopo pendente, por `label` (ordem alfabética, pt-BR).
3. Contas MCP com ferramenta em `needs_reapproval`, por `label`; dentro da conta, por nome da ferramenta.

**Revisar próxima** (botão primário do cabeçalho) abre o diálogo do **primeiro** item da fila: D-P1 para plugin, D-P3 para conta com escopo pendente, D-P5 para ferramenta MCP. Se o primeiro item não puder ser aberto agora (ex.: plugin durante sessão de voz), o botão fica desabilitado com a dica desse motivo.

Um plugin com `status update_available` e aprovação antiga mostra, na linha, a terceira linha de texto (ver §5.5, item 11).

### 5.5 Wireframe (escala 10 px × 20 px)

```
 0  ◉ Gideon   [Assistente] [Extensões] [Permissões •2] [Configurações] [Diagnóstico]                               ● Em espera   [Cancelar]
 1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 3     [Visão geral]   Concessões   Auditoria
 4 ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 6     Visão geral                                                                                                       [Revisar próxima]
 7     O que precisa da sua decisão agora e o que já está concedido.
10     2 aprovadas · 2 pendentes
12               ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
13               │ Pendências · 2 aguardando sua decisão                                                                      │
14               │                                                                                                            │
15               │ [Plugin]   gideon.camera 0.1.0 · publisher não autenticado                                                 │
16               │            Pede: captura da câmera                                                               [Revisar] │
17               │                                                                                                            │
18               │ [Conexão]  Casa (Home Assistant) · aguardando consentimento: 1 escopo                                      │
19               │                                                                                                            │
20               │                                                                                                  [Revisar] │
21               │                                                                                                            │
22               │                                                                                                            │
23               │                                                                                                            │
24               │                                                                                                            │
25               │                                                                                                            │
26               └────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
27               ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
28               │ Concessões ativas                                                                                          │
29               │                                                                                                            │
30               │ [Plugin]   gideon.llm_engine 0.2.0 · rede do motor LLM, armazenamento de config.  Aprovada           Ver › │
31               │ [Conexão]  Casa · Home Assistant · 1 escopo concedido                              Concedido               │
32               │                                                                                                      Ver › │
33               │ Ver todas em Concessões ›                                                                                  │
34               │                                                                                                            │
35               │                                                                                                            │
36               │                                                                                                            │
37               │                                                                                                            │
38               │                                                                                                            │
39               └────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
40               ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
41               │ ▸ Como funciona                                                                                            │
42               └────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Nota: o exemplo tem 2 aprovadas e 2 pendentes, e o badge da aba mostra `•2` (= P). Na linha 16 o botão `Revisar` é da linha do plugin; na linha 20, da conta.

### 5.6 Elementos (tabela)

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| 1 | Barra de abas, 3.ª posição | aba nível 1 + badge | `Permissões` + ` •P` se P > 0 | contador (§8) | clique ou Ctrl+3 abre a aba | normal; ativa (fundo acento 18 %, barra 3 px); sem badge com P = 0 | Básico |
| 2 | Sub-abas, y 56–100 | sub-aba (texto) | `Visão geral` | fixa | — | ativa: branco bold + sublinhado 2 px | Básico |
| 3 | Sub-abas | sub-aba | `Concessões` | fixa | troca de sub-aba; preserva o filtro | inativa | Básico |
| 4 | Sub-abas | sub-aba | `Auditoria` | fixa | troca de sub-aba | inativa | Básico |
| 5 | Cabeçalho, x 32, y 116 | título 24 px bold | `Visão geral` | fixa | — | — | Básico |
| 6 | Cabeçalho, x 32, y 150 | subtítulo 14 px #9db0e0 | `O que precisa da sua decisão agora e o que já está concedido.` | fixa | — | — | Básico |
| 7 | Cabeçalho, x 1188–1348, y 124–164 | botão primário 40 px | `Revisar próxima` | fila (§5.4) | abre o diálogo do primeiro item | habilitado se P > 0 e o primeiro item puder abrir; senão desabilitado com dica (`Nada pendente.` ou o motivo) | Básico |
| 8 | Faixa de resumo, x 32, y 184 | texto 14 px bold | `{A} aprovada(s) · {P} pendente(s)` | A e P (§8) | — | plural: `1 aprovada`, `2 aprovadas`, `1 pendente`, `2 pendentes`; A = P = 0: `Nenhuma permissão aprovada ou pendente.` | Básico |
| 9 | Faixa de resumo, à direita | badge | `Core desconectado` (Erro) · `Sessão de voz ativa: mudanças em plugins bloqueadas` (Aviso) | `core.connected`, `core.sessionId` | — | só nesses dois casos (podem aparecer juntos) | Básico |
| 10 | Card Pendências, x 140, y 236 | cartão | `Pendências · {P} aguardando sua decisão`; com P = 0: `Pendências` | fila | — | — | Básico |
| 11 | Linha de plugin (56 px) | badge + 2 ou 3 linhas + botão | badge `Plugin` (Info) · linha 1: `<plugin_id> <versão> · publisher não autenticado` · linha 2 (12 px): `Pede: <rótulos>` · linha 3 (12 px, Aviso, só se `update_available`): `Atualização: a aprovação anterior não vale para esta versão.` · botão secundário `Revisar` | `hubEntries` com `permissions` não vazio, `permissions_approved` falso e status `installed` ou `update_available` | `Revisar` abre D-P1 | itens de P (§8) | Básico |
| 12 | Linha de conta com escopo pendente | badge + texto + botão | badge `Conexão` (Neutro) · linha 1: `<label> · <provedor>` · linha 2: `aguardando consentimento: <n> escopo(s)` · `Revisar` | `connectionsItems` com `pending_scopes` | `Revisar` abre D-P3 | — | Básico |
| 13 | Linha de ferramenta MCP | badge + texto + botão | badge `Conexão` · linha 1: `<label> · MCP` · linha 2: `Ferramenta <nome>: precisa de nova aprovação` · `Revisar` | `tools[]` com `state` `needs_reapproval` | `Revisar` abre D-P5 | — | Básico |
| 14 | Estado vazio do card Pendências (P = 0) | estado vazio, altura 160 | `Nada pendente.` (14 px bold) / `Plugins, skills e contas aparecem aqui quando precisarem da sua decisão.` (12 px) | — | — | só com P = 0; ícone escudo 32 px | Básico |
| 15 | Card Concessões ativas, x 140, y 552 | cartão | `Concessões ativas` (vira `Concedido recentemente` com NOVO §11.3) | concessões (§8) | — | — | Básico |
| 16 | Linha de plugin aprovado (32 px) | badge + texto + estado + link | badge `Plugin` · `<plugin_id> <versão> · <rótulos>` · `Aprovada` · `Ver ›` | `hubEntries` com `permissions_approved` verdadeiro | `Ver ›` abre Concessões com filtro Plugins e a linha selecionada | — | Básico |
| 17 | Linha de conta com escopo concedido (32 px) | badge + texto + estado + link | badge `Conexão` · `<label> · <provedor> · <n> escopo(s) concedido(s)` · `Concedido` · `Ver ›` | `connectionsItems` com `granted_scopes` não vazio | `Ver ›` abre Concessões com filtro Conexões | — | Básico |
| 18 | Link de rodapé do card (20 px) | link 14 px #9db0e0 | `Ver todas em Concessões ›` | fixa | abre Concessões, filtro Todas | aparece sempre | Básico |
| 19 | Estado vazio do card Concessões (sem aprovação nem escopo concedido) | estado vazio, altura 160 | `Nenhuma permissão concedida ainda.` / `Aprove um plugin ou consinta escopos de uma conta para vê-los aqui.` | — | — | — | Básico |
| 20 | Bloco Como funciona, y 798 | bloco recolhível (56 px) | `Como funciona` com `▸` (recolhido) / `▾` (aberto) | — | clique alterna | recolhido por padrão | Básico |
| 21 | Texto aberto de Como funciona (14 px) | texto | `Permissões são decisões suas. Aprovar não instala nem executa nada. Revogar desativa o plugin e encerra o processo. Skills não concedem permissão: usam capacidades de plugins já aprovados. Contas só usam os escopos que você consentiu.` | fixa | — | aberto | Básico |

### 5.7 Ordenação, agrupamento, filtros
- Sem filtros nesta sub-aba.
- Ordem dos cards: Pendências, Concessões ativas, Como funciona (fixa).
- Ordem das linhas em Pendências: §5.4. Em Concessões ativas: plugins por `plugin_id`, depois contas por `label`.

### 5.8 Estados

| Estado | Como aparece |
|---|---|
| Normal (P > 0 e A > 0) | cards com linhas; botão primário habilitado |
| Sem pendência (P = 0) | item 14 no card Pendências; badge da aba some; botão primário desabilitado com dica `Nada pendente.` |
| Sem concessão (A = 0) | item 19 no card Concessões |
| Sessão de voz | item 9 (Aviso). Revisar de plugin desabilitado com dica `Indisponível durante a sessão de voz.`; Revisar de conta funciona |
| Core offline | item 9 (Erro `Core desconectado`); todos os botões desabilitados com dica `Core desconectado.`; se não houver último snapshot: card Pendências mostra `Core desconectado. Conecte o Core para ver as permissões.` |
| Configuração em modo seguro ou reinício pendente | Aviso (texto fixo): `Configuração em modo seguro ou aguardando reinício: mudanças em plugins estão bloqueadas.` Mesma regra de `preferencesAvailable` |
| Operação em andamento (`connectionsBusy`) | botões de conta desabilitados; barra de progresso indeterminada no topo do card afetado |

---

## 6. Sub-aba "Concessões"

### 6.1 Objetivo
Uma tabela única com **tudo que está concedido ou pedindo decisão**, de qualquer origem: plugin, skill ou conta. Permite ver, filtrar e agir sem trocar de tela.

### 6.2 Condição, nível
- Condição: sempre visível. Lista vazia mostra o estado vazio (§6.8).
- Nível: **Básico** (rótulos, estados, Revisar, Revogar, Consentir, Confiar, Ver em Skills). **Avançado** (atrás de "Mostrar opções avançadas"): ID da permissão ou do escopo na segunda linha da célula, hash do manifesto, e o ID da ferramenta MCP.

### 6.3 Layout em grade

| Região | x | y | largura | altura | Conteúdo |
|---|---|---|---|---|---|
| Cabeçalho | 32 | 116 | 1316 | 60 | `Concessões`; subtítulo; **sem** botão primário (concessão nasce em Revisar, nunca numa tela de criação) |
| Faixa de resumo | 32 | 184 | 1316 | 40 | `{A} aprovadas · {P} pendentes` (mesma regra de §5.6 item 8) |
| Filtro segmentado | 140 | 236 | 420 | 40 | `Todas` · `Plugins` · `Skills` · `Conexões` |
| Contagem | 560 | 236 | 420 | 40 | `{n} itens · {P} pendentes` (texto à direita, 14 px) |
| Agrupar por | 1040 | 236 | 200 | 40 | combo: `Agrupar por: Origem` / `Agrupar por: Item` |
| Cabeçalho da tabela | 140 | 284 | 1100 | 32 | colunas abaixo, texto 12 px semibold #9db0e0 |
| Corpo da tabela | 140 | 316 | 1100 | 564 | linhas de 52 px (14 px + 12 px); rola |

Colunas (x a partir de 140):

| Coluna | Largura | x inicial | Conteúdo |
|---|---|---|---|
| Nº | 40 | 140 | posição na lista (leitor de tela e referência) |
| Origem | 120 | 180 | badge `Plugin` (Info) · `Skill` (Neutro) · `Conexão` (Neutro) |
| Item | 280 | 300 | linha 1 (14 px): `<plugin_id> <versão>` · `<nome> v<versão>` · `<label>`. Linha 2 (12 px): `<provedor>` para conta; `SERVIDOR FALSO` (selo Aviso) se `fake` |
| Permissão ou escopo | 280 | 580 | conforme a origem (§6.5): rótulo(s) de permissão de plugin, rótulo de escopo de conta ou ferramenta MCP. Linha 2 (Avançado): ID |
| Acesso | 110 | 860 | só para conta e MCP: `leitura` · `escrita` · `pública` · `destrutiva`; para plugin e skill: `—` |
| Estado | 150 | 970 | badge (§3.5) |
| Ação | 120 | 1120 | botão secundário ou perigo (§6.6). Sem ação: texto 12 px cinza |

### 6.4 Wireframe (escala 10 px × 20 px)

```
 0  ◉ Gideon   [Assistente] [Extensões] [Permissões •2] [Configurações] [Diagnóstico]                               ● Em espera   [Cancelar]
 1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 3     Visão geral   [Concessões]   Auditoria
 4 ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 6     Concessões
 7     Tudo o que plugins, skills e contas podem usar, com a sua decisão.
10     2 aprovadas · 2 pendentes
12               (Todas)   Plugins   Skills   Conexões                             5 itens · 2 pendentes      Agrupar por: [Origem ▾]
14               #    Origem     Item                       Permissão ou escopo           Acesso    Estado                Ação
16               1    Plugin     gideon.llm_engine 0.2.0    rede do motor LLM, armaz…     —         Aprovada              [Revogar]
17               ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
18               2    Plugin     gideon.camera 0.1.0        captura da câmera             —         Pendente              [Revisar]
19               ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
20               3    Skill      lista_compras v1.0.0       2 capacidades, 1 ok           —         Testada · ok          [Ver Skills]
21               ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
22               4    Conexão    Casa · Home Assistant      Ler estados das entidades     leitura   Concedido             [Revogar conta]
23               ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
24               5    Conexão    Casa · Home Assistant      Chamar serviços               escrita   Aguardando            [Consentir]
25               ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
```

Nota: "2 capacidades, 1 ok" depende de NOVO §11.4 (hoje a ponte só diz `permissions_ok` sim/não). Sem NOVO, a célula mostra `Permissões pendentes` ou `Permissões ok`, e a lista de faltantes em `missing`.

### 6.5 Linhas por origem

A tabela tem **uma linha por plugin** (D1), **uma linha por skill**, **uma linha por escopo** de conta e **uma linha por ferramenta MCP** que precisa de confiança.

**A. Plugin** (origem `Plugin`)

| Campo | Regra |
|---|---|
| Item | `<plugin_id> <semver>` |
| Permissão ou escopo | rótulos de §3.1, separados por `, ` (regra de `+N`) |
| Acesso | `—` |
| Estado | `Aprovada` (Sucesso) · `Pendente` (Aviso) · `Não aprovada` (Neutro) · `Aprovada · não instalado` (Sucesso) · `Incompatível: <motivo>` (Erro). Ver §3.5 |
| Ação | `Aprovada` → `Revogar` (D-P2). `Pendente` ou `Não aprovada` → `Revisar` (D-P1). `Incompatível` → texto `Sem ação: versão incompatível.` |

Plugin sem permissão declarada (`permissions` vazio) **não aparece** nesta tabela.

**B. Skill** (origem `Skill`)

| Campo | Regra |
|---|---|
| Item | `<name> v<version>` (linha 1); `<id>` (linha 2, Avançado) |
| Permissão ou escopo | `Permissões ok` (Sucesso) ou `Permissões pendentes` (Aviso) + `Faltando: <missing>` se houver dependência faltando (texto 12 px). Com NOVO §11.4: `<n> capacidades, <k> ok` |
| Acesso | `—` |
| Estado | `<state>` capitalizado (§3.5). `Permissões ok` ou `pendentes` vai à coluna da permissão |
| Ação | `Ver em Skills` (abre Extensões › Skills). Com NOVO §11.4 e dono pendente: `Revisar` abre D-P1 do plugin dono |

Skill **não tem botão de revogar**: a permissão de skill vem do plugin dono (`skills.rs`, `owner_approved`). Revogar é feito no plugin.

**C. Escopo de conta** (origem `Conexão`). Uma linha por escopo de `granted_scopes` ou `pending_scopes`.

| Campo | Regra |
|---|---|
| Item | `<label> · <provedor>` (linha 1); `SERVIDOR FALSO` (selo Aviso, linha 2) se `fake` |
| Permissão ou escopo | rótulo do escopo (§3.2). Avançado: ID |
| Acesso | `leitura` · `escrita` · `pública` · `destrutiva` (§3.4) |
| Estado | `Concedido` (Sucesso) · `Aguardando consentimento` (Aviso) · `Não concedido` (Neutro, quando o escopo não está em nenhum dos dois). Linha 2 (12 px): status da conta (§6.5.1) |
| Ação | `Concedido` → `Revogar conta` (D-P4). `Aguardando consentimento` → `Consentir` (D-P3). `Não concedido` → sem ação |

Revogar conta é **por conta**, não por escopo: o Core tem revogação por escopo desde o WP8 (§11.7 implementado: `connection_revoke_scope`), mas esta spec mantém "Revogar conta" como ação principal. Por isso o botão aparece em todas as linhas concedidas da conta; D-P4 lista todos os escopos que serão retirados.

**D. Ferramenta MCP** (origem `Conexão`). Uma linha por ferramenta em `needs_reapproval` **e** por ferramenta `trusted` (para visibilidade).

| Campo | Regra |
|---|---|
| Item | `<label> · MCP` |
| Permissão ou escopo | `Ferramenta <nome>` (Avançado: risco exato em §3.4) |
| Acesso | `escrita` ou `destrutiva` (§3.4) |
| Estado | `Confiável` (Sucesso) · `Precisa de nova aprovação` (Aviso) · `Recusada` (Erro) |
| Ação | `Precisa de nova aprovação` → `Confiar` (D-P5). `Confiável` → sem ação, texto `Cada chamada ainda pede aprovação.` `Recusada` → sem ação, texto `Recusada pelo Core: nada a fazer.` |

#### 6.5.1 Status da conta (linha 2 de C)

Mesmos textos de `connStatusText` em `app/Main.qml`: `Desconectada` · `Conectando (aguardando confirmação)` · `Conectada` · `Expirada` · `Offline` · `Erro` · `Reautenticação necessária`.

### 6.6 Ações → resultado (resumo; detalhes em §4)

| Ação | Diálogo | Chamada (bridge.py) | Resultado na tela |
|---|---|---|---|
| Revisar (plugin) | D-P1 | `approveHub` | linha vira `Aprovada` (ou `Aprovada · não instalado`) |
| Revogar (plugin) | D-P2 | `revokePlugin` | linha vira `Não aprovada` |
| Consentir (escopo) | D-P3 | `connectionConsent` | linha vira `Concedido` |
| Revogar conta (escopo concedido) | D-P4 | `connectionRevoke` | todas as linhas da conta viram `Não concedido` e a conta fica `Desconectada` |
| Confiar (ferramenta MCP) | D-P5 | `connectionTrustTools` | linha vira `Confiável` |
| Ver em Skills | sem diálogo | navegação | abre Extensões › Skills (sem alterar nada) |

### 6.7 Filtros, ordenação e agrupamento

- **Filtro segmentado** (padrão `Todas`): `Todas` · `Plugins` (só origem Plugin) · `Skills` (só origem Skill) · `Conexões` (só origem Conexão). O filtro é mantido ao trocar de sub-aba e ao voltar (sessão de janela).
- **Ordenação** (padrão, sem escolha do usuário): (1) estado de pendência primeiro: `Pendente`, `Aguardando consentimento`, `Precisa de nova aprovação`; depois `Não aprovada`, `Não concedido`, `Permissões pendentes`; depois `Aprovada`, `Concedido`, `Permissões ok`, `Confiável`, `Testada` etc.; (2) origem: Plugin, Skill, Conexão; (3) Item em ordem alfabética pt-BR; (4) rótulo da permissão ou escopo, pt-BR.
- **Agrupar por: Origem** (padrão): cabeçalhos de grupo `Plugins · n`, `Skills · n`, `Conexões · n`, na ordem Plugin, Skill, Conexão. Cada grupo mantém a ordenação acima.
- **Agrupar por: Item**: cabeçalho de grupo com o item (`<plugin_id> <semver>` · `<label> · <provedor>` · `<nome> v<versão>`) e, à direita do cabeçalho, `{n} linhas · {P} pendente(s)`. Itens em ordem: pendentes primeiro, depois alfabética.
- Sem busca nesta versão.

### 6.8 Estados

| Estado | Texto | Ação |
|---|---|---|
| Tudo vazio (nenhum plugin com permissão, nenhuma skill, nenhuma conta) | `Nenhum plugin, skill ou conta pede permissão ainda.` / `Instale ou conecte em Extensões para ver as permissões aqui.` | botão secundário `Abrir Extensões` |
| Filtro vazio | `Nenhum item em <Plugins|Skills|Conexões> aqui.` | — |
| Core offline | banner (Erro): `Core desconectado. Mostrando o último estado conhecido; nada pode ser alterado.` (ou `Conecte o Core para ver as permissões.` sem snapshot) | todos os botões desabilitados |
| Sessão de voz | banner (Aviso) do item 9 (§5.6) | `Revisar` e `Revogar` de plugin desabilitados (dica `Indisponível durante a sessão de voz.`) |
| Operação de conta em andamento | barra indeterminada acima da tabela | botões de conta desabilitados |
| Estado mudou (revisão) | resultado no diálogo: `Estado mudou; reabra a confirmação` | reabrir |

---

## 7. Sub-aba "Auditoria"

### 7.1 Objetivo
Mostrar, em ordem cronológica inversa, o que o **Core** fez nesta sessão que tenha a ver com permissões, plugins, skills, contas e comandos, **sem nenhum conteúdo** (nem texto de fala, nem argumento, nem resposta de servidor, nem token).

### 7.2 Condição, nível
- Condição: sempre visível.
- Nível: **Básico** para Tipo, Origem, Resultado e Nº. **Avançado** (`▸ Detalhes técnicos`, visível só com "Mostrar opções avançadas" ligado em Configurações › Geral): caminho do log (NOVO §11.6) e código de resultado quando existir.

### 7.3 Layout em grade

| Região | x | y | largura | altura | Conteúdo |
|---|---|---|---|---|---|
| Cabeçalho | 32 | 116 | 1316 | 60 | `Auditoria`; subtítulo; sem botão primário |
| Faixa de resumo | 32 | 184 | 1316 | 40 | `{n} eventos nesta sessão` |
| Chips de origem | 140 | 236 | 480 | 40 | `Todos` · `Plugin` · `Skill` · `Conexão` · `Comando` |
| Cabeçalho da tabela | 140 | 284 | 1100 | 32 | `Nº` · `Tipo` · `Origem` · `Resultado` |
| Corpo | 140 | 316 | 1100 | 500 | linhas de 44 px; rola; até 64 linhas |
| Detalhes técnicos (Avançado) | 140 | 840 | 1100 | 40 | recolhido por padrão |

Colunas: Nº 80 (x 140–220) · Tipo 620 (x 220–840) · Origem 160 (x 840–1000) · Resultado 240 (x 1000–1240).

### 7.4 Wireframe (escala 10 px × 20 px)

```
 0  ◉ Gideon   [Assistente] [Extensões] [Permissões •2] [Configurações] [Diagnóstico]                               ● Em espera   [Cancelar]
 1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 3     Visão geral   Concessões   [Auditoria]
 4 ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 6     Auditoria
 7     Eventos recentes do Core, sem conteúdo. Até 64, desde o início desta sessão do Core.
10     5 eventos nesta sessão
12               (Todos)   Plugin   Skill   Conexão   Comando
14               Nº     Tipo                                                    Origem     Resultado
16               #48    Acesso revogado no servidor; segredos apagados          Conexão    Concluído
17               ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
18               #47    Chamada de operação de conta                            Conexão    —
19               ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
20               #46    Permissões de plugin aprovadas                          Plugin     Concluído
21               ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
22               #45    Ação proposta, aguardando sua decisão                   Comando    —
23               ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
24               #44    Passo de skill registrado                               Skill      —
25               ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
40               ▸ Detalhes técnicos (Avançado): caminho do log (NOVO, seção 11)
```

Nota: o exemplo mostra 5 de 64 linhas possíveis. Linha 40 = detalhes técnicos, recolhidos.

### 7.5 Como a Auditoria é montada

Fonte: o **anel de eventos do Core** (`src/core.rs`, `emit`; tamanho 64, `core.rs:785-786`). Cada evento tem `sequence`, `kind`, `request_id` e `session_id`. Só `sequence` e `kind` são usados. `request_id` e `session_id` **não são mostrados**, nem em Avançado.

Regras:
1. Entrada: a lista do snapshot `events` (NOVO §11.1). A ordem é por `sequence` decrescente (mais novo primeiro).
2. Tipo: o texto vem da **tabela tipo → frase (§7.6)**, pela chave `kind`. Se `kind` tiver sufixo após `:` (ex.: `agent_blocked:loop_blocked`), usa a parte antes do `:` e o sufixo conforme a própria tabela.
3. Origem: pela coluna Origem da tabela. Filtros usam essa coluna.
4. Resultado: pela coluna Resultado da tabela (`Concluído` · `Falhou` · `Negado` · `Recusado` · `—`). `—` significa "não há resultado no evento"; não quer dizer que deu certo.
5. `kind` **não catalogado**: aparece como `Evento do Core sem descrição` (Neutro), origem `Core`. Só aparece com filtro `Todos`. Isso mostra que a tabela ficou para trás, sem vazar o nome cru.
6. Nº = `sequence`. Não há hora: o evento não tem data (ver §11.2).
7. Limite: o anel guarda 64; quando cheio, o evento mais antigo sai. A lista começa vazia a cada início do Core.

Por que nada de conteúdo vaza: o evento não tem campo de conteúdo. O texto de fala, de comando, de argumento e de resposta de conta **não está** no anel. A tabela só traduz o tipo.

### 7.6 Tabela completa: tipo → frase (todos os eventos existentes)

Fonte: todos os pontos que empurram eventos no código, `src/core.rs` (`emit`), `src/plugins.rs` (`events.push`, `Ev::Audit`), `src/connections.rs` (`log`), `src/skills.rs`, `src/hub.rs`, `src/registry.rs`, `src/agent.rs`, `src/world.rs` (`audit_kind`). Frase em português; o tipo cru não aparece na tela.

| Tipo (`kind`) | Origem | Frase exibida | Resultado |
|---|---|---|---|
| `hub_import_started` | Plugin | Importação de plugin iniciada | — |
| `hub_payload_staged` | Plugin | Pacote de plugin verificado e guardado; nada foi instalado | Concluído |
| `hub_import_cancelled` | Plugin | Importação de plugin cancelada | — |
| `hub_import_timeout` | Plugin | Importação de plugin expirou sem conclusão | Falhou |
| `hub_staged_discarded` | Plugin | Pacote preparado descartado | — |
| `hub_permissions_approved` | Plugin | Permissões de plugin aprovadas | Concluído |
| `hub_plugin_installed` | Plugin | Plugin instalado (desativado) | Concluído |
| `hub_plugin_updated` | Plugin | Plugin atualizado (desativado até nova ativação) | Concluído |
| `hub_plugin_rolled_back` | Plugin | Plugin revertido para a versão anterior | Concluído |
| `hub_plugin_removed` | Plugin | Plugin removido | Concluído |
| `plugin_enabled` | Plugin | Plugin ativado | Concluído |
| `plugin_disabled` | Plugin | Plugin desativado | — |
| `plugin_revoked` | Plugin | Permissões de plugin revogadas; plugin desativado | Concluído |
| `plugin_started` | Plugin | Plugin iniciado em sandbox, sem rede | — |
| `plugin_stopped` | Plugin | Plugin parado | — |
| `plugin_failed` | Plugin | Plugin falhou | Falhou |
| `plugin_log` | Plugin | Plugin registrou uma linha de log (conteúdo não exibido) | — |
| `plugin_settings_cleared` | Plugin | Configurações guardadas pelo plugin LLM apagadas | Concluído |
| `capability_invoked` | Plugin | Capacidade de plugin invocada | — |
| `capability_partial` | Plugin | Plugin enviou resultado parcial | — |
| `llm_fallback_used` | Plugin | Modelo de reserva respondeu no lugar do principal | — |
| `llm_configured` | Plugin | Configuração do motor LLM salva | Concluído |
| `llm_marked_good` | Plugin | Modelo marcado como bom | Concluído |
| `llm_rolled_back` | Plugin | Motor LLM voltou à última configuração boa | Concluído |
| `secret_set` | Plugin | Chave do provedor salva | Concluído |
| `secret_cleared` | Plugin | Chave do provedor removida | Concluído |
| `screen_capture` | Plugin | Captura de tela simulada (sem hardware real) | — |
| `input_action` | Plugin | Ação de entrada simulada (sem hardware real) | — |
| `audio_action` | Plugin | Ação de áudio simulada (sem hardware real) | — |
| `mic_action` | Plugin | Ação de microfone simulada (sem hardware real) | — |
| `camera_action` | Plugin | Ação de câmera simulada (sem hardware real) | — |
| `synthetic_action` | Plugin | Ação simulada de plugin de percepção | — |
| `skill_validated` | Skill | Manifest de skill validado | Concluído |
| `skill_draft_put` | Skill | Rascunho de skill gravado | Concluído |
| `skill_plugin_validate` | Skill | Validação de skill feita pelo plugin | Concluído |
| `skill_plugin_list` | Skill | Lista de skills pedida ao plugin | — |
| `skill_plugin_dry_run` | Skill | Simulação de skill feita pelo plugin | Concluído |
| `skill_approved` | Skill | Skill aprovada | Concluído |
| `skill_enabled` | Skill | Skill habilitada | Concluído |
| `skill_run_started` | Skill | Execução de skill iniciada | — |
| `skill_step` | Skill | Passo de skill registrado | — |
| `skill_service_denied` | Skill | Skill tentou um serviço não permitido; recusado | Recusado |
| `skill_run_done` | Skill | Execução de skill concluída | Concluído |
| `skill_run_failed` | Skill | Execução de skill falhou | Falhou |
| `skill_rolled_back` | Skill | Execução de skill revertida: passos concluídos desfeitos | — |
| `skill_exported` | Skill | Pacote de skill exportado | Concluído |
| `skill_import_previewed` | Skill | Pré-visualização de pacote de skill | — |
| `skill_imported` | Skill | Skill importada como rascunho (publisher não verificado) | Concluído |
| `connection_added` | Conexão | Conta criada (desconectada) | Concluído |
| `connection_connected` | Conexão | Conta conectada | Concluído |
| `connection_consented` | Conexão | Escopos concedidos | Concluído |
| `connection_expired` | Conexão | Conta expirou; reautenticação necessária | — |
| `connection_refreshed` | Conexão | Credencial da conta renovada | Concluído |
| `connection_trusted` | Conexão | Ferramenta MCP confiada | Concluído |
| `connection_call` | Conexão | Chamada de operação de conta (resultado no log, não no anel) | — |
| `connection_disconnected` | Conexão | Conta desconectada; segredos apagados | Concluído |
| `connection_revoked` | Conexão | Acesso revogado no servidor; segredos apagados | Concluído |
| `connection_removed` | Conexão | Conta removida | Concluído |
| `registry_visual_allowed` | Conexão | Fallback visual ligado por você | Concluído |
| `registry_visual_revoked` | Conexão | Fallback visual desligado | Concluído |
| `registry_visual_run` | Conexão | Fallback visual executou um passo | — |
| `session_started` | Comando | Sessão de voz iniciada | — |
| `transcript_partial` | Comando | Transcrição parcial recebida (texto não exibido) | — |
| `transcript_final` | Comando | Transcrição final recebida (texto não exibido) | — |
| `capture_completed` | Comando | Captura de áudio concluída | — |
| `speech_started` | Comando | Resposta por voz iniciada | — |
| `speech_completed` | Comando | Resposta por voz concluída | — |
| `tts_failed` | Comando | Falha na resposta por voz | Falhou |
| `wake_failed` | Comando | Falha no detector da frase de wake | Falhou |
| `command_authorized` | Comando | Comando autorizado | — |
| `command_success` | Comando | Comando concluído (recibo verificado) | Concluído |
| `command_failed` | Comando | Comando falhou | Falhou |
| `command_denied` | Comando | Comando negado | Negado |
| `command_rejected` | Comando | Comando recusado | Recusado |
| `tool_proposed` | Comando | Ação proposta, aguardando sua decisão | — |
| `tool_authorized` | Comando | Ação autorizada por você | — |
| `tool_denied` | Comando | Ação negada por você | Negado |
| `tool_executed` | Comando | Ação executada | Concluído |
| `tool_failed` | Comando | Ação falhou | Falhou |
| `agent_started` | Comando | Agente iniciado | — |
| `agent_step` | Comando | Passo do agente registrado | — |
| `agent_tool` | Comando | Ferramenta do agente chamada | — |
| `agent_done` | Comando | Agente concluiu | Concluído |
| `agent_failed` | Comando | Agente falhou | Falhou |
| `agent_aborted` | Comando | Agente abortado | — |
| `agent_blocked` | Comando | Agente bloqueado | Recusado |
| `agent_blocked:loop_blocked` | Comando | Agente bloqueado: repetiu a mesma ação | Recusado |
| `agent_blocked:stale_screen` | Comando | Agente bloqueado: a tela mudou desde a observação | Recusado |
| `preferences_updated` | Comando | Preferências salvas | Concluído |
| `preferences_storage_error` | Comando | Falha ao salvar preferências | Falhou |
| `configuration_recovered` | Comando | Configuração recuperada; padrões restaurados | Concluído |
| `configuration_recovery_error` | Comando | Falha ao recuperar a configuração | Falhou |

Fora da tabela (decisão): `route_create_issue` é nome de ferramenta, não evento. `skill_disabled` e `skill_version_changed` aparecem no código só como motivos de reversão de skill (`src/skills.rs`), não como evento próprio do anel. Por isso, desabilitar skill hoje não deixa evento no anel (lacuna, §11.10).

### 7.7 Filtros, ordenação, estados

| Item | Regra |
|---|---|
| Chip `Todos` (padrão) | todos os eventos |
| Chip `Plugin` | origem Plugin |
| Chip `Skill` | origem Skill |
| Chip `Conexão` | origem Conexão |
| Chip `Comando` | origem Comando (inclui propostas e passos do agente, D6) |
| Ordenação | `Nº` decrescente, fixa |
| Agrupamento | nenhum |
| Vazio | `Nenhum evento nesta sessão do Core.` (texto 14 px, moldura tracejada, altura 140) |
| Filtro sem resultado | `Nenhum evento de <origem> nesta sessão.` |
| Core offline | banner `Core desconectado.`; lista mostra o último snapshot, se houver |

---

## 8. Como o contador é calculado

Esta seção define o número P do badge `Permissões •P` (§1), a faixa de resumo (§5.6, item 8) e o cabeçalho de Pendências (§5.6, item 10). **São a mesma conta.**

Definições:
- **A (aprovadas)** = número de plugins com `permissions_approved` verdadeiro **+** número de contas com `granted_scopes` não vazio.
- **P (pendentes)** = soma de três itens:
  1. Plugins em `hubEntries` com `permissions` não vazio, `permissions_approved` falso e `status` ∈ {`installed`, `update_available`}.
  2. Contas em `connectionsItems` com `pending_scopes` não vazio (cada conta conta **uma** vez, não por escopo).
  3. Contas MCP em `connectionsItems` com pelo menos uma ferramenta `tools[].state` = `needs_reapproval` (cada conta conta uma vez).

Excluídos de P (com motivo):
- Plugin `not_installed` sem aprovação: não bloqueia nada. Aparece em Concessões como `Não aprovada`, mas não conta.
- Plugin `incompatible`: não é decisão do usuário hoje.
- **Skills** com `permissions_ok` falso: a pendência é do plugin dono e já conta no item 1. Contar a skill também seria dupla contagem (D4).
- Propostas de ação do Assistente e do agente (`tool_proposals`, `agent`): decididas no Assistente, ação a ação (D5).
- Contas sem `pending_scopes` nem ferramenta a confiar.

Quando recalcular: ao mudar `hubEntries` (`hubEntriesChanged`) e `connectionsItems` (`connectionsChanged`). O badge atualiza na barra de abas mesmo fora desta aba.

Exibição:
- P = 0: badge some; texto do resumo `Nenhuma permissão aprovada ou pendente.` se também A = 0; senão `{A} aprovada(s) · 0 pendentes`.
- P > 0: badge `•P` (P ≤ 99) ou `•99+`. Accessible.name da aba: `Permissões, P pendências`.
- Core offline: P = 0 (badge some); a faixa mostra `Core desconectado` (Erro).
- Sessão de voz: P continua contando (D7); só as ações de plugin ficam bloqueadas.

Fila de Visão geral: os mesmos itens de P, na ordem de §5.4. Quantidade da fila = P.

---

## 9. Acessibilidade

Regras da casca (`docs/ui-spec/00-casca.md`) valem: foco visível com anel de 2 px de acento, Esc fecha diálogo, rótulos sem inglês e sem código cru.

| Tema | Regra |
|---|---|
| Ordem de foco | aba nível 1 → sub-abas → botão primário do cabeçalho → filtro (Concessões) ou chips (Auditoria) → combo Agrupar por → linhas da tabela (setas ↑/↓ movem entre linhas) → botão da linha (Tab) |
| Teclado na tabela | Enter na linha abre o botão de ação primário dessa linha. Setas trocam de linha. Home/End vão ao primeiro/último |
| Nomes acessíveis | badges: `Plugin, aprovada` etc.; botões: `Revisar permissões de <plugin_id>`, `Revogar permissões de <plugin_id>`, `Consentir escopos de <label>`, `Revogar acesso da conta <label>`, `Confiar na ferramenta <nome>`, `Ver em Skills: <nome>`, `Ver <linha>` (Visão geral) |
| Cor + palavra | todo estado tem texto (`Aprovada`, `Pendente`…) além da cor. Nunca só cor |
| Tabela | cabeçalhos de coluna marcados como cabeçalho; célula do estado com o texto completo |
| Diálogos | foco inicial: D-P1 no checkbox; D-P2, D-P4 e D-P5 em `Cancelar`; D-P3 em `Cancelar` |
| Anúncio de resultado | o texto de resultado do diálogo ou do card é anunciado quando muda (`hubApprovalResult`, `connectionsResult`) |
| Dica de botão desabilitado | a dica do motivo também fica em `Accessible.description` (não só no tooltip) |
| Tamanho de texto | 14 px no corpo; 12 px só em legenda; 17 px semibold em título de cartão |
| Contraste | textos #9db0e0 e acima sobre #0e1a3a e #0b1530 com contraste ≥ 4.5:1; selos com o tom da §3.5 e texto escuro sobre Aviso |
| Movimento | nenhuma animação obrigatória; barra de progresso é indeterminada e some ao terminar |
| HiDPI | ícones e anel de foco em vetor ou escala de tela |

---

## 10. Responsivo (abaixo de 900 px)

| Elemento | Regra |
|---|---|
| Abas nível 1 | só ícones com tooltip (o nome: `Permissões`) |
| Sub-abas | barra rola na horizontal |
| Cabeçalho | título, depois subtítulo, depois o botão primário em linha própria, largura total |
| Faixa de resumo | texto quebra; badge vai para a linha de baixo |
| Filtro e combo (Concessões) | empilham: filtro em largura total; combo abaixo, à esquerda |
| Tabela de Concessões | vira cartões. Cada cartão: linha 1 = Origem (badge) + Item; linha 2 = Permissão ou escopo; linha 3 = Acesso + Estado; linha 4 = botão de ação em largura total. Coluna Nº oculta |
| Tabela de Auditoria | vira cartões: linha 1 = Tipo; linha 2 = Origem e Resultado (badges); Nº à direita da linha 2 |
| Cartões de Visão geral | já são largura total; linhas de fila: texto à esquerda, botão à direita |
| Diálogos | largura `janela − 32`, mínimo 720 − 32 = 688 px |
| Gutter | 32 px nas duas laterais (16 px mínimo); nenhuma tabela estoura a largura |
| Mínimo | 720 × 520. Abaixo disso a janela não é suportada (`00-casca.md`) |

---

## 11. Itens NOVO (precisa de mudança na ponte ou no Core) e (UI)

**Status verificado no WP8 (`docs/WP8.md`), por item:** 11.1 implementado (`events`); 11.2 implementado com outro nome (`at_ms`, Unix ms, não `at` ISO); 11.3 parcial (datas de aprovação e de concessão existem; `revoked_at` não); 11.4 parcial (`permissions_ok`/`missing` existem; lista `capabilities[]` e contagem não); 11.5 parcial (`outcome` existe no evento, mas o resultado de `connection_call`/`tool_*` nem sempre aparece); 11.6 não implementado (não há caminho do log na ponte; `coreRootPath` é só a pasta); 11.7 implementado (`connection_revoke_scope`, `connectionRevokeScope`, `DPermDialogs.qml`); 11.8 implementado com outro texto (`app/components/BExt.js`); 11.9 não implementado (`display_manipulate` não existe em `src/world.rs`; decisão do dono pendente); 11.10 não implementado (`skill_disable` só emite evento quando há execução ativa).

### 11.1 NOVO (ponte): expor os eventos
- O que: o snapshot já tem `events` (lista de 64, validada em `app/bridge.py` linhas 657–665) e a ponte não expõe. Criar propriedade QML, por exemplo `auditEvents` (`QVariantList`), com `NOTIFY` próprio, e preencher com `snapshot['events']`.
- Sem isso: a Auditoria (§7) não tem dados.

### 11.2 NOVO (Core): hora nos eventos
- O que: incluir `at` (ISO-8601, UTC) em cada evento de `Core::emit` (`src/core.rs`, struct `Event`) e acrescentar `at` em `EVENT_KEYS` (`app/bridge.py`, linha 45).
- Efeito: coluna de hora na Auditoria e ordenação por data em "Concessões ativas" (§11.3).

### 11.3 NOVO (Core): datas de concessão e revogação
- O que: guardar `approved_at` e `revoked_at` por aprovação em `hub::Approval` (`src/hub.rs`, `approve` e `revoke_approval`) e expor `approved_at` em `hub.entries`. Para contas: `granted_at` por escopo em `connections`.
- Efeito: título `Concedido recentemente` (§5.6 item 15) e contagem `N revogadas` no resumo.

### 11.4 NOVO (Core + ponte): capacidades de skill
- O que: em `skills::Item` (`src/skills.rs`), trocar `permissions_ok` (bool) e `missing` por uma lista `capabilities[]` com `{capability, owner_plugin_id, owner_approved, permission}`. Expor na ponte (`SKILL_ITEM_KEYS`, `bridge.py`).
- Efeito: contagem `N capacidades, k ok` e botão `Revisar` para o plugin dono (§6.5 B).

### 11.5 NOVO (Core): resultado no evento de conta e de ferramenta
- O que: incluir `outcome` no evento do anel para `connection_call` e `tool_*` (hoje o resultado só vai ao `audit.log` via `log` em `src/connections.rs`).
- Efeito: coluna Resultado correta para essas linhas (§7.6 hoje mostra `—`).

### 11.6 NOVO (ponte): caminho do log
- O que: propriedade com o diretório do Core (`storage.root`), para mostrar `<pasta>/audit.log` em Detalhes técnicos (§7.2).
- Nota: `audit.log` guarda só `{version, sequence}` por resposta e as linhas de conta (`src/storage.rs:798-833`). O caminho é a única coisa exibida.

### 11.7 NOVO (Core): revogação por escopo
- O que: a conta não tem revogação por escopo; `connection_revoke` apaga a conta inteira (`src/connections.rs`). Para revogar um escopo só, criar operação nova no Core e slot na ponte.
- Hoje: esta spec usa "Revogar conta" (D-P4) e avisa quais escopos saem.

### 11.8 NOVO (ponte): textos de motivo de incompatibilidade
- O que: tabela de exibição para `reason` (`api_version`, `target`, `dependencies_unresolved`), no formato de `CODE_MESSAGES`. Hoje a QML mostra o código cru (`Incompatível: ` + `reason`, `app/Main.qml`).

### 11.9 NOVO (Core, decisão): `display_manipulate`
- O que: confirmar se existe serviço no Core que exija `display_manipulate`. Se não existir, a permissão não deveria ser aprovável (manifesto aceitaria algo que não libera nada). Hoje o rótulo existe (`PERMISSION_LABELS`), mas `src/world.rs` não tem o serviço.

### 11.10 NOVO (Core): desabilitar skill sem evento
- O que: `skill_disable` (`src/skills.rs`) não empurra evento ao anel. Sem isso a Auditoria não mostra desabilitação de skill. Criar evento `skill_disabled` (hoje `skill_disabled` é só motivo de reversão).

### 11.11 (UI) — sem mudança na ponte
- **U1** D-P1 usa `core.permissionLabel` (corrige AC-04). Hoje mostra IDs crus (`Main.qml:361`).
- **U2** D-P4 e D-P5: diálogos de confirmação novos, usando `connectionRevoke` e `connectionTrustTools` que já existem. Fecha parte de AC-05 (Revogar conta e Confiar). `Remover conta` e `Remover chave` continuam sem confirmação em Extensões (fora desta aba).
- **U3** D-P3: diálogo de consentimento usando `connectionConsent` existente.
- **U4** Visão geral: botão `Revisar próxima` e fila ordenada (§5.4).
- **U5** Badge `•P` na barra de abas e o contador de §8: calculado na QML a partir de `hubEntries` e `connectionsItems`. Sem campo novo.

---

## 12. Achados e como esta tela resolve

| Achado | Como esta tela resolve | Pendência |
|---|---|---|
| **AC-03** (página Permissões sem conteúdo) | Visão geral (fila e concessões) e Concessões (tabela única) | — |
| **AC-04** (IDs crus no diálogo de revisão) | D-P1 mostra rótulos de §3.1; ID só em Avançado | — |
| **AC-05** (ações destrutivas sem confirmação) | Revogar conta, Confiar: diálogo (D-P4, D-P5). Revogar plugin já tinha (D-P2) | `Remover conta` e `Remover chave` continuam sem confirmação em Extensões. Recomendado tratar lá. |
| **DU-10** (três formatos de permissão) | Um formato só: rótulo de §3.1 / §3.2. ID cru só em Avançado | — |
| **NT-04** (Permissões existe sem conteúdo) | Conteúdo completo, com dados já existentes no Core | depende de §11.1 para Auditoria |
| **AC-01** (sessão de voz desliga a Conversa) | Esta tela **não** corrige AC-01. Mantém o bloqueio de mudanças de plugin durante a sessão (D7) e explica na tela | a decisão de manter o bloqueio precisa do dono |
| **AC-16** (não se sabe quando o modelo de reserva respondeu) | O evento `llm_fallback_used` aparece na Auditoria com a frase `Modelo de reserva respondeu no lugar do principal` | a Conversa continua sem o aviso (fora desta aba) |
| **AC-14 / AC-12** | fora desta aba | — |

Recomendações para outras telas (fora desta spec, só para o dono decidir):
- Extensões › Conexões tem controles de consentimento e revogação (P11-C4 a P11-C12 em `UI_INVENTORY`). Pela regra de unicidade de `UI_IA`, Permissões é o lugar dos grants: lá, esses controles deveriam virar link para Permissões.
- Extensões › Plugins tem `Revogar permissões` (D-P2) e `Revisar permissões` (D-P1). Mesma regra: link para Permissões.

---

## 13. Fora de escopo

- Instalar, ativar, desativar, atualizar, remover plugin (Extensões › Plugins).
- Provedor, chave, modelo e consentimento de nuvem do LLM (Extensões › Modelos LLM).
- Remover conta (sem confirmação hoje) e remover chave.
- Criar ou editar skill, importar e exportar pacote.
- Exportar auditoria, caminho do log como ação (Diagnóstico, Avançado).
- Verificação de publisher (nenhum publisher é autenticado nesta build).
- Histórico longo: a Auditoria mostra só o anel de 64 da sessão do Core.
- Qualquer item marcado como memória, almas, hábitos ou automações (sem backend).
