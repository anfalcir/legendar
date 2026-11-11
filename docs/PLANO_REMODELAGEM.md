# Plano de remodelagem do Legendar

- **Documento:** plano mestre do produto e da implementação
- **Status:** implementado e validado nas Fases 0–9; a homologação do usuário com mídia real, modelos completos e computador-alvo permanece como etapa final
- **Escopo:** aplicação desktop pessoal para transcrição, alinhamento, tradução e exportação de legendas SRT
- **Branch de referência:** main

---

## 1. Objetivo e visão do produto

Transformar o Legendar em uma aplicação desktop especializada em produzir legendas SRT fiéis ao conteúdo falado, temporalmente alinhadas ao áudio e, quando solicitado, traduzidas para inglês ou português brasileiro.

O produto deverá combinar:

1. Reconhecimento de fala com Whisper.
2. Alinhamento temporal refinado da transcrição com o áudio original.
3. Segmentação de texto em unidades confortáveis de leitura.
4. Tradução contextual sem perder a correspondência temporal com a fala.
5. Validação automática e exportação segura do SRT.
6. Interface gráfica elegante, responsiva e previsível durante todo o processamento.

**Princípio central:** a qualidade do Legendar será medida pelo resultado final — fidelidade textual, sincronização, legibilidade e confiabilidade operacional — e não apenas pela integração de modelos de IA.

Não existe sincronização universalmente infalível. Ruído, fala simultânea, pronúncia incomum, música e erros de reconhecimento podem limitar o resultado. O sistema deverá detectar, sinalizar e tratar essas situações, sem fabricar timestamps ou apresentar confiança inexistente.

## 2. Escopo do produto

### 2.1. Funcionalidades incluídas

| ID | Requisito | Comportamento esperado |
|---|---|---|
| FR-01 | Arquivos locais | Aceitar os principais formatos de áudio e vídeo suportados pelo FFmpeg instalado. |
| FR-02 | YouTube | Receber URL de vídeo e obter o áudio necessário ao processamento. |
| FR-03 | Inspeção de mídia | Identificar duração, streams, codecs, resolução temporal e faixas de áudio. |
| FR-04 | Seleção de faixa | Permitir escolher a faixa quando houver múltiplas faixas de áudio; selecionar uma faixa padrão quando houver apenas uma. |
| FR-05 | Normalização | Preparar o áudio em formato interno consistente sem perder o mapeamento de tempo para a mídia original. |
| FR-06 | Transcrição | Utilizar Whisper para reconhecer a fala no idioma original. |
| FR-07 | Idioma de origem | Detectar automaticamente e permitir correção manual pelo usuário. |
| FR-08 | Alinhamento | Produzir âncoras temporais por palavra ou unidade compatível com o alinhador. |
| FR-09 | Controle de qualidade | Identificar palavras não alinhadas, tempos suspeitos, lacunas, sobreposições e segmentos fora da duração da mídia. |
| FR-10 | Segmentação | Agrupar palavras em legendas legíveis, respeitando pausas, sintaxe e limites configurados. |
| FR-11 | Tradução | Traduzir para inglês ou português brasileiro, preservando sentido e vínculo temporal com o texto original. |
| FR-12 | SRT | Gerar arquivo SRT UTF-8 com numeração e timestamps válidos. |
| FR-13 | Progresso | Exibir etapa atual e percentual somente quando houver progresso mensurável. |
| FR-14 | Logs | Disponibilizar log de etapas claro, recolhível e atualizado durante a execução. |
| FR-15 | Cancelamento | Permitir cancelamento cooperativo e limpeza segura dos recursos do trabalho. |
| FR-16 | Recuperação | Apresentar erros compreensíveis sem encerrar inesperadamente a interface. |
| FR-17 | Preferências | Persistir preferências simples, como idioma final e pasta de saída. |
| FR-18 | Cache | Reutilizar modelos já disponíveis e isolar arquivos temporários por trabalho. |

### 2.2. Idiomas

- Idiomas finais suportados pelo produto: **inglês (EN)** e **português brasileiro (PT-BR)**.
- Idioma de origem: detecção automática, com possibilidade de seleção manual.
- A matriz de idiomas efetivamente homologados dependerá da disponibilidade e da qualidade dos modelos de alinhamento.
- Quando origem e destino forem iguais, não executar tradução desnecessária.
- Um idioma reconhecido pelo Whisper não será automaticamente considerado homologado para alinhamento temporal.

### 2.3. Fontes e formatos

**Fontes de entrada:**

- URL pública de vídeo do YouTube.
- Arquivo local de áudio.
- Arquivo local de vídeo.

**Formatos candidatos para homologação:**

| Tipo | Formatos |
|---|---|
| Vídeo | MP4, MKV, MOV, AVI, WebM, WMV, MPEG, FLV |
| Áudio | MP3, WAV, M4A, AAC, FLAC, OGG, OPUS, WMA |

A extensão não será considerada prova suficiente de compatibilidade. A aplicação deverá inspecionar o conteúdo com ffprobe e tratar codecs ou contêineres não suportados com mensagens claras. A lista final será definida pela matriz de testes, não apenas por uma lista nominal.

### 2.4. Fora do escopo inicial

Para manter o produto enxuto, não fazem parte da primeira versão:

- Editor profissional de vídeo.
- Queima ou incorporação de legendas no vídeo.
- Exportação para múltiplos formatos além de SRT.
- Diarização ou identificação de cada pessoa que fala.
- Banco de dados de projetos e histórico complexo.
- Contas, nuvem ou sincronização entre dispositivos.
- Processamento paralelo de vários trabalhos na mesma instância.
- Múltiplos provedores de tradução configuráveis pelo usuário.
- Ferramentas de edição audiovisual não essenciais à produção do SRT.

