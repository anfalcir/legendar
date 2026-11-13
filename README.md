# Legendar

Aplicação desktop para transcrever áudio/vídeo, produzir legendas SRT e traduzir diretamente arquivos SRT existentes entre português brasileiro e inglês, preservando os timestamps.

- **Estado:** TranslateGemma foi integrado à `main` pela PR #36. A Fase 8.1 segue em homologação real: faltam smoke com pesos reais, validação no Linux Mint/Ryzen de referência e aprovação editorial PT-BR. NLLB permanece temporariamente como baseline selecionável; Gemini continua como backend remoto explícito.
- **Base técnica:** Python 3.10–3.13, PySide6, FFmpeg, Whisper, WhisperX e runtime local llama.cpp/TranslateGemma; NLLB permanece temporariamente no código como baseline.
- **Qualidade:** validade estrutural não equivale a aprovação editorial ou audiovisual; a Fase 8 registra essa distinção.
- **Licença do código:** MIT. As licenças dos modelos e pesos são independentes e devem ser observadas.

## O que a aplicação faz

1. Recebe mídia local, URL do YouTube ou um arquivo SRT existente para tradução direta.
2. Inspeciona streams e normaliza o áudio para WAV PCM mono 16 kHz, preservando o offset da mídia.
3. Para mídia, transcreve a fala com OpenAI Whisper (padrão) ou faster-whisper/CTranslate2 (seleção explícita, ainda em homologação operacional).
4. Alinha palavras com WhisperX.
5. Segmenta o texto em cues, valida e publica SRT por troca atômica. No modo SRT, executa somente leitura/tradução/validação/publicação, sem processamento de áudio, Whisper ou WhisperX.
6. Opcionalmente traduz as cues com TranslateGemma local (runtime llama.cpp preparado sob demanda), NLLB como baseline temporária ou Gemini Developer API como rota remota; o backend é selecionado em Preferências.

## Requisitos

- Python 3.10–3.13 e [uv](https://docs.astral.sh/uv/)
- FFmpeg e ffprobe no `PATH`
- Para YouTube: `yt-dlp-ejs` e Deno ≥ 2.3 ou Node ≥ 22
- Espaço em disco para os modelos; consulte [Instalação](docs/INSTALACAO.md)

## Instalação e execução

**Linux Mint/Ubuntu x86_64 — pacote para usuário:** quando houver uma versão publicada em Releases, baixe `legendar-linux-x86_64-*.tar.gz`, extraia o arquivo e execute `./packaging/linux/install.sh` no terminal. O instalador prepara Python 3.12 e o ambiente isolado em `~/.local/share/legendar`, solicita autorização antes de instalar dependências do sistema e cria um atalho no menu. Não usa `sudo` para instalar o aplicativo nem altera o Python do sistema; `sudo` só é solicitado se FFmpeg/bibliotecas do sistema estiverem ausentes. O cache de modelos fica separado e é preservado ao atualizar/desinstalar. O uv/Python gerenciado fica isolado do toolchain do usuário; o desinstalador preserva o cache compartilhado do uv.

**Execução a partir do código (desenvolvimento):**

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
- [Distribuição Linux](docs/DISTRIBUICAO_LINUX.md)
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
