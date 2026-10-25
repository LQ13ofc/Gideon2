# Especificação de tela: Configurações (aba de nível 1)

Status: especificação-alvo para revisão. Nenhuma linha de código foi alterada.
Aba: **Configurações** (4ª aba da barra de nível 1; atalho Ctrl+4).
Sub-abas (nível 2), nesta ordem: **Voz e Wake · Áudio · Dispositivos · Aparência · Privacidade · Geral**.

Fontes lidas: `docs/UI_IA.md` (seção 4, Regras de unicidade, Casca), `docs/ui-spec/00-casca.md`, `docs/UI_NOTION_REQS.md` (B2),
`docs/UI_INVENTORY.md` (P1, P2, P3, D1, D5–D9, AC-01, AC-05, AC-06, AC-09, AC-15, NF-14, NF-19, NF-22, NF-23, NT-06 a NT-17),
`docs/BASE_UI_MAP.md`, `docs/A1.md`, `app/bridge.py` (preferências, `select_wake`, `saveFeedback`, `savePreferences`,
`rollbackPreferences`, `recoverConfiguration`, `configurationStatus`, `CODE_MESSAGES`, `OPS`, `PENDING`, `WAKE_QUALIFICATION_LABELS`),
`app/Main.qml` (diálogo `preferences`, `themeIndex`, `accentColor`, `stateLabels`), `src/storage.rs` (`Config`, `commit_preferences`,
`select_wake`, `rollback_preferences`, `recover_configuration`), `src/core.rs` (ordem de validação das operações de preferências).

---

## 0. Legenda de marcas

| Marca | Significado |
|---|---|
| **NOVO (precisa de mudança na ponte/Core)** | Não existe hoje. Exige alteração em `app/bridge.py`, `src/` ou no pacote. A marca diz exatamente o quê. |
| **NOVO (só QML, sem ponte/Core)** | Não existe hoje. Muda só `app/Main.qml` ou componentes QML. Usada apenas quando a mudança não toca a ponte nem o Core. |
| **Indisponível: <motivo>** | Texto exibido em linha desativada quando o recurso não existe hoje. O controle fica esmaecido e o motivo aparece em 12 px abaixo dele. |
| **Básico / Avançado** | Nível do item. Avançado só aparece com "Mostrar opções avançadas" ligado (seção 5). |
| **SINTÉTICO** | Selo discreto ao lado de dados simulados. |

Convenção de coordenadas: pixels da janela de referência **1380 × 904**, origem no canto superior esquerdo.
Formato: `(x, y, largura, altura)`. Botões têm altura 40 px; interruptores (switch) 24 px de altura e 44 px de largura.

---

## 1. Geometria comum da aba

Herdada de `docs/ui-spec/00-casca.md`. Não repetir a casca; esta seção só fixa o que a aba usa.

| Região | Posição (x, y, w, h) | Conteúdo desta aba |
|---|---|---|
| Barra de sub-abas | (0, 56, 1380, 44) | Seis rótulos: Voz e Wake · Áudio · Dispositivos · Aparência · Privacidade · Geral. Sub-aba ativa com sublinhado. |
| Título da sub-aba | (32, 116, 1000, 30) | 24 px bold. Texto da seção 7 de cada sub-aba. |
| Subtítulo | (32, 150, 1000, 20) | 14 px `#9db0e0`, máximo 90 caracteres. |
| Ação primária | (1228, 116, 120, 40) | Só existe em **Áudio** ("Aplicar"). Nas outras sub-abas não há ação primária no cabeçalho. |
| Faixa de resumo | (32, 184, 1316, 40) | Uma linha de texto 14 px bold com badges à direita. |
| Faixa de aviso (opcional) | (140, 236, 1100, 48) | Só aparece quando há estado global (seção 4). Empurra todo o conteúdo para baixo em 60 px. |
| Área de conteúdo | (140, 236, 1100, até 864) | Largura 1100 px, centralizada na janela de 1380 px. Rola na vertical. |
| "Como funciona" | Última linha do conteúdo, (140, y, 1100, 56) | Recolhido por padrão. Expandido, cresce cerca de 120 px. |

**Grade de 12 colunas** dentro da área de conteúdo (largura 1100, espaço 16):
largura da coluna = (1100 − 11 × 16) / 12 = **77 px**.
Início da coluna k: x = 140 + (k − 1) × 93. Largura de um vão de n colunas: 77n + 16(n − 1).

| Vão | Largura (px) | Início das colunas (x) |
|---|---|---|
| 12 colunas | 1100 | 140 |
| 8 colunas | 728 | 140 |
| 6 colunas | 542 | 140 e 698 |
| 4 colunas | 356 | 140, 884 |
| 3 colunas | 263 | 140, 326, 512 (não usado) |

Cartões: raio 14 px, padding 20 px, título 17 px semibold (no ponto (x+20, y+20)), corpo 14 px, legenda 12 px.
Cada sub-aba tem no máximo **3 cartões**. "Como funciona" não conta como cartão.

**Reflow:**
- 900 a 1239 px de largura: a área de conteúdo passa a ter largura `janela − 64` (sem centralização); a grade de 12 colunas continua.
- Abaixo de 900 px: todos os cartões passam a ocupar 12 colunas (empilhados); o cabeçalho empilha título, subtítulo e ação primária; a barra de sub-abas rola na horizontal; linhas com rótulo e controle mantêm rótulo à esquerda e controle à direita; tabelas quebram linha.
- Abaixo de 720 px a janela não é suportada (tamanho mínimo da casca).

**Toast**: mensagem de sucesso ou erro de ação de preferência aparece no canto inferior direito por 4 s (regra da casca).

---

## 2. Regras gerais: aplicar ou salvar

Decisão adotada para toda a aba. Justificativa: a ponte grava cada alteração de preferência como uma nova revisão do arquivo de configuração, com `RestartRequired` quando a frase muda (`src/storage.rs`, `commit_preferences`). Gravar a cada movimento de slider geraria revisões descartáveis e risco de `stale_preferences`.

| Tipo de controle | Comportamento | Motivo |
|---|---|---|
| Interruptor (switch) de liga/desliga | **Salva ao mudar**, sem botão. Confirma com toast "Preferências salvas pelo Core". | Binário, reversível, sem efeito destrutivo. Feedback imediato. |
| Controle numérico ou deslizante (volume, prazo da sessão) | **Aplicar explícito**. Mudança fica como rascunho até "Aplicar" (Áudio) ou "Salvar prazo" (Voz e Wake). Indicador "Alterações não aplicadas" enquanto houver rascunho. | Evita uma gravação por arrasto. |
| Escolha de frase de despertar | **Confirmação** em diálogo (seção 8.1). Ao confirmar, salva; a frase só vale após reinício do Core. | Única alteração que exige reinício. Precisa de confirmação explícita. |
| Seleção de tema e cor | **Aplicar na hora** (prévia ao vivo). Persistência: ver seção 10. | Efeito visual, sem gravação hoje. |
| Restaurar padrões / Preservar arquivo | **Confirmação** em diálogo (seções 8.2 e 8.3). | Substitui a configuração inteira. |
| Apagar dados de plugin | **Confirmação** (seção 8.4). | Destrutivo, sem volta. |

**Regra de revisão.** Toda gravação envia a revisão atual da configuração. Enquanto uma gravação estiver pendente (`preferences_request` ou `pending`), **todos os demais controles de preferência ficam desativados** com o texto "Enviando ao Core" (texto de `PENDING`). Isso evita que um segundo toque envie uma revisão já superada.

**Regra de campos vizinhos.** Um interruptor que salva sozinho envia somente o próprio campo e mantém o valor salvo do outro campo, nunca o rascunho:
- Resposta por voz (Áudio) → `savePreferences(audible_novo, prazo_salvo)`.
- Indicador visual (Aparência) → `saveFeedback(visual_novo, volume_salvo)`.
- Prazo da sessão (Voz e Wake, "Salvar prazo") → `savePreferences(audible_salvo, prazo_novo)`.
- Volume (Áudio, "Aplicar") → `saveFeedback(visual_salvo, volume_novo)`.

**Quando a mudança vale.**
- Resposta por voz, indicador visual, volume e prazo da sessão: valem a partir da próxima sessão de voz ou da próxima resposta. Texto fixo: "Alterações se aplicam à próxima sessão." (D1-T3, mantido).
- Frase de despertar: vale somente após reinício do Core.

---

## 3. Estados globais da aba

Afetam todas as sub-abas. Quando um estado tem faixa de aviso, a faixa ocupa (140, 236, 1100, 48) e o conteúdo desce 60 px.

| Estado | Condição de origem | Faixa de aviso (texto exato) | Controles de preferência | Ações sempre disponíveis |
|---|---|---|---|---|
| Normal | `core.connected` e `configurationStatus == "ready"` e sem sessão | (nenhuma) | Habilitados | Todas |
| Core desconectado | `core.connected` falso | "Indisponível: Core desconectado. Os valores mostrados são os últimos conhecidos." | Desativados; valores em cinza | Nenhuma de escrita |
| Sessão de voz em andamento | `core.sessionId` não vazio | "Indisponível agora: sessão de voz em andamento. Tente quando o Gideon estiver em espera." | Desativados (lógica de `preferencesAvailable`) | Leitura |
| Reinício pendente | `configurationStatus == "restart_required"` | "Configuração salva; reinicie o Core para ativar os recursos" (texto da ponte) | Desativados: "Indisponível: reinício do Core pendente." | Botão "Reiniciar Core" (implementado, seção 8.5) |
| Modo seguro | `configurationStatus == "safe_mode"` | "Modo seguro: configuração inválida preservada; áudio e comandos bloqueados" (texto da ponte, com recuperação). Sem recuperação: "Modo seguro: arquivo excede o limite de recuperação automática; conteúdo preservado" | Desativados: "Indisponível: modo seguro." Só o botão de recuperação de Geral funciona | Recuperação (seção 8.3) |
| Gravação pendente | `pending` ou `preferences_request` | (nenhuma; o controle mostra "Enviando ao Core") | Desativados até a resposta | Nenhuma |

Observação: o reinício do Core pela UI existe (seção 8.5: `coreRestart` em `app/bridge.py`, botão em `app/pages/DiagRecuperacao.qml`; verificado no WP8, `docs/WP8.md`). Ele é controlado pela ponte e espera o Core voltar; o launcher inicia o Core de novo.

---

## 4. Mapeamento do diálogo D1 "Preferências" (será removido)

O diálogo `preferencesDialog` (D1, `app/Main.qml:161-202`) deixa de existir. Cada elemento vai para uma sub-aba:

