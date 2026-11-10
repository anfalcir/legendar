# Fase 0 — protocolo, decisões e evidências

- **Projeto:** Legendar
- **Fase:** 0 — Definições e prova técnica
- **Status:** definição técnica e pacote de POC concluídos; validação operacional final do lock/POC depende dos workflows atuais
- **Data:** 10/11/2026
- **Branch:** `phase-0/technical-inventory`
- **Plano mestre:** [PLANO_REMODELAGEM.md](PLANO_REMODELAGEM.md)
- **Estado vivo:** [ESTADO_ATUAL.md](ESTADO_ATUAL.md)
- **Matriz de dependências:** [MATRIZ_DEPENDENCIAS.md](MATRIZ_DEPENDENCIAS.md)
- **Handoff da próxima fase:** [HANDOFF_FASE_1.md](HANDOFF_FASE_1.md)

---

## 1. Objetivo e limite de conclusão

A Fase 0 reduz riscos antes da reestruturação. Ela deve definir os contratos de produto e de dependências e demonstrar que os principais componentes candidatos podem ser combinados em uma POC reproduzível.

A fase é considerada tecnicamente concluída quando:
- os requisitos e perfis de dependências estão declarados no repositório;
- o lock é consistente, reproduzível e seleciona explicitamente as variantes de backend;
- os fluxos sintéticos de mídia e timeline são comprovados;
- existe uma POC mínima e repetível de reconhecimento/alinhamento PT-BR e EN;
- as decisões e limitações são documentadas;
- as provas que exigem amostras próprias anotadas ou hardware do responsável estão alocadas às fases de produto que as implementam, com critérios explícitos;
- o handoff orienta a IA responsável pela Fase 1 sem decisões arquiteturais fundamentais escondidas.

**A conclusão da Fase 0 não equivale à homologação de precisão temporal do produto.** As provas de timestamp com referências humanas permanecem no gate da Fase 5; a validação de qualidade/performance no computador-alvo permanece nas Fases 4, 5 e 8; a seleção de fornecedor de tradução permanece antes da Fase 6. Isso evita tanto iniciar a arquitetura sem contratos quanto afirmar uma qualidade que ainda não foi medida.

No momento desta atualização, as implementações e o pacote de documentação estão na branch isolada. Os workflows finais referentes ao HEAD atual ainda estão na fila do GitHub Actions; consulte `docs/ESTADO_ATUAL.md` e o PR #1 para o resultado mais recente. Não converter “queued” em “passed”.

## 2. Inventário de ambiente

### 2.1. Ferramenta

`scripts/phase0_inventory.py` é somente leitura e usa biblioteca padrão do Python. Coleta:
- versão/implementação do Python;
- sistema, kernel, distribuição Linux, arquitetura e CPU;
- quantidade de CPUs lógicas e RAM total/disponível;
- armazenamento livre/total;
- controladores PCI de vídeo no Linux (fabricante, IDs PCI, classe e driver);
- FFmpeg, ffprobe e NVIDIA `nvidia-smi`;
- runtimes JavaScript Deno e Node;
- versões das distribuições Python relevantes;
- opcionalmente, importação PyTorch e capacidades CUDA/ROCm expostas por ele (`--probe-torch`).

Não coleta hostname, usuário, credenciais, nomes/URLs de mídia, conteúdo, números de série ou caminhos arbitrários. Não instala pacotes, baixa modelos nem modifica o projeto. O relatório contém informações de hardware/versões e deve ser revisado antes de compartilhamento.

### 2.2. Execução

```bash
python scripts/phase0_inventory.py
python scripts/phase0_inventory.py --probe-torch
python scripts/phase0_inventory.py --probe-torch \
  --output "$HOME/legendar-phase0-environment.json"
```

O relatório enviado em 10/11/2026 foi gerado antes da ampliação do coletor. Ele registrou CPython 3.12.3, Linux x86_64, AMD Ryzen 3 2200G com quatro CPUs lógicas, 12,59 GiB RAM total, 165,60 GiB livres no volume consultado, Radeon Vega integrada e ausência de FFmpeg/ffprobe e PyTorch no interpretador consultado.

Esse é um perfil de homologação CPU, não a definição dos requisitos globais do produto. Reexecutar o coletor atualizado antes da homologação no computador-alvo e instalar FFmpeg/ffprobe conforme a distribuição identificada.

## 3. Governança de dependências e perfis

### 3.1. Fontes de verdade

- `pyproject.toml`: requisitos diretos, faixas, extras e grupos.
- `uv.lock`: resolução exata, dependências transitivas, marcadores e fontes de wheels.
- `docs/MATRIZ_DEPENDENCIAS.md`: política e justificativas.
- `requirements.txt`: snapshot legado, nunca atualizar manualmente como segundo manifesto.

A máquina local não é fonte de verdade de dependências. Toda instalação de verificação usa ambiente isolado, perfil explícito e lockfile.

### 3.2. Runtime

Python declarado: `>=3.10,<3.14`.

Dependência base: PySide6 `>=6.9,<7`.

Perfis mutuamente exclusivos:
- `runtime-cpu`: Whisper, yt-dlp, yt-dlp-ejs, Torch 2.8, torchvision 0.23, torchaudio 2.8 e WhisperX estável 3.8.6.
- `runtime-cu128`: mesmo conjunto com wheels oficiais CUDA 12.8; somente Linux/Windows compatíveis.

WhisperX usa intervalo `>=3.8.6,<3.8.7` para excluir pré-releases. O primeiro lock produzido com faixa mais ampla `<3.9` escolheu 3.8.7rc1, contrariando a política stable-only; a faixa foi corrigida. A CI valida a versão exata no lock.

PyTorch é roteado por índice explícito:
- CPU: `https://download.pytorch.org/whl/cpu`;
- CUDA 12.8: `https://download.pytorch.org/whl/cu128`;
- macOS usa wheels PyPI no perfil CPU, podendo expor MPS em ambientes compatíveis.

Não oferecer ROCm 7.2 no estado atual: o índice consultado resolve PyTorch a partir de 2.11, mas WhisperX estável 3.8.6 requer Torch 2.8.x. Não usar RC ou override para mascarar isso.

Comandos de instalação:

```bash
# Linux/Windows ou macOS: CPU (no macOS, wheels PyPI)
uv sync --locked --no-dev --extra runtime-cpu

# Linux/Windows com NVIDIA/driver CUDA 12.8 compatíveis
uv sync --locked --no-dev --extra runtime-cu128
```

Nunca combinar os dois extras. O lock e os exports devem demonstrar que o perfil CPU não carrega pacotes NVIDIA e que CUDA 12.8 inclui os componentes NVIDIA pertinentes.

### 3.3. Dependências externas e runtime YouTube

- FFmpeg e ffprobe são executáveis obrigatórios, não pacotes Python.
- yt-dlp-ejs é declarado no runtime.
- Deno deve ser verificado no preflight do fluxo YouTube; Node pode ser alternativa conforme a versão/recomendação do yt-dlp.
- Modelos Whisper/alinhamento são baixados sob demanda e armazenados em cache. Registrar nome, origem/revisão, licença e política de armazenamento; pesos não vão para Git.
- O coletor da Fase 0 detecta FFmpeg/ffprobe, Deno e Node sem instalar nada.

### 3.4. Conflitos encontrados e resolução

