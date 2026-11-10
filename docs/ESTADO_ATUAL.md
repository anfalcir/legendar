# Estado atual do Legendar

- **Última atualização:** 10/11/2026
- **Repositório:** anfalcir/legendar
- **Branch de referência:** main
- **Visibilidade verificada:** privada
- **Fase atual:** Fase 0 — Definições e prova técnica (em andamento)
- **Fonte de verdade:** este documento para progresso; PLANO_REMODELAGEM.md para escopo e critérios

> Este é um documento vivo. Atualize-o ao iniciar/concluir fases, aprovar decisões, executar testes ou identificar bloqueios. Não marque como concluído algo que não tenha evidência verificável.

---

## 1. Resumo executivo

O repositório foi limpo e o plano mestre de remodelagem foi registrado. A remodelagem funcional ainda não começou.

A aplicação existente é uma base legada pequena em Python/PySide6, com integração básica ao Whisper, yt-dlp e FFmpeg. O comportamento atual ainda está orientado à geração de transcrições em texto, não à produção de SRT temporizado e traduzido.

A Fase 0 foi iniciada em 10/11/2026 em uma branch isolada. A primeira entrega estabelece coleta reproduzível do ambiente e um protocolo de prova técnica. Ainda não foram executados benchmarks de Whisper/WhisperX no computador-alvo nem homologados idiomas, modelos ou dependências experimentais.

**Estado do produto:** baseline preservada; Fase 0 em andamento; nenhuma fase de implementação funcional da remodelagem aprovada como concluída.

## 2. Situação do repositório

| Item | Estado observado |
|---|---|
| Repositório | anfalcir/legendar |
| Visibilidade | Privada, confirmada na API do GitHub em 09/11/2026 |
| Branch padrão | main |
| Histórico da main | Baseline e documentação preservadas; a execução da Fase 0 ocorre em branch separada |
| Diretórios de testes | Criados para a Fase 0; testes de domínio e pipeline ainda inexistentes |
| Diretório docs | Contém plano mestre, estado vivo, protocolo da Fase 0 e matriz/política de dependências |
| Configuração de projeto | pyproject.toml como fonte canônica; perfis completos runtime-cpu/runtime-cu128; ROCm 7.2 bloqueado pela incompatibilidade com WhisperX estável; uv.lock universal pendente de resolução/inspeção; requirements.txt é snapshot legado transitório |
| Licença | MIT, conforme informado pelo responsável; o arquivo LICENSE não estava presente na baseline inspecionada e precisa ser restaurado com o aviso original apropriado antes da distribuição |
| Releases/tags | Nenhuma identificada na última inspeção |
| CI | Nenhum workflow encontrado na árvore verificada e nenhuma execução de Actions registrada |

A documentação inicial foi publicada no commit f5101b0f587fd545aadcea93e0cc3d0b96c3e5df. A revisão estrutural foi publicada em ba8a34a04be899ea22f6fe4779eab76003757769. A estrutura proposta mantém src/legendar como pacote de aplicação e deixa tests/, docs/ e resources/ na raiz do projeto. O README aponta para o plano, o estado vivo e o protocolo da Fase 0. A branch de execução atual é `phase-0/technical-inventory`.

## 3. Baseline técnica identificada

### 3.1. Arquivos existentes antes da documentação

    .gitignore
    README.md
    core/
      __init__.py
      instagram.py
      transcription.py
      youtube.py
    gui/
      __init__.py
      styles.py
      ui_main.py
      worker.py
    main.py
    requirements.txt

### 3.2. Capacidades atuais identificadas por inspeção

| Área | Situação da baseline |
|---|---|
| Interface | PySide6; janela principal simples com abas YouTube e Arquivo MP4 |
| YouTube | Integração existente com yt-dlp |
| Arquivo local | Fluxo de seleção e transcrição de MP4 |
| Whisper | Integração existente com modelo base |
| FFmpeg | Caminho local ffmpeg/bin ou PATH |
| Saída | Arquivo TXT |
| Alinhamento por palavra | Não implementado |
| WhisperX | Não integrado |
| VAD | Não integrado como etapa própria |
| Tradução EN/PT-BR | Não implementada |
| Geração SRT | Não implementada |
| Validador SRT | Não implementado |
| Seleção de faixa de áudio | Não implementada |
| Progresso por etapa | Parcial e ainda não estruturado como pipeline |
| Logs | Área de texto simples na interface |
| Máquina de estados | Não identificada como componente explícito |
| Cancelamento cooperativo | Não implementado de forma completa |
| Cache isolado por job | Não implementado |
| Testes automatizados | Baseline sem suíte; branch Fase 0 adiciona 7 testes unittest para o coletor de ambiente; CI ampliada para Python 3.10–3.13 em Linux, Windows e macOS |
| Documentação técnica | README, plano mestre, estado vivo e protocolo de execução da Fase 0 |

