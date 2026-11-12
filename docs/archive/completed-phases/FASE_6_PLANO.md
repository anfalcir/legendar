# Fase 6 — Benchmark e aceleração da tradução

**Status:** **concluída e integrada à `main`**. Além da implementação dos dois adaptadores, a Fase 6 agora oferece seleção explícita do motor nas Preferências, configuração local da chave Gemini e reconfiguração sem reiniciar a aplicação. O smoke real Gemini (2 cues, `gemini-3.8-flash`, sem grounding) e a CI determinística foram aprovados. O benchmark comparativo NLLB × Gemini não será executado nesta fase por decisão de produto; ambos os motores permanecem disponíveis e opcionais, com NLLB como padrão.

**Objetivo:** reduzir o tempo de tradução hoje dominado pelo NLLB (aproximadamente 14 minutos na mídia de referência de 37min10s), sem degradar sentido, terminologia, consistência ou integridade das cues.

## 1. Decisão arquitetural

A porta `Translator` continua sendo a única interface do pipeline. Dois adaptadores permanecem disponíveis:

- `NllbTranslator`: baseline local, Transformers/PyTorch.
- `GeminiTranslator`: candidato via Gemini Developer API, com lotes contextuais.

O padrão continua sendo **NLLB**, mas o usuário pode selecionar explicitamente qualquer um dos dois motores. A seleção do motor é feita pelo usuário em **Preferências → Motor de tradução**:

| Opção | Comportamento |
|---|---|
| **NLLB-200 (local)** | Tradução local, sem envio do texto para serviço externo; é o padrão. |
| **Gemini (API)** | Tradução contextual via Gemini Developer API; exige chave configurada localmente. |

As variáveis de ambiente continuam aceitas para automação/CI e compatibilidade:

| Variável | Padrão | Função |
|---|---|---|
| `LEGENDAR_TRANSLATION_BACKEND` | `nllb` | Backend inicial quando não há preferência salva |
| `GEMINI_API_KEY` | ausente | Fallback de credencial para CI/ambientes automatizados |
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
4. Preservação estrita de nomes próprios e entidades nomeadas: pessoas, personagens, cidades, lugares, povos, raças, clãs, famílias, facções, organizações, títulos, obras e universos ficcionais. Nunca traduzir, transliterar ou adaptar esses nomes; preservar a grafia canônica original. Se houver provável erro de reconhecimento, usar contexto e pesquisa para inferir a grafia original somente com evidência forte; na dúvida, manter a forma da transcrição.
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

Grounding com Google Search é **habilitado por padrão** no fluxo Gemini para atender ao requisito de investigar entidades e terminologia contextual. A documentação oficial atual lista suporte nos modelos Gemini 3 Flash estáveis; o adaptador permite explicitamente `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash` e `gemini-3.5-flash-lite`, rejeitando combinações não habilitadas. Configure `LEGENDAR_GEMINI_GROUNDING=false` para desativar. O modelo deve pesquisar apenas quando houver nomes, termos ou referências ambíguas, confrontar fontes com as cues e jamais acrescentar fatos à fala. O benchmark registra consultas e latência para quantificar o impacto. Use apenas quando uma referência cultural, nome ou termo do universo exigir pesquisa. Grounding ajuda a identificar referências, mas não autoriza acrescentar fatos à fala. Ele pode aumentar latência e consumo; compare separadamente a configuração ligada/desligada.

## 5. Configuração local

A configuração normal é feita dentro do aplicativo:

1. Abra **Preferências**.
2. Em **Motor de tradução**, escolha **NLLB-200 (local)** ou **Gemini (API)**.
3. Se escolher Gemini, informe a chave no campo **Chave Gemini**.
4. A chave é armazenada localmente no perfil do usuário, fora do QSettings, com arquivo privado `0600` quando suportado pelo sistema.
5. A aplicação nunca registra a chave em logs, relatórios de desempenho, prompts persistidos ou commits.
6. A troca de motor é aplicada imediatamente aos próximos jobs; não é necessário reiniciar o aplicativo.

As variáveis de ambiente continuam disponíveis para CI e automação. O campo de Preferências é a configuração recomendada para uso normal do desktop.

Para voltar ao NLLB:

```bash
export LEGENDAR_TRANSLATION_BACKEND=nllb
```

A chave para o workflow GitHub Actions deve ser cadastrada em **Settings → Secrets and variables → Actions → New repository secret**, com o nome exato `GEMINI_API_KEY`. Nunca a coloque no código, em commit, artefato ou log.

## 6. Benchmark pareado (mantido como ferramenta, não como gate da Fase 6)

O script `scripts/phase6_translation_benchmark.py` compara NLLB e Gemini sobre as mesmas cues, na mesma ordem. O manifesto TSV usa:

```tsv
cue_id	source_text	reference_text
1	The old city was quiet.	A cidade antiga estava silenciosa.
2	Then the bells began to ring.	Então os sinos começaram a tocar.
```

- `reference_text` deve conter a tradução humana revisada para todas as linhas ou ficar vazio em todas.
- Manifesto sem referências mede desempenho e integridade estrutural, mas não comprova qualidade lexical.
- O relatório contém tempo, mediana, cues/s, WER/CER quando há referência, configuração e métricas sanitizadas. Quando ambos os backends são executados, calcula também speedup do Gemini sobre NLLB, redução percentual de tempo e deltas WER/CER. Não contém texto das cues, traduções, referências ou chave.
- O corpus real e os manifestos devem permanecer locais; não fazer commit de conteúdo privado.

Execução recomendada com três repetições no mesmo computador:

```bash
PYTHONPATH=src uv run --locked --group dev --group phase0 \\
  python scripts/phase6_translation_benchmark.py \\
  --manifest ./corpus/traducao-37min.tsv \\
  --source-language en \\
  --target-language pt \\
  --backends nllb,gemini \\
  --repeats 4 \\
  --output ./phase6-translation-benchmark.json
```

A execução deve usar a mesma mídia/cues, hardware, idioma, referências e versão do corpus. Registrar separadamente primeira execução (carga/cache) e execuções quentes. Não comparar runners GitHub com o computador de referência.

## 7. Critérios de conclusão da Fase 6

A Fase 6 é considerada concluída com base nos requisitos de implementação definidos para esta etapa:

- ambos os adaptadores implementados atrás da mesma porta `Translator`;
- NLLB mantido como padrão e Gemini mantido como opção explícita;
- seleção persistente do backend em **Preferências**;
- chave Gemini configurável localmente pela própria aplicação;
- chave fora do QSettings, logs, relatórios de desempenho e código versionado;
- troca de backend aplicada aos próximos jobs sem reiniciar a aplicação;
- validação estrutural 1:1, cancelamento, retries e métricas sanitizadas preservados;
- CI determinística e smoke real Gemini aprovados.

O benchmark comparativo NLLB × Gemini e a revisão humana permanecem disponíveis como ferramentas de homologação futura, mas **não são mais gates de conclusão da Fase 6**, conforme decisão do usuário. A Fase 7 pode avançar sem retirar nenhum dos dois motores.

## 8. CI e homologação real

- Testes determinísticos cobrem prompt, contexto, estrutura JSON, IDs, ordem, vazios, bloqueio/truncamento, retries, erros HTTP, cancelamento, métricas e seleção de backend.
- O workflow `Phase 6 quality` executa a matriz Python 3.10–3.13, testes, cobertura, Ruff e validação de formatação.
- O smoke real da API é opcional no CI e só executa quando o secret `GEMINI_API_KEY` estiver configurado. O smoke básico desativa Google Search grounding para isolar autenticação e geração do modelo.
- Em 12/11/2026, o smoke real foi aprovado após atualização da chave: 2 cues traduzidas, 1 requisição, 0 retries, 1,5656 s, 556 tokens de entrada e 36 de saída. Grounding estava desativado.
- A CI sem chave não comprova acesso real, latência, quotas, grounding nem qualidade de tradução.
- A homologação final ainda exige benchmark pareado com NLLB no corpus/mídia de referência de 37min10s no hardware-alvo, validação separada do grounding e revisão humana cega. Até a aprovação desses gates, Gemini não será promovido a padrão.

O registro de execução e evidências da homologação real está em [FASE_6_HOMOLOGACAO.md](FASE_6_HOMOLOGACAO.md). Ele deve ser atualizado somente com resultados observados; a configuração do secret, isoladamente, não equivale a smoke aprovado.

## 9. Referências

- [Gemini Developer API — Generate content](https://ai.google.dev/gemini-api/docs/generate-content)
- [Gemini Developer API — Structured output](https://ai.google.dev/gemini-api/docs/structured-output)
- [Gemini Developer API — Grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search)
- [Gemini Developer API — Models](https://ai.google.dev/gemini-api/docs/models)
- [NLLB-200 distilled 600M — model card e licença](https://huggingface.co/facebook/nllb-200-distilled-600M)


## 10. Ajustes de compatibilidade API

- `gemini-3.8-flash` é um ID estável e GA segundo a documentação oficial consultada em 11/11/2026.
- A geração usa `thinkingConfig.thinkingLevel=LOW` para reduzir latência; `temperature` foi removido do payload.
- Grounding é permitido no `gemini-3.8-flash` e permanece habilitado por padrão no adaptador; `LEGENDAR_GEMINI_GROUNDING=false` permite desativá-lo.
- O smoke de CI não substitui uma chamada real com a chave do usuário.
