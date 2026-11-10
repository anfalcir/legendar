# Estado atual do Legendar

- **Última atualização:** 10/11/2026
- **Repositório:** anfalcir/legendar
- **Branch atual deste trabalho:** `phase-3/media-ingestion`
- **Branch padrão / base de integração:** `main`
- **Branch de implementação da Fase 1:** `phase-1/architecture` (integrada)
- **Branch de implementação da Fase 2:** `phase-2/professional-ui` (integrada)
- **Branch de implementação da Fase 3:** `phase-3/media-ingestion` (em execução; ainda não integrada)
- **Branch padrão:** `main`
- **Fases concluídas:** Fase 0 — Definições e prova técnica; Fase 1 — Reestruturação arquitetural; Fase 2 — Interface profissional
- **Fase em execução:** Fase 3 — Entrada e preparação de mídia (implementação na branch, CI/revisão/PR ainda pendentes)
- **Fase concluída mais recente:** Fase 2 — Interface profissional, implementada, validada e integrada à `main`
- **PR da Fase 0:** [#1](https://github.com/anfalcir/legendar/pull/1), integrada por squash
- **PR da Fase 1:** [#2](https://github.com/anfalcir/legendar/pull/2), merged por squash em 10/11/2026
- **PR da Fase 2:** [#3](https://github.com/anfalcir/legendar/pull/3), merged por squash em 10/11/2026
- **Commit de integração da Fase 0:** `992cb874274e73d0264994e39926113f1461236f`
- **Commit de integração da Fase 1:** `de31dddffc4f8e761692129d4c47a02ca89b8b83`
- **Commit de integração da Fase 2:** `4129f0a906a04693502f298b71767605499e3f68`
- **Documentos de handoff:** [HANDOFF_FASE_1.md](HANDOFF_FASE_1.md), [HANDOFF_FASE_2.md](HANDOFF_FASE_2.md) e [HANDOFF_FASE_3.md](HANDOFF_FASE_3.md)

> A `main` continua com as Fases 0, 1 e 2 concluídas e integradas. A Fase 3 está em desenvolvimento na branch `phase-3/media-ingestion`, baseada na `main` pós-Fase 2. Os adaptadores de entrada/normalização e a GUI de inspeção foram implementados; a matriz final Python 3.10–3.13 ainda não foi aprovada e não há PR/merge. Portanto, a Fase 3 não está concluída.

---

## 1. Resumo executivo

A aplicação nova já tem camadas `domain`, `application`, `infrastructure`, `presentation` e `bootstrap`; inclui entidades e invariantes, máquina de estados, pipeline serial com portas/fakes, cancelamento/progresso, workspaces isolados, publicação SRT atômica e configuração. A Fase 2 acrescentou interface Qt profissional com temas claro/escuro/sistema, diálogos de confirmação, preferências persistidas, progresso honesto, log expansível, acessibilidade e proteção contra ações acidentais. Na branch `phase-3/media-ingestion`, estão implementados adaptadores concretos ffprobe/FFmpeg/yt-dlp, seleção de faixa, offsets com proveniência e inspeção assíncrona Qt; ainda aguardam validação final/merge. Whisper/WhisperX, alinhamento, tradução e SRT final continuam reservados às fases posteriores. O legado `main.py`/`core/`/`gui/` continua preservado.

A Fase 0 estabeleceu e documentou a direção técnica: governança de dependências, perfis de runtime, coletor de ambiente, prova sintética de mídia/offset, script de POC PT-BR/EN e contrato arquitetural. O plano operacional e o handoff da Fase 1 foram atualizados para registrar o checkpoint, as evidências e as pendências.

**Estado:** Fase 0 concluída e integrada. O workflow push #113 terminou com 16/16 jobs aprovados e a PR workflow #114 concluiu com sucesso; os jobs exclusivos de push (benchmark completo e instalação CUDA) foram pulados no evento PR por configuração. A PR #1 foi integrada por squash no commit `992cb874274e73d0264994e39926113f1461236f`. Na Fase 1, os workflows [#116](https://github.com/anfalcir/legendar/actions/runs/42905199857) e [#127](https://github.com/anfalcir/legendar/actions/runs/42905799938) aprovaram Python 3.10–3.13 (196 testes, cobertura 88%, Ruff/format verdes); a Fase 1 foi integrada à `main` pela PR #2, commit `de31ddd`. Na Fase 2, o workflow push [#42911438434](https://github.com/anfalcir/legendar/actions/runs/42911438434) e o workflow da PR [#42912335753](https://github.com/anfalcir/legendar/actions/runs/42912335753) aprovaram 4/4 ambientes, 218 testes por ambiente, cobertura 88%, Ruff check/format. A CI da Fase 0 na PR [#42912336061](https://github.com/anfalcir/legendar/actions/runs/42912336061) também aprovou a matriz multiplataforma, lock/perfis e prova FFmpeg/offset; CUDA e benchmark WhisperX foram pulados nesse evento conforme a configuração. A Fase 2 foi integrada à `main` pela PR #3, commit `4129f0a`; a Fase 3 continua bloqueada até aprovação explícita.

## 2. Situação do repositório

| Item | Estado |
|---|---|
| Repositório | `anfalcir/legendar` |
| PRs de execução | [#1 — Fase 0](https://github.com/anfalcir/legendar/pull/1), [#2 — Fase 1](https://github.com/anfalcir/legendar/pull/2) e [#3 — Fase 2](https://github.com/anfalcir/legendar/pull/3), todas merged por squash |
| Branch de conclusão da Fase 0 | `phase-0/technical-inventory` |
| Branch de implementação da Fase 1 | `phase-1/architecture`, integrada na `main` pela PR #2 |
| Branch de implementação da Fase 2 | `phase-2/professional-ui`, integrada na `main` pela PR #3 |
| Branch de implementação da Fase 3 | `phase-3/media-ingestion`, em execução; ainda sem PR/merge |
| `main` | Contém as entregas integrais das Fases 0, 1 e 2; HEAD inclui o merge squash `4129f0a` |
| Fonte de dependências | `pyproject.toml` |
| Lock | `uv.lock` regenerado pela CI e integrado à `main`; invariantes, fontes e exports CPU/CUDA aprovados no workflow #113 |
| Coletor | `scripts/phase0_inventory.py` |
| POC de mídia | `scripts/phase0_media_poc.py` |
| POC de modelos | `scripts/phase0_model_poc.py` |
| Validador do lock | `scripts/phase0_validate_lock.py` |
| Documentação técnica | plano mestre, estado vivo, protocolo, matriz de dependências, planos operacionais e handoffs das Fases 1, 2 e 3 |
| CI | `.github/workflows/phase0-quality.yml`, `phase1-quality.yml` e `phase3-quality.yml`; a Fase 3 está em validação Python 3.10–3.13 + FFmpeg |

As PRs #1, #2 e #3 foram revisadas e integradas. A `main` contém as entregas integrais das Fases 0, 1 e 2; as branches `phase-1/architecture` e `phase-2/professional-ui` preservam o histórico. A branch `phase-3/media-ingestion` contém a implementação em andamento e ainda não está integrada.

### 2.1. Checkpoint atual da Fase 1

Implementação existente em `src/legendar/`: domínio independente de Qt/infraestrutura;
orquestração serial por portas injetadas; eventos e estado do job; cancelamento cooperativo;
segmentação pura; configuração/logging; parsing de metadados de ffprobe e detecção de
ferramentas externas; cache de modelos somente observável; publicação SRT validada e atômica;
bootstrap e entrypoint. A camada Qt evoluiu na Fase 2 para uma janela profissional com temas,
diálogos, preferências QSettings, proteções de início/cancelamento, progresso, log, acessibilidade
e testes offscreen; ver `docs/FASE_2_PLANO.md` e `docs/HANDOFF_FASE_2.md`.

Na `main`, o pipeline de mídia permanece no estado pós-Fase 2. Na branch `phase-3/media-ingestion`,
a entrada local/YouTube, inspeção ffprobe, seleção de faixa e normalização FFmpeg já foram conectadas
ao pipeline; essa entrega ainda aguarda CI final e PR. Whisper/WhisperX, transcrição, alinhamento,
tradução e publicação SRT continuam fora da Fase 3. A pasta `core/`, `gui/` e `main.py` permanece
preservada e está coberta por testes de caracterização com doubles. A estratégia de convivência/
aposentadoria está em `docs/LEGACY_BASELINE.md`.

## 3. Baseline da aplicação antes da Fase 1

Arquivos da baseline identificados:

```text
core/
  __init__.py
  instagram.py
  transcription.py
  youtube.py
gui/
  __init__.py
  styles.py
  ui_main.py
  worker.py
main.py
requirements.txt
```

Situação funcional observada:

| Área | Estado da baseline |
|---|---|
| GUI | PySide6, janela simples com fluxos YouTube e MP4 |
| YouTube | Integração existente com yt-dlp |
| Arquivo local | Fluxo de seleção/transcrição de MP4 |
| Reconhecimento | Whisper, saída textual |
| FFmpeg | Caminho local ou PATH, ainda depende de instalação verificável |
| Alinhamento por palavra | Não implementado na baseline |
| WhisperX | Não integrado na baseline |
| Tradução | Não implementada |
| SRT | Não implementado |
| Inspeção e seleção de áudio | Parcial/inexistente como pipeline explícito |
| Máquina de estados | Não identificada como componente completo |
| Cancelamento cooperativo | Não implementado de forma completa |
| Temporários por job | Não implementados de forma completa |
| Testes | Sem suíte funcional prévia; os testes atuais cobrem infraestrutura da Fase 0 |

Os módulos antigos devem ser caracterizados com testes antes de remoção/refatoração. Não presumir que os scripts da Fase 0 já tenham reorganizado a aplicação.

## 4. Decisões consolidadas na Fase 0

- Repositório como fonte de verdade das dependências; máquina local como perfil de homologação.
- `pyproject.toml` para dependências diretas e `uv.lock` para resolução exata.
- Python declarado `>=3.10,<3.14`.
- Perfis `runtime-cpu` e `runtime-cu128`, mutuamente exclusivos.
- PyTorch CPU e CUDA 12.8 com índices explícitos; MPS possível via wheel PyPI macOS; ROCm 7.2 não oferecido devido à incompatibilidade atual com WhisperX estável 3.8.6.
- WhisperX estável 3.8.6 é o candidato inicial de alinhamento; o intervalo `>=3.8.6,<3.8.7` exclui a pré-release 3.8.7rc1.
- Whisper permanece o motor candidato de reconhecimento.
- `yt-dlp-ejs` declarado; Deno deve ser detectado no preflight YouTube.
- FFmpeg e ffprobe são ferramentas externas obrigatórias.
- Normalização inicial: WAV PCM signed 16-bit, mono, 16 kHz.
- O offset/time base original deve ser preservado separadamente do WAV; timestamp global = offset da origem + offset do chunk + timestamp local.
- Tradução é opcional e isolada por porta/adaptador; a Fase 1 não escolhe fornecedor. A Fase 6 deverá avaliar custo, privacidade, retenção e limites.
- Texto traduzido mantém referência temporal aos segmentos originais; não inventar timestamps por palavra para texto traduzido.

Detalhes e comandos: [MATRIZ_DEPENDENCIAS.md](MATRIZ_DEPENDENCIAS.md), [FASE_0_PROTOCOLO.md](FASE_0_PROTOCOLO.md) e [HANDOFF_FASE_1.md](HANDOFF_FASE_1.md).

## 5. Inventário do computador-alvo recebido

O relatório inicial, recebido em 10/11/2026, identificou:

| Item | Observação |
|---|---|
| Python | CPython 3.12.3 |
| Sistema | Linux x86_64, kernel 7.0.0-42-generic |
| CPU | AMD Ryzen 3 2200G, quatro CPUs lógicas |
| RAM | 12,59 GiB total; 7,65 GiB disponíveis no momento da coleta |
| Disco | 218,51 GiB total; 165,60 GiB livres |
| Gráficos | Radeon Vega integrada; sem NVIDIA detectada por `nvidia-smi` |
| FFmpeg/ffprobe | Não encontrados no inventário enviado |
| PyTorch/Whisper/WhisperX/PySide6 | Ausentes no interpretador consultado |

O primeiro relatório antecede a ampliação do coletor que agora identifica distribuição Linux, controladores PCI e runtimes JS. Reexecutar antes da homologação das fases 3–5. O resultado de hardware não restringe o manifesto do produto e não autoriza prometer aceleração ROCm.

## 6. Evidências e estado das validações

| Verificação | Evidência final | Interpretação |
|---|---|---|
| Matriz do coletor/CLI | Workflow [#109](https://github.com/anfalcir/legendar/actions/runs/42858694179): 12 combinações Python 3.10–3.13 × Ubuntu/Windows/macOS, todas aprovadas | Portabilidade do coletor, dos testes e dos CLIs; não declara a aplicação completa homologada nos três sistemas |
| FFmpeg/ffprobe e timeline | Workflow #109 aprovado; áudio sintético com offset não-zero normalizado para WAV PCM mono/16 kHz e mapeamento local→global validado | Prova sintética de mídia/timeline aprovada |
| Lock e manifesto | Workflow #109 aprovou resolução, `uv.lock`, invariantes, origem dos wheels e exports dos dois perfis | Lock atual da branch é consistente com `pyproject.toml` |
| Runtime CPU + WhisperX | Workflow #109 instalou o perfil CPU e concluiu a POC PT-BR/EN | Compatibilidade inicial do runtime demonstrada; não equivale à aceitação do produto |
| Runtime CUDA 12.8 | Workflow #109 instalou e importou Torch, torchvision e torchaudio do perfil CUDA | Instalação/importação validada; runner sem GPU física, portanto não comprova execução de inferência CUDA |
| Benchmark FLEURS PT-BR | 2 amostras; WER médio 0,275; RTF médio 0,372; 26 palavras com timestamps válidos; 0 inválidas | Amostra pequena de fala lida, somente referência lexical/técnica |
| Benchmark FLEURS EN | 2 amostras; WER médio 0,209559; RTF médio 0,163; 30 palavras com timestamps válidos; 0 inválidas | Amostra pequena de fala lida, somente referência lexical/técnica |
| Suíte completa da Fase 1 | CI [#116](https://github.com/anfalcir/legendar/actions/runs/42905199857): 196 passed em cada ambiente Python 3.10–3.13; cobertura total de 88% | 4/4 jobs aprovados; inclui domínio, aplicação, infraestrutura, integração, GUI e caracterização legada |
| Ruff da Fase 1 | `ruff check` e `ruff format --check` aprovados na CI #116 em Python 3.10–3.13 | Todo o escopo mantido da arquitetura e dos testes está lintado e formatado |
| Inicialização da GUI nova | `PYTHONPATH=src QT_QPA_PLATFORM=offscreen timeout 5s uv run --locked python -m legendar`: abriu e permaneceu no event loop até timeout | Smoke test local, sem processamento real |
| CI da Fase 1 | **Concluída e aprovada** | Workflows [#116](https://github.com/anfalcir/legendar/actions/runs/42905199857) e [#127](https://github.com/anfalcir/legendar/actions/runs/42905799938), ambos 4/4 verdes em Python 3.10–3.13 |
| Suíte completa da Fase 2 | [CI #42911438434](https://github.com/anfalcir/legendar/actions/runs/42911438434): 218 passed por ambiente; cobertura 88% | 4/4 jobs aprovados em Python 3.10–3.13; inclui testes Qt offscreen, preferências e confirmações |
| Ruff da Fase 2 | `ruff check` e `ruff format --check` aprovados na CI #42911438434 | 91 arquivos formatados; escopo mantido inteiro aprovado |
| Caracterização e destino do legado | Concluída | Nove testes com doubles; política de preservação, congelamento e gate de aposentadoria em `LEGACY_BASELINE.md` |
| Inventário atualizado no computador-alvo | Pendente | Reexecutar antes da homologação de mídia/modelos |
| Precisão temporal contra timestamps humanos | Pendente | Gate da Fase 5 |
| Tradução com fornecedor/custo/privacidade | Decidido adiar escolha do provedor até antes da Fase 6 | Não bloqueia arquitetura |

O benchmark final usou WhisperX 3.8.6, modelo `tiny`, CPU/int8, quatro áudios FLEURS do split `test` (dois `pt_br`, dois `en_us`), revisão de dataset fixada. O processo levou 62,131 s no runner GitHub e atingiu pico de RSS de 3.456.839.680 bytes (~3,22 GiB). O RTF é a razão entre o tempo de transcrição+alinhamento e a duração de cada áudio; valores abaixo de 1 indicam que essa pequena execução levou menos tempo que a duração de áudio no runner.

O log também registrou aviso não bloqueante de `torchcodec`: as bibliotecas FFmpeg compartilhadas não foram carregadas pelo backend de I/O do pyannote. A POC, contudo, lê o áudio para memória e entrega o waveform diretamente ao WhisperX/alinhador; o job terminou com sucesso. A prova separada de FFmpeg/ffprobe também passou. Isso não valida decodificação via TorchCodec no produto; se essa via for usada futuramente, sua compatibilidade deverá ser homologada explicitamente.

WER mede erro lexical, não precisão dos timestamps. As quatro amostras de fala lida não representam pregações, música, ruído, sobreposição ou fala espontânea. A cobertura de timestamps observada é apenas um smoke check dos limites/estrutura, não comparação com anotação humana.

## 7. Status das fases

| Fase | Status | Observação |
|---|---|---|
| 0 — Definições e prova técnica | **Concluída e integrada** | PR #1 merged por squash; CI final verde |
| 1 — Reestruturação arquitetural | **Concluída e integrada** | PR #2 merged por squash no commit `de31ddd`; 196 testes por ambiente Python 3.10–3.13, cobertura 88%, Ruff/format aprovados |
| 2 — Interface profissional | **Concluída e integrada** | PR #3 merged por squash no commit `4129f0a`; 218 testes por ambiente Python 3.10–3.13, cobertura 88%, Ruff/format aprovados |
| 3 — Entrada e preparação de mídia | **Em execução na branch `phase-3/media-ingestion`** | Implementação presente; finalizar CI Python 3.10–3.13, revisão e PR/merge. Ainda não concluída |
| 4 — Reconhecimento Whisper | Não iniciada | Comparação PT-BR/EN e desempenho no computador-alvo |
| 5 — Alinhamento temporal | Não iniciada | Referência humana, mediana/P95, cobertura e anomalias |
| 6 — Tradução, segmentação e SRT | Não iniciada | Escolha de fornecedor antes da implementação da tradução |
| 7 — Integração ponta a ponta | Não iniciada | Conectar GUI ao pipeline real |
| 8 — Testes e homologação | Não iniciada | Homologação nos ambientes declarados suportados |
| 9 — Documentação e finalização | Em preparação | Documentação inicial e handoff registrados |

## 8. Pendências encaminhadas às fases corretas

1. **Fases 1 e 2:** concluídas e integradas à `main`; não há pendências atribuídas a essas fases. A Fase 2 não ativou processamento real de mídia.
2. **Fase 3 (branch atual):** concluir a matriz CI Python 3.10–3.13 + FFmpeg, revisar cancelamento/cleanup e abrir PR; homologação com arquivos reais e computador-alvo permanece necessária antes da validação global da Fase 8.
3. **Fase 4:** comparar modelos Whisper com corpus PT-BR/EN representativo; registrar WER/CER, duração, memória e RTF no hardware-alvo.
4. **Fase 5:** anotar manualmente início/fim de palavras e medir erro mediano/P95, cobertura e falhas; não homologar sincronização só por WER.
5. **Antes da Fase 6:** escolher provedor e aprovar custo, privacidade, retenção, limites e comportamento de falha.
6. **Fase 8:** testar aplicação e fluxos completos nos sistemas/backends declarados como suportados.

As pendências acima são gates de produto alocados às fases responsáveis; elas não reabrem a Fase 0.

## 9. Próxima ação objetiva

As Fases 1 e 2 estão concluídas e integradas à `main`. A Fase 3 está em implementação na branch
`phase-3/media-ingestion`; a próxima ação é obter CI verde em todos os ambientes, concluir revisão e
integrar por PR. Não iniciar a Fase 4 antes do merge e de aprovação explícita.

---

## Histórico de atualizações

| Data | Atualização |
|---|---|
| 09/11/2026 | Plano mestre e estado inicial registrados; remodelagem funcional ainda não iniciada |
| 10/11/2026 | Coletor de ambiente, CI inicial, matriz de dependências e protocolo da Fase 0 introduzidos |
| 10/11/2026 | Prova FFmpeg/ffprobe adicionada e aprovada em CI para WAV mono/16 kHz e mapeamento de offset |
| 10/11/2026 | Identificada e corrigida seleção indevida de WhisperX 3.8.7rc1; intervalo restrito ao estável 3.8.6 |
| 10/11/2026 | Identificado conflito de datasets 5.2.0 com huggingface-hub<1.0 do WhisperX 3.8.6; dependência removida e avaliação migrou para TSV/arquivos FLEURS |
| 10/11/2026 | Handoff da Fase 1 criado com decisões, arquitetura, contratos, testes, limites e instruções de execução |
| 10/11/2026 | Workflow #109 concluído com 16/16 jobs aprovados; lock e perfis CPU/CUDA validados, matriz de 12 ambientes verde, POC FFmpeg/offset verde e benchmark WhisperX PT-BR/EN concluído |
| 10/11/2026 | Workflow final push #113 aprovado com 16/16 jobs e PR workflow #114 concluído com sucesso; PR #1 integrada por squash na `main` (commit `992cb874274e73d0264994e39926113f1461236f`) |
| 10/11/2026 | Branch `phase-1/architecture` criada a partir da `main` atualizada; Fase 1 pronta para iniciar, sem implementação antecipada |
| 10/11/2026 | Fase 1 concluída e integrada por squash na `main` pela PR #2, commit `de31ddd`; 196 testes aprovados em Python 3.10–3.13, cobertura de 88%, Ruff check/format verdes, CI #127 confirmada e CI Fase 0 PR #160 aprovada |
| 10/11/2026 | Fase 2 concluída e integrada por squash na `main` pela PR #3, commit `4129f0a`; 218 testes aprovados em Python 3.10–3.13, cobertura 88%, Ruff check/format verdes; gates PR herdados Fase 0/1 aprovados |
| 10/11/2026 | Fase 3 iniciada na branch `phase-3/media-ingestion`; adaptadores FFmpeg/ffprobe/yt-dlp, seleção de faixa e inspeção Qt assíncrona implementados; CI final e PR ainda pendentes |
