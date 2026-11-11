# Plano operacional — Fase 5: alinhamento temporal

- **Status:** implementação em execução na branch `phase-5/temporal-alignment`
- **Base:** `main` com Fase 4 integrada; HEAD inicial `13af311e3469493e4f69e3faa62f2be043d43839`
- **Escopo:** forced alignment local PT-BR/EN, timestamps por palavra, offset global, cobertura, anomalias e avaliação contra fronteiras humanas
- **Fora do escopo:** tradução, segmentação editorial final, publicação SRT e integração completa da GUI (Fases 6/7)

## 1. Objetivo

Implementar um adaptador real de forced alignment atrás da porta `Aligner` existente, usando WhisperX 3.8.6 já fixado no lockfile. A transcrição textual permanece sob responsabilidade do OpenAI Whisper (Fase 4); o WhisperX recebe o texto reconhecido e devolve limites temporais alinhados por palavra.

A saída precisa distinguir rigorosamente:

- **Janela de busca:** limites aproximados do decoder Whisper, em tempo local do WAV normalizado; restringe onde o alinhador procura.
- **Timestamp alinhado:** início/fim calculados pelo forced alignment e convertidos para a timeline global da mídia original.

A janela aproximada nunca é promovida a `TranscriptSegment.range` ou `TranscriptWord.range`. Uma palavra sem evidência temporal permanece no resultado, sem timestamp.

## 2. Entregas

1. Adaptador `WhisperXAligner` em `infrastructure/alignment` com import tardio, cache persistente e carregamento sob demanda por idioma.
2. Modelos de alinhamento configurados para `pt` e `en`; nenhum idioma fora do escopo é aceito silenciosamente.
3. Execução serializada por instância, com cache em memória por idioma e arquivos de modelo fora do workspace temporário.
4. Pré-preparo de `punkt_tab` NLTK no cache do produto, sem depender de download para diretório arbitrário do usuário.
5. Entrada exclusivamente no contrato WAV PCM signed 16-bit, mono, 16 kHz já produzido pela Fase 3.
6. Uso de `interpolate_method="ignore"`; o WhisperX não preenche automaticamente lacunas com tempos interpolados.
7. Associação das palavras devolvidas pelo alinhador ao texto original por conteúdo e ordem, para que uma palavra omitida não desloque os timestamps das palavras seguintes.
8. Preservação de palavras não alinhadas, texto original e diagnóstico por segmento.
9. Conversão de tempo local para timeline global com o offset do stream aplicado exatamente uma vez.
10. Validação de duração, janela, monotonicidade, sobreposição, limites da mídia e score devolvido pelo alinhador.
11. Integração no bootstrap e preflight Qt: geração permanece bloqueada se WhisperX não estiver instalado/configurado.
12. Geração final continua bloqueada enquanto o publicador SRT permanecer placeholder das Fases 6/7; inspeção de mídia e abertura da GUI continuam disponíveis.
13. Testes determinísticos do adaptador, domínio, bootstrap, GUI e propagação de anomalias ao pipeline.
14. Smoke real com Whisper + WhisperX em FLEURS PT-BR/EN.
15. Avaliador local de manifesto JSONL com fronteiras de palavras anotadas por humanos, calculando mediana/P95 e cobertura sem copiar dados privados para o relatório.

## 3. Decisões técnicas

### Modelos e dispositivos

- Versão WhisperX: 3.8.6, conforme `pyproject.toml` e `uv.lock`; não ampliar faixa ou alterar o runtime nesta fase.
- Português: `jonatasgrosman/wav2vec2-large-xlsr-53-portuguese`.
- Inglês: `WAV2VEC2_ASR_BASE_960H` (bundle torchaudio).
- `LEGENDAR_ALIGN_DEVICE` aceita `auto`, `cpu` ou `cuda`. `auto` seleciona CUDA quando disponível; caso contrário usa CPU.
- MPS não é anunciado para o alinhador WhisperX desta versão. O reconhecimento Whisper da Fase 4 continua aceitando MPS conforme o runtime.
- Pesos ficam sob `<models_dir>/whisperx-align`; dados NLTK ficam em `<models_dir>/whisperx-align/nltk_data`. Nunca versionar pesos/cache.
- O modelo de idioma é carregado apenas quando existir pelo menos uma janela válida; a instância compartilha e reutiliza os modelos PT/EN.

### Janelas e palavra não alinhada

- Cada `TranscriptSegment.alignment_window` contém o intervalo aproximado local que veio do Whisper.
- Janela ausente, fora da duração do WAV ou maior que 90 segundos não é processada; as palavras ficam explicitamente sem alinhamento e recebem diagnóstico.
- A saída de WhisperX é reconciliada por texto e ordem. A ausência de um token no array de saída não pode fazer a palavra seguinte herdar sua posição.
- Score ausente/fora de [0, 1], texto incompatível, tempo ausente, tempo invertido e timestamp fora da janela/mídia não são promovidos a palavra alinhada.
- Sobreposição temporal acima da tolerância de 50 ms é sinalizada; não é corrigida silenciosamente.

### Timeline global e offsets

A regra é:

~~~text
tempo_global = offset_do_stream + tempo_local_do_WAV
~~~

O objeto `TimelineMapping` pode representar um offset de origem negativo (algumas faixas começam antes de zero); o `TimeRange` final continua exigindo timestamps não negativos. Se uma palavra calculada cair antes de zero, ela permanece sem timestamp e recebe diagnóstico — não se faz clipping nem deslocamento artificial.

O offset é aplicado somente após o WhisperX devolver o tempo local. O offset do contêiner não é enviado ao modelo e não é somado novamente ao tempo que ele devolve.

### Progresso e cancelamento

