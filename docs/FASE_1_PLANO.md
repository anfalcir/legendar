# Plano de execução — Fase 1: Reestruturação arquitetural

- **Documento:** plano operacional da Fase 1 (escopo, sequência, critérios de aceite)
- **Status:** em execução — implementação fechada; CI e revisão final em validação
- **Branch de trabalho:** `phase-1/architecture`
- **Base:** `main` pós-integração da Fase 0 (commit de squash `992cb87`)
- **Fontes de referência:** [PLANO_REMODELAGEM.md](PLANO_REMODELAGEM.md), [ESTADO_ATUAL.md](ESTADO_ATUAL.md), [HANDOFF_FASE_1.md](HANDOFF_FASE_1.md)

---

## 1. Objetivo da fase

Estabelecer a estrutura arquitetural do produto — camadas, contratos, máquina de estados,
pipeline serial testável, políticas de temporários/cache, configuração e inicialização —
**sem implementar funcionalidade real de mídia, reconhecimento, alinhamento ou tradução**.
A fase entrega esqueleto profissional, testável e substituível, que isola as funcionalidades
das próximas fases (2–7).

Frase de orientação do handoff: *a Fase 0 autorizou construir a estrutura que mantém as
funcionalidades isoladas, testáveis e substituíveis — não a implementação das funcionalidades.*

## 2. Restrições herdadas (não violar)

- Domínio sem importar Qt, FFmpeg, Whisper, rede ou filesystem concreto.
- Interface não executa processamento pesado; workers comunicam-se por sinais tipados.
- Controlador de job é autoridade única sobre transições de estado.
- Cancelamento cooperativo, com pontos seguros; publicação final atômica e não cancelável.
- Um único job ativo por instância.
- Temporários isolados por job; cache de modelos separado e nunca apagado para cancelar job.
- Regra temporal: `timestamp_global = source_stream_offset + chunk_offset + timestamp_local`.
- Tradução atrás de porta; nenhum fornecedor escolhido nesta fase.
- Não editar lockfile manualmente; não usar `requirements.txt` como fonte.
- Decisões abertas e riscos vão para o estado atual, não para mudanças silenciosas.

## 3. Sequência de execução (commits pequenos e reversíveis)

| Etapa | Entrega | Evidência | Situação no checkpoint |
|---|---|---|---|
| 1 | Plano de execução e política de lint/testes (`pyproject` apenas grupos/tools; sem novas deps de runtime) | plano e grupos `test`/`lint` configurados | Concluída |
| 2 | Testes de caracterização da baseline (`core/`, `gui/`) e helpers puros extraídos | contratos legados executados com doubles, sem rede ou modelos | Concluída; nove casos de caracterização e compatibilidade adicionados |
| 3 | Camada `domain`: objetos de valor temporais, entidades, erros tipados, eventos | testes de invariantes | Concluída |
| 4 | Máquina de estados (`JobState` + `StateMachine`) com tabela de transições | testes de transições válidas/inválidas | Concluída |
| 5 | `application`: portas (protocolos), `JobContext`, progresso e pipeline serial fake | testes com fakes de transcriber/aligner/translator | Concluída |
| 6 | `infrastructure`: metadados/ferramentas de mídia, cache de modelos, workdir/factory, publisher atômico | testes unitários; sem inferência/modelos reais | Concluída no escopo da Fase 1; adapters reais permanecem nas fases 3–6 |
| 7 | `presentation`: view model sem Qt + janela Qt mínima + worker que traduz eventos em sinais | testes pytest-qt de estados/fakes | Concluída no escopo da Fase 1; polimento visual/preferências pertencem à Fase 2 |
| 8 | `bootstrap`: composição explícita, entrypoint `python -m legendar`, preflight de ferramentas externas | smoke test offscreen | Concluída |
| 9 | Migração/estratégia do legado (`main.py`, `core/`, `gui/`) documentada e executada | baseline caracterizada, congelada fora da arquitetura nova e com gate de aposentadoria | Concluída; arquivos preservados temporariamente até paridade e homologação end-to-end |
| 10 | CI da Fase 1 (ruff + pytest + import-check de fronteiras + pytest-qt offscreen) + documentação | workflow dedicado verde em Python 3.10–3.13 | Em validação; workflow `phase1-quality.yml` criado e conectado à branch/PR |

