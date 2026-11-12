# Legendar

Aplicação desktop para transcrever áudio, alinhar a fala à linha do tempo da mídia e produzir legendas SRT, com tradução local opcional entre português brasileiro e inglês.

- **Estado:** Fases 1–6 da frente de qualidade/desempenho implementadas e integradas à `main`; a Fase 6 oferece NLLB e Gemini como motores opcionais, com configuração local do Gemini em Preferências.
- **Base técnica:** Python 3.10–3.13, PySide6, FFmpeg, Whisper, WhisperX e NLLB-200.
- **Qualidade:** o arquivo pode ser estruturalmente válido sem estar editorialmente aprovado. O plano atual trata essa lacuna explicitamente.
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

## Documentação viva

O índice técnico e operacional está em [docs/README.md](docs/README.md). Os documentos mantidos na raiz de `docs/` são os documentos vivos:

- [Estado atual](docs/ESTADO_ATUAL.md)
- [Plano de correção, qualidade e desempenho](docs/PLANO_CORRECAO_MELHORIA.md)
- [Arquitetura](docs/ARQUITETURA.md)
- [Operação](docs/OPERACAO.md)
- [Instalação](docs/INSTALACAO.md)
- [Homologação](docs/HOMOLOGACAO.md)
- [Decisões](docs/DECISOES.md)
- [Matriz de dependências](docs/MATRIZ_DEPENDENCIAS.md)

Planos, handoffs e relatórios encerrados das Fases 0–10 foram preservados em [docs/archive/README.md](docs/archive/README.md). O arquivamento organiza o histórico; não apaga evidências.

## Princípios do produto

- Fidelidade ao que foi falado e preservação de todo o conteúdo reconhecido.
- Timestamps ancorados em evidência temporal; nenhum horário inventado para mascarar falha de alinhamento.
- Legibilidade como critério de qualidade, não apenas validade sintática do SRT.
- Tradução local e privada, com avaliação contextual e terminológica.
- Desempenho otimizado somente quando testes pareados demonstrarem qualidade equivalente.
- Erros, conteúdo não alinhado e resultados que precisam de revisão devem ser explícitos.

## Plano atual

A auditoria e as Fases 1–6 já instrumentaram o pipeline, corrigiram integridade/segmentação, integraram o gate editorial, disponibilizaram benchmark pareado de ASR e consolidaram dois motores de tradução opcionais. O baseline operacional da mídia de 37min10s é aproximadamente 23min21s nas execuções quentes, com NLLB consumindo cerca de 14 minutos. A Fase 6 foi concluída com Gemini opt-in, configuração local da chave em Preferências e NLLB mantido como padrão.

O plano completo, com critérios de aceite, fases, benchmarks e estratégia de aceleração de CPU/GPU, está em [PLANO_CORRECAO_MELHORIA.md](docs/PLANO_CORRECAO_MELHORIA.md).
