# Fase 6 — Benchmark e aceleração da tradução

**Status:** implementação técnica em validação na PR [#14](https://github.com/anfalcir/legendar/pull/13); CI determinística aprovada no head anterior. Smoke real da API e benchmark com corpus humano permanecem pendentes.
**Objetivo:** reduzir o tempo de tradução hoje dominado pelo NLLB (aproximadamente 14 minutos na mídia de referência de 37min10s), sem degradar sentido, terminologia, consistência ou integridade das cues.

## 1. Decisão arquitetural

A porta `Translator` continua sendo a única interface do pipeline. Dois adaptadores permanecem disponíveis:

- `NllbTranslator`: baseline local, Transformers/PyTorch.
- `GeminiTranslator`: candidato via Gemini Developer API, com lotes contextuais.

O padrão permanece **NLLB** até que o benchmark pareado e a revisão humana aprovem o candidato. A seleção é explícita:

| Variável | Padrão | Função |
|---|---|---|
| `LEGENDAR_TRANSLATION_BACKEND` | `nllb` | `nllb` ou `gemini` |
| `GEMINI_API_KEY` | ausente | Credencial do Gemini Developer API |
| `LEGENDAR_GEMINI_MODEL` | `gemini-3.8-flash` | Modelo configurável |
| `LEGENDAR_GEMINI_BATCH_SIZE` | `32` | Cues atuais por requisição (1–100) |
| `LEGENDAR_GEMINI_TIMEOUT` | `120` | Timeout por requisição, em segundos |
| `LEGENDAR_GEMINI_MAX_RETRIES` | `3` | Tentativas adicionais para HTTP 429/5xx (0–8) |
| `LEGENDAR_GEMINI_GROUNDING` | `true` | Habilita pesquisa contextual; use `false` para desativar |

Não há fallback silencioso. Se Gemini falhar, o job falha com diagnóstico sanitizado; selecione `nllb` explicitamente para voltar ao motor local. Isso impede que uma mesma homologação misture resultados de motores diferentes sem evidência.

## 2. Tradução contextual exigida

O prompt do adaptador exige:

1. Português brasileiro natural, contemporâneo e idiomático quando esse for o destino.
2. Tradução de significado e intenção, não substituição literal palavra por palavra.
3. Preservação de sujeito, negação, tempo verbal, tom, relações entre ideias e registro oral.
4. Preservação de nomes próprios e entidades nomeadas: pessoas, personagens, cidades, lugares, povos, raças, clãs, famílias, facções, organizações, títulos, obras e universos ficcionais.
5. Preservação de termos específicos, números, datas, siglas, referências e nomes de usuário.
6. Não inventar traduções para nomes ambíguos; manter o original quando não houver evidência suficiente.
7. Não acrescentar explicações, notas, fatos externos, resumo, censura ou suavização.
8. Correspondência exata de cada `cue_id`, na mesma ordem e uma única vez.

Cada lote recebe as cues anteriores e posteriores como contexto, além das últimas 12 unidades já traduzidas (original + tradução) para reforçar consistência terminológica entre lotes. O contexto é auxiliar: somente as cues atuais podem ser devolvidas.

## 3. Lotes, estrutura e integridade

- Padrão de 32 cues por requisição; configurável de 1 a 100.
- JSON estruturado com `translations: [{cue_id, text}]`.
- Validação de quantidade, tipo, IDs, ordem, duplicações e texto vazio antes de aceitar o lote.
- Se a geração for bloqueada ou terminar em `MAX_TOKENS`, o lote é rejeitado.
- O progresso avança somente depois que um lote inteiro foi validado.
- Cancelamento é verificado entre lotes.
- Nenhum timestamp é enviado ao tradutor ou alterado por ele: a aplicação reaplica os textos nas cues originais e conserva seus intervalos.
- A resposta não é reordenada silenciosamente. Qualquer divergência 1:1 bloqueia o job.

## 4. Resiliência, privacidade e métricas

O adaptador usa HTTPS e envia a chave no header `x-goog-api-key`, nunca na URL. Para a família Gemini 3, usa `thinkingLevel=LOW` para reduzir latência e não envia `temperature`, parâmetro não recomendado/compatível com o perfil atual desses modelos. Não registra chave, prompt, texto-fonte, tradução, referências humanas ou corpo bruto de erro. Erros HTTP são convertidos em mensagens sanitizadas.

- Timeout configurável (padrão 120 s).
- Retry com espera exponencial para HTTP 429 e 5xx, respeitando `Retry-After` quando numérico.
- HTTP 4xx não transitório falha imediatamente.
- Métricas sanitizadas: número de requisições, retries, lotes, cues, duração de chamadas, tokens de entrada/saída e consultas de grounding.
- O snapshot de performance não contém texto ou segredo.

Grounding com Google Search é **habilitado por padrão** no fluxo Gemini para atender ao requisito de investigar entidades e terminologia contextual. A documentação oficial atual lista suporte no `gemini-3.8-flash` e no `gemini-3.5-flash-lite`; o adaptador permite explicitamente esses modelos e rejeita combinações não suportadas. Configure `LEGENDAR_GEMINI_GROUNDING=false` para desativar. O modelo deve pesquisar apenas quando houver nomes, termos ou referências ambíguas, confrontar fontes com as cues e jamais acrescentar fatos à fala. O benchmark registra consultas e latência para quantificar o impacto. Use apenas quando uma referência cultural, nome ou termo do universo exigir pesquisa. Grounding ajuda a identificar referências, mas não autoriza acrescentar fatos à fala. Ele pode aumentar latência e consumo; compare separadamente a configuração ligada/desligada.

## 5. Instalação e configuração

Não foi adicionada dependência Python para o Gemini: o adaptador usa a biblioteca padrão `urllib`. Isso mantém o lockfile reproduzível e evita uma nova dependência no runtime desktop.

Exemplo para execução local (não salve a chave em arquivo versionado):

```bash
export GEMINI_API_KEY="..."
export LEGENDAR_TRANSLATION_BACKEND=gemini
export LEGENDAR_GEMINI_MODEL=gemini-3.8-flash
export LEGENDAR_GEMINI_BATCH_SIZE=32
```

Para voltar ao NLLB:

```bash
export LEGENDAR_TRANSLATION_BACKEND=nllb
```

A chave para o workflow GitHub Actions deve ser cadastrada em **Settings → Secrets and variables → Actions → New repository secret**, com o nome exato `GEMINI_API_KEY`. Nunca a coloque no código, em commit, artefato ou log.

## 6. Benchmark pareado

O script `scripts/phase6_translation_benchmark.py` compara NLLB e Gemini sobre as mesmas cues, na mesma ordem. O manifesto TSV usa:

```tsv
cue_id	source_text	reference_text
1	The old city was quiet.	A cidade antiga estava silenciosa.
2	Then the bells began to ring.	Então os sinos começaram a tocar.
```

- `reference_text` deve conter a tradução humana revisada para todas as linhas ou ficar vazio em todas.
- Manifesto sem referências mede desempenho e integridade estrutural, mas não comprova qualidade lexical.
- O relatório contém tempo, mediana, cues/s, WER/CER quando há referência, configuração e métricas sanitizadas. Não contém texto das cues, traduções, referências ou chave.
- O corpus real e os manifestos devem permanecer locais; não fazer commit de conteúdo privado.

Execução recomendada com três repetições no mesmo computador:

```bash
PYTHONPATH=src uv run --locked --group dev --group phase0 \\
  python scripts/phase6_translation_benchmark.py \\
  --manifest ./corpus/traducao-37min.tsv \\
  --source-language en \\
  --target-language pt \\
  --backends nllb,gemini \\
  --repeats 3 \\
  --output ./phase6-translation-benchmark.json
```

A execução deve usar a mesma mídia/cues, hardware, idioma, referências e versão do corpus. Registrar separadamente primeira execução (carga/cache) e execuções quentes. Não comparar runners GitHub com o computador de referência.

## 7. Protocolo de qualidade e aceite

O relatório numérico é necessário, mas não substitui revisão humana bilíngue cega. Congelar antes da comparação um conjunto que inclua:

- nomes próprios, cidades, raças, clãs, povos, facções e termos recorrentes;
- expressões idiomáticas, ambiguidades e referências culturais;
- negações, sujeitos, tempos verbais e relações entre cues;
- números, datas, siglas e referências;
- fala informal, frases interrompidas e cues curtas.

A decisão deve registrar:

1. tempo total de tradução e tempo por lote;
2. mediana e dispersão de três execuções quentes, quando viável;
3. tokens de entrada/saída, retries e latência;
4. WER/CER contra referências humanas quando disponíveis;
5. revisão humana de sentido, naturalidade, terminologia e nomes;
6. zero perda, duplicação, vazio, reordenação ou alteração de timestamps;
7. comportamento de cancelamento, erro e retorno explícito ao NLLB.

**Aceite:** Gemini deve demonstrar ganho material e tradução não inferior na revisão humana, sem qualquer quebra estrutural. Uma meta de throughput de pelo menos 1,5× é alvo de experimento, não garantia. Se não passar, não será adotado como padrão; os resultados orientarão otimizações do NLLB (CTranslate2, quantização, batch/length bucketing e beam search).

## 8. CI e homologação real

- Testes determinísticos cobrem prompt, contexto, estrutura JSON, IDs, ordem, vazios, bloqueio/truncamento, retries, erros HTTP, cancelamento, métricas e seleção de backend.
- O workflow `Phase 6 quality` executa a matriz Python 3.10–3.13, testes, cobertura, Ruff e validação de formatação.
- O smoke real da API é opcional no CI e só executa quando o secret `GEMINI_API_KEY` estiver configurado.
- A CI sem chave não comprova acesso real, latência, quotas, grounding nem qualidade de tradução.
- A homologação final usa o corpus e a mídia de referência de 37min10s no hardware-alvo; a decisão de adoção permanece pendente até esses resultados.

## 9. Referências

- [Gemini Developer API — Generate content](https://ai.google.dev/gemini-api/docs/generate-content)
- [Gemini Developer API — Structured output](https://ai.google.dev/gemini-api/docs/structured-output)
- [Gemini Developer API — Grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search)
- [Gemini Developer API — Models](https://ai.google.dev/gemini-api/docs/models)
- [NLLB-200 distilled 600M — model card e licença](https://huggingface.co/facebook/nllb-200-distilled-600M)


## 10. Ajustes de compatibilidade API

- `gemini-3.8-flash` é um ID estável e GA segundo a documentação oficial consultada em 11/11/2026.
- A geração usa `thinkingConfig.thinkingLevel=LOW` para reduzir latência; `temperature` foi removido do payload.
- Grounding é permitido no `gemini-3.8-flash` e permanece desativado por padrão.
- O smoke de CI não substitui uma chamada real com a chave do usuário.
