# Decisão técnica — substituição do motor local por TranslateGemma

- **Data:** 12/11/2026
- **Projeto:** Legendar
- **Status:** decisão aprovada pelo usuário; implementação em andamento na Fase 8.1.
- **Decisão:** substituir integralmente NLLB-200 pelo Google TranslateGemma 4B como único motor de tradução local. Gemini Developer API continua como backend remoto independente e explicitamente selecionável.
- **Modelo inicial:** TranslateGemma 4B Instruct, quantização GGUF Q4_K_M.
- **Runtime candidato adotado para a integração:** servidor local do projeto llama.cpp, com API HTTP restrita a loopback e parâmetros de idioma por requisição (chat_template_kwargs). O runtime deverá ser iniciado e encerrado pelo adaptador do Legendar, sem exigir daemon externo persistente.
- **Modelo GGUF candidato:** bullerwins/translategemma-4b-it-GGUF:Q4_K_M, derivado dos pesos oficiais google/translategemma-4b-it. O repositório declara licença Gemma; a quantização é derivada comunitária, não publicação oficial do Google.
- **Contrato de idioma:** origem e destino serão enviados como códigos explícitos. PT-BR será pt-BR; inglês seguirá a origem detectada/configurada (en inicialmente). Não confiar apenas no texto do prompt para definir o par.
- **Contrato de unidades:** preservar a porta Translator, índices, cardinalidade 1:1, ordem, cancelamento e timestamps externos ao adaptador. O modelo recebe contexto vizinho limitado e instruções de preservação de entidades; o resultado só é aceito quando cada unidade esperada estiver presente exatamente uma vez e com texto não vazio.
- **Limite de contexto:** o cartão oficial informa contexto total de 2K tokens. O empacotamento de unidades deverá respeitar orçamento conservador, reservar espaço de saída e dividir/reprocessar lotes incompletos sem publicar saída parcial.
- **Privacidade:** tradução local não envia conteúdo à nuvem. O servidor deve escutar exclusivamente em 127.0.0.1; não expor porta à rede.
- **Download e integridade:** baixar sob demanda para cache do Legendar, validar tamanho/hash publicado quando disponível e falhar com mensagem explícita. Não commitar pesos nem conteúdo de mídia.
- **Licença:** Gemma Terms of Use e política de uso proibido aplicam-se aos pesos e derivados. O aplicativo deverá informar origem, licença e obrigações; não descrever o modelo como Apache/MIT nem como domínio público.
- **Remoção NLLB:** após a integração do novo adaptador e validação dos contratos, remover código, dependências, testes, configurações e documentação NLLB. Não manter NLLB como fallback oculto.
- **Critério de aceite:** testes unitários/integrados do adaptador e ciclo de vida; CI completa; smoke real do modelo; uma execução ponta a ponta no hardware de referência; avaliação do corpus-ouro PT-BR; comparação de tempo/RAM e qualidade com a evidência NLLB existente. CI verde isoladamente não aprova qualidade tradutória.

## Evidências técnicas

- [Modelo oficial e chat template](https://huggingface.co/google/translategemma-4b-it): exige uma única mensagem de usuário com conteúdo tipado e campos source_lang_code e target_lang_code; o cartão informa contexto de 2K tokens.
- [Derivado GGUF Q4_K_M e instruções llama.cpp](https://huggingface.co/bullerwins/translategemma-4b-it-GGUF): documenta o uso com llama.cpp e o arquivo Q4_K_M.
- [Suporte especializado no llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/chat.cpp): o parser TranslateGemma transforma mensagens e usa chat_template_kwargs para os códigos de idioma.
- [Documentação do servidor llama.cpp](https://github.com/ggml-org/llama.cpp/tree/master/tools/server): referência para API HTTP local.
- [Termos Gemma](https://ai.google.dev/gemma/terms): termos legais aplicáveis.

## Riscos e validações obrigatórias

1. Confirmar que a versão do llama.cpp distribuída/instalada reconhece o template TranslateGemma e aplica os códigos de idioma por requisição.
2. Confirmar compatibilidade do GGUF escolhido, tokenizer/chat template e quantização com essa versão.
3. Medir RAM e velocidade no Ryzen 3 2200G (4 núcleos físicos) antes de definir threads/contexto padrão.
4. Verificar se o download do repositório GGUF exige autenticação/aceite de licença; não armazenar tokens em logs ou preferências sem proteção.
5. Avaliar tradução de blocos de legenda, contexto, PT-BR oral e entidades com referência humana, não apenas frases isoladas.
6. Tratar falha do servidor, encerramento, cancelamento, timeout, porta ocupada, download interrompido e falta de espaço sem travar a GUI ou publicar SRT parcial.

## Sequência de implementação

1. Prova de conceito reproduzível do servidor e do chat_template_kwargs.
2. Adaptador TranslateGemmaTranslator sob a porta existente.
3. Gestão do processo local, download/cache e readiness.
4. Testes de unidade, integração e falhas.
5. Migração do bootstrap, Preferências e runtime para TranslateGemma como única rota local.
6. Remoção total de NLLB e limpeza de dependências/documentação.
7. CI, smoke real, corpus-ouro e homologação E2E.


## Prova de conceito manual do protocolo

Instale o runtime llama.cpp conforme a [documentação do modelo GGUF](https://huggingface.co/bullerwins/translategemma-4b-it-GGUF). Em Linux/macOS, o repositório documenta o instalador do projeto; no Windows, documenta WinGet. O primeiro início baixa a quantização escolhida e pode exigir que o usuário aceite os termos Gemma no Hugging Face.

Inicie o servidor **somente em loopback**, com um slot e contexto nativo:

```bash
llama serve -hf bullerwins/translategemma-4b-it-GGUF:Q4_K_M \
  --host 127.0.0.1 --port 8080 -c 2048 -np 1 -t 4 --no-webui \
  --alias translategemma-4b
```

Em outro terminal, na raiz do repositório:

```bash
uv run --locked --no-sync python scripts/phase8_1_translategemma_smoke.py \
  "I will be back."
```

O smoke usa apenas a API local, envia os códigos de idioma por requisição em chat_template_kwargs e imprime somente o texto retornado. Ele não inicia o servidor nem baixa pesos. O adaptador de produção deverá gerenciar essas duas responsabilidades; este script é exclusivamente uma prova de protocolo. Ainda é necessário executar o smoke com o modelo real antes de declarar compatibilidade.
