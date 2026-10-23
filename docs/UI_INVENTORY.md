# Inventário da UI atual do Gideon (Qt)

Escopo: tudo que a UI Qt (`app/Main.qml`) deixa o usuário ver ou fazer hoje, com a ponte `app/bridge.py` como única fonte de dados e ações. Documento de referência para desenhar uma nova arquitetura de informação. Somente leitura: nenhum código foi alterado.

Fontes lidas: `app/Main.qml` (1574 linhas, inteiro), `app/bridge.py` (2130 linhas: todos os `@Slot`, `@Property`, `OPS`, `PENDING`, `SECTION_SIGNALS`), `app/main.py` (flags), `src/protocol.rs` (enum `Operation`), `docs/BASE_UI_MAP.md`, `docs/B3.md`, `docs/B4.md`, `docs/C1.md`, `docs/C2.md`, `docs/C3.md`, `docs/C4.md`, `docs/S4.md`, `docs/S5.md`, `docs/UI_NOTION_REQS.md`, `README.md`.

## 0. Como ler

**Convenção de linhas.** `Main.qml:N` é a linha no QML. `bridge.py:N` é a linha da declaração no Python. Slots e propriedades aparecem pelo nome; o índice completo com linhas está no Apêndice A.

**Ids das linhas.** `SB-` barra lateral, `HD-` cabeçalho, `Px-C/I/T` página x (C controle, I informação dinâmica, T texto fixo), `Dx-C/I/T` diálogo x, `NF-` funcionalidade do Core sem tela, `NT-` cobertura do Notion, `AC-` achado.

**Classes (campo "Classe").**
- **DIÁRIO**: uso frequente de quem usa o Gideon no dia a dia (conversar, ver o estado, cancelar, decidir uma aprovação).
- **OCASIONAL**: configuração e setup, feitos uma vez ou de tempos em tempos (frase de wake, provedor, conectar conta, instalar plugin).
- **AVANÇADO**: poder de usuário ou gestão fina (manifests de skill, revisões, remover, reverter, operações de conexão, fallback de modelo).
- **DEV/TESTE**: só para desenvolvimento ou validação (texto de teste, invocação de capability de teste, dados sintéticos, "SERVIDOR FALSO", leitura de teste).

**Contagem.** Controle = elemento interativo declarado (botão, campo, caixa, combo, spin, slider, aba, item de navegação). Um template de delegate (ex.: um botão por frase, um botão por skill) conta como uma linha; a multiplicidade está na coluna de visibilidade. Informação dinâmica = texto cujo conteúdo vem de propriedade do Core ou da ponte (`core.*`, `window.*`, `modelData`). Texto fixo = literal no QML. Os totais estão na seção 9.

**Interpretação de "Plugins" e "Hub dialog".** São o mesmo diálogo. O objeto `hubDialog` (`Main.qml:203`, título "Plugins — Gideon Hub") abre pelo item da barra lateral "Plugins" (`Main.qml:601`, objectName `hubButton`) e pelo botão "Explorar catálogo" da página Gideon Hub (`Main.qml:886`). O diálogo "Revisar permissões" abre a partir dele.

**Estado da sessão de voz.** Quase tudo que escreve no Core fica desabilitado enquanto há sessão de voz ativa (`core.sessionId` não vazio), porque `preferencesAvailable` exige `not sessionId` (`bridge.py:1683-1684`). Esse efeito propaga para `hubLifecycleAvailable`, `pluginsAvailable` e `chatAvailable` (`bridge.py:1728-1729`, `1745-1746`, `1272-1273`). Ver AC-01.

---

## 1. Shell: barra lateral, cabeçalho e rodapé

### 1.1 Barra lateral (`Main.qml:544-622`)

Seções: PRINCIPAL (`Main.qml:576`), VOZ E ÁUDIO (`:583`), EXTENSÕES (`:591`), SISTEMA (`:603`). Modo trilho (icones só) quando a janela tem menos de 980 px (`Main.qml:40`).

| ID | Item (rótulo) | objectName · linha | Destino | Visível / habilitado quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| SB-01 | Início | nav0 · `Main.qml:580` | página 0 | sempre | DIÁRIO | — |
| SB-02 | Conversa | nav7 · `:581` | página 7 | visível se `core.chatAvailable` (plugin de chat rodando e preferências disponíveis, AC-01) | DIÁRIO | — |
| SB-03 | Voz e Wake | nav1 · `:588` | página 1 | sempre | OCASIONAL | Início (card "Frase de despertar") |
| SB-04 | Áudio | nav2 · `:589` | página 2 | sempre | OCASIONAL | — |
| SB-05 | Gideon Hub | nav6 · `:596` | página 6 | sempre | OCASIONAL | SB-08 (mesmo catálogo) |
| SB-06 | Skills | nav10 · `:597` | página 10 | visível se `core.skillsAvailable` | AVANÇADO | — |
| SB-07 | Conexões | nav11 · `:598` | página 11 | visível se `core.connectionsAvailable` | AVANÇADO | — |
| SB-08 | Plugins | hubButton · `:601` | abre `hubDialog` | habilitado se `core.connected` | OCASIONAL | SB-05, P6-C1 |
| SB-09 | Modelos LLM | nav8 · `:599` | página 8 | visível se `core.modelsAvailable` (plugin llm_engine rodando com `llm_engine.models`) | OCASIONAL | — |
| SB-10 | Percepção e ação | nav9 · `:600` | página 9 | visível se `core.perceptionAvailable` (algum plugin C4 rodando) | DEV/TESTE | — |
| SB-11 | Permissões | nav4 · `:608` | página 4 | sempre | OCASIONAL | — |
| SB-12 | Diagnóstico | nav5 · `:609` | página 5 | sempre | OCASIONAL | Início (card "Estado do sistema") |
| SB-13 | Aparência | nav3 · `:610` | página 3 | sempre | OCASIONAL | — |
| SB-14 | Preferências | settingsButton · `:611` | abre `preferences` | habilitado se `core.connected` | OCASIONAL | P1-C2, P2-C2 |

Rodapé da barra lateral (só fora do modo trilho):

| ID | Conteúdo | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| SB-R1 | Diagnóstico: `configurationMessage` ou "Áudio virtual · " + `diagnostic` | diagnostics · `Main.qml:618` | `core.configurationMessage`, `core.diagnostic` | largura >= 980 | OCASIONAL | P5-I1 |
| SB-R2 | "Base local / inglês · perfil virtual" | — · `:619` | texto fixo | largura >= 980 | OCASIONAL | — |

### 1.2 Cabeçalho (`Main.qml:623-652`)

| ID | Elemento | objectName · linha | Conteúdo / ação | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| HD-01 | Título da página | pageTitle · `:631` | `window.navigation[window.page]` (lista em `Main.qml:39`) | sempre | DIÁRIO | — |
| HD-02 | Subtítulo da página | pageSubtitle · `:632` | `window.pageSubtitles[page]` (`Main.qml:43`), texto fixo | sempre | DIÁRIO | — |
| HD-03 | Orbe de atividade | activityIndicator · `:641` | imagem do orbe | `core.visualFeedback` | DIÁRIO | P3-C8, D1-C5 |
| HD-04 | Ponto de estado (cor) | — · `:642-645` | cor: amarelo se desconectado ou modo seguro/reinício; verde se idle; azul nos demais | sempre | DIÁRIO | — |
| HD-05 | Rótulo do estado (aura) | aura · `:647` | `stateLabels[core.state]`, senão "Erro" (`Main.qml:110`) | sempre | DIÁRIO | P0-I4, P5 (STT/TTS) |
| HD-06 | Cancelar sessão | cancelButton · `:651` | `core.cancel()` (slot `cancel`, `bridge.py:1238`) | `sessionCancellable`: conectado e estado capturing, transcribing, executing ou speaking | DIÁRIO | P7-C3 e outros "Cancelar" (AC-08) |

---

## 2. Páginas

Visibilidade geral das páginas: `window.page` (0 a 11). Páginas 8, 9, 10 e 11 voltam ao Início se o recurso sumir (`Main.qml:159`). A página 7 não tem esse retorno.

### Página 0: Início

- **Propósito:** visão geral do Core, cartões-resumo e último texto de voz ou de resultado.
- **Linhas:** nav `Main.qml:580`; cabeçalho de página e subtítulo `:631-632`; herói `heroGrid` `:654-699`; cartões `summaryRow` `:701-724`; transcrição, resultado e entrada de teste `:1560-1572`.
- **Visibilidade:** a página é a 0. Herói só com altura >= 640 (`:656`). Card "Estado do sistema" só com largura >= 760 (`:677`). Transcrição, resultado e entrada de teste aparecem também em qualquer outra página quando há sessão (`:1561`, `:1565`, `:1567`).

| ID | Controle (rótulo) | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| P0-C1 | "Abrir" (card Frase de despertar) | GlowButton · `:720` | `window.page = 1` | navega | sempre na página 0 | DIÁRIO | P1 (SB-03) |
| P0-C2 | "Abrir" (card Entrada de áudio) | GlowButton · `:720` | `window.page = 2` | navega | sempre na página 0 | DIÁRIO | SB-04 |
| P0-C3 | "Abrir" (card Modo) | GlowButton · `:720` | `window.page = 6` | navega (vai para Gideon Hub, não para Conversa) | sempre na página 0 | DIÁRIO | SB-05 |
| P0-C4 | Campo "Comando de texto" (placeholder "Comando de texto no perfil de teste") | textInput · `:1569` | `core.submitText(text)` (`bridge.py:1246`) | envia texto ao Core como entrada de voz de teste | habilitado se `core.textAvailable` (exige `--virtual-input` e wake de replay, `src/core.rs:809-812`) | DEV/TESTE | — |
| P0-C5 | "Enviar" | sendButton · `:1570` | `core.submitText` | igual a P0-C4 | habilitado se `textAvailable` e campo não vazio | DEV/TESTE | P1 de Conversa (mesmo padrão) |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P0-I1 | Saudação do herói "Olá," e "Gideon" | — · `:667-668` | texto fixo | página 0 e altura >= 640 | DIÁRIO | — |
| P0-I2 | Linha de estado do herói: "Seu Gideon, em um só lugar." ou "Vamos reconectar ao Gideon." | — · `:670` | `core.connected` | página 0 e altura >= 640 | DIÁRIO | — |
| P0-T1 | "Acompanhe a conversa, ajuste sua voz e conheça as capacidades disponíveis." | — · `:671` | texto fixo | página 0 e altura >= 640 | DIÁRIO | — |
| P0-T2 | "Base · áudio virtual · validação física pendente" | — · `:672` | texto fixo (não reflete o Core) | página 0 e altura >= 640 | DIÁRIO | Diálogo Preferências, rodapé |
| P0-I3 | Card "Estado do sistema": "Conectado ao Core" ou "Core offline" | — · `:682` | `core.connected` | largura >= 760 | DIÁRIO | P5-I3 |
| P0-I4 | Wake: estado | — · `:690` | `window.statusText(core.wakeStatus)` ← `bridge.py:1703` | largura >= 760 | DIÁRIO | P1-I3, P5-I4 |
| P0-I5 | STT: estado | — · `:690` | `statusText(core.sttStatus)` ← `bridge.py:1705` | largura >= 760 | DIÁRIO | P5-I5 |
| P0-I6 | TTS: estado | — · `:690` | `statusText(core.speechStatus)` ← `bridge.py:1707` | largura >= 760 | DIÁRIO | P2-I1, P5-I6 |
| P0-T3 | Rótulos "Wake", "STT", "TTS", "Estado do sistema", "Privacidade" | — · `:684, :681, :694` | texto fixo | largura >= 760 | DIÁRIO | — |
| P0-T4 | "Sem histórico de conversas. Áudio e legendas em memória." | — · `:695` | texto fixo | largura >= 760 | DIÁRIO | D1-T1 (privacidade) |
| P0-I7 | Cartão Frase de despertar: frase ativa | — · `:707, :718` | `window.wakeText()` ← `core.snapshotPack` (`bridge.py:1701`) | sempre na página 0 | DIÁRIO | P1-I1, D1-I2 |
| P0-I8 | Cartão Entrada de áudio: "PCM virtual" ou "Indisponível" | — · `:707` | `window.packAvailable` ← `core.wakeChoices` | sempre na página 0 | DIÁRIO | P2-T1 |
| P0-T5 | Cartão Modo: valor "Base · sem LLM" | — · `:707` | literal fixo (não lê o plugin LLM, AC-02) | sempre na página 0 | DIÁRIO | Conversa (P7-I2) |
| P0-T6 | Rótulos dos cartões: "Frase de despertar", "Entrada de áudio", "Modo" | — · `:707, :717` | texto fixo | sempre na página 0 | DIÁRIO | — |
| P0-I9 | Transcrição (legenda) da sessão | subtitle · `Main.qml:1563` | `core.subtitle` ← `transcript.raw` (`bridge.py:1801`); nome de acessibilidade "Transcrição parcial" ou "final" conforme `core.partial` (`bridge.py:1803`) | página 0 ou sessão ativa | DIÁRIO | P7-I4 (parcial do chat, outro canal) |
| P0-T7 | Placeholder "Sua conversa aparecerá aqui." | subtitle · `:1563` | texto fixo | transcrição vazia | DIÁRIO | — |
| P0-I10 | Resultado do comando (recibo) | result · `:1565` | `core.result` ← `display_receipt` (`bridge.py:1805`) ou `command.code`; cor verde se `core.resultVerified` (`bridge.py:1809`) | página 0 ou sessão, e texto não vazio | DIÁRIO | — |
| P0-I11 | Resultado do texto de teste | textResult · `:1572` | `core.textResult` (`bridge.py:1699`) | página 0 ou sessão, e texto não vazio | DEV/TESTE | P0-C4 |

### Página 1: Voz e Wake

