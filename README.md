# Legendar

Aplicação desktop para transcrever áudio, alinhar a fala ao tempo da mídia e produzir legendas SRT, com tradução local opcional para inglês ou português brasileiro.

- **Estado:** Fases 0–9 concluídas, validadas e integradas à `main`. O que resta é a homologação do usuário com mídia real e hardware próprio.
- **Suíte:** 452 testes aprovados e 86% de cobertura no ambiente com FFmpeg (442 aprovados e 10 skips explícitos sem FFmpeg).
- **Licença:** MIT, em [LICENSE](LICENSE).

## O que a aplicação faz

1. Recebe um arquivo local (áudio ou vídeo) ou uma URL do YouTube.
2. Inspeciona a mídia com ffprobe, permite escolher a faixa de áudio e normaliza para WAV PCM mono 16 kHz preservando o offset temporal.
3. Transcreve com Whisper no idioma de origem.
4. Alinha por palavra com WhisperX e sinaliza palavras sem âncora confiável.
5. Segmenta em cues de até duas linhas de 42 caracteres, respeitando pausas e tempo de leitura.
6. Traduz por cue com NLLB-200 distilled 600M **local**, preservando os tempos originais.
7. Valida o trilho, reparseia o arquivo e publica o SRT por troca atômica.
8. Mostra etapa, progresso honesto, log recolhível e permite cancelamento cooperativo em ponto seguro.

## Requisitos

- Python 3.10–3.13 e [uv](https://docs.astral.sh/uv/)
- FFmpeg e ffprobe no `PATH`
- Para YouTube: `yt-dlp-ejs` (já instalado pelo perfil) e Deno ≥ 2.3 ou Node ≥ 22
- Espaço em disco para os modelos (≈ 6 GB)

## Instalação e execução

```bash
git clone https://github.com/anfalcir/legendar.git
cd legendar

uv lock --check
uv sync --locked --group dev --group phase0 --extra runtime-cpu
# GPU NVIDIA com CUDA 12.8: use --extra runtime-cu128 no lugar de runtime-cpu

PYTHONPATH=src uv run --locked --no-sync python -m legendar
```

Detalhes por sistema operacional, perfis de hardware, variáveis de ambiente e
desinstalação estão em [docs/INSTALACAO.md](docs/INSTALACAO.md).


## Testes

```bash
# Suíte determinística (sem rede, sem modelos)
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q

# Somente end-to-end (matriz de idiomas, falhas e mídia real)
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q -m e2e

# Qualidade estática e documentação
uv run --locked --no-sync ruff check src/legendar tests scripts
uv run --locked --no-sync ruff format --check src/legendar tests
uv run --locked --no-sync python scripts/check_doc_links.py
```

A CI da Fase 8 instala FFmpeg e roda a matriz Python 3.10–3.13 com gate de
cobertura de 85% (`.github/workflows/phase8-quality.yml`).

## Documentação

**Porta de entrada técnica**

- [Arquitetura](docs/ARQUITETURA.md) — camadas, módulos, portas, estados, threads e publicação.
- [Operação](docs/OPERACAO.md) — uso da janela, estados, cancelamento, arquivos, erros e diagnóstico.
- [Instalação](docs/INSTALACAO.md) — requisitos, perfis, execução, verificação e desinstalação.
- [Homologação](docs/HOMOLOGACAO.md) — roteiro passo a passo para validar com mídia real e hardware próprio.
- [Decisões](docs/DECISOES.md) — decisões consolidadas e decisões abertas.
- [Plano mestre de remodelagem](docs/PLANO_REMODELAGEM.md) — visão do produto, requisitos e critérios de aceite.
- [Estado atual](docs/ESTADO_ATUAL.md) — estado real, evidências, riscos e pendências.
- [Matriz de dependências](docs/MATRIZ_DEPENDENCIAS.md) — governança, faixas de versão, perfis e compatibilidade.
- [Baseline legada](docs/LEGACY_BASELINE.md) — contratos caracterizados e política da aplicação anterior.

**Planos e handoffs por fase**

| Fase | Plano | Handoff |
|---|---|---|
| 0 | [Protocolo](docs/FASE_0_PROTOCOLO.md) | — |
| 1 | [Plano](docs/FASE_1_PLANO.md) | [Handoff](docs/HANDOFF_FASE_1.md) |
| 2 | [Plano](docs/FASE_2_PLANO.md) | [Handoff](docs/HANDOFF_FASE_2.md) |
| 3 | [Plano](docs/FASE_3_PLANO.md) | [Handoff](docs/HANDOFF_FASE_3.md) |
| 4 | [Plano](docs/FASE_4_PLANO.md) | [Handoff](docs/HANDOFF_FASE_4.md) |
| 5 | [Plano](docs/FASE_5_PLANO.md) | [Handoff](docs/HANDOFF_FASE_5.md) |
| 6 | [Plano](docs/FASE_6_PLANO.md) | [Handoff](docs/HANDOFF_FASE_6.md) |
| 7 | [Plano](docs/FASE_7_PLANO.md) | [Handoff](docs/HANDOFF_FASE_7.md) |
| 8 | [Plano](docs/FASE_8_PLANO.md) | [Handoff](docs/HANDOFF_FASE_8.md) e [relatório](docs/RELATORIO_FASE_8.md) |
| 9 | [Plano](docs/FASE_9_PLANO.md) | [Handoff final](docs/HANDOFF_FASE_9.md) |

## Limites conhecidos

- A precisão temporal e a qualidade tradutória dependem de homologação humana com corpus autorizado e o computador-alvo.
- O cancelamento é cooperativo: uma inferência em andamento termina antes de o job encerrar.
- A publicação (`PUBLISHING`) é ponto de não retorno e não aceita cancelamento.
- Empacotamento distribuível (PyInstaller) ainda não é um fluxo homologado.
- Sistemas operacionais oficialmente suportados serão declarados após a homologação integrada; a CI cobre Ubuntu com Python 3.10–3.13.
- O repositório preserva a aplicação anterior (`main.py`, `core/`, `gui/`) como baseline caracterizada.

## Licença

MIT. Consulte [LICENSE](LICENSE).
