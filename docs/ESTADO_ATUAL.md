# Estado atual do Legendar

- **Última atualização:** 10/11/2026
- **Repositório:** anfalcir/legendar
- **Branch de referência do trabalho:** `main`
- **Branch padrão / base de integração:** `main`
- **Branch de implementação da Fase 1:** `phase-1/architecture` (integrada)
- **Branch de implementação da Fase 2:** `phase-2/professional-ui` (integrada)
- **Branch de implementação da Fase 3:** `phase-3/media-ingestion` (integrada pela PR #4)
- **Branch de implementação da Fase 5:** `phase-5/temporal-alignment` (integrada)
- **Branch de implementação da Fase 6:** `phase-6/translation-segmentation-srt`, enviada ao `origin`; aguardando abertura da PR
- **Branch padrão:** `main`
- **Fases concluídas e integradas:** Fases 0–5
- **Fase em execução:** Fase 6 — tradução, segmentação e SRT (implementação concluída e CI de push verde; falta abrir a PR e integrar)
- **Fase concluída mais recente integrada:** Fase 5 — alinhamento temporal WhisperX
- **Implementação mais recente:** tradução local por cue com NLLB-200 distilled 600M, segmentação editorial de duas linhas, validação do trilho e publicação SRT atômica
- **Última integração na `main`:** PR [#6](https://github.com/anfalcir/legendar/pull/6), squash em `5c9a2ba48a7e2d16d2099511c3c1456c59ae299c`
- **PR da Fase 0:** [#1](https://github.com/anfalcir/legendar/pull/1), integrada por squash
- **PR da Fase 1:** [#2](https://github.com/anfalcir/legendar/pull/2), merged por squash em 10/11/2026
- **PR da Fase 2:** [#3](https://github.com/anfalcir/legendar/pull/3), merged por squash em 10/11/2026
- **PR da Fase 3:** [#4](https://github.com/anfalcir/legendar/pull/4), merged por squash em 10/11/2026
- **PR da Fase 4:** [#5](https://github.com/anfalcir/legendar/pull/5), merged por squash em 10/11/2026
- **PR da Fase 5:** [#6](https://github.com/anfalcir/legendar/pull/6), merged por squash em 10/11/2026
- **Commit de integração da Fase 0:** `992cb874274e73d0264994e39926113f1461236f`
- **Commit de integração da Fase 1:** `de31dddffc4f8e761692129d4c47a02ca89b8b83`
- **Commit de integração da Fase 2:** `4129f0a906a04693502f298b71767605499e3f68`
- **Commit de integração da Fase 3:** `dfa440b39e7623356388c774834e23ee53fc1d09`
- **Commit de integração da Fase 4:** `2f9751139616591e31a0ec73902265b38b040d41`
- **Commit de integração da Fase 5:** `5c9a2ba48a7e2d16d2099511c3c1456c59ae299c`
- **Documentos de handoff:** [HANDOFF_FASE_1.md](HANDOFF_FASE_1.md), [HANDOFF_FASE_2.md](HANDOFF_FASE_2.md), [HANDOFF_FASE_3.md](HANDOFF_FASE_3.md), [HANDOFF_FASE_4.md](HANDOFF_FASE_4.md), [HANDOFF_FASE_5.md](HANDOFF_FASE_5.md) e [HANDOFF_FASE_6.md](HANDOFF_FASE_6.md)

> As Fases 0–5 estão concluídas e integradas à `main`. A Fase 5 foi integrada pela PR [#6](https://github.com/anfalcir/legendar/pull/6), squash no commit `5c9a2ba48a7e2d16d2099511c3c1456c59ae299c`. CI push [#42935484072](https://github.com/anfalcir/legendar/actions/runs/42935484072) e PR [#42935490648](https://github.com/anfalcir/legendar/actions/runs/42935490648) passaram com 5/5 jobs cada; gates herdados Fases 0, 1, 3 e 4 também passaram. A suíte determinística aprovou 303 testes por ambiente em Python 3.10–3.13, com 2 skips esperados e cobertura de 85%; Ruff check e format passaram. O smoke real CPU Whisper + WhisperX 3.8.6 executou PT-BR/EN e publicou artefato. A Fase 6 está implementada e publicada na branch `phase-6/translation-segmentation-srt`: a suíte determinística local aprovou 387 testes com 2 skips esperados (FFmpeg/ffprobe ausentes no ambiente de desenvolvimento), e Ruff check, Ruff format e `uv lock --check` estão limpos. O workflow `phase6-quality.yml` valida a matriz Python 3.10–3.13 e um smoke do adaptador NLLB com o runtime CPU real, sem baixar pesos. A branch foi enviada ao `origin` e o workflow push [#42951041522](https://github.com/anfalcir/legendar/actions/runs/42951041522) passou com 5/5 jobs (Python 3.10–3.13 determinísticos e NLLB adapter com `transformers` real em CPU); falta abrir a PR e integrar. A precisão temporal e a qualidade tradutória em corpus autorizado de pregações e no computador-alvo permanecem como homologação de produto, não como bloqueio de engenharia.

---

## 1. Resumo executivo

A aplicação nova tem camadas `domain`, `application`, `infrastructure`, `presentation` e `bootstrap`; inclui entidades/invariantes, máquina de estados, pipeline serial, cancelamento e workspaces isolados. A Fase 2 acrescentou interface Qt profissional com temas, confirmações, preferências, progresso honesto, log, acessibilidade e proteção contra ações acidentais. A Fase 3 integrou aquisição local/YouTube, ffprobe, seleção de faixa, FFmpeg e inspeção assíncrona. A Fase 4 integrou Whisper local atrás da porta `Transcriber`. A Fase 5 integrou WhisperX atrás da porta `Aligner`, com palavras em timeline global, diagnóstico explícito e métricas. A Fase 6 integrou segmentação editorial, tradução local por cue atrás da porta `Translator`, validação do trilho e publicação SRT de duas linhas. A GUI ainda não dispara o pipeline completo: conectar a janela ao job real é o escopo da Fase 7. O legado `main.py`/`core/`/`gui/` continua preservado.

A Fase 0 estabeleceu e documentou a direção técnica: governança de dependências, perfis de runtime, coletor de ambiente, prova sintética de mídia/offset, script de POC PT-BR/EN e contrato arquitetural. O plano operacional e o handoff da Fase 1 foram atualizados para registrar o checkpoint, as evidências e as pendências.

**Estado:** Fase 0 concluída e integrada. O workflow push #113 terminou com 16/16 jobs aprovados e a PR workflow #114 concluiu com sucesso; os jobs exclusivos de push (benchmark completo e instalação CUDA) foram pulados no evento PR por configuração. A PR #1 foi integrada por squash no commit `992cb874274e73d0264994e39926113f1461236f`. Na Fase 1, os workflows [#116](https://github.com/anfalcir/legendar/actions/runs/42905199857) e [#127](https://github.com/anfalcir/legendar/actions/runs/42905799938) aprovaram Python 3.10–3.13 (196 testes, cobertura 88%, Ruff/format verdes); a Fase 1 foi integrada à `main` pela PR #2, commit `de31ddd`. Na Fase 2, o workflow push [#42911438434](https://github.com/anfalcir/legendar/actions/runs/42911438434) e o workflow da PR [#42912335753](https://github.com/anfalcir/legendar/actions/runs/42912335753) aprovaram 4/4 ambientes, 218 testes por ambiente, cobertura 88%, Ruff check/format. A CI da Fase 0 na PR [#42912336061](https://github.com/anfalcir/legendar/actions/runs/42912336061) também aprovou a matriz multiplataforma, lock/perfis e prova FFmpeg/offset; CUDA e benchmark WhisperX foram pulados nesse evento conforme a configuração. A Fase 2 foi integrada à `main` pela PR #3, commit `4129f0a`. A Fase 3 foi autorizada, implementada e integrada à `main` pela PR #4, commit `dfa440b39e7623356388c774834e23ee53fc1d09`.

## 2. Situação do repositório

| Item | Estado |
|---|---|
| Repositório | `anfalcir/legendar` |
| PRs de execução | [#1 — Fase 0](https://github.com/anfalcir/legendar/pull/1), [#2 — Fase 1](https://github.com/anfalcir/legendar/pull/2), [#3 — Fase 2](https://github.com/anfalcir/legendar/pull/3), [#4 — Fase 3](https://github.com/anfalcir/legendar/pull/4), [#5 — Fase 4](https://github.com/anfalcir/legendar/pull/5) e [#6 — Fase 5](https://github.com/anfalcir/legendar/pull/6); todas integradas por squash. A Fase 6 está na branch `phase-6/translation-segmentation-srt`, já enviada ao `origin`, e a PR ainda precisa ser aberta |
| Branch de conclusão da Fase 0 | `phase-0/technical-inventory` |
| Branch de implementação da Fase 1 | `phase-1/architecture`, integrada na `main` pela PR #2 |
| Branch de implementação da Fase 2 | `phase-2/professional-ui`, integrada na `main` pela PR #3 |
| Branch de implementação da Fase 3 | `phase-3/media-ingestion`, integrada na main pela PR #4 |
| Branch de implementação da Fase 4 | `phase-4/whisper-recognition`, integrada à `main` pela PR #5 |
| Branch de implementação da Fase 5 | `phase-5/temporal-alignment`, integrada à `main` pela PR #6 |
| Branch de implementação da Fase 6 | `phase-6/translation-segmentation-srt`, enviada ao `origin`; CI push [#42951041522](https://github.com/anfalcir/legendar/actions/runs/42951041522) verde |
| `main` | Contém as entregas integrais das Fases 0–5; HEAD de integração da Fase 5: `5c9a2ba48a7e2d16d2099511c3c1456c59ae299c` |
| Fonte de dependências | `pyproject.toml` |
| Lock | `uv.lock` regenerado pela CI e integrado à `main`; invariantes, fontes e exports CPU/CUDA aprovados no workflow #113 |
| Coletor | `scripts/phase0_inventory.py` |
| POC de mídia | `scripts/phase0_media_poc.py` |
| POC de modelos | `scripts/phase0_model_poc.py` |
| Validador do lock | `scripts/phase0_validate_lock.py` |
| Documentação técnica | plano mestre, estado vivo, protocolo, matriz de dependências, planos operacionais e handoffs das Fases 1–6 |
| CI | workflows de qualidade das Fases 0–6; Fase 6 acrescenta matriz Python 3.10–3.13, testes herméticos do adaptador NLLB e smoke do runtime de tradução CPU com `transformers` real |

As PRs #1–#6 foram revisadas e integradas por squash. A `main` contém as Fases 0–5; a branch `phase-5/temporal-alignment` foi integrada pela PR #6. As branches `phase-1/architecture`, `phase-2/professional-ui`, `phase-3/media-ingestion`, `phase-4/whisper-recognition` e `phase-5/temporal-alignment` preservam seus históricos. A branch `phase-6/translation-segmentation-srt` contém a Fase 6 completa e aguarda PR; quando integrada, a `main` passará a conter as Fases 0–6.

### 2.1. Checkpoint atual da Fase 1

Implementação existente em `src/legendar/`: domínio independente de Qt/infraestrutura;
orquestração serial por portas injetadas; eventos e estado do job; cancelamento cooperativo;
segmentação pura; configuração/logging; parsing de metadados de ffprobe e detecção de
ferramentas externas; cache de modelos somente observável; publicação SRT validada e atômica;
bootstrap e entrypoint. A camada Qt evoluiu na Fase 2 para uma janela profissional com temas,
diálogos, preferências QSettings, proteções de início/cancelamento, progresso, log, acessibilidade
e testes offscreen; ver `docs/FASE_2_PLANO.md` e `docs/HANDOFF_FASE_2.md`.

Na `main`, a entrada local/YouTube, inspeção ffprobe, seleção de faixa e normalização FFmpeg estão integradas pela Fase 3. Na branch `phase-4/whisper-recognition`, Whisper local foi conectado ao pipeline; a porta `Transcriber` recebe WAV PCM mono/16 kHz, devolve idioma e segmentos textuais e não define timestamps. A Fase 5 é responsável pelo alinhamento e já está integrada. A Fase 6, na branch `phase-6/translation-segmentation-srt`, consome `AlignmentResult`, segmenta em cues de duas linhas, traduz por cue atrás da porta `Translator` e publica o SRT validado. A pasta `core/`, `gui/` e `main.py` continua preservada e coberta por testes de caracterização com doubles; a política de aposentadoria está em `docs/LEGACY_BASELINE.md`.

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
- Tradução é opcional e isolada por porta/adaptador. Decisão da Fase 6: NLLB-200 distilled 600M local via `transformers`, sem enviar texto a serviço externo; custo zero por chamada, retenção nenhuma fora do computador e falha explícita quando modelo ou dispositivo não estão disponíveis.
- Texto traduzido mantém referência temporal aos segmentos originais; não inventar timestamps por palavra para texto traduzido.
- Segmentação e publicação usam o mesmo alvo editorial (duas linhas de 42 caracteres, ~17 cps); o validador reporta o que ficou fora do alvo em vez de truncar texto.

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
| Suíte e integração de mídia da Fase 3 | CI push [#42921552291](https://github.com/anfalcir/legendar/actions/runs/42921552291) e CI PR [#42921987927](https://github.com/anfalcir/legendar/actions/runs/42921987927): 249 testes aprovados por ambiente Python 3.10–3.13; 87% de cobertura | 4/4 jobs aprovados em cada workflow; integração FFmpeg/ffprobe sintética real, Qt offscreen e contrato yt-dlp offline |
| Ruff da Fase 3 | `ruff check` e `ruff format --check` aprovados nos workflows push/PR | 97 arquivos formatados |
| Gates herdados da Fase 0/1 na PR da Fase 3 | PR workflows [Fase 0 #42921987820](https://github.com/anfalcir/legendar/actions/runs/42921987820) e [Fase 1 #42921987910](https://github.com/anfalcir/legendar/actions/runs/42921987910) aprovados | 14 jobs executados da Fase 0 e 4 jobs da Fase 1 aprovados; benchmark WhisperX e smoke CUDA pulados no evento PR por configuração |
| Caracterização e destino do legado | Concluída | Nove testes com doubles; política de preservação, congelamento e gate de aposentadoria em `LEGACY_BASELINE.md` |
| Adaptador Whisper | Concluído e integrado pela PR #5 | OpenAI Whisper local; PT/EN automático/manual; cache e modelo carregado sob demanda; transcrição em worker |
| Benchmark de reconhecimento | Smoke real aprovado | FLEURS, tiny/base/small, duas amostras por idioma; WER/CER/RTF/tempo/RSS no artefato da CI |
| Inventário e benchmark do computador-alvo | Pendente | Executar scripts locais com runtime CPU/CUDA adequado; runner GitHub não representa o hardware de implantação |
| Corpus representativo de pregações | Pendente | Preparar amostras autorizadas com referências textuais humanas e fronteiras revisadas; avaliar fora do corpus de fala lida FLEURS |
| Adaptador de alinhamento WhisperX | Concluído e integrado pela PR #6 | PT/EN, cache por idioma, janela de busca separada do range final, sem interpolação automática e diagnósticos explícitos |
| Avaliador temporal | Concluído e integrado pela PR #6 | JSONL local com palavra/início/fim humano; mediana/P95, cobertura e não alinhadas; relatório sem áudio, caminhos ou texto |
| Inventário atualizado no computador-alvo | Pendente | Reexecutar antes da homologação de mídia/modelos |
| Precisão temporal contra timestamps humanos | Pendente como homologação de produto | Usar corpus autorizado com fronteiras humanas PT-BR/EN e executar no computador-alvo; não bloqueia o desenvolvimento das Fases 6/7 |
| Smoke integrado Fase 5 | Aprovado na CI PR #42935490648 | FLEURS CPU, tiny, uma amostra por idioma; PT 12/12 alinhadas (100%, WER 0,0833); EN 14/15 (93,33%, WER 0,3529), uma palavra sem alinhamento preservada; bounds válidos em todas as palavras alinhadas |
| Tradução com fornecedor/custo/privacidade | Decidido na Fase 6: NLLB-200 distilled 600M local | Pesos baixados sob demanda para `<models_dir>/nllb`; nenhum texto enviado a serviço externo; adapter isolado atrás da porta `Translator` |
| Segmentação editorial | Concluída na branch `phase-6/translation-segmentation-srt` | Duas linhas de 42 caracteres, 84 por cue, 1–7 s, pausa de 0,6 s, 17 cps; subdivisão usa apenas timestamps de palavras alinhadas |
| Tradução por cue | Concluída na branch `phase-6/translation-segmentation-srt` | 1:1 com tempos preservados, lotes de 16, `num_beams=4`, cancelamento entre lotes, falha explícita em saída inconsistente |
| Publicação SRT | Concluída na branch `phase-6/translation-segmentation-srt` | `format_srt` com duas linhas, `validate_track` antes da troca, roundtrip e escrita atômica |
| Suíte e CI da Fase 6 | Local e CI de push verdes | 387 testes aprovados e 2 skips esperados; Ruff check/format e `uv lock --check` limpos; `phase6-quality.yml` cobre Python 3.10–3.13 e runtime CPU com `transformers` real, com 5/5 jobs aprovados em [#42951041522](https://github.com/anfalcir/legendar/actions/runs/42951041522) |
| Qualidade tradutória PT↔EN | Pendente como homologação de produto | Corpus autorizado de pregações com revisão humana; nomes próprios, números e linguagem religiosa ainda não medidos |

O benchmark final usou WhisperX 3.8.6, modelo `tiny`, CPU/int8, quatro áudios FLEURS do split `test` (dois `pt_br`, dois `en_us`), revisão de dataset fixada. O processo levou 62,131 s no runner GitHub e atingiu pico de RSS de 3.456.839.680 bytes (~3,22 GiB). O RTF é a razão entre o tempo de transcrição+alinhamento e a duração de cada áudio; valores abaixo de 1 indicam que essa pequena execução levou menos tempo que a duração de áudio no runner.

O log também registrou aviso não bloqueante de `torchcodec`: as bibliotecas FFmpeg compartilhadas não foram carregadas pelo backend de I/O do pyannote. A POC, contudo, lê o áudio para memória e entrega o waveform diretamente ao WhisperX/alinhador; o job terminou com sucesso. A prova separada de FFmpeg/ffprobe também passou. Isso não valida decodificação via TorchCodec no produto; se essa via for usada futuramente, sua compatibilidade deverá ser homologada explicitamente.

WER mede erro lexical, não precisão dos timestamps. As quatro amostras de fala lida não representam pregações, música, ruído, sobreposição ou fala espontânea. A cobertura de timestamps observada é apenas um smoke check dos limites/estrutura, não comparação com anotação humana.

## 7. Status das fases

| Fase | Status | Observação |
|---|---|---|
| 0 — Definições e prova técnica | **Concluída e integrada** | PR #1 merged por squash; CI final verde |
| 1 — Reestruturação arquitetural | **Concluída e integrada** | PR #2 merged por squash no commit `de31ddd`; 196 testes por ambiente Python 3.10–3.13, cobertura 88%, Ruff/format aprovados |
| 2 — Interface profissional | **Concluída e integrada** | PR #3 merged por squash no commit `4129f0a`; 218 testes por ambiente Python 3.10–3.13, cobertura 88%, Ruff/format aprovados |
| 3 — Entrada e preparação de mídia | **Concluída e integrada** | PR #4 merged por squash em `dfa440b39e7623356388c774834e23ee53fc1d09`; CI 4/4 push e PR em Python 3.10–3.13, 249 testes por ambiente e cobertura 87% |
| 4 — Reconhecimento Whisper | **Concluída e integrada** | PR #5 merged por squash em `2f975113`; CI push/PR 4/4 em Python 3.10–3.13; smoke real CPU e benchmark tiny/base/small PT-BR/EN publicados. Homologação no computador-alvo/corpus de pregações segue pendente |
| 5 — Alinhamento temporal | **Implementada, validada e integrada** | PR #6; WhisperX 3.8.6 PT/EN, CI push/PR verde, 303 testes, smoke real CPU. Precisão contra fronteiras humanas e homologação no computador-alvo continuam como gate de produto |
| 6 — Tradução, segmentação e SRT | **Implementada, validada e com CI push verde na branch** | `phase-6/translation-segmentation-srt`; NLLB-200 distilled 600M local por cue, duas linhas de 42 caracteres, validação do trilho e publicação atômica; 387 testes locais verdes e 5/5 jobs em [#42951041522](https://github.com/anfalcir/legendar/actions/runs/42951041522). Falta abrir a PR e integrar. Qualidade tradutória e leitura em mídia real seguem como gate de produto |
| 7 — Integração ponta a ponta | Não iniciada | Conectar GUI ao pipeline real e exibir avisos de segmentação/tradução/validação |
| 8 — Testes e homologação | Não iniciada | Homologação nos ambientes declarados suportados |
| 9 — Documentação e finalização | Em preparação | Documentação inicial e handoff registrados |

## 8. Pendências encaminhadas às fases corretas

1. **Fases 0–5:** implementação e integração concluídas na `main`; PR #6 e todos os gates de CI da Fase 5 aprovados.
2. **Fase 4 — homologação de produto ainda aberta:** atualizar inventário do computador-alvo e executar benchmark com amostras representativas de pregações PT-BR/EN e referências textuais humanas revisadas. O smoke FLEURS não homologa qualidade final nem escolhe definitivamente o perfil.
3. **Fase 5 — homologação temporal ainda aberta:** avaliar início/fim de palavras em corpus autorizado, medir mediana/P95, cobertura e falhas no computador-alvo. Não homologar sincronização apenas por WER; esse gate não bloqueia as Fases 6/7.
4. **Fase 6 — implementação concluída e CI de push verde:** tradução local por cue com NLLB-200, segmentação de duas linhas, validação do trilho e publicação SRT atômica. Falta abrir a PR, acompanhar o workflow no evento PR e integrar. Homologar qualidade tradutória e comportamento em mídia real continua como gate de produto.
5. **Fase 8:** testar aplicação e fluxos completos nos sistemas/backends declarados como suportados, incluindo arquivos reais e homologação online controlada do YouTube.

As pendências acima são gates de produto alocados às fases responsáveis; elas não reabrem a Fase 0.

## 9. Próxima ação objetiva

A Fase 5 está concluída e integrada pela PR #6 (squash `5c9a2ba`). A Fase 6 está implementada e enviada ao `origin` na branch `phase-6/translation-segmentation-srt`, com o workflow push [#42951041522](https://github.com/anfalcir/legendar/actions/runs/42951041522) verde em 5/5 jobs: falta abrir a PR em https://github.com/anfalcir/legendar/pull/new/phase-6/translation-segmentation-srt, acompanhar `phase6-quality.yml` no evento PR e integrar por squash. Depois disso, a Fase 7 conecta a GUI ao pipeline real, consumindo `PipelineResult`, avisos de segmentação/tradução/validação e o caminho do SRT publicado. Os gates de precisão temporal com fronteiras humanas e de qualidade tradutória em pregações continuam obrigatórios para homologação do produto.

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
| 10/11/2026 | Fase 3 implementada na branch `phase-3/media-ingestion`; adaptadores FFmpeg/ffprobe/yt-dlp, seleção de faixa, preflight EJS e inspeção Qt assíncrona concluídos; CI de push 4/4 verde |
| 10/11/2026 | PR #4 aprovada: CI da Fase 3 4/4, Fase 1 4/4 e 14 jobs executados da Fase 0 aprovados; dois jobs exclusivos de push foram pulados no evento PR conforme configuração |
| 10/11/2026 | Fase 3 integrada por squash à `main` pela PR #4, commit `dfa440b39e7623356388c774834e23ee53fc1d09`; 249 testes por ambiente Python 3.10–3.13, cobertura 87%, Ruff/format verdes |

| 10/11/2026 | Fase 4 integrada por squash pela PR #5 no commit `2f9751139616591e31a0ec73902265b38b040d41`; CI push/PR 4/4 Python 3.10–3.13, smoke CPU real tiny/base/small PT-BR/EN e artefato de métricas publicados. Homologação no computador-alvo e corpus de pregações permanece pendente |

| 10/11/2026 | Fase 5 iniciada na branch `phase-5/temporal-alignment` a partir da `main` pós-Fase 4; adaptador WhisperX, janela aproximada, offset global, diagnósticos, smoke e avaliador temporal adicionados em implementação. CI e PR ainda pendentes |

| 10/11/2026 | Fase 5 concluída e integrada por squash pela PR #6 no commit `5c9a2ba48a7e2d16d2099511c3c1456c59ae299c`; push/PR 5/5 jobs aprovados, gates herdados Fases 0/1/3/4 verdes, 303 testes por Python 3.10–3.13 (2 skips), 85% de cobertura, Ruff/format verdes e smoke real Whisper + WhisperX CPU PT-BR/EN publicado. Precisão temporal em corpus humano e homologação no computador-alvo permanecem gates de produto |

| 10/11/2026 | Fase 6 iniciada na branch `phase-6/translation-segmentation-srt`: dependências `transformers` e `sentencepiece` declaradas, layout de duas linhas, `SegmentationPolicy`, porta `Translator`, validação do trilho, publicação SRT e adaptador NLLB-200 implementados |

| 10/11/2026 | Fase 6 implementada e validada localmente: 387 testes aprovados e 2 skips esperados, Ruff check/format e `uv lock --check` limpos, workflow `phase6-quality.yml` criado com matriz Python 3.10–3.13 e smoke do runtime CPU real. Qualidade tradutória e comportamento em mídia real seguem como homologação de produto |

| 11/11/2026 | Fase 6 publicada na branch `phase-6/translation-segmentation-srt` (head `9760b41f9f6db79fa4ad7d709d372138c81ed3cc`) com implementação, testes, CI e documentação em commits separados. Workflow push [#42951041522](https://github.com/anfalcir/legendar/actions/runs/42951041522) passou com 5/5 jobs: Python 3.10–3.13 determinísticos e NLLB adapter com `transformers` real em CPU. Falta abrir a PR e integrar por squash |
