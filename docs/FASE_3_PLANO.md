# Plano operacional — Fase 3: Entrada e preparação de mídia

- **Status:** concluída, validada e integrada à `main` pela PR #4 (squash)
- **Branch de implementação:** `phase-3/media-ingestion` (integrada)
- **Base de implementação:** `main` pós-Fase 2, commit `4129f0a906a04693502f298b71767605499e3f68`
- **Escopo:** aquisição de fonte, inspeção, seleção de faixa, normalização de áudio e isolamento/limpeza dos artefatos de mídia
- **Limites:** sem Whisper/WhisperX, transcrição, alinhamento, tradução ou publicação SRT final

## 1. Objetivo

Implementar os fluxos reais de entrada previstos no roadmap: arquivos locais de áudio/vídeo e URLs do YouTube. Inspecionar contêineres e streams com ffprobe, selecionar a faixa de áudio correta, normalizar para WAV PCM signed 16-bit mono/16 kHz, preservar separadamente o offset da faixa original e manter mídia baixada/áudio normalizado no workspace exclusivo do job.

A GUI inicia inspeções fora da thread principal, permite selecionar uma faixa local quando há múltiplas faixas e apresenta estados de prontidão e erros honestos. A Fase 3 prepara o áudio; não promete transcrição ou SRT.

## 2. Entregas

1. **Fontes:** seletor explícito para arquivo local ou URL de vídeo individual do YouTube; validação do caminho, URL, host, credenciais e porta.
2. **YouTube:** adaptador yt-dlp por API Python, sem shell; rejeita playlists, limita saída ao workspace do job, aplica timeout/retries e hooks de progresso/cancelamento.
3. **Runtime EJS:** preflight valida yt-dlp e runtime JS compatível; prefere Deno >=2.3 e aceita Node.js >=22 como alternativa. O runtime escolhido e seu caminho são configurados explicitamente no yt-dlp.
4. **Inspeção:** ffprobe identifica contêiner, duração quando disponível, streams de áudio/vídeo, codec, canais, sample rate, idioma, título, disposição default e offset.
5. **Seleção de faixa:** prefere a faixa marcada como default; respeita seleção explícita pelo índice global do stream e rejeita índices inexistentes/não-áudio.
6. **Normalização:** FFmpeg extrai somente a faixa selecionada e gera WAV PCM s16le, mono, 16 kHz. Não altera a fonte.
7. **Timeline:** preserva `stream.start_time`; se ausente, deriva `start_pts * time_base`; depois usa `format.start_time` como fallback identificado; zero somente quando não há timestamp. A duração relativa do contêiner não é comparada cegamente com um timestamp absoluto do stream.
8. **Validação/publicação:** reabre o WAV via ffprobe e valida codec, sample rate, canais e duração positiva. A gravação temporária ocorre no mesmo diretório do destino e a publicação por hard-link atômico falha quando o destino já existe.
9. **Cancelamento/timeout:** ffprobe e FFmpeg são executados sem shell, com timeout e encerramento controlado; yt-dlp verifica o token nos hooks e usa timeout de socket. Falhas/cancelamentos limpam artefatos parciais.
10. **Workspace:** mídia baixada, WAV e temporários ficam no diretório isolado do job. A limpeza valida a raiz e não remove o cache de modelos nem a mídia de origem.
11. **GUI:** inspeção prévia em QThread dedicada, seleção das faixas locais, metadados e offset visíveis, cancelamento cooperativo e bloqueios enquanto há trabalho.
12. **CI/testes:** testes unitários sem rede, contrato yt-dlp com doubles, integração sintética com FFmpeg/ffprobe reais, matriz Python 3.10–3.13 e Ruff/format.
13. **Documentação:** README, roadmap, estado atual, plano operacional e handoff sincronizados com a implementação e evidências.

## 3. Fora do escopo (fases posteriores)

- Whisper/WhisperX concretos, download de modelos, transcrição e detecção automática do idioma.
- Alinhamento por palavra, VAD e aplicação dos offsets à timeline final.
- Segmentação de legendas, tradução, geração e publicação SRT.
- Prometer compatibilidade com toda URL, DRM, contêiner ou codec existente.
- Homologação final em hardware/HiDPI e em todos os sistemas operacionais (gate global da Fase 8).

