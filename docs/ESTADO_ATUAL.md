# Estado atual do Legendar

- **Última atualização:** 10/11/2026
- **Repositório:** anfalcir/legendar
- **Branch de referência de implementação:** `phase-0/technical-inventory`
- **Branch padrão:** `main`
- **Fase:** Fase 0 — Definições e prova técnica, em fechamento técnico
- **Próxima fase:** Fase 1 — Reestruturação arquitetural
- **PR da Fase 0:** [#1](https://github.com/anfalcir/legendar/pull/1), aberta e ainda Draft
- **Documento de handoff:** [HANDOFF_FASE_1.md](HANDOFF_FASE_1.md)

> A branch da Fase 0 está isolada da `main`. Não iniciar a Fase 1 na branch padrão até revisar e integrar a PR #1. Não interpretar uma CI enfileirada como aprovação. O repositório continua sendo a fonte de verdade dos requisitos e das dependências.

---

## 1. Resumo executivo

A remodelagem funcional do Legendar ainda não começou. A baseline continua sendo uma pequena aplicação Python/PySide6 com fluxos antigos de transcrição via Whisper/yt-dlp e saída textual; ela não implementa ainda o pipeline SRT final, alinhamento robusto, tradução ou cancelamento arquitetural completo.

A Fase 0 estabeleceu e documentou a direção técnica: governança de dependências, perfis de runtime, coletor de ambiente, prova sintética de mídia/offset, script de POC PT-BR/EN e contrato arquitetural para a próxima fase. A documentação de passagem para a IA da IDE está em `docs/HANDOFF_FASE_1.md`.

**Estado de fechamento:** os entregáveis e decisões foram preparados na branch. A validação automatizada final do manifesto/lock e a execução do smoke benchmark de modelo estão em workflows GitHub Actions enfileirados. O lock existente deve ser regenerado após a última alteração do manifesto, porque a resolução anterior continha WhisperX 3.8.7rc1 e o grupo de avaliação antigo que dependia de `datasets` 5.2.0. Até essa regeneração e aprovação, não tratar `uv sync --locked` como validado no HEAD atual.

## 2. Situação do repositório

| Item | Estado |
|---|---|
| Repositório | `anfalcir/legendar` |
| PR de execução | [#1 — Fase 0](https://github.com/anfalcir/legendar/pull/1) |
| Branch de execução | `phase-0/technical-inventory` |
| `main` | Mantida sem as alterações desta branch; ainda não integrada |
| Fonte de dependências | `pyproject.toml` |
| Lock | `uv.lock` versionado, mas a revisão mais recente ainda depende da regeneração pela CI para ficar coerente com o manifesto final |
| Coletor | `scripts/phase0_inventory.py` |
| POC de mídia | `scripts/phase0_media_poc.py` |
| POC de modelos | `scripts/phase0_model_poc.py` |
| Validador do lock | `scripts/phase0_validate_lock.py` |
| Documentação técnica | plano mestre, estado vivo, protocolo, matriz de dependências e handoff Fase 1 |
| CI | workflow `.github/workflows/phase0-quality.yml`; matriz determinística, validação do lock, instalação CPU/CUDA, prova de mídia e benchmark PT-BR/EN |

O PR #1 deve ser revisado e integrado antes de criar `phase-1/architecture` a partir da `main` atualizada. Não mesclar automaticamente.

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

| Verificação | Evidência atual | Interpretação |
|---|---|---|
| Coletor de ambiente | 12 combinações Python 3.10–3.13 × Linux/Windows/macOS passaram em execução anterior | Valida o coletor, não a aplicação completa |
| Prova sintética FFmpeg/ffprobe | Workflow #65 e PR #67 passaram com teste de normalização e offset não-zero | Contrato sintético de áudio/timeline validado |
| Lockfile histórico | Resolução anterior gerou lock, mas revelou WhisperX 3.8.7rc1 e conflito do grupo `datasets` 5.2.0 | Não usar esse lock como evidência do manifesto final |
| Manifesto corrigido | WhisperX restringido a 3.8.6 estável; grupo de avaliação usa huggingface-hub compatível com WhisperX e remove datasets | Corrige as incompatibilidades identificadas; precisa regenerar o lock |
| Validador do lock | `scripts/phase0_validate_lock.py` verifica WhisperX estável, yt-dlp-ejs, fontes de Torch e conflito CPU/CUDA | Pronto para CI; execução final ainda pendente |
| Exportação CPU/CUDA | CI agora verifica ausência de pacotes NVIDIA no perfil CPU e presença no perfil CUDA | Execução final ainda pendente |
| Instalação CPU e WhisperX PT-BR/EN | Job instala runtime CPU e executa script FLEURS tiny/int8 | A execução final do job está enfileirada; não há resultado publicado no momento deste registro |
| Instalação/import CUDA | Job instala perfil cu128 e importa Torch/torchaudio/torchvision sem exigir GPU física | A execução final do job está enfileirada |
| Inventário atualizado no computador-alvo | Pendente | Deve ocorrer antes de homologação de mídia/modelos |
| Precisão temporal contra timestamps humanos | Pendente | Gate da Fase 5 |
| Tradução com fornecedor/custo/privacidade | Decidido adiar escolha de provedor até antes da Fase 6 | Não bloqueia arquitetura |

A POC FLEURS usa fala lida, corpus público CC-BY-4.0, dois idiomas e amostras pequenas. WER mede fidelidade lexical, não erro de timestamps. A medição definitiva precisa de amostras representativas e palavras anotadas manualmente.

## 7. Status das fases

| Fase | Status | Observação |
|---|---|---|
| 0 — Definições e prova técnica | **Em fechamento técnico** | Decisões, scripts, testes e handoff preparados; sincronização final do lock e jobs de instalação/POC ainda aguardam execução CI |
| 1 — Reestruturação arquitetural | Não iniciada | Handoff pronto; iniciar após integração da PR #1 e conclusão dos checks finais |
| 2 — Interface profissional | Não iniciada | Workers simulados e máquina de estados da GUI |
| 3 — Entrada e preparação de mídia | Não iniciada | Homologar formatos, streams, offsets e temporários |
| 4 — Reconhecimento Whisper | Não iniciada | Comparação PT-BR/EN e desempenho no computador-alvo |
| 5 — Alinhamento temporal | Não iniciada | Referência humana, mediana/P95, cobertura e anomalias |
| 6 — Tradução, segmentação e SRT | Não iniciada | Escolha de fornecedor antes da implementação da tradução |
| 7 — Integração ponta a ponta | Não iniciada | Conectar GUI ao pipeline real |
| 8 — Testes e homologação | Não iniciada | Homologação nos ambientes declarados suportados |
| 9 — Documentação e finalização | Em preparação | Documentação inicial e handoff registrados |

## 8. Pendências encaminhadas às fases corretas

1. **Fechamento operacional da Fase 0:** aguardar workflow final atualizar `uv.lock`, confirmar `scripts/phase0_validate_lock.py`, exportação CPU/CUDA, instalação/importação dos dois perfis, prova FFmpeg e relatório da POC FLEURS. Se a fila do GitHub continuar sem execução, rodar `uv lock` com a versão de uv fixada no workflow, revisar e commitar o lock antes de instalar.
2. **Antes da Fase 3:** repetir inventário atualizado no computador-alvo e instalar/verificar FFmpeg/ffprobe.
3. **Fase 4:** comparar modelos Whisper com corpus PT-BR/EN representativo; registrar WER/CER, duração, memória e RTF.
4. **Fase 5:** anotar manualmente início/fim de palavras e medir erro mediano/P95, cobertura e falhas; não homologar sincronização só por WER.
5. **Antes da Fase 6:** escolher provedor e aprovar custo, privacidade, retenção, limites e comportamento de falha.
6. **Fase 8:** testar aplicações e fluxos completos nos sistemas/backends declarados como suportados.

## 9. Próxima ação objetiva

Concluir a CI final e regeneração do lock na branch `phase-0/technical-inventory`; então revisar e integrar a PR #1. A IA da IDE deverá iniciar a Fase 1 a partir da `main` atualizada, criando `phase-1/architecture`, e seguir [HANDOFF_FASE_1.md](HANDOFF_FASE_1.md).

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