### 3.3. Pontos técnicos da baseline que exigem revisão

- O worker de processamento contém pausas artificiais e lógica de limpeza de cache compartilhado. Isso deverá ser removido e substituído por gerenciamento isolado por job.
- A interface utiliza atualização manual de eventos em um ponto do fluxo. A arquitetura nova deverá usar sinais/eventos sem bloquear a thread principal.
- O processamento atual não tem uma máquina de estados completa, política consistente de cancelamento ou progresso estruturado.
- Há uma integração de Instagram simbólica/incompleta, que não faz parte do escopo futuro e deverá ser removida durante a reorganização, depois de confirmar que nenhuma dependência funcional a utiliza.
- A lista atual de dependências precisa ser auditada, simplificada e compatibilizada com WhisperX/alinhadores e ambiente-alvo.
- O formato atual de saída TXT deverá deixar de ser o objetivo principal; o produto final terá SRT.

Esses itens são observações de inspeção da baseline, não evidência de falha em todos os cenários de execução. A primeira fase deverá estabelecer testes reproduzíveis antes de substituir comportamentos.

## 4. Roadmap e status das fases

| Fase | Status | Observação |
|---|---|---|
| 0 — Definições e prova técnica | **Em andamento** | Inventário inicial recebido; perfis CPU/CUDA explícitos; ROCm bloqueado por incompatibilidade de versões upstream; lock universal em nova validação na CI; FFmpeg e POCs pendentes |
| 1 — Reestruturação arquitetural | Não iniciada | Depende da aprovação dos resultados da Fase 0 |
| 2 — Interface profissional | Não iniciada | Começar com workers simulados para validar os estados |
| 3 — Entrada e preparação de mídia | Não iniciada | Incluir YouTube, formatos locais, streams e offsets |
| 4 — Reconhecimento Whisper | Não iniciada | Manter idioma original |
| 5 — Alinhamento temporal | Não iniciada | WhisperX candidato principal; validar PT-BR e EN |
| 6 — Tradução, segmentação e SRT | Não iniciada | Definir provedor de tradução e regras de vínculo temporal |
| 7 — Integração de ponta a ponta | Não iniciada | Progresso real, cancelamento e recuperação |
| 8 — Testes e homologação | Não iniciada | Métricas temporais e testes E2E |
| 9 — Documentação e finalização | Em preparação | Plano mestre e estado vivo registrados; documentação final ainda dependerá da implementação |

**Regra:** status de fase só poderá mudar para concluída quando os critérios de saída do plano mestre tiverem sido verificados. A documentação inicial não significa que a Fase 9 esteja concluída.

## 5. Decisões já estabelecidas

### Confirmadas como direção do produto

- Aplicação desktop de uso pessoal.
- Repositório privado.
- PySide6 permanece como framework de interface, salvo evidência técnica contrária.
- Whisper permanece como motor central de reconhecimento de fala.
- Fontes: URL do YouTube e arquivo local de áudio/vídeo.
- Saída principal: SRT.
- Idiomas finais: inglês e português brasileiro.
- Idioma de origem detectado automaticamente, com correção manual.
- Interface com confirmação, bloqueio de controles, cancelamento controlado, progresso honesto e log recolhível.
- Escopo enxuto; sem editor de vídeo, banco de dados de projetos, nuvem ou múltiplos jobs simultâneos na primeira versão.

### Recomendações técnicas ainda sujeitas à prova/decisão

