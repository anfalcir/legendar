# Estado atual do Legendar

- **Atualização:** 13/11/2026.
- **Situação do projeto:** desenvolvimento pausado por decisão do usuário após a homologação funcional do TranslateGemma.
- **Resultado:** o motor local funciona no fluxo real de tradução. A tradução e a composição/concentração das frases melhoraram; o resultado é suficiente para a relevância e a expectativa atuais, embora ainda não seja ótimo. Melhorias futuras continuam possíveis, mas não há trabalho ativo nem prazo de retomada.
- **Branch de referência:** `main`.
- **Repositório:** [anfalcir/legendar](https://github.com/anfalcir/legendar).

## Produto integrado

O Legendar é uma aplicação desktop PySide6 com três origens: mídia local, YouTube e arquivo SRT. Para mídia, executa aquisição/inspeção, preparação de áudio, ASR, alinhamento, segmentação, tradução opcional e publicação. Para uma origem SRT, executa leitura, tradução opcional, validação e publicação diretamente, sem reprocessar áudio.

A origem `Arquivo SRT` foi integrada pela [PR #43](https://github.com/anfalcir/legendar/pull/43), commit `483ec3ff6c9ef544553ea994084493ebe25cef72`. Ela exige idioma de origem explícito, preserva a ordem e os intervalos das cues e impede sobrescrever o arquivo de entrada. A rota foi coberta por testes de infraestrutura, aplicação, GUI e arquitetura.

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
