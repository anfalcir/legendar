# Handoff técnico — Fase 2: Interface profissional

- **Projeto:** Legendar
- **Atualização:** 10/11/2026
- **Fase 0:** concluída e integrada à `main`
- **Fase 1:** concluída, validada e integrada à `main` pela PR #2, commit `de31ddd`
- **Fase 2:** implementação concluída e validada; PR #3 aguardando integração
- **Branch de implementação:** `phase-2/professional-ui`
- **Base:** `main` com Fases 0 e 1 integradas
- **CI final:** [run #42911438434](https://github.com/anfalcir/legendar/actions/runs/42911438434)

Este handoff registra o que foi alterado e as fronteiras preservadas. A implementação foi feita sobre a branch dedicada; não houve mudanças diretas na `main` durante a execução. A Fase 3 permanece bloqueada até aprovação explícita do responsável.

## 1. Entregas

### Sistema visual e composição
- Identidade visual própria com temas claro, escuro e sistema.
- Componentes QSS reutilizáveis: cabeçalho, painéis, campos, botões primário/secundário/perigo, estados disabled, hover e foco visível.
- Janela principal reorganizada em cartões, com cabeçalho, estado geral, origem, idiomas, destino, ações, progresso, atividade e estado de prontidão.
- Conteúdo dentro de área de rolagem vertical para manter acessibilidade em janela menor; teste em 680×620.
- Estados e áreas com nomes acessíveis e sequência de tabulação explícita.

### Confirmações e proteção contra ações acidentais
- Diálogo modal de confirmação antes de iniciar, com mídia, idiomas e destino.
- Substituição de saída existente exige confirmação separada; padrão seguro é Não.
- Cancelamento exige confirmação; padrão seguro é Não.
- Guardas contra início reentrante/clique repetido e contra múltiplos pedidos de cancelamento.
- O worker devolve a decisão real do controlador. Se a publicação já começou e o controlador rejeita o cancelamento, a UI informa que a etapa não pode ser interrompida, sem alegar sucesso.
- Campos e preferências ficam desabilitados enquanto a thread trabalha e são reabilitados após o término.

### Progresso, atividade e preferências
- Barra indeterminada enquanto não existe métrica e percentual apenas após evento real.
- Animação indeterminada termina em estados terminais sem percentual.
- Log recolhível com timestamps locais, avisos/erros/conclusão, limite de linhas e rolagem não intrusiva.
- QSettings persiste tema, idioma final, diretório de saída, estado do log e geometria.
- Caminhos de mídia, transcrições e credenciais não são persistidos.

## 2. Validação

Workflow [Phase 1 quality #42911438434](https://github.com/anfalcir/legendar/actions/runs/42911438434), executado sobre a branch de Fase 2, aprovado em 4/4 ambientes:

| Python | Resultado |
|---|---|
| 3.10 | 218 testes; cobertura 88%; Ruff/format verdes |
| 3.11 | 218 testes; cobertura 88%; Ruff/format verdes |
| 3.12 | 218 testes; cobertura 88%; Ruff/format verdes |
| 3.13 | 218 testes; cobertura 88%; Ruff/format verdes |

A suíte tem 2.480 statements e 88% de cobertura. Ruff check e `ruff format --check` passaram; 91 arquivos estavam formatados. Os testes Qt executaram com plataforma offscreen.

## 3. Fronteiras preservadas

- Nenhuma integração real YouTube/FFmpeg, Whisper/WhisperX ou tradução de fornecedor foi implementada.
- Nenhum processamento de mídia roda na thread principal; o worker continua executando na QThread.
- O controlador e a máquina de estados da Fase 1 continuam sendo a autoridade para cancelamento e publicação.
- A publicação continua sendo etapa não cancelável.
- A baseline legada em `main.py`, `core/` e `gui/` continua preservada e caracterizada.
- Não foram introduzidos novos grupos de dependência runtime nem modificações no lock.

## 4. Limitações e homologação remanescente

Os testes cobrem temas, diálogos, preferências, estados, confirmações, clique reentrante, cancelamento, tabulação, rolagem e janela estreita em Qt offscreen. Eles não substituem a inspeção visual manual em monitores físicos, scaling HiDPI, diferentes gerenciadores de janela ou os sistemas operacionais declarados para homologação. Essa prova pertence à Fase 8.

O pipeline real permanece explicitamente pendente até a Fase 3. O botão principal nesta fase demonstra o ciclo de vida com portas/fakes nos testes, mas não baixa nem transcreve mídia real.

## 5. Próximo marco

A Fase 2 está tecnicamente concluída e validada; a integração à `main` será feita pela PR #3 após revisão dos gates verdes. Não iniciar a Fase 3 sem aprovação explícita do responsável.

## 6. Documentos relacionados

- [Plano mestre](PLANO_REMODELAGEM.md)
- [Estado atual](ESTADO_ATUAL.md)
- [Plano operacional da Fase 2](FASE_2_PLANO.md)
- [Plano operacional da Fase 1](FASE_1_PLANO.md)
- [Baseline legada](LEGACY_BASELINE.md)
- [Handoff da Fase 1](HANDOFF_FASE_1.md)
