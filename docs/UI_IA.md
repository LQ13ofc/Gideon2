# Gideon App — arquitetura de informação (proposta v4: 5 abas, cada uma com sub-abas)

Base: docs/UI_NOTION_REQS.md (Notion S2 + "13 · Interface"), docs/UI_INVENTORY.md (levantamento do código), respostas do dono
(poucas abas no topo, estilo KDE/Plasma, estrutura antes de visual, cada aba com sub-abas).

## Casca (igual em todas as telas)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◉ Gideon   [Assistente] [Extensões] [Permissões •2] [Configurações] [Diagnóstico]   ● Em espera  [Cancelar] │  ← abas (nível 1)
├──────────────────────────────────────────────────────────────────────────────┤
│  Hoje · Conversa · Agente · Atividade                                         │  ← sub-abas (nível 2) da aba ativa
├──────────────────────────────────────────────────────────────────────────────┤
│  título da sub-aba + 1 linha de explicação                       [ação primária] │
│  faixa de resumo (1 linha, badges)                                            │
│  conteúdo: no máximo 3 blocos (cartões); "Como funciona" recolhível           │
└──────────────────────────────────────────────────────────────────────────────┘
```
- Abas de nível 1: ícone + rótulo, estilo Breeze; contador/badge quando há pendência (ex.: Permissões •2).
- Sub-abas de nível 2: texto, sublinhado no ativo. **Sub-aba condicional** (depende de plugin) some; se o usuário precisa dela, a sub-aba
  vizinha mostra o atalho "Instalar em Extensões › Plugins".
- Estado do assistente (pílula) e **Cancelar** (só quando há algo a cancelar) ficam sempre à direita da barra de abas.
- Abaixo de 900 px: abas viram só ícones com tooltip; sub-abas rolam na horizontal.
- Níveis de conteúdo: **Básico** (sempre) · **Avançado** (atrás de "Mostrar opções avançadas", em Configurações › Geral) · **Desenvolvimento**
  (atrás de "Modo desenvolvedor", em Diagnóstico › Desenvolvedor; é onde ficam SINTÉTICO/SERVIDOR FALSO por extenso, replay, comando de teste).
- Honestidade: selos obrigatórios continuam, mas como **selo discreto** ao lado do item afetado, nunca como parágrafo.

---

## 1. Assistente  (uso diário)

Sub-abas: **Hoje · Conversa · Agente · Atividade**

### 1.1 Hoje
Objetivo: ver como o Gideon está e dar um comando.
1. **Estado (HUD)**: orbe pequeno + frase grande (Pronto para ouvir / Ouvindo… / Transcrevendo… / Pensando… / Executando… / Falando… / Erro); aviso "microfone ativo" quando capturando; Cancelar.
2. **Comando**: campo "Diga ou digite um comando" (+ exemplo) e Enviar (primário). Em desenvolvimento a entrada de texto de teste é a mesma (rotulada no modo dev).
3. **Última interação**: Você / Gideon (bolhas), recibo com cor+palavra (Concluído / Falhou), proposta pendente com **alvo, efeito, risco** e Autorizar/Negar.
4. **Chips de estado** (1 linha, clicáveis): Wake (frase + qualificação) → Configurações › Voz e Wake; Entrada → Configurações › Dispositivos; Modo → real: "Base" ou "Base + LLM (modelo)".
Vazio: "Diga 'Hey Gideon' ou digite um comando".
Avançado: confiança/transcrição parcial ao vivo. Dev: ver 4 abaixo (Desenvolvedor).

### 1.2 Conversa  (condicional: plugin LLM em execução)
1. Mensagens (rolagem; parcial → final; estado "Aguardando resposta").
2. Entrada fixa embaixo + Enviar/Cancelar resposta.
3. Propostas de ferramenta inline (alvo, efeito, risco; Autorizar/Negar).
4. Aviso quando o **fallback** respondeu (hoje inexistente) e quando faltam consentimento de nuvem ou chave (com link para Extensões › Modelos LLM).
Vazio: sugestões ("Que horas são?", "Abrir o Brave").
Sem plugin: a sub-aba não aparece; Hoje mostra o chip "Modo: Base, sem LLM" com atalho para instalar.

### 1.3 Agente  (condicional: plugin LLM)
1. Objetivo (campo) + Iniciar (primário) / Abortar.
2. Passos: lista (n, tipo, ferramenta, risco, estado, código) — rolagem, cores+palavras.
3. Orçamento (passos, tempo, tokens) em linha; resposta final (texto puro).
4. Aprovações pendentes do agente (reaproveita o cartão de proposta).
Vazio: "Descreva um objetivo; o Gideon propõe passos e pede sua aprovação".

### 1.4 Atividade
Linha do tempo única do que aconteceu (sem conteúdo sensível): comandos e recibos, execuções de skill, runs do agente, propostas autorizadas/negadas, erros recuperados.
Fontes existentes: `events` (anel de 64), histórico de skills, última chamada de conexão. Filtros: Tudo · Comandos · Skills · Agente · Erros.
Vazio: "Nada ainda nesta sessão".

---

## 2. Extensões  (uso ocasional)

Sub-abas: **Plugins · Skills · Conexões · Modelos LLM · Percepção e ação**  (as duas últimas são condicionais)

### 2.1 Plugins  (une "Gideon Hub" + "Plugins")
Resumo: catálogo (verificado / não configurado) · N instalados · N ativos · N em quarentena.
Controle segmentado: Todos · Instalados · Disponíveis · Quarentena.
1. **Grade de cartões**: nome, versão, 1 linha, badge de estado (Disponível / Instalado / Ativo / Parado / Falhou / Quarentena / Incompatível), ação primária contextual (Instalar · Ativar · Desativar), menu ⋯ (Revogar · Remover · Apagar dados do plugin).
2. **Detalhe** (painel ao selecionar): publisher (não autenticado), versão, hash, capacidades, **permissões em português** + estado, dependências, tamanho; botão "Revisar permissões e instalar".
3. Banner de 1 linha: "Pacotes verificados por checksum · sem rede · publisher não autenticado" + "Como funciona".
Vazio: "Catálogo não configurado" + Explorar catálogo.
Avançado: importar/descartar pacote em staging (hoje só CLI → linha desativada com o comando).

### 2.2 Skills
Resumo: N instaladas · N habilitadas · N rascunhos. Segmentado interno: **Minhas · Criar · Importar/Exportar · Execuções**.
- *Minhas*: lista (nome, versão, estado Rascunho/Validada/Testada/Aprovada/Habilitada/Desabilitada, deps ok/faltando, origem), ações contextuais (Validar · Simular · Aprovar · Habilitar · Versões/Voltar · Remover com confirmação), detalhe com permissões necessárias × aprovadas.
- *Criar*: editor de manifesto (texto), "Gerar com LLM" (só com plugin), Validar, Salvar rascunho; erros do validador em português.
- *Importar/Exportar*: pasta e nome do arquivo (mostrar o caminho!), prévia com publisher **não verificado**, achados, delta de permissões, Confirmar como rascunho; Exportar com caminho resultante.
- *Execuções*: executar com entradas, progresso por passo, aprovar/negar passo (com risco), Cancelar, histórico (estado, passo, códigos).
Vazio por segmento com ação. "Como funciona" recolhível. Nível Avançado: JSON bruto, hashes.

### 2.3 Conexões
Resumo: N contas · N conectadas · N pendentes.
Segmentado: **Contas · Rotas · Nova conta**.
- *Contas*: um cartão por conta (GitHub, Google, Home Assistant, MCP): status (Conectado / Conectando / Expirado / Reautenticar / Offline / Erro / Desconectado), conta, **escopos como chips** (concedidos × pedidos), ações (Conectar · Consentir por escopo · Atualizar · Desconectar · Revogar · Remover — todas com confirmação), campo de token (Home Assistant), ferramentas MCP descobertas com **Confiar**; operações disponíveis com rótulo de risco.
- *Rotas*: por finalidade (Criar issue, Listar eventos, Ler estado): rota escolhida e descartadas com motivo; interruptor "Permitir fallback visual" (desligado, com aviso).
- *Nova conta*: provedor + apelido; passo a passo de consentimento (código de usuário).
Selo "SERVIDOR FALSO" discreto por conta quando for o caso (detalhe no modo dev).

### 2.4 Modelos LLM  (condicional: plugin LLM)
Resumo: modelo atual · estado (Disponível / Indisponível: motivo / Sem chave / Sem consentimento) · Nuvem/Local.
Segmentado: **Modelo atual · Catálogo · Personalizados · Provedor e chaves · Fallback e hardware**.
- *Modelo atual*: detalhes (licença, quantização, hash, recursos, custo, latência), "Testar" (selftest) e "Voltar ao último bom".
- *Catálogo*: lista com filtro Local/Nuvem, selo de certificação (Certificado / Candidato / Declarado), detalhe à direita, **Usar este modelo** (fluxo configurar → testar → marcar bom/reverter), Carregar mais.
- *Personalizados*: formulário (provedor, modelo, porta/URL https, recursos declarados), lista com Remover.
- *Provedor e chaves*: provedor, modelo, URL, **consentimento de nuvem**, chave (campo oculto; "chave configurada" só quando existe) — hoje no diálogo Motor LLM.
- *Fallback e hardware*: seleção de fallback com aviso de nuvem; CPU/RAM/GPU.

### 2.5 Percepção e ação  (condicional: plugin de percepção em execução)
Resumo: N plugins · privacidade (mic/câmera).
Segmentado: **Privacidade · Plugins · Último resultado**.
- *Privacidade*: indicadores de microfone e câmera sempre visíveis + "Backends simulados: nenhum hardware real é acessado".
- *Plugins*: um cartão por plugin (screen_observe, computer_control, audio_advanced, mic_advanced, camera_gesture, display_manipulate): estado, permissão, selo SINTÉTICO, "backend real: pendente de validação humana", botões de teste só-leitura; display_manipulate com UNSUPPORTED.
- *Último resultado*: saída da última chamada (texto puro).

---

## 3. Permissões  (ocasional; é a central de grants)

Sub-abas: **Visão geral · Concessões · Auditoria**
(a aba mostra um contador de pendências). Plugins, Skills e Conexões **não** são sub-abas aqui (já existem em Extensões):
são **filtros** dentro de Concessões, para não repetir a navegação.

### 3.1 Visão geral
Resumo: N aprovadas · N pendentes · N revogadas. **Fila de pendências** (o que precisa da sua decisão agora, com Revisar). Lista curta "Concedido recentemente". "Como funciona" recolhível.
Vazio: "Nada pendente".

### 3.2 Concessões
Uma tabela única com filtro segmentado **Todas · Plugins · Skills · Conexões** e coluna "Origem" (badge). Linhas:
plugin → permissão (rótulo em português) · estado · Revisar/Revogar; skill → necessárias × aprovadas × faltando · Revisar; conexão → escopo · acesso (leitura/escrita/público/destrutivo) · concedido · Consentir/Revogar. Agrupar por Origem ou por Item.

### 3.3 Auditoria
Eventos recentes do Core (anel de 64): hora, tipo, resultado — sem conteúdo. Filtros por origem (Plugin · Skill · Conexão · Comando). Avançado: caminho do log.

---

## 4. Configurações  (ocasional)

Sub-abas: **Voz e Wake · Áudio · Dispositivos · Aparência · Privacidade · Geral**

### 4.1 Voz e Wake
Resumo: frase ativa + qualificação + estado do wake.
1. **Frase de despertar**: opções certificadas como cartões selecionáveis (Hey Gideon · "em desenvolvimento"; Okay Gideon · "requer prova de conceito", bloqueada), troca exige reiniciar o Core (botão "Reiniciar Core" quando suportado, hoje texto).
2. **Sessão**: tempo máximo (leitura hoje).
3. Desativados com motivo: sensibilidade.

### 4.2 Áudio
Resumo: saída · voz · volume.
1. **Volume da resposta** (slider, valor, Aplicar).
2. **Voz**: voz atual (fixa hoje) e estado da resposta; feedback **audível** e **visual** (interruptores).
3. Desativados com motivo: escolha de voz.

### 4.3 Dispositivos
Entrada: PCM virtual (único hoje; microfone físico "pendente de validação humana"). Saída: virtual. Câmera/Tela: simuladas pelos plugins de Percepção (link para Extensões › Percepção e ação). Desativado com motivo: seleção de dispositivo físico.

### 4.4 Aparência
Tema (Escuro/Claro/Sistema), cor de destaque (amostras), HUD visual, prévia ao vivo. (Persistência real pendente: indicar "não persiste ainda" ou implementar.)

### 4.5 Privacidade
O que é e não é guardado (nada em disco; áudio e legendas só em memória), consentimento de nuvem (leitura aqui, edição em Modelos LLM › Provedor), apagar dados de plugins, retenção (sem controle hoje → texto).

### 4.6 Geral
Idioma (fixo hoje, com motivo), iniciar no login (indisponível, com motivo), **Mostrar opções avançadas** (interruptor), restaurar padrões / modo seguro (com confirmação).

---

## 5. Diagnóstico  (avançado)

Sub-abas: **Estado · Motores · Recuperação · Desenvolvedor** (a última só quando o modo está ligado; o interruptor fica em Estado)

### 5.1 Estado
Core (conectado/offline), perfil, idioma da Base, versão do pacote, privacidade, bloco **Últimos erros** (máx. 5), interruptor **Modo desenvolvedor**. (Não há feed de eventos aqui: ele existe só em Assistente › Atividade e Permissões › Auditoria.)
### 5.2 Motores
Wake · STT · TTS: cartão com badge de estado, motor, detalhe; pacote de voz (preflight, entrada/saída).
### 5.3 Recuperação
Reiniciar Core (quando exigido: wake/feedback/plugins), reparar instalação (hoje só CLI → comando em linha desativada), modo seguro, última configuração boa do LLM.
### 5.4 Desenvolvedor  (condicional)
Comando de texto de teste, invocar capability, replay, rótulos SINTÉTICO/SERVIDOR FALSO por extenso, versões, hashes.

---

## Regras de unicidade (resolve as duplicações DU-01..DU-17)

| Informação / controle | Único lugar |
|---|---|
| Estado Wake/STT/TTS | HUD (resumo) · detalhe em Diagnóstico › Motores |
| Frase de wake | Configurações › Voz e Wake (chip no Assistente só leva até lá) |
| Volume | Configurações › Áudio |
| Indicador visual (HUD) | Configurações › Aparência |
| Catálogo de plugins | Extensões › Plugins |
| Permissões e grants | Permissões (outras telas só mostram o estado e linkam) |
| Provedor, chave, consentimento de nuvem | Extensões › Modelos LLM › Provedor e chaves |
| Cancelar | Pílula do cabeçalho (sessão/resposta); "Abortar" (agente) e "Cancelar execução" (skill) ficam dentro dos seus blocos com rótulos distintos |
| Diagnóstico em texto | Diagnóstico (sem rodapé fixo) |

## Fora de escopo
Memory, Souls, Habits, Automations (sem backend). Onboarding: decisão do dono.
