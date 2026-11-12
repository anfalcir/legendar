# Decisões técnicas consolidadas

- **Escopo:** escolhas que afetam contrato, dependências, formato de saída, testes ou operação.
- **Regra:** mudar uma decisão exige atualizar este arquivo, os testes correspondentes e o [estado atual](ESTADO_ATUAL.md).
- **Plano de evolução:** hipóteses ainda não aprovadas estão separadas das decisões vigentes no final deste documento.

| # | Tema | Decisão | Consequência |
|---|---|---|---|
| 1 | Tradução atual | NLLB-200 distilled 600M local, por cue, atrás da porta `Translator` | nenhum texto sai do computador; pesos baixados para o cache |
| 2 | Mecanismo de tradução | Tokenizador SentencePiece, origem `por_Latn`/`eng_Latn`, destino por `forced_bos_token_id` | dependências `transformers` + `sentencepiece` diretas |
| 3 | Escopo de idiomas | Somente PT-BR e inglês | idiomas fora da matriz são recusados |
| 4 | Reconhecimento atual | Whisper local no idioma de origem; não usar tarefa de tradução do Whisper | timestamps do reconhecimento são aproximados até o alinhamento |
| 5 | Alinhamento | WhisperX 3.8.6 como alinhador primário atual; stable-ts não é fallback | trocar exige avaliação em corpus anotado |
| 6 | Layout atual | Duas linhas de 42 caracteres, 84 por cue, 1–7 s, pausa de 0,6 s, ~17 CPS | limite editorial atual; plano novo deve validar política e exceções |
| 7 | Tradução e tempo | Tradução reescreve texto preservando `TimeRange` e relação 1:1 por cue | tempo não é derivado de contagem de palavras traduzidas |
| 8 | Validação atual | Falha estrutural bloqueia publicação; risco de leitura ainda pode ser aviso | o novo gate editorial será especificado e testado antes de adotar thresholds |
| 9 | Publicação | Arquivo temporário + `validate_roundtrip` + troca atômica | arquivo anterior permanece intacto em falha |
| 10 | Cancelamento | Cooperativo por token; `PUBLISHING` é ponto de não retorno | inferência em andamento termina antes do encerramento |
| 11 | Threads | `QThread` + sinais enfileirados; sem `processEvents` nem sleeps artificiais | widgets não são tocados fora da thread da interface |
| 12 | Estado | `StateMachine` é autoridade das transições; controlador emite um evento terminal | GUI renderiza snapshot |
| 13 | Arquitetura | Layout `src`, camadas `domain/application/infrastructure/presentation/bootstrap` | importações proibidas falham nos testes |
| 14 | Empacotamento Python | `[tool.uv] package = false`; execução com `PYTHONPATH=src` | não há entry point distribuído publicado |
| 15 | Dependências | `pyproject.toml` canônico, `uv.lock` universal versionado, índices PyTorch explícitos | instalar com `uv sync --locked` |
| 16 | Perfis | `runtime-cpu` e `runtime-cu128` exclusivos; ROCm não declarado | compatibilidade limitada pela interseção das dependências |
| 17 | Faixa Python | `>=3.10,<3.14` | definida pela compatibilidade do stack atual |
| 18 | Snapshot legado | `requirements.txt` removido | exportação por `uv export` documentada em [INSTALACAO.md](INSTALACAO.md) |
| 19 | Temporários | Workspace exclusivo por job; cache de modelos não é apagado para cancelar | limpeza segura em conclusão, falha e cancelamento |
| 20 | Logs | Log rotativo com home redigido; UI recebe mensagens amigáveis | não registrar caminho pessoal ou segredo |
| 21 | Privacidade | Fluxo padrão NLLB permanece local; Gemini é integração externa opt-in e transmite o texto das cues à API | chave fora do repositório/logs; escolha explícita do backend |
| 22 | Testes | Suíte determinística sem rede/modelos; integração/E2E real depende de ferramentas | CI instala FFmpeg |
| 23 | Baseline legada | `main.py`, `core/` e `gui/` preservados e caracterizados | histórico em [baseline arquivada](archive/previous-remodeling/LEGACY_BASELINE.md) |
| 24 | Integração anterior | Fases 6–9 foram integradas por squash local quando PR não estava disponível | histórico detalhado preservado no arquivo |
| 25 | Tema | Fusion + `QPalette` completa + QSS no `QApplication` | menus, tooltips, popups e estados desabilitados seguem o tema |
| 26 | Geometria da janela | `QByteArray` de `saveGeometry()`, reencaixe na tela e estado maximizado | geometria persiste entre aberturas |
| 27 | Feedback de falhas | Banner persistente no snapshot + status bar | falha não fica somente no log |
| 28 | Idiomas da GUI | Falado e final independentes; tradução opcional | seleção de idioma não é perdida |
| 29 | Layout da janela | Página única compacta, duas colunas em largura suficiente | interface se adapta a janelas menores |
| 30 | Cache privado | Diretórios privados `0o700` | NLTK pode preparar `punkt_tab` em cache privado |
| 31 | Telemetria de desempenho | Instrumentação local via porta `PerformanceReporter`; relatório JSON privado, sem mídia ou texto e sem envio externo | Não afeta o resultado do job; métricas servem à baseline comparável da Fase 1 |
| 32 | ASR alternativo | `FasterWhisperTranscriber` via faster-whisper/CTranslate2 disponível por seleção explícita; OpenAI Whisper permanece padrão | Sem fallback silencioso; promoção do candidato depende de benchmark no hardware/corpus de referência e gate lexical/temporal |
| 33 | Tradução Gemini | `GeminiTranslator` via REST/urllib, opt-in; NLLB permanece padrão e alternativa local; grounding contextual habilitado por padrão no Gemini | sem fallback silencioso; chave e texto externo exigem escolha/configuração explícitas |
| 34 | Configuração Gemini no desktop | Motor e chave são configuráveis em Preferências; a chave fica fora do QSettings em armazenamento local privado | troca de backend aplicada aos próximos jobs sem reinício; chave não entra em logs/relatórios |
| 35 | Aceite da Fase 6 | NLLB e Gemini permanecem implementados e opcionais; benchmark comparativo não é gate desta fase | ambos ficam disponíveis para homologação futura sem bloquear a Fase 7 |

## Decisões da Fase 10 (D1–D6)

A implementação e seu handoff estão preservados em [FASE_10_PLANO.md](archive/previous-remodeling/FASE_10_PLANO.md) e [HANDOFF_FASE_10.md](archive/previous-remodeling/HANDOFF_FASE_10.md).

| # | Tema | Decisão |
|---|---|---|
| D1 | Navegação | Página única compacta, sem wizard |
| D2 | Política de tradução | Tradução opcional; sem tradução, a legenda sai no idioma falado |
| D3 | Pares de idiomas | PT-BR e inglês |
| D4 | Progresso | Percentual quando medido; relógio de etapa quando não |
| D5 | Notificações | Banner persistente e status bar |
| D6 | Distribuição Linux | Entrada `.desktop`; PyInstaller ainda não homologado |

## Hipóteses de evolução — ainda não aprovadas

As linhas abaixo são opções para benchmark, não novas dependências ou decisões de produto.

| Tema | Opção em avaliação | Condição para adoção |
|---|---|---|
| ASR | Otimizar faster-whisper/CTranslate2 e comparar configurações | Backend alternativo já implementado; promover a padrão somente após WER/CER, alinhamento e ganho medidos no hardware de referência |
| ASR CPU | INT8 e ajuste de threads | suporte real no hardware e ausência de regressão |
| Tradução | NLLB convertido para CTranslate2 | revisão humana equivalente, tokens/segundo maior e licença validada |
| Tradução | Gemini Developer API (`gemini-3.8-flash`) | throughput maior e revisão humana não inferior, com integridade 1:1 e privacidade aprovada |
| Tradução CPU | INT8, beam 2/1 e token-bucketing | comparação com beam 4 e NLLB Transformers, sem erro crítico |
| Memória | Evicção de modelos entre estágios | redução de pressão de RAM sem aumentar tempo total |
| Segmentação | Agrupamento global entre segmentos Whisper | melhora de leitura sem perda textual ou deslocamento temporal |
| Exibição | Estender cue dentro de silêncio disponível | sem cruzar a próxima fala, fim da mídia ou limite editorial |
| Gate de qualidade | `APPROVED`, `REVIEW_REQUIRED`, `BLOCKED` | testes positivos/negativos e critérios documentados |

## Decisões ainda abertas

| Tema | Situação | Onde será decidido |
|---|---|---|
| Precisão temporal em corpus real | Metas provisórias: mediana 150 ms / P95 350 ms | Fases 1, 2 e 8 do [plano](PLANO_CORRECAO_MELHORIA.md) |
| Qualidade tradutória PT↔EN | Benchmark comparativo não executado por decisão de produto; ferramenta preservada | homologação futura, se desejada |
| Preservação do texto original junto ao SRT traduzido | Não implementada | decisão de produto futura |
| Backends oficialmente suportados | CI cobre Ubuntu; homologação multiplataforma pendente | após benchmark/homologação |
| Empacotamento distribuível | PyInstaller declarado, fluxo não homologado | frente futura |
| Adoção operacional de ASR alternativo | Implementado e integrado; não é padrão | Benchmark local pareado, revisão humana e homologação da Fase 8 |
| Backend de tradução otimizado | NLLB Transformers segue padrão; Gemini disponível como opção operacional | benchmark/homologação futura, sem bloquear a Fase 6 |
