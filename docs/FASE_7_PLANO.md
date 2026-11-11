# Plano operacional — Fase 7: integração de ponta a ponta da GUI

- **Status:** implementada e validada na branch `phase-7/gui-pipeline-integration`, a ser integrada à `main` por squash.
- **Fronteira:** a janela dispara o `SerialPipeline` real, consome eventos de domínio, mostra progresso e log, permite cancelamento cooperativo e abre a pasta do SRT publicado.
- **Dependências:** Fases 1–6 integradas à `main` (arquitetura, GUI, mídia, Whisper, WhisperX, tradução/segmentação/SRT).
- **Documento de transferência:** [HANDOFF_FASE_7.md](HANDOFF_FASE_7.md).

---

## 1. Objetivos e escopo

### 1.1. Dentro do escopo

1. Ligar o botão **Gerar legenda** ao pipeline completo, sem simulação e sem trabalho pesado na thread da interface.
2. Executar `JobController.run` em `QThread` dedicada, recebendo eventos por sinal Qt e traduzindo-os em estado exibível.
3. Exibir progresso real quando medido e progresso indeterminado quando a etapa não informa métrica.
4. Bloquear campos e controles incompatíveis durante validação, preparação, transcrição, alinhamento, segmentação, tradução e publicação.
5. Permitir cancelamento cooperativo com confirmação, sem matar a thread da GUI e sem abandonar o job antes do encerramento dos subprocessos.
6. Restaurar controles após conclusão, cancelamento ou falha, preservando mensagem e log para diagnóstico.
7. Abrir a pasta do SRT publicado ao final do trabalho, a partir da própria janela.
8. Limpar o diretório temporário do job em todos os caminhos terminais.

### 1.2. Fora do escopo

- Medir WER, precisão temporal e qualidade tradutória em corpus humano (Fase 8).
- Executar mídia real, modelos completos e YouTube ao vivo na CI (Fase 8).
- Reprocessar ou editar o SRT depois de publicado.
- Suportar mais de um job simultâneo na mesma instância.

## 2. Arquitetura de execução

| Componente | Papel |
|---|---|
| `MainWindow` | Monta `JobRequest`/`JobContext`, confirma a operação, cria a thread e renderiza o snapshot |
| `JobWorker` | Roda `JobController.run` em `QThread`; reemite eventos e garante `completed` mesmo em erro |
| `JobController` | Autoridade de estado, progresso monotônico, erro por categoria e evento terminal único |
| `SerialPipeline` | Etapas de mídia, reconhecimento, alinhamento, segmentação, tradução, validação e publicação |
| `JobViewModel` | Traduz eventos em `JobViewSnapshot` (estado, progresso, log, saída, erro, permissões) |
| `MediaInspectionWorker` | Inspeção ffprobe em `QThread` própria, com token de cancelamento |
| `JobContext` | Identidade do job, diretório temporário exclusivo, destino do SRT e token |

Regras mantidas:

- Nenhum widget é tocado fora da thread da interface; a única travessia é `event_received`/`completed`.
- O controlador emite um único evento terminal; a janela não decide estado de domínio.
- Publicação (`PUBLISHING`) é ponto de não retorno: o pedido de cancelamento é recusado e explicado.
- Serviços externos (FFmpeg, Whisper, WhisperX, NLLB, yt-dlp) continuam encapsulados nos adaptadores injetados pelo bootstrap.

## 3. Fluxo do usuário

1. O usuário escolhe arquivo local ou URL do YouTube e, se quiser, inspeciona as faixas de áudio.
2. Define idioma falado (automático ou manual), idioma final, tradução opcional e caminho do SRT.
3. Clica em **Gerar legenda**; a janela valida a entrada e mostra o resumo de confirmação.
4. Confirmação aceita: o botão é desabilitado imediatamente, o workspace do job é criado e a thread inicia.
5. O painel de andamento mostra etapa, mensagem e progresso; o log acumula eventos com timestamp.
6. Durante o trabalho, **Cancelar trabalho** pede confirmação e desabilita-se após o primeiro pedido aceito.
7. No fim, a janela informa conclusão, exibe o caminho publicado, reabilita os campos e habilita **Abrir pasta**.
8. Em falha, a mensagem de domínio aparece no painel e no log, o SRT anterior permanece intacto e os controles são restaurados.


