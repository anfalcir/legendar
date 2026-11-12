# Plano mestre de correção da qualidade e melhoria de desempenho

- **Documento:** plano vigente de engenharia, critérios de aceite e handoff de execução.
- **Projeto:** Legendar — `anfalcir/legendar`.
- **Data de abertura:** 11/11/2026.
- **Base da auditoria:** `main` em `d3530490df466aa6eeff4728b63d7e8dc22f056e` (início da Fase 1).
- **Status:** Fases 1–6 concluídas na implementação e integradas à `main`. A Fase 6 mantém NLLB e Gemini como backends opcionais, seleção persistente em Preferências e chave Gemini configurável localmente. O smoke real Gemini foi aprovado. O benchmark comparativo NLLB × Gemini permanece como ferramenta futura e não é gate desta fase por decisão de produto.
- **Princípio de aprovação:** melhorar tempo de execução sem degradar a qualidade textual, temporal ou editorial.

Documentos relacionados: [estado atual](ESTADO_ATUAL.md), [arquitetura](ARQUITETURA.md), [decisões](DECISOES.md), [matriz de dependências](MATRIZ_DEPENDENCIAS.md) e [roteiro de homologação](HOMOLOGACAO.md).

---

## 1. Resumo executivo

O baseline operacional consolidado em 11/11/2026 foi de aproximadamente **23min21s para 37min10s de áudio** nas execuções quentes. A tradução NLLB responde por cerca de 14 minutos e foi o principal alvo da Fase 6. A Fase 6 foi encerrada com os dois backends disponíveis e selecionáveis; medições comparativas futuras não bloqueiam a sequência do plano. A auditoria estática do código, por sua vez, identificou problemas que podem produzir um SRT fragmentado, difícil de ler e com perda silenciosa de palavras não alinhadas.

O trabalho será conduzido em duas frentes coordenadas:

1. **Qualidade e integridade:** corrigir o fluxo de dados desde o reconhecimento até a publicação, assegurando que o conteúdo reconhecido seja preservado, o alinhamento seja confiável e a segmentação forme legendas confortáveis.
2. **Desempenho:** medir o custo real de cada estágio e avaliar implementações, quantização, batching, threads e gestão de memória. Uma alteração só entra no produto quando a qualidade permanece equivalente.

Não se pretende substituir toda a arquitetura nem trocar todos os modelos de uma vez. Whisper, WhisperX e NLLB atuais serão mantidos como baseline de comparação até que uma alternativa passe pelos mesmos testes.

## 2. Contexto e baseline

### 2.1. Resultado operacional reportado

| Indicador | Valor inicial | Natureza |
|---|---:|---|
| Duração da mídia | 37min10s | Mídia de referência |
| Tempo total (mediana quente) | aproximadamente 23min21s | Baseline medido na Fase 1 |
| RTF global aproximado | 0,63 | Calculado a partir da mediana quente |
| Tempo de tradução NLLB | aproximadamente 14 min | Maior estágio medido |
| Tempo dos demais estágios | disponível nos relatórios sanitizados em `logs/` | Instrumentação da Fase 1 |
| Perfil de hardware/execução | registrado no inventário da Fase 1 | Reexecutar antes de benchmarks futuros |

A decomposição da Fase 1 já mediu as etapas individualmente, distinguindo carregamento de modelos, inferência e preparação. Não é necessário reabrir a discrepância histórica de aproximadamente uma hora.

### 2.2. Perfil de hardware conhecido

O inventário de ambiente arquivado da Fase 0 registrou, na máquina então inspecionada:

- AMD Ryzen 3 2200G;
- quatro CPUs lógicas;
- aproximadamente 12,59 GiB de RAM;
- vídeo integrado Radeon Vega;
- ausência de GPU NVIDIA/CUDA naquele inventário.

O inventário é antigo e não deve ser tratado como estado garantido da máquina atual. Reexecutar `scripts/phase0_inventory.py --probe-torch` antes dos benchmarks e registrar CPU, núcleos físicos/lógicos, RAM disponível, GPU, backend e versões.

A estratégia precisa funcionar bem em CPU. CUDA, MPS ou outros backends compatíveis serão otimizados quando detectados, mas não serão pré-requisito para uma aplicação utilizável.

### 2.3. Configuração atual identificada no código

| Etapa | Implementação atual | Observação técnica |
|---|---|---|
| Reconhecimento | `WhisperTranscriber` / OpenAI Whisper | Padrão `base`, PyTorch; execução atual não usa word timestamps |
| Alinhamento | `WhisperXAligner` | WhisperX 3.8.6; chama `whisperx.align` por segmento original |
| Segmentação | `segment_alignment` | Fase 3 substitui processamento isolado por fluxo global de palavras, com rastreabilidade de origem |
| Tradução | `NllbTranslator` | NLLB-200 distilled 600M via Transformers/PyTorch |
| Parâmetros da tradução | `batch_size=16`, `num_beams=4` | Já existe batching; há oportunidades para otimizar sua composição e a geração |
| Publicação | `SrtPublisher` | Round-trip e gravação atômica |

