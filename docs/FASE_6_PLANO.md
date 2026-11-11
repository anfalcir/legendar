# Plano operacional — Fase 6: tradução por cue, segmentação editorial e SRT

- **Status:** implementada, validada e integrada à `main` por squash na Fase 7 (a criação de PR não estava disponível no ambiente). CI de push da branch: [#42951451587](https://github.com/anfalcir/legendar/actions/runs/42951451587), 5/5 jobs verdes.
- **Fronteira:** consumir `AlignmentResult` da Fase 5, produzir cues de até duas linhas, traduzir localmente quando solicitado e publicar o SRT de forma atômica.
- **Dependências:** Fases 4 (transcrição) e 5 (alinhamento) integradas à `main`.
- **Decisão de tradução:** NLLB-200 distilled 600M local, executado pelo adaptador `NllbTranslator`; nenhum texto da legenda sai do computador.
- **Documento de transferência:** [HANDOFF_FASE_6.md](HANDOFF_FASE_6.md).

---

## 1. Objetivos e escopo

### 1.1. Dentro do escopo

1. Segmentar palavras alinhadas em cues legíveis, com quebra preferencial em fim de frase ou de oração, sem fabricar timestamps.
2. Aplicar o alvo editorial de **duas linhas de 42 caracteres** e ~17 caracteres por segundo na segmentação e na gravação do arquivo.
3. Traduzir **uma cue por vez**, preservando exatamente os tempos das cues originais e a correspondência 1:1 de textos.
4. Validar o trilho final antes da publicação: falhas estruturais interrompem o job; riscos de legibilidade viram avisos no resultado.
5. Publicar o SRT atomicamente, com verificação de ida e volta do conteúdo gravado.
6. Expor a disponibilidade da tradução no preflight da GUI, sem bloquear a janela quando a configuração estiver inválida.

### 1.2. Fora do escopo

- Reintegrar a janela Qt ao pipeline completo com controle de job em produção (Fase 7).
- Homologar qualidade tradutória em corpus de pregações (Fase 8).
- Suportar idiomas além de PT-BR e inglês; o mapa `NLLB_CODES` declara exatamente os idiomas de produto.
- Editar legendas manualmente, ou traduzir mantendo o texto original em paralelo.

## 2. Arquitetura

| Arquivo | Responsabilidade |
|---|---|
| `src/legendar/domain/value_objects/text_layout.py` | `wrap_lines`: quebra equilibrada em até N linhas, sem perder palavras |
| `src/legendar/domain/entities/subtitle.py` | `SubtitleCue.lines()` usa a regra de layout para produzir as linhas publicadas |
| `src/legendar/infrastructure/filesystem/srt.py` | `format_srt` grava no máximo duas linhas por cue |
| `src/legendar/application/pipeline/segmentation.py` | `SegmentationPolicy` + `segment_alignment`: agrupa palavras, quebra por pausa/frase e subdivide cues acima do tempo de leitura |
| `src/legendar/application/pipeline/translation.py` | `TranslationUnit`, `TranslationResult`, `build_translation_units`, `apply_translation` |
| `src/legendar/application/pipeline/validation.py` | `validate_track`: falhas estruturais e avisos de legibilidade |
| `src/legendar/application/ports/protocols.py` | Porta `Translator` por cue, com idiomas explícitos |
| `src/legendar/application/pipeline/serial_pipeline.py` | Etapas `SEGMENTING`, `TRANSLATING`, `VALIDATING_SRT` e `PUBLISHING`; tradução e validação como passos próprios |
| `src/legendar/infrastructure/translation/nllb.py` | Adaptador `NllbTranslator`: cache, dispositivo, lotes, cancelamento e validação de saída |
| `src/legendar/bootstrap/app.py` | Compõe o tradutor real e calcula `translate_available`/`translate_readiness_details` |
| `src/legendar/presentation/qt/main_window.py` | Checkbox de tradução, tooltip de preflight e bloqueio do idioma final quando não há tradução |
| `tests/unit/domain/test_text_layout.py` | Regra de layout e `SubtitleCue.lines()` |
| `tests/unit/application/test_segmentation.py` | Política, pausas, frases, subdivisão por leitura e reuso de fronteiras |
| `tests/unit/application/test_translation.py` | Unidades, aplicação 1:1, tempos preservados e falhas explícitas |
| `tests/unit/application/test_validation.py` | Falhas estruturais, tolerância de fim de mídia e avisos |
| `tests/unit/infrastructure/test_nllb_translator.py` | Adaptador com tokenizador/modelo/lotes/dispositivo injetados |
| `tests/integration/test_srt_publication.py` | Formatação de duas linhas, overflow, linha única, roundtrip e publicação |
| `tests/integration/test_translation_publication.py` | Pipeline completo com tradutor falso e publicador real |
| `.github/workflows/phase6-quality.yml` | Matriz Python 3.10–3.13 e verificação de lock/lint/format |

## 3. Regras editoriais de segmentação

`SegmentationPolicy` é imutável e validada na construção; os padrões são:

| Parâmetro | Padrão | Efeito |
|---|---|---|
| `max_chars_per_line` | 42 | Largura máxima de uma linha publicada |
| `max_lines` | 2 | Duas linhas por cue |
| `max_chars_per_cue` | 84 | Capacidade total (2 × 42) |
| `min_cue_duration` | 1,0 s | Cue menor é mantida e reportada em `short_cues` |
| `max_cue_duration` | 7,0 s | Cue maior é subdividida antes de virar aviso |
| `max_gap` | 0,6 s | Pausa que separa grupos de palavras |
| `chars_per_second` | 17,0 | Velocidade de leitura usada no cálculo de tempo |
| `sentence_break_ratio` | 0,5 | Zona da cue onde uma quebra de frase é preferida |
| `min_words_per_split_part` | 2 | Evita fragmentos de uma palavra ao subdividir |

Regras efetivas:

1. Um segmento sem palavras alinhadas e sem intervalo válido é registrado em `dropped_segments`; nada é inventado.
2. Grupos de palavras contíguas são separados por pausa acima de `max_gap`, por fim de frase (`.!?…`), por fim de oração (`,;:—-`) próximo da metade da cue ou por excesso de caracteres.
3. Quando o texto excede o tempo de leitura ou a duração máxima, a cue é **subdividida em partes contíguas** cujas fronteiras são timestamps reais de palavras; o excesso remanescente é reportado em `overflow_cues`.
4. Cues subdivididas nunca compartilham a mesma palavra e nunca se sobrepõem.
5. `SegmentationResult` expõe `dropped_segments`, `short_cues`, `overflow_cues`, `source_segment_count`, `coverage_ratio` e `is_lossless` para diagnóstico.


## 4. Tradução por cue

A tradução roda **depois** da segmentação. Cada cue já possui tempo e texto finais, então o tradutor recebe exatamente as unidades que serão publicadas e devolve exatamente um texto por unidade.

Contrato (`Translator`):

```text
translate(
    units: tuple[TranslationUnit, ...],
    *,
    source_language: Language,
    target_language: Language,
    progress: ProgressSink,
    token: CancellationToken | None = None,
) -> TranslationResult
```

Garantias verificadas por testes:

- `TranslationUnit.index` é o índice final da cue e precisa ser ≥ 1; texto vazio é erro.
- `apply_translation` preserva `TimeRange` e `source_segments` de cada cue; apenas o texto e o idioma mudam.
- Contagem divergente, texto vazio ou tradução que não alterou nenhuma cue são falhas explícitas (`TranslationError`).
- Cues idênticas ao original são permitidas (nomes, siglas, interjeições) e contabilizadas como aviso com os índices.
- O pipeline traduz a partir do idioma **detectado** na transcrição, não do idioma declarado pelo usuário; se a mídia já está no idioma final, o job falha pedindo para desabilitar a tradução.
- O idioma devolvido pelo tradutor precisa ser o idioma final solicitado.

## 5. Validação e publicação

`validate_track(track, media_duration=...)` separa dois níveis:

| Nível | Condição | Efeito |
|---|---|---|
| Falha estrutural | trilho vazio | `SrtValidationError` |
| Falha estrutural | cue sem texto após normalização | `SrtValidationError` |
| Falha estrutural | cue termina depois do fim da mídia + 0,5 s de tolerância | `SrtValidationError` |
| Aviso | duração abaixo de `min_cue_duration` | `short_cues` |
| Aviso | duração acima de `max_cue_duration` | `long_cues` |
| Aviso | duração menor que o tempo de leitura | `overflow_cues` |
| Aviso | texto acima de `max_chars_per_cue` | `wide_cues` |

Publicação:

1. `format_srt` normaliza espaços e grava no máximo duas linhas por cue, usando `SubtitleCue.lines()`.
2. Texto maior que a capacidade permanece na última linha, íntegro; o validador sinaliza o excesso em vez de truncar.
3. `SrtPublisher.publish` escreve em arquivo temporário e troca atomicamente no destino.
4. `validate_roundtrip` reparseia o conteúdo e confirma índices, tempos e texto antes da troca.
5. `PUBLISHING` é o ponto de não retorno: não consulta cancelamento depois da troca.

## 6. Modelo, runtime e configuração

- Modelo padrão: `facebook/nllb-200-distilled-600M` (checkpoint multilíngue único para PT→EN e EN→PT).
- Origem definida no tokenizador (`por_Latn`/`eng_Latn`); destino via `forced_bos_token_id`.
- Cache dos pesos: `<models_dir>/nllb`; o download acontece sob demanda na primeira tradução.
- Dispositivo: `auto` resolve para CUDA quando disponível, senão CPU. MPS não é assumido compatível.
- Variáveis de ambiente: `LEGENDAR_TRANSLATE_DEVICE` (`auto`, `cpu`, `cuda`) e `LEGENDAR_TRANSLATE_MODEL`.
- Lotes de até 16 cue por chamada, com verificação de cancelamento a cada lote e progresso por cue.
- Limites de tokens: 256 de entrada e 256 de saída por cue; `num_beams=4`.
- Dependências nos perfis `runtime-cpu` e `runtime-cu128`: `transformers>=4.57,<5` e `sentencepiece>=0.2,<1`.
- Tokenizador lento (`use_fast=False`) para usar SentencePiece direto, sem camada de conversão.

Preflight da GUI (`bootstrap/app.py`):

- `translate_available` é verdadeiro somente quando `transformers` está instalado e a configuração de dispositivo/modelo é válida.
- Configuração inválida não impede a janela de abrir: o checkbox fica desabilitado e o tooltip mostra o motivo.
- Sem tradução marcada, o idioma final acompanha o idioma de origem e fica bloqueado; com tradução marcada, o campo é liberado.

## 7. Testes e critérios de aceitação

| Área | Evidência |
|---|---|
| Layout de duas linhas | `tests/unit/domain/test_text_layout.py` e `tests/integration/test_srt_publication.py` |
| Segmentação | `tests/unit/application/test_segmentation.py` (pausa, frase, leitura, reuso de fronteira, política inválida) |
| Tradução por cue | `tests/unit/application/test_translation.py` e `tests/unit/application/test_pipeline.py` |
| Validação | `tests/unit/application/test_validation.py` |
| Adaptador NLLB | `tests/unit/infrastructure/test_nllb_translator.py` (sem download: carregadores injetados) |
| Ponta a ponta sem rede | `tests/integration/test_translation_publication.py` |
| Arquitetura | `tests/test_architecture.py` (porta por cue e isolamento de `transformers`) |

Critérios de aceitação:

1. Nenhuma palavra do texto original é perdida na segmentação ou na publicação.
2. Todo `TimeRange` publicado é derivado de palavras alinhadas ou do intervalo original do segmento.
3. Cada cue publicada tem no máximo duas linhas de 42 caracteres; excessos são reportados.
4. Tradução devolve exatamente um texto por cue e mantém os tempos originais.
5. Jobs sem tradução continuam publicando o SRT no idioma detectado.
6. Suíte determinística verde em Python 3.10–3.13, Ruff check/format limpos.

## 8. Riscos e limites conhecidos

- NLLB pode devolver texto mais longo que o original; o layout e o validador sinalizam, mas a reescrita editorial não está no escopo.
- O adaptador precisa carregar pesos na primeira tradução; a primeira execução é lenta e não deve ser confundida com travamento.
- Qualidade tradutória em linguagem religiosa, nomes próprios e números não foi medida; medição é gate de produto da Fase 8.
- A tradução não é interrompida no meio de uma chamada de inferência; o cancelamento é cooperativo entre lotes.
- O SRT publicado não preserva o texto original quando a tradução é solicitada; arquivar o original exige decisão futura.

## 9. Comandos de verificação

```bash
uv lock --check
uv sync --locked --group dev --group phase0

QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q
uv run --locked --no-sync ruff check src/legendar tests scripts
uv run --locked --no-sync ruff format --check src/legendar tests/unit tests/integration tests/gui tests/helpers tests/test_architecture.py
```

## 10. Pendências de homologação do produto (não bloqueiam a Fase 7)

1. Avaliar tradução PT↔EN em corpus autorizado de pregações com revisão humana.
2. Medir tempo de primeira tradução, memória e comportamento no computador-alvo.
3. Confirmar a decisão editorial sobre manter ou não o texto original em arquivo separado.
4. Homologar a janela com mídia real, arquivos longos e cancelamento durante a tradução.