| Origem (D1) | Conteúdo | Destino nesta aba |
|---|---|---|
| D1-C1 "Preservar arquivo e restaurar padrões" | Recuperação em modo seguro | Geral, cartão 3 (seção 7.6) e diálogo 8.3 |
| D1-C2 / D1-C3 Frase do pack e "Selecionar" | Escolha de frase | Voz e Wake, cartão 1, com confirmação 8.1 |
| D1-C4 "Resposta por voz (saída virtual)" | Interruptor | Áudio, cartão 2 |
| D1-C5 "Indicador visual de atividade" | Interruptor | Aparência, cartão 3 (ver seção 10 e nota sobre a unicidade em 7.2) |
| D1-C6 / D1-C7 Ganho e "Salvar indicador e ganho" | Volume | Áudio, cartão 1, com "Aplicar" |
| D1-C8 Prazo (50 a 60000 ms) | Prazo da sessão | Voz e Wake, cartão 2 (avançado, seção 5.1) |
| D1-C9 "Salvar" | Gravação de resposta e prazo | Eliminado: cada controle salva o próprio campo (seção 2) |
| D1-C10 "Restaurar anterior" | Rollback de uma etapa | Geral, cartão 3 (avançado) |
| D1-C11 "Motor LLM" | Abre o diálogo D3 | Privacidade, cartão 2 (link para Modelos LLM) |
| D1-C12 "Fechar" | Fecha o diálogo | Eliminado (não há diálogo) |
| D1-I1 Mensagem de configuração | Faixa de aviso | Faixa de aviso (seção 3) |
| D1-I2 Descrição do pack | "<pack> · em desenvolvimento · virtual" | Voz e Wake, faixa de resumo (texto curto) e Voz da Base em Áudio |
| D1-I3 Qualificação | Texto da frase escolhida | Cartões de frase (seção 9) |
| D1-I4 Ganho | "Ganho da saída virtual: N% (0% = mudo)" | Áudio, cartão 1 |
| D1-I5 "Atual no Core" | Voz e prazo | Áudio (estado da resposta) e Voz e Wake (prazo) |
| D1-I6 Resultado de preferências | Texto de retorno | Toast (seção 1) |
| D1-T1 Texto de privacidade | "Privacidade: capturas e legendas em memória; ..." | Privacidade, cartão 1 (reescrito, seção 7.5) |
| D1-T2 / D1-T3 | Rótulos e aviso de próxima sessão | Rótulos das sub-abas e seção 2 |

---

## 5. Interruptor "Mostrar opções avançadas"

- Fica em **Geral**, cartão 2 (seção 7.6).
- Efeito: revela os itens avançados listados abaixo em **todas** as sub-abas. Não altera valores.
- Padrão: **desligado**.
- Persistência: **NOVO (precisa de mudança na ponte/Core)**: campo `show_advanced` (booleano, padrão falso) em `config.json` (`src/storage.rs`, `Config`), gravado com revisão (mesmo padrão de `feedback_preferences`). Sem essa mudança, o interruptor vale só durante a execução da janela.
- Quando desligado, os itens avançados saem da tela e da ordem de foco, e também do leitor de tela.

### 5.1 Lista completa de itens avançados por sub-aba

| Sub-aba | Itens revelados |
|---|---|
| Voz e Wake | (a) Prazo da sessão em milissegundos, com "Salvar prazo" (controle D1-C8, faixa 50 a 60000, passo 1000). (b) Código de qualificação de cada frase (`dev_qualified` ou `poc_required`). (c) Identificador técnico de cada frase (ex.: `hey_gideon`). (d) Código do estado do wake (`wake_status`). |
| Áudio | (a) Ganho salvo no Core, em número (ex.: "Ganho salvo no Core: 100%"). (b) Código do estado da resposta (`speech_status`). (c) Idioma do pacote: "Idioma do pacote: inglês (EN)". |
| Dispositivos | (a) Formato da entrada: "Formato da entrada: PCM mono 16 kHz". (b) Código do estado de captura (`stt_status`). (c) Sink: "Sink: virtual (sem ID de dispositivo)". |
| Aparência | (a) Valor hexadecimal da cor de destaque (ex.: `#7693ff`). (b) Valor salvo do indicador visual (`visual_feedback`, verdadeiro ou falso). |
| Privacidade | (a) Valor salvo do consentimento de nuvem, em booleano. (b) Nota: "Inclui modelos personalizados" dentro do diálogo de apagar dados. |
| Geral | (a) Botão "Restaurar anterior" (D1-C10) e seu texto de ajuda. (b) "Revisão da configuração: N" (`preferencesRevision`). |

Nenhum item de nível Básico some quando o interruptor muda.

---

## 6. Convenção dos wireframes

Cada sub-aba traz o seu wireframe em escala aproximada: 1 coluna = 10 px, 1 linha = 20 px. A origem do desenho é o canto superior esquerdo da área de conteúdo (x 140, y 236); o desenho mostra os 1100 px de largura da área. Os textos do desenho estão sem acentos por ser ASCII; o texto exato está nas tabelas. O botão "Aplicar" (Áudio) fica no cabeçalho e não aparece no desenho. Os botões são desenhados com 1 linha a mais que a altura real; as coordenadas exatas valem as das tabelas.

---

## 7. Sub-abas

### 7.1 Voz e Wake

**Título**: Voz e Wake · **Subtítulo**: "Frase de despertar certificada, prazo da sessão e estado do wake."
**Faixa de resumo**: "Frase ativa: <nome> · <qualificação> · Estado do wake: <estado>" (dados: `active_phrase` e `wake_status`).

**Objetivo.** Escolher entre as frases de despertar certificadas do pacote, ver o estado do wake e da captura e saber o que foi comprovado.

**Condição de aparecimento.** Sempre visível. Sem pacote (`wakeChoices` vazio), o cartão 1 mostra o texto "Nenhum pacote de voz configurado. Reparo só pela linha de comando (gideon-install repair)." e os tiles somem.

**Nível.** Básico (ocasional). Itens avançados: seção 5.1, item 1.

**Layout em grade.**
- Cartão 1 "Frase de despertar": vão de 8 colunas, (140, 236, 728, 320).
- Cartão 2 "Sessão e estado": vão de 4 colunas, (884, 236, 356, 320).
- Cartão 3 "Ajustes de detecção": vão de 12 colunas, (140, 572, 1100, 110).
- "Como funciona": (140, 698, 1100, 56).
- Com faixa de aviso, tudo desce 60 px.
- Reflow abaixo de 900 px: cartões empilhados, tiles de frase em uma coluna (cada um 100% de largura).

**Wireframe**

```
+-C1 Frase de despertar-------------------------------------------------+ +-C2 Sessao e estado---------------+
|                                                                       | |                                  |
|                                                                       | |                                  |
|                                                                       | | +-Prazo maximo: 30 s-----------+ |
| +--------------------------------+ +--------------------------------+ | | +-Estado do wake---------------+ |
| | Hey Gideon (em desenvolvimento | | Okay Gideon (requer prova)     | | | +------------------------------+ |
| |                                | |                                | | | +-Captura----------------------+ |
| +--------------------------------+ +--------------------------------+ | |                                  |
|                                                                       | | +-ms [spin] (-+  +-Salvar praz-+ |
| +-------------------------------------------------------------------+ | | +-------------+  +-------------+ |
| | Texto honesto de qualificacao                                     | | |                                  |
| |                                                                   | | |                                  |
| +-------------------------------------------------------------------+ | |                                  |
| +-Reiniciar Core-+                                                    | |                                  |
| +----------------+                                                    | |                                  |
+-----------------------------------------------------------------------+ +----------------------------------+

+-C3 Ajustes de deteccao-------------------------------------------------------------------------------------+
|                                                                                                            |
|                   +-Sensibilidade (desativada)-------+  +-Indisponivel: limiar fixo----------------------+ |
|                   +----------------------------------+  +------------------------------------------------+ |
+------------------------------------------------------------------------------------------------------------+

+------------------------------------------------------------------------------------------------------------+
| Como funciona (recolhido)                                                                                  |
+------------------------------------------------------------------------------------------------------------+
```

**Elementos**

| # | Região / posição (x, y, w, h) | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| VW-1 | C1 título (160, 256) | Texto | "Frase de despertar" | Texto fixo | Nenhuma | Sempre | Básico |
| VW-2 | C1 subtítulo (160, 282, 688, 16) | Texto 12 px | "Só frases qualificadas podem ser escolhidas. A troca vale depois de reiniciar o Core." | Texto fixo | Nenhuma | Sempre | Básico |
| VW-3 | Tile "Hey Gideon" (160, 306, 336, 96) | Cartão selecionável | Linha 1: "Hey Gideon". Linha 2: badge "em desenvolvimento" (tom Info). Linha 3: "Salva" ou "Ativa neste processo" (ou ambas). Linha 4 (12 px): "Qualificada em desenvolvimento; validação física pendente" | `core.wakeChoices` (`id`, `text`, `qualification_label`); `active_phrase` (via `window.activeWake()`); frase salva: **NOVO (precisa de mudança na ponte/Core)**: propriedade `savedWakeId` com `preferences.wake_phrase`. Hoje esse valor só existe dentro do texto de `packDescription`. | Clique: se `dev_qualified` e `preferencesAvailable`, abre diálogo 8.1. Confirmado → `core.selectWake(id)` → Core `select_wake` → toast "Preferências salvas pelo Core" e faixa "Configuração salva; reinicie o Core para ativar os recursos". | Normal; selecionado (borda de 2 px no acento); desativado (sessão, modo seguro, desconectado); pendente de reinício (salva ≠ ativa: linha 3 mostra "Reinício necessário para ativar esta frase") | Básico |
| VW-4 | Tile "Okay Gideon" (512, 306, 336, 96) | Cartão desativado | Linha 1: "Okay Gideon". Linha 2: badge "requer prova de conceito" (tom Aviso). Linha 3: "Bloqueada: sem qualidade aprovada". Linha 4 (12 px): "Pode ser transcrita como 'K Gideon'." Linha 4 mostra o texto da qualificação: "Requer prova de conceito: frase sem qualidade aprovada" | `core.wakeChoices` (`qualification`) | Sem ação. Tooltip: "Indisponível: requer prova de conceito; sem qualidade aprovada". O Core recusaria com `wake_not_qualified`. | Sempre desativado | Básico |
| VW-5 | Texto honesto (160, 418, 688, 72) | Texto 14 px, 3 linhas | Texto completo na seção 9.2 | Texto fixo (baseado em `docs/A1.md`) | Nenhuma | Sempre | Básico |
| VW-6 | Faixa de estado do reinício (356, 500, 492, 40) | Texto 14 px | "Configuração salva; reinicie o Core para ativar os recursos" | `core.configurationMessage` | Nenhuma | Só com `configurationStatus == "restart_required"` | Básico |
| VW-7 | Botão "Reiniciar Core" (160, 500, 180, 40) | Botão secundário | "Reiniciar Core" | **IMPLEMENTADO (WP8)**: operação de reinício controlado `core_restart` (seção 8.5). | Abre diálogo 8.5. Confirmado → reinício do Core. | Só aparece com reinício pendente. Sem a mudança: desativado com "Indisponível: o app não reinicia o Core ainda." | Básico |
| VW-8 | C2 título (904, 256) | Texto | "Sessão e estado" | Texto fixo | Nenhuma | Sempre | Básico |
| VW-9 | Linha prazo (904, 290, 316, 26) | Texto | "Prazo máximo da sessão: 30 s" (converte ms para segundos, arredonda para segundos inteiros) | `core.sessionTimeout` | Nenhuma (só leitura) | Sempre | Básico |
| VW-10 | Linha estado do wake (904, 324, 316, 26) | Texto | "Estado do wake: <estado>". Estado = `statusLabels[wakeStatus]`. Sem valor: "Indisponível" | `core.wakeStatus` | Nenhuma | Sempre | Básico |
| VW-11 | Linha captura (904, 358, 316, 26) | Texto | "Captura: <estado>". Estado = `statusLabels[sttStatus]`. Sem valor: "Indisponível" | `core.sttStatus` | Nenhuma | Sempre | Básico |
| VW-12 | Prazo editável (904, 394, 150, 40) | Campo numérico (spin) | Rótulo acessível "Prazo da sessão em milissegundos" | `core.sessionTimeout` | Digitar ou ajustar: rascunho | Desativado em sessão, modo seguro, reinício pendente, desconectado | **Avançado** |
| VW-13 | Botão "Salvar prazo" (1070, 394, 150, 40) | Botão primário | "Salvar prazo" | Ação: `core.savePreferences(audible_salvo, prazo)` | Salva; toast "Preferências salvas pelo Core". Faixa 50 a 60000 ms; fora da faixa a tela não envia (mensagem em VW-14) | Desativado sem rascunho | **Avançado** |
| VW-14 | Linhas avançadas (904, 440, 316, 60) | Texto 12 px, 3 linhas | "Código de qualificação: dev_qualified" (ou poc_required). "Identificador técnico: hey_gideon". "Estado técnico do wake: <wake_status>". Se o prazo estiver fora de 50 a 60000 ms: "Valor fora do limite permitido (50 a 60000 ms); nada foi salvo." | `wakeChoices` (`qualification`, `id`); `wakeStatus`; validação local | Nenhuma | Sempre que avançado ligado | **Avançado** |
| VW-15 | C3 título (160, 592) | Texto | "Ajustes de detecção" | Texto fixo | Nenhuma | Sempre | Básico |
| VW-16 | Sensibilidade (160, 622, 170, 32) e controle desativado (340, 622, 360, 32) | Rótulo + deslizante desativado | "Sensibilidade" | Nenhuma (NT-07, sem campo no Core) | Sem ação | Sempre desativado | Básico |
| VW-17 | Motivo (720, 622, 500, 32) | Texto 12 px | "Indisponível: limiar de detecção fixo no pacote; o Core não tem ajuste de sensibilidade." | Texto fixo | Nenhuma | Sempre | Básico |
| VW-18 | "Como funciona" (140, 698, 1100, 56) | Bloco recolhível | Título: "Como funciona". Expandido: "A frase de despertar muda só entre as opções certificadas do pacote. Trocar exige reiniciar o Core. O prazo da sessão vale na próxima sessão de voz." | Texto fixo | Expande e recolhe | Sempre | Básico |

