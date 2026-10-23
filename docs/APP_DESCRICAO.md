# Gideon App — como vai ser (descrição para aprovação)

Texto direto, em português simples. Detalhes por elemento (posição em pixels, textos exatos, dados) ficam em `docs/ui-spec/`.
Pesquisa que embasa as escolhas: `docs/research/` (assistentes e launchers, navegação e configurações, temas).

**Legenda:** ✅ já existe no Core/app · 🆕 novo, só no app (configuração salva localmente, sem mudar o Core) · 🔧 novo, precisa de mudança no Core ou na ponte · ⛔ indisponível hoje (aparece desativado, com o motivo escrito).

---

## 1. A ideia em uma frase

Um assistente de voz que **mostra uma coisa por vez**: se está pronto, ouvindo, pensando, executando ou falando. Tudo o que é de uso diário está
na primeira aba; o resto (extensões, permissões, configurações, diagnóstico) fica em quatro abas, cada uma com sub-abas. O visual é calmo,
escuro por padrão, com estilo KDE/Plasma, e **quase tudo é configurável** (temas, cores, densidade, fontes, atalhos).

## 2. No que me inspirei (e o que peguei de cada um)

| App | O que peguei |
|---|---|
| **Home Assistant (Assist)** | Quatro estados de voz com nomes fixos (parado, ouvindo, processando, respondendo); paleta Ctrl+K para ir a qualquer página. |
| **Raycast / Alfred** | Teclado primeiro (Enter envia, Esc cancela, Ctrl+K ações); confirmação de ação de risco mostrando exatamente o que vai rodar; três modos de permissão (Perguntar, Automático, Sempre permitir); respostas longas recolhidas. |
| **Gemini / Alexa+** | Escuta como ondulação radial (não spinner); pensando como movimento lento; cartão de resultado com ação separada. |
| **VS Code** | Busca de configurações; marca de "modificado" em cada opção; filtro "somente modificados"; restaurar padrão por item; perfis exportáveis sem segredos; editar como JSON (avançado). |
| **KDE Plasma (Configurações do Sistema)** | Janela com abas simples, busca, destaque do que mudou, cores com acento. |
| **GNOME** | Aplicar na hora (sem botão Aplicar) para opções simples; Aplicar só quando um conjunto precisa valer junto. |
| **Obsidian** | Ação separada e explícita para liberar algo perigoso (código de terceiros). |
| **Material You / Catppuccin / Nord** | Tema definido por papéis de cor (fundo, superfície, texto, acento…) e presets prontos; validação de contraste (WCAG AA). |