- WhisperX como primeiro candidato a forced alignment.
- stable-ts permanece apenas como referência comparativa condicionada a benefício mensurável; o repositório upstream foi arquivado em 30/05/2026.
- VAD para apoiar delimitação de fala e tratamento de silêncios.
- Serviço de tradução contextual único, encapsulado por interface.
- WAV PCM mono 16 kHz como formato interno inicial a validar.
- QSettings para preferências simples.
- Diretório temporário por job e publicação atômica de SRT.
- CPU como caminho de compatibilidade quando suportado; CUDA, ROCm e MPS como perfis opcionais e independentes, sujeitos à homologação.
- pytest, pytest-qt, pytest-cov e Ruff como conjunto candidato de qualidade.

## 6. Fase 0 — definições e prova técnica (em andamento)

### Objetivo

Reduzir os maiores riscos técnicos antes de estruturar a aplicação nova: qualidade de alinhamento, suporte de idioma, compatibilidade das dependências do produto em diferentes ambientes, custo/privacidade da tradução e desempenho em perfis de hardware representativos.

**Diretriz de arquitetura de dependências:** o repositório é a fonte de verdade dos requisitos de software. O equipamento atual é um perfil de homologação; não define sozinho o conjunto de dependências nem limita os sistemas e backends que o produto poderá suportar. A seleção de wheels PyTorch faz parte do perfil runtime; uma resolução genérica contra PyPI que introduza CUDA/NVIDIA sem seleção explícita foi descartada.

### Entregáveis iniciais implementados na branch `phase-0/technical-inventory`

- `scripts/phase0_inventory.py`: coletor somente leitura, sem dependências externas, com informações de Python, distribuição Linux, CPU, RAM, armazenamento, controladores gráficos PCI em Linux, FFmpeg/ffprobe, NVIDIA e versões dos pacotes relevantes.
- `tests/test_phase0_inventory.py`: sete testes automatizados com `unittest`, incluindo parsing de `os-release` e detecção de gráficos PCI AMD.
- `pyproject.toml`: manifesto canônico para dependências-base, perfis completos `runtime-cpu` e `runtime-cu128`, extra `alignment-whisperx`, índices PyTorch explícitos e grupos de desenvolvimento.
- `docs/MATRIZ_DEPENDENCIAS.md`: política de governança, comandos de instalação por perfil, faixas de versão, requisitos externos e estratégia de compatibilidade.
- `docs/FASE_0_PROTOCOLO.md`: histórico das resoluções experimentais e incompatibilidade upstream que impede oferecer ROCm 7.2 com WhisperX estável 3.8.6.

- `docs/FASE_0_PROTOCOLO.md`: comandos, política de privacidade, inventário recebido, análise de compatibilidade, matriz experimental, métricas e critérios de saída.
- `.github/workflows/phase0-quality.yml`: CI ampliada para Python 3.10–3.13 em Linux, Windows e macOS (execuções desta matriz pendentes).
- README atualizado para apontar para a matriz e o protocolo.

### Validação realizada nesta entrega

| Verificação | Resultado | Limite da evidência |
|---|---|---|
| `python -m compileall -q scripts tests` | Aprovado | Executado no ambiente de desenvolvimento desta entrega |
| `python -m unittest discover -s tests -v` | 7 testes aprovados na CI | Testes do coletor; não cobrem Whisper, alinhamento ou GUI |
| Execução do coletor e parsing do JSON | Aprovado na CI | Smoke test no runner Ubuntu; o inventário real do computador-alvo foi recebido separadamente |
| Manifesto e instalação de dependências | `pyproject.toml` declara perfis backend explícitos; nenhuma instalação no ambiente do usuário; primeira resolução PyPI descartada por incluir CUDA no perfil implícito; novo `uv.lock` em validação pela CI |

O ambiente de desenvolvimento usado para validar o script não deve ser confundido com o ambiente-alvo. O primeiro inventário do computador-alvo foi recebido em 10/11/2026 e está documentado em `docs/FASE_0_PROTOCOLO.md`. Como esse relatório foi gerado antes da ampliação do coletor, ainda falta repetir a coleta para obter a distribuição Linux e os IDs PCI/driver da Radeon. O hardware recebido é um perfil real de desempenho e implantação; não será usado para restringir os requisitos de software do produto.

### Atividades pendentes

