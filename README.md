# Legendar

Aplicação desktop para transcrever áudio e vídeo, gerar legendas SRT e traduzir arquivos SRT existentes entre inglês e português brasileiro, preservando a estrutura temporal.

**Estado em 13/11/2026:** o TranslateGemma 4B Q4_K_M está integrado e funcionalmente homologado como único motor local. A tradução e a composição das frases melhoraram e o resultado foi considerado suficiente para a relevância e a expectativa atuais do projeto. A qualidade ainda não é ótima; há espaço para melhorias futuras. O desenvolvimento está pausado neste ponto, sem tarefas ou prazo de retomada definidos.

## Recursos

- Entrada por arquivo de mídia local, URL do YouTube ou arquivo SRT.
- Mídia: inspeção, preparação de áudio, transcrição com OpenAI Whisper (padrão) ou faster-whisper selecionável, alinhamento WhisperX e segmentação em cues.
- SRT como origem: leitura, tradução opcional, validação e publicação direta, sem executar FFmpeg, Whisper ou WhisperX.
- Tradução local com TranslateGemma 4B IT Q4_K_M via runtime llama.cpp gerenciado pelo próprio aplicativo.
- Gemini Developer API como opção remota explícita; o texto das cues é enviado ao serviço quando esse backend é selecionado.
- Publicação SRT por gravação atômica, mantendo a origem protegida contra sobrescrita.
- Perfis de recursos, diagnóstico de dependências e preparação idempotente do runtime local.

## Estado da tradução

TranslateGemma é o único motor local. Gemini continua como alternativa remota opcional, sem fallback automático entre os motores. O antigo motor local e suas configurações/dependências específicas foram removidos do código mantido; configurações persistidas antigas são migradas para TranslateGemma. Pesos legados já baixados não são apagados automaticamente do disco.

A homologação funcional confirmou que o fluxo de tradução executa e que a qualidade percebida melhorou. Isso não representa aprovação editorial máxima nem uma avaliação quantitativa WER/CER. O resultado atual é aceito para o uso pretendido neste momento.

## Base técnica

- Python 3.10–3.13, PySide6 e arquitetura em camadas sob `src/legendar`.
- FFmpeg/ffprobe para mídia e Whisper/WhisperX para ASR/alinhamento.
- llama.cpp e pesos GGUF TranslateGemma preparados sob demanda, após consentimento.
- `pyproject.toml` e `uv.lock` são as fontes de verdade das dependências.
- Código sob licença MIT; modelos e pesos têm licenças independentes.

## Instalação e execução

Consulte [Instalação](docs/INSTALACAO.md). Para Linux Mint/Ubuntu x86_64, consulte também [Distribuição Linux](docs/DISTRIBUICAO_LINUX.md). A distribuição está preparada por bundle de usuário, mas ainda não há uma release estável publicada.

Execução a partir do código:

```bash
git clone https://github.com/anfalcir/legendar.git
cd legendar
uv lock --check
uv sync --locked --group dev --group phase0 --extra runtime-cpu
PYTHONPATH=src uv run --locked --no-sync python -m legendar
```

## Testes e qualidade

```bash
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q -m e2e
uv run --locked --no-sync ruff check src/legendar tests scripts
uv run --locked --no-sync ruff format --check src/legendar tests
uv run --locked --no-sync python scripts/check_doc_links.py
```

A CI principal valida Python 3.10–3.13, cobertura, FFmpeg, Qt offscreen, E2E, lint e documentação. Consulte [GitHub Actions](https://github.com/anfalcir/legendar/actions).

## Documentação

A documentação ativa está indexada em [docs/README.md](docs/README.md). Planos de execução encerrados e registros substituídos ficam em [docs/archive/](docs/archive/README.md). O documento de estado atual e o registro de homologação são as fontes de verdade para a situação do produto.
