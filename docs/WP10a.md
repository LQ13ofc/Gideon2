# WP-10a: áreas Notion (Memória, Almas, Hábitos, Automações, Histórico)

Status: **implementado no pacote, não ligado ao Core, à ponte nem à casca.** Nenhum arquivo existente foi editado.
Os itens PROD-01 a PROD-05 de `docs/GAP_AUDIT.md` continuam abertos até a ligação (passo 9 abaixo). PROD-06 depende de
decisão do dono (ver "Decisões").

## 1. Arquivos criados

| Arquivo | Conteúdo |
|---|---|
| `src/personal.rs` | Regras comuns (versão 1 obrigatória, CAS por `revision`, ledger 0600 atômico, retenção, exportação/apagamento), trait `SkillEngine`, agregado `Personal` (ponto único de integração) |
| `src/memory.rs` | Memória: fatos com fonte, consentimento por fonte, prazo (TTL), busca, edição, exclusão |
| `src/souls.rs` | Almas: estilo e prioridades, modo (influência ou simulação), proveniência fixa, prévia, dica para o plugin LLM |
| `src/habits.rs` | Hábitos: uma Skill habilitada com entradas fixas, versão fixada, edição com versão anterior, reversão, execução |
| `src/automations.rs` | Automações: agenda única ou repetida, execução pelo motor de Skills, pausa por deriva, execução manual |
| `src/conversations.rs` | Histórico de conversas em texto: sessões, renomear, apagar, exportar, retenção |
| `src/personal_engine.rs` | Adaptador do Core: `impl SkillEngine for Core` sobre `skills_view()` e `skill_run()` |
| `tests/personal_areas.rs` | 17 testes de integração (carregam `src/*.rs` por `#[path]`, funcionam antes de `lib.rs` exportar os módulos) |
| `app/pages/Memoria.qml` | Permissões › Memória |
| `app/pages/Almas.qml` | Configurações › Almas |
| `app/pages/Habitos.qml` | Extensões › Hábitos |
| `app/pages/Automacoes.qml` | Assistente › Automações |
| `app/pages/Conversas.qml` | Assistente › Histórico |
| `app/components/PConfirm.qml` | Confirmação de ação destrutiva (Cancelar é o foco inicial) |
| `app/components/PItemRow.qml` | Linha de lista (título, detalhe, selo, ações) |
| `app/components/PResult.qml` | Mostra a recusa do Core para uma área (mensagem traduzida, nunca código cru) |
| `app/components/PRetentionNote.qml` | Linha "histórico guardado por N dias / não guardado", lida de `core.historyRetention` |
| `scripts/test_personal_qml.py` | Gate de UI offscreen (8 testes) com Core falso |
| `scripts/personal_host.qml` | Hospedeira de teste da página (só para o gate) |
| `docs/WP10a.md` | Este documento |

## 2. Fontes lidas no Notion

Lidas com `notion-search` e `notion-fetch` em 2026-10-25 (páginas de 2026-10-13):
- "10 · Contexto pessoal, Memory, Habits e Soul" (Memory, Soul, Habit, perfil; retenção; exclusão; "aprendizado não é execução").
- "13 · Interface, HUD e Design System" (lista de áreas: Conversations, Memory, Souls, Habits, Automations, Devices, Permissions...).
- "Referência anterior 03 — Produto e UX" (páginas obrigatórias e critérios de aceitação: "Memory (fontes/TTL/exclusão)", "Souls (perfil, preview sem alegar mudança de identidade)", "Habits (versões/edição/permissions)", "Automations (jobs/cancel)").
- "16 · Automations, tarefas longas e execução remota" (disparadores, estados, "trigger não é autorização permanente", "tarefas sensíveis não continuam após mudança material de contexto").
- "S4 · Skill Engine e compartilhamento" (Habit = instância privada de Skill; "nenhuma permissão alçada por habit").
- "Roadmap oficial" e "Decisões vigentes" (D08).

**Conflito de escopo, registrado para o dono.** As páginas de decisão dizem que Memory, Souls, Habits e Automations
"não entram automaticamente" nos cinco estágios (D08, roteiro). A ordem do dono (mandato de WP-10a) é que tudo do Notion
exista e funcione. Implementei seguindo o mandato, sem mudar o roteiro. O dono deve registrar a decisão em "Decisões vigentes".

