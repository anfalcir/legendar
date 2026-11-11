# Relatório — Fase 8: testes e homologação automatizada

- **Data da medição:** 11/11/2026
- **Ambiente local:** Linux, Python 3.12.3, Qt offscreen (`QT_QPA_PLATFORM=offscreen`), FFmpeg/ffprobe 7.0.2 static em `./ffmpeg/bin` (ignorado pelo Git).
- **Comando principal:** `PATH="$PWD/ffmpeg/bin:$PATH" QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q --cov=legendar --cov-report=term`
- **Resultado:** **443 testes aprovados, 0 falhas, 0 skips**, cobertura **86%** (4115 instruções, 577 não cobertas).
- **Sem FFmpeg no `PATH`:** 433 aprovados e 10 skips explícitos (mídia real e integração FFmpeg).
- **Documentação:** 23 arquivos Markdown verificados, nenhum link relativo quebrado.

> Este relatório distingue o que foi **provado automaticamente** do que depende de
> homologação humana com mídia real, hardware e julgamento editorial. Nenhuma
> pendência humana é apresentada como concluída.

## 1. Composição da suíte

| Camada | Diretório | Testes | Observação |
|---|---|---|---|
| Domínio | `tests/unit/domain` | 48 | máquina de estados, entidades, layout, value objects |
| Aplicação | `tests/unit/application` | 73 | pipeline, segmentação, tradução, validação, progresso, controlador |
| Infraestrutura | `tests/unit/infrastructure` | 119 | ffmpeg/ffprobe, Whisper, WhisperX, NLLB, cache, yt-dlp, paths |
| Apresentação | `tests/unit/presentation` | 19 | view model, preferências, tema |
| Metas e avaliação | `tests/unit/test_phase4_*.py`, `tests/unit/test_phase5_*.py` | 35 | benchmark de modelo e avaliação temporal |
| Governança | `tests/unit/test_bootstrap.py`, `tests/test_architecture.py`, `tests/test_documentation.py` | 44 | composição, camadas, links e documentos obrigatórios |
| Integração | `tests/integration` | 29 | publicação SRT, tradução, workspace, mídia real com FFmpeg |
| GUI | `tests/gui` | 43 | janela offscreen, diálogos, fluxo completo |
| E2E | `tests/e2e` | 24 | matriz de idiomas, falhas, cancelamento e mídia real |
| Legado | `tests/legacy` | 9 | caracterização da baseline preservada |
| **Total** | — | **443** | confirmado por `pytest --collect-only` |

## 2. Cobertura por área crítica

| Módulo | Cobertura | Comentário |
|---|---|---|
| `domain/state/machine.py` | 100% | transições válidas e inválidas |
| `application/job/controller.py` | 94% | evento terminal único, cancelamento, categorias |
| `application/pipeline/serial_pipeline.py` | 95% | ordem das etapas, progresso, falhas |
| `application/pipeline/segmentation.py` | 96% | política, pausas, leitura, subdivisão |
| `application/pipeline/validation.py` | 98% | falhas estruturais e avisos |
| `infrastructure/filesystem/publisher.py` | 100% | troca atômica e roundtrip |
| `infrastructure/filesystem/srt.py` | 88% | formatação e parsing |
| `presentation/qt/main_window.py` | 86% | fluxo, confirmações, cancelamento, pasta publicada |
| `presentation/qt/view_model/job_view_model.py` | 98% | mapeamento de eventos |
| `infrastructure/alignment/whisperx.py` | 67% | trechos que exigem o runtime WhisperX real |
| `infrastructure/translation/nllb.py` | 76% | inferência real coberta por smoke de CI |

Cobertura numérica não substitui comportamento: cada requisito do plano mestre
tem teste nomeado, listado nos planos e handoffs das fases correspondentes.

## 3. Matriz end-to-end executada

| Caso | Resultado | Evidência |
|---|---|---|
| PT → PT | aprovado | `tests/e2e/test_language_matrix.py::test_language_matrix_publishes_a_valid_srt[pt-pt]` |
| PT → EN | aprovado | idem `[pt-en]`; tempos idênticos em `test_translated_job_keeps_one_text_per_cue_and_the_original_times` |
| EN → PT | aprovado | idem `[en-pt]` |
| EN → EN | aprovado | idem `[en-en]`, sem chamada ao tradutor |
| Idioma divergente sem tradução | aprovado | `test_language_matrix_is_reported_on_failure_without_publishing` |
| Preservação integral das palavras | aprovado | `test_untranslated_job_preserves_every_original_word` |

## 4. Mídia real exercitada