- **Propósito:** escolher a frase de wake certificada do pacote e ver o estado do wake e da captura.
- **Linhas:** nav `Main.qml:588`; `wakeCardPanel` `:733-758`; `captureCardPanel` `:759-771`.
- **Visibilidade:** página 1 (sempre no menu). A lista de frases vem de `core.wakeChoices`. Sem pack: texto "Nenhum pack de wake configurado." (`:757`).

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| P1-C1 | Botão de frase "<texto> · <qualificação>" (um por frase) | wakeCard_<id> · `:746-754` | `core.selectWake(id)` (`bridge.py:1648`) → Core `select_wake(revision, phrase_id)` | troca a frase do pack; exige reinício do Core | habilitado se `core.preferencesAvailable` e qualificação `dev_qualified`; marcado se for a frase ativa | OCASIONAL | D1-C2, D1-C3 |
| P1-C2 | "Abrir ajustes da Base" | GlowButton · `:769` | `preferences.open()` | abre Preferências | habilitado se `core.connected` | OCASIONAL | D1, P2-C2 |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P1-I1 | Frase ativa | wakeActive · `:738` | `window.wakeText()` ← `core.snapshotPack.active_phrase` | página 1 | OCASIONAL | P0-I7, D1-I2 |
| P1-I2 | Qualificação da frase ativa | wakeActiveQualification · `:739` | `window.activeWake().qualification` | página 1 e há frase ativa no pack | OCASIONAL | D1-I3 |
| P1-I3 | "Estado do wake: <estado>" | wakeStatusLine · `:740` | `statusText(core.wakeStatus)` ← `bridge.py:1703` | página 1 | DIÁRIO | P0-I4, P5-I4 |
| P1-I4 | Frases disponíveis (texto e qualificação de cada frase) | wakeCard_<id> · `:749` | `core.wakeChoices` ← `bridge.py:1638` | página 1 | OCASIONAL | D1-C2 |
| P1-I5 | "Captura: <estado do STT> · prazo da sessão: <N> ms" | captureStatusLine · `:765` | `statusText(core.sttStatus)`, `core.sessionTimeout` (`bridge.py:1691`) | página 1 | OCASIONAL | P5-I5, D1-C8 |
| P1-T1 | "Escolha uma frase qualificada do pack. A alteração requer reinício do Core." | — · `:736` | texto fixo | página 1 | OCASIONAL | — |
| P1-T2 | Rótulos "Frase ativa", "Frases disponíveis", "Entrada", "Estado", "Captura", "Frase de despertar" | — · `:737, :741, :762, :764, :760` | texto fixo | página 1 | OCASIONAL | — |
| P1-T3 | "PCM virtual · pré-roll de 1 segundo · processamento na CPU. Microfone físico, AEC e redução de ruído ainda indisponíveis." | — · `:763` | texto fixo | página 1 | OCASIONAL | — |
| P1-T4 | "Nenhum pack de wake configurado." | — · `:757` | texto fixo, condicional a `wakeChoices` vazio | sem pack | OCASIONAL | — |
| P1-I6 | Aviso de qualificação da frase (dev_qualified ou poc_required) | wakeQualification (em Preferências, `:183`) | `wakeChoice` atual | (ver D1) | OCASIONAL | P1-I2 |

### Página 2: Áudio

- **Propósito:** resposta por voz e ganho da saída virtual.
- **Linhas:** nav `Main.qml:589`; `speechCardPanel` `:772-779`; `gainCardPanel` `:780-795`.
- **Visibilidade:** página 2. Controles de ganho habilitados só com `preferencesAvailable` e `voiceAvailable` (`bridge.py:1687`: `speech_status` diferente de `unavailable`).

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| P2-C1 | Slider "Ganho da resposta por voz" (0 a 100, passo 5) | gainSlider · `:788` | só estado local da tela até "Aplicar" | nenhum (local) | habilitado se `preferencesAvailable` e `voiceAvailable` | OCASIONAL | D1-C6 (spin do mesmo valor) |
| P2-C2 | "Abrir ajustes da Base" | GlowButton · `:791` | `preferences.open()` | abre Preferências | habilitado se `core.connected` | OCASIONAL | P1-C2, SB-14 |
| P2-C3 | "Aplicar" | applyGainButton · `:793` | `core.saveFeedback(core.visualFeedback, round(gain))` (`bridge.py:1655`) → Core `feedback_preferences` | grava ganho (e mantém visual) | habilitado se `preferencesAvailable` e `voiceAvailable` | OCASIONAL | D1-C7 |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P2-I1 | "Resposta: <estado do TTS>" | speechStatusLine · `:778` | `statusText(core.speechStatus)` ← `bridge.py:1707` | página 2 | OCASIONAL | P0-I6, P5-I6 |
| P2-I2 | "Ganho atual: N%" | gainCurrent · `:786` | `core.outputVolume` ← `bridge.py:1653` | página 2 | OCASIONAL | D1-I4 |
| P2-T1 | "Pocket TTS · Alba · inglês · saída virtual. Outras vozes e dispositivos físicos ainda indisponíveis." | — · `:776` | texto fixo | página 2 | OCASIONAL | P0-I8 (rótulo "PCM virtual") |
| P2-T2 | Rótulos "Voz", "Estado", "Ganho da resposta por voz", "Volume da resposta", "Resposta por voz" | — · `:775, :777, :785, :782, :774` | texto fixo | página 2 | OCASIONAL | — |

### Página 3: Aparência

- **Propósito:** tema e cor da janela e o interruptor do HUD.
- **Linhas:** nav `Main.qml:610`; `appearanceGrid` `:797-839` (`themeCardPanel` `:801-822`, `accentCardPanel` `:823-831`, `hudCardPanel` `:832-838`).
- **Visibilidade:** página 3. Duas colunas se a janela tem mais de 1000 px (`:800`).
- **Persistência:** tema e cor são estado da janela (`window.themeIndex`, `window.accentColor`, `Main.qml:34-35`). Não há slot, nem campo no snapshot, e `bridge.py` não guarda tema (grep: zero ocorrências). Reiniciar a janela volta ao padrão. Só o interruptor do HUD é salvo pelo Core.

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| P3-C1 | Tema "Gideon" (índice 0) | theme0 · `:806-809` | `window.themeIndex = 0` | troca tema da janela (não salvo) | sempre na página 3 | OCASIONAL | — |
| P3-C2 | Tema "Clássico" (índice 1) | theme1 · `:806-809` | `window.themeIndex = 1` | idem | sempre na página 3 | OCASIONAL | — |
| P3-C3 | Tema "Minimalista" (índice 2) | theme2 · `:806-809` | `window.themeIndex = 2` | idem | sempre na página 3 | OCASIONAL | — |
| P3-C4 | Cor de destaque "Azul" | accentAzul · `:828` | `window.accentColor = "#7693ff"` | cor da janela (não salva) | sempre na página 3 | OCASIONAL | — |
| P3-C5 | Cor "Violeta" | accentVioleta · `:828` | `window.accentColor = "#b386ff"` | idem | sempre | OCASIONAL | — |
| P3-C6 | Cor "Ciano" | accentCiano · `:828` | `window.accentColor = "#66dcf4"` | idem | sempre | OCASIONAL | — |
| P3-C7 | Cor "Rosa" | accentRosa · `:828` | `window.accentColor = "#f28bd7"` | idem | sempre | OCASIONAL | — |
| P3-C8 | Checkbox "Mostrar esfera e indicador de atividade" | visualPagePreference · `:835` | `core.saveFeedback(checked, core.outputVolume)` → Core `feedback_preferences` | liga e desliga orbe no cabeçalho e no herói | habilitado se `preferencesAvailable` | OCASIONAL | D1-C5, HD-03 |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P3-T1 | Títulos "Tema", "Cor de destaque", "HUD visual" e nomes dos temas | — · `:802, :824, :833, :816` | texto fixo | página 3 | OCASIONAL | — |
| P3-T2 | "Tema e cor se aplicam a esta janela." | — · `:821` | texto fixo | página 3 | OCASIONAL | — |
| P3-T3 | "Mostrar esfera e indicador de atividade" (rótulo do checkbox) | visualPagePreference · `:835` | texto fixo | página 3 | OCASIONAL | D1-C5 |
| P3-T4 | "Estado textual, legendas e cancelamento permanecem disponíveis." | — · `:836` | texto fixo | página 3 | OCASIONAL | — |
| P3-T5 | "O indicador é salvo pelo Core." | — · `:837` | texto fixo | página 3 | OCASIONAL | — |

### Página 4: Permissões

- **Propósito (pelo Notion e pelo nome):** listar capacidades e aprovações.
- **Linhas:** nav `Main.qml:608`; único card `:840-843`.
- **Conteúdo real:** um card "Comandos da Base" com um parágrafo. Nenhuma lista de permissões, de aprovações ou de grants. Não há controle nesta página. Ver AC-03.

| ID | Controle | Observação | Classe |
|---|---|---|---|
| P4-C (nenhum) | — | a página não tem controle | — |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P4-T1 | Título "Comandos da Base" | — · `:841` | texto fixo | página 4 | OCASIONAL | — |
| P4-T2 | "O Hub declara permissões e registra aprovação por manifesto. Plugins instalados e aprovados podem ser ativados em sandbox sem rede. Comandos da Base não dependem de plugins." | — · `:842` | texto fixo | página 4 | OCASIONAL | D2-I5, D4-T1 |

### Página 5: Diagnóstico

- **Propósito:** estado dos motores e da conexão, em texto.
- **Linhas:** nav `Main.qml:609`; `diagnosticsPanel` `:844-867`.
- **Visibilidade:** página 5. Nenhum controle.

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P5-I1 | Diagnóstico de motores: "<estado do wake> · <estado do STT> · <estado do TTS>" ou mensagem de configuração | — · `:850` | `core.diagnostic` ← `bridge.py:1811` (rótulos `DIAG_LABELS`, `bridge.py:15`) | página 5 | DIÁRIO | SB-R1 (rodapé) |
| P5-I2 | Descrição do pack ou "Pack de voz não configurado" | — · `:851` | `core.packDescription` ← `bridge.py:1640` | página 5 | OCASIONAL | D1-I2 |
| P5-I3 | "Conectado ao Core" ou "Core offline" | — · `:855` | `core.connected` | página 5 | DIÁRIO | P0-I3 |
| P5-I4 | Wake: estado | — · `:862` | `statusText(core.wakeStatus)` | página 5 | DIÁRIO | P0-I4, P1-I3 |
| P5-I5 | STT: estado | — · `:862` | `statusText(core.sttStatus)` | página 5 | DIÁRIO | P0-I5, P1-I5 |
| P5-I6 | TTS: estado | — · `:862` | `statusText(core.speechStatus)` | página 5 | DIÁRIO | P0-I6, P2-I1 |
| P5-T1 | Títulos "Motores e conexão" e "Estado do sistema"; rótulos "Wake", "STT", "TTS" | — · `:849, :854, :857` | texto fixo | página 5 | DIÁRIO | — |

### Página 6: Gideon Hub

- **Propósito:** catálogo local de plugins, com o botão para o diálogo de instalação e aprovação.
- **Linhas:** nav `Main.qml:596`; `hubPanel` `:868-903`; banner `:872-881`; card "Catálogo local" `:882-902`.
- **Visibilidade:** página 6. Lista de entradas ou estado vazio ("Nenhum plugin no catálogo ainda", `:898-901`).

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| P6-C1 | "Explorar catálogo" | hubCatalogButton · `:886` | `hubDialog.open()` | abre o diálogo Plugins (D2) | habilitado se `core.connected` | OCASIONAL | SB-08, D2 |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P6-I1 | Banner: descrição do Hub | — · `:879` | `core.hubDescription` ← `bridge.py:1788` | página 6 | OCASIONAL | D2-I1 |
| P6-I2 | Entrada do catálogo: "<id> <versão> · <estado> · <permissões aprovadas ou não>" (uma linha por plugin) | hubEntry_<id> · `:894` | `core.hubEntries` ← `bridge.py:1786` (status, reason, permissions_approved) | página 6 | OCASIONAL | D2-I4 |
| P6-I3 | Estado vazio: "Nenhum plugin no catálogo ainda. Conecte o Core para carregar o catálogo local." | EmptyState · `:900` | texto fixo, condicional a `hubEntries` vazio | catálogo vazio | OCASIONAL | — |
| P6-T1 | "Instalar copia o pacote verificado para o Core; nada é executado. O catálogo não concede acesso ao computador." | — · `:888` | texto fixo | página 6 | OCASIONAL | D2-T1 |
| P6-T2 | Título "Catálogo local", "Explorar catálogo" (rótulo do botão) | — · `:885` | texto fixo | página 6 | OCASIONAL | — |

### Página 7: Conversa

- **Propósito:** conversa por texto com o motor LLM opcional, decisões de ferramenta e agente.
- **Linhas:** nav `Main.qml:581`; aviso de indisponibilidade `chatOffColumn` `:1235-1242`; `chatPage` `:1402-1477` (painel `chatPanel`) e lateral `chatSide` `:1478-1558` (`toolPanel` `:1489-1516`, `agentPanel` `:1518-1556`).
- **Visibilidade:** página 7. A conversa aparece só com `core.chatAvailable` (plugin de chat com `*.chat` rodando, e preferências disponíveis: AC-01). Sem isso, aparece o aviso de `chatOffColumn` (`:1237`). Propostas aparecem só com propostas (`:1491`). Painel do agente aparece com o chat disponível (`:1520`).

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| P7-C1 | Campo "Mensagem para o motor LLM" (máx. 4096; Enter envia) | chatInput · `:1462-1471` | local (rascunho em `window.drafts`); Enter chama `sendChatDraft` | texto a enviar | habilitado se `chatAvailable` e estado não for waiting/streaming | DIÁRIO | — |
| P7-C2 | "Enviar" | chatSend · `:1472` | `core.sendChat(text)` (`bridge.py:1294`) → `capability_invoke` `*.chat`, prazo 10 s | envia turno ao plugin LLM | habilitado se `chatAvailable` e `chatTextProblem` vazio | DIÁRIO | — |
| P7-C3 | "Cancelar" (resposta do LLM) | chatCancel · `:1473` | `core.cancelChat()` (`bridge.py:1329`) → `capability_cancel` | cancela a resposta | habilitado se estado waiting/streaming | DIÁRIO | HD-06 (mesmo rótulo, outro efeito, AC-08) |
| P7-C4 | "Negar" (proposta pendente) | deny_<id> · `:1509` | `core.decideTool(id, "deny")` (`bridge.py:1340`) → Core `tool_decide` | recusa a ferramenta | visível se proposta `pending` | DIÁRIO | P10-C19 (passo de skill, mesmo padrão) |
| P7-C5 | "Autorizar" (proposta pendente) | authorize_<id> · `:1510` | `core.decideTool(id, "authorize")` | autoriza a ferramenta | visível se `pending` | DIÁRIO | P10-C20 |
| P7-C6 | Campo "Objetivo para o agente" (máx. 1024) | agentGoal · `:1525-1533` | local; `window.drafts["#agent"]` | texto do objetivo | habilitado se não há run ativo | AVANÇADO | — |
| P7-C7 | "Abortar" (agente) | agentAbort · `:1538` | `core.agentAbort()` (`bridge.py:1362`) | aborta o run | habilitado se `agentActive` | AVANÇADO | HD-06 (outro efeito) |
| P7-C8 | "Iniciar" (agente) | agentStart · `:1539` | `core.agentStart(goal)` (`bridge.py:1353`) | inicia run do agente | habilitado se `chatAvailable`, sem run ativo e objetivo válido | AVANÇADO | — |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P7-I1 | "Estado: <estado da conversa>" | chatState · `:1418` | `core.chatStateLabel` ← `bridge.py:1286` (`CHAT_STATE_LABELS`) | página 7 com chat | DIÁRIO | P7-I4 (mesmo texto) |
| P7-I2 | Aviso "Consentimento de nuvem desativado: envios são recusados até você marcá-lo em Motor LLM." | chatConsentHint · `:1420` | `core.llmConfig.cloud_consent` ← `bridge.py:1387` | consentimento não concedido | DIÁRIO | D3-I3, P8-I20 |
| P7-I3 | Balão de mensagem: "Você" ou "Gideon" + sufixo "cancelada" ou "erro" + texto | Rectangle de balão · `:1433-1442` | `core.chatMessages` ← `bridge.py:1288` (até 64) | há mensagens | DIÁRIO | — |
| P7-I4 | Resposta em andamento: estado + texto parcial ou "Aguardando resposta…" | chatStreaming · `:1444-1454` | `core.chatStateLabel`, `core.chatPartial` ← `bridge.py:1290` | estado waiting ou streaming | DIÁRIO | P7-I1 |
| P7-I5 | Aviso da conversa | chatResult · `:1457` | `core.chatResult` ← `bridge.py:1292` | texto não vazio | DIÁRIO | — |
| P7-I6 | Problema do texto digitado | chatInputProblem · `:1475` | `core.chatTextProblem(texto)` (`bridge.py:1275`) | texto inválido | DIÁRIO | — |
| P7-I7 | Título de proposta "Ferramenta <nome> · <estado>" | toolTitle_<id> · `:1500` | `core.toolProposals` ← `bridge.py:1336`; `toolStateText` | há propostas | DIÁRIO | — |
| P7-I8 | Proposta de conexão: "Conexão: <provedor> · conta <nome> · operação <op> (<rótulo>) · risco <r>" | connProposal_<id> · `:1502` | `connProposalText(p)` sobre `core.connectionsItems` | proposta com kind connection | AVANÇADO | P11 (conta) |
| P7-I9 | "Argumentos: <JSON>" | — · `:1503` | `modelData.args` | há proposta | DIÁRIO | — |
| P7-I10 | "Motivo: <texto do código>" | — · `:1504` | `core.codeMessage(reason)` | proposta com motivo | DIÁRIO | — |
| P7-I11 | "Resultado: <texto>" | — · `:1505` | `modelData.result` | proposta executada | DIÁRIO | — |
| P7-I12 | Aviso das propostas | toolResult · `:1515` | `core.toolResult` ← `bridge.py:1338` | texto não vazio | DIÁRIO | — |
| P7-I13 | Banner do agente: estado em palavras (+ código de erro) | agentBanner · `:1522` | `core.agentStateLabel` ← `bridge.py:1373` | há run | AVANÇADO | — |
| P7-I14 | "Tokens: <usados> de <máximo>" | agentBudget · `:1523` | `core.agentBudget` ← `bridge.py:1383` | há run | AVANÇADO | — |
| P7-I15 | Passo do agente: "Passo n · ferramenta <nome> · risco <r> · <estado> (· código)" | agentStep_<n>_<kind> · `:1549` | `core.agentSteps` ← `bridge.py:1379` | há passos | AVANÇADO | — |
| P7-I16 | Resposta final do agente | agentAnswer · `:1554` | `core.agentAnswer` ← `bridge.py:1381` | run concluído | AVANÇADO | — |
| P7-I17 | Aviso do agente | agentResult · `:1555` | `core.agentResult` ← `bridge.py:1385` | texto não vazio | AVANÇADO | — |
| P7-I18 | Erro de meta do agente | agentGoalProblem · `:1534` | `core.agentGoalProblem(texto)` (`bridge.py:1367`) | texto inválido | AVANÇADO | — |
| P7-T1 | "Conversa", "Mensagem", "Propostas de ferramenta", "Agente", "Objetivo" (títulos e rótulos) | — · `:1417, :1459, :1490, :1519, :1524` | texto fixo | página 7 | DIÁRIO | — |
| P7-T2 | "Nenhuma mensagem ainda. O motor LLM é opcional: voz, wake e comandos da Base funcionam sem ele." | chatEmpty · `:1430` | texto fixo, condicional a mensagens vazias e estado idle | sem mensagens | DIÁRIO | — |
| P7-T3 | "Motor LLM não está ativo. O plugin llm_engine é opcional: instale e ative pelo Gideon Hub. Voz, wake e comandos da Base funcionam sem ele." | chatUnavailable · `:1240` | texto fixo | página 7 sem chat disponível | DIÁRIO | AC-01 (aparece também durante sessão de voz com plugin rodando) |

