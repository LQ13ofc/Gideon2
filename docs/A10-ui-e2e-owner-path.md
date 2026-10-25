# A10 — caminho do proprietário na UI instalada (E2E com microfone de laboratório)

Estado: REPRODUZIDO / DEFEITO DO CORE CORRIGIDO / DEMAIS PENDENTES.
Escopo: o caminho que o proprietário seguiu (ligar "Ouvir o microfone", reiniciar, escolher o
microfone, mudar a sensibilidade da frase) foi refeito em um pacote instalado, com uma raiz
privada e um perfil `e2e` novo. Nenhum dado do perfil `dono` foi lido para escrita nem alterado.
Não há microfone, alto-falante ou dispositivo físico do proprietário em nenhum passo de escrita.
Nenhum commit foi feito.

## Ambiente e método

- Pacote 9.9.9 gerado do HEAD (`scripts/build_package.py`) e instalado em `/home/lucas/GideonUiE2E`
  com `gideon-install`; perfil `e2e` criado pelo instalador. Depois, o pacote 9.9.8 (árvore de
  trabalho com a correção do Core, ver D1) foi aplicado com `gideon-install update`.
- Core iniciado pelo `gideon-launch` instalado, log em arquivo.
- Dispositivos virtuais criados por mim e descarregados ao fim: sink nulo `gideon_e2e_sink`,
  fonte `gideon_e2e_mic` (remap do monitor), e sink nulo `gideon_e2e_out` para a voz de saída do
  Core (assim a resposta de voz não toca nos alto-falantes e não volta ao microfone). Padrões
  do sistema (saída HDMI, entrada webcam) conferidos antes e depois: iguais.
- UI: o cliente instalado (`app/`, venv `ui/` do pacote) carregado em processo como em
  `app/main.py __main__`, em Wayland. Cliques e teclas são eventos enviados à própria janela
  (`QMouseEvent` / `QKeyEvent`), no mesmo modelo de `scripts/explore_ui.py`. Nada fora da janela.
  O seletor de microfone foi usado pelo teclado porque o popup é outra janela.
- Clipes: `/tmp/gideon-wake-lab/clips` (positivos "Hey Gideon", "open Brave", "what time is it";
  negativos "Hey Julian", "Gideon" sozinho), tocados com `pw-play --target gideon_e2e_sink`.
- Ruído real: o gravador de ruído de 22 min já em curso (`/tmp/gideon-wake-lab/real-noise/`,
  de outro agente) foi usado para os 60 s do webcam, em vez de abrir o microfone de novo.
  Mistura com voz em SNR 15 dB e 5 dB pelo script de mistura (SNR medido 15,00 e 5,00).

## Caminho do proprietário na UI (pacote 9.9.9, perfil novo)

| # | Passo | Resultado observado | Evidência |
|---|---|---|---|
| 1 | Abrir a UI com o Core | Conecta; Core em `idle`; ao abrir o Core, o replay de boot ocupa a fala por alguns segundos | `00-start.png` |
| 2 | Guia de primeira execução, passo 3 | Aparece só uma vez por raiz de Core (a marca "Introdução concluída" fica em `$XDG_CONFIG_HOME/gideon-app/<hash>`). Nas repetições do mesmo perfil ela não voltou: não é defeito, mas explica por que o proprietário não a vê de novo | `01`, `02` |
| 3 | Ligar "Ouvir o microfone" | Diálogo com o texto de consentimento; "Cancelar" tem o foco; "Ativar escuta" salva a preferência no Core | `03-consent.png`, `S4b-dispositivos-consent.png` |
| 4 | Aviso após consentir | "Será ativado ao reiniciar o Core. Enquanto isso, a entrada segue virtual." (passo 3) e "Escuta do microfone: aguardando reinício do Core" (Dispositivos) com "Reiniciar agora" habilitado | `04`, `07` |
| 5 | Reiniciar agora | Core volta em 13,6 s; escuta em `capturing`, `mic_active` verdadeiro; gravador lendo o padrão do sistema (webcam) | `08-after-restart.png` |
| 6 | Lista de microfones antes de atualizar | "Dispositivos ainda não consultados: use Atualizar lista"; o seletor mostra só "Padrão do sistema" | `09` antes do clique |
| 7 | Atualizar lista | Cinco opções, incluindo "GideonE2EMic"; a webcam aparece como "padrão do sistema" | `09a-after-refresh.png` |
| 8 | Escolher o microfone (teclado) | Core salva `audio_input_device=gideon_e2e_mic`; o gravador passou a `pw-record --target gideon_e2e_mic` sem reinício (conferido no processo) | `10-input-selected.png` |
| 9 | Voz e Wake: sensibilidade da frase | A primeira mudança é salva (1,00 para 1,05). As mudanças seguintes são recusadas pelo Core com `configuration_not_ready` e o controle volta ao valor salvo (ver U1). O cabeçalho mostra "Reinício necessário" | `12-sensitivity-1-5.png` |
| 10 | "Estado do wake" | Mostra "Falhou" (uma vez, sem motivo na tela; ver U3) | `12-sensitivity-1-5.png` |
| 11 | Clipes de fala após a mudança, sem reiniciar | Nenhum wake, nenhuma sessão, nenhum evento novo. O Core segue vivo nessa rodada | `driver.log`, S8 |

Divergência principal: o proprietário mudou a sensibilidade, a tela pediu reinício, e a escuta
ficou sem detectar até o reinício. Se a detecção chegasse nesse estado, o Core (pacote 9.9.9)
encerrava: ver D1.

## Reprodução do defeito do Core (pacote 9.9.9, sem a interface)

1. Core com escuta ligada, wake pronto. Mudança de sensibilidade pela operação
   `select_wake_phrases`: `configuration_status` passa a `restart_required`.
2. Um clipe "Hey Gideon open Brave" tocado no microfone virtual.
3. Resultado: o Core fez `panic` em `src/core.rs:455` (`Option::unwrap()` sobre `None`) e saiu.
   O launcher também saiu, e a UI fica com o Core offline. Duas vezes: na segunda, o clipe foi
   tocado e a detecção levou ao panic. Na primeira, o panic veio em período ocioso, sem clipe
   tocado por mim; a origem dessa detecção ociosa não foi isolada.

Causa: mudar a lista de frases (inclusive a sensibilidade) marca `RestartRequired`
(`src/storage.rs`, `changed_wake`). Com isso `audio_wake` não abre sessão, mas
`capture_packet` ainda fazia `self.session.as_ref().unwrap()` ao detectar a frase.

## Matriz no Core (pacote 9.9.8, com a correção), microfone virtual e ruído real

Arquivos: `/tmp/claude-1000/ui-e2e/matrix.json`, `/tmp/claude-1000/ui-e2e/matrix.log`.

| Linha | Condição | Core vivo | Wake | Transcrição | Comando | Observação |
|---|---|---|---|---|---|---|
| M0 | sensibilidade 1,30 sem reiniciar; clipe "open Brave" limpo | sim | não | "A Gideon open brave. A." (não ativou, sem sessão) | — | `restart_required` mantido; sem panic |
| M1 | reiniciar; sensibilidade 1,30; clipe limpo | sim | sim | "A Gideon open brave. A." | `command_rejected`, fala de saída | STT errou o "Hey" |
| M2 | sensibilidade 0,5 + reiniciar; clipe limpo | sim | sim | "Hey Gideon, open brave." | `command_success` | |
| M3 | sensibilidade 1,5 + reiniciar; clipe limpo | sim | sim | "A Gideon open brave. A." | `command_rejected`, fala de saída | |
| M4 | sensibilidade 1,0 + reiniciar; ruído real do webcam SNR 15 dB | sim | sim | "Hey Gideon, open brave." | `command_success` | |
| M5 | sensibilidade 1,0 + reiniciar; ruído real do webcam SNR 5 dB | sim | sim | "Gideon open brave" | `command_rejected`, fala de saída | |

Leitura: com o Core reiniciado, a frase ativa nas sensibilidades 0,5, 1,0, 1,3 e 1,5 e com ruído
real a SNR 15 e 5 dB. O STT transcreve, o comando é avaliado e a fala de saída toca. A
sensibilidade só vale após reiniciar (M0). Os comandos com `command_rejected` mostram que a
transcrição precisa estar limpa para o comando ser aceito. Os testes não medem falso disparo
com ruído sem fala: isso fica com o conjunto de ruído de 22 min de outro agente.

Troca de dispositivo no Core: escolher `default` e depois `gideon_e2e_mic` com a escuta ligada
não gerou eventos nem erro, e a captura seguiu em `capturing`.

## Defeitos

### D1 — corrigido: panic do Core na detecção com reinício pendente

- Sintoma: depois de mudar a frase ou a sensibilidade com a escuta ligada, a primeira detecção
  derrubava o Core (`panic` em `core.rs`), o launcher saía e a UI ficava offline. Com o perfil
  do proprietário sem Core ativo e sem eventos, isso é compatível com o que ele vê (hipótese, não
  provada: o log do launcher dele não foi guardado).
- Correção: `src/core.rs`, `capture_packet`: a detecção sem sessão é descartada com `return`,
  sem `unwrap`. Teste novo `detection_while_restart_is_pending_is_dropped_without_panic`.
- Verificação: `cargo test --lib` 159 passam; `cargo fmt --check` ok; `cargo clippy --all-targets
  -- -D warnings` ok; `scripts/test_bridge_protocol.py` 235 testes ok; pacote 9.9.8 instalado com
  a correção, matriz M0 a M5 sem derrubar o Core.

### U1 — não corrigido: mudanças de sensibilidade seguintes são recusadas

