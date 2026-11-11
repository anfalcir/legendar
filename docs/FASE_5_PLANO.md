# Fase 5 — Benchmark e aceleração da transcrição (ASR)

**Status:** implementação inicial em validação na branch `phase-5/asr-performance`.
**Objetivo:** reduzir o tempo de reconhecimento sem perda lexical nem quebra do contrato temporal consumido pelo WhisperX.

## 1. Estratégia

A porta `Transcriber` continua sendo a única interface conhecida pelo pipeline. Dois adaptadores ficam disponíveis:

- `WhisperTranscriber`: OpenAI Whisper + PyTorch, baseline atual.
- `FasterWhisperTranscriber`: faster-whisper + CTranslate2, candidato otimizado.

O backend do produto permanece `whisper` por padrão. A adoção do candidato é explícita por configuração; não ocorre apenas porque o pacote está instalado.

## 2. Seleção do backend e configuração

Variáveis de ambiente:

| Variável | Padrão | Significado |
|---|---|---|
| `LEGENDAR_ASR_BACKEND` | `whisper` | `whisper` ou `faster-whisper` |
| `LEGENDAR_WHISPER_MODEL` | `base` | Perfil do modelo |
| `LEGENDAR_WHISPER_DEVICE` | `auto` | `auto`, `cpu` ou `cuda` |
| `LEGENDAR_FASTER_WHISPER_COMPUTE_TYPE` | automático | CPU: `int8`; CUDA: `float16` |
| `LEGENDAR_FASTER_WHISPER_CPU_THREADS` | `4` | Threads do CTranslate2 |
| `LEGENDAR_FASTER_WHISPER_BEAM_SIZE` | `5` | Beam search |
| `LEGENDAR_FASTER_WHISPER_VAD_FILTER` | `false` | VAD experimental; desligado por padrão |

O modelo `large` é mapeado para `large-v3` no adaptador faster-whisper. MPS não é suportado pelo CTranslate2; use CPU ou CUDA.

O perfil de runtime do projeto já instala WhisperX, que declara faster-whisper/CTranslate2 como dependências transitivas. A aplicação faz detecção de disponibilidade no preflight e não deve encerrar a GUI se o backend selecionado estiver ausente ou mal configurado; nesse caso, a prontidão de transcrição é marcada como indisponível e o baseline não é selecionado silenciosamente.

## 3. Equivalência e integridade

O candidato mantém, explicitamente:

- tarefa `transcribe`, idioma solicitado/detectado e beam padrão 5;
- fallback de temperatura e limiares de compressão, log-probabilidade e silêncio próximos aos defaults do Whisper;
- condicionamento pelo texto anterior;
- VAD desligado no comparativo inicial;
- timestamps de segmento somente como `alignment_window` local ao WAV;
- nenhuma fabricação de timestamps de palavra;
- consumo integral do generator do faster-whisper antes de finalizar a transcrição;
- cancelamento cooperativo durante o consumo dos segmentos;
- carga tardia, cache do modelo e inferência serializada;
- métricas de carga, leitura de áudio, inferência, segmentos e palavras.

Os timestamps de ambos os motores seguem para o mesmo WhisperX. O forced alignment continua responsável pelos tempos confiáveis de palavra e pela conversão à linha do tempo global.

## 4. Benchmark pareado

O benchmark `scripts/phase5_asr_benchmark.py` executa os dois backends sobre as mesmas amostras e calcula WER, CER, tempo de parede, fator de tempo real (RTF), carga do modelo, inferência, memória de pico e configuração do runtime.

FLEURS PT-BR/EN é o corpus público padrão (fala lida, CC-BY-4.0). Para amostras locais, use um TSV com cabeçalho:

```tsv
language	audio	reference
pt-BR	./amostra-pt.wav	Transcrição humana revisada.
en-US	./sample-en.wav	Reviewed human reference.
```

Execução recomendada no computador de referência:

```bash
PYTHONPATH=src uv run --locked --group dev --group phase0 --extra runtime-cpu \
  python scripts/phase5_asr_benchmark.py \
  --backends openai-whisper,faster-whisper \
  --models base \
  --samples-per-language 10 \
  --device cpu \
  --cpu-threads 4 \
  --beam-size 5 \
  --manifest ./corpus/manifest.tsv \
  --output ./phase5-asr-benchmark-local.json
```

O primeiro sample de cada backend/model inclui carga fria; os seguintes reutilizam o modelo. Compare os relatórios com o mesmo corpus, cache e computador. Não compare tempos de runners GitHub com os do computador de referência.

## 5. Alinhamento e VAD

`scripts/phase5_alignment_smoke.py` aceita `--backend openai-whisper|faster-whisper` e envia a saída de cada motor ao mesmo WhisperX. O smoke verifica WER, cobertura estrutural, palavras não alinhadas e limites dos timestamps. FLEURS não tem anotações humanas de fronteiras de palavra, portanto esses checks não medem erro temporal real.

VAD é experimento separado. Não ativar por padrão sem medir perda de fala baixa, pausas, início/fim de palavras e alinhamento restaurado. O comparativo inicial usa VAD desligado nos dois caminhos.

Não paralelizar janelas de áudio sem overlap, contexto e reconciliação de fronteiras testados. Evitar oversubscription e manter uma única inferência por adaptador.

## 6. Critérios de aceite

A adoção de faster-whisper como padrão exige, em conjunto:

1. WER/CER por idioma dentro do gate definido contra o baseline no mesmo corpus, com revisão humana de nomes próprios, números, negações e trechos difíceis.
2. Ausência de perda ou duplicação de texto; consumo integral dos segmentos.
3. WhisperX com cobertura e alinhamento aprovados, sem piora de palavras não alinhadas ou timestamps inválidos.
4. Ganho de desempenho reproduzível no hardware de referência, com resultados frios e quentes, configuração e memória registrados.
5. Interface responsiva, cancelamento funcional e progresso sem percentuais fictícios.
6. Backend baseline preservado como fallback configurável.

Smoke CI com poucas amostras comprova integração e não substitui o corpus humano nem a homologação real. A gravação de 37min10s e o hardware de referência continuam necessários para a decisão operacional final.

## 7. Evidências

- Benchmark pareado: `phase5-asr-benchmark.json` (artefato do workflow).
- Smoke Whisper + WhisperX: `phase5-alignment-smoke.json`.
- Smoke faster-whisper + WhisperX: `phase5-faster-whisper-alignment-smoke.json`.
- Relatórios sanitizados não incluem áudio, texto reconhecido, referências, URLs ou caminhos de mídia.