### Página 8: Modelos LLM

- **Propósito:** escolher, testar e configurar o modelo do motor LLM, a partir do catálogo do plugin.
- **Linhas:** nav `Main.qml:599`; `modelsPanel` `:1127-1234`: "Modelo atual" `:1131-1138`, "Catálogo" `:1139-1199`, "Adicionar modelo personalizado" `:1200-1216`, "Fallback (opcional)" `:1217-1228`, "Hardware e plugin" `:1229-1233`.
- **Visibilidade:** página 8 e `core.modelsAvailable` (plugin llm_engine rodando com `llm_engine.models`). Ao abrir a página, a lista é recarregada (`Main.qml:33`). Sem o plugin, a página some do menu e o app volta ao Início (`:159`).

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| P8-C1 | "Atualizar lista" | modelsRefresh · `:1137` | `core.listModels(aba atual)` (`bridge.py:1539`) → capability `list` | recarrega a primeira página da aba | habilitado se `modelsAvailable` e não `modelsBusy` | OCASIONAL | — |
| P8-C2 | Abas "Recomendados" e "Personalizados" | modelsTabs · `:1141-1152` (TabButtons `:1146`, `:1149`) | ao trocar aba: `core.listModels(aba)` | troca a lista | sempre | OCASIONAL | — |
| P8-C3 | Filtro "Mostrar:" (Todos, Local, Nuvem) | modelsFilter · `:1156` | filtro local da lista (`window.filteredModels`) | filtra a lista | sempre | OCASIONAL | — |
| P8-C4 | Botão do modelo "<rótulo> · Local|Nuvem" (um por modelo) | model_<id> · `:1166` | `window.selectModel(m)` (local, sem Core) | abre "Detalhes" do modelo | sempre na lista | OCASIONAL | P8-I9 |
| P8-C5 | "Carregar mais" | modelsLoadMore · `:1170` | `core.loadMoreModels(aba)` (`bridge.py:1545`) | próxima página do catálogo | visível se há mais itens no total; habilitado se `modelsAvailable` e não busy | OCASIONAL | — |
| P8-C6 | "Usar este modelo" | useModelButton · `:1194` | `core.useModel(id, revisão capturada)` (`bridge.py:1552`) → `llm_configure` → `selftest` → `llm_mark_good` ou `llm_rollback` | grava modelo, testa e marca como bom; reverte se falhar | habilitado se há modelo selecionado e não busy | OCASIONAL | D3-C1, D3-C2 (mesma configuração) |
| P8-C7 | "Remover" (modelo personalizado) | removeCustomButton · `:1195` | `removeCustomConfirm` → `core.deleteCustomModel(id)` (`bridge.py:1572`) | remove da lista personalizada (não apaga no provedor) | visível só na aba Personalizados com modelo selecionado | AVANÇADO | D7 |
| P8-C8 | Provedor do modelo personalizado (Local llama.cpp, Ollama, Personalizado https, OpenRouter, OpenCode, Google) | customProvider · `:1202` | local (`customForm()`, `:144`) | define o formulário | sempre na aba Personalizados | AVANÇADO | D3-C1 (lista menor) |
| P8-C9 | "Identificador do modelo" (letras, números, . _ : / -, máx. 128) | customModelId · `:1203` | local | id do modelo | sempre na aba Personalizados | AVANÇADO | — |
| P8-C10 | Porta do servidor local (1024 a 65535, padrão 8080) | customPort · `:1204` | local | porta | habilitado para Local e Ollama | AVANÇADO | — |
| P8-C11 | "URL https do modelo personalizado" (máx. 200) | customUrl · `:1205` | local | URL | habilitado só para Personalizado | AVANÇADO | D3-C3 |
| P8-C12 | Recurso declarado "Streaming" (Desconhecido, Suportado, Não suportado) | customStreaming · `:1209` | local | valor declarado | sempre | AVANÇADO | — |
| P8-C13 | Recurso declarado "Tool use" | customToolUse · `:1210` | local | idem | sempre | AVANÇADO | — |
| P8-C14 | Recurso declarado "Visão" | customVision · `:1211` | local | idem | sempre | AVANÇADO | — |
| P8-C15 | Recurso declarado "Cancelamento" | customCancel · `:1212` | local | idem | sempre | AVANÇADO | — |
| P8-C16 | "Salvar modelo personalizado" | saveCustomButton · `:1215` | `core.saveCustomModel(form)` (`bridge.py:1565`) | grava na lista personalizada (até 16) | habilitado se disponível, não busy e `customFormProblem` vazio | AVANÇADO | — |
| P8-C17 | Modelo para fallback (lista de todos os modelos) | fallbackModel · `:1220` | local | escolhe o fallback | sempre na seção Fallback | AVANÇADO | — |
| P8-C18 | "Usar como fallback" | setFallbackButton · `:1225` | `core.setFallback(id, revisão)` (`bridge.py:1578`) → `llm_configure` | grava fallback | habilitado se disponível, não busy e `fallbackAllowed()` (nuvem exige consentimento e chave) | AVANÇADO | D3-C7 (consentimento) |
| P8-C19 | "Remover fallback" | clearFallbackButton · `:1226` | `core.clearFallback(revisão)` (`bridge.py:1580`) | remove fallback | habilitado se há fallback | AVANÇADO | — |
| P8-C20 | "Apagar dados do plugin" | clearPluginSettingsButton · `:1232` | `clearPluginConfirm` → `core.clearPluginSettings()` (`bridge.py:1598`) → `plugin_settings_clear` | apaga configurações guardadas pelo plugin (não o Core) | habilitado se conectado e não busy | AVANÇADO | D8 |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P8-I1 | "Estado do modelo atual: <texto>" (Disponível, Indisponível: recurso X, Sem chave, Sem consentimento) | modelsStatus · `:1133` | `core.modelsStatus` ← `bridge.py:1616` (`model_status`) | página 8 | OCASIONAL | D3-I1, D3-I3 |
| P8-I2 | "Configurado: <provedor> · <modelo>" ou "Nenhum modelo configurado" | modelsSelectedLabel · `:1134` | `core.modelsSelected` ← `bridge.py:1630` | página 8 | OCASIONAL | D3 |
| P8-I3 | Progresso (barra indeterminada) | modelsProgress · `:1135` | `core.modelsBusy` ← `bridge.py:1612` | operação em curso | OCASIONAL | — |
| P8-I4 | Resultado da operação de modelo | modelsResult · `:1136` | `core.modelsResult` ← `bridge.py:1614` | texto não vazio | OCASIONAL | — |
| P8-I5 | Contagem "N de M" da aba | modelsCount · `:1159` | `core.modelsRecommended` / `modelsCustom` e `*Total` (`bridge.py:1620-1626`) | página 8 | OCASIONAL | — |
| P8-I6 | "Nenhum modelo nesta lista." | modelsEmpty · `:1158` | texto fixo, condicional a lista vazia | lista vazia | OCASIONAL | — |
| P8-I7 | Selo de certificação por modelo: "Certificado", "Candidato", "Declarado" ou "Testado" | badge_<id> · `:1167` | `core.certificationBadge(state)` (`bridge.py:1607`) | por modelo | OCASIONAL | P8-I9 |
| P8-I8 | Lista de modelos: "<rótulo> · Local|Nuvem" | model_<id> · `:1166` | `window.filteredModels(...)` sobre `core.modelsRecommended/Custom` | por modelo | OCASIONAL | — |
| P8-I9 | Detalhes do modelo: título e linha "Local|Nuvem · provedor · modelo" | modelDetailTitle · `:1176-1177` | `window.selectedModel` (cópia do catálogo) | há modelo selecionado | OCASIONAL | P8-C4 |
| P8-I10 | "Certificação: <selo> · evidência · data" | modelDetailCertification · `:1178` | `selectedModel.certification` | há modelo selecionado | AVANÇADO | — |
| P8-I11 | "Licença", "Quantização", "Hash (SHA-256)", "Backend" | — · `:1179` | `selectedModel.license/quantization/sha256/backend` | há modelo selecionado | AVANÇADO | — |
| P8-I12 | Recursos: "Recurso streaming/tool_use/vision/cancel: <Suportado|Não suportado|Desconhecido>" (4 linhas) | — · `:1182-1186` | `core.featureLabel(features[x])` ← `bridge.py:1609` | há modelo selecionado | AVANÇADO | — |
| P8-I13 | "Contexto: N tokens" ou "não informado" | — · `:1188` | `features.context_tokens` | há modelo selecionado | AVANÇADO | — |
| P8-I14 | "Custo (USD por milhão de tokens): entrada X · saída Y" ou "Custo: não informado" | — · `:1189` | `selectedModel.cost` | há modelo selecionado | AVANÇADO | — |
| P8-I15 | "Latência: <baixa|média|alta|desconhecida> · hardware mínimo: RAM X GB, GPU <...>" | — · `:1190` | `latency_hint`, `min_hardware` | há modelo selecionado | AVANÇADO | — |
| P8-I16 | "Funciona offline" ou "Requer rede" | — · `:1191` | `selectedModel.offline` | há modelo selecionado | AVANÇADO | — |
| P8-I17 | Hardware da máquina: "CPU: N núcleos · RAM: X GB · GPU: ..." ou "Hardware: aguardando catálogo" | modelsHardware · `:1231` | `core.modelsHardware` ← `bridge.py:1628` | página 8 | AVANÇADO | — |
| P8-I18 | Fallback atual: "Atual: <provedor> · <modelo>" ou "Nenhum fallback configurado" | fallbackCurrent · `:1219` | `core.modelsFallback` ← `bridge.py:1634` | página 8 | AVANÇADO | D3 |
| P8-I19 | Aviso "Mensagens poderão ir para a nuvem se o modelo principal falhar" | fallbackCloudWarning · `:1221` | `window.fallbackIsCloud()` | fallback de nuvem escolhido | AVANÇADO | P8-I20 |
| P8-I20 | "Para fallback na nuvem, marque o consentimento em Motor LLM." | fallbackConsentNeeded · `:1222` | `core.llmConfig.cloud_consent` | fallback de nuvem sem consentimento | AVANÇADO | P7-I2, D3-I3 |
| P8-I21 | Problema do formulário personalizado | customFormProblem · `:1214` | `core.customFormProblem(form)` (`bridge.py:1605`) | texto não vazio | AVANÇADO | — |
| P8-T1 | Títulos "Modelo atual", "Catálogo", "Adicionar modelo personalizado", "Fallback (opcional)", "Hardware e plugin"; rótulos de recursos e campos | — · `:1132, :1140, :1201, :1218, :1230` | texto fixo | página 8 | OCASIONAL | — |
| P8-T2 | "Recursos declarados (não certificados)"; "Mostrar:" | — · `:1206, :1155` | texto fixo | página 8 | AVANÇADO | — |
| P8-T3 | "Aba Recomendados", "Aba Personalizados", "Filtro por local ou nuvem" (rótulos de acessibilidade) | modelsTabRecommended · `:1146` | texto fixo | página 8 | OCASIONAL | — |

### Página 9: Percepção e ação