## 4. Critérios de aceite

- [x] Arquivo local e YouTube são fontes distintas e validadas; processos não usam shell.
- [x] yt-dlp rejeita playlists e restringe os artefatos ao workspace.
- [x] Progresso do download só é percentual quando o tamanho total está disponível.
- [x] ffprobe identifica streams e metadados; a faixa default e a escolha explícita são respeitadas.
- [x] Offset e proveniência são derivados/preservados; timestamp absoluto não é confundido com duração relativa.
- [x] FFmpeg gera WAV PCM s16le mono/16 kHz e o resultado é revalidado por ffprobe.
- [x] Fonte original é preservada; temporários são removidos após sucesso, falha ou cancelamento.
- [x] Cancelamento/timeout encerram processos ou são observados em checkpoints.
- [x] Workspace isolado; limpeza não remove cache nem fonte.
- [x] GUI executa inspeção fora da thread principal e permite escolher entre faixas locais.
- [x] Testes offline e integração sintética real; CI Python 3.10–3.13 aprovada.
- [x] README, roadmap, estado atual e handoff descrevem a implementação sem prometer funções futuras.

## 5. Evidência de validação

Workflow push: [#42921552291](https://github.com/anfalcir/legendar/actions/runs/42921552291), no commit validado `d93b268f84573de569f1e08b72ee73d59795288e`.

| Ambiente | Resultado | Testes | Cobertura | Qualidade |
|---|---:|---:|---:|---|
| Python 3.10 / Ubuntu + FFmpeg | aprovado | 249 | 87% | Ruff check e format aprovados |
| Python 3.11 / Ubuntu + FFmpeg | aprovado | 249 | 87% | Ruff check e format aprovados |
| Python 3.12 / Ubuntu + FFmpeg | aprovado | 249 | 87% | Ruff check e format aprovados |
| Python 3.13 / Ubuntu + FFmpeg | aprovado | 249 | 87% | Ruff check e format aprovados |

Cobertura por ambiente: 3.069 instruções, 396 não cobertas. Formatação: 97 arquivos verificados. O workflow compila `src/legendar` e `tests`, roda a suíte integral com Qt offscreen e fixtures sintéticas que executam FFmpeg/ffprobe reais.

### Limites da evidência

- O downloader YouTube usa testes de contrato offline com doubles; não foi realizado download de rede real na CI. A disponibilidade efetiva depende do YouTube, yt-dlp, do pacote yt-dlp-ejs e do runtime EJS no computador.
- Os testes FFmpeg/ffprobe geram mídia sintética e não equivalem à homologação de todo codec/contêiner presente nos arquivos do usuário.
- Homologação visual em monitor/HiDPI e plataformas adicionais pertence à Fase 8.

## 6. Integração concluída

- **PR:** [#4 — feat(phase-3): implement media ingestion and audio preparation](https://github.com/anfalcir/legendar/pull/4)
- **Estado:** closed / merged por squash em 10/11/2026.
- **Commit de integração:** `dfa440b39e7623356388c774834e23ee53fc1d09`.
- **CI da PR:** Fase 3 [#42921987927](https://github.com/anfalcir/legendar/actions/runs/42921987927) — 4/4; Fase 1 [#42921987910](https://github.com/anfalcir/legendar/actions/runs/42921987910) — 4/4; Fase 0 [#42921987820](https://github.com/anfalcir/legendar/actions/runs/42921987820) — todos os 14 jobs executados aprovados, com benchmark WhisperX e smoke CUDA pulados por serem exclusivos de push.
- **CI de push da Fase 3:** [#42921980451](https://github.com/anfalcir/legendar/actions/runs/42921980451) — 4/4; matriz anterior [#42921552291](https://github.com/anfalcir/legendar/actions/runs/42921552291) também 4/4.

A Fase 3 está concluída e integrada à `main`. A Fase 4 não foi iniciada; seu início exige checkpoint explícito do usuário.
