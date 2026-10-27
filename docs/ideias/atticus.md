# Ideias novas: Atticus (pesquisado em 2026-10-26)

Status: BACKLOG. Nada daqui entra antes de o Core estar 100% funcional (decisão do dono, 2026-10-26).

## O que é
Assistente de voz de apertar-e-falar para Mac (existe versão Windows), gratuito e de código aberto, lançado por volta de 2026-10-14 por um estudante secundarista (Saarth). Segura Ctrl+Option+Espaço, fala, solta. Transcrição no aparelho; sem chave de API (usa o plano Claude/Devin do usuário).

## Funcionalidades que o Gideon não tem

| Ideia | Descrição | Já temos de base | Custo estimado |
|---|---|---|---|
| Ditado global | Segurar tecla, falar, texto limpo vai para o campo em foco | Atalho push-to-talk, Parakeet (STT) | M |
| Agentes em segundo plano | Tarefas grandes rodam enquanto o usuário continua | Agente C3, fila N-5 | M |
| Atalhos aprendidos | Pedido repetido vira skill sugerida (aprovada pelo usuário) e roda sem IA | Skills, LLM local, aprovação | M |
| Apontar na tela | "Onde eu clico?" marca o ponto na tela; diagramas com rótulos; perguntas sobre o que está na tela | Captura de tela, árvore AT-SPI | M a L |
| Copiloto de reunião | Responde e anota durante chamadas, notas salvas localmente | Áudio ao vivo, STT, Memória | L (privacidade: gravar chamadas) |
| Rascunho de email | Lê o email na tela e escreve a resposta, nunca envia | Captura de tela, LLM | S a M |
| Compras e formulários | Preenche formulários e compra, sempre confirmando antes | Ações reais com confirmação | L |
| Lista de bloqueio explícita | rm, sudo, ferramentas de disco e desligamento sempre bloqueados | Sandbox, níveis de risco | S |
| Latência de comando medida | Meta: abrir app em menos de 0,1 s sem IA | Comandos sem LLM | S |

## Ordem sugerida (depois do Core completo)
1. Ditado global
2. Agentes em segundo plano
3. Atalhos aprendidos
4. Apontar na tela
5. Copiloto de reunião e rascunho de email

## Fontes
- https://www.producthunt.com/products/atticus
- https://github.com/SaarthurR/atticus-mac
- https://github.com/FindlayHi/atticus-windows
- https://news.ycombinator.com/item?id=50049588
- https://alternativeto.net/software/atticus-for-mac/about/
- https://completeaitraining.com/news/atticus-adds-voice-controlled-desktop-actions-to-claude-on/

Nota: a busca achou outros produtos chamados Atticus (software de formatação de livros; "advogado interno" com IA); não são o alvo.