| Formato | Codec de fixture | Resultado |
|---|---|---|
| WAV | PCM 16-bit | aprovado, normalização para mono 16 kHz |
| MP3 | libmp3lame | aprovado |
| M4A | AAC | aprovado |
| MKV | PCM 16-bit (inclui caso com duas faixas e offset de 1,25 s) | aprovado, offset preservado |
| MP4 | AAC | aprovado |
| WebM | Opus | aprovado |
| Mídia corrompida | — | falha controlada, sem publicação |
| Mídia sem áudio | vídeo H.264 | `INVALID_INPUT`, sem publicação |

As fixtures são sintéticas (senos e silêncio), geradas em tempo de teste: nenhum
arquivo de mídia pessoal é versionado.


## 5. Falhas e cancelamento

Todos os casos da seção 4 de [FASE_8_PLANO.md](FASE_8_PLANO.md) passaram:
categoria correta, evento terminal único, destino intacto e ausência de
`.partial`. O teste
`test_second_failed_job_does_not_touch_the_previous_published_file` confirma que
uma falha posterior não corrompe um SRT já publicado.

## 6. Testes de interface cobertos

| Requisito da Fase 8 | Teste |
|---|---|
| Clique duplo em Gerar | `test_reentrant_start_confirmation_cannot_create_duplicate_jobs` |
| Clique duplo em Cancelar | `test_repeated_cancel_requests_are_ignored_after_first_acceptance` |
| Confirmação e desistência de início | `test_start_declined_does_not_create_workspace` |
| Confirmação e desistência de cancelamento | `test_cancel_declined_keeps_the_job_running` |
| Bloqueio de controles | `test_progress_is_indeterminate_until_pipeline_reports_a_measurement` |
| Transição para cancelamento | `test_cancel_stops_a_cooperative_pipeline` |
| Falha em etapa | `test_pipeline_failure_is_shown_and_allows_retry` |
| Conclusão e restauração | `test_generate_runs_off_the_ui_thread_and_completes` |
| Expandir/recolher log durante o job | `test_activity_panel_can_be_collapsed_and_expanded` |
| Atualizações sem congelamento | `test_generate_runs_off_the_ui_thread_and_completes` |
| Fechamento durante trabalho ativo | `test_close_after_thread_wait_cleans_workspace_before_window_exit` |
| Tentativa de segundo job | `test_reentrant_start_confirmation_cannot_create_duplicate_jobs` |
| Pasta do SRT publicado | `test_open_folder_is_enabled_only_after_a_published_job` |

## 7. O que permanece com o usuário (homologação de produto)

Estes itens exigem mídia real, modelos baixados, hardware do usuário ou
julgamento editorial. Eles **não** invalidam as fases anteriores e estão
atribuídos à homologação final:

1. Transcrever e alinhar 2–3 pregações reais PT-BR e comparar fronteiras de
   palavra com marcações humanas (metas da seção 9.4 do plano mestre).
2. Revisar a tradução PT↔EN de trechos com nomes próprios, números, siglas e
   linguagem religiosa.
3. Medir tempo total, memória e temperatura na primeira execução com os pesos
   reais de Whisper, WhisperX e NLLB.
4. Executar o fluxo YouTube completo com uma URL que o usuário tenha direito de
   processar, incluindo cancelamento durante o download.
5. Validar a interface em monitor físico, HiDPI e no sistema operacional padrão
   do usuário.
6. Testar arquivo longo (mais de uma hora) para confirmar tempo total e uso de
   memória.
7. Inspecionar o SRT final em um player de referência, além do parser da suíte.

## 8. Riscos residuais

| Risco | Impacto | Mitigação atual |
|---|---|---|
| Modelos reais não são exercitados na suíte determinística | falha de runtime aparece só no uso real | smoke tests de CI por fase e preflight de ambiente na GUI |
| Qualidade tradutória não medida | texto correto, mas pouco natural | revisão humana pendente do NLLB por cue |
| Cancelamento não interrompe inferência em andamento | espera termina a chamada | documentado nos handoffs das Fases 6 e 7 |
| YouTube muda com frequência | fluxo pode quebrar | yt-dlp com runtime JS verificado no preflight |
| Precisão temporal depende de áudio e fala | legendas fora de sincronia em casos difíceis | diagnósticos de alinhamento e avisos no log |
| Cobertura concentrada em módulos puros | ramos de runtime real menos cobertos | smoke tests com runtime real por fase |

## 9. Conclusão da fase

A suíte automatizada cobre o fluxo completo, os quatro pares de idioma, seis
formatos de mídia com ferramentas reais, os modos de falha e o cancelamento,
sem rede, sem modelos baixados e sem credenciais. A CI da fase executa a matriz
Python 3.10–3.13 com FFmpeg instalado, gate de cobertura de 85% e verificação de
links da documentação. As pendências da seção 7 são de homologação de produto e
estão encaminhadas ao usuário.