1. Reexecutar o coletor atualizado no computador-alvo para registrar distribuição, GPU/driver PCI e confirmar o runtime Python usado; esse resultado complementará o perfil de implantação, não redefinirá os requisitos do produto.
2. Instalar/validar FFmpeg e ffprobe no ambiente de teste; ainda não foram encontrados no inventário enviado.
3. Resolver os perfis `runtime-cpu` e `runtime-cu128` em ambientes isolados; inspecionar os índices/wheels selecionados e gerar `uv.lock` universal sem misturar variantes de backend. Reavaliar ROCm quando a compatibilidade PyTorch/WhisperX tiver versão estável compatível.
4. Executar CI de compatibilidade para Python 3.10–3.13 e Linux/Windows/macOS nos componentes multiplataforma; a CI do coletor não vale como homologação da aplicação completa nem do stack Whisper/PyTorch.
5. Criar amostras próprias/autorizadas em PT-BR e inglês, transcrições de referência e marcações temporais revisadas manualmente.
6. Testar Whisper e WhisperX em perfis CPU e acelerados quando houver infraestrutura compatível; medir qualidade, tempo e memória em mais de um perfil representativo.
7. Avaliar normalização, streams, offsets, chunks e comportamento com números, siglas, música e fala sobreposta.
8. Avaliar opções de tradução contextual, custo, privacidade, limites e formato estruturado; consolidar decisões antes da Fase 1.

O protocolo executável e os comandos estão em [docs/FASE_0_PROTOCOLO.md](FASE_0_PROTOCOLO.md).

### Critério de saída da Fase 0

- POC reproduzível para PT-BR e inglês.
- Transcrição e alinhamento avaliados contra referências humanas.
- Limitações e idiomas suportados documentados.
- Estratégia de chunking/offset definida para mídias longas.
- Estratégia de tradução escolhida ou decisão de adiar tradução externa justificada.
- Dependências e ambiente compatíveis documentados.
- Metas de sincronização confirmadas ou recalibradas com evidência.
- Aprovação do responsável pelo projeto para iniciar a Fase 1.

## 7. Registro de testes e evidências

