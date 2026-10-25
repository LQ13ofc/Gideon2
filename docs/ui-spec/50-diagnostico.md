# Especificação — aba Diagnóstico (50)

Status: proposta de especificação, 2026-10-23. Idioma da interface: português. Sem emojis. Código de referência: `docs/UI_IA.md` §5 (decisões do dono aplicadas abaixo), casca `docs/ui-spec/00-casca.md`.
Fontes lidas: `docs/UI_IA.md`, `docs/ui-spec/00-casca.md`, `docs/UI_NOTION_REQS.md`, `docs/UI_INVENTORY.md` (P5, SB-*, AC-17, NF-13..18, NF-21..23, DU-01/02), `docs/B4.md`, `docs/BASE_UI_MAP.md`, `app/bridge.py`, `app/Main.qml`, `src/protocol.rs`, `src/core.rs`, `src/storage.rs`, `src/pack.rs`, `src/tts.rs`, `scripts/package_tools/gideon-install`, `scripts/package_tools/gideon-launch`.

Convenções:
- Coordenadas em px da janela 1380 × 904 (referência), origem no canto superior esquerdo. Área de conteúdo: x 140–1240, y 236–880 (00-casca).
- Níveis: **Básico** (sempre visível), **Avançado** (atrás de "Mostrar opções avançadas", Configurações › Geral), **Desenvolvimento** (atrás de "Modo desenvolvedor").
- Rótulo marcado **NOVO (precisa de mudança na ponte/Core)** = o item não existe hoje e exige código; o texto da marcação diz exatamente o que falta.
- "Existe" = já existe em `app/bridge.py` ou `app/Main.qml` com o mesmo dado.
- Desenhos ASCII: escala aproximada, 1 coluna ≈ 12 px, 1 linha ≈ 24 px. Os valores exatos estão nas tabelas de regiões. Nos desenhos, textos podem estar encurtados com "…"; o texto exato está na tabela de elementos.

---

## 0. Decisões aplicadas

1. Sub-abas: **Estado · Motores · Recuperação · Desenvolvedor** (esta última só com "Modo desenvolvedor" ligado).
2. A sub-aba **Eventos foi removida** (decisão do dono). Não há terceiro feed de eventos. O histórico do que aconteceu vive em **Assistente › Atividade** (o que o assistente fez) e em **Permissões › Auditoria** (concessões, aprovações, revogações). Diagnóstico mostra só os **últimos erros** dentro de Estado.
3. A **tabela tipo de evento → frase em português** (seção 4) é a **única fonte** da frase de evento. Atividade e Permissões › Auditoria reutilizam a mesma tabela; esta spec a define.
4. Estado mostra o estado do Core e da configuração, e não repete o estado dos motores (DU-01). Os estados de wake, STT e TTS aparecem só em Motores (detalhe) e no resumo do HUD do Assistente.
5. O rodapé de diagnóstico da barra lateral (SB-R1) não existe mais (a casca não tem rodapé). O texto de diagnóstico em linha (DU-02, `DIAG_LABELS`) é substituído pelas frases desta spec. Ver seção 2.
6. Cada sub-aba tem no máximo 3 blocos (cartões) e "Como funciona" recolhível, conforme `docs/UI_IA.md` e a casca.

### 0.1 Aba e sub-abas

