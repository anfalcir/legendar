# Handoff técnico — Fase 3: entrada e preparação de mídia

- **Status:** implementação desenvolvida; CI/revisão final pendentes
- **Branch:** `phase-3/media-ingestion`
- **Base:** `main` pós-Fase 2, commit `4129f0a906a04693502f298b71767605499e3f68`
- **PR:** ainda não aberta
- **Limite:** esta fase prepara/inspeciona mídia; não implementa Whisper, alinhamento, tradução ou publicação SRT

## 1. O que está implementado na branch

### Fontes e inspeção
- Seletor de arquivo local ou URL do YouTube.
- `FfprobeInspector` identifica faixas, metadados e offsets.
- Faixa default é preferida; escolha manual usa o índice global do stream.
- Metadados de título, idioma, codec, canais, taxa de amostragem e origem do offset aparecem na GUI.
- Inspeção prévia executada em worker/QThread, com cancelamento e repetição no início do pipeline.

### Normalização e timeline
- `FfmpegAudioPreparer` extrai apenas o stream selecionado e gera WAV PCM s16le, mono, 16 kHz.
- A saída é escrita em arquivo parcial, reaberta por ffprobe, validada e publicada com hard-link para impedir sobrescrita concorrente.
- O arquivo-fonte não é alterado.
- `AudioAsset.timeline_start_seconds` e `timeline_offset_source` mantêm separadamente o offset da fonte; o WAV não recebe uma soma duplicada desse offset.
- ffprobe/FFmpeg trabalham sem shell, possuem timeout e checkpoints de cancelamento, e não deixam o parcial após falhas/cancelamento.

### YouTube
- Adaptador yt-dlp por API Python.
- Hosts oficiais permitidos explicitamente; credenciais/portas não permitidas são rejeitadas.
- Sem playlist; formato de áudio preferencial; output dentro do workspace exclusivo.
- Progress hook somente informa percentual quando há bytes totais disponíveis.
- Cancelamento no hook e timeout de socket; limpeza de downloads parciais; URL omitida de detalhes de erro.
- GUI habilita YouTube somente quando yt-dlp e runtime EJS (Deno/Node) estão detectados.

### Bootstrap e fronteira para próximas fases
- Bootstrap injeta ffprobe, FFmpeg e yt-dlp nas portas do pipeline.
- Transcriber, aligner e publisher permanecem placeholders explícitos.
- Um job real pode concluir aquisição, inspeção e normalização, mas não deve sugerir que produziu transcrição ou SRT: a etapa seguinte informa claramente que Whisper será conectado na Fase 4.

## 2. Arquivos centrais

- `src/legendar/domain/entities/media.py`
- `src/legendar/infrastructure/media/ffprobe.py`
- `src/legendar/infrastructure/media/ffmpeg.py`
- `src/legendar/infrastructure/media/youtube.py`
- `src/legendar/application/ports/protocols.py`
- `src/legendar/application/pipeline/serial_pipeline.py`
- `src/legendar/bootstrap/app.py`
- `src/legendar/presentation/qt/main_window.py`
- `src/legendar/presentation/qt/workers/media_inspection_worker.py`
- `tests/unit/infrastructure/test_ffmpeg.py`
- `tests/unit/infrastructure/test_youtube.py`
- `tests/integration/test_ffmpeg_media_ingestion.py`
- `tests/gui/test_main_window.py`
- `.github/workflows/phase3-quality.yml`

## 3. Testes e CI

A suíte foi ampliada para 245 testes antes das últimas correções de formatação/ciclo de vida Qt. Em execuções anteriores, Python 3.10, 3.11 e 3.12 completaram 245 testes; os gates Ruff check passaram, mas Ruff format apontou nove arquivos que foram ajustados depois. Python 3.13 sofreu um segfault em `test_media_inspection_can_be_cancelled_without_blocking_the_window`, no ciclo de vida do worker Qt; o worker passou a chamar `deleteLater` na própria thread ao emitir `finished`.

O último workflow disponível para o snapshot atualizado é [#42916191288](https://github.com/anfalcir/legendar/actions/runs/42916191288), ainda pendente/sem jobs atribuídos. Portanto, ainda não há evidência verde da matriz final 3.10–3.13 para o código atualizado.

## 4. Limites e riscos conhecidos

1. O YouTube depende da disponibilidade do conteúdo, das mudanças do YouTube, do yt-dlp/EJS e de runtime externo; não prometer suporte a toda URL/DRM.
2. Os testes do yt-dlp são de contrato com doubles; não fazem download real/rede. A homologação com URL real deve ser uma validação manual controlada, sem ser condição para testes determinísticos.
3. A integração real FFmpeg/ffprobe usa mídia sintética criada no runner; não substitui homologação de codecs/contêineres de arquivos reais do computador-alvo.
4. Offset temporal foi preservado no domínio e comprovado sinteticamente. A aplicação do offset em timestamps globais de transcrição/alinhamento pertence às Fases 4/5; não somá-lo no WAV e de novo no alinhador.
5. Whisper/WhisperX, download de modelos, transcrição, alinhamento, tradução, segmentação, SRT final e revisão visual da experiência completa seguem fora do escopo.

## 5. Próximos passos obrigatórios

1. Verificar/obter execução CI válida para o snapshot atual (Python 3.10–3.13).
2. Corrigir falhas do workflow sem reduzir escopo de testes nem enfraquecer Ruff.
3. Fazer revisão técnica de segurança e ciclo de vida Qt, confirmar cleanup/atomicidade.
4. Marcar os critérios de aceite somente com evidências.
5. Sincronizar README, roadmap, estado e este handoff no snapshot final.
6. Abrir PR para `main`, obter CI verde e revisão; só declarar a Fase 3 concluída depois do merge squash confirmado.

**Não iniciar a Fase 4 nesta branch.** O responsável deverá aprovar explicitamente a próxima fase após a integração da Fase 3.
