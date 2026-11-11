# Arquitetura do Legendar

- **Escopo:** aplicação desktop PySide6 que transforma áudio/vídeo em SRT validado, com tradução local opcional.
- **Princípio:** regras puras no domínio, orquestração na aplicação, integrações na infraestrutura, Qt apenas na apresentação e composição explícita no bootstrap.
- **Documentos relacionados:** [PLANO_REMODELAGEM.md](PLANO_REMODELAGEM.md), [ESTADO_ATUAL.md](ESTADO_ATUAL.md), [OPERACAO.md](OPERACAO.md), [INSTALACAO.md](INSTALACAO.md) e [DECISOES.md](DECISOES.md).

## 1. Camadas

| Camada | Diretório | Pode importar | Nunca importa |
|---|---|---|---|
| Domínio | `src/legendar/domain` | biblioteca padrão | Qt, FFmpeg, torch, `transformers`, `requests` |
| Aplicação | `src/legendar/application` | domínio | Qt, infraestrutura concreta, torch |
| Infraestrutura | `src/legendar/infrastructure` | domínio, aplicação (portas) | Qt, apresentação |
| Apresentação | `src/legendar/presentation` | aplicação (portas, pipeline, eventos), domínio | adaptadores concretos de infraestrutura |
| Bootstrap | `src/legendar/bootstrap` | todas as camadas | — |

Essa direção é verificada por `tests/test_architecture.py`, que falha se uma
camada importar algo proibido.

## 2. Mapa de módulos

```text
src/legendar/
  bootstrap/app.py                     composição de portas reais + entrada da GUI
  domain/
    entities/{media,transcript,subtitle}.py
    value_objects/{language,time,text_layout}.py
    state/machine.py                   estados e transições do job
    events/job_events.py               eventos estruturados do job
    errors/{base,catalog}.py           categorias e erros de domínio
  application/
    job/{context,controller}.py        contexto do job e autoridade de estado
    pipeline/{serial_pipeline,segmentation,translation,validation}.py
    ports/protocols.py                 portas (Protocol) do pipeline
    progress/sink.py                   progresso monotônico e escalonado
  infrastructure/
    media/{probe,ffmpeg,ffprobe,tools,youtube}.py
    transcription/whisper.py           adaptador Whisper
    alignment/whisperx.py              adaptador WhisperX
    translation/nllb.py                adaptador NLLB-200
    filesystem/{srt,publisher,atomic,workspace,paths}.py
    config/settings.py                 diretórios de cache, saída, logs e temporários
    logging/setup.py                   log rotativo com redação de caminho pessoal
  presentation/qt/
    main_window.py                     janela, confirmações, estado e resultado
    view_model/job_view_model.py       eventos → snapshot exibível (sem Qt)
    workers/{job_worker,media_inspection_worker}.py
    dialogs.py, preferences.py, theme.py
```

## 3. Fluxo de um job

1. `MainWindow` monta `JobRequest` (origem, idiomas, tradução, faixa) e `JobContext` (job id, workspace, destino, token).
2. `JobWorker` roda `JobController.run` em `QThread`; o controlador abre o estado `VALIDATING_INPUT`.
3. `SerialPipeline` executa, em ordem: inspeção, preparação de áudio, transcrição, alinhamento, segmentação, tradução opcional, validação e publicação.
4. Cada etapa reporta progresso por `ScaledProgress`, que mapeia a fração local para a faixa global da etapa.
5. O controlador converte transições em `StateChanged`, mensagens em `ProgressReported`/`LogRecorded` e o desfecho em `JobCompleted`, `JobFailed` ou `JobCancelled` — um único evento terminal.
6. `JobViewModel` transforma eventos em `JobViewSnapshot`; a janela apenas desenha, habilita controles e limpa o workspace.

## 4. Portas do pipeline

| Porta | Contrato resumido |
|---|---|
| `MediaInspector` | `inspect(source, token) -> MediaInfo` |
| `MediaDownloader` | `fetch(source, dir, token, progress) -> caminho local` |
| `AudioPreparer` | `prepare(media, stream, destino, token, progress) -> AudioAsset` |
| `Transcriber` | `transcribe(audio, language, progress, token) -> Transcript` |
| `Aligner` | `align(audio, transcript, progress, token) -> AlignmentResult` |
| `Translator` | `translate(units, source_language, target_language, progress, token) -> TranslationResult` |
| `SubtitlePublisher` | `publish(track, destino) -> caminho publicado` |
| `CancellationToken` | `is_cancelled`, `raise_if_cancelled()` |