- **Propósito:** testar sensores e ações simulados (C4). Nada age no computador.
- **Linhas:** nav `Main.qml:600`; `perceptionPanel` `:904-959`; privacidade `:909-914`; cartões por plugin `:915-953`; resultado `:954-958`.
- **Visibilidade:** página 9 e `core.perceptionAvailable` (algum dos 6 plugins C4 rodando; `bridge.py:1848`). Sem nenhum, a página some e o app volta ao Início.

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| P9-C1 | "Capturar" (screen_observe) | perception_screen_observe.capture · `:944-948` | `core.perceptionInvoke("screen_observe.capture", "{}")` (`bridge.py:1863`) | leitura sintética da tela | habilitado se conectado, plugin `running`, sem invocação em curso | DEV/TESTE | — |
| P9-C2 | "Estado" (screen_observe) | perception_screen_observe.status · `:944-948` | `perceptionInvoke("screen_observe.status")` | leitura | idem | DEV/TESTE | — |
| P9-C3 | "Árvore" (computer_control) | perception_computer_control.tree · `:944-948` | `perceptionInvoke("computer_control.tree")` | leitura sintética da árvore de acessibilidade | idem | DEV/TESTE | — |
| P9-C4 | "Estado" (computer_control) | perception_computer_control.status · `:944-948` | `perceptionInvoke(...)` | leitura | idem | DEV/TESTE | — |
| P9-C5 | "Estado" (audio_advanced) | perception_audio_advanced.state · `:944-948` | `perceptionInvoke(...)` | leitura | idem | DEV/TESTE | — |
| P9-C6 | "Estado" (mic_advanced) | perception_mic_advanced.state · `:944-948` | `perceptionInvoke(...)` | leitura; atualiza o indicador de microfone | idem | DEV/TESTE | P9-I1 |
| P9-C7 | "Estado" (camera_gesture) | perception_camera_gesture.state · `:944-948` | `perceptionInvoke(...)` | leitura; atualiza o indicador de câmera | idem | DEV/TESTE | P9-I2 |
| P9-C8 | "Estado" (display_manipulate) | perception_display_manipulate.status · `:944-948` | `perceptionInvoke(...)` | sempre "UNSUPPORTED" | idem | DEV/TESTE | — |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P9-I1 | "Microfone · indicador: ligado|desligado|não lido|plugin inativo" | micIndicator · `:912` | `core.perceptionMicIndicator` ← `bridge.py:1859` (último estado lido) | página 9 | DEV/TESTE | — |
| P9-I2 | "Câmera · indicador: ..." | cameraIndicator · `:913` | `core.perceptionCameraIndicator` ← `bridge.py:1861` | página 9 | DEV/TESTE | — |
| P9-T1 | "Backends simulados: nenhum hardware pessoal é acessado nesta build." | — · `:911` | texto fixo | página 9 | DEV/TESTE | P9-T2 |
| P9-I3 | Título do cartão "<plugin> <versão>" | perceptionTitle_<id> · `:923` | `core.perceptionPlugins` ← `bridge.py:1850` | por plugin | DEV/TESTE | D2-I9 |
| P9-I4 | Selo de estado: "em execução", "iniciando", "desativado", "falhou", "parado", "em quarentena" | perceptionState_<id> · `:931` | `perceptionStateText(state)` | por plugin | DEV/TESTE | D2-I9 |
| P9-I5 | "Último erro: <código>" | perceptionError_<id> · `:934` | `last_error` | há erro | DEV/TESTE | D2-I9 |
| P9-I6 | Selo "SINTÉTICO — sem hardware real" ou "UNSUPPORTED" (display_manipulate) | perceptionBadge_<id> · `:935` | constante por plugin | por plugin | DEV/TESTE | — |
| P9-I7 | "Permissão exigida: <rótulos> · concedida|não concedida" | — · `:936` | `plugin.permissions` (do Hub) e `approved` | por plugin | DEV/TESTE | D2-I5, D4-I2 |
| P9-I8 | Resultado da última ação | perceptionResult · `:957` | `core.perceptionResult` ← `bridge.py:1854` | texto não vazio | DEV/TESTE | — |
| P9-T2 | "Backend real: não suportado / pendente de validação humana" | — · `:937` | texto fixo | por plugin | DEV/TESTE | P9-T1 |
| P9-T3 | Títulos "Privacidade", "Último resultado" | privacyCard · `:910`; perceptionResultCard · `:955` | texto fixo | página 9 | DEV/TESTE | — |

### Página 10: Skills

- **Propósito:** motor de skills (procedimentos declarativos). Validar, simular, aprovar, habilitar, executar com decisão por passo, importar, exportar, histórico.
- **Linhas:** nav `Main.qml:597`; `skillsPanel` `:960-1126`: "Como funciona" `:964-969`, "Entradas e skills instaladas" `:970-1014`, "Criar skill" `:1015-1049`, "Importar e exportar" `:1050-1084`, "Execução e histórico" `:1085-1125`.
- **Visibilidade:** página 10 e `core.skillsAvailable` (snapshot `skills` presente, `bridge.py:1985`). A lista é vazia no início (texto "Nenhuma skill no Core ainda. Crie uma abaixo.", `:979`).
- **Regra central da página:** nada aqui concede permissão (`window.skillCan`, `Main.qml:50-61`).

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| P10-C1 | Campo "Entradas (JSON)" (texto "{}", até 16 KiB) | skillInputs · `:973-978` | local; usado por Simular e Executar | entradas da skill | sempre | AVANÇADO | — |
| P10-C2 | "Simular" (uma por skill) | skillDryRun_<id>_<versão> · `:994` | `core.skillDryRun(id, versão, entradas)` (`bridge.py:1905`) → `skill_dry_run` | valida dependências e prévia, sem chamar capacidades; marca "testada" | `skillCan("dry")`: sempre, exceto busy | AVANÇADO | — |
| P10-C3 | "Aprovar" | skillApprove_<id>_<versão> · `:995` | `core.skillApprove(id, versão)` (`bridge.py:1910`) → `skill_approve` com revisão | aprova a versão | estado `tested` | AVANÇADO | — |
| P10-C4 | "Habilitar" | skillEnable_<id> · `:996` | `core.skillEnable(id)` (`bridge.py:1915`) → `skill_enable` | habilita a versão aprovada | estado `approved` ou `disabled` | AVANÇADO | — |
| P10-C5 | "Desabilitar" | skillDisable_<id> · `:997` | `core.skillDisable(id)` → `skill_disable` | desabilita | estado `enabled` | AVANÇADO | — |
| P10-C6 | "Executar" | skillRun_<id> · `:998` | `core.skillRun(id, entradas)` (`bridge.py:1923`) → `skill_run` | inicia execução com decisão por passo | estado `enabled` e sem execução ativa | AVANÇADO | — |
| P10-C7 | "Reverter versão" | skillRollback_<id> · `:999` | `core.skillRollback(id)` → `skill_rollback` | volta à versão anterior | sempre, exceto busy | AVANÇADO | D10 (nenhum; ver NF-14) |
| P10-C8 | "Permissões" (abre o painel de permissões) | skillPermissions_<id> · `:1000` | `window.skillSelected = linha` (local) | mostra o painel de permissões | sempre | AVANÇADO | P10-I7 |
| P10-C9 | "Exportar" | skillExport_<id> · `:1001` | `core.skillExport(id, versão)` (`bridge.py:1940`) → `skill_export` | grava `<home>/skill-exports/<id>-<versão>.gskill` (caminho não é mostrado, AC-13) | estado approved, enabled ou disabled | AVANÇADO | — |
| P10-C10 | "Remover" (skill) | skillRemove_<id> · `:1002` | `removeSkillConfirm` → `core.skillRemove(id)` (`bridge.py:1921`) → `skill_remove` com revisão | remove a skill | sempre, exceto busy | AVANÇADO | D9 |
| P10-C11 | Editor "Manifesto da skill em JSON" | skillManifest · `:1018-1023` | local | texto do manifest | sempre | AVANÇADO | — |
| P10-C12 | "Validar" | skillValidate · `:1026` | `core.skillValidate(texto)` (`bridge.py:1901`) → `skill_validate` (não grava) | valida o manifest | habilitado se texto não vazio e não busy | AVANÇADO | — |
| P10-C13 | "Salvar rascunho" | skillSaveDraft · `:1027` | `core.skillSaveDraft(texto)` (`bridge.py:1903`) → `skill_save_draft` | grava como validada (não habilitada) | igual a P10-C12 | AVANÇADO | — |
| P10-C14 | Campo "Descrição da skill para o LLM" (máx. 1024) | skillDescription · `:1032-1037` | local | descrição | sempre | AVANÇADO | — |
| P10-C15 | "Gerar com LLM" | skillDraftWithLlm · `:1038` | `core.skillDraftWithLlm(descrição)` (`bridge.py:1956`) → `llm_engine.skill_draft`, prazo 30 s | cria rascunho pelo plugin (nunca habilita) | habilitado se `skillLlmAvailable` (plugin llm_engine rodando) e não busy | AVANÇADO | D3-C7 (plugin LLM) |
| P10-C16 | Campo "nome do pacote, sem caminho" (1 a 64, `[A-Za-z0-9._-]`) | skillImportName · `:1055-1061` | local | nome do arquivo em `<home>/skill-imports` | sempre | AVANÇADO | — |
| P10-C17 | "Pré-visualizar" (importação) | skillImport · `:1062` | `core.skillImport(nome)` (`bridge.py:1945`) → `skill_import` (lê só `<home>/skill-imports/<nome>.gskill`) | gera prévia | habilitado se nome válido e não busy | AVANÇADO | — |
| P10-C18 | "Instalar como rascunho" | skillImportConfirm · `:1082` | `core.skillImportConfirm(nome)` (`bridge.py:1949`) → `skill_import_confirm` | instala como rascunho (sem permissões) | habilitado se prévia sem achados e não busy | AVANÇADO | — |
| P10-C19 | "Negar passo" (um por passo aguardando) | skillDeny_<passo> · `:1103` | `core.skillDecide(run, passo, "deny")` (`bridge.py:1929`) | nega o passo | visível se passo `awaiting_approval` | AVANÇADO | P7-C4 (padrão igual) |
| P10-C20 | "Autorizar passo" | skillAuthorize_<passo> · `:1104` | `core.skillDecide(run, passo, "authorize")` | autoriza o passo que muda estado | idem | AVANÇADO | P7-C5 |
| P10-C21 | "Cancelar execução" | skillCancel · `:1110` | `core.skillCancel(run)` (`bridge.py:1935`) → `skill_cancel` | cancela a execução e desfaz passos concluídos | habilitado se execução `running` ou `awaiting_approval` | AVANÇADO | HD-06, P7-C3 |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P10-I1 | Resultado das skills (mensagem) | skillsResult · `:967` | `core.skillsResult` ← `bridge.py:1993` | texto não vazio | AVANÇADO | — |
| P10-I2 | Barra de progresso (indeterminada) | skillsProgress · `:968` | `core.skillsBusy` ← `bridge.py:1987` | operação em curso | AVANÇADO | — |
| P10-I3 | Linha da skill: "<nome> · <id> v<versão>" | skillTitle_<id>_<versão> · `:989` | `core.skillsItems` ← `bridge.py:1995` | por skill | AVANÇADO | — |
| P10-I4 | "Estado: <estado> · origem: <criada|importada (publisher não verificado)|rascunho do LLM> [· versão ativa]" | skillState_<id>_<versão> · `:990` | `skillStateText`, `skillSourceText` | por skill | AVANÇADO | D9 |
| P10-I5 | "Dependências: ok | faltando: X · permissões: aprovadas | pendentes" | skillDeps_<id>_<versão> · `:991` | `deps_ok`, `missing`, `permissions_ok` | por skill | AVANÇADO | P10-I7 |
| P10-I6 | "Aprovadas no Core: sim|não · Faltando: ..." e título "Permissões de <id> v<versão>" | skillPermissions · `:1010-1011` | `window.skillSelected` (cópia da linha) | após clicar em Permissões | AVANÇADO | P10-I5 |
| P10-I7 | Nota "Aprovar permissões não concede nada à skill: ela só usa capacidades já instaladas e aprovadas." | — · `:1012` | texto fixo | após clicar em Permissões | AVANÇADO | P4-T2 |
| P10-I8 | "Entradas (JSON de objeto, até 16 KiB) para Simular e Executar" | — · `:972` | texto fixo | sempre | AVANÇADO | — |
| P10-I9 | Aviso "Nenhuma skill no Core ainda. Crie uma abaixo." | skillsEmpty · `:979` | texto fixo, condicional a lista vazia | sem skills | AVANÇADO | — |
| P10-I10 | Rascunho gerado: "Rascunho <id> · v<versão> · <estado> · nada foi habilitado" | skillDraftOutput · `:1043` | `core.skillDraftOutput` ← `bridge.py:2004` | após "Gerar com LLM" com sucesso | AVANÇADO | — |
| P10-I11 | "Requisitos: ..." do rascunho | — · `:1044` | `draftOutput.requirements` | idem | AVANÇADO | — |
| P10-I12 | "Ambiguidades: ..." do rascunho | — · `:1045` | `draftOutput.ambiguities` | idem | AVANÇADO | — |
| P10-I13 | "Passos previstos:" (um por linha: "id → chamada") | — · `:1046` | `draftOutput.preview` | idem | AVANÇADO | — |
| P10-I14 | "Diferença:" (texto da versão) | — · `:1047` | `draftOutput.diff` | quando há diferença | AVANÇADO | — |
| P10-I15 | Aviso "Gerar com LLM indisponível: o plugin llm_engine não está ativo." | skillLlmUnavailable · `:1040` | texto fixo, condicional a `skillLlmAvailable` falso | sem plugin LLM | AVANÇADO | P7-T3 |
| P10-I16 | Pacote importado: "Pacote <nome>: <id> v<versão>" | skillImportPreview · `:1066` | `core.skillImportPreview` ← `bridge.py:2002` | após pré-visualizar | AVANÇADO | — |
| P10-I17 | "Publisher: <nome> · não verificado" | skillImportPreview · `:1067` | `publisher` | idem | AVANÇADO | D10 |
| P10-I18 | "Permissões exigidas: ... Novas nesta versão: ..." | — · `:1068` | `permissions_required`, `permission_delta` | idem | AVANÇADO | — |
| P10-I19 | "Escalada de permissões: esta versão pede mais que a anterior; aprove de novo antes de usar." | — · `:1069` | `permissions_escalated` | escalada | AVANÇADO | — |
| P10-I20 | "Dependências faltando: ..." | — · `:1070` | `missing_deps` | idem | AVANÇADO | — |
| P10-I21 | "Já existe uma skill com este id no Core." | — · `:1071` | `duplicate` | duplicata | AVANÇADO | — |
| P10-I22 | "Achado: <mensagem do código> (campo)" (um por achado) | skillFinding_<código> · `:1077` | `findings[]` + `core.codeMessage` | há achados | AVANÇADO | — |
| P10-I23 | Aviso "Importar instala como rascunho e nunca concede permissões. Valide, simule e aprove antes de usar." | — · `:1081` | texto fixo | prévia | AVANÇADO | P4-T2 |
| P10-I24 | "Execução <run> · <skill> · <estado> · passo <id>" | skillRunState · `:1090` | `core.skillCurrentRun` ← `bridge.py:1998` | há execução | AVANÇADO | — |
| P10-I25 | Passo: "Passo <id> · <estado> (· mensagem do código)" | skillStep_<id> · `:1100` | `skillCurrentRun.steps[]` | há execução | AVANÇADO | — |
| P10-I26 | "Saídas: <JSON>" | skillOutputs · `:1109` | `skillCurrentRun.outputs` | há saídas | AVANÇADO | — |
| P10-I27 | "Histórico de execuções" (título) e aviso "Nenhuma execução registrada." | skillHistoryEmpty · `:1114` | texto fixo, condicional | histórico vazio | AVANÇADO | — |
| P10-I28 | Linha do histórico: "<run> · <skill> v<versão> · <estado> · passo <id> · códigos" | skillHistory_<n> · `:1120-1122` | `core.skillHistory` ← `bridge.py:2000` (sem conteúdo) | por execução | AVANÇADO | — |
| P10-T1 | Títulos "Como funciona", "Entradas e skills instaladas", "Criar skill", "Importar e exportar", "Execução e histórico", "Permissões de..." | — · `:965, :971, :1016, :1051, :1086` | texto fixo | página 10 | AVANÇADO | — |
| P10-T2 | "Validar não grava. Simular não chama capacidades. Executar pede sua aprovação em cada passo que muda estado. Skills não concedem permissões." | — · `:966` | texto fixo | página 10 | AVANÇADO | — |
| P10-T3 | "Criar"/"Gerar com LLM: descreva o que a skill deve fazer (até 1024 bytes)" e rótulos | — · `:1029` | texto fixo | página 10 | AVANÇADO | — |

