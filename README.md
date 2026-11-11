# Legendar

Aplicação desktop para transcrever áudio de vídeos, alinhar a fala ao tempo da mídia e produzir legendas SRT, com tradução opcional para inglês ou português brasileiro.

A remodelagem é executada por fases. As Fases 0–8 estão implementadas, validadas por CI e integradas à `main`. A Fase 6 entregou a segmentação editorial de duas linhas, a tradução local por cue com NLLB-200 distilled 600M, a validação do trilho e a publicação SRT atômica com roundtrip; seu CI de push passou 5/5 jobs. A Fase 7 conectou a janela ao pipeline real: o botão de geração dispara o trabalho em `QThread`, com progresso honesto, cancelamento cooperativo, log recolhível, recuperação de erro e abertura da pasta do SRT publicado. A Fase 8 consolidou a matriz de testes — quatro pares de idioma, modos de falha, cancelamento e mídia real em seis formatos — com 443 testes aprovados e 86% de cobertura no ambiente com FFmpeg. A precisão temporal e a qualidade tradutória em pregações, no computador-alvo, continuam como gates de homologação do produto. A aplicação anterior permanece preservada como baseline.

## Documentação do projeto

- [Plano mestre de remodelagem](docs/PLANO_REMODELAGEM.md) — visão do produto, requisitos, arquitetura, pipeline de sincronização, fases e critérios de aceite.
- [Estado atual](docs/ESTADO_ATUAL.md) — documento vivo com o que existe, o que está em andamento, decisões, testes, riscos e próximos passos.
- [Protocolo da Fase 0](docs/FASE_0_PROTOCOLO.md) — inventário do ambiente, experimentos, métricas, evidências e critérios para a prova técnica.
- [Matriz de dependências](docs/MATRIZ_DEPENDENCIAS.md) — fonte canônica, faixas de versões, dependências externas, perfis de hardware e política de compatibilidade.
- [Plano operacional da Fase 1](docs/FASE_1_PLANO.md) — etapas, evidências e critérios de conclusão da reestruturação.
- [Baseline legada](docs/LEGACY_BASELINE.md) — contratos caracterizados, limitações e política de migração da aplicação anterior.
- [Handoff da Fase 1](docs/HANDOFF_FASE_1.md) — arquitetura, critérios e decisões de migração.
- [Plano operacional da Fase 2](docs/FASE_2_PLANO.md) — identidade visual, UX, confirmações, preferências e critérios de validação da interface profissional.
- [Handoff da Fase 2](docs/HANDOFF_FASE_2.md) — implementação, evidências de CI, limitações e próximos gates.
- [Plano operacional da Fase 3](docs/FASE_3_PLANO.md) — escopo, decisões de mídia, critérios de aceite e gates de CI.
- [Handoff da Fase 3](docs/HANDOFF_FASE_3.md) — arquitetura implementada, evidências, riscos e próximos passos.
- [Plano operacional da Fase 4](docs/FASE_4_PLANO.md) — reconhecimento local, perfis Whisper, cache, métricas e critérios de aceite.
- [Handoff da Fase 4](docs/HANDOFF_FASE_4.md) — arquitetura implementada, testes, benchmark e gates de homologação.
- [Plano operacional da Fase 5](docs/FASE_5_PLANO.md) — WhisperX, janelas, offsets, métricas e avaliação temporal.
- [Handoff da Fase 5](docs/HANDOFF_FASE_5.md) — adaptador, cache, diagnósticos, testes e homologação.
- [Plano operacional da Fase 6](docs/FASE_6_PLANO.md) — segmentação editorial, tradução por cue, validação e publicação SRT.
- [Handoff da Fase 6](docs/HANDOFF_FASE_6.md) — contratos, regras congeladas, runtime NLLB, testes e limites conhecidos.
- [Plano operacional da Fase 7](docs/FASE_7_PLANO.md) — integração da GUI ao pipeline, progresso, cancelamento, log e recuperação.
- [Handoff da Fase 7](docs/HANDOFF_FASE_7.md) — modelo de threads, estados, encerramento seguro, resultado publicado e testes.
- [Plano operacional da Fase 8](docs/FASE_8_PLANO.md) — matriz de testes, E2E, mídia real, falhas e gates de CI.
- [Handoff da Fase 8](docs/HANDOFF_FASE_8.md) — contratos de teste, comandos e limites da homologação automatizada.
- [Relatório da Fase 8](docs/RELATORIO_FASE_8.md) — evidências medidas, cobertura, riscos residuais e pendências humanas.

## Direção do produto

- Entrada por URL do YouTube ou arquivos locais de áudio e vídeo.
- Whisper como motor central de reconhecimento de fala.
- Alinhamento temporal refinado por palavra.
- Segmentação e tradução contextual para inglês ou português brasileiro.
- Exportação de legendas SRT.
- Interface desktop em PySide6, com processamento em segundo plano, progresso, logs e cancelamento controlado.

Consulte o [plano de remodelagem](docs/PLANO_REMODELAGEM.md) para distinguir funcionalidades planejadas das que já foram implementadas.

## Estado da implementação atual

A aplicação anterior em `main.py`, `core/` e `gui/` permanece preservada como baseline de compatibilidade, com contratos caracterizados. A `main` contém as Fases 0–7 integradas. O fluxo atual cobre entrada local/YouTube, inspeção e normalização de mídia, transcrição Whisper, alinhamento WhisperX por palavra, segmentação de duas linhas, tradução local PT↔EN por cue, validação do trilho e publicação SRT atômica — tudo disparado pela janela com progresso, cancelamento e recuperação controlados. Consulte [docs/ESTADO_ATUAL.md](docs/ESTADO_ATUAL.md) para o estado vivo e [docs/FASE_7_PLANO.md](docs/FASE_7_PLANO.md) para a integração da interface.

## Licença

O projeto é tratado como MIT. Consulte o arquivo LICENSE e preserve os avisos de copyright e licença aplicáveis.