A implementação NLLB usa `torch.inference_mode()`, portanto o plano não presume que a ausência desse mecanismo seja o gargalo. O custo deverá ser decomposto em tokenização, padding, transferência, geração autoregressiva e decodificação do resultado.

### 2.4. Limites da evidência atual

A auditoria foi estática e identificou caminhos de código e lacunas dos testes. Ela não mede, por si só, o erro temporal no áudio de 37 minutos nem atribui cada erro textual a Whisper, WhisperX ou NLLB. A comparação experimental e a referência humana são etapas obrigatórias.

---

## 3. Objetivos de produto

### 3.1. Qualidade

O SRT aprovado deverá:

1. Preservar todo o conteúdo reconhecido, sem omissões silenciosas.
2. Não atribuir timestamps finais fabricados a palavras sem evidência temporal.
3. Manter início e fim coerentes com a fala e com a linha do tempo original.
4. Formar cues contínuas e legíveis, sem fragmentação artificial.
5. Respeitar largura, número de linhas, duração e velocidade de leitura.
6. Evitar repetições anômalas, caracteres inesperados e saídas vazias ou suspeitas.
7. Manter a consistência de nomes próprios, números, siglas e vocabulário do domínio na tradução.
8. Informar claramente quando a automação não tem evidência suficiente para publicar um resultado confiável.

### 3.2. Desempenho

- **Meta inicial de aceite:** redução de pelo menos 20% na mediana do tempo total da execução completa, em comparação pareada com o baseline, sem degradação mensurável da qualidade.
- **Meta aspiracional:** redução de 30% ou mais no tempo total. Isso não é promessa de desempenho nem justificativa para aceitar regressão.
- **Meta por gargalo:** uma otimização deverá reduzir de forma material o estágio que pretende corrigir; como referência de experimento, buscar pelo menos 1,5× de throughput quando a alternativa e o hardware permitirem.
- **Condição inegociável:** se uma configuração mais rápida não atingir os gates de qualidade, ela não será adotada como padrão.

A meta global é deliberadamente moderada porque a aceleração teórica de uma etapa não se converte integralmente em aceleração do job completo. A Lei de Amdahl e os custos de carregamento, memória e sincronização precisam ser considerados.

---

## 4. Critérios de qualidade e métricas

Os limites a seguir são critérios propostos para orientar os testes. Os valores já existentes no código ou no avaliador permanecem identificados como baseline; os demais serão calibrados na Fase 1/2 com corpus representativo.

### 4.1. Integridade textual

- Cada palavra/token da transcrição deve ser contabilizado no resultado: publicado, explicitamente não alinhado com revisão requerida ou rejeitado por uma regra documentada.
- Nenhuma palavra não alinhada pode simplesmente desaparecer porque a segmentação filtrou `word.range is None`.
- A publicação automática de um trilho com conteúdo reconhecido sem timestamp confiável deve ser bloqueada até que exista recuperação validada ou revisão explícita.
- O sistema não pode compensar uma palavra não alinhada copiando o timestamp de outra palavra ou usando silenciosamente a janela aproximada do Whisper como timestamp final.
- A reconciliação deverá considerar pontuação, contrações, palavras repetidas e tokens omitidos sem deslocar o alinhamento das palavras seguintes.

### 4.2. Reconhecimento (ASR)

Avaliar com manifesto de áudio e transcrição humana revisada:

- WER e CER;
- nomes próprios, números, datas, referências e siglas;
- falsos trechos de fala em silêncio;
- repetições de palavras/frases;
- omissões e inserções;
- consistência entre início, meio e fim da mídia.

**Gate comparativo proposto:** a alternativa não poderá piorar WER/CER em mais de 0,5 ponto percentual absoluto frente ao baseline no mesmo corpus, e nenhuma regressão crítica poderá ocorrer em nomes, números, negações ou trechos representativos. A amostra e a margem devem ser congeladas antes do experimento.

### 4.3. Alinhamento temporal

O avaliador `scripts/phase5_alignment_evaluation.py` já possui metas provisórias de erro de fronteira:

- mediana de início/fim ≤ 150 ms;
- P95 de início/fim ≤ 350 ms.

Esses valores são **metas provisórias existentes**, ainda pendentes de homologação em fala real. A Fase 2 deverá medir:

- erro absoluto do início e do fim;
- mediana e P95;
- cobertura de palavras alinhadas;
- número de palavras sem alinhamento;
- sobreposições, janelas inválidas e scores;
- erros por idioma, ruído, fala rápida e tipo de mídia.

Uma taxa global de alinhamento não substitui a análise dos casos não alinhados. Palavra sem âncora deve continuar explícita.

### 4.4. Legibilidade e estabilidade visual

Manter como ponto de partida editorial:

