# Fase 8.1 — Auditoria de regressão, confiabilidade de tradução, legibilidade PT-BR e desempenho

- **Projeto:** Legendar — `anfalcir/legendar`
- **Data da auditoria:** 12/11/2026
- **Base auditada:** `main`, commit `92ac98dbef5748bf008f54fb2d4db3ad9a1d14d9`
- **Status:** plano elaborado a partir dos testes reais; **execução das correções ainda não iniciada**
- **Relação com a Fase 8:** incremento corretivo da homologação. A Fase 8 continua aberta até que a implementação da Fase 8.1 seja concluída e a homologação integral volte a passar.
- **Documento de referência:** [plano mestre](PLANO_CORRECAO_MELHORIA.md) · [estado atual](ESTADO_ATUAL.md) · [roteiro de homologação](HOMOLOGACAO.md)

---

## 1. Objetivo e regra de condução

A Fase 8.1 transforma os resultados reais de 12/11/2026 em um plano cirúrgico de correção. O trabalho deverá resolver, em ordem de dependência:

1. falha de lote e recuperação segura da tradução Gemini;
2. regressão de desempenho associada à política de threads, sem confundir esse problema com a política de retenção de modelos;
3. fragmentação de cues e ausência de composição de frases curtas;
4. vazamento de PT-PT, erros semânticos e falta de contexto suficiente na tradução;
5. divergência entre formatação SRT, validador de produção e avaliador da Fase 8;
6. oportunidades adicionais de desempenho, somente depois de estabilizar qualidade e recursos.

**Esta fase é de correção dirigida por evidência. Não é autorização para reescrever a arquitetura, trocar o backend padrão, substituir modelos em lote ou alterar simultaneamente vários parâmetros.**

A execução deve preservar a arquitetura e os contratos existentes sempre que possível. Mudanças em contratos de tradução ou no vínculo entre texto e timestamps precisam ser justificadas com testes de regressão e uma explicação explícita da rastreabilidade temporal.

### 1.1. Princípios inegociáveis

- Nenhuma palavra reconhecida pode desaparecer silenciosamente.
- Nenhum timestamp pode ser inventado, interpolado sem evidência ou deslocado para acomodar o texto traduzido.
- Nenhum lote parcial pode ser tratado como tradução concluída.
- Nenhum backend deve substituir outro automaticamente ou misturar traduções de motores diferentes sem decisão explícita.
- Nenhuma redução de beam, mudança de modelo, quantização ou alteração de threads entra no padrão sem medição pareada e verificação de qualidade.
- PT-BR deve ser avaliado por naturalidade e significado, não por substituição mecânica de pronomes ou palavras isoladas.
- Uma legenda curta pode ser legítima. O objetivo não é impor número mínimo de palavras, mas evitar fragmentação artificial sem apagar interjeições, pausas ou fronteiras de frase válidas.
- Limites de exibição não podem ser resolvidos simplesmente cortando texto.
- Relatórios continuam sanitizados: nunca registrar áudio, transcrição, texto traduzido, chave de API, URL privada ou caminho pessoal.

---

## 2. Resultado executivo da auditoria

### 2.1. Achados prioritários

| ID | Prioridade | Achado | Evidência | Direção da correção |
|---|---|---|---|---|
| A-01 | P1 — alta | Gemini interrompeu a tradução no terceiro lote, após 64 unidades aceitas de 927 | 3 requisições, 2 lotes concluídos, 64 unidades, 0 retries; erro reportado pelo usuário na região da cue 71 | classificar respostas inválidas, recuperar somente itens/lotes afetados com limite de tentativas e manter resultados em staging até completar 100% |
| A-02 | P1 — alta | A tradução NLLB apresenta PT-PT e erros semânticos/lexicais incompatíveis com o alvo PT-BR | formas como “teu”, “tu”, “protecção”; 15 ocorrências de “Não, obrigado”; a comparação temporal confirma correspondência com “Thank you” em várias cues PT (por exemplo, 99–104), mas a segmentação diferente exige revisão individual das demais | avaliação com corpus-ouro PT-BR, unidades com contexto frasal, glossário controlado e política explícita de revisão |
| A-03 | P1 — alta | A segmentação ainda gera fragmentação excessiva | 657/925 cues (71,0%) têm até 3 palavras; 40 têm uma palavra; proporção praticamente igual ao SRT PT anterior (71,4%) | acrescentar composição/agrupamento de cues curtas por frase/oração, sem remover fronteiras temporais ou sintáticas legítimas |
| A-04 | P1 — alta | O SRT final excede a largura editorial em algumas linhas, e a validação de produção não detecta todos esses casos | 3 linhas acima de 42 caracteres no SRT novo; maior linha com 59 caracteres | alinhar layout, validador de produção e script de qualidade; subdividir em novas cues usando âncoras reais |
| A-05 | P1 — alta | A execução NLLB regrediu para 45min49s, quase o dobro da mediana quente anterior | 2 threads intra-op/1 inter-op no teste novo; baseline quente 4/4 | corrigir detecção de CPU e medir matriz de threads de forma controlada |
| A-06 | P1 — alta | O perfil declara não reter modelos, mas os adaptadores permanecem carregados ao fim do job | `retain_models=false`, mas Whisper, WhisperX e NLLB registram `loaded_after_job=true`; o helper de liberação não é chamado | aplicar o ciclo de vida em pontos seguros, inclusive falha/cancelamento, e cobrir concorrência |
| A-07 | P2 — média | WhisperX executa uma chamada de alinhamento por segmento do ASR | 487 chamadas para 487 segmentos na execução NLLB | avaliar agrupamento de chamadas em janelas limitadas, isoladamente e com validação temporal |
| A-08 | P2 — média | Os gates não representam a qualidade tradutória semântica nem são equivalentes entre script e pipeline | status `REVIEW_REQUIRED` pode ser publicado; script da Fase 8 encontra largura que o validador de produção pode não sinalizar | separar aprovação estrutural, revisão editorial e revisão semântica da tradução |

**Conclusão executiva:** a regressão de tempo é real e mensurável; a fragmentação não foi resolvida pelo incremento testado; a tradução PT-BR precisa de uma frente própria; e a rota Gemini precisa de resiliência de lote. Os dados apontam uma hipótese forte para a lentidão — redução indevida de threads — mas a validação causal pertence ao protocolo experimental desta fase.

### 2.2. O que não foi comprovado

- O log Gemini não contém o texto da resposta nem a mensagem específica da exceção, por decisão de sanitização. Portanto, não é possível afirmar apenas pelo JSON se a resposta inteira veio vazia ou se a resposta estruturada trouxe uma cue específica sem texto.
- O usuário identificou a falha por volta da cue 71. Como 64 unidades foram aceitas e o terceiro lote foi solicitado, a explicação mais provável é que a terceira resposta foi rejeitada por conteúdo inválido em um dos itens, possivelmente a cue 71. Os 2.203 tokens de saída registrados reforçam que houve conteúdo na resposta HTTP; não provam que todos os itens estavam corretos.
- A queda de threads é a hipótese principal para a regressão de tempo, mas os logs não isolam temperatura da CPU, carga externa do sistema, variação de clock ou todos os efeitos de cache. Não se deve declarar causalidade antes do teste pareado.
- A tradução NLLB não tem parâmetro explícito de variante regional PT-BR no adaptador atual. Isso é evidência de uma limitação de controle de idioma, não prova de que cada erro observado decorra somente do idioma do checkpoint.
- Os arquivos de inglês são saídas automáticas do reconhecimento/alinhamento, não uma transcrição humana de referência. Erros de ASR podem ter contaminado as traduções e precisam ser separados dos erros do tradutor.

---

## 3. Inventário dos artefatos e leitura dos resultados

### 3.1. Arquivos auditados

SRTs:

- [`temporario/EN-baseline.srt`](../temporario/EN-baseline.srt) — saída em inglês usada como referência de comparação; não é transcrição humana.
- [`temporario/baseline.srt`](../temporario/baseline.srt) — saída PT anterior.
- [`temporario/teste-2026.11.12.srt`](../temporario/teste-2026.11.12.srt) — saída PT da execução nova.

Relatórios:

- [`job-2e5e93e3369c.json`](../temporario/logs/job-2e5e93e3369c.json) — NLLB, execução concluída.
- [`job-b845be3d8e7f.json`](../temporario/logs/job-b845be3d8e7f.json) — Gemini, execução interrompida por falha de tradução.
- [`job-2f6d8c3e5dad.json`](../temporario/logs/job-2f6d8c3e5dad.json), [`job-501f9e6ce91c.json`](../temporario/logs/job-501f9e6ce91c.json) e [`job-d796d6a8218f.json`](../temporario/logs/job-d796d6a8218f.json) — três execuções quentes completas anteriores, usadas para a mediana.
- [`job-c8e8b3d46d76.json`](../temporario/logs/job-c8e8b3d46d76.json) — execução completa com carregamento inicial de modelos.
- [`job-2b922358055c.json`](../temporario/logs/job-2b922358055c.json) — execução de referência sem tradução; não deve ser comparada como job completo.

Todos os sete JSON disponíveis foram considerados na auditoria. A comparação principal de desempenho usa as três execuções anteriores marcadas como modelos já carregados antes do job, não mistura a execução fria na mediana quente.

### 3.2. Métricas de fragmentação e layout

| Métrica | Inglês automático | PT anterior | PT novo |
|---|---:|---:|---:|
| Quantidade de cues | 967 | 944 | 925 |
| Média de palavras por cue | 2,94 | 3,38 | 3,33 |
| Cues com até 3 palavras | 816 (84,4%) | 674 (71,4%) | 657 (71,0%) |
| Cues de uma palavra | 61 | 51 | 40 |
| Cues com menos de 1 segundo | 477 | 715 | 437 |
| Cues acima de 17 CPS | 352 | 677 | 444 |
| Mediana da duração | aproximadamente 1,0 s | aproximadamente 0,58 s | aproximadamente 1,0 s |
| Percentual de cues terminadas em pontuação final | 46,6% | 67,5% | 66,1% |
| Linhas com mais de 42 caracteres | 2 | 5 | 3 |

Leitura correta desses números:

1. O SRT PT novo melhorou em relação ao SRT inglês automático e reduziu bastante a quantidade de cues abaixo de um segundo em relação ao PT anterior.
2. Porém, comparando o PT novo com o PT anterior, o percentual de cues com até três palavras praticamente não mudou: 71,0% contra 71,4%. Portanto, a sensação de melhor agrupamento não representa ainda uma correção robusta da fragmentação.
3. O aumento da mediana de duração é positivo, mas 444 cues continuam acima de 17 CPS. A legibilidade não pode ser julgada só pela média de palavras.
4. O SRT novo contém três linhas acima de 42 caracteres; uma chega a 59 caracteres. A maior cue tem 96 caracteres no total. Há, portanto, violações físicas do layout declarado.

Exemplos do SRT novo que devem virar casos de teste, preservando os timestamps originais:

- Cue 347: “Três à esquerda, dois à direita, nove / degraus, dois à esquerda e a terceira prateleira à direita.” — 17 palavras e linha de 59 caracteres.
- Cue 172: “Bem, nas palavras de Chomple para o medo, / um final tão agradável para um tão desagradável” — linha de 47 caracteres.
- Cue 783: “Quando cheguei às cavernas há muitos anos, / naveguei para o rasteiro de água como Braskily como” — linha de 51 caracteres.

Esses exemplos não autorizam cortar ou remover palavras. Eles demonstram que o algoritmo precisa produzir uma quantidade maior de cues quando o conteúdo não couber de forma legível.

### 3.3. Evidências de idioma e semântica

O SRT PT novo contém formas associadas ao português europeu, entre elas:

- “tu”, “teu” e “tua” em contextos nos quais o alvo solicitado é PT-BR;
- “protecção” e “até ao”, que reforçam a deriva de variante;
- somente três ocorrências de “você” no conjunto analisado.

O indício mais objetivo de erro semântico são 15 ocorrências de “Não, obrigado” no PT. A comparação temporal confirma correspondência com “Thank you” em várias cues (PT 99–104, por exemplo), embora as segmentações diferentes impeçam atribuir automaticamente todas as 15 ao mesmo original. Nos casos confirmados, não é preferência estilística: é mudança de sentido/polaridade.

Outros exemplos de frases que precisam de revisão contextual:

| Original em inglês (automático) | Resultado PT observado | Risco |
|---|---|---|
| “Do you really / have a / first book?” | “Você realmente / ter um / Primeiro livro?” | construção não natural e divisão por fragmentos |
| “safe haven is / yours for as / long as you / require it” | “O refúgio seguro é / o seu para como / Enquanto você / exigir isso.” | sintaxe e sentido pouco naturais |
| “Float trick?” | “Trilho de flutuar?” | escolha lexical provavelmente incorreta |
| “We keep us safe.” | “Mantemos-nos a salvo.” | construção inadequada em PT-BR |
| “Any protection / or privilege / bestowed upon” | “Qualquer protecção / ou privilégio / Desviados” | vocabulário e contexto possivelmente corrompidos |

Há também problemas presentes no inglês automático, como nomes e expressões reconhecidos incorretamente. Por exemplo, “Wing for” pode ser uma falha de reconhecimento de “Wingfeather”. Nesses casos, a auditoria humana deve comparar com o áudio, para não atribuir automaticamente ao tradutor um erro que já existia na origem.

**Regra:** a correção de idioma deve ser feita por bloco de sentido e contexto, com conjunto de referência revisado por humano fluente em PT-BR. Não implementar um substituidor global de “tu” por “você”, “teu” por “seu” ou equivalentes: isso pode quebrar falas, relações, citações, personagens e concordância.

### 3.4. Desempenho: comparação entre as execuções

A mídia tem aproximadamente 37min10s.

| Execução | Resultado | Tempo total | Transcrição | Alinhamento | Tradução |
|---|---|---:|---:|---:|---:|
| Três execuções quentes anteriores — mediana | concluída | **23min21s** | — | — | — |
| NLLB novo (`2e5e93e3369c`) | concluída | **45min49s** | 19min15s | 5min43s | 20min44s |
| Gemini novo (`b845be3d8e7f`) | falhou no terceiro lote | **32min29s até a falha** | 24min30s | 6min02s | 1min48s antes da falha |

O NLLB novo praticamente dobrou o tempo total em relação à mediana quente anterior (aproximadamente +96,3%). A execução Gemini não completou e, portanto, seus 32min29s não são uma medição comparável de job concluído.

Decomposição das causas prováveis:

- **Whisper:** 19min15s no NLLB novo, contra mediana anterior de aproximadamente 5min49s nas três execuções quentes. O tempo de inferência representa praticamente toda a etapa; carregar o modelo levou cerca de 1,2s.
- **WhisperX:** 5min43s, com 487 chamadas de alinhamento, uma por segmento do ASR. A carga do modelo foi de aproximadamente 5,5s; o custo dominante foi a inferência repetida por segmento.
- **NLLB:** 20min44s, dos quais aproximadamente 20min32s foram geração. A execução gerou 15.025 tokens, praticamente o mesmo volume das execuções quentes anteriores. A geração anterior teve mediana de aproximadamente 13min57s. Logo, o custo por volume de geração piorou de forma material.
- **Carregamento de modelos:** soma pequena diante dos estágios de inferência. A auditoria não recomenda otimizar primeiro o download/cache dos modelos.

### 3.5. Política de CPU: hipótese prioritária

No teste novo, o relatório registra:

- CPU: AMD Ryzen 3 2200G;
- 4 núcleos físicos e 4 CPUs lógicas no inventário;
- perfil `low-memory`;
- PyTorch intra-op: 2 threads;
- PyTorch inter-op: 1 thread.

As três execuções quentes anteriores registram 4 threads intra-op e 4 inter-op.

O código de [`profile.py`](../src/legendar/infrastructure/resources/profile.py) estima núcleos físicos como metade de `os.cpu_count()`. Isso assume dois processadores lógicos por núcleo físico. No equipamento observado, a proporção é 4/4, portanto a estimativa cai incorretamente de quatro para dois. Como o perfil de baixa memória limita threads com base nessa estimativa, o modo automático seleciona duas threads.

A coincidência é forte: a geração NLLB atual levou aproximadamente 47% mais que a mediana das três execuções quentes anteriores, com volume de tokens semelhante e metade das threads intra-op. Whisper e WhisperX também ficaram significativamente mais lentos.

**Não concluir causalidade ainda.** A implementação deverá medir 2, 3 e 4 threads intra-op, com inter-op controlado, mesmo hardware, mesmos arquivos, mesma configuração, sistema sem carga externa e três execuções quentes por configuração. O número de threads deve refletir topologia física e afinidade disponível, não uma divisão fixa por dois.

### 3.6. Ciclo de vida dos modelos: defeito confirmado, causa de tempo não comprovada

A política atual grava `retain_models=false`, mas os snapshots terminam com Whisper, WhisperX e NLLB ainda carregados. Em [`serial_pipeline.py`](../src/legendar/application/pipeline/serial_pipeline.py), o helper `_release_resources()` está definido, mas não possui chamadas no fluxo do pipeline.

Isso significa que a promessa da Fase 7 de liberar modelos em `low-memory` não está efetivamente cumprida nesse caminho. Os relatórios mostram RSS máximo de aproximadamente 5,33 GB e memória disponível do sistema em torno de 8,63 GB ao final da tradução; não há evidência nesses arquivos de que swapping ou esgotamento de RAM tenha causado a lentidão. Portanto:

- corrigir o ciclo de vida porque o contrato de recursos não está sendo cumprido;
- não afirmar que essa falha causou os 45min49s;
- validar se a liberação entre etapas é segura com jobs simultâneos e cancelamento;
- liberar objetos/cache residentes sem apagar checkpoints do cache em disco.

---

## 4. Investigação cirúrgica do código

A implementação deve seguir estes caminhos, e não se limitar à primeira função que parece relacionada.

### 4.1. Gemini — resposta vazia e recuperação

Arquivos principais:

- [`gemini.py`](../src/legendar/infrastructure/translation/gemini.py)
- [`translation.py`](../src/legendar/application/pipeline/translation.py)
- [`serial_pipeline.py`](../src/legendar/application/pipeline/serial_pipeline.py)
- [`test_gemini_translator.py`](../tests/unit/infrastructure/test_gemini_translator.py)

Comportamento atual relevante:

1. Gemini processa lotes de 32 cues.
2. A resposta HTTP é recebida em `_request_with_retry()`.
3. A validação de candidato, JSON, IDs, quantidade, ordem e texto vazio ocorre depois, em `_parse_response()`.
4. O retry existente cobre erros HTTP 429 e 5xx, mas não erros de conteúdo estruturado detectados pelo parser.
5. Se uma cue vier vazia, o lote inteiro é rejeitado. A métrica de unidades traduzidas só é incrementada após o lote passar integralmente.

A sequência 3 requests / 2 batches / 64 unidades aceitas / 0 retries é compatível com falha de validação na terceira resposta. O plano deve preservar os critérios rígidos de integridade e adicionar recuperação limitada, em vez de aceitar texto vazio.

**Intervenção requerida:**

- criar uma taxonomia de falhas: sem candidato, bloqueio de segurança, JSON inválido, lote truncado, quantidade errada, IDs duplicados/fora de ordem, item vazio, falha de rede, rate limit e erro do servidor;
- validar e registrar quais IDs falharam sem gravar o conteúdo das cues;
- manter traduções válidas em staging por `cue_id`, sem publicá-las enquanto houver IDs ausentes;
- tentar novamente somente os itens vazios/inválidos quando a resposta e os IDs permitirem isolamento seguro;
- para resposta inteira malformada ou sem candidato, repetir o lote dentro de limite configurado;
- para `MAX_TOKENS`, dividir o lote em sublotes menores, sem alterar a ordem nem omitir IDs;
- respeitar cancelamento durante backoff e novas tentativas;
- não repetir indefinidamente falhas de autenticação, configuração ou bloqueio de segurança;
- produzir um erro final seguro e acionável quando o orçamento de recuperação acabar;
- somente devolver `TranslationResult` após todas as unidades estarem presentes, únicas, não vazias e na ordem esperada.

**Observabilidade obrigatória:** requests, tentativas, lotes originais/subdivididos, IDs afetados, categoria da falha, finish reason, contagens de candidato/parte e total de unidades concluídas. Nenhum texto, prompt, credencial ou resposta integral deve aparecer no JSON de performance.

### 4.2. Segmentação — corrigir composição, não duplicar a regra de pontuação

Arquivo principal: [`segmentation.py`](../src/legendar/application/pipeline/segmentation.py).

A implementação já tem regras de pontuação final. `_prefers_break_after()` reconhece ponto final, exclamação, interrogação e reticências; `_CLAUSE_ENDINGS` considera vírgula, ponto e vírgula, dois-pontos e travessões para preferir um limite de subdivisão. Portanto, **não basta adicionar novamente “quebrar no ponto final”**: essa regra já existe.

A lacuna encontrada é outra:

- o fluxo atual constrói grupos contíguos de palavras;
- ele separa por pausa, excesso de caracteres, duração e velocidade de leitura;
- ele não executa uma etapa posterior de recomposição de microcues consecutivas;
- `min_words_per_split_part` restringe subdivisões, mas não é um tamanho mínimo para a cue final;
- fronteiras de sentença significativas já são preservadas em testes, então uma fusão irrestrita também seria regressão.

**Intervenção requerida:**

1. separar claramente a formação de unidades de frase/oração da etapa de subdivisão visual;
2. primeiro reconhecer limites preferenciais de sentença e oração;
3. agrupar palavras/cues consecutivas quando a fala for contínua, respeitando pausa máxima, pontuação, travessão e barreiras de fallback;
4. somente então subdividir blocos que excedam o limite de exibição, priorizando pontuação e limites sintáticos;
5. usar quantidade máxima de palavras como limite complementar, nunca como regra isolada;
6. manter os limites de referência de até duas linhas, 42 caracteres por linha, 84 por cue, duração máxima de 7s e alvo de cerca de 17 CPS;
7. preservar início/fim obtidos de palavras alinhadas e só estender em silêncio seguro documentado;
8. classificar interjeições, vocativos e respostas curtas legítimas como exceções aceitáveis, sem forçar fusão;
9. manter o texto total recuperável exatamente, inclusive pontuação e palavras repetidas;
10. emitir métricas que mostrem quantas cues foram agrupadas, subdivididas e mantidas como exceção.

Não fixar um mínimo rígido de duas, três ou quatro palavras: isso penalizaria respostas curtas legítimas. A função de uma regra de palavras máximas é impedir blocos enormes, não obrigar todas as legendas a terem o mesmo tamanho.

### 4.3. Tradução — contexto e variante PT-BR

Arquivos principais:

- [`translation.py`](../src/legendar/application/pipeline/translation.py)
- [`nllb.py`](../src/legendar/infrastructure/translation/nllb.py)
- [`gemini.py`](../src/legendar/infrastructure/translation/gemini.py)
- [`test_translation.py`](../tests/unit/application/test_translation.py)
- [`test_nllb_translator.py`](../tests/unit/infrastructure/test_nllb_translator.py)

Hoje a aplicação cria uma unidade para cada cue e exige uma saída 1:1. A tradução ocorre por cue, mesmo quando a cue contém apenas um fragmento sintático. O batching do NLLB agrupa requisições para inferência, mas não transforma automaticamente os textos em frases completas. O código NLLB usa `por_Latn`, sem parâmetro regional PT-BR explícito; ao contrário do Gemini, não existe prompt com instruções editoriais.

**Direção de projeto:**

- traduzir blocos de frase/oração com contexto anterior e posterior, em vez de enviar fragmentos de duas ou três palavras isolados;
- cada bloco deverá carregar uma lista explícita dos IDs/cues/palavras de origem e seus limites temporais;
- preservar rastreabilidade de todos os blocos até o texto reconhecido;
- estabelecer instruções PT-BR para o Gemini, reforçando português brasileiro contemporâneo, naturalidade oral, concordância, vocabulário, pronomes, tratamento e preservação de nomes próprios;
- para NLLB, testar a qualidade do idioma com corpus revisado e investigar alternativas compatíveis, sem presumir que `por_Latn` garanta PT-BR;
- manter glossário de nomes próprios e termos do universo da obra, mas só corrigir nomes com evidência no áudio/referência confiável;
- avaliar negação, sujeito, tempo verbal, relação entre falantes, nomes, números e coerência entre cues vizinhas;
- evitar tradução palavra por palavra quando a frase completa exige reordenação natural em PT-BR.

**Restrição temporal essencial:** uma tradução de frase inteira pode ficar mais longa que o texto original. Não repartir a tradução em timestamps por proporção de palavras. Primeiro formar blocos de origem já temporizados; cada saída traduzida deve manter um vínculo claro com o bloco de origem. Quando o texto final não couber no limite visual, solicitar uma versão concisa e fiel dentro do mesmo bloco ou marcar revisão/bloqueio. Só subdividir a saída em duas cues quando existirem pontos de corte derivados de âncoras reais de origem e o mapeamento tiver sido validado. Na ausência dessa evidência, não inventar tempos.

**Decisão de escopo:** esta fase não autoriza benchmark comparativo amplo Gemini × NLLB nem mudança automática do backend padrão. Cada caminho deve passar pelos critérios de confiabilidade e qualidade aplicáveis; qualquer troca de padrão ou comparação formal entre motores exige decisão explícita do responsável pelo produto, conforme a decisão vigente da Fase 6.

### 4.4. Formatação física e gate de publicação

Arquivos principais:

- [`text_layout.py`](../src/legendar/domain/value_objects/text_layout.py)
- [`subtitle.py`](../src/legendar/domain/entities/subtitle.py)
- [`srt.py`](../src/legendar/infrastructure/filesystem/srt.py)
- [`validation.py`](../src/legendar/application/pipeline/validation.py)
- [`phase8_srt_quality.py`](../scripts/phase8_srt_quality.py)

O layout atual tenta manter até duas linhas, mas, quando o texto não cabe, `_merge_overflow()` mantém todas as palavras na última linha disponível. Essa escolha evita perda silenciosa, mas pode produzir linha fisicamente muito maior que 42 caracteres. É comportamento intencional do formatador, não defeito isolado de serialização.

O validador de produção verifica `len(text) > max_chars_per_cue`, mas não mede necessariamente cada linha efetivamente retornada por `cue.lines()`. Já o script da Fase 8 verifica a largura física das linhas. Os dois gates podem discordar. Além disso, o pipeline publica `REVIEW_REQUIRED`; apenas `BLOCKED` interrompe a publicação.

**Intervenção requerida:**

- tornar a largura física de cada linha e a quantidade de linhas critérios explícitos do validador de produção;
- reutilizar a mesma regra de layout no pipeline e no avaliador, evitando implementações paralelas;
- o formato final não pode exceder duas linhas de 42 caracteres;
- quando o texto não couber, subdividir em novas cues antes da serialização, usando os limites temporais reais;
- nenhum texto pode ser descartado para satisfazer o limite;
- manter separados os alertas editoriais brandos e as violações estruturais;
- definir quais violações bloqueiam publicação automática e quais permitem publicação com revisão explícita;
- o status de conclusão da UI não deve sugerir que uma saída `REVIEW_REQUIRED` foi editorialmente aprovada;
- preservar round-trip, publicação atômica e arquivo anterior em caso de falha.

**Proposta de gate:**

- `BLOCKED`: perda de conteúdo, timestamp inválido/fabricado, sobreposição proibida, cue fora da mídia, linha acima do limite, mais de duas linhas, texto vazio, unidade de tradução ausente/duplicada ou mapeamento temporal inconsistente.
- `REVIEW_REQUIRED`: fragmento sintático suspeito, cue curta ambígua, possível repetição, naturalidade duvidosa, entidade incerta ou questão tradutória que não possa ser resolvida deterministicamente.
- `APPROVED`: todos os invariantes estruturais passaram. Isso **não** equivale a certificação semântica da tradução sem revisão humana.

A implementação final deve explicitar os limites e exceções no documento de decisões e cobrir testes positivos e negativos.

---

## 5. Plano de execução ordenado

A sequência abaixo é deliberada. Não avançar para otimização de modelo antes de corrigir a política de threads, e não congelar qualidade antes de estabelecer os novos contratos de composição e tradução.

### Etapa 8.1.0 — Congelar evidências e corpus de referência

**Objetivo:** impedir que mudanças posteriores apaguem a causa original ou tornem comparações inválidas.

Tarefas:

1. preservar os três SRTs e os sete JSON atuais em `temporario/` como evidência histórica;
2. registrar checksum SHA-256 de cada fixture no relatório de experimento;
3. criar trechos de teste pequenos e sanitizados que reproduzam:
   - resposta Gemini com uma cue vazia;
   - resposta Gemini sem candidato;
   - resposta truncada;
   - sequência de fragmentos de legenda;
   - sentença curta seguida de outra sentença;
   - interjeição isolada legítima;
   - frase longa que ultrapassa duas linhas;
   - nome próprio/termo recorrente;
   - mudança de sentido em negação/agradecimento;
4. criar referência PT-BR revisada por humano para uma amostra do áudio, armazenada localmente fora do Git quando houver mídia/texto protegido;
5. separar explicitamente erros de ASR da origem e erros introduzidos pela tradução;
6. usar a mesma transcrição/alinhamento congelados para testar isoladamente segmentação e tradução, evitando comparar duas execuções completas que produziram quantidades e limites de cues diferentes.

**Saída obrigatória:** manifesto de corpus, hashes, amostras sintéticas versionáveis, referência humana local e relatório com a separação entre evidências e hipóteses.

**Gate:** nenhum experimento comparativo começa sem arquivo, modelo, parâmetros, hardware e referência identificados.

### Etapa 8.1.1 — Corrigir confiabilidade do Gemini

**Objetivo:** um item vazio ou uma resposta imperfeita não deve invalidar trabalho já concluído sem tentativa de recuperação, nem permitir publicação incompleta.

Tarefas:

1. implementar a taxonomia de falhas da seção 4.1;
2. instrumentar o lote com IDs esperados e IDs efetivamente recebidos;
3. distinguir resposta inteira vazia, candidato ausente, bloqueio, JSON inválido, lote truncado e campo `text` vazio;
4. preservar em memória os itens que já passaram na validação, indexados por ID;
5. reprocessar somente itens vazios quando a resposta estiver estruturalmente íntegra e os IDs permitirem isolamento;
6. dividir lote em sublotes menores após truncamento por limite de saída;
7. revalidar o conjunto integral por ID, cardinalidade, ordem, duplicidade e texto não vazio;
8. limitar tentativas e backoff; respeitar cancelamento;
9. se qualquer unidade continuar inválida, encerrar como falha clara, sem publicar SRT parcial;
10. melhorar a mensagem na interface e os registros sanitizados.

**Testes obrigatórios:**

- item específico vazio dentro de resposta com outros itens corretos;
- repetição do item vazio com sucesso;
- item vazio persistente após o limite de tentativas;
- candidato ausente;
- resposta sem partes;
- JSON inválido;
- JSON com quantidade errada;
- IDs ausentes, duplicados ou reordenados;
- `finishReason=MAX_TOKENS` e subdivisão;
- erro HTTP 429/5xx com retry;
- erro 4xx não recuperável sem retry infinito;
- bloqueio de segurança sem exposição do prompt/conteúdo;
- cancelamento durante backoff e entre sublotes;
- garantia de que nenhuma unidade parcial chega ao publisher.

**Gate:** tradução somente será considerada completa com todos os IDs esperados exatamente uma vez e nenhum texto vazio. O teste sintético equivalente ao problema da cue 71 deve passar.

### Etapa 8.1.2 — Corrigir topologia de CPU e ciclo de vida de modelos

**Objetivo:** recuperar alocação adequada de CPU e cumprir a política `low-memory` sem causar regressões de memória ou concorrência.

Tarefas:

1. corrigir `_physical_cpu_count()` para detectar a topologia real do sistema;
2. no Linux, preferir informações de `physical id`/`core id` ou sysfs já disponíveis; tratar afinidade/cgroups quando aplicável;
3. quando a topologia não puder ser determinada, registrar a incerteza e usar fallback conservador explícito, sem presumir sempre SMT 2:1;
4. separar a decisão de threads da decisão de reter modelos: pouca RAM não significa necessariamente metade dos núcleos disponíveis;
5. testar 2/1, 3/1, 4/1, 4/2 e 4/4 (intra-op/inter-op) no hardware de referência, incluindo 4/4 como referência histórica;
6. verificar a ordem de configuração do PyTorch antes da primeira inferência e registrar threads efetivas;
7. localizar todos os adaptadores com `release_resources()`;
8. conectar `_release_resources()` ao pipeline em `finally` seguro, de acordo com a política de retenção;
9. liberar o modelo Whisper depois da transcrição, WhisperX depois do alinhamento e NLLB depois da tradução quando `retain_models=false`;
10. garantir limpeza também em falha e cancelamento;
11. impedir descarte durante inferência concorrente: usar exclusão, lease/refcount ou a política explícita de serialização de jobs que o sistema realmente oferecer;
12. preservar pesos e checkpoints no cache em disco;
13. registrar `loaded_before_job`, `loaded_after_stage`, `loaded_after_job`, tempo de liberação e falhas de liberação.

**Testes obrigatórios:**

- 4 CPUs físicas / 4 lógicas devem ser detectadas como 4 núcleos;
- 4 físicas / 8 lógicas devem ser detectadas como 4 núcleos;
- topologia ausente deve seguir fallback documentado;
- afinidade limitada deve ser respeitada;
- `low-memory` libera os três adaptadores nos pontos previstos;
- `balanced`/ `performance` preservam modelos conforme o contrato;
- liberação após falha e cancelamento;
- dois jobs ou duas chamadas concorrentes não podem liberar modelo em uso;
- cache em disco permanece íntegro;
- falha de liberação não mascara falha original nem derruba job concluído.

**Protocolo de desempenho:** com o mesmo áudio, comparar pelo menos três execuções quentes por configuração; alternar configurações em condições térmicas similares; não rodar outras tarefas pesadas; guardar cold start separado. Registrar relógio de CPU, uso por núcleo, threads efetivas, RSS, memória disponível e tempo por estágio.

**Gate:** o perfil automático não pode reduzir indevidamente 4 núcleos físicos a 2. A política de retenção precisa ser demonstravelmente aplicada. Nenhuma configuração de threads será promovida sem mediana e dispersão medidas.

### Etapa 8.1.3 — Reestruturar composição das cues e limites de exibição

**Objetivo:** produzir legendas que acompanhem frases/orações com boa continuidade visual, sem excesso de microcues e sem ultrapassar o espaço de tela.

Tarefas:

1. mapear precisamente como os grupos atuais são formados e em que condições cada fronteira é criada;
2. preservar a lógica existente de pontuação final, pausas e continuidade;
3. criar uma etapa explícita para recompor microcues contíguas quando elas formarem uma mesma unidade sintática/semântica;
4. preferir fronteiras em ponto final, interrogação, exclamação e reticências; em seguida, vírgula, dois-pontos, ponto e vírgula ou travessão quando apropriado;
5. usar pausa real como fronteira preferencial, sem atravessar pausas significativas;
6. usar máximo de palavras como limite complementar e configurável; calibrar por exemplos e revisão, não impor uma constante sem teste;
7. respeitar até 2 linhas × 42 caracteres, máximo 84 caracteres, duração máxima de 7 segundos e alvo aproximado de 17 CPS;
8. manter subdivisão somente em limites entre palavras alinhadas;
9. tratar cue curta legítima como exceção, não erro a ser automaticamente fundido;
10. evitar agrupar falas que pertencem a turnos ou sentenças distintos;
11. quando não houver diarização, não inventar identificação de falante; usar apenas pistas existentes, como travessão e pausa;
12. gerar métricas pré/pós: número de cues, distribuição de palavras, duração, CPS, mudanças por minuto, cues de 1/2/3 palavras, fragmentos sintáticos, linhas largas e exceções;
13. verificar que a concatenação das cues mantém exatamente o conteúdo de origem, descontadas apenas normalizações de espaço formalmente permitidas.

**Testes obrigatórios:**

- fala contínua entre segmentos Whisper;
- ponto final/interrogação/exclamação;
- frase curta terminada em pontuação não fundida à próxima;
- oração longa subdividida em duas ou mais cues legíveis;
- vírgula e conectivos não deixados artificialmente isolados;
- pausa curta não fragmenta uma frase sem necessidade;
- pausa significativa separa unidades;
- interjeição de uma palavra permanece quando legítima;
- travessão/diálogo preservado;
- fala rápida sem perda ou timestamps inventados;
- texto que ultrapassa 84 caracteres é dividido em cues com âncoras reais;
- palavras longas, números e nomes próprios não são cortados.

**Gate:** reduzir a fragmentação no corpus congelado sem elevar CPS, largura, perda textual ou erro temporal. A meta quantitativa deve ser calibrada contra a referência humana; não aprovar simplesmente por cair a quantidade de cues.

### Etapa 8.1.4 — Adequar o contrato de tradução a blocos contextualizados

**Objetivo:** deixar de traduzir fragmentos isolados sem perder o vínculo temporal.

Tarefas:

1. avaliar o contrato atual de `TranslationUnit`, que hoje representa uma cue individual;
2. especificar unidade contextual com ID próprio e lista dos IDs/cues/palavras-fonte que a compõem;
3. transportar texto, idioma, contexto adjacente e referências de entidades sem depender da memória informal do modelo;
4. definir mapeamento explícito entre unidade de tradução e intervalo temporal original;
5. preservar reordenação linguística natural dentro da mesma unidade;
6. limitar a unidade de origem para evitar truncamento de tokenizador/modelo;
7. detectar limites de entrada: NLLB usa truncamento de entrada em 256 tokens; jamais aceitar truncamento silencioso;
8. validar cardinalidade e integridade do resultado por ID de unidade, não por posição implícita;
9. converter cada resultado em cue com a janela temporal da unidade de origem ou em subdivisões cuja origem temporal esteja comprovada;
10. se a tradução final não couber, solicitar concisão fiel ou exigir revisão; não dividir proporcionalmente por palavras traduzidas.

**Gate:** cada palavra de origem deve ser rastreável a uma ou mais unidades; cada unidade de destino deve apontar para sua origem e janela real; nenhuma cue final pode depender de timestamps artificiais.

### Etapa 8.1.5 — Corrigir qualidade editorial PT-BR

**Objetivo:** tornar a saída brasileira natural e semanticamente fiel.

Tarefas:

1. preparar um pequeno corpus-ouro com frases completas, contexto anterior/posterior e revisão humana PT-BR;
2. incluir diálogos, perguntas, respostas curtas, agradecimentos, negações, pronomes, tempos verbais, nomes próprios, topônimos, títulos, clãs/raças e termos específicos da obra;
3. incluir explicitamente exemplos equivalentes aos erros observados em 12/11, incluindo “Thank you”;
4. estabelecer glossário aprovado para nomes e entidades, sem corrigir transcrição quando o áudio não sustentar a correção;
5. escrever/revisar instruções Gemini para português brasileiro natural, oral e idiomático;
6. investigar opções técnicas para NLLB compatíveis com o escopo, mas não presumir que uma configuração genérica de português produza PT-BR;
7. pontuar preservação de sentido, negação, sujeito, tempo verbal, registro, concordância, nomes/números e naturalidade;
8. exigir revisão humana cega de exemplos representativos antes de declarar aprovação;
9. registrar separadamente erros provenientes da transcrição original e erros introduzidos pela tradução.

**Não fazer:** pós-processamento de pronomes por substituição global; tradução por cue isolada sem contexto; “correção” automática de nome sem áudio/glossário confiável; aprovação semântica baseada apenas em retorno não vazio.

**Gate:** nenhum erro crítico de sentido, negação, nome ou número na amostra de aceite; PT-BR aprovado por revisor humano; casos não resolvidos são marcados para revisão, não escondidos por heurística.

### Etapa 8.1.6 — Unificar o gate de qualidade e a publicação

**Objetivo:** fazer o runtime e a ferramenta da Fase 8 aplicarem os mesmos critérios estruturais.

Tarefas:

1. reutilizar a mesma função de cálculo de linhas físicas no runtime e em `phase8_srt_quality.py`;
2. verificar quantidade real de linhas e caracteres em cada linha depois do wrap;
3. transformar overflow em subdivisão temporal válida antes da publicação;
4. distinguir violação estrutural de risco editorial;
5. alinhar os códigos de issue, severidades, mensagens e thresholds do script e de `validate_track()`;
6. decidir com clareza quando `REVIEW_REQUIRED` é publicável e qual confirmação explícita a UI deve exigir;
7. não confundir estado técnico do job concluído com aprovação editorial;
8. manter o bloqueio para perda de conteúdo, timestamps inválidos, IDs de tradução ausentes e sobreposição;
9. gerar relatório estruturado que inclua status e contagens, sem texto privado.

**Testes obrigatórios:**

- 42 caracteres exatos por linha aceitos;
- 43 caracteres rejeitados;
- 2 linhas aceitas;
- 3 linhas rejeitadas ou subdivididas antes do gate;
- overflow de texto sem perda;
- cue com até 84 caracteres que mesmo assim gera linha física acima de 42;
- comportamento idêntico do validador runtime e do script;
- `REVIEW_REQUIRED` não aparece na interface como aprovação final;
- publisher nunca recebe trilho que deveria estar `BLOCKED`.

**Gate:** zero violações estruturais na saída publicada e equivalência entre o gate do aplicativo e o avaliador da Fase 8.

### Etapa 8.1.7 — Otimizar os gargalos remanescentes isoladamente

**Objetivo:** recuperar e, se possível, melhorar o tempo total sem sacrificar qualidade.

Somente começar depois das Etapas 8.1.1–8.1.6 estarem estáveis.

Experimentos separados:

1. **CPU/threads:** comparar 2/1, 3/1, 4/1 e 4/2; controlar afinidade e condição térmica.
2. **NLLB beam:** comparar 4, 2 e 1 sem alterar simultaneamente batch ou modelo.
3. **NLLB batching:** testar tamanhos de lote e limite de tokens isoladamente.
4. **Length bucketing:** agrupar textos de tamanho semelhante para reduzir padding. O job novo teve 6.018 tokens de entrada e 13.527 posições padded, cerca de 2,25 vezes o volume útil; medir se isso reduz tempo real.
5. **Alternativa CTranslate2 para NLLB:** medir tempo, memória, qualidade e compatibilidade de licença/modelo.
6. **Faster-whisper/CTranslate2:** avaliar como candidato de ASR sem promovê-lo automaticamente; medir WER/CER e alinhamento no mesmo corpus.
7. **WhisperX:** experimentar agrupamento de segmentos em janelas limitadas, reduzindo chamadas unitárias, sem perder a associação de cada palavra ao texto e ao tempo.
8. **Outros parâmetros:** testar um por vez, com baseline congelada e reversão simples.

Para cada experimento registrar: hipótese, única variável alterada, comando/configuração, versão, hardware, cold/warm, três execuções quentes quando viável, mediana, dispersão, RSS, CPU por núcleo, tempo por etapa, throughput, métricas de texto e decisão.

**Gate:** um experimento só pode ser promovido se melhora materialmente o estágio-alvo e passa integralmente os gates de qualidade; ganho isolado de tokens/s não é suficiente.

### Etapa 8.1.8 — Regressão final, documentação e encerramento

Entregas:

1. suíte unitária completa;
2. integração de tradutores, segmentador, formatador, validador e publisher;
3. testes de cancelamento e falha sem SRT parcial;
4. E2E real com a mesma mídia de aproximadamente 37min10s;
5. ao menos três execuções quentes para a configuração final, com cold start separado;
6. revisão humana PT-BR e inspeção do SRT em player real;
7. atualização dos relatórios e da baseline de desempenho;
8. CI verde em todas as matrizes aplicáveis;
9. lint, formatação, cobertura e links documentais aprovados;
10. documentação viva, decisões, arquitetura, homologação e matriz de dependências coerentes;
11. nenhum documento encerrado permanece como instrução ativa na raiz de `docs/`;
12. PR revisada e mergeada na `main`, com CI pós-merge aprovada, antes de encerrar a fase.

---

## 6. Critérios objetivos de aceite

Os thresholds abaixo são gates de engenharia propostos para esta execução; devem ser congelados antes dos experimentos e só alterados com justificativa documentada.

### 6.1. Integridade

- 100% das unidades de tradução esperadas mapeadas uma única vez.
- Zero texto vazio aceito.
- Zero palavra reconhecida descartada silenciosamente.
- Zero timestamp fabricado/interpolado sem evidência.
- Zero sobreposição estrutural proibida.
- Zero truncamento de entrada/saída não sinalizado.
- Cancelamento e falha não publicam SRT parcial.

### 6.2. Legibilidade

- máximo de duas linhas por cue;
- máximo de 42 caracteres em cada linha;
- máximo de 84 caracteres totais por cue;
- nenhuma cue acima de 7 segundos sem exceção explícita;
- medir e reportar CPS, duração, cues de 1/2/3 palavras, variação de cues por minuto e fragmentos sintáticos;
- meta de leitura de aproximadamente 17 CPS, com qualquer violação destacada e encaminhada conforme severidade;
- não impor mínimo absoluto de palavras; exceções curtas legítimas devem ser mantidas;
- nenhuma melhora na média pode mascarar uma regressão na cauda (P90/P95), em linhas largas ou na sincronização.

### 6.3. Tradução PT-BR

- revisão humana de amostra representativa de pelo menos 30 blocos completos, cobrindo começo/meio/fim e categorias críticas;
- zero erro crítico de negação, intenção, identidade de personagem, número ou entidade na amostra de aceite;
- nenhuma ocorrência de “Thank you” traduzida com sentido de recusa/negação;
- naturalidade e registro aprovados por revisor fluente em PT-BR;
- erros de ASR e erros de tradução contabilizados separadamente;
- nenhuma aprovação automática apenas por diferença lexical ou idioma detectado.

### 6.4. Gemini

- simulação da falha equivalente à cue 71 recuperada com sucesso ou falha final clara e não ambígua;
- retries limitados, contabilizados e canceláveis;
- todos os IDs recebidos e validados antes de conclusão;
- nenhuma publicação parcial;
- erro final identifica categoria e IDs afetados sem expor texto privado.

### 6.5. Desempenho

Referência histórica: mediana quente de **23min21s** nas três execuções anteriores comparáveis. Execução NLLB atual: **45min49s**.

Meta desta correção: recuperar o patamar histórico, antes de buscar uma nova aceleração. Para a mesma mídia, hardware, cache e configuração final:

- mediana de três execuções quentes **≤ 26min30s**;
- nenhuma execução quente individual acima de 30 minutos sem causa externa identificada e registrada;
- tempos de Whisper, WhisperX e NLLB apresentados separadamente;
- carregamento de modelos separado de inferência;
- RSS, memória disponível, threads efetivas e uso por núcleo registrados;
- se a meta não for atingida, a fase não deve ser declarada aprovada por causa de um único teste rápido.

O limite de 26min30s é um teto de recuperação inicial, não promessa de velocidade. O objetivo preferencial continua sendo retornar próximo de 23–25 minutos com a qualidade corrigida.

---

## 7. Matriz de arquivos a revisar

| Área | Arquivo | Responsabilidade |
|---|---|---|
| Segmentação | `src/legendar/application/pipeline/segmentation.py` | agrupamento por frase/oração, subdivisão temporal e exceções curtas |
| Contrato de tradução | `src/legendar/application/pipeline/translation.py` | unidade contextual, IDs e aplicação rastreável |
| Gemini | `src/legendar/infrastructure/translation/gemini.py` | parser, retries, recuperação por item/lote e métricas sanitizadas |
| NLLB | `src/legendar/infrastructure/translation/nllb.py` | idioma, limite de tokens, geração e batching |
| Política de recursos | `src/legendar/infrastructure/resources/profile.py` | topologia, afinidade e threads |
| Pipeline | `src/legendar/application/pipeline/serial_pipeline.py` | liberação segura, erro, cancelamento e gate |
| Layout | `src/legendar/domain/value_objects/text_layout.py` | linhas físicas, overflow sem perda |
| Entidade SRT | `src/legendar/domain/entities/subtitle.py` | contrato das cues e layout |
| Serialização | `src/legendar/infrastructure/filesystem/srt.py` | formato, round-trip e publicação |
| Qualidade | `src/legendar/application/pipeline/validation.py` | severidade e bloqueio |
| Alinhamento | `src/legendar/infrastructure/alignment/whisperx.py` | chamadas por segmento e possibilidade de janelas agrupadas |
| Avaliador | `scripts/phase8_srt_quality.py` | paridade de regras com o runtime |
| Testes | `tests/unit/application/test_segmentation.py` | pontuação, agregação, limites e preservação textual |
| Testes | `tests/unit/application/test_translation.py` | contrato, mapeamento e preservação de tempo |
| Testes | `tests/unit/infrastructure/test_gemini_translator.py` | resposta vazia, retries e recuperação |
| Testes | `tests/unit/infrastructure/test_nllb_translator.py` | idiomas, lote, limite de tokens e integridade |
| Testes | `tests/unit/infrastructure/test_resource_profile.py` | topologia e política de threads |
| Testes | `tests/unit/domain/test_text_layout.py` | limite físico sem perda |
| Testes | `tests/unit/application/test_pipeline.py` | lifecycle, cancelamento, publicação e gate |

Não modificar todos esses arquivos em um único commit sem uma divisão clara por etapa. Cada etapa deve ter commits pequenos, testes associados e revisão do diff.

---

## 8. Riscos de implementação e atalhos proibidos

| Atalho | Por que é perigoso | Alternativa exigida |
|---|---|---|
| Somente aumentar o tamanho do lote Gemini | pode aumentar truncamento e não resolve item vazio | classificar falha, validar por ID e recuperar com limites |
| Aceitar resposta parcial | produz SRT incompleto com aparência de sucesso | staging e gate de 100% dos IDs |
| Fazer fallback automático Gemini → NLLB | mistura estilos/qualidade, mascara falha e viola seleção explícita | erro claro; usuário escolhe outro backend |
| Trocar `por_Latn` por substituições de palavras/pronomes | não corrige sintaxe, sentido nem contexto | avaliação PT-BR por blocos completos |
| Fundir toda cue curta à próxima | apaga pausas, perguntas, interjeições e mudanças de frase | composição condicionada por pontuação, tempo e contexto |
| Dividir texto por contagem proporcional de palavras | timestamps deixam de representar fala real | cortes apenas em âncoras temporais válidas |
| Truncar texto para caber em 42 caracteres | perda silenciosa | subdividir em cues reais ou exigir revisão |
| Reduzir beam, aumentar batch ou trocar modelo ao mesmo tempo | impede atribuir causa e medir regressão | um experimento por variável |
| Concluir que a liberação de modelos causou a lentidão | logs não demonstram pressão de RAM/swap | corrigir lifecycle e medir separadamente |
| Considerar CI verde como aprovação de tradução | testes determinísticos não avaliam naturalidade humana | corpus-ouro e inspeção humana |
| Alterar o backend padrão nesta fase sem aprovação | decisão de produto independente da correção técnica | manter padrão até decisão explícita |

---

## 9. Handoff para a IA executora

A IA que executar esta fase deverá seguir este roteiro e não pular gates:

1. Ler este documento inteiro, [estado atual](ESTADO_ATUAL.md), [plano mestre](PLANO_CORRECAO_MELHORIA.md), [decisões](DECISOES.md) e [homologação](HOMOLOGACAO.md).
2. Confirmar que os arquivos de evidência ainda correspondem aos artefatos listados e calcular seus hashes.
3. Reproduzir métricas dos SRTs e logs antes de modificar código.
4. Abrir uma etapa de implementação por vez, com escopo fechado.
5. Antes de editar um módulo, ler sua implementação completa e todos os testes associados.
6. Escrever testes de regressão para a evidência específica antes ou junto da correção.
7. Executar a suíte relevante, Ruff, format check e validação documental após cada etapa.
8. Fazer revisão de efeitos colaterais: timestamps, conteúdo, IDs, cancelamento, publicação, memória e concorrência.
9. Atualizar este documento com resultado real, evidências e decisões; não marcar etapa como concluída sem teste.
10. Repetir a mídia real no hardware de referência somente depois de os testes determinísticos passarem.
11. Não executar benchmark amplo Gemini × NLLB nem trocar o backend padrão sem decisão explícita.
12. Ao final, atualizar os documentos vivos e a matriz de dependências; arquivar qualquer plano substituído sem apagar evidência.
13. Criar PR com commits por etapa, revisar diff integral, aguardar CI e só então fazer merge para `main`.
14. Validar o estado pós-merge: commit, workflows, documentos, links, lockfile e testes.
15. Entregar relatório de conclusão com cada gate como PASS/FAIL/BLOCKED, números medidos e limitações restantes.

### 9.1. Modelo de relatório por etapa

Para cada etapa, registrar:

- **Objetivo e hipótese**
- **Arquivos alterados**
- **Comportamento anterior reproduzido**
- **Correção feita**
- **Testes adicionados**
- **Comandos executados**
- **Resultado dos testes e cobertura**
- **Métricas antes/depois**
- **Riscos e regressões procurados**
- **Decisão:** PASS, FAIL ou BLOCKED
- **Commit/PR**
- **Pendências explícitas**

### 9.2. Condições de parada

Interromper a progressão e documentar o bloqueio se:

- o corpus de referência não puder ser reproduzido;
- houver perda de conteúdo ou deslocamento temporal;
- não for possível distinguir erro de ASR de erro de tradução;
- a melhoria de velocidade degradar semântica, PT-BR ou sincronização;
- a liberação de recursos puder afetar outro job ativo;
- os gates do aplicativo e do script divergirem;
- for necessária uma decisão de produto não coberta pelas decisões existentes.

---

## 10. Definição de conclusão da Fase 8.1

A Fase 8.1 só poderá ser marcada como concluída quando:

- Gemini tratar respostas vazias/malformadas com recuperação limitada e sem saída parcial;
- o perfil de CPU usar topologia real e a política de retenção funcionar como documentado;
- o agrupamento de cues reduzir fragmentação sem fundir sentenças legítimas;
- o SRT final respeitar o limite de duas linhas e 42 caracteres por linha sem perda;
- a tradução PT-BR passar pela amostra humana de aceitação;
- runtime e avaliador estrutural aplicarem os mesmos gates;
- a mediana quente da mídia de referência ficar dentro da meta definida, sem regressão de qualidade;
- os testes, documentação e CI estiverem verdes;
- a PR estiver mergeada na `main` e o estado pós-merge validado.

**Resultado esperado:** uma homologação repetível, com falhas recuperáveis, tradução em PT-BR natural, cues construídas por unidades de sentido, layout consistente e desempenho novamente próximo da baseline histórica — sem sacrificar rastreabilidade textual ou temporal.
