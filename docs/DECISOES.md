# Decisões técnicas consolidadas

- **Formato:** registro curto de decisões (contexto, escolha, consequência), consolidado na Fase 9.
- **Escopo:** decisões que afetam contrato, dependências, formato de saída, testes ou operação.
- **Regra:** mudar uma decisão exige atualizar este arquivo, os testes correspondentes e o [ESTADO_ATUAL.md](ESTADO_ATUAL.md).

| # | Tema | Decisão | Consequência |
|---|---|---|---|
| 1 | Tradução | NLLB-200 distilled 600M local, por cue, atrás da porta `Translator` | nenhum texto sai do computador; primeira execução baixa ≈2,4 GB |
| 2 | Mecanismo de tradução | Tokenizador lento SentencePiece, origem `por_Latn`/`eng_Latn`, destino por `forced_bos_token_id` | dependências `transformers` + `sentencepiece` diretas nos perfis de runtime |
| 3 | Escopo de idiomas | Somente PT-BR e inglês; qualquer outro idioma é recusado | `NLLB_CODES` declara exatamente os pares suportados |
| 4 | Reconhecimento | Whisper local no idioma de origem; nunca a tarefa de tradução do Whisper | timestamps do reconhecimento são aproximados até o alinhamento |
| 5 | Alinhamento | WhisperX 3.8.6 como alinhador primário; stable-ts não é dependência nem fallback | trocar exige comparação em corpus anotado e nova decisão |
| 6 | Layout da legenda | Duas linhas de 42 caracteres, 84 por cue, 1–7 s, pausa de 0,6 s, ~17 cps | excesso é sinalizado, nunca truncado |
| 7 | Tradução e tempo | A tradução reescreve texto mantendo `TimeRange` e a relação 1:1 por cue | nenhum timestamp é derivado da contagem de palavras traduzidas |
| 8 | Validação SRT | Falha estrutural bloqueia publicação; risco de leitura vira aviso | nenhum SRT inválido é publicado como concluído |
| 9 | Publicação | Arquivo temporário + `validate_roundtrip` + troca atômica | SRT anterior permanece intacto em qualquer falha |
| 10 | Cancelamento | Cooperativo por token; `PUBLISHING` é ponto de não retorno | inferência em andamento termina antes do encerramento |
| 11 | Threads | `QThread` + sinais enfileirados; sem `processEvents` nem sleeps artificiais | nenhum widget é tocado fora da thread da interface |
| 12 | Estado | `StateMachine` é a única autoridade de transição; controlador emite um evento terminal | a GUI apenas renderiza snapshot |
| 13 | Arquitetura | Layout `src`, camadas `domain/application/infrastructure/presentation/bootstrap` | importações proibidas falham em `tests/test_architecture.py` |
| 14 | Empacotamento Python | `[tool.uv] package = false`; execução com `PYTHONPATH=src` | não há instalação de pacote nem entry point publicado |
| 15 | Dependências | `pyproject.toml` canônico, `uv.lock` universal versionado, índices PyTorch explícitos | instalação sempre com `uv sync --locked` |
| 16 | Perfis | `runtime-cpu` e `runtime-cu128` exclusivos; ROCm não declarado | PyTorch 2.11 do índice ROCm 7.2 é incompatível com WhisperX 3.8.6 |
| 17 | Faixa de Python | `>=3.10,<3.14` | definida pela compatibilidade do WhisperX, não pela máquina de desenvolvimento |
| 18 | Snapshot legado | `requirements.txt` removido na Fase 9 | exportação por `uv export` documentada em [INSTALACAO.md](INSTALACAO.md) |
| 19 | Temporários | Workspace exclusivo por job em `<cache>/tmp`; cache de modelos nunca é apagado | limpeza segura em conclusão, falha e cancelamento |
| 20 | Logs | Log rotativo em arquivo com home redigido; UI recebe mensagens amigáveis | nenhum caminho pessoal ou segredo no log |
| 21 | Privacidade | Sem telemetria, sem nuvem, sem credenciais no repositório | áudio e texto permanecem locais |
| 22 | Testes | Suíte determinística sem rede/modelos; mídia real marcada como `integration`/`e2e` e pulada sem FFmpeg | CI instala FFmpeg para executá-los sempre |
| 23 | Baseline legada | `main.py`, `core/` e `gui/` preservados e caracterizados | remoção exige política em [LEGACY_BASELINE.md](LEGACY_BASELINE.md) |
| 24 | Integração das Fases 6–8 | Squash local, sem PR, por indisponibilidade de `gh`/token no ambiente | histórico detalhado permanece nas branches de fase |

## Decisões ainda abertas (dependem do usuário)

| Tema | Situação | Onde será decidido |
|---|---|---|
| Precisão temporal em corpus real | metas provisórias da seção 9.4 do plano mestre | homologação final |
| Qualidade tradutória PT↔EN | não medida em corpus autorizado | homologação final |
| Arquivar o texto original junto do SRT traduzido | não implementado | decisão de produto |
| Plataformas/backends oficialmente suportados | somente Ubuntu na CI | após homologação integrada |
| Empacotamento distribuível (PyInstaller) | dependência declarada, fluxo não homologado | fase futura |
