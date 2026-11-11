# Estado atual do Legendar

- **Última atualização:** 11/11/2026
- **Repositório:** anfalcir/legendar
- **Branch padrão / base de integração:** `main`
- **Fases concluídas e integradas:** 0, 1, 2, 3, 4, 5, 6, 7, 8 e 9
- **Fase em execução:** nenhuma — roadmap do plano mestre encerrado
- **Próxima etapa:** homologação do usuário com mídia real, modelos completos e computador-alvo
- **Suíte determinística:** 451 testes aprovados e 86% de cobertura com FFmpeg/ffprobe no `PATH`; 441 aprovados e 10 skips explícitos sem as ferramentas
- **Documentação:** guias de arquitetura, operação, instalação e decisões publicados; links relativos verificados automaticamente
- **Manifestos:** `pyproject.toml` e `uv.lock`; o `requirements.txt` legado foi removido

> Este documento registra a realidade do repositório, não a intenção. Toda
> afirmação abaixo tem como evidência um teste, um comando executado ou um
> documento de fase. O que depende do usuário está explicitamente separado.

---

## 1. Resumo executivo

O Legendar é uma aplicação desktop PySide6 que produz legendas SRT fiéis ao
áudio: recebe arquivo local ou YouTube, normaliza a mídia com FFmpeg, transcreve
com Whisper, alinha por palavra com WhisperX, segmenta em cues de duas linhas,
traduz localmente por cue com NLLB-200 quando solicitado, valida o trilho e
publica o arquivo por troca atômica.

Todas as fases do [plano mestre](PLANO_REMODELAGEM.md) estão implementadas e
integradas à `main`. A Fase 6 entregou segmentação, tradução e publicação; a
Fase 7 conectou a janela ao pipeline real; a Fase 8 provou o fluxo com matriz
end-to-end e mídia real; a Fase 9 consolidou a documentação e encerrou o legado.

O que resta não é implementação: é a homologação com pregações reais, pesos
completos, hardware do usuário e julgamento editorial, listada na seção 6.

## 2. Situação do repositório

