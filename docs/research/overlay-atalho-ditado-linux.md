# Overlay, atalho global, ditado, lembretes, busca de arquivos e "perguntar sobre a tela" no Linux (KDE Plasma 6 Wayland)

Pesquisa somente leitura feita em outubro de 2026, com busca web e leitura pontual de páginas públicas. Nenhum código foi alterado, nada foi instalado e nenhum teste foi feito em um desktop real. Onde a fonte é fraca (README de projeto, issue de GitHub, post de fórum, resultado de busca não aberto), isso está marcado. Itens marcados **(não verificado)** não foram confirmados em fonte primária e precisam de teste físico antes de virar requisito.

## 0. Resumo e recomendações principais

1. **Atalho global: usar o portal `org.freedesktop.portal.GlobalShortcuts`**, com o Core Rust como dono da sessão do portal. Sem permissão de sistema, com consentimento do usuário. Como plano B sem portal, comando de linha (`gideon-cli toggle`) vinculado a um atalho do KDE Plasma. Este é o padrão que apps como Voxtype usam em KDE (modo toggle). Fontes: [ArchWiki XDG Desktop Portal](https://wiki.archlinux.org/title/XDG_Desktop_Portal), [Voxtype FAQ](https://github.com/peteonrails/voxtype/blob/main/docs/FAQ.md).
2. **HUD compacto: começar com uma janela Qt comum, sem-borda, com regra de janela do KWin "Manter acima" (Keep Above) criada pelo usuário.** `Qt.WindowStaysOnTopHint` não tem efeito confiável em Wayland. LayerShellQt (wlr-layer-shell) é o caminho "certo" para ancorar no topo, mas o suporte do KWin precisa de teste físico antes de ser padrão. Fontes: [KDE Discuss](https://discuss.kde.org/t/kde-plasma-support-for-qt-windowstaysontophint-flag-in-wayland/3106), [LayerShellQt API](https://api.kde.org/legacy/plasma/layer-shell-qt/html/annotated.html).
3. **Lembretes e timers: fazer no Core**, com persistência em SQLite e entrega por notificação (org.freedesktop.Notifications, que é o servidor do Plasma). Esforço baixo, impacto alto no dia a dia, sem risco de permissão. Não depender de `systemd --user timer` para isso; um timer de sistema só serve para despertar o Core.
4. **Ditado para qualquer app: começar pelo modo seguro** (transcrição mostrada no HUD, usuário confirma; cópia para a área de transferência com notificação). Injeção de teclas só depois, via portal RemoteDesktop + libei (`ConnectToEIS`), com consentimento. Evitar por padrão `uinput`/`ydotool`/`dotool` e leitura de `/dev/input` (evdev), por exigirem acesso amplo a teclado ou grupo `input`. `wtype` não funciona em KDE (protocolo de teclado virtual ausente).
5. **"Perguntar sobre minha tela": fazer por captura única acionada pelo usuário**, pelo portal Screenshot (ou pelo CLI do Spectacle, se o portal falhar), enviando para o LLM somente com consentimento de nuvem já existente no C1. Nada de captura contínua. Não usar ScreenCast como caminho inicial (exige picker e PipeWire, com bugs relatados).
6. **Busca de arquivos: Baloo como primeira opção** (já é o backend do KRunner), com `plocate` como alternativa leve para nomes de arquivo. Fazer depois do núcleo, via capability com raízes permitidas pelo usuário.
7. **Skip**: integração como método de entrada (fcitx5/IBus) para ditado; evdev como padrão; `uinput` direto.

## 1. Premissas e pontos a corrigir

- **Nixi**: a busca encontrou o site [heynixi.com](https://heynixi.com/), não `heynixi.app`. O site descreve um assistente **somente para Windows 10/11** que "fica no topo da tela", abre apps, cria lembretes e dita texto, com reconhecimento e IA rodando no PC e internet só quando o usuário pede busca ou site. Não encontrei documentação técnica de como ele implementa o overlay. Vale confirmar o domínio antes de citar como referência.
- **Estado real do Gideon** (de `docs/AGENT_STATE.md`, `docs/C4.md`, `docs/C0.md`, `README.md`): Core em Rust; plugins `python3_script` em sandbox `bwrap` sem rede, com registro fixo de capabilities no Core; permissões concedidas pelo Core/usuário; C4 (percepção e ação) existe **apenas com backend `synthetic`**; o backend `real` responde `unsupported`. Wayland real, KDE real, PipeWire, áudio físico e Flatpak estão **NÃO validados**. Qualquer item abaixo que toque em desktop real depende da rodada de validação humana (`docs/HUMAN_VALIDATION.md`).
- Este documento não tenta decidir o que o Gideon "é" em UI; sugere onde cada capacidade deve morar.

## 2. Mapa para a arquitetura do Gideon

| Capacidade | Dono sugerido | Por quê |
|---|---|---|
| Atalho global e push-to-talk | **Core** (sessão do portal) | Único lugar com a política de consentimento e com o registro de capabilities. Evita que um plugin escute teclas. |
| HUD / overlay | **App Qt** (`app/Main.qml`, bridge) | É apresentação. Não deve ser plugin: plugins não têm acesso a display. |
| Captura de transcrição e STT | **Plugin** (`python3_script`) | Já é o padrão de C1/C2. Só recebe áudio autorizado pelo Core. |
| Injeção de texto (ditado) | **Core**, capability `input_control` com aprovação | É uma ação de estado alterado. Deve passar pelo gate de Safety, com confirmação visível. |
| Timers e lembretes | **Core** (persistência + agendador) | Precisa sobreviver ao fechamento da UI e ao plugin parar. |
| Notificações | **Core** via D-Bus `org.freedesktop.Notifications` | Plugin sem rede e sem D-Bus de sessão por padrão. |
| Busca de arquivos | **Plugin** com capability `files.search` e raízes escolhidas pelo usuário | Acesso a arquivos é permissão explícita; o plugin só recebe o resultado. |
| Perguntar sobre a tela | Core captura (portal) → plugin/LLM raciocina | A captura é de "pele" do sistema; o LLM só recebe a imagem após consentimento de nuvem (C1). |

Conexão com fases existentes: C3 (agente observe-plan-act-verify) já tem o ponto de encaixe para "perguntar sobre a tela" e para ações de ditado; C4.1 (`screen.observe`) e C4.2 (`computer.control`) hoje são sintéticos e precisam de adapter real via portal, não de reescrita.

## 3. Capacidades, uma por uma

### 3.1 Overlay / HUD compacto sempre acima

**Opções**

| Opção | Como funciona | Prós | Contras |
|---|---|---|---|
| A. `Qt.WindowStaysOnTopHint` | Flag de janela Qt | Zero código extra | Em Wayland, o xdg-shell não deixa o cliente escolher empilhamento; a flag não é confiável ([KDE Discuss](https://discuss.kde.org/t/kde-plasma-support-for-qt-windowstaysontophint-flag-in-wayland/3106), [Qt Forum](https://forum.qt.io/topic/143381/how-to-get-window-stays-on-top-in-plasma-wayland)). |
| B. Janela Qt + regra do KWin "Manter acima" | Usuário (ou assistente de setup) cria regra "Keep Above: Force" para a janela `gideon` | Estável, persiste, sem código de protocolo | Exige configuração manual ou script; é uma regra do desktop, não do app. Fonte de uso: [Medium, PiP always on top no KDE](https://medium.com/@80h3m14n/pip-always-on-top-on-kde-e79061a881f4). |
| C. KWin script `keepAbove` | Script carregado no KWin altera `keepAbove` da janela | Dinâmico, pode ser ligado/desligado | API `keepAbove` documentada em [KWin scripting API](https://develop.kde.org/docs/plasma/kwin/api/); precisa de instalação de script. Relatos de que `setWindowLayer` via D-Bus funciona são anedóticos **(não verificado)**. |
| D. wlr-layer-shell via **LayerShellQt** | Surface de camada (topo, ancorada em bordas, zona exclusiva) | Caminho padrão para overlays e docks em Wayland; permite HUD ancorado sem roubar foco | Suporte do KWin precisa de confirmação. [wayland.app](https://wayland.app/protocols/wlr-layer-shell-unstable-v1) lista KWin 6.7 na tabela de compositores, mas a página não rotula colunas e não confirmei a versão exata. Não encontrei nota de release do Plasma que cite layer-shell **(não verificado)**. |

**Exemplos de como outros projetos fazem**

- Um overlay de letras para Plasma 6 usa explicitamente wlr-layer-shell, "sempre acima, click-through e fora da barra de tarefas, sem regras de janela" ([kshadowlrc](https://github.com/haytham818/kshadowlrc)). É um dos poucos exemplos que alega ausência de regras, mas sem detalhes de teste.
- Um dock de Plasma 6 usa LayerShellQt na camada top com zona exclusiva e KWayland para rastreamento ([kde-cutefish-dock](https://github.com/Lumeo-sd/kde-cutefish-dock)).
- Um PR de overlay Qt descreve `import org.kde.layershell 1.0` com `layer`, `anchors`, `keyboardInteractivity` e `exclusionZone` (note: `exclusionZone`, não `exclusiveZone`) e admite que **não foi testado em sessão KDE real** ([mouthtype PR #390](https://github.com/CodesWhat/mouthtype/pull/390)). O import só resolve se o módulo estiver instalado; isso é um detalhe de empacotamento para o Flatpak e para o pacote relocável.
- Launchers (Vicinae, Ulauncher, Albert): não encontrei fonte sobre como cada um faz overlay em Wayland. A fonte que encontrei diz que apps Wayland não registram atalhos globais sozinhos; o usuário vincula uma tecla ao comando de abrir o launcher ([LinuxLinks sobre Vicinae](https://www.linuxlinks.com/vicinae-native-launcher-desktop/), [AlternativeTo](https://alternativeto.net/software/ulauncher/?platform=linux)). KRunner é componente interno do Plasma; não verifiquei seu mecanismo **(não verificado)**.

**Recomendação para o Gideon**

- **Agora**: janela Qt sem borda, com `Qt.Tool`/`Qt.FramelessWindowHint`, mais regra "Manter acima" no setup. Funciona em X11 e em Wayland com a regra. Sem dependência nova.
- **Depois (após validação física)**: backend opcional com LayerShellQt quando o módulo estiver instalado; cair para o modo A/B se não estiver. Gate: teste em KDE Wayland real, com e sem tela cheia.
- Não prometer "aparece sobre tela cheia" sem teste. A única regra de camada `overlay` que encontrei é de uso manual **(não verificado)**.

**Esforço**: baixo (modo B), médio (LayerShellQt com fallback). **Risco**: a validação física pode mostrar que o KWin não aceita a surface; o fallback cobre.
**Recomendação**: **construir agora** (modo B) e **depois** o modo layer-shell.

### 3.2 Atalho global e push-to-talk

**Caminhos**

1. **Portal GlobalShortcuts** (`org.freedesktop.portal.GlobalShortcuts`). É a via portável e com consentimento. O ArchWiki marca `xdg-desktop-portal-kde` como suportando o portal em KDE Plasma 6 ([ArchWiki](https://wiki.archlinux.org/title/XDG_Desktop_Portal)); não consegui abrir a tabela para confirmar a linha, então isso fica **(não verificado em fonte primária)**. A MR 80 do `xdg-desktop-portal-kde` que implementa o portal (de 2022) aparece como rascunho e depende de mudança no flatpak/xdg-desktop-portal ([MR 80](https://invent.kde.org/plasma/xdg-desktop-portal-kde/-/merge_requests/80)). Um blog da KDE de maio de 2026 diz que no Wayland o `kglobalacceld` fica embutido no KWin ([KDE blog](https://blogs.kde.org/2026/05/03/gestures-in-graz-and-beyond/)); não abri o post, só o trecho da busca. Um relato de Plasma 6.0 em Arch mostra atalhos quebrados **(versão antiga)** ([Arch forum](https://bbs.archlinux.org/viewtopic.php?id=293520)).
   - Limite relatado: um atalho do portal precisa ser vinculado e consentido individualmente; por isso uma tecla de "cancelar" não pode ser global pelo portal ([ECRomaneli/wayland-global-shortcuts](https://github.com/ECRomaneli/wayland-global-shortcuts) e relato de Voxtype/HermesKey). **(fonte secundária)**
   - Push-to-talk (press e release): a especificação do portal tem sinais de ativação e desativação **(não verificado no KDE)**. Voxtype diz que em KDE usa **modo toggle**, não segurar-para-falar ([busca Voxtype](https://github.com/peteonrails/voxtype)).
2. **Atalho do próprio KDE chamando um comando**. Não depende de portal: o usuário cria um atalho de sistema que executa `gideon-cli toggle` (ou D-Bus no Core). Zero permissão extra. É o modo que Voxtype descreve para Hyprland/Sway ("bind" no compositor), adaptado ao KDE.
3. **KGlobalAccel** diretamente (C++/Qt): só faz sentido se o app for C++; o Gideon é Qt/QML, então daria para usar, mas acopla o Core a componente do KDE. Não verificado no Wayland.
4. **evdev** (`/dev/input/event*`): lê teclas antes do compositor. Ferramentas como `whisper-dictate-linux` e o fallback do Voxtype usam isso e exigem grupo `input` ([whisper-dictate-linux](https://github.com/jmorenov/whisper-dictate-linux), [Voxtype FAQ](https://github.com/peteonrails/voxtype/blob/main/docs/FAQ.md)). Um PR de um ditado Wayland remove a exigência do grupo amplo e concede só `/dev/uinput` por `uaccess` ligado à sessão ([turbo-whisper PR #27](https://github.com/knowall-ai/turbo-whisper/pull/27)). Mesmo assim, qualquer processo do usuário com acesso a esses dispositivos lê todas as teclas. **Risco alto para um app que pode gravar voz.**

**Como as ferramentas citadas fazem push-to-talk**

- **Voxtype**: Rust, offline; em Hyprland/Sway/River liga/desliga por comando de bind; em X11 e em compositores sem eventos de soltura usa evdev com grupo `input`; em KDE usa toggle ([GitHub](https://github.com/peteonrails/voxtype)).
- **hyprwhspr**: push-to-talk que só trava na soltura da tecla; exige `wtype` e `wl-clipboard` em Wayland ([GitHub](https://github.com/goodroot/hyprwhspr)). Não confirmei o suporte KDE **(não verificado)**.
- **whisper-dictate-linux**: evdev, whisper.cpp, digita no cursor; diz que funciona em KDE e que `ydotool` atua "no nível do kernel" ([GitHub](https://github.com/jmorenov/whisper-dictate-linux)).
- **Speech Note**: app de anotações; o texto fica na própria janela, então não há inserção em outros apps ([busca](https://usevoicy.com/blog/speech-to-text-linux/)) **(fonte secundária)**.
- **WhisperWriter**: só apareceu numa tabela de comparação com suporte Wayland "parcial" **(não verificado)**.
- **Talon**: documentação oficial diz que Linux é X11 e que "Wayland compositors lack the APIs necessary for Talon and Wayland support is not planned" ([Talon docs](https://talonvoice.com/docs/reference/official.html)). Não usar como referência de Wayland.
- **nerd-dictation**: não pesquisei a fundo; tende a usar `xdotool`, que é X11 **(não verificado)**.

**Recomendação**

- **Agora**: atalho via portal, com o Core como dono da sessão; fallback para comando de atalho do KDE. Modo **toggle** como padrão em KDE; press-and-hold só depois de confirmar o sinal de soltura no KDE real.
- **Não** usar evdev como padrão. Se for oferecido como opção, ser explícito sobre o grupo `input` e o risco de keylogger, e manter desligado.

**Esforço**: baixo-médio. **Risco**: comportamento de sinais do portal no KDE; conflito com atalhos já existentes.
**Recomendação**: **construir agora** (portal + fallback de comando).

### 3.3 Ditado para qualquer app

**O que a pesquisa diz sobre os caminhos de injeção**

| Caminho | Situação em KDE Wayland | Permissão | Recomendação |
|---|---|---|---|
| `wtype` (protocolo virtual-keyboard) | **Não funciona**: "Compositor does not support the virtual keyboard protocol" em KDE e GNOME ([Voxtype FAQ](https://github.com/peteonrails/voxtype/blob/main/docs/FAQ.md), [HermesKey #97](https://github.com/graygarbage/HermesKey/issues/97)) | nenhuma | **Não usar** em KDE. |
| `ydotool` | Funciona para relatos de Ubuntu 25.10 KDE, com daemon ([gist](https://gist.github.com/danielrosehill/d3913d4c8cc69acaf3ee7772771c2f1d)) | `/dev/uinput` (grupo ou udev); daemon | Plano B, opt-in, com aviso. |
| `dotool` | Recomendado pelo Voxtype: sem daemon, suporta layouts ([FAQ](https://github.com/peteonrails/voxtype/blob/main/docs/FAQ.md)) | `/dev/uinput` | Plano B, opt-in. Layouts não US são problema relatado ([Handy #718](https://github.com/cjpais/Handy/discussions/718)). |
| **Portal RemoteDesktop + libei (`ConnectToEIS`)** | Caminho oficial e com consentimento. libei faz parte dos portais RemoteDesktop e InputCapture desde a versão 1.17; persistência de consentimento na 1.21 ([Who-T, jul/2026](http://who-t.blogspot.com/2026/07/libei-integrations-in-xdg-remotedesktop.html)). Relato de KDE Plasma 6.7.5 com RemoteDesktop v2 e `ConnectToEIS` ([fcitx5-lotus #526](https://github.com/LotusInputMethod/fcitx5-lotus/issues/526), **fonte secundária**). Relato de que a primeira vez exige prompt do portal. | Diálogo do portal (primeira vez) | **Caminho certo para injeção.** |
| KWin EIS privado (`kwin-mcp`) | Funciona sem prompt, mas é interface D-Bus privada e pode quebrar entre versões ([kwin-mcp](https://github.com/CrunchyMonkies/kwin-mcp)) | nenhuma | **Não usar** em produto. |
| Área de transferência + aviso | Sem injeção; usuário cola com Ctrl+V | nenhuma | **Modo seguro** para o início. |
| Método de entrada (fcitx5 / text-input-v3) | KWin inicia o IME; funciona em apps nativos que implementam text-input; apps Chromium podem usar versão diferente do protocolo ([fcitx wiki](https://fcitx-im.org/wiki/Using_Fcitx_5_on_Wayland), [KDE CJKV](https://linux.kde.org/docs/cjkv-input/)). Não achei fonte sobre plugin de ditado no fcitx5 | Instalar e selecionar como teclado virtual | **Skip** por ora: alto esforço e cobertura parcial. |

Observação: um cliente de ditado Wayland descreve que o libei via RemoteDesktop "não exige kernel, grupo input ou udev" e funciona em KDE Plasma ≥ 6.1 e GNOME ≥ 46, mas depende do consentimento do portal (resultado de busca sobre propostas de ditado Wayland; não consegui abrir a fonte exata, então tratar como **não verificado**).

**Segurança e o que é aceitável**

- Injetar texto no app com foco é a ação mais arriscada da lista: pode cair em campo de senha, terminal com `sudo` ou janela de banco. O sistema não detecta de forma geral se o foco é um campo de senha em Wayland.
- Práticas recomendadas pela pesquisa e pelo modelo do Gideon:
  - Mostrar o texto no HUD antes de inserir, com botão de confirmar e de cancelar (Esc local, não global).
  - Inserção sempre com aprovação de permissão `input_control` concedida pelo usuário, revogável; registrar no log de auditoria do Core.
  - Não capturar teclas globais além do atalho de ativação.
  - Bloquear inserção quando o último evento for de sessão bloqueada ou de janela identificada como sensível, quando houver como identificar (**não verificado** no KDE).
  - Nunca enviar o texto transcrito a nuvem sem consentimento do C1.

**Recomendação**

- **Agora**: transcrição → HUD → botão "copiar" e notificação "copiado". Zero permissão.
- **Depois**: injeção via portal RemoteDesktop + libei, com confirmação no HUD e aprovação da capability. Medir primeiro no KDE Wayland real.
- **Não**: `ydotool`/`dotool`/evdev como caminho padrão; `wtype` em KDE; KWin EIS privado.

**Esforço**: alto (portal, sessão de emulação, política de confirmação). **Impacto**: alto. **Risco**: alto (injeção em app errado).
**Recomendação**: **depois** (modo seguro já agora).

### 3.4 Timers, lembretes e to-do

**Opções**

- **Agendador no Core + SQLite**: o Core guarda `reminders(id, due_at, text, state)` e dispara a entrega. Sobrevive a fechamento de UI e a parada de plugin. Como o Core já é o dono do estado, é a opção mais coerente com o modelo atual (persistência em `storage.rs`, a confirmar no código). **Recomendado.**
- **`systemd --user` timers**: bons para horário fixo e recorrente, mas criar um unit por lembrete é pesado e exige escrita em `~/.config/systemd/user`. Uso sugerido: só para acordar o Core quando ele estiver parado, se for necessário. Não há fonte que eu tenha lido sobre isso especificamente **(não verificado para este caso)**.
- **Entrega de notificação**:
  - `org.freedesktop.Notifications` é o que o Plasma implementa. A wiki da KDE diz que o comportamento segue a especificação 1.2 e que o campo de expiração é ignorado, todas usam o mesmo timeout ([KDE wiki](https://community.kde.org/Plasma/Notifications)) **(página com ~1,7 ano, pode estar desatualizada)**.
  - **KNotification** (framework KF6) é a API Qt-friendly e roteia para o servidor do Plasma ([api.kde.org](https://api.kde.org/knotifications-index.html)). Para o app Qt é a escolha natural; para o Core Rust, D-Bus direto.
  - **libnotify** (`notify-send`) usa o mesmo D-Bus; útil para teste, não precisa virar dependência.
- **KClock/kclockd**: existe um daemon de alarmes e timers do KDE que agenda despertar via PowerDevil e expõe `org.kde.kclockd` ([KClock](https://github.com/KDE/kclock)). Reaproveitar não é recomendado, porque acopla o Gideon a outro app, mas mostra que suspensão e despertar são problemas reais.

**Recomendação**: **construir agora** no Core (SQLite + agendador simples em loop com `tokio`/`timerfd`, não depende de systemd), entrega via D-Bus de notificação, e UI no HUD. Não prometer despertar com o computador suspenso sem teste.

**Esforço**: baixo-médio. **Impacto**: alto. **Risco**: baixo; atenção a fuso horário e a lembretes perdidos durante suspensão.

### 3.5 Busca de arquivos

- **Baloo** (indexador do KDE): é o backend que o KRunner usa para busca rápida; indexa nomes e, opcionalmente, conteúdo. Fontes de problema: uso de memória alto em idle (relato de 3 GB do `baloo_file_extractor`) e CPU alta na indexação ([Manjaro forum](https://forum.manjaro.org/t/baloo-indexing-high-cpu-and-memory-usage-when-idle/96726), [KDE Discuss](https://discuss.kde.org/t/why-baloo-is-so-inefficient/49223)). A wiki de debug mostra 100 a 1000 arquivos/s na indexação ([KDE wiki](https://community.kde.org/Baloo/Debugging)). O desligamento de conteúdo (`indexing=true` só para nomes) é o caminho comum. Consultar via CLI `baloosearch` (**nome do binário em Plasma 6 não verificado**).
- **plocate**: índice de nomes e caminhos atualizado por timer; leve e rápido para nome. Não cobre conteúdo. Não encontrei benchmark comparando com Baloo **(não verificado)**.
- Mapa para o Gideon: capability `files.search` no plugin, com **raízes autorizadas pelo usuário** (não o home inteiro por padrão), resultado limitado (ex.: 20 itens), abrir arquivo só por ação explícita. Busca por conteúdo fica para depois.

**Recomendação**: **depois**. Impacto médio-alto; esforço médio; risco de privacidade (indexar o home inteiro) moderado. Começar com plocate ou Baloo por nome.

### 3.6 "Perguntar sobre minha tela"

- **Portal Screenshot** (`org.freedesktop.portal.Screenshot`): captura única, usada pelo `xdg-desktop-portal-kde`, que o ArchWiki lista como suportado ([ArchWiki](https://wiki.archlinux.org/title/XDG_Desktop_Portal)). É o caminho recomendado para captura pontual com consentimento.
- **Spectacle (CLI)**: alternativa, com flags de captura em segundo plano e sem notificação (verificar com `spectacle --help` **(não verificado)**). Relatos de falha em Plasma 6.6: "The process is not authorized to take a screenshot" em Spectacle, Flameshot, Ksnip e grim, sem solução confirmada ([KDE Discuss](https://discuss.kde.org/t/kde-plasma-cant-take-screen-capture/47247)).
- **ScreenCast** (fluxo contínuo): exige picker, PipeWire e a sessão de portal. Relato de bug no `xdg-desktop-portal` 1.20.3 que impede o plugin de tela do KWin de inicializar, com workaround documentado ([Bazzite](https://universal-blue.discourse.group/t/screen-sharing-silently-broken-on-kde-wayland-root-cause-found-upstream-bug-filed-workaround-documented/11901)). **Não usar como base agora.**
- **Segurança**: captura só por ação do usuário ("olhar a tela" no HUD), mostrar miniatura antes de enviar, enviar a LLM de nuvem só com `cloud_consent` (que já existe e é default off no C1), registrar no log. Nenhum processo deve capturar em segundo plano.
- **Mapa**: C4.1 `screen.observe` tem que ter backend real via portal, mantendo o sintético para gate. Hoje o contrato é `real_backend: unsupported`; mudar isso exige validação física.

**Recomendação**: **depois** (após C4.1 real e após validar portal Screenshot no KDE real). Impacto alto; esforço médio; risco de privacidade alto, mitigado por ação explícita.

## 4. Roadmap priorizado (impacto no dia a dia vs. esforço)

| Ordem | Capacidade | Impacto no dia a dia | Esforço | Recomendação | Dono no Gideon | Bloqueio |
|---|---|---|---|---|---|---|
| 1 | Lembretes e timers | Alto | Baixo-médio | **Construir agora** | Core (SQLite + notificação D-Bus) | Nenhum |
| 2 | Atalho global (portal) + fallback por comando | Alto | Baixo-médio | **Construir agora** | Core (sessão do portal) | Teste em KDE real do portal |
| 3 | HUD compacto (janela Qt + regra "Manter acima") | Alto | Baixo | **Construir agora** | App Qt | Nenhum; teste visual |
| 4 | Ditado em modo seguro (HUD + copiar) | Alto | Baixo-médio | **Construir agora** | Plugin STT + HUD | Depende de STT (C-futuro) |
| 5 | Perguntar sobre a tela (captura única) | Alto | Médio | **Depois** | Core (portal Screenshot) + LLM (C1/C3) | C4.1 real; teste KDE |
| 6 | HUD via LayerShellQt (ancorado, acima de tudo) | Médio | Médio | **Depois** | App Qt | Teste de KWin real |
| 7 | Injeção de ditado via RemoteDesktop/libei | Alto | Alto | **Depois** | Core (capability `input_control`) | Portal + confirmação no HUD |
| 8 | Busca de arquivos (plocate ou Baloo por nome) | Médio-alto | Médio | **Depois** | Plugin `files.search` | Permissão de raízes |
| 9 | Busca por conteúdo de arquivos | Médio | Alto | **Mais tarde** | Plugin | Indexação |
| 10 | Ditado via fcitx5/IBus | Médio | Muito alto | **Skip** | — | — |
| 11 | evdev / uinput como padrão | Médio | Médio | **Skip** (opt-in no máximo) | — | Risco de keylogger |
| 12 | ydotool / dotool como padrão | Médio | Baixo | **Skip** (plano B opt-in) | — | Grupo/uinput |

## 5. Lacunas e o que não está verificado

- Não consegui abrir a tabela do ArchWiki para confirmar linha por linha o suporte de GlobalShortcuts, RemoteDesktop e Screenshot no `xdg-desktop-portal-kde`. As afirmações se apoiam em resumos de busca.
- Não achei nota de release do Plasma que confirme layer-shell no KWin nem a versão exata. A tabela do wayland.app mostra KWin 6.7 sem rótulo de coluna.
- Não encontrei documentação oficial do LayerShellQt com exemplo mínimo de `Window`; o exemplo é de um PR não testado.
- O post da KDE sobre gestos (kglobalacceld embutido no KWin) foi visto só no trecho de busca.
- Não há benchmark público Baloo vs. plocate.
- Não há fonte sobre como Vicinae, Ulauncher, Albert, KRunner ou Nixi implementam overlay. Não considerei nada disso como verificado.
- Sinal de soltura do portal GlobalShortcuts no KDE: não confirmado.
- Nada disso foi testado em KDE Wayland real. O Gideon ainda não validou Wayland real; as recomendações de "construir agora" devem ser validadas em `docs/HUMAN_VALIDATION.md` antes de virar gate.
- Fontes secundárias e de fórum foram usadas quando não havia primária; estão marcadas no texto.

## 6. Fontes

- Nixi: https://heynixi.com/ (via busca); https://www.nixiai.ai/en/help/install-desktop-app (outro produto, para não confundir)
- wlr-layer-shell e compositores: https://wayland.app/protocols/wlr-layer-shell-unstable-v1
- LayerShellQt (API): https://api.kde.org/legacy/plasma/layer-shell-qt/html/annotated.html
- Qt WindowStaysOnTopHint no Wayland: https://discuss.kde.org/t/kde-plasma-support-for-qt-windowstaysontophint-flag-in-wayland/3106 ; https://forum.qt.io/topic/143381/how-to-get-window-stays-on-top-in-plasma-wayland
- KWin scripting API: https://develop.kde.org/docs/plasma/kwin/api/
- Overlay/PiP no KDE: https://medium.com/@80h3m14n/pip-always-on-top-on-kde-e79061a881f4 ; https://github.com/haytham818/kshadowlrc ; https://github.com/Lumeo-sd/kde-cutefish-dock ; https://github.com/CodesWhat/mouthtype/pull/390
- Launchers: https://www.linuxlinks.com/vicinae-native-launcher-desktop/ ; https://alternativeto.net/software/ulauncher/?platform=linux
- XDG Desktop Portal: https://wiki.archlinux.org/title/XDG_Desktop_Portal
- GlobalShortcuts no KDE: https://invent.kde.org/plasma/xdg-desktop-portal-kde/-/merge_requests/80 ; https://blogs.kde.org/2026/05/03/gestures-in-graz-and-beyond/ ; https://bbs.archlinux.org/viewtopic.php?id=293520 ; https://github.com/ECRomaneli/wayland-global-shortcuts
- Voxtype: https://github.com/peteonrails/voxtype ; https://github.com/peteonrails/voxtype/blob/main/docs/FAQ.md ; https://github.com/peteonrails/voxtype/issues/85
- Outros ditados: https://github.com/jmorenov/whisper-dictate-linux ; https://github.com/goodroot/hyprwhspr ; https://github.com/knowall-ai/turbo-whisper/pull/27 ; https://github.com/Kieirra/murmure/discussions/305 ; https://usevoicy.com/blog/speech-to-text-linux/
- Talon: https://talonvoice.com/docs/reference/official.html
- Injeção: https://github.com/graygarbage/HermesKey/issues/97 ; https://github.com/cjpais/Handy/discussions/718 ; https://gist.github.com/danielrosehill/d3913d4c8cc69acaf3ee7772771c2f1d ; https://github.com/CrunchyMonkies/kwin-mcp ; https://github.com/LotusInputMethod/fcitx5-lotus/issues/526 ; http://who-t.blogspot.com/2026/07/libei-integrations-in-xdg-remotedesktop.html ; https://poltertype.com/blog/wrong-layout-typing-on-wayland/
- IME: https://fcitx-im.org/wiki/Using_Fcitx_5_on_Wayland ; https://linux.kde.org/docs/cjkv-input/
- Notificações e timers: https://community.kde.org/Plasma/Notifications ; https://api.kde.org/knotifications-index.html ; https://github.com/KDE/kclock
- Busca de arquivos: https://community.kde.org/Baloo/Debugging ; https://forum.manjaro.org/t/baloo-indexing-high-cpu-and-memory-usage-when-idle/96726 ; https://discuss.kde.org/t/why-baloo-is-so-inefficient/49223
- Captura de tela: https://discuss.kde.org/t/kde-plasma-cant-take-screen-capture/47247 ; https://universal-blue.discourse.group/t/screen-sharing-silently-broken-on-kde-wayland-root-cause-found-upstream-bug-filed-workaround-documented/11901
- Arquitetura do Gideon (local): `docs/AGENT_STATE.md`, `docs/C0.md`, `docs/C4.md`, `docs/S4.md`, `README.md`, `AGENTS.md`