- Aba de nível 1: **Diagnóstico**, ícone Breeze `utilities-system-monitor`, 5ª aba, atalho **Ctrl+5** (00-casca). Sempre visível (Notion: "Diagnostics", NT-05/NT-40).
- Badge da aba: **"•N"** (cor Erro #ff7d8a) quando N > 0, onde N = número de motores de voz com estado `Falhou` (wake, STT, TTS) + 1 se `configurationStatus` ≠ `ready`. Some quando N = 0.
- Barra de sub-abas (nível 2, y 56–100): texto 14 px, altura 44, padding horizontal 18 (00-casca). Ordem: `Estado` · `Motores` · `Recuperação` · `Desenvolvedor*`. O asterisco não é texto: indica que a sub-aba só existe com o modo ligado.

```
Barra de sub-abas (nível 2)
 Estado   Motores   Recuperação   Desenvolvedor        <- última só com "Modo desenvolvedor" ligado
 ^ ativa: texto branco negrito + sublinhado 2 px do acento
```

### 0.2 Tabela de sub-abas

| Sub-aba | Condição de aparecimento | Nível | Badge | Ação primária no cabeçalho |
|---|---|---|---|---|
| Estado | sempre | Básico | nenhum | nenhuma |
| Motores | sempre | Básico (nomes e estados); Avançado (última fala, pico, RMS, confiança) | nenhum | nenhuma |
| Recuperação | sempre | Básico (reinício, configuração); Avançado (última configuração boa do motor LLM, catálogo, linha de comando, códigos de saída) | "•1" (Aviso) se `configurationStatus` ≠ `ready`; senão nenhum | nenhuma (o reinício fica no bloco 1, R07) |
| Desenvolvedor | `developerMode` = ligado (NOVO, seção 8) | Desenvolvimento | nenhum | nenhuma |

Regras de sub-aba:
- Sub-aba ativa ao abrir a aba: **Estado**. A última sub-aba usada é lembrada só durante a sessão da janela (não persiste).
- Se o modo desenvolvedor for desligado com a sub-aba Desenvolvedor ativa, a ativa passa para **Estado** e a sub-aba some.
- Atalho **Ctrl+Tab** percorre as sub-abas visíveis (00-casca).

---

## 1. Layout comum da aba (grade)

| Região | x | y | largura | altura | Observação |
|---|---|---|---|---|---|
| Cabeçalho da sub-aba | 32 | 116 | 1316 | 60 | Título 24 px negrito (y 116); subtítulo 14 px (y 146). Padrão 00-casca. |
| Faixa de resumo | 32 | 184 | 1316 | 40 | Frase-resumo à esquerda; badges à direita. Padrão 00-casca. |
| Área de conteúdo | 140 | 236 | 1100 | até 880 | Centralizada acima de 1240 px de janela. Rola na vertical se não couber; cabeçalho e barras ficam fixos. |
| Grade | — | — | 12 colunas, gap 16 | — | Coluna = (1100 − 11 × 16) ÷ 12 = 77 px. Span 6 = 542 px; span 12 = 1100 px. |

Largura menor que 1240 px: a área de conteúdo tem largura da janela − 64, com x = 32 (não centralizada). Largura menor que 900 px (reflow): todo bloco ocupa span 12, cabeçalho empilha título e ação, e as colunas internas dos blocos empilham em uma coluna. Abas viram só ícones com tooltip (00-casca). Mínimo da janela 720 × 520.

Cartões: raio 14, padding 20, título 17 px semibold, corpo 14 px, legenda 12 px. Bloco "Como funciona": linha recolhível de altura 56 com título e uma linha de resumo, recolhido por padrão, ícone ▸/▾ à direita.

---

## 2. Como os códigos crus viram frases

### 2.1 Regras

- **R-01** Nenhum código cru (`stt_failed`, `plugin_crashed`, `running`, `replay_finished`, IDs de plugin, hashes) aparece no nível **Básico**. Em **Avançado**, o código aparece depois da frase, em linha própria, 12 px, cor #9db0e0, no formato `código: <valor>`. Em **Desenvolvimento** (sub-aba Desenvolvedor), identificadores técnicos aparecem crus, porque são a ferramenta de teste.
- **R-02** Frases de estado de motor e de sessão usam **inicial maiúscula** ("Falhou", "Em espera"). Frases de erro e de evento usam inicial maiúscula e ponto final quando são frase completa.
- **R-03** Código sem frase na tabela 3.x **não** pode mostrar o código no nível Básico. Texto de fallback no Básico: `Core recusou a ação.` O código vai para Avançado. Hoje `code_message` (app/bridge.py, `def code_message`) devolve `Core recusou a ação: {code}`: isso precisa mudar. **NOVO (precisa de mudança na ponte/Core):** `code_message` passa a devolver `Core recusou a ação.` e a expor o código separadamente para o nível Avançado.
- **R-04** `DIAG_LABELS` (app/bridge.py, linha 15) traduz em minúsculas ("indisponível", "em espera"), enquanto `statusLabels` (app/Main.qml, linha 111) traduz com inicial maiúscula. **NOVO (precisa de mudança na ponte/Core):** remover `DIAG_LABELS` e o rodapé SB-R1. Diagnóstico usa só as tabelas desta seção.
- **R-05** Texto do usuário usa **"capacidade"**, nunca "capability". Os rótulos "Cancelar" do Diagnóstico nunca são "Cancelar" sozinhos (ver seção 8.4).
- **R-06** Estado offline do cliente: **"Core desconectado"** (cor neutra). Hoje `stateLabels.offline` diz "Core indisponível" (app/Main.qml, linha 110). **NOVO (precisa de mudança na ponte/Core):** trocar esse texto para "Core desconectado" e usar a mesma frase em toda a aplicação (pílula da casca também usa "Core desconectado", 00-casca).
- **R-07** Formatos pt-BR: decimal com vírgula ("3,2 s"); milhar com espaço fino ("28 800"); hora `HH:MM:SS` de 24 horas; hashes mostrados com 16 caracteres + "…" (Desenvolvedor) ou 12 caracteres + "…" (linhas de plugin).
- **R-08** Conteúdo sensível nunca aparece em Diagnóstico: texto de transcrição, texto de comando, argumentos de ferramenta, texto de plugin, chave de API, `request_id`, `session_id`. Eventos mostram só o tipo (tabela 4) e a hora.
- **R-09** Controle desabilitado mostra o motivo em texto de 12 px abaixo (00-casca: "Indisponível: <motivo>") e em tooltip.
- **R-10** Diagnóstico não concede, aprova ou revoga nada. Não há botão de permissão nesta aba.

### 2.2 Como o estado é lido

Tudo vem do snapshot do Core por propriedades da ponte já existentes (`core.wakeStatus`, `core.sttStatus`, `core.speechStatus`, `core.state`, `core.configurationStatus`, `core.pluginItems`, `core.hubEntries`). Sem consulta extra (polling): a ponte já atualiza a cada snapshot (00-casca, `docs/BASE_UI_MAP.md`: ativo 150 ms, ocioso 1 s, watchdog 2 s, reconexão 0,5–5 s).

---

## 3. Tradução de códigos (tabelas de exibição)

Coluna **Origem**: "existe" = texto já usado no QML ou na ponte; "NOVO" = precisa ser criado (marcado NOVO (precisa de mudança na ponte/Core)).

### 3.1 Motores de voz

**Wake** (`wake_status`; lista `WAKE_STATES` em app/bridge.py)

| Código | Frase | Tom do badge | Observação | Origem |
|---|---|---|---|---|
| `unavailable` | Indisponível | Neutro #9db0e0 | | existe |
| `starting` | Iniciando | Info #7693ff | | existe |
| `replaying` | Reproduzindo | Info #7693ff | replay de teste (`--wake-replay`) | existe |
| `replay_finished` | Replay encerrado | Neutro #9db0e0 | Nota obrigatória: "Replay encerrado não significa que o wake esteja armado." | existe |
| `failed` | Falhou | Erro #ff7d8a | | existe |

**Transcrição** (`stt_status`; `STT_STATES`)

| Código | Frase | Tom | Origem |
|---|---|---|---|
| `unavailable` | Indisponível | Neutro | existe |
| `starting` | Iniciando | Info | existe |
| `ready` | Pronto | Sucesso #5ee0a0 | existe |
| `failed` | Falhou | Erro | existe |

**Resposta em voz** (`speech_status`; `SPEECH_STATES`)

| Código | Frase | Tom | Origem |
|---|---|---|---|
| `unavailable` | Indisponível | Neutro | existe |
| `idle` | Em espera | Neutro | existe |
| `speaking` | Respondendo | Info | existe |
| `completed` | Concluído | Sucesso | existe |
| `failed` | Falhou | Erro | existe |
| `muted` | Mudo | Neutro | existe |
| `disabled` | Desligado | Neutro | existe |
| `cancelled` | Cancelado | Neutro | existe |
| `timed_out` | Tempo esgotado | Erro | existe |
| `audio_error` | Erro de áudio | Erro | existe |
| `stt_failed` | Falha na transcrição | Erro | existe |
| `stt_unavailable` | Transcrição indisponível | Aviso #f2c15c | existe |
| `transcript_final` | Transcrição final | Neutro | existe |
| `capture_completed` | Captura concluída | Neutro | existe |
| `no_speech` | Sem fala detectada | Aviso | existe |
| `capture_too_long` | Captura longa demais | Aviso | existe |

**Motor LLM (plugin)**: ver 3.3 (estado do plugin).

### 3.2 Sessão e configuração do Core

| Código (campo) | Frase | Tom | Onde | Origem |
|---|---|---|---|---|
| `state` = `idle` | Em espera | Neutro | Estado | existe |
| `state` = `capturing` | Ouvindo | Info | Estado | existe |
| `state` = `transcribing` | Transcrevendo | Info | Estado | existe |
| `state` = `executing` | Executando | Info | Estado | existe |
| `state` = `speaking` | Respondendo | Info | Estado | existe |
| cliente sem conexão | Core desconectado | Neutro | Estado | NOVO (precisa de mudança na ponte/Core): troca de "Core indisponível" (R-06) |
| `configuration_status` = `ready` | Pronta | Sucesso | Estado | existe |
| `configuration_status` = `safe_mode` | Modo seguro | Erro | Estado, Recuperação | existe (`stateLabels`) |
| `configuration_status` = `restart_required` | Reinício necessário | Aviso | Estado, Recuperação | existe (`stateLabels`) |
| sem conexão (configuração) | Indisponível | Neutro | Estado | existe |

Mensagens de configuração (exatas, vindas de `configurationMessage`, app/bridge.py):

| Condição | Texto exato |
|---|---|
| `safe_mode` com recuperação disponível | Modo seguro: configuração inválida preservada; áudio e comandos bloqueados |
| `safe_mode` sem recuperação | Modo seguro: arquivo excede o limite de recuperação automática; conteúdo preservado |
| `restart_required` | Configuração salva; reinicie o Core para ativar os recursos |
| `ready` | Nenhuma ação pendente |

### 3.3 Plugins (estado de cada plugin em `pluginItems`)

| Código (`state`) | Frase | Tom | Origem |
|---|---|---|---|
| `disabled` | Desativado | Neutro | existe (`pluginStateText`) |
| `starting` | Iniciando | Info | existe |
| `running` | Ativo (sandbox, sem rede) | Sucesso | existe |
| `failed` | Falhou | Erro | existe (mostra o motivo abaixo) |
| `stopped` | Parado | Neutro | existe |
| `quarantined` | Em quarentena | Erro | existe |

Motivo de falha (`last_error`, `PLUGIN_LAST_ERRORS`). Se o código não estiver aqui, usar R-03.

| Código (`last_error`) | Frase | Origem |
|---|---|---|
| `plugin_crashed` | Plugin encerrou com falha | existe (`CODE_MESSAGES`) |
| `plugin_not_runnable` | Plugin não pode ser executado | existe |
| `plugin_cpu_exceeded` | Plugin passou do limite de processamento | NOVO (precisa de mudança na ponte/Core): adicionar a `CODE_MESSAGES` |
| `plugin_output_invalid` | Plugin devolveu uma resposta inválida | NOVO (precisa de mudança na ponte/Core): adicionar |
| `plugin_start_failed` | Plugin não conseguiu iniciar | NOVO (precisa de mudança na ponte/Core): adicionar |
| `plugin_quarantined` | Plugin em quarentena | NOVO (precisa de mudança na ponte/Core): adicionar |
| `handshake_timeout` | Plugin não respondeu ao iniciar | NOVO (precisa de mudança na ponte/Core): adicionar |
| `handshake_mismatch` | Plugin não é a versão esperada | NOVO (precisa de mudança na ponte/Core): adicionar |

### 3.4 Catálogo do Hub e armazenamento

| Código | Frase | Origem |
|---|---|---|
| `status` = `not_installed` | Não instalado | existe |
| `status` = `update_available` | Atualização disponível | existe |
| `status` = `installed` com plugin ativo | Instalado · ativo (sandbox, sem rede) | existe |
| `status` = `installed` com plugin desativado | Instalado · desativado (sem execução) | existe |
| `payload_staged` verdadeiro e não instalado | Pacote verificado em staging; não instalado | existe |
| `status` = `incompatible` (motivo `reason`) | Incompatível: <motivo> | existe |
| motivo `ledger_missing` | Registro de instalação ausente | NOVO (precisa de mudança na ponte/Core): adicionar |
| motivo `ledger_invalid` | Registro de instalação inválido | NOVO (precisa de mudança na ponte/Core): adicionar |
| `hub_import_busy` | Importação do catálogo em andamento | existe |
| `hub_storage_error` | Falha ao gravar o registro do catálogo. | NOVO (precisa de mudança na ponte/Core): adicionar |
| `plugin_storage_error` | Falha ao gravar o registro dos plugins. | NOVO (precisa de mudança na ponte/Core): adicionar |
| `preferences_storage_error` | Falha ao gravar as preferências. | NOVO (precisa de mudança na ponte/Core): adicionar |
| `preferences_unavailable` | Preferências indisponíveis no momento. | NOVO (precisa de mudança na ponte/Core): adicionar |
| `configuration_not_ready` | Configuração ainda não está pronta. | NOVO (precisa de mudança na ponte/Core): adicionar |
| `hub_import_timeout` | Importação expirou antes de terminar. | NOVO (precisa de mudança na ponte/Core): adicionar |

### 3.5 Ferramentas, agente e conversa (usados em Estado: últimos erros)

| Código | Frase | Origem |
|---|---|---|
| tool `pending` | aguardando sua decisão | existe (`toolStateText`) |
| tool `authorized` | autorizada; executando | existe |
| tool `executed` | executada | existe |
| tool `denied` | negada | existe |
| tool `failed` | falhou | existe |
| tool `expired` | expirada | existe |
| tool `cancelled` | cancelada | existe |
| agente `thinking` | Pensando | existe (`AGENT_STATE_LABELS`) |
| agente `waiting_tool` | Executando ferramenta | existe |
| agente `awaiting_approval` | Aguardando sua aprovação | existe |
| agente `done` | Concluído | existe |
| agente `failed` | Falhou | existe |
| agente `aborted` | Abortado | existe |
| agente `blocked` | Bloqueado | existe |
| conversa `waiting` | Aguardando resposta | existe (`CHAT_STATE_LABELS`) |
| conversa `error` | Erro | existe |

### 3.6 Códigos de erro usados em Diagnóstico (subconjunto de `CODE_MESSAGES`)

Diagnóstico mostra estes códigos em "Últimos erros", Recuperação e Motores. Todos os demais continuam em `CODE_MESSAGES` e seguem R-03.

| Código | Frase | Origem |
|---|---|---|
| `busy` | Core ocupado; tente novamente em instantes | existe |
| `input_disabled` | Entrada de texto indisponível no momento | existe |
| `no_lkg` | Não há configuração anterior salva para restaurar | existe |
| `stale_llm_revision` | Configuração do motor mudou; reabra o diálogo | existe |
| `stale_hub_revision` | Catálogo mudou; atualize e tente de novo | existe |
| `stale_plugin_revision` | Estado do plugin mudou; atualize e tente de novo | existe |
| `llm_storage_error` | Falha ao gravar a configuração do motor | existe |
| `secrets_storage_error` | Falha ao gravar o cofre de chaves | existe |
| `virtual_input_disabled` (resposta do wake de teste) | Entrada de teste não ativa no Core | NOVO (precisa de mudança na ponte/Core): adicionar |
| `unknown_capability` | Capacidade do motor LLM desconhecida | existe |
| `capability_timeout` | Plugin não respondeu no prazo | existe |
| `timed_out` | Tempo esgotado | existe |

---

## 4. Tipos de evento → frase em português (fonte única)

**Esta tabela é a única fonte da frase de evento.** Assistente › Atividade (spec da aba Assistente, ainda a ser escrita) e Permissões › Auditoria (spec 30-permissoes.md) reutilizam esta mesma tabela e não criam frases próprias. Diagnóstico › Estado (Últimos erros) usa a coluna E.

Colunas: **Tipo** = valor que o Core registra no anel de eventos (64 entradas, `src/core.rs` `emit`). **Frase** = texto exato mostrado. **Categoria** = filtro (Atividade: Tudo · Comandos · Skills · Agente · Erros; Auditoria: Plugin · Skill · Conexão · Comando). **A** = aparece em Atividade. **P** = aparece em Permissões › Auditoria. **E** = aparece em Últimos erros. "—" = não exibido.

Regras:
- **EV-R1** Frase de evento: `<Frase>`. Quando o tipo tem sufixo (`agent_blocked:<motivo>`), a frase base é seguida de ` · <motivo em frase>` (linha 3.5 e abaixo).
- **EV-R2** Sem conteúdo: nenhuma frase desta tabela mostra texto, argumento ou identificador. Tipos marcados "—" não aparecem em lugar nenhum.
- **EV-R3** Hora: cada evento mostra a hora de recebimento pela ponte (`HH:MM:SS`). O anel do Core não tem hora. **NOVO (precisa de mudança na ponte/Core):** a ponte registra a hora de recebimento de cada `sequence` novo. Sem hora conhecida: "—".
- **EV-R4** Ordem: mais recente primeiro, pelo campo `sequence` (decrescente).
- **EV-R5** O anel tem 64 entradas e reinicia com o Core. Qualquer lista derivada diz isso em "Como funciona" (em Estado).

| Tipo (kind) | Frase | Categoria | A | P | E | Observação |
|---|---|---|---|---|---|---|
| `session_started` | Sessão de voz iniciada | Comando | sim | sim | não | |
| `transcript_partial` | — | — | não | não | não | Parcial nunca vira ação; não exibido. |
| `transcript_final` | Fala reconhecida | Comando | sim | sim | não | Sem texto. |
| `capture_completed` | Captura de fala concluída | Comando | sim | sim | não | |
| `no_speech` | Nenhuma fala detectada | Comando | sim | sim | não | |
| `capture_too_long` | Captura longa demais | Comando | sim | sim | sim | |
| `cancelled` | Sessão cancelada | Comando | sim | sim | não | |
| `timed_out` | Tempo esgotado na sessão de voz | Comando | sim | sim | sim | |
| `audio_error` | Erro de áudio na captura | Comando | sim | sim | sim | |
| `stt_failed` | Falha na transcrição | Comando | sim | sim | sim | |
| `stt_unavailable` | Transcrição indisponível | Comando | sim | sim | sim | |
| `speech_started` | Resposta em voz iniciada | Comando | sim | sim | não | |
| `speech_completed` | Resposta em voz concluída | Comando | sim | sim | não | |
| `tts_failed` | Falha na resposta em voz | Comando | sim | sim | sim | |
| `wake_failed` | Falha na detecção da frase de despertar | Plugin | não | sim | sim | Área de Últimos erros: "Motores". |
| `command_authorized` | Comando autorizado | Comando | sim | sim | não | |
| `command_success` | Comando concluído com efeito verificado | Comando | sim | sim | não | |
| `command_failed` | Comando não concluído: efeito não verificado | Comando | sim | sim | sim | |
| `tool_proposed` | Ferramenta proposta; aguarda sua decisão | Comando | sim | sim | não | |
| `tool_authorized` | Ferramenta autorizada por você | Comando | sim | sim | não | |
| `tool_denied` | Ferramenta negada | Comando | sim | sim | não | |
| `tool_executed` | Ferramenta executada | Comando | sim | sim | não | |
| `tool_failed` | Ferramenta falhou | Comando | sim | sim | sim | |
| `agent_started` | Agente iniciado | Agente | sim | sim | não | |
| `agent_step` | Passo do agente | Agente | sim | sim | não | |
| `agent_tool` | Ferramenta usada pelo agente | Agente | sim | sim | não | |
| `agent_done` | Agente concluiu | Agente | sim | sim | não | |
| `agent_failed` | Agente falhou | Agente | sim | sim | sim | |
| `agent_aborted` | Agente abortado | Agente | sim | sim | não | |
| `agent_blocked` | Agente bloqueado | Agente | sim | sim | sim | Sufixo `:loop_blocked` → "o modelo repetiu a mesma ação"; `:stale_screen` → "a tela mudou desde a observação"; sem sufixo → "motivo não informado". Ex.: "Agente bloqueado · o modelo repetiu a mesma ação". |
| `skill_validated` | Skill validada | Skill | sim | sim | não | |
| `skill_approved` | Skill aprovada | Skill | sim | sim | não | |
| `skill_enabled` | Skill habilitada | Skill | sim | sim | não | |
| `skill_run_started` | Execução de skill iniciada | Skill | sim | sim | não | |
| `skill_step` | Passo de skill executado | Skill | sim | sim | não | |
| `skill_run_done` | Execução de skill concluída | Skill | sim | sim | não | |
| `skill_run_failed` | Execução de skill falhou | Skill | sim | sim | sim | |
| `skill_rolled_back` | Skill voltou à versão anterior | Skill | sim | sim | não | |
| `skill_service_denied` | Skill bloqueada: serviço não permitido | Skill | sim | sim | não | |
| `skill_plugin_validate` | Validação de skill pelo plugin | Skill | sim | não | não | |
| `skill_plugin_dry_run` | Simulação de skill pelo plugin | Skill | sim | não | não | |
| `skill_plugin_list` | Lista de skills do plugin consultada | Skill | sim | não | não | |
| `skill_draft_put` | Rascunho de skill salvo | Skill | sim | sim | não | |
| `skill_exported` | Skill exportada | Skill | sim | sim | não | Sem caminho do arquivo (AC-13 fica a cargo da tela de Skills). |
| `skill_import_previewed` | Prévia de importação de skill | Skill | sim | sim | não | |
| `skill_imported` | Skill importada como rascunho | Skill | sim | sim | não | |
| `hub_import_started` | Importação de pacote iniciada | Plugin | não | sim | não | |
| `hub_payload_staged` | Pacote verificado e guardado; não instalado | Plugin | não | sim | não | |
| `hub_import_cancelled` | Importação de pacote cancelada | Plugin | não | sim | não | |
| `hub_import_timeout` | Importação de pacote expirou | Plugin | não | sim | sim | |
| `hub_permissions_approved` | Permissões do plugin aprovadas | Plugin | não | sim | não | |
| `hub_plugin_installed` | Plugin instalado (desativado) | Plugin | não | sim | não | |
| `hub_plugin_updated` | Plugin atualizado (desativado) | Plugin | não | sim | não | |
| `hub_plugin_rolled_back` | Plugin voltou à versão anterior | Plugin | não | sim | não | |
| `hub_plugin_removed` | Plugin removido | Plugin | não | sim | não | |
| `hub_staged_discarded` | Pacote guardado descartado | Plugin | não | sim | não | |
| `plugin_enabled` | Plugin ativado (sandbox, sem rede) | Plugin | não | sim | não | |
| `plugin_disabled` | Plugin desativado | Plugin | não | sim | não | |
| `plugin_revoked` | Permissões do plugin revogadas | Plugin | não | sim | não | |
| `plugin_started` | Plugin iniciado | Plugin | sim | sim | não | |
| `plugin_stopped` | Plugin parado | Plugin | sim | sim | não | |
| `plugin_failed` | Plugin falhou | Plugin | sim | sim | sim | |
| `capability_invoked` | Capacidade invocada | Plugin | sim | sim | não | Sem entrada nem saída. |
| `capability_partial` | Resposta parcial recebida | Plugin | sim | sim | não | Conteúdo não exibido. |
| `plugin_log` | — | — | não | não | não | Conteúdo de log de plugin: nunca exibido. |
| `llm_fallback_used` | Modelo de reserva respondeu | Plugin | sim | sim | não | Resolve AC-16 no histórico. |
| `llm_configured` | Motor LLM configurado | Configuração | não | sim | não | |
| `llm_marked_good` | Configuração do motor marcada como boa | Configuração | não | sim | não | |
| `llm_rolled_back` | Motor LLM voltou à configuração anterior | Configuração | não | sim | não | |
| `secret_set` | Chave de provedor salva | Configuração | não | sim | não | Sem a chave. |
| `secret_cleared` | Chave de provedor removida | Configuração | não | sim | não | |
| `preferences_updated` | Preferências salvas | Configuração | não | sim | não | |
| `configuration_recovered` | Configuração recuperada; reinício necessário | Configuração | não | sim | sim | |
| `connection_added` | Conta adicionada | Conexão | não | sim | não | |
| `connection_connected` | Conta conectada | Conexão | não | sim | não | |
| `connection_consented` | Escopo concedido | Conexão | não | sim | não | |
| `connection_refreshed` | Acesso renovado | Conexão | não | sim | não | |
| `connection_expired` | Acesso expirou | Conexão | não | sim | sim | |
| `connection_disconnected` | Conta desconectada | Conexão | não | sim | não | |
| `connection_revoked` | Acesso revogado | Conexão | não | sim | não | |
| `connection_removed` | Conta removida | Conexão | não | sim | não | |
| `connection_trusted` | Ferramentas da conta confiadas | Conexão | não | sim | não | |
| `connection_call` | Chamada a conta registrada | Conexão | sim | sim | não | Sem parâmetros. |
| `registry_visual_allowed` | Fallback visual permitido | Conexão | não | sim | não | |
| `registry_visual_revoked` | Fallback visual revogado | Conexão | não | sim | não | |
| `registry_visual_run` | Ação visual executada | Conexão | sim | sim | não | |
| `screen_capture` | Captura de tela (percepção) | Percepção | não | sim | não | Ação de percepção. |
| `input_action` | Ação de teclado ou mouse | Percepção | não | sim | não | |
| `audio_action` | Ação de áudio | Percepção | não | sim | não | |
| `mic_action` | Ação de microfone | Percepção | não | sim | não | |
| `camera_action` | Ação de câmera | Percepção | não | sim | não | |
| `synthetic_action` | Ação simulada (sem hardware real) | Percepção | não | sim | não | Selo SINTÉTICO por extenso (seção 8.5). |

Observação: `speaking`, `connection_available`, `skill_disabled` e `connection_limit` não são registrados no anel de eventos (são estados ou códigos de resposta) e por isso não aparecem na tabela.

---

## 5. Sub-aba Estado

### 5.1 Objetivo
Mostrar, em uma olhada, se o Core está conectado, em qual configuração ele está, qual é o perfil da Base, a privacidade, o interruptor do modo desenvolvedor e os últimos erros desta sessão.

### 5.2 Condição de aparecimento
Sempre visível. Primeira sub-aba da aba Diagnóstico.

### 5.3 Nível
Básico. O código de cada erro aparece só em Avançado (R-01).

### 5.4 Layout em grade (x, y, largura, altura em px)

| Região | x | y | largura | altura | Span | Conteúdo |
|---|---|---|---|---|---|---|
| Faixa de resumo | 32 | 184 | 1316 | 40 | — | Frase-resumo e badge de erros (elementos S01–S02) |
| Bloco 1 "Core e configuração" | 140 | 236 | 542 | 200 | 6 | Conexão, estado, sessão, configuração (S03–S10) |
| Bloco 2 "Base e privacidade" | 698 | 236 | 542 | 200 | 6 | Perfil, idiomas, pacote, versão, privacidade, modo desenvolvedor (S11–S20) |
| Bloco 3 "Últimos erros" | 140 | 452 | 1100 | 230 | 12 | Até 5 erros, estado vazio ou offline (S21–S27) |
| Como funciona | 140 | 698 | 1100 | 56 | 12 | Recolhível (S28) |

Reflow < 900 px: blocos 1 e 2 empilham (span 12); bloco 3 continua span 12; "Como funciona" fica abaixo.

### 5.5 Wireframe (área de conteúdo, escala aproximada)

```
┌─ Core e configuração ──────────────────────┐ ┌─ Base e privacidade ───────────────────────┐
│ Conectado ao Core                          │ │ Perfil: Desenvolvimento · áudio virtual    │
│ Estado atual: Em espera                    │ │ Idioma da interface: português             │
│ Sessão de voz: nenhuma                     │ │ Idioma da voz: inglês                      │
│                                            │ │ Pacote de voz: Base de voz virtual         │
│ Configuração: Pronta                       │ │ Versão da Base: x.y.z                      │
│ Nenhuma ação pendente                      │ │ Sem histórico de conversas. Áudio e…       │
│                                            │ │ Modo desenvolvedor        [ ] Desligado    │
└────────────────────────────────────────────┘ └────────────────────────────────────────────┘

┌─ Últimos erros ───────────────────────────────────────────────────────────────────────────┐
│ Erros desta sessão, mais recentes primeiro. Máximo de 5.                                  │
│                                                                                           │
│ 14:02:11 · Voz · Falha na transcrição                                                     │
│ 14:01:47 · Plugin · Plugin encerrou com falha                                             │
│ —        · Motores · Falhou: detector de frase                                            │
│                                                                                           │
│ Sem erros: "Nenhum erro nesta sessão."  [Ver Atividade]                                   │
│                                                                                           │
│                                                                                           │
└───────────────────────────────────────────────────────────────────────────────────────────┘

┌─ Como funciona ───────────────────────────────────────────────────────────────────────────┐
│ O Core informa o que aconteceu. Detalhes dos motores: aba Motores.                        │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.6 Elementos

| # | Região / posição (x, y, l, a) | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| S01 | Cabeçalho título (32, 116) | Texto 24 px negrito | `Estado` | fixo | — | — | Básico |
| S02 | Cabeçalho subtítulo (32, 146) | Texto 14 px #9db0e0 | `Core, configuração, perfil da Base e últimos erros desta sessão.` | fixo | — | — | Básico |
| S03 | Faixa de resumo (32, 184, 1316, 40) — frase | Texto 14 negrito | `Core conectado · configuração pronta · sem erros recentes` (a) · `Core conectado · configuração pronta · 1 erro recente` / `… · N erros recentes` (b) · `Core conectado · reinício necessário` (c) · `Core conectado · modo seguro` (d) · `Core desconectado · tentando reconectar` (e) | `core.connected`, `core.configurationStatus`, contagem de S21 | — | (a)–(e) conforme condições | Básico |
| S04 | Faixa de resumo — badge à direita (x 1236, alinhado a 1348 − 16) | Badge (altura 22) | `Erros: N` | contagem de linhas válidas de S21 | Clique rola a página até o bloco 3 | Neutro se N = 0; Erro se N > 0 | Básico |
| S05 | Bloco 1 (140, 236, 542, 200) — título | Título 17 px semibold | `Core e configuração` | fixo | — | — | Básico |
| S06 | Bloco 1 — linha de conexão (y 276) | Ponto + texto 14 px | `Conectado ao Core` (ponto Sucesso) · `Core desconectado` (ponto Neutro) | `core.connected` | — | conectado / desconectado | Básico |
| S07 | Bloco 1 — legenda (y 300) | Legenda 12 px #9db0e0 | `Tentando reconectar sozinho (intervalo de 0,5 a 5 s).` | fixo | — | só desconectado | Básico |
| S08 | Bloco 1 — estado atual (y 324) | Texto 14 | `Estado atual: <frase>` (frase da tabela 3.2 de `core.state`; desconectado: `Core desconectado`) | `core.state` | — | Em espera, Ouvindo, Transcrevendo, Executando, Respondendo, Modo seguro, Reinício necessário, Core desconectado | Básico |
| S09 | Bloco 1 — sessão (y 348) | Texto 14 | `Sessão de voz: nenhuma` · `Sessão de voz: em andamento` | `core.sessionId` vazio / não vazio | — | — | Básico |
| S10 | Bloco 1 — configuração (y 372) | Badge + texto 14 | badge: `Pronta` (Sucesso) · `Modo seguro` (Erro) · `Reinício necessário` (Aviso) · `Indisponível` (Neutro, desconectado). Texto ao lado: `Configuração: <badge>` | `core.configurationStatus` | — | conforme badge | Básico |
| S11 | Bloco 1 — mensagem da configuração (y 396) | Texto 14 | `Nenhuma ação pendente` (pronta) · texto de `configurationMessage` (seção 3.2) (modo seguro ou reinício) | `core.configurationMessage` | — | conforme configuração | Básico |
| S12 | Bloco 1 — link (y 420) | Botão secundário (altura 30) | `Abrir Recuperação` | — | Vai para a sub-aba Recuperação | só se configuração ≠ pronta | Básico |
| S13 | Bloco 1 — legenda de bloqueio (y 300) | Legenda 12 px | `Preferências e modo desenvolvedor ficam bloqueados até a sessão terminar.` | `core.sessionId` | — | só com sessão ativa | Básico |
| S14 | Bloco 2 "Base e privacidade" (698, 236, 542, 200) — título | Título 17 px semibold | `Base e privacidade` | fixo | — | — | Básico |
| S15 | Bloco 2 — perfil (y 276) | Texto 14 | `Perfil: <frase de perfil>`. Frase: `Desenvolvimento · áudio virtual · inglês` para o escopo `dev_virtual_en`. Sem dado: `Perfil: não informado` | `core.snapshotPack` → `base_pack.scope` (mapeamento SCOPE_LABELS) | — | desconectado: `Perfil: —` | Básico |
| S16 | Bloco 2 — idioma da interface (y 300) | Texto 14 | `Idioma da interface: português` | fixo | — | — | Básico |
| S17 | Bloco 2 — idioma da voz (y 324) | Texto 14 + legenda 12 px | `Idioma da voz: inglês` · legenda `Português para voz não está comprovado.` | `base_pack.language` (`LANGUAGE_LABELS`) | — | — | Básico |
| S18 | Bloco 2 — pacote de voz (y 348) | Texto 14 | `Pacote de voz: <nome>`; sem mapeamento: `Pacote de voz da Base` | `base_pack.id` (mapeamento PACK_LABELS) | — | — | Básico |
| S19 | Bloco 2 — versão e privacidade (y 372) | Texto 14 | `Versão da Base: <versão>` (sem dado: `Versão da Base: não informada`) · `Sem histórico de conversas. Áudio e legendas ficam só em memória.` | versão: NOVO (precisa de mudança na ponte/Core): `packageInfo.version` (lido do PACKAGE.json do pacote instalado); privacidade: fixo | — | — | Básico |
| S20 | Bloco 2 — modo desenvolvedor (y 396) | Rótulo 14 negrito + interruptor 40×24 + estado | `Modo desenvolvedor` · `Desligado` / `Ligado` · legenda 12 px `Mostra a aba Desenvolvedor, com ferramentas de teste. Não concede permissões.` | NOVO (precisa de mudança na ponte/Core): `core.developerMode` (seção 8.2) | Desligado→Ligado: abre o diálogo da seção 8.3. Ligado→Desligado: sem diálogo; toast `Modo desenvolvedor desligado.` Bloqueado em sessão: ver S13 | desligado, ligado, bloqueado (sessão) | Básico |
| S21 | Bloco 3 "Últimos erros" (140, 452, 1100, 230) — título | Título 17 px semibold | `Últimos erros` | fixo | — | — | Básico |
| S22 | Bloco 3 — legenda (y 484) | Legenda 12 px | `Erros desta sessão, mais recentes primeiro. Máximo de 5.` | fixo | — | — | Básico |
| S23 | Bloco 3 — linhas 1 a 5 (y 512, 536, 560, 584, 608; altura 24 cada) | Linha de lista 14 px | `HH:MM:SS · <Área> · <frase>`. Exemplo: `14:02:11 · Voz · Falha na transcrição`. Nível Avançado acrescenta ` · código: <código>` em linha própria, 12 px. Hora sem dado: `—` | NOVO (precisa de mudança na ponte/Core): propriedade `recentEvents` (snapshot `events`, anel de 64) + hora de recebimento (EV-R3); frase pela tabela 4 (coluna E); erros de plugin por `pluginItems[].last_error` (tabela 3.3) | Linha não é clicável (somente leitura) | ver regras R-S1 | Básico (código: Avançado) |
| S24 | Bloco 3 — estado vazio (moldura tracejada, y 512, altura 140) | Estado vazio | `Nenhum erro nesta sessão.` | contagem de S21 = 0 | — | vazio | Básico |
| S25 | Bloco 3 — link no estado vazio (y 640) | Botão secundário (altura 30) | `Ver Atividade` | — | Vai para Assistente › Atividade com filtro "Erros" | sempre no estado vazio | Básico |
| S26 | Bloco 3 — offline (y 512) | Texto 14 | `Sem dados: o Core está desconectado.` | `core.connected` | — | só desconectado | Básico |
| S27 | Bloco 3 — área (y 512) | Lista | Área (texto da coluna Área): `Voz`, `Comando`, `Ferramenta`, `Agente`, `Skill`, `Plugin`, `Motores`, `Motor LLM`, `Configuração`, `Conexão`, `Catálogo` | regra da categoria da tabela 4 | — | — | Básico |
| S28 | Como funciona (140, 698, 1100, 56) — título e resumo | Bloco recolhível | `Como funciona` · resumo: `O que o Core informou e os erros desta sessão.` · expandido: `Esta tela mostra fatos do Core e não muda nada. A configuração fica em Configurações; os motores estão na aba Motores. A lista de erros some quando o Core reinicia.` | fixo | ▸/▾ expande e recolhe | recolhido por padrão | Básico |

Regras específicas (Estado):
- **R-S1** Últimos erros: entram (1) os eventos do anel com tipo marcado **E** na tabela 4, do mais recente para o mais antigo; (2) os plugins em `failed` ou `quarantined` com `last_error` (uma linha cada, hora "—" se não houver evento correspondente); (3) motores de voz com estado `failed` que não tenham evento correspondente no anel (uma linha cada, hora "—"). Lista limitada a 5 linhas. Duplicata (mesmo tipo e mesma área) só entra uma vez.
- **R-S2** Área de cada linha: a coluna "Área" (S27) segue a categoria da tabela 4; para plugins, "Plugin" (nunca o ID do plugin no nível Básico).
- **R-S3** Estado vazio de Últimos erros só aparece quando a contagem é zero E o Core está conectado.
- **R-S4** Badge de erros (S04) usa a mesma contagem de S21, não uma contagem nova.
- **R-S5** Nada nesta sub-aba repete o estado dos motores (DU-01). Para o estado do wake, STT e TTS, use Motores.

### 5.7 Estados
- **Carregando** (antes do primeiro snapshot): S03 mostra `Carregando dados do Core…`; demais campos mostram "—" sem badge.
- **Normal**: conforme S03–S19.
- **Desconectado**: S03(e); S06 "Core desconectado"; S08 "Core desconectado"; S10 "Indisponível"; S15 "Perfil: —"; S26 texto de bloqueio. A sub-aba continua legível (dados em cache do último snapshot não são usados: campos vazios).
- **Modo seguro / Reinício necessário**: S03(c)/(d), S10, S11.
- **Sessão de voz**: S09 "em andamento", S13 aparece; controles de configuração ficam bloqueados (S20).
- **Sem erros**: S24.
- **Com erros**: S23 com até 5 linhas; S04 em Erro.

### 5.8 Dados
Fontes existentes: `core.connected`, `core.state`, `core.sessionId`, `core.configurationStatus`, `core.configurationMessage`, `core.snapshotPack`, `core.pluginItems`. Fontes NOVAS: `core.developerMode`, `core.recentEvents`, `packageInfo`, mapeamentos SCOPE_LABELS e PACK_LABELS (seção 11).

### 5.9 Regras
- Estado nunca decide nada: é só leitura, exceto S12 (navega), S20 (interruptor) e S25 (navega).
- Estado não mostra hashes nem versões de plugin. Versões e hashes ficam em Desenvolvedor (seção 8.6).

---

## 6. Sub-aba Motores

### 6.1 Objetivo
Mostrar o estado e o detalhe de cada motor de voz (wake, transcrição, resposta em voz), o pacote de voz em uso, a última captura e a última resposta, e, quando instalado, o motor LLM. Esta é a única tela com o detalhe dos motores (DU-01).

### 6.2 Condição de aparecimento
Sempre visível. A linha "Motor LLM (plugin)" só aparece com um plugin de motor LLM instalado (`pluginItems` com `plugin_id` do motor LLM). Sem ele, o bloco 1 tem 3 colunas e a área fica mais curta.

### 6.3 Nível
Básico: nome, estado, motor, idioma, saída, frase. Avançado: última resposta (tempo, amostras, trechos, pico, RMS), origem da fala, confiança da transcrição, revisão da transcrição.

### 6.4 Layout em grade

| Região | x | y | largura | altura | Span | Conteúdo |
|---|---|---|---|---|---|---|
| Faixa de resumo | 32 | 184 | 1316 | 40 | — | Resumo dos três motores (M03) |
| Bloco 1 "Motores de voz" | 140 | 236 | 1100 | 250 (sem LLM) · 360 (com LLM) | 12 | Três colunas (Wake 152, STT 524, TTS 896; largura 340 cada) e, se houver, a linha do motor LLM (M22–M24) |
| Bloco 2 "Pacote de voz" | 140 | 502 (sem LLM) · 612 (com LLM) | 542 | 230 | 6 | Verificação, entrada, saída, qualificação (M25–M29) |
| Bloco 3 "Última captura e resposta" | 698 | mesmo y do bloco 2 | 542 | 230 | 6 | Última captura e última resposta (M30–M36) |
| Como funciona | 140 | 748 (sem LLM) · 858 (com LLM) | 1100 | 56 | 12 | Recolhível (M40) |

Com LLM, a área rola (o conteúdo ultrapassa 880 px). Reflow < 900 px: colunas do bloco 1 empilham (Wake, STT, TTS, LLM); blocos 2 e 3 empilham.

### 6.5 Wireframe (com plugin LLM instalado)

```
┌─ Motores ─────────────────────────────────────────────────────────────────────────────────┐
│ Wake                       Transcrição (STT)          Resposta em voz (TTS)               │
│ [Falhou]                   [Pronto]                   [Respondendo]                       │
│ Frase: Hey Gideon          Motor: moonshine EN        Voz: Alba · inglês                  │
│ em desenvolvimento         Idioma: inglês             Saída: virtual                      │
│ Entrada: PCM virtual       pt-BR não comprovado       Última: 3,2 s                       │
│                                                                                           │
│ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -               │
│ Motor LLM (linha só com plugin LLM instalado)                                             │
│ [Ativo (sandbox, sem rede)]   Configurado: OpenRouter · modelo x                          │
│ Resposta de reserva: não usada nesta sessão                                               │
│                                                                                           │
│                                                                                           │
│                                                                                           │
└───────────────────────────────────────────────────────────────────────────────────────────┘

┌─ Pacote de voz ────────────────────────────┐ ┌─ Captura e resposta ───────────────────────┐
│ Verificação: Verificado                    │ │ Captura: 1,8 s · 28 800 amostras           │
│ Entrada: PCM virtual                       │ │ Motivo: Captura concluída                  │
│ Saída: virtual                             │ │                                            │
│ Qualificação: em desenvolvimento;          │ │ Resposta: 3,2 s · 4 trechos                │
│ validação física pendente                  │ │ pico 0,42 · RMS 0,11  (avançado)           │
│                                            │ │                                            │
│ Trocar a voz ou a frase exige              │ │ Confiança da transcrição: não medida       │
│ reinício do Core.                          │ │ Origem da fala: Voz  (avançado)            │
│                                            │ │                                            │
└────────────────────────────────────────────┘ └────────────────────────────────────────────┘

┌─ Como funciona ───────────────────────────────────────────────────────────────────────────┐
│ Replay encerrado não significa que o wake esteja armado.                                  │
└───────────────────────────────────────────────────────────────────────────────────────────┘


```

### 6.6 Elementos

| # | Região / posição (x, y, l, a) | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| M01 | Cabeçalho título (32, 116) | Texto 24 negrito | `Motores` | fixo | — | — | Básico |
| M02 | Cabeçalho subtítulo (32, 146) | Texto 14 | `Wake, transcrição e resposta em voz: o que cada motor está fazendo agora.` | fixo | — | — | Básico |
| M03 | Faixa de resumo (32, 184) | Texto 14 negrito | `Wake: <frase> · Transcrição: <frase> · Resposta em voz: <frase>` (frases da tabela 3.1; sem conexão: `Core desconectado`) | `core.wakeStatus`, `core.sttStatus`, `core.speechStatus` | — | conforme estados | Básico |
| M04 | Bloco 1 (140, 236, 1100, 250/360) — título | Título 17 semibold | `Motores de voz` | fixo | — | — | Básico |
| M05 | Coluna Wake (152, 276, 340) — título | Título 17 semibold | `Wake (frase de despertar)` | fixo | — | — | Básico |
| M06 | Coluna Wake — badge (y 304) | Badge | frase de `wake_status` (tabela 3.1) | `core.wakeStatus` | — | cinco estados; desconectado: Indisponível | Básico |
| M07 | Coluna Wake — frase (y 332) | Texto 14 | `Frase: <texto> · <qualificação>`. Qualificação: `em desenvolvimento` ou `requer prova de conceito`. Sem frase: `Frase: não configurada` | `core.snapshotPack` → `active_phrase` e `wake_phrases` (texto e qualificação; `WAKE_QUALIFICATION_LABELS`) | — | — | Básico |
| M08 | Coluna Wake — motor (y 356) | Texto 14 | `Motor: <nome do motor>`; sem mapeamento: `Motor: não identificado` | `base_pack.engines.wake` (mapeamento ENGINE_LABELS) | — | — | Básico |
| M09 | Coluna Wake — entrada (y 380) | Texto 14 + legenda 12 px | `Entrada: PCM virtual` · legenda `Reprodução de teste; sem microfone ao vivo.` | `base_pack.audio_input` (`virtual_pcm` → `PCM virtual`) | — | — | Básico |
| M10 | Coluna Wake — nota (y 404) | Legenda 12 px Aviso | `Replay encerrado: o wake não está armado para ouvir.` | `wake_status` = `replay_finished` | — | só replay encerrado | Básico |
| M11 | Coluna Wake — nota de falha (y 404) | Legenda 12 px Erro | `Falhou. Reinicie o Core em Recuperação.` | `wake_status` = `failed` | Link textual: vai para Recuperação | só falha | Básico |
| M12 | Coluna STT (524, 276, 340) — título | Título 17 semibold | `Transcrição (STT)` | fixo | — | — | Básico |
| M13 | Coluna STT — badge (y 304) | Badge | frase de `stt_status` (tabela 3.1) | `core.sttStatus` | — | quatro estados | Básico |
| M14 | Coluna STT — motor (y 332) | Texto 14 | `Motor: <nome do motor> · idioma inglês`; sem mapeamento: `Motor: não identificado · idioma inglês` | `base_pack.engines.stt` (ENGINE_LABELS); `base_pack.language` | — | — | Básico |
| M15 | Coluna STT — legenda (y 356) | Legenda 12 px | `Português não está comprovado para transcrição.` | fixo | — | — | Básico |
| M16 | Coluna STT — nota de falha (y 380) | Legenda 12 px Erro | `Falhou. Reinicie o Core em Recuperação.` | `stt_status` = `failed` | Link textual para Recuperação | só falha | Básico |
| M17 | Coluna TTS (896, 276, 340) — título | Título 17 semibold | `Resposta em voz (TTS)` | fixo | — | — | Básico |
| M18 | Coluna TTS — badge (y 304) | Badge | frase de `speech_status` (tabela 3.1) | `core.speechStatus` | — | 16 estados da tabela 3.1 | Básico |
| M19 | Coluna TTS — voz (y 332) | Texto 14 | `Voz: <voz> · <nome do motor> · inglês`. Ex.: `Voz: Alba · Pocket TTS · inglês` | `base_pack.voice`, `base_pack.engines.tts` (ENGINE_LABELS) | — | — | Básico |
| M20 | Coluna TTS — saída (y 356) | Texto 14 + legenda 12 px | `Saída: virtual` · legenda `Sem alto-falante físico comprovado.` | `base_pack.audio_output` (`virtual` → `Virtual`) | — | — | Básico |
| M21 | Coluna TTS — última resposta (y 380) | Texto 12 px, Avançado | `Última resposta: <s> s · <amostras> amostras · <trechos> trechos`; sem: `Última resposta: nenhuma nesta sessão` | NOVO (precisa de mudança na ponte/Core): propriedade `lastSpeech` (campos `speech`: `elapsed_ms`, `samples`, `chunks`) | — | sem resposta | Avançado |
| M22 | Coluna TTS — pico e RMS (y 404) | Texto 12 px, Avançado | `Pico: <valor> · RMS: <valor>` | NOVO (precisa de mudança na ponte/Core): `lastSpeech` (`peak`, `rms`); unidade pendente (seção 13) | — | sem resposta | Avançado |
| M23 | Bloco 1 — separador (y 436) | Linha fina | — | — | — | só com LLM | — |
| M24 | Linha do motor LLM (152, 456, 1076) — título | Título 14 negrito | `Motor LLM (plugin)` | fixo | — | só com plugin LLM instalado | Básico |
| M25 | Linha LLM — badge | Badge | estado do plugin (tabela 3.3): `Ativo (sandbox, sem rede)`, `Iniciando`, `Falhou`, `Parado`, `Em quarentena`, `Desativado` | `pluginItems[].state` do plugin LLM | — | conforme estado | Básico |
| M26 | Linha LLM — configuração | Texto 14 | `Configurado: <provedor> · <modelo>` · `Nenhum modelo configurado` | `core.modelsSelected` (existe; o rótulo "Configurado: …" é montado da mesma forma que hoje) | — | — | Básico |
| M27 | Linha LLM — reserva | Texto 14 | `Resposta de reserva: nesta sessão` (se `llm_fallback_used` estiver no anel) · `Resposta de reserva: não usada nesta sessão` | anel de eventos (`llm_fallback_used`) — NOVO (precisa de mudança na ponte/Core): ver M-NOVO-2 | — | — | Básico |
| M28 | Linha LLM — falha | Texto 12 px Erro | `Falhou: <frase do motivo>` (tabela 3.3, `last_error`) | `pluginItems[].last_error` | — | só falha | Básico |
| M29 | Bloco 2 "Pacote de voz" — título | Título 17 semibold | `Pacote de voz` | fixo | — | — | Básico |
| M30 | Bloco 2 — verificação | Texto 14 | `Verificação: Verificado` · `Verificação: Não verificado` | NOVO (precisa de mudança na ponte/Core): propriedade `packPreflight` (`base_pack.preflight`, `verified` → `Verificado`) | — | — | Básico |
| M31 | Bloco 2 — entrada | Texto 14 | `Entrada: PCM virtual` | NOVO (precisa de mudança na ponte/Core): `packAudioInput` (`base_pack.audio_input`) | — | — | Básico |
| M32 | Bloco 2 — saída | Texto 14 | `Saída: virtual` | NOVO (precisa de mudança na ponte/Core): `packAudioOutput` (`base_pack.audio_output`) | — | — | Básico |
| M33 | Bloco 2 — qualificação | Texto 14 | `Qualificação: em desenvolvimento; validação física pendente` (escopo `dev_virtual_en`); outro escopo: `Qualificação: não informada` | `base_pack.scope` | — | — | Básico |
| M34 | Bloco 2 — aviso | Legenda 12 px | `Trocar a voz ou a frase exige reinício do Core.` | fixo | — | — | Básico |
| M35 | Bloco 3 "Última captura e resposta" — título | Título 17 semibold | `Última captura e resposta` | fixo | — | — | Básico |
| M36 | Bloco 3 — captura | Texto 14 | `Captura: <dur> s · <amostras> amostras`. Duração = (fim − início) em segundos, 1 casa decimal. Sem captura: `Nenhuma captura nesta sessão.` | NOVO (precisa de mudança na ponte/Core): propriedade `lastCapture` (`capture`: `start_us`, `end_us`, `samples`) | — | sem captura | Básico |
| M37 | Bloco 3 — motivo | Texto 14 | `Motivo: <frase>` (frase de `capture.reason`: `Captura concluída`, `Sem fala detectada`, `Captura longa demais`, `Falha na transcrição`, `Transcrição indisponível`, `Erro de áudio`, `Cancelado`, `Transcrição final`) | `lastCapture.reason` (tabela 3.1) | — | — | Básico |
| M38 | Bloco 3 — resposta | Texto 14 | `Resposta: <s> s` (ver M21) | `lastSpeech` | — | — | Básico |
| M39 | Bloco 3 — avançado | Texto 12 px Avançado | `Origem da última fala: Voz` · `Origem da última fala: Texto de teste` · `Confiança da transcrição: não medida` · `Revisão da transcrição: <n>` | NOVO (precisa de mudança na ponte/Core): `transcript.source` (`voice` → `Voz`; `user_text` → `Texto de teste`), `transcript.revision`; confiança é sempre "não medida" por design | — | — | Avançado |
| M40 | Como funciona (140, 748 ou 858, 1100, 56) | Bloco recolhível | `Como funciona` · resumo: `O que cada motor está fazendo. O resumo curto fica no Assistente.` · expandido: `Replay encerrado e reproduzindo são testes de reprodução: não indicam microfone armado. Trocar frase, voz ou dispositivo exige reinício do Core.` | fixo | ▸/▾ | recolhido | Básico |

Notas de elementos:
- **M-NOVO-2** A linha "Resposta de reserva" depende de o Core informar o uso do modelo de reserva. Hoje o evento `llm_fallback_used` fica no anel, mas a ponte não o expõe. **NOVO (precisa de mudança na ponte/Core):** expor `recentEvents` (seção 11, item N6). Até lá, a linha mostra "não usada nesta sessão".

### 6.7 Estados
- **Normal**: cada coluna mostra o badge e as linhas da tabela.
- **Desconectado**: todos os badges em "Indisponível" (Neutro); M03 "Core desconectado"; blocos 2 e 3 mostram "Sem dados: o Core está desconectado."
- **Replay**: M06 "Reproduzindo" ou M10 com replay encerrado.
- **Falha**: badge Erro e nota de falha com link para Recuperação.
- **Sem pacote**: M30–M33 mostram "Não informado" e M07 mostra "Frase: não configurada".
- **Avançado desligado**: M21, M22, M39 ficam ocultos (não apenas cinzas).

### 6.8 Dados
Existentes: `core.wakeStatus`, `core.sttStatus`, `core.speechStatus`, `core.wakeText()`, `activeWake()`, `core.modelsSelectedLabel`, `core.pluginItems`, `core.snapshotPack`, `core.sessionTimeout` (não exibido aqui). NOVOS: `packPreflight`, `packAudioInput`, `packAudioOutput`, `lastCapture`, `lastSpeech`, `transcript` (fonte, revisão), mapeamentos ENGINE_LABELS e PACK_LABELS.

### 6.9 Regras
- **R-M1** Nomes de motor vêm de ENGINE_LABELS (chave = ID do motor no pacote). ID não mapeado: `Motor: não identificado`. Nunca mostrar o ID no Básico.
- **R-M2** "Entrada: PCM virtual" é sempre o rótulo do pacote atual: a Base não tem microfone físico comprovado. Não escrever "microfone".
- **R-M3** Português para transcrição e voz nunca aparece como "suportado". Só a legenda de M15 e M17 (com o texto do item).
- **R-M4** Não há ação de reiniciar motor nesta sub-aba. O único caminho é Recuperação (reinício do Core).

---

## 7. Sub-aba Recuperação

### 7.1 Objetivo
Dar os caminhos de recuperação disponíveis hoje: reiniciar o Core quando a configuração exige, restaurar configuração, voltar à última configuração boa do motor LLM, ver problemas do catálogo e obter os comandos de instalação, atualização, reversão e reparo para o terminal.

### 7.2 Condição de aparecimento
Sempre visível. Badge "•1" quando `configurationStatus` ≠ `ready`. Sem ação primária no cabeçalho: o reinício fica no bloco 1 (R07), para não repetir o mesmo botão.

### 7.3 Nível
Básico: reinício, restauração de configuração (blocos 1). Avançado: última configuração boa do motor LLM, catálogo (bloco 2 parte avançada), comandos de terminal (bloco 3) e tabela de códigos de saída.

### 7.4 Layout em grade

| Região | x | y | largura | altura | Span | Conteúdo |
|---|---|---|---|---|---|---|
| Faixa de resumo | 32 | 184 | 1316 | 40 | — | Frase de resumo (R01) e badge de pendências (R02) |
| Bloco 1 "Reiniciar e restaurar" | 140 | 236 | 542 | 200 | 6 | R03–R12 |
| Bloco 2 "Motor LLM e catálogo" | 698 | 236 | 542 | 200 | 6 | R13–R22 |
| Bloco 3 "Comandos no terminal" | 140 | 452 | 1100 | 230 | 12 | R23–R33 |
| Como funciona | 140 | 698 | 1100 | 56 | 12 | R34 |

Reflow < 900 px: blocos empilhados (span 12).

### 7.5 Wireframe

```
┌─ Reiniciar e restaurar ────────────────────┐ ┌─ Motor LLM e catálogo ─────────────────────┐
│ Reinício do Core: não necessário           │ │ Última configuração boa: disponível        │
│ Use se o Core estiver com erro ou          │ │ [Voltar à última configuração boa]         │
│ após trocar frase ou feedback.             │ │                                            │
│                                            │ │ Catálogo de plugins: sem problemas         │
│ [Reiniciar Core]                           │ │ Nenhum problema de armazenamento.          │
│                                            │ │                                            │
│ [Restaurar anterior]                       │ │                                            │
│ [Preservar arquivo e restaurar padrões]    │ │                                            │
│                                            │ │                                            │
└────────────────────────────────────────────┘ └────────────────────────────────────────────┘


┌─ Comandos no terminal (copiar) ───────────────────────────────────────────────────────────┐
│ Instalar:   gideon-install --install-root <RAIZ> install <PACOTE>   [Copiar]              │
│ Atualizar:  gideon-install --install-root <RAIZ> update <PACOTE>   [Copiar]               │
│ Reverter:   gideon-install --install-root <RAIZ> rollback          [Copiar]               │
│ Reparar:    gideon-install --install-root <RAIZ> repair            [Copiar]               │
│ Criar perfil: gideon-install --install-root <RAIZ> profile create <NOME>                  │
│ Abrir perfil: gideon-launch --install-root <RAIZ> <PERFIL>                                │
│                                                                                           │
│ Com o Core ativo, install, update, rollback e repair são recusados.                       │
│                                                                                           │
└───────────────────────────────────────────────────────────────────────────────────────────┘


┌─ Como funciona ───────────────────────────────────────────────────────────────────────────┐
│ Reiniciar e restaurar não apagam dados. Pacotes: só pelo terminal.                        │
└───────────────────────────────────────────────────────────────────────────────────────────┘


```

### 7.6 Elementos

| # | Região / posição (x, y, l, a) | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| R01 | Faixa de resumo (32, 184) | Texto 14 negrito | `Reinício do Core: não necessário` · `Reinício do Core: necessário` · `Modo seguro: recuperação disponível` · `Core desconectado: nada a fazer aqui` | `core.configurationStatus`, `core.configurationRecoveryAvailable`, `core.connected` | — | conforme | Básico |
| R02 | Faixa de resumo — badge (direita) | Badge | `Pendências: 1` (Aviso) ou `Pendências: 0` (Neutro) | `configurationStatus` ≠ `ready` | — | — | Básico |
| R03 | Cabeçalho | — | nenhum botão de cabeçalho (ver 7.2). Este número fica reservado; a ação de reinício é R07 | — | — | — | — |
| R04 | Bloco 1 (140, 236, 542, 200) — título | Título 17 semibold | `Reiniciar e restaurar` | fixo | — | — | Básico |
| R05 | Bloco 1 — badge do reinício (y 276) | Badge | `Necessário agora` (Aviso) · `Não necessário` (Neutro) · `Indisponível` (Neutro, desconectado) | `configurationStatus` = `restart_required` | — | três | Básico |
| R06 | Bloco 1 — texto (y 304) | Texto 14 | `Reinício exigido ao trocar a frase de despertar, mudar o feedback ou alterar plugins.` (sempre) · com `restart_required`, linha extra: `A configuração salva só vale depois do reinício.` | fixo + `configurationStatus` | — | — | Básico |
| R07 | Bloco 1 — botão (y 360) | Botão secundário (40) | `Reiniciar Core` | — | Abre R-D1; se confirmado, ver seção 7.8 | habilitado se conectado e sem sessão; desabilitado caso contrário | Básico |
| R08 | Bloco 1 — motivo desabilitado (y 404) | Legenda 12 px | `Indisponível: há uma sessão de voz em andamento` · `Indisponível: Core desconectado` | `core.sessionId`, `core.connected` | — | só desabilitado | Básico |
| R09 | Bloco 1 — subtítulo (y 432) | Texto 14 negrito | `Configuração` | fixo | — | — | Básico |
| R10 | Bloco 1 — texto (y 452) | Texto 14 | `Volta às preferências anteriores salvas pelo Core.` (pronta) · `Preserva o arquivo inválido e volta aos padrões. Depois, reinicie o Core.` (modo seguro) | fixo por estado | — | — | Básico |
| R11 | Bloco 1 — botão `Restaurar anterior` (y 476) | Botão secundário (40) | `Restaurar anterior` | `core.rollbackAvailable` | `core.rollbackPreferences()`; resultado mostrado em `core.preferencesResult` | visível se `rollbackAvailable`; habilitado se sessão ausente | Básico |
| R12 | Bloco 1 — botão `Preservar arquivo e restaurar padrões` (y 476) | Botão secundário (40) | `Preservar arquivo e restaurar padrões` | `core.recoveryAvailable` | Abre R-D2; se confirmado: `core.recoverConfiguration()` | visível só em modo seguro com recuperação disponível | Básico |
| R13 | Bloco 2 "Motor LLM e catálogo" (698, 236, 542, 200) — título | Título 17 semibold | `Motor LLM e catálogo` | fixo | — | — | Avançado |
| R14 | Bloco 2 — subtítulo (y 276) | Texto 14 negrito | `Motor LLM` | fixo | — | — | Avançado |
| R15 | Bloco 2 — texto LKG (y 300) | Texto 14 | `Há uma configuração boa salva: <provedor> · <modelo>` · `Não há configuração anterior salva para restaurar.` | NOVO (precisa de mudança na ponte/Core): `llmLastKnownGood` (presença de `llm.config.lkg`) e par provedor/modelo | — | sem LKG | Avançado |
| R16 | Bloco 2 — botão (y 332) | Botão secundário (40) | `Voltar à última configuração boa` | NOVO (precisa de mudança na ponte/Core): slot `rollbackLlm()` | Abre R-D3; se confirmado: `rollbackLlm()` → Operação `llm_rollback` com `llmRevision` atual | visível só com LKG; habilitado se conectado, sem sessão, sem `modelsBusy` | Avançado |
| R17 | Bloco 2 — motivo desabilitado (y 376) | Legenda 12 px | `Indisponível: há uma sessão de voz em andamento` | `sessionId` | — | só com sessão | Avançado |
| R18 | Bloco 2 — subtítulo (y 404) | Texto 14 negrito | `Catálogo de plugins` | fixo | — | — | Avançado |
| R19 | Bloco 2 — situação do catálogo (y 428) | Texto 14 | `Nenhum problema de armazenamento.` · `Falha ao gravar o registro do catálogo.` · `Importação interrompida pendente: <n>. Não é possível importar este pacote de novo até a recuperação manual.` | NOVO (precisa de mudança na ponte/Core): `hubOrphans` (contagem de `orphans`) e `hubStorageError` (campos `HUB_KEYS`) | — | três | Avançado |
| R20 | Bloco 2 — legenda (y 452) | Legenda 12 px | `O catálogo é verificado por SHA-256; o valor aparece em Desenvolvedor.` | fixo | — | — | Avançado |
| R21 | Bloco 3 "Comandos no terminal" (140, 452, 1100, 230) — título | Título 17 semibold | `Comandos no terminal` | fixo | — | — | Avançado |
| R22 | Bloco 3 — legenda (y 484) | Texto 14 | `Rodam fora do aplicativo, no terminal. Troque <RAIZ> pelo caminho absoluto da instalação; <PACOTE> pelo diretório do pacote; <NOME> pelo nome do perfil; <PERFIL> pelo perfil criado.` | fixo | — | — | Avançado |
| R23 | Bloco 3 — linha "Instalar" (y 512) | Rótulo 12 negrito + código 13 px monoespaçado + botão `Copiar` (30 px) | `Instalar` · `gideon-install --install-root <RAIZ> install <PACOTE>` · `Copiar` | fixo | `Copiar` escreve o texto na área de transferência | sempre | Avançado |
| R24 | Bloco 3 — linha "Atualizar" (y 544) | idem | `Atualizar` · `gideon-install --install-root <RAIZ> update <PACOTE>` · `Copiar` | fixo | idem | sempre | Avançado |
| R25 | Bloco 3 — linha "Reverter" (y 576) | idem | `Reverter` · `gideon-install --install-root <RAIZ> rollback` · `Copiar` | fixo | idem | sempre | Avançado |
| R26 | Bloco 3 — linha "Reparar" (y 608) | idem | `Reparar` · `gideon-install --install-root <RAIZ> repair` · `Copiar` | fixo | idem | sempre | Avançado |
| R27 | Bloco 3 — linha "Criar perfil" (y 640) | idem | `Criar perfil` · `gideon-install --install-root <RAIZ> profile create <NOME>` · `Copiar` | fixo | idem | sempre | Avançado |
| R28 | Bloco 3 — linha "Abrir perfil" (y 672) | idem | `Abrir perfil` · `gideon-launch --install-root <RAIZ> <PERFIL>` · `Copiar` | fixo | idem | sempre | Avançado |
| R29 | Bloco 3 — nota de Core ativo (y 704, dentro do bloco) | Legenda 12 px | `Com o Core ativo, instalar, atualizar, reverter e reparar são recusados (código de saída 3).` | fixo | — | — | Avançado |
| R30 | Bloco 3 — nota de reparo | Legenda 12 px | `Se o terminal mostrar "run: gideon-install --install-root <RAIZ> repair", execute o comando de reparo.` | fixo | — | — | Avançado |
| R31 | Bloco 3 — códigos de saída (recolhível dentro do bloco) | Lista 12 px | `0 ok` · `2 uso incorreto` · `3 perfil com Core ativo` · `4 verificação do pacote falhou` · `5 estado inválido ou reparo necessário` · `6 bloqueado ou outro erro` | fixo (códigos de saída de `gideon-install`) | — | recolhido por padrão | Avançado |
| R32 | Bloco 3 — rótulo do reparo (sem bloqueio) | Texto 12 | `Reparo e atualização ficam no terminal: esta tela não executa instalador.` | fixo | — | — | Avançado |
| R33 | Bloco 3 — cópia | Feedback | `Comando copiado.` (toast 4 s) | — | — | após Copiar | Avançado |
| R34 | Como funciona (140, 698, 1100, 56) | Bloco recolhível | `Como funciona` · resumo: `Reinícios e restaurações não apagam dados do usuário. Instalação e pacotes só pelo terminal.` · expandido: `Reiniciar o Core encerra os plugins em execução e refaz a conexão. A instalação versionada (gideon-install) não é executada por esta tela.` | fixo | ▸/▾ | recolhido | Básico |

Observações:
- R09–R12 aparecem no bloco 1 abaixo do reinício (R04–R08), na ordem de leitura.
- Os códigos de saída (R31) são do `gideon-install` conforme o cabeçalho do script (`Exit codes: 0 ok, 2 usage, 3 profile_active, 4 verify_failed, 5 state, 6 other`).

### 7.7 Comandos (texto exato para copiar)

Os comandos são copiados como texto exato, com os marcadores `<...>` que o usuário troca. Sintaxe confirmada em `scripts/package_tools/gideon-install` e `gideon-launch`:

```
gideon-install --install-root <RAIZ> install <PACOTE>
gideon-install --install-root <RAIZ> update <PACOTE>
gideon-install --install-root <RAIZ> rollback
gideon-install --install-root <RAIZ> repair
gideon-install --install-root <RAIZ> profile create <NOME>
gideon-launch --install-root <RAIZ> <PERFIL>
```

- `<RAIZ>`: caminho absoluto da instalação (`--install-root` exige caminho absoluto).
- `<PACOTE>`: diretório do pacote `gideon-base` (o que passa em `gideon-verify`).
- `<NOME>`: `[a-z0-9_-]{1,32}`.
- `<PERFIL>`: nome do perfil existente (`profile list` lista).
- Nunca usar esses comandos a partir da interface para executar nada: a tela só copia.

### 7.8 Diálogos de confirmação (texto exato)

Todos com **Cancelar** focado por padrão (00-casca). Esc fecha.

**R-D1 — Reiniciar o Core**
- Título: `Reiniciar o Core?`
- Corpo: `O Core será reiniciado e a conexão será refeita. Plugins em execução serão parados.`
- Botões: `Cancelar` (foco inicial) · `Reiniciar Core` (primário).
- Depois de confirmar: pílula `Core desconectado`; texto `Reiniciando o Core…` (12 px, bloco 1). Ao reconectar: toast `Core reiniciado.`. Se não voltar em 30 s: texto `O Core não voltou. Confira o terminal e use o comando de reparo em Recuperação.`

**R-D2 — Preservar arquivo e restaurar padrões**
- Título: `Preservar o arquivo e restaurar os padrões?`
- Corpo: `O arquivo inválido fica guardado e as preferências voltam aos padrões. Reinicie o Core depois.`
- Botões: `Cancelar` (foco) · `Restaurar padrões`.

**R-D3 — Voltar à última configuração boa**
- Título: `Voltar à última configuração boa?`
- Corpo: `A configuração atual do motor LLM será trocada pela última que funcionou.`
- Botões: `Cancelar` (foco) · `Voltar`.

### 7.9 Estados
- **Normal**: R05 "Não necessário"; R03 oculto; R11/R12 conforme `rollbackAvailable` e `recoveryAvailable`.
- **Reinício necessário**: R03 aparece no cabeçalho; R05 "Necessário agora"; R06 linha extra.
- **Modo seguro**: R12 aparece; R10 mostra o texto de modo seguro; R01 "Modo seguro: recuperação disponível" (ou sem recuperação: R12 oculto, R01 mostra só o modo).
- **Sessão de voz ativa**: todos os botões que escrevem (R07, R11, R12, R16) ficam desabilitados com R08/R17.
- **Desconectado**: tudo desabilitado; R05 "Indisponível"; R19 "Sem dados: o Core está desconectado."
- **Sem LKG**: R16 oculto; R15 "Não há configuração anterior salva para restaurar."

### 7.10 Dados
Existentes: `core.configurationStatus`, `core.configurationRecoveryAvailable`, `core.recoveryAvailable`, `core.rollbackAvailable`, `core.recoverConfiguration()`, `core.rollbackPreferences()`, `core.preferencesResult`, `core.sessionId`, `core.connected`, `core.llmRevision`, `core.modelsBusy`. NOVOS: `llmLastKnownGood`, `rollbackLlm()`, `hubOrphans`, `hubStorageError`, `restartCore()` (seção 11).

### 7.11 Regras
- **R-R1** Reiniciar Core: IMPLEMENTADO (WP8, DOCS-02). Existe `coreRestart` em `app/bridge.py` (op `core_restart`, espera o Core voltar, tempo limite de 30 s) e o botão `restartCoreButton` em `app/pages/DiagRecuperacao.qml`. R07 segue as regras da tabela (conectado e sem sessão, `coreRestartAvailable`). A frase "reinício do Core ainda não existe nesta versão" está obsoleta.
- **R-R2** Nenhum botão desta sub-aba aprova, concede ou revoga permissão.
- **R-R3** Restauração de configuração (R11, R12) não apaga o arquivo: o arquivo inválido é preservado (R-D2 diz isso).

---

## 8. Sub-aba Desenvolvedor (condicional)

### 8.1 Objetivo
Dar, só para desenvolvimento e teste, as ferramentas que hoje estão espalhadas ou ausentes: comando de texto de teste, disparo de wake de teste, invocação de capacidades de plugins com formulário e JSON, leitura do replay de wake, legenda dos selos por extenso e versões e hashes do pacote.

### 8.2 Condição de aparecimento e interruptor (NOVO)
- Aparece só quando `core.developerMode` é verdadeiro. Interruptor em **Estado › Base e privacidade** (S20).
- **Estado atual (WP8):** o interruptor existe em `app/pages/CfgGeral.qml` (`behavior.devMode`, `devModeConfirm`) e `app/pages/DiagEstado.qml`, gravado pelo app por perfil (`app/uisettings.py`). Não há campo `developer_mode` no Core (`src/storage.rs`) nem `developerMode` na ponte, então a versão do Core continua **NOVO (precisa de mudança na ponte/Core):** o valor deve ser guardado pelo Core (não pela ponte, porque a ponte não escreve em disco). Campo `developer_mode` (booleano, padrão `false`) em `storage::Config`, com revisão de compare-and-set, operação `developer_mode` {`revision`, `enabled`} idle-only (mesma regra de `preferences`), e slot de ponte `setDeveloperMode(bool)`. Propriedade de ponte `developerMode` (bool). Mínimo alternativo se o Core não puder ser mudado agora: booleano só em memória da ponte, que volta a `false` ao reabrir, e a legenda S20 deve dizer "Vale só nesta sessão do aplicativo."
- Bloqueio em sessão de voz: S20 desabilitado com o motivo de S13.

### 8.3 Nível
Desenvolvimento. Nenhum elemento desta sub-aba aparece sem o modo ligado.

### 8.4 Diálogo de confirmação (ao ligar)

- Título: `Ativar modo desenvolvedor?`
- Corpo: `Este modo mostra ferramentas de teste na aba Desenvolvedor: comando de texto de teste, wake de teste, invocação de capacidades de plugin com JSON e identificadores técnicos (versões e hashes). Elas não concedem permissões nem mudam o que o Gideon pode fazer no seu computador. Use somente em desenvolvimento ou teste.`
- Botões: `Cancelar` (foco inicial) · `Ativar modo desenvolvedor` (primário).
- Resultado: `Modo desenvolvedor ligado.` (toast 4 s). Se o Core recusar: `Core ocupado; tente novamente em instantes` (busy) ou `Indisponível: há uma sessão de voz em andamento`.
- Desligar: sem diálogo; toast `Modo desenvolvedor desligado.`.

### 8.5 Layout em grade

| Região | x | y | largura | altura | Span | Conteúdo |
|---|---|---|---|---|---|---|
| Faixa de resumo (aviso) | 32 | 184 | 1316 | 40 | — | Aviso e botão de desligar (D03) |
| Bloco 1 "Entrada de teste" | 140 | 236 | 542 | 240 | 6 | D04–D11 |
| Bloco 2 "Invocar capacidade" | 698 | 236 | 542 | 340 | 6 | D12–D20 |
| Bloco 3 "Versões, hashes e selos" | 140 | 592 | 1100 | 260 | 12 | D21 (duas colunas: versões à esquerda, selos à direita) |

Sem "Como funciona" nesta sub-aba (o aviso fica na faixa de resumo). A área rola (blocos 2 e 3 ultrapassam 880 px). Reflow < 900 px: blocos empilhados; as duas colunas do bloco 3 empilham (versões, depois selos).

### 8.6 Wireframe

```
┌─ Entrada de teste ─────────────────────────┐ ┌─ Invocar capacidade ───────────────────────┐
│ Comando de texto de teste                  │ │ Capacidade: [ screen_observe.status v ]    │
│ [Texto de teste…]  [Enviar]                │ │ ( Texto )  ( JSON )                        │
│ Resultado: —                               │ │ Texto: [                              ]    │
│                                            │ │                                            │
│ [Disparar wake de teste]                   │ │ Entrada em JSON (objeto, até 2 048 bytes)  │
│ Replay de wake: reproduzindo               │ │ [ { … } ]                                  │
│ Replay: iniciado pelo Core (wake-replay)   │ │ [Invocar] [Cancelar invocação]             │
│ Indisponível: entrada de teste inativa     │ │ Prazo: 3 s · Resultado: —                  │
│                                            │ │                                            │
│                                            │ │                                            │
│                                            │ │                                            │
└────────────────────────────────────────────┘ │                                            │
                                               │                                            │
                                               │                                            │
                                               └────────────────────────────────────────────┘

┌─ Versões, hashes e selos ─────────────────────────────────────────────────────────────────┐
│ Versão da Base: x.y.z                         SINTÉTICO — sem hardware real               │
│ Protocolo do Core: 1                          SERVIDOR FALSO — sem credenciais reais      │
│ Pacote de voz: <id> · escopo <escopo>         UNSUPPORTED — nada foi executado            │
│ Motores: wake <id> · stt <id> · tts <id>      em desenvolvimento — validação pendente     │
│ SHA-256 do pacote: <16 caracteres>…           requer prova de conceito — não selecionável │
│ Catálogo do Hub: SHA-256 <16 caracteres>…     não verificado — publisher não autenticado  │
│ Plugin <id> <versão> · <hash 12>…             pendente de validação humana                │
│ Revisões: preferências <n> · LLM <n>                                                      │
│ Binário e PACKAGE.json: <sha256> · commit                                                 │
│                                                                                           │
│                                                                                           │
└───────────────────────────────────────────────────────────────────────────────────────────┘


```

### 8.7 Elementos

| # | Região / posição (x, y, l, a) | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| D01 | Cabeçalho título (32, 116) | Texto 24 negrito | `Desenvolvedor` | fixo | — | — | Desenvolvimento |
| D02 | Cabeçalho subtítulo (32, 146) | Texto 14 | `Ferramentas de teste. Não concedem permissões; use somente em desenvolvimento.` | fixo | — | — | Desenvolvimento |
| D03 | Faixa de resumo (32, 184, 1316, 40) — aviso | Texto 14 negrito Aviso #f2c15c | `Modo desenvolvedor ligado: ferramentas de teste. Não concedem permissões.` | `core.developerMode` | — | — | Desenvolvimento |
| D03b | Faixa de resumo — botão (direita) | Botão secundário (30) | `Desligar modo desenvolvedor` | `core.developerMode` | Desliga (sem diálogo; toast `Modo desenvolvedor desligado.`); bloqueado em sessão | habilitado sem sessão | Desenvolvimento |
| D04 | Bloco 1 "Entrada de teste" (140, 236, 542, 240) — título | Título 17 semibold | `Entrada de teste` | fixo | — | — | Desenvolvimento |
| D05 | Bloco 1 — subtítulo (y 276) | Texto 14 negrito | `Comando de texto de teste` | fixo | — | — | Desenvolvimento |
| D06 | Bloco 1 — campo (y 300, altura 40) | Campo de texto | placeholder `Comando de texto no perfil de teste` | `core.textAvailable` (habilita) | Digitar; Enter envia (mesma ação de D07) | vazio, preenchido, desabilitado | Desenvolvimento |
| D06a | Bloco 1 — validação (y 346) | Legenda 12 px Erro | `Texto vazio` · `Texto acima de 512 bytes` · `Texto com quebra de linha ou controle não é aceito` | `core.textProblem` (regras de `text_problem`) | — | só com erro | Desenvolvimento |
| D07 | Bloco 1 — botão `Enviar` (à direita do campo D06, y 300) | Botão primário (40) | `Enviar` | `core.textAvailable`, `core.sessionId` | `core.submitText(texto)` → `text` | habilitado se disponível e não vazio | Desenvolvimento |
| D08 | Bloco 1 — motivo desabilitado (y 346) | Legenda 12 px | `Indisponível: há uma sessão de voz em andamento` · `Indisponível: o Core não tem entrada de texto de teste (exige --virtual-input e --commands-sandbox).` | `sessionId`, `textAvailable` | — | só desabilitado | Desenvolvimento |
| D09 | Bloco 1 — resultado (y 372) | Texto 14 | `<texto de core.textResult>`; vazio: `Nenhum comando de teste enviado.` | `core.textResult` | — | — | Desenvolvimento |
| D10 | Bloco 1 — botão `Disparar wake de teste` (y 404, 40) | Botão secundário | `Disparar wake de teste` | NOVO (precisa de mudança na ponte/Core): slot `virtualWake()` → operação `virtual_wake` (já existe no Core, exige `--virtual-input`); habilitado com `core.textAvailable` | `virtualWake()`; resposta no texto de D11 | habilitado / desabilitado com D08 | Desenvolvimento |
| D11 | Bloco 1 — replay (y 452) | Texto 14 + legenda 12 px | `Replay de wake: <frase>` (`reproduzindo` para `replaying`; `encerrado` para `replay_finished`; `não ativo` nos demais) · legenda `O replay é iniciado pelo Core com --wake-replay. Não há microfone nesta tela.` | `core.wakeStatus` | — | — | Desenvolvimento |
| D12 | Bloco 2 "Invocar capacidade" (698, 236, 542, 340) — título | Título 17 semibold | `Invocar capacidade` | fixo | — | — | Desenvolvimento |
| D13 | Bloco 2 — campo `Capacidade` (y 276) | Combobox | rótulo `Capacidade`; opções: as capacidades dos plugins com `state` = `running` (ID cru, texto exato da capacidade). Vazio: `Nenhuma capacidade em execução. Ative um plugin em Extensões › Plugins.` | `core.pluginItems[].capabilities` filtrado por `state` = `running` | Escolhe a capacidade | vazio | Desenvolvimento |
| D14 | Bloco 2 — segmentado (y 330) | Segmentado 2 opções | `Texto` · `JSON` (padrão `Texto`) | local | Troca o campo de entrada (D15/D16) | — | Desenvolvimento |
| D15 | Bloco 2 — campo texto (modo Texto, y 370) | Campo de texto | rótulo `Texto para a capacidade`; máximo 256 caracteres | local | Envia `{"text": <texto>}` via `core.invokeCapability(capacidade, texto)` (existe) | só modo Texto | Desenvolvimento |
| D16 | Bloco 2 — área JSON (modo JSON, y 370, altura 120) | Área de texto monoespaçada | rótulo `Entrada em JSON (objeto)`; placeholder `{ }`; máximo 2 048 bytes UTF-8 | local | Envia o objeto via NOVO slot `invokeCapabilityJson(capacidade, texto)` | só modo JSON | Desenvolvimento |
| D16a | Bloco 2 — validação JSON (y 496) | Legenda 12 px Erro | `JSON inválido: use um objeto entre chaves.` · `A entrada deve ser um objeto JSON.` · `Entrada acima de 2 048 bytes.` | validação local antes de enviar | — | só com erro | Desenvolvimento |
| D17 | Bloco 2 — botão `Invocar` (y 520, 40) | Botão primário | `Invocar` | — | Envia (prazo 3 000 ms; texto `Prazo: 3 s`) | habilitado se há capacidade, plugin em execução, entrada válida e sem invocação em andamento | Desenvolvimento |
| D18 | Bloco 2 — botão `Cancelar invocação` (y 520) | Botão secundário (40) | `Cancelar invocação` | `core.cancelCapability(capacidade)` (existe) | Cancela a invocação em andamento | visível só com invocação em andamento desta capacidade | Desenvolvimento |
| D19 | Bloco 2 — estado (y 568) | Texto 12 px | `Invocação em andamento…` · `Sem resultado ainda.` · `Prazo: 3 s` | NOVO (precisa de mudança na ponte/Core): propriedade `capabilityPending` (hoje é o campo interno `capability_pending` da ponte) | — | — | Desenvolvimento |
| D20 | Bloco 2 — resultado (y 596, altura até 120) | Texto monoespaçado 13 px, rolável | rótulo `Resultado` + `core.capabilityResultText` (até 512 caracteres; excedente com "…") | `core.capabilityResultText` (existe) | — | vazio: `Sem resultado ainda.` | Desenvolvimento |
| D21 | Bloco 3 "Versões, hashes e selos" (140, 592, 1100, 260) — título | Título 17 semibold | `Versões, hashes e selos` | fixo | — | — | Desenvolvimento |
| V01 | Bloco 3 — coluna Versões (linha 1, y 632) | Texto 13 px monoespaçado | `Versão da Base: <versão>` | NOVO (precisa de mudança na ponte/Core): `packageInfo.version` | — | sem dado: `não informada` | Desenvolvimento |
| V02 | Bloco 3 — linha 2 | idem | `Protocolo do Core: <versão do protocolo>` | NOVO (precisa de mudança na ponte/Core): expor `snapshot.version` (`TOP_KEYS`) como `protocolVersion` | — | — | Desenvolvimento |
| V03 | Bloco 3 — linha 3 | idem | `Pacote de voz: <id> · escopo <escopo>` | `core.snapshotPack` → `base_pack.id`, `base_pack.scope` (existe) | — | — | Desenvolvimento |
| V04 | Bloco 3 — linha 4 | idem | `Motores: wake <id> · stt <id> · tts <id>` | NOVO (precisa de mudança na ponte/Core): propriedade `packEngines` (`base_pack.engines`) | — | — | Desenvolvimento |
| V05 | Bloco 3 — linha 5 | idem | `SHA-256 do pacote de voz: <16 caracteres>…` | NOVO (precisa de mudança na ponte/Core): `packHash` (hash do `pack.json` ou do pacote de voz, calculado pelo Core) | — | sem dado: `não informado` | Desenvolvimento |
| V06 | Bloco 3 — linha 6 | idem | `SHA-256 do catálogo do Hub: <16 caracteres>…` | NOVO (precisa de mudança na ponte/Core): `catalogSha256` (`HUB_KEYS` `catalog_sha256`) | — | sem catálogo: `não informado` | Desenvolvimento |
| V07 | Bloco 3 — linhas de plugin (uma por entrada com status `installed`, `update_available` ou payload em staging) | idem | `<plugin_id> <semver> · manifesto <12 caracteres>…` | `core.hubEntries[]` (`semver`, `manifest_sha256` — existe) | — | sem plugin: `Nenhum plugin instalado` | Desenvolvimento |
| V08 | Bloco 3 — revisões | idem | `Revisões: preferências <n> · motor LLM <n>` | `core.preferencesRevision`, `core.llmRevision` (existe) | — | — | Desenvolvimento |
| V09 | Bloco 3 — binário | idem | `Binário e PACKAGE.json: <16 caracteres>… · commit <8 caracteres>` | NOVO (precisa de mudança na ponte/Core): `packageInfo` (sha256 do binário, commit, do `PACKAGE.json`) | — | sem dado: `não informado` | Desenvolvimento |
| V10 | Bloco 3 — última captura | idem | `SHA-256 da última captura: <16 caracteres>…` | NOVO (precisa de mudança na ponte/Core): `lastCapture.pcm_sha256` (campo validado em `CAPTURE_KEYS`) | — | sem captura: `não informado` | Desenvolvimento |
| S01s | Bloco 3 — coluna Selos (título) | Título 14 negrito | `Selos por extenso` | fixo | — | — | Desenvolvimento |
| S02s | Coluna Selos — linha SINTÉTICO | Texto 13 px | `SINTÉTICO — sem hardware real: o resultado é simulado; nenhum dispositivo real foi usado.` | fixo (selo usado em percepção e atividade de percepção) | — | — | Desenvolvimento |
| S03s | Coluna Selos — SERVIDOR FALSO | Texto 13 px | `SERVIDOR FALSO — sem credenciais reais: a conexão usa um servidor de teste.` | fixo (conexões com `fake` = verdadeiro) | — | — | Desenvolvimento |
| S04s | Coluna Selos — UNSUPPORTED | Texto 13 px | `UNSUPPORTED — recurso não suportado neste ambiente; nada foi executado.` | fixo | — | — | Desenvolvimento |
| S05s | Coluna Selos — em desenvolvimento | Texto 13 px | `em desenvolvimento — qualificação de teste; validação física pendente.` | fixo | — | — | Desenvolvimento |
| S06s | Coluna Selos — requer prova de conceito | Texto 13 px | `requer prova de conceito — frase não qualificada; não pode ser escolhida.` | fixo | — | — | Desenvolvimento |
| S07s | Coluna Selos — não verificado | Texto 13 px | `não verificado — o publisher não foi autenticado.` | fixo | — | — | Desenvolvimento |
| S08s | Coluna Selos — pendente | Texto 13 px | `pendente de validação humana — backend real ainda não validado com hardware.` | fixo | — | — | Desenvolvimento |

### 8.8 Lista completa do que o modo desenvolvedor revela

1. **Comando de texto de teste** (D05–D09): campo, Enviar, resultado. Mesmo slot `submitText` que o campo de comando do Assistente (Hoje). Em desenvolvimento, o Assistente rotula o campo como de teste; o envio é o mesmo.
2. **Disparo de wake de teste** (D10): botão novo; equivale a `VirtualWake` do Core (só com `--virtual-input`). Ver N3.
3. **Replay de wake** (D11): leitura do estado `replaying`/`replay_finished`; o replay é iniciado pelo Core com `--wake-replay`, não por esta tela.
4. **Invocar capacidade** (D12–D20): dois formatos (Texto, JSON), seleção de capacidade em execução, Invocar (3 s), Cancelar invocação, resultado (512 caracteres).
5. **Rótulos SINTÉTICO e SERVIDOR FALSO por extenso** (S02s–S03s): a legenda usa as palavras completas, e o selo curto continua nas telas de Percepção e Conexões.
6. **Versões e hashes do pacote** (V01–V09): versão da Base, protocolo, pacote de voz e motores, hashes (pacote, catálogo, plugins, binário), revisões de preferências e de motor LLM.
7. **Selos de honestidade** (S04s–S08s): UNSUPPORTED, em desenvolvimento, requer prova de conceito, não verificado, pendente de validação humana.

O modo desenvolvedor **não** revela: botões de aprovação, concessão ou revogação de permissão; agente de teste (`agent_test_bump`); ação de captura de teste (`Action`); comandos de percepção de ação. Esses itens ficam fora desta tela (ver NF-04, NF-05, NF-11 em `docs/UI_INVENTORY.md`).

### 8.9 Estados
- **Normal**: todos os campos conforme condição.
- **Sessão de voz**: D06, D07, D10, D17 e D18 desabilitados com D08 (texto de sessão); V01–V09 continuam legíveis.
- **Sem entrada de teste**: D06, D07, D10 desabilitados com D08 (texto do Core sem entrada de teste).
- **Sem capacidade em execução**: D13 mostra o texto de vazio; D17 desabilitado.
- **Invocação em andamento**: D17 desabilitado; D18 visível; D19 "Invocação em andamento…".
- **Sem plugin instalado**: V07 mostra `Nenhum plugin instalado`.

### 8.10 Dados
Existentes: `core.textAvailable`, `core.textResult`, `core.submitText`, `core.wakeStatus`, `core.pluginItems`, `core.invokeCapability`, `core.cancelCapability`, `core.capabilityResultText`, `core.hubEntries`, `core.preferencesRevision`, `core.llmRevision`, `core.snapshotPack`. NOVOS: `core.developerMode` + `setDeveloperMode`, `virtualWake()`, `invokeCapabilityJson()`, `protocolVersion`, `packEngines`, `packHash`, `catalogSha256`, `packageInfo`.

### 8.11 Regras
- **R-DV1** O modo desenvolvedor não muda permissões, aprovações nem o que o Gideon pode fazer. Não há botão de permissão nesta sub-aba.
- **R-DV2** O texto de teste (D06) passa pelas mesmas regras de `text_problem` (vazio, máximo 512 bytes, sem quebra de linha ou controle).
- **R-DV3** JSON de invocação (D16): objeto apenas, máximo 2 048 bytes UTF-8 (limite de decisão desta spec: 4096 bytes é o limite de entrada do Core e precisa de folga para o envelope; ver seção 13). Validação local antes do envio.
- **R-DV4** Identificadores crus (IDs de motor, de plugin, de capacidade, hashes) aparecem só nesta sub-aba.
- **R-DV5** Se o Core for reiniciado com o modo ligado, o valor vem do Core (N1). Sem persistência (alternativa da seção 8.2), o modo volta a desligado e a sub-aba some.

---

## 9. Modo desenvolvedor: resumo do que muda fora de Diagnóstico

- Assistente › Hoje: o campo de comando usa o mesmo slot de D06 (`submitText`). Com o modo ligado, o rótulo do campo mostra "Comando de texto de teste". A spec da aba Assistente precisa repetir essa regra.
- Extensões › Plugins (diálogo de plugins): o campo de capacidade e o botão Invocar continuam (texto livre), mas o rótulo "Cancelar" vira "Cancelar invocação" (R-05). Com o modo ligado, o campo JSON só aparece em Diagnóstico, não no diálogo.
- Percepção e ação: os selos SINTÉTICO e UNSUPPORTED continuam como selos curtos (00-casca); a legenda por extenso fica em Diagnóstico › Desenvolvedor.

---

## 10. Acessibilidade

- **A11-01** Abas de nível 1 e 2 usam papel de aba (tablist/tab) com nome: "Diagnóstico" e os nomes das sub-abas. A aba ativa tem `aria-selected` verdadeiro.
- **A11-02** Ctrl+5 seleciona a aba Diagnóstico; Ctrl+Tab percorre as sub-abas visíveis; setas esquerda/direita também movem o foco entre sub-abas.
- **A11-03** Ordem de foco = ordem de leitura (coluna de `#` nas tabelas). Dentro de um bloco, o foco vai do título para os controles, de cima para baixo.
- **A11-04** Badges têm texto e cor juntos (nunca só cor). O nome acessível de um badge é a frase completa: "Motor de transcrição: Falhou".
- **A11-05** Pílula de estado da casca: alteração de estado de um motor para Falhou é anunciada uma vez por região `aria-live="polite"` (sem repetir a cada snapshot).
- **A11-06** Interruptor "Modo desenvolvedor" (S20): papel `switch`; estado anunciado como "ligado" ou "desligado"; desabilitado anuncia o motivo (`aria-describedby` apontando para S13).
- **A11-07** Controles desabilitados têm motivo textual (R-09) ligado por `aria-describedby`.
- **A11-08** Botões "Copiar" (R23–R28) têm nome acessível "Copiar comando: <rótulo>" (ex.: "Copiar comando: Instalar"). O toast R33 é anunciado com `role="status"`.
- **A11-09** Diálogos (R-D1, R-D2, R-D3, 8.4): foco inicial em Cancelar; Esc fecha; ao fechar, o foco volta ao controle que abriu o diálogo.
- **A11-10** Campo JSON (D16): rótulo visível e erro ligado por `aria-describedby`. Campo de texto (D06): mesmo padrão.
- **A11-11** Alvos de toque e clique: botões 40 px de altura; interruptor 40 × 24 px; botões "Copiar" 30 px com área mínima de 40 px de toque.
- **A11-12** Contraste: texto de corpo e legendas usam os tokens de `docs/UI_DESIGN.md` com razão mínima de 4,5:1 sobre o fundo do cartão. Badges de Erro (#ff7d8a), Aviso (#f2c15c), Sucesso (#5ee0a0) e Info (#7693ff) são usados com texto negrito e fundo escuro.
- **A11-13** Nenhuma animação nesta aba (estado é texto). O ponto colorido da linha de conexão é decorativo (`aria-hidden`).
- **A11-14** Monoespaçado (comandos, JSON, resultado) usa `white-space: pre-wrap` e quebra de linha; nunca corta o comando no meio sem aviso.
- **A11-15** Reflow: com 720 px de largura, nenhum controle some e nenhuma linha de texto fica cortada horizontalmente (a área rola verticalmente).

---

## 11. Itens NOVO (precisa de mudança na ponte/Core), consolidados

| ID | Item | O que muda (mínimo) | Onde |
|---|---|---|---|
| N1 | Modo desenvolvedor persistente | Campo `developer_mode` (bool, padrão false) em `storage::Config` com revisão CAS; operação `developer_mode` {`revision`, `enabled`} idle-only; slot `setDeveloperMode(bool)`; propriedade `developerMode`. Alternativa: só memória da ponte (seção 8.2). | `src/storage.rs`, `src/protocol.rs`, `src/core.rs`, `app/bridge.py` |
| N2 | Reiniciar Core | Operação IPC `restart_core` que responde `ok`, grava o estado, encerra o processo com código 75; `gideon-launch` reinicia o Core com os mesmos argumentos; a ponte reconecta (0,5–5 s) e mostra `Reiniciando o Core…`; recusado com sessão ativa (`busy`). Slot `restartCore()`. | `src/protocol.rs`, `src/transport.rs`, `scripts/package_tools/gideon-launch`, `app/bridge.py` |
| N3 | Disparo de wake de teste | Slot `virtualWake()` que envia `VirtualWake` (operação já existente, exige `--virtual-input`). Recusado com sessão ativa. | `app/bridge.py` (Core já tem a operação) |
| N4 | Invocar capacidade com JSON | Slot `invokeCapabilityJson(capability, json_text)` que envia `capability_invoke` com objeto JSON (o Core já aceita `serde_json::Value`); valida objeto e 2 048 bytes antes. | `app/bridge.py` |
| N5 | Última configuração boa do motor LLM | Propriedade `llmLastKnownGood` (presença e par provedor/modelo de `llm.config.lkg`) e slot `rollbackLlm()` que envia `llm_rollback` com `llmRevision`. | `app/bridge.py` (Core já tem `llm_rollback`; `lkg` vem no snapshot) |
| N6 | Eventos e hora | Propriedade `recentEvents` (snapshot `events`, até 64) e hora de recebimento por `sequence` na ponte; remover a dependência de hora no Core. | `app/bridge.py` |
| N7 | Pacote e captura/fala | Propriedades `packPreflight`, `packAudioInput`, `packAudioOutput`, `packEngines`, `lastCapture`, `lastSpeech`, `transcript` (fonte, revisão). Campos já validados em `bridge.py` (`PACK_KEYS`, `CAPTURE_KEYS`, `SPEECH_KEYS`, `TRANSCRIPT_KEYS`). | `app/bridge.py` |
| N8 | Versões e hashes | `protocolVersion` (snapshot `version`), `packageInfo` (versão, commit, sha256 do binário e do `PACKAGE.json`, lidos do pacote instalado), `packHash`, `catalogSha256` (`HUB_KEYS`). | `src/protocol.rs` (versão), `app/bridge.py`; `packageInfo` pela ponte a partir do pacote |
| N9 | Armazenamento do catálogo | `hubOrphans` (contagem de `orphans`), `hubStorageError` (campos já validados em `HUB_KEYS`). | `app/bridge.py` |
| N10 | Mapeamentos de exibição | Tabelas novas: `ENGINE_LABELS` (ID do motor → nome exibido), `PACK_LABELS`, `SCOPE_LABELS` (`dev_virtual_en` → `Desenvolvimento · áudio virtual · inglês`), `EVENT_LABELS` (tabela 4), `CAPTURE_REASON_LABELS` (tabela 3.1 de `capture.reason`). Cada uma com teste de tabela (padrão de `scripts/test_bridge_protocol.py`). | `app/bridge.py` |
| N11 | Frases de código faltantes | Adicionar a `CODE_MESSAGES` os códigos marcados NOVO nas seções 3.3, 3.4 e 3.6, e remover `DIAG_LABELS` (R-04). | `app/bridge.py` |
| N12 | Fallback sem código cru | `code_message` devolve `Core recusou a ação.` e expõe o código só para Avançado (R-03). | `app/bridge.py` |
| N13 | Texto "Core desconectado" | Trocar `stateLabels.offline` de "Core indisponível" para "Core desconectado" (R-06). | `app/Main.qml` |
| N14 | Copiar comando | Escrita na área de transferência (sem leitura) para os botões R23–R28. | `app/Main.qml` |
| N15 | Confirmações | Diálogos R-D1, R-D2, R-D3 e 8.4 (texto da seção 7.8 e 8.4). Renomear "Cancelar" de invocação de capacidade para "Cancelar invocação". | `app/Main.qml` |
| N16 | Interruptor do modo | Interruptor S20 e diálogo 8.4 (texto exato). | `app/Main.qml` |

Itens que **não** precisam de mudança: Ferramenta de linha de comando (`gideon-install`, `gideon-launch`): existem e são só copiados. Preferências de feedback, rollback de preferências e recuperação de configuração (`recover_configuration`): existem.

---

## 12. Rastreio: achados e funcionalidades cobertos

| ID | Achado / funcionalidade | Onde esta spec trata | Situação |
|---|---|---|---|
| AC-17 | "Comando de texto" e "Invocar" aparecem na interface comum, sem separação de modo de desenvolvimento | Seção 8 (tudo atrás do interruptor), seção 9 (resumo fora de Diagnóstico) | Resolvido por esta spec (depende de N1, N3, N4) |
| NF-13 | Snapshot de captura (início, fim, amostras, hash, motivo) | M36–M37 (Motores); V10 (hash do PCM, em Desenvolvedor) | Coberto (depende de N7) |
| NF-14 | Snapshot de fala (amostras, trechos, hash, pico, RMS, tempo) | M21, M22 (Motores, Avançado) | Coberto (depende de N7) |
| NF-15 | Transcrição: revisão, confiança, `audio_end_us`, fonte | M39 (fonte e revisão em Avançado; confiança "não medida") | Coberto (depende de N7) |
| NF-16 | Pacote de voz: motores, preflight, entrada e saída | M08, M14, M19, M20, M30–M33, V03–V04 | Coberto (depende de N7) |
| NF-17 | Hub: órfãos, repositório, hash do catálogo, erro de armazenamento | R19 (órfãos e erro de armazenamento), V06 (hash do catálogo). `repository` e `retry_after` ficam fora (repositório fica em Conexões e `retry_after` é de conexões) | Coberto em parte |
| NF-18 | Eventos e sequência (anel de 64) | Seção 4 (tabela de tipos, fonte única), S23 (Últimos erros) | Coberto; sub-aba Eventos removida por decisão do dono |
| NF-21 | Atualização e reversão do pacote (`gideon-install update|rollback`) | R24, R25 (comandos copiáveis) | Coberto como comando de terminal (nenhum botão) |
| NF-22 | Reinício do Core | R03, R07, R-D1, N2 | Coberto; N2 IMPLEMENTADO (WP8: `coreRestart`) |
| NF-23 | Reparo de instalação (`gideon-install repair`) | R26, R30 | Coberto como comando de terminal |
| DU-01 | Estado de wake, STT e TTS em quatro lugares | Estado sem estados de motor (R-S5); detalhe só em Motores | Resolvido nesta aba |
| DU-02 | Diagnóstico em texto (rodapé, `DIAG_LABELS` minúsculas, texto da aba) | R-04, N11; rodapé removido (decisão 5) | Resolvido nesta aba (depende de N11) |

---

## 13. Pendências e verificações (antes de implementar)

1. **Unidade de pico e RMS** (M22): `src/tts.rs` declara `peak: f32` e `rms: f64` (linhas 31–32) sem unidade documentada. Confirmar antes de exibir. Até confirmar, mostrar só `Pico: <valor> · RMS: <valor>` sem unidade, em Avançado.
2. **Limite do JSON de invocação**: 2 048 bytes é decisão desta spec, com base no limite de quadro de entrada do Core (4096 bytes, `docs/BASE_UI_MAP.md`). Confirmar o limite exato do quadro antes de implementar N4.
3. **Nomes de motores**: ENGINE_LABELS depende dos IDs de motor gerados por `src/pack.rs` (descritor do perfil). Confirmar os IDs reais antes de fechar a tabela de nomes.
4. **Hora de recebimento**: o anel do Core não tem hora (`src/protocol.rs`, `struct Event`). A ponte registra a hora de recebimento; confirmar se isso basta (sem hora do evento real).
5. **`llm.config.lkg`** (N5): o campo é citado em `docs/UI_INVENTORY.md` (NF-06); confirmar que existe no snapshot real antes de exibir R15.
6. **Número de pendências** (badge "•N" da aba): a soma depende de três motores e da configuração. Revisar se o dono quer contar também plugins em `failed`.
7. **Texto de 30 s** do reinício (R-D1): valor de decisão desta spec; confirmar contra o tempo real de reinício do Core com o pacote instalado.
8. **Ícone da aba** (`utilities-system-monitor`): confirmar que o tema Breeze tem o ícone.
9. **Desenhos ASCII**: escala aproximada. As coordenadas exatas são as das tabelas de grade (seções 5.4, 6.4, 7.4, 8.5).