Uma pré-visualização simples de mídia sincronizada com legendas poderá ser avaliada como evolução posterior, depois de estabilizado o pipeline principal.

## 3. Jornada principal do usuário

1. O usuário escolhe YouTube ou arquivo local.
2. Informa ou seleciona a mídia.
3. O sistema inspeciona o arquivo e, se necessário, solicita a faixa de áudio.
4. O usuário confirma idioma de origem (automático ou manual), idioma final e destino do SRT.
5. O sistema apresenta um resumo e solicita confirmação para iniciar.
6. A aplicação bloqueia controles incompatíveis com a execução e mostra o painel de progresso.
7. O pipeline extrai e normaliza o áudio, transcreve, alinha, segmenta, traduz quando necessário e valida.
8. O arquivo temporário é validado e publicado no destino por operação segura.
9. A interface informa conclusão e permite abrir a pasta ou localizar o SRT produzido.

O usuário deverá sempre saber em qual etapa o trabalho está, o que está sendo executado e se a operação pode ser cancelada.

## 4. Requisitos de experiência e interface

### 4.1. Organização visual

A janela principal deverá priorizar:

- Seleção da origem da mídia.
- Idioma de origem, com detecção automática e opção manual.
- Idioma final: EN ou PT-BR.
- Diretório e nome do arquivo de saída.
- Ação principal para gerar as legendas.

Configurações avançadas não essenciais não deverão ocupar a tela principal. A identidade visual deverá ser consistente, com tipografia, espaçamento, hierarquia, ícones, estados e feedback cuidadosamente tratados.

### 4.2. Estados da interface

A aplicação deverá implementar uma máquina de estados explícita. Os estados mínimos são:

| Estado | Processar | Cancelar | Campos de entrada |
|---|---|---|---|
| Aguardando | Ativo quando os dados forem válidos | Desativado | Ativos |
| Validando | Desativado | Conforme a operação | Bloqueados |
| Preparando mídia | Desativado | Ativo | Bloqueados |
| Transcrevendo | Desativado | Ativo | Bloqueados |
| Alinhando | Desativado | Ativo | Bloqueados |
| Segmentando/traduzindo | Desativado | Ativo | Bloqueados |
| Validando SRT | Desativado | Ativo até o ponto seguro | Bloqueados |
| Cancelando | Desativado | Desativado | Bloqueados |
| Concluído | Ativo | Desativado | Ativos |
| Falha | Ativo | Desativado | Ativos |

A tabela deverá ser refinada conforme os limites de cancelamento de cada etapa. Não será permitido iniciar outro trabalho enquanto o anterior estiver ativo ou em cancelamento.

### 4.3. Proteção contra cliques acidentais

- Exigir confirmação antes de iniciar, exibindo origem, idioma de destino e arquivo de saída.
- Desabilitar imediatamente o botão de processamento após a confirmação.
- Prevenir disparo duplicado por cliques rápidos, sinais repetidos ou atalhos.
- Bloquear campos que não podem mudar durante o trabalho.
- Exigir confirmação para cancelar uma operação ativa.
- Desabilitar o botão de cancelar depois do primeiro pedido de cancelamento.
- Restaurar controles somente após encerramento confirmado e limpeza necessária.

A proteção deverá existir na lógica de aplicação, não apenas na apresentação visual dos botões.

### 4.4. Progresso e logs

- Exibir percentual somente quando a etapa fornecer progresso real ou uma estimativa calibrada e claramente identificada.
- Utilizar progresso indeterminado quando não houver métrica confiável.
- Mostrar o nome da etapa atual e mensagens curtas, sem mensagens repetitivas ou artificiais.
- Permitir recolher e expandir o log sem interromper o processamento.
- Registrar mudanças de etapa, progresso, avisos, erros e conclusão com timestamp.
- Atualizar a GUI por sinais/eventos, mantendo processamento pesado fora da thread principal.
- Não utilizar sleeps artificiais nem chamadas repetidas a processEvents para simular responsividade.

## 5. Estratégia de transcrição, alinhamento e sincronização

Esta é a área de maior risco técnico e deverá ser validada antes da construção completa do produto.

### 5.1. Pipeline recomendado

1. Inspecionar mídia e selecionar o stream de áudio.
2. Extrair áudio para uma representação interna padronizada.
3. Executar Whisper em modo de transcrição, no idioma de origem — não usar a tradução automática do Whisper para gerar o texto final.
4. Obter transcrição segmentada e metadados do reconhecimento.
5. Executar forced alignment com WhisperX e modelo compatível com o idioma.
6. Mapear os timestamps para a linha temporal da mídia original.
7. Aplicar validação e classificação de qualidade das âncoras.
8. Segmentar o texto original com base nas palavras alinhadas.
9. Traduzir as unidades sem perder a associação temporal com o original.
10. Validar conteúdo, temporalidade e legibilidade.
11. Serializar, validar novamente e publicar o SRT.

**Responsabilidade dos componentes:**

- Whisper: reconhecer o conteúdo falado.
- WhisperX/alinhador: localizar temporalmente o texto reconhecido no áudio.
- VAD: identificar regiões de atividade de fala e apoiar segmentação/inspeção.
- Segmentador: organizar as palavras em unidades de legenda.
- Tradutor: produzir o texto no idioma final, sem inventar timestamps.
- Validador SRT: impedir a publicação de arquivo estruturalmente inválido.

Forced alignment localiza no áudio um texto fornecido; não corrige por si só erros de reconhecimento. Se a transcrição estiver errada, o alinhamento poderá falhar ou encontrar correspondências inadequadas. O fluxo deverá distinguir erro textual de erro temporal.

### 5.2. Whisper e idioma original

