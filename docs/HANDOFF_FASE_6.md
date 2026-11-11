# Handoff técnico — Fase 6: tradução por cue, segmentação e SRT

- **Status:** implementação concluída e publicada na branch `phase-6/translation-segmentation-srt`; CI de push [#42951041522](https://github.com/anfalcir/legendar/actions/runs/42951041522) verde em 5/5 jobs. Falta abrir a PR e integrar por squash.
- **Plano operacional:** [FASE_6_PLANO.md](FASE_6_PLANO.md)
- **Fronteira:** consumir `AlignmentResult`, publicar SRT de duas linhas e traduzir localmente por cue.
- **Fora de escopo:** reintegrar a GUI ao job completo (Fase 7) e homologar qualidade tradutória (Fase 8).

## 1. Arquitetura entregue

| Arquivo | Responsabilidade |
|---|---|
| `src/legendar/domain/value_objects/text_layout.py` | `wrap_lines` equilibra linhas e nunca descarta palavras |
| `src/legendar/domain/entities/subtitle.py` | `SubtitleCue.lines()` expõe as linhas publicadas |
| `src/legendar/infrastructure/filesystem/srt.py` | `format_srt` grava até duas linhas por cue |
| `src/legendar/application/pipeline/segmentation.py` | `SegmentationPolicy` e `segment_alignment` |
| `src/legendar/application/pipeline/translation.py` | Unidades, resultado e aplicação da tradução |
| `src/legendar/application/pipeline/validation.py` | `validate_track` e `TrackValidationReport` |
| `src/legendar/application/ports/protocols.py` | Porta `Translator` por cue |
| `src/legendar/application/pipeline/serial_pipeline.py` | Etapas `SEGMENTING`/`TRANSLATING`/`VALIDATING_SRT`/`PUBLISHING` |
| `src/legendar/infrastructure/translation/nllb.py` | Adaptador `NllbTranslator` |
| `src/legendar/bootstrap/app.py` | Composição do tradutor e preflight de tradução |
| `src/legendar/presentation/qt/main_window.py` | Checkbox, tooltip e bloqueio do idioma final |

## 2. Contrato da porta `Translator`

Entrada:

- `units`: uma `TranslationUnit` por cue final, com `index` ≥ 1 e texto normalizado não vazio.
- `source_language`: idioma **detectado** na transcrição.
- `target_language`: idioma final escolhido pelo usuário.
- `progress` e `token`: progresso por cue e cancelamento cooperativo.

Saída:

- `TranslationResult.language` precisa ser igual a `target_language`.
- `TranslationResult.texts` precisa ter exatamente `len(units)` itens, na mesma ordem.

Regras que o adaptador não pode violar:

1. Não alterar `TimeRange`; o vínculo temporal pertence à cue.
2. Não reordenar, fundir ou dividir cues.
3. Não devolver texto vazio; o adaptador limpa espaços e falha se restar vazio.
4. Não inventar tradução quando faltar modelo, dispositivo ou idioma.

## 3. Segmentação: decisões congeladas

- Alvo: duas linhas de 42 caracteres, 84 caracteres por cue, ~17 caracteres por segundo.
- Cue entre 1 s e 7 s; pausa acima de 0,6 s separa grupos.
- Quebra de frase (`.!?…`) é preferida perto da metade da cue; quebra de oração (`,;:—-`) entra como segunda opção.
- Cue acima do tempo de leitura é **subdividida** em partes contíguas; fronteiras são sempre timestamps de palavras alinhadas.
- Subdivisão não reaproveita palavras nem cria sobreposição; no mínimo duas palavras por parte.
- Segmento sem palavras alinhadas nem intervalo vai para `dropped_segments` e nunca gera cue artificial.
- `SegmentationResult` é diagnóstico, não exceção: o pipeline transforma os campos em avisos.

Não relaxar esses limites sem nova decisão documentada e testes correspondentes; o layout do arquivo depende deles.

## 4. Tradução local com NLLB-200

- Checkpoint padrão `facebook/nllb-200-distilled-600M`; `LEGENDAR_TRANSLATE_MODEL` permite outro checkpoint compatível.
- Origem no tokenizador (`por_Latn`/`eng_Latn`), destino via `forced_bos_token_id`.
- Cache em `<models_dir>/nllb`; carga sob demanda, reutilizada entre jobs no mesmo processo.
- Dispositivo `auto` → CUDA se disponível, senão CPU; `cuda` explícito falha com `ModelError` quando não há GPU.
- Lotes de 16 cue, `num_beams=4`, 256 tokens de entrada e de saída.
- Cancelamento verificado antes de carregar pesos, antes de cada lote e depois da tradução.
- Falhas: contagem divergente, texto vazio, idioma incorreto ou nenhuma cue alterada levantam `TranslationError`; ausência de `transformers` levanta `ModelError`.

A primeira tradução baixa os pesos e é lenta por definição. Não transformar esse tempo em timeout de job.

## 5. Validação e publicação

Falhas estruturais (`SrtValidationError`, job interrompido):

- trilho vazio;
- cue sem texto após normalização;
- cue terminando depois do fim da mídia + 0,5 s de tolerância.

Avisos (job conclui, usuário vê o que ficou fora do alvo):

- `short_cues`, `long_cues`, `overflow_cues`, `wide_cues`;
- tradução idêntica ao original em cues específicas;
- idioma detectado diferente do declarado;
- palavras sem alinhamento e anomalias do alinhador.

Publicação: `format_srt` → `validate_roundtrip` → `atomic_write_text`. A troca atômica é o ponto de não retorno e não consulta cancelamento.

## 6. Execução e testes

```bash
uv lock --check
uv sync --locked --group dev --group phase0
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q
uv run --locked --no-sync ruff check src/legendar tests scripts
uv run --locked --no-sync ruff format --check src/legendar tests/unit tests/integration tests/gui tests/helpers tests/test_architecture.py
```

Suíte determinística da branch: 387 testes aprovados e 2 skips esperados (FFmpeg/ffprobe ausentes no ambiente local), com 36 testes de GUI executados offscreen.

Testes que documentam o comportamento:

| Arquivo | Cobre |
|---|---|
| `tests/unit/domain/test_text_layout.py` | duas linhas equilibradas, palavra maior que a linha, overflow sem perda, `SubtitleCue.lines()` |
| `tests/unit/application/test_segmentation.py` | política padrão e inválida, pausa, frase, leitura, subdivisão, reuso de fronteira |
| `tests/unit/application/test_translation.py` | unidades por cue, 1:1, tempos preservados, falhas explícitas |
| `tests/unit/application/test_validation.py` | estrutura, tolerância de fim de mídia, avisos |
| `tests/unit/infrastructure/test_nllb_translator.py` | carregadores injetados, lotes, dispositivo, idioma, cancelamento |
| `tests/integration/test_srt_publication.py` | formatação, overflow, linha única, roundtrip, publicação atômica |
| `tests/integration/test_translation_publication.py` | pipeline traduzido ponta a ponta com publicador real |
| `tests/gui/test_main_window.py` | checkbox de tradução, tooltip e par de idiomas do job |
| `tests/test_architecture.py` | porta por cue e isolamento de `transformers`/`sentencepiece` |

Nenhum teste baixa pesos: o adaptador aceita `tokenizer_loader`, `model_loader`, `batch_translator`, `device_resolver` e `version_provider` injetados.

## 7. Configuração operacional

| Variável | Padrão | Efeito |
|---|---|---|
| `LEGENDAR_TRANSLATE_DEVICE` | `auto` | `auto`, `cpu` ou `cuda`; outro valor invalida a configuração |
| `LEGENDAR_TRANSLATE_MODEL` | `facebook/nllb-200-distilled-600M` | Checkpoint HF carregado no cache local |

Configuração inválida não impede a GUI de abrir: `translate_available=False` e o motivo aparece em `translate_readiness_details`. O checkbox fica desabilitado e o job segue sem tradução.

## 8. Limites conhecidos

- Tradução é PT↔EN; outro `Language` levanta `UnsupportedLanguageError` pelo mapa `NLLB_CODES`.
- MPS não é assumido compatível com o tradutor.
- Cancelamento não interrompe uma chamada de inferência em andamento.
- Texto traduzido mais longo que duas linhas é publicado inteiro e sinalizado como `wide_cues`; não há reescrita automática.
- O SRT final substitui o texto original; não existe exportação paralela do texto de origem.

## 9. Pendências de homologação (produto)

1. Avaliar PT↔EN em corpus autorizado de pregações com revisão humana da tradução.
2. Medir tempo, memória e estabilidade da primeira tradução no computador-alvo.
3. Inspecionar casos com nomes próprios, números, siglas e linguagem religiosa.
4. Decidir se o produto deve arquivar o texto original junto do SRT traduzido.

## 10. Próxima fronteira

A Fase 7 deve conectar a janela ao pipeline completo: disparar o job real a partir do botão, consumir `PipelineResult`/erros de domínio, exibir os avisos de segmentação, tradução e validação, e permitir abrir a pasta do SRT publicado. A Fase 6 não deve ser reaberta para acomodar decisões de UI; qualquer mudança de contrato precisa de teste e registro.
