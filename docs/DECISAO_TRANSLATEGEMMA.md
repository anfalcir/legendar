# Decisão técnica — substituição do motor local por TranslateGemma

- **Data:** 12/11/2026
- **Projeto:** Legendar
- **Status:** decisão aprovada; runtime autônomo, adaptador com batching/contexto e composição no bootstrap/Preferências estão na PR #36. A CI do incremento de batching está em execução; o smoke com pesos reais e a homologação no hardware de referência continuam pendentes.
- **Decisão:** substituir integralmente NLLB-200 pelo Google TranslateGemma 4B como único motor de tradução local. Gemini Developer API continua como backend remoto independente e explicitamente selecionável.
- **Modelo inicial:** TranslateGemma 4B Instruct, quantização GGUF Q4_K_M.
- **Runtime candidato adotado para a integração:** servidor local do projeto llama.cpp, com API HTTP restrita a loopback e parâmetros de idioma por requisição (chat_template_kwargs). O runtime deverá ser iniciado e encerrado pelo adaptador do Legendar, sem exigir daemon externo persistente.
- **Modelo GGUF candidato:** bullerwins/translategemma-4b-it-GGUF:Q4_K_M, derivado dos pesos oficiais google/translategemma-4b-it. O repositório declara licença Gemma; a quantização é derivada comunitária, não publicação oficial do Google.
- **Contrato de idioma:** origem e destino serão enviados como códigos explícitos. PT-BR será pt-BR; inglês seguirá a origem detectada/configurada (en inicialmente). Não confiar apenas no texto do prompt para definir o par.
- **Contrato de unidades:** preservar a porta Translator, índices, cardinalidade 1:1, ordem, cancelamento e timestamps externos ao adaptador. O adaptador envia um lote como uma única mensagem de usuário em texto, com marcadores exclusivos por cue e códigos de idioma em `chat_template_kwargs`; acrescenta até duas cues anteriores ao início do lote e até duas posteriores ao fim como contexto, descartando suas traduções. O lote inicial limita-se a 32 cues e 8.000 caracteres antes da contagem exata. O resultado só é aceito quando todos os marcadores aparecem exatamente uma vez, em ordem e com conteúdo não vazio. Respostas inválidas, truncadas ou com marcadores alterados provocam divisão recursiva do lote; a unidade isolada é reenviada como texto puro. Não existe fallback automático para NLLB.
- **Limite de contexto:** o cartão oficial informa contexto total de 2K tokens. O adaptador consulta `/v1/chat/completions/input_tokens` do llama.cpp com o payload completo para contar o prompt já renderizado pelo template; reserva até 512 tokens para saída e 64 tokens de margem. Lotes que excedem 2.048 tokens são divididos antes da geração. Lotes com saída incompleta ou estrutura inválida também são subdivididos, sem publicar resultado parcial.
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

### Implementação autônoma atual

A PR #36 agora inclui instalação assistida e idempotente do runtime CPU Linux x86_64 do llama.cpp, fixado no release `b12321`, com verificação SHA-256 do tarball, extração segura para o cache privado, retomada de download e carregamento das bibliotecas locais. A instalação ocorre somente após consentimento explícito; não usa sudo, não altera o PATH do sistema e não aceita licença/credencial em nome do usuário. O adaptador prepara runtime → modelo → servidor automaticamente antes da tradução e encerra apenas o processo que ele próprio iniciou. A validação do runtime real e do modelo real ainda depende do smoke no hardware de referência.

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
5. Migração do bootstrap e Preferências para expor TranslateGemma como backend local selecionável; integração inicial implementada na PR #36.
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

Para validar o contrato de lote do adaptador (três cues com marcadores e contagem real de tokens), execute:

```bash
uv run --locked --no-sync python scripts/phase8_1_translategemma_smoke.py --batch-check
```

O smoke de lote é aprovado apenas se o llama.cpp contar o prompt dentro do contexto de 2K e o modelo devolver os três marcadores, uma única vez e na ordem correta. Se falhar, não aumentar o lote nem remover a recuperação recursiva; registrar a resposta como incompatibilidade do template/quantização.


## Operação autônoma e idempotente do runtime

**Requisito de produto aprovado em 12/11/2026:** o usuário não deve precisar instalar, iniciar, monitorar ou encerrar manualmente o llama.cpp para usar a tradução local. O Legendar será responsável por preparar e gerenciar o runtime.

### Comportamento esperado

1. **Verificação leve na abertura:** inspecionar versão/compatibilidade do executável, presença e integridade básica do modelo em cache, permissões e espaço disponível. A verificação não baixa o modelo nem bloqueia a abertura da janela.
2. **Preparação sob demanda:** ao selecionar tradução local ou iniciar um job que a utiliza, executar novamente o preflight. Se faltar runtime, oferecer instalação assistida; se faltar modelo, informar tamanho/origem/licença e solicitar a autorização necessária antes do download. A instalação/download só ocorre após consentimento explícito.
3. **Inicialização automática:** imediatamente antes da etapa TRANSLATING, iniciar o servidor gerenciado pelo próprio Legendar, em loopback, com parâmetros compatíveis e porta alocada sem colisão. Aguardar readiness por health check com timeout e diagnóstico acionável.
4. **Reutilização:** se o processo gerenciado e o modelo/versionamento esperados já estiverem saudáveis, reutilizá-los. Chamadas repetidas de ensure/install/start devem convergir para o mesmo estado, sem reinstalação, downloads redundantes ou processos duplicados.
5. **Concorrência e propriedade:** proteger instalação, download e inicialização com lock entre threads/processos; distinguir processo próprio de qualquer servidor externo. Nunca encerrar nem adotar silenciosamente processo desconhecido que apenas responda na mesma porta.
6. **Falhas e cancelamento:** downloads devem ser retomáveis/atômicos, validar checksum quando publicado e nunca deixar artefato parcial como modelo instalado. Inicialização, health check e tradução devem respeitar cancelamento e timeouts; falhas devem explicar a ação necessária sem registrar tokens ou conteúdo das legendas.
7. **Encerramento:** reutilizar o servidor durante a vida do aplicativo e encerrar graciosamente apenas o processo filho iniciado pelo Legendar quando a aplicação fechar. Em seguida, aguardar e aplicar encerramento forçado apenas como último recurso. Preservar pesos e cache.
8. **Interface:** apresentar estados claros (verificando, aguardando autorização, instalando, baixando, iniciando, pronto, falha), progresso real quando disponível e ações explícitas para tentar novamente/abrir instruções. Toda operação demorada ocorre fora da thread visual.