**Estados.**
- *Normal*: tiles ativos, faixa de estado conforme o Core.
- *Sessão de voz*: tiles e prazo desativados; faixa de aviso de sessão (seção 3).
- *Reinício pendente*: tile salvo mostra "Reinício necessário para ativar esta frase"; VW-6 e VW-7 aparecem; demais controles desativados.
- *Modo seguro*: tiles e prazo desativados; VW-3 e VW-4 mostram "Indisponível: modo seguro."
- *Sem pacote*: texto "Nenhum pacote de voz configurado. Reparo só pela linha de comando (gideon-install repair)." no lugar dos tiles.
- *Erro ao salvar*: linha de erro de 12 px abaixo do cartão afetado com o texto do código (seção 12). Toast de erro.
- *Gravando*: tiles e botões desativados; texto "Enviando ao Core".

**Textos de rótulo, placeholder e tooltip.** Campo de prazo sem placeholder. Tooltip do tile desativado: "Indisponível: requer prova de conceito; sem qualidade aprovada".

**Regras.**
- A frase só muda pelas opções certificadas do pacote (`select_wake` rejeita as demais).
- Trocar frase não encerra a sessão atual; a frase nova vale depois do reinício.
- Sem frase arbitrária: não há campo de texto livre para a frase.

---

### 7.1A Idiomas (Frente 2, NOVO)

**Título**: Idiomas · **Subtítulo**: "Em que idiomas a IA fala e entende. Só idiomas instalados podem ser escolhidos."
**Faixa de resumo**: nenhuma. A página mostra duas seções e um botão Aplicar.

**Seção "A IA entende em…"** (STT): caixas de seleção (GCheckbox), de 1 a 3 idiomas. Dados: `languages.engines.stt` e `languages.stt_selected`.
**Seção "A IA fala em…"** (TTS): botões de rádio (GRadio), um idioma por vez; a voz segue o idioma. Dados: `languages.engines.tts`, `languages.tts_selected`, `languages.tts_voice`.

Cada linha mostra: nome, estado (**Instalado** / **Não instalado** / **Não suportado**), tamanho ("cerca de N MB", "(parcial)" quando o total é soma de arquivos conhecidos), licença, qualidade ("não medido" quando não houver medição) e, quando houver, o motivo.

**Estados e controles**
- `bundled` (Instalado): selecionável. Hoje: inglês (TTS e STT) e o wake em inglês.
- `available_not_installed` (Não instalado): aparece desativado, com o botão **Instalar** desativado e o motivo **"Aguardando aprovação do download pelo dono"**. Nenhum download é feito pela página.
- `unsupported` (Não suportado): desativado, com o motivo do catálogo. Hoje: wake em português e em francês.

**Regras.**
- Aplicar envia uma única operação `language_preference` com a lista de STT, o idioma de fala e a voz (CAS em `revision`). O botão só fica ativo com mudança e com 1 a 3 idiomas de escuta.
- O Core recusa idioma não instalado (`language_not_installed`), idioma sem suporte (`language_unsupported`) e lista inválida (`invalid_languages`). A recusa não grava nada.
- A escolha salva vale no próximo início do Core: aparece a nota "Idioma salvo. Reinicie o Core para aplicar." (`restart_required.stt` / `restart_required.tts`).
- Desfazer usa a reversão de preferências existente. Se o valor anterior não estiver instalado, a reversão é recusada (`language_not_installed`).
- O idioma da interface é outra configuração e continua em português.

**Medição e honestidade.** O estado "Instalado" de um idioma significa que o pacote tem os arquivos, não que a qualidade foi medida. A qualidade só aparece como medida quando houver evidência em `docs/evidence/`. Pesquisa e lista de downloads: `docs/research/idiomas-stt-tts.md`.

**Dados do Core.** Snapshot `languages` (`version`, `engines`, `stt_selected`, `tts_selected`, `tts_voice`, `restart_required`, `install`); preferências `stt_languages`, `tts_language`, `tts_voice` (ausentes em ledgers antigos: padrão inglês).

---

### 7.2 Áudio

**Título**: Áudio · **Subtítulo**: "Volume e feedback da resposta do Gideon. Vale a partir da próxima sessão."
**Ação primária (cabeçalho)**: "Aplicar" em (1228, 116, 120, 40). Ativa só com rascunho de volume e preferências disponíveis.
**Faixa de resumo**: "Saída: virtual · Voz: Alba · Volume: <N>% · Resposta por voz: <ligada|desligada>".

**Objetivo.** Regular o volume da resposta falada e ligar ou desligar a resposta por voz.

**Condição de aparecimento.** Sempre visível. Controles de volume e voz dependem de `voiceAvailable`.

**Nível.** Básico. Itens avançados: seção 5.1 (Áudio).

**Nota de unicidade (decisão).** A seção 4.2 da IA lista o interruptor "indicador visual" em Áudio, mas a tabela "Regras de unicidade" de `docs/UI_IA.md` diz que o indicador visual fica só em **Configurações › Aparência**. Esta especificação segue a regra de unicidade: o interruptor fica em Aparência (seção 7.4) e aqui há só um texto com link. Decisão a confirmar pelo dono (seção 15).

**Layout em grade.**
- Cartão 1 "Volume da resposta": 6 colunas, (140, 236, 542, 250).
- Cartão 2 "Resposta": 6 colunas, (698, 236, 542, 250).
- Cartão 3 "Voz": 12 colunas, (140, 502, 1100, 150).
- "Como funciona": (140, 668, 1100, 56).
- Reflow abaixo de 900 px: cartões empilhados.

**Wireframe**

```
+-C1 Volume da resposta------------------------------+  +-C2 Resposta----------------------------------------+
|                                                    |  |                                                    |
|                                                    |  |                                                    |
| +-slider 0-100---------------------------+  +-100-+|  | +-Resposta por voz (saida virtual)  [sw]---------+ |
| +----------------------------------------+  +-----+|  | +------------------------------------------------+ |
| +-0% = mudo. Nao altera volume do host-----------+ |  | +-Indicador visual: ver Aparencia  [link]--------+ |
| +------------------------------------------------+ |  | +------------------------------------------------+ |
| +-Alteracoes nao aplicadas-----------------------+ |  |                                                    |
|                                                    |  | +-Resposta: Em espera----------------------------+ |
|                                                    |  |                                                    |
+----------------------------------------------------+  +----------------------------------------------------+

+-C3 Voz-----------------------------------------------------------------------------------------------------+
|                                                                                                            |
|                                                                                                            |
| +-Pocket TTS - Alba - ingles - saida virtual-------------------------------------------------------------+ |
| +-Escolha de voz (desativada-+                                                                             |
| +----------------------------+  +-Indisponivel: escolha de voz nao implementada----------------------+     |
| +-Avancado: idioma do pacote ingles (EN)-----------------------------------------------------------------+ |
+-+--------------------------------------------------------------------------------------------------------+-+

+-Como funciona (recolhido)----------------------------------------------------------------------------------+
+------------------------------------------------------------------------------------------------------------+
```

