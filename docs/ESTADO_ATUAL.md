# Estado atual do Legendar

- **Última atualização:** 11/11/2026
- **Repositório:** [anfalcir/legendar](https://github.com/anfalcir/legendar)
- **Branch de integração:** `main`
- **Base de início da Fase 1:** `d3530490df466aa6eeff4728b63d7e8dc22f056e`
- **Fase 1 — instrumentação integrada à `main`:** PR [#8](https://github.com/anfalcir/legendar/pull/8), squash `12e3f40db5fe9b849f1a51715802eea7dba0449e`.
- **Integração da organização documental e do plano vigente:** PR [#7](https://github.com/anfalcir/legendar/pull/7), squash `a62f4459b76b07aa86f00d22acf663a8f95b7368`, integrada à `main`.
- **CI da Fase 1 (PR #8):** aprovada. Incluiu 492 testes, cobertura de 85,46%, E2E com FFmpeg/Qt em Python 3.10–3.13, smoke OpenAI Whisper PT-BR/EN, smoke NLLB real com Transformers em CPU, matriz multiplataforma, validação documental e os workflows determinísticos relacionados. Os checks de WhisperX benchmark/CUDA foram marcados como skipped pelos critérios do runner, não como falha.
- **Remodelação arquitetural anterior:** Fases 0–10 integradas à `main`.
- **Nova frente:** instrumentação da Fase 1 integrada à `main`; baseline de desempenho com a mídia real de 37 minutos ainda pendente no equipamento de homologação.
- **CI de referência:** [run 43031178212](https://github.com/anfalcir/legendar/actions/runs/43031178212), 5/5 jobs aprovados no commit auditado.
- **Documentação:** raiz de `docs/` reservada a documentos vivos; histórico anterior preservado em `docs/archive/`.

> Este documento separa comportamento observado no código, resultados confirmados por CI e medições ainda pendentes. Um teste verde de software não equivale a homologação de qualidade audiovisual.

## 1. Resumo executivo

O Legendar é uma aplicação desktop PySide6 que recebe áudio/vídeo, normaliza o áudio, transcreve com Whisper, alinha palavras com WhisperX, forma legendas, traduz localmente com NLLB-200 quando solicitado, valida o trilho e publica SRT por troca atômica.

A arquitetura e a base de engenharia das Fases 0–10 estão integradas. Uma auditoria estática posterior identificou lacunas no caminho de qualidade final: ausência de consolidação editorial entre segmentos consecutivos do Whisper, subdivisão de textos com CPS alto sem resolver a falta de tempo de leitura, aceitação de cues curtas como simples aviso, possível perda de palavras sem alinhamento na segmentação e ausência de um gate editorial bloqueante.

A prioridade agora é corrigir a integridade e a legibilidade do resultado antes de trocar motores ou reduzir configurações de qualidade. Em paralelo, o novo plano estabelece instrumentação para localizar os gargalos de desempenho e testar otimizações com comparação pareada.

## 2. Estado da Fase 1 — instrumentação integrada

A instrumentação está integrada à `main` (PR #8, squash `12e3f40db5fe9b849f1a51715802eea7dba0449e`). Ela mede cada etapa do pipeline e expõe métricas internas dos adaptadores. Nenhum modelo ou parâmetro de qualidade foi trocado: Whisper, WhisperX, NLLB, beam, batch, dtype e política de alinhamento permanecem iguais.

**Etapas instrumentadas:** aquisição, inspeção, preparação do áudio, transcrição, alinhamento, segmentação, tradução opcional, validação e publicação.

**Detalhamento dos motores:**
- Whisper: carga do modelo, leitura do WAV, inferência, quantidade de segmentos e palavras reconhecidas.
- WhisperX: carga do modelo, preparação do Punkt, leitura do WAV, tempo acumulado das chamadas por segmento, palavras alinhadas e não alinhadas.
- NLLB: carga do tokenizador/modelo, lotes/unidades, tokenização, transferência para dispositivo, geração, decodificação, contagem de tokens e tokens/s.

**Relatório local:** `~/.cache/legendar/logs/performance/job-<job-id>.json`, com arquivo `0600` e diretório privado. Não contém mídia, transcrição, texto SRT, URL, caminho da mídia, mensagem de exceção ou credenciais e não é transmitido para serviços externos. A coleta é best-effort e não pode falhar o job.

**Leitura dos relatórios:**
```bash
uv run --locked --no-sync python scripts/phase1_performance_summary.py --last 10
```

**Validação automatizada:** 492 testes aprovados; cobertura global de 85,46%; E2E em quatro versões de Python; smoke de reconhecimento Whisper PT-BR/EN; smoke NLLB real em CPU; CI multiplataforma e documentação aprovadas.

**Estado da evidência operacional:** a instrumentação está concluída e integrada, mas a baseline no equipamento real ainda não foi coletada. O tempo inicial de aproximadamente 60 minutos para 37 minutos de áudio continua sendo relato do usuário, não uma medição decomposta. Fase 1 só será considerada concluída após executar o inventário atualizado e as rodadas fria/quentes com a mesma mídia/configuração.
## 3. Estado do repositório

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
| Benchmark por etapa | Instrumentação integrada; baseline real comparável ainda pendente |
| Otimização de motores | Candidatos em avaliação; nenhum motor alternativo adotado |
| Homologação audiovisual final | Pendente |

## 4. Evidências de qualidade e lacunas conhecidas

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