WhisperX pode reportar progresso por callback; o adaptador o converte em fração do segmento atual. Carregamento de pesos e preparação do NLTK podem deixar a UI em progresso indeterminado, sem porcentagem inventada.

O token de cancelamento é consultado antes de carregar/preparar, antes de cada segmento e depois de cada chamada de alinhamento. A chamada de alto nível WhisperX não é interrompida à força durante a inferência; o cancelamento é consumido ao retornar da chamada segura. A QThread mantém a interface responsiva.

### Diagnósticos e parcialidade

`Aligner` retorna `AlignmentResult` com:
- contagem de palavras efetivamente alinhadas;
- palavras esperadas sem intervalo;
- problemas estáveis como `missing_alignment_window`, `unmatched_word`, `word_text_mismatch`, `out_of_bounds`, `window_too_long`, `invalid_word_score`, `overlap` e `unexpected_aligned_word`.

O pipeline conserva as palavras não alinhadas e expõe avisos de anomalia. Uma saída parcial não é declarada completa. Se nenhuma palavra for alinhada, a etapa falha com erro de domínio, em vez de avançar fingindo sucesso.

## 4. Avaliação reproduzível

### Smoke automatizado público

~~~bash
uv sync --locked --group dev --group phase0 --extra runtime-cpu
uv run --locked --group dev --group phase0 --extra runtime-cpu \
  python scripts/phase5_alignment_smoke.py \
  --model tiny --samples-per-language 1 --device cpu \
  --cache-dir .cache/phase5 \
  --output phase5-alignment-smoke.json
~~~

O smoke usa FLEURS PT-BR/EN, executa Whisper e WhisperX reais e registra WER lexical, RTF, cobertura, palavras sem alinhamento, timestamps dentro dos limites e memória. FLEURS não possui fronteiras de palavras anotadas; portanto, o resultado é um smoke de integração/estrutura, não uma medição de erro temporal humano.

### Avaliação local com fronteiras humanas

Criar um JSONL, uma amostra por linha. Áudio deve ser WAV PCM s16le, mono, 16 kHz, normalizado pela Fase 3. Os tempos de referência são globais; as janelas são locais ao WAV.

~~~json
{"sample_id":"pt-01","audio":"./pt-01.wav","language":"pt","timeline_offset_seconds":4.5,"segments":[{"text":"Uma frase.","window_start_seconds":0.0,"window_end_seconds":2.5,"words":[{"word":"Uma","start":4.62,"end":4.91},{"word":"frase.","start":5.02,"end":5.56}]}]}
~~~

Comando:

~~~bash
uv run --locked --group dev --group phase0 --extra runtime-cpu \
  python scripts/phase5_alignment_evaluation.py \
  --manifest ./referencias-humanas.jsonl \
  --models-dir .cache/phase5 \
  --device auto \
  --output ./avaliacao-alinhamento.json
~~~

O relatório inclui mediana e P95 dos erros absolutos de início e fim, cobertura, não alinhadas, limites inválidos e diagnósticos. Não inclui caminhos, áudio, texto nem palavras de referência.

### Limites provisórios

O plano mestre usa como metas iniciais:
- erro mediano de início e fim ≤ 150 ms;
- P95 de início e fim ≤ 350 ms;
- zero timestamp inválido/fora da duração;
- toda palavra não alinhada permanece identificada e visível.

Esses números são metas de engenharia provisórias, não garantias universais. A aprovação exige amostras suficientes, idiomas/vozes/condições representativas, revisão humana e análise de falhas. O script calcula os resultados, mas não declara aceitação automática do produto.

## 5. Critérios de aceite da implementação

- [x] Adaptador WhisperX atrás da porta `Aligner`; Whisper/PyTorch continuam fora do domínio e da aplicação.
- [x] Modelos PT/EN, dispositivo configurável, cache local e carga tardia.
- [x] Janela aproximada separada do timestamp final.
- [x] Interpolação automática desligada; palavras sem tempo permanecem explícitas.
- [x] Offset do stream aplicado uma única vez, inclusive para offset de origem negativo.
- [x] Diagnósticos de cobertura, palavra ausente, texto divergente, limites, score e sobreposição.
- [x] Preflight GUI e bloqueio de geração quando WhisperX está ausente.
- [x] Geração final bloqueada enquanto o publicador SRT das Fases 6/7 não existe.
- [x] Smoke automatizado FLEURS e avaliador local com referência humana.
- [ ] CI push e PR aprovadas em todos os jobs.
- [ ] Smoke real Whisper + WhisperX executado e artefato conferido.
- [ ] Benchmark com corpus autorizado de pregações no computador-alvo.
- [ ] Precisão temporal homologada contra fronteiras humanas com mediana/P95.

## 6. Riscos e limites

- Modelo português pode consumir memória e tempo consideráveis em CPU; não declarar perfil de hardware recomendado antes de medir no computador-alvo.
- Primeira execução pode baixar pesos Hugging Face/torchaudio e NLTK; exige rede, espaço livre e cache gravável.
- Cancelamento não interrompe no meio da chamada de alto nível.
- Score do WhisperX é score do alinhador, não probabilidade calibrada de que a fronteira esteja correta.
- FLEURS é fala lida e não representa pregações, música, ruído, nomes próprios ou fala sobreposta.
- Forced alignment não corrige erros lexicais do Whisper; texto errado pode ainda ser alinhado acusticamente em posição plausível. O corpus humano deve revisar o texto de referência.
- Tradução, segmentação editorial e SRT permanecem fora desta fase.

## 7. Próximo checkpoint

Depois de CI, revisão e merge, a próxima fase do roadmap é a Fase 6 — tradução, segmentação e SRT (a composição final GUI/pipeline permanece na Fase 7). A homologação temporal do computador-alvo/corpus humano continua como gate de produto.