**Elementos**

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| AU-1 | C1 título (160, 256) | Texto | "Volume da resposta" | Texto fixo | Nenhuma | Sempre | Básico |
| AU-2 | C1 subtítulo (160, 282) | Texto 12 px | "Ganho da resposta por voz na saída virtual. Vale a partir da próxima sessão." | Texto fixo | Nenhuma | Sempre | Básico |
| AU-3 | Deslizante (160, 318, 420, 40) | Slider 0 a 100, passo 5 | Nome acessível: "Volume da resposta por voz, por cento" | `core.outputVolume` (valor salvo); rascunho local | Arrastar altera só o rascunho. Nunca grava. | Desativado sem `preferencesAvailable` ou sem `voiceAvailable` | Básico |
| AU-4 | Valor (596, 318, 70, 40) | Texto 14 px bold | "<N>%" (valor do rascunho) | Rascunho | Nenhuma | Mostra "<N>%" | Básico |
| AU-5 | Dica (160, 362, 502, 24) | Texto 12 px | "0% = mudo. Não altera o volume do sistema do host." | Texto fixo (baseado em `docs/BASE_UI_MAP.md`) | Nenhuma | Sempre | Básico |
| AU-6 | Aviso de rascunho (160, 386, 502, 24) | Texto 12 px, tom Aviso | "Alterações não aplicadas" | Rascunho ≠ salvo | Nenhuma | Só com rascunho | Básico |
| AU-7 | Botão "Aplicar" (1228, 116, 120, 40) | Botão primário | "Aplicar" | `core.saveFeedback(visual_salvo, volume_rascunho)` → Core `feedback_preferences` | Grava volume. Toast "Preferências salvas pelo Core". Rascunho vira valor salvo. | Desativado sem rascunho, sem `preferencesAvailable` ou sem `voiceAvailable` | Básico |
| AU-8 | C2 título (718, 256) | Texto | "Resposta" | Texto fixo | Nenhuma | Sempre | Básico |
| AU-9 | Interruptor (718, 296, 502, 40) | Interruptor com rótulo | "Resposta por voz (saída virtual)". Sem motor de voz: rótulo "Resposta por voz indisponível" e linha "Indisponível: motor de voz não está disponível no Core." | `core.audibleFeedback`; `core.voiceAvailable` | Muda → `core.savePreferences(novo, prazo_salvo)`. Toast "Preferências salvas pelo Core". Erro: volta ao valor anterior | Desativado com sessão, modo seguro, reinício pendente ou sem voz | Básico |
| AU-10 | Link de indicador (718, 344, 502, 40) | Texto com link | "Indicador visual: <ligado|desligado>. Alterar em Aparência." | `core.visualFeedback` | Clique → muda para a sub-aba Aparência | Sempre | Básico |
| AU-11 | Estado da resposta (718, 420, 502, 24) | Texto 14 px | "Resposta: <estado>". Estado = `statusLabels[speechStatus]`; sem valor: "Indisponível" | `core.speechStatus` | Nenhuma | Sempre | Básico |
| AU-12 | Código da resposta (718, 448, 502, 24) | Texto 12 px | "Código do estado da resposta: <speech_status>" | `core.speechStatus` | Nenhuma | Sempre | **Avançado** |
| AU-13 | C3 título (160, 522) | Texto | "Voz" | Texto fixo | Nenhuma | Sempre | Básico |
| AU-14 | Voz atual (160, 552, 1060, 24) | Texto 14 px | "Voz da Base: Pocket TTS · Alba · inglês · saída virtual" | Texto fixo com a voz do pacote (`core.packDescription`) | Nenhuma | Sempre | Básico |
| AU-15 | Escolha de voz (160, 584, 300, 40) | Lista suspensa desativada | Rótulo acessível "Escolha de voz (indisponível)" | Nenhuma | Sem ação | Sempre desativado | Básico |
| AU-16 | Motivo da escolha (480, 592, 680, 24) | Texto 12 px | "Indisponível: escolha de voz não implementada; só a voz do pacote existe." | Texto fixo | Nenhuma | Sempre | Básico |
| AU-17 | Idioma do pacote (160, 628, 1060, 24) | Texto 12 px | "Idioma do pacote: inglês (EN)" | Texto fixo (pacote valida `language == "en"`) | Nenhuma | Sempre | **Avançado** |
| AU-18 | "Como funciona" (140, 668, 1100, 56) | Bloco recolhível | Expandido: "O volume é aplicado ao áudio gerado pelo Gideon antes da saída virtual. Ele não muda o volume do sistema nem do dispositivo." | Texto fixo | Expande e recolhe | Sempre | Básico |

**Estados.**
- *Normal*: deslizante e interruptor ativos.
- *Rascunho*: AU-6 visível e botão "Aplicar" ativo.
- *Sessão de voz / reinício pendente / modo seguro / desconectado*: desativados; faixa de aviso de estado (seção 3).
- *Sem motor de voz*: AU-9 com rótulo "Resposta por voz indisponível", deslizante desativado, AU-11 "Resposta: Indisponível".
- *Erro*: linha de erro de 12 px abaixo de AU-7 com o texto do código.

**Regras.**
- Volume 0 é mudo: não cria tarefa de voz no Core.
- Mudança de volume não altera o mixer do sistema.
- O volume vale no áudio que o Gideon gera, antes da saída virtual.

---

### 7.3 Dispositivos

**Título**: Dispositivos · **Subtítulo**: "Microfone e alto-falante usados pelo Gideon. A lista vem do sistema; a troca vale na próxima sessão de voz." (texto real de `app/pages/CfgDispositivos.qml:37`; a lista vem do Core, A4 `src/devices.rs`, e o padrão é "PCM virtual" até o usuário escolher um dispositivo — DOCS-03, WP8)
**Ação primária**: nenhuma.
**Faixa de resumo**: "Entrada: PCM virtual · Saída: virtual · Câmera e tela: simuladas".

**Objetivo.** Mostrar o que o Gideon usa como entrada e saída, e deixar claro o que é virtual, simulado ou indisponível.

**Condição de aparecimento.** Sempre visível. O link para Percepção e ação só funciona com `perceptionAvailable`.

**Nível.** Básico. Itens avançados: seção 5.1 (Dispositivos).

**Layout em grade.**
- Cartão 1 "Entrada (microfone)": 6 colunas, (140, 236, 542, 260).
- Cartão 2 "Saída (alto-falante)": 6 colunas, (698, 236, 542, 260).
- Cartão 3 "Câmera e tela": 12 colunas, (140, 516, 1100, 150).
- "Como funciona": (140, 682, 1100, 56).
- Reflow abaixo de 900 px: três cartões empilhados.

**Wireframe**

```
+-C1 Entrada (microfone)-----------------------------+  +-C2 Saida (alto-falante)----------------------------+
|                                                    |  |                                                    |
|                                                    |  |                                                    |
| +-Dispositivo em uso: PCM virtual----------------+ |  | +-Dispositivo em uso: Saida virtual--------------+ |
|                                                    |  |                                                    |
| +-PCM virtual - pre-roll 1 s - CPU---------------+ |  | +-Sem reproducao fisica comprovada---------------+ |
|                                                    |  |                                                    |
| +-Microfone fisico (desativa-+                     |  | +-Alto-falante fisico (desat-+                     |
|                                                    |  |                                                    |
| +-Indisponivel: adaptador fisico-----------------+ |  | +-Indisponivel: adaptador de saida---------------+ |
|                                                    |  |                                                    |
+-+-Avancado: PCM mono 16 kHz----------------------+-+  +-+-Avancado: sink virtual-------------------------+-+

+-C3 Camera e tela-------------------------------------------------------------------------------------------+
|                                                                                                            |
| +-Camera: simulada [SINTETICO]---------------------------------------------------------------------------+ |
| +-Tela: simulada [SINTETICO]-----------------------------------------------------------------------------+ |
| +-Ver em Percepcao e acao----+                                                                             |
+------------------------------------------------------------------------------------------------------------+

+-Como funciona (recolhido)----------------------------------------------------------------------------------+
+------------------------------------------------------------------------------------------------------------+
```

**Elementos**

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| DI-1 | C1 título (160, 256) | Texto | "Entrada (microfone)" | Texto fixo | Nenhuma | Sempre | Básico |
| DI-2 | Dispositivo de entrada (160, 292, 502, 24) | Texto 14 px | "Dispositivo em uso: PCM virtual" | Texto fixo (`docs/BASE_UI_MAP.md`: entrada virtual) | Nenhuma | Sempre | Básico |
| DI-3 | Detalhe de entrada (160, 328, 502, 30) | Texto 12 px | "PCM virtual · pré-roll de 1 segundo · processamento na CPU. Microfone físico, cancelamento de eco e redução de ruído ainda indisponíveis." | Texto fixo (P1-T3, reescrito como detalhe) | Nenhuma | Sempre | Básico |
| DI-4 | Microfone físico (160, 372, 300, 32) | Lista suspensa desativada | Rótulo acessível "Microfone físico (indisponível)" | Nenhuma (NT-08, NT-43) | Sem ação | Sempre | Básico |
| DI-5 | Motivo do microfone (160, 410, 502, 24) | Texto 12 px | "Indisponível: adaptador de microfone físico não implementado; validação humana pendente." | Texto fixo | Nenhuma | Sempre | Básico |
| DI-6 | Avançado de entrada (160, 466, 502, 24) | Texto 12 px | "Formato da entrada: PCM mono 16 kHz" | Texto fixo (`docs/BASE_UI_MAP.md`) | Nenhuma | Sempre | **Avançado** |
| DI-7 | Código de captura (160, 494, 502, 24) | Texto 12 px | "Código do estado de captura: <stt_status>" | `core.sttStatus` | Nenhuma | Sempre | **Avançado** |
| DI-8 | C2 título (718, 256) | Texto | "Saída (alto-falante)" | Texto fixo | Nenhuma | Sempre | Básico |
| DI-9 | Dispositivo de saída (718, 292, 502, 24) | Texto 14 px | "Dispositivo em uso: Saída virtual" | Texto fixo (sink virtual) | Nenhuma | Sempre | Básico |
| DI-10 | Detalhe de saída (718, 328, 502, 30) | Texto 12 px | "Sem reprodução física comprovada." | Texto fixo (`docs/BASE_UI_MAP.md`) | Nenhuma | Sempre | Básico |
| DI-11 | Alto-falante físico (718, 372, 300, 32) | Lista suspensa desativada | Rótulo acessível "Alto-falante físico (indisponível)" | Nenhuma (NT-09, NT-44) | Sem ação | Sempre desativado | Básico |
| DI-12 | Motivo da saída (718, 410, 502, 24) | Texto 12 px | "Indisponível: adaptador de saída física não implementado." | Texto fixo | Nenhuma | Sempre | Básico |
| DI-13 | Avançado de saída (718, 466, 502, 24) | Texto 12 px | "Sink: virtual (sem ID de dispositivo)" | Texto fixo | Nenhuma | Sempre | **Avançado** |
| DI-14 | C3 título (160, 536) | Texto | "Câmera e tela" | Texto fixo | Nenhuma | Sempre | Básico |
| DI-15 | Câmera (160, 566, 1060, 24) | Texto 14 px + selo | "Câmera: simulada" + selo "SINTÉTICO". Motivo em 12 px: "Indisponível: sem câmera real." | Texto fixo; `core.perceptionAvailable` | Nenhuma | Sempre | Básico |
| DI-16 | Tela (160, 598, 1060, 24) | Texto 14 px + selo | "Tela: simulada" + selo "SINTÉTICO". Motivo em 12 px: "Indisponível: sem captura de tela real." | Texto fixo | Nenhuma | Sempre | Básico |
| DI-17 | Link para Percepção (160, 630, 300, 32) | Botão secundário | "Ver em Extensões › Percepção e ação" | `core.perceptionAvailable` | Clique → vai para Extensões › Percepção e ação. Sem plugin: desativado com "Indisponível: nenhum plugin de percepção em execução." | Ativo só com plugin em execução | Básico |
| DI-18 | "Como funciona" (140, 682, 1100, 56) | Bloco recolhível | Expandido: "Entrada e saída são virtuais nesta versão. Dispositivos físicos entram quando o adaptador for validado." | Texto fixo | Expande e recolhe | Sempre | Básico |

