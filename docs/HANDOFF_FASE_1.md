# Handoff técnico — Fase 1 concluída

- **Projeto:** Legendar
- **Atualização:** 10/11/2026
- **Fase 0:** concluída, validada e integrada; workflow final #113 aprovado (16/16 jobs), com limitações explicitadas
- **Fase 1:** concluída tecnicamente; CI Python 3.10–3.13 verde (196 testes por ambiente, 88% cobertura); revisão técnica concluída; PR #2 aguarda integração
- **Branch de conclusão da Fase 0:** `phase-0/technical-inventory`
- **PR de integração:** [#1 — Fase 0: inventário, governança de dependências e prova técnica](https://github.com/anfalcir/legendar/pull/1), merged por squash
- **Commit na main:** `992cb874274e73d0264994e39926113f1461236f`
- **Regra de governança:** o repositório é a fonte de verdade das dependências e decisões; o computador de homologação não define sozinho os requisitos do produto.

Este documento registra a conclusão técnica da Fase 1. Não reiniciar a arquitetura nem antecipar funcionalidades das fases seguintes. A PR #2 reúne a entrega validada; a Fase 2 permanece bloqueada até aprovação explícita do responsável. Leia-o em conjunto com o [plano mestre](PLANO_REMODELAGEM.md), o [estado atual](ESTADO_ATUAL.md), o [plano operacional da Fase 1](FASE_1_PLANO.md), a [baseline legada](LEGACY_BASELINE.md), a [matriz de dependências](MATRIZ_DEPENDENCIAS.md) e o [protocolo da Fase 0](FASE_0_PROTOCOLO.md).

## Checkpoint atual da Fase 1

A branch de trabalho continua sendo `phase-1/architecture`, baseada no commit de integração
da Fase 0 (`992cb874274e73d0264994e39926113f1461236f`). O trabalho deste checkpoint inclui:

- `src/legendar/domain`: entidades, objetos de valor, erros, eventos e máquina de estados;
- `application`: protocolos, contexto de job/cancelamento, controlador, progresso e pipeline serial;
- `infrastructure`: parser de metadados ffprobe, descoberta de ferramentas, cache somente leitura
  de modelos, workspaces isolados, publicação SRT validada/atômica, configuração e logging;
- `presentation/qt`: view model, janela mínima e worker com eventos por sinais Qt;
- `bootstrap` e `python -m legendar`, além de testes unitários, de integração e GUI com fakes.

**Evidências finais:** workflow [Phase 1 quality #116](https://github.com/anfalcir/legendar/actions/runs/42905199857) aprovado em Python 3.10, 3.11, 3.12 e 3.13 (4/4 jobs); cada ambiente executou 196 testes, com cobertura total de 88%, `ruff check` e `ruff format --check` aprovados. O workflow [Phase 0 quality #160](https://github.com/anfalcir/legendar/actions/runs/42905199743) também aprovou 12 combinações Python/SO, o lock/perfis e a prova FFmpeg/ffprobe com preservação de offset; CUDA e o benchmark WhisperX foram pulados intencionalmente no evento PR, conforme a configuração dos workflows. 

Nesta fase foram adicionados nove testes de caracterização da baseline, testes de idempotência concorrente e cancelamento em operação, proteção de saída/cache, limpeza segura e verificações de fronteira. Corrigiu-se a compatibilidade Python 3.10/3.11 do worker antigo e o caminho MP3 em colisões. O cancelamento é sincronizado, é propagado pelas portas de processamento e pode encerrar o subprocesso ffprobe; a publicação SRT atômica permanece o ponto não cancelável. A política de legado/lint está em `docs/LEGACY_BASELINE.md`.

**Não restam gates técnicos da Fase 1.** A arquitetura ainda não processa mídia real, não integra Whisper/WhisperX concretos nem fornecedor de tradução; esses itens continuam corretamente alocados às fases 3–6. O legado `main.py`, `core/` e `gui/` permanece caracterizado e preservado até paridade/homologação. A Fase 2 segue não iniciada, aguardando aprovação explícita.

---

## 1. O que a Fase 0 encerrou

A Fase 0 concluiu as definições que permitem estruturar a aplicação sem manter decisões fundamentais em aberto:

1. Inventário reproduzível, sem dependências externas e sem leitura de conteúdo privado de mídia.
2. Manifesto canônico de dependências, grupos de desenvolvimento e perfis completos de runtime.
3. Lockfile universal versionado, com fontes explícitas de wheels PyTorch e restrição a WhisperX estável 3.8.6.
4. Governança de dependências externas e de runtimes auxiliares do YouTube.
5. Prova determinística de normalização mono/16 kHz e preservação de offsets da mídia.
6. POC automatizada de transcrição e alinhamento PT-BR/EN com um conjunto público pequeno e métricas reproduzíveis.
7. Decisões de arquitetura de pipeline, timestamp, tradução, cancelamento, temporários e limites de homologação registradas para a Fase 1.
8. Evidências finais da CI registradas: workflow #109 com 16/16 jobs aprovados, lock validado, 12 combinações Python/SO aprovadas, instalação CPU/CUDA 12.8, POC FFmpeg/offset e smoke benchmark FLEURS PT-BR/EN publicado.

**Importante:** a conclusão da Fase 0 significa que a direção técnica e os contratos arquiteturais iniciais estão suficientemente definidos e que as provas automatizadas de viabilidade planejadas passaram. Não significa que toda a qualidade de reconhecimento/alinhamento já foi homologada para produção, nem que todos os sistemas operacionais e backends foram validados como suportados. A PR #1 foi integrada e a branch `phase-1/architecture` está pronta; os itens que dependem de anotação humana e do hardware-alvo permanecem como gates das fases de integração, alinhamento e homologação, conforme a seção 7.

## 2. Decisões técnicas consolidadas

### 2.1. Python e governança

- Fonte de requisitos diretos: `pyproject.toml`.
- Fonte de resolução reproduzível: `uv.lock`.
- Ferramenta de gerenciamento: `uv`; não é dependência de runtime do aplicativo.
- Python declarado: `>=3.10,<3.14`.
- A faixa superior existe por compatibilidade declarada pelo WhisperX estável adotado; não foi escolhida com base no Python instalado no computador-alvo.
- `requirements.txt` continua identificado como snapshot legado. Não atualizá-lo manualmente nem usá-lo como uma segunda fonte de verdade. Remover ou gerar exportação depois da migração do produto, mediante teste.
- Instalações deverão ocorrer em ambientes isolados e com `uv sync --locked`. Não instalar, atualizar ou remover dependências globalmente no computador do usuário.

### 2.2. Perfis completos de runtime

Instalar exatamente um perfil por ambiente:

| Perfil | Plataformas/seleção | Conteúdo |
|---|---|---|
| `runtime-cpu` | Linux/Windows: wheels PyTorch CPU explícitos; macOS: wheels PyPI, com MPS apenas quando o ambiente oferecer suporte | PySide6 base, Whisper, yt-dlp, yt-dlp-ejs, PyTorch/torchvision/torchaudio e WhisperX estável |
| `runtime-cu128` | Linux/Windows com driver/hardware compatíveis | Mesmo conjunto, selecionando wheels oficiais PyTorch CUDA 12.8 |

Comandos:

```bash
uv sync --locked --no-dev --extra runtime-cpu
uv sync --locked --no-dev --extra runtime-cu128
```

O segundo comando é para Linux/Windows compatíveis e não deve ser utilizado no macOS. O manifesto declara os extras conflitantes para impedir que variantes CPU e CUDA sejam instaladas juntas.

Versões/faixas críticas atualmente declaradas:

- PySide6: `>=6.9,<7`.
- openai-whisper: `>=20250625`.
- yt-dlp: `>=2025.4.30`.
- yt-dlp-ejs: `>=0.8,<1`.
- PyTorch: `>=2.8,<2.9`.
- torchvision: `>=0.23,<0.24`.
- torchaudio: `>=2.8,<2.9`.
- WhisperX: `>=3.8.6,<3.8.7` — faixa deliberada para excluir a pré-release 3.8.7rc1.

A geração anterior de lock selecionou 3.8.7rc1 apesar da descrição anterior mencionar stable-only. Essa inconsistência foi identificada e corrigida restringindo o intervalo do WhisperX. A CI deve garantir que o lock contenha 3.8.6, nunca RC/pré-release.

ROCm 7.2 não é um perfil completo disponível nesta fase: o índice testado oferece PyTorch a partir de 2.11, incompatível com a faixa 2.8.x exigida pelo WhisperX 3.8.6. Não forçar prerelease ou override para contornar o conflito. Reavaliar somente com compatibilidade upstream estável ou substituição tecnicamente homologada do alinhador.

### 2.3. Dependências externas

- `ffmpeg` e `ffprobe` são executáveis externos obrigatórios para entrada e preparação de mídia. Não são substituídos por pacotes Python.
- `yt-dlp-ejs` é dependência Python declarada para o fluxo EJS do yt-dlp.
- Deno é o runtime JavaScript preferencial a detectar no preflight do fluxo YouTube; Node pode ser identificado como alternativa conforme a compatibilidade exigida pela versão do yt-dlp. Não instalar runtimes do sistema silenciosamente.
- Modelos Whisper e alinhadores são artefatos de runtime: cache/download sob demanda, com origem, nome, versão/revisão, licença e local de armazenamento documentados.
- stable-ts não foi adotado: o repositório foi arquivado e não há ganho comparativo comprovado que justifique torná-lo dependência do produto.

### 2.4. Reconhecimento e alinhamento

- Whisper permanece como motor de reconhecimento candidato principal.
- WhisperX estável 3.8.6 é o alinhador inicial candidato para arquitetura e POC.
- Idiomas de prioridade para homologação: português brasileiro (`pt`) e inglês (`en`).
- Reconhecer um idioma não significa que o alinhamento desse idioma esteja homologado.
- Falha parcial de alinhamento deve ser representada explicitamente; não fabricar timestamps.
- Usar o modelo Whisper multilingue em avaliação conjunta PT/EN. Modelos maiores poderão ser comparados depois; não presumir que `tiny` seja modelo final.

### 2.5. Normalização e linha temporal

O formato interno inicial validado é WAV PCM signed 16-bit, mono, 16 kHz. A transformação remove metadados do novo WAV, mas a aplicação deverá preservar separadamente a referência à origem temporal.

Regra de conversão:

```text
timestamp_global =
    source_stream_offset
    + chunk_offset
    + timestamp_local_do_alinhador
```

- Todos os valores devem ser finitos e os intervalos devem satisfazer `0 <= start < end <= duração` dentro de tolerância definida.
- Registrar índice global do stream selecionado, time base, offset original e metadados do chunk.
- Não somar offsets mais de uma vez.
- Não descartar a origem temporal ao normalizar para WAV.
- Em chunks, preservar offset global e overlap; deduplicar palavras do overlap de forma determinística.
- A prova sintética FFmpeg valida um offset não-zero e a regra de mapeamento, mas ainda não cobre todas as variações de contêiner, stream e codec.

### 2.6. Tradução

Decisão para a Fase 1: definir uma porta/interface de tradução, sem escolher ou integrar um fornecedor concreto nesta fase.

Política funcional:
- A transcrição original permanece disponível e não é sobrescrita pelo texto traduzido.
- Tradução é opcional e só executada quando idioma final difere do idioma de origem.
- Enviar somente texto e contexto estritamente necessário; não enviar áudio ao serviço de tradução.
- Cada segmento traduzido mantém referência ao(s) segmento(s) original(is) e ao intervalo temporal de origem.
- A segmentação traduzida pode diferir da segmentação original, mas o sistema não pode inventar timestamps de palavra para texto traduzido sem alinhamento com áudio no idioma de destino.
- Saída do provedor deverá ser estruturada, validada e limitada em tamanho; erros, limites, timeout e indisponibilidade terão tratamento explícito.
- Seleção de provedor, custo, condições de privacidade, política de retenção e uso de credenciais ficam para decisão formal antes da Fase 6, quando o contrato estiver definido e houver comparação atualizada. Não adicionar chave de fornecedor no código nem persistir secrets em texto puro.

### 2.7. Hardware de homologação

O inventário recebido em 10/11/2026 identificou:

- CPython 3.12.3, Linux x86_64.
- AMD Ryzen 3 2200G, quatro CPUs lógicas.
- 12,59 GiB de RAM total.
- 165,60 GiB livres na unidade consultada.
- FFmpeg/ffprobe não encontrados naquele interpretador/ambiente.
- Sem NVIDIA detectada pelo `nvidia-smi`; a Radeon Vega integrada não deve ser tratada como ROCm suportado.

Este é um perfil de homologação CPU e não limita o produto. Reexecutar o coletor atualizado e testar instalação nesse computador antes da integração de mídia/modelos. Não prometer tempo real nem desempenho de modelos grandes sem benchmark.

## 3. Arquitetura alvo a estabelecer na Fase 1

A Fase 1 deverá separar responsabilidades e definir contratos antes da implementação de funcionalidades reais. A estrutura pode ser ajustada mediante inspeção da baseline, mas deverá preservar esta separação:

```text
src/legendar/
  domain/
    entities/
    value_objects/
    events/
    errors/
  application/
    ports/
    use_cases/
    pipeline/
    state/
  infrastructure/
    media/
    downloads/
    speech/
    alignment/
    translation/
    settings/
    filesystem/
  presentation/
    qt/
      windows/
      dialogs/
      view_models/
      workers/
  bootstrap/
tests/
  unit/
  integration/
  gui/
docs/
```

Responsabilidades:

- **domain:** entidades, valores, estados e invariantes sem dependência de Qt, FFmpeg, Whisper ou serviços externos.
- **application:** casos de uso, orquestração do pipeline, portas/interfaces e políticas de cancelamento/progresso.
- **infrastructure:** implementações concretas de mídia, downloader, reconhecimento, alinhamento, tradução, configurações e filesystem.
- **presentation:** PySide6, views, view models/controllers e workers. A camada de domínio não deve importar Qt.
- **bootstrap:** composição explícita das dependências e inicialização da aplicação.

### 3.1. Contratos mínimos a definir

1. `MediaSource`: origem local ou YouTube sem misturar UI e download.
2. `MediaInfo` e `AudioStreamInfo`: duração, streams, codecs, time base, offset e stream selecionado.
3. `AudioAsset`: caminho temporário, formato/sample rate/canais e mapeamento para timeline de origem.
4. `Transcript`, `TranscriptSegment` e `TranscriptWord`: texto, idioma, origem, confiança quando disponível e timestamps opcionais.
5. `AlignmentResult`: palavras alinhadas, não alinhadas e diagnósticos; falha parcial não deve ser convertida em sucesso integral.
6. `SubtitleCue`: texto, intervalo, idioma e referências aos segmentos/words de origem.
7. `TranslationRequest/Result`: texto e contexto autorizado, locale de origem/destino e referências temporais; nenhuma dependência de fornecedor no domínio.
8. `JobContext`: ID, diretório exclusivo, cancelamento, progresso, logger e checkpoints seguros.
9. `PipelineState`: transições válidas, estado atual e motivo de falha/cancelamento.
10. `SrtWriter/Validator`: writer puro e validador determinístico para UTF-8, numeração, timestamps, limites e ordem.

Não criar abstrações genéricas sem consumidor real. Interfaces devem proteger fronteiras instáveis (Qt, subprocessos, modelos, rede, filesystem), não transformar cada classe em um framework.

### 3.2. Pipeline e estados

Definir um único pipeline serial por instância no escopo inicial:

```text
IDLE
  -> VALIDATING_INPUT
  -> INSPECTING_MEDIA
  -> PREPARING_AUDIO
  -> TRANSCRIBING
  -> ALIGNING
  -> SEGMENTING
  -> TRANSLATING (optional)
  -> VALIDATING_SRT
  -> PUBLISHING
  -> COMPLETED

Qualquer etapa cancelável -> CANCELLING -> CANCELLED
Falha -> FAILED
```

- UI não executa processamento pesado nem espera bloqueante.
- Workers não atualizam widgets diretamente; emitem sinais/eventos tipados para a thread principal.
- Clique duplo, sinais duplicados e reentrada devem ser idempotentemente bloqueados.
- Cancelamento é cooperativo, com pontos seguros. Publicação final deve ser atômica; não cancelar depois que a troca atômica já foi confirmada.
- Só um job ativo por instância na primeira versão.
- Cada job usa diretório temporário exclusivo; não limpar cache de modelos compartilhado para cancelar um job.
- Erros devem ser categorizados e traduzidos para mensagens claras na camada de apresentação.

### 3.3. Estratégia de testes para a Fase 1

- Criar testes de caracterização da baseline antes de remover fluxos antigos.
- Unit tests para entidades, transições, validação temporal e regras puras.
- Tests para serialização/configuração e mapeamento de timeline.
- Testes de integração com FFmpeg/ffprobe simulados ou fixtures sintéticas; sem baixar modelos no suite unitária.
- GUI tests com pytest-qt somente para comportamentos de tela/estado, não inferência real.
- Usar fake implementations de downloader/transcriber/aligner/translator para provar o pipeline e cancelamento sem modelo.
- CI executa em lockfile. Nenhum teste dependente de áudio público ou download de modelo deverá ser colocado na suite rápida dos 12 cenários multiplataforma.
- Model POC de FLEURS deve ser job separado/controlado e seus artefatos são evidência, não fixture runtime do aplicativo.

## 4. Não fazer na Fase 1

- Não implementar o refinamento visual completo da GUI (Fase 2).
- Não integrar todo o processamento real do YouTube/FFmpeg (Fase 3).
- Não executar Whisper ou WhisperX em cada teste unitário.
- Não implementar tradução de fornecedor específico.
- Não construir editor de vídeo, histórico, nuvem, diarização ou multi-job.
- Não expandir suporte de SO/backend com base apenas no sucesso dos testes do coletor.
- Não criar/editar lockfile manualmente.
- Não atualizar `requirements.txt` como alternativa ao manifesto.
- Não mover segredos para arquivos versionados.
- Não misturar o código legado com a arquitetura nova sem caracterização e plano de remoção.

## 5. Critérios de aceite da Fase 1

Status detalhado por critério, com pendências marcadas, está no [plano da Fase 1](FASE_1_PLANO.md).
Já há evidência local para domínio/fronteiras, máquina de estados, pipeline com fakes,
cancelamento/progresso/publicação, temporários/cache, configuração, inicialização offscreen e
caracterização da baseline legada. A estratégia de convivência, preservação e futura aposentadoria
está documentada; a política de Ruff e o workflow próprio da Fase 1 também foram implementados.
Não restam pendências de implementação ou validação atribuídas à Fase 1. A PR #2 aguarda integração;
a janela continua mínima por decisão de escopo — a interface profissional pertence à Fase 2.

## 6. Instrução operacional para a próxima IA

1. Leia `README.md`, `docs/PLANO_REMODELAGEM.md`, `docs/ESTADO_ATUAL.md` e o [plano da Fase 1](FASE_1_PLANO.md) antes de qualquer mudança.
2. Trate a Fase 1 como concluída; não recrie pacotes, não reabra decisões já aprovadas sem nova evidência e não refaça os gates verdes.
3. Preserve `main.py`, `core/` e `gui/` conforme `LEGACY_BASELINE.md` até que exista paridade homologada nas fases de produto.
4. Mantenha a política Ruff definida em `LEGACY_BASELINE.md`: lint estrito sobre a arquitetura e testes mantidos, sem reformatação incidental do legado/histórico.
5. Preserve os workflows de Fase 0 e Fase 1. Mudanças futuras não devem enfraquecer seus gates nem misturar testes de produto com POCs controladas.
6. A próxima entrega de produto é a Fase 2 — interface profissional — mas só poderá começar depois de aprovação explícita do responsável.

**Mensagem de orientação:** a Fase 0 não autorizou a implementação de todas as funcionalidades. Ela autorizou construir a estrutura arquitetural que mantém essas funcionalidades isoladas, testáveis e substituíveis. Preserve decisões e gates acima; quando houver evidência nova que contradiga uma decisão, documente a evidência e proponha alteração, não faça mudança silenciosa.

## 7. Validações que continuam obrigatórias depois da Fase 1

Essas pendências não bloqueiam a criação da arquitetura, mas bloqueiam a aprovação de funcionalidades dependentes:

| Quando | Validação necessária |
|---|---|
| Antes da Fase 3 | Reexecutar inventário no computador-alvo; instalar/identificar FFmpeg e ffprobe; verificar espaço de cache e runtime JS |
| Durante a Fase 3 | Homologar contêineres, codecs, múltiplas faixas, offsets, arquivos longos, interrupção e retomada segura |
| Durante a Fase 4 | Comparar modelos Whisper em PT-BR/EN com corpus representativo e transcrição revisada; medir WER/CER, latência e memória no computador-alvo |
| Durante a Fase 5 | Anotar manualmente timestamps de palavras em trechos PT-BR/EN; medir erro mediano e P95; verificar cobertura, palavras não alinhadas, música, ruído e fala sobreposta |
| Antes da Fase 6 | Escolher serviço/provedor de tradução com comparação de qualidade, preço, privacidade, retenção, limites e falhas; aprovar política de dados |
| Durante a Fase 8 | Homologar fluxos completos no hardware/SO declarados como suportados; não extrapolar a matriz do coletor para o aplicativo |

O benchmark público FLEURS fornece uma referência lexical inicial para comparar PT-BR e inglês. Ele é composto por fala lida e não deve ser tratado como corpus representativo de pregações, música de fundo ou fala espontânea. WER mede transcrição; não mede precisão temporal. A aceitação de alinhamento requer referências de tempo anotadas manualmente.
