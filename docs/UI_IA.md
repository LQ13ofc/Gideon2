# Gideon App — arquitetura de informação (proposta v3)

Base: docs/UI_NOTION_REQS.md (Notion S2 + "13 · Interface"), docs/UI_INVENTORY.md (levantamento do código) e as respostas do dono
(poucas abas no topo, estilo KDE/Plasma, estrutura antes de visual).

## Princípios

1. **5 abas no topo** (as mesmas áreas que o Notion pede para a janela principal): Assistente · Extensões · Permissões · Configurações · Diagnóstico.
2. Dentro de Extensões e Configurações, **lista de seções à esquerda** (padrão "Configurações do Sistema" do KDE) e conteúdo à direita. Nada mais de menu lateral com 12 itens.
3. **Uma coisa, um lugar**: cada informação e cada controle existe em uma única tela (acabam as duplicações DU-01..DU-17).
4. **Divulgação progressiva**: três níveis — *Básico* (sempre visível), *Avançado* (atrás de "Mostrar opções avançadas", lembrado), *Desenvolvimento/Teste* (só com "Modo desenvolvedor" ligado em Diagnóstico; rótulos SINTÉTICO / SERVIDOR FALSO / replay vivem aqui ou como selo discreto).
5. **Só mostra o que existe**: áreas sem backend (Memory, Souls, Habits, Automations, dispositivos físicos) não ganham página; no máximo uma linha desativada com motivo dentro da seção certa.
6. Texto explicativo curto (≤ 2 linhas); o resto em "Como funciona" recolhível. Todo estado = cor + palavra. PlainText para dados do Core.

## As 5 abas

### 1. Assistente  (diário)
É o HUD + conversa. Um estado em destaque.
- **Faixa de estado** (HUD): Em espera / Ouvindo / Transcrevendo / Pensando / Executando / Falando / Erro, microfone ativo, botão **Cancelar** (só quando há algo a cancelar).
- **Comando**: campo "Diga ou digite", Enviar.
- **Conversa**: transcrição da voz e, **se o plugin LLM roda**, o chat com o LLM no mesmo painel (modo "Voz | Chat"); propostas de ferramenta com alvo, efeito e **risco** + Autorizar/Negar.
- **Agente** (só com LLM): painel lateral recolhível com objetivo, passos, aprovações, Abortar.
- Atalhos: status de uma linha (Wake · Entrada · Modo — com o Modo REAL, não texto fixo) que leva às Configurações.

### 2. Extensões  (ocasional)  — seções à esquerda
- **Plugins** (une "Gideon Hub" e "Plugins"): catálogo + instalados, estados, instalar/ativar/desativar/revogar/remover, quarentena.
- **Skills**: lista, criar (manual e "Gerar com LLM" se disponível), importar/exportar, versões, executar, histórico.
- **Conexões**: contas, escopos, rotas (fallback visual desligado por padrão).
- **Modelos LLM** — só aparece com o plugin LLM instalado: modelo atual, catálogo, personalizados, fallback, hardware; **Provedor e chaves** (hoje no diálogo "Motor LLM") entra aqui, não solto.
- **Percepção e ação** — só aparece com plugin C4 em execução (hoje todos sintéticos): privacidade (mic/câmera) no topo, um cartão por plugin.

### 3. Permissões  (ocasional)
Hoje é uma página vazia; passa a ser a central de grants (dados já existem no Core):
- Resumo: aprovadas · pendentes · revogadas.
- Tabela única: **quem** (plugin/skill/conexão) · **o quê** (permissão em português, nunca ID cru) · **estado** · ação (Revisar/Revogar).
- **Auditoria**: últimos eventos (anel de 64 do Core) sem conteúdo sensível.

### 4. Configurações  (ocasional) — seções à esquerda
- **Voz e Wake**: frase certificada (opções selecionáveis com badge), sessão máx.; dispositivos de captura (hoje só PCM virtual → linha desativada com motivo).
- **Áudio**: volume, voz (fixa hoje), feedback audível/visual, saída (virtual → desativado com motivo).
- **Aparência**: tema, cor de destaque, HUD visual (persistência real pendente: AC-06).
- **Privacidade**: o que é guardado (nada em disco), retenção (sem controle hoje → texto curto), consentimento de nuvem.
- **Geral**: idioma (fixo hoje), iniciar no login (indisponível hoje, com motivo), "Mostrar opções avançadas".
(O diálogo "Preferências" desaparece: tudo isso é esta aba.)

### 5. Diagnóstico  (avançado)
- Estado: Core conectado, engines Wake/STT/TTS com badge, pacote de voz.
- Eventos recentes e recuperação (reiniciar Core quando exigido).
- **Modo desenvolvedor** (switch): revela comando de texto de teste, invocar capability, rótulos SINTÉTICO/SERVIDOR FALSO por extenso, replay.

## Cabeçalho e rodapé

Barra de abas no topo (ícone + rótulo; estilo Breeze), à direita o **estado do assistente** (pílula) e Cancelar quando aplicável. Sem rodapé fixo. Abaixo de 900 px as abas viram só ícones com tooltip.

## O que sai da interface principal

Cartão "Estado do sistema" do Início (→ Diagnóstico); hero de marketing; três cartões "Abrir"; diálogos Preferências / Motor LLM / Revisar permissões / Plugins (viram seções); entrada separada "Gideon Hub"; texto fixo "Modo: Base · sem LLM"; rodapé de diagnóstico.

## Lacunas conhecidas (viram linhas desativadas com motivo, não páginas)
Sensibilidade, dispositivos físicos, escolha de voz, idioma, performance, iniciar no login, retenção, onboarding (a decidir), HUD WakeDetected.

## Fora de escopo
Memory, Souls, Habits, Automations (sem backend).
