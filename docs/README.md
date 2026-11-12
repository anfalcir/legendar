# Documentação viva do Legendar

Este diretório mantém na raiz somente documentos que orientam a operação atual, registram decisões vigentes ou conduzem a evolução em andamento. Planos específicos de fases encerradas, handoffs e relatórios substituídos ficam em `archive/`.

## Estado e evolução

- [Estado atual](ESTADO_ATUAL.md) — fonte de verdade sobre o que está implementado, integrado, validado, pendente e em risco.
- [Plano de correção, qualidade e desempenho](PLANO_CORRECAO_MELHORIA.md) — plano mestre vigente, incluindo a Fase 8 de regressão e homologação real.

## Referência técnica e operacional

- [Arquitetura](ARQUITETURA.md) — camadas, pipeline, portas, estados, recursos e publicação.
- [Operação](OPERACAO.md) — jornada de uso, estados, cancelamento, arquivos e diagnóstico.
- [Instalação](INSTALACAO.md) — requisitos, perfis, instalação, execução e verificação.
- [Homologação](HOMOLOGACAO.md) — roteiro prático com mídia real, hardware, avaliação estrutural e revisão do SRT.
- [Decisões](DECISOES.md) — escolhas consolidadas e pontos ainda em avaliação.
- [Matriz de dependências](MATRIZ_DEPENDENCIAS.md) — manifesto, lock, compatibilidade e candidatos em avaliação.

## Histórico

- [Fases 5 e 6 — planos e registro de homologação](archive/completed-phases/): planos e evidências preservados após encerramento das fases.
- [Remodelação anterior — Fases 0–10](archive/previous-remodeling/): protocolos, planos, handoffs, relatório e baseline da implementação anterior.
- [Índice do arquivo histórico](archive/README.md).

Os documentos arquivados são evidência histórica, não instruções operacionais atuais. Em caso de divergência, prevalecem os documentos vivos e o comportamento integrado à `main`.