- Manter Whisper como motor central de reconhecimento.
- Avaliar modelos e perfis de desempenho/precisão em amostras representativas.
- Registrar modelo, idioma, parâmetros e versão usada no trabalho.
- Evitar baixar novamente modelos já armazenados.
- Não presumir que timestamps aproximados do reconhecimento são equivalentes a alinhamento por palavra.
- Não utilizar timestamps da tarefa de tradução do Whisper como base de sincronização.

### 5.3. Forced alignment

**Candidato primário:** WhisperX, condicionado à prova técnica de compatibilidade, instalação, licença, suporte de idioma e qualidade.

**Alternativa não selecionada na Fase 0:** stable-ts. Ela não foi adicionada ao manifesto nem definida como fallback automático. Reconsiderar somente se a avaliação com timestamps humanos da Fase 5 identificar limitações relevantes no alinhador primário; nesse caso, comparar ambos no mesmo corpus anotado, idiomas e condições. Essa eventual comparação é uma decisão de produto da Fase 5, não uma pendência da Fase 0.

O alinhador deverá ser selecionado por idioma. Deve existir matriz explícita de suporte e de homologação. Quando não houver alinhador compatível ou a qualidade for insuficiente, o sistema deverá informar a limitação e evitar apresentar o resultado como plenamente sincronizado.

### 5.4. Tratamento temporal robusto

- Preservar duração, time base e offset do stream de áudio original.
- Aplicar compensação de offset quando a faixa selecionada começar depois do início do contêiner.
- Se houver segmentação em chunks, preservar a origem temporal de cada chunk e o overlap entre blocos.
- Converter tempos locais dos chunks para tempos globais antes de segmentar o SRT.
- Evitar duplicação ou perda de palavras em regiões de overlap.
- Não eliminar pausas nem comprimir a linha temporal de modo que as legendas deixem de corresponder à mídia original.
- Detectar timestamps ausentes, negativos, invertidos, de duração zero, excessivamente curtos/longos ou fora da duração.
- Detectar sobreposições incompatíveis, lacunas suspeitas e palavras sem alinhamento.
- Preservar o texto original reconhecido separadamente do texto normalizado usado pelo alinhador.
- Tratar números, siglas, abreviações, pontuação, contrações e nomes próprios sem alterar silenciosamente o conteúdo apresentado.
- Não distribuir artificialmente palavras por uma frase inteira quando o alinhador não fornecer âncoras confiáveis.
- Sinalizar trechos problemáticos para revisão em vez de fabricar precisão.

VAD poderá apoiar limites de fala e regiões de silêncio, mas não deverá substituir o alinhamento fonético ou deslocar os timestamps sem mapeamento verificável.

### 5.5. Tradução e preservação do tempo

A tradução ocorrerá depois da transcrição e do alinhamento na língua de origem.

Regras:

- Traduzir unidades semânticas com contexto suficiente.
- Manter vínculo explícito entre texto de origem, intervalo temporal e texto traduzido.
- Preservar nomes, números, referências e termos técnicos.
- Não resumir, omitir ou acrescentar conteúdo.
- Não atribuir timestamps com base na quantidade de palavras da tradução.
- Se uma unidade traduzida precisar ser dividida, a divisão deverá utilizar âncoras da fala original e limites sintáticos defensáveis.
- Quando não houver âncora segura para redistribuir um trecho traduzido, sinalizar para revisão.
- Se origem e destino forem iguais, reutilizar a transcrição original e não chamar o serviço de tradução.

A primeira versão poderá utilizar um único serviço contextual de tradução por meio de uma interface interna isolada. O provedor ainda deverá ser escolhido. Apenas texto e contexto estritamente necessários serão enviados; o áudio não será enviado ao serviço de tradução. Credenciais nunca poderão ser armazenadas no repositório.

### 5.6. Segmentação e legibilidade

Parâmetros iniciais para experimentar e calibrar:

| Critério | Ponto de partida |
|---|---|
| Linhas por legenda | Até 2 |
| Caracteres por linha | Referência de até 42 |
| Velocidade de leitura | Alvo inicial de até 17 caracteres por segundo |
| Duração mínima | Referência de 1 segundo |
| Duração máxima | Referência de 7 segundos |
| Quebra | Preferir fronteiras sintáticas e semânticas |
| Sobreposição | Evitar, exceto quando tecnicamente justificada |
| Pontuação | Natural no idioma final |

Esses parâmetros são configurações iniciais, não regras universais. Serão avaliados por idioma, tipo de conteúdo e duração da fala. Não se deverá alterar o tempo de fala apenas para esconder um texto excessivamente longo; o algoritmo deverá buscar divisão semanticamente correta e, quando não for possível, emitir alerta.

## 6. Preparação e entrada de mídia

### 6.1. FFmpeg e ffprobe

- Utilizar ffprobe para obter streams, codecs, duração e metadados temporais.
- Utilizar FFmpeg para extrair e normalizar o áudio.
- Não confiar somente na extensão do arquivo.
- Tratar arquivos sem áudio, corrompidos, truncados ou com codec indisponível.
- Permitir seleção de faixa quando houver múltiplas faixas.
- Homologar os formatos e combinações de contêiner/codec efetivamente suportados.

A representação interna inicial a avaliar é WAV PCM, mono, 16 kHz, desde que a prova técnica confirme compatibilidade com os modelos escolhidos. O processamento não deverá perder o mapeamento temporal da mídia original.

### 6.2. YouTube

- Utilizar yt-dlp para obter o áudio necessário.
- Validar URL e tratar vídeo privado, indisponível, removido ou restrito.
- Exibir progresso real do download quando disponível.
- Permitir cancelamento efetivo do subprocesso.
- Limitar e tratar tentativas de rede.
- Remover artefatos temporários do trabalho.
- Não armazenar cookies, tokens ou credenciais em logs ou no repositório.
- Utilizar somente conteúdo que o usuário tenha direito de acessar e processar, respeitando os termos aplicáveis da plataforma.