**Estados.**
- *Normal*: textos de estado sem ação.
- *Sem plugin de percepção*: DI-17 desativado e DI-15/16 mantêm o selo.
- *Modo seguro*: DI-2 e DI-9 mostram "Indisponível: modo seguro." no lugar do nome do dispositivo.

**Regras.** Nenhum controle desta aba troca de dispositivo hoje. Os controles desativados existem para mostrar o que falta, sem prometer nada.

---

### 7.4 Aparência

**Título**: Aparência · **Subtítulo**: "Tema e cor de destaque desta janela, com prévia imediata."
**Ação primária**: nenhuma.
**Faixa de resumo**: "Tema: Gideon · Destaque: Azul · Esfera: ligada · Não salvo ao reabrir" (dados: `themeIndex`, `accentColor`, `visualFeedback`).

**Objetivo.** Escolher tema e cor de destaque da janela e ligar ou desligar a esfera de atividade.

**Condição de aparecimento.** Sempre visível. O interruptor da esfera depende de `preferencesAvailable`.

**Nível.** Básico. Itens avançados: seção 5.1 (Aparência).

**Estado atual (fato verificado).** Tema e cor são estado da janela (`window.themeIndex`, `window.accentColor`, `app/Main.qml:34-35`). Não há slot, campo no snapshot ou gravação (`app/bridge.py` não guarda tema). Ao reabrir, volta a "Gideon" e "Azul" (AC-06). Só a esfera é salva, pelo Core (`feedback_preferences`).

**Layout em grade.**
- Cartão 1 "Tema": 6 colunas, (140, 236, 542, 300).
- Cartão 2 "Cor de destaque": 6 colunas, (698, 236, 542, 300).
- Cartão 3 "Indicador visual e prévia": 12 colunas, (140, 552, 1100, 240).
- "Como funciona": (140, 808, 1100, 56).
- Reflow abaixo de 900 px: cartões empilhados; amostras de cor quebram em duas linhas; a prévia fica acima do interruptor.

**Wireframe**

```
+-C1 Tema--------------------------------------------+  +-C2 Cor de destaque---------------------------------+
|                                                    |  |                                                    |
|                                                    |  |                                                    |
| +-Escuro--------++-Claro (indis-+ +-Sistema (ind-+ |  | | Azul    || Violeta | | Ciano   | | Rosa    |     |
| +---------------++--------------+ +--------------+ |  | |         ||         | |         | |         |     |
| +-Indisponivel: tema claro e do sistema----------+ |  | +---------++---------+ +---------+ +---------+     |
|                                                    |  |                                                    |
| +-Gideon--------++-Classico-----+ +-Minimalista--+ |  | +-Nao salvo ao reabrir---------------------------+ |
| +---------------++--------------+ +--------------+ |  | +-Avancado: #7693ff------------------------------+ |
|                                                    |  |                                                    |
| +-Nao salvo ao reabrir---------------------------+ |  |                                                    |
|                                                    |  |                                                    |
+----------------------------------------------------+  +----------------------------------------------------+

+-C3 Indicador e previa--------------------------------------------------------------------------------------+
|                                                                                                            |
| +--------------------------------------------------+    +-Mostrar esfera e indicador [sw]----------------+ |
| |                                                  |    +------------------------------------------------+ |
| | Previa ao vivo                                   |    +-Salvo pelo Core (NOVO)-------------------------+ |
| |                                                  |    +------------------------------------------------+ |
| +--------------------------------------------------+                                                       |
+------------------------------------------------------------------------------------------------------------+

+-Como funciona (recolhido)----------------------------------------------------------------------------------+
+------------------------------------------------------------------------------------------------------------+
```

**Elementos**

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| AP-1 | C1 título (160, 256) | Texto | "Tema" | Texto fixo | Nenhuma | Sempre | Básico |
| AP-2 | Segmentos de tema (160, 308, 502, 40) | Controle segmentado de 3 opções | "Escuro" (ativo) · "Claro" · "Sistema" | `window.themeIndex` (variante escura ativa) | "Escuro": ativo. "Claro" e "Sistema": desativados (AP-4) | Só "Escuro" é escolhível hoje | Básico |
| AP-3 | Tooltip de "Claro" e "Sistema" | Tooltip | "Indisponível: paleta clara não existe no app. 'Sistema' ainda não segue o sistema operacional." | Texto fixo | Nenhuma | Sempre | Básico |
| AP-4 | Motivo (160, 356, 502, 24) | Texto 12 px | "Indisponível: tema claro e tema do sistema não existem nesta versão." | Texto fixo | Nenhuma | Sempre | Básico |
| AP-5 | Rótulo da variante (160, 384, 502, 20) | Texto 14 px bold | "Variante escura" | Texto fixo | Nenhuma | Sempre | Básico |
| AP-6 | Variantes (160, 406, 502, 40) | Controle segmentado de 3 opções | "Gideon" · "Clássico" · "Minimalista" | `window.themeIndex` (0, 1, 2) | Escolhe a variante; aplica na hora (prévia). Não grava. | Padrão: "Gideon" | Básico |
| AP-7 | Nota de persistência (160, 458, 502, 24) | Texto 12 px | Obsoleto (WP8): a nota "Não ficam salvos ao reabrir" não existe no código; tema e cor ficam salvos pelo app por perfil. | Não implementar a nota antiga | Nenhuma | Sempre | Básico |
| AP-8 | C2 título (718, 256) | Texto | "Cor de destaque" | Texto fixo | Nenhuma | Sempre | Básico |
| AP-9 | Amostra "Azul" (718, 300, 110, 72) | Amostra selecionável | "Azul" + "Selecionada" quando ativa | `window.accentColor` = `#7693ff` | Escolhe; aplica na hora. Não grava. | Selecionada: borda de 2 px | Básico |
| AP-10 | Amostra "Violeta" (834, 300, 110, 72) | Amostra selecionável | "Violeta" | `#b386ff` | Idem | Idem | Básico |
| AP-11 | Amostra "Ciano" (950, 300, 110, 72) | Amostra selecionável | "Ciano" | `#66dcf4` | Idem | Idem | Básico |
| AP-12 | Amostra "Rosa" (1066, 300, 110, 72) | Amostra selecionável | "Rosa" | `#f28bd7` | Idem | Idem | Básico |
| AP-13 | Nota da cor (718, 388, 502, 24) | Texto 12 px | "Usada em destaques, botões e foco. Não fica salva ao reabrir." | Texto fixo | Nenhuma | Sempre | Básico |
| AP-14 | Valor da cor (718, 420, 502, 24) | Texto 12 px | "Valor da cor: #7693ff" | `window.accentColor` | Nenhuma | Sempre | **Avançado** |
| AP-15 | C3 título (160, 572) | Texto | "Indicador visual e prévia" | Texto fixo | Nenhuma | Sempre | Básico |
| AP-16 | Prévia (160, 604, 520, 160) | Miniatura viva | Rótulo "Prévia ao vivo". Mostra fundo do tema, faixa de destaque e esfera só com esfera ligada. | `themeIndex`, `accentColor`, `visualFeedback` | Nenhuma (reflete a escolha) | Esfera ausente quando desligada | Básico |
| AP-17 | Interruptor da esfera (716, 604, 504, 40) | Interruptor com rótulo | "Mostrar esfera e indicador de atividade" | `core.visualFeedback` | Muda → `core.saveFeedback(novo, volume_salvo)`. Toast "Preferências salvas pelo Core". Erro: volta ao valor anterior. | Desativado sem `preferencesAvailable` | Básico |
| AP-18 | Nota da esfera (716, 652, 504, 36) | Texto 12 px | "O indicador é salvo pelo Core. Estado textual, legendas e Cancelar continuam disponíveis." | Texto fixo (P3-T4 e P3-T5) | Nenhuma | Sempre | Básico |
| AP-19 | Valor salvo da esfera (716, 700, 504, 24) | Texto 12 px | "Valor salvo do indicador visual: ligado" (ou desligado) | `core.visualFeedback` | Nenhuma | Sempre | **Avançado** |
| AP-20 | Motivo sem Core (716, 700, 504, 24) | Texto 12 px | "Indisponível: Core desconectado; alteração não salva." | `core.connected` | Nenhuma | Só desconectado (substitui AP-19) | Básico |
| AP-21 | "Como funciona" (140, 808, 1100, 56) | Bloco recolhível | Expandido: "Tema e cor são da janela. A esfera é a única escolha desta aba que o Core guarda hoje." | Texto fixo | Expande e recolhe | Sempre | Básico |

**Estados.**
- *Normal*: escolhas aplicadas na hora; persistência conforme seção 10.
- *Sessão de voz / modo seguro / reinício pendente*: somente AP-17 fica desativado; tema e cor continuam ativos (não tocam áudio).
- *Desconectado*: AP-17 desativado e AP-20 visível.

**Regras.** A escolha de tema ou cor não envia nada ao Core hoje. A escolha da esfera envia o campo visual com revisão.

---

### 7.5 Privacidade

**Título**: Privacidade · **Subtítulo**: "O que o Gideon guarda, onde fica e quem pode receber dados."
**Ação primária**: nenhuma.
**Faixa de resumo**: "Áudio e legendas: só em memória · Nuvem: não concedida · Retenção: sem controle" (o trecho "não concedida" vem de `core.llmConfig.cloud_consent`).

**Objetivo.** Dizer com clareza o que fica em memória, o que não é guardado, o estado do consentimento de nuvem e como apagar dados de plugin.

**Condição de aparecimento.** Sempre visível. Link para Modelos LLM depende de `modelsAvailable`. Botão de apagar depende de `modelsAvailable`.

**Nível.** Básico. Itens avançados: seção 5.1 (Privacidade).

**Layout em grade.**
- Cartão 1 "O que fica guardado": 6 colunas, (140, 236, 542, 300).
- Cartão 2 "Envio à nuvem": 6 colunas, (698, 236, 542, 300).
- Cartão 3 "Retenção e dados de plugins": 12 colunas, (140, 552, 1100, 200).
- "Como funciona": (140, 768, 1100, 56).
- Reflow abaixo de 900 px: cartões empilhados.

**Wireframe**