## 5. Máquina de estados

`IDLE → VALIDATING_INPUT → INSPECTING_MEDIA → PREPARING_AUDIO → TRANSCRIBING →
ALIGNING → SEGMENTING → [TRANSLATING] → VALIDATING_SRT → PUBLISHING →
COMPLETED`, com `CANCELLING → CANCELLED` e `FAILED` como desvios.

Regras:

- Somente `StateMachine.transition` decide se uma transição é válida.
- `PUBLISHING` é terminal para cancelamento: a troca atômica já começou.
- `JobController` garante um único evento terminal por job, mesmo sob erro inesperado.

## 6. Threads e responsividade

- A thread principal só desenha; nenhum FFmpeg, modelo ou rede roda nela.
- `JobWorker` vive em `QThread`; eventos atravessam por `Signal(object)` em conexão enfileirada.
- A inspeção de mídia tem `QThread` própria e token independente.
- Fechar a janela durante o trabalho pede cancelamento, espera até 5 s e só então encerra.

## 7. Publicação SRT

1. `segment_alignment` produz cues de até duas linhas de 42 caracteres (84 por cue), 1–7 s, pausa de 0,6 s.
2. A tradução opcional reescreve o texto preservando `TimeRange` e a relação 1:1 por cue.
3. `validate_track` bloqueia trilho vazio, cue sem texto e cue além do fim da mídia; reporta avisos de duração e largura.
4. `format_srt` serializa; `validate_roundtrip` reparseia e compara; `atomic_write_text` troca o arquivo por rename.
5. Em qualquer falha anterior à troca, o SRT existente permanece intacto e nenhum `.partial` sobra.

## 8. Configuração e caminhos

| Item | Padrão | Variável |
|---|---|---|
| Cache (modelos, logs, temporários) | `~/.cache/legendar` | `LEGENDAR_CACHE_DIR` |
| Saída sugerida | `~/Videos` | `LEGENDAR_OUTPUT_DIR` |
| Modelo Whisper | `base` | `LEGENDAR_WHISPER_MODEL` |
| Dispositivo Whisper | `auto` | `LEGENDAR_WHISPER_DEVICE` |
| Dispositivo do alinhador | `auto` | `LEGENDAR_ALIGN_DEVICE` |
| Dispositivo da tradução | `auto` | `LEGENDAR_TRANSLATE_DEVICE` |
| Checkpoint de tradução | `facebook/nllb-200-distilled-600M` | `LEGENDAR_TRANSLATE_MODEL` |

Workspaces ficam em `<cache>/tmp` e são exclusivos por job; modelos ficam em
`<cache>/models` e nunca são removidos para cancelar um job.

## 9. Arquitetura de testes

| Camada | Diretório | Isolamento |
|---|---|---|
| Unitário | `tests/unit` | dublês em memória, sem I/O externo |
| Integração | `tests/integration` | sistema de arquivos real; FFmpeg quando instalado |
| GUI | `tests/gui` | Qt offscreen com pipeline dublê |
| E2E | `tests/e2e` | controlador, pipeline e publicação reais |
| Governança | `tests/test_architecture.py`, `tests/test_documentation.py` | importações e documentação |

`tests/helpers/fakes.py` concentra os dublês reutilizáveis; nenhum teste baixa
modelos, acessa rede ou depende de credenciais.

## 10. Baseline legada

`main.py`, `core/` e `gui/` permanecem como aplicação anterior caracterizada por
testes (`tests/legacy`) e descrita em [LEGACY_BASELINE.md](LEGACY_BASELINE.md).
A aplicação nova não importa esses módulos; a política de aposentadoria está no
documento da baseline.

| `ProgressSink` | `report(fraction, message)` |

As portas existem porque têm consumidor real no pipeline e dublês nos testes.
Nenhuma abstração é criada sem consumidor.