## 3. Regras por área

**Comuns.** Cada área é um ledger JSON privado (0600, diretório 0700), gravado de forma atômica (arquivo temporário,
fsync, rename). Leitura recusa link simbólico, hard link, dono estranho, permissão de grupo/outros e arquivo acima do limite.
Um ledger corrompido faz a abertura falhar (não há reparo silencioso). Toda mutação exige `revision` atual (senão
`stale_revision`). Pedido sem `"version": 1` ou com campo desconhecido é recusado.

**Retenção.** O Core passa `Some(janela_ms)` ou `None` (`never`), vindo de `preferences.history_retention`.
- `never`: nada de conversa é gravado (`retention_never`), o histórico existente é apagado na próxima chamada, e fatos
  vindos de conversa são recusados e removidos. Fatos digitados pelo usuário não são afetados.
- janela: conversas e execuções antigas saem da visão e do disco; fatos de conversa saem após a janela.
- Esta é uma decisão minha: a retenção governa o histórico, não as memórias que o usuário curou. O dono pode mudar.

**Memória.** Consentimento por fonte (`user_typed`, `conversation`), desligado por padrão. Desligar uma fonte apaga os
fatos dela. Prazo opcional por fato (1 a 365 dias). `forget_all` exige `confirm: true` e também desliga as fontes.
Fonte `import` existe no ledger, mas não há tela de importação neste pacote: não há controle de importação na UI.

**Almas.** Proveniência fixa na criação: `declared` (confiança 1.0), `inferred_from_chat` (exige evidência, confiança
máxima 0.8), `user_documents` (exige `consent_documents: true` e evidência, confiança máxima 0.8). Modo `influence` ou
`simulation` (rotulado "imitação do seu estilo"). Uma alma ativa por vez. A prévia não gera texto e diz isso.
Só a dica `active_hint()` é oferecida ao plugin LLM. Sem plugin LLM, a alma ativa não altera respostas (dito na tela).

**Hábitos.** Cada hábito fixa `skill_id` + `skill_version` (a versão habilitada no momento da criação ou edição).
Antes de executar, compara com a versão habilitada agora: se mudou, recusa (`skill_version_changed`) até o usuário revisar.
Editar re-fixa a versão e guarda a anterior; "Versão anterior" volta, mas só se essa versão ainda estiver habilitada.
Execução chama `SkillEngine::run_skill`, então valem todas as verificações do motor. Resultados são histórico (retenção).
Frases de disparo são guardadas e mostradas, mas **não disparam por voz neste pacote** (ligação ao roteador de comandos
pendente).

**Automações.** Agenda `once` (instante futuro) ou `every` (início + intervalo entre 1 min e 30 dias). Fixa a versão da
Skill na criação. Em cada disparo: recheca a versão (deriva pausa a automação com `skill_version_changed`); se o motor
recusar, pausa com o código (revisão obrigatória). Ocupado (`skill_busy`, `agent_busy`, `busy`) adia sem contar.
At-most-once: a próxima data é gravada antes do pedido ao motor. Datas perdidas não viram rajada: a próxima execução é a
primeira data futura. "Executar agora" passa pelas mesmas verificações e não altera a agenda. `once` vira `done` após o
disparo. Automações só rodam com o Core ativo e o timer chamando `tick`.
Limite honesto: "iniciada" (`ok`) significa que o motor aceitou a execução, não que o resultado foi verificado; o
resultado verificado é o da própria Skill (histórico de Skills).

**Histórico.** Sessões de texto (usuário e assistente), até 100 sessões e 200 turnos por sessão, 2000 caracteres por
turno. Título é a primeira linha do usuário (60 caracteres). Abrir, renomear, apagar uma sessão; apagar tudo
(`confirm: true`); exportar o texto de todas (aparece como texto selecionável na tela). Áudio nunca entra aqui.

## 4. Decisões de posição nas abas (docs/UI_IA.md)

Proposta, a ser aprovada: as cinco áreas entram nas abas existentes, sem aba nova.

