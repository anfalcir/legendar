# Instalação do Legendar

- **Escopo:** instalar e executar a aplicação a partir do código versionado.
- **Fonte de verdade das dependências:** `pyproject.toml` e `uv.lock`; a matriz detalhada está em [MATRIZ_DEPENDENCIAS.md](MATRIZ_DEPENDENCIAS.md).
- **Operação:** [OPERACAO.md](OPERACAO.md).
- **Distribuição Linux:** [DISTRIBUICAO_LINUX.md](DISTRIBUICAO_LINUX.md).

## 1. Requisitos

| Item | Versão | Observação |
|---|---|---|
| Python | 3.10 a 3.13 | faixa declarada em `requires-python` |
| uv | 0.13.7 (versão usada na CI) | gerencia ambiente e lockfile |
| FFmpeg | qualquer versão estável recente | obrigatório no `PATH` |
| ffprobe | mesma origem do FFmpeg | obrigatório no `PATH` |
| Runtime JavaScript | Deno ≥ 2.3 ou Node ≥ 22 | necessário apenas para YouTube (`yt-dlp-ejs`) |
| Espaço em disco | reservar pelo menos 8 GB livres | cache de Whisper/WhisperX e TranslateGemma GGUF (~2,5 GB) |

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

- `runtime-cpu` instala o stack PyTorch CPU, Whisper, WhisperX e yt-dlp. O runtime llama.cpp/TranslateGemma é preparado pelo próprio aplicativo, sob demanda. Dependências transitivas exigidas pelo WhisperX permanecem resolvidas pelo lockfile.
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
| `LEGENDAR_RESOURCE_PROFILE` | `auto` | `auto`, `low-memory`, `balanced` ou `performance`; `auto` é conservador abaixo de 16 GiB de RAM |
| `LEGENDAR_CPU_THREADS` | definido pelo perfil | sobrescreve o número de threads CPU |
| `LEGENDAR_CPU_INTEROP_THREADS` | definido pelo perfil | sobrescreve threads inter-op do PyTorch |

Configuração inválida não impede a janela de abrir: o recurso afetado fica
desabilitado com o motivo no painel de prontidão. O perfil de recursos e os overrides
de threads também podem ser definidos no ambiente antes de iniciar a aplicação.

TranslateGemma é o único backend local e está funcionalmente homologado para o uso atual.
O aplicativo verifica/prepara o runtime llama.cpp e o modelo sob demanda; a instalação
do runtime e o download dos pesos exigem consentimento explícito. O cache é preservado
entre execuções. Gemini é opcional, selecionado explicitamente em **Preferências**, e
transmite o texto das cues à API externa. Não há fallback automático entre os motores.

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

## 9. Pacote de usuário para Linux Mint/Ubuntu x86_64

O projeto disponibiliza um pacote de instalação por usuário (não é um executável
PyInstaller monolítico). O arquivo contém o código versionado, o lockfile, o
instalador, o lançador e o desinstalador. O instalador prepara um Python 3.12
isolado com `uv`, instala o perfil CPU a partir de `uv.lock` e cria um atalho no
menu. O aplicativo e o ambiente Python ficam em `~/.local/share/legendar/app`;
o executável de entrada fica em `~/.local/bin/legendar`. Modelos, configurações
e logs permanecem fora desse diretório e não são removidos por atualizações.

Quando uma GitHub Release Linux estiver publicada, baixe o arquivo
`legendar-linux-x86_64-*.tar.gz`, extraia-o e execute no terminal:

```bash
cd legendar-linux-x86_64-*/
./packaging/linux/install.sh
```

O instalador não usa `sudo` para instalar o aplicativo, Python ou dependências
Python. Se FFmpeg/ffprobe ou bibliotecas Qt do sistema estiverem ausentes, oferece
instalação via APT e só prossegue após confirmação explícita. A primeira instalação
baixa Python e o stack CPU do lockfile; reserve conexão estável e pelo menos 8 GB
livres. TranslateGemma/llama.cpp e o GGUF continuam sendo preparados pelo próprio
aplicativo sob demanda, com consentimentos separados.

O lançador verifica o ambiente de forma idempotente em modo offline a cada abertura.
Se detectar dependências inconsistentes, oferece reparo online antes de alterar o
ambiente. O desinstalador remove o aplicativo, o ambiente Python, o uv privado e o atalho,
mas preserva `~/.cache/legendar` (modelos, configurações e logs) e `~/.cache/uv`
(Python gerenciado/cache de wheels, que pode ser compartilhado com outros projetos).

O workflow `Linux distribution` valida ShellCheck, lockfile e conteúdo do arquivo;
publica o pacote em Releases somente quando uma tag de versão é criada. A primeira
versão desse instalador ainda precisa de homologação operacional no Linux Mint do
hardware de referência. Não confundir pacote gerado/CI verde com homologação real.

O grupo `build` ainda mantém PyInstaller para experimentos, mas não é usado por
esse fluxo de distribuição.

## 10. Desinstalar

```bash
# remover o ambiente do projeto
rm -rf .venv

# remover cache, modelos e logs (opcional)
rm -rf ~/.cache/legendar
```

Nenhum arquivo é instalado fora do diretório do projeto e do cache acima.

Os pesos dos modelos são baixados sob demanda.
