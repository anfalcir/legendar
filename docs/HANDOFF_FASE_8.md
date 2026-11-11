# Handoff técnico — Fase 8: testes e homologação

- **Status:** implementação concluída na branch `phase-8/validation`, integrada à `main` por squash.
- **Plano operacional:** [FASE_8_PLANO.md](FASE_8_PLANO.md)
- **Relatório de evidências:** [RELATORIO_FASE_8.md](RELATORIO_FASE_8.md)
- **Fronteira:** provar o fluxo completo por testes e separar explicitamente o que exige homologação humana.
- **Fora de escopo:** documentação final e revisão de instalação (Fase 9).

## 1. O que foi acrescentado

| Arquivo | Papel |
|---|---|
| `tests/e2e/support.py` | Fixtures de referência: transcrição temporizada, alinhamento e pipeline real com portas controladas |
| `tests/e2e/test_language_matrix.py` | Matriz PT→PT, PT→EN, EN→PT, EN→EN e divergência de idioma sem tradução |
| `tests/e2e/test_failure_modes.py` | Falhas por etapa, cancelamento e preservação do SRT anterior |
| `tests/e2e/test_real_media.py` | Fluxo com FFmpeg/ffprobe reais em seis formatos, mídia corrompida e vídeo sem áudio |
| `scripts/check_doc_links.py` | Verificador de links relativos da documentação |
| `tests/test_documentation.py` | Links, descoberta de Markdown e presença dos documentos obrigatórios |
| `.github/workflows/phase8-quality.yml` | Matriz Python 3.10–3.13 com FFmpeg, gate de cobertura, suíte `e2e` isolada e consistência da documentação |

Também foi registrado o marcador `e2e` em `pyproject.toml` e adicionados ao
`.gitignore` os artefatos locais de cobertura (`/.coverage`, `coverage.xml`,
`htmlcov/`) e `nohup.out`.

## 2. Contratos de teste que não devem ser enfraquecidos

1. Todo caso E2E usa o **controlador** e o **pipeline reais**, incluindo
   `JobController`, `SerialPipeline`, validação do trilho e `SrtPublisher`.
2. As portas externas substituídas são apenas as que exigem modelo, rede ou
   binário: inspetor, preparador, transcritor, alinhador e tradutor.
3. Cada caso verifica o evento terminal: exatamente um `JobCompleted`,
   `JobFailed` ou `JobCancelled` por job.
4. Nenhum teste de falha aceita arquivo publicado: destino inexistente ou
   inalterado.
5. Tempos publicados precisam estar dentro da duração da mídia, sem
   sobreposição e com numeração contínua a partir de 1.
6. O layout sem tradução respeita duas linhas de 42 caracteres; com tradução, o
   excesso é permitido e sinalizado, nunca truncado.
7. Testes de mídia real devem ser **pulados**, não falhar, quando FFmpeg e
   ffprobe não existem no `PATH`.

## 3. Como executar localmente

```bash
# Sem FFmpeg no PATH: integração de mídia e casos reais são pulados
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q

# Com ferramentas estáticas baixadas em ./ffmpeg/bin (ignorado pelo Git)
PATH="$PWD/ffmpeg/bin:$PATH" QT_QPA_PLATFORM=offscreen \
  uv run --locked --no-sync pytest -q --cov=legendar --cov-report=term

# Apenas a matriz end-to-end
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q -m e2e

# Documentação
uv run --locked --no-sync python scripts/check_doc_links.py
uv run --locked --no-sync pytest -q tests/test_documentation.py
```

Resultado de referência no ambiente de desenvolvimento (Python 3.12.3, FFmpeg
7.0.2 static): 443 testes aprovados, 0 skips, cobertura 86%.

## 4. CI da fase

`phase8-quality.yml` roda em pushes de `phase-8/**` e `phase-9/**` e em PRs para
`main` que toquem código, testes, scripts, dependências, documentação ou o
próprio workflow. Dois jobs:

- **full-suite**: instala FFmpeg e bibliotecas Qt, valida o lock, sincroniza
  dependências, compila `src`, `tests` e `scripts`, roda a suíte completa com
  `--cov-fail-under=85`, roda `-m e2e` isolada, Ruff check e Ruff format check.
- **docs-consistency**: verifica links de Markdown e os documentos obrigatórios.

Os gates herdados (`phase0`, `phase1`, `phase3`, `phase4`, `phase5`,
`phase6-quality.yml`) continuam válidos e independentes.

## 5. Decisões congeladas

1. Ferramentas externas na CI vêm do gerenciador de pacotes do runner, não de
   um binário versionado.
2. Fixtures de mídia são sintéticas e geradas em tempo de execução; nenhum
   arquivo de mídia pessoal entra no repositório.
3. Cobertura mínima de 85% é gate de CI, não um objetivo em si: os critérios de
   aceite continuam sendo comportamentais.
4. O verificador de links é determinístico e não acessa a internet.
5. Pendências humanas ficam no relatório, nunca marcadas como concluídas.

## 6. Limites conhecidos

- Modelos reais (Whisper, WhisperX, NLLB) não são baixados na suíte; eles têm
  smoke tests próprios em workflows de fase.
- O fluxo YouTube ao vivo não é automatizado.
- Não há teste de arquivo com mais de uma hora nem medição de memória real.
- A matriz oficialmente suportada de sistemas operacionais segue pendente de
  homologação do aplicativo integrado.

## 7. Próxima fronteira

A Fase 9 deve consolidar a documentação: arquitetura, operação, instalação,
decisões, revisão final do README, política do `requirements.txt` legado e
registro do estado final do projeto com as evidências das Fases 6–9.
