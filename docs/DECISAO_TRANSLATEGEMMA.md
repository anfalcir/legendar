# Decisão técnica — motor local TranslateGemma

- **Atualização:** 13/11/2026.
- **Status:** integrado e funcionalmente homologado no fluxo real de tradução.
- **Motor local vigente:** TranslateGemma 4B Instruct, GGUF Q4_K_M.
- **Runtime:** llama.cpp gerenciado automaticamente pelo Legendar.
- **Alternativa remota:** Gemini Developer API, opcional e selecionada explicitamente.
- **Qualidade observada:** melhora perceptível em tradução e composição das frases; suficiente para o uso atual, mas ainda aquém do resultado ideal. O projeto está pausado com possibilidade de evolução futura.

## Decisão

TranslateGemma é o único motor de tradução local mantido pelo aplicativo. O backend Gemini continua disponível como opção remota, sem fallback automático. A seleção local padrão é TranslateGemma. Configurações persistidas da antiga opção local são migradas para TranslateGemma; o identificador antigo não seleciona nem inicializa outro motor.

O motor local anterior foi removido do código mantido, bootstrap, interface, testes específicos, workflow dedicado e dependências diretas de tradução. Os planos e resultados antigos foram preservados em [archive](archive/phase-8.1/README.md). Pesos legados já baixados no computador não são apagados automaticamente.

## Modelo e protocolo

- Modelo: `google/translategemma-4b-it`.
- Quantização GGUF adotada: `bullerwins/translategemma-4b-it-GGUF:Q4_K_M`.
- Revisão imutável do repositório GGUF: `7c938465a870d8624bcfa98a8e4a3510053c19a8`.
- Arquivo: `translategemma-4b-it-Q4_K_M.gguf`.
- SHA-256 do arquivo: `7f7357c14abd9da4eb200b38b05da502cd6e10d7e1d403fbc9f78c19f3209b72`.
- Licença: os termos Gemma aplicam-se aos pesos e derivados. A quantização GGUF é um artefato comunitário derivado dos pesos oficiais; a licença MIT do código do aplicativo não altera os termos do modelo.

O adaptador envia o par de idiomas explicitamente por requisição. As unidades são agrupadas em JSON compacto com IDs locais numéricos; cues adjacentes podem ser fornecidas como contexto sem alterar o contrato externo. O lote inicial limita-se a até 32 cues e 8.000 caracteres antes da contagem exata. O runtime conta o prompt já renderizado pelo chat template e reserva orçamento para a saída dentro do contexto de 2K tokens.

A resposta usa gramática GBNF e é validada novamente pelo aplicativo quanto a JSON, cardinalidade, IDs e conteúdo não vazio. Lotes fora do orçamento são subdivididos antes da geração; respostas estruturalmente inválidas recebem recuperação limitada. Nenhum resultado parcial é publicado. Os timestamps permanecem no domínio da aplicação e não são gerados pelo modelo.

## Operação do runtime

O Legendar gerencia instalação, download, preparação, inicialização, health check, reutilização e encerramento do servidor. O runtime CPU Linux x86_64 é fixado no release llama.cpp `b12321`, com verificação de integridade e extração segura. A instalação do runtime e o download do GGUF são feitos sob demanda e exigem autorização explícita.

O servidor escuta somente em `127.0.0.1`. O aplicativo reutiliza somente o processo que ele próprio iniciou e encerra apenas esse processo. O modelo e o cache são preservados entre execuções. Operações demoradas ocorrem em worker, não na thread da interface.

A instalação assistida documentada está limitada a Linux x86_64. A CI cobre a base Python do aplicativo, mas não representa homologação completa de todos os sistemas operacionais.

## Privacidade

TranslateGemma executa localmente e não envia as cues a um serviço externo. O Gemini envia o texto à API do Google quando escolhido; essa escolha é explícita. A chave Gemini é armazenada no perfil privado do usuário e não deve aparecer em QSettings, logs, URLs ou relatórios.

## Homologação

A execução representativa com arquivo SRT em inglês e destino PT-BR concluiu o fluxo real. O usuário observou melhora na tradução e na composição das frases e aceitou a saída como suficiente para a necessidade atual. A aceitação é funcional e prática; não equivale a qualidade ótima, nem a uma aprovação quantitativa WER/CER ou por corpus humano.

Melhorias futuras podem investigar naturalidade, precisão semântica, concisão, composição entre cues, terminologia e desempenho/consumo de recursos. O trabalho está pausado e não há plano ativo de execução.

## Referências técnicas

- [Modelo oficial e chat template](https://huggingface.co/google/translategemma-4b-it).
- [Derivado GGUF Q4_K_M](https://huggingface.co/bullerwins/translategemma-4b-it-GGUF).
- [Suporte do llama.cpp ao parser TranslateGemma](https://github.com/ggml-org/llama.cpp/blob/master/common/chat.cpp).
- [Servidor llama.cpp](https://github.com/ggml-org/llama.cpp/tree/master/tools/server).
- [Termos Gemma](https://ai.google.dev/gemma/terms).
