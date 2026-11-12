# Documentação viva do Legendar

Este diretório mantém na raiz somente documentos que orientam a operação atual, registram decisões vigentes ou conduzem a evolução em andamento.

## Estado e evolução

- [Estado atual](ESTADO_ATUAL.md) — o que está implementado, validado, pendente e em risco.
- [Plano de correção, qualidade e desempenho](PLANO_CORRECAO_MELHORIA.md) — plano mestre de trabalho para corrigir a qualidade do SRT e reduzir o tempo de execução sem perda de qualidade.
- [Plano operacional da Fase 5](FASE_5_PLANO.md) — configuração do faster-whisper, benchmark pareado e critérios de aceite do ASR.
- [Plano operacional da Fase 6](FASE_6_PLANO.md) — Gemini contextual, benchmark pareado com NLLB, segurança e critérios de homologação.

## Referência técnica e operacional

- [Arquitetura](ARQUITETURA.md) — camadas, pipeline, portas, estados e publicação.
- [Operação](OPERACAO.md) — jornada de uso, estados, cancelamento, arquivos e diagnóstico.
- [Instalação](INSTALACAO.md) — requisitos, perfis, instalação, execução e verificação.
- [Homologação](HOMOLOGACAO.md) — roteiro prático com mídia real, hardware e revisão do SRT.
- [Decisões](DECISOES.md) — escolhas consolidadas e pontos ainda em avaliação.
- [Matriz de dependências](MATRIZ_DEPENDENCIAS.md) — manifesto, lock, compatibilidade e candidatos em avaliação.

## Histórico

Planos por fase, handoffs, relatório da Fase 8, plano mestre anterior e baseline legada foram preservados em [archive/README.md](archive/README.md). O histórico não é a fonte de verdade do estado operacional atual; para isso, consulte [ESTADO_ATUAL.md](ESTADO_ATUAL.md).
