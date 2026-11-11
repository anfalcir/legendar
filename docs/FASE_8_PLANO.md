# Plano operacional — Fase 8: testes e homologação

- **Status:** implementada e validada na branch `phase-8/validation`, a ser integrada à `main` por squash.
- **Fronteira:** provar por testes automatizados que o fluxo completo funciona, documentar o que só pode ser homologado com mídia, hardware e julgamento humano, e publicar o relatório da fase.
- **Dependências:** Fases 0–7 integradas à `main`.
- **Relatório de evidências:** [RELATORIO_FASE_8.md](RELATORIO_FASE_8.md).
- **Documento de transferência:** [HANDOFF_FASE_8.md](HANDOFF_FASE_8.md).

---

## 1. Objetivos e escopo

### 1.1. Dentro do escopo

1. Consolidar a matriz de testes: unitários, integração, GUI e end-to-end.
2. Cobrir os quatro pares de idioma do produto (PT→PT, PT→EN, EN→PT, EN→EN) no caminho real de aplicação.
3. Exercitar mídia real com FFmpeg/ffprobe para WAV, MP3, M4A, MKV, MP4 e WebM, além de mídia corrompida e sem áudio.
4. Cobrir modos de falha por etapa e cancelamento em pontos seguros, verificando que nenhum SRT inválido ou parcial é publicado.
5. Verificar que o SRT publicado é reparseável por parser independente, com numeração, ordem e tempos válidos.
6. Estabelecer gate de cobertura e gate de documentação (links relativos) na CI.
7. Produzir o relatório da fase com evidências, riscos e pendências humanas.

### 1.2. Fora do escopo

- Baixar modelos grandes na CI: Whisper, WhisperX e NLLB reais são smoke tests de fase, não da suíte determinística.
- Homologar qualidade tradutória, precisão temporal e leitura em corpus de pregações: depende de julgamento humano e do computador-alvo.
- Testar YouTube ao vivo de forma automatizada: depende de rede, de conteúdo disponível e dos termos da plataforma.
- Empacotamento e distribuição (PyInstaller) como produto final.

## 2. Estratégia de teste

| Camada | Diretório | Isolamento | O que prova |
|---|---|---|---|
| Unitário | `tests/unit` | doubles em memória | invariantes de domínio, pipeline, adaptadores e view model |
| Integração | `tests/integration` | sistema de arquivos real, FFmpeg quando disponível | publicação atômica, roundtrip SRT, workspace, mídia real |
| GUI | `tests/gui` | Qt offscreen + pipeline com doubles | fluxo da janela, confirmações, cancelamento, log, encerramento |
| End-to-end | `tests/e2e` | controlador + pipeline + publicador reais | matriz de idiomas, modos de falha, mídia real |
| Governança | `tests/test_architecture.py`, `tests/test_documentation.py` | importação e leitura de arquivos | camadas, isolamento de dependências e coerência da documentação |

Marcadores registrados em `pyproject.toml`: `integration`, `gui` e `e2e`.
A CI executa a suíte completa e, em seguida, a suíte `-m e2e` isolada.

## 3. Matriz end-to-end determinística

| Caso | Entrada | Resultado esperado |
|---|---|---|
| PT → PT | fala PT, sem tradução | SRT PT, palavras originais preservadas, duas linhas de 42 caracteres |
| PT → EN | fala PT, tradução marcada | SRT EN, 1 texto por cue, tempos idênticos ao original |
| EN → PT | fala EN, tradução marcada | SRT PT, tempos idênticos ao original |
| EN → EN | fala EN, sem tradução | SRT EN, sem chamada ao tradutor |
| Idioma final divergente sem tradução | fala EN, destino PT | `JobFailed` `UNSUPPORTED_LANGUAGE`, nada publicado |

Cada caso verifica: evento terminal único, arquivo publicado no destino exato,
ausência de `.partial`, reparse do SRT, numeração contínua, ausência de
sobreposição, limites de linha e coerência de idioma.

## 4. Matriz de falhas e cancelamento

| Cenário | Categoria esperada | Garantia |
|---|---|---|
| Mídia sem áudio | `INVALID_INPUT` | nada publicado |
| Transcrição vazia | `MODEL_FAILED` | nada publicado |
| Alinhamento sem palavras | `ALIGNMENT_INSUFFICIENT` | nada publicado |
| Tradutor devolve idioma errado | `TRANSLATION_FAILED` | nada publicado |
| Falha de escrita | `WRITE_FAILED` | SRT anterior intacto |
| Cancelamento antes de iniciar | `CANCELLED` | destino intocado |
| Cancelamento entre etapas | `CANCELLED` | nenhum `.partial` deixado |
| Erro inesperado | `UNEXPECTED` | mensagem genérica, detalhe técnico no evento |
| Segundo job falhando | categoria do novo erro | arquivo publicado anteriormente intacto |

## 5. Mídia real

`tests/e2e/test_real_media.py` e `tests/integration/test_ffmpeg_media_ingestion.py`
geram fixtures sintéticas com FFmpeg e exercitam inspeção, seleção de faixa,
offset de stream, normalização para WAV PCM mono 16 kHz e publicação.

Quando FFmpeg/ffprobe não estão instalados, esses testes são **pulados**
explicitamente; a CI da fase instala as ferramentas para executá-los sempre.

## 6. Critérios de aceitação

1. Suíte completa verde em Python 3.10–3.13, com cobertura mínima de 85%.
2. Nenhum teste depende de rede, de modelos baixados ou de credenciais.
3. Toda falha de etapa produz evento terminal único com categoria estável.
4. Nenhum caminho de falha publica SRT parcial, inválido ou vazio.
5. Mídia real homologada nos formatos exercitados pela suíte.
6. Documentação sem links relativos quebrados.
7. Relatório da fase publicado com evidências e pendências humanas explícitas.

## 7. Comandos de verificação

```bash
uv lock --check
uv sync --locked --group dev --group phase0
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q \
  --cov=legendar --cov-report=term-missing --cov-fail-under=85
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q -m e2e
uv run --locked --no-sync ruff check src/legendar tests scripts
uv run --locked --no-sync ruff format --check src/legendar tests
uv run --locked --no-sync python scripts/check_doc_links.py
```

Em ambientes sem FFmpeg no `PATH`, prefixe os comandos de teste com o diretório
das ferramentas estáticas:

```bash
PATH="$PWD/ffmpeg/bin:$PATH" QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q
```
