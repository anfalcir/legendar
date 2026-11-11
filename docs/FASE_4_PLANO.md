# Plano operacional — Fase 4: reconhecimento Whisper

- **Status:** implementação concluída na branch `phase-4/whisper-recognition`; integração depende de CI e PR
- **Base:** `main` após Fase 3 (HEAD inicial `cbba552a9b72d2dee3f4daed59607c39eda21d7a`)
- **Escopo:** transcrição local em idioma original, suporte PT-BR/EN, perfis Whisper, cache, erros, worker e benchmark
- **Fora do escopo:** forced alignment, timestamps por palavra, tradução, segmentação final e publicação SRT

## 1. Objetivo

Conectar o reconhecimento de fala real à porta `Transcriber` já definida na arquitetura, sem acoplar domínio/aplicação à biblioteca OpenAI Whisper. A saída desta fase é texto original segmentado pelo decoder e idioma identificado/confirmado. Não é uma legenda temporalmente alinhada.

## 2. Entregas

1. Adaptador `WhisperTranscriber` em `infrastructure/transcription`, com imports pesados tardios, carga de modelo sob demanda e reutilização em memória entre jobs.
2. Reconhecimento explícito com `task="transcribe"`; idiomas PT e EN podem ser informados pelo usuário ou detectados pelo Whisper.
3. Leitura validada do contrato de áudio da Fase 3: WAV PCM signed 16-bit, mono, 16 kHz; arquivo vazio, truncado, com formato divergente ou não finito é rejeitado.
4. Cache persistente sob `AppSettings.models_dir/whisper`, fora do workspace temporário de cada job.
5. Perfis multilíngues `tiny`, `base`, `small`, `medium`, `large` e `turbo`; padrão inicial `base`, configurável por `LEGENDAR_WHISPER_MODEL`.
6. Dispositivo configurável por `LEGENDAR_WHISPER_DEVICE` (`auto`, `cpu`, `cuda`, `mps`); autodetecção prioriza CUDA, MPS e CPU.
7. Erros de instalação, download, dispositivo, inferência, resposta inválida e idioma fora do produto convertidos em erros de domínio compreensíveis.
8. Modelo compartilhado no bootstrap, com carregamento serializado e inferência serializada; processamento permanece na QThread do job.
9. Preflight de prontidão da GUI: a geração só é habilitada quando FFmpeg/ffprobe e Whisper estão disponíveis; ausência de Whisper não impede abrir a interface nem inspecionar mídia.
10. Benchmark reproduzível `scripts/phase4_model_benchmark.py`: WER, CER, tempo, RTF, RSS, versões e comparação entre perfis.
11. Benchmark público FLEURS e manifesto TSV local de áudio/referência para amostras autorizadas; o relatório não incorpora áudio nem texto reconhecido.
12. Workflow de qualidade com matriz determinística Python 3.10–3.13 e smoke real CPU PT-BR/EN comparando `tiny`, `base` e `small`.

## 3. Decisões técnicas

### Reconhecimento e idioma

- Whisper recebe `task="transcribe"`; nunca usar `task="translate"` nesta fase.
- Origem informada pelo usuário é enviada ao motor; quando ausente, o motor detecta o idioma.
- Apenas PT-BR (`pt`) e inglês (`en`) são aceitos pelo domínio nesta versão. Idiomas detectados fora dessa matriz produzem erro explícito, sem rotular incorretamente o resultado.
- Os segmentos de texto são preservados na ordem retornada. A saída não carrega palavras nem ranges temporais inferidos.
- `language_probability` permanece ausente porque a chamada pública de alto nível retorna código de idioma, não uma probabilidade de confiança auditável para esta porta.

### Timestamps e fronteira da Fase 5

O Whisper devolve limites aproximados de segmentos e pode oferecer word timestamps experimentais, mas esses dados não substituem forced alignment. O adaptador não transfere os tempos do decoder para `TranscriptSegment.range` e não cria `TranscriptWord`. A Fase 5 fará alinhamento com WhisperX e aplicará offsets/chunks na timeline global.

### Perfis, dispositivo e cache

- Padrão inicial: `base`. É um ponto de partida configurável, não uma declaração de melhor qualidade/performance.
- `tiny` favorece velocidade; `small` e superiores podem elevar qualidade e custo de CPU/RAM. A decisão final depende das medições.
- `auto` escolhe CUDA, depois MPS, depois CPU; seleção forçada indisponível falha com mensagem de domínio.
- Os pesos ficam fora do Git, sob `<models_dir>/whisper`, e são baixados no primeiro uso.
- O cache do disco persiste entre execuções; o modelo carregado é reutilizado pelo objeto compartilhado no bootstrap.

### Progresso e cancelamento

