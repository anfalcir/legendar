# Plano operacional — Fase 9: documentação e finalização

- **Status:** implementada e validada na branch `phase-9/documentation`, a ser integrada à `main` por squash.
- **Fronteira:** consolidar arquitetura, operação, instalação e decisões; retirar o manifesto legado; revisar o README; registrar o estado final e o roteiro de homologação do usuário.
- **Dependências:** Fases 0–8 integradas à `main`.
- **Documento de transferência:** [HANDOFF_FASE_9.md](HANDOFF_FASE_9.md).

---

## 1. Objetivos e escopo

### 1.1. Dentro do escopo

1. Publicar guias de arquitetura, operação e instalação coerentes com o código.
2. Registrar as decisões técnicas consolidadas e as que dependem do usuário.
3. Remover o `requirements.txt` legado e documentar a exportação a partir do lockfile.
4. Reescrever o README como porta de entrada: estado, instalação, execução, testes, documentação e limites.
5. Adicionar a licença referenciada pelo README.
6. Ampliar a verificação de documentação (documentos obrigatórios, links, licença).
7. Atualizar o plano mestre e o estado atual com o encerramento das Fases 6–9.

### 1.2. Fora do escopo

- Homologação humana de tradução, sincronização e leitura em mídia real.
- Empacotamento distribuível e assinatura de binários.
- Publicação em PyPI ou canais de distribuição.
- Novas funcionalidades além das previstas no plano mestre.

## 2. Entregáveis

| Documento | Conteúdo |
|---|---|
| [ARQUITETURA.md](ARQUITETURA.md) | camadas, mapa de módulos, fluxo do job, portas, estados, threads, publicação e arquitetura de testes |
| [OPERACAO.md](OPERACAO.md) | jornada na UI, estados, cancelamento, arquivos, primeira execução, erros, preferências, diagnóstico |
| [INSTALACAO.md](INSTALACAO.md) | requisitos, ferramentas externas, perfis `uv`, execução, verificação, ajustes por ambiente, pip e desinstalação |
| [DECISOES.md](DECISOES.md) | 24 decisões consolidadas e 5 decisões abertas |
| [HANDOFF_FASE_9.md](HANDOFF_FASE_9.md) | encerramento do projeto, evidências e roteiro de homologação |
| `README.md` | porta de entrada único e coerente com os guias |
| `LICENSE` | MIT, referenciada pelo README |

## 3. Mudanças de repositório

- Remoção de `requirements.txt` (snapshot UTF-16 da baseline, sem relação com o manifesto atual).
- `tests/test_documentation.py` passa a exigir os documentos das Fases 8 e 9 e a presença do `LICENSE`.
- `docs/MATRIZ_DEPENDENCIAS.md`, `docs/ESTADO_ATUAL.md`, `docs/PLANO_REMODELAGEM.md` e `docs/LEGACY_BASELINE.md` atualizados para refletir a remoção.
- Nenhuma mudança de comportamento em `src/`.

## 4. Critérios de aceitação

1. Toda afirmação dos guias corresponde ao código ou a um teste existente.
2. A documentação não contém links relativos quebrados.
3. Instalação e execução podem ser reproduzidas seguindo apenas [INSTALACAO.md](INSTALACAO.md).
4. O README leva a todos os documentos relevantes e não promete o que não existe.
5. `pyproject.toml` + `uv.lock` são os únicos manifestos de dependências.
6. Suíte completa, Ruff e verificação de documentação verdes após as mudanças.
7. O estado final e as pendências humanas estão explícitos em [ESTADO_ATUAL.md](ESTADO_ATUAL.md).

## 5. Comandos de verificação

```bash
uv lock --check
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q
uv run --locked --no-sync ruff check src/legendar tests scripts
uv run --locked --no-sync ruff format --check src/legendar tests
uv run --locked --no-sync python scripts/check_doc_links.py
```

## 6. Encerramento

A Fase 9 fecha o roadmap do plano mestre. O que resta não é implementação: é a
homologação do usuário com mídia real, modelos completos e o computador-alvo,
conforme a seção 7 de [RELATORIO_FASE_8.md](RELATORIO_FASE_8.md).
