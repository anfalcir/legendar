# Arquitetura do Legendar

- **Escopo:** aplicação desktop PySide6 que transforma áudio/vídeo em SRT validado, com tradução local opcional.
- **Princípio:** regras puras no domínio, orquestração na aplicação, integrações na infraestrutura, Qt apenas na apresentação e composição explícita no bootstrap.
- **Evolução atual:** correções de integridade, segmentação editorial, gate de qualidade e desempenho são conduzidos pelo [plano vigente](PLANO_CORRECAO_MELHORIA.md).
- **Documentos relacionados:** [estado atual](ESTADO_ATUAL.md), [operação](OPERACAO.md), [instalação](INSTALACAO.md), [decisões](DECISOES.md) e [plano de correção/melhoria](PLANO_CORRECAO_MELHORIA.md).

## 1. Camadas

| Camada | Diretório | Pode importar | Nunca importa |
|---|---|---|---|
| Domínio | `src/legendar/domain` | biblioteca padrão | Qt, FFmpeg, torch, `transformers`, `requests` |
| Aplicação | `src/legendar/application` | domínio | Qt, infraestrutura concreta, torch |
| Infraestrutura | `src/legendar/infrastructure` | domínio, aplicação (portas) | Qt, apresentação |
| Apresentação | `src/legendar/presentation` | aplicação (portas, pipeline, eventos), domínio | adaptadores concretos de infraestrutura |
| Bootstrap | `src/legendar/bootstrap` | todas as camadas | — |

Essa direção é verificada por `tests/test_architecture.py`, que falha se uma camada importar algo proibido.

## 2. Mapa de módulos

```text
src/legendar/
  bootstrap/app.py
  domain/
    entities/{media,transcript,subtitle}.py
    value_objects/{language,time,text_layout}.py
    state/machine.py
    events/job_events.py
    errors/{base,catalog}.py
  application/
    job/{context,controller}.py
    pipeline/{serial_pipeline,performance,segmentation,translation,validation}.py
    ports/protocols.py
    progress/sink.py
  infrastructure/
    media/{probe,ffmpeg,ffprobe,tools,youtube}.py
    transcription/whisper.py
    alignment/whisperx.py
    translation/{nllb,gemini,llama_runtime}.py
    filesystem/{srt,publisher,atomic,workspace,paths}.py
    config/settings.py
    diagnostics/performance.py
    logging/setup.py
  presentation/qt/
    main_window.py
    dialogs.py, preferences.py
    view_model/job_view_model.py
    workers/{job_worker,media_inspection_worker}.py
    dialogs.py, preferences.py, theme.py
```

## 3. Fluxo de um job

1. `MainWindow` monta `JobRequest` (origem, idiomas, tradução, faixa) e `JobContext` (job id, workspace, destino, token).
2. `JobWorker` roda `JobController.run` em `QThread`; o controlador abre `VALIDATING_INPUT`.
3. `SerialPipeline` executa, em ordem: aquisição, inspeção, preparação de áudio, transcrição, alinhamento, segmentação, tradução opcional, validação e publicação; a sessão de desempenho mede cada etapa sem interferir no fluxo.
4. Cada etapa reporta progresso por `ScaledProgress`, que mapeia a fração local para a faixa global.
5. O controlador converte transições e mensagens em eventos; o resultado é um único evento terminal.
6. `JobViewModel` transforma eventos em snapshot; a janela apenas desenha, habilita controles e limpa o workspace.
7. `PipelinePerformanceSession` acumula tempos monotônicos, CPU e recursos por etapa. Snapshots dos adaptadores separam carga dos modelos, inferência, chamadas de alinhamento e fases internas da tradução; `JsonPerformanceReporter` persiste JSON local privado, fora do fluxo de conteúdo.

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
| `PerformanceReporter` | captura recursos e persiste relatório sanitizado local, opcional ao pipeline |
| `CancellationToken` | `is_cancelled`, `raise_if_cancelled()` |

## 5. Máquina de estados

`IDLE → VALIDATING_INPUT → INSPECTING_MEDIA → PREPARING_AUDIO → TRANSCRIBING → ALIGNING → SEGMENTING → [TRANSLATING] → VALIDATING_SRT → PUBLISHING → COMPLETED`, com `CANCELLING → CANCELLED` e `FAILED` como desvios.

- Somente `StateMachine.transition` decide transições válidas.
- `PUBLISHING` é terminal para cancelamento: a troca atômica já começou.
- `JobController` garante um único evento terminal por job.

## 6. Threads e responsividade

- A thread principal só desenha; FFmpeg, modelos e rede rodam fora dela.
- `JobWorker` vive em `QThread`; eventos atravessam por `Signal(object)`.
- A inspeção de mídia tem `QThread` própria.
- O cancelamento de inferência é cooperativo; uma chamada em andamento retorna antes do encerramento.

## 7. Publicação SRT atual

1. A segmentação atual usa palavras alinhadas e produz cues de até duas linhas de 42 caracteres; a política atual declara 1–7 s, pausa de 0,6 s e cerca de 17 CPS.
2. A tradução opcional preserva `TimeRange` e correspondência 1:1 entre cue e texto traduzido.
3. `validate_track` bloqueia estrutura inválida e sinaliza riscos de legibilidade.
4. `format_srt` serializa; `validate_roundtrip` reparseia e compara; `atomic_write_text` troca o arquivo por rename.

