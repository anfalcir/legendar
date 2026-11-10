# Plano operacional — Fase 3: Entrada e preparação de mídia

- **Status:** implementação desenvolvida; validação final em andamento (não concluída, sem PR/merge)
- **Branch:** `phase-3/media-ingestion`
- **Base:** `main` com Fases 0, 1 e 2 integradas (Fase 2: `4129f0a`)
- **Escopo:** aquisição de fonte, inspeção, seleção de faixa, normalização de áudio e isolamento/limpeza dos artefatos de mídia
- **Limites:** sem Whisper/WhisperX, transcrição, alinhamento, tradução ou publicação SRT final

## 1. Objetivo

Implementar os fluxos reais de entrada previstos no roadmap: arquivos locais de áudio/vídeo e URLs do YouTube. Inspecionar contêineres e streams com ffprobe, selecionar a faixa de áudio correta, normalizar para WAV PCM signed 16-bit mono/16 kHz com FFmpeg, preservar separadamente o offset da faixa original e manter mídia baixada/áudio normalizado no workspace exclusivo do job.

A camada GUI deve iniciar inspeções e processamento fora da thread principal, permitir selecionar uma faixa local quando a mídia tiver múltiplas faixas e mostrar erros/preflight de modo honesto. A Fase 3 prepara o áudio; não promete transcrição.

## 2. Entregas

1. **Fonte de entrada:** escolha explícita entre arquivo local e URL do YouTube; validação de caminho/URL, domínio, extensão, existência e acesso.
2. **YouTube:** adaptador yt-dlp usando a dependência do perfil CPU, sem shell interpolation, sem playlists e com cancelamento/progresso por hooks; arquivo adquirido dentro do workspace.
3. **Inspeção:** ffprobe identifica contêiner, duração quando disponível, streams de áudio/vídeo, codec, canais, taxa de amostragem, idioma, título, marcação default e offset de apresentação.
4. **Seleção de faixa:** preferir a faixa marcada como default; respeitar seleção explícita pelo índice global; rejeitar índices inexistentes ou não-áudio.
5. **Normalização:** FFmpeg extrai apenas a faixa selecionada, converte para WAV PCM signed 16-bit, mono, 16 kHz; não altera a fonte; escreve em arquivo intermediário e publica o artefato preparado atomicamente.
6. **Timeline:** preservar `stream.start_time`; se ausente, derivar `start_pts * time_base`; depois usar `format.start_time` como fallback explicitamente identificado; zero somente quando não houver timestamp disponível. Nunca somar o offset ao conteúdo WAV e novamente ao alinhador.
7. **Validação:** reabrir o WAV gerado com ffprobe e confirmar codec, sample rate, canais e duração positiva antes de considerá-lo pronto.
8. **Cancelamento/timeout:** ffprobe, FFmpeg e yt-dlp devem encerrar ou chegar a checkpoints em cancelamento; erros incluem detalhes técnicos limitados sem despejar URLs ou dados sensíveis.
9. **Workspace:** fonte baixada, arquivos parciais e WAV ficam sob o diretório isolado do job; limpeza idempotente não toca no cache de modelos nem em arquivos do usuário.
10. **GUI:** seletor local/YouTube; inspeção assíncrona; seleção das faixas de áudio da fonte local; feedback da mídia/áudio preparado; controles bloqueados durante operação; cancelamento cooperativo.
11. **CI e testes:** unitários sem rede, testes de contrato para yt-dlp com fake, integração sintética real com FFmpeg/ffprobe, matriz Python 3.10–3.13, Ruff/format e verificação de arquitetura.
12. **Documentação:** README, roadmap, estado atual, plano operacional e handoff atualizados com evidências reais.

## 3. Fora do escopo (fases posteriores)

- Whisper/WhisperX concretos, download de modelos, transcrição, idioma detectado por modelo e alinhamento por palavra.
- Segmentação/legendas SRT, tradução e escolha de fornecedor.
- Integração ponta a ponta de toda a geração de SRT.
- Prometer que todas as URLs/contêineres/DRMs são suportados. YouTube dependerá dos limites do yt-dlp/EJS e da disponibilidade do conteúdo.
- Homologação final em hardware/HiDPI e todos os sistemas operacionais (gate global da Fase 8).

## 4. Critérios de aceite

