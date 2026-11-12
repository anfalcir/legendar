# Instalação do Legendar

- **Escopo:** instalar e executar a aplicação a partir do código versionado.
- **Fonte de verdade das dependências:** `pyproject.toml` e `uv.lock`; a matriz detalhada está em [MATRIZ_DEPENDENCIAS.md](MATRIZ_DEPENDENCIAS.md).
- **Operação:** [OPERACAO.md](OPERACAO.md).

## 1. Requisitos

| Item | Versão | Observação |
|---|---|---|
| Python | 3.10 a 3.13 | faixa declarada em `requires-python` |
| uv | 0.13.7 (versão usada na CI) | gerencia ambiente e lockfile |
| FFmpeg | qualquer versão estável recente | obrigatório no `PATH` |
| ffprobe | mesma origem do FFmpeg | obrigatório no `PATH` |
| Runtime JavaScript | Deno ≥ 2.3 ou Node ≥ 22 | necessário apenas para YouTube (`yt-dlp-ejs`) |
| Espaço em disco | ≈ 6 GB livres | pesos NLLB (≈2,4 GB) + Whisper/WhisperX |

Sistemas operacionais oficialmente homologados ainda não foram declarados: a CI
exercita Ubuntu com Python 3.10–3.13, e a validação em Windows/macOS depende da
homologação do usuário.

## 2. Instalar as ferramentas externas

**Ubuntu/Debian**

```bash
sudo apt-get update
sudo apt-get install --yes ffmpeg
```

**Windows**

```powershell
winget install Gyan.FFmpeg
```

**macOS**

```bash
brew install ffmpeg
```

Confirme:

```bash
ffmpeg -version | head -n 1
ffprobe -version | head -n 1
```

Para YouTube, instale também o runtime JavaScript:

```bash
# Linux/macOS
curl -fsSL https://deno.land/install.sh | sh
```

## 3. Instalar as dependências Python

```bash
git clone https://github.com/anfalcir/legendar.git
cd legendar

# 1) Conferir o lockfile versionado
uv lock --check

# 2) Ambiente de desenvolvimento e testes (sem modelos)
uv sync --locked --group dev --group phase0

# 3) Perfil de execução: escolha exatamente um
uv sync --locked --group dev --group phase0 --extra runtime-cpu
# ou, para GPU NVIDIA com CUDA 12.8:
uv sync --locked --group dev --group phase0 --extra runtime-cu128
```

Observações:

- `runtime-cpu` instala o stack PyTorch CPU, Whisper, WhisperX, NLLB (`transformers` + `sentencepiece`) e yt-dlp.
- `runtime-cu128` é exclusivo para Linux/Windows com CUDA 12.8; macOS usa os wheels PyPI do perfil CPU e pode expor MPS em runtime.
- Não combine os dois perfis: eles são declarados como conflitantes.
- O perfil ROCm não é declarado nesta versão (o PyTorch disponível no índice ROCm 7.2 é incompatível com a faixa exigida pelo WhisperX 3.8.6).

## 4. Executar

```bash
PYTHONPATH=src uv run --locked --no-sync python -m legendar
```

Windows (PowerShell):

```powershell
$env:PYTHONPATH = "src"
uv run --locked --no-sync python -m legendar
```

Na primeira execução, a aplicação cria `~/.cache/legendar/{models,logs,tmp}`.

## 5. Verificar a instalação

```bash
# Suíte determinística (sem rede, sem modelos)
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q

# Lint e formatação
uv run --locked --no-sync ruff check src/legendar tests scripts
uv run --locked --no-sync ruff format --check src/legendar tests

# Documentação
uv run --locked --no-sync python scripts/check_doc_links.py

# Mídia real (quando FFmpeg/ffprobe estão no PATH)
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q -m "integration or e2e"
```

Sem FFmpeg/ffprobe, os testes de mídia real são pulados explicitamente; os
demais continuam válidos.

## 6. Ajustes por ambiente

| Situação | Ação |
|---|---|
| Qt não abre no Linux | instale `libegl1`, `libgl1` e `libxkbcommon-x11-0` |
| Sessão sem display (SSH/CI) | use `QT_QPA_PLATFORM=offscreen` para testes |
| GPU NVIDIA | use `--extra runtime-cu128` e confira `LEGENDAR_*_DEVICE=auto` |
| Sem GPU | use `--extra runtime-cpu`; `auto` resolve para CPU |
| Cache em outro disco | defina `LEGENDAR_CACHE_DIR` antes de abrir a aplicação |
| Saída padrão diferente | defina `LEGENDAR_OUTPUT_DIR` |

## 7. Perfis e variáveis de runtime

| Variável | Padrão | Efeito |
|---|---|---|
| `LEGENDAR_CACHE_DIR` | `~/.cache/legendar` | modelos, logs e temporários |
| `LEGENDAR_OUTPUT_DIR` | `~/Videos` | sugestão de pasta de saída |
| `LEGENDAR_WHISPER_MODEL` | `base` | `tiny`, `base`, `small`, `medium`, `large`, `turbo` |
| `LEGENDAR_WHISPER_DEVICE` | `auto` | `auto`, `cpu`, `cuda` |
| `LEGENDAR_ALIGN_DEVICE` | `auto` | dispositivo do WhisperX |
| `LEGENDAR_TRANSLATE_DEVICE` | `auto` | dispositivo do NLLB |
| `LEGENDAR_TRANSLATE_MODEL` | `facebook/nllb-200-distilled-600M` | checkpoint compatível |
| `LEGENDAR_RESOURCE_PROFILE` | `auto` | `auto`, `low-memory`, `balanced` ou `performance`; `auto` é conservador abaixo de 16 GiB de RAM |
| `LEGENDAR_CPU_THREADS` | definido pelo perfil | sobrescreve o número de threads CPU |
| `LEGENDAR_CPU_INTEROP_THREADS` | definido pelo perfil | sobrescreve threads inter-op do PyTorch |

Configuração inválida não impede a janela de abrir: o recurso afetado fica
desabilitado com o motivo no painel de prontidão. O perfil de recursos e os overrides
de threads também podem ser definidos no ambiente antes de iniciar a aplicação.

A chave Gemini não é uma variável obrigatória de instalação: configure-a localmente
em **Preferências**. O backend Gemini é opcional e transmite o texto das cues à API
externa quando selecionado; NLLB permanece o caminho local padrão.

## 8. Instalação por pip (sem uv)

O projeto não é publicado no PyPI. Para um ambiente `pip`, gere o arquivo de
requisitos a partir do lockfile versionado:

```bash
uv export --locked --no-hashes --group dev --extra runtime-cpu --no-emit-project \
  -o requirements-export.txt
python -m pip install -r requirements-export.txt
```

O antigo `requirements.txt` da baseline foi removido na Fase 9 para não
concorrer com `pyproject.toml`/`uv.lock`.

## 9. Empacotamento

`pyinstaller` está declarado no grupo `build`, mas o empacotamento ainda não é
um entregável homologado: faltam validação de binários, tamanho e caminhos de
modelos. Enquanto isso, a execução suportada é a partir do código com `uv`.

## 10. Desinstalar

```bash
# remover o ambiente do projeto
rm -rf .venv

# remover cache, modelos e logs (opcional)
rm -rf ~/.cache/legendar
```

Nenhum arquivo é instalado fora do diretório do projeto e do cache acima.

Os pesos dos modelos são baixados sob demanda.
