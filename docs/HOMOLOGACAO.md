# Homologação do Legendar — resultado atual

- **Data do registro:** 13/11/2026.
- **Decisão:** homologado funcionalmente para o uso atual; qualidade aceita como suficiente, ainda não ótima.
- **Motor local:** TranslateGemma 4B Instruct Q4_K_M via llama.cpp.
- **Entrada representativa:** `temporario/EN-baseline.srt`, inglês, 967 cues.
- **Destino:** português brasileiro.
- **Modo utilizado:** origem `Arquivo SRT`; tradução direta, sem repetir ASR ou alinhamento.

## Resultado observado

A execução real concluiu o fluxo de tradução com TranslateGemma. O usuário observou melhora na tradução e na composição/concentração das frases em comparação ao resultado anterior. A saída foi considerada suficiente para a relevância e a expectativa atuais do projeto, razão pela qual o desenvolvimento foi pausado neste marco.

A avaliação também identificou oportunidades de melhoria: naturalidade e precisão semântica, concisão, composição entre cues, consistência de nomes/termos e organização de frases. O resultado atual não deve ser descrito como perfeito, ótimo ou editorialmente definitivo.

Não foi elaborado nesta rodada um corpus humano de referência, pontuação WER/CER ou estudo comparativo quantitativo. A decisão é baseada na homologação funcional e na avaliação prática do usuário.

## Observação de recursos

Durante a execução, o usuário observou uso elevado de CPU e memória. A temperatura de CPU ficou em torno de 80 °C sob carga, enquanto o computador em repouso costuma ficar em torno de 40 °C. São observações do uso real, sem protocolo controlado, e ficam registradas como oportunidade de investigação futura, não como falha funcional confirmada.

## Critérios técnicos cobertos

- A entrada SRT exige idioma de origem explícito.
- O leitor aceita UTF-8/UTF-8-BOM, UTF-16 com BOM e Windows-1252; rejeita arquivo vazio, estrutura inválida e codificação inválida.
- A rota SRT não chama FFmpeg, Whisper ou WhisperX.
- A aplicação mantém ordem e timestamps das cues durante a tradução; os testes cobrem a preservação desses dados.
- A saída não pode sobrescrever a entrada, inclusive quando o pipeline é chamado fora da GUI.
- O protocolo TranslateGemma valida a estrutura de resposta, cardinalidade e IDs antes de aceitar cada lote; lotes com saída inválida recebem recuperação limitada e saída parcial não é publicada.
- Não há fallback automático para Gemini.

## Evidências de CI

| Marco | Resultado |
|---|---|
| Correção do protocolo TranslateGemma, PR #41 | 27 verificações aprovadas, 3 opcionais puladas, nenhuma falha |
| CI pós-merge da Fase 8 | 5/5 jobs aprovados |
| Origem SRT direta, PR #43 | 27 verificações aprovadas, 3 opcionais puladas, nenhuma falha |

A CI valida o comportamento automatizado e os contratos internos. Ela não substitui a avaliação humana da qualidade da tradução.

## Situação e retomada futura

A homologação funcional está encerrada para o objetivo atual. O projeto permanece pausado. Não há execução pendente, prazo ou obrigação de continuar o desenvolvimento.

Caso seja retomado, as frentes naturais são melhorar naturalidade PT-BR e fidelidade semântica, compor frases entre cues com mais inteligência, preservar terminologia/nomenclatura e investigar uso de CPU/memória/temperatura. Qualquer mudança deve comparar qualidade e desempenho em conjunto e não pode perder conteúdo nem deslocar timestamps sem evidência.

Documentos relacionados: [estado atual](ESTADO_ATUAL.md), [operação](OPERACAO.md), [arquitetura](ARQUITETURA.md) e [decisão técnica TranslateGemma](DECISAO_TRANSLATEGEMMA.md).
