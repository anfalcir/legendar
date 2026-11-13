# Distribuição para Linux Mint/Ubuntu x86_64

- **Status:** primeira implementação do instalador por usuário em revisão; ainda não publicada em GitHub Releases nem homologada no Linux Mint de referência.
- **Objetivo:** entregar uma instalação simples, isolada, atualizável e removível, sem alterar o Python do sistema nem exigir privilégios administrativos para o aplicativo.
- **Plataforma inicial:** Linux x86_64 (inclui Linux Mint x86_64). Outras arquiteturas e sistemas operacionais não fazem parte deste artefato.

## 1. Decisão de distribuição

O primeiro artefato não será um executável PyInstaller monolítico. O Legendar depende de um stack Python pesado (PySide6, PyTorch, Whisper e WhisperX), FFmpeg do sistema e modelos externos com licenças próprias. Empacotar indiscriminadamente todas as bibliotecas em um binário único aumentaria o tamanho e ainda exigiria gestão de bibliotecas nativas e pesos externos.

A estratégia escolhida é um **bundle de bootstrap por usuário**:
- código-fonte versionado + `pyproject.toml` + `uv.lock`;
- instalador e lançador Bash;
- Python 3.12 gerenciado pelo `uv`, sem substituir o Python do sistema;
- ambiente virtual isolado em `~/.local/share/legendar/app/.venv`;
- atalho de menu em `~/.local/share/applications`;
- cache de modelos/logs separado em `~/.cache/legendar`;
- runtime llama.cpp e GGUF TranslateGemma preparados posteriormente pelo aplicativo, sob demanda e com consentimento.

O arquivo compactado inicial é pequeno em comparação com o ambiente instalado: o download dos wheels Python acontece durante a instalação. A primeira instalação requer internet e espaço livre suficiente (recomendação mínima de 8 GiB).

## 2. Instalação

Após uma GitHub Release publicar `legendar-linux-x86_64-*.tar.gz`:

1. Baixe o arquivo e o checksum `.sha256`.
2. Extraia o pacote.
3. Abra um terminal dentro da pasta extraída e execute:

```bash
./packaging/linux/install.sh
```

O instalador:
- aceita somente Linux x86_64;
- exige `curl`;
- instala `uv 0.13.7` em `~/.local/bin`, sem modificar perfis de shell;
- instala Python 3.12 gerenciado pelo uv;
- oferece instalar FFmpeg/ffprobe e bibliotecas Qt via APT se estiverem ausentes (a senha/sudo só é solicitada após confirmação);
- instala o perfil CPU do `uv.lock` em ambiente isolado;
- cria o comando `~/.local/bin/legendar` e o atalho de menu.

Nenhum comando de instalação do aplicativo ou do Python usa `sudo`. A senha administrativa só pode ser solicitada para pacotes do sistema, mediante consentimento explícito.

## 3. Verificação idempotente e reparo

A cada abertura, `launch.sh` executa uma sincronização offline e bloqueada pelo `uv.lock`. Se o ambiente estiver íntegro, a operação não baixa pacotes nem altera o conjunto instalado. Se detectar dependências ausentes/inconsistentes, oferece reparo online antes de sincronizar novamente. O log do lançador fica em `~/.cache/legendar/logs/launcher.log`.

A idempotência do instalador é distinta da idempotência do runtime TranslateGemma: o primeiro mantém o ambiente Python consistente; o aplicativo continua responsável por instalar/validar llama.cpp, baixar o GGUF após consentimento, iniciar o servidor e encerrá-lo com segurança.

## 4. Atualização e remoção

Para atualizar, execute o instalador de uma versão mais recente. O ambiente é sincronizado a partir do lockfile da versão instalada. O cache de modelos, logs e configurações permanece separado do código.

Para remover, execute `~/.local/share/legendar/app/uninstall.sh`. O desinstalador pede confirmação e remove o aplicativo, o ambiente Python, o uv privado, a documentação, o atalho e o comando de entrada. Por padrão, preserva `~/.cache/legendar` (modelos/logs/configurações) e `~/.cache/uv` (Python gerenciado/cache de wheels); a limpeza desses caches deve ser uma decisão separada do usuário.

## 5. CI e publicação

O workflow `.github/workflows/linux-distribution.yml`:
- verifica `uv.lock` e resolução do perfil CPU;
- executa `bash -n` e ShellCheck nos scripts;
- gera o tarball com ordenação e timestamps determinísticos;
- calcula SHA-256 e verifica os arquivos obrigatórios;
- disponibiliza o artefato da execução do workflow;
- publica uma GitHub Release em modo **pré-release** somente para tags `vX.Y.Z` que correspondam à versão em `src/legendar/__init__.py`. O artefato inicial não será marcado como estável até a homologação real no Linux Mint e o smoke TranslateGemma.

O workflow não instala o ambiente pesado completo no runner: a validação de resolução é feita com dry-run. Portanto, a CI valida o pacote e seus scripts, mas não substitui a instalação real no Linux Mint.

## 6. Gates antes de declarar homologado

- Instalar a partir do tarball em uma conta Linux Mint limpa ou representativa.
- Confirmar ausência de alterações no Python global e ausência de sudo para instalação Python.
- Abrir pelo menu e pela linha de comando.
- Verificar reparo offline/online e repetição sem download redundante.
- Confirmar que cache e preferências sobrevivem a atualização e desinstalação.
- Executar o smoke TranslateGemma com pesos reais e a única tradução representativa descrita em [HOMOLOGACAO.md](HOMOLOGACAO.md).
- Registrar tamanho do bundle, tempo de instalação, espaço ocupado e eventuais bibliotecas nativas ausentes.

Até que esses gates sejam aprovados, o pacote deve ser descrito como **instalador experimental para homologação**, não como release estável.
