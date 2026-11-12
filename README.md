# Legendar

Aplicação desktop para transcrever áudio, alinhar a fala à linha do tempo da mídia e produzir legendas SRT, com tradução opcional entre português brasileiro e inglês.

- **Estado:** Fases 1–7 implementadas e integradas à `main`; Fase 8 em homologação. NLLB local e Gemini API permanecem como motores de tradução opcionais, com chave Gemini configurada localmente em Preferências.
- **Base técnica:** Python 3.10–3.13, PySide6, FFmpeg, Whisper, WhisperX e NLLB-200.
- **Qualidade:** validade estrutural não equivale a aprovação editorial ou audiovisual; a Fase 8 registra essa distinção.
- **Licença do código:** MIT. As licenças dos modelos e pesos são independentes e devem ser observadas.

## O que a aplicação faz

1. Recebe mídia local ou URL do YouTube.
2. Inspeciona streams e normaliza o áudio para WAV PCM mono 16 kHz, preservando o offset da mídia.
3. Transcreve a fala no idioma de origem com OpenAI Whisper (padrão) ou faster-whisper/CTranslate2 (seleção explícita, ainda em homologação operacional).
4. Alinha palavras com WhisperX.
5. Segmenta o texto em cues, valida e publica SRT por troca atômica.
6. Opcionalmente traduz as cues com NLLB-200 local ou Gemini Developer API; o motor e a chave Gemini são configurados em Preferências.

## Requisitos

- Python 3.10–3.13 e [uv](https://docs.astral.sh/uv/)
- FFmpeg e ffprobe no `PATH`
- Para YouTube: `yt-dlp-ejs` e Deno ≥ 2.3 ou Node ≥ 22
- Espaço em disco para os modelos; consulte [Instalação](docs/INSTALACAO.md)

## Instalação e execução

```bash
git clone https://github.com/anfalcir/legendar.git
cd legendar

uv lock --check
uv sync --locked --group dev --group phase0 --extra runtime-cpu
# Alternativa em Linux/Windows com GPU NVIDIA compatível:
# uv sync --locked --group dev --group phase0 --extra runtime-cu128

PYTHONPATH=src uv run --locked --no-sync python -m legendar
```

## Testes e qualidade estática

```bash
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q -m e2e
uv run --locked --no-sync ruff check src/legendar tests scripts
uv run --locked --no-sync ruff format --check src/legendar tests
uv run --locked --no-sync python scripts/check_doc_links.py
```

A CI da Fase 8 executa a matriz Python 3.10–3.13 com FFmpeg, Qt offscreen, E2E, cobertura e consistência documental. Consulte [GitHub Actions](https://github.com/anfalcir/legendar/actions).

## Documentação

O índice técnico e operacional está em [docs/README.md](docs/README.md). Somente documentos vivos permanecem na raiz de `docs/`; planos e relatórios encerrados estão em [docs/archive/README.md](docs/archive/README.md).

Documentos vivos:
- [Estado atual](docs/ESTADO_ATUAL.md)
- [Plano mestre de correção, qualidade e desempenho](docs/PLANO_CORRECAO_MELHORIA.md)
- [Arquitetura](docs/ARQUITETURA.md)
- [Operação](docs/OPERACAO.md)
- [Instalação](docs/INSTALACAO.md)
- [Homologação](docs/HOMOLOGACAO.md)
- [Decisões](docs/DECISOES.md)
- [Matriz de dependências](docs/MATRIZ_DEPENDENCIAS.md)

## Princípios do produto

- Fidelidade ao que foi falado e preservação de todo o conteúdo reconhecido.
- Timestamps ancorados em evidência temporal; nenhum horário inventado para mascarar falha de alinhamento.
- Legibilidade como critério de qualidade, não apenas validade sintática do SRT.
- Tradução local e privada como opção padrão, com Gemini externo opt-in.
- Desempenho otimizado somente quando testes pareados demonstrarem qualidade equivalente.
- Erros, conteúdo não alinhado e resultados que precisam de revisão devem ser explícitos.

## Plano atual

As Fases 1–7 estão implementadas e integradas. A Fase 8 adicionou o avaliador determinístico de SRT e permanece em andamento até a homologação audiovisual no hardware-alvo, incluindo desempenho cold/warm, revisão em player, sincronização, PT-BR e fragmentação. O plano e os critérios estão em [PLANO_CORRECAO_MELHORIA.md](docs/PLANO_CORRECAO_MELHORIA.md).
