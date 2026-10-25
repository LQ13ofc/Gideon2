# WP8 — Documentação: verificação dos marcadores NOVO em docs/ui-spec/*

Pacote: WP-8 (DOCS-01 a DOCS-04) de `docs/GAP_AUDIT.md`. Arquivos tocados: `docs/ui-spec/*`, `docs/HUMAN_VALIDATION.md`, `docs/WP8.md` (este). Não foram editados `docs/GAP_AUDIT.md` nem `docs/AGENT_STATE.md` (o orquestrador faz). Nenhum código foi alterado.

## 1. Método e comandos

Universo: as linhas que contêm `NOVO` em `docs/ui-spec/*`, obtidas com:

    grep -c "NOVO" docs/ui-spec/*           # 00:0, 01:0, 10:35, 20:53, 30:30, 40:39, 50:57, README:1 = 215 linhas
    grep -n "NOVO" docs/ui-spec/*.md        # lista usada neste documento

Verificação contra o código, por busca de texto (Grep/grep), leitura dos trechos e contagem de strings:

    grep -n "<campo>" app/bridge.py src/*.rs          # propriedades, slots, campos de snapshot e chaves
    grep -rn "<texto>" app src                         # copy de interface e textos de código
    grep -rl "<propriedade>" app/pages app/components  # uso na QML
    sed -n <a>,<b>p <arquivo>                          # leitura de trechos de código

Nenhum gate, teste ou build foi executado: é mudança só de documentação (regra do WP: rodar apenas gates afetados; não há gate para `.md`). O grafo (`scripts/graph.py`) não foi usado, pois a verificação é de leitura e busca de texto; a ferramenta de busca usada foi grep.

Legenda de status:
- **IMPLEMENTADO**: o que o marcador pede existe no código (pode ter nome ou texto diferente, indicado).
- **PARCIAL**: parte existe; a parte que falta está descrita.
- **NAO**: não existe no código (verificado por busca).
- **LEGENDA**: a linha explica o marcador; não é item.
- **NAO VERIFICADO**: não foi possível confirmar em tempo útil; fica em aberto.
- **CORRIGIDO**: a frase estava desatualizada e foi editada neste WP.

## 2. Resumo

| Status | Quantidade (linhas NOVO) |
|---|---|
| IMPLEMENTADO (incl. CORRIGIDO) | ver tabelas |
| PARCIAL | ver tabelas |
| NAO | ver tabelas |
| LEGENDA | ver tabelas |
| NAO VERIFICADO | ver tabelas |

Universo: 215 linhas NOVO (contagem original, `grep -c`). Após as edições, a numeração de algumas linhas mudou (+2 em 10, 20 e 30). Cada linha tem entrada na seção 3.

## 3. Marcadores verificados

Formato: `arquivo:linha` | marcador (resumo) | status | evidência. Linhas em **CORRIGIDO** tiveram a frase de spec editada neste WP.

### 3.1 docs/ui-spec/README.md (1 linha)

| Ref | Marcador | Status | Evidência |
|---|---|---|---|
| README.md:14 | Legenda "Itens marcados NOVO precisam de mudança na ponte/Core" | LEGENDA | Explicação geral, sem item. |

### 3.2 docs/ui-spec/40-configuracoes.md (39 linhas)

| Ref | Marcador | Status | Evidência |
|---|---|---|---|
| 40:20 | Legenda NOVO (ponte/Core) | LEGENDA | Explicação. |
| 40:21 | Legenda NOVO (só QML) | LEGENDA | Explicação. |
| 40:106 | Botão "Reiniciar Core" (NOVO, §8.5) na linha de reinício pendente | IMPLEMENTADO (texto atualizado) | `coreRestart`, `coreRestartAvailable`, `coreRestartResult` em `app/bridge.py:2375-2396`; botão `restartCoreButton` em `app/pages/DiagRecuperacao.qml`. |
| 40:110 | Observação: "o estado de reinício depende de ação externa" | CORRIGIDO | Frase obsoleta: o reinício pela UI existe (`app/bridge.py:2375`). Editado. |
| 40:146 | Persistência de `show_advanced` no Core (`config.json`) | PARCIAL | Interruptor existe como `behavior.advanced` em `app/uisettings.py:104` (arquivo por perfil, app). `src/storage.rs` `Config` não tem `show_advanced`. |
| 40:228 | Tile "Hey Gideon": frase salva via `savedWakeId` (NOVO Core) | PARCIAL | Não há propriedade `savedWakeId` em `app/bridge.py`. Frase salva sai de `packDescription` (`app/bridge.py:2290-2297`); a lista real é `wakePhraseRows`/`selectWake` (`app/bridge.py:2298-2341`). Texto "validação física pendente" existe no código. |
| 40:232 | Botão VW-7 "Reiniciar Core" (NOVO: operação) | IMPLEMENTADO (CORRIGIDO) | Mesma evidência de 40:106. Editado. |
| 40:263 | §7.1A Idiomas (Frente 2, NOVO) | IMPLEMENTADO | `languagesAvailable`, `setLanguages`, `languageSttItems` (`app/bridge.py:2512-2535`); `app/pages/CfgIdiomas.qml` existe. |
| 40:497 | Previa ao vivo "Salvo pelo Core (NOVO)" (C3) | IMPLEMENTADO | `visualFeedback` e `saveFeedback` (`app/bridge.py:2364-2368`) gravam `feedback_preferences` no Core (`src/storage.rs`). |
| 40:516 | AP-7 nota "Tema e cor se aplicam a esta janela. Não ficam salvos ao reabrir." | CORRIGIDO | Texto não existe no código; tema e cor ficam salvos pelo app (ver 40:792). Linha da tabela editada. |
| 40:651 | Interruptor "Mostrar opções avançadas": "Guardado pelo Core (NOVO)" | NAO | Guardado pelo app, não pelo Core (`app/uisettings.py:104`). Frase de Core não corrigida (ver seção 4). |
| 40:685 | GE-8 interruptor `show_advanced` (NOVO, §5) | PARCIAL | Mesma evidência de 40:146. Frase "Sem NOVO: vale só nesta execução" está obsoleta (persiste por perfil); não corrigida (ver seção 4). |
| 40:690 | GE-13 botão "Restaurar padrões…" (NOVO: `restore_defaults`) | IMPLEMENTADO (CORRIGIDO) | Core: `PreferencesRestoreDefaults` (`src/protocol.rs:147,670,1268`; `src/core.rs:1742,2420-2426`). Ponte: `restoreCoreDefaults` (`app/bridge.py:2600-2604`). UI: `restoreCoreDefaultsButton` em `app/pages/CfgGeral.qml:425-430`. Editado. |
| 40:711 | §8.1 Trocar frase de despertar (confirmação; NOVO só QML) | NAO | Não existe diálogo "Trocar frase" (`grep "Trocar frase"` sem resultado). Só há confirmação para frase fraca (`weakConfirm`, `app/pages/CfgVoz.qml:457`) e remoção (`deleteConfirm`). |
| 40:723 | §8.2 Restaurar padrões fora do modo seguro (NOVO) | IMPLEMENTADO (CORRIGIDO) | Mesma evidência de 40:690. Título editado. |
| 40:734 | §8.2 Ação: `restore_defaults(revision)` (NOVO) | IMPLEMENTADO (CORRIGIDO) | Op `preferences_restore_defaults` com `revision` (`app/bridge.py:2603`). Editado. |
| 40:753 | §8.3 Erros: "Não foi possível preservar o arquivo…" e "cópia de segurança diferente" (NOVO na ponte) | NAO | Textos não existem (`grep` sem resultado). Core cria `config.invalid.json` (`src/storage.rs:1043-1066`), mas o código de erro não é mapeado. |
| 40:762 | §8.5 Reiniciar Core (NOVO, precisa de ponte/Core) | IMPLEMENTADO (CORRIGIDO) | Mesma evidência de 40:106. Título editado. |
| 40:768 | §8.5 Ação: operação NOVO de reinício | IMPLEMENTADO (CORRIGIDO) | `core_restart` (`app/bridge.py:1627,1738,2379`), tempo limite de 30 s (`RESTART_TIMEOUT_MS`, `app/bridge.py:482`). Editado. |
| 40:792 | §10 Comportamento atual: "Tema e cor… não são salvos pelo Core nem pelo app" | CORRIGIDO | Obsoleto: `theme.mode`, `theme.preset`, `theme.accent` são app-side por perfil (`app/uisettings.py:84`, `THEME_KEYS`; `app/pages/CfgAparencia.qml:80-112`). Editado. |
| 40:794 | §10 Alvo: `theme`/`accent` em `config.json` (NOVO Core) | NAO | `src/storage.rs` `Config` sem campos `theme`/`accent`. Continua aberto (decisão de persistir no Core). |
| 40:801 | §10 Tema claro e tema do sistema (NOVO QML) | IMPLEMENTADO | `app/theme/Theme.qml:150-153` (`systemDark`, `isDark` por `theme.mode` system/dark/light); opções em `app/pages/CfgAparencia.qml:88-89`. |
| 40:829 | Código `stale_preferences` (NOVO na ponte) | IMPLEMENTADO (texto diferente) | `app/bridge.py:1067`: "Configurações mudaram no Core; atualize e tente de novo". Texto da spec ainda não alinhado (CORRIGIDO na tabela). |
| 40:830 | Código `invalid_preferences` | IMPLEMENTADO (texto diferente) | `app/bridge.py:1068`. |
| 40:831 | Código `preferences_storage_error` | IMPLEMENTADO (texto diferente) | `app/bridge.py:1072`. |
| 40:832 | Código `preferences_unavailable` | IMPLEMENTADO (texto diferente) | `app/bridge.py:1073`. |
| 40:833 | Falha de cópia de segurança | NAO | Sem texto nem código de cópia de segurança (ver 40:753). |
| 40:834 | Cópia de segurança diferente | NAO | Idem. |
| 40:859 | AC-06 "Tema e cor não persistem" (NOVO) | CORRIGIDO | Obsoleto no app. Editado. |
| 40:871 | Item 1 consolidado: `savedWakeId` | PARCIAL | Não há propriedade com esse nome; função coberta por `wakePhraseRows`/`selectWake` (`app/bridge.py:2298-2341`). |
| 40:872 | Item 2 consolidado: reinício do Core | IMPLEMENTADO (CORRIGIDO) | Ver 40:106. |
| 40:873 | Item 3 consolidado: `restore_defaults` | IMPLEMENTADO (CORRIGIDO) | Ver 40:690. |
| 40:874 | Item 4 consolidado: `show_advanced` no `config.json` | PARCIAL | Ver 40:146. Falta a persistência no Core. |
| 40:875 | Item 5 consolidado: `theme`/`accent` no `config.json` | PARCIAL | Persistem no app (`uisettings.py`); falta o Core. |
| 40:876 | Item 6 consolidado: textos de `CODE_MESSAGES` | PARCIAL | Quatro dos seis textos existem (40:829-832). Faltam os dois de cópia de segurança (40:833-834). |
| 40:877 | Item 7 consolidado: tema claro e do sistema | IMPLEMENTADO (CORRIGIDO) | Ver 40:801. |
| 40:878 | Item 8 consolidado: diálogos de troca de frase e restauração | PARCIAL | Restauração tem diálogo (`coreDefaultsConfirm`, `app/pages/CfgGeral.qml:430`). Troca de frase não tem (40:711). |
| 40:879 | Item 9 consolidado: valor salvo × rascunho (volume e prazo) | NAO VERIFICADO | Não auditado em detalhe. |
| 40:880 | Item 10 consolidado: estado "Enviando ao Core" | PARCIAL | `PENDING` existe em `app/bridge.py`; a desativação durante gravação não foi verificada. |

Observação: as linhas 40:829-832 e 40:871-880 foram verificadas com a tabela consolidada. A linha 40:793-796 do §10 (campos de `config.json`) não está em NOVO, mas faz parte do mesmo item (40:794).

### 3.3 docs/ui-spec/10-assistente.md (35 linhas)

| Ref | Marcador | Status | Evidência |
|---|---|---|---|
| 10:24 | Legenda `NOVO (ponte/Core)` | LEGENDA | Explicação. |
| 10:25 | Legenda `NOVO (QML)` | LEGENDA | Explicação. |
| 10:129 | §2.3 Regra de "Erro" (prioridade 11), NOVO QML | NAO VERIFICADO | Não auditado. |
| 10:146 | Botão do cabeçalho cobre também a resposta do chat (NOVO QML) | NAO VERIFICADO | Não auditado. |
| 10:241 | H-09a Linha "Confiança" (NOVO: expor `transcript.confidence`) | PARCIAL | `transcriptSummary` expõe `snapshot["transcript"]` (`app/bridge.py:3083`), inclui `confidence` (validado em `app/bridge.py:1012`). Exibido só em `app/pages/DiagMotores.qml:325` ("Confiança da transcrição: desconhecida"), não na Conversa. |
| 10:251 | H-13 Texto "Efeito: {effect}" (NOVO: campo `effect` em tool proposals) | IMPLEMENTADO | `src/tools.rs:361` (`effect: Option<Effect>`, registro) e `src/tools.rs:358` (`risk`). Ponte aceita `effect` (`app/bridge.py:611-633`). Texto de ausência em `app/components/AProposalCard.qml:44`. Propostas locais não têm o campo (correto pela spec). |
| 10:252 | H-14 "Risco: {…}" (NOVO: campo `risk`) | IMPLEMENTADO | `src/tools.rs:358`; `app/bridge.py:632`; `app/components/AProposalCard.qml:56` ("Risco:"). |
| 10:256 | H-18 "Autorizar" com diálogo para risco alto (NOVO QML) | IMPLEMENTADO | `app/components/AProposalCard.qml:134` (`title: "Autorizar a ferramenta " + …`). |
| 10:294 | Texto "Indisponível: Core desconectado." (NOVO QML) | IMPLEMENTADO | `grep` encontra o texto em `app/`. |
| 10:295 | Texto "Indisponível: uma sessão de voz está em andamento." | IMPLEMENTADO | Encontrado em `app/`. |
| 10:296 | Texto "Indisponível: a entrada de texto só existe no perfil de teste." | IMPLEMENTADO | Encontrado em `app/`. |
| 10:297 | Texto "Indisponível: o Core precisa de atenção." | IMPLEMENTADO | Encontrado em `app/`. |
| 10:301 | Validação ao digitar: slot `commandProblem(texto)` (NOVO ponte/Core) | IMPLEMENTADO (CORRIGIDO) | `app/bridge.py:1854`; usado em `app/pages/InicioHoje.qml`. Frase "Até lá, o erro só aparece após o envio" removida. |
| 10:343 | §7.2 Sub-aba depende de `chatAvailable` e some na sessão de voz (NOVO ponte/Core) | NAO | `chatAvailable` (`app/bridge.py:1849`) → `pluginsAvailable` → `hubLifecycleAvailable` → `preferencesAvailable` (`app/bridge.py:2424`), que exige `not self.sessionId`. Continua igual. |
| 10:405 | CV-02 banner com flag de fallback (NOVO) | PARCIAL | Flag existe (`used_fallback`, `app/bridge.py:462`; `app/pages/Conversa.qml:62` `fallbackRecent`). Demais banners cobertos por `llmConfig`. |
| 10:406 | CV-03 sugestões "Que horas são?" e "Abrir o Brave" (NOVO copy) | IMPLEMENTADO | Textos encontrados em `app/` ("Que horas são?"; "Abrir o Brave"). |
| 10:410 | CV-07 proposta inline com "Efeito/Risco" (NOVO) | IMPLEMENTADO | `app/components/AProposalCard.qml:34-56`. |
| 10:429 | Item 4 "Respondeu o modelo de reserva: {modelo}." (NOVO ponte/Core `used_fallback`) | PARCIAL | Dado existe (`llmLastChat`, `app/bridge.py:2399`; `Conversa.qml:62`). Texto "Respondeu o modelo de reserva" não existe; há "Resposta de reserva". |
| 10:565 | AG-06 botão "Abortar" (texto e nome "Abortar agente") | IMPLEMENTADO | `app/pages/Agente.qml:139-142`. |
| 10:572 | AG-08 linha "Tokens … Passos … Tempo" (NOVO passos) | IMPLEMENTADO | `app/pages/Agente.qml:178` ("Passos " + steps + "/" + max_steps); `agentBudget` (`app/bridge.py:1990`). Formato difere do texto da spec. |
| 10:581 | AG-12 "A resposta aparece aqui quando o agente concluir." (NOVO copy) | IMPLEMENTADO | Texto encontrado em `app/pages/Agente.qml`. `agentAnswer` (`app/bridge.py:1988`). |
| 10:582 | AG-13 cartão de aprovação com "Efeito e Risco" (NOVO) | PARCIAL | Dados `toolProposals` com `run_id`/`step` (`AGENT_PROPOSAL_KEYS`, `app/bridge.py:157`) e `risk`/`effect` do Core. Cartão por `run_id` não foi verificado em detalhe. |
| 10:599 | "Indisponível: o motor LLM não está ativo." (NOVO QML) | NAO | Texto não existe (`grep` sem resultado). Há "Configuração do motor indisponível" (código `llm_unavailable`, `app/bridge.py:709`). |
| 10:603 | Agente: "Indisponível: uma sessão de voz está em andamento." | IMPLEMENTADO | Texto encontrado em `app/`. |
| 10:618 | AG-06 diálogo de confirmação de aborto (NOVO QML) | IMPLEMENTADO | `app/pages/Agente.qml:314-317` (`agentAbortDialog`, "Cancelar" é o padrão). |
| 10:709 | AT-02 lista de eventos (NOVO ponte: expor `events`) | IMPLEMENTADO | `events` property (`app/bridge.py:1879-1880`); `app/pages/Atividade.qml`. |
| 10:710 | AT-03 "Nada neste filtro." (NOVO copy) | IMPLEMENTADO | Texto encontrado em `app/`. |
| 10:715 | §6.7 mapa de eventos → texto (NOVO QML) | IMPLEMENTADO | `app/shell/EventLabels.js`, `app/shell/ActivityRows.js`. |
| 10:760 | "Evento do Core" para `kind` desconhecido (NOVO copy) | IMPLEMENTADO | Texto encontrado em `app/`. |
| 10:775 | Ordem da linha do tempo; skill/última chamada sem horário (NOVO QML; timestamp no Core) | PARCIAL | Timestamp existe (`at_ms`, `src/core.rs:834,1048`). Ordenação por `sequence` em `app/shell/ActivityRows.js`; regra das linhas sem horário não verificada. |
| 10:795 | "O motor LLM parou. Conversa indisponível." (NOVO copy) | NAO | Texto não existe. |
| 10:800 | Tabela "comportamento alvo" (NOVO ponte/Core) | PARCIAL | Itens N-1 a N-9 (seção 9.2) verificados abaixo. |
| 10:884 | §9.2 "Não existe — NOVO (ponte/Core)" (cabeçalho) | CORRIGIDO | Adicionado status por item (N-1..N-9). |
| 10:898 (atual 10:900) | §9.3 "Só QML (NOVO QML, sem ponte)" (cabeçalho) | LEGENDA | Itens da seção 9.3 não auditados individualmente. |
| 10:940 (atual 10:940) | D-4: "Mantido como NOVO (N-4)" | IMPLEMENTADO | N-4 implementado (`agentBudget`, `agentSteps`, `app/bridge.py:1986-1990`; orçamento de tempo em `app/pages/Agente.qml`). |

Itens N-1 a N-9 (seção 9.2):
- N-1 risk e effect em tool proposals: IMPLEMENTADO para registro (`src/tools.rs:358-361`).
- N-2 horário no Event: IMPLEMENTADO (`at_ms`, `src/core.rs:834,1045-1048`).
- N-3 `@Property events`: IMPLEMENTADO (`app/bridge.py:1879`).
- N-4 `step`, `max_steps`, `started_ms_ago`: IMPLEMENTADO (`agentSteps`, `agentBudget`, `app/bridge.py:1986-1990`).
- N-5 desacoplar chat/agente da sessão de voz: NAO (ver 10:343).
- N-6 `used_fallback`: IMPLEMENTADO (`app/bridge.py:462`; `src/llmcfg.rs`, `src/plugins.rs`).
- N-7 `commandProblem`: IMPLEMENTADO (`app/bridge.py:1854`).
- N-8 tradução do recibo de erro: IMPLEMENTADO (`COMMAND_CODE_MESSAGES`, `app/bridge.py:2729-2731`).
- N-9 `transcript.confidence` exposto: IMPLEMENTADO (`app/bridge.py:3083`).

### 3.4 docs/ui-spec/30-permissoes.md (30 linhas)

| Ref | Marcador | Status | Evidência |
|---|---|---|---|
| 30:9 | Legenda NOVO (precisa de ponte/Core) | LEGENDA | Explicação. |
| 30:31 | D2 estado "Revogada" não existe no snapshot | NAO | `permissions_approved` é booleano (`app/bridge.py:40` `ENTRY_KEYS`); nenhum estado "revoked" no snapshot (`grep` em `src/hub.rs` e `app/` sem resultado para estado). |
| 30:32 | D3 "Concessões ativas" até existir a data (NOVO §11.3) | CORRIGIDO | Obsoleto: `approved_at_ms` existe (`app/bridge.py:40`; `app/shell/PermRows.js:145`) e `granted_at_ms` existe (`src/connections.rs:1210,2083`; `CAccountCard.qml:171`). Editado. Falta a data de revogação. |
| 30:83 | Eventos (Auditoria): `auditEvents` (NOVO §11.1) | IMPLEMENTADO | Propriedade `events` (`app/bridge.py:1879`), usada em `app/pages/PermAuditoria.qml:29`. Nome diferente. |
| 30:84 | Caminho do log (Avançado) (NOVO §11.6) | NAO | Só `coreRootPath` (`app/bridge.py:3066`), a pasta do Core. Sem `audit.log` exposto. |
| 30:196 | Motivo `api_version` ("versão de API não suportada") (NOVO §11.8) | IMPLEMENTADO (texto diferente) | `app/components/BExt.js:7-9` ("versão de API incompatível"). |
| 30:197 | Motivo `target` (NOVO §11.8) | IMPLEMENTADO (texto diferente) | `app/components/BExt.js:8` ("plataforma incompatível"). |
| 30:198 | Motivo `dependencies_unresolved` (NOVO §11.8) | IMPLEMENTADO (texto diferente) | `app/components/BExt.js:10`. |
| 30:263 | D-P3 consentir escopos de conta (usa slot existente) | IMPLEMENTADO | `connectionConsent` (`app/bridge.py:2957`), `app/components/DPermDialogs.qml:288`. |
| 30:280 | D-P4 revogar acesso da conta (confirmação ausente, AC-05) | IMPLEMENTADO | `revokeConfirm` em `app/pages/Conexoes.qml:425` com texto "Revogar a conta …". |
| 30:296 | D-P5 confiar em ferramenta MCP (confirmação) | IMPLEMENTADO | `trustConfirm` em `app/pages/Conexoes.qml:485-496`. |
| 30:410 | Card 15 "Concessões ativas" (vira "Concedido recentemente" com §11.3) | PARCIAL | Data de aprovação existe (`PermRows.js:145` `grantedDate`); título "Concedido recentemente" não existe. |
| 30:494 | "2 capacidades, 1 ok" (NOVO §11.4) | NAO | Texto não existe. Sem `capabilities[]` no Core (`src/skills.rs`). |
| 30:517 | "Com NOVO §11.4: `<n> capacidades, <k> ok`" | NAO | Mesma evidência. |
| 30:520 | Ação "Revisar" abre D-P1 do plugin dono (NOVO §11.4) | PARCIAL | Texto "Revisar" existe em `app/shell/PermRows.js`, `app/pages/PermVisao.qml`, `app/pages/Plugins.qml`. Fluxo com §11.4 não existe. |
| 30:534 | Revogar conta é por conta; "o Core não tem revogação por escopo" (NOVO §11.7) | CORRIGIDO | Obsoleto: `connection_revoke_scope` existe (`src/protocol.rs`, `src/core.rs`, `src/connections.rs`; `app/bridge.py:2975-2979`; UI `app/pages/Conexoes.qml:457`, `DPermDialogs.qml:369`). Editado (ver seção 4). |
| 30:589 | Detalhes técnicos: caminho do log (NOVO §11.6) | NAO | Ver 30:84. |
| 30:626 | "▸ Detalhes técnicos (Avançado): caminho do log (NOVO, seção 11)" | NAO | Ver 30:84. |
| 30:636 | Entrada: lista `events` (NOVO §11.1) | IMPLEMENTADO | Ver 30:83. Ordenação por `sequence` (`app/bridge.py:1880`). |
| 30:833 | Cabeçalho §11 "Itens NOVO" | CORRIGIDO | Adicionado status por item 11.1–11.10. |
| 30:835 | 11.1 expor eventos (ponte) | IMPLEMENTADO | `events` (`app/bridge.py:1879`). |
| 30:839 | 11.2 hora nos eventos (Core, campo `at`) | IMPLEMENTADO (nome diferente) | `at_ms` em cada evento (`src/core.rs:834,1045-1048`); `app/bridge.py:1880`. Não é ISO-8601. |
| 30:843 | 11.3 datas de concessão e revogação | PARCIAL | `approved_at_ms` (`app/bridge.py:40`), `granted_at_ms` (`src/connections.rs:1210`). `revoked_at` não existe (`grep` sem resultado). |
| 30:847 | 11.4 capacidades de skill (`capabilities[]`) | PARCIAL | `deps_ok`, `permissions_ok`, `missing` existem (`app/bridge.py:1319`). Lista `capabilities[]` não existe. |
| 30:851 | 11.5 `outcome` no evento de conta e de ferramenta | PARCIAL | `outcome` existe em todos os eventos (`src/protocol.rs`, `outcome_of`; `app/bridge.py:1880`). Resultado de `connection_call`/`tool_*` ainda não auditado nas linhas. |
| 30:855 | 11.6 caminho do log (ponte) | NAO | Ver 30:84. |
| 30:859 | 11.7 revogação por escopo (Core + ponte) | IMPLEMENTADO | `connection_revoke_scope` (`src/protocol.rs`, `src/core.rs`), `connectionRevokeScope` (`app/bridge.py:2975`), UI em `app/pages/Conexoes.qml:457` e `app/components/DPermDialogs.qml:369`. |
| 30:863 | 11.8 textos de motivo de incompatibilidade | IMPLEMENTADO | `app/components/BExt.js:7-10` (texto diferente da spec). |
| 30:866 | 11.9 `display_manipulate` (decisão do Core) | NAO | `grep display_manipulate src` sem resultado; só rótulo em `app/bridge.py:1191` e lista `PERCEPTION_PLUGINS:704`. Decisão do dono pendente. |
| 30:869 | 11.10 desabilitar skill sem evento | NAO | `src/skills.rs` (`disable`): evento `skill_disabled` só com run ativa (`skill_start_rollback`). |

### 3.5 docs/ui-spec/20-extensoes.md (53 linhas)

| Ref | Marcador | Status | Evidência |
|---|---|---|---|
| 20:25 | Legenda "Sem ID, é elemento novo e está marcado como NOVO" | LEGENDA | Explicação. |
| 20:28 | Legenda `NOVO (precisa de mudança na ponte/Core)` | LEGENDA | Explicação. |
| 20:230 | L1: nome amigável do plugin (campo `name` no catálogo) | NAO | `ENTRY_KEYS` (`app/bridge.py:40`) sem `name`; catálogo (`src/hub.rs`) sem campo `name`/`description`. |
| 20:288 | Ação 5 "Apagar dados do plugin" (`clearPluginSettings(plugin_id)`) | CORRIGIDO | Implementado: `clearPluginSettingsOf(pluginId)` (`app/bridge.py:2245`), usado em `app/pages/Plugins.qml:340`. Editado. |
| 20:354 | R-PL-3 importação de pacote do Hub pela UI (NF-01) | NAO | Core tem `HubBegin`, `HubChunk`, `HubFinish` (`src/core.rs:2016-2056`), mas a ponte não tem os slots e a UI não tem seletor de arquivo (`grep hub_begin app` sem resultado). |
| 20:357 | R-PL-6 "permissão sem rótulo: <ID>" (completar `PERMISSION_LABELS`) | PARCIAL | Texto existe (`app/`). `PERMISSION_LABELS` (`app/bridge.py:1191`) não cobre todas as permissões do catálogo (não auditado a fundo). |
| 20:446 | "Necessárias: <lista>" (`permissions_required` em `skillsItems`) | CORRIGIDO | Implementado: `permissionsRequired` (`app/bridge.py:2919`), `app/components/BSkillDetail.qml:130`. Editado. |
| 20:450 | "× aprovadas × faltando" (forma do IA §2.2, necessárias NOVO) | PARCIAL | "Necessárias" existe; "× aprovadas × faltando" não existe com essa forma. |
| 20:524 | EX-SK-CR-05 "Achado: <mensagem> (<campo>)" (`findings[]`) | PARCIAL | Texto existe, `app/pages/Skills.qml:470`. `findings[]` chega na prévia de importação; a validação devolve só texto. |
| 20:580 | EX-SK-IE-02 texto "Coloque o arquivo .gskill na pasta de importação…" | IMPLEMENTADO | Texto existe em `app/`. |
| 20:581 | EX-SK-IE-03 pasta `<home>/skill-imports` (NOVO ponte) | CORRIGIDO | Implementado: `paths` no snapshot (`src/skills.rs:2975`), `skillPaths` (`app/bridge.py:2921`), `app/pages/Skills.qml`. Editado. |
| 20:586 | EX-SK-IE-08 botão "Exportar" por skill (`skillExport`) | IMPLEMENTADO | `skillExport` (`app/bridge.py:2864`), `skill_export` (`src/skills.rs:3396`). |
| 20:607 | Caminho do pacote exportado (`skill_export` devolve o caminho) | NAO | `skill_export` devolve só `"ok"` (`src/skills.rs:3451`); o caminho `<data>/skill-exports/<id>-<versão>.gskill` é gravado mas não devolvido. |
| 20:642 | Alvo do passo de skill "Alvo: <capability ou tool>" (NOVO) | NAO | `SKILL_STEP_KEYS` (`app/bridge.py:1320`) sem `target`. |
| 20:643 | Efeito do passo de skill (NOVO) | IMPLEMENTADO | `effect` em `SKILL_STEP_KEYS` (`app/bridge.py:1320`); `app/pages/Skills.qml:555` ("Efeito:"). |
| 20:644 | Risco do passo de skill (NOVO) | IMPLEMENTADO | `risk` (`app/bridge.py:1320,1373`); `app/pages/Skills.qml:555` ("Risco:"). |
| 20:674 | R-SK-4 nenhum caminho sem o campo novo (3.6.5; EX-SK-IE-03) | PARCIAL | Pasta de importação exposta; caminho exportado não (ver 20:607). |
| 20:970 | EX-MD-AT-03 "Último bom: <provedor> · <modelo>" (NOVO `llm.config.lkg`) | CORRIGIDO | Implementado: `core.llmConfig` (`app/bridge.py:2000`) com `lkg`; `app/pages/ModelosLlm.qml:49` ("Último bom: "). Editado. |
| 20:971 | EX-MD-AT-04 botão "Testar" (selftest isolado) | CORRIGIDO | Implementado: `llmSelftest` (`app/bridge.py:2023`), op `manual_selftest`. Editado. |
| 20:972 | EX-MD-AT-05 "Voltar ao último bom" (`rollbackLkg`) | CORRIGIDO | Implementado: `llmRollback` (`app/bridge.py:2032`), `app/pages/ModelosLlm.qml`. Editado. |
| 20:980 | Detalhe do modelo "Detalhes indisponíveis: carregue o catálogo…" (NOVO) | PARCIAL | Texto existe (`app/`). O slot `describe(id)` não existe (ver NOVO-13). |
| 20:1148 | Item 9 "Último uso do fallback: <modelo> em <hora>" (NOVO `llm_fallback_used`) | NAO | Texto não existe. Dado parcial: `llmLastChat.used_fallback`/`at_ms` (`app/bridge.py:462,2399`). |
| 20:1368 | "Pacote exportado; publisher não verificado" + caminho (NOVO) | PARCIAL | Texto existe (`app/bridge.py:1612`). Caminho não (ver 20:607). |
| 20:1434 | C-1 texto "Revogar a conta <nome>?…" (UI apenas) | IMPLEMENTADO | `app/pages/Conexoes.qml:425`. |
| 20:1435 | C-2 texto "Remover a conta <nome> do Gideon?…" | IMPLEMENTADO | `app/pages/Conexoes.qml:465`. |
| 20:1436 | C-3 texto "Remover a chave do provedor…" | IMPLEMENTADO | `app/pages/ModelosLlm.qml:702`. |
| 20:1437 | C-4 texto "Confiar na ferramenta <nome>?…" | IMPLEMENTADO | `app/pages/Conexoes.qml:485`. |
| 20:1438 | C-5 texto "Permitir o fallback visual para criar issue?…" | IMPLEMENTADO | Texto encontrado em `app/`; `registryAllowVisual` (`app/bridge.py:3043`). |
| 20:1439 | C-6 "Cancelar a execução <run>? Os passos concluídos serão desfeitos." | NAO | Texto não existe (botão "Cancelar execução" existe). |
| 20:1495 | P-SK-1 "Validar" em Minhas (validar skill instalada pelo id) | NAO | `skillValidate` recebe texto (`app/bridge.py:2825`); não há op por id. |
| 20:1497 | P-SK-3 "Reverter versão" sem versão anterior (flag na ponte) | NAO | Sem campo de versão anterior no snapshot de skill (`grep previous_version` em `src/skills.rs` sem resultado). |
| 20:1504 | Cabeçalho §10.2 lacunas (NOVO) | CORRIGIDO | Adicionado status por NOVO-01..17. |
| 20:1508 | NOVO-01 importar pacote do Hub pela UI | PARCIAL | Core tem `HubBegin`/`HubChunk`/`HubFinish` (`src/core.rs:2016-2056`). Ponte e UI não. |
| 20:1509 | NOVO-02 descartar payload em staging | PARCIAL | Core tem `HubDiscardStaged` (`src/core.rs:2112`; `src/hub.rs:1025`). Ponte não expõe. |
| 20:1510 | NOVO-03 nome e descrição de plugin | NAO | Ver 20:230. |
| 20:1511 | NOVO-04 apagar dados de um plugin qualquer | IMPLEMENTADO | Ver 20:288. |
| 20:1512 | NOVO-05 rótulos de todas as permissões | PARCIAL | Ver 20:357. |
| 20:1513 | NOVO-06 `permissions_required` em `skillsItems` | IMPLEMENTADO | Ver 20:446. |
| 20:1514 | NOVO-07 caminho da pasta de importação | IMPLEMENTADO | Ver 20:581. |
| 20:1515 | NOVO-08 `skill_export` devolve o caminho | NAO | Ver 20:607. |
| 20:1516 | NOVO-09 alvo, efeito e risco por passo | PARCIAL | Efeito e risco existem (20:643-644); `target` não. |
| 20:1517 | NOVO-10 saldo de LKG | IMPLEMENTADO | Ver 20:970. |
| 20:1518 | NOVO-11 voltar ao último bom | IMPLEMENTADO | Ver 20:972. |
| 20:1519 | NOVO-12 testar o modelo atual | IMPLEMENTADO | Ver 20:971. |
| 20:1520 | NOVO-13 detalhe de modelo fora da página (`describe`) | NAO | Sem `describe` em `app/bridge.py` nem `llm_engine.models describe` (`grep` sem resultado). |
| 20:1521 | NOVO-14 último uso do fallback (`llm_fallback_used`) | PARCIAL | Evento existe no Core (`src/plugins.rs`), mas não é exposto à ponte. Último chat tem `used_fallback` (`app/bridge.py:462`). |
| 20:1522 | NOVO-15 confirmação "Permitir fallback visual" | IMPLEMENTADO | Texto e UI em `app/` (`registryAllowVisual`, `app/bridge.py:3043`). |
| 20:1523 | NOVO-16 textos de motivo de incompatibilidade | IMPLEMENTADO | Ver 30:196-198. |
| 20:1524 | NOVO-17 tradução de rota e de estado de candidato | NAO VERIFICADO | Não auditado. |
| 20:1539 | AC-13 exportação sem caminho (NOVO-08) | NAO | Ver 20:607. |
| 20:1540 | AC-14 aprovação sem risco nem efeito (NOVO-09) | PARCIAL | Risco e efeito existem; alvo não (20:642). |
| 20:1542 | AC-16 usuário não sabe quando o fallback respondeu (NOVO-14) | PARCIAL | Ver 20:1148 e NOVO-14. |
| 20:1589 | Checklist "NOVO-01 a NOVO-17 têm decisão registrada" | NAO | Checklist não preenchido neste WP (decisões são do dono). |

Nota: as linhas 20:1539-1542 são referências AC, não itens; estão listadas porque contêm NOVO.

### 3.6 docs/ui-spec/50-diagnostico.md (57 linhas)

| Ref | Marcador | Status | Evidência |
|---|---|---|---|
| 50:587 | Lista "NOVOS: packPreflight, packAudioInput, packAudioOutput, lastCapture, lastSpeech, transcript…" | PARCIAL | `snapshotPack`, `captureSummary`, `speechSummary`, `transcriptSummary` existem (`app/bridge.py:2609,3079-3083`). `packPreflight`, `packAudioInput`, `packAudioOutput`, `lastSpeech` não existem como propriedade (`grep` sem resultado). |
| 50:674 | R15 "Há uma configuração boa salva: <provedor> · <modelo>" (NOVO `llmLastKnownGood`) | PARCIAL | `llm.config.lkg` existe (`src/llmcfg.rs`; `app/bridge.py:470`). Texto e propriedade `llmLastKnownGood` não existem; `app/pages/DiagRecuperacao.qml:141-167` usa `core.llmConfig.lkg` com outros textos. |
| 50:675 | R16 "Voltar à última configuração boa" (slot `rollbackLlm()`) | IMPLEMENTADO | Texto em `app/pages/DiagRecuperacao.qml:159`; ação via `llmRollback` (`app/bridge.py:2032`). Nome do slot difere. |
| 50:678 | R19 situação do catálogo ("Nenhum problema de armazenamento." / "Importação interrompida pendente") | PARCIAL | `hubStorage` (`app/bridge.py:3085`), "Falha ao gravar o registro" e "Situação de armazenamento:" (`DiagRecuperacao.qml:181`). Textos "Nenhum problema" e "Importação interrompida pendente" não existem. |
| 50:747 | Lista "NOVOS: llmLastKnownGood, rollbackLlm(), hubOrphans, hubStorageError, restartCore()" | PARCIAL | `rollbackLlm` e `restartCore` não têm esses nomes; a função existe como `llmRollback` e `coreRestart`. `hubOrphans` e `hubStorageError` não existem como propriedade (`hubStorage` existe). |
| 50:750 | R-R1 Reiniciar Core (NOVO N2) | CORRIGIDO | Implementado: `coreRestart` (`app/bridge.py:2375`), `restartCoreButton` (`app/pages/DiagRecuperacao.qml:58`). Frase obsoleta editada. |
| 50:761 | §8.2 "Condição de aparecimento e interruptor (NOVO)" | PARCIAL | Interruptor existe como `behavior.devMode` (`app/uisettings.py:105`; `app/pages/CfgGeral.qml:109-118`; `DiagEstado.qml:195`), gravado pelo app. |
| 50:763 | `developer_mode` no Core, `setDeveloperMode`, `developerMode` na ponte | CORRIGIDO | Estado atual anotado (app-side). Campo no Core: NAO (`grep developer_mode src` sem resultado). Editado. |
| 50:840 | D10 botão "Disparar wake de teste" (`virtualWake`) | IMPLEMENTADO | `virtualWake` (`app/bridge.py:3072`), `app/pages/DiagDev.qml`. |
| 50:846 | D16 área JSON e `invokeCapabilityJson` | IMPLEMENTADO | `invokeCapabilityJson` (`app/bridge.py:2687`), `app/pages/DiagDev.qml`. |
| 50:850 | D19 estado "Invocação em andamento… / Sem resultado ainda. / Prazo: 3 s" (`capabilityPending`) | PARCIAL | `capabilityPending` (`app/bridge.py:2697`). "Sem resultado ainda." (`DiagDev.qml:306`) e "Prazo: 3 s" (`DiagDev.qml:280`) existem; "Invocação em andamento…" não. |
| 50:853 | V01 "Versão da Base: <versão>" (`packageInfo.version`) | IMPLEMENTADO | `packageInfo` (`app/bridge.py:3064`); `app/pages/DiagEstado.qml:171`; `DiagDev.qml:72`. |
| 50:854 | V02 "Protocolo do Core: <versão>" (`protocolVersion`) | NAO | `app/pages/DiagDev.qml:73` mostra "Protocolo do Core: não informado". Snapshot `version` não é exposto. |
| 50:856 | V04 "Motores: wake · stt · tts" (`packEngines`) | IMPLEMENTADO | Dado via `snapshotPack.engines` (`app/bridge.py:2609`); `DiagDev.qml:18,75`. Nome difere. |
| 50:857 | V05 "SHA-256 do pacote de voz" (`packHash`) | NAO | `app/pages/DiagDev.qml:76` mostra "não informado". Sem `packHash` no Core/ponte. |
| 50:858 | V06 "SHA-256 do catálogo do Hub" (`catalogSha256`) | IMPLEMENTADO | `hubStorage.catalogSha` (`app/bridge.py:1593`); `app/pages/DiagDev.qml:77`. |
| 50:861 | V09 "Binário e PACKAGE.json: sha… · commit…" (`packageInfo`) | PARCIAL | `packageInfo.commit` e `version` existem (`DiagDev.qml:72`). SHA do binário não. |
| 50:862 | V10 "SHA-256 da última captura" (`lastCapture.pcm_sha256`) | IMPLEMENTADO | `captureSummary` (`app/bridge.py:3079`), `CAPTURE_KEYS` com `pcm_sha256` (`app/bridge.py:306`); `DiagDev.qml:90`. |
| 50:893 | Lista "NOVOS: core.developerMode + setDeveloperMode, virtualWake(), invokeCapabilityJson(), protocolVersion, packEngines, packHash, catalogSha256, packageInfo" | PARCIAL | Ver 50:761, 50:840, 50:846, 50:854, 50:856, 50:857, 50:858, 50:853. |
| 50:932 | §11 "Itens NOVO (precisa de mudança na ponte/Core), consolidados" | LEGENDA | Cabeçalho. Itens N1..N11 e NF abaixo. |
| 50:946 | N11 "Frases de código faltantes" + remover `DIAG_LABELS` (R-04) | PARCIAL | Muitos códigos existem em `CODE_MESSAGES`. `DIAG_LABELS` ainda existe (`app/bridge.py:18`). |
| 50:969 | NF-22 "Reinício do Core … Coberto; NOVO (N2)" | CORRIGIDO | Ver 50:750. |

Linhas adicionais de `50-diagnostico.md` (revisão de cobertura; a primeira leitura não listou estas linhas):

| Ref | Marcador | Status | Evidência |
|---|---|---|---|
| 50:9 | Legenda "NOVO (precisa de mudança na ponte/Core)" | LEGENDA | Explicação. |
| 50:43 | Tabela de estados: `developerMode` = ligado (NOVO, §8) | PARCIAL | Interruptor app-side: `behavior.devMode` (`app/uisettings.py:105`). Propriedade `developerMode` do Core/ponte não existe (`grep developerMode app src` sem resultado). |
| 50:73 | R-03 `code_message` devolve "Core recusou a ação: {code}" (NOVO: mudar) | IMPLEMENTADO (spec obsoleta, não editada) | `app/bridge.py:1277-1281`: texto genérico `GENERIC_FAILURE`; o código só aparece com `CODE_DETAIL` ligado (nível Avançado). |
| 50:74 | R-04 remover `DIAG_LABELS` | NAO | `DIAG_LABELS` ainda existe (`app/bridge.py:19`). |
| 50:76 | R-06 estado offline "Core desconectado" (trocar "Core indisponível") | PARCIAL | "Core desconectado" em `app/pages/DiagEstado.qml:80,89`. `stateLabels.offline` ainda é "Core indisponível" (`app/shell/Labels.js:5`). |
| 50:90 | Legenda da coluna Origem | LEGENDA | Explicação. |
| 50:145 | Cliente sem conexão: "Core desconectado" (R-06) | PARCIAL | Mesma evidência de 50:76. |
| 50:177 | `plugin_cpu_exceeded` em CODE_MESSAGES | IMPLEMENTADO | Tabela de erros do plugin, `app/bridge.py:1582` ("Plugin passou do limite…"). |
| 50:178 | `plugin_output_invalid` | IMPLEMENTADO | `app/bridge.py:1581-1582` (tabela de erros do plugin). |
| 50:179 | `plugin_start_failed` | IMPLEMENTADO | `app/bridge.py:1581-1582`. |
| 50:180 | `plugin_quarantined` | IMPLEMENTADO | `app/bridge.py:1581-1582`. |
| 50:181 | `handshake_timeout` | NAO VERIFICADO | Só uma ocorrência em `app/bridge.py`; não confirmado como mensagem. |
| 50:182 | `handshake_mismatch` | NAO VERIFICADO | Idem. |
| 50:194 | motivo `ledger_missing` | IMPLEMENTADO | `HUB_REASON_LABELS` (`app/bridge.py:1577`). |
| 50:195 | motivo `ledger_invalid` | IMPLEMENTADO | `app/bridge.py:1577`. |
| 50:197 | `hub_storage_error` | IMPLEMENTADO | `CODE_MESSAGES.update` (`app/bridge.py:1700`). |
| 50:198 | `plugin_storage_error` | IMPLEMENTADO | `app/bridge.py:1700`. |
| 50:199 | `preferences_storage_error` | IMPLEMENTADO | `app/bridge.py:1072`. |
| 50:200 | `preferences_unavailable` | IMPLEMENTADO | `app/bridge.py:1073`. |
| 50:201 | `configuration_not_ready` | IMPLEMENTADO | `app/bridge.py:1209`. |
| 50:202 | `hub_import_timeout` | NAO VERIFICADO | Presente em `src/core.rs` (evento); mensagem na ponte não confirmada. |
| 50:239 | `virtual_input_disabled` (resposta do wake de teste) | IMPLEMENTADO | `app/bridge.py:1176`. |
| 50:255 | EV-R3 hora de cada evento (ponte registra recebimento) | IMPLEMENTADO | Core envia `at_ms` (Unix ms) em cada evento (`src/core.rs:834,1045-1048`); `events` (`app/bridge.py:1880`); `app/pages/DiagEstado.qml:41` usa `E.clockText(ev.at_ms)`. |
| 50:433 | S19 "Versão da Base" (`packageInfo.version`) | IMPLEMENTADO | `app/bridge.py:3064`; `app/pages/DiagEstado.qml:171`. |
| 50:434 | S20 `core.developerMode` (interruptor) | PARCIAL | Ver 50:43. |
| 50:437 | S23 linhas de eventos com hora (`HH:MM:SS · Área · frase`) | IMPLEMENTADO | `app/pages/DiagEstado.qml:41`; `E.eventArea`, `E.eventPhrase`. |
| 50:554 | M21 TTS "Última resposta" (`lastSpeech`) | PARCIAL | `speechSummary` (`app/bridge.py:3081`) entrega `elapsed_ms`, `samples`, `chunks`. Nome `lastSpeech` não existe. |
| 50:555 | M22 TTS "Pico e RMS" | PARCIAL | `speechSummary` tem `peak` e `rms` (`SPEECH_KEYS`, `app/bridge.py:307`). Texto não auditado. |
| 50:560 | M27 "Resposta de reserva: nesta sessão / não usada nesta sessão" (evento `llm_fallback_used`) | IMPLEMENTADO | `app/pages/DiagMotores.qml:68-72` (`llmFallbackUsed` lê `core.events`, `kind === "llm_fallback_used"`) e `:233`. |
| 50:563 | M30 "Verificação: Verificado" (`packPreflight`) | IMPLEMENTADO | `app/pages/DiagMotores.qml:260` usa `page.pack.preflight === "verified"`. Dado vem de `snapshotPack`; nome `packPreflight` não existe. |
| 50:564 | M31 "Entrada: PCM virtual" (`packAudioInput`) | PARCIAL | Texto em `app/pages/InicioHoje.qml:100` e `OOnboarding.qml`. Propriedade `packAudioInput` não existe; dado via `snapshotPack`. |
| 50:565 | M32 "Saída: virtual" (`packAudioOutput`) | PARCIAL | Mesma evidência de 50:564. |
| 50:569 | M36 "Captura: <dur> s · <amostras>" (`lastCapture`) | PARCIAL | `captureSummary` (`app/bridge.py:3079`). Nome `lastCapture` não existe; texto não auditado. |
| 50:572 | M39 "Origem da última fala", "Confiança da transcrição", "Revisão" | PARCIAL | "Confiança da transcrição: desconhecida" em `app/pages/DiagMotores.qml:325`. "Origem da última fala" não encontrado. |
| 50:576 | M-NOVO-2 expor eventos (`recentEvents`, N6) | IMPLEMENTADO | `events` (`app/bridge.py:1879-1880`); nome difere de `recentEvents`. |

### 3.7 Tabelas de referência cruzada

Os itens NOVO do 50 e do 30 que mencionam "NF-" e "N2" foram conferidos pela tabela consolidada (seção 11 de cada arquivo). Itens NF (NF-17, NF-18, NF-21, NF-23) não têm marcador NOVO e não foram auditados.

## 4. Stale statements corrigidas neste WP

- `40-configuracoes.md`: 110 (reinício externo), 232/106/762/768 (reinício implementado), 690/723/734/873 (restore_defaults implementado), 792 (tema não salvo), 516 (AP-7 nota), 859 (AC-06), 379 (DOCS-03 subtítulo), 829-832 (textos de código), 801/877 (tema claro/sistema), 872 (reinício).
- `50-diagnostico.md`: 750 (R-R1 reinício), 763 (dev mode app-side), 969 (NF-22).
- `30-permissoes.md`: 32 (D3 datas), 534 (revogação por escopo), 833 (status da seção 11).
- `20-extensoes.md`: 288 (clearPluginSettingsOf), 446 (permissions_required), 581 (skill-imports), 970-972 (LKG, selftest, rollback), 1504 (status 10.2).
- `10-assistente.md`: 301 (commandProblem), 884 (status 9.2).
- `HUMAN_VALIDATION.md` D1 (garage_door, ver seção 6).

Pendente de correção (marcado, não editado): `40-configuracoes.md` 685 e 146 ("sem NOVO vale só nesta execução" está obsoleto, o interruptor persiste por perfil) e 651 ("Guardado pelo Core"); `20-extensoes.md` 1148 e 1368 (caminho do pacote). Esses itens ficam para o dono da spec, pois a decisão de persistir `show_advanced` no Core ainda não foi tomada.

## 5. Totais

Contagem de linhas NOVO por arquivo (grep): README 1, 40 39, 10 35, 30 30, 20 53, 50 57, 00 0, 01 0 = 215.

Cada linha NOVO do grep tem uma entrada na seção 3 (com a exceção de linhas de lista de propriedades, que são cobertas pelas entradas dos itens citados). Os status estão em cada linha da tabela; não há contagem automática por status.

Observação de honestidade: algumas linhas do grep combinam dois marcadores (por exemplo 40:228, 40:497, 10:343, 10:406); a linha foi classificada pelo item principal e o outro está citado na evidência. A primeira leitura deste WP não listou as linhas 9 a 576 de `50-diagnostico.md`; elas foram acrescentadas na seção 3.6 após a conferência com `grep -n NOVO`.

## 6. DOCS-01 a DOCS-04

- **DOCS-01** (`restore_defaults`): FEITO no código (`PreferencesRestoreDefaults`, `restoreCoreDefaults`, `restoreCoreDefaultsButton`). Spec corrigida em 40:690, 723, 734, 873. Evidência acima.
- **DOCS-02** (reinício do Core): FEITO no código (`core_restart`, `coreRestart`, `restartCoreButton` em `app/pages/DiagRecuperacao.qml:58`). Spec corrigida em 50:750, 969 e 40:110, 232, 762, 768. Evidência acima.
- **DOCS-03** (subtítulo de dispositivos): Dispositivos são listados pelo Core (`src/devices.rs`, enumeração A4 read-only via `pactl`/`pw-dump`) e exibidos em `app/pages/CfgDispositivos.qml:37`. Subtítulo e explicação corrigidos em `docs/ui-spec/40-configuracoes.md:379`. A faixa de resumo (40:381) foi mantida; "PCM virtual" é o padrão até o usuário escolher dispositivo (`app/pages/InicioHoje.qml:100`).
- **DOCS-04** (D1 garage_door): código trata `garage_door.*` como perigoso (`src/connections.rs:678-679`, `dangerous_service`; teste em `src/connections.rs:4475-4494`). `docs/HUMAN_VALIDATION.md` D1 atualizado com a evidência. A decisão continua com o dono (checkbox aberto): manter o estado atual do código ou remover `garage_door.*` e ajustar o teste.

## 7. O que não foi feito e por quê

- Nenhum item de código foi implementado (fora do escopo de WP8: só docs).
- Itens NAO e PARCIAL continuam como estão no código; a lista completa está nas tabelas (seção 3). Os principais são: persistência de `show_advanced`, `theme`, `accent` e `developer_mode` no Core; slots de importação de pacote do Hub na ponte; `describe(id)`; caminho do pacote exportado; `display_manipulate` (decisão do dono); log de auditoria exposto; revogação de data; desacoplar chat da sessão de voz (N-5); textos de cópia de segurança.
- Itens NAO VERIFICADO: 40:879, 10:129, 10:146, 20:1524, 50:181 e 50:182 (`handshake_*`), 50:202 (`hub_import_timeout`); e 10:775 e 10:582 em parte.
- Nenhum gate ou teste foi executado (docs-only).
- Commit: não feito (o orquestrador commita).
