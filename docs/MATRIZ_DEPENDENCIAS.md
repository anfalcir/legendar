# Matriz e política de dependências do Legendar

- **Status:** política aprovada como direção de engenharia; versões experimentais ainda em validação na Fase 0
- **Fonte canônica de requisitos diretos:** `pyproject.toml`
- **Fonte canônica da resolução exata:** `uv.lock` (a criar após validar a matriz de plataforma e o stack PyTorch)
- **Snapshot legado:** `requirements.txt` (transitório; não é fonte de verdade)

---

## 1. Princípio de governança

O repositório Legendar é a fonte de verdade dos requisitos de software. O computador em que o aplicativo será executado é um ambiente de validação e implantação, não a autoridade que define as dependências, as versões permitidas ou os limites arquiteturais do produto.

As decisões de dependências devem ser orientadas por:

1. Funcionalidades e contratos do produto.
2. Compatibilidade declarada e testada pelos projetos upstream.
3. Interseção de versões suportadas entre dependências diretas e transitivas.
4. Disponibilidade de wheels/binários para os sistemas e arquiteturas que o projeto pretende suportar.
5. Testes automatizados em matriz de Python e sistemas operacionais.
6. Segurança, licença, manutenção, custo operacional e reprodutibilidade.

O inventário de uma máquina identifica o perfil daquele ambiente. Não deve, isoladamente, excluir tecnologias, definir versões mínimas globais, obrigar o projeto a usar CPU ou impedir que outros usuários utilizem aceleração compatível.

## 2. Fontes de verdade

| Artefato | Responsabilidade | Regra |
|---|---|---|
| `pyproject.toml` | Requisitos diretos, faixas de versões, extras e grupos de desenvolvimento | Cadastro canônico; alterações de dependências começam aqui |
| `uv.lock` | Resolução exata das dependências transitivas e diretas para os ambientes declarados | Deve ser versionado e atualizado junto da mudança de requisitos, após conclusão da resolução da Fase 0 |
| `requirements.txt` | Snapshot de instalação da baseline anterior | Legado transitório; não editar manualmente nem tratar como autoridade; remover ou substituir por exportação gerada quando a migração for concluída |
| `docs/MATRIZ_DEPENDENCIAS.md` | Justificativas, categorias, compatibilidade, políticas e estado da homologação | Documenta decisões; não substitui os manifestos executáveis |

O `pyproject.toml` registra PySide6 como dependência-base e oferece perfis completos de runtime (`runtime-cpu`, `runtime-cu128` e `runtime-rocm72`). Cada perfil reúne Whisper, yt-dlp e o conjunto de pacotes PyTorch correspondente; deve-se instalar exatamente um perfil. O extra `alignment-whisperx` acrescenta o alinhador candidato e pode ser combinado com qualquer perfil cuja plataforma/versão seja compatível.

A primeira resolução experimental feita apenas contra PyPI foi **rejeitada e não foi commitada**: o pacote `torch` selecionado puxava bibliotecas CUDA/NVIDIA mesmo sem o projeto ter escolhido um perfil CUDA. Isso demonstrou que um lock universal sem seleção explícita da origem PyTorch não é suficiente. O manifesto agora direciona os pacotes PyTorch para índices explícitos por perfil, usando CPU, CUDA 12.8 ou ROCm 7.2. No macOS, o perfil CPU utiliza os wheels PyPI do PyTorch, nos quais a aceleração MPS pode estar disponível conforme o hardware/sistema. A nova resolução universal será validada antes de versionar `uv.lock`.

A escolha de `uv` é uma decisão de gerenciamento de projeto, não uma dependência de runtime do aplicativo. Seu lockfile suporta resolução universal com marcadores de plataforma, versões Python e variantes por extra; isso permite registrar diferentes perfis sem fazer do computador local a referência do projeto.

## 3. Requisitos iniciais registrados em pyproject.toml

| Componente | Categoria | Requisito atual | Motivo / situação |
|---|---|---|---|
| PySide6 | Runtime-base | `>=6.9,<7` | Framework GUI; faixa minor ampla, com limite major para exigir revisão de compatibilidade |
| openai-whisper | Runtime nos perfis `runtime-*` | `>=20250625` | Motor de reconhecimento central; declarado como requisito em todos os perfis completos |
| yt-dlp | Runtime nos perfis `runtime-*` | `>=2025.4.30` | Entrada YouTube; declarado como requisito em todos os perfis completos |
| PyTorch / torchvision / torchaudio (CPU) | Perfil completo `runtime-cpu` | `torch>=2.8,<3`; `torchvision>=0.23,<1`; `torchaudio>=2.8,<3` | Rota sem GPU dedicada; usa índice CPU explícito em Linux/Windows e wheels PyPI em macOS |
| PyTorch / torchvision / torchaudio (CUDA 12.8) | Perfil completo `runtime-cu128` | Mesmas faixas PyTorch do perfil CPU | Perfil opcional para Linux/Windows com CUDA 12.8 compatível; utiliza índice oficial cu128 |
| PyTorch / torchvision / torchaudio + Triton ROCm | Perfil experimental `runtime-rocm72` | Faixas e pacotes declarados no manifesto | Perfil opcional Linux/ROCm 7.2; exige GPU/driver suportados e homologação própria |
| WhisperX | Extra `alignment-whisperx` | `>=3.8.6,<4` | Candidato de alinhamento; deve ser combinado com exatamente um perfil `runtime-*`; só será promovido após POC PT-BR/EN |
| pytest / pytest-qt / pytest-cov | Desenvolvimento e testes | Declarados no grupo `test` | Testes unitários, integração e GUI; não são dependências do usuário final |
| Ruff | Desenvolvimento | Declarado no grupo `lint` | Lint e formatação; não é dependência do usuário final |
| PyInstaller | Empacotamento | Declarado no grupo `build` | Ferramenta de build; não é dependência de runtime |