| Item | Estado |
|---|---|
| `main` | Contém as Fases 0–9 integradas |
| Fases 0–5 | Integradas por PRs squash (#1 a #6) |
| Fase 6 | Branch `phase-6/translation-segmentation-srt`; squash `d600283`; CI de push 5/5 jobs ([#42951451587](https://github.com/anfalcir/legendar/actions/runs/42951451587)) |
| Fase 7 | Branch `phase-7/gui-pipeline-integration`; squash `9ccab33` |
| Fase 8 | Branch `phase-8/validation`; squash `e9e2a18` |
| Fase 9 | Branch `phase-9/documentation`; squash local |
| Motivo do squash local (6–9) | criação de PR indisponível no ambiente de execução (sem `gh` e sem token) |
| Manifestos | `pyproject.toml` (canônico) + `uv.lock` (198 pacotes resolvidos) |
| Lockfile | validado com `uv lock --check` |
| Legado | `main.py`, `core/` e `gui/` preservados e caracterizados em [LEGACY_BASELINE.md](LEGACY_BASELINE.md) |

## 3. Arquitetura em operação

| Camada | Conteúdo atual |
|---|---|
| `domain` | entidades de mídia/transcrição/legenda, value objects, máquina de estados, eventos e catálogo de erros |
| `application` | `JobContext`, `JobController`, `SerialPipeline`, segmentação, tradução por cue, validação, portas e progresso |
| `infrastructure` | ffprobe/FFmpeg, yt-dlp, Whisper, WhisperX, NLLB, SRT atômico, workspace, settings e logging |
| `presentation` | janela PySide6, view model puro, workers, diálogos, preferências e tema |
| `bootstrap` | composição das portas reais, preflight de ambiente e entrada da GUI |

Detalhes em [ARQUITETURA.md](ARQUITETURA.md).

## 4. Evidências de validação

| Evidência | Resultado |
|---|---|
| Suíte completa com FFmpeg 7.0.2 static e Qt offscreen | **451 testes aprovados, 0 skips, cobertura 86%** |
| Suíte completa sem FFmpeg/ffprobe | **441 aprovados, 10 skips explícitos** |
| Ruff check (`src/legendar`, `tests`, `scripts`) | limpo |
| Ruff format check (arquivos mantidos) | limpo |
| `uv lock --check` | 198 pacotes, sem divergência |
| Verificador de links da documentação | sem links relativos quebrados |
| CI Fase 6 (`phase6-quality.yml`) | 5/5 jobs em Python 3.10–3.13 + smoke NLLB real em CPU |
| CI Fase 8 (`phase8-quality.yml`) | matriz Python 3.10–3.13 com FFmpeg, cobertura ≥ 85%, `-m e2e` isolada e consistência de documentação |
| Gates herdados | `phase0`, `phase1`, `phase3`, `phase4`, `phase5` permanecem ativos |

## 5. Decisões que sustentam o estado atual

As 24 decisões consolidadas e as 5 abertas estão em [DECISOES.md](DECISOES.md).
As mais relevantes para operar o produto hoje:

1. Tradução local NLLB-200 distilled 600M, por cue, sem enviar texto a terceiros.
2. Duas linhas de 42 caracteres por cue, 1–7 s, pausa de 0,6 s, ~17 cps.
3. WhisperX 3.8.6 como alinhador primário; stable-ts fora do manifesto.
4. Publicação atômica com roundtrip e `PUBLISHING` como ponto de não retorno.
5. `pyproject.toml` + `uv.lock` como únicos manifestos; pip via `uv export`.

## 6. Pendências de homologação (usuário)

| # | Item | Como validar |
|---|---|---|
| 1 | Precisão temporal em fala real | marcar fronteiras humanas em 2–3 pregações e comparar com o SRT |
| 2 | Qualidade tradutória PT↔EN | revisar nomes, números, siglas e linguagem religiosa |
| 3 | Desempenho no computador-alvo | medir tempo, memória e temperatura na primeira execução completa |
| 4 | Fluxo YouTube | processar uma URL autorizada e cancelar durante o download |
| 5 | Interface física | validar HiDPI, tema e sistema operacional padrão |
| 6 | Arquivo longo | processar mais de uma hora e verificar estabilidade |
| 7 | Inspeção independente | abrir o SRT final em um player de referência |

Roteiro detalhado: [HANDOFF_FASE_9.md](HANDOFF_FASE_9.md) seção 4.

## 7. Riscos e limitações conhecidas

| Risco | Situação |
|---|---|
| Modelos reais fora da suíte determinística | cobertos por smoke tests de fase e preflight de ambiente |
| Qualidade tradutória não medida | decisão editorial pendente do usuário |
| Cancelamento não interrompe inferência em andamento | documentado; observado entre lotes/etapas |
| Publicação não cancelável | decisão explícita para preservar integridade do arquivo |
| YouTube muda com frequência | yt-dlp + runtime JS verificado no preflight |
| Empacotamento distribuível | não homologado; execução suportada é via `uv` |
| Plataformas suportadas | CI cobre Ubuntu/Python 3.10–3.13; demais dependem de homologação |

## 8. Como reproduzir a validação

```bash
uv lock --check
uv sync --locked --group dev --group phase0

QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q -m e2e

uv run --locked --no-sync ruff check src/legendar tests scripts
uv run --locked --no-sync ruff format --check src/legendar tests
uv run --locked --no-sync python scripts/check_doc_links.py
```

Em ambiente sem FFmpeg no `PATH`, os testes de mídia real são pulados; para
executá-los localmente, aponte o `PATH` para um build estático (a CI instala o
pacote do sistema).

## 9. Documentos de referência

| Documento | Papel |
|---|---|
| [PLANO_REMODELAGEM.md](PLANO_REMODELAGEM.md) | destino do produto e critérios de aceite |
| [ARQUITETURA.md](ARQUITETURA.md) | camadas, fluxo, portas, estados e testes |
| [OPERACAO.md](OPERACAO.md) | uso da janela, arquivos, erros e diagnóstico |
| [INSTALACAO.md](INSTALACAO.md) | requisitos, perfis, execução e verificação |
| [DECISOES.md](DECISOES.md) | decisões consolidadas e abertas |
| [MATRIZ_DEPENDENCIAS.md](MATRIZ_DEPENDENCIAS.md) | governança, perfis e compatibilidade |
| [RELATORIO_FASE_8.md](RELATORIO_FASE_8.md) | evidências de teste e pendências humanas |
| [LEGACY_BASELINE.md](LEGACY_BASELINE.md) | baseline antiga e política de aposentadoria |
| Planos e handoffs das Fases 0–9 | histórico técnico de cada fronteira |

## 10. Política de manutenção deste documento

Atualizar `ESTADO_ATUAL.md` quando:

- uma fase começar ou terminar;
- uma decisão técnica mudar;
- um teste relevante passar ou falhar;
- surgir bloqueio, risco material ou pendência humana;
- uma funcionalidade for implementada, alterada ou removida.

Nenhuma tarefa é marcada como concluída sem evidência executável. Se o plano
mestre e este documento divergirem, este documento descreve o repositório e a
divergência deve ser registrada antes de qualquer nova implementação.


Relatório completo, matriz de cenários e riscos residuais:
[RELATORIO_FASE_8.md](RELATORIO_FASE_8.md).