1. **PyPI sem origem PyTorch explícita:** lock experimental incluiu pacotes CUDA/NVIDIA no perfil genérico. Rejeitado; índices PyTorch passaram a ser explícitos.
2. **ROCm 7.2 e WhisperX 3.8.6:** Torch do índice ROCm 7.2 começa em 2.11; WhisperX requer 2.8.x. Perfil removido.
3. **WhisperX 3.8.7rc1:** versão pré-release apareceu quando o limite era `<3.9`. Faixa restringida para `<3.8.7`; validador dedicado verifica que só 3.8.6 aparece.
4. **datasets 5.2 / huggingface-hub:** datasets 5.2 exige `huggingface-hub>=1.31`; WhisperX 3.8.6 exige `huggingface-hub<1.0`. A dependência datasets foi removida do grupo de avaliação. A POC lê TSV e áudio do corpus FLEURS diretamente via huggingface-hub e tarfile; não usa `--no-deps` nem manipula metadata.
5. **yt-dlp EJS:** yt-dlp-ejs foi incluído no manifesto e no teste de lock para que o suporte EJS não seja uma dependência implícita omitida.

## 4. POC de preparação de mídia e offsets

Arquivo: `scripts/phase0_media_poc.py`.

Uso em arquivo real:

```bash
python scripts/phase0_media_poc.py input.mp4 --output /tmp/legendar-normalized.wav
python scripts/phase0_media_poc.py input.mkv --stream-index 2 \
  --output /tmp/legendar-normalized.wav
```

Prova sintética:

```bash
python scripts/phase0_media_poc.py --self-test
```

A prova gera uma fonte de áudio, desloca a faixa em 1,25 s no contêiner e:
- identifica a faixa de áudio global por ffprobe;
- registra o offset e sua origem (stream timestamp ou fallback do contêiner);
- normaliza para WAV PCM signed 16-bit, mono, 16 kHz;
- confirma codec/sample rate/canais;
- verifica o mapeamento local → global.

Contrato de timeline:

```text
global_timestamp =
    source_stream_offset
    + chunk_offset
    + local_aligner_timestamp
```

A prova sintética foi aprovada em CI nos workflows #65/#66/#67. Ela não cobre ainda toda a variedade de contêineres, codecs, streams, offsets negativos, arquivos longos e fronteiras de chunk. Essa abrangência é da Fase 3 e dos testes integrados subsequentes.

## 5. POC de reconhecimento/alinhamento PT-BR e inglês

Arquivo: `scripts/phase0_model_poc.py`.