**Limitações conhecidas:** a política editorial e a consolidação cronológica de cues foram implementadas nas Fases 3 e 4. O gate estrutural da Fase 8 mede limites e riscos do SRT, mas não substitui revisão audiovisual, avaliação de naturalidade PT-BR ou conferência de sincronização em player.

## 8. Configuração e caminhos

| Item | Padrão | Variável |
|---|---|---|
| Cache (modelos, logs, temporários) | `~/.cache/legendar` | `LEGENDAR_CACHE_DIR` |
| Saída sugerida | `~/Videos` | `LEGENDAR_OUTPUT_DIR` |
| Modelo Whisper | `base` | `LEGENDAR_WHISPER_MODEL` |
| Dispositivo Whisper | `auto` | `LEGENDAR_WHISPER_DEVICE` |
| Dispositivo do alinhador | `auto` | `LEGENDAR_ALIGN_DEVICE` |
| Padding de recuperação do alinhamento | `0,75 s` no bootstrap de produção | `LEGENDAR_ALIGN_RECOVERY_PADDING_SECONDS` |
| Dispositivo da tradução | `auto` | `LEGENDAR_TRANSLATE_DEVICE` |
| Checkpoint de tradução | `facebook/nllb-200-distilled-600M` | `LEGENDAR_TRANSLATE_MODEL` |

Workspaces ficam em `<cache>/tmp` e são exclusivos por job; modelos ficam em `<cache>/models`. A chave Gemini é armazenada separadamente no perfil local do usuário, com arquivo privado `0600` quando suportado, e não faz parte do QSettings.

## 9. Arquitetura de testes

| Camada | Diretório | Isolamento |
|---|---|---|
| Unitário | `tests/unit` | dublês em memória, sem I/O externo |
| Integração | `tests/integration` | sistema de arquivos real; FFmpeg quando instalado |
| GUI | `tests/gui` | Qt offscreen com pipeline dublê |
| E2E | `tests/e2e` | controlador, pipeline e publicação com adaptadores controlados |
| Governança | `tests/test_architecture.py`, `tests/test_documentation.py` | importações e documentação |

Os testes E2E de mídia atuais usam adaptadores falsos para reconhecimento e alinhamento; não medem qualidade real dos motores.

## 10. Evolução sob o plano atual

A arquitetura em camadas e as portas `Transcriber`, `Aligner` e `Translator` permitem avaliar adaptadores alternativos sem reescrever a aplicação. A Fase 7 adiciona uma política transversal de recursos: perfis controlam retenção de modelos e threads CPU sem acoplar a UI aos runtimes. A Fase 6 mantém `NllbTranslator` e `GeminiTranslator` atrás da mesma porta; a seleção persistida em Preferências altera o adaptador usado pelos próximos jobs sem reiniciar a GUI. As próximas mudanças devem preservar essas fronteiras.

A evolução proposta é:
- instrumentar tempo e memória por estágio;
- preservar integralmente o conteúdo reconhecido e bloquear publicação quando houver palavras sem âncora temporal confiável (Fase 2);
- **recuperar alinhamentos parciais com segunda tentativa controlada, sem fabricar timestamps (Fase 2);**
- formar cues a partir de um fluxo contínuo de palavras alinhadas;
- distinguir tempo de fala de tempo de exibição;
- transformar riscos editoriais em um gate explícito;
- avaliar faster-whisper/CTranslate2 e NLLB via CTranslate2 por benchmark;
- gerenciar a residência dos modelos e threads por perfil de hardware.

As próximas mudanças devem ser guiadas pelas evidências de homologação real da Fase 8. Escopo, critérios e pendências estão em [PLANO_CORRECAO_MELHORIA.md](PLANO_CORRECAO_MELHORIA.md).


## 11. Runtime local gerenciado e idempotente

O runtime TranslateGemma é uma dependência operacional sob responsabilidade do bootstrap/infraestrutura, não uma tarefa manual do usuário. A camada de infraestrutura deve expor um gerenciador com operações idempotentes de diagnóstico, preparação, inicialização, health check e encerramento. A apresentação consome estados/progresso por worker e nunca executa instalação, rede, I/O pesado ou espera de processo na thread Qt.

- Na abertura: diagnóstico leve, sem download nem bloqueio da janela.
- Na seleção/execução da tradução local: preflight atualizado; propor instalação do runtime/modelo ausente e solicitar consentimentos necessários.
- Antes de TRANSLATING: garantir modelo válido, iniciar/reutilizar apenas processo gerenciado e aguardar readiness.
- Concorrência: locks para impedir instalações, downloads ou servidores duplicados; arquivos temporários e publicação atômica do modelo.
- Encerramento: parar somente o processo filho criado pelo Legendar; preservar pesos/cache e nunca matar processos externos.
- Segurança: loopback exclusivo, versão fixada, integridade verificada, sem privilégios elevados silenciosos e sem credenciais em logs/configurações comuns.

A máquina de estados operacional e seus eventos de progresso devem ser testáveis sem baixar o modelo real. A prova com pesos reais permanece um gate separado de homologação. A primeira fatia de infraestrutura está em desenvolvimento na PR #36: diagnóstico local, download retomável do GGUF após consentimento e SHA-256, inicialização em loopback, readiness, reutilização do processo próprio e encerramento seguro; ainda não está conectada ao bootstrap nem ao adaptador de tradução.
