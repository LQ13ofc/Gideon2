# Validação humana — checklist consolidado do dono

Data de referência: 2026-10-23. Repo: `/home/lucas/Documentos/Gideon/base`.
Este documento reúne (A) o que já está AUTO_VERIFIED no ambiente virtual, com referências a `docs/evidence/*.json`,
(B) o que só o dono pode validar com hardware, contas e sessão reais (AWAITING_HUMAN_VALIDATION), (C) higiene de
segurança pendente e (D) decisões que dependem do dono.

Regras desta rodada:
- Nenhuma chave, token ou segredo aparece aqui. Quando um item citar um provedor, cite só o nome.
- Testes com contas reais, microfone, alto-falantes ou sessão pessoal só com consentimento explícito do dono, na hora do teste.
- Usar instalação e perfis de teste fora do host pessoal (ex.: `~/GideonTeste`), nunca o perfil principal do dia a dia.
- Nada disto foi validado fisicamente. Todas as evidências do pacote têm `physical_validation: NOT_PERFORMED`.

---

## A. Status AUTO_VERIFIED (ambiente virtual)

Caminhos de evidência são relativos a `docs/evidence/`. Todas as linhas passaram em sandbox, com Core real, servidores
falsos em loopback, áudio/PCM virtual e Qt offscreen. O gate de integração E4 roda contra o PACOTE instalado.

### S1 — Núcleo de voz (A0–A5)

| Etapa | Escopo verificado | Resultado | Evidência | Limites honestos |
|---|---|---|---|---|
| A0 Runtime/IPC | Daemon headless, socket JSON-lines, sessões, cancelamento, shutdown, perfil isolado | 32 aprovados, 0 falhas. CPU ociosa 0,0%; RSS ocioso ~3,1 MiB | `a0.json`; `a0-selectable-regression.json` | Sem dispositivo de áudio; wake só virtual (produção recusa wake virtual) |
| A1 Wake word | "Hey Gideon" (DEV) e "Okay" (candidato) em corpus sintético | Hey: `PASS_DEV_ONLY`, recall 73/76, 0 falsos disparos em 320 negativos. Okay: `FAILED`. Integração 44/0 | `a1-selectable-hey.json`; `a1-selectable-okay.json`; `a1-quality.json`; `a1-selectable-integration.json` | Corpus sintético DEV, sem holdout independente; `distribution_certified: false`; sem microfone real |
| A2 VAD | Detecção de fala nativa em namespace bwrap | 33/0 | `a2.json` | Sem dispositivos; áudio autorizado PCM→Core |
| A3 STT | Transcrição nativa, sessão, revisão | 67/0 | `a3-integration.json` | Intermitências A1/A3 não se repetiram; causa não resolvida |
| A4 Comandos | Wake→STT→comando determinístico com sandbox | 138/0 | `a4-integration.json` | Worker de comandos usa `/usr/bin/python3` do host |
| A5 TTS, encerramento, soak | TTS virtual, shutdown limpo, soak | Integração 93/0; shutdown 2/0; soak 8/0 | `a5-integration.json`; `a5-shutdown.json`; `a5-soak.json` | Sem alto-falante real; sem AEC/barge-in |

### S2 — Base usável, pacote e UI (B1–B4)

| Etapa | Escopo verificado | Resultado | Evidência | Limites honestos |
|---|---|---|---|---|
| B1 UI e S1 nativo | Qt conectada ao Core, S1 nativo, auditoria | UI 32/0; auditoria 0 falhas | `b1-s1-regression.json`; `b1-ui.json`; `base-audit.json` | Qt offscreen |
| B2 Preferências, modo seguro, pacote de voz | Preferências, modo seguro, feedback | 31/0; 96/0; 36/0; 39/0 | `b2-preferences.json`; `b2-safe-mode.json`; `b2-pack.json`; `b2-feedback.json` | Sem áudio físico |
| B3 Hub de plugins | Catálogo, permissões, staging, ciclo instalar/reverter/remover | 69/0; 64/0; 76/0; 99/0 | `b3-catalog.json`; `b3-permissions.json`; `b3-import.json`; `b3-lifecycle.json` | Publisher não autenticado |
| B4 Pacote e update | Pacote relocável (B4.1); update/rollback com perfis (B4.2); gate final S2 | Pacote 67/0; update/rollback 129/0; S2 final 223/0 | `b4-package.json`; `b4-update.json`; `s2-final.json`; `ui-reference.json` | Sem assinatura, canal de update, autostart, Flatpak/portal; KDE/Wayland real não validados |