## 4. Regras de proteção contra cliques acidentais

| Situação | Comportamento |
|---|---|
| Clique duplo em Gerar | `_starting`/thread ativa impedem segunda execução; o pipeline é criado uma única vez por job |
| Confirmação recusada | Nenhum workspace é criado; controles voltam ao estado anterior |
| Destino existente | Segunda confirmação explícita, com **Não** como escolha padrão |
| Cancelar sem job | Botão permanece desabilitado |
| Cancelar repetido | Segundo pedido é ignorado enquanto o primeiro está pendente |
| Cancelamento recusado | Janela explica que a publicação já começou e mantém o job |
| Fechar durante o trabalho | Pedido de cancelamento, espera até 5 s e só então fecha; caso contrário, ignora o fechamento |
| Segundo job durante o trabalho | Bloqueado pela checagem de estado e pelos controles desabilitados |

## 5. Progresso e log

- Percentual vem de `ProgressReported`; sem métrica, a barra fica indeterminada com texto "sem percentual medido".
- `JobViewModel` limita o log a 500 linhas, prefixa avisos/erros e mantém a leitura no fim apenas quando o usuário está no fim.
- O painel de atividade pode ser recolhido e expandido durante a execução sem interromper o job.
- Mensagens terminais alimentam a barra de status e o estado do indicador no cabeçalho.

## 6. Testes e critérios de aceitação

| Área | Evidência |
|---|---|
| Fluxo completo na UI | `tests/gui/test_main_window.py::test_generate_runs_off_the_ui_thread_and_completes` |
| Reentrância | `test_reentrant_start_confirmation_cannot_create_duplicate_jobs` |
| Cancelamento | `test_cancel_stops_a_cooperative_pipeline`, `test_cancel_declined_keeps_the_job_running`, `test_cancel_rejection_is_reported_when_pipeline_has_entered_publication` |
| Falha e retry | `test_pipeline_failure_is_shown_and_allows_retry`, `test_progress_indicator_stops_animating_after_terminal_failure` |
| Progresso honesto | `test_progress_is_indeterminate_until_pipeline_reports_a_measurement` |
| Log | `test_activity_panel_can_be_collapsed_and_expanded`, `test_log_scroll_follows_only_when_the_user_is_at_the_bottom` |
| Inspeção de mídia | `test_media_inspection_runs_in_worker_and_exposes_stream_selection`, `test_media_inspection_can_be_cancelled_without_blocking_the_window` |
| Encerramento | `test_close_after_thread_wait_cleans_workspace_before_window_exit` |
| Pasta do SRT | `test_open_folder_is_enabled_only_after_a_published_job`, `test_open_folder_reports_failure_without_crashing`, `test_open_folder_without_a_publication_explains_the_state` |
| Preferências | `tests/unit/presentation/test_preferences.py` |

Critérios de aceitação:

1. Nenhum processamento pesado ocorre na thread da interface.
2. A interface nunca inicia um segundo job antes do encerramento do primeiro.
3. Cancelamento é cooperativo, confirmado pelo usuário e refletido no estado.
4. Todo caminho terminal libera controles e limpa o workspace do job.
5. A pasta do SRT publicado é acessível pela interface após a conclusão.
6. Suíte determinística verde em Python 3.10–3.13 com Qt offscreen.

## 7. Limites conhecidos

- O cancelamento só é observado entre etapas e entre lotes; uma inferência em andamento termina antes.
- Fechar a janela com o job em `PUBLISHING` é recusado, porque a troca atômica já começou.
- A janela não oferece cancelamento durante a troca atômica nem depois do evento terminal.
- A abertura da pasta depende do serviço de desktop do sistema; falha é reportada, não silenciada.
- A homologação visual em monitor físico, HiDPI e outros sistemas operacionais permanece na Fase 8.

## 8. Comandos de verificação

```bash
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q tests/gui
uv run --locked --no-sync ruff check src/legendar tests scripts
uv run --locked --no-sync ruff format --check src/legendar tests/unit tests/integration tests/gui tests/helpers tests/test_architecture.py
```