- [ ] Local e YouTube são fontes distintas e validadas; nenhum comando é executado por shell.
- [ ] yt-dlp não baixa playlists e grava somente dentro do workspace.
- [ ] Progresso de download é medido somente com tamanho total disponível; caso contrário não inventar percentual.
- [ ] ffprobe lista faixas e metadados; a faixa default é escolhida corretamente e índice explícito é respeitado.
- [ ] Offsets são derivados e a origem do offset é registrada (stream, start_pts/time_base, container ou zero assumido).
- [ ] FFmpeg gera WAV PCM s16le mono/16 kHz e o resultado é validado novamente por ffprobe.
- [ ] Arquivo fonte não é alterado; arquivo parcial não fica após sucesso/falha/cancelamento.
- [ ] Cancelamento e timeout encerram subprocessos ou download em checkpoints; não deixam processos órfãos.
- [ ] Workspaces permanecem isolados e sua limpeza não toca cache ou arquivos fonte.
- [ ] GUI inspeciona sem bloquear a thread principal e permite selecionar faixas locais múltiplas.
- [ ] Testes sem rede; fixtures reais sintéticas para contêineres/codecs/offsets; CI 3.10–3.13 verde.
- [ ] README, roadmap, estado atual e handoff correspondem à implementação real.

## 5. Sequência de implementação

1. Completar metadados do domínio e parser ffprobe (default, time_base e origem do offset).
2. Adaptador FFmpeg com saída intermediária, validação pós-conversão e cancelamento.
3. Adaptador yt-dlp com validação de origem, workspace, hooks e cancelamento.
4. Conectar portas ao pipeline e bootstrap; garantir erros explícitos para os motores das Fases 4/5 ainda ausentes.
5. Adicionar origem YouTube/local e inspeção/seleção assíncrona de faixas na GUI.
6. Suíte unitária, contrato de downloader e integração sintética real.
7. CI dedicada, correções, revisão arquitetural, documentação e PR para `main`.

## 6. Evidências e estado da execução

### Implementação presente na branch

- Entidade `AudioStreamInfo` agora registra `is_default` e origem do offset. `MediaInfo.default_stream()` prefere a faixa default; índices globais explícitos continuam respeitados.
- Parser ffprobe deriva offset por `stream.start_time`, `start_pts × time_base`, fallback de `format.start_time` ou zero assumido, registrando a proveniência.
- `FfmpegAudioPreparer` usa subprocesso sem shell, timeouts/cancelamento, arquivo parcial exclusivo, validação do WAV por ffprobe e publicação sem sobrescrever um destino concorrente.
- `YtDlpDownloader` aceita hosts oficiais do YouTube, rejeita playlists e caminhos fora do workspace, usa hooks para progresso/cancelamento e evita expor a URL em mensagens de erro.
- Bootstrap compõe portas reais de inspeção, preparação e download. Transcrição, alinhamento e publicação final permanecem placeholders explícitos das Fases 4–7.
- GUI possui seleção local/YouTube, inspeção prévia em QThread, seleção de faixa local e exibição dos metadados da faixa escolhida. Inspeção é repetida no pipeline quando o job inicia.
- Testes unitários e fixtures sintéticas reais de FFmpeg/ffprobe foram adicionados. Testes de downloader usam doubles; não acessam rede.

### Validação CI

- Workflow dedicado: [phase3-quality.yml](../.github/workflows/phase3-quality.yml).
- Primeira execução [#42914913047](https://github.com/anfalcir/legendar/actions/runs/42914913047): identificou seis falhas de fixtures/expectativas; corrigidas em commits subsequentes.
- Execuções seguintes chegaram a **245 testes aprovados** nos ambientes Python 3.10, 3.11 e 3.12. Nessas tentativas o gate de lint passou, mas a formatação ainda falhou; uma execução Python 3.13 sofreu segfault durante o teste de cancelamento Qt.
- O ciclo de vida do worker de inspeção foi ajustado para autoexclusão na própria thread; os nove arquivos apontados pelo Ruff foram formatados.
- Último run disparado para o snapshot após essas correções: [#42916191288](https://github.com/anfalcir/legendar/actions/runs/42916191288), ainda sem jobs atribuídos quando este documento foi atualizado. Portanto, não conta como aprovação.

### Bloqueios para conclusão

1. Obter uma execução de CI do snapshot atual com os quatro ambientes Python 3.10–3.13 concluídos, incluindo testes, Ruff e formatação.
2. Revisar resultados e eventuais correções da CI; confirmar que a correção de ciclo de vida Qt eliminou o segfault no Python 3.13.
3. Fazer revisão final de segurança/arquitetura e confirmar que a limpeza dos workspaces mantém a origem e o cache intactos.
4. Completar este documento e os documentos vivos com a evidência final.
5. Abrir PR para `main`, aguardar CI de PR e revisão, então integrar por squash.

A Fase 3 **não está concluída**. Não marcar os critérios abaixo como aprovados com base apenas em código presente ou testes de uma parte da matriz. Não declarar integração à `main` até existir PR merged e commit confirmado.