### 6.3. Temporários e cache

- Criar diretório temporário isolado por job.
- Nunca apagar uma pasta global compartilhada durante a execução.
- Separar cache de modelos de arquivos temporários de mídia.
- Remover temporários ao concluir, falhar ou cancelar, com política segura de recuperação para encerramentos inesperados.
- Não apagar arquivos de entrada nem sobrescrever saídas existentes sem confirmação.

## 7. Arquitetura proposta

A arquitetura deverá separar regras de negócio, orquestração, infraestrutura e apresentação. A estrutura é uma referência inicial e poderá ser simplificada quando a implementação demonstrar que uma separação adicional não agrega valor.

    src/
      legendar/
        main.py
        bootstrap.py
        domain/
          models.py
          subtitles.py
          job_states.py
          exceptions.py
        application/
          job_controller.py
          processing_pipeline.py
          services/
            media_service.py
            transcription_service.py
            alignment_service.py
            translation_service.py
            subtitle_service.py
        infrastructure/
          media/
            ffmpeg.py
            youtube.py
          transcription/
            whisper_engine.py
          alignment/
            whisperx_engine.py
          translation/
            provider.py
          export/
            srt_writer.py
        presentation/
          gui/
            main_window.py
            components/
            dialogs/
            workers/
            controllers/
            styles/
        config/
          settings.py
    tests/
      unit/
      integration/
      e2e/
      fixtures/
    docs/
      PLANO_REMODELAGEM.md
      ESTADO_ATUAL.md
      FASE_0_PROTOCOLO.md
      MATRIZ_DEPENDENCIAS.md
    resources/
      icons/
    README.md
    LICENSE
    pyproject.toml
    uv.lock

### 7.1. Responsabilidades

| Camada | Responsabilidade |
|---|---|
| domain | Modelos, estados, invariantes e regras independentes de framework |
| application | Orquestração do job, casos de uso e políticas de fluxo |
| infrastructure | Integrações com Whisper, alinhadores, tradução, FFmpeg e YouTube |
| presentation | Widgets, janelas, diálogos, sinais e apresentação de estado |
| tests | Evidências automatizadas de qualidade |
| docs | Plano, arquitetura, operação e validação |

### 7.2. Regras arquiteturais

- A lógica de negócio não deverá depender de widgets Qt.
- A interface não deverá executar Whisper, FFmpeg ou chamadas de rede na thread principal.
- Workers deverão comunicar progresso e resultado por sinais/eventos estruturados.
- O controlador de job deverá ser a autoridade sobre transições de estado.
- Cancelamento deverá atravessar as etapas por mecanismo cooperativo e explícito.
- Dependências externas deverão ser encapsuladas por serviços/adaptadores.
- O pipeline deverá receber dependências de forma testável, permitindo mocks nos testes.
- O produto deverá oferecer um caminho de execução em CPU quando suportado pelos componentes e tratar aceleração por hardware como perfil opcional. O hardware de uma máquina de desenvolvimento não poderá, sozinho, determinar o conjunto de dependências, a arquitetura ou os sistemas suportados.
- Persistência de preferências poderá utilizar QSettings; banco de dados não é necessário no escopo inicial.
- Empacotamento deverá ser tratado depois de estabilizada a aplicação.

## 8. Confiabilidade, segurança e recuperação

### 8.1. Publicação segura do SRT

- Gerar o conteúdo em arquivo temporário no mesmo destino ou em local que permita rename atômico.
- Validar o arquivo completo antes da publicação.
- Usar nome sem colisão ou solicitar confirmação antes de sobrescrever.
- Publicar por operação atômica quando suportada pelo sistema de arquivos.
- Em falha, manter a saída anterior intacta e remover apenas o temporário pertencente ao job.

### 8.2. Cancelamento

- Cancelar downloads e subprocessos explicitamente.
- Interromper a etapa corrente em ponto seguro, quando possível.
- Não matar a thread da GUI.
- Não finalizar a aplicação como substituto de cancelamento.
- Não marcar o trabalho como cancelado antes da confirmação de encerramento dos processos.
- Limpar apenas os recursos do próprio job.
- Registrar o resultado do cancelamento e eventuais recursos que não puderam ser removidos.

### 8.3. Erros

Cada falha deverá conter categoria, etapa, mensagem compreensível e detalhe técnico disponível no log. Categorias mínimas:

- Entrada inválida.
- Mídia sem áudio ou não suportada.
- Falha de download.
- Falha de FFmpeg/ffprobe.
- Falha de modelo ou reconhecimento.
- Idioma/alinhador não suportado.
- Alinhamento insuficiente.
- Falha de tradução ou indisponibilidade do provedor.
- Falha de validação SRT.
- Falha de escrita ou falta de espaço.
- Cancelamento.
- Erro inesperado.

Nenhum erro deverá resultar em um SRT incompleto apresentado como concluído.

### 8.4. Privacidade

- O repositório é privado e destinado a uso pessoal.
- Nenhuma credencial, token, cookie, chave de API ou arquivo de mídia privado será commitado.
- Logs deverão evitar conteúdo sensível e segredos.
- O áudio deverá permanecer local, salvo decisão futura explícita e documentada.
- Caso a tradução utilize serviço externo, transmitir somente o texto necessário e deixar esse comportamento documentado.
- Não adicionar telemetria ou coleta de dados sem necessidade e consentimento.

## 9. Estratégia de testes e qualidade

A qualidade será demonstrada por testes e amostras de referência, não por inspeção visual isolada.

### 9.1. Testes unitários

Cobrir:

- Validação de URL, caminhos, arquivos e formatos.
- Inspeção de streams e seleção de áudio.
- Comandos e argumentos de FFmpeg/ffprobe.
- Normalização e mapeamento temporal.
- Conversão de timestamps e offsets.
- Modelos de domínio e transições da máquina de estados.
- Tratamento de palavras não alinhadas.
- Segmentação e quebra de linhas.
- Tradução estruturada e validação da resposta.
- Numeração, ordenação e serialização SRT.
- Escrita atômica, colisões e limpeza de temporários.
- Cancelamento e recuperação de erros.

### 9.2. Testes de integração

Cobrir integrações reais ou controladas com:

- ffprobe e FFmpeg.
- yt-dlp.
- Whisper.
- WhisperX e modelos de alinhamento.
- Serviço de tradução selecionado.
- Sistema de arquivos e publicação SRT.

Os testes unitários e de CI não deverão depender de baixar modelos grandes ou acessar serviços externos. Utilizar mocks e fixtures pequenas. Testes reais de modelos deverão ser uma suíte separada, identificada e reproduzível.

### 9.3. Base de referência temporal

Criar um conjunto pequeno e versionado de áudios próprios ou autorizados, com transcrição e marcações temporais verificadas manualmente.

Casos mínimos:

- PT-BR com fala clara.
- Inglês com fala clara.
- Diferentes velocidades de fala.
- Pausas longas e curtas.
- Música de fundo.
- Ruído ambiental.
- Nomes próprios e termos técnicos.
- Números, datas e siglas.
- Frases longas.
- Sobreposição de vozes.
- Áudio estéreo e múltiplas faixas.
- Mídia com offset de áudio diferente de zero.
- Mídia longa e processamento por chunks.

Avaliar:

- WER ou métrica equivalente para erros de reconhecimento.
- Erro absoluto de início e término das palavras alinhadas.
- Erro mediano e percentil 95.
- Percentual de palavras alinhadas.
- Palavras sem timestamp.
- Sobreposições e lacunas suspeitas.
- Legibilidade e fidelidade de tradução.
- Validade estrutural e temporal do SRT.

### 9.4. Metas iniciais de sincronização

Para áudios controlados e casos homologados, metas de referência provisórias a validar na Fase 5, usando timestamps de palavras anotados manualmente:

- Erro mediano de início/fim de palavra: até 150 ms.
- Percentil 95 de erro: até 350 ms.
- Nenhum timestamp inválido ou fora da duração da mídia.
- Nenhuma palavra sem alinhamento ocultada silenciosamente.
- Toda anomalia relevante deve produzir alerta ou bloquear a publicação conforme severidade.

Essas metas são provisórias e deverão ser recalibradas com base na medição real, idioma, conteúdo e equipamento. Não representam garantia universal para ruído, música, fala simultânea ou transcrições incorretas.

### 9.5. Testes de interface

Automatizar, no mínimo:

- Clique duplo em Processar.
- Clique duplo em Cancelar.
- Confirmação e desistência de início.
- Confirmação e desistência de cancelamento.
- Bloqueio visual e funcional dos controles.
- Transição para estado de cancelamento.
- Falha em cada etapa.
- Conclusão e restauração dos controles.
- Expandir/recolher log enquanto processa.
- Atualizações sem congelamento da janela.
- Fechamento da janela durante trabalho ativo.
- Tentativa de iniciar segundo job.

### 9.6. Testes end-to-end

Executar o fluxo completo com:

1. Vídeo local PT-BR para PT-BR.
2. Vídeo local PT-BR para inglês.
3. Vídeo local em inglês para PT-BR.
4. Vídeo local em inglês para inglês.
5. Áudio local MP3.
6. Áudio local WAV.
7. Outros formatos homologados.
8. Vídeo do YouTube.
9. Arquivo longo.
10. Entrada inválida, corrompida, sem áudio ou interrompida.

Inspecionar o SRT em parser independente e reproduzi-lo com a mídia original em player de referência.

### 9.7. Ferramentas de qualidade

Avaliar e adotar um conjunto enxuto:

- pytest para testes.
- pytest-qt para testes da interface Qt.
- pytest-cov para cobertura.
- Ruff para lint e formatação.
- Verificações de tipos quando agregarem valor.
- CI para testes determinísticos e verificações estáticas.

A cobertura numérica não substitui critérios de comportamento e cenários de regressão.

## 10. Progresso, logs e métricas de execução

O pipeline deverá emitir eventos estruturados com, no mínimo:

- Identificador do job.
- Etapa.
- Estado.
- Timestamp do evento.
- Mensagem.
- Progresso quando mensurável.
- Total/processado quando disponível.
- Aviso ou erro associado.

Não somar percentuais arbitrários de etapas para fabricar uma barra aparentemente precisa. Quando uma etapa não informar progresso, exibir estado indeterminado com atividade e mensagens recentes.

A interface deverá receber atualizações sem polling agressivo. O log deverá ser útil para diagnóstico sem sobrecarregar o usuário com linhas repetitivas.

## 11. Dependências, instalação e distribuição

O repositório Legendar é a fonte de verdade dos requisitos de software. O ambiente local é um perfil de execução/homologação; não define sozinho quais bibliotecas, versões ou backends o produto pode suportar.

### 11.1. Governança