### Página 11: Conexões

- **Propósito:** contas de serviços (GitHub, Google, Home Assistant, MCP), consentimento por escopo, operações com o rótulo de risco, teste de leitura, rotas.
- **Linhas:** nav `Main.qml:598`; `connectionsPanel` `:1243-1353` (nova conta `:1253-1267`, contas `:1268-1352`); `routesPanel` `:1355-1399`.
- **Visibilidade:** página 11 e `core.connectionsAvailable` (`bridge.py:2085`). Rotas: `core.registryAvailable` (`:1357`).
- **Servidores:** todas as contas desta build usam servidores falsos (mensagem em `:1249`; "SERVIDOR FALSO" em `:1281`).

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| P11-C1 | Provedor da nova conta (GitHub, Google, Home Assistant, MCP) | connectionProvider · `:1257` | local | define o provedor | sempre | OCASIONAL | — |
| P11-C2 | "Nome da conta (ex.: Casa)" (máx. 64) | connectionLabel · `:1258-1263` | local | nome | sempre | OCASIONAL | P11-I3 |
| P11-C3 | "Adicionar conta" | connectionAdd · `:1264` | `core.connectionAdd(provedor, nome)` (`bridge.py:2021`) → `connection_add` | cria conta desconectada (máx. 8) | habilitado se sem operação em curso, nome válido e menos de 8 contas | OCASIONAL | — |
| P11-C4 | Caixa de consentimento por escopo pendente (uma por escopo) | connScope_<id>_<escopo> · `:1290-1298` | local (`window.setDraft`, `connDraftRevision`) | marca escopos a consentir | visível quando há escopo pendente | OCASIONAL | — |
| P11-C5 | Campo "Token de longa duração do Home Assistant" (oculto, 16 a 256) | connToken_<id> · `:1304-1310` | local; limpo logo após o envio | token | só em conta Home Assistant `connecting` | OCASIONAL | — |
| P11-C6 | "Enviar token" | connSetToken_<id> · `:1311` | `core.connectionSetToken(id, token)` (`bridge.py:2064`) → `connection_set_token`; limpa o campo | Core valida com uma sonda | habilitado se sem operação em curso e 16 a 256 caracteres | OCASIONAL | — |
| P11-C7 | "Consentir escopos marcados" | connConsent_<id> · `:1315` | `core.connectionConsent(id, JSON dos marcados)` (`bridge.py:2031`) → `connection_consent` | concede escopos marcados | visível com escopo pendente; habilitado se ao menos um marcado | OCASIONAL | — |
| P11-C8 | "Conectar" | connConnect_<id> · `:1316` | `core.connectionConnect(id)` (`bridge.py:2027`) → `connection_connect` | inicia conexão (device code ou token) | `connCan("connect")`: desconectada, erro, offline, expirada ou reautenticação | OCASIONAL | — |
| P11-C9 | "Atualizar" | connRefresh_<id> · `:1317` | `core.connectionRefresh(id)` → `connection_refresh` | renova credencial | `connCan("refresh")`: não MCP e conectada, expirada, reautenticação ou erro | AVANÇADO | — |
| P11-C10 | "Desconectar" | connDisconnect_<id> · `:1318` | `core.connectionDisconnect(id)` → `connection_disconnect` | apaga segredos; status desconectada | conectando, conectada, MCP com erro, expirada, reautenticação | AVANÇADO | — |
| P11-C11 | "Revogar" (Danger) | connRevoke_<id> · `:1319` | `core.connectionRevoke(id)` → `connection_revoke`. **Sem confirmação** (AC-05) | revoga no servidor e apaga | conectada, expirada ou reautenticação | AVANÇADO | — |
| P11-C12 | "Remover" (Danger) | connRemove_<id> · `:1320` | `core.connectionRemove(id)` → `connection_remove`. **Sem confirmação** (AC-05) | remove a conta | qualquer status exceto conectando | AVANÇADO | — |
| P11-C13 | "Confiar" (uma por ferramenta MCP que precisa de nova aprovação) | connTrust_<id>_<ferramenta> · `:1333` | `core.connectionTrustTools(id, [nome])` (`bridge.py:2072`) → `connection_trust_tools` | confia na ferramenta (cada chamada ainda pede aprovação) | visível só com estado `needs_reapproval` | AVANÇADO | — |
| P11-C14 | "Testar leitura" (uma por operação de leitura) | connTest_<id>_<operação> · `:1345` | `core.connectionCall(id, operação, "{}")` (`bridge.py:2051`) → `connection_call` | chamada de leitura **sem parâmetros** | visível se risco `read` e não `state.get`; habilitado se conectada e escopo concedido | DEV/TESTE | P11-I15 |
| P11-C15 | "Planejar" (uma por finalidade) | routePlan_<finalidade> · `:1385` | `core.registryPlan(finalidade)` (`bridge.py:2107`) → `registry_plan` (não executa) | mostra rota escolhida e descartadas | habilitado se `registryBusy` for falso | AVANÇADO | — |
| P11-C16 | "Ligar / Desligar fallback visual (revogar)" | routeVisual_<finalidade> · `:1386-1391` | `core.registryAllowVisual(finalidade, bool)` (`bridge.py:2111`) → `registry_allow_visual` | liga ou desliga o fallback visual (padrão desligado) | só para "Criar issue" | AVANÇADO | P11-I20 |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| P11-I1 | Resultado das conexões | connectionsResult · `:1250` | `core.connectionsResult` ← `bridge.py:2089` | texto não vazio | OCASIONAL | — |
| P11-I2 | Barra de progresso (indeterminada) | connectionsProgress · `:1251` | `core.connectionsBusy` ← `bridge.py:2087` | operação em curso | OCASIONAL | — |
| P11-I3 | Problema do nome da conta | connectionLabelProblem · `:1266` | `core.connectionLabelProblem(texto)` (`bridge.py:2083`) | texto inválido | OCASIONAL | P11-C2 |
| P11-I4 | "Nenhuma conta ainda. Adicione uma acima." | connectionsEmpty · `:1270` | texto fixo, condicional a lista vazia | sem contas | OCASIONAL | — |
| P11-I5 | Título da conta "<nome> · <provedor>" | connTitle_<id> · `:1280` | `core.connectionsItems` ← `bridge.py:2093` | por conta | OCASIONAL | — |
| P11-I6 | "SERVIDOR FALSO — sem credenciais reais" | connFake_<id> · `:1281` | `item.fake` | conta de servidor falso | DEV/TESTE | — |
| P11-I7 | "Estado: <estado>" (desconectada, conectando (aguardando confirmação), conectada, expirada, offline, erro, reautenticação necessária) | connStatus_<id> · `:1282` | `item.status` ← `connStatusText` | por conta | OCASIONAL | — |
| P11-I8 | "Conta no serviço: <account_ref>" | connAccount_<id> · `:1283` | `item.account_ref` | há referência | OCASIONAL | — |
| P11-I9 | "Código para confirmar no servidor: <código>" | connUserCode_<id> · `:1284` | `item.user_code` | conectando com código | OCASIONAL | — |
| P11-I10 | "Escopos concedidos: ..." | connGranted_<id> · `:1285` | `item.granted_scopes` | por conta | OCASIONAL | — |
| P11-I11 | "Escopos pedidos, aguardando seu consentimento: ..." | connPending_<id> · `:1286` | `item.pending_scopes` | há pendentes | OCASIONAL | — |
| P11-I12 | Rótulo da caixa de escopo "<rótulo> (<escopo>)" | connScope_<id>_<escopo> · `:1293` | `connScopeLabel` sobre `core.connectionsProviders` | por escopo pendente | OCASIONAL | — |
| P11-I13 | Ferramentas descobertas: "<nome> · <risco> · <estado> (motivo)" | connTool_<id>_<nome> · `:1332` | `item.tools[]` ← `connToolRiskText`, `connToolStateText` | conta MCP com ferramentas | AVANÇADO | — |
| P11-I14 | "Descrição do servidor: <texto>" (só texto, nunca enviado ao modelo) | connToolDesc_<id>_<nome> · `:1335` | `tools[].description` | ferramenta com descrição | AVANÇADO | — |
| P11-I15 | Operação: "<nome> (<rótulo>) · <risco> [· escopo não concedido]" | connOp_<id>_<nome> · `:1344` | `connOperationsFor(item)` ← `core.connectionsProviders` | por operação do provedor | AVANÇADO | — |
| P11-I16 | "Última chamada: <operação> · <resultado>" | connLastCall · `:1351` | `core.connectionLastCall` ← `bridge.py:2097` (só o resultado; o conteúdo do MCP não é exibido, AC-12) | há chamada | AVANÇADO | — |
| P11-I17 | Resultado das rotas | routesResult · `:1363` | `core.registryResult` ← `bridge.py:2121` | texto não vazio | AVANÇADO | — |
| P11-I18 | "<finalidade> · rota escolhida: <rota>" ou "nenhuma rota disponível" | routePurpose_<id> · `:1373` | `core.registryPurposes` ← `bridge.py:2127` | por finalidade | AVANÇADO | — |
| P11-I19 | Candidatos: "Escolhida|Descartada · <rota> · <status> · <motivo>" | routeCandidate_<id>_<rota> · `:1379` | `candidates[]` | por rota | AVANÇADO | — |
| P11-I20 | "Fallback visual: ligado por você | desligado (padrão)" | routeVisualState_<id> · `:1393` | `core.registryVisualAllowed` ← `bridge.py:2129` | só "Criar issue" | AVANÇADO | P11-C16 |
| P11-I21 | Aviso do fallback visual (texto constante) | routeVisualWarning_<id> · `:1394` | `core.registryVisualWarning` ← `bridge.py:2123` | só "Criar issue" | AVANÇADO | — |
| P11-T1 | "Como funciona": "Gideon usa a API autorizada de cada serviço. Você concede cada escopo; escrita e ações públicas pedem aprovação. Neste ambiente, todas as contas são servidores falsos." | — · `:1249` | texto fixo | página 11 | OCASIONAL | — |
| P11-T2 | Títulos "Como funciona", "Nova conta", "Contas", "Ferramentas descobertas (a descrição vem do servidor e é só texto)", "Operações", "Rotas" e a explicação de rotas | — · `:1248, :1254, :1269, :1323, :1338, :1361-1362` | texto fixo | página 11 | OCASIONAL | — |

---

## 3. Diálogos

### D1. Preferências (`preferences`, objectName `preferencesDialog`, `Main.qml:161-202`)

- **Propósito:** configuração da Base: frase de wake, feedback, ganho, prazo da sessão, rollback, recuperação de configuração e entrada para o Motor LLM.
- **Abre por:** SB-14 (`Main.qml:611`), P1-C2 (`:769`), P2-C2 (`:791`).
- **Visibilidade:** abre com `core.connected`. Controles desabilitados quando `preferencesAvailable` for falso (sessão de voz ativa, modo seguro ou reinício pendente; AC-01). Recuperação só em modo seguro (`:175`).
- **Fechar:** botão padrão do Qt, traduzido para "Fechar" (`localizeClose`, `:120`).

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| D1-C1 | "Preservar arquivo e restaurar padrões" | recoverConfigurationButton · `:175` | `core.recoverConfiguration()` (`bridge.py:1658`) → `recover_configuration` | preserva o arquivo inválido e volta aos padrões; reinício necessário | visível só em modo seguro; habilitado se `recoveryAvailable` | OCASIONAL | — |
| D1-C2 | Frase de wake do pack (lista) | wakeChoice · `:180` | local | escolhe a frase | `preferencesAvailable` | OCASIONAL | P1-C1 |
| D1-C3 | "Selecionar" | selectWakeButton · `:181` | `core.selectWake(id)` (`bridge.py:1648`) → `select_wake` (reinício) | grava a frase | habilitado se `preferencesAvailable` e a frase escolhida for `dev_qualified` | OCASIONAL | P1-C1 |
| D1-C4 | Checkbox "Resposta por voz (saída virtual)" | audiblePreference · `:184` | local; gravado por "Salvar" (D1-C9) | liga ou desliga resposta por voz | habilitado se `preferencesAvailable` e `voiceAvailable` | OCASIONAL | — |
| D1-C5 | Checkbox "Indicador visual de atividade" | visualPreference · `:185` | local; gravado por "Salvar indicador e ganho" (D1-C7) | liga ou desliga orbe | `preferencesAvailable` | OCASIONAL | P3-C8, HD-03 |
| D1-C6 | Ganho da saída virtual (0 a 100, passo 5, editável) | volumePreference · `:187` | local; gravado por D1-C7 | ganho | `preferencesAvailable` e `voiceAvailable` | OCASIONAL | P2-C1 |
| D1-C7 | "Salvar indicador e ganho" | saveFeedbackButton · `:188` | `core.saveFeedback(visual, volume)` (`bridge.py:1655`) → `feedback_preferences` | grava visual e ganho | `preferencesAvailable` | OCASIONAL | P2-C3, P3-C8 |
| D1-C8 | Prazo da sessão em ms (50 a 60000, passo 1000) | timeoutPreference · `:191` | local; gravado por D1-C9 | prazo da sessão | `preferencesAvailable` | AVANÇADO | P1-I5 |
| D1-C9 | "Salvar" | savePreferencesButton · `:193` | `core.savePreferences(audible, timeout)` (`bridge.py:1670`) → `preferences` | grava resposta por voz e prazo | `preferencesAvailable` | OCASIONAL | D1-C4, D1-C8 |
| D1-C10 | "Restaurar anterior" | rollbackPreferencesButton · `:194` | `core.rollbackPreferences()` (`bridge.py:1674`) → `rollback_preferences` | volta à configuração anterior | `rollbackAvailable` | AVANÇADO | — |
| D1-C11 | "Motor LLM" | llmOpenButton · `:198` | fecha Preferências e abre D3 (`window.openLlm()`) | abre o diálogo do Motor LLM | `core.connected` | OCASIONAL | D3 |
| D1-C12 | "Fechar" | Dialog.Close · `:165` | fecha | — | sempre | DIÁRIO | — |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| D1-I1 | Mensagem de configuração (modo seguro, reinício necessário) | configurationMessage · `:174` | `core.configurationMessage` ← `bridge.py:1665` | há mensagem | OCASIONAL | SB-R1 |
| D1-I2 | Descrição do pack: "<pack> · em desenvolvimento · virtual", perfil no processo, configuração salva, voz, idioma "inglês", "candidata" | packDescription · `:176` | `core.packDescription` ← `bridge.py:1640` | há pack | OCASIONAL | P0-I7, P5-I2 |
| D1-I3 | Qualificação da frase escolhida ("Qualificada em desenvolvimento; validação física pendente" ou "Requer prova de conceito") | wakeQualification · `:183` | `core.wakeChoices` | há frase | OCASIONAL | P1-I2 |
| D1-I4 | "Ganho da saída virtual: N% (0% = mudo)" | — · `:186` | `core.outputVolume` ← `bridge.py:1653` | sempre | OCASIONAL | P2-I2 |
| D1-I5 | "Atual no Core: voz ligada|desligada · N ms" (ou "Padrões de recuperação: ..." em modo seguro) | — · `:196` | `core.audibleFeedback`, `core.sessionTimeout`, `core.configurationStatus` | sempre | OCASIONAL | P1-I5 |
| D1-I6 | Resultado de preferências | preferencesResult · `:197` | `core.preferencesResult` ← `bridge.py:1695` | texto não vazio | OCASIONAL | — |
| D1-T1 | "Privacidade: capturas e legendas em memória; sem histórico persistente. Entrada/saída virtuais. CPU e sensibilidade fixas. Dispositivos físicos, outras vozes/idiomas e login automático indisponíveis." | — · `:189` | texto fixo | sempre | OCASIONAL | P0-T4 |
| D1-T2 | "Prazo da sessão em milissegundos", "Frase de wake do pack", rótulos de D1-C4 a D1-C8 | — · `:190`, `:180` | texto fixo | sempre | OCASIONAL | — |
| D1-T3 | "Alterações se aplicam à próxima sessão. Voz, frases e dispositivos dependem do pack e dos adaptadores disponíveis." | — · `:199` | texto fixo | sempre | OCASIONAL | — |

### D2. Plugins — Gideon Hub (`hubDialog`, objectName `hubDialog`, título "Plugins — Gideon Hub", `Main.qml:203-280`)

- **Propósito:** catálogo do Hub; revisar e aprovar permissões; instalar, reverter e remover pacotes verificados; ativar, desativar, revogar plugins; invocar capacidades de teste.
- **Abre por:** SB-08 (`Main.qml:601`) e P6-C1 (`:886`). Requer `core.connected`.
- **Visibilidade:** a maioria dos controles depende do estado de cada plugin e de `hubLifecycleAvailable` (`bridge.py:1728`) e `pluginsAvailable` (`bridge.py:1745`), que caem em sessão de voz (AC-01).

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| D2-C1 | "Cancelar importação" | abortHubImportButton · `:216` | `core.abortHubImport()` (`bridge.py:1783`) → `hub_abort` | cancela importação em curso (feita pela CLI) | visível só com importação ativa | OCASIONAL | — |
| D2-C2 | "Revisar permissões" ou "Permissões aprovadas" (uma por plugin) | review_<id> · `:225` | abre D4 com o plugin (`window.reviewPlugin`) | revisa permissões do manifest | habilitado se `hubApprovalAvailable` e status not_installed, update_available ou installed, e ainda não aprovado | OCASIONAL | P6-I2 |
| D2-C3 | "Instalar pacote verificado" | install_<id> · `:226` | `core.installHub(id, manifest_sha256)` (`bridge.py:1734`) → `hub_install` com revisão | instala (desativado) o payload já verificado em staging | visível se not_installed ou update_available; habilitado se `hubLifecycleAvailable`, payload em staging e permissões aprovadas | OCASIONAL | — |
| D2-C4 | "Reverter versão" | rollback_<id> · `:236` | `core.rollbackHub(id)` (`bridge.py:1737`) → `hub_rollback` | volta à versão anterior | habilitado se há versão anterior e estado installed | AVANÇADO | — |
| D2-C5 | "Remover plugin" (Danger) | remove_<id> · `:237` | abre D5 (`removeConfirm`) → `core.removeHub(id, revisão)` (`bridge.py:1740`) → `hub_remove` | remove o pacote instalado | habilitado se `hubLifecycleAvailable` | AVANÇADO | P10-C10 (padrão igual) |
| D2-C6 | "Ativar" | enable_<id> · `:254` | `core.enablePlugin(id)` (`bridge.py:1760`) → `plugin_enable` | ativa em sandbox sem rede | habilitado se `pluginsAvailable` e `pluginCanEnable` (instalado, aprovado, desativado) | OCASIONAL | — |
| D2-C7 | "Desativar" | disable_<id> · `:255` | `core.disablePlugin(id)` (`bridge.py:1763`) → `plugin_disable` | desativa | habilitado se `pluginsAvailable` e ativo | OCASIONAL | — |
| D2-C8 | "Revogar permissões" (Danger) | revoke_<id> · `:256` | abre D6 (`revokeConfirm`) → `core.revokePlugin(id, revisão)` (`bridge.py:1766`) → `plugin_revoke` | revoga aprovação e desativa | habilitado se `pluginsAvailable` e não em quarentena | AVANÇADO | — |
| D2-C9 | Campo "Texto para a capability" (máx. 256) | capabilityInput_<id> · `:257-263` | local (`window.setDraft`) | texto de teste | habilitado se plugin `running` | DEV/TESTE | — |
| D2-C10 | "Invocar" (uma por capability) | invoke_<capability> · `:269` | `core.invokeCapability(cap, texto)` (`bridge.py:1771`) → `capability_invoke`, prazo 3 s | invoca capability de teste | habilitado se plugin `running` | DEV/TESTE | — |
| D2-C11 | "Cancelar" (capability) | cancelCapability_<id> · `:270` | `core.cancelCapability(cap)` (`bridge.py:1774`) → `capability_cancel` | cancela a invocação | habilitado se é a capability ativa | DEV/TESTE | P7-C3 (rótulo) |
| D2-C12 | "Fechar" | Dialog.Close · `:207` | fecha | — | sempre | DIÁRIO | — |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| D2-I1 | Descrição do Hub | hubDescription · `:214` | `core.hubDescription` ← `bridge.py:1788` | sempre | OCASIONAL | P6-I1 |
| D2-I2 | "Preparando <plugin>: N/M bytes" | — · `:215` | `core.hubImportDescription` ← `bridge.py:1779` | importação ativa | AVANÇADO | — |
| D2-I3 | Linha do plugin do catálogo: "<id> <versão> · <publisher>" | — · `:222` | `core.hubEntries` | por entrada | OCASIONAL | P6-I2 |
| D2-I4 | Estado: "Instalado · ativo (sandbox, sem rede)", "Instalado · desativado (sem execução)", "Atualização disponível", "Pacote verificado em staging; não instalado", "Não instalado" ou "Incompatível: <motivo>" + licença | status_<id> · `:223` | `status`, `payload_staged`, `reason`, `license`, `pluginEnabledFor` | por entrada | OCASIONAL | P6-I2 |
| D2-I5 | "Permissões aprovadas para este manifesto:" ou "Permissões declaradas (não aprovadas):" + IDs de permissão (rótulos) + política de suporte | — · `:224` | `permissions`, `permissions_approved`, `core.permissionLabel`, `support_policy` | por entrada | OCASIONAL | P9-I7, D4-I2, P4-T2 |
| D2-I6 | Título "Instalados no Core" | — · `:229` | texto fixo | há instalados | AVANÇADO | — |
| D2-I7 | "<id> <versão> · Em quarentena | Instalado · ativo | Instalado · desativado (sem execução)" | — · `:235` | `core.hubInstalled` ← `bridge.py:1732` | há instalados | AVANÇADO | D2-I4 |
| D2-I8 | Resultado do ciclo de instalação | hubLifecycleResult · `:240` | `core.hubApprovalResult` ← `bridge.py:1709` | texto não vazio | OCASIONAL | — |
| D2-I9 | Linha de plugin no Core: "<id> <versão> · Ativo (sandbox, sem rede) | Iniciando… | Falhou: erro | Parado | Em quarentena | Desativado" | pluginStatus_<id> · `:251` | `core.pluginItems` ← `bridge.py:1747` | por plugin | OCASIONAL | P9-I3, P9-I4 |
| D2-I10 | "Capacidades: ..." | — · `:252` | `pluginItems.capabilities` | por plugin | AVANÇADO | — |
| D2-I11 | "Aprove novamente as permissões para ativar" | reapprovalHint_<id> · `:253` | `pluginInstalled` e não `pluginApproved` | instalado sem aprovação atual | OCASIONAL | — |
| D2-I12 | Resultado do ciclo de plugin | pluginLifecycleResult · `:275` | `core.pluginResult` ← `bridge.py:1751` | texto não vazio | OCASIONAL | — |
| D2-I13 | Resultado da capability (texto ou JSON, até 512 caracteres) | capabilityResult · `:276` | `core.capabilityResultText` ← `bridge.py:1753` | há resultado | DEV/TESTE | — |
| D2-I14 | Título "Plugins no Core" | — · `:241` | texto fixo | há plugins | OCASIONAL | — |
| D2-T1 | "Instalar copia o pacote verificado para o Core; nada é executado. O catálogo não concede acesso ao computador." | — · `:277` | texto fixo | sempre | OCASIONAL | P6-T1 |
| D2-T2 | Texto de confirmação de remoção e revogação (ver D5 e D6) | — | texto fixo | ao confirmar | AVANÇADO | — |

### D3. Motor LLM (`llmDialog`, objectName `llmDialog`, `Main.qml:281-348`)

- **Propósito:** configurar o provedor do motor LLM, a chave (write-only) e o consentimento de nuvem.
- **Abre por:** D1-C11 (`Main.qml:198`) apenas. Não há entrada direta na barra lateral.
- **Visibilidade:** os campos habilitam com `core.llmConfigAvailable` (`bridge.py:1393`): config pronta, sem sessão de voz (AC-01). A configuração não depende do plugin LLM estar instalado (AC-09).
- **Regra:** a chave sai do QML na mesma chamada e o campo é limpo; nunca é exibida de volta (`Main.qml:330-331`).

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| D3-C1 | Provedor (OpenRouter, OpenCode, Google AI Studio, Personalizado) | llmProvider · `:303-307` | local (inicial: `core.llmConfig.provider`) | escolhe o provedor | habilitado se `llmConfigAvailable` | OCASIONAL | P8-C8 |
| D3-C2 | Modelo (letras, números, . _ : / -, máx. 128) | llmModel · `:309-313` | local | id do modelo | habilitado se `llmConfigAvailable` | OCASIONAL | P8-C6 |
| D3-C3 | URL do provedor personalizado (máx. 200, só https; http só em loopback de teste) | llmUrl · `:315-318` | local | URL | habilitado só se "Personalizado" e disponível | AVANÇADO | P8-C11 |
| D3-C4 | Chave de API (write-only, mascarada, máx. 256) | llmKey · `:320-324` | local; some do QML ao enviar | chave | habilitado se disponível | OCASIONAL | — |
| D3-C5 | "Salvar chave" | saveKeyButton · `:327-332` | `core.setApiKey(provedor, chave)` (`bridge.py:1398`) → `secret_set`; limpa o campo | grava no cofre do Core | habilitado se disponível e campo não vazio | OCASIONAL | — |
| D3-C6 | "Remover chave" (Danger) | clearKeyButton · `:333` | `core.clearApiKey(provedor)` (`bridge.py:1404`) → `secret_clear`. **Sem confirmação** (AC-05) | apaga a chave do provedor | habilitado se disponível e chave configurada | AVANÇADO | — |
| D3-C7 | Checkbox "Permitir envio de conversas ao provedor na nuvem" | llmConsent · `:335` | local (inicial: consentimento salvo; nunca ligado sozinho) | consentimento de nuvem | habilitado se disponível | OCASIONAL | P7-I2, P8-I20 |
| D3-C8 | "Salvar configuração" | saveLlmConfigButton · `:338-342` | `core.configureLlm(provedor, modelo, url, consentimento, revisão capturada)` (`bridge.py:1410`) → `llm_configure` | grava provedor, modelo, URL e consentimento | habilitado se disponível, modelo válido e provedor não local | OCASIONAL | P8-C6 |
| D3-C9 | "Fechar" | Dialog.Close · `:286` | fecha | — | sempre | DIÁRIO | — |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| D3-I1 | "Chave configurada" ou "Sem chave" | llmKeyStatus · `:319` | `core.llmSecretsConfigured[provedor]` ← `bridge.py:1389` | sempre | OCASIONAL | P8-I1 |
| D3-I2 | "Consentimento salvo: concedido | não concedido" | — · `:337` | `core.llmConfig.cloud_consent` | sempre | OCASIONAL | P7-I2 |
| D3-I3 | Aviso "Mensagens serão enviadas ao provedor escolhido na nuvem" (sempre visível) | llmConsentWarning · `:336` | texto fixo | sempre | OCASIONAL | — |
| D3-I4 | "Configuração local ativa: altere em Modelos LLM." | llmLocalNotice · `:344` | `core.llmConfig.provider` (local ou ollama) | provedor local salvo | OCASIONAL | P8-I2 |
| D3-I5 | Resultado da configuração | llmResult · `:345` | `core.llmResult` ← `bridge.py:1395` | texto não vazio | OCASIONAL | — |
| D3-T1 | "Motor opcional. Sem ele, voz, wake e comandos da Base continuam funcionando." | — · `:301` | texto fixo | sempre | OCASIONAL | P7-T2 |
| D3-T2 | Rótulos "Provedor", "Modelo: letras, números e . _ : / - (até 128)", "URL personalizada: somente https (http apenas em loopback de teste)", "Chave" | — · `:302, :308, :314` | texto fixo | conforme provedor | OCASIONAL | — |

### D4. Revisar permissões (`reviewDialog`, objectName `hubReviewDialog`, `Main.qml:349-368`)

- **Propósito:** aprovar as permissões declaradas de um plugin, por manifest, com reconhecimento de que o publisher não é autenticado.
- **Abre por:** D2-C2 (`Main.qml:225`). Captura a revisão ao abrir (`core.beginHubReview`, `:352`).
- **Visibilidade:** aprovação disponível se `hubApprovalAvailable` (`bridge.py:1716`).

| ID | Controle | objectName · linha | Ação / slot | Efeito | Visível / habilitado | Classe | Duplicado em |
|---|---|---|---|---|---|---|---|
| D4-C1 | Checkbox "Entendo que o publisher não foi autenticado" | publisherAcknowledgement · `:363` | local | reconhecimento obrigatório | habilitado se `hubApprovalAvailable` | OCASIONAL | — |
| D4-C2 | "Aprovar estas permissões" | approveHubButton · `:364` | `core.approveHub(plugin, manifest, permissions, reconhecido, revisão)` (`bridge.py:1723`) → `hub_approve` | grava aprovação por manifest; não instala nem executa | habilitado se disponível, reconhecimento marcado e ainda não aprovado | OCASIONAL | — |
| D4-C3 | "Fechar" | Dialog.Close · `:354` | fecha | — | sempre | DIÁRIO | — |

| ID | Informação | objectName · linha | Fonte | Visível quando | Classe | Duplicado em |
|---|---|---|---|---|---|---|
| D4-I1 | "<id> <versão> · <publisher>" | — · `:360` | `window.reviewPlugin` (cópia da linha do catálogo) | sempre | OCASIONAL | D2-I3 |
| D4-I2 | "Permissões: <IDs separados por vírgula>" (IDs crus, sem rótulo, AC-04) | — · `:361` | `reviewPlugin.permissions` | sempre | OCASIONAL | D2-I5 |
| D4-I3 | "Aprovar permissões não instala nem executa este plugin. A aprovação vale somente para este manifesto." | — · `:362` | texto fixo | sempre | OCASIONAL | D2-T1 |
| D4-I4 | Resultado da aprovação | hubApprovalResult · `:365` | `core.hubApprovalResult` ← `bridge.py:1709` | texto não vazio | OCASIONAL | D2-I8 |

### D5 a D9. Diálogos de confirmação (todos com "Cancelar" focado por padrão)

| ID | Diálogo (objectName · linhas) | Texto de confirmação (linha) | Botão de confirmação (linha) | Ação | Classe |
|---|---|---|---|---|---|
| D5 | Remover plugin (`removeConfirm`, `:370-385`) | "Remover <id> <versão> do Core? Nada é executado e o catálogo não muda." (`:382`) | "Remover" confirmRemoveButton (`:383`) | `core.removeHub(id, revisão)` | AVANÇADO |
| D6 | Revogar permissões (`revokeConfirm`, `:386-401`) | "Revogar permissões de <id>? O plugin será desativado e o processo encerrado. Reativar exige nova aprovação." (`:398`) | "Revogar" confirmRevokeButton (`:399`) | `core.revokePlugin(id, revisão)` | AVANÇADO |
| D7 | Remover modelo personalizado (`removeCustomConfirm`, `:403-417`) | "Remover <rótulo> da lista de modelos personalizados? O modelo no provedor não é apagado." (`:414`) | "Remover" confirmRemoveCustomButton (`:415`) | `core.deleteCustomModel(id)` | AVANÇADO |
| D8 | Apagar dados do plugin (`clearPluginConfirm`, `:419-431`) | "Apagar as configurações guardadas pelo plugin LLM, inclusive modelos personalizados? O plugin e a configuração do Core (provedor, modelo e chaves) não são alterados." (`:428`) | "Apagar dados" confirmClearPluginButton (`:429`) | `core.clearPluginSettings()` | AVANÇADO |
| D9 | Remover skill (`removeSkillConfirm`, `:433-447`) | "Remover <id> v<versão> do Core? Nada é executado." (`:444`) | "Remover" confirmRemoveSkillButton (`:445`) | `core.skillRemove(id)` | AVANÇADO |

Sem confirmação, apesar de destrutivos: Revogar e Remover conexão (P11-C11, P11-C12) e Remover chave do provedor (D3-C6). Ver AC-05.

---

## 4. Funcionalidades do Core sem tela

Operações do enum `Operation` (`src/protocol.rs`) e recursos documentados que a UI não expõe, ou expõe só parcialmente. "Sem slot" = nenhum `@Slot` em `bridge.py` envia a operação (grep).

| ID | Funcionalidade do Core | Fonte | Situação na UI | Classe |
|---|---|---|---|---|
| NF-01 | Importação de pacote do Hub por bytes: `hub_begin`, `hub_chunk`, `hub_finish` | `src/protocol.rs` (HubBegin, HubChunk, HubFinish); `docs/B3.md` B3.2b | Sem slot. Só a CLI `scripts/hub_import.py`. A UI mostra progresso (D2-I2) e cancela (D2-C1). Não há seletor de arquivo | AVANÇADO |
| NF-02 | Descartar payload em staging: `hub_discard_staged` | `src/protocol.rs` (HubDiscardStaged) | Sem slot, sem tela. Não há como descartar payload verificado sem reinstalar | AVANÇADO |
| NF-03 | Wake virtual: `virtual_wake` | `src/protocol.rs` (VirtualWake) | Sem slot. Só teste (`--virtual-input`) | DEV/TESTE |
| NF-04 | Ação de captura: `action` (`session_id`, `capability`) | `src/protocol.rs` (Action) | Sem slot, sem tela | DEV/TESTE |
| NF-05 | Bump de época de teste: `agent_test_bump` | `src/protocol.rs` (AgentTestBump); `docs/C3.md` | Sem slot. Só teste | DEV/TESTE |
| NF-06 | Última configuração boa do motor LLM (LKG): `llm_mark_good`, `llm_rollback`, campo `llm.config.lkg` | `docs/C2.md` item 2 | Usados só dentro de "Usar este modelo" (P8-C6). Sem botão de restaurar LKG; `lkg` não aparece no QML | AVANÇADO |
| NF-07 | Descrever modelo: `llm_engine.models` com `describe {id}` | `docs/C2.md` | Não chamado por `bridge.py` (grep zero) | AVANÇADO |
| NF-08 | Recursos efetivos do modelo: `llm_engine.models` com `features {}` | `docs/C2.md` | Não chamado por `bridge.py` | AVANÇADO |
| NF-09 | Sondar o modelo atual sem trocá-lo (selftest isolado) | `docs/C2.md` (selftest) | Só existe dentro do fluxo "Usar este modelo" | AVANÇADO |
| NF-10 | Fallback usado na última resposta (`llm_fallback_used`, `used_fallback`) | `docs/C2.md` (evento sem conteúdo) | Não exposto ao bridge nem à UI. O usuário não vê quando o fallback respondeu (AC-16) | AVANÇADO |
| NF-11 | Ações e configuração de percepção: `computer_control.act`, `audio_advanced.act`, `mic_advanced.configure`, `mic_advanced.monitor`, `mic_advanced.record`, `camera_gesture.optin`, `camera_gesture.capture`, `camera_gesture.gestures` | `bridge.py` `PERCEPTION_CAPABILITIES` (allowlist); `docs/C4.md` | Allowlisted, mas `perceptionActions` (`Main.qml:108`) só tem leituras. Sem botão para nenhuma delas | DEV/TESTE |
| NF-12 | Operações de conexão com parâmetros: `repo.get`, `issues.create`, `issues.update`, `pulls.comment`, `gmail.send`, `gmail.messages.delete`, `calendar.events.create`, `drive.files.create`, `states.list` (sem ID), `service.call`, `mcp.call` | `docs/S5.md` E2; `bridge.py` `connectionCall` | UI só envia `"{}"` (`Main.qml:1345`). Operações que precisam de parâmetros ou de escrita não têm formulário | AVANÇADO |
| NF-13 | Snapshot de captura: `capture` (início, fim, contagem de amostras, SHA-256 do PCM, motivo) | `bridge.py` `CAPTURE_KEYS`, `validate_snapshot` | Validado, não exibido | AVANÇADO |
| NF-14 | Snapshot de fala: `speech` (amostras, pedaços, SHA-256, pico, RMS, primeiro PCM, tempo decorrido, sink) e `speech_samples` | `bridge.py` `SPEECH_KEYS`, `TOP_KEYS` | Validado; a UI só mostra `speechStatus`. Sem progresso de TTS | AVANÇADO |
| NF-15 | Transcrição: `transcript.revision`, `transcript.confidence`, `transcript.audio_end_us`, `transcript.source` | `bridge.py` `TRANSCRIPT_KEYS` | Validado, não exibido (confiança é "Desconhecido" por design) | AVANÇADO |
| NF-16 | Pacote de voz: `base_pack.engines`, `preflight`, `audio_input`, `audio_output` | `bridge.py` `PACK_KEYS` | Validado, não exibido | AVANÇADO |
| NF-17 | Hub: `orphans`, `repository`, `catalog_sha256`, `storage_error` (conexões) e `retry_after` | `bridge.py` `HUB_KEYS`, `CONN_BLOCK_KEYS`, `docs/S5.md` | Validado, não exibido. Os códigos de erro chegam como texto, não os campos | AVANÇADO |
| NF-18 | Eventos e sequência (`events`, `sequence`, anel de 64) e log de auditoria | `bridge.py` `EVENT_KEYS`; `docs/S5.md` (audit) | Sem tela de eventos ou auditoria | AVANÇADO |
| NF-19 | Caminho do pacote exportado de skill (`<home>/skill-exports/...`) | `docs/S4.md` D4 | Mensagem "Pacote exportado; publisher não verificado" sem caminho (AC-13) | AVANÇADO |
| NF-20 | Origem da importação de skill: arquivo em `<home>/skill-imports` | `docs/S4.md` D4 | Só um campo de nome; o usuário precisa colocar o arquivo lá sem instrução na UI | AVANÇADO |
| NF-21 | Atualização e reversão do pacote instalado (`gideon-install update|rollback`) | `docs/B4.md` B4.2 | Só CLI. A UI não oferece atualização de pacote (`docs/B4.md`) | OCASIONAL |
| NF-22 | Reinício do Core (exigido por wake, feedback de config e plugins) | `docs/B2`, `bridge.py` (`restart_required`) | UI só escreve "reinicie o Core" (D1-I1). Sem ação | OCASIONAL |
| NF-23 | Reparo de instalação (`gideon-install repair`) | `docs/B4.md` (emendas) | Só CLI | AVANÇADO |
| NF-24 | Plugin settings (`settings.get/put`) | `docs/C2.md` item 4 | Lado do plugin, sem tela. Só o "apagar" tem tela (P8-C20) | AVANÇADO |
| NF-25 | Revisões de estado não usadas: `preferencesRevision`, `skillsRevision`, `connectionsRevision`, `registryRevision` | `bridge.py:1693, 1991, 2091, 2125` | Propriedades sem uso no QML (grep). A revisão é enviada em outras chamadas, então não há perda funcional | DEV/TESTE |
| NF-26 | Dispositivos de entrada e saída, câmera e tela reais | `docs/BASE_UI_MAP.md`; `docs/C4.md` | Sem adaptadores; só simulados (P9) ou virtuais (P1, P2) | OCASIONAL |

---

## 5. Duplicações globais

Mesma informação ou mesmo controle em mais de um lugar. Lista consolidada (as referências por linha estão nas tabelas acima).

| ID | Assunto | Onde aparece | Observação |
|---|---|---|---|
| DU-01 | Estado do Wake, STT e TTS | P0-I4..I6 (Início), P1-I3, P1-I5, P2-I1, P5-I4..I6, HD-05 (aura) | Quatro lugares para o mesmo dado |
| DU-02 | Diagnóstico em texto | SB-R1 (rodapé), P5-I1, D1-I1 | Rodapé usa prefixo "Áudio virtual" diferente de P5-I1 |
| DU-03 | Frase de wake | P0-I7, P1-I1, P1-I4 (cartões), P1-C1, D1-C2, D1-C3, D1-I2 | Seleção em duas telas (cartão e Preferências) |
| DU-04 | Ganho da resposta | P2-C1, P2-C3, P2-I2, D1-C6, D1-C7, D1-I4 | Gravado por dois caminhos (Preferências e página Áudio) |
| DU-05 | Indicador visual (orbe) | P3-C8, D1-C5, D1-C7, HD-03, herói do Início | Gravado por dois caminhos |
| DU-06 | Prazo da sessão | D1-C8, D1-C9, D1-I5, P1-I5 | Só lido na página Voz e Wake |
| DU-07 | Catálogo de plugins | SB-05 (Gideon Hub), SB-08 (Plugins), P6-I2, D2-I3..I7 | Duas entradas no menu para o mesmo catálogo (ver NT-03) |
| DU-08 | Descrição do Hub | P6-I1, D2-I1 | Mesmo texto |
| DU-09 | Estado de plugin | D2-I4, D2-I7, D2-I9, P9-I3..P9-I5 | Mesmo estado em duas telas |
| DU-10 | Permissões de plugin e de skill | D2-I5, D4-I2 (IDs crus), P9-I7, P10-I5, P10-I6 | Três formatos diferentes (IDs crus em D4 e rótulos nos demais) |
| DU-11 | Consentimento de nuvem | P7-I2, P8-I20, D3-C7, D3-I2 | Mostrado em quatro lugares |
| DU-12 | Configuração do motor LLM | D3 (provedor, modelo, URL, consentimento) e P8-C6, P8-C18 (usar, fallback) | Dois diálogos gravam a mesma configuração |
| DU-13 | Estado do chat | P7-I1 e P7-I4 (mesmo texto) | Repetido na mesma página |
| DU-14 | Transcrição e resultado | P0-I9, P0-I10 (aparecem em qualquer página com sessão) | Repetem-se em todas as páginas durante a sessão |
| DU-15 | Botões "Cancelar" | HD-06, P7-C3, P7-C7 (Abortar), P10-C21, D2-C1, D2-C11 | Mesmo rótulo, efeitos diferentes (AC-08) |
| DU-16 | Mensagem de ativação do Motor LLM | P7-T3, P10-I15 | Textos parecidos, em telas diferentes |
| DU-17 | Privacidade | P0-T4, D1-T1 | Texto fixo, nenhum controle |

---

## 6. Achados (fatos verificados no código)

