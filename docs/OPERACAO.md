# Operação do Legendar

- **Público:** usuário que executa a aplicação e precisa entender estados, logs, cache, cancelamento e mensagens de erro.
- **Instalação:** [INSTALACAO.md](INSTALACAO.md).
- **Arquitetura:** [ARQUITETURA.md](ARQUITETURA.md).
- **Plano de qualidade e desempenho:** [PLANO_CORRECAO_MELHORIA.md](PLANO_CORRECAO_MELHORIA.md).

## 1. Abrir a aplicação

```bash
PYTHONPATH=src uv run --locked --no-sync python -m legendar
```

O comando abre a janela principal. Nada é processado sem confirmação explícita. Não use `python main.py` para operar a arquitetura nova: esse arquivo pertence à aplicação legada preservada como baseline.

## 2. Jornada na interface

1. **Origem:** escolha *Arquivo de mídia*, *Arquivo SRT* ou *YouTube*.
2. **Mídia:** em arquivo local, inspecione faixas quando necessário; no YouTube, o áudio é obtido automaticamente.
3. **SRT existente:** escolha *Arquivo SRT* e selecione o arquivo .srt de origem. Informe obrigatoriamente o idioma atual; o formato SRT não contém metadados confiáveis de idioma.
4. **Idioma final e tradução:** escolha PT-BR ou inglês e marque a tradução quando origem e destino forem diferentes.
5. **Destino:** selecione outro caminho SRT. O arquivo de origem nunca pode ser sobrescrito.
6. **Gerar legenda:** revise o resumo e confirme.
7. Acompanhe **Andamento do trabalho** e **Atividade**; o log pode ser recolhido.
8. Ao final, abra a pasta de destino.

**Modo Arquivo SRT:** lê as cues existentes, traduz diretamente o texto e publica outro SRT preservando os timestamps. Não executa inspeção de mídia, FFmpeg, Whisper ou WhisperX.

### 2.1. Preferências de tradução

- TranslateGemma 4B é o novo motor local disponível e deve ser selecionado para a homologação da Fase 8.1. NLLB-200 permanece temporariamente selecionável como baseline legado; o Gemini Developer API é uma alternativa remota explícita. A preferência atualmente inicializa em NLLB para preservar a configuração legada até a homologação real.
- Selecione o backend em **Preferências**. Para validar o novo motor, selecione **TranslateGemma 4B (local)**. A escolha é persistida localmente e aplicada aos próximos trabalhos, sem reiniciar a aplicação.
- Para usar Gemini, configure a chave API no próprio painel de Preferências. É possível substituir ou remover a chave por ali.
- A chave é armazenada em arquivo local privado, fora do QSettings, logs e relatórios de desempenho. Não a compartilhe nem a coloque no repositório.
- Ao selecionar Gemini, o texto das cues é enviado à API externa do Google para tradução. Use essa opção somente quando estiver de acordo com esse fluxo de dados e houver conectividade.
- Não existe fallback silencioso entre Gemini e NLLB: escolha/configuração inválida deve ser corrigida explicitamente.

## 3. Estados exibidos

| Estado | Significado | Controles |
|---|---|---|
| Aguardando | pronto para iniciar | campos ativos |
| Validando entrada | conferindo mídia, idioma e destino | campos bloqueados |
| Inspecionando / Preparando áudio | ffprobe e normalização | cancelar ativo |
| Transcrevendo / Alinhando | Whisper e WhisperX | cancelar ativo |
| Segmentando / Traduzindo | cues e backend escolhido (TranslateGemma, NLLB legado ou Gemini) | cancelar ativo |
| Validando SRT | checagem estrutural/editorial atual | cancelar ativo |
| Publicando | troca atômica do arquivo | cancelamento recusado |
| Concluído | SRT publicado | abrir pasta |
| Cancelado | interrompido em ponto seguro | campos ativos |
| Falha | erro com categoria e mensagem | campos ativos |

Percentual só aparece quando existe medida real. Quando não existe, a interface mostra o relógio de etapa sem inventar porcentagem. Esse relógio informa tempo decorrido da etapa; não substitui o benchmark estruturado por CPU/RAM e mediana de execuções planejado em [PLANO_CORRECAO_MELHORIA.md](PLANO_CORRECAO_MELHORIA.md).

## 4. Cancelamento