### S3 — Plugins, LLM, agente e percepção (C0–C4)

| Etapa | Escopo verificado | Resultado | Evidência | Limites honestos |
|---|---|---|---|---|
| C0 Runtime de plugins | Sandbox bwrap, capabilities, ativar/revogar/reaprovar, quarentena | 120/0 no gate (`c0-plugins.json`) | `c0-plugins.json` | Sem seccomp; exec de binários de /usr permitido |
| C1 Motor LLM (opcional) | Cofre de chaves no Core, broker HTTP com allowlist, consentimento de nuvem | 109/0 (1 ignorado). Ao vivo: Google PASSED; Mistral PASSED (custom); OpenRouter EXTERNAL_BLOCKED (403); OpenCode EXTERNAL_BLOCKED (402) | `c1-llm.json` | Plugin nunca recebe resultado de ferramenta |
| C2 Model Manager (só no plugin) | Provedores local/ollama em loopback, último bom conhecido, fallback | 105/0; ao vivo Google e Mistral PASSED | `c2-models.json` | llama.cpp e GGUF NÃO baixados nem testados (B4 abaixo) |
| C3 Runtime do agente | Ciclo observar-planejar-agir-verificar, limites, aprovação por proposta | 131/0 (4 ignorados) | `c3-agent.json` | LLM roteirizado, não LLM real em loop |
| C4 Percepção e ação | Captura, árvore de acessibilidade, clique/digitação, áudio, microfone, câmera, display | 181/0 (3 ignorados) | `c4.json` | SOMENTE backend sintético ("SINTÉTICO — sem hardware real"); display `UNSUPPORTED` |

### S4 — Skills (D1–D4)

| Etapa | Escopo verificado | Resultado | Evidência | Limites honestos |
|---|---|---|---|---|
| D1–D2 Manifest/DSL e executor | Validador, executor, undo, cancelamento, revogação | Core 175/0 | `s4.json` (gate `s4-core`) | Só skills de teste (fixtures) |
| D3 Criador por LLM | Rascunho pelo plugin, validação, simulação; autoaprovação negada | Gate final 72/0 | `s4.json` (gate `s4-final`) | LLM real NÃO gerou skill (roteirizado) |
| D4 Compartilhamento `.gskill` | Exportação sem segredos, prévia, adulteração e escalada negadas | 151/0 | `s4.json` (gate `s4-share`) | Sem assinatura (integridade só por sha256) |

### S5 — Conectores e integração (E1–E4)

| Etapa | Escopo verificado | Resultado | Evidência | Limites honestos |
|---|---|---|---|---|
| E1 + E2.1 Gerenciador e GitHub | Contas, consentimento por escopo, ledger com CAS, cofre, orçamento de rede | 119/0 (2 ignorados) | `e1-connections.json` | Servidor FALSO em loopback |
| E2.2 Google | Gmail, Calendar, Drive; reautenticação se escopo muda | 111/0 (4 ignorados) | `e22-google.json` | Servidor falso; quota só do servidor falso |
| E2.3 Home Assistant | Estados, serviços, token colado no cofre; serviços perigosos com confirmação forte | 101/0 (4 ignorados) | `e23-ha.json` | Servidor falso; `garage_door.*` fora da lista de perigosos (decisão D1) |
| E2.4 MCP | Servidor MCP falso em sandbox sem rede; descoberta, re-aprovação de ferramenta | 188/0 (4 ignorados) | `e24-mcp.json` | Servidor falso; saída de ferramenta tratada como dado |
| E3 Registro de capacidades | Rota API antes de visual; fallback visual desligado por padrão | 129/0 (3 ignorados) | `e3-registry.json` | Só `create_issue` tem rota visual |
| E4 Integração total (pacote) | Pacote completo instalado; smoke; update v1→v2→rollback; kill -9; perfis; offline; demo E2E; Qt Skills/Conexões/Rotas; higiene | **288/0** (3 ignorados, todos fora do ambiente), 603 s, uma execução completa | `e4-integration.json` | Ver seção A.1 |

