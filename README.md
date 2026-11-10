# Legendar

Aplicação desktop para transcrever áudio de vídeos, alinhar a fala ao tempo da mídia e produzir legendas SRT, com tradução opcional para inglês ou português brasileiro.

A remodelagem está em execução por fases. As Fases 0, 1 e 2 foram implementadas, validadas e integradas à `main` pelas PRs #1–#3. A Fase 3 está em desenvolvimento na branch `phase-3/media-ingestion`: entrada local/YouTube, ffprobe, seleção de faixa e normalização FFmpeg já foram implementados, mas a validação final da CI e a integração por PR ainda estão pendentes. A aplicação anterior permanece preservada como baseline. Whisper/WhisperX, tradução e publicação SRT continuam nas fases posteriores.

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

## Direção do produto

- Entrada por URL do YouTube ou arquivos locais de áudio e vídeo.
- Whisper como motor central de reconhecimento de fala.
- Alinhamento temporal refinado por palavra.
- Segmentação e tradução contextual para inglês ou português brasileiro.
- Exportação de legendas SRT.
- Interface desktop em PySide6, com processamento em segundo plano, progresso, logs e cancelamento controlado.

Consulte o [plano de remodelagem](docs/PLANO_REMODELAGEM.md) para distinguir funcionalidades planejadas das que já foram implementadas.

## Estado da implementação atual

A aplicação anterior em `main.py`, `core/` e `gui/` permanece preservada como baseline de compatibilidade, com contratos caracterizados. A `main` contém as Fases 0–2 integradas. Na branch `phase-3/media-ingestion`, a nova arquitetura já possui adaptadores concretos para ffprobe, FFmpeg e yt-dlp, seleção de faixa local e inspeção assíncrona; essa implementação ainda aguarda CI final e integração por PR. Whisper/WhisperX, alinhamento, tradução e publicação SRT continuam fora do escopo da Fase 3. Consulte [docs/ESTADO_ATUAL.md](docs/ESTADO_ATUAL.md), [docs/FASE_3_PLANO.md](docs/FASE_3_PLANO.md) e [docs/HANDOFF_FASE_3.md](docs/HANDOFF_FASE_3.md).

## Licença

O projeto é tratado como MIT. Consulte o arquivo LICENSE e preserve os avisos de copyright e licença aplicáveis.