| Área | Aba › sub-aba | Página (`pageDefs.id`) | Por quê |
|---|---|---|---|
| Histórico (Conversations) | Assistente › **Histórico** (depois de Conversa) | `conversas` | Uso diário; relaciona-se com Conversa |
| Automações | Assistente › **Automações** (depois de Atividade) | `automacoes` | Rotinas do dia a dia |
| Hábitos | Extensões › **Hábitos** (depois de Skills) | `habitos` | Hábito é instância privada de Skill |
| Memória | Permissões › **Memória** (depois de Auditoria) | `memoria` | Consentimento por fonte e exclusão são centro de permissões |
| Almas | Configurações › **Almas** (depois de Privacidade) | `almas` | Perfil de comunicação, ajuste de preferências |
| Devices (PROD-06) | Configurações › Dispositivos (já existe) | `cfg_dispositivos` | Sem mudança neste pacote; a decisão de virar área própria é do dono |

Nenhuma aba de nível 1 nova. Hábitos e Automações não têm aba própria. Se o dono quiser "Devices" como área, a decisão
é dele; hoje o conteúdo já existe.

## 5. Contrato com o Core, a ponte e a casca (passos para o orquestrador)

Estes passos são **a única ligação necessária**. Ordem sugerida: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10.

**Passo 1: `src/lib.rs`** (acrescentar, em ordem alfabética):
```
pub mod automations;
pub mod conversations;
pub mod habits;
pub mod memory;
pub mod personal;
pub mod personal_engine;
pub mod souls;
```
Verificado: uma cópia do crate com estas linhas passa `cargo clippy --lib -- -D warnings` (ver seção 7).

**Passo 2: `src/core.rs`, campo e abertura.**
- Campo: `personal: Option<crate::personal::Personal>` em `Core` (inicializado com `None` em `Core::new`).
- Em `configure_storage` (ou onde o diretório de dados é conhecido): `self.personal = crate::personal::Personal::open(&data_dir.join("personal")).ok();`
  Use o mesmo diretório de dados que o `Storage` usa (o orquestrador confirma o caminho; o `Storage` não expõe um getter
  público de raiz neste código).
- Se `open` falhar, `personal` fica `None` e a ponte mostra indisponível. Não há fallback silencioso.

**Passo 3: `src/protocol.rs`, operações.** Acrescentar ao enum `Operation` (e ao parser estrito):
- `Personal { area: String, payload: serde_json::Value }` (op de fio `"personal"`). Payload é o pedido versionado da área
  (ex.: `{"version":1,"op":"add",...}`); `area` é `memory`, `souls`, `habits`, `automations` ou `conversations`.
- `PersonalExport {}` (op `"personal_export"`): devolve `Personal::export_all(now_ms, retention)`.
- `PersonalEraseAll { confirm: bool }` (op `"personal_erase_all"`): exige `confirm == true` (senão `confirmation_required`),
  depois `Personal::erase_all()`.
- Na tabela de origem de eventos (`origin_of`, `src/protocol.rs` ~linha 410), acrescentar `("personal_", "config")` se
  o orquestrador quiser eventos. Os pedidos novos **não emitem evento** por padrão.
- Resposta: o resultado `Ok(Value)` vai no campo de dados da resposta (o orquestrador adiciona o campo se o envelope
  atual não tiver); o código de erro é o `&'static str` devolvido.

**Passo 4: `src/core.rs`, despacho.** Não passe `self.personal` por referência junto com `self` (empréstimo duplo). Use:
```
let retention = self.preferences.history_retention.window_ms();
let now = crate::protocol::unix_ms();
let mut personal = self.personal.take().ok_or("personal_unavailable")?;
let result = personal.apply(&area, payload, now, retention, self);
self.personal = Some(personal);
```
(`Core` implementa `SkillEngine` em `src/personal_engine.rs`, então `self` é o motor.) `now` é o relógio de parede em ms
(`crate::protocol::unix_ms()`), não `Instant`. Mesmo padrão para `PersonalExport` e `PersonalEraseAll`.