#### A.1 Gate E4 (`scripts/verify_e4_integration.py`), pontos que o dono precisa conhecer

- Tudo o que foi exercitado rodou com binários do PACOTE (`gideon-install`, `gideon-launch`, `gideon-core`, `gideon-base`, `gideon-verify`, app Qt e venvs do pacote), em sandbox bwrap sem repositório, sem uv e sem rede exceto o loopback dos fakes.
- Provado: S1 por PCM virtual (wake replay, STT, comando, TTS virtual) em cada fase; install v1; update v1→v2 recusado com Core ativo (`profile_active`, exit 3), lock preso (`locked`, exit 6) e aplicado depois; rollback; `kill -9` do Core em duas ocasiões sem processo órfão e sem efeito duplicado; ledgers `skills.json`, `connections.json`, `registry.json`, `hub-installed.json`, `secrets.json` byte-idênticos, `plugin-state.json` com o mesmo conjunto de plugins habilitados; perfis alice/bob isolados; offline (somente `lo`; chamada de modelo remoto falha com `network_unavailable` em menos de 50 s); demo com Hub, LLM roteirizado (tool call, rascunho de skill, issue no GitHub falso com aprovação); Qt Conexões, Rotas e Skills a partir do pacote; higiene (sem padrão de chave em 27.129 arquivos, sem chave de teste no binário, nenhum flag de teste no argv padrão, modos 0600/0700, nada gravável por outros).
- Idle (10 s): Core 0,0% de um núcleo, árvore 0,0%; RSS do Core ~6–7 MiB.
- Produção sem flags de teste: `gideon-core` sem `--connections-fake`, `--agent-synthetic` ou `--hub-catalog` não expõe ferramentas sintéticas, provedores falsos nem serviço sintético; cada conexão real retorna `real_backend_unsupported` sem contatar nada.
- Pacotes foram construídos a partir de árvore COM alterações não commitadas (`package_dirty_flag: true`, ver D2). Commit e reconstrução são necessários antes de qualquer identidade de release.
- Skips documentados (não implementáveis aqui): contas reais GitHub/Google/Home Assistant; áudio físico, KDE Wayland, portais, Flatpak; binário llama.cpp e GGUF reais.

---

## B. AWAITING_HUMAN_VALIDATION — itens para o dono

Ordem sugerida: B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8 → B9. Para cada item, reportar exatamente o que for pedido em "Reportar".

Pré-requisito comum: construir o pacote a partir de um commit limpo e instalá-lo fora do host pessoal:
```
cd /home/lucas/Documentos/Gideon/base
mkdir -p ~/GideonPkgs                                           # OUT_DIR deve existir
python3 scripts/build_package.py ~/GideonPkgs --version 0.4.0
PKG=~/GideonPkgs/gideon-base-0.4.0
python3 -I -B $PKG/bin/gideon-install --install-root ~/GideonTeste install $PKG
python3 -I -B ~/GideonTeste/current/bin/gideon-install --install-root ~/GideonTeste profile create dono
~/GideonTeste/current/bin/gideon-launch --install-root ~/GideonTeste dono
```
Observação: o Core de hoje NÃO tem caminho de microfone vivo. Wake e STT rodam por replay ou PCM virtual; áudio físico só existe
depois que o adaptador real for implementado. O dono valida B1 só quando o adaptador existir.

### B1 — Wake, STT e TTS com microfone e alto-falantes físicos

