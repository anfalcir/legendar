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

1. **Origem da mídia:** escolha *Arquivo local* ou *YouTube*.
2. **Faixas de áudio:** inspecione e selecione a faixa correta quando necessário.
3. **Idioma falado:** detectar automaticamente ou escolher explicitamente.
4. **Idioma final:** PT-BR ou inglês. Habilite tradução quando origem e destino forem diferentes.
5. **Destino:** selecione o caminho do SRT; sobrescrita exige confirmação.
6. **Gerar legenda:** revise o resumo e confirme.
7. Acompanhe **Andamento do trabalho** e **Atividade**; o log pode ser recolhido.
8. Ao final, abra a pasta de destino.

## 3. Estados exibidos

| Estado | Significado | Controles |
|---|---|---|
| Aguardando | pronto para iniciar | campos ativos |
| Validando entrada | conferindo mídia, idioma e destino | campos bloqueados |
| Inspecionando / Preparando áudio | ffprobe e normalização | cancelar ativo |
| Transcrevendo / Alinhando | Whisper e WhisperX | cancelar ativo |
| Segmentando / Traduzindo | cues e NLLB | cancelar ativo |
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

Consulte [homologação](HOMOLOGACAO.md) e [estado atual](ESTADO_ATUAL.md).
