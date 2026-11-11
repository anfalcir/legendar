# Estado atual do Legendar

- **Última atualização:** 11/11/2026
- **Repositório:** [anfalcir/legendar](https://github.com/anfalcir/legendar)
- **Branch de integração:** `main`
- **Base de início da Fase 1:** `d3530490df466aa6eeff4728b63d7e8dc22f056e`
- **Fase 1 — instrumentação integrada à `main`:** PR [#8](https://github.com/anfalcir/legendar/pull/8), squash `12e3f40db5fe9b849f1a51715802eea7dba0449e`.
- **Integração da organização documental e do plano vigente:** PR [#7](https://github.com/anfalcir/legendar/pull/7), squash `a62f4459b76b07aa86f00d22acf663a8f95b7368`, integrada à `main`.
- **CI da Fase 1 (PR #8):** aprovada. Incluiu 492 testes, cobertura de 85,46%, E2E com FFmpeg/Qt em Python 3.10–3.13, smoke OpenAI Whisper PT-BR/EN, smoke NLLB real com Transformers em CPU, matriz multiplataforma, validação documental e os workflows determinísticos relacionados. Os checks de WhisperX benchmark/CUDA foram marcados como skipped pelos critérios do runner, não como falha.
- **Remodelação arquitetural anterior:** Fases 0–10 integradas à `main`.
- **Fase 1:** concluída e integrada à `main`; baseline real da mídia de 37min10s consolidado em 11/11/2026.
- **Fase 2:** concluída, validada pelo CI e integrada à `main` pela PR #9. A próxima frente é a Fase 3.
- **CI de referência:** [run 43031178212](https://github.com/anfalcir/legendar/actions/runs/43031178212), 5/5 jobs aprovados no commit auditado.
- **Documentação:** raiz de `docs/` reservada a documentos vivos; histórico anterior preservado em `docs/archive/`.

> Este documento separa comportamento observado no código, resultados confirmados por CI e medições ainda pendentes. Um teste verde de software não equivale a homologação de qualidade audiovisual.

## 1. Resumo executivo

O Legendar é uma aplicação desktop PySide6 que recebe áudio/vídeo, normaliza o áudio, transcreve com Whisper, alinha palavras com WhisperX, forma legendas, traduz localmente com NLLB-200 quando solicitado, valida o trilho e publica SRT por troca atômica.

A arquitetura e a base de engenharia das Fases 0–10 estão integradas. A auditoria estática posterior identificou lacunas editoriais; as Fases 2 e 3 já corrigiram a integridade textual e a consolidação cronológica da segmentação. A Fase 4 está em implementação na branch `phase-4/editorial-quality-gate`: gate estruturado, diagnósticos editoriais e aviso de revisão na interface.

As Fases 1, 2 e 3 estão concluídas e integradas à `main`. A Fase 3 consolidou globalmente as palavras alinhadas, preservou segmentos fallback, reforçou fronteiras editoriais e adicionou extensão segura de exibição. A Fase 4 está em andamento; CI e merge ainda pendentes. O baseline real de 37min10s é ~23min21s; NLLB consome ~14min e será o foco da Fase 6, quando será avaliado Gemini com credencial fornecida pelo usuário via secret do GitHub.

## 2. Estado da Fase 1 — concluída

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

**Evidência operacional consolidada (11/11/2026):** o inventário atualizado e quatro execuções da mídia real de 37min10s foram coletados: uma fria e três quentes. As três execuções quentes ficaram na faixa de ~23 minutos, com mediana de aproximadamente 23min21s (RTF ~0,63). A tradução NLLB foi o maior estágio isolado, em torno de 14 minutos por execução quente. Essa medição substitui o relato histórico de ~1 hora como baseline operacional para os próximos experimentos; não é necessário investigar o ambiente da medição histórica para avançar.
## 3. Estado da Fase 2 — concluída

A implementação atual da branch de Fase 2:

- preserva explicitamente palavras sem alinhamento no diagnóstico da segmentação;
- impede publicação quando qualquer palavra reconhecida permanece sem evidência temporal confiável;
- executa uma segunda tentativa controlada somente em segmentos com palavras não alinhadas, ampliando a janela em até 0,75 s por lado;
- mantém `interpolate_method="ignore"` e não fabrica timestamps;
- registra tentativas, duração e palavras recuperadas nas métricas de performance;
- possui testes unitários para perda explícita, bloqueio de publicação e recuperação.

A Fase 2 foi integrada à `main` após CI verde em todas as matrizes relevantes. A homologação audiovisual real continua sendo gate posterior.

## 3. Estado da Fase 3 — concluída e integrada à `main`

A Fase 3 foi integrada pela PR #10, squash commit `10f6d6d428a1fa5a45a7c7fd13870f48bdf67019`. A implementação usa fluxo global cronológico de palavras alinhadas, consolida segmentos contíguos do Whisper, preserva segmentos fallback como barreiras, mantém rastreabilidade `source_segments`, rejeita cronologia inválida, respeita fronteiras de frase significativas e estende cues curtas somente no silêncio seguro antes da próxima cue (margem de 80 ms). O corpus determinístico cobre continuidade, pausas, pontuação, CPS, extensão segura, fallback intercalado, rastreabilidade e layout final de duas linhas.

**Validação:** CI específica verde em Python 3.10–3.13; 506 testes aprovados; cobertura global de 86%; Ruff lint/formatação e integração FFmpeg/Qt/E2E aprovados. Workflows das Fases 4, 5, 6 e 8 também passaram no mesmo head. A homologação audiovisual com a mídia real de 37min10s permanece no escopo da Fase 8.

## 4. Estado do repositório

| Área | Estado |
|---|---|
| Arquitetura das Fases 0–10 | Integrada à `main` |
| UI, worker e pipeline real | Implementados |
| Reconhecimento | OpenAI Whisper local; padrão declarado `base` |
| Alinhamento | WhisperX 3.8.6; forced alignment por segmento |
| Segmentação | Fluxo global cronológico integrado; consolida limites do Whisper, preserva fallback e rastreabilidade de origem |
| Tradução | NLLB-200 distilled 600M via Transformers/PyTorch |
| Publicação | SRT com round-trip e gravação atômica |
| Gate editorial | Em implementação: relatório estruturado e bloqueio de perda de conteúdo na branch da Fase 4 |
| Benchmark por etapa | Instrumentação integrada; baseline real consolidado em 11/11/2026 |
| Otimização de motores | Fases 5–7 planejadas; Gemini é candidato para a Fase 6, sem adoção ainda |
| Homologação audiovisual final | Pendente |

## 5. Evidências de qualidade e lacunas conhecidas

Os módulos auditados incluem:

- `src/legendar/infrastructure/transcription/whisper.py`
- `src/legendar/infrastructure/alignment/whisperx.py`
- `src/legendar/application/pipeline/segmentation.py`
- `src/legendar/application/pipeline/validation.py`
- `src/legendar/application/pipeline/serial_pipeline.py`
- `src/legendar/infrastructure/translation/nllb.py`
- `src/legendar/infrastructure/filesystem/srt.py`

Achados da auditoria original e tratamento atual:

1. A segmentação isolada por segmento foi substituída na branch da Fase 3 pelo fluxo global de palavras alinhadas; aguarda CI e homologação.
2. A subdivisão por velocidade de leitura continua limitada a timestamps reais. A Fase 3 adiciona extensão apenas em silêncio seguro antes da próxima cue.
3. Cues curtas sem silêncio posterior seguro continuam explícitas para avaliação; não recebem duração inventada.
4. A Fase 2 bloqueia a publicação quando há palavras reconhecidas sem âncora temporal confiável, impedindo a perda silenciosa observada na auditoria original.
5. A validação estrutural ainda não é um gate editorial completo; a Fase 4 tratará CPS, duração, fragmentação e exceções.
6. Os testes E2E determinísticos continuam usando dublês; a homologação com áudio real permanece necessária para avaliar modelos e qualidade audiovisual.
7. O alinhador real ainda chama WhisperX por segmento. O baseline instrumentado está disponível; otimizações de alinhamento não fazem parte do escopo atual.

Esses achados descrevem o código e os testes; não identificam, por si sós, a origem de cada erro textual ou temporal de uma mídia específica. A correlação com áudio de referência exige homologação.

## 6. Desempenho: baseline disponível e limitações

**Baseline operacional consolidado em 11/11/2026:** uma execução fria e três quentes da mídia de referência de 37min10s. A mediana quente foi aproximadamente 23min21s (RTF ~0,63). A tradução NLLB foi o maior estágio, em torno de 14 minutos por execução quente. Os relatórios sanitizados estão preservados em `logs/`; não é necessário reabrir o relato histórico de aproximadamente uma hora.

Configuração atual relevante:

- Transcrição: OpenAI Whisper, padrão `base`, execução PyTorch.
- Alinhamento: WhisperX 3.8.6, chamadas por segmento.
- Tradução: NLLB-200 distilled 600M via Transformers/PyTorch, `num_beams=4`, lote padrão de 16 unidades e tokenização com padding.
- O adaptador de tradução já implementa batching; o próximo trabalho deve investigar custo por token, padding, beam search, tempo de geração e backend, não apenas aumentar o tamanho do lote.

O inventário da Fase 0 registrou um perfil de referência com Ryzen 3 2200G, quatro CPUs lógicas, cerca de 12,59 GiB de RAM e AMD Vega integrada, sem NVIDIA. Esse inventário é histórico e precisa ser reexecutado antes de uma decisão de hardware ou configuração.

O plano vigente exige instrumentação de tempo de cada etapa, CPU, memória e configuração dos modelos; benchmark frio/quente; e comparação com a mesma mídia e hardware. A meta inicial é reduzir o tempo global em pelo menos 20% sem degradação mensurável de qualidade; 30% é uma meta aspiracional, não uma garantia.

## 7. Plano de execução vigente

A fonte de verdade para a próxima frente é [PLANO_CORRECAO_MELHORIA.md](PLANO_CORRECAO_MELHORIA.md).

| Fase | Objetivo | Situação |
|---|---|---|
| 0 | Auditoria, organização documental e plano | Documentada nesta entrega |
| 1 | Instrumentação e baseline por etapa | **Concluída** |
| 2 | Integridade textual e alinhamento recuperável | **Concluída e integrada à `main`** |
| 3 | Segmentação global e legibilidade | **Concluída e integrada à `main` (PR #10)** |
| 4 | Gate editorial e diagnóstico textual | **Em implementação na branch `phase-4/editorial-quality-gate`; CI/merge pendentes** |
| 5 | Benchmark e aceleração da transcrição | Planejada |
| 6 | Benchmark e aceleração da tradução | Planejada |
| 7 | Gestão de memória, threads e perfis de execução | Planejada |
| 8 | Regressão, homologação real e comparação final | Planejada |

Nenhuma dessas fases de código é declarada concluída por existir apenas no plano.

## 8. Critérios que não podem ser sacrificados

- Nenhuma palavra reconhecida pode desaparecer silenciosamente.
- Nenhum timestamp pode ser inventado para encobrir falha de alinhamento.
- A segmentação deve respeitar pausas, continuidade sintática, duração de exibição, CPS e limites de linhas.
- Uma falha editorial grave deve gerar revisão explícita, não um falso sucesso.
- Uma otimização de motor só será adotada após avaliação de WER/CER, cobertura, alinhamento e revisão humana da tradução.
- A publicação continua atômica e só ocorre após os gates definidos.

## 9. Próximas ações

1. Concluir CI, revisão e merge da Fase 4; confirmar que CPS, duração, fragmentação e integridade são critérios editoriais auditáveis.
2. Executar a Fase 5 isoladamente, se o benchmark confirmar oportunidade de aceleração de ASR.
3. Na Fase 6, comparar Gemini API com NLLB usando o mesmo corpus e revisão humana. Antes das chamadas reais, solicitar o cadastro de `GEMINI_API_KEY` como secret no GitHub.
4. Exigir do Gemini PT-BR idiomático, interpretação contextual, preservação de entidades/nomenclaturas próprias e consistência terminológica; grounding/pesquisa só poderá apoiar interpretação sem acrescentar conteúdo não falado.
5. Consolidar a Fase 8 com comparação do pipeline completo, homologação audiovisual com a mídia real, validação no hardware-alvo e evidências sanitizadas.

## 10. Histórico documental

Os protocolos, planos, handoffs e relatórios concluídos da remodelação anterior estão preservados em [archive/README.md](archive/README.md). Eles servem como registro histórico; este arquivo e o plano vigente representam o estado atual.