- [ ] **"Hey Gideon"** (status DEV; `PASS_DEV_ONLY` só no corpus sintético). Sala silenciosa, 20 tentativas; com ruído ou TV, outras 20.
  - Esperado: sem disparo sem a frase; resultado registrado. Não prometer ao usuário final antes deste item passar.
  - Reportar: acertos x 20, falsos disparos, distância, modelos de microfone e alto-falante, ambiente.
- [ ] **"Okay"** (status `FAILED` na baseline). Mesmo roteiro, só para registro.
  - Reportar: acertos x 20, falsos disparos, condições.
- [ ] **STT com voz real**: dizer "Hey Gideon, open brave" (mesma frase do fixture A4), volume normal.
  - Esperado: transcrição exibida corresponde ao dito; ação só dentro da tabela de comandos.
  - Reportar: transcrição, se o comando executou, latência percebida.
- [ ] **TTS audível**: ouvir a resposta pelo alto-falante.
  - Esperado: fala inteligível, sem cortes, volume configurado respeitado.
  - Reportar: inteligibilidade, cortes, volume.
- [ ] **Eco e barge-in** (não validados): Gideon falando com música no mesmo alto-falante; depois interromper a fala com a voz.
  - Esperado: sem auto-disparo por eco; fala para e escuta o novo comando.
  - Reportar: falsos disparos por eco, tempo até parar.
- [ ] **Hotplug e PipeWire** (não validados): desconectar e reconectar o microfone USB durante a escuta; trocar a saída de áudio no PipeWire.
  - Esperado: estado claro na UI e recuperação sem reiniciar o Core; TTS segue na saída nova.
  - Reportar: estado exibido, se recuperou, onde a fala saiu.

### B2 — KDE Wayland: UI e portais

- [ ] Abrir a UI do pacote instalado (`~/GideonTeste/current/bin/gideon-app`) em sessão Plasma Wayland real.
  - Esperado: janela, tema, idioma PT, teclado e estados corretos; sem erro no terminal.
  - Reportar: captura de tela, erros do terminal, foco.
- [ ] Portais de captura de tela, entrada e áudio: hoje NENHUM backend real existe. Esperado: "não suportado" exibido na UI, nenhuma ação real.
  - Reportar: mensagem exibida para cada portal.

### B3 — Flatpak (decisão adiada)

- [ ] Decidir se Flatpak entra no escopo (portais de áudio/background e bwrap aninhado dos workers, ver B4.2).
  - Esperado: nenhuma validação agora; só testar se o Flatpak for construído.
  - Reportar: decisão (sim/não) e motivo.

### B4 — Modelo LLM local (llama.cpp e GGUF): EXIGE AUTORIZAÇÃO DO DONO

- [ ] **Autorizar ou recusar o download** do binário llama.cpp e de um GGUF pequeno. Informar origem, tamanho e hash antes de qualquer download. Nenhum download sem resposta explícita.
- [ ] Escolher o modelo local (recomendado ou personalizado) pela aba "Modelos LLM" da UI.
- [ ] Certificar o modelo: `selftest` e matriz de recursos pela UI.
  - Esperado: só vira "Certificado" com evidência real; antes disso continua `candidate`.
  - Reportar: modelo, hardware (CPU, RAM, GPU), resultado do selftest, latência e recursos suportados.
- [ ] **Chaves remotas próprias** (opcional): criar chaves nos provedores pelo painel deles, cadastrar pela UI "Motor LLM" (campo mascarado, cofre do Core), ativar consentimento de nuvem só se quiser enviar conteúdo.
  - Ao vivo, com arquivo de chaves 0600 FORA do repositório: `GIDEON_LIVE_KEYS_FILE=<arquivo> python3 scripts/verify_c2_live.py`.
  - Reportar: resultado e código HTTP por provedor. Não reportar chave nem corpo de resposta.

### B5 — Plugins de percepção e ação com backends reais (todos NÃO suportados hoje)

