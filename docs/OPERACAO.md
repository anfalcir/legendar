# Operação do Legendar

- **Público:** usuário que executa a aplicação e precisa entender estados, logs, cache, cancelamento e mensagens de erro.
- **Instalação:** [INSTALACAO.md](INSTALACAO.md). **Arquitetura:** [ARQUITETURA.md](ARQUITETURA.md).

## 1. Abrir a aplicação

```bash
PYTHONPATH=src uv run --locked --no-sync python -m legendar
```

O comando abre a janela principal. Nada é processado sem confirmação explícita.

## 2. Jornada na interface

1. **Origem da mídia:** escolha *Arquivo local* ou *YouTube*.
   - Arquivo local: use **Selecionar arquivo…** (MP4, MKV, MOV, WebM, M4A, MP3, WAV, FLAC, OGG, OPUS, AAC).
   - YouTube: cole a URL de um único vídeo que você tenha direito de processar.
2. **Faixas de áudio (opcional):** **Inspecionar faixas** roda ffprobe fora da thread da interface e permite escolher a faixa. Sem inspeção, a faixa padrão é usada.
3. **Idioma falado:** *Detectar automaticamente* ou idioma explícito.
4. **Idioma final:** PT-BR ou inglês. Marque **Traduzir a fala para o idioma final** quando forem diferentes.
5. **Destino:** caminho do SRT. A extensão é normalizada para `.srt`; sobrescrever exige confirmação.
6. **Gerar legenda:** revise o resumo (mídia, idiomas, destino) e confirme.
7. Acompanhe **Andamento do trabalho** e o painel **Atividade**; o log pode ser recolhido durante a execução.
8. Ao final, a barra de status mostra o caminho publicado e **Abrir pasta** fica disponível.

## 3. Estados exibidos

| Estado | Significado | Controles |
|---|---|---|
| Aguardando | pronto para iniciar | campos ativos, Gerar ativo quando o ambiente está pronto |
| Validando entrada | conferindo mídia, idiomas e destino | campos bloqueados, Cancelar ativo |
| Inspecionando / Preparando áudio | ffprobe e normalização | campos bloqueados, Cancelar ativo |
| Transcrevendo / Alinhando | Whisper e WhisperX | campos bloqueados, Cancelar ativo |
| Segmentando / Traduzindo | cues e NLLB | campos bloqueados, Cancelar ativo |
| Validando SRT | checagem estrutural | campos bloqueados, Cancelar ativo |
| Publicando | troca atômica do arquivo | campos bloqueados, cancelamento recusado |
| Concluído | SRT publicado | campos ativos, Abrir pasta habilitado |
| Cancelado | interrompido em ponto seguro | campos ativos |
| Falha | erro com categoria e mensagem | campos ativos para correção |

Progresso percentual só aparece quando a etapa informa métrica real; caso
contrário a barra fica indeterminada com o texto "sem percentual medido".

## 4. Cancelamento

- **Cancelar trabalho** pede confirmação e é desabilitado após o primeiro pedido aceito.
- O cancelamento é cooperativo: é observado entre etapas e entre lotes de tradução.
- Uma inferência em andamento termina antes de o job encerrar.
- Durante a publicação o pedido é recusado, porque a troca atômica já começou.
- Fechar a janela durante o trabalho solicita cancelamento e espera até 5 segundos.

## 5. Onde ficam os arquivos

| Conteúdo | Local padrão | Variável |
|---|---|---|
| Modelos (Whisper, WhisperX, NLLB) | `~/.cache/legendar/models` | `LEGENDAR_CACHE_DIR` |
| Logs rotativos | `~/.cache/legendar/logs/legendar.log` | `LEGENDAR_CACHE_DIR` |
| Temporários por job | `~/.cache/legendar/tmp/<job>` | `LEGENDAR_CACHE_DIR` |
| SRT publicado | caminho escolhido na janela (sugestão `~/Videos`) | `LEGENDAR_OUTPUT_DIR` |

