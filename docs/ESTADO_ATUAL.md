# Estado atual do Legendar

- **Última atualização:** 11/11/2026
- **Repositório:** [anfalcir/legendar](https://github.com/anfalcir/legendar)
- **Branch de integração:** `main`
- **HEAD usado nesta atualização documental:** `85aa832954aa539d2c8e96a4335608f958e88776`
- **Integração da organização documental e do plano vigente:** PR [#7](https://github.com/anfalcir/legendar/pull/7), squash `a62f4459b76b07aa86f00d22acf663a8f95b7368`, integrada à `main`.
- **CI da integração:** o job de documentação da PR #7 passou; parte da matriz da PR não chegou a executar testes porque os runners não resolveram os espelhos Ubuntu durante `apt-get`. A nova execução pós-merge da Fase 8 está em andamento ([run #43055692640](https://github.com/anfalcir/legendar/actions/runs/43055692640)). Não considerar a matriz completa aprovada até os jobs terminarem.
- **Remodelação arquitetural anterior:** Fases 0–10 integradas à `main`.
- **Nova frente:** plano de correção da qualidade editorial e melhoria de desempenho documentado; implementação ainda não iniciada.
- **CI de referência:** [run 43031178212](https://github.com/anfalcir/legendar/actions/runs/43031178212), 5/5 jobs aprovados no commit auditado.
- **Documentação:** raiz de `docs/` reservada a documentos vivos; histórico anterior preservado em `docs/archive/`.

> Este documento separa comportamento observado no código, resultados confirmados por CI e medições ainda pendentes. Um teste verde de software não equivale a homologação de qualidade audiovisual.

## 1. Resumo executivo

O Legendar é uma aplicação desktop PySide6 que recebe áudio/vídeo, normaliza o áudio, transcreve com Whisper, alinha palavras com WhisperX, forma legendas, traduz localmente com NLLB-200 quando solicitado, valida o trilho e publica SRT por troca atômica.

A arquitetura e a base de engenharia das Fases 0–10 estão integradas. Uma auditoria estática posterior identificou lacunas no caminho de qualidade final: ausência de consolidação editorial entre segmentos consecutivos do Whisper, subdivisão de textos com CPS alto sem resolver a falta de tempo de leitura, aceitação de cues curtas como simples aviso, possível perda de palavras sem alinhamento na segmentação e ausência de um gate editorial bloqueante.

A prioridade agora é corrigir a integridade e a legibilidade do resultado antes de trocar motores ou reduzir configurações de qualidade. Em paralelo, o novo plano estabelece instrumentação para localizar os gargalos de desempenho e testar otimizações com comparação pareada.

## 2. Estado do repositório

| Área | Estado |
|---|---|
| Arquitetura das Fases 0–10 | Integrada à `main` |
| UI, worker e pipeline real | Implementados |
| Reconhecimento | OpenAI Whisper local; padrão declarado `base` |
| Alinhamento | WhisperX 3.8.6; forced alignment por segmento |
| Segmentação | Algoritmo determinístico atual; correções planejadas |
| Tradução | NLLB-200 distilled 600M via Transformers/PyTorch |
| Publicação | SRT com round-trip e gravação atômica |
| Gate editorial | Insuficiente: riscos de leitura podem continuar como avisos |
| Benchmark por etapa | Ainda não há baseline estruturada e comparável por estágio |
| Otimização de motores | Candidatos em avaliação; nenhum motor alternativo adotado |
| Homologação audiovisual final | Pendente |

## 3. Evidências de qualidade e lacunas conhecidas

Os módulos auditados incluem:

- `src/legendar/infrastructure/transcription/whisper.py`
- `src/legendar/infrastructure/alignment/whisperx.py`
- `src/legendar/application/pipeline/segmentation.py`
- `src/legendar/application/pipeline/validation.py`
- `src/legendar/application/pipeline/serial_pipeline.py`
- `src/legendar/infrastructure/translation/nllb.py`
- `src/legendar/infrastructure/filesystem/srt.py`

Achados estáticos confirmados:

1. A segmentação percorre cada segmento original da transcrição separadamente; não há consolidação explícita de palavras entre segmentos consecutivos.
2. Grupos acima da velocidade de leitura podem ser subdivididos em cues menores, cujos tempos continuam limitados aos intervalos reais das palavras.
3. Cues abaixo de 1 segundo são diagnosticadas, mas não recebem tratamento editorial que assegure conforto de leitura.
4. Quando um segmento contém palavras alinhadas e não alinhadas, o caminho principal da segmentação considera somente as palavras com intervalo. Isso pode omitir texto no SRT.
5. A validação estrutural bloqueia falhas graves de formato, mas duração curta, CPS e outros riscos de legibilidade são avisos e não impedem a publicação.
6. Os testes E2E de mídia usam transcritor e alinhador falsos. Eles validam integração e publicação, não a qualidade real dos modelos em fala contínua.
7. O alinhador real chama WhisperX por segmento. O custo acumulado precisa ser medido antes de qualquer mudança de lote.

Esses achados descrevem o código; não identificam, por si sós, a origem de cada erro textual ou temporal de uma mídia específica. A correlação com áudio de referência exige homologação.

## 4. Desempenho: baseline disponível e limitações

**Relato operacional inicial:** aproximadamente 60 minutos para processar uma mídia de 37 minutos, ou RTF global aproximado de 1,62.

Essa medição é informada pelo usuário, não reproduzida nesta auditoria. Não há ainda tempos confiáveis e persistidos por estágio, portanto não se deve atribuir uma fração exata do total à transcrição ou à tradução.

Configuração atual relevante:

- Transcrição: OpenAI Whisper, padrão `base`, execução PyTorch.
- Alinhamento: WhisperX 3.8.6, chamadas por segmento.
- Tradução: NLLB-200 distilled 600M via Transformers/PyTorch, `num_beams=4`, lote padrão de 16 unidades e tokenização com padding.
- O adaptador de tradução já implementa batching; o próximo trabalho deve investigar custo por token, padding, beam search, tempo de geração e backend, não apenas aumentar o tamanho do lote.

O inventário da Fase 0 registrou um perfil de referência com Ryzen 3 2200G, quatro CPUs lógicas, cerca de 12,59 GiB de RAM e AMD Vega integrada, sem NVIDIA. Esse inventário é histórico e precisa ser reexecutado antes de uma decisão de hardware ou configuração.

O plano vigente exige instrumentação de tempo de cada etapa, CPU, memória e configuração dos modelos; benchmark frio/quente; e comparação com a mesma mídia e hardware. A meta inicial é reduzir o tempo global em pelo menos 20% sem degradação mensurável de qualidade; 30% é uma meta aspiracional, não uma garantia.

## 5. Plano de execução vigente

A fonte de verdade para a próxima frente é [PLANO_CORRECAO_MELHORIA.md](PLANO_CORRECAO_MELHORIA.md).

| Fase | Objetivo | Situação |
|---|---|---|
| 0 | Auditoria, organização documental e plano | Documentada nesta entrega |
| 1 | Instrumentação e baseline por etapa | Próxima execução |
| 2 | Integridade textual e alinhamento recuperável | Planejada |
| 3 | Segmentação global e legibilidade | Planejada |
| 4 | Gate editorial e diagnóstico textual | Planejada |
| 5 | Benchmark e aceleração da transcrição | Planejada |
| 6 | Benchmark e aceleração da tradução | Planejada |
| 7 | Gestão de memória, threads e perfis de execução | Planejada |
| 8 | Regressão, homologação real e comparação final | Planejada |

Nenhuma dessas fases de código é declarada concluída por existir apenas no plano.

## 6. Critérios que não podem ser sacrificados

- Nenhuma palavra reconhecida pode desaparecer silenciosamente.
- Nenhum timestamp pode ser inventado para encobrir falha de alinhamento.
- A segmentação deve respeitar pausas, continuidade sintática, duração de exibição, CPS e limites de linhas.
- Uma falha editorial grave deve gerar revisão explícita, não um falso sucesso.
- Uma otimização de motor só será adotada após avaliação de WER/CER, cobertura, alinhamento e revisão humana da tradução.
- A publicação continua atômica e só ocorre após os gates definidos.

## 7. Próximas ações

1. Integrar a reorganização e o plano documental.
2. Executar a Fase 1, criando a medição de baseline sem alterar os motores.
3. Usar a mesma mídia de 37 minutos para separar transcrição, alinhamento, segmentação, tradução e publicação.
4. Executar as fases de correção de integridade e legibilidade.
5. Medir candidatos de aceleração em comparação pareada; atualizar a matriz de dependências somente quando um candidato for aprovado.
6. Fazer a homologação final no hardware-alvo e registrar evidências sanitizadas.

## 8. Histórico documental

Os protocolos, planos, handoffs e relatórios concluídos da remodelação anterior estão preservados em [archive/README.md](archive/README.md). Eles servem como registro histórico; este arquivo e o plano vigente representam o estado atual.