- `pyproject.toml` é o manifesto canônico das dependências diretas, faixas de versão, extras e grupos de desenvolvimento.
- `uv.lock` é o registro versionado da resolução universal exata de dependências transitivas, variantes PyTorch e marcadores de plataforma; toda instalação de validação deve usar `uv sync --locked`.
- `requirements.txt` foi removido na Fase 9 por ser um snapshot UTF-16 da baseline, sem relação com o manifesto atual. Consumidores que usam pip geram a lista com `uv export --locked`, conforme [INSTALACAO.md](INSTALACAO.md); nenhum segundo manifesto é versionado.
- Dependências diretas devem refletir contratos usados pelo próprio Legendar. Dependências transitivas devem ser resolvidas pelo gerenciador e registradas no lockfile, sem duplicação manual desnecessária.
- Utilizar faixas de versão com limites mínimos testados e limites máximos somente quando houver justificativa de compatibilidade. Fixações exatas ficam no lockfile, não no manifesto de requisitos.
- Separar dependências-base, perfis completos de runtime, recursos opcionais (como alinhamento) e ferramentas de desenvolvimento/teste/build.
- Para bibliotecas com variantes de hardware (PyTorch), selecionar explicitamente a origem dos wheels por perfil; não depender da escolha implícita do índice público.
- Nenhuma instalação ou atualização silenciosa de pacotes globais será feita pelo aplicativo.

### 11.2. Manifesto e baseline inicial

O `pyproject.toml` foi introduzido na Fase 0 com PySide6 como dependência-base e perfis completos de POC: `runtime-cpu` e `runtime-cu128`. Cada perfil inclui Whisper, yt-dlp, a variante correspondente do stack PyTorch e WhisperX, evitando que o alinhador seja instalado sem backend explícito. O macOS utiliza os wheels PyPI do PyTorch no perfil CPU e pode expor MPS no runtime quando o ambiente oferecer suporte. O perfil ROCm 7.2 não é oferecido nesta versão porque a matriz oficial disponível resolve PyTorch a partir de 2.11, incompatível com a faixa exigida pelo WhisperX estável 3.8.6 (`>=2.8,<2.9`).

A faixa inicial de Python é `>=3.10,<3.14`, determinada pela compatibilidade declarada pelo candidato WhisperX estável 3.8.6, e não pela versão instalada no computador-alvo. Essa faixa será ampliada quando a interseção das dependências críticas, os wheels e a CI demonstrarem suporte adicional.

A matriz, os comandos de instalação, os perfis, as justificativas, as dependências externas e a política de manutenção estão em [docs/MATRIZ_DEPENDENCIAS.md](MATRIZ_DEPENDENCIAS.md). Uma resolução experimental anterior feita apenas contra PyPI puxou bibliotecas CUDA/NVIDIA por padrão para Linux e foi descartada; a resolução agora usa índices explícitos para não confundir perfil CPU com GPU. O lock universal está versionado e validado por resolução. A CI executa instalação real/importação do perfil CPU e CUDA 12.8, além de uma POC de modelo PT-BR/EN; isso é evidência de compatibilidade inicial, não homologação completa do produto em todos os sistemas e hardwares.

### 11.3. Ferramentas externas

FFmpeg e ffprobe são dependências externas obrigatórias do pipeline de mídia, não pacotes Python. O instalador/preflight deverá localizá-los, validar suas versões e informar como instalá-los. O fluxo YouTube declara `yt-dlp-ejs` e requer um runtime JavaScript compatível; Deno é o runtime preferencial a identificar no preflight, com Node avaliado somente conforme suporte da versão do yt-dlp.

### 11.4. Perfis de hardware e plataforma

CPU deverá ser uma via de compatibilidade quando suportada pelos componentes. CUDA e MPS são perfis independentes selecionados segundo a compatibilidade oficial do PyTorch, do alinhador, dos drivers e do sistema operacional. O manifesto disponibiliza atualmente perfis CPU e CUDA 12.8; macOS usa os wheels PyPI do PyTorch e verifica MPS no runtime. ROCm permanece como possibilidade arquitetural, mas o perfil ROCm 7.2 não é declarado instalável enquanto o PyTorch disponível nesse índice (>=2.11) for incompatível com a faixa exigida pelo WhisperX estável 3.8.6 (>=2.8,<2.9). Perfis indisponíveis ou incompatíveis não serão apresentados como suportados. O projeto não instalará todos os backends indiscriminadamente nem inferirá suporte apenas pela presença de uma GPU.

O inventário do computador-alvo será usado para medir desempenho e validar um perfil concreto. Não poderá reduzir a matriz global do produto. Os sistemas operacionais e arquiteturas oficialmente suportados serão declarados somente depois de integração e CI comprovarem os fluxos GUI, mídia, Whisper e alinhamento.

### 11.5. Reprodutibilidade e qualidade

A Fase 0 gerou e validou a resolução lockada em ambiente isolado, confirmou a compatibilidade inicial dos wheels e executou a matriz do coletor/CLI em Python 3.10–3.13 × Ubuntu/Windows/macOS. O workflow #109 também instalou/importou os perfis CPU e CUDA 12.8, executou a prova FFmpeg/offset e o smoke benchmark WhisperX PT-BR/EN. Isso demonstra reprodutibilidade e compatibilidade inicial dos componentes avaliados; não equivale à homologação completa das dependências e fluxos do produto em todos os sistemas e hardwares. A fase de integração deverá separar testes com lockfile (reprodutibilidade) e testes de compatibilidade/atualização (faixas de versão).

Referências técnicas:

- Python Packaging User Guide: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
- Dependency Groups: https://packaging.python.org/en/latest/specifications/dependency-groups/
- uv universal resolution: https://docs.astral.sh/uv/concepts/resolution/
- PyTorch: https://docs.pytorch.org/get-started/locally/
- Whisper: https://github.com/openai/whisper
- WhisperX: https://github.com/m-bain/whisperX
- FFmpeg: https://ffmpeg.org/documentation.html
- yt-dlp: https://github.com/yt-dlp/yt-dlp
- PySide6: https://doc.qt.io/qtforpython/

Versões, licenças, wheels, modelos, requisitos de runtime e combinações de backend deverão ser conferidos e testados antes de serem declarados suportados.

## 12. Roadmap de execução

