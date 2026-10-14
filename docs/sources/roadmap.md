Here is the result of "fetch" for the Page with URL https://app.notion.com/p/3f852661c75181018fafd8395bebf11a as of 2026-10-13T21:26:12.268Z:
<page url="https://app.notion.com/p/3f852661c75181018fafd8395bebf11a" icon="🗺️">
<ancestor-path>
<parent-page url="https://app.notion.com/p/3f852661c751813fa040d7cd3611ad96" title="Gideon — Desenvolvimento (S1–S5)"/>
<ancestor-2-page url="https://app.notion.com/p/3f452661c7518107b6ecd81411f4cc44" title="Gideon — Wiki"/>
</ancestor-path>
<properties>
{"title":"Roadmap oficial — cinco sequências integradas (S1–S5)"}
</properties>
<iconMetadata>{"type":"emoji","emoji":"🗺️"}</iconMetadata>
<content>
> **Roadmap oficial do Gideon — cinco sequências verticais, um único produto.**
> **Planejamento aprovado; nenhuma conclusão de implementação pode ser presumida sem Git/testes da nova árvore.**
## Regra de execução
S1 → S2 → S3 → S4 → S5. Dentro da sequência, **um subgate por vez**: definir contrato mínimo → implementar no projeto existente → testar integração com tudo que veio antes → corrigir erros → registrar evidência → `AUTO_VERIFIED` → próximo passo. Nenhuma POC isolada serve como produto pronto. Cross-cutting Safety, logging, cancelamento e configuração existem somente na dimensão necessária ao passo atual.
## S1 — Base: dar vida (A0–A5)
**Fluxo:** “Hey Gideon” → detectar wake → pre-roll/captura → transcrição ao falar, com parciais → decisão/execução de **comando determinístico** → verificar ação → resposta TTS.
- **A0:** Core, áudio virtual/real desacoplado, sessões, policies, estado e testes básicos.
- **A1:** wake detectado por engine inicial certificada, filtro de falsos wakes e baixo consumo em idle.
- **A2:** captura da fala a partir do wake, bounded ring pre-roll, VAD/timeout, cancelamento.
- **A3:** STT streaming integrado A1–A2, partial/final, unknown/no speech, nada executado por partial inseguro.
- **A4:** comandos como abrir app, hora, volume/mute/cancel; argumento tipado, Safety e verificação do executor; negações, ambiguidade e fora de escopo não acionam.
- **A5:** fala/som de resposta com resultado real, erros e cancelamento; E2E A1→A5 usando PCM autorizado e virtual sink.
**Gate S1:** suite headless real com wake→STT→comando→TTS, ações apenas no sandbox, falhas e restart/cancel; **sem LLM, sem app e sem Model Manager**. Qualificação física da voz permanece pendente.
[Especificação S1](https://app.notion.com/p/3f852661c751819c90e3e076da45a433).
## S2 — App: dar rosto (B1–B4)
- **B1:** HUD/QML e estados reais Core→UI, transcrição e feedback; cancelamento, reconnect/recovery, entrada de texto para teste.
- **B2:** Voice Settings para wake phrases **suportadas** pela engine, dispositivos, voz, sons, sensitividade, idioma, aparência, consumo; config persistente sem editar arquivos manualmente.
- **B3:** **Gideon Hub** usa catálogo GitHub de componentes versionados, instalados sob demanda com checksum, dependencies, compatibilidade e permissões; sem auto-instalar plugins/skills.
- **B4:** pacote Linux com Core+App+Base funcional, startup/recovery/update/rollback sem alterar host pessoal.
**Gate S2:** mesmo fluxo completo S1 controlável/observável pelo App + instalação/removal fictícia do Hub em namespace isolado; regressão S1.
[Especificação S2](https://app.notion.com/p/3f852661c75181e58361e8046a9b23b6).
## S3 — Plugins: ganhar inteligência e capacidades (C0–C4)
- **C0:** runtime/SDK de plugins, capability registry, permissões e sandbox por componente, ativar/desinstalar/revogar.
- **C1:** primeiro plugin **LLM Engine**, opcional; sem ele S1 continua operante.
- **C2:** **único gerenciador de modelos do Gideon = LLM Model Manager**, *somente dentro do plugin LLM*: modelos locais/remotos, recomendados/certificados e personalizados, capacidade real de tool-use/vision, privacy/cost/compute budgets, escolha manual e fallback autorizado.
- **C3:** Agent Runtime com observe→plan→act→verify, ferramentas tipadas, limites, confirmação e interrupção.
- **C4:** acrescentar isoladamente tela/visão, mouse/teclado, áudio avançado, microfone avançado, gestos de webcam e manipulação da imagem pré-display **somente quando compositor/API suportar**, nessa ordem de estudo e integração. Funcionalidade específica impossível no host não pode se passar por universal.
**Gate S3:** instalar LLM, escolher modelo, agente usar ferramenta autoritativa em sandbox, adicionar/desativar plugin sem quebrar voz e App; não confundir replay com Wayland/áudio físico.
[Especificação S3](https://app.notion.com/p/3f852661c75181a4a8f1ffd1450e2196) · [Política LLM](https://app.notion.com/p/3f852661c751812a96e5f2f4e9a69007).
## S4 — Sistema de Skills: ensinar (D1–D4)
- **D1:** formato declarativo, dependências e permissões, schema/versionamento.
- **D2:** executor testável com steps, preconditions, resultados, rollback e cancelamento.
- **D3:** agente LLM propõe Skill (Draft), valida/dry-run/preview, nunca autoaprova ou amplia grants.
- **D4:** importar/exportar e compartilhar Skill com amigos via arquivo/URL/catálogo GitHub no Hub, com hashes, autores, licenças, revisão de permissões e isolamento entre usuários.
**Gate S4:** perfil sintético A cria/exporta, B instala, verifica dependências, autoriza em simulação e executa; **não criar coleção de Skills prontas**, apenas o mecanismo e fixtures QA.
[Especificação S4](https://app.notion.com/p/3f852661c751819ca755f96eb12b1993).
## S5 — Connections: conectar serviços (E1–E4)
- **E1:** contas/providers, OAuth/scopes, segredo protegido, lifecycle/revocation, APIs tipadas.
- **E2:** integração progressiva GitHub, Google Gmail/Calendar/Drive, Home Assistant e MCP, **uma por vez**, APIs fake antes de credenciais reais.
- **E3:** agente/Skills preferem API estruturada autorizada a cliques no navegador; fallback visual exige autorização própria.
- **E4:** pacote Linux final integrado S1–S5, E2E cross-component com identidade de build, rollback/restart, logs, segurança, orçamento de CPU/RAM, perfis e modo offline.
**Gate S5:** `READY_FOR_HUMAN_VALIDATION` somente após cenários automatizados de todos os fluxos executáveis, com lista de pendências físicas/credenciais reais honesta.
[Especificação S5](https://app.notion.com/p/3f852661c751815e8dbbda86fa71c47e).
## Regras globais
**Sem teste humano intermediário.** Não usar microfone/áudio/visual/teclado/contas reais nem instalar na sessão pessoal durante desenvolvimento. Provar em HOME/XDG isolado, virtual audio, fixtures autorizadas, Qt offscreen, fake tools e APIs simuladas. Sem push/merge/deploy/remoção destrutiva sem consentimento.
**“Perfeita antes da próxima”** = `AUTO_VERIFIED` em todo comportamento verificável e sem bug crítico conhecido, não alegação impossível de 99,9% de wake antes de medição física. Só após S5 propor uma rodada humana consolidada. Uma falha nessa rodada volta ao subgate correto.
**Escopos pendentes:** Memory/Soul/Habits pessoais, automações duráveis, sync multiplataforma e funcionalidades experimentais continuam no backlog até nova decisão; não entram automaticamente entre S1 e S5.
[Critérios completos de aprovação](https://app.notion.com/p/3f852661c75181cc92c8d18bd203335d) · [Decisões vigentes](https://app.notion.com/p/3f852661c751819aaf36e0a147be2137).
## Estado atual
`S1–S5: PLANNED`. Próxima ação de engenharia segura: iniciar **A0**, definir contratos do fluxo mínimo e reconciliar evidências do repositório antigo sem alterá-lo. Notion representa a intenção, Git verifica implementação. Não atribuir estado AUTO_VERIFIED sem testes do código novo.
</content>
</page>