**Passo 5: `src/core.rs`, timer.** No mesmo laço que chama `purge_history_due` (ver `src/core.rs` ~linha 1084 e a chamada
em ~1777), acrescentar o mesmo `take`/devolução e `personal.tick(now, retention, self)`. O resultado (lista de eventos,
sem conteúdo) pode ser ignorado ou emitido como evento de automação. Chamar também em `purge_history_now` (ou no caminho
que trata `history_retention`) para que a troca para `never` apague o histórico sem esperar a próxima operação.

**Passo 6: `src/core.rs`, snapshot.** Onde o snapshot monta blocos (ex.: `skills: self.skills_view(),` ~linha 1170),
acrescentar:
```
personal: match self.personal.as_ref() {
    Some(p) => p.snapshot(crate::protocol::unix_ms(), self.preferences.history_retention.window_ms()),
    None => serde_json::json!({"status": "unavailable"}),
},
```
Bloco `personal` tem as chaves `retention`, `memory`, `souls`, `habits`, `automations`, `conversations`. Cada área tem
`revision` (CAS) e a lista para a tela.

**Passo 7: `app/bridge.py`** (ponte; contrato de snapshot e validação):
- `TOP_KEYS` (linha ~49): acrescentar `'personal'`. **Sem isso, `validate_snapshot` recusa todo snapshot.**
- `validate_snapshot`: validar que `personal`, se presente, é um objeto (`dict`). Nada além disso é obrigatório.
- `SNAPSHOT_SECTION_KEYS` (linha ~1719): acrescentar `'personal'`.
- `SECTION_SIGNALS` (linha ~1718): acrescentar `'personal':'personalChanged'` e declarar o sinal `personalChanged` na ponte.
- Propriedades (QML lê):
  - `@Property('QVariantMap', notify=changed) personal` → `self.snapshot.get('personal') or {}`.
  - `@Property(bool, notify=changed) personalAvailable` → `self.online and isinstance((self.snapshot.get('personal') or {}).get('memory'), dict)`.
  - `@Property('QVariantMap', notify=changed) personalReply` → `self.personal_reply` (inicial `{}`), no formato
    `{"area": str, "code": str, "reply": dict}`.
- Slots:
  - `@Slot(str,str) personalOp(area, payloadJson)`: `json.loads` (JSON inválido → `personal_reply = {area, code: 'invalid_request', reply: {}}`,
    sem envio); depois `self._request('personal', area=area, payload=payload)`. Se `_request` devolver `False`, defina
    `personal_reply` com `core_unavailable` (e não deixe fila de pedido, igual aos outros canais).
  - `@Slot() personalExport()`: `_request('personal_export')`; a resposta vai para `personal_reply` com `area: 'export'`.
  - `@Slot(bool) personalEraseAll(confirmed)`: só envia com `confirmed is True`.
- Ao chegar a resposta do pedido `personal`, copie o código e o dado para `personal_reply` (área vem do pedido em voo).
- `CODE_MESSAGES` (linha ~1095): acrescentar as mensagens em português dos códigos da tabela abaixo. Código sem texto
  faz `core.codeMessage` devolver vazio, e a página mostra "Não foi possível concluir a ação." (aceitável, mas melhor
  ter texto).

Códigos novos (sem texto hoje): `stale_revision`, `consent_required`, `retention_never`, `invalid_text`, `memory_full`,
`invalid_ttl`, `unknown_fact`, `confirmation_required`, `unknown_soul`, `soul_capacity`, `invalid_provenance`,
`invalid_confidence`, `invalid_evidence`, `invalid_skill_id`, `skill_not_enabled`, `habit_capacity`, `habit_paused`,
`skill_version_changed`, `no_previous_version`, `invalid_inputs`, `unknown_habit`, `unknown_automation`,
`automation_capacity`, `schedule_in_past`, `invalid_schedule`, `invalid_status`, `automation_done`, `automation_paused`,
`unknown_session`, `conversation_capacity`, `invalid_request`, `unsupported_version`, `unknown_area`, `ledger_invalid`,
`ledger_unreadable`, `ledger_write_failed`, `ledger_full`, `personal_dir_unavailable`, `personal_unavailable`,
`core_unavailable`, `deferred`, `needs_review`. Códigos do motor de Skills (`skill_busy`, `skill_run`, `destructive_disabled`,
`agent_busy`, `busy`, `unknown_skill`, `manifest_unavailable`) já existem em `CODE_MESSAGES` ou em `COMMAND_CODE_MESSAGES`;
confira antes de duplicar.

