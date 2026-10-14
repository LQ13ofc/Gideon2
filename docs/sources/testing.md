Here is the result of "fetch" for the Page with URL https://app.notion.com/p/3f852661c75181cc92c8d18bd203335d as of 2026-10-13T21:26:59.188Z:
<page url="https://app.notion.com/p/3f852661c75181cc92c8d18bd203335d" icon="🧪">
<ancestor-path>
<parent-page url="https://app.notion.com/p/3f852661c751813fa040d7cd3611ad96" title="Gideon — Desenvolvimento (S1–S5)"/>
<ancestor-2-page url="https://app.notion.com/p/3f452661c7518107b6ecd81411f4cc44" title="Gideon — Wiki"/>
</ancestor-path>
<properties>
{"title":"Qualidade — gates e testes sem intervenção humana"}
</properties>
<iconMetadata>{"type":"emoji","emoji":"🧪"}</iconMetadata>
<content>
**Status:** política transversal aprovada. A linha de trabalho é uma única árvore que sempre executa o mesmo Gideon; uma sequência não é a soma de POCs isoladas.
## Estados estritos
`PLANNED` → `IMPLEMENTED` (código + testes unitários) → `INTEGRATED` (funcionalidade conectada ao fluxo real anterior) → `AUTO_VERIFIED` (testes E2E negativos e regressão/sandbox) → `AWAITING_HUMAN_VALIDATION` (quando precisa de fala real, portal/periférico/conta) → `HUMAN_VERIFIED` (após autorização do usuário). Um estado não implica o seguinte automaticamente. `BLOCKED_EXTERNAL` para indisponibilidade hardware/credential/platform, `FAILED` para bug conhecido bloqueante.
## Regra de progressão sem pular
Trabalhar um **subgate por vez** na ordem definida A0→A5, B1→B4, C0→C4.x, D1→D4, E1→E4. Cada subgate deve acrescentar código integrado e passar pelo menos:
1. contrato e checks positivos/negativos;
2. processo real com serviços sandbox/fixtures quando aplicável;
3. estado Core/UI verdadeiro, ação verificada/não execução comprovada;
4. cancel/timeout/error/restart/rollback no escopo;
5. regressão do fluxo desde wake até etapa já entregue;
6. registro de commit/source→binary hash e riscos.
Ao terminar um subgate, adicionar checkpoint curto a `docs/AGENT_STATE.md`, sem relatórios redundantes.
## Freeze humano total durante produção
Usuário não testa mic/câmera/tela/timbre, não ouve 24 clips, não instala software, não roda comandos no PC, não fornece credenciais, não aprova prompts triviais e não faz validação UI. Agente não controla sessão pessoal, não abre QML windows nela, não toca speakers, nem altera PipeWire/Flatpak global, nem coleta voz, nem faz push/merge/deploy ou mudanças destrutivas. Usar ambiente isolado HOME/XDG, bwrap/containers onde apropriado, áudio virtual, IPC e Qt offscreen, fake services/tools e PCM de fixture autorizado por hash.
## Perfeição possível de provar
"Perfeita antes de avançar" = `AUTO_VERIFIED` rigoroso, sem P0/P1 conhecido no escopo verificável. Wake 99,9%, FAR real, qualidade de TTS, hotplug físico, Wayland portals, mouse real e APIs conectadas não podem ser provados sem ensaios humanos/hardware. Isso fica explicitamente **pendente até a primeira validação consolidada após S5**, sem mentir no relatório.
## Limite de trabalho
O agente pode trabalhar autonomamente enquanto ferramenta/sessão estiver ativa. Se surgir bloqueio externo, continuar casos verificáveis do **mesmo subgate** e reportar parte ainda pendente; se somente o teste físico falta, emitir `AUTO_VERIFIED/PHYSICAL_PENDING` e seguir. Se um erro técnico automação ainda reparável impede o contrato, NÃO pular para próxima etapa.
## Conteúdo mínimo do checkpoint
Etapa/gate ID, branch/HEAD, commits, condições PASS/FAIL e ignored, build identity, resource measurement, blockers/hardware, testes sem ação real, próximo slice. Notion registra decisões duráveis e critérios; Git contém código/testes reais. Não criar repositório remoto nem declarar release sem autorização.
## Critérios de início/fim do projeto
`S1 AUTO_VERIFIED` antes de App; `S2 AUTO_VERIFIED` antes de LLM Plugin; `S3 AUTO_VERIFIED` antes de Skill Engine; `S4 AUTO_VERIFIED` antes de Connections; `S5 AUTO_VERIFIED` = candidato `READY_FOR_HUMAN_VALIDATION`. Uma rodada integrada com usuário vem depois; podem ser necessárias correções e ensaios adicionais antes de beta/GA.
## Retorno de falha
Bug encontrado em S4 que quebra S1: suspender avanço e corrigir integração desde o primeiro gate afetado; manter histórico de bug+teste regressão. Nunca inventar "etapa perfeita" por número alto de testes sem cobertura de uso real.
</content>
</page>
