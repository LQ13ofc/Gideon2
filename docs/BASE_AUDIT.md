# Rodada de auditoria S1/B1 — 2026-10-14

Resultado funcional: AUTO_VERIFIED no escopo virtual EN/DEV/offscreen, após
correções e regressão completa no MESMO binário. B2 permaneceu parado. Não foi
feita validação humana, acionamento de áudio/display pessoal, instalação global,
push, deploy ou alteração de legado.

## Problemas e correções

| Área | Problema constatado / contraprova | Correção / evidência |
|---|---|---|
| Captura→STT | Frame válido de 1600 amostras ia inteiro a worker limitado a 1280 | Split 1280+320 sem perda, timestamps exatos; rejeição de PCM antes de enviar; teste Core |
| Transcript | Clock do worker não era limitado ao PCM aceito | Partial não pode estar no futuro; Final precisa cobrir endpoint exato |
| Lifecycle STT | Closure usava sid/state mutáveis da próxima iteração | Bind por sessão, rejeitar callback de stream fechado; SDK adversarial + streaming nativo |
| Callback error | Exceção de callback podia ser engolida pelo SDK | Falha vira pacote recusado pelo protocolo estrito, impedindo Final/ação |
| Storage | Hardlink audit.log >64KiB podia truncar outro inode vinculado | nlink=1 e checagem do descriptor aberto; sentinel privado de teste preservado |
| TTS pack | Lista vazia/incompleta de hashes passava no loop | Quatro artifacts obrigatórios sem duplicação/traversal, engine e paths locais exatos, symlink recusado |
| Deadlines | Executor herdava prazo encurtado do STT; timeout podia ficar sem feedback | Budget próprio limitado ao deadline global; falha de deadline com TTS quando há tempo; late receipt descartado |
| IPC→Qt | Payload aninhado inválido/deep JSON passava pelo envelope | Validação antes de QML, fault injection em socket Qt real, clear/revoke/offline |
| Janela | Minimum viewport deixava transcrição abaixo da altura legível | Minimum height 520 e viewport ≥48; bounds e leitura verificadas em 480×520 e scale 2 |
| Namespace | Wake/STT herdavam ambiente incidental do pai | Ambiente mínimo explícito para todos os workers; fake secret não chega ao namespace |
| Harness | Processo encerrava entre listar filhos e ler cmdline | Sampler tolera desaparecimento; regressão com processo real; não mascara erro de worker |
| Session ID | Seed aleatório podia excepcionalmente ser zero, inválido para cliente | Seed de produção sempre positivo; u64 continua string em QML |

As contraprovas de callback/IPC/manifesto são testes adversariais controlados,
não alegação de incidente físico. Inferência real e efeitos reais em namespace
foram reexecutados; estes testes não substituem o E2E por mocks. Não se observou
exportação de segredo real; teste de ambiente usa apenas sentinel autorizado.

Commits de código: 82c8783 (Base), 8b16886 (App), 2ad4338 (harness). Evidência
source→binary e recursos: docs/evidence/base-audit.json. Não misturar resultados
de compilações: todos os nove grupos têm o SHA do binário final em comum.

## Verificação

- fmt/check/test/clippy -D warnings/release/diff-check PASS.
- 32 testes Rust; 5 nativos de wake; 7 testes adversariais adicionais (callback,
  preflight TTS, sockets Qt, processo encerrado). Zero ignored.
- A0/A1/A2/A3/A4/A5: 32/44/33/67/138/93 verificações de processo.
- Soak de dois ciclos no mesmo daemon: 8; shutdown após PCM: 2.
- B1: 34 verificações, incluindo voz completa, keyboard Cancel, restart/reconnect,
  watchdog SIGSTOP/SIGCONT, HiDPI/acessibilidade e minimum readable viewport.
- Snapshot offscreen inspecionado; toda renderização em namespace/software.
- Legado revisto somente-leitura com GIT_OPTIONAL_LOCKS=0: mesmo ef0a0f3,
  51 entradas dirty/untracked e 12 worktrees.

Não afirmar "zero bugs" por essa amostragem. Os problemas encontrados no escopo
foram corrigidos e os testes finais passaram; os limites abaixo continuam abertos.

## Preparação gráfica entregue

[Mapa da Base para S2](BASE_UI_MAP.md) contém fluxo Mermaid, ownership por arquivo,
FSM/erros ortogonais, dicionário de IPC, perfis/capabilities reais, privacidade,
catálogo/wake e dependências B2/B3/B4. Graphify AST atualizado: 545 nós/1104 arestas.
QML não é indexado por Graphify: foi revisado por fonte e runtime offscreen.
A UI não deve criar autoridade, inventar features nem confundir efeito concluído
com TTS concluído. Não há Model Manager geral ou página LLM na Base.

## Condições para prosseguir

B2 pode ser desenvolvido no perfil virtual suportado usando o mapa e o MESMO
Core, após esta rodada; nenhuma nova implementação B2 foi iniciada aqui.
Ainda são necessários discovery e update/rollback de config pelo backend;
persistência atômica/aplicação não deve ser inventada no cliente. Hub e pacote
vêm em sequência, sem publicar ou instalar na sessão pessoal.

Desempenho não está congelado: cold start de Pocket continua em segundos, e pico
RSS da árvore própria é alto (~1.5GB; páginas compartilhadas somadas). Os valores
atuais exatos e o idle pós-EOF estão no JSON. Parakeet/Piper/Kokoro ainda precisam
comparação antes de escolha definitiva; corpus independente/pt-BR não aprovados.

CPAL/PipeWire, AEC, hotplug/barge-in e pacote relocável são pendências de
IMPLEMENTAÇÃO. Qualidade acústica, periféricos e Wayland reais são
AWAITING_HUMAN_VALIDATION, somente na rodada consolidada após S5. Não declarar
prontidão de uso real antes de fechar ambos. S1 aprovado em virtual não significa
que conectar um microfone hoje produzirá o produto completo.