**Passo 8: `app/Main.qml`** (dono do arquivo: orquestrador).
- `pageDefs` (linhas ~43-66): acrescentar nas posições indicadas:
  - após `{id: "conversa", ...}`: `{id: "conversas", tab: "assistente", label: "Histórico"},`
  - após `{id: "atividade", ...}`: `{id: "automacoes", tab: "assistente", label: "Automações"},`
  - após `{id: "skills", ...}`: `{id: "habitos", tab: "extensoes", label: "Hábitos"},`
  - após `{id: "perm_auditoria", ...}`: `{id: "memoria", tab: "permissoes", label: "Memória"},`
  - após `{id: "cfg_privacidade", ...}`: `{id: "almas", tab: "configuracoes", label: "Almas"},`
- `availability` (linha ~69): acrescentar `conversas: true, automacoes: true, habitos: true, memoria: true, almas: true`.
  (As páginas mostram "Indisponível" enquanto o Core não responde, então não precisam de condição de plugin.)
- Instanciar as páginas no contêiner (linhas ~245-275), nas mesmas posições: `Conversas {}` após `Conversa {}`,
  `Automacoes {}` após `Atividade {}`, `Habitos {}` após `Skills {}`, `Memoria {}` após `PermAuditoria {}`, `Almas {}` após `CfgPrivacidade {}`.
- Ctrl+1…5 e a ordem das abas não mudam.

**Passo 9: `docs/GAP_AUDIT.md`** (orquestrador). Depois de ligar e rodar os testes de integração, marcar PROD-01 (Memória),
PROD-02 (Almas), PROD-03 (Hábitos), PROD-04 (Automações), PROD-05 (Histórico) como FEITO com evidência. PROD-06 fica
"decisão pendente do dono" (Devices já existe em Configurações › Dispositivos).

**Passo 10: controle de privacidade global (ainda não existe na casca).** Não há controle na UI para "exportar tudo" nem
"apagar dados pessoais". Sugestão para `app/pages/CfgPrivacidade.qml` (dono: WP-4): dois botões, um chama
`core.personalExport()` e mostra o texto em área selecionável (como em Histórico), o outro chama
`core.personalEraseAll(true)` depois de `PConfirm`. Até lá, o Core oferece as operações, mas a tela não.

## 6. Como a ligação chama cada área (referência rápida)

| Página | Lê de `core` | Envia (`core.personalOp`) |
|---|---|---|
| Memória | `personal.memory`, `personalAvailable`, `personalReply`, `historyRetention` | `memory`: consent, add, edit, forget, forget_all, search |
| Almas | `personal.souls` | `souls`: create, update (não usado na tela), activate, deactivate, delete, preview |
| Hábitos | `personal.habits`, `skillsItems` | `habits`: create, edit, set_status, rollback, delete, run |
| Automações | `personal.automations`, `skillsItems` | `automations`: create, set_status, delete, run_now |
| Histórico | `personal.conversations`, `historyRetention` | `conversations`: get, rename, delete, forget_all, export |

Toda chamada leva `version: 1` e, nas mutações, `revision` lido do bloco atual.

## 7. Testes (o que foi rodado e o resultado)

Comandos e resultados, em 2026-10-25, no diretório `/home/lucas/Documentos/Gideon/base`:

1. `cargo test --test personal_areas`: **17 testes, 17 OK, 0 falhas**.
   Cobre: consentimento e CAS (`stale_revision`); edição e busca; retenção `never` e janela (conversas e fatos de
   conversa); TTL; revogar fonte apaga fatos; `forget_all` exige confirmação; regras de proveniência (`invalid_provenance`,
   `consent_required`); dica da alma ativa e prévia; campo desconhecido em `update` recusado; Hábito fixa versão, recusa
   deriva, edita, reverte (só com versão anterior habilitada), pausa; resultados de Hábito respeitam retenção; agendamento
   `once` roda uma vez; `every` não gera rajada; motor ocupado adia; deriva e recusa do motor pausam; validação de agenda
   (`schedule_in_past`, `invalid_schedule`); histórico de automação respeita retenção; Histórico `never` apaga e persiste
   (reabertura); versão e campos desconhecidos recusados; ledgers 0600; ledger corrompido falha fechado; link simbólico
   recusado (`ledger_unreadable`); exportar tudo e apagar tudo sem arquivos no disco.