| Data | Escopo | Resultado | Evidência |
|---|---|---|---|
| 09/11/2026 | Inspeção da árvore e documentação inicial | Plano e estado preparados; ainda não havia testes de remodelagem | Verificação da baseline no GitHub |
| 10/11/2026 | Coletor da Fase 0 e CI inicial | `compileall`, 7 testes `unittest`, CLI e JSON smoke test aprovados no workflow `Phase 0 quality`; inventário do computador-alvo recebido; sem benchmark de modelos | [PR #1](https://github.com/anfalcir/legendar/pull/1) |
| 10/11/2026 | Governança de dependências | `pyproject.toml` e matriz de dependências adicionados; `requirements.txt` classificado como snapshot legado; `uv.lock` condicionado à validação do stack e das plataformas | [PR #1](https://github.com/anfalcir/legendar/pull/1) |
| 10/11/2026 | Perfis PyTorch | Perfis runtime explícitos para CPU e CUDA 12.8 mantidos. Primeira resolução PyPI descartada por incluir libs CUDA/NVIDIA implicitamente; segunda resolução identificou conflito entre PyTorch ROCm 7.2 (>=2.11) e WhisperX 3.8.6 (>=2.8,<2.9), por isso ROCm não é oferecido como perfil runtime nesta versão | [PR #1](https://github.com/anfalcir/legendar/pull/1) |

**Nenhum teste funcional da nova arquitetura foi executado até esta atualização.** Não há ainda evidência de homologação do SRT, WhisperX, tradução, cancelamento ou formatos além dos fluxos atuais da baseline.

Quando testes forem executados, registrar:

- Comando ou cenário.
- Versões e ambiente.
- Fixture utilizada.
- Resultado observado.
- Métrica e limite esperado.
- Falhas e correções.
- Link para CI ou commit, quando houver.

## 8. Riscos e pendências

| ID | Risco/pendência | Tratamento |
|---|---|---|
| R-01 | Forced alignment pode não suportar igualmente todos os idiomas | Matriz de modelos e idiomas na Fase 0 |
| R-02 | Texto reconhecido incorretamente compromete o alinhamento | Separar qualidade textual e temporal; sinalizar inconsistências |
| R-03 | Tradução mais longa não cabe no intervalo original | Segmentar por âncoras de fala; não distribuir tempos artificialmente |
| R-04 | Offset e chunking podem deslocar ou duplicar legendas | Preservar time base, offset e origem global de cada chunk |
| R-05 | Modelos grandes podem exigir recursos excessivos | Benchmark CPU/GPU, cache e perfis de execução |
| R-06 | Dependências Whisper/PyTorch/WhisperX podem conflitar | POC em ambiente isolado e versões fixadas |
| R-07 | Falha ou cancelamento pode deixar arquivos incompletos | Diretório por job e publicação atômica |
| R-08 | Serviço externo de tradução implica custo e transmissão de texto | Escolher provedor conscientemente e documentar dados enviados |
| R-09 | Formatos e codecs variam por instalação de FFmpeg | Inspecionar streams e manter matriz de formatos homologados |
| R-10 | Arquivo LICENSE não estava presente na baseline inspecionada | Recuperar/restaurar aviso MIT apropriado e validar dependências/licenças antes de distribuição |
| R-11 | Distribuição Linux e driver gráfico do equipamento-alvo ainda não foram confirmados; WhisperX/PyTorch precisam de resolução de versões específica | Reexecutar o coletor ampliado; resolver dependências em ambiente virtual isolado; não alterar `requirements.txt` por tentativa |
| R-12 | Ryzen 3 2200G com Radeon Vega não aparece como APU oficialmente suportada na matriz Linux ROCm 7.2.1 consultada | Planejar homologação em CPU; não depender de ROCm; reavaliar somente se surgir evidência oficial/compatível |
| R-13 | FFmpeg/ffprobe não foram encontrados no computador-alvo | Instalar por canal do sistema operacional após identificar a distribuição; verificar `ffmpeg -version` e `ffprobe -version` antes das POCs de mídia |
| R-14 | Resolução PyTorch/WhisperX varia por Python, SO, arquitetura e backend; PyPI pode resolver wheels CUDA sem seleção explícita; PyTorch ROCm 7.2 disponível exige versão incompatível com WhisperX 3.8.6 | Usar índices oficiais explícitos por perfil; validar perfis em ambientes isolados; não anunciar ROCm como runtime completo até compatibilidade upstream; inspecionar o lock universal |
| R-15 | `requirements.txt` contém um snapshot antigo, com pins transitivos e plataformas misturadas | Migrar para `pyproject.toml` + `uv.lock`; remover ou gerar exportação do snapshot somente após instalação limpa e homologação |

## 9. Regras de atualização deste documento

A cada avanço, atualizar:

1. Data da última atualização.
2. Fase atual e status de cada fase.
3. Entregáveis concluídos e pendentes.
4. Decisões aprovadas, rejeitadas ou ainda abertas.
5. Testes executados, com evidências.
6. Bugs, riscos e bloqueios.
7. Próxima ação objetiva.

Use os status: **Não iniciada**, **Em andamento**, **Bloqueada**, **Concluída** e **Aprovada**. Uma fase pode estar concluída tecnicamente e aguardar aprovação; nesse caso, não a marque como aprovada.

Não registrar como concluído somente porque o código foi escrito ou porque um workflow iniciou. Exigir resultado verificável.

## 10. Histórico de atualizações

| Data | Atualização |
|---|---|
| 09/11/2026 | Criados o plano mestre de remodelagem e o documento vivo de estado inicial. README conectado à documentação; estrutura proposta revisada. Nenhuma fase de implementação funcional iniciada. |
| 10/11/2026 | Iniciada a Fase 0 em branch separada: coletor de ambiente, sete testes automatizados, protocolo experimental, CI e README. Inventário do computador-alvo recebido (Ryzen 3 2200G, 4 CPUs lógicas, 12,59 GiB RAM, Python 3.12.3; FFmpeg/PyTorch ausentes no runtime). CPU é um perfil de homologação e não limita os requisitos globais do produto. |
| 10/11/2026 | Manifesto de dependências adicionado: `pyproject.toml` é a fonte canônica de dependências diretas; `docs/MATRIZ_DEPENDENCIAS.md` define a política; lockfile pendente da validação multiplataforma e dos backends PyTorch. |