```
+-C1 O que fica guardado-----------------------------+  +-C2 Envio a nuvem-----------------------------------+
|                                                    |  |                                                    |
|                                                    |  |                                                    |
| +-EM MEMORIA - audio capturado-------------------+ |  | +-Consentimento: nao concedido-------------------+ |
| +------------------------------------------------+ |  | +------------------------------------------------+ |
|                                                    |  | +------------------------------------------------+ |
| +-EM MEMORIA - legendas--------------------------+ |  | | Texto: envio a nuvem exige consentimento       | |
| +------------------------------------------------+ |  | +------------------------------------------------+ |
| +------------------------------------------------+ |  |                                                    |
| | NAO GUARDADO - historico                       | |  | +-Abrir Modelos LLM > Proved-+                     |
| +------------------------------------------------+ |  | +----------------------------+                     |
| +------------------------------------------------+ |  | +-Indisponivel: plugin de LLM--------------------+ |
| | PRIVADO - configuracoes                        | |  |                                                    |
| +------------------------------------------------+ |  |                                                    |
+----------------------------------------------------+  +----------------------------------------------------+

+-C3 Retencao e plugins--------------------------------------------------------------------------------------+
|                                                                                                            |
| +-Retencao: Indisponivel: controle nao existe------------------------------------------------------------+ |
| +-Dados de plugins: texto--------------------------------------------------------------------------------+ |
| +-Apagar dados de plug-+                                                                                   |
+------------------------------------------------------------------------------------------------------------+

+-Como funciona (recolhido)----------------------------------------------------------------------------------+
+------------------------------------------------------------------------------------------------------------+
```

**Elementos**

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| PR-1 | C1 título (160, 256) | Texto | "O que fica guardado" | Texto fixo | Nenhuma | Sempre | Básico |
| PR-2 | Linha 1 (160, 290, 502, 48) | Selo + texto | Selo "EM MEMÓRIA". Texto: "Áudio capturado: só em memória durante a captura. Nenhum arquivo de voz é gravado." | Texto fixo (`docs/BASE_UI_MAP.md`: sem WAV de voz persistido) | Nenhuma | Sempre | Básico |
| PR-3 | Linha 2 (160, 346, 502, 48) | Selo + texto | Selo "EM MEMÓRIA". Texto: "Legendas: só em memória, sem histórico." | Texto fixo (D1-T1, P0-T4) | Nenhuma | Sempre | Básico |
| PR-4 | Linha 3 (160, 402, 502, 48) | Selo + texto | Selo "NÃO GUARDADO". Texto: "Histórico de conversas: não há histórico salvo." | Texto fixo (P0-T4) | Nenhuma | Sempre | Básico |
| PR-5 | Linha 4 (160, 458, 502, 48) | Selo + texto | Selo "PRIVADO". Texto: "Configurações: guardadas pelo Core em área privada. O caminho não é exibido." | Texto fixo (`docs/BASE_UI_MAP.md`; NF-19 para caminhos) | Nenhuma | Sempre | Básico |
| PR-6 | C2 título (718, 256) | Texto | "Envio à nuvem" | Texto fixo | Nenhuma | Sempre | Básico |
| PR-7 | Estado do consentimento (718, 292, 502, 40) | Texto 14 px | "Consentimento salvo: não concedido" (ou "concedido"). Sem motor LLM configurado: "Indisponível: nenhum motor LLM configurado." | `core.llmConfig.cloud_consent === true` (valor do QML já existente) | Nenhuma | Sempre | Básico |
| PR-8 | Explicação (718, 344, 502, 48) | Texto 14 px | "Sem consentimento, conversas não são enviadas à nuvem. Você marca o consentimento no provedor do motor LLM." | Texto fixo | Nenhuma | Sempre | Básico |
| PR-9 | Link "Abrir Modelos LLM › Provedor e chaves" (718, 410, 300, 40) | Botão secundário | "Abrir Modelos LLM › Provedor e chaves" | `core.modelsAvailable` | Clique → Extensões › Modelos LLM › Provedor e chaves | Ativo só com `modelsAvailable` | Básico |
| PR-10 | Motivo do link (718, 458, 502, 24) | Texto 12 px | "Indisponível: Modelos LLM só aparece com o plugin de LLM em execução." | `core.modelsAvailable` | Nenhuma | Só quando PR-9 desativado | Básico |
| PR-11 | C3 título (160, 572) | Texto | "Retenção e dados de plugins" | Texto fixo | Nenhuma | Sempre | Básico |
| PR-12 | Retenção (160, 604, 1060, 32) | Texto 14 px | "Retenção: Indisponível: não há controle de retenção. Dados em memória deixam de existir quando o Core encerra." | Texto fixo (NT-17) | Nenhuma | Sempre | Básico |
| PR-13 | Texto dos dados de plugin (160, 648, 1060, 24) | Texto 12 px | "Dados de plugins: configurações guardadas pelo plugin de LLM. O Core e as chaves não são afetados." | Texto fixo (D8) | Nenhuma | Sempre | Básico |
| PR-14 | Botão "Apagar dados de plugins" (160, 680, 240, 40) | Botão de perigo | "Apagar dados de plugins" | `core.modelsAvailable` | Abre diálogo 8.4. Confirmado → `core.clearPluginSettings()`. Resultado em PR-15. | Desativado sem `modelsAvailable`; motivo em PR-16 | Básico |
| PR-15 | Resultado (320, 688, 800, 24) | Texto 12 px | Texto retornado pelo Core, sem tradução adicional | Resposta de `clearPluginSettings` | Nenhuma | Só após ação | Básico |
| PR-16 | Motivo do botão (160, 728, 1060, 24) | Texto 12 px | "Indisponível: nenhum plugin de LLM com dados guardados." | `core.modelsAvailable` | Nenhuma | Só quando PR-14 desativado | Básico |
| PR-17 | Nota avançada (160, 760, 1060, 20) | Texto 12 px | "Inclui modelos personalizados (lista do plugin de LLM)." | Texto fixo | Nenhuma | Sempre | **Avançado** |
| PR-18 | "Como funciona" (140, 768, 1100, 56) | Bloco recolhível | Expandido: "Nada do que você fala é guardado em disco pela interface. A nuvem só recebe conversas com consentimento." | Texto fixo | Expande e recolhe | Sempre | Básico |

**Estados.**
- *Normal*: leitura do consentimento; botões conforme plugin.
- *Sem motor LLM*: PR-7 com "Indisponível: nenhum motor LLM configurado." e PR-9 desativado.
- *Sessão de voz*: botão de apagar desativado com motivo "Indisponível agora: sessão de voz em andamento."
- *Erro ao apagar*: texto do código em PR-15 em tom Erro.

**Regras.** Esta aba não altera consentimento. Consentimento só muda em Modelos LLM › Provedor e chaves (`docs/UI_IA.md`, Regras de unicidade).

---

### 7.6 Geral

**Título**: Geral · **Subtítulo**: "Idioma, inicialização, opções avançadas e restauração da configuração."
**Ação primária**: nenhuma.
**Faixa de resumo**: "Idioma: português · Opções avançadas: <ligadas|desligadas> · Configuração: <pronta|modo seguro|reinício pendente>".

**Objetivo.** Mostrar idioma e recursos que não existem, ligar o modo avançado e restaurar a configuração.

**Condição de aparecimento.** Sempre visível. O botão de restaurar muda conforme `configurationStatus`.

**Nível.** Básico. O próprio interruptor é básico; o que ele revela está na seção 5.1.

**Layout em grade.**
- Cartão 1 "Idioma e inicialização": 6 colunas, (140, 236, 542, 300).
- Cartão 2 "Opções avançadas": 6 colunas, (698, 236, 542, 300).
- Cartão 3 "Restaurar padrões": 12 colunas, (140, 552, 1100, 240).
- "Como funciona": (140, 808, 1100, 56).
- Reflow abaixo de 900 px: cartões empilhados; botões ocupam a largura toda.

**Wireframe**

```
+-C1 Idioma e inicializacao--------------------------+  +-C2 Opcoes avancadas--------------------------------+
|                                                    |  |                                                    |
|                                                    |  |                                                    |
| +-Idioma da interface: Portugues (fixo)----------+ |  | +-Mostrar opcoes avancadas [sw]------------------+ |
| +------------------------------------------------+ |  | +------------------------------------------------+ |
| | Outros idiomas: Indisponivel                   | |  | +------------------------------------------------+ |
| +------------------------------------------------+ |  | | Guardado pelo Core (NOVO). Padrao: desligado   | |
|                                                    |  | |                                                | |
| +-Iniciar no login (desativado)------------------+ |  | +------------------------------------------------+ |
| +------------------------------------------------+ |  |                                                    |
|                                                    |  | +-Opcoes avancadas: desligadas-------------------+ |
| +-Desempenho: Indisponivel-----------------------+ |  |                                                    |
| +------------------------------------------------+ |  |                                                    |
+----------------------------------------------------+  +----------------------------------------------------+

+-C3 Restaurar-----------------------------------------------------------------------------------------------+
|                                                                                                            |
| +------------------------------------------------------------------------------------+                     |
| | Texto: restaurar padroes com confirmacao                                           |                     |
| +------------------------------------------------------------------------------------+  +-Restaurar padr-+ |
|                                                                                                            |
| +-Restaurar anterior (av.)-------------------------------------------------------------------------------+ |
| +-Revisao da configuracao: N (av.)-----------------------------------------------------------------------+ |
+------------------------------------------------------------------------------------------------------------+

+-Como funciona (recolhido)----------------------------------------------------------------------------------+
+------------------------------------------------------------------------------------------------------------+
```

**Elementos**