2. `cargo clippy --test personal_areas -- -D warnings`: **passou** (sem avisos).
3. Cópia do crate com as sete linhas de `lib.rs` (seção 5, passo 1), em diretório de rascunho fora do repositório:
   `cargo clippy --lib -- -D warnings`: **passou**. Isto compila o adaptador `impl SkillEngine for Core` contra o `Core`
   real. Não roda o Core.
4. `rustfmt --edition 2021` nos arquivos Rust novos: aplicado.
5. `qmllint -I app` nos 5 páginas e 4 componentes novos: **sem saída, código 0**.
6. `QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_personal_qml.py`: **8 testes, 8 OK**.
   Cobre: cada página carrega com o contrato de Core falso; Memória envia `add` com revisão e fonte, e mostra recusa do
   Core traduzida; fonte de conversa desligada com `historyRetention == never`; revogar fonte pede confirmação antes de
   enviar; Almas envia `create` com proveniência e prioridades separadas; Hábitos só oferece Skills habilitadas e recusa
   JSON inválido; Automações envia `once` no futuro; Histórico lista, abre (`get`) e exporta.

**Não testado (honesto):**
- Nenhum teste liga o Core real: o adaptador compila, mas não foi executado contra `skill_run` real (nem disparo de
  automação com Skill de verdade, nem deriva com motor real, nem timer).
- A ponte (`app/bridge.py`), `Main.qml` e `protocol.rs`/`core.rs` **não foram alterados**; portanto nenhum slot novo foi
  testado, e `scripts/test_bridge_protocol.py` e `scripts/test_snapshot_contract.py` ainda não cobrem o bloco `personal`
  (vão passar a valer depois do passo 7).
- Durante os testes de QML aparecem linhas `TypeError: Cannot read property 'X' of null` na criação das páginas. As
  asserções passam, porque as ligações se corrigem depois da criação. Não identifiquei a causa; suspeito de interação
  entre o Core falso (um `QObject` Python como propriedade de contexto) e a criação das páginas, mas não confirmei. Deve
  ser verificado com a ponte real antes de dar a casca por pronta.
- Não houve teste visual (captura de tela) nem verificação de acessibilidade/teclado nas telas novas.
- Layout em largura de telefone (400 px) não verificado; as páginas usam `PageFrame`, como as outras.
- Hábitos: as frases de disparo não são acionadas por voz (ligação com o roteador de comandos não existe neste pacote).
- Importação de fatos (fonte `import`) não tem tela.
- Exportar/apagar tudo existe no Core, mas não há controle na casca (passo 10).

## 8. Processo (para o revisor)

- Escrita: só com as ferramentas Write/Edit, exceto dois desvios, reconhecidos aqui: (a) um comando de shell com heredoc
  vazio (`python3 - <<'EOF'`, sem efeito sobre arquivos); (b) uma troca `sed -i` em `scripts/test_personal_qml.py` para
  renomear três chamadas de `findChildren` (conferido por grep depois). Não há outros arquivos alterados fora da lista da seção 1.
- Nenhum commit, push ou deploy. `docs/GAP_AUDIT.md`, `docs/AGENT_STATE.md` e os demais arquivos de outros pacotes não foram tocados.
- Os arquivos `scripts/personal_host.qml` e `scripts/test_personal_qml.py` são novos; o gate pede `QT_QPA_PLATFORM=offscreen`.

## 9. Decisões pendentes do dono

1. Escopo das áreas (PROD-01 a PROD-04): confirmar entrada no roteiro (o Notion D08 diz "não entram automaticamente").
2. Retenção aplicada à memória (decisão desta implementação: retenção governa histórico, não memória curada).
3. Posição das abas (seção 4) e se Devices vira área própria (PROD-06).
4. Habilitar a voz para frases de Hábito (depende do roteador de comandos; fora deste pacote).
5. Controles de exportar e apagar tudo na casca (passo 10).
