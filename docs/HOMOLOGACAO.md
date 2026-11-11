# Homologação do Legendar — roteiro prático

- **Para quem:** você, no seu computador, com mídia real.
- **Para quê:** fechar os critérios que nenhum teste automático decide — sincronia, qualidade da tradução, desempenho e conforto da interface.
- **Tempo:** ~2 h de trabalho, mais o download inicial de modelos (~3 GB).
- **Contexto:** [OPERACAO.md](OPERACAO.md) explica estados e erros; [INSTALACAO.md](INSTALACAO.md) cobre perfis de hardware.

## 0. Preparar o ambiente (uma vez)

Estado medido nesta máquina: sem GPU NVIDIA, Node 22 presente, FFmpeg só em
`./ffmpeg/bin` (fora do `PATH`) e perfis de runtime ainda **não** instalados.

```bash
cd ~/Documentos/Codes/legendar

# 1) Perfis de execução (≈3 GB de download; sem GPU use runtime-cpu)
uv sync --locked --group dev --group phase0 --extra runtime-cpu

# 2) FFmpeg/ffprobe no PATH (já existe uma cópia local no repositório)
export PATH="$PWD/ffmpeg/bin:$PATH"     # ou: sudo apt-get install -y ffmpeg

# 3) Conferir as ferramentas e as bibliotecas
ffmpeg -version | head -n 1
ffprobe -version | head -n 1
uv run --locked --no-sync python -c "import importlib.util as u; print({n: bool(u.find_spec(n)) for n in ('torch','whisper','whisperx','transformers','yt_dlp')})"
```

Espere `True` nos cinco nomes. O modelo de transcrição padrão é `base`; para
mídia real use `export LEGENDAR_WHISPER_MODEL=small` (ou `medium`) na sessão do
terminal antes de abrir a aplicação.

## 1. Abrir o sistema

```bash
cd ~/Documentos/Codes/legendar
export PATH="$PWD/ffmpeg/bin:$PATH"
export LEGENDAR_WHISPER_MODEL=small
PYTHONPATH=src uv run --locked --no-sync python -m legendar
```

**Observe na abertura**

- janela única com a pílula de estado no topo e o rodapé de prontidão;
- rodapé verde = pronto; âmbar = falta algo, e a frase diz exatamente o quê;
- **Traduzir a fala para o idioma final** cinza = tradução indisponível (o tooltip diz por quê);
- destino sugerido já preenchido (padrão `~/Videos`).

Se a janela não abrir: `tail -40 ~/.cache/legendar/logs/legendar.log`.

## 2. Teste A — PT-BR para PT-BR (2 a 5 min de áudio)

1. **Origem da mídia:** *Arquivo local* → **Selecionar arquivo…**.
2. Opcional: **Inspecionar faixas** e escolha a faixa de áudio certa.
3. **Idioma falado:** Português (BR). **Idioma final:** Português (BR). Tradução desmarcada.
4. **Destino:** confirme o caminho `.srt`.
5. **Gerar legenda →** → revise o resumo → **Iniciar processamento**.

**Observe**

- a sequência de etapas: preparar áudio → transcrever → alinhar → segmentar → validar SRT → publicar;
- o percentual só aparece quando existe medida real; "sem percentual medido" é esperado em transcrição e alinhamento;
- os campos bloqueiam durante o trabalho e o **Cancelar trabalho** fica ativo;
- no fim: caminho publicado na barra de status e **Abrir pasta** habilitado.

**Anote:** tempo total e tempo por etapa.

## 3. Conferir o SRT no player (insubstituível)

```bash
vlc --sub-file="$HOME/Videos/<nome>.srt" "$HOME/Videos/<nome>.mp4"
```

**Observe**

- a fala aparece sincronizada, sem legenda adiantada ou atrasada de forma sistemática;
- no máximo 2 linhas por cue, linhas de até 42 caracteres, nenhuma cue passando de 7 s;
- acentuação correta (UTF-8), sem sobreposição de cues e sem cue depois do fim do vídeo;
- nomes próprios, números, referências bíblicas e termos técnicos.

**Anote:** 3 trechos com o tempo do vídeo e o tempo que a legenda mostra. Essa é
a medida que calibra a meta de sincronia (seção 9.4 do plano mestre).

