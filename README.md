# Legendar

Aplicação desktop para transcrever áudio de vídeos, alinhar a fala ao tempo da mídia e produzir legendas SRT, com tradução opcional para inglês ou português brasileiro.

A remodelagem é executada por fases. As Fases 0–4 estão validadas e integradas à `main`; a Fase 5 — alinhamento temporal com WhisperX — está em implementação na branch `phase-5/temporal-alignment`. A Fase 4 foi integrada por squash pela PR [#5](https://github.com/anfalcir/legendar/pull/5), commit `2f9751139616591e31a0ec73902265b38b040d41`. A Fase 5 distingue janelas aproximadas do Whisper de timestamps finais alinhados, preserva palavras sem alinhamento e acrescenta avaliação temporal contra referências humanas. A homologação no computador-alvo e com pregações permanece gate de produto. A aplicação anterior permanece preservada como baseline.

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

## Direção do produto

- Entrada por URL do YouTube ou arquivos locais de áudio e vídeo.
- Whisper como motor central de reconhecimento de fala.
- Alinhamento temporal refinado por palavra.
- Segmentação e tradução contextual para inglês ou português brasileiro.
- Exportação de legendas SRT.
- Interface desktop em PySide6, com processamento em segundo plano, progresso, logs e cancelamento controlado.

Consulte o [plano de remodelagem](docs/PLANO_REMODELAGEM.md) para distinguir funcionalidades planejadas das que já foram implementadas.

## Estado da implementação atual

A aplicação anterior em `main.py`, `core/` e `gui/` permanece preservada como baseline de compatibilidade, com contratos caracterizados. A `main` contém as Fases 0–4 integradas; a Fase 5 está em desenvolvimento na branch `phase-5/temporal-alignment`, conectando forced alignment WhisperX à transcrição local da Fase 4. A saída ainda não é SRT final; tradução, segmentação editorial e publicação permanecem nas Fases 6/7. O botão de geração final segue bloqueado enquanto não há publicador SRT. Consulte [docs/ESTADO_ATUAL.md](docs/ESTADO_ATUAL.md), [docs/FASE_5_PLANO.md](docs/FASE_5_PLANO.md) e [docs/HANDOFF_FASE_5.md](docs/HANDOFF_FASE_5.md).

## Licença

O projeto é tratado como MIT. Consulte o arquivo LICENSE e preserve os avisos de copyright e licença aplicáveis.
