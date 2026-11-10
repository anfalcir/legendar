# Legendar

Aplicação desktop para transcrever áudio de vídeos, alinhar a fala ao tempo da mídia e produzir legendas SRT, com tradução opcional para inglês ou português brasileiro.

A remodelagem está em execução por fases. A Fase 1 — reestruturação arquitetural — foi implementada, validada e integrada à `main` (PR #2), com CI em Python 3.10–3.13 (196 testes por ambiente). A aplicação anterior permanece preservada como baseline até que os fluxos substitutos sejam implementados e homologados. A Fase 2 e as integrações de produto seguintes ainda não foram iniciadas.

## Documentação do projeto

- [Plano mestre de remodelagem](docs/PLANO_REMODELAGEM.md) — visão do produto, requisitos, arquitetura, pipeline de sincronização, fases e critérios de aceite.
- [Estado atual](docs/ESTADO_ATUAL.md) — documento vivo com o que existe, o que está em andamento, decisões, testes, riscos e próximos passos.
- [Protocolo da Fase 0](docs/FASE_0_PROTOCOLO.md) — inventário do ambiente, experimentos, métricas, evidências e critérios para a prova técnica.
- [Matriz de dependências](docs/MATRIZ_DEPENDENCIAS.md) — fonte canônica, faixas de versões, dependências externas, perfis de hardware e política de compatibilidade.
- [Plano operacional da Fase 1](docs/FASE_1_PLANO.md) — etapas, evidências e critérios de conclusão da reestruturação.
- [Baseline legada](docs/LEGACY_BASELINE.md) — contratos caracterizados, limitações e política de migração da aplicação anterior.
- [Handoff da Fase 1](docs/HANDOFF_FASE_1.md) — decisões consolidadas, arquitetura-alvo, critérios de aceite e instruções para continuidade na IDE.

## Direção do produto

- Entrada por URL do YouTube ou arquivos locais de áudio e vídeo.
- Whisper como motor central de reconhecimento de fala.
- Alinhamento temporal refinado por palavra.
- Segmentação e tradução contextual para inglês ou português brasileiro.
- Exportação de legendas SRT.
- Interface desktop em PySide6, com processamento em segundo plano, progresso, logs e cancelamento controlado.

Consulte o [plano de remodelagem](docs/PLANO_REMODELAGEM.md) para distinguir funcionalidades planejadas das que já foram implementadas.

## Estado da implementação atual

A aplicação anterior em `main.py`, `core/` e `gui/` permanece preservada como baseline de compatibilidade, com contratos caracterizados. A nova arquitetura em `src/legendar/` possui camadas, pipeline, máquina de estados, cancelamento cooperativo, publicação SRT atômica e GUI mínima. Ela ainda não processa mídia real: integração FFmpeg/YouTube, Whisper/WhisperX, tradução e refinamento visual pertencem às fases posteriores. O andamento e as evidências estão em [docs/ESTADO_ATUAL.md](docs/ESTADO_ATUAL.md).

## Licença

O projeto é tratado como MIT. Consulte o arquivo LICENSE e preserve os avisos de copyright e licença aplicáveis.
