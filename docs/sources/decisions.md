Here is the result of "fetch" for the Page with URL https://app.notion.com/p/3f852661c751819aaf36e0a147be2137 as of 2026-10-13T21:26:45.121Z:
<page url="https://app.notion.com/p/3f852661c751819aaf36e0a147be2137" icon="✅">
<ancestor-path>
<parent-page url="https://app.notion.com/p/3f452661c7518107b6ecd81411f4cc44" title="Gideon — Wiki"/>
</ancestor-path>
<properties>
{"title":"Decisões vigentes"}
</properties>
<iconMetadata>{"type":"emoji","emoji":"✅"}</iconMetadata>
<content>
**Fonte de decisões atuais.** O histórico integral de decisões anteriores foi preservado no Arquivo. Esta página registra apenas decisões que orientam a implementação corrente.
## D01 · Uma linha vertical, não quatro/cinco projetos
**ACCEPTED — 13/10/2026.** O mesmo Gideon evolui em ordem obrigatória: S1 Base (wake/captura/STT/comando/TTS) → S2 App/Hub → S3 Plugins (LLM Engine primeiro) → S4 sistema de criação/compartilhamento de Skills → S5 Connections. Um subgate só avança após integração e testes automáticos do fluxo existente. Sem peças isoladas para juntar depois.
## D02 · Voz na Base, LLM opcional
**ACCEPTED.** S1 funciona sem LLM ou rede para comandos determinísticos. Motores de Wake/STT/TTS são componentes internos certificados/versionados da Base. **Não existe Model Manager geral**. Configuração de frases suportadas, voz, feedback e devices em S2. Escolha de provedor/modelo **apenas para LLMs**, dentro do plugin LLM Engine opcional de S3.
## D03 · Modelos LLM escolhidos pelo usuário
**ACCEPTED.** Plugin LLM tem opções Local / Nuvem, modelo/provider fixo e roteamento automático somente entre alternativas autorizadas. Modelos locais recomendados/certificados pela equipe + aba de modelos personalizados compatíveis, com capacidades e limitações reais (tool use, contexto, streaming, visão, memória/VRAM etc.). Sem fallback silencioso que exporte dados privados.
## D04 · Plugins, Skills e Connections separados
**ACCEPTED.** Plugins dão capacidades; Skills são procedimentos que combinam capacidades disponíveis, podendo ser criados por agente e usuários, exportados/compartilhados pelo Hub; Connections são APIs/contas externas (GitHub, Google, Home Assistant, MCP). Não criar catálogo de skills oficiais — somente engine e fixtures de testes. Preferir integração API autorizada a clique visual.
## D05 · Segurança e privacidade
**ACCEPTED.** Core autoritativo, capabilities tipadas, SafetyManager, scope/grants, confirmação de risco, execução verificável e cancelamento. Plugin/modelo/skill não aumenta privilégios. Dados, chaves e voz não são compartilhados sem consentimento; usuários separados; perfis de hardware modestos. Linux KDE Wayland prioritário.
## D06 · Sem ações ou testes humanos no desenvolvimento
**ACCEPTED.** Não solicitar ao usuário testes intermediários, clipes, interação com PC, microfone, instalação, permissões, credenciais ou decisões triviais. Testar com fixtures autorizadas, ambiente virtual e UI offscreen isolados. Só depois de S5 tecnicamente integrado propor uma rodada humana consolidada. AUTO_VERIFIED não significa precisão acústica/hardware validada.
## D07 · Preservar aprendizado sem carregar arquitetura antiga
**ACCEPTED.** Começar a construção como primeira implementação conhecendo os benchmarks, falhas e decisões anteriores. Manter worktrees/datasets/QA íntegros. Nada de apagar histórico, push/deploy/merge destrutivo ou mudar sessão pessoal.
## D08 · O que ainda precisa de decisão
Memória/Habits/Souls, automações agendadas, sincronização privada, recursos espaciais e plataformas adicionais têm documentação histórica, **mas nenhum encaixe obrigatório aprovado nas cinco sequências atuais**. Não adicioná-los silenciosamente.
## Fontes
<mention-page url="https://app.notion.com/p/3f852661c75181018fafd8395bebf11a"/> · <mention-page url="https://app.notion.com/p/3f852661c751812a96e5f2f4e9a69007"/> · <mention-page url="https://app.notion.com/p/3f852661c75181cc92c8d18bd203335d"/>.
**Regra:** qualquer mudança de decisão aprovada deve atualizar esta página e a documentação proprietária; decisões antigas permanecem no arquivo, com motivo de supersessão.
</content>
</page>
