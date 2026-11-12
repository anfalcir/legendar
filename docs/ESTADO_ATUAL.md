# Estado atual do Legendar

- **Última atualização:** 12/11/2026
- **Commit de integração da Fase 6:** `7f337bc10cf210336fbf2367b56aea7e767bce32` (PR #19; a `main` também contém os commits posteriores de sincronização documental).
- **Repositório:** [anfalcir/legendar](https://github.com/anfalcir/legendar)
- **Branch de integração:** `main`
- **Base de início da Fase 1:** `d3530490df466aa6eeff4728b63d7e8dc22f056e`
- **Fase 1 — instrumentação integrada à `main`:** PR [#8](https://github.com/anfalcir/legendar/pull/8), squash `12e3f40db5fe9b849f1a51715802eea7dba0449e`.
- **Integração da organização documental e do plano vigente:** PR [#7](https://github.com/anfalcir/legendar/pull/7), squash `a62f4459b76b07aa86f00d22acf663a8f95b7368`, integrada à `main`.
- **CI da Fase 1 (PR #8):** aprovada. Incluiu 492 testes, cobertura de 85,46%, E2E com FFmpeg/Qt em Python 3.10–3.13, smoke OpenAI Whisper PT-BR/EN, smoke NLLB real com Transformers em CPU, matriz multiplataforma, validação documental e os workflows determinísticos relacionados. Os checks de WhisperX benchmark/CUDA foram marcados como skipped pelos critérios do runner, não como falha.
- **Remodelação arquitetural anterior:** Fases 0–10 integradas à `main`.
- **Fase 1:** concluída e integrada à `main`; baseline real da mídia de 37min10s consolidado em 11/11/2026.
- **Fase 2:** concluída, validada pelo CI e integrada à `main` pela PR #9.
- **Fase 3:** concluída e integrada à `main` pela PR #10, squash `10f6d6d428a1fa5a45a7c7fd13870f48bdf67019`.
- **Fase 4:** concluída e integrada à `main` pela PR [#11](https://github.com/anfalcir/legendar/pull/11), squash `32f20c3a5455dcc16f48e78a742ba4c7018339b5`. CI: 506 testes aprovados, cobertura de 86%, Python 3.10–3.13, Ruff e smoke Whisper/WhisperX CPU PT-BR/EN.
- **Fase 5:** implementação concluída e integrada pela PR [#12](https://github.com/anfalcir/legendar/pull/12), commit `57f68985f1156b1d0c693f4b7d80e6aea145a8d0`; backend faster-whisper/CTranslate2 opt-in, benchmark pareado e smoke de alinhamento para ambos os motores. A homologação no hardware de referência permanece pendente; Whisper continua padrão.
- **Fase 6:** implementação técnica integrada à `main` pela PR [#19](https://github.com/anfalcir/legendar/pull/19), squash `7f337bc10cf210336fbf2367b56aea7e767bce32`. CI específica aprovada no run [43134372712](https://github.com/anfalcir/legendar/actions/runs/43134372712): runtime real NLLB/CPU e suíte determinística em Python 3.10–3.13, lint e formatação. Smoke real Gemini foi skipped porque `GEMINI_API_KEY` não estava disponível. Benchmark pareado real na mídia de 37min10s e revisão humana cega permanecem pendentes. Gemini é opt-in; NLLB continua padrão.
- **CI de referência:** [run 43031178212](https://github.com/anfalcir/legendar/actions/runs/43031178212), 5/5 jobs aprovados no commit auditado.
- **Documentação:** raiz de `docs/` reservada a documentos vivos; histórico anterior preservado em `docs/archive/`.

> Este documento separa comportamento observado no código, resultados confirmados por CI e medições ainda pendentes. Um teste verde de software não equivale a homologação de qualidade audiovisual.

## 1. Resumo executivo

O Legendar é uma aplicação desktop PySide6 que recebe áudio/vídeo, normaliza o áudio, transcreve com Whisper, alinha palavras com WhisperX, forma legendas, traduz localmente com NLLB-200 quando solicitado, valida o trilho e publica SRT por troca atômica.

A arquitetura e a base de engenharia das Fases 0–10 estão integradas. As Fases 2 e 3 corrigiram a integridade textual e a consolidação cronológica da segmentação. A Fase 4 integrou gate editorial estruturado, diagnósticos de leitura/texto, bloqueio de perda de conteúdo e aviso de revisão na interface; tudo integrado à `main` pela PR #11.

As Fases 1–6 estão implementadas e integradas à `main`. A Fase 3 consolidou globalmente as palavras alinhadas; a Fase 4 integrou o gate editorial; e a Fase 5 adicionou o adaptador faster-whisper/CTranslate2, benchmark pareado e smokes de alinhamento. A PR [#12](https://github.com/anfalcir/legendar/pull/12) foi integrada no commit `57f68985f1156b1d0c693f4b7d80e6aea145a8d0`. A Fase 6 adicionou o backend contextual Gemini, benchmark pareado e smoke real opt-in, integrados pela PR [#19](https://github.com/anfalcir/legendar/pull/19), commit `7f337bc10cf210336fbf2367b56aea7e767bce32`. OpenAI Whisper e NLLB permanecem padrões até que os respectivos benchmarks locais e revisões de qualidade aprovem alternativas. O baseline da mídia de 37min10s é ~23min21s; NLLB consome ~14min e segue como gargalo a avaliar.

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
| Reconhecimento | OpenAI Whisper local (`base`) como padrão; `FasterWhisperTranscriber` via CTranslate2 disponível por seleção explícita, ainda não promovido |
| Alinhamento | WhisperX 3.8.6; forced alignment por segmento |
| Segmentação | Fluxo global cronológico integrado; consolida limites do Whisper, preserva fallback e rastreabilidade de origem |
| Tradução | NLLB-200 distilled 600M via Transformers/PyTorch como padrão; Gemini Developer API via `GeminiTranslator` disponível por seleção explícita, ainda em homologação |
| Publicação | SRT com round-trip e gravação atômica |
| Gate editorial | Relatório estruturado com estados `APPROVED`, `REVIEW_REQUIRED` e `BLOCKED`, bloqueio de perda e avisos de revisão; integrado pela PR #11 |
| Benchmark por etapa | Instrumentação integrada; baseline real consolidado em 11/11/2026 |
| Otimização de motores | Fase 5 implementada e integrada; benchmark de hardware pendente para promover faster-whisper. Fase 6 em validação técnica; Fase 7 planejada |
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

1. A segmentação isolada foi substituída pelo fluxo global cronológico de palavras alinhadas na Fase 3, integrada pela PR #10; a homologação audiovisual completa permanece na Fase 8.
2. A subdivisão por velocidade de leitura continua limitada a timestamps reais. A Fase 3 adiciona extensão apenas em silêncio seguro antes da próxima cue.
3. Cues curtas sem silêncio posterior seguro continuam explícitas para avaliação; não recebem duração inventada.
4. A Fase 2 bloqueia a publicação quando há palavras reconhecidas sem âncora temporal confiável, impedindo a perda silenciosa observada na auditoria original.
5. A Fase 4 integrou o gate editorial estruturado; os diagnósticos heurísticos exigem revisão humana e não alteram automaticamente o texto.
6. Os testes E2E determinísticos continuam usando dublês; a homologação com áudio real permanece necessária para avaliar modelos e qualidade audiovisual.
7. O alinhador real ainda chama WhisperX por segmento. O baseline instrumentado está disponível; otimizações de alinhamento não fazem parte do escopo atual.

Esses achados descrevem o código e os testes; não identificam, por si sós, a origem de cada erro textual ou temporal de uma mídia específica. A correlação com áudio de referência exige homologação.

## 6. Desempenho: baseline disponível e limitações

**Baseline operacional consolidado em 11/11/2026:** uma execução fria e três quentes da mídia de referência de 37min10s. A mediana quente foi aproximadamente 23min21s (RTF ~0,63). A tradução NLLB foi o maior estágio, em torno de 14 minutos por execução quente. Os relatórios sanitizados estão preservados em `logs/`; não é necessário reabrir o relato histórico de aproximadamente uma hora.

Configuração atual relevante:

- Transcrição: OpenAI Whisper, padrão `base`, execução PyTorch; faster-whisper/CTranslate2 está disponível por seleção explícita, com INT8 CPU/FP16 CUDA conforme configuração, mas ainda sem promoção operacional.
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
| 4 | Gate editorial e diagnóstico textual | **Concluída e integrada à `main` (PR #11)** |
| 5 | Benchmark e aceleração da transcrição | **Implementação concluída e integrada à `main` (PR #12)**; benchmark local/homologação para promoção do candidato pendentes |
| 6 | Benchmark e aceleração da tradução | **Implementação integrada pela PR #19; smoke real da API, benchmark pareado e revisão humana pendentes** |
| 7 | Gestão de memória, threads e perfis de execução | Planejada |
| 8 | Regressão, homologação real e comparação final | Planejada |

A Fase 5 tem implementação integrada; seu aceite operacional depende da homologação real na Fase 8. A implementação técnica da Fase 6 está integrada e sua CI passou; o aceite operacional do Gemini depende de smoke real da API, benchmark pareado na mídia de referência e revisão humana.

## 8. Critérios que não podem ser sacrificados

- Nenhuma palavra reconhecida pode desaparecer silenciosamente.
- Nenhum timestamp pode ser inventado para encobrir falha de alinhamento.
- A segmentação deve respeitar pausas, continuidade sintática, duração de exibição, CPS e limites de linhas.
- Uma falha editorial grave deve gerar revisão explícita, não um falso sucesso.
- Uma otimização de motor só será adotada após avaliação de WER/CER, cobertura, alinhamento e revisão humana da tradução.
- A publicação continua atômica e só ocorre após os gates definidos.

## 9. Próximas ações

1. Homologar o benchmark pareado da Fase 5 no computador de referência, com áudio de 37min10s e referências humanas, antes de alterar o backend padrão.
2. Fase 6: implementação e CI integradas pela PR #19; cadastrar `GEMINI_API_KEY` como secret no GitHub Actions e no ambiente local antes das chamadas reais; executar smoke da API, benchmark pareado e revisão humana.
3. Exigir do Gemini PT-BR idiomático, interpretação contextual, preservação de entidades/nomenclaturas próprias e consistência terminológica; grounding/pesquisa só poderá apoiar interpretação sem acrescentar conteúdo não falado.
4. Executar a Fase 7 para gestão de memória, threads e perfis de execução, conforme os resultados dos benchmarks.
5. Consolidar a Fase 8 com comparação do pipeline completo, homologação audiovisual com a mídia real, validação no hardware-alvo e evidências sanitizadas.

## 10. Histórico documental

Os protocolos, planos, handoffs e relatórios concluídos da remodelação anterior estão preservados em [archive/README.md](archive/README.md). Eles servem como registro histórico; este arquivo e o plano vigente representam o estado atual.
