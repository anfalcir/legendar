# Plano de execução — Fase 1: Reestruturação arquitetural

- **Documento:** plano operacional da Fase 1 (escopo, sequência, critérios de aceite)
- **Status:** concluída, validada e integrada à `main` pela PR #2 (squash)
- **Branch de implementação:** `phase-1/architecture` (integrada à `main`)
- **Base:** `main` pós-integração da Fase 0 (commit de squash `992cb87`); integração final da Fase 1 em `de31ddd`
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
| 10 | CI da Fase 1 (ruff + pytest + import-check de fronteiras + pytest-qt offscreen) + documentação | workflow dedicado verde em Python 3.10–3.13 | Concluída; runs [#116](https://github.com/anfalcir/legendar/actions/runs/42905199857) e [#127](https://github.com/anfalcir/legendar/actions/runs/42905799938), ambos 4/4 aprovados |

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
- [x] CI da Fase 1 verde na matriz Python 3.10–3.13 e revisão global final concluída;
- [x] decisões abertas e riscos no estado atual;
- [x] revisão final antes da Fase 2.

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
Evidências finais verificadas no GitHub Actions:

- Workflow [Phase 1 quality #116](https://github.com/anfalcir/legendar/actions/runs/42905199857): **4/4 jobs aprovados** em Python 3.10, 3.11, 3.12 e 3.13.
- Workflow final [Phase 1 quality #127](https://github.com/anfalcir/legendar/actions/runs/42905799938): **4/4 jobs aprovados** após as atualizações finais de documentação.
- A suíte completa registrou **196 testes aprovados por ambiente**, com cobertura total reportada de **88%**.
- `ruff check` e `ruff format --check` passaram no escopo mantido da arquitetura e dos testes em todos os quatro ambientes.
- `compileall`, verificação de lock e inicialização Qt offscreen passaram.
- O workflow [Phase 0 quality #160](https://github.com/anfalcir/legendar/actions/runs/42905199743) também passou: 12/12 combinações Python 3.10–3.13 × Ubuntu/Windows/macOS, resolução/lock e prova FFmpeg/ffprobe com normalização e offset. Os jobs CUDA e WhisperX foram pulados intencionalmente no evento PR; as provas completas continuam documentadas no workflow push #113.

O workflow dedicado `.github/workflows/phase1-quality.yml` é agora o gate reproduzível da Fase 1. A política de qualidade não enfraquece o código novo: `ruff check` e `ruff format --check` cobrem integralmente a arquitetura nova e os testes mantidos. A baseline legada e scripts históricos ficam fora do lint retroativo para evitar reformatação incidental; os fontes legados são compilados na CI e seus contratos são protegidos por testes de caracterização.

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
7. Arquivos de evidência da Fase 0 foram preservados. A política de lint/format está definida
   em `LEGACY_BASELINE.md`: arquitetura nova e testes mantidos são verificados integralmente;
   legado e scripts históricos são compilados/caracterizados sem reformatação incidental.

Resultado: todos os critérios técnicos da Fase 1 foram atendidos, a CI dedicada está verde
em Python 3.10–3.13 e a revisão final foi concluída. A PR #2 foi integrada por squash à `main`
no commit `de31dddffc4f8e761692129d4c47a02ca89b8b83`. Nenhuma atividade da Fase 2 foi iniciada;
a Fase 2 permanece condicionada à aprovação explícita.
