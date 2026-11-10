# Handoff técnico — Fase 3: entrada e preparação de mídia

- **Status:** implementação concluída; CI de push aprovada; integração por PR pendente
- **Branch:** `phase-3/media-ingestion`
- **Base:** `main` pós-Fase 2, commit `4129f0a906a04693502f298b71767605499e3f68`
- **Commit com CI verde:** `d93b268f84573de569f1e08b72ee73d59795288e`
- **Workflow:** [#42921552291](https://github.com/anfalcir/legendar/actions/runs/42921552291)
- **Limite:** esta fase prepara/inspeciona mídia; não implementa Whisper, alinhamento, tradução ou publicação SRT

## 1. Arquitetura implementada

### Fontes e inspeção

- Seletor local/YouTube na GUI, com validação de origem.
- `FfprobeInspector` mapeia streams, metadados, duração e offsets.
- Faixa default é preferida; a escolha manual usa o índice global do stream.
- Metadados do stream escolhido (título, idioma, codec, canais, sample rate, offset e proveniência) aparecem na interface.
- Inspeção prévia executada em uma QThread dedicada; o objeto executor é a própria thread. O token de cancelamento é thread-safe e o resultado retorna à GUI por sinais enfileirados.
- A inspeção é repetida pelo pipeline quando o job começa, evitando tratar metadados antigos como autoridade.

### Normalização e timeline

- `FfmpegAudioPreparer` extrai somente a faixa selecionada e gera WAV PCM s16le, mono, 16 kHz.
- O arquivo é produzido em caminho temporário exclusivo no diretório do destino, reaberto por ffprobe e validado antes da publicação.
- Publicação por hard-link atômico impede sobrescrita concorrente; o temporário é removido em sucesso, falha ou cancelamento.
- A mídia de origem não é alterada.
- `AudioAsset.timeline_start_seconds` e `timeline_offset_source` preservam separadamente o offset da fonte. O WAV não recebe o offset e o alinhador futuro não deve somá-lo novamente.
- Um timestamp absoluto de stream não é comparado diretamente com duração relativa do contêiner sem a origem da timeline. A regra foi coberta por teste de regressão.
- ffprobe/FFmpeg usam listas de argumentos, sem shell, timeout e encerramento controlado do subprocesso.

### YouTube e EJS

- Adaptador yt-dlp por API Python; hosts permitidos explicitamente, sem credenciais ou portas arbitrárias.
- Sem playlists; saída com prefixo reservado dentro do workspace; validação do caminho e do arquivo produzido.
- Progress hook só calcula percentual com bytes totais conhecidos; cancelamento no hook e timeout de socket.
- Preflight verifica yt-dlp e runtime EJS. Deno >=2.3 é preferido; Node.js >=22 é alternativa.
- O runtime escolhido e o caminho do executável são enviados explicitamente em `js_runtimes` para a API do yt-dlp. A simples presença de Node não é tratada como suporte se não estiver habilitado.
- Detalhes de erro não expõem a URL completa.

### Bootstrap e fronteira para próximas fases

- Bootstrap injeta ffprobe, FFmpeg e yt-dlp por portas do pipeline.
- Os motores de transcrição, alinhamento e publicação continuam como placeholders explícitos.
- A execução real pode concluir aquisição, inspeção e normalização, mas falha de forma honesta na etapa seguinte informando que Whisper será conectado na Fase 4; não sugere que gerou transcrição ou SRT.

## 2. Arquivos centrais

- `src/legendar/domain/entities/media.py`
- `src/legendar/infrastructure/media/ffprobe.py`
- `src/legendar/infrastructure/media/probe.py`
- `src/legendar/infrastructure/media/ffmpeg.py`
- `src/legendar/infrastructure/media/youtube.py`
- `src/legendar/infrastructure/media/tools.py`
- `src/legendar/application/pipeline/serial_pipeline.py`
- `src/legendar/bootstrap/app.py`
- `src/legendar/presentation/qt/main_window.py`
- `src/legendar/presentation/qt/workers/media_inspection_worker.py`
- `tests/unit/infrastructure/test_ffmpeg.py`
- `tests/unit/infrastructure/test_probe.py`
- `tests/unit/infrastructure/test_ffprobe_parser.py`
- `tests/unit/infrastructure/test_youtube.py`
- `tests/unit/test_bootstrap.py`
- `tests/integration/test_ffmpeg_media_ingestion.py`
- `tests/gui/test_main_window.py`
- `.github/workflows/phase3-quality.yml`

## 3. CI e testes

O workflow [#42921552291](https://github.com/anfalcir/legendar/actions/runs/42921552291) foi concluído com **4/4 jobs aprovados**:

| Python | Testes | Cobertura |
|---|---:|---:|
| 3.10 | 249 | 87% |
| 3.11 | 249 | 87% |
| 3.12 | 249 | 87% |
| 3.13 | 249 | 87% |

Cada job compila o código e os testes, executa a suíte completa com integração real sintética FFmpeg/ffprobe, confirma Ruff check e Ruff format. Cobertura por ambiente: 3.069 instruções (396 não cobertas); 97 arquivos já formatados.

Uma regressão encontrada durante a validação comparava `stream.start_time` diretamente com `format.duration`. Isso é inválido quando o stream possui timestamp absoluto e a duração é apenas a extensão relativa. A entidade preserva ambos sem fazer essa comparação incorreta; um teste específico impede que volte.

Também houve falha nativa no ciclo de vida Qt quando um QObject worker era destruído em um arranjo separado de QThread. A implementação final usa uma subclasse QThread dedicada, com a inspeção em `run()`, retorno por sinais enfileirados e cancelamento via token. A matriz final verde confirma que o teste de cancelamento não reproduziu o crash nos quatro ambientes.

### Limites de homologação

- Não foi feito download online real do YouTube na CI: o contrato do yt-dlp é testado sem rede para manter determinismo. A validação online depende de disponibilidade do conteúdo, EJS, runtime, versão e restrições do serviço.
- Fixtures sintéticas comprovam FFmpeg/ffprobe no runner, não todos os formatos de mídia do computador-alvo.
- Homologação de GUI física/HiDPI, outros sistemas e arquivos representativos do usuário segue na Fase 8.

## 4. Próximos passos

1. Abrir PR para `main`.
2. Aguardar a matriz de pull request e revisar o diff/checks.
3. Integrar por squash e confirmar o commit na `main`.
4. Atualizar o estado vivo com o SHA de merge.
5. Não iniciar a Fase 4 sem novo checkpoint explícito.

**A implementação está validada por CI de push, mas a Fase 3 só estará concluída/integrada depois do merge da PR.**
