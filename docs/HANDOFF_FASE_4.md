# Handoff técnico — Fase 4: reconhecimento Whisper

- **Status:** implementação concluída na branch `phase-4/whisper-recognition`; validação automatizada/merge em andamento
- **Base:** `main` após integração da Fase 3
- **Fronteira:** reconhecimento lexical local; não implementa forced alignment, tradução ou SRT
- **Plano operacional:** [FASE_4_PLANO.md](FASE_4_PLANO.md)

## 1. Arquitetura e arquivos

| Arquivo | Responsabilidade |
|---|---|
| `src/legendar/infrastructure/transcription/whisper.py` | Adaptador local `WhisperTranscriber`; lazy import, carga/cache do modelo, idioma, validação de WAV e normalização de resposta |
| `src/legendar/infrastructure/transcription/__init__.py` | Export público do adaptador |
| `src/legendar/bootstrap/app.py` | Composição de um transcriber compartilhado entre pipelines e preflight do pacote |
| `src/legendar/presentation/qt/main_window.py` | Estado de prontidão separado para FFmpeg/ffprobe e Whisper; botão de geração bloqueado quando runtime ausente |
| `tests/unit/infrastructure/test_whisper_transcriber.py` | Testes herméticos do adaptador, sem Torch, download ou rede |
| `scripts/phase4_model_benchmark.py` | Avaliação lexical por modelo |
| `tests/unit/test_phase4_model_benchmark.py` | Parser de manifesto e normalização de métricas |
| `.github/workflows/phase4-quality.yml` | Matriz Python 3.10–3.13 e smoke real CPU PT-BR/EN |

A porta `Transcriber` e as entidades `Transcript`/`TranscriptSegment` preexistiam. O adaptador pertence somente à infraestrutura. Aplicação/domínio não importam Whisper ou PyTorch.

## 2. Contrato de áudio e resultado

- Entrada: `AudioAsset` produzido pela Fase 3, WAV PCM s16le, mono, 16 kHz.
- A leitura valida sample rate, canais, largura de amostra, compressão, quantidade de frames e forma de onda finita.
- O Whisper executa `task="transcribe"`; não é usado para tradução.
- Idioma manual é passado ao motor. Sem seleção manual, a resposta detectada é mapeada para PT ou EN.
- Resposta fora do suporte PT/EN falha explicitamente.
- Texto e ordem dos segmentos são mantidos; ranges e palavras ficam vazios.
- `model_name` e versão da distribuição são preservados em `Transcript`.

Não usar as faixas aproximadas dos segmentos Whisper como timestamps finais. A Fase 5 deverá alinhar o texto com WhisperX, preservar o offset da mídia e validar cada âncora temporal.

## 3. Runtime, cache e comportamento

- `openai-whisper` já está declarado no extra `runtime-cpu` e `runtime-cu128`; nenhuma dependência direta nova foi necessária.
- Variáveis: `LEGENDAR_WHISPER_MODEL=base` e `LEGENDAR_WHISPER_DEVICE=auto`.
- Perfis aceitos: `tiny`, `base`, `small`, `medium`, `large`, `turbo`; todos multilíngues.
- Dispositivos: `auto`, `cpu`, `cuda`, `mps`; detecção automática prioriza CUDA/MPS/CPU.
- Pesos persistem em `<models_dir>/whisper`. O modelo é carregado sob demanda e reutilizado em memória.
- A UI não bloqueia ao carregar/transcrever: a operação acontece na QThread do job.
- O progresso é indeterminado durante inferência; não estimar porcentagem ou tempo restante.
- Cancelamento consultado antes/depois da inferência. A API de alto nível não expõe interrupção imediata durante um decode longo; isso está explicitado no plano.

## 4. Benchmark reproduzível

FLEURS (Google, CC-BY-4.0), configurações `pt_br` e `en_us`, é o corpus padrão. O benchmark compara modelos e registra WER/CER, tempo de reconhecimento, RTF, RSS máximo, versões, plataforma e IDs de amostra.

Também aceita TSV local com cabeçalho `language`, `audio`, `reference`. Áudios podem ser referenciados por caminho absoluto ou relativo ao manifesto; áudio local precisa ser lido por SoundFile e estar em 16 kHz. O relatório não contém transcrições, texto de referência, áudio ou caminho local.

Comando recomendado no computador-alvo:

```bash
python scripts/phase0_inventory.py --probe-torch \
  --output "$HOME/legendar-phase4-environment.json"

uv sync --locked --no-dev --group phase0 --extra runtime-cpu
uv run --locked --no-dev --group phase0 --extra runtime-cpu \
  python scripts/phase4_model_benchmark.py \
  --models tiny,base,small --samples-per-language 10 \
  --device auto --cache-dir .cache/phase4 \
  --output "$HOME/legendar-phase4-benchmark.json"
```

Revisar os dados de hardware antes de compartilhar o inventário. Benchmark em runner GitHub não substitui este resultado.

## 5. Testes e evidências

- Testes do adaptador usam `model_loader`, `device_resolver` e `audio_loader` injetados.
- Cobrem idioma forçado/detectado, texto/segmentos, ausência de timestamps, cache em memória, perfis inválidos, erro de carga/inferência, resposta vazia/inválida e cancelamento.
- Testes do benchmark cobrem aliases PT/EN, validação do manifesto, caminhos relativos e normalização.
- O job CPU de CI usa modelos `tiny`, `base` e `small`, duas amostras FLEURS por idioma e publica JSON de métricas. Registrar aqui o run final após CI.

## 6. Pendências de homologação

1. Rodar inventário atualizado no computador-alvo; o último perfil do documento de estado é um Ryzen 3 2200G com quatro CPUs lógicas, 12,59 GiB RAM e Radeon Vega integrada, anterior à implantação deste adaptador.
2. Executar comparação de modelos no hardware real e observar RAM/disco/tempo.
3. Montar/revisar amostras de fala representativas de pregações PT-BR e inglês, com referência textual humana; não usar transcrições privadas sem autorização.
4. Definir um perfil recomendado somente depois das medições; `base` é um padrão provisório configurável.
5. A Fase 5 deverá realizar avaliação temporal humana; WER/CER não são métricas de sincronização.

## 7. Próxima fronteira

Após merge, a Fase 5 pode consumir `Transcript` original e realizar forced alignment com WhisperX. Não mover alinhamento para este adaptador nem adicionar word timestamps aproximados nesta fronteira.