Os temporários do job são removidos ao concluir, falhar ou cancelar. O cache de
modelos nunca é apagado por cancelamento.

## 6. Primeira execução

A primeira tradução baixa `facebook/nllb-200-distilled-600M` (≈2,4 GB) para o
cache; o primeiro alinhamento baixa o modelo WhisperX do idioma. Esse download
acontece uma vez e não é um travamento: o painel mostra a etapa em andamento
sem percentual quando a biblioteca não informa progresso.

## 7. Mensagens de erro e o que fazer

| Categoria | Mensagem típica | Ação recomendada |
|---|---|---|
| Entrada inválida | arquivo não encontrado, URL vazia | revise o caminho ou a URL |
| Mídia sem áudio ou não suportada | "A mídia selecionada não possui áudio." | escolha outra faixa/arquivo |
| Falha de download | vídeo privado, removido ou restrito | confirme acesso e tente novamente |
| Falha de FFmpeg/ffprobe | ferramenta ausente ou arquivo corrompido | instale FFmpeg/ffprobe e verifique o arquivo |
| Falha de modelo | transcrição vazia, modelo indisponível | confira o cache e a memória disponível |
| Idioma/alinhador não suportado | idioma final difere da fala sem tradução | marque a tradução ou ajuste o idioma |
| Alinhamento insuficiente | nenhuma palavra alinhada | revise a qualidade do áudio |
| Falha de tradução | idioma devolvido diferente do pedido | confira `LEGENDAR_TRANSLATE_MODEL` |
| Validação SRT | trilho vazio ou cue além do fim da mídia | reporte com o log da execução |
| Escrita/ espaço | não foi possível gravar | verifique permissão e espaço em disco |
| Cancelamento | "Trabalho cancelado." | nenhum SRT parcial é publicado |
| Erro inesperado | mensagem genérica + detalhe técnico no log | consulte `logs/legendar.log` |

Nenhum erro apresenta SRT incompleto como concluído: a publicação só ocorre
depois da validação e do roundtrip.


## 8. Preferências persistidas

A janela grava em `QSettings` (organização/produto `Legendar`):

- tema (claro, escuro ou sistema);
- idioma final preferido;
- pasta de saída;
- estado expandido ou recolhido do log;
- geometria da janela.

Nada sensível é gravado: o aplicativo não armazena credenciais, cookies ou
tokens, e não envia áudio para serviços externos.

## 9. YouTube

- Requer `yt-dlp`, `yt-dlp-ejs` e um runtime JavaScript compatível (Deno ≥ 2.3 ou Node ≥ 22) no `PATH`.
- O preflight da janela mostra o motivo quando o fluxo está indisponível.
- Downloads podem ser cancelados; os arquivos temporários ficam no workspace do job.
- Use apenas conteúdo que você tenha direito de acessar e processar.

## 10. Manutenção segura

```bash
# Conferir a integridade do lockfile
uv lock --check

# Reinstalar dependências exatamente como no lock
uv sync --locked --group dev --group phase0 --extra runtime-cpu
```

- Não apague `~/.cache/legendar/models` se quiser evitar novos downloads.
- Para liberar espaço, remova apenas `~/.cache/legendar/tmp` com a aplicação fechada.
- O log rotativo guarda até ~3 MB (`legendar.log` + 2 backups).

## 11. Diagnóstico rápido

```bash
# Ferramentas externas
ffmpeg -version | head -n 1
ffprobe -version | head -n 1

# Ambiente Python e perfis instalados
PYTHONPATH=src uv run --locked --no-sync python -c \
  "import importlib.util as u; print({n: bool(u.find_spec(n)) for n in ('torch','whisper','whisperx','transformers')})"

# Suíte de testes (sem rede e sem modelos)
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q
```

Se a janela abrir com "Verifique o ambiente", o painel de prontidão lista
exatamente qual ferramenta ou runtime falta.