- **Cancelar trabalho** pede confirmação e é desabilitado após o primeiro pedido aceito.
- O cancelamento é cooperativo e observado entre etapas/lotes.
- Uma inferência em andamento termina antes de o job encerrar.
- Durante a publicação o pedido é recusado, pois a troca atômica já começou.
- Fechar a janela durante o trabalho solicita cancelamento.

## 5. Onde ficam os arquivos

| Conteúdo | Local padrão | Variável |
|---|---|---|
| Modelos | `~/.cache/legendar/models` | `LEGENDAR_CACHE_DIR` |
| Logs rotativos | `~/.cache/legendar/logs/legendar.log` | `LEGENDAR_CACHE_DIR` |
| Temporários por job | `~/.cache/legendar/tmp/<job-id>` | `LEGENDAR_CACHE_DIR` |
| Saída sugerida | `~/Videos` | `LEGENDAR_OUTPUT_DIR` |

O cache dos modelos não é apagado ao cancelar um job. Somente o workspace temporário do job deve ser limpo.

## 6. Diagnóstico

1. Confira a mensagem persistente no topo da janela.
2. Consulte o fim de `~/.cache/legendar/logs/legendar.log`.
3. Verifique FFmpeg/ffprobe e os perfis Python sincronizados.
4. Não apague manualmente cache de modelos durante o processamento.
5. Para problemas de qualidade do SRT, registre a etapa, trecho/tempo da mídia e diagnóstico; não conclua que CI verde comprova qualidade audiovisual.

### 6.1. Relatórios de desempenho da Fase 1

A partir da versão instrumentada, cada job gera automaticamente um relatório JSON local em:

```text
~/.cache/legendar/logs/performance/job-<job-id>.json
```

O diretório é privado e os arquivos são gravados com permissão `0600`. O relatório contém somente duração, contagens, recursos do equipamento, versões e configuração técnica. Não contém mídia, transcrição, conteúdo SRT, URL, caminho da mídia ou credenciais; ele não é enviado para nenhum serviço externo.

Para consultar os últimos jobs:

```bash
uv run --locked --no-sync python scripts/phase1_performance_summary.py --last 10
```

O resumo apresenta tempo e RTF por etapa, estado de carga dos modelos (`cold`, `warm` ou `unused`) e métricas do backend de tradução quando disponíveis. Os relatórios antigos podem conter métricas específicas do NLLB. Uma execução fria carrega o modelo sob demanda; a carga e eventual download são medidos separadamente da inferência.

### Protocolo prático para a mídia de 37 minutos

1. Atualize o projeto para a `main` que contém a PR #8 e abra o Legendar normalmente.
2. Gere o inventário atual do equipamento, na raiz do repositório:

   ```bash
   uv run --locked --no-sync python scripts/phase0_inventory.py --probe-torch --output phase1-inventory.json
   ```

3. Feche e reabra o Legendar antes da rodada fria. Execute o áudio de referência com o idioma, a opção de tradução e o mesmo modelo/configuração usados na execução original. A primeira execução registra a carga sob demanda dos modelos (e eventual acesso ao cache).
4. Sem fechar o aplicativo, execute o mesmo arquivo mais três vezes. Como os adaptadores permanecem carregados na instância do aplicativo, essas rodadas serão quentes.
5. Não altere arquivo, idioma, tradução, modelo, cache ou equipamento entre as quatro rodadas. Evite tarefas pesadas paralelas.
6. Consulte os resultados:

   ```bash
   uv run --locked --no-sync python scripts/phase1_performance_summary.py --last 10
   ```

O relatório de cada job fica em `~/.cache/legendar/logs/performance/`. Envie os JSONs dessas quatro execuções (e, se possível, o inventário) para análise. Eles não incluem áudio, transcrição, texto SRT, URL ou caminho pessoal do arquivo. O inventário também não contém conteúdo de mídia; ainda assim, compartilhe-o apenas se estiver confortável em revelar o modelo de CPU/GPU, RAM e versões do ambiente.

Evite comparar uma execução fria com uma quente como se fossem equivalentes. A carga de modelo é exibida separadamente da inferência; para identificar o gargalo de uso contínuo, considere principalmente as três execuções quentes.

Consulte [homologação](HOMOLOGACAO.md) e [estado atual](ESTADO_ATUAL.md).
