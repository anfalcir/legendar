# Plano operacional — Fase 2: Interface profissional

- **Status:** implementação concluída e validada; integração pendente na PR #3
- **Branch:** `phase-2/professional-ui`
- **Base:** `main` após a integração da Fase 1 (`de31ddd`) e sincronização documental
- **Escopo:** camada de apresentação Qt e sua suíte de testes; sem processamento real de mídia
- **Roadmap:** Fase 2 — Interface profissional

## 1. Objetivo

Entregar uma janela desktop visualmente consistente, clara e acessível, com hierarquia visual, estados explícitos, diálogos de confirmação, preferências persistidas, progresso honesto e logs úteis. A GUI deve continuar sendo uma camada de apresentação: nenhum processamento pesado ou regra de domínio será movido para a thread principal.

O botão principal ainda não executará processamento real. O pipeline de mídia é deliberadamente conectado na Fase 3; nesta fase, os fluxos serão demonstrados por doubles nos testes.

## 2. Entregas

1. **Sistema visual:** temas claro/escuro/sistema, paleta e tipografia consistentes, cartões, botões primário/secundário/perigo, campos, foco visível, estados disabled/hover e escala responsiva.
2. **Janela principal:** cabeçalho com identidade Legendar, seleção de mídia, configuração de idiomas, destino, ação primária, estado de prontidão, andamento e logs recolhíveis; layout utilizável em resoluções menores sem cortes.
3. **Confirmação de processamento:** diálogo modal com origem, idioma, destino e caminho final. Duplo clique, sinais repetidos ou reentrância não podem iniciar dois jobs. Se o destino existir, a substituição exige confirmação separada com padrão seguro (Não).
4. **Cancelamento seguro:** confirmar antes de solicitar cancelamento; a opção padrão é Não. Após confirmação, desabilitar imediatamente o botão e rejeitar novos pedidos enquanto a thread conclui.
5. **Estados e progresso:** campos e ações bloqueados durante execução; cancelar só aparece habilitado em estados canceláveis; publicação permanece não cancelável. Barra indeterminada quando não há métrica e percentual apenas quando um evento fornecer progresso real.
6. **Logs e feedback:** painel expansível, rolagem automática sem sequestrar a leitura quando o usuário estiver examinando linhas antigas, timestamps locais, níveis visuais, limite de linhas, mensagens de erro/aviso/conclusão e caminho da saída.
7. **Preferências:** QSettings para tema, idioma final padrão, diretório de saída, estado expandido do log e geometria da janela. Não persistir caminho da mídia nem conteúdo privado.
8. **Acessibilidade/usabilidade:** ordem de tabulação, rótulos, foco, tooltips, atalhos sem duplicar ações, botões com nomes acessíveis e navegação por teclado.
9. **Testes:** pytest-qt offscreen para diálogos, tema, persistência, estados, confirmações, clique duplo, cancelamento repetido, campos bloqueados, progresso indeterminado/determinado, logs e diferentes tamanhos de janela.
10. **Documentação e CI:** sincronizar README, estado atual e roadmap; manter matriz Python 3.10–3.13, Ruff, format, compileall e testes completos verdes.

## 3. Limites

- Não implementar download YouTube, FFmpeg real, Whisper/WhisperX, tradução de fornecedor, processamento paralelo ou E2E real.
- Não simular percentuais ou tempo restante que o pipeline não medir.
- Não armazenar caminhos de mídia, mídia, transcrições ou segredos em QSettings.
- Não enfraquecer contratos de cancelamento, workspace, publicação atômica ou fronteiras arquiteturais da Fase 1.
- Não modificar a baseline legada em `main.py`, `core/` e `gui/` salvo correção indispensável comprovada por teste.

## 4. Critérios de aceite

- [x] Identidade visual consistente em tema claro, escuro e sistema.
- [x] Janela reorganizada em cartões e área rolável; teste Qt em 680×620 confirma o comportamento responsivo básico.
- [x] Diálogo de confirmação mostra origem, idioma falado, idioma final e destino antes de iniciar.
- [x] Clique repetido/reentrância não cria jobs duplicados.
- [x] Sobrescrita de saída preexistente exige consentimento explícito e padrão Não.
- [x] Cancelamento exige confirmação, padrão Não, e só é solicitado uma vez; rejeição na etapa não cancelável é informada corretamente.
- [x] Campos e preferências são bloqueados durante a thread e reabilitados após seu término.
- [x] Progresso indeterminado/determinado é honesto, monotônico e acessível; não inventa percentual.
- [x] Log expansível com timestamp, níveis e rolagem que respeita a posição de leitura.
- [x] Preferências persistem com QSettings isolado; mídia, transcrições e credenciais não são armazenadas.
- [x] Execução do pipeline permanece em QThread; teste confirma que não bloqueia a GUI.
- [x] Testes Qt offscreen, pytest, Ruff e Ruff format passam em Python 3.10–3.13.
- [x] README, roadmap, estado atual, handoff e este plano refletem o que foi entregue.

## 5. Ordem de execução

1. Sistema de tema e componentes visuais reutilizáveis.
2. Diálogos de confirmação e preferências.
3. Reestruturação da janela e adaptação do ViewModel para progresso/logs.
4. Guardas de início/cancelamento e ciclo de vida de controles.
5. Testes Qt e revisão de acessibilidade/responsividade.
6. CI completa, correções, revisão e atualização documental.
7. PR para `main`; só integrar depois dos gates verdes.

## 6. Evidências finais

- **Workflow:** [Phase 1 quality #42911438434](https://github.com/anfalcir/legendar/actions/runs/42911438434), reutilizado como gate de qualidade; 4/4 jobs aprovados em Python 3.10, 3.11, 3.12 e 3.13.
- **Suíte:** 218 testes aprovados por ambiente.
- **Cobertura:** 88% (2.480 statements; 292 não cobertos).
- **Ruff:** `ruff check` aprovado nos quatro ambientes.
- **Formatação:** `ruff format --check` aprovado; 91 arquivos já formatados.
- **Qt:** testes offscreen cobrem tema, diálogos, preferências, confirmação destrutiva, cancelamento, reentrância, tabulação, acessibilidade, scroll e layout estreito.
- **Isolamento:** nenhum processamento real de mídia/modelo/tradução foi ativado nesta fase; os fluxos de job usam doubles.

### Limites confirmados

A tela está visualmente estruturada e funcional sob os testes automatizados, mas a homologação visual em monitores físicos, scaling HiDPI e diferentes ambientes desktop Linux/Windows/macOS continua sendo parte da homologação global da Fase 8. A interface ainda usa um pipeline simulado/pendente: processamento real de mídia fica na Fase 3 e seguintes.

A implementação está validada tecnicamente e pronta para integração. A Fase 3 permanece bloqueada até aprovação explícita do responsável.