- O Core recusa toda mudança de frase depois da primeira, enquanto `restart_required` durar
  (`configuration_not_ready`). O mapeamento da UI (`app/bridge.py`, `CODE_MESSAGES`) para esse
  código diz "reinicie o Gideon ou recupere a configuração", que não é o conselho certo: basta
  reiniciar o Core. Não vi essa mensagem na tela; vi o controle voltar ao valor salvo (1,05).
- Sugestão: (a) desabilitar o controle com a mensagem "reinicie o Core para mudar de novo", ou
  (b) aceitar as mudanças e aplicar no reinício. A escolha é de produto. Não mexi em
  `CfgVoz.qml` nem no texto da UI sem essa decisão.

### U2 — não corrigido: lista de microfones só aparece depois de "Atualizar lista"

- A lista começa como "Dispositivos ainda não consultados". O proprietário tem a entrada em
  "Padrão do sistema" (webcam). Sem o clique, ele nunca vê o microfone físico.
- Sugestão: consultar `audio_devices` ao abrir a página Dispositivos. `CfgDispositivos.qml` está
  sendo editado por outro agente: não mexi.

### U3 — não corrigido, não reproduzido no Core: "Estado do wake: Falhou"

- Na rodada da UI, depois das mudanças de sensibilidade, o Core emitiu `wake_failed` (origem
  `speech`) e a tela mostrou "Falhou" sem motivo. Os eventos vivem só na memória, e o log de
  auditoria guarda apenas o número de sequência (`storage.rs`, `audit`), então o motivo não ficou.
- O gatilho exato não foi isolado: a troca de dispositivo sozinha e uma mudança de sensibilidade
  seguida de clipe não reproduziram. A fonte mais provável é a saída do worker de wake
  (`src/live.rs`, leitor de stdout enviando `Err`). Sugestão: registrar o motivo do worker.

### U4 — observação: a auditoria não guarda eventos

- `audit.log` só tem `{"version":1,"sequence":N}`. Sem Core rodando, o perfil não mostra nada.
  Isso explica por que o proprietário vê "nenhum evento" em qualquer falha. Não é a causa do
  problema, mas precisa de decisão se a auditoria deve guardar os eventos.

### U5 — observação: "open brave" não abre o Brave

Estado (A11): corrigido com a preferência `real_actions` (consentimento em Privacidade). Com ela ligada, "open brave"
abre o Brave de verdade e o recibo só sai com processo novo observado; comprovado ao vivo em docs/A11-real-actions-test.md.
Desligada, o comportamento de sandbox continua o mesmo, como descrito abaixo.

- O comando roda `scripts/command_worker.py` em sandbox, que verifica um processo simulado. A
  UI mostra "Comando concluído com efeito verificado" e "Processo do app verificado no sandbox:
  com.brave.Browser.desktop". Nenhum Brave foi aberto neste PC. Isso pode induzir o proprietário
  a achar que o aplicativo abriu.

## Sequência em que a experiência do proprietário diverge

1. Liga "Ouvir o microfone" e reinicia: funciona (escuta ativa em `capturing`).
2. Não atualiza a lista: só vê "Padrão do sistema" (webcam). U2.
3. Muda a sensibilidade: a tela pede reinício, e só a primeira mudança é salva. U1.
4. Sem reinício, nada é detectado. Se a detecção ocorresse, o Core caía (D1, corrigido no 9.9.8).
5. Sem Core ativo, o perfil não tem eventos (U4) e a UI só mostra offline ou "Falhou" (U3).

## Limites

- Microfone real do proprietário não foi usado. O teste usou o microfone virtual com ruído real
  do webcam misturado a SNR fixo. O ruído ambiente sem fala não foi testado aqui.
- O passo de mouse no popup do seletor não foi testado (popup é outra janela); o teclado foi.
- A sensibilidade foi conferida por teclado no `Slider` (passo 0,05), com saltos de 0,6 s.

## Arquivos

- Capturas: `/tmp/claude-1000/ui-e2e/` (`00-start.png` a `14-end.png`, `S4b-dispositivos-consent.png`,
  `09a-after-refresh.png`). Relatório: `/tmp/claude-1000/ui-e2e/report.json`; log do driver:
  `/tmp/claude-1000/ui-e2e/driver.log`; log do Qt: `/tmp/claude-1000/ui-e2e/qt-stderr.log`.
- Matriz: `/tmp/claude-1000/ui-e2e/matrix.json`, `/tmp/claude-1000/ui-e2e/matrix.log`.
- Mistura de ruído: `/tmp/claude-1000/ui-e2e/mix/webcam-snr15.wav`, `webcam-snr5.wav`.
- Correção e teste: `src/core.rs` (`capture_packet`, teste `detection_while_restart_is_pending_is_dropped_without_panic`).
- Limpeza: sinks e fonte virtuais descarregados, raiz `/home/lucas/GideonUiE2E` apagada, entradas
  de configuração da UI criadas pelo teste removidas. O `record_long.sh` de outro agente não foi
  tocado.
