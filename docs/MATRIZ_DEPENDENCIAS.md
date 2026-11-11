# Matriz e política de dependências do Legendar

- **Status:** política de dependências consolidada na Fase 0; compatibilidade completa do produto permanece condicionada à integração/homologação.
- **Fonte canônica de requisitos diretos:** `pyproject.toml`.
- **Fonte canônica de resolução exata:** `uv.lock`, versionado no repositório.
- **Gerenciador:** `uv`, ferramenta de desenvolvimento/instalação; não é dependência de runtime.
- **Snapshot legado:** `requirements.txt`, não autoritativo e não deve ser atualizado manualmente.

---

## 1. Princípio de governança

O repositório Legendar é a fonte de verdade dos requisitos de software. O computador onde o aplicativo será executado é um perfil de validação/implantação, não a autoridade que define dependências, versões ou limites arquiteturais do produto.

Decisões devem considerar contratos do produto, compatibilidade upstream, interseção de dependências, disponibilidade de wheels/binários, CI multiplataforma, segurança, licença, manutenção, privacidade e reprodutibilidade.

Nenhuma instalação/update global deve ser executada silenciosamente pelo aplicativo. Alterações devem ocorrer em ambiente isolado e ser registradas no manifesto e no lockfile.

## 2. Fontes de verdade

| Artefato | Responsabilidade | Regra |
|---|---|---|
| `pyproject.toml` | Dependências diretas, intervalos, extras e grupos de desenvolvimento/avaliação | Fonte canônica; toda alteração começa aqui |
| `uv.lock` | Resolução exata, dependências transitivas, marcadores e origens dos wheels | Versionar e atualizar com o manifesto; instalar com `--locked` |
| `requirements.txt` | Snapshot da baseline antiga | Legado transitório; não editar manualmente; remover ou gerar exportação somente após migração |
| `docs/MATRIZ_DEPENDENCIAS.md` | Justificativas, categorias, compatibilidade, políticas e evidências | Documentação; não substitui artefatos executáveis |

Dependências transitivas não devem ser copiadas para o manifesto só porque constam de `pip freeze`. Declarar diretamente bibliotecas importadas como contrato pelo código Legendar ou necessárias para uma decisão explícita de compatibilidade.

## 3. Manifesto de runtime e perfis

A dependência-base é PySide6. O aplicativo completo deve instalar exatamente um perfil de runtime; os extras CPU e CUDA são declarados como conflitantes.

| Componente | Requisito no manifesto | Categoria e observação |
|---|---|---|
| PySide6 | `>=6.9,<7` | GUI base |
| openai-whisper | `>=20250625` | Reconhecimento |
| yt-dlp | `>=2025.4.30` | Entrada YouTube |
| yt-dlp-ejs | `>=0.8,<1` | Suporte EJS do fluxo YouTube |
| PyTorch | `>=2.8,<2.9` | Backend tensorial; origem do wheel selecionada pelo perfil |
| torchvision | `>=0.23,<0.24` | Pareado com Torch 2.8 |
| torchaudio | `>=2.8,<2.9` | Pareado com Torch 2.8 |
| WhisperX | `>=3.8.6,<3.8.7` | Alinhador candidato; intervalo deliberado para aceitar release estável 3.8.6 e excluir 3.8.7rc1 |
| pytest / pytest-qt / pytest-cov | Grupo `test` | Testes; não runtime |
| Ruff | Grupo `lint` | Qualidade de código; não runtime |
| PyInstaller | Grupo `build` | Empacotamento; não runtime |
| jiwer / soundfile / huggingface-hub | Grupo `phase0` | Métrica lexical, decodificação de áudio e download dos dados públicos de avaliação; não runtime do produto |

### Python

O projeto declara `>=3.10,<3.14`. O limite superior decorre do candidato WhisperX estável 3.8.6, cuja metadata não declara suporte a Python 3.14; não foi escolhido pela versão instalada no computador-alvo. Ampliar exige rever a interseção do perfil completo e testar wheels/integrações.

### Perfis disponíveis

| Extra | Seleção PyTorch | Plataformas pretendidas | Observação |
|---|---|---|---|
| `runtime-cpu` | Índice oficial CPU em Linux/Windows; wheels PyPI em macOS | Linux, Windows, macOS | Perfil de compatibilidade |
| `runtime-cu128` | Índice oficial CUDA 12.8 | Linux/Windows compatíveis | Opcional; depende de GPU/driver NVIDIA compatíveis |
| ROCm 7.2 | Não exposto como extra | — | PyTorch disponível no índice ROCm consultado começa em 2.11; WhisperX 3.8.6 exige Torch 2.8.x |
| Apple MPS | Wheel PyTorch PyPI no perfil CPU | macOS/Apple Silicon quando suportado | A disponibilidade é detectada no runtime; não há índice MPS separado |

Comandos:

```bash
# Instalação completa em CPU
uv sync --locked --no-dev --extra runtime-cpu

# Instalação completa CUDA 12.8 (Linux/Windows compatíveis)
uv sync --locked --no-dev --extra runtime-cu128
```

Não combinar extras `runtime-*`. Não forçar a instalação de ROCm 7.2 com override ou versão pré-release do WhisperX; reavaliar quando o upstream estável oferecer interseção compatível ou houver outra solução de alinhamento homologada.

Uma resolução antiga contra PyPI sem origem explícita foi descartada porque introduziu bibliotecas NVIDIA/CUDA sem seleção explícita de perfil. A configuração atual direciona Torch/torchvision/torchaudio para os índices oficiais CPU/cu128 onde aplicável. O lock universal preserva as variantes e seus marcadores; a CI deve verificar os perfis separadamente.

**Correção de integridade do lock:** a primeira faixa `whisperx>=3.8.6,<3.9` permitiu selecionar `3.8.7rc1`. Isso foi corrigido para `>=3.8.6,<3.8.7`. O lock atual deve conter somente WhisperX 3.8.6, nunca uma pré-release.

## 4. Dependências transitivas e conflitos relevantes

Pacotes como NumPy, CTranslate2, faster-whisper, transformers, pyannote-audio, torchcodec, NLTK e bibliotecas NVIDIA podem surgir como dependências transitivas. Não duplicar no manifesto sem contrato próprio ou necessidade explícita de controle.

Um conflito identificado na prova de avaliação: `datasets>=5.2` exige `huggingface-hub>=1.31`, enquanto WhisperX estável 3.8.6 exige `huggingface-hub<1.0`. A dependência `datasets` foi removida do grupo de avaliação; a POC lê TSV e arquivos de áudio do FLEURS diretamente usando `huggingface-hub`, respeitando a interseção do runtime. Não contornar com `--no-deps`, alterações manuais de metadata ou constraints ocultos.

## 5. Executáveis e runtimes externos

| Componente | Categoria | Política |
|---|---|---|
| FFmpeg | Ferramenta externa obrigatória | Localizar `ffmpeg` no PATH ou distribuição gerenciada pelo instalador; verificar versão/capacidades |
| ffprobe | Ferramenta externa obrigatória | Localizar e verificar; inspeção de streams e timestamps |
| Deno | Runtime JavaScript recomendado (>=2.3) a detectar no fluxo YouTube | Pré-flight deve identificar versão mínima e explicar ausência/incompatibilidade |
| Node.js | Runtime alternativo (>=22) a detectar e configurar explicitamente no yt-dlp | Não assumir que sua presença basta sem verificar compatibilidade; não é habilitado por padrão em todas as versões do yt-dlp |
| Modelos Whisper/alinhadores | Artefatos de runtime | Cache/download sob demanda; registrar ID/revisão, licença e local; não incluir pesos no Git |

### Reconhecimento local (Fase 4)

- O pacote `openai-whisper` é o motor local de reconhecimento; o áudio não é enviado a uma API externa.
- O perfil inicial configurado por padrão é `base`; `tiny`, `small`, `medium`, `large` e `turbo` são perfis multilíngues selecionáveis por configuração. O padrão é uma escolha inicial, não uma homologação de qualidade.
- `LEGENDAR_WHISPER_MODEL` seleciona o perfil. `LEGENDAR_WHISPER_DEVICE` aceita `auto`, `cpu`, `cuda` ou `mps`; `auto` prioriza CUDA, depois MPS e por fim CPU.
- Os pesos são baixados na primeira utilização e mantidos em `<models_dir>/whisper` (por padrão, sob `~/.cache/legendar/models/whisper`). O cache não pertence ao workspace temporário e nunca é removido ao cancelar um job.
- O adaptador utiliza `task="transcribe"`, sem tradução automática e sem timestamps por palavra. Segmentos do decoder não são tratados como forced alignment; a Fase 5 continua responsável pela sincronização temporal.

FFmpeg/ffprobe não são substituídos por pacotes Python com nomes semelhantes. O aplicativo deverá apresentar orientações para instalar ferramentas ausentes, sem alterar o sistema operacional silenciosamente.

### Runtime JavaScript do YouTube (EJS)

O fluxo YouTube depende do suporte JavaScript EJS do yt-dlp e não deve tratar a simples existência de um binário como compatibilidade. O preflight aceita Deno >=2.3 (preferencial) ou Node.js >=22. Quando Node é selecionado, o adaptador configura explicitamente `js_runtimes` na API Python do yt-dlp; não confiar no default, que pode habilitar somente Deno. A versão instalada é lida no preflight e a GUI informa runtime ausente, versão antiga ou selecionada.

