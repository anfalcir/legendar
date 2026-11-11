# Handoff final — Fase 9: documentação e finalização

- **Status:** implementação concluída na branch `phase-9/documentation`, integrada à `main` por squash.
- **Plano operacional:** [FASE_9_PLANO.md](FASE_9_PLANO.md)
- **Encerramento:** as Fases 0–9 estão concluídas e integradas à `main`. O que resta é homologação do usuário, não implementação.

## 1. Documentação entregue

| Documento | Para quê serve |
|---|---|
| [README.md](../README.md) | porta de entrada: estado, instalação rápida, execução, testes e índice |
| [ARQUITETURA.md](ARQUITETURA.md) | camadas, módulos, portas, estados, threads, publicação e testes |
| [OPERACAO.md](OPERACAO.md) | uso da janela, estados, cancelamento, arquivos, erros e diagnóstico |
| [INSTALACAO.md](INSTALACAO.md) | requisitos, perfis `uv`, ferramentas externas, verificação e desinstalação |
| [DECISOES.md](DECISOES.md) | decisões consolidadas e decisões abertas |
| [PLANO_REMODELAGEM.md](PLANO_REMODELAGEM.md) | destino do produto e critérios globais de aceite |
| [ESTADO_ATUAL.md](ESTADO_ATUAL.md) | estado real, evidências, riscos e pendências |
| [RELATORIO_FASE_8.md](RELATORIO_FASE_8.md) | matriz de testes, cobertura e pendências humanas |
| [MATRIZ_DEPENDENCIAS.md](MATRIZ_DEPENDENCIAS.md) | governança de dependências, perfis e compatibilidade |
| Planos e handoffs das Fases 0–8 | histórico técnico de cada fronteira |

## 2. Mudanças de repositório na fase

1. `requirements.txt` removido: era um snapshot UTF-16 da baseline, sem
   correspondência com o manifesto atual. A exportação para `pip` agora é feita
   por `uv export` (documentada em [INSTALACAO.md](INSTALACAO.md)).
2. `LICENSE` (MIT) adicionado, conforme prometido pelo README.
3. `tests/test_documentation.py` passou a exigir os documentos das Fases 8 e 9,
   o `LICENSE` e links relativos válidos.
4. `docs/MATRIZ_DEPENDENCIAS.md`, `docs/PLANO_REMODELAGEM.md`,
   `docs/ESTADO_ATUAL.md` e `docs/LEGACY_BASELINE.md` atualizados para refletir
   a remoção e o encerramento das fases.
5. Nenhuma alteração de comportamento em `src/`: a suíte passou de 443 para
   452 testes (442 sem FFmpeg), porque a fase acrescentou os testes de
   documentação e a verificação da retirada do manifesto legado.

## 3. Evidências de verificação

```bash
uv lock --check
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q
uv run --locked --no-sync ruff check src/legendar tests scripts
uv run --locked --no-sync ruff format --check src/legendar tests
uv run --locked --no-sync python scripts/check_doc_links.py
```

Resultados registrados: suíte completa verde (452 testes com FFmpeg; 442 + 10
skips sem FFmpeg), Ruff check e format limpos, lockfile válido e nenhum link
relativo quebrado.

## 4. Roteiro de homologação do usuário

Passo a passo prático, com o que fazer e o que observar em cada teste:
[HOMOLOGACAO.md](HOMOLOGACAO.md). Resumo:

1. Instalar pelo [INSTALACAO.md](INSTALACAO.md) com o perfil adequado ao seu hardware.
2. Abrir a aplicação e confirmar o painel de prontidão (FFmpeg, Whisper, WhisperX, NLLB).
3. Processar um vídeo PT-BR curto sem tradução; inspecionar o SRT no player de referência.
4. Repetir com tradução para inglês e revisar nomes, números e termos técnicos.
5. Repetir com áudio em inglês e saída PT-BR.
6. Testar uma URL do YouTube que você tenha direito de processar, incluindo cancelar durante o download.
7. Testar cancelamento durante transcrição, alinhamento e tradução.
8. Medir tempo, memória e temperatura em uma pregação longa.
9. Registrar divergências de sincronização com marcações humanas para calibrar as metas da seção 9.4 do plano mestre.
10. Validar a interface no seu monitor e sistema operacional padrão.

## 5. Limites conhecidos (não são dívidas ocultas)

- Modelos reais não são exercitados pela suíte determinística; há smoke tests por fase na CI.
- Não há empacotamento distribuível homologado.
- A precisão temporal e a qualidade tradutória dependem de homologação humana.
- O fluxo YouTube depende de `yt-dlp` e de um runtime JavaScript compatível.
- `PUBLISHING` não é cancelável por decisão explícita.

## 6. Encerramento do roadmap

Com as Fases 0–9 integradas, o produto atende aos critérios globais de aceite do
plano mestre que podem ser demonstrados por código, testes e CI. Os critérios que
dependem de mídia real e julgamento humano estão listados acima e em
[RELATORIO_FASE_8.md](RELATORIO_FASE_8.md) seção 7.