## 4. Layout-alvo (ajustado do handoff à realidade do repositório)

O handoff propunha `src/legendar/...`. O repositório está em layout flat e `pyproject`
declara `package = false`. A Fase 1 adota `src/legendar/` para separação limpa de import e
distribuição futura, **sem publicar o pacote** (`package = false` mantido), executando via
`PYTHONPATH`/`uv run python -m legendar`. Justificativa registrada no estado atual.

```text
src/legendar/
  __init__.py
  __main__.py
  bootstrap/
  domain/            (value_objects, entities, state, errors, events)
  application/       (ports, pipeline, state, job, progress)
  infrastructure/    (media, speech, alignment, translation, filesystem, settings, legacy)
  presentation/qt/   (view_model, windows, workers)
scripts/             (evidências da Fase 0 preservadas)
tests/               (unit/, gui/, integration/; fakes compartilhados)
```

## 5. Critérios de aceite (do handoff, verificáveis)

- [x] árvore de pacotes e dependências entre camadas documentada;
- [x] imports do domínio livres de Qt e de implementações externas (teste de fronteira);
- [x] entidades/objetos de valor principais e invariantes com testes;
- [x] máquina de estados com transições válidas/inválidas testadas;
- [x] pipeline serial com contratos e fakes testados;
- [x] cancelamento, progresso, falha e publicação representados sem inferência real;
- [x] temporários e cache com políticas testadas separadamente;
- [x] configuração e inicialização centralizadas e reproduzíveis;
- [x] aplicação inicia em modo de desenvolvimento (smoke test offscreen local);
- [ ] CI da Fase 1 verde na matriz Python 3.10–3.13 e revisão global final concluída;
- [x] decisões abertas e riscos no estado atual;
- [ ] revisão final antes da Fase 2.

## 6. Fora de escopo na Fase 1

Refinamento visual completo (Fase 2); integração real YouTube/FFmpeg/Whisper (Fases 3–5);
tradução de fornecedor (Fase 6); edição de vídeo, histórico, nuvem, diarização, multi-job.

## 7. Riscos conhecidos

- **PySide6/Deps pesadas:** o perfil `runtime-*` instala Whisper/WhisperX/Torch; a suíte
  rápida e a CI usam apenas dependências-base + grupo `dev`, com fakes. Testes que dependem de
  FFmpeg são marcados e pulados quando ausente.
- **Legado acoplado:** `gui.worker` importa dependências opcionais no topo. A baseline agora
  tem testes com doubles e política de congelamento/aposentadoria documentada em
  [LEGACY_BASELINE.md](LEGACY_BASELINE.md); não criar novas dependências com `src/legendar/`.
- **Layout flat → `src/`:** a mudança de import exige ajuste de entrypoint e CI; mitigada por
  `__main__.py`, `PYTHONPATH=src` explícito e teste de import.

## 8. Execução (checkpoint registrado em 10/11/2026)

A implementação arquitetural está na branch `phase-1/architecture`, sobre a base da Fase 0.
Validações locais executadas:

- `uv run --locked pytest -q`: **175 passed**;
- `uv run --locked ruff check src/legendar tests/unit tests/integration tests/gui tests/helpers tests/test_architecture.py tests/conftest.py tests/__init__.py`: aprovado;
- `uv run --locked ruff format --check` sobre os mesmos arquivos de arquitetura/teste: aprovado;
- `PYTHONPATH=src QT_QPA_PLATFORM=offscreen timeout 5s uv run --locked python -m legendar`: a janela abriu e permaneceu no event loop até o timeout esperado.

O workflow dedicado `.github/workflows/phase1-quality.yml` foi criado para executar a suíte
pytest completa (incluindo Qt offscreen), Ruff e a verificação de lock em Python 3.10–3.13.
A execução verde desse workflow ainda é gate obrigatório antes de encerrar a fase. `ruff check .`
continua fora da política deliberada: os arquivos legados são cobertos por caracterização e
compilação, sem reformatação incidental; o código novo é integralmente lintado.