- até duas linhas por cue;
- até 42 caracteres por linha;
- alvo de aproximadamente 17 caracteres por segundo;
- duração preferencial entre 1 e 7 segundos;
- quebra em limites de frase/oração e respeito a pausas;
- ausência de sobreposição e ordem temporal válida.

A regra de 1 segundo não pode ser aplicada como extensão arbitrária sobre fala ou sobre a legenda seguinte. Deve-se distinguir:

- **intervalo de fala:** âncoras provenientes das palavras alinhadas;
- **intervalo de exibição:** intervalo escolhido para manter a legenda visível enquanto houver silêncio seguro, limitado pela próxima cue e pelo fim da mídia.

Uma cue curta poderá ser estendida somente dentro de silêncio disponível e de limites explícitos. Quando não existir silêncio suficiente, o algoritmo deve tentar consolidar conteúdo contíguo; se ainda assim não houver solução, registrar uma exceção ou exigir revisão, em vez de criar uma sequência de flashes.

Métricas adicionais:

- cues abaixo da duração mínima;
- CPS por cue e P95 do CPS;
- mudanças de legenda por minuto;
- cues de uma palavra isolada sem justificativa;
- fragmentos iniciados/encerrados em limites sintáticos ruins;
- pausas entre cues e distância da próxima fala;
- repetição consecutiva e duplicação textual.

### 4.5. Tradução

A comparação deve combinar:

- revisão humana bilíngue cega entre baseline e candidato;
- preservação de sentido, negação, sujeito e tempo verbal;
- consistência de nomes próprios e termos recorrentes;
- números, referências e siglas;
- adequação ao contexto da frase e da legenda vizinha;
- comprimento final e CPS após tradução.

Não aceitar uma tradução apenas porque devolveu um texto não vazio ou alterou o idioma. Uma saída pode ser lexicalmente plausível e semanticamente incorreta.

### 4.6. Critérios de bloqueio e aviso

A Fase 4 introduzirá um resultado estruturado de qualidade com estados como:

- `APPROVED`: sem falhas críticas e dentro dos critérios aceitos;
- `REVIEW_REQUIRED`: conteúdo preservado, mas há problemas que precisam de decisão humana;
- `BLOCKED`: conteúdo perdido, timestamp não confiável, estrutura inválida ou risco crítico.

A política exata será testada e documentada. Uma interjeição legítima de curta duração não deve ser tratada como falha automaticamente; a exceção precisa ser identificável e auditável.

---

## 5. Fases de execução

### Fase 0 — Auditoria, organização documental e plano

**Objetivo:** estabelecer uma fonte de verdade para a nova frente.

Entregas:
- auditoria estática do pipeline e testes existentes;
- classificação de problemas confirmados, hipóteses e medições pendentes;
- documentos históricos arquivados sem apagar o conteúdo;
- este plano mestre, métricas e fases;
- atualização de estado, decisões e matriz de dependências.

**Critério de conclusão:** documentação viva consistente e plano aprovado para execução. Esta entrega documental cobre essa fase; não significa que as correções de código estejam realizadas.

### Fase 1 — Instrumentação e baseline de desempenho

**Objetivo:** descobrir o tempo e o custo real de cada etapa, antes de alterar os motores.

Entregas:

1. Medição monotônica de duração de cada estágio: aquisição, inspeção, preparação, transcrição, alinhamento, segmentação, tradução, validação e publicação.
2. Medição separada de inicialização/carregamento de modelos e inferência.
3. Relatório sanitizado com:
   - duração e RTF por etapa;
   - throughput de áudio, tokens e cues quando aplicável;
   - CPU, núcleos físicos/lógicos, RAM e GPU;
   - RSS máximo e memória livre antes/depois dos estágios;
   - modelo, versão, dispositivo, dtype, beam, batch e threads;
   - número de segmentos, palavras, cues e lotes;
   - cobertura de alinhamento e quantidade de avisos.
4. Distinguir execução **fria** (cache/carregamento) de execução **quente** (modelos disponíveis).
5. Criar benchmark repetível com a mídia de 37 minutos e amostras menores representativas.
6. Preservar privacidade: relatório não deve conter áudio, transcrição, legenda, URLs privadas, caminhos pessoais ou credenciais.

**Protocolo comparativo:** mesma mídia, hardware, versão, idioma, destino, cache e configuração; pelo menos três execuções quentes por candidato quando viável; comparar mediana, dispersão e pico de memória. Registrar a execução fria separadamente.

**Implementação da Fase 1 (11/11/2026):**

- Criada instrumentação monotônica no pipeline para aquisição, inspeção, preparação do áudio, transcrição, alinhamento, segmentação, tradução opcional, validação e publicação.
- O relatório registra tempo de parede e CPU do processo por etapa, snapshots de RSS/memória disponível antes/depois, duração da mídia, contagens de segmentos/palavras/cues/avisos e status de conclusão, falha ou cancelamento.
- Os adaptadores Whisper, WhisperX e NLLB expõem snapshots numéricos sanitizados. O custo de carregamento (incluindo eventual download/cache frio) é separado do custo de inferência; o alinhador acumula o custo de cada chamada por segmento; NLLB separa tokenização, transferência, geração e decodificação.
- O relatório local inclui CPU, núcleos físicos/lógicos quando detectáveis, RAM, adaptadores gráficos, versões relevantes, ferramentas FFmpeg/ffprobe e configuração de modelo/dispositivo/beam/batch.
- Relatórios ficam em `~/.cache/legendar/logs/performance/`, com diretório privado e arquivos `0600`. Não são enviados à rede e não incluem mídia, transcrição, texto de legenda, URL, caminho da mídia, mensagem de exceção ou credenciais.
- O resumo `scripts/phase1_performance_summary.py` calcula tempos e RTF por etapa e destaca o throughput de geração da tradução quando mensurável.
- A instrumentação é best-effort: falha ao escrever o relatório é registrada no log e não altera o resultado do job.
- Testes unitários cobrem medição, delta de contadores, anonimização, permissões e integração com o pipeline.

**Integração e validação de código:** concluídas pela PR [#8](https://github.com/anfalcir/legendar/pull/8), squash `12e3f40db5fe9b849f1a51715802eea7dba0449e`. CI aprovada com 492 testes, cobertura de 85,46%, E2E FFmpeg/Qt em Python 3.10–3.13, smoke Whisper PT-BR/EN, smoke NLLB real em CPU, matriz multiplataforma e validação documental.

**Conclusão da Fase 1 (11/11/2026):**

1. Inventário atualizado do equipamento de homologação registrado junto aos relatórios.
2. Uma execução fria e três execuções quentes da mídia real de 37min10s foram capturadas.
3. A mediana das execuções quentes ficou em aproximadamente 23min21s (RTF ~0,63).
4. A tradução NLLB foi confirmada como estágio dominante, com aproximadamente 14 minutos por execução quente.
5. Os relatórios sanitizados e o inventário foram preservados em `logs/` no repositório para rastreabilidade.

**Critério de conclusão atendido:** baseline reproduzível com decomposição temporal dos estágios, sem alterar os motores ou parâmetros de qualidade. A Fase 1 está encerrada; novas otimizações de performance passam a ser tratadas nas fases específicas de aceleração.

### Fase 2 — Integridade textual e robustez do alinhamento

**Objetivo:** impedir perda silenciosa de conteúdo e tornar a falha de alinhamento recuperável ou explícita.

Entregas:

1. Contrato de conservação do texto reconhecido entre transcrição, alinhamento, segmentação e resultado.
2. Reconciliação de palavras alinhadas/não alinhadas que não descarte tokens sem timestamp.
3. Tentativas de recuperação controladas para janelas inválidas ou palavras omitidas, sem inventar tempos.
4. Avaliação de uma segunda tentativa de alinhamento com janelas maiores/agrupadas, desde que preserve as posições e não misture falas diferentes.
5. Diagnóstico por palavra e segmento, com score e motivo de não alinhamento.
6. Regra de bloqueio de publicação quando houver conteúdo reconhecido sem destino temporal confiável.
7. Testes para palavras repetidas, pontuação, contrações, omissão de token, nomes próprios, sobreposição, offset e fim de mídia.

**Critério de conclusão:** nenhum token reconhecido desaparece silenciosamente; toda palavra sem âncora termina alinhada por método validado ou exige revisão. A timeline global continua correta.

**Implementação e conclusão da Fase 2 (11/11/2026):**

- O domínio já preservava palavras não alinhadas; a segmentação passou a carregar explicitamente `unmatched_words` e a considerar o resultado não lossless quando houver conteúdo sem âncora temporal.
- O pipeline deixou de transformar palavras sem alinhamento em simples aviso: `AlignmentInsufficientError` bloqueia a publicação antes da segmentação/publicação quando existe qualquer palavra reconhecida sem evidência temporal confiável.
- O adaptador WhisperX ganhou uma segunda tentativa controlada somente para segmentos com palavras não alinhadas. A janela é ampliada em até 0,75 s por lado, limitada pela duração do áudio e pelo máximo configurado, e a resposta passa pelo mesmo casamento textual, validação temporal e score. Se a segunda tentativa não melhorar a cobertura, o primeiro resultado é preservado.
- A recuperação não interpola timestamps, não copia janelas aproximadas para palavras e não desloca palavras seguintes para preencher lacunas.
- Foram adicionadas métricas sanitizadas de tentativas, tempo de recuperação e palavras recuperadas ao snapshot de performance.
- Testes cobrem perda explícita, bloqueio de publicação e recuperação com janela ampliada.

**Critério de conclusão atendido:** nenhuma palavra reconhecida sem âncora temporal chega à publicação; a recuperação usa somente evidência produzida pelo alinhador. CI verde e merge na `main` concluídos pela PR #9. A homologação audiovisual de precisão continua sendo gate posterior.

### Fase 3 — Segmentação global e legibilidade

**Objetivo:** substituir a segmentação isolada por segmento por uma estratégia editorial que considere a sequência contínua de palavras alinhadas.

Entregas:

1. Construir fluxo cronológico de palavras, preservando referências aos segmentos de origem.
2. Permitir consolidar palavras através de limites do Whisper quando a fala for contínua.
3. Respeitar pausas, pontuação, fim de frase, mudanças de turno detectáveis, lacunas e limites reais.
4. Otimizar a escolha de fronteiras para equilibrar comprimento de texto, duração, CPS e sintaxe.
5. Evitar subdividir automaticamente uma cue em flashes quando o problema é falta de tempo de leitura.
6. Separar tempo de fala de tempo de exibição, permitindo extensão somente dentro de silêncio seguro.
7. Tratar cues curtas legítimas como exceções explícitas.
8. Preservar todo o texto, sem sobreposição, duplicação ou reordenação.
9. Recalcular o layout após tradução, pois o comprimento no idioma final muda.

**Critério de conclusão:** corpus determinístico de alinhamentos comprova redução de fragmentação artificial, conservação textual, estabilidade temporal, tratamento de pausas/frases e respeito aos limites editoriais; CI completa verde. A homologação audiovisual com mídia real, player e comparação humana fica concentrada na Fase 8, para não confundir a validação do algoritmo puro com a validação ponta a ponta do modelo e do áudio.

**Implementação concluída e integrada à `main` (11/11/2026, PR #10):**

- A segmentação passou a construir um fluxo global cronológico de palavras alinhadas, em vez de reiniciar o agrupamento em cada segmento do Whisper. Segmentos sem timestamps por palavra são preservados em sua própria janela e funcionam como barreiras, impedindo que cues alinhadas de antes/depois os absorvam.
- As cues podem atravessar limites artificiais do ASR quando há continuidade temporal e textual; pausas, pontuação, limite de caracteres e duração continuam determinando fronteiras.
- Cada cue preserva os índices de todos os segmentos de origem em `source_segments`.
- A entrada fora de ordem cronológica — inclusive segmentos sem word timestamps — é rejeitada explicitamente; o sistema não reordena silenciosamente palavras e não altera o texto falado.
- Fronteiras de frase são respeitadas também em frases concisas quando a duração real de fala já oferece massa temporal suficiente; pausas e limites de pontuação participam da escolha editorial.
- Cues curtas podem ganhar tempo de exibição até a duração mínima ou o tempo de leitura calculado, somente dentro do silêncio anterior à próxima cue e com margem de segurança de 80 ms. A última cue não é estendida sem evidência do fim da mídia.
- O SRT aplica quebra de linha pelo layout de domínio já existente (até duas linhas de 42 caracteres); a segmentação mantém texto normalizado e o round-trip valida o conteúdo sem alterar palavras.
- O alinhador atual não oferece diarização confiável de falantes. A Fase 3 não infere mudança de interlocutor: usa cronologia, pausas e pontuação, mantendo essa limitação documentada.
- Testes foram adicionados para consolidação entre segmentos, pausas, rastreabilidade, cronologia inválida em segmentos alinhados e fallback, preservação de segmentos fallback intercalados, fronteira de frase e extensão segura.

**Resultado e evidências:** corpus determinístico cobre continuidade entre segmentos, pausas, fronteiras de frase, divisão por CPS, extensão segura, segmentos fallback intercalados, rastreabilidade e rejeição de cronologia inválida. A redução de fragmentação artificial é comprovada por cenários em que dois segmentos contíguos do ASR passam a formar uma cue única, enquanto pausas e fronteiras de frase continuam gerando cues separadas. PR #10 foi integrada à `main` por squash no commit `10f6d6d428a1fa5a45a7c7fd13870f48bdf67019`. A CI específica da Fase 3 passou em Python 3.10–3.13, com 506 testes aprovados, cobertura global de 86%, Ruff lint/formatação e FFmpeg/Qt/E2E aprovados. Workflows das Fases 4, 5, 6 e 8 também passaram no mesmo head. A homologação audiovisual com o arquivo real de 37min10s permanece planejada na Fase 8.

### Fase 4 — Gate editorial e diagnóstico de texto

**Objetivo:** impedir que um SRT estruturalmente válido, mas editorialmente ruim, seja apresentado como aprovado.

Entregas:

- resultado de qualidade estruturado em vez de avisos livres;
- bloqueios para perda de conteúdo, timestamps inválidos e erros críticos;
- alertas de CPS, duração, cue curta, cue longa, quebra sintática e flicker;
- detecção de segmentos repetidos, loops, duplicações e texto suspeito em silêncio;
- verificação de caracteres fora do conjunto esperado, sem proibir idiomas, nomes ou símbolos legítimos;
- verificação de números, nomes, siglas e termos frequentes;
- resumo final com contagem de cues aprovadas, exceções e revisão requerida;
- logs e interface mostrando motivo e etapa, sem esconder o detalhe técnico.

A detecção de repetição não deve remover texto automaticamente: repetição pode ser falada de verdade. O sistema deve identificar candidatos e preservar o conteúdo até haver evidência de erro.

**Critério de conclusão:** os defeitos conhecidos geram alerta ou bloqueio verificável, com testes positivos e negativos; nenhum mecanismo de limpeza apaga fala legítima.

**Implementação concluída e integrada à `main` (11/11/2026):**

- Criado relatório estruturado `TrackValidationReport`, com estados `APPROVED`, `REVIEW_REQUIRED` e `BLOCKED`, issues identificáveis, severidade, índices das cues, contagem, CPS máximo e P95.
- O gate classifica duração curta/longa, velocidade de leitura, largura, fragmentos após conectivos/preposições, sequências rápidas de cues curtas (flicker), duplicações consecutivas próximas, caracteres de controle/substituição e loops de palavras.
- Na tradução, compara números e siglas em relação ao trilho-fonte. O detector é conservador: nomes próprios e terminologia não são considerados validados automaticamente apenas por capitalização.
- Segmentos de origem com texto que não chegaram ao SRT bloqueiam a publicação; segmentos vazios não são tratados como perda de conteúdo.
- Problemas editoriais não críticos preservam o SRT, mas marcam o resultado como `REVIEW_REQUIRED`; a interface recebe um aviso final com detalhes das primeiras ocorrências. Nenhuma regra apaga ou reescreve fala.
- Os testes cobrem estados, métricas, duplicações, texto suspeito, loops, fronteiras sintáticas, invariantes de tradução e bloqueio antes da chamada ao publicador.

**Limites explícitos desta entrega:** o pipeline atual não dispõe de medição de energia/VAD no estágio editorial; portanto, o gate não afirma detectar texto pronunciado durante silêncio real. A consistência de nomes próprios e termos recorrentes exige glossário/avaliação contextual e continuará sendo validada no trabalho de tradução da Fase 6 e na homologação da Fase 8. Os alertas heurísticos são candidatos à revisão, não correções automáticas.

**Integração e evidências:** PR [#11](https://github.com/anfalcir/legendar/pull/11), squash `32f20c3a5455dcc16f48e78a742ba4c7018339b5`. O workflow [Phase 4 quality](https://github.com/anfalcir/legendar/actions/runs/43114553749) passou integralmente: 506 testes aprovados, 10 testes E2E/integration ignorados nos jobs determinísticos sem FFmpeg, cobertura de 86%, Python 3.10–3.13, Ruff lint/format e smoke Whisper/WhisperX CPU PT-BR/EN. Os workflows relacionados das Fases 0, 1, 3, 5, 6 e 8 também passaram sobre o mesmo commit.

### Fase 5 — Benchmark e aceleração da transcrição (ASR)

<escape>**Status da implementação: concluída e integrada à `main` pela PR [#12](https://github.com/anfalcir/legendar/pull/12), commit `57f68985f1156b1d0c693f4b7d80e6aea145a8d0`.**</escape>

Foi implementado `FasterWhisperTranscriber` via CTranslate2 atrás da porta `Transcriber`, com seleção explícita por `LEGENDAR_ASR_BACKEND`; OpenAI Whisper permanece como padrão e fallback configurável. O pacote não é selecionado automaticamente por estar instalado. Foram adicionados controles de compute type, threads, beam e VAD (desligado por padrão), consumo integral do generator, cancelamento cooperativo, métricas e benchmark pareado WER/CER/RTF. O smoke de alinhamento envia ambos os backends ao mesmo WhisperX.

**Pendente, sem bloquear a conclusão da implementação:** benchmark no computador de referência com o áudio de 37min10s e corpus representativo com referência humana, incluindo comparação fria/quente, WER/CER, revisão de nomes/números/negações, cobertura do WhisperX e memória. Até essa homologação, não promover faster-whisper a padrão nem declarar ganho real no hardware do usuário.

**Objetivo:** reduzir o tempo de reconhecimento sem perda de fidelidade.

Baseline:
- adaptador atual `WhisperTranscriber`;
- modelo padrão `base`;
- PyTorch;
- reconhecimento sem timestamps de palavra, pois o forced alignment é uma etapa posterior.

Implementação integrada pela Fase 5:

**A. faster-whisper / CTranslate2**

- `FasterWhisperTranscriber` implementado atrás da mesma porta `Transcriber`.
- Seleção explícita por `LEGENDAR_ASR_BACKEND`; OpenAI Whisper permanece padrão.
- CPU INT8 e CUDA FP16 como escolhas automáticas iniciais por dispositivo, com compute type configurável.
- Threads limitadas/configuráveis e beam compartilhado entre os adaptadores para comparação justa.
- Consumo integral do generator, cancelamento cooperativo e preservação de `alignment_window` local ao WAV.
- Métricas separadas de carga, leitura de áudio e inferência.

Benchmark/homologação ainda necessários para decisão operacional:
- Comparar mesmo tamanho de modelo, idioma, corpus e estratégia de decodificação.
- Medir CPU `int8`, GPU `float16` e, quando suportado, `int8_float16` no hardware real.
- Revisar WER/CER, nomes, números, negações e trechos difíceis com referência humana.
- Confirmar cobertura e qualidade do WhisperX após cada backend.

A documentação do faster-whisper expõe execução INT8 em CPU, FP16 em GPU, timestamps de palavra e VAD opcional. A adoção não é automática: os parâmetros de decoding e o comportamento do VAD precisam ser comparados com o Whisper atual.

**B. VAD e silêncio**

- Medir proporção de silêncio e tempo gasto no reconhecimento.
- Testar VAD como experimento separado, primeiro com parâmetros conservadores.
- Verificar se pausas, fala baixa, início/fim de palavra e timestamps restaurados permanecem corretos.
- Não habilitar VAD por padrão se houver perda de fala ou mudança de alinhamento.

**C. Modelo e decoding**

- Comparar `base`, `small` e os demais perfis pertinentes, sem assumir que modelo menor será aceitável.
- Manter o baseline de qualidade para cada idioma e trecho.
- Testar parâmetros de beam e threads individualmente.
- Não quebrar o áudio em janelas paralelas sem estratégia de overlap, contexto e reconciliação testada; paralelismo ingênuo pode duplicar ou perder palavras nas fronteiras.

**D. CPU e execução**

- Medir threads intra/inter-op e `cpu_threads` do backend.
- Evitar oversubscription: o produto não deve alocar mais threads totais do que os núcleos físicos disponíveis sem evidência de ganho.
- Ajustar lote e paralelismo por perfil de hardware.
- Manter interface responsiva e progresso honesto.

**Critério de conclusão da implementação:** adaptador, seleção explícita, benchmark reproduzível, integração com WhisperX, testes e CI documentados e integrados à `main` — concluído pela PR #12. **Critério para promoção operacional do candidato:** WER/CER dentro do gate, qualidade de nomes/números preservada, alinhamento posterior aprovado e ganho de tempo demonstrado no hardware de referência — pendente de homologação local/Fase 8.

### Fase 6 — Benchmark e aceleração da tradução

**Objetivo:** reduzir o custo da tradução sem degradar sentido, terminologia, consistência ou integridade das cues.

**Status:** **concluída**. A implementação mantém `NllbTranslator` e `GeminiTranslator` atrás da mesma porta `Translator`, com NLLB como padrão e Gemini como opção explícita. O usuário escolhe o motor em Preferências e configura a chave Gemini localmente; a troca é aplicada aos próximos jobs sem reinício. O smoke real Gemini foi aprovado. O benchmark comparativo permanece disponível, mas não é gate desta fase por decisão de produto.

**Diretriz de tradução contextual:** permanece integralmente implementada no `GeminiTranslator`, incluindo PT-BR idiomático, preservação de nomes/entidades, contexto entre cues, grounding opcional, JSON estruturado e validação 1:1.

**Entregas concluídas:**
- adaptador Gemini contextual via Developer API;
- NLLB preservado como backend local padrão;
- seleção persistente do backend em Preferências;
- configuração, substituição e remoção da chave Gemini pela GUI;
- armazenamento local da chave fora do QSettings, logs e relatórios;
- reconfiguração do tradutor sem reinício;
- testes unitários da credencial local e persistência da preferência;
- documentação e critérios de aceite atualizados.

**Ferramenta preservada para avaliação futura:** `scripts/phase6_translation_benchmark.py` continua disponível para comparar tempo, throughput, tokens e qualidade quando houver decisão de executar esse experimento. Nenhuma execução comparativa é exigida para iniciar a Fase 7.

### Fase 7 — Gestão de memória, threads e perfis

**Objetivo:** evitar que a aceleração de uma etapa seja anulada por pressão de RAM, swapping ou disputa de CPU.

**Status:** **implementação concluída e preparada para homologação pareada no hardware de referência**. A Fase 7 introduz política explícita de recursos, evicção segura de modelos entre etapas em perfil de pouca memória, configuração de threads CPU antes da primeira inferência e registro do perfil efetivo no relatório de desempenho.

Entregas implementadas:
- perfil `auto`, `low-memory`, `balanced` e `performance`;
- modo `auto` conservador para máquinas com menos de 16 GiB de RAM;
- perfil `low-memory` libera Whisper após transcrição, WhisperX após alinhamento e NLLB após tradução;
- pesos/checkpoints continuam no cache em disco; somente objetos residentes e caches de backend são liberados;
- perfil `balanced` preserva modelos residentes para favorecer jobs repetidos;
- perfil `performance` prioriza retenção e maior paralelismo CPU;
- threads PyTorch intra-op/inter-op configuráveis por ambiente e definidas antes da primeira inferência;
- política registrada nos metadados sanitizados do job;
- falha de evicção é best-effort e não altera o resultado do job;
- testes unitários cobrem perfis, evicção e overrides de threads.

Configuração:
- `LEGENDAR_RESOURCE_PROFILE=auto|low-memory|balanced|performance`;
- `LEGENDAR_CPU_THREADS=N`;
- `LEGENDAR_CPU_INTEROP_THREADS=N`.

**Decisão:** `auto` é o padrão. Em hardware com menos de 16 GiB, o produto prefere evitar manter simultaneamente os modelos pesados residentes. Em hardware maior, mantém os modelos para reduzir recargas. A escolha pode ser sobrescrita explicitamente sem alterar o cache em disco.

**Critério de conclusão:** a implementação atende ao controle de recursos; o aceite de desempenho continua condicionado à medição pareada no hardware de referência, porque não é tecnicamente válido declarar ganho de tempo ou ausência de swapping sem executar o protocolo no equipamento real.

### Fase 8 — Regressão, homologação e liberação

**Objetivo:** comprovar a melhoria no pipeline completo e congelar uma baseline nova.

Entregas:

1. Testes unitários para integridade textual, alinhamento, segmentação, gate e tradução.
2. E2E determinístico com dublês para contratos e publicação.
3. E2E real separado, opt-in, com modelos instalados e corpus autorizado.
4. Corpus de avaliação local com amostras PT-BR e EN e referências revisadas.
5. Comparação antes/depois com a mesma mídia de 37 minutos.
6. Medição fria e quente, três execuções quentes quando viável, mediana e dispersão.
7. Inspeção do SRT em player real, com trechos anotados para sincronização e legibilidade.
8. Atualização de documentação, matriz de dependências e decisões.
9. CI verde, lock reproduzível e revisão do diff antes de merge.

**Critério de conclusão:** todos os gates de qualidade atendidos, ganho de tempo documentado, nenhum erro crítico aberto e homologação no hardware-alvo concluída.

---

## 6. Estratégia de benchmark e comparação

### 6.1. Matriz de execução

| Cenário | Reconhecimento | Tradução | Objetivo |
|---|---|---|---|
| B0 — baseline | Whisper atual | NLLB Transformers atual | Referência imutável |
| B1 | faster-whisper, mesmo perfil de modelo | NLLB atual | Isolar ganho de ASR |
| B2 | ASR aprovado | CTranslate2 NLLB candidato | Isolar ganho de tradução |
| B3 | ASR aprovado | NLLB com batch/beam alternativos | Ajustar throughput e qualidade |
| B4 | configuração combinada aprovada | configuração combinada aprovada | Ver ganho total e efeitos de interação |

Não trocar ASR e tradução simultaneamente no primeiro experimento. Isso impede atribuição causal e dificulta localizar regressões.

### 6.2. Protocolo

- Fixar arquivo, versão, idioma, hardware, parâmetros e pesos.
- Excluir downloads de modelo do benchmark quente, mas medir a carga inicial separadamente.
- Fazer pelo menos três execuções quentes por configuração quando o ambiente permitir.
- Intercalar baseline e candidato ou executar em condições térmicas comparáveis.
- Não executar outras tarefas pesadas durante o teste.
- Registrar tempo por estágio, RSS máximo, CPU, GPU, dispositivo e threads.
- Comparar mediana e dispersão, não apenas a melhor execução.
- Guardar áudio e referências em ambiente local autorizado; no Git entram apenas testes sintéticos e métricas sanitizadas.

### 6.3. Corpus de referência

Priorizar trechos representativos de:
- fala contínua;
- pausas longas e curtas;
- fala rápida;
- palavras repetidas;
- nomes próprios e termos religiosos;
- números, datas, siglas e referências;
- ruído, música de fundo e fala baixa;
- começo e fim de mídia;
- português brasileiro e inglês.

A mídia completa de 37 minutos será usada para o benchmark de desempenho. Para métricas lexicais/temporais, construir amostras com texto e fronteiras humanas revisadas, sem subir mídia privada ou transcrição confidencial ao repositório.

---

## 7. Como priorizar gargalos e evitar otimização prematura

### Transcrição

Investigar primeiro:
1. custo real de inferência do Whisper base;
2. faster-whisper/CTranslate2 no mesmo tamanho de modelo e parâmetros comparáveis;
3. INT8 em CPU e FP16 quando houver GPU suportada;
4. threads e aproveitamento do hardware;
5. VAD como experimento separado;
6. tamanho do modelo e parâmetros de decodificação.

Não reduzir o modelo nem a busca de decoding apenas por tempo sem medir WER/CER e revisar nomes/números.

### Tradução

Investigar primeiro:
1. tempo de geração por token;
2. custo de `num_beams=4`;
3. CTranslate2 com NLLB convertido;
4. quantização suportada pelo hardware real;
5. bucketing por comprimento e padding;
6. tamanho de batch e orçamento de tokens;
7. contexto e glossário sem perda de correspondência 1:1.

O lote atual de 16 cues já é uma otimização existente. A hipótese de ganho está no backend, no decoding, na quantização e na formação de batches mais eficientes.