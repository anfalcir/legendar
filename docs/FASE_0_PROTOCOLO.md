# Fase 0 — protocolo de execução e evidências

- **Projeto:** Legendar
- **Fase:** 0 — Definições e prova técnica
- **Status:** Em andamento
- **Início:** 10/11/2026
- **Branch de trabalho:** `phase-0/technical-inventory`
- **Documento de referência:** [Plano mestre de remodelagem](PLANO_REMODELAGEM.md)

---

## 1. Objetivo

Reduzir os riscos técnicos antes de consolidar a arquitetura e as dependências do produto. A Fase 0 deverá produzir evidências reproduzíveis sobre:

1. Ambiente real de execução (sistema operacional, Python, CPU, RAM, GPU e armazenamento).
2. Compatibilidade entre Whisper, WhisperX, PyTorch, FFmpeg e os demais componentes.
3. Qualidade de transcrição e alinhamento em português brasileiro e inglês.
4. Preservação de offsets, duração e linha temporal da mídia.
5. Desempenho e consumo de recursos no equipamento-alvo.
6. Viabilidade, privacidade e custo do serviço de tradução.
7. Critérios mensuráveis para aprovar a arquitetura da Fase 1.

Nenhuma dependência de alinhamento ou tradução será incorporada à aplicação antes da prova técnica e da resolução de compatibilidade.

## 2. Primeira entrega: inventário do ambiente

Foi adicionado `scripts/phase0_inventory.py`, ferramenta independente que usa somente a biblioteca padrão do Python.

### O que coleta

- Versão e implementação do Python.
- Sistema operacional, kernel, distribuição Linux (quando aplicável), arquitetura e modelo de CPU.
- Quantidade de CPUs lógicas, memória física total/disponível e capacidade livre/total do disco.
- Controladores gráficos PCI detectáveis em Linux (fabricante, IDs PCI, classe e driver, sem identificadores únicos do equipamento).
- Disponibilidade e versão de FFmpeg e ffprobe, incluindo a pasta local `ffmpeg/bin` quando existir.
- Presença de `nvidia-smi` e identificação das GPUs NVIDIA consultáveis. A ausência desta ferramenta não significa ausência de GPU AMD/Intel.
- Versões instaladas de Whisper, WhisperX, stable-ts, PyTorch, torchaudio, torchvision, NumPy, PySide6 e yt-dlp.
- Opcionalmente, resultado da importação do PyTorch, disponibilidade CUDA/ROCm exposta pela API CUDA do PyTorch e dispositivos reconhecidos.

### O que não faz

- Não instala, atualiza ou remove pacotes.
- Não baixa modelos ou pesos.
- Não abre nem analisa arquivos de áudio/vídeo.
- Não envia dados pela rede.
- Não coleta hostname, nome de usuário, números de série, caminhos de arquivos, URLs, conteúdo de mídia ou credenciais.
- Não altera arquivos do projeto.

A consulta de runtime do PyTorch só acontece quando `--probe-torch` é informado. A importação pode consumir memória e inicializar bibliotecas nativas, mas não baixa modelos.

### Como executar

A partir da raiz do repositório:

```bash
python scripts/phase0_inventory.py
```

Para consultar também o runtime do PyTorch:

```bash
python scripts/phase0_inventory.py --probe-torch
```

Para salvar o JSON em um local fora do repositório:

```bash
python scripts/phase0_inventory.py --probe-torch --output "$HOME/legendar-phase0-environment.json"
```

O comando não substitui um relatório existente sem a opção explícita `--force`. O JSON deve ser revisado antes de ser compartilhado; mesmo sem identificadores pessoais, ele contém informações sobre hardware e versões instaladas.

## 3. Validação automatizada da ferramenta

Os testes usam `unittest`, sem adicionar dependências de desenvolvimento nesta fase.

```bash
python -m compileall -q scripts tests
python -m unittest discover -s tests -v
```

A validação inicial executada durante a preparação desta entrega resultou em:

- 7 testes automatizados aprovados na CI após a ampliação dos testes de distribuição Linux e gráficos PCI.
- Compilação dos arquivos Python aprovada.
- Execução do `--help` aprovada.
- Execução de ponta a ponta do coletor e validação sintática do JSON aprovadas.

