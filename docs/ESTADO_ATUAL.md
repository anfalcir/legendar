# Estado atual do Legendar

- **Última atualização:** 09/11/2026
- **Repositório:** anfalcir/legendar
- **Branch de referência:** main
- **Visibilidade verificada:** privada
- **Fase atual:** preparação — Fase 0 ainda não iniciada
- **Fonte de verdade:** este documento para progresso; PLANO_REMODELAGEM.md para escopo e critérios

> Este é um documento vivo. Atualize-o ao iniciar/concluir fases, aprovar decisões, executar testes ou identificar bloqueios. Não marque como concluído algo que não tenha evidência verificável.

---

## 1. Resumo executivo

O repositório foi limpo e o plano mestre de remodelagem foi registrado. A remodelagem funcional ainda não começou.

A aplicação existente é uma base legada pequena em Python/PySide6, com integração básica ao Whisper, yt-dlp e FFmpeg. O comportamento atual ainda está orientado à geração de transcrições em texto, não à produção de SRT temporizado e traduzido.

**Estado do produto:** baseline preservada; plano documentado; nenhuma fase de implementação da remodelagem aprovada como concluída.

## 2. Situação do repositório

| Item | Estado observado |
|---|---|
| Repositório | anfalcir/legendar |
| Visibilidade | Privada, confirmada na API do GitHub em 09/11/2026 |
| Branch padrão | main |
| Histórico da main | Um commit raiz na última verificação anterior à documentação |
| Diretórios de testes | Ainda não existentes na baseline |
| Diretório docs | Criado com o plano e este documento |
| Configuração de projeto | requirements.txt existente; pyproject.toml ainda não existe |
| Licença | Projeto tratado pelo responsável como MIT; recuperar/restaurar aviso e arquivo LICENSE apropriado antes da distribuição |
| Releases/tags | Nenhuma identificada na última inspeção |
| CI | Não avaliada nesta etapa |

A documentação deste plano será publicada em um commit próprio após a baseline. O estado do histórico deverá ser atualizado com o hash desse commit após a publicação.

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
| Testes automatizados | Nenhuma suíte identificada |
| Documentação técnica | README existente; documentação de arquitetura ainda ausente antes deste plano |

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
| 0 — Definições e prova técnica | **Não iniciada** | Próxima fase recomendada |
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
- stable-ts como alternativa a comparar, não como dependência confirmada.
- VAD para apoiar delimitação de fala e tratamento de silêncios.
- Serviço de tradução contextual único, encapsulado por interface.
- WAV PCM mono 16 kHz como formato interno inicial a validar.
- QSettings para preferências simples.
- Diretório temporário por job e publicação atômica de SRT.
- CPU como caminho de compatibilidade e GPU como aceleração opcional.
- pytest, pytest-qt, pytest-cov e Ruff como conjunto candidato de qualidade.

## 6. Fase atual — preparação da Fase 0

### Objetivo

Reduzir os maiores riscos técnicos antes de estruturar a aplicação nova: qualidade de alinhamento, suporte de idioma, compatibilidade de dependências, custo/privacidade da tradução e desempenho no equipamento-alvo.

### Atividades necessárias

1. Definir ambiente e sistema operacional de referência.
2. Inventariar CPU, RAM, GPU e armazenamento disponíveis no ambiente-alvo.
3. Criar amostras curtas de áudio próprio/autorizado em PT-BR e inglês, com fala clara e condições desafiadoras.
4. Criar transcrições de referência e marcações temporais verificadas manualmente para parte dessas amostras.
5. Testar Whisper em perfis/modelos candidatos.
6. Testar WhisperX e confirmar modelos de alinhamento para PT-BR e inglês nas versões escolhidas.
7. Comparar alinhamento com stable-ts somente se houver compatibilidade e benefício mensurável.
8. Testar normalização e preservação de offsets com FFmpeg/ffprobe.
9. Avaliar opções de tradução contextual, custo, privacidade, limites e formato estruturado da resposta.
10. Medir qualidade, velocidade, memória e taxa de palavras alinhadas.
11. Aprovar as dependências e as metas iniciais de qualidade.
12. Registrar decisões e critérios antes de avançar para a Fase 1.

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
| 09/11/2026 | Inspeção da árvore e documentação inicial | Plano e estado preparados; ainda não há testes de remodelagem | Verificação da baseline no GitHub |

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
| 09/11/2026 | Criados o plano mestre de remodelagem e o documento vivo de estado inicial. Nenhuma fase de implementação iniciada. |