| # | Região / posição | Tipo | Texto exato | Fonte de dados | Ação → resultado | Estados | Nível |
|---|---|---|---|---|---|---|---|
| GE-1 | C1 título (160, 256) | Texto | "Idioma e inicialização" | Texto fixo | Nenhuma | Sempre | Básico |
| GE-2 | Idioma atual (160, 290, 502, 24) | Texto 14 px | "Idioma da interface: Português (fixo)" | Texto fixo (a UI é só em português; `docs/BASE_UI_MAP.md`) | Nenhuma | Sempre | Básico |
| GE-3 | Outros idiomas (160, 326, 502, 48) | Lista suspensa desativada + motivo | Rótulo acessível "Outros idiomas (indisponível)". Motivo 12 px: "Indisponível: só o português existe na interface. Reconhecimento e voz usam inglês, fixo no pacote." | Texto fixo (NT-13) | Sem ação | Sempre desativado | Básico |
| GE-4 | Iniciar no login (160, 390, 502, 24) | Rótulo + interruptor desativado | "Iniciar no login" | Nenhuma (NT-16) | Sem ação | Sempre desativado | Básico |
| GE-5 | Motivo de login (160, 418, 502, 24) | Texto 12 px | "Indisponível: inicialização automática no login não existe neste pacote." | Texto fixo (B4) | Nenhuma | Sempre | Básico |
| GE-6 | Desempenho (160, 470, 502, 24) | Texto 14 px + motivo | "Desempenho: Indisponível: não há controle de desempenho; o processamento usa CPU fixa." | Texto fixo (NT-15) | Nenhuma | Sempre | Básico |
| GE-7 | C2 título (718, 256) | Texto | "Opções avançadas" | Texto fixo | Nenhuma | Sempre | Básico |
| GE-8 | Interruptor (718, 292, 502, 40) | Interruptor com rótulo | "Mostrar opções avançadas" | `show_advanced` (NOVO, seção 5) | Muda → revela ou oculta os itens da seção 5.1 em todas as sub-abas; grava com revisão | Padrão desligado. Sem NOVO: vale só nesta execução | Básico |
| GE-9 | Descrição (718, 344, 502, 72) | Texto 12 px | "Mostra ajustes técnicos em todas as sub-abas de Configurações. Não altera nenhum valor, só a visualização." | Texto fixo | Nenhuma | Sempre | Básico |
| GE-10 | Estado (718, 430, 502, 24) | Texto 12 px | "Opções avançadas: ligadas" ou "Opções avançadas: desligadas" | Estado do interruptor | Nenhuma | Sempre | Básico |
| GE-11 | C3 título (160, 572) | Texto | "Restaurar padrões" | Texto fixo | Nenhuma | Sempre | Básico |
| GE-12 | Texto de restauração (160, 604, 860, 40) | Texto 14 px | "Volta prazo da sessão, resposta por voz, indicador, volume e frase de despertar aos padrões. Pede confirmação. Se a frase mudar, reinicie o Core." | Texto fixo | Nenhuma | Só fora do modo seguro | Básico |
| GE-13 | Botão "Restaurar padrões…" (1040, 604, 180, 40) | Botão secundário | "Restaurar padrões…" | **NOVO (precisa de mudança na ponte/Core)**: operação `restore_defaults` (hoje só existe `recover_configuration`, que vale apenas em modo seguro) | Abre diálogo 8.2 (versão de estado normal). Confirmado → Core. Toast "Preferências salvas pelo Core". | Sem a mudança: desativado com "Indisponível: restaurar padrões fora do modo seguro ainda não existe." | Básico |
| GE-14 | Faixa de modo seguro (160, 604, 1060, 40) | Faixa de aviso (Aviso) | "Modo seguro: configuração inválida preservada; áudio e comandos bloqueados" (ou o texto de limite) | `core.configurationMessage` | Nenhuma | Só em modo seguro | Básico |
| GE-15 | Botão de recuperação (160, 652, 300, 40) | Botão de perigo | "Preservar arquivo e restaurar padrões" | `core.recoveryAvailable` (D1-C1) | Abre diálogo 8.3. Confirmado → `core.recoverConfiguration()`. Toast "Configuração recuperada; reinício necessário". | Só em modo seguro. Sem `recoveryAvailable`: "Indisponível: arquivo excede o limite de recuperação automática." | Básico |
| GE-16 | Botão "Restaurar anterior" (160, 700, 180, 40) | Botão secundário | "Restaurar anterior" | `core.rollbackAvailable` (D1-C10) | Chama `core.rollbackPreferences()` (revisão atual). Toast "Preferências salvas pelo Core". Se a frase mudar: faixa de reinício. | Ativo só com `rollbackAvailable`. Sem anterior: "Indisponível: não há configuração anterior." | **Avançado** |
| GE-17 | Ajuda do rollback (356, 708, 864, 24) | Texto 12 px | "Desfaz a última alteração de preferências (uma etapa). Se a frase mudar, reinicie o Core." | Texto fixo | Nenhuma | Sempre | **Avançado** |
| GE-18 | Revisão (160, 748, 1060, 24) | Texto 12 px | "Revisão da configuração: <preferencesRevision>" | `core.preferencesRevision` | Nenhuma | Sempre | **Avançado** |
| GE-19 | "Como funciona" (140, 808, 1100, 56) | Bloco recolhível | Expandido: "Em modo seguro, o arquivo inválido é preservado antes de ser substituído pelos padrões." | Texto fixo | Expande e recolhe | Sempre | Básico |

**Estados.**
- *Normal*: GE-12 e GE-13; GE-14 a GE-15 ocultos.
- *Modo seguro*: GE-14 e GE-15 aparecem; GE-13 oculto (o diálogo 8.3 cobre a restauração).
- *Modo seguro sem recuperação possível*: GE-14 com o texto de limite; GE-15 desativado com motivo.
- *Reinício pendente*: GE-13 e GE-15 desativados ("Indisponível: reinício do Core pendente.").
- *Sessão de voz*: GE-13, GE-15 e GE-16 desativados; motivo "Indisponível agora: sessão de voz em andamento.".

**Regras.** Restaurar nunca apaga o arquivo anterior: em modo seguro ele é preservado como `config.invalid.json` antes da substituição (`src/storage.rs`, `recover_configuration`).

---

## 8. Diálogos e fluxos

### 8.1 Trocar frase de despertar (confirmação; NOVO só QML, sem ponte/Core)

- **Abre por**: clique em um tile de frase qualificada (VW-3).
- **Largura**: 420 px, centralizado. Título 17 px.
- **Campos (somente leitura)**:
  - "Frase atual": `<texto da frase salva>` (ex.: "Hey Gideon").
  - "Nova frase": `<texto escolhido> · <qualificação>` (ex.: "Okay Gideon · requer prova de conceito"). Só chega aqui uma frase `dev_qualified`.
- **Texto do corpo**: "A troca só vale depois que o Core for reiniciado. Até lá, a frase atual continua ativa."
- **Botões**: [Cancelar] (foco inicial) · [Trocar frase].
- **Ação**: "Trocar frase" → `core.selectWake(id)` → toast "Preferências salvas pelo Core"; faixa "Configuração salva; reinicie o Core para ativar os recursos"; estado "Reinício necessário".
- **Esc** equivale a Cancelar.

### 8.2 Restaurar padrões fora do modo seguro (IMPLEMENTADO, WP8: `preferences_restore_defaults`)

- **Abre por**: GE-13. **Título**: "Restaurar padrões do Gideon?"
- **Campos por linha** (formato "Atual → padrão"; linhas iguais ficam em cinza):
  1. "Frase de despertar": `<atual>` → "padrão do pacote".
  2. "Resposta por voz": `<ligada|desligada>` → "ligada".
  3. "Indicador visual": `<ligado|desligado>` → "ligado".
  4. "Volume da resposta": `<N>%` → "100%".
  5. "Prazo máximo da sessão": `<N> s` → "30 s".
- **Aviso** (tom Aviso): "Se a frase de despertar mudar, reinicie o Core depois. Até lá, a frase atual continua ativa."
- **Botões**: [Cancelar] (foco inicial) · [Restaurar padrões].
- **Ação**: "Restaurar padrões" → operação `preferences_restore_defaults` com `revision` (Core: `src/protocol.rs` `PreferencesRestoreDefaults`, `src/core.rs`; ponte: `restoreCoreDefaults`, `app/bridge.py`). Recusada com `busy` durante sessão. Sucesso: toast "Preferências salvas pelo Core" e, se a frase mudou, faixa de reinício.
- **Erro**: texto do código (seção 12).

### 8.3 Preservar arquivo e restaurar padrões (modo seguro)

Operação existente: `core.recoverConfiguration()` → Core `recover_configuration`. Condição: modo seguro e `recoveryAvailable`.

- **Abre por**: GE-15. **Título**: "Preservar arquivo e restaurar padrões".
- **Campos (somente leitura)**, uma linha cada:
  1. "Arquivo atual": "config.json (inválido)".
  2. "Cópia de segurança": "config.invalid.json, na pasta privada do Gideon. Não é apagada."
  3. "Frase de despertar após restaurar": "padrão do pacote".
  4. "Resposta por voz após restaurar": "ligada".
  5. "Indicador visual após restaurar": "ligado".
  6. "Volume da resposta após restaurar": "100%".
  7. "Prazo máximo da sessão após restaurar": "30 s".
- **Aviso** (tom Aviso): "Depois de restaurar, reinicie o Core. Áudio e comandos ficam bloqueados até o reinício."
- **Botões**: [Cancelar] (foco inicial) · [Preservar e restaurar].
- **Resultado sucesso**: toast "Configuração recuperada; reinício necessário" (texto existente) e faixa "Configuração salva; reinicie o Core para ativar os recursos".
- **Erros**: "Não foi possível preservar o arquivo; a configuração original não foi alterada." (NOVO na ponte, seção 12). Em conflito de cópia: "Já existe uma cópia de segurança diferente; nada foi alterado." (NOVO na ponte).

### 8.4 Apagar dados de plugin (existente, D8)

- **Abre por**: PR-14. **Título**: "Apagar dados do plugin de LLM".
- **Texto exato** (D8): "Apagar as configurações guardadas pelo plugin LLM, inclusive modelos personalizados? O plugin e a configuração do Core (provedor, modelo e chaves) não são alterados."
- **Botões**: [Cancelar] (foco inicial) · [Apagar dados].
- **Ação**: `core.clearPluginSettings()`.

### 8.5 Reiniciar Core (IMPLEMENTADO, WP8: `coreRestart`, `app/bridge.py`)

- **Abre por**: VW-7 (somente com reinício pendente).
- **Título**: "Reiniciar o Core agora?"
- **Texto**: "Sessões em andamento serão encerradas. A nova frase de despertar passa a valer depois do reinício."
- **Botões**: [Cancelar] (foco inicial) · [Reiniciar Core].
- **Ação**: reinício controlado do Core (`core_restart`, `app/bridge.py`), com estado "Reiniciando o Core…" e depois "Core reiniciado e conectado de novo"; se o Core não voltar em 30 s, a faixa mostra o aviso de tempo esgotado. Recusado com `busy` enquanto há sessão ativa (`coreRestartAvailable`).
- **Estado anterior (obsoleto)**: a frase "Indisponível: o app não reinicia o Core ainda." não existe mais no código; VW-7 fica ativo quando `coreRestartAvailable`.

---

## 9. Frases de despertar

### 9.1 Tabela

| Frase | Id técnico (avançado) | Qualificação (código) | Rótulo exibido | Pode ser escolhida | Texto da linha no tile | O que está comprovado e o que não está |
|---|---|---|---|---|---|---|
| Hey Gideon | `hey_gideon` | `dev_qualified` | em desenvolvimento | Sim, com confirmação 8.1 e reinício | "Qualificada em desenvolvimento; validação física pendente" | Comprovado: reconhecimento no corpus de desenvolvimento, com verificação automática (`docs/A1.md`: AUTO_VERIFIED). Não comprovado: microfone físico, ambiente real e outras vozes. Não é certificação acústica. |
| Okay Gideon | `okay_gideon` | `poc_required` | requer prova de conceito | Não (bloqueada) | "Requer prova de conceito: frase sem qualidade aprovada" | O detector suporta a frase, mas a qualidade é POC_REQUIRED (`docs/A1.md`). O reconhecimento de fala pode escrever "K Gideon". Não é escolhível. |

Fonte dos rótulos: `WAKE_QUALIFICATION_LABELS` em `app/bridge.py` e textos de `app/Main.qml` (`wakeQualification`). Id técnico: `scripts/build_base_pack.py`.

### 9.2 Texto honesto (VW-5, exato)

"Comprovado: a frase 'Hey Gideon' foi reconhecida em corpus de desenvolvimento, com verificação automática. Não comprovado: uso com microfone físico, em ambientes reais e com outras vozes. Não há reconhecimento comprovado em português (pt-BR). Não é certificação acústica. 'Okay Gideon' não tem qualidade aprovada e fica bloqueada."