## 3. A casca (igual em todas as telas)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ◉ Gideon  [Assistente] [Extensões] [Permissões•2] [Configurações] [Diagnóstico]  🔍 Ctrl+K   ● Em espera  [Cancelar] │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  sub-abas da aba ativa  (ex.: Hoje · Conversa · Agente · Atividade)                   │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  Título da sub-aba                                                    [Ação principal] │
│  uma linha explicando para que serve                                                   │
│  ┌ faixa de resumo ─────────────────────────────────────────────────────────────────┐ │
│  └──────────────────────────────────────────────────────────────────────────────────┘ │
│  cartões de conteúdo (no máximo 3 visíveis)                                            │
└──────────────────────────────────────────────────────────────────────────────────────┘
```
- **Barra de abas (topo):** logo e nome à esquerda; as 5 abas no centro-esquerda (ícone + nome); à direita a **busca/paleta (Ctrl+K)**, a **pílula de estado** do assistente e o botão **Cancelar** (só aparece quando há algo a cancelar).
- **Sub-abas:** logo abaixo, texto com sublinhado na ativa. Se uma sub-aba depende de um plugin, ela some; no lugar, a vizinha mostra "Instale em Extensões › Plugins".
- **Contadores:** uma aba com pendência mostra um número (ex.: Permissões •2 = duas decisões esperando você).
- **Sem rodapé fixo.** Mensagens rápidas aparecem como aviso temporário no canto inferior direito.
- **Janela pequena (< 900 px):** as abas viram só ícones (com o nome ao passar o mouse); mínimo 720×520.
- **Teclado:** Ctrl+1…5 troca de aba · Ctrl+Tab troca de sub-aba · Ctrl+K abre a paleta · Esc fecha/cancela · Enter envia · Shift+Enter quebra linha · Ctrl+M liga/desliga o microfone 🆕.
- **Paleta Ctrl+K 🆕:** digite e vá direto a qualquer página, configuração ou comando ("tema escuro", "volume", "instalar plugin"). Prefixos: `p:` páginas, `s:` configurações, `c:` comandos.

## 4. As cinco abas, uma por uma

### 4.1 Assistente (o dia a dia)

**Hoje**
- *Em cima:* o **estado em destaque** — orbe pequeno e uma frase grande: "Pronto para ouvir", "Ouvindo…", "Transcrevendo…", "Pensando…", "Executando…", "Falando…" ou "Erro". Se o microfone está captando, aparece "Microfone ativo".
- *Logo abaixo:* o **campo de comando** ("Diga ou digite um comando"), com Enviar e uma dica ("Ex.: abrir o Brave").
- *Meio:* **última interação** em duas bolhas (Você / Gideon) com o resultado (Concluído / Falhou). Se há algo esperando sua aprovação, o cartão mostra **o que vai ser feito, onde e qual o risco**, com Autorizar e Negar.
- *Embaixo:* três **chips clicáveis**: Wake (frase ativa), Entrada (PCM virtual hoje), Modo (Base ou Base + LLM, o real). Cada um leva à configuração certa.
- Vazio: "Diga 'Hey Gideon' ou digite um comando".

**Conversa** (só com o plugin LLM rodando)
- Mensagens ocupam a tela; campo de envio fixo embaixo; propostas de ferramenta aparecem no meio da conversa com risco e botões. Avisos claros se falta chave ou consentimento de nuvem, ou se o modelo reserva (fallback) respondeu 🔧.

**Agente** (só com LLM)
- Campo "Objetivo" + Iniciar/Abortar; lista de passos com estado (cor + palavra); orçamento (passos, tempo, tokens) em uma linha; resposta final; aprovações pendentes no mesmo cartão.

**Atividade** 🔧
- Linha do tempo do que o assistente fez por você: comandos, execuções de skills, passos do agente, aprovações e erros. Filtros: Tudo · Comandos · Skills · Agente · Erros. Sem conteúdo sensível.

### 4.2 Extensões (o que se instala e conecta)

**Plugins** (junta o antigo "Gideon Hub" e "Plugins")
- *Faixa de resumo:* catálogo verificado · N instalados · N ativos.
- *Filtro:* Todos · Instalados · Disponíveis · Quarentena.
- *Grade de cartões:* nome, versão, 1 linha, **estado em cor+palavra** (Disponível, Instalado, Ativo, Parado, Falhou, Quarentena), botão principal contextual (Instalar/Ativar/Desativar) e menu ⋯ (Revogar, Remover, Apagar dados).
- *Painel de detalhes (à direita ao clicar):* quem publica (não verificado), versão, capacidades e **permissões em português**; "Revisar permissões e instalar".
- Vazio: "Catálogo não configurado" + botão Explorar catálogo.

**Skills**
- Quatro partes: **Minhas · Criar · Importar/Exportar · Execuções**.
- *Minhas:* lista com estado (Rascunho → Validada → Testada → Aprovada → Habilitada), dependências ok/faltando, ações (Validar, Simular, Aprovar, Habilitar, Voltar versão, Remover com confirmação).
- *Criar:* editor do manifesto, "Gerar com LLM" (se houver plugin), Validar, Salvar rascunho; erros do validador em português.
- *Importar/Exportar:* mostra o **caminho exato** da pasta; prévia com "publisher não verificado", achados e mudança de permissões; Exportar mostra o arquivo gerado.
- *Execuções:* escolhe entradas, executa com progresso por passo, aprova cada passo com risco visível, Cancelar, histórico.

**Conexões**
- **Contas:** um cartão por serviço (GitHub, Google, Home Assistant, MCP): estado, conta, **escopos como etiquetas**, botões (Conectar, Consentir por escopo, Atualizar, Desconectar, Revogar — as destrutivas pedem confirmação).
- **Rotas:** para cada finalidade (ex.: criar issue) mostra o caminho escolhido e os descartados, com motivo; chave "Permitir fallback visual" (desligada, com aviso).
- **Nova conta:** passo a passo de consentimento.

**Modelos LLM** (só com o plugin LLM)
- *Modelo atual · Catálogo · Personalizados · Provedor e chaves · Fallback e hardware.* Catálogo com selo de certificação (Certificado/Candidato/Declarado), detalhes à direita (licença, quantização, custo, recursos) e o botão **Usar este modelo** (configura → testa → mantém ou volta). Chaves ficam em campo oculto; o consentimento de nuvem fica ao lado.

**Percepção e ação** (só com plugins de percepção)
- *Privacidade* (indicadores de microfone e câmera sempre visíveis) · *Plugins* (um cartão por plugin com selo SINTÉTICO e botões de teste só de leitura) · *Último resultado*.

### 4.3 Permissões (você decide o que cada coisa pode)

**Visão geral:** resumo "N aprovadas · N pendentes · N revogadas", a **fila do que espera sua decisão** (botão Revisar) e as concessões recentes.
**Concessões:** uma tabela única de tudo o que foi concedido (plugins, skills, conexões), com filtro Todas · Plugins · Skills · Conexões; colunas: quem · o quê (sempre em português) · estado · ação (Revisar/Revogar). Agrupa por origem ou por item.
**Auditoria:** o que foi aprovado, negado ou revogado, com hora e resultado, sem conteúdo.

### 4.4 Configurações (tudo é ajustável)

Seis sub-abas: **Voz e Wake · Áudio · Dispositivos · Aparência · Privacidade · Geral**. Ver a lista completa na seção 6. Cada opção tem um nome, uma linha de ajuda, aplica na hora, mostra uma barra "modificado" quando difere do padrão e tem "Restaurar padrão".

### 4.5 Diagnóstico (para quando algo não vai bem)

**Estado** (Core, perfil, versão, últimos erros, interruptor Modo desenvolvedor) · **Motores** (Wake, STT, TTS com estado e pacote de voz) · **Recuperação** (reiniciar Core, modo seguro, última configuração boa do LLM, comandos de reparo copiáveis) · **Desenvolvedor** (só com o modo ligado: comando de teste, invocar capability, replay, rótulos técnicos por extenso).

## 5. Temas e aparência (o que o usuário controla)

### 5.1 Como um tema funciona
Um tema é um conjunto de **papéis de cor** (não cores soltas): fundo, superfície, superfície variante, borda, texto, texto secundário, **acento**, texto sobre acento, sucesso, aviso, erro, informação. Tudo na tela usa esses papéis, então qualquer tema fica coerente.
O app **valida o contraste** (WCAG AA: texto 4,5:1, bordas e controles 3:1). Se você escolhe uma cor ruim, ele **corrige sozinho** e mostra o antes e o depois; se não der para corrigir, recusa e explica.

### 5.2 Presets prontos 🆕 (8)
Gideon Escuro (padrão) · Gideon Claro · Alto contraste · Estilo Breeze escuro · Estilo Breeze claro · Estilo Catppuccin · Estilo Nord · Daltonismo-seguro. Hex de cada um em `docs/research/ux-temas.md` (já checados contra os limiares).

### 5.3 O que dá para mexer
**Básico:** modo (Sistema/Escuro/Claro) · preset · cor de destaque (amostras + cor livre) · densidade (compacta/normal/espaçosa) · raio dos cantos (quadrado → bem arredondado) · tamanho da fonte (12–20) · família da fonte (sistema ou lista) · contraste (normal/alto).
**Avançado:** cada cor individual · animações (desligadas/reduzidas/normais) · translucidez · intensidade da sombra · peso do título · altura da linha · largura da barra lateral. Tudo com **prévia ao vivo** e "Restaurar".
**Importar/Exportar tema** (arquivo JSON versionado, validado ao importar). **Seguir o sistema** (claro/escuro e acento do KDE) quando disponível. **Reduzir movimento** respeita a preferência do sistema.

## 6. As configurações (muitas, organizadas)

### Voz e Wake
- ✅ Frase de despertar: **Hey Gideon** (em desenvolvimento) · Okay Gideon (requer prova de conceito — bloqueada).
- ✅ Tempo máximo da sessão (leitura hoje).
- ⛔ Sensibilidade do wake (indisponível: ainda fixa na Base).
- 🆕 Mostrar o transcrito parcial ao vivo · 🆕 Mostrar a confiança (Avançado).
- 🔧 Reiniciar o Core quando a troca de frase exigir (botão em vez de só texto).

### Áudio
- ✅ Volume da resposta (0–100). ✅ Feedback sonoro (liga/desliga). ✅ Feedback visual (liga/desliga).
- ⛔ Escolha de voz (indisponível: voz única hoje). ⛔ Velocidade da fala.
- 🆕 Som de início/fim de escuta (liga/desliga, só UI).

### Dispositivos
- ✅ Entrada: PCM virtual. ✅ Saída: virtual. ⛔ Microfone e alto-falante físicos (pendente de validação humana).
- Câmera e tela: simuladas pelos plugins de Percepção (link).

### Aparência
- Tudo da seção 5. 🆕 Mostrar orbe animado (liga/desliga) · 🆕 Orbe: pequeno/médio · 🆕 Idioma da interface (⛔ só português hoje).

### Privacidade
- ✅ Nada de histórico gravado em disco; áudio e legendas só em memória (texto explicativo curto).
- 🔧 Retenção do histórico de Atividade (nenhum / sessão).
- ✅ Consentimento de nuvem (leitura aqui; edição em Modelos LLM). ✅ Apagar dados de plugin. 🆕 Pedir confirmação para ações de escrita/públicas (padrão: sempre).
- 🆕 Por capacidade: Perguntar / Automático (só leitura) / Sempre permitir — padrão Perguntar; "Não perguntar de novo" reversível.

### Geral
- 🆕 Mostrar opções avançadas (liga/desliga, lembrado). 🆕 Mostrar dicas e vazios com sugestões. 🆕 Atalhos de teclado (liga/desliga) e lista dos atalhos.
- 🆕 Aba inicial ao abrir. 🆕 Lembrar tamanho e posição da janela.
- ⛔ Iniciar no login (indisponível: autostart ainda não existe).
- 🆕 Exportar/Importar configurações (sem segredos) · 🆕 Perfis de configuração.
- ✅ Restaurar padrões / modo seguro (com confirmação digitando o nome do perfil).
- 🆕 Editar como JSON (avançado).

### Busca nas configurações
Campo no topo da aba: encontra opções por nome ou ajuda e abre a sub-aba já com a opção destacada. Filtro **Somente modificados**. Cada opção alterada ganha uma barra à esquerda.

## 7. Regras de qualidade (valem para toda página)

1. **Uma pergunta por página:** título, uma linha de explicação, faixa de resumo, no máximo 3 cartões.
2. **Texto curto.** Explicações longas ficam em "Como funciona" (recolhido).
3. **Estado = cor + palavra**, nunca só cor.
4. **Ação principal sempre no mesmo lugar** (canto direito do cabeçalho ou do cartão).
5. **Ações perigosas pedem confirmação** que mostra exatamente o que vai acontecer.
6. **Vazio útil:** ícone, uma frase e o botão do próximo passo.
7. **Nada em inglês nem códigos crus** na tela principal; códigos só em Avançado.
8. **Honestidade:** itens simulados, sem verificação ou ainda indisponíveis têm selo discreto ou ficam desativados com o motivo.
9. **Teclado e leitor de tela:** foco visível, nomes acessíveis, ordem lógica.
10. **Rápido e leve:** animações curtas (≈200 ms), orbe parado quando ocioso.

## 8. O que isso exige de trabalho

- **Só app (🆕):** sistema de temas e presets, paleta Ctrl+K, busca de configurações, marcas de modificado, perfis, atalhos, abas e sub-abas. Guardado localmente pelo app, sem mudar o Core.
- **Ponte/Core (🔧):** feed de Atividade, aviso de fallback respondido, retenção, botão de reiniciar Core, modos de permissão por capacidade, lista de concessões unificada.
- **Fora de escopo agora (⛔):** dispositivos físicos, escolha de voz, sensibilidade, idioma, iniciar no login. Aparecem desativados com o motivo.

## 9. Ordem de construção sugerida
1. Casca nova (abas, sub-abas, pílula, paleta) e sistema de temas com presets.
2. Assistente › Hoje e Configurações (as duas mais vistas).
3. Extensões (Plugins, Skills, Conexões, Modelos, Percepção).
4. Permissões (com a lista unificada) e Diagnóstico.
5. Busca, perfis, importar/exportar, polimento e acessibilidade.
Cada etapa termina com capturas reais comparadas ao mockup aprovado.