- **Fronteiras de camada** (`tests/test_architecture.py`): `domain` não importa Qt,
  `application`/`presentation`/`infrastructure`, nem `whisperx`/`torch`/`ffmpeg`/`yt_dlp`;
  nenhum módulo de domínio faz I/O no import; `application` conhece apenas `domain` e as
  portas.
- **Domínio**: `JobState`/`StateMachine` (transições válidas, terminais, reinício
  explícito), `TimeRange` (finito e monotônico), `Language`/`OutputLanguage`,
  `MediaSource`/`MediaInfo`/`AudioAsset`, `Transcript`/`AlignmentResult`,
  `SubtitleCue`/`SubtitleTrack` (índices sequenciais, sem sobreposição, idioma único,
  normalização de texto), catálogo de erros com `ErrorCategory` e eventos de job imutáveis
  (`JobStarted`, `StateChanged`, `ProgressReported`, `JobCompleted`, `JobCancelled`,
  `JobFailed`).
- **Aplicação**: `SerialPipeline` (inspeção → preparação de áudio → transcrição →
  alinhamento → segmentação → [tradução] → validação → publicação), com portas injetadas;
  `segment_alignment` pura com diagnósticos (segmento descartado, cue curta, overflow de
  leitura); progresso monotônico escalonado por etapa; `JobController` como dono da máquina
  de estados e dos eventos (terminal único, categorias de erro); `JobContext` +
  `TempWorkspaceFactory` com limpeza segura que nunca toca no cache de modelos.
- **Infraestrutura existente nesta árvore**: parser/metadados de ffprobe, descoberta de
  executáveis externos, cache de modelos sem operação de exclusão, formatação/parse de SRT
  determinística com round-trip validado, escrita atômica e `SrtPublisher`, configuração e
  logging.
- **Composição e apresentação mínima existentes**: bootstrap, `python -m legendar`, janela Qt,
  view model e worker com cancelamento cooperativo. A janela foi smoke-testada offscreen; o
  pipeline default informa explicitamente que processamento real só será conectado na Fase 3.
- **Ainda não implementados**: adapters concretos para FFmpeg/Whisper/WhisperX/tradução,
  preflight de cache/modelos, preferências persistidas, localização completa e aposentadoria
  do legado. `main.py`, `core/` e `gui/` foram preservados.

Desvios conscientes em relação ao plano original:

1. O progresso é produzido pelo pipeline com `MonotonicProgress`/`ScaledProgress` e chega ao
   controlador por callback; a UI só traduz em sinais Qt (nunca regride nem duplica).
2. `JobStarted` é emitido **antes** do primeiro `StateChanged` (sequência 1), para que a UI
   tenha `job_id`/rótulo antes de qualquer transição.
3. Cancelamento passa por `CANCELLING` antes de `CANCELLED`: a máquina só aceita estados
   intermediários explícitos, e `PUBLISHING` é o ponto de não retorno (escrita atômica).
4. Se o idioma final difere do idioma detectado e a tradução não foi pedida, o job falha
   cedo com `UnsupportedLanguageError` em vez de publicar um SRT com rótulo incorreto;
   origem informada diferente da detectada vira *warning* no resultado.
5. A publicação grava direto no destino final de forma atômica (sem cópia dupla); a
   validação estrutural ocorre em `VALIDATING_SRT` e novamente dentro do publisher.
6. Overflow de leitura significa "texto não cabe no tempo da cue"
   (`duration < chars/22`), não o contrário.
7. Arquivos de evidência da Fase 0 foram preservados. A validação de lint/format deste
   checkpoint foi restrita à arquitetura e aos testes da Fase 1; a suíte global ainda requer
   uma política explícita para o legado e os arquivos históricos.

Próximas ações para fechar a Fase 1: aguardar/inspecionar a execução integral do workflow
`phase1-quality.yml`, corrigir qualquer falha encontrada, revisar o diff e confirmar a coerência
final dos documentos. Não iniciar a Fase 2 sem revisão e aprovação explícitas.