---

## 10. Persistência de Aparência

**Comportamento atual (verificado no WP8, `docs/WP8.md`).** Tema (`theme.mode`, `theme.preset`), cor de destaque (`theme.accent`) e o modo claro/sistema são gravados pelo app, por perfil, em arquivo JSON (`app/uisettings.py`, `app/theme/Theme.qml`); eles persistem ao reabrir. Não são gravados pelo Core: o alvo abaixo (`config.json`) continua aberto. A esfera continua salva pelo Core (`feedback_preferences`).

**Alvo (NOVO, precisa de mudança na ponte/Core).**
- Campo `theme` em `config.json` com lista fechada: `gideon`, `classico`, `minimalista`. Padrão: `gideon`.
- Campo `accent` com lista fechada: `#7693ff`, `#b386ff`, `#66dcf4`, `#f28bd7`. Padrão: `#7693ff`.
- Validação em `src/storage.rs` (`Config::validate`) e entrada em `previous_preferences`, para o rollback também valer para aparência.
- Operação de gravação com revisão (igual à esfera). **Decisão**: permitida durante sessão de voz, porque não altera áudio nem frase. Sem essa decisão, a regra seria a mesma das preferências de áudio.
- Ao abrir: a janela lê `theme` e `accent` do snapshot e aplica antes de mostrar a janela.

**Claro e Sistema (NOVO, só QML, sem ponte/Core).** Paleta clara completa e seguir `prefers-color-scheme` do sistema. Sem isso, AP-2 mantém "Claro" e "Sistema" desativados.

---

## 11. Acessibilidade

- **Ordem de foco** (Tab): sub-abas → título da aba → cartão 1 (de cima para baixo, da esquerda para a direita) → cartão 2 → cartão 3 → "Como funciona". Ctrl+Tab troca de sub-aba (regra da casca).
- **Foco visível**: anel de 2 px do acento em todo controle, inclusive tiles e amostras de cor.
- **Nomes acessíveis**: todo controle tem `Accessible.name`. Exemplos: "Volume da resposta por voz, por cento", "Resposta por voz (saída virtual)", "Mostrar esfera e indicador de atividade", "Prazo da sessão em milissegundos", "Cor de destaque Azul, selecionada".
- **Estado de interruptor**: anunciado como "ligado" ou "desligado", nunca só por cor.
- **Controles desativados** anunciam o motivo pela descrição acessível ("Indisponível: ...").
- **Cor nunca sozinha**: selos e estados têm texto (ex.: "Selecionada", "Bloqueada", "requer prova de conceito").
- **Contraste**: texto principal sobre o fundo do tema com contraste mínimo de 4,5:1; selos Aviso e Erro também com texto escrito.
- **Tamanho de alvo**: botões e controles com altura mínima de 40 px. Interruptores 44 × 24 px com área de toque de 40 px.
- **Diálogos de confirmação**: foco inicial em [Cancelar]; Esc cancela; Enter não confirma sem o foco explícito.
- **Mensagens de resultado** (toast e faixas de aviso): anunciadas como status (leitor de tela), sem roubar o foco.
- **Modo seguro e reinício**: anunciados ao entrar na aba.
- **Opções avançadas**: quando ocultas, não ficam na ordem de foco nem no leitor de tela.
- **HiDPI**: todo texto em unidades relativas; a grade muda por largura, não por escala.

---

## 12. Textos de erro e de código

| Código (Core) | Texto exibido | Estado |
|---|---|---|
| `busy` | "Core ocupado; tente novamente em instantes" | Existente (`CODE_MESSAGES`) |
| `wake_not_qualified` | "Frase de wake sem qualificação aprovada" | Existente |
| `stale_preferences` | "Configuração mudou no Core; atualize a tela e tente de novo." | IMPLEMENTADO com outro texto (WP8): `CODE_MESSAGES` em `app/bridge.py:1067` ("Configurações mudaram no Core; atualize e tente de novo"). Este texto é o da tabela, a ser alinhado. |
| `invalid_preferences` | "Valor fora do limite permitido; nada foi salvo." | IMPLEMENTADO com outro texto (WP8): `app/bridge.py:1068`. O código não aparece cru. |
| `preferences_storage_error` | "Não foi possível gravar a configuração; nada foi alterado." | IMPLEMENTADO com outro texto (WP8): `app/bridge.py:1072`. |
| `preferences_unavailable` | "Configuração indisponível no Core agora." | IMPLEMENTADO com outro texto (WP8): `app/bridge.py:1073`. |
| Falha de cópia de segurança | "Não foi possível preservar o arquivo; a configuração original não foi alterada." | **NOVO (precisa de mudança na ponte/Core)**: entrada em `CODE_MESSAGES`. |
| Cópia de segurança diferente | "Já existe uma cópia de segurança diferente; nada foi alterado." | **NOVO (precisa de mudança na ponte/Core)**: entrada em `CODE_MESSAGES`. |
| Código desconhecido | "Core recusou a ação: <código>" | Existente (fallback de `code_message`) |

Achado: os códigos de preferências `stale_preferences`, `invalid_preferences`, `preferences_storage_error` e `preferences_unavailable` não estão em `CODE_MESSAGES` (`app/bridge.py`). O usuário vê o código cru.

---

## 13. Ligação com os achados e as necessidades do Notion

| ID | Situação | Onde fica nesta especificação |
|---|---|---|
| NT-06 | Frase certificada existe; "Okay Gideon" bloqueada | VW-3, VW-4, seção 9 |
| NT-07 | Sensibilidade não existe | VW-16 e VW-17 (desativada com motivo) |
| NT-08 | Entrada física não existe | DI-4, DI-5 |
| NT-09 | Saída física não existe | DI-11, DI-12 |
| NT-10 | Feedback audível existe | AU-9 |
| NT-11 | Feedback visual existe | AP-17 (única escolha; ver nota de unicidade em 7.2) |
| NT-12 | Voz fixa, escolha não existe | AU-14 a AU-16 |
| NT-13 | Idioma fixo | GE-2, GE-3 |
| NT-14 | Volume existe | AU-3 a AU-7 |
| NT-15 | Desempenho não existe | GE-6 |
| NT-16 | Iniciar no login não existe | GE-4, GE-5 |
| NT-17 | Privacidade e retenção | seção 7.5, PR-12 |
| AC-01 | Sessão de voz bloqueia configuração e a tela avisava mal | Faixa de sessão (seção 3) com texto explícito |
| AC-05 | Ação destrutiva sem confirmação | Confirmação em 8.1 a 8.5 |
| AC-06 | Tema e cor não persistem | Obsoleto no app (WP8: persistem por perfil em `uisettings.py`); aberto só para gravação no Core (seção 10) |
| AC-09 | Motor LLM sem plugin | PR-9 e PR-10 (link condicional) |
| AC-15 / NT-36 | Sem divulgação progressiva | Seção 5 (interruptor) |
| AC-18 | Textos fixos de hardware | AU-14, DI-2, DI-9 (ficam fixos até existir dado real) |
| D1 | Diálogo de preferências | Removido; seção 4 |

---

## 14. Lista consolidada de itens NOVO

| # | Item | Tipo | Onde |
|---|---|---|---|
| 1 | Propriedade `savedWakeId` (`preferences.wake_phrase`) | Substituída, não implementada com esse nome: a lista é `wakePhraseRows`/`selectWake` (WP8). Pendente: confirmação de 8.1 | `app/bridge.py` |
| 2 | Reinício controlado do Core (botão "Reiniciar Core") | IMPLEMENTADO (WP8): `coreRestart`, `app/pages/DiagRecuperacao.qml` | Core, ponte e launcher |
| 3 | Restaurar padrões fora do modo seguro (`preferences_restore_defaults`) | IMPLEMENTADO (WP8): `src/protocol.rs`, `src/core.rs`, `app/bridge.py` | `src/core.rs`, `src/storage.rs`, `app/bridge.py` |
| 4 | Campo `show_advanced` em `config.json` | NOVO (precisa de mudança na ponte/Core) | `src/storage.rs`, `app/bridge.py` |
| 5 | Campos `theme` e `accent` em `config.json` e operação de gravação com revisão | NOVO (precisa de mudança na ponte/Core) | `src/storage.rs`, `src/protocol.rs`, `app/bridge.py` |
| 6 | Textos de código de preferências em `CODE_MESSAGES` (seção 12) | NOVO (precisa de mudança na ponte/Core) | `app/bridge.py` |
| 7 | Tema claro e tema do sistema | IMPLEMENTADO (WP8): `app/theme/Theme.qml` (`theme.mode` system/dark/light) | `app/Main.qml` |
| 8 | Diálogos de confirmação de troca de frase e de restauração fora do modo seguro | NOVO (só QML, sem ponte/Core) | `app/Main.qml` |
| 9 | Valor salvo × rascunho nos controles de volume e prazo | NOVO (só QML, sem ponte/Core) | `app/Main.qml` |
| 10 | Estado "Enviando ao Core" nos controles de preferência | Já existe em `PENDING`; a desativação durante gravação é NOVO (só QML, sem ponte/Core) | `app/Main.qml` |

Nada desta lista está em uso. Os itens 2 a 6 mudam a ponte ou o Core e devem ser planejados antes de implementar.

---

## 15. Decisões a confirmar pelo dono

1. **Indicador visual**: `docs/UI_IA.md` 4.2 lista o interruptor em Áudio, mas a tabela de unicidade manda usar Aparência. Esta especificação segue a unicidade (seção 7.2).
2. **Prazo da sessão**: a IA diz "leitura hoje" em 4.1. Esta especificação mantém a leitura no nível básico e põe a edição (já existente, D1-C8) no avançado.
3. **Apagar dados de plugin**: a IA lista em Privacidade sem nível. O inventário classifica D8 como Avançado. Esta especificação deixa o botão no nível básico (como a IA), com confirmação. Confirmar.
4. **Tema**: a IA cita "Escuro · Claro · Sistema". O app tem três variantes escuras ("Gideon", "Clássico", "Minimalista"). Esta especificação mostra os dois conjuntos: Escuro/Claro/Sistema no nível superior e as três variantes escuras abaixo.
5. **Passo do prazo**: o passo de 1000 ms a partir de 50 ms produz valores como 1050 ms. Confirmar se o passo deve ser 1000 com início em 1000, ou manter o comportamento de D1-C8.
6. **Modo seguro**: o nome `config.invalid.json` e o texto "Não é apagada" vêm do Core (`recover_configuration`). Confirmar a redação para o usuário.

---

## 16. Fora de escopo

- Memória, Almas, Hábitos e Automações (sem backend; `docs/UI_INVENTORY.md`, NT-54 a NT-57).
- Onboarding (NT-37): decisão do dono.
- Seleção de dispositivo físico, escolha de voz, idioma de interface, desempenho, login automático e retenção: aparecem somente como linhas desativadas com motivo, sem controle real.
- Diagnóstico, Extensões e Permissões: fora desta aba. Esta aba só linka para elas.