### Política de segurança e instalação

- O endpoint deve escutar somente em `127.0.0.1`; não usar `0.0.0.0`, exposição LAN ou servidor persistente externo.
- Preferir distribuição oficial e versão fixada do llama.cpp por plataforma, com metadados de versão e verificação de integridade. Não executar scripts remotos arbitrários com privilégios elevados.
- Se a instalação exigir gerenciador do sistema, senha administrativa, termos de uso ou autenticação Hugging Face, parar e orientar/solicitar a ação do usuário; nunca elevar privilégios nem aceitar termos em seu nome.
- Não persistir tokens Hugging Face em QSettings, logs ou relatórios. Usar autenticação local já configurada pelo usuário ou fluxo seguro documentado.
- O downloader reutiliza, quando disponível, o token já mantido pelo `huggingface_hub`/ambiente (`HF_TOKEN`); não solicita nem persiste credenciais próprias. Respostas HTTP 401/403 orientam o usuário a aceitar os termos Gemma e autenticar-se localmente.
- Não baixar pesos automaticamente na abertura. O download pesado só começa após a escolha de tradução local e autorização informada.
- A instalação e o modelo ficam no diretório privado do Legendar, salvo quando uma instalação gerenciada pelo sistema for explicitamente escolhida pelo usuário.

### Critérios de aceite adicionais

- Duas ou mais chamadas concorrentes de preflight/start resultam em no máximo uma instalação/download e um processo gerenciado.
- Reabrir o aplicativo com runtime/modelo íntegros não altera arquivos nem baixa novamente.
- Reiniciar o aplicativo encerra o processo filho anterior quando possível e inicia um novo somente quando tradução for solicitada.
- Servidor externo, porta ocupada, processo morto, download interrompido, modelo corrompido, espaço insuficiente, ausência de autenticação e cancelamento têm testes de falha determinísticos.
- A GUI permanece responsiva durante verificação, instalação, download e inicialização.
- A tradução só começa após readiness confirmada; nenhum SRT parcial é publicado em falha.
- Nenhum fallback silencioso para Gemini ou NLLB. Gemini continua sendo uma escolha explícita independente.


## Artefato GGUF fixado para instalação reproduzível

- Repositório: `bullerwins/translategemma-4b-it-GGUF`
- Revisão imutável: `7c938465a870d8624bcfa98a8e4a3510053c19a8`
- Arquivo: `translategemma-4b-it-Q4_K_M.gguf`
- Tamanho publicado: aproximadamente 2,49 GB.
- SHA-256: `7f7357c14abd9da4eb200b38b05da502cd6e10d7e1d403fbc9f78c19f3209b72`
- Download: URL `resolve/{revision}/{filename}`, sem depender do branch mutável `main`.

A referência do arquivo e seu checksum foram conferidos na página do artefato Hugging Face. O arquivo GGUF é uma quantização comunitária derivada do TranslateGemma; a licença Gemma continua aplicável. O instalador deverá exibir essa informação antes de solicitar consentimento.

## Implementação incremental — primeira fatia do lifecycle

A PR #36 adiciona `infrastructure/translation/llama_runtime.py` e `infrastructure/translation/translategemma.py` com:
- inspeção local rápida de executável e arquivo GGUF, sem rede; download do GGUF após consentimento explícito, com retomada HTTP Range, arquivo parcial separado, SHA-256 fixado e publicação atômica;
- início do subcomando `llama serve` com loopback exclusivo, porta dinâmica, contexto de 2K e um slot;
- health check `/health` e identidade do modelo esperado em `/v1/models`, com timeout, cancelamento e detecção de saída prematura;
- locks de thread e de arquivo entre processos para downloads/servidores duplicados, reutilização apenas do processo filho próprio e encerramento gracioso/forçado desse filho;
- preservação do modelo/cache e testes unitários determinísticos com processo/HTTP simulados.

**Limites desta fatia:** a instalação assistida do runtime CPU Linux x86_64 está implementada em cache privado, sem sudo, com release fixado, SHA-256, retomada e extração segura. O GGUF é baixado no worker após consentimento explícito, com retomada e checksum. O adaptador prepara runtime → modelo → servidor automaticamente, conta o prompt renderizado pelo endpoint de tokens, agrupa cues e usa marcadores para reconstruir a relação 1:1; falhas de estrutura causam divisão recursiva até unidades individuais. O smoke dedicado de lote foi acrescentado, mas ainda precisa ser executado contra pesos reais. A implementação continua limitada a Linux x86_64 para instalação assistida; suporte/runtime das demais plataformas não foi homologado. O modelo real, o comportamento do template com marcadores, o desempenho e a qualidade PT-BR ainda não foram validados no hardware de referência. NLLB permanece temporariamente no código/`main` como baseline durante a migração, sem fallback silencioso.