- [ ] Captura de tela real por portal (`screen_observe`). Esperado hoje: `real_backend: unsupported`, `reason: needs_human_validation`.
- [ ] Controle de entrada real (`computer_control`, via libei/portal). Esperado: nenhum clique real; mensagem de não suportado.
- [ ] Roteamento de áudio real (`audio_advanced`). Esperado: não suportado; PipeWire intocado.
- [ ] Microfone avançado (`mic_advanced`) e câmera (`camera_gesture`). Esperado: não suportado; indicador de privacidade nunca ligado sem ação do dono.
- [ ] Manipulação de display (`display_manipulate`). Esperado: `UNSUPPORTED` por inteiro.
  - Reportar: mensagens exibidas; reportar qualquer item que aparecer como ativo.

### B6 — Criação e compartilhamento de skills entre dois usuários reais

- [ ] Usuário A cria uma skill (manual ou pelo criador), valida, simula, aprova e exporta (`skill_export`, `.gskill` em `~/GideonTeste/.../data/skill-exports/`).
- [ ] Transferir o `.gskill` ao usuário B por canal do dono (não por este chat).
- [ ] Usuário B importa (`skill_import`), revisa a prévia, confirma (entra como rascunho), re-aprova, simula e executa.
  - Esperado: pacote sem segredos nem caminhos pessoais; publisher "não verificado"; `signature: null`; nenhuma permissão concedida automaticamente.
  - Reportar: achados da prévia, se B aprovou permissões, se a execução ficou dentro do mundo de teste.

### B7 — Contas reais GitHub, Google e Home Assistant (SOMENTE com consentimento explícito)

- [ ] Confirmar por escrito, no momento do teste, que o dono autoriza cada conta.
- [ ] GitHub: conta de teste com o menor escopo (`repo:read`). Esperado: escopos concedidos batem com os pedidos; `account_ref` correto; revogar remove o token do cofre. Não criar issue pública sem aprovação explícita.
- [ ] Google: conta de teste, leitura de agenda somente. Não enviar e-mail nem apagar nada nesta rodada.
- [ ] Home Assistant: token colado no campo oculto da UI. Testar `ha_get_state` e um serviço não perigoso. Confirmar que `lock.unlock` pede confirmação forte.
  - Reportar: status, escopos, resultado de revogação. Nunca colar token no chat.

### B8 — Desempenho: ocioso e durante jogo

- [ ] Ocioso por 30 minutos com Core e UI abertos: `ps -o pid,%cpu,rss -C gideon-base`.
  - Esperado: CPU ociosa abaixo de 1% e RSS abaixo de 32 MiB (E4 mediu 0,0% e ~6–7 MiB em sandbox de 10 s).
  - Reportar: valores medidos.
- [ ] Jogo em tela cheia com wake ativo. Esperado: sem queda perceptível de quadros e sem atraso anormal de voz. Nunca medido.
  - Reportar: FPS antes e depois, latência de resposta, máquina e placa de vídeo.

### B9 — Instalação, update, rollback e recuperação em disco real

- [ ] Instalar o pacote oficial em `~/GideonTeste` e criar o perfil `dono` (comandos do pré-requisito). Reportar a saída e se o S1 passou.
- [ ] Update para a versão 2 com o perfil preservado. Esperado: recusado com o Core rodando (`profile_active`, exit 3); aceito com o Core parado.
  - `python3 -I -B ~/GideonTeste/current/bin/gideon-install --install-root ~/GideonTeste update <PKG_v2>`
- [ ] Rollback para a versão 1: `... --install-root ~/GideonTeste rollback`. Esperado: preferências, plugins e skills preservados; S1 funciona.
- [ ] `kill -9` do Core durante uma sessão de voz (instância de teste). Esperado: ao subir de novo, socket recuperado, snapshot ocioso, nenhum efeito duplicado.
- [ ] `kill -9` do `gideon-install` no meio de um update (instância de teste), depois `... repair`. Esperado: `needs_repair` (exit 5) e `repair` restaura estado válido.
- [ ] Matar um plugin ativo (ex.: `llm_engine`) durante uma resposta. Esperado: `failed` com código; Core segue; S1 funciona.
  - Reportar: códigos de saída, saída de `list` após cada passo, estado antes e depois.

---

## C. Higiene de segurança (fazer antes de qualquer outra coisa)

- [ ] **Revogar as chaves colocadas no chat** nos painéis de OpenCode, OpenRouter, Google, Mistral, ZenMux e DeepSeek. Depois de revogar, confirmar que cada provedor mostra a chave como inválida.
- [ ] **Apagar o arquivo temporário de chaves** fora do repositório, usado nos testes ao vivo do C1/C2: `/tmp/claude-1000/-home-lucas-Documentos-Gideon/5fd6f0b3-714b-4e76-9110-b1db87d89aef/scratchpad/k/keys.json` e `.../k/live.json`. Apagar só depois de revogar.
- [ ] **Limpar o banco do claude-mem**: pode conter prompts colados e chaves. Inspecionar e apagar os registros sensíveis. Não exportar nem copiar esse banco.
- [ ] **Conferir os provedores** por uso anormal ou cobranças inesperadas após a revogação.
- [ ] **Varredura de segredos no repositório** antes de qualquer commit ou push. Nenhum push autorizado.
- [ ] **Chaves novas**: criar somente no painel do provedor e cadastrar pela UI "Motor LLM". Nunca no chat nem em arquivo versionado.

---

## D. Decisões do dono

- [ ] **D1 — `garage_door.*` no Home Assistant**: deve continuar perigoso (exige confirmação forte, escopo `services.dangerous`)? O código JÁ trata `garage_door.*` como perigoso (`src/connections.rs:678-679`, função `dangerous_service`; teste `dangerous_services_are_destructive_and_need_their_scope` em `src/connections.rs:4475` com `("garage_door", "open")` em :4494). A lista atual no código: `lock.unlock`, `lock.open`, `cover.open_cover`, `cover.close_cover`, `alarm_control_panel.*` e `garage_door.*`. Decisão do dono pendente: manter (estado atual do código) ou remover `garage_door.*` da lista, ajustando o teste. Até a decisão, o código não muda. (Atualizado no WP8, DOCS-04; ver `docs/WP8.md`.)
- [ ] **D2 — Commit e identidade do pacote**: o E4 foi executado com árvore não commitada (`package_dirty_flag: true`; ver `e4-integration.json`, campo `identity`). Para release, commitar e reconstruir, depois repetir o gate do pacote.
- [ ] **D3 — Flatpak**: entra ou não no escopo (B3).
- [ ] **D4 — Assinatura, canal de update e autostart** de pacote: adiados; decidir antes de distribuir.
- [ ] **D5 — Worker de comandos**: hoje usa `/usr/bin/python3` do host. Decidir se entra no runtime empacotado.

---

Status: E4 AUTO_VERIFIED no ambiente virtual (288/0, 3 skips documentados). Itens B1–B9 AWAITING_HUMAN_VALIDATION.

READY_FOR_HUMAN_VALIDATION


## Adendo 2026-10-24 — novos itens para a rodada humana
- [ ] **Áudio ao vivo** (Configurações › Dispositivos › "Ouvir o microfone", confirmar o diálogo, "Reiniciar agora"; só depois de ler docs/A6-live-audio.md): dizer "Hey Gideon" ao microfone real; conferir o indicador "Microfone ativo", troca de dispositivo em Configurações › Dispositivos, TTS no alto-falante escolhido. Reportar acertos, falsos disparos e latência.
- [ ] **Sensibilidade do wake** (0,5 / 1,0 / 1,5): comparar acertos e falsos disparos em sala silenciosa e com ruído.
- [ ] **Iniciar no login**: ligar em Configurações › Geral, encerrar a sessão e entrar de novo; conferir `~/.config/autostart/gideon.desktop` e desligar.
- [ ] **Primeira execução guiada**, **perfis de configurações**, **temas** (8 presets) e **atalhos** (Ctrl+K, Ctrl+1..5, Esc) no Plasma Wayland real.
- [ ] **Reiniciar Core** pela interface (Diagnóstico › Recuperação) com o pacote instalado.
