Here is the result of "fetch" for the Page with URL https://app.notion.com/p/3f852661c751813fa040d7cd3611ad96 as of 2026-10-13T21:26:59.188Z:
<page url="https://app.notion.com/p/3f852661c751813fa040d7cd3611ad96" icon="🚀">
<ancestor-path>
<parent-page url="https://app.notion.com/p/3f452661c7518107b6ecd81411f4cc44" title="Gideon — Wiki"/>
</ancestor-path>
<properties>
{"title":"Gideon — Desenvolvimento (S1–S5)"}
</properties>
<iconMetadata>{"type":"emoji","emoji":"🚀"}</iconMetadata>
<content>
> **Um único Gideon, evoluindo por funcionalidades integradas.**
> **Estado documentado: planejamento aprovado; implementação nova não comprovada neste Notion.**
## Objetivo e método
Começamos pelo fluxo mínimo que funciona de ponta a ponta, não por múltiplos componentes separados. Dentro de cada sequência: **contrato mínimo → implementar → integrar no fluxo existente → testar positivo/negativo → corrigir → regressão completa → AUTO_VERIFIED → avançar**. Não pular gates. Qualidade física exige teste humano posterior; não declarar perfeição apenas com replays.
## Cinco sequências obrigatórias
**S1 — Base:** “Hey Gideon” → escuta/pre-roll → STT em streaming → comandos determinísticos autorizados/verificados → TTS e feedback. Sem LLM e **sem gerenciador de modelos**.
**S2 — App e Gideon Hub:** HUD e configuração de wake suportado, dispositivos, sons/feedback e privacidade; catálogo GitHub para instalar/desinstalar extensões sob demanda, nunca automaticamente.
**S3 — Plugins:** primeiro **LLM Engine**, único componente com **gerenciador de modelos de LLM** (recomendados certificados ou personalizados, locais/nuvem); depois capacidades de tela, mouse/teclado, áudio avançado, microfone, webcam/gestos, manipulação visual de display quando suportada. Um plugin por vez.
**S4 — Sistema de Skills:** criar engine e ferramentas de criação, teste, revisão, execução, exportação e compartilhamento de skills criadas por usuários/agentes; **não criar catálogo de skills prontas**.
**S5 — Connections:** integrações por API com GitHub, Google, Home Assistant, MCP e demais serviços aprovados, uma por vez; preferir API autorizada a automação visual frágil.
## Regras transversais
Core autoritativo, Safety/Capability Manager e grants por ação; plugins, Skills e LLM não fornecem permissões. Processos e estados com cancelamento e recuperação, logs e recursos limitados, baixo impacto idle, privacidade e isolamento por usuário.
**Human freeze:** não solicitar testes, clipes, aparelhos, conta, alteração de host nem interferir na sessão pessoal durante S1–S5; usar virtual audio, fixtures autorizadas, Qt offscreen, HOME/XDG e serviços fake. Marcar `AUTO_VERIFIED` versus `AWAITING_HUMAN_VALIDATION`. A primeira rodada humana consolidada será proposta **depois** de uma build integrada S1–S5 tecnicamente pronta. Não push, merge, deploy ou operação destrutiva sem autorização.
## Documento de execução — ler por demanda
**Fonte principal (ler no bootstrap):**
<page url="https://app.notion.com/p/3f852661c75181018fafd8395bebf11a">Roadmap oficial — cinco sequências integradas (S1–S5)</page>
**Leia somente a sequência em curso:**
<page url="https://app.notion.com/p/3f852661c751819c90e3e076da45a433">S1 · Gideon Base — wake, STT, comandos e TTS</page>
<page url="https://app.notion.com/p/3f852661c75181e58361e8046a9b23b6">S2 · Gideon App e Hub</page>
<page url="https://app.notion.com/p/3f852661c75181a4a8f1ffd1450e2196">S3 · Plugins e LLM Engine</page>
<page url="https://app.notion.com/p/3f852661c751819ca755f96eb12b1993">S4 · Skill Engine e compartilhamento</page>
<page url="https://app.notion.com/p/3f852661c751815e8dbbda86fa71c47e">S5 · Connections e integrações</page>
**Regras obrigatórias transversais:**
<page url="https://app.notion.com/p/3f852661c751812a96e5f2f4e9a69007">Política — Modelos LLM (somente plugin)</page>
<page url="https://app.notion.com/p/3f852661c75181cc92c8d18bd203335d">Qualidade — gates e testes sem intervenção humana</page>
## Assuntos conscientemente fora do ciclo obrigatório
Memory pessoal, Souls, Habits, automações agendadas, sincronização e plataformas adicionais não foram posicionados nas sequências atuais. Preservados no backlog/arquivo; não adicionar silenciosamente. Tecnologias específicas e números de benchmarks herdados devem ser reavaliados quando usados.
## Estado e manutenção
Checkpoint curto em `docs/AGENT_STATE.md` do projeto de código, contendo etapa/commit/testes/bloqueios/próximo. Não pedir novo prompt a cada microetapa enquanto houver sessão e trabalho seguro. Notion documenta decisões; jamais marcar feature concluída sem evidência Git.
</content>
</page>