## 4. Teste B — PT-BR para inglês

Mesma mídia do Teste A; **Idioma final: Inglês** e marque **Traduzir a fala para
o idioma final**.

**Observe:** a primeira execução baixa o NLLB-200 distilled (~2,4 GB) — a etapa
fica sem percentual, isso é download, não travamento. Depois, revise: os tempos
continuam idênticos aos do Teste A (a tradução não move cues), nomes e números
preservados, frases completas (sem corte no meio da ideia).

## 5. Teste C — inglês para PT-BR e detecção automática

1. Mídia com fala em inglês → **Idioma falado: Inglês**, **final: Português (BR)**, tradução marcada.
2. Repita uma vez com **Idioma falado: Detectar automaticamente** e confirme que o resultado não degrada.

## 6. Teste D — cancelamento

Em três momentos distintos (baixar, transcrever, traduzir): **Cancelar trabalho** → confirmar.

**Observe:** "Cancelando em um ponto seguro…", o job encerra em segundos, **nenhum
SRT parcial** aparece no destino, os campos voltam a ficar ativos e
`~/.cache/legendar/tmp` fica sem a pasta do job. Fechar a janela durante o
trabalho também pede cancelamento.

## 7. Teste E — YouTube

*YouTube* → cole a URL de um vídeo curto que você tenha direito de processar →
**Gerar legenda**. Se o preflight indicar indisponível, o motivo aparece no
rodapé (aqui: Node 22 já atende; falta apenas `yt-dlp`, que vem do perfil).

## 8. Teste F — pregação longa (desempenho)

Uma mídia de 30–60 min, com a aplicação aberta e o monitor do sistema visível.

**Observe e anote:** tempo total e por etapa, RAM máxima, uso de CPU,
temperatura, se a janela continua respondendo (rolar o log, mover a janela) e se
a última cue termina coerente com o fim da mídia. Registre também o hardware
(CPU, RAM, GPU) e o modelo usado.

## 9. Teste G — interface e acessibilidade

- **Preferências:** tema (sistema, claro, escuro), idioma final padrão, pasta padrão, log expandido — feche e reabra para confirmar que persistem.
- Escala do sistema em 125% e 150% (HiDPI): nada cortado, botões alcançáveis.
- Teclado: `Tab` percorre os campos na ordem lógica, `Enter` aciona **Gerar legenda**, `Esc` fecha diálogos.
- Redimensionar a janela para o mínimo: o conteúdo rola em vez de sobrepor.

## 10. Teste H — erros esperados

| Induzir | Mensagem esperada |
|---|---|
| Renomear/mover o arquivo depois de selecionar | entrada inválida, campo volta a ficar ativo |
| Vídeo sem faixa de áudio | "A mídia selecionada não possui áudio." |
| Destino em pasta sem permissão | falha de escrita, nenhum arquivo publicado |
| Destino já existente | segunda confirmação antes de sobrescrever |

## 11. Como registrar

Devolva esta tabela preenchida (ou só o que divergir):

| Teste | Resultado | Tempo | Observações |
|---|---|---|---|
| A — PT→PT curto | | | |
| SRT no player | | | |
| B — PT→EN | | | |
| C — EN→PT / automático | | | |
| D — cancelamento (3 pontos) | | | |
| E — YouTube | | | |
| F — pregação longa | | | |
| G — interface/HiDPI | | | |
| H — erros | | | |

## 12. O que não é bug

- Etapas sem percentual: transcrição, alinhamento e download não informam progresso medido.
- Primeira execução lenta: download de modelos no cache (`~/.cache/legendar/models`).
- Cancelamento demora alguns segundos: a inferência em andamento termina antes.
- **Publicando** recusa cancelamento: a troca atômica já começou (ponto de não retorno).
- Modelo `base` erra mais em áudio ruidoso: troque para `small`/`medium` e repita.

## 13. Quando algo falha

1. Categoria e mensagem na barra de status.
2. Detalhe técnico em `~/.cache/legendar/logs/legendar.log` (rotativo, ~3 MB).
3. Me envie: a categoria, o trecho do log e o arquivo problemático (ou as
   características dele: duração, contêiner, codec, taxa de amostragem).
