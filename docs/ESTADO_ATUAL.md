# Estado atual do Legendar

- **Última atualização:** 10/11/2026
- **Repositório:** anfalcir/legendar
- **Branch de trabalho atual:** `phase-1/architecture`
- **Branch padrão:** `main`
- **Fase concluída:** Fase 0 — Definições e prova técnica
- **Fase atual:** Fase 1 — Reestruturação arquitetural, pronta para início (ainda não iniciada)
- **PR da Fase 0:** [#1](https://github.com/anfalcir/legendar/pull/1), integrada por squash
- **Commit de integração na main:** `992cb874274e73d0264994e39926113f1461236f`
- **Documento de handoff:** [HANDOFF_FASE_1.md](HANDOFF_FASE_1.md)

> A Fase 0 está concluída e integrada. O workflow final da branch [#113](https://github.com/anfalcir/legendar/actions/runs/42867776364) terminou com 16/16 jobs aprovados; a validação da PR [#114](https://github.com/anfalcir/legendar/actions/runs/42867789927) também concluiu com sucesso. A branch `phase-1/architecture` foi criada diretamente do commit de integração da `main`. Nenhuma implementação da Fase 1 foi iniciada neste checkpoint.

---

## 1. Resumo executivo

A remodelagem funcional do Legendar ainda não começou. A baseline continua sendo uma pequena aplicação Python/PySide6 com fluxos antigos de transcrição via Whisper/yt-dlp e saída textual; ela não implementa ainda o pipeline SRT final, alinhamento robusto, tradução ou cancelamento arquitetural completo.

A Fase 0 estabeleceu e documentou a direção técnica: governança de dependências, perfis de runtime, coletor de ambiente, prova sintética de mídia/offset, script de POC PT-BR/EN e contrato arquitetural para a próxima fase. A documentação de passagem para a IA da IDE está em `docs/HANDOFF_FASE_1.md`.

**Estado de fechamento:** Fase 0 concluída, validada e integrada. O workflow push final #113, no HEAD documental `2726a19916f4397bbb233eb6658bee588ee15968`, terminou com 16/16 jobs aprovados. A revisão da PR #114 também concluiu com sucesso; nela, os jobs exclusivos de push (benchmark completo e instalação CUDA) foram pulados intencionalmente, pois já são executados no workflow push. A PR #1 foi integrada por squash no commit `992cb874274e73d0264994e39926113f1461236f`. A branch `phase-1/architecture` já foi criada a partir desse commit e está pronta para o planejamento/execução da Fase 1; nenhuma implementação da Fase 1 foi iniciada.

## 2. Situação do repositório

| Item | Estado |
|---|---|
| Repositório | `anfalcir/legendar` |
| PR de execução | [#1 — Fase 0](https://github.com/anfalcir/legendar/pull/1), merged por squash |
| Branch de conclusão da Fase 0 | `phase-0/technical-inventory` |
| Branch de trabalho da Fase 1 | `phase-1/architecture`, criada do commit de integração |
| `main` | Atualizada e contém a entrega integral da Fase 0 |
| Fonte de dependências | `pyproject.toml` |
| Lock | `uv.lock` regenerado pela CI e integrado à `main`; invariantes, fontes e exports CPU/CUDA aprovados no workflow #113 |
| Coletor | `scripts/phase0_inventory.py` |
| POC de mídia | `scripts/phase0_media_poc.py` |
| POC de modelos | `scripts/phase0_model_poc.py` |
| Validador do lock | `scripts/phase0_validate_lock.py` |
| Documentação técnica | plano mestre, estado vivo, protocolo, matriz de dependências e handoff Fase 1 |
| CI | workflow `.github/workflows/phase0-quality.yml`; matriz determinística, validação do lock, instalação CPU/CUDA, prova de mídia e benchmark PT-BR/EN |

A PR #1 foi revisada e integrada. A branch `phase-1/architecture` já existe e deriva diretamente do commit de squash da `main`; continuar nela ao iniciar a Fase 1.

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
| 1 — Reestruturação arquitetural | **Pronta para iniciar** | Branch `phase-1/architecture` criada a partir do commit de integração; implementação ainda não iniciada |
| 2 — Interface profissional | Não iniciada | Workers simulados e máquina de estados da GUI |
| 3 — Entrada e preparação de mídia | Não iniciada | Homologar formatos, streams, offsets e temporários |
| 4 — Reconhecimento Whisper | Não iniciada | Comparação PT-BR/EN e desempenho no computador-alvo |
| 5 — Alinhamento temporal | Não iniciada | Referência humana, mediana/P95, cobertura e anomalias |
| 6 — Tradução, segmentação e SRT | Não iniciada | Escolha de fornecedor antes da implementação da tradução |
| 7 — Integração ponta a ponta | Não iniciada | Conectar GUI ao pipeline real |
| 8 — Testes e homologação | Não iniciada | Homologação nos ambientes declarados suportados |
| 9 — Documentação e finalização | Em preparação | Documentação inicial e handoff registrados |

## 8. Pendências encaminhadas às fases corretas

1. **Fase 1 — pronta para execução:** ler integralmente o handoff, inspecionar a baseline e elaborar o plano de implementação antes de refatorar. A branch `phase-1/architecture` já está criada; nenhuma alteração funcional foi iniciada.
2. **Antes da Fase 3:** repetir o inventário atualizado no computador-alvo e instalar/verificar FFmpeg/ffprobe.
3. **Fase 4:** comparar modelos Whisper com corpus PT-BR/EN representativo; registrar WER/CER, duração, memória e RTF no hardware-alvo.
4. **Fase 5:** anotar manualmente início/fim de palavras e medir erro mediano/P95, cobertura e falhas; não homologar sincronização só por WER.
5. **Antes da Fase 6:** escolher provedor e aprovar custo, privacidade, retenção, limites e comportamento de falha.
6. **Fase 8:** testar aplicação e fluxos completos nos sistemas/backends declarados como suportados.

As pendências acima são gates de produto alocados às fases responsáveis; elas não reabrem a Fase 0.

## 9. Próxima ação objetiva

Iniciar a Fase 1 na branch já preparada `phase-1/architecture`: ler o [HANDOFF_FASE_1.md](HANDOFF_FASE_1.md), inspecionar o código legado, registrar o plano detalhado de implementação e os primeiros critérios de aceite antes de alterar a arquitetura.

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