O ambiente em que esses testes foram executados é um ambiente isolado de desenvolvimento, não o computador-alvo do Legendar. Portanto, seus dados de hardware e suas versões não devem ser usados para fixar dependências ou escolher modelos.

## 4. Evidências técnicas iniciais (10/11/2026)

Esta pesquisa orienta os experimentos, mas não substitui testes locais:

| Tema | Evidência observada | Consequência para o projeto |
|---|---|---|
| WhisperX publicado | PyPI lista a versão 3.8.6, publicada em 25/05/2026, com Python `>=3.10,<3.14` | Registrar a versão efetivamente testada; não presumir que qualquer Python da baseline seja compatível |
| WhisperX em desenvolvimento | O `pyproject.toml` da branch principal indica 3.8.7rc1 e requer `torch~=2.8.0` e `torchvision~=0.23.0` | A baseline fixa `torch==2.7.0`; a instalação indiscriminada pode alterar o ambiente e gerar incompatibilidades |
| Alinhamento em português | O mapeamento atual do WhisperX associa `pt` a `jonatasgrosman/wav2vec2-large-xlsr-53-portuguese` | A existência do modelo não comprova precisão para PT-BR; medir com referência humana |
| Limitações do alinhador | A documentação do WhisperX alerta sobre modelos específicos por idioma, tokens fora do vocabulário e fala sobreposta | Incluir números, siglas, nomes próprios, música e fala simultânea na matriz de avaliação |
| stable-ts | O repositório foi arquivado em 30/05/2026 | Não adotar como dependência estratégica sem ganho mensurável e avaliação de manutenção |

Fontes primárias:

- [WhisperX no PyPI](https://pypi.org/project/whisperx/)
- [Dependências do WhisperX](https://github.com/m-bain/whisperX/blob/main/pyproject.toml)
- [Mapeamento de modelos de alinhamento do WhisperX](https://github.com/m-bain/whisperX/blob/main/whisperx/alignment.py)
- [Limitações documentadas do WhisperX](https://github.com/m-bain/whisperX#limitations)
- [Repositório stable-ts e aviso de arquivamento](https://github.com/jianfch/stable-ts)

**Decisão provisória:** não alterar `requirements.txt` nesta etapa. Primeiro, definir o Python e o sistema operacional de referência e resolver o conjunto compatível de versões em ambiente virtual isolado.

## 4A. Inventário recebido do computador-alvo (10/11/2026)

Arquivo recebido: `legendar-phase0-environment.json`, gerado em `2026-11-10T12:38:10Z`. A evidência foi incorporada ao estado do projeto; o arquivo JSON não foi adicionado ao repositório.

| Item | Resultado observado |
|---|---|
| Runtime | CPython 3.12.3 |
| Sistema | Linux, kernel 7.0.0-42-generic, arquitetura x86_64 |
| CPU | AMD Ryzen 3 2200G with Radeon Vega Graphics |
| CPU lógica | 4 processadores lógicos |
| Memória RAM | 12,59 GiB total; 7,65 GiB disponíveis no momento da coleta |
| Disco | 218,51 GiB total; 165,60 GiB livres no volume consultado |
| GPU NVIDIA | Nenhum `nvidia-smi` detectado |
| Gráficos integrados | O identificador do processador declara Radeon Vega Graphics; o relatório enviado antecede a enumeração PCI adicionada ao coletor atualizado |
| FFmpeg / ffprobe | Não encontrados no PATH nem em `ffmpeg/bin` do projeto |
| Pacotes Python | Somente `yt-dlp 2024.4.9` entre os pacotes consultados; Whisper, PyTorch, PySide6, NumPy, WhisperX e stable-ts ausentes neste interpretador |
| Runtime PyTorch | Não importado: `ModuleNotFoundError` |

### Interpretação técnica

1. **CPU é a baseline de homologação.** O Ryzen 3 2200G tem 4 CPUs lógicas reportadas. O caminho inicial deverá priorizar modelos pequenos e processamento sequencial, medindo tempo real por minuto de áudio e pico de memória. Não há evidência suficiente para prometer processamento em tempo real.
2. **A Radeon integrada não deve ser tratada como acelerador ROCm suportado.** A matriz oficial Linux do ROCm 7.2.1 lista APUs Ryzen AI recentes (arquiteturas gfx1150/gfx1151) e não lista o Ryzen 3 2200G. Portanto, a arquitetura não dependerá de ROCm neste equipamento; soluções comunitárias fora da matriz não serão assumidas como estáveis.
3. **Python 3.12.3 está dentro da faixa declarada pelo WhisperX 3.8.6 (>=3.10 e <3.14), mas isso não prova compatibilidade do conjunto de dependências.** A árvore de desenvolvimento atual do WhisperX especifica `torch~=2.8.0` e `torchvision~=0.23.0`, enquanto a baseline do Legendar fixa PyTorch 2.7.0. A resolução deverá ocorrer em ambiente virtual isolado, sem misturar os pacotes do aplicativo legado.
4. **A preparação de mídia está bloqueada até instalar e validar FFmpeg/ffprobe.** Não se deve iniciar a POC de alinhamento ou processamento de mídia antes de confirmar esses binários e suas versões.
5. **O inventário representa o interpretador usado no comando, não necessariamente todas as instalações Python da máquina.** A ausência de pacotes deve ser interpretada como ausência nesse runtime específico.
6. **O snapshot de RAM é momentâneo.** A memória disponível pode mudar; medir também o pico durante transcrição/alinhamento.

Fontes oficiais consultadas em 10/11/2026:
- [Matriz de compatibilidade ROCm para Ryzen em Linux](https://rocmdocs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityryz/native_linux/native_linux_compatibility.html)
- [WhisperX 3.8.6 no PyPI](https://pypi.org/project/whisperx/)
- [Dependências da branch principal do WhisperX](https://github.com/m-bain/whisperX/blob/main/pyproject.toml)
- [Modelos e requisitos aproximados do Whisper](https://github.com/openai/whisper/blob/main/README.md)
- [Pacote FFmpeg no Ubuntu](https://packages.ubuntu.com/ffmpeg)

**Interpretação restrita ao ambiente inventariado:** este computador será um perfil concreto de teste em CPU; não há evidência para instalar/usar ROCm nele. Isso não restringe o conjunto de dependências do Legendar nem impede que perfis NVIDIA CUDA, AMD ROCm ou Apple MPS sejam suportados em outros ambientes após homologação. Não alterar o stack do sistema global; preparar ambientes virtuais isolados.

O coletor foi ampliado após o primeiro relatório para identificar distribuição (`/etc/os-release`) e controladores gráficos PCI AMD/Intel/NVIDIA por sysfs. A CI valida essas novas rotinas. Repetir a coleta no computador-alvo com a versão atual da branch para completar a evidência de distribuição e driver gráfico.

## 4B. Requisito de governança das dependências do produto

A diretriz do projeto é que o **repositório seja a fonte de verdade das dependências**. O inventário do computador-alvo serve para identificar um perfil de implantação e medir desempenho; não define sozinho as bibliotecas, as versões ou as tecnologias permitidas.

Foi criado nesta branch:

- `pyproject.toml`: manifesto canônico de dependências diretas, faixas de versão, extra experimental de alinhamento e grupos de desenvolvimento.
- `docs/MATRIZ_DEPENDENCIAS.md`: justificativas, requisitos externos, política de versão, perfis de hardware e critérios de compatibilidade.

Requisitos diretos iniciais registrados:

| Componente | Requisito |
|---|---|
| PySide6 | `>=6.9,<7` |
| openai-whisper | `>=20250625` |
| yt-dlp | `>=2025.4.30` |
| WhisperX | Extra experimental `alignment-whisperx`, `>=3.8.6,<4` |
| Python | `>=3.10,<3.14`, faixa inicial orientada pelo candidato WhisperX, não pelo Python instalado no equipamento |

O arquivo `requirements.txt` permanece preservado como snapshot legado e não é a fonte canônica. O `uv.lock` ainda não foi criado: primeiro será necessário validar a resolução PyTorch/WhisperX, os wheels e as fontes de distribuição para os sistemas e perfis pretendidos; depois o lockfile será versionado para reprodutibilidade. Não foram instaladas nem promovidas dependências por esta alteração documental/manifesto.

CPU é um caminho de compatibilidade quando suportado pelos componentes. CUDA, ROCm e MPS são perfis opcionais. A ausência de suporte ROCm no equipamento atual não limita a arquitetura ou a compatibilidade que o projeto poderá oferecer em outros equipamentos.

## 5. Plano experimental

### 5.1. Ambiente

- [x] Criar coletor reproduzível do ambiente.
- [x] Testar o coletor sem instalar dependências adicionais.
- [ ] Executar o coletor no computador-alvo.
- [ ] Registrar sistema operacional, Python, CPU, RAM, GPU, driver, espaço livre e versões das bibliotecas.
- [ ] Confirmar a versão de Python que será oficialmente suportada.

### 5.2. Corpus de referência

Preparar amostras próprias ou autorizadas, sem publicar conteúdo privado no repositório:

- [ ] PT-BR com fala clara.
- [ ] Inglês com fala clara.
- [ ] Ritmos de fala diferentes e pausas.
- [ ] Música de fundo e ruído ambiental.
- [ ] Nomes próprios, termos técnicos, números, datas e siglas.
- [ ] Uma amostra com fala sobreposta, para documentar limites.
- [ ] Transcrição de referência revisada por pessoa.
- [ ] Marcação manual de início e fim de palavras em trechos representativos.

Guardar os arquivos de mídia em armazenamento local privado. Versionar somente metadados e fixtures sintéticas/explicitamente autorizadas.

### 5.3. Experimentos de reconhecimento e alinhamento

Comparar, no mínimo:

- Whisper em perfis de modelo adequados à capacidade do equipamento.
- WhisperX com modelo de alinhamento correspondente ao idioma.
- stable-ts apenas como comparação controlada, considerando que o repositório está arquivado.
- Execução em CPU e aceleração disponível, quando aplicável.

Para cada execução, registrar modelo e versão, idioma detectado/selecionado, parâmetros, duração do áudio, tempo de execução, pico de memória quando medido, palavras reconhecidas, palavras alinhadas, palavras sem timestamp e falhas.

### 5.4. Métricas

Avaliar os resultados contra referências humanas:

- WER (ou métrica adequada ao idioma) para reconhecimento.
- Erro absoluto do início e fim das palavras, com mediana e percentil 95.
- Percentual de palavras com âncoras temporais.
- Número e natureza de palavras não alinhadas.
- Timestamps negativos, invertidos, de duração zero ou fora da mídia.
- Lacunas e sobreposições suspeitas.
- Efeitos de offset, normalização e chunking.

As metas de 150 ms de erro mediano e 350 ms no percentil 95 descritas no plano mestre permanecem provisórias até a medição.

### 5.5. Mídia e offsets

- [ ] Inspecionar streams e time base com ffprobe.
- [ ] Testar faixas de áudio com offset diferente de zero.
- [ ] Confirmar que a normalização para WAV PCM mono/16 kHz preserva a linha temporal.
- [ ] Testar conversão de tempos locais de chunks para tempos globais.
- [ ] Detectar duplicação ou perda nas regiões de overlap.

### 5.6. Tradução

- [ ] Comparar provedores viáveis quanto à qualidade, custo, privacidade e latência.
- [ ] Exigir saída estruturada validável e vínculo com os segmentos de origem.
- [ ] Definir comportamento de falha e tratamento de limites de requisição.
- [ ] Não enviar áudio a serviço de tradução.
- [ ] Aprovar explicitamente o provedor antes de incorporá-lo.

## 6. Critério para encerrar a Fase 0

A Fase 0 só poderá ser marcada como concluída após:

1. Inventário real do equipamento-alvo registrado.
2. Ambiente limpo e reproduzível com versões compatíveis definidas.
3. Prova de transcrição e alinhamento para PT-BR e inglês comparada com referência humana.
4. Limitações e métricas documentadas.
5. Estratégia de offsets/chunks validada.
6. Decisão de tradução registrada (provedor escolhido ou adiamento justificado).
7. Critérios técnicos e dependências consolidados.
8. Revisão dos riscos e aprovação do responsável pelo projeto para iniciar a Fase 1.

Até esses itens serem atendidos, a Fase 1 não deve começar e nenhuma dependência experimental deve ser promovida a requisito de execução.

## 7. Histórico

| Data | Registro |
|---|---|
| 10/11/2026 | Início operacional da Fase 0. Coletor de ambiente, testes automatizados e protocolo experimental adicionados na branch `phase-0/technical-inventory`. |