| Fase | Nome | Entregáveis principais | Critério de saída |
|---|---|---|---|
| 0 | Definições e prova técnica | Inventário, governança/lock, perfis CPU/CUDA, prova de mídia/offset, POC smoke PT-BR/EN e decisões de tradução/modelos | Direção técnica e contratos suficientes para iniciar Fase 1; limitações e validações humanas encaminhadas explicitamente às Fases 4, 5, 6 e 8 |
| 1 | Reestruturação arquitetural | Camadas, modelos de domínio, pipeline, estados, configurações, tratamento de erros, testes e CI | **Concluída e integrada à `main` pela PR #2 (squash, commit `de31ddd`):** arquitetura executável e testada; baseline legada caracterizada/preservada; CI Python 3.10–3.13 verde (196 testes por ambiente); critérios do [plano operacional da Fase 1](FASE_1_PLANO.md) aprovados |
| 2 | Interface profissional | Janela, identidade visual, diálogos, máquina de estados, workers simulados, progresso e log | **Concluída e integrada à `main` pela PR #3 (squash, commit `4129f0a`):** temas claro/escuro/sistema, confirmações seguras, proteção contra reentrância, preferências QSettings, acessibilidade, logs e progresso honesto; CI 4/4 em Python 3.10–3.13, 218 testes por ambiente, cobertura 88% |
| 3 | Entrada e preparação de mídia | YouTube, áudio/vídeo local, ffprobe, FFmpeg, faixas, normalização e temporários | **Concluída e integrada à `main` pela PR #4 (squash, commit `dfa440b`):** aquisição local/YouTube, inspeção, seleção de faixa e normalização; CI 4/4 em Python 3.10–3.13, 249 testes por ambiente, cobertura 87%, gates herdados aprovados |
| 4 | Reconhecimento Whisper | Adaptador local, detecção/seleção de idioma, perfis, cache, erros, worker e benchmark lexical | **Concluída e integrada pela PR #5 (squash, commit `2f975113`):** Whisper local PT-BR/EN, cache e worker; CI 4/4 Python 3.10–3.13 em push/PR e smoke CPU tiny/base/small com WER/CER/RTF publicados. Inventário e corpus representativo no computador-alvo permanecem como homologação de produto |
| 5 | Alinhamento temporal | WhisperX, janelas de busca, offsets, chunks, validação de palavra, diagnósticos e avaliação com fronteiras humanas | **Implementada e integrada pela PR #6** (squash `5c9a2ba`): alinhamento PT/EN, palavras não alinhadas explícitas, offsets globais, avaliador temporal, CI e smoke real aprovados. A precisão contra fronteiras humanas no computador-alvo continua gate de homologação do produto |
| 6 | Tradução, segmentação e SRT | Tradução, vínculo temporal, regras de leitura, writer e validator | **Concluída e integrada à `main` por squash (`d600283`):** segmentação de duas linhas de 42 caracteres, tradução local por cue com NLLB-200 distilled 600M, validação do trilho e publicação SRT atômica com roundtrip; 387 testes locais verdes e workflow `phase6-quality.yml` com matriz Python 3.10–3.13, 5/5 jobs verdes no push [#42951451587](https://github.com/anfalcir/legendar/actions/runs/42951451587). Qualidade tradutória e leitura em mídia real seguem como homologação de produto |
| 7 | Integração de ponta a ponta | GUI conectada ao pipeline, progresso real, cancelamento, logs e recuperação | **Concluída e integrada à `main` por squash:** a janela dispara o `SerialPipeline` real em `QThread`, consome eventos, bloqueia campos, cancela em ponto seguro, limpa o workspace e abre a pasta do SRT publicado; 39 testes de GUI offscreen verdes, suíte determinística completa verde e Ruff limpo. Critérios do [plano operacional da Fase 7](FASE_7_PLANO.md) atendidos |
| 8 | Testes e homologação | Unitários, integração, GUI, E2E, regressão e relatório | **Concluída e integrada à `main` por squash:** matriz E2E PT→PT, PT→EN, EN→PT e EN→EN, modos de falha e cancelamento, mídia real em seis formatos com FFmpeg, gate de cobertura de 85% e verificador de links; **443 testes aprovados e 86% de cobertura** na medição da fase (433 aprovados e 10 skips explícitos sem FFmpeg). A Fase 9 acrescentou os testes de documentação, totalizando **451**. Evidências e pendências humanas em [RELATORIO_FASE_8.md](RELATORIO_FASE_8.md) |
| 9 | Documentação e finalização | Guias, arquitetura, operação, instalação, decisões e revisão final | **Concluída e integrada à `main` por squash:** [ARQUITETURA.md](ARQUITETURA.md), [OPERACAO.md](OPERACAO.md), [INSTALACAO.md](INSTALACAO.md), [DECISOES.md](DECISOES.md), README revisado, `LICENSE` MIT, remoção do `requirements.txt` legado e verificação automática de links da documentação. Documentação coerente com código e instalação reproduzível |

A execução e as evidências das Fases 1–9 estão registradas em [ESTADO_ATUAL.md](ESTADO_ATUAL.md),
[FASE_1_PLANO.md](FASE_1_PLANO.md), [FASE_2_PLANO.md](FASE_2_PLANO.md), [FASE_3_PLANO.md](FASE_3_PLANO.md),
[FASE_4_PLANO.md](FASE_4_PLANO.md), [FASE_5_PLANO.md](FASE_5_PLANO.md), [FASE_6_PLANO.md](FASE_6_PLANO.md),
[FASE_7_PLANO.md](FASE_7_PLANO.md), [FASE_8_PLANO.md](FASE_8_PLANO.md) e [FASE_9_PLANO.md](FASE_9_PLANO.md),
com os handoffs correspondentes em [HANDOFF_FASE_1.md](HANDOFF_FASE_1.md) a [HANDOFF_FASE_8.md](HANDOFF_FASE_8.md)
e o encerramento em [HANDOFF_FASE_9.md](HANDOFF_FASE_9.md), além do
[relatório de testes e homologação](RELATORIO_FASE_8.md).
As Fases 0–9 estão concluídas e integradas à `main`; a homologação do usuário com mídia real
e hardware próprio é a única etapa restante.

### 12.1. Regras de execução das fases

- Uma fase por vez, sem avançar por mera conclusão de código.
- Cada fase terá escopo, entregáveis, testes, critérios de aceite e revisão.
- Mudanças de escopo serão registradas antes da execução.
- A documentação relacionada será atualizada junto com as alterações.
- Problemas críticos e decisões abertas deverão constar no documento de estado.
- A aprovação do usuário será o checkpoint para avançar para a fase seguinte.

## 13. Critérios globais de aceite

O projeto remodelado somente será considerado pronto quando:

- A interface for consistente, responsiva e visualmente refinada.
- O processamento pesado não bloquear a GUI.
- Cliques acidentais e tarefas duplicadas forem impedidos.
- Estados, desabilitação de controles e cancelamento forem confiáveis.
- YouTube e formatos locais homologados funcionarem.
- Whisper realizar a transcrição no idioma de origem.
- O alinhamento temporal tiver sido medido com dados de referência.
- Anomalias de alinhamento forem sinalizadas.
- EN e PT-BR forem produzidos conforme solicitado.
- Segmentação respeitar legibilidade e contexto.
- O SRT passar por validação estrutural e temporal.
- Arquivos temporários e cache forem isolados e limpos com segurança.
- Testes automatizados e end-to-end essenciais forem aprovados.
- Instalação e execução forem reproduzíveis.
- Documentação estiver completa e corresponder ao comportamento real.
- Dependências, modelos, licenças e dados transmitidos a serviços externos estiverem documentados.

**Situação após a Fase 9:** os critérios verificáveis por código, teste e CI estão
atendidos e registrados em [ESTADO_ATUAL.md](ESTADO_ATUAL.md) e
[RELATORIO_FASE_8.md](RELATORIO_FASE_8.md). Permanecem dependentes do usuário:
medição de alinhamento com fronteiras humanas, revisão da qualidade tradutória,
homologação do fluxo YouTube real, validação visual em monitor físico/sistema
padrão e empacotamento distribuível. Nenhum desses itens é apresentado como
concluído.

## 14. Decisões consolidadas e validações encaminhadas

| Tema | Decisão de saída da Fase 0 | Validação ou decisão restante |
|---|---|---|
| Alinhador primário | WhisperX estável 3.8.6 integrado à `main` pela Fase 5; smoke real CPU PT-BR/EN aprovado | Precisão temporal, cobertura e tolerância a casos difíceis ainda exigem corpus de pregações com fronteiras humanas e validação no computador-alvo |
| Alternativa | stable-ts não foi incluído como dependência nem como fallback automático | Reconsiderar somente se a homologação humana da Fase 5/8 mostrar limitação mensurável do alinhador primário |
| Tradução | Porta/adaptador independente; preservar original e não enviar áudio ao fornecedor. A Fase 6 escolheu NLLB-200 distilled 600M local via `transformers`, com pesos em `<models_dir>/nllb`, inferência no próprio computador e tradução por cue | Aprovar desempenho e qualidade PT↔EN em corpus autorizado de pregações; medir tempo de primeira carga, memória e comportamento no computador-alvo |
| Modelo Whisper | OpenAI Whisper local; perfil inicial `base`, com `tiny`, `small`, `medium`, `large` e `turbo` disponíveis | Comparar WER/CER/RTF e memória em corpus PT-BR/EN; validar no computador-alvo e em fala representativa antes de declarar recomendação |
| Normalização | WAV PCM signed 16-bit, mono, 16 kHz; conversão sintética e preservação de offset foram aprovadas | Homologar codecs, contêineres, streams, qualidade de áudio e fixtures reais na Fase 3 |
| Idiomas | PT-BR e EN passaram pelo smoke integrado de Whisper + WhisperX da Fase 5 | Não declarar precisão/homologação de produto antes de avaliar corpus humano e computador-alvo nas Fases 5/8 |
| Parâmetros SRT | Regras implementadas na Fase 6: duas linhas de 42 caracteres, 84 por cue, 1–7 s, pausa de 0,6 s e ~17 cps; validador reporta excessos sem truncar | Calibrar com leitura real em corpus de pregações e revisão humana na Fase 8 |
| Distribuição | Perfis CPU e CUDA 12.8 estão declarados; macOS usa wheels PyPI do perfil CPU e pode expor MPS conforme runtime | Definir plataformas/backends oficialmente suportados somente após homologação da aplicação integrada na Fase 8 |

A Fase 0 encerra as decisões estruturais necessárias para começar a arquitetura. Os itens da terceira coluna são validações de produto, dependem de evidências ou decisões de fornecedor e permanecem atribuídos às fases que os consomem; não são critérios ocultos para reabrir esta fase.

## 15. Política de manutenção da documentação

O documento ESTADO_ATUAL.md é a fonte operacional do progresso. Deve ser atualizado:

- Ao iniciar ou encerrar uma fase.
- Após cada checkpoint de aprovação.
- Quando uma decisão técnica mudar.
- Quando um teste relevante passar ou falhar.
- Quando surgir um bloqueio ou risco material.
- Quando uma funcionalidade for implementada, removida ou alterada.

Nenhuma tarefa será marcada como concluída sem evidência: teste, inspeção, comando executado ou validação documentada.

O plano mestre registra o destino e os critérios. O estado atual registra a realidade do repositório. Se houver divergência entre intenção e implementação, o estado atual deverá descrevê-la claramente e o plano deverá ser atualizado quando a mudança for aprovada.