Referências oficiais: [yt-dlp EJS](https://github.com/yt-dlp/ejs) e [EJS wiki do yt-dlp](https://github.com/yt-dlp/yt-dlp-wiki/blob/master/EJS.md).

## 6. Política de hardware e backend

A aplicação deve detectar capacidades em runtime e selecionar apenas backends homologados. Presença de GPU não é evidência de que todas as etapas podem usá-la.

- **CPU:** caminho de compatibilidade quando suportado pelas dependências e modelos.
- **NVIDIA CUDA 12.8:** perfil opcional Linux/Windows com wheels PyTorch oficiais e driver compatível.
- **Apple MPS:** possível por wheels PyPI no macOS/Apple Silicon; precisa ser testado na aplicação integrada.
- **AMD ROCm 7.2:** sem perfil completo no estado atual pela incompatibilidade entre Torch >=2.11 do índice e Torch 2.8.x requerido pelo WhisperX estável 3.8.6.
- **Outros backends:** não anunciar sem wheels, preflight e testes específicos.

O computador inventariado (Ryzen 3 2200G, quatro CPUs lógicas, Radeon Vega) é somente um perfil concreto de homologação CPU; não limita os requisitos globais do produto.

## 7. Reprodutibilidade e CI

A CI da Fase 0 separa:
1. Testes determinísticos do coletor em Python 3.10–3.13 × Linux/Windows/macOS.
2. Resolução/consistência do lock e simulação de instalação dos dois perfis com `uv sync --locked --dry-run`.
3. Instalação real e importação do perfil CPU junto da POC de modelo PT-BR/EN.
4. Instalação real e importação de Torch, torchvision e torchaudio no perfil CUDA 12.8; o runner não precisa ter GPU física, portanto `torch.cuda.is_available() == False` é esperado e não é falha do teste de wheel.
5. Prova FFmpeg/ffprobe de normalização e mapeamento de offsets.

Os 12 cenários de coletor não equivalem a suporte funcional completo do aplicativo em todos os sistemas operacionais. A POC FLEURS é um smoke benchmark pequeno; WER mede reconhecimento lexical, não precisão temporal. No workflow #109, com WhisperX 3.8.6 / tiny / CPU-int8 e duas amostras por idioma, PT-BR apresentou WER médio 0,275 e RTF médio 0,372 (26 palavras com timestamps válidos); EN apresentou WER médio 0,209559 e RTF médio 0,163 (30 palavras com timestamps válidos). Não houve palavra com timestamp ausente/inválido nas quatro amostras. O processo levou 62,131 s e o pico de RSS foi 3.456.839.680 bytes (~3,22 GiB) no runner GitHub. O artefato `legendar-phase0-model-poc` contém os detalhes por amostra.

O log registrou um aviso não bloqueante de TorchCodec/pyannote: as bibliotecas FFmpeg compartilhadas não foram carregadas para o backend de I/O. A POC faz preload do áudio e passa o waveform diretamente ao WhisperX/alinhador, portanto o teste concluiu com sucesso; a decodificação via TorchCodec não foi validada por esse benchmark. A prova independente com FFmpeg/ffprobe passou no mesmo workflow. Se o produto vier a usar o caminho de I/O do TorchCodec, verificar a compatibilidade de bibliotecas e versões explicitamente.

A Fase 4 acrescenta `scripts/phase4_model_benchmark.py`: comparação reproduzível de modelos com WER, CER, RTF, duração, RSS e versões. O script usa FLEURS ou um manifesto TSV local (`language`, `audio`, `reference`); o relatório contém métricas e IDs sintéticos, nunca áudio ou texto transcrito. A CI executa smoke test CPU PT-BR/EN em Python 3.12. A qualidade no computador-alvo e em corpus representativo de pregações precisa ser medida antes de declarar um perfil recomendado.

A precisão de alinhamento deve ser medida com timestamps humanos anotados e amostras representativas do uso final.

### POC de idioma

A avaliação controlada usa FLEURS `pt_br` e `en_us`, split test, revisão de dataset fixada, modelo WhisperX `tiny`, CPU/int8 e amostras pequenas. Registra WER, tempos, RTF, memória máxima do processo, palavras alinhadas e palavras sem timestamp válido. O corpus é CC-BY-4.0 e consiste em fala lida; não representa sermões, música, ruído, fala espontânea ou sobreposição.

Relatório CI: artefato `legendar-phase0-model-poc`, quando a execução do job terminar. Ele é evidência experimental, não dado de runtime do aplicativo.

## 8. Migração do legado

Manter `requirements.txt` apenas até que:
1. `pyproject.toml` e `uv.lock` estejam validados.
2. Instalações limpas dos perfis sejam reproduzíveis.
3. Fluxos essenciais estejam homologados.
4. Migração do aplicativo e documentação estejam coerentes.

Depois, remover o snapshot ou gerar exportação automaticamente para consumidores que ainda precisem de pip. Nunca manter dois manifestos editados manualmente.

## 9. Manutenção e atualização

- Preferir releases estáveis; pré-releases e branches móveis somente em laboratório com aprovação explícita.
- Definir mínimos a partir de funcionalidades utilizadas e versões testadas.
- Fixar versões exatas no lockfile; usar intervalos no manifesto.
- Atualizar lock junto de manifesto e documentação.
- Revalidar origem de wheels, índices, marcadores, licenças, segurança e Python/OS/arquiteturas.
- Evitar overrides; quando inevitáveis, justificar escopo e prazo de revisão.
- Reavaliar dependências sem manutenção, com licença inadequada ou sem wheels compatíveis.
- Não confundir a presença de pacote/modelo com qualidade comprovada.

Referências técnicas:
- [Python Packaging User Guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [Dependency Groups](https://packaging.python.org/en/latest/specifications/dependency-groups/)
- [uv universal resolution](https://docs.astral.sh/uv/concepts/resolution/)
- [PyTorch installation](https://docs.pytorch.org/get-started/locally/)
- [OpenAI Whisper](https://github.com/openai/whisper)
- [WhisperX](https://github.com/m-bain/whisperX)
- [FFmpeg](https://ffmpeg.org/documentation.html)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [Google FLEURS dataset](https://huggingface.co/datasets/google/fleurs)
- [OpenAI Whisper — API local Python](https://github.com/openai/whisper)