### Python

O requisito inicial do projeto é `>=3.10,<3.14`. O limite superior atual decorre do candidato WhisperX 3.8.6, cuja metadata ainda não declara suporte a Python 3.14. Ele não foi escolhido por causa do Python 3.12.3 instalado no computador-alvo.

Esse intervalo é provisório e deverá ser expandido assim que a interseção das dependências críticas, os wheels e a CI demonstrarem compatibilidade com versões adicionais. A CI de compatibilidade deve testar as versões mínimas e máximas admitidas pelo projeto, não apenas a versão instalada na máquina de desenvolvimento.

### Instalação por perfil

O aplicativo completo exige um dos perfis abaixo. O manifesto não pressupõe o computador do mantenedor:

```bash
# CPU (Linux/Windows usa o índice CPU do PyTorch; macOS usa o wheel PyPI)
uv sync --no-dev --extra runtime-cpu

# CUDA 12.8 em Linux/Windows compatíveis
uv sync --no-dev --extra runtime-cu128

# AMD ROCm 7.2 em Linux compatível (experimental)
uv sync --no-dev --extra runtime-rocm72

# Acrescentar forced alignment depois/para a POC
uv sync --no-dev --extra runtime-cpu --extra alignment-whisperx
```

Não combinar mais de um extra `runtime-*`. O próprio `uv` declara esses perfis como conflitantes para impedir a resolução acidental de variantes PyTorch incompatíveis. No macOS, a rota é o wheel PyPI do PyTorch; MPS é capacidade do runtime/macOS quando hardware e versão suportarem, não um pacote separado neste manifesto.

A faixa Python `>=3.10,<3.14` é atualmente limitada pelo candidato WhisperX estável 3.8.6, não pelo computador do usuário. Aumentar a faixa exige revalidar a interseção de dependências do perfil completo, inclusive o alinhador.

## 4. Dependências transitivas e componentes externos

### Dependências Python transitivas

Pacotes como PyTorch, torchaudio, torchvision, NumPy, tiktoken, CTranslate2, faster-whisper, pyannote-audio, torchcodec, transformers e NLTK podem ser instalados por dependências diretas. Não devem ser repetidos como dependências diretas do Legendar apenas porque aparecem em um snapshot de `pip freeze`.

Uma biblioteca será declarada diretamente quando o código do Legendar a importar/utilizar como contrato próprio ou quando houver uma decisão explícita de controlar sua compatibilidade. A versão exata de dependências transitivas e os wheels/índices correspondentes a cada perfil serão registrados no lockfile universal; o lockfile não deverá transformar uma instalação CPU em uma instalação CUDA por resolução implícita contra PyPI.

O stack de WhisperX requer atenção especial: o metadata e a configuração upstream em evolução podem alterar os requisitos de PyTorch/torchvision/torchcodec. Não se deve acrescentar `torch==...` ao manifesto do Legendar sem validar o alinhador, o backend e as fontes de wheels em todos os perfis pretendidos.

### Executáveis e runtimes externos

| Componente | Categoria | Requisito |
|---|---|---|
| FFmpeg | Ferramenta externa obrigatória | Executável `ffmpeg` disponível no PATH ou fornecido pelo instalador do Legendar |
| ffprobe | Ferramenta externa obrigatória | Executável `ffprobe` disponível no PATH ou fornecido pelo instalador |
| Runtime JavaScript compatível | Requisito condicional do fluxo YouTube | Avaliar a combinação recomendada pelo yt-dlp para a versão selecionada; declarar e verificar no preflight quando necessária |
| Modelos Whisper/alinhamento | Artefatos de runtime | Downloads sob demanda/cache; registrar nome, origem, licença e política de armazenamento; não incluí-los indiscriminadamente no Git |

FFmpeg/ffprobe não são substituídos por pacotes Python com nomes semelhantes. O preflight do aplicativo deverá localizar, identificar a versão e apresentar instruções de instalação sem tentar alterar o sistema operacional silenciosamente.

## 5. Perfis de execução e aceleração

Os perfis de hardware não definem a lista global de dependências do produto. Eles selecionam uma combinação compatível de wheels e backend:

| Perfil | Política |
|---|---|
| CPU | Perfil completo `runtime-cpu`; índice oficial CPU do PyTorch em Linux/Windows e wheel PyPI no macOS |
| NVIDIA CUDA 12.8 | Perfil completo `runtime-cu128`; índice oficial cu128 em Linux/Windows compatíveis |
| AMD ROCm 7.2 | Perfil completo experimental `runtime-rocm72`; índice oficial rocm7.2 em Linux, sujeito à matriz de GPU/driver |
| Apple Silicon / MPS | Usa wheel PyPI do PyTorch em macOS; MPS é detectado/selecionado no runtime quando disponível, sem índice separado |
| Outros aceleradores | Não presumir compatibilidade; exigir adapter, wheels disponíveis, preflight e teste antes de declarar suporte |

A aplicação deverá detectar capacidades disponíveis em runtime e selecionar um backend validado. A presença de uma GPU não garante que cada etapa do pipeline possa utilizá-la. O produto deverá manter um fallback CPU quando a funcionalidade e as dependências escolhidas o permitirem, e deverá explicar quando determinado backend não estiver disponível.

O Ryzen 3 2200G inventariado é um perfil de teste concreto. A ausência de NVIDIA e a ausência do APU na matriz ROCm consultada significam apenas que não foi demonstrada aceleração suportada nesse equipamento. Isso não restringe o projeto a CPU em outros ambientes nem elimina perfis CUDA/ROCm/MPS homologáveis.

## 6. Política de versões: versatilidade sem perda de controle

- Usar faixas de compatibilidade, não pins exatos de todas as dependências no manifesto.
- Definir limite mínimo a partir de funcionalidade realmente utilizada e de uma versão testada.
- Usar limite superior somente quando houver incompatibilidade conhecida, mudança major previsível ou requisito upstream explícito.
- Fixar versões exatas no lockfile para tornar uma instalação reproduzível.
- Não duplicar dependências transitivas no manifesto sem motivo técnico.
- Não usar pre-releases, branches móveis ou commits Git em produção sem justificativa registrada e aprovação.
- Preferir releases estáveis; pre-releases só entram em laboratório.
- Evitar overrides de dependências; qualquer override deve ter evidência, escopo e prazo de revisão.
- Reavaliar dependências sem manutenção, vulneráveis, com licenças incompatíveis ou sem wheels para os ambientes declarados.
- Alterações de versão deverão passar por CI, testes funcionais relevantes e atualização desta matriz.

## 7. Estratégia de compatibilidade e CI

A matriz de homologação será progressiva:

1. Testar a aplicação e os requisitos determinísticos em Python 3.10, 3.11, 3.12 e 3.13 enquanto esse for o intervalo suportado pela dependência crítica de alinhamento.
2. Testar sistemas Linux, Windows e macOS em CI para componentes multiplataforma; não declarar suporte funcional do aplicativo em um sistema antes dos testes GUI, mídia, Whisper e alinhamento nesse sistema.
3. Manter uma execução com lockfile para reprodutibilidade e uma verificação periódica de atualização/compatibilidade para detectar releases novas.
4. Separar testes leves (sem baixar modelos nem acessar a rede) dos testes reais de modelo, que serão controlados, identificados e medidos.
5. Testar o perfil CPU e, quando houver infraestrutura, perfis acelerados em runners/equipamentos compatíveis.
6. Registrar versões testadas, sistema, arquitetura, resultado e limitações no estado atual.

A matriz do inventário nesta Fase 0 verifica somente o coletor de diagnóstico. Ela não equivale à homologação do aplicativo completo nos três sistemas operacionais.

## 8. Migração do snapshot legado

O `requirements.txt` existente é um snapshot com dependências transitivas fixadas, contém itens que podem não ser necessários no produto final e não separa runtime, testes e build. Ele será preservado até que:

1. O manifesto `pyproject.toml` esteja validado.
2. A resolução `uv.lock` seja criada para os ambientes declarados.
3. A instalação limpa seja testada.
4. Os fluxos essenciais sejam homologados.

Depois disso, o snapshot legado será removido ou substituído por exportações geradas do lockfile para consumidores que necessitem de `pip`. Nunca haverá dois manifestos mantidos manualmente como fontes concorrentes.

## 9. Referências técnicas consultadas em 10/11/2026

- [Python Packaging User Guide — pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [Python Packaging User Guide — dependency groups](https://packaging.python.org/en/latest/specifications/dependency-groups/)
- [uv — universal resolution e lockfile multiplataforma](https://docs.astral.sh/uv/concepts/resolution/)
- [PyTorch — instalação por sistema operacional e backend](https://docs.pytorch.org/get-started/locally/)
- [PySide6 no PyPI](https://pypi.org/project/PySide6/)
- [openai-whisper no PyPI](https://pypi.org/project/openai-whisper/)
- [WhisperX estável no PyPI](https://pypi.org/project/whisperx/)
- [yt-dlp no PyPI](https://pypi.org/project/yt-dlp/)