| ID | Achado | Evidência | Impacto |
|---|---|---|---|
| AC-01 | Durante a sessão de voz, a conversa e os controles de configuração ficam indisponíveis. O item Conversa some da barra e a página 7 exibe "Motor LLM não está ativo" mesmo com o plugin rodando. Causa: `chatAvailable` depende de `pluginsAvailable`, que depende de `hubLifecycleAvailable`, que depende de `preferencesAvailable`, que exige `not sessionId`. Inferido do código; confirmar em execução | `bridge.py:1272-1273, 1683-1684, 1728-1729, 1745-1746`; `Main.qml:581, 1237, 1405` | Alto: sessão de voz mostra a conversa como desligada |
| AC-02 | Cartão "Modo: Base · sem LLM" é texto fixo na página Início. Não reflete o plugin de chat | `Main.qml:707` | Alto: informação falsa quando o LLM roda |
| AC-03 | Página "Permissões" não lista permissões, aprovações ou grants. Só um parágrafo | `Main.qml:840-843` | Alto: a página existe sem conteúdo |
| AC-04 | Diálogo "Revisar permissões" mostra IDs crus (`network.llm`), enquanto os demais usam `core.permissionLabel` | `Main.qml:361` vs `:224, :936` | Médio: inconsistência de texto |
| AC-05 | Revogar e Remover conexão (`:1319-1320`) e Remover chave do provedor (`:333`) executam sem confirmação. Remover plugin, revogar plugin, remover modelo, apagar dados e remover skill pedem confirmação | `Main.qml:1319, 1320, 333` vs `:237, :256, :415, :429, :445` | Alto: ações destrutivas sem freio |
| AC-06 | Tema e cor da janela não persistem. Não há campo no snapshot nem slot | `Main.qml:34-35`; `bridge.py` (sem `theme`) | Baixo: escolha se perde ao reabrir |
| AC-07 | O catálogo de plugins aparece em duas entradas do menu ("Gideon Hub" e "Plugins") e o Notion pede "uma aba Plugins" | `Main.qml:596, 601`; `docs/UI_NOTION_REQS.md` | Médio: duplicação de entrada |
| AC-08 | O rótulo "Cancelar" aparece em seis lugares com efeitos diferentes (sessão de voz, resposta do LLM, capability, execução de skill, importação) | `Main.qml:651, 1473, 270, 1110, 216` | Médio: rótulo ambíguo |
| AC-09 | A configuração do Motor LLM funciona sem o plugin instalado (`llmConfigAvailable` não checa plugin), enquanto o Notion diz que a área LLM só existe com o plugin | `bridge.py:1393`; `Main.qml:198, 281` | Baixo: divergência de regra |
| AC-10 | Provedores "Local (llama.cpp)" e "Ollama" aparecem como opções, mas o C2 registra que llama.cpp não foi baixado nem testado; modelos locais ficam "candidato" | `Main.qml:1202`; `docs/C2.md` ("Não feito") | Médio: opção oferecida sem validação |
| AC-11 | Página Percepção e ação exibe estados sintéticos em produto, com selo "SINTÉTICO — sem hardware real" | `Main.qml:935, 911` | Baixo: classe DEV/TESTE dentro da navegação principal |
| AC-12 | "Testar leitura" envia `{}`. Operações que precisam de parâmetros falham sem formulário. Conteúdo de ferramenta MCP não é exibido (só o resultado) | `Main.qml:1345, 1351`; `bridge.py:2051` | Médio |
| AC-13 | Exportar skill não mostra o caminho do arquivo gerado | `Main.qml:1001`; `bridge.py:1940` e `OPS` | Baixo |
| AC-14 | Proposta de ferramenta local não mostra risco nem efeito. Só propostas de conexão mostram risco. Passos de skill mostram o id e o estado, sem risco | `Main.qml:1500-1505, 1502, 1549` | Médio: aprovação sem risco nem efeito |
| AC-15 | Não há divulgação progressiva: Skills e Conexões mostram todos os campos técnicos na mesma página. Não há "avançado" | `grep "Avançad" app/Main.qml` vazio | Médio |
| AC-16 | O usuário não sabe quando o fallback do modelo respondeu | `docs/C2.md`; `bridge.py` sem `used_fallback` | Médio |
| AC-17 | Entrada de teste "Comando de texto" e "Invocar" de capability aparecem na interface comum, sem separação de modo de desenvolvimento | `Main.qml:1569, 257-270` | Baixo: nenhuma barreira visual |
| AC-18 | Textos fixos com dados de hardware e de voz (Pocket TTS · Alba, PCM virtual, CPU) ficam errados quando surgem dispositivos ou vozes reais | `Main.qml:707, 763, 776, 789`; `bridge.py:1640` | Baixo: manutenção |

---

## 7. Cobertura do Notion

Fonte: `docs/UI_NOTION_REQS.md`. Classificação: **EXISTE** (tela e controle hoje), **EXISTE NO CORE, SEM TELA**, **NÃO IMPLEMENTADO** (lacuna: não há backend nem tela), **NÃO CONSTRUÍDO DE PROPÓSITO** (sem backend, decisão registrada).

| ID | Requisito / área do Notion | Situação | Onde está (tela ou controle) / o que falta | Verificado em |
|---|---|---|---|---|
| NT-01 | Dashboard / Conversas básico | EXISTE | Início (P0), transcrição de voz (P0-I9), Conversa só com LLM (P7) | `Main.qml:654-724, 1563, 1402` |
| NT-02 | Configuração de Voz e Dispositivos | EXISTE PARCIAL | Voz e Wake (P1), Áudio (P2), Preferências (D1). Dispositivos físicos: NÃO IMPLEMENTADO | `Main.qml:733-795`; `docs/BASE_UI_MAP.md` (CPAL/PipeWire ausentes) |
| NT-03 | Extensões: Hub, "uma aba Plugins" | EXISTE COM CONFLITO | Plugins (D2) e Gideon Hub (P6) são duas entradas para o mesmo catálogo (AC-07) | `Main.qml:596, 601` |
| NT-04 | Permissões | EXISTE SEM CONTEÚDO | Página P4 só tem texto. Dados existem no Core (`hub.entries.permissions`, `permissions_approved`, `skills.permissions_ok`, `connections.granted_scopes`) mas não há lista (AC-03) | `Main.qml:840-843`; `bridge.py` (`hubEntries`, `connectionsItems`, `skillsItems`) |
| NT-05 | Diagnóstico | EXISTE (mínimo) | P5 com motores e estado do sistema. Sem log, sem eventos (NF-18) | `Main.qml:844-867` |
| NT-06 | Preferências: frase de wake certificada | EXISTE | D1-C2/C3 e P1-C1; só `dev_qualified` é selecionável; "Okay Gideon" fica bloqueada | `Main.qml:180-181, 746-754`; `docs/BASE_UI_MAP.md` |
| NT-07 | Preferências: sensibilidade limitada | NÃO IMPLEMENTADO | Texto "CPU e sensibilidade fixas" (D1-T1). Sem campo no Core | `Main.qml:189`; `bridge.py` (sem `sensitivity`) |
| NT-08 | Preferências: dispositivo de entrada | NÃO IMPLEMENTADO | Só "PCM virtual" (P1-T3). Adaptador físico ausente | `Main.qml:763`; `docs/BASE_UI_MAP.md` |
| NT-09 | Preferências: dispositivo de saída | NÃO IMPLEMENTADO | Só "saída virtual" (P2-T1). Adaptador físico ausente | `Main.qml:776` |
| NT-10 | Feedback audível | EXISTE | D1-C4 e D1-C9, habilitado só com voz disponível | `Main.qml:184, 193`; `bridge.py:1687-1690` |
| NT-11 | Feedback visual | EXISTE | D1-C5, P3-C8 (salvo pelo Core) | `Main.qml:185, 835` |
| NT-12 | Voz da Base | EXISTE SÓ COMO TEXTO | Voz fixa (Pocket TTS · Alba) em P2-T1. Escolha de voz NÃO IMPLEMENTADA (comparações Piper e Kokoro pendentes) | `Main.qml:776`; `docs/BASE_UI_MAP.md` |
| NT-13 | Idioma | NÃO IMPLEMENTADO (fixo) | Inglês fixo no pack (`D1-I2`, "inglês"). A língua da UI é PT fixa e distinta do ASR e TTS, conforme `docs/BASE_UI_MAP.md` | `bridge.py:1971` (`language: "en"`, `src/core.rs`) |
| NT-14 | Volume | EXISTE | Ganho da saída virtual 0 a 100 (P2-C1..C3, D1-C6..C7) | `Main.qml:788, 793, 187` |
| NT-15 | Performance | NÃO IMPLEMENTADO | Texto "CPU fixa" (D1-T1). Sem controle | `Main.qml:189` |
| NT-16 | Iniciar no login | NÃO IMPLEMENTADO | Texto "login automático indisponíveis" (D1-T1). Autostart não existe (`docs/B4.md`) | `Main.qml:189`; `docs/B4.md` |
| NT-17 | Privacidade e retenção | PARCIAL | Só texto fixo ("sem histórico persistente", "em memória"); sem controle de retenção | `Main.qml:695, 189` |
| NT-18 | HUD: Idle ("Em espera") | EXISTE | HD-05 | `Main.qml:110, 647` |
| NT-19 | HUD: WakeDetected | NÃO EXPOSTO | Não há estado no protocolo; é ocorrência interna (`docs/BASE_UI_MAP.md`) | `docs/BASE_UI_MAP.md` (tabela de estados) |
| NT-20 | HUD: Listening | EXISTE | "Ouvindo" para `capturing` | `Main.qml:110` |
| NT-21 | HUD: Transcribing | EXISTE | "Transcrevendo" | `Main.qml:110` |
| NT-22 | HUD: Thinking | PARCIAL | Só dentro de Conversa e Agente ("Aguardando resposta", "Pensando"). O HUD global não tem estado | `Main.qml:1418, 1451`; `bridge.py:155` |
| NT-23 | HUD: Acting | EXISTE | "Executando" (estado `executing`, recibo do Core) | `Main.qml:110` |
| NT-24 | HUD: Speaking | EXISTE | "Respondendo" | `Main.qml:110` |
| NT-25 | HUD: Error | PARCIAL | Sem estado próprio. "Erro" só como rótulo de fallback (`Main.qml:647`); erros aparecem em textos | `Main.qml:647` |
| NT-26 | HUD: AwaitingConfirmation | NÃO CONSTRUÍDO DE PROPÓSITO (voz) | "Confirm não tem backend ativo" (`docs/BASE_UI_MAP.md`). Aprovações existem em Conversa (P7-C4, C5) e Skills (P10-C19, C20) | `docs/BASE_UI_MAP.md` |
| NT-27 | HUD: transcrição visível | EXISTE | P0-I9 | `Main.qml:1563` |
| NT-28 | HUD: ferramenta em execução | PARCIAL | Só na Conversa e no Agente (P7-I7, P7-I15). Não no HUD | `Main.qml:1500, 1549` |
| NT-29 | HUD: progresso | PARCIAL | Só barras indeterminadas em Skills, Modelos e Conexões. Sem progresso de fala ou captura | `Main.qml:968, 1135, 1251`; NF-14 |
| NT-30 | HUD: aviso de microfone ativo | NÃO IMPLEMENTADO | Só o indicador simulado do plugin C4 (P9-I1) | `Main.qml:912`; `docs/C4.md` |
| NT-31 | HUD: sucesso ou falha verificados | EXISTE | Recibo verificado em cor diferente (P0-I10) | `Main.qml:1565`; `bridge.py:1809` |
| NT-32 | HUD: botão Cancelar | EXISTE | HD-06 | `Main.qml:651` |
| NT-33 | Um estado principal em destaque | EXISTE | Título da página e estado em pílula (HD-01, HD-05) | `Main.qml:631, 635-649` |
| NT-34 | Aprovação mostra alvo, efeito e risco | PARCIAL | Alvo sim (ferramenta e argumentos). Risco só em conexão e agente. Efeito não descrito (AC-14) | `Main.qml:1500-1505, 1502, 1549` |
| NT-35 | Usuário interrompe tarefa e áudio a qualquer momento | EXISTE | HD-06, P7-C3, P7-C7, P10-C21, D2-C1 | `Main.qml:651, 1473, 1538, 1110, 216` |
| NT-36 | Modo básico legível, avançado revelado aos poucos | NÃO IMPLEMENTADO | Não há divulgação progressiva (AC-15) | `grep "Avançad"` vazio em `app/Main.qml` |
| NT-37 | Onboarding | NÃO IMPLEMENTADO | Nenhum fluxo de primeira execução (grep zero) | `app/Main.qml`, `app/bridge.py` |
| NT-38 | Estado vazio | EXISTE | P6-I3, P7-T2, P8-I6, P10-I9, P11-I4 | `Main.qml:898-901, 1430, 1158, 979, 1270` |
| NT-39 | Recuperação de erro | PARCIAL | Modo seguro com "Preservar arquivo e restaurar padrões" (D1-C1). Reconexão automática. Sem ação de reinício do Core (NF-22) | `Main.qml:175`; `bridge.py:1138-1152` |
| NT-40 | Diagnóstico simples | EXISTE | P5 | `Main.qml:844-867` |
| NT-41 | Acessibilidade e foco | PARCIAL | Nomes de acessibilidade em 142 linhas do QML. Foco de teclado e HiDPI não verificados nesta leitura | `grep -c "Accessible.name" app/Main.qml` = 142 |
| NT-42 | Efeitos degradam em máquina fraca; Wayland | NÃO VERIFICADO NESTA LEITURA | Orbe em raster por software, sem shader (`app/visual.py`). Wayland real pendente (`docs/B4.md`) | `app/visual.py:1` |
| NT-43 | Devices: microfone | NÃO IMPLEMENTADO (físico) | Só virtual (P1-T3) | `docs/BASE_UI_MAP.md` |
| NT-44 | Devices: alto-falante | NÃO IMPLEMENTADO (físico) | Só virtual (P2-T1) | `docs/BASE_UI_MAP.md` |
| NT-45 | Devices: câmera | SÓ SIMULADA, PARCIAL | Estado simulado (P9-C7). Opt-in e captura sem tela (NF-11) | `Main.qml:944-948`; `docs/C4.md` |
| NT-46 | Devices: tela | SÓ SIMULADA | Captura e árvore simuladas (P9-C1, P9-C3). Sem tela real | `Main.qml:944-948`; `docs/C4.md` |
| NT-47 | Skills | EXISTE | Página 10 (AVANÇADO) | `Main.qml:960-1126` |
| NT-48 | Connections | EXISTE | Página 11 (AVANÇADO) | `Main.qml:1243-1399` |
| NT-49 | LLM Models, só com plugin LLM | EXISTE | Página 8 aparece só com `modelsAvailable` (`Main.qml:599`). Motor LLM (D3) existe sem plugin (AC-09) | `Main.qml:599, 159` |
| NT-50 | Settings | EXISTE | Preferências (D1) | `Main.qml:161-202` |
| NT-51 | Sem página de download de modelos | CONFORME | Nenhuma tela de download | `app/Main.qml` |
| NT-52 | Troca de wake só por frase certificada do pacote | CONFORME | P1-C1 e D1-C3 | `Main.qml:746, 181` |
| NT-53 | Controles ausentes desabilitados e rotulados | PARCIAL | Muitos controles desabilitados com motivo. Exceções: Permissões vazia (AC-03) e aviso errado na Conversa (AC-01) | `Main.qml:1237, 840` |
| NT-54 | Memory | NÃO CONSTRUÍDO DE PROPÓSITO | Sem backend em `src/`, `app/` e `scripts/`. Backlog em `docs/sources/roadmap.md:58` | grep zero |
| NT-55 | Souls | NÃO CONSTRUÍDO DE PROPÓSITO | Idem | grep zero; `docs/sources/decisions.md:27` |
| NT-56 | Habits | NÃO CONSTRUÍDO DE PROPÓSITO | Idem | grep zero; `docs/sources/decisions.md:27` |
| NT-57 | Automations | NÃO CONSTRUÍDO DE PROPÓSITO | Sem backend. "Automações duráveis" no backlog | grep zero; `docs/sources/roadmap.md:58` |

---

## 8. Contagem por página

Contagem feita sobre as tabelas deste documento (cada linha de controle ou de informação conta uma vez). Controle = linha `Px-C` ou `Dx-C`. Informação dinâmica = linha `Px-I` ou `Dx-I`. Texto fixo = linha `Px-T` ou `Dx-T`. A seção 9 traz os totais.

<!--CONTAGEM-->

---

## 9. Resumo: páginas sobrecarregadas e páginas vazias

<!--RESUMO-->

---

## Apêndice A. Índice de slots e propriedades da ponte

<!--APENDICE-->