A inferência de alto nível do OpenAI Whisper não oferece callback de progresso/cancelamento por janela ao adaptador. Durante reconhecimento a UI permanece em progresso indeterminado (sem percentual inventado). O token é consultado antes do carregamento, antes da inferência e assim que a chamada retorna. Portanto, um pedido de cancelamento durante uma inferência longa é concluído no retorno seguro do Whisper, não interrompe à força o kernel de inferência. A GUI permanece responsiva porque o trabalho ocorre no worker.

## 4. Configuração e execução

Valores padrão:

| Variável | Padrão | Valores |
|---|---|---|
| `LEGENDAR_WHISPER_MODEL` | `base` | `tiny`, `base`, `small`, `medium`, `large`, `turbo` |
| `LEGENDAR_WHISPER_DEVICE` | `auto` | `auto`, `cpu`, `cuda`, `mps` |

Instalação de runtime (perfil já declarado no manifesto):

```bash
# CPU
uv sync --locked --no-dev --extra runtime-cpu

# NVIDIA CUDA 12.8, somente em sistema/driver compatível
uv sync --locked --no-dev --extra runtime-cu128
```

Primeira execução pode baixar os pesos do modelo; precisa de acesso à rede. Depois disso, o arquivo de modelo é lido do cache local. A aplicação não envia áudio para serviço externo de reconhecimento.

## 5. Benchmark

FLEURS é a referência pública controlada de fala lida e licenciada CC-BY-4.0. Para comparação local com 10 amostras por idioma:

```bash
uv sync --locked --no-dev --group phase0 --extra runtime-cpu
uv run --locked --no-dev --group phase0 --extra runtime-cpu \
  python scripts/phase4_model_benchmark.py \
  --models tiny,base,small \
  --samples-per-language 10 \
  --device auto \
  --cache-dir .cache/phase4 \
  --output phase4-model-benchmark.json
```

Manifesto local TSV para referências revisadas:

```text
language<TAB>audio<TAB>reference
pt-BR<TAB>./amostra-01.wav<TAB>Texto de referência revisado.
en<TAB>./sample-02.wav<TAB>Reviewed reference text.
```

```bash
uv run --locked --no-dev --group phase0 --extra runtime-cpu \
  python scripts/phase4_model_benchmark.py \
  --models tiny,base,small --manifest ./corpus.tsv \
  --device cpu --cache-dir .cache/phase4 \
  --output ./relatorio-fase4.json
```

O relatório guarda WER/CER, duração, tempo de transcrição, RTF, RSS máximo, modelo, runtime e identificadores de amostra. Não grava áudio, caminho local, transcrição reconhecida nem referência textual. Para material privado, mantenha o relatório e o manifesto localmente.

## 6. Critérios de aceite da implementação

- [x] Adaptador concreto atrás de `Transcriber`, sem import de Whisper/Torch no import-time.
- [x] Idioma forçado e detecção automática com mapeamento explícito PT/EN.
- [x] Texto reconhecido preservado, sem timestamps ou palavras fabricados.
- [x] Cache de disco e reutilização do modelo em memória.
- [x] Dispositivo selecionável e falha clara para backend indisponível.
- [x] Tratamento de erros/cancelamento em fronteiras seguras.
- [x] Execução em worker e prontidão Whisper refletida na GUI.
- [x] Testes unitários determinísticos sem download de pesos/rede.
- [x] Benchmark com FLEURS e manifesto local, WER/CER/RTF/RSS.
- [ ] Workflow da Fase 4 aprovado em todos os jobs.
- [ ] Execução do benchmark no computador-alvo com inventário atualizado.
- [ ] Avaliação com fala representativa de pregações e transcrições de referência revisadas.

Os dois últimos itens são gates de qualidade/hardware: CI em runner GitHub comprova execução do código, não desempenho no computador-alvo nem qualidade em conteúdo real. Não aprovar perfil recomendado apenas por uma amostra FLEURS pequena.

## 7. Riscos e limites

- O primeiro download de pesos depende de internet, espaço livre e disponibilidade upstream.
- Perfis grandes podem exceder RAM/tempo aceitáveis no computador-alvo.
- Cancelamento durante a chamada de alto nível só é consumido quando o decoder retorna.
- WER/CER não medem precisão temporal, alinhamento, legibilidade, diarização nem qualidade de tradução.
- FLEURS é fala lida; não representa sermões, sotaques/nomes próprios de interesse, música, sobreposição ou acústica do uso final.
- A precisão de palavras/timestamps permanece na Fase 5.

## 8. Próximo checkpoint

Após workflow e revisão da PR, integrar esta fase à `main`. Antes de declarar um perfil ideal para o computador-alvo, executar inventário atualizado e benchmark local; a aplicação pode usar `base` como padrão provisório, mas a recomendação final deve seguir evidências.
