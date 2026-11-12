# Fase 6 — Registro de homologação real

Este documento registra evidências da homologação operacional do backend Gemini. Não registrar chaves, prompts completos, textos de mídia privada ou traduções integrais neste arquivo.

## Estado inicial

- Implementação: integrada à `main` pela PR #19.
- CI determinística e runtime NLLB/CPU: aprovados no workflow 43134372712.
- Backend padrão: NLLB.
- Gemini: opt-in, ainda não promovido.
- Secret `GEMINI_API_KEY`: usuário informou que foi configurado no GitHub Actions em 12/11/2026; a presença efetiva será comprovada pelo job de smoke real.

## Gates de aceite

| Gate | Evidência | Estado |
|---|---|---|
| Smoke real Gemini Developer API | Workflow Phase 6, job Optional live Gemini Developer API smoke | Aguardando execução |
| Benchmark pareado no hardware de referência | Manifesto local da mídia de 37min10s, três repetições quentes | Pendente |
| Qualidade contra referência humana | WER/CER + revisão humana cega | Pendente |
| Integridade estrutural | IDs 1:1, ordem, cues não vazias e timestamps preservados | Pendente |
| Decisão operacional | Registro de ganho e ausência de regressões | Pendente |

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
  --repeats 3 \
  --output ./phase6-translation-benchmark.json
```

A execução mede apenas o estágio de tradução. Comparar a mediana das execuções quentes, throughput, retries, tokens, WER/CER quando houver referência humana e revisão humana cega. Não comparar tempos do runner GitHub com o hardware de referência. Não promover Gemini sem ganho material e qualidade não inferior.

## Resultado do smoke real

Será preenchido após a execução do workflow que utiliza o secret do repositório.