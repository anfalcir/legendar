# Estado atual do Legendar

- **Atualização:** 15/11/2026.
- **Situação do projeto:** retomada pontual para reforçar e tornar explícito o contrato de sincronização entre alinhamento, tradução e publicação; a evolução editorial continua sem prazo definido.
- **Resultado:** o motor local funciona no fluxo real de tradução. A tradução e a composição/concentração das frases melhoraram; o resultado é suficiente para a relevância e a expectativa atuais, embora ainda não seja ótimo. O trabalho desta rodada é de engenharia e regressão, não uma nova homologação de qualidade editorial.
- **Branch de referência:** `main`.
- **Repositório:** [anfalcir/legendar](https://github.com/anfalcir/legendar).

## Produto integrado

O Legendar é uma aplicação desktop PySide6 com três origens: mídia local, YouTube e arquivo SRT. Para mídia, executa aquisição/inspeção, preparação de áudio, ASR, alinhamento, segmentação, tradução opcional e publicação. Para uma origem SRT, executa leitura, tradução opcional, validação e publicação diretamente, sem reprocessar áudio.

A origem `Arquivo SRT` foi integrada pela [PR #43](https://github.com/anfalcir/legendar/pull/43), commit `483ec3ff6c9ef544553ea994084493ebe25cef72`. Ela exige idioma de origem explícito, preserva a ordem, o texto e os timestamps das cues e impede sobrescrever o arquivo de entrada. A rota foi coberta por testes de infraestrutura, aplicação, GUI e arquitetura. O bundle Linux `0.1.0` foi construído a partir da mesma árvore de código integrada.

## Transcrição, âncoras temporais e tradução

O fluxo de mídia já segue a separação correta de responsabilidades:

1. Whisper executa reconhecimento no idioma de origem (`task="transcribe"`). Os tempos de segmento são aproximados e servem como janelas de referência, não como âncoras finais.
2. WhisperX executa forced alignment por palavra contra o áudio. O pipeline exige evidência temporal confiável e bloqueia a publicação quando há palavras não alinhadas ou anomalias não recuperadas.
3. A segmentação forma as cues finais a partir das palavras alinhadas e mantém `source_segments`.
4. A tradução recebe uma unidade por cue, com ID, intervalo temporal e contexto. TranslateGemma usa lotes estruturados; IDs locais de cada lote são remontados para os índices originais.
5. A aplicação substitui exclusivamente o texto traduzido e preserva, sem recálculo, os índices, `TimeRange` e referências de origem. A publicação SRT é reaberta e comparada antes da troca atômica.

A tarefa de tradução nativa do Whisper não participa desse fluxo. Não se usa a duração do texto traduzido para estimar tempos. A decisão está registrada em [DECISOES.md](DECISOES.md), e os testes de regressão cobrem a correspondência entre unidades, trilho traduzido e timestamps efetivamente publicados.

## Tradução vigente

- **Motor local único:** TranslateGemma 4B Instruct, GGUF Q4_K_M, por llama.cpp gerenciado pelo aplicativo.
- **Opção remota:** Gemini Developer API, selecionável explicitamente em Preferências. O texto da legenda é enviado à API quando essa opção é escolhida.
- **Fallback:** não existe fallback automático entre o motor local e Gemini.
- **Configuração inicial:** TranslateGemma é o padrão local. Preferências antigas que apontavam para o motor local anterior são migradas para TranslateGemma.
- **Motor local anterior:** removido do código mantido, bootstrap, seletor de Preferências, testes específicos, workflow e dependências diretas de tradução. O registro histórico permanece em `docs/archive/`.
- **Cache antigo:** pesos/modelos que já existam no computador do usuário não são apagados automaticamente. Não são mais usados pelo aplicativo.

A instalação do runtime é assistida e idempotente. A inspeção leve ocorre na abertura; instalação/download sob demanda exigem autorização; o servidor local é iniciado e reutilizado automaticamente em loopback e apenas o processo gerenciado pelo aplicativo é encerrado.

## Resultado da homologação real

A execução representativa usou o SRT em inglês `temporario/EN-baseline.srt` (967 cues) como entrada direta e TranslateGemma para gerar português brasileiro, sem repetir ASR ou alinhamento.

O usuário confirmou que a tradução e a composição das frases melhoraram perceptivelmente e que o resultado atende ao uso pretendido neste momento. Também registrou que ainda há espaço para melhorar naturalidade, concisão e organização das frases. Não foi produzido nesta rodada um corpus humano de referência nem uma medição quantitativa WER/CER; portanto, a aprovação é funcional e de adequação prática ao uso atual, não uma declaração de qualidade editorial ótima.

Durante a execução real, foi observado uso elevado de CPU e memória e temperatura de CPU em torno de 80 °C sob carga, comparada a aproximadamente 40 °C em repouso. Esse registro é uma observação operacional do usuário, não um benchmark térmico ou de desempenho controlado.

Detalhes e limites estão em [HOMOLOGACAO.md](HOMOLOGACAO.md).

## Evidências de engenharia

- A integração do runtime e do adaptador TranslateGemma foi feita pela [PR #36](https://github.com/anfalcir/legendar/pull/36).
- A correção do protocolo de lotes, com JSON compacto, GBNF, orçamento de contexto e recuperação estrutural limitada, foi integrada pela [PR #41](https://github.com/anfalcir/legendar/pull/41), commit `fe615fe246f777ee17e19dff45c66986c8e348fd`.
- A CI da PR #41 aprovou 27 verificações; 3 verificações opcionais foram puladas e nenhuma falhou.
- A CI pós-merge da Fase 8 concluiu 5/5 jobs com sucesso.
- A CI da origem SRT na PR #43 aprovou 27 verificações; 3 opcionais foram puladas e nenhuma falhou.
- A PR documental #44 foi fechada sem merge independente ao ser substituída pela consolidação da PR #45. Seu registro da entrada SRT foi recuperado integralmente no plano arquivado em `docs/archive/phase-8.1/FASE_8_1_PLANO.md`; os documentos vivos já refletem esse estado consolidado.
- O bundle Linux x86_64 foi construído e teve seu checksum verificado; ainda não existe uma release estável publicada.

Os números de CI acima comprovam os contratos de software exercitados, não qualidade editorial por si só.

## Melhorias possíveis caso o projeto seja retomado

1. Refinar a naturalidade PT-BR, contexto e fidelidade semântica.
2. Melhorar a composição entre cues e a concisão das frases sem perda de significado.
3. Revisar nomes próprios, terminologia recorrente e consistência entre cenas/segmentos.
4. Investigar o consumo de CPU/memória e o aquecimento observado, medindo qualidade e desempenho em conjunto.

Esses itens são possibilidades futuras, não tarefas abertas ou compromisso de execução.

## Documentação

- [Índice da documentação viva](README.md).
- [Operação](OPERACAO.md).
- [Arquitetura](ARQUITETURA.md).
- [Instalação](INSTALACAO.md).
- [Distribuição Linux](DISTRIBUICAO_LINUX.md).
- [Decisão técnica TranslateGemma](DECISAO_TRANSLATEGEMMA.md).
- [Arquivo histórico](archive/README.md).
