# Fase 6 — Registro de homologação real

Este documento registra evidências da homologação operacional do backend Gemini. Não registrar chaves, prompts completos, textos de mídia privada ou traduções integrais neste arquivo.

## Estado inicial

- Implementação: integrada à `main` pela PR #19.
- CI determinística e runtime NLLB/CPU: aprovados no workflow 43134372712.
- Backend padrão: NLLB.
- Gemini: opt-in, ainda não promovido.
- Secret `GEMINI_API_KEY`: reconhecido pelo GitHub Actions e chamada real aprovada em 12/11/2026 após o usuário atualizar a chave.

## Gates de aceite

| Gate | Evidência | Estado |
|---|---|---|
| Smoke real Gemini Developer API | Run `43135725775`, job `130914361060`; 2 cues aceitas em `gemini-3.8-flash` | **Aprovado (sem grounding)** |
| Benchmark pareado no hardware de referência | Manifesto local da mídia de 37min10s, três repetições quentes | Pendente |
| Qualidade contra referência humana | WER/CER + revisão humana cega | Pendente |
| Integridade estrutural | IDs 1:1, ordem, cues não vazias e timestamps preservados | Pendente |
| Decisão operacional | Registro de ganho e ausência de regressões | Pendente |

## Corpus real recebido — Wingfeather Saga S4E2

Arquivo-fonte em inglês recebido em `logs/EN-Watch The Wingfeather Saga S4E2 Home at Chimney Hill on Angel.srt`.

- 967 cues, IDs sequenciais de 1 a 967, sem duplicidades.
- Primeiro cue: `00:00:14,677`; último cue termina em `00:37:02,879`.
- O SRT português histórico tem 944 cues e timestamps diferentes. Ele **não** é referência humana nem deve ser pareado cue a cue com este arquivo.
- O benchmark de desempenho deve executar NLLB e Gemini sobre as mesmas 967 unidades inglesas. A integridade do resultado deve validar 967 saídas para 967 entradas, preservando os IDs/ordem do contrato de tradução.
- Não versionar o manifesto gerado, pois ele contém o texto-fonte da mídia.

### Gerar o manifesto local

A partir da raiz do repositório:

```bash
PYTHONPATH=src uv run --locked --group dev --group phase0 \
  python scripts/phase6_build_manifest.py \
  --source "logs/EN-Watch The Wingfeather Saga S4E2 Home at Chimney Hill on Angel.srt" \
  --output ./corpus/traducao-37min.tsv
```

O gerador valida estrutura, timestamps, duração positiva, texto não vazio, IDs sequenciais e duplicidades. Escreve `reference_text` vazio em todas as linhas e imprime o SHA-256 do SRT de origem para rastreabilidade local. Não cria nem presume referência humana.

### Validação automatizada do corpus

- Workflow [Phase 6 quality #307](https://github.com/anfalcir/legendar/actions/runs/43144606532), executado sobre o commit da preparação do corpus.
- A etapa de geração e validação processou o SRT inglês real e confirmou 967 linhas, IDs de 1 a 967 em ordem e `reference_text` vazio em todas.
- Suítes determinísticas aprovadas em Python 3.10, 3.11, 3.12 e 3.13; lint e formatação aprovados.
- Smoke real da Gemini Developer API aprovado; testes do adaptador NLLB com runtime Transformers CPU aprovados.
- PR [#22](https://github.com/anfalcir/legendar/pull/22) integrada à `main` por squash em `ab343da21710301906cde987e052cdaa9d5aa0fd`.
- PR [#23](https://github.com/anfalcir/legendar/pull/23) protegeu `/corpus/` e o relatório local no `.gitignore`; merge `185f0843b0954319f8fd32be99a50811c8f5e5d6`.

**Limite da evidência:** a CI validou a geração do manifesto, mas não executou o benchmark pareado completo. O tempo comparável ainda precisa ser medido no hardware de referência do usuário.

## Protocolo do benchmark local

O manifesto TSV deve conter `cue_id`, `source_text` e, quando disponíveis, `reference_text`. As referências humanas devem estar completas em todas as linhas ou ausentes em todas. Manter o corpus privado/local.

Executar no mesmo computador, com o mesmo manifesto, idiomas e configuração:

```bash
PYTHONPATH=src uv run --locked --group dev --group phase0 \
  python scripts/phase6_translation_benchmark.py \
  --manifest ./corpus/traducao-37min.tsv \
  --source-language en \
  --target-language pt \
  --backends nllb,gemini \
  --repeats 4 \
  --output ./phase6-translation-benchmark.json
```

A execução mede apenas o estágio de tradução. Comparar a mediana das execuções quentes, throughput, retries, tokens, WER/CER quando houver referência humana e revisão humana cega. Não comparar tempos do runner GitHub com o hardware de referência. Não promover Gemini sem ganho material e qualidade não inferior.

## Resultado do smoke real

Histórico observado em 12/11/2026:

- Run [43135567777](https://github.com/anfalcir/legendar/actions/runs/43135567777): secret reconhecido; API retornou HTTP 429. Smoke reprovado.
- Run [43135725775](https://github.com/anfalcir/legendar/actions/runs/43135725775), primeira tentativa sem grounding: API retornou HTTP 503. Smoke reprovado.
- Após o usuário atualizar a chave da API, o job `130914361060` do mesmo workflow foi reexecutado e **aprovado**. O smoke confirmou tradução real de 2 cues com `gemini-3.8-flash`, em uma requisição, sem retries, em 1,5656 s; 556 tokens de entrada, 36 de saída e zero consultas de grounding.
- Os jobs determinísticos Python 3.10, 3.11, 3.12 e 3.13, além do job NLLB/Transformers CPU, também foram aprovados nessa execução.
- A variável `LEGENDAR_GEMINI_GROUNDING=false` estava ativa no smoke. Portanto, a autenticação e geração básica estão homologadas; grounding ainda precisa ser validado separadamente.
- A PR [#20](https://github.com/anfalcir/legendar/pull/20), que adicionou este registro e isolou o smoke básico sem grounding, foi integrada à `main` por squash em `80d7ef9ef37e68c587534194db93a34970389f3a`.

**Conclusão parcial:** o secret atualizado funciona e o adaptador consegue traduzir via Gemini Developer API. Isso não comprova ainda qualidade final, grounding, ganho de desempenho no corpus real ou superioridade sobre NLLB. O benchmark pareado e a revisão humana permanecem gates obrigatórios.