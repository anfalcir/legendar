# Handoff técnico — Fase 5: alinhamento temporal WhisperX

- **Status:** implementação concluída e integrada à `main` pela PR [#6](https://github.com/anfalcir/legendar/pull/6), squash `5c9a2ba48a7e2d16d2099511c3c1456c59ae299c`
- **CI:** push [#42935484072](https://github.com/anfalcir/legendar/actions/runs/42935484072) e PR [#42935490648](https://github.com/anfalcir/legendar/actions/runs/42935490648), ambos 5/5; gates herdados Fases 0/1/3/4 aprovados
- **Plano operacional:** [FASE_5_PLANO.md](FASE_5_PLANO.md)
- **Fronteira:** forced alignment local PT-BR/EN, sem tradução ou publicação SRT

## 1. Arquitetura

| Arquivo | Responsabilidade |
|---|---|
| `src/legendar/infrastructure/alignment/whisperx.py` | Adaptador `WhisperXAligner`; modelos PT/EN, NLTK, cache, alinhamento, validações e diagnósticos |
| `src/legendar/infrastructure/alignment/__init__.py` | Export do adaptador |
| `src/legendar/infrastructure/media/waveform.py` | Leitura validada de WAV PCM s16le mono/16 kHz compartilhada entre motores |
| `src/legendar/domain/entities/transcript.py` | `TranscriptSegment.alignment_window` distingue janela aproximada de range final |
| `src/legendar/domain/value_objects/time.py` | `TimelineMapping` representa offset de origem negativo; `TimeRange` impede timestamp final negativo |
| `src/legendar/infrastructure/transcription/whisper.py` | Preserva os limites aproximados do decoder somente em `alignment_window` |
| `src/legendar/bootstrap/app.py` | Injeta o alinhador real e verifica pacote/configuração |
| `src/legendar/presentation/qt/main_window.py` | Preflight WhisperX e bloqueio do botão quando runtime/publicador não estão prontos |
| `src/legendar/application/pipeline/serial_pipeline.py` | Propaga palavras não alinhadas e avisos de anomalia |
| `tests/unit/infrastructure/test_whisperx_aligner.py` | Testes determinísticos do adaptador |
| `tests/unit/test_phase5_alignment_evaluation.py` | Testes do manifesto e métricas |
| `scripts/phase5_alignment_smoke.py` | Smoke integrado real Whisper + WhisperX/FLEURS |
| `scripts/phase5_alignment_evaluation.py` | Avaliação local contra fronteiras humanas |
| `.github/workflows/phase5-quality.yml` | Matriz Python 3.10–3.13 e runtime real CPU PT-BR/EN |

## 2. Contrato do adaptador

Entrada:
- `AudioAsset` produzido pela Fase 3, WAV PCM s16le, mono, 16 kHz.
- `Transcript` original da Fase 4.
- Cada segmento deve ter `alignment_window` local ao WAV, preenchida a partir dos limites aproximados do Whisper.

Saída:
- Cada palavra original permanece na ordem da transcrição.
- Palavra com alinhamento válido recebe `TranscriptWord.range` em timeline global e score do WhisperX.
- Palavra sem intervalo, palavra ausente no output, score inválido, janela inválida ou texto incompatível permanece sem range e aparece em `AlignmentDiagnostics.unmatched_words/issues`.
- `TranscriptSegment.range` é derivado do primeiro/último limite de palavras alinhadas naquele segmento; nunca copia a janela aproximada.

O alinhador executa WhisperX com `interpolate_method="ignore"`. Não alterar para `nearest`, `linear` ou outro método que preencha lacunas sem evidência acústica, salvo nova decisão documentada e avaliação com referência humana.

## 3. Modelos e runtime

- WhisperX 3.8.6 já está fixado no `uv.lock`.
- PT: `jonatasgrosman/wav2vec2-large-xlsr-53-portuguese`.
- EN: `WAV2VEC2_ASR_BASE_960H`.
- Variável `LEGENDAR_ALIGN_DEVICE`: `auto` (CUDA, senão CPU), `cpu` ou `cuda`.
- Cache: `<models_dir>/whisperx-align`; NLTK: `<models_dir>/whisperx-align/nltk_data`.
- Carga e downloads ocorrem no worker na primeira etapa de alinhamento; pesos e Punkt persistem entre execuções.
- O adaptador serializa inferência e reutiliza modelo carregado por idioma.

Não afirmar que MPS é suportado pelo alinhador desta versão. Não instalar outro runtime paralelo ou alterar versões WhisperX/Torch sem revalidar lock e matriz completa.

## 4. Timeline, falhas e cancelamento

A conversão global é feita uma vez:

~~~text
timestamp_global = audio.timeline_start_seconds + timestamp_local
~~~

Offsets de stream negativos são aceitos na transformação, mas TimeRange final continua não negativo. Palavra antes de zero fica sem alinhamento; nunca aplicar clipping para criar range artificial.

Janelas ausentes/fora do WAV/>90 s não carregam modelo nem chamam WhisperX. Palavras reconciliadas por texto e sequência evitam deslocamento quando WhisperX omite tokens sem caracteres alinháveis. Overlap acima de 50 ms, score inválido e tempos fora da busca/mídia viram diagnóstico.

Token de cancelamento é checado antes de carregar, antes de cada segmento e após cada chamada. Chamada de alto nível não é interrompida durante inferência; UI permanece responsiva no worker.

A GUI deve continuar bloqueando a geração final enquanto o publicador SRT estiver em placeholder. Isso é esperado até a conclusão das Fases 6/7; inspeção de mídia permanece disponível.

## 5. Avaliação

### Smoke FLEURS

~~~bash
uv sync --locked --group dev --group phase0 --extra runtime-cpu
uv run --locked --group dev --group phase0 --extra runtime-cpu \
  python scripts/phase5_alignment_smoke.py \
  --model tiny --samples-per-language 1 --device cpu \
  --cache-dir .cache/phase5 --output phase5-alignment-smoke.json
~~~

O smoke executa reconhecimento e alinhamento reais; registra WER lexical, RTF, cobertura e limites válidos. Não mede erro de timestamp humano.

### Corpus local anotado

O JSONL deve conter sample_id, caminho WAV, idioma, offset global, segmentos, janela local e fronteiras globais de cada palavra. Exemplo completo e comandos em [FASE_5_PLANO.md](FASE_5_PLANO.md).

~~~bash
uv run --locked --group dev --group phase0 --extra runtime-cpu \
  python scripts/phase5_alignment_evaluation.py \
  --manifest ./referencias-humanas.jsonl \
  --models-dir .cache/phase5 --device auto \
  --output ./avaliacao-alinhamento.json
~~~

Relatório sanitizado sem caminho/áudio/texto. Métricas por início e fim, mediana/P95, cobertura e não alinhadas. Metas do plano mestre: mediana ≤150 ms, P95 ≤350 ms, zero intervalos inválidos e não alinhadas visíveis. Não declarar aceitação automática.

## 6. Pendências de homologação do produto (não bloqueiam o início da Fase 6)

1. Executar benchmark com amostras autorizadas de pregações PT-BR e inglês, após revisão humana da transcrição e fronteiras.
2. Atualizar inventário e executar os modelos no computador-alvo; observar RAM, latência, cache e comportamento ao alternar idiomas.
3. Inspecionar manualmente casos com overlap, nomes próprios, números, fala rápida, pausas, música e ruído.
4. Aprovar os limites median/P95 com dados suficientes; a pequena amostra FLEURS não comprova precisão de pregação.
5. Manter exportação final bloqueada até implementação do publicador SRT na Fase 6/7.

## 7. Próxima fronteira

A Fase 5 já está integrada à `main`. A Fase 6 está preparada para consumir `AlignmentResult` e implementar tradução, segmentação e SRT; a decisão de provedor/custo/privacidade deve ser tomada no checkpoint inicial da Fase 6. A integração GUI ponta a ponta continua sendo a Fase 7. Não deslocar publicação SRT para este adaptador. A homologação de precisão temporal em pregações e no computador-alvo permanece gate de produto.