Corpus: [Google FLEURS](https://huggingface.co/datasets/google/fleurs), CC-BY-4.0, configurações `pt_br` e `en_us`, split `test`. A revisão do dataset é fixada no script; são selecionadas poucas amostras por idioma. Arquivos TSV e áudio são obtidos do repositório público com `huggingface-hub`; nenhuma mídia ou transcrição é commitada ao Legendar.

Configuração da prova:
- WhisperX release estável 3.8.6, respeitando o runtime declarado;
- modelo Whisper `tiny` multilingue;
- CPU e `int8`;
- alinhador por idioma (`pt`/ `en`);
- poucas amostras para testar compatibilidade e pipeline, não estabelecer qualidade de produção.

O JSON gerado contém:
- nome/revisão do dataset, idioma e IDs de amostra;
- duração e quantidade de palavras de referência/hipótese;
- WER normalizado;
- duração de transcrição/alinhamento e fator de tempo real (RTF);
- contagem de palavras com timestamps válidos e contagem não alinhada/inválida;
- versão Python/PyTorch/WhisperX, modelo/dispositivo, RSS de pico e tempo total;
- limitações da amostragem.

Execução local (após sincronização lockada):

```bash
uv sync --locked --no-dev --group phase0 --extra runtime-cpu
uv run --locked python scripts/phase0_model_poc.py \
  --model tiny --samples-per-language 2 \
  --cache-dir .cache/phase0 --output phase0-model-poc.json
```

A CI roda o smoke benchmark no runner Ubuntu e publica o artefato `legendar-phase0-model-poc` quando o job termina.

**Como interpretar:** FLEURS é fala lida, não sermões, fala espontânea, música, ruído ou sobreposição. WER mede erro lexical e não precisão temporal. A contagem de timestamps verifica cobertura/validade básica e não erro contra marcação humana. O desempenho de runner GitHub não prevê desempenho no Ryzen 3 2200G. O resultado é uma prova de compatibilidade/reprodutibilidade, não critério único de aceitação de produto.

## 6. CI e comandos de verificação

Workflow: `.github/workflows/phase0-quality.yml`.

Jobs:
1. Resolver e verificar lockfile em uv fixado; em push, gerar/atualizar `uv.lock`; em PR, exigir lock atualizado.
2. Validar invariantes: WhisperX estável 3.8.6, yt-dlp-ejs, fontes explícitas CPU/cu128, extras conflitantes e Python compatível.
3. Exportar perfil CPU e falhar se houver dependências NVIDIA; exportar CUDA e exigir pacotes NVIDIA.
4. Testar coletor, compilação, CLI e testes unitários em Python 3.10–3.13 × Linux/Windows/macOS.
5. Instalar realmente perfil CPU e executar POC FLEURS PT-BR/EN.
6. Instalar realmente perfil CUDA 12.8 e importar Torch/torchvision/torchaudio; não exige GPU física no runner.
7. Instalar FFmpeg/ffprobe e executar POC sintética de mídia/offset.

Comandos básicos:

```bash
python -m compileall -q scripts tests
python -m unittest discover -s tests -v
python scripts/phase0_inventory.py --help
python scripts/phase0_media_poc.py --help
python scripts/phase0_model_poc.py --help
python scripts/phase0_validate_lock.py
uv lock --check
uv sync --locked --no-dev --extra runtime-cpu --dry-run
uv sync --locked --no-dev --extra runtime-cu128 --dry-run
```

O workflow final no HEAD atual deve estar totalmente concluído e verde antes da integração da PR. Um workflow em estado `queued` ou `in_progress` não é evidência de aprovação.

## 7. Decisões de arquitetura para a Fase 1

| Tema | Decisão de saída da Fase 0 |
|---|---|
| Arquitetura | Separar domínio, aplicação, infraestrutura, apresentação PySide6 e bootstrap |
| Reconhecimento | Whisper multilingue como motor inicial candidato |
| Alinhamento | WhisperX estável 3.8.6 como primeiro adapter/candidato; sem acoplar domínio à biblioteca |
| Idiomas | Prioridade PT-BR e EN; detecção de idioma não equivale a idioma alinhado homologado |
| Áudio interno | WAV PCM signed 16-bit, mono, 16 kHz |
| Timeline | Preservar stream index/time base/offset original; global = source offset + chunk offset + local |
| Chunking | Chunks com offset global e overlap explícito; deduplicação determinística; sem timestamps artificiais |
| Tradução | Porta/adaptador independente; não escolher fornecedor na Fase 1; texto original preservado; não enviar áudio |
| SRT | Writer/validator puros; intervalos finitos, ordenados, duração positiva, UTF-8 e publicação atômica |
| Estado | Pipeline serial com estados explícitos, cancelamento cooperativo e progresso somente mensurável |
| Concorrência | Um job ativo por instância no escopo inicial |
| Temporários | Diretório isolado por job; cache de modelos compartilhado não deve ser limpo ao cancelar |
| UI | Workers em background e sinais tipados; worker nunca manipula widgets diretamente |

Os detalhes e contratos sugeridos estão em `docs/HANDOFF_FASE_1.md`.

## 8. Validações deliberadamente encaminhadas às fases de produto

Estas provas dependem de fixtures humanas, ambiente de implantação ou decisões na fase que consome a funcionalidade. Elas não devem ser substituídas por uma declaração sem evidência.

| Gate | Fase | Evidência exigida |
|---|---|---|
| Instalação/preflight no computador-alvo | Antes/durante Fase 3 | Novo inventário, distribuição Linux, GPU/driver, FFmpeg/ffprobe, Deno/Node, espaço de cache; instalação CPU lockada |
| Matriz de contêineres/codecs/streams | Fase 3 | Fixtures locais autorizadas, faixas múltiplas, offsets, duração, formatos e falhas de decodificação |
| Qualidade de reconhecimento | Fase 4 | Corpus PT-BR/EN representativo e transcrições de referência; WER/CER, duração, RSS, RTF |
| Precisão temporal de alinhamento | Fase 5 | Início/fim de palavras anotados manualmente; erro mediano/P95, cobertura, palavras sem timestamp, números, siglas, nomes, ruído, música e sobreposição |
| Tradução | Antes/durante Fase 6 | Comparação atualizada de fornecedores, custo por volume, privacidade, retenção, limites, latência, structured output e comportamento de falha |
| Suporte completo de plataforma/backend | Fase 8 | Aplicativo integrado (GUI, mídia, reconhecimento, alinhamento) testado nos SOs/backends que forem declarados suportados |

Metas temporais de 150 ms mediana e 350 ms P95 permanecem alvos provisórios do plano mestre até existirem dados anotados e o responsável aprovar/recalibrar. Não rotular idioma/backend como homologado com base somente em disponibilidade de modelo/wheel.

## 9. Registro de evidências e histórico

| Data/execução | Escopo | Resultado e limite |
|---|---|---|
| 10/11/2026 — primeiras execuções | Coletor, 7 testes, CLI, JSON e matriz Python/SO | 12 combinações anteriores passaram; era validação do coletor |
| 10/11/2026 — workflows #65/#66/#67 | Lock inicial, 12 combinações e POC FFmpeg/offset | POC de mídia e matriz passaram; o lock/manifesto foram posteriormente refinados |
| 10/11/2026 — workflow #69 | Primeiro benchmark com `datasets` | Falhou por incompatibilidade de dependências `datasets` 5.2 / Hugging Face Hub / WhisperX 3.8.6; dependência removida |
| 10/11/2026 — lock estável | Restrições e validador de lock | WhisperX restringido para versão estável 3.8.6; lock deve ser regenerado e validado depois da última revisão do manifesto |
| HEAD atual | Lock, instalação CPU/CUDA, FLEURS e docs de handoff | Verificar status de execução em [PR #1](https://github.com/anfalcir/legendar/pull/1) e [Actions](https://github.com/anfalcir/legendar/actions); registrar somente resultados concluídos |

## 10. Critério de passagem à Fase 1

A Fase 1 poderá começar depois de:
- [ ] PR #1 ser revisada e integrada à `main`;
- [ ] workflow do HEAD integrado estar verde;
- [ ] `uv.lock` corresponder ao manifesto e passar pelo validador;
- [ ] os dois perfis principais passarem instalação/importação CI;
- [ ] a POC smoke PT-BR/EN ter resultado publicado (sucesso ou falha diagnosticada, com limitação explícita);
- [ ] prova sintética FFmpeg/offset estar verde;
- [ ] `ESTADO_ATUAL.md`, `MATRIZ_DEPENDENCIAS.md`, plano e handoff estarem coerentes.

O gate de POC exige que seja possível executar o pipeline básico nos dois idiomas e que os resultados/limitações estejam disponíveis. Não exige aceitar o WhisperX como alinhador de produção sem avaliação humana: essa aprovação é da Fase 5.

---

## Referências primárias

- [WhisperX no PyPI](https://pypi.org/project/whisperx/)
- [WhisperX pyproject.toml](https://github.com/m-bain/whisperX/blob/main/pyproject.toml)
- [WhisperX alinhamento e limitações](https://github.com/m-bain/whisperX#limitations)
- [Google FLEURS dataset (CC-BY-4.0)](https://huggingface.co/datasets/google/fleurs)
- [OpenAI Whisper](https://github.com/openai/whisper)
- [PyTorch — instalação local](https://pytorch.org/get-started/locally/)
- [uv — lockfile/resolução](https://docs.astral.sh/uv/concepts/resolution/)
- [FFmpeg documentation](https://ffmpeg.org/documentation.html)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
