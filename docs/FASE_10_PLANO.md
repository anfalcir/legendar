# Plano operacional — Fase 10: correções e endurecimento pós-homologação

- **Status:** proposta de execução; nenhuma mudança de código aplicada ainda.
- **Fronteira:** eliminar os 13 achados da homologação de 11/11/2026 tratando causas
  sistêmicas (não apenas os sintomas), sem regredir as Fases 0–9.
- **Dependências:** Fases 0–9 integradas à `main` (ver [ESTADO_ATUAL.md](ESTADO_ATUAL.md)).
- **Roteiro que originou os achados:** [HOMOLOGACAO.md](HOMOLOGACAO.md).
- **Documento de transferência previsto:** `docs/HANDOFF_FASE_10.md` (criado ao final da execução).

---

## 1. Método: como cada causa foi provada

Cada achado foi reproduzido com sonda descartável **antes** de virar tarefa. O que
não pôde ser reproduzido fora do ambiente do usuário está marcado como hipótese
com teste de diagnóstico obrigatório.

| # | Sintoma relatado | Prova executada | Veredito |
|---|---|---|---|
| 1 | Tema escuro com pedaços claros | Render offscreen com `stylesheet_for("dark")` + inspeção do QSS | **Sistêmico**: tema não cobre menus, tooltips, barras horizontais, fundo do viewport nem a paleta do `QApplication` |
| 2 | Janela cortada, sem responsividade, maximizar falha | Sondas de `minimumSizeHint` e roundtrip de `QSettings` | **Sistêmico**: mínimos fixos + geometria serializada como `bytes` (restauração inválida) + conteúdo de 1287 px de altura mínima |
| 3 | Dropdown de origem cortado, exige barra | `showPopup()` + `visualRect()` em combo estilo QSS do produto | **Sistêmico**: `sizeHintForRow`=26 px contra `padding` do item no QSS; afeta as 5 combos |
| 4 | Rodapé com textos cinzas desnecessários | Leitura de `readiness_details` e do rodapé | **Pontual**: dados do preflight impressos na UI |
| 5 | Sem logo, sem ícone, sem identidade | Busca por `assets/`, `setWindowIcon`, `.desktop` | **Pontual e ausente**: nada existe em `src/` |
| 6 | Tela muito extensa | `content.minimumSizeHint()` = 722×1287; `sizeHint` = 728×1437 | **Sistêmico**: layout de coluna única |
| 7 | "Transcrevendo" por 15 min sem subetapas | Inspeção da API instalada do Whisper e do `_STAGE_RANGES` | **Sistêmico**: Whisper não expõe callback; faixa 15→55% nunca reporta |
| 8 | Idioma falado trava o idioma final | `_sync_translation_controls()` | **Sistêmico**: regra de UI acopla os dois campos |
| 9 | Erro de par de idiomas só após 15 min | `serial_pipeline.py:83-91` + `Language.parse` tardio | **Sistêmico**: validação dentro do pipeline, não no pré-voo |
| 10 | Faixa editável apesar de única | Fluxo `_invalidate_media_inspection`/`stream_combo` | **Pontual** |
| 11 | Erro registrado só no histórico | `job_view_model.report_error` | **Sistêmico**: não existe camada de notificação |
| 12 | NLTK `punkt_tab` falha após 11 min | Reprodução do download no cache real | **Sistêmico**: cache criado com umask 002 + NLTK 3.10 recusa diretório não privado + download em tempo de alinhamento |
| 13 | Botões inconsistentes após falha | QSS sem `:disabled` para `variant="danger"`; flags duplicadas em `_render` | **Sistêmico**: estados derivados ad hoc |

### 1.1. Evidências brutas coletadas

| Evidência | Valor observado | Consequência |
|---|---|---|
| `content.sizeHint()` | 728 × 1437 | item 6 |
| `content.minimumSizeHint()` | 722 × 1287 | janela não pode ser compactada abaixo disso sem refazer o layout |
| `QLabel#pageTitle` mínimo | 303 px | título não quebra → força largura |
| `window.minimumSizeHint()` | 38 × 93 (sem WM) contra `setMinimumSize(680, 620)` | piso artificial, não derivado do layout |
| `restoreGeometry(settings.value("window/geometry"))` | `False` (bytes lidos de variante INI) | geometria nunca restaurada corretamente |
| `restoreGeometry(QByteArray)` no mesmo dado | `True` | correção é tipar o valor |
| `view.sizeHintForRow(0)` | 26 px | item 3 |
| popup do combo com 2 itens | `view.height()=52`, item 26 px + padding | segundo item exige rolagem |
| `nltk.download('punkt_tab', download_dir=cache)` | `False` + `Refusing to install into ... writable by, or owned by, another account` | item 12 |
| permissões do cache antes do `chmod` | `0o775` (`umask 0002`, `mkdir` sem `mode`) | origem da recusa do NLTK |
| idem após `chmod -R go-w` no cache | `True` e `nltk.data.load(...)` funciona | prova de causa |
| `whisper/transcribe.py` | sem `progress_callback`; só `verbose` (tqdm) e `clip_timestamps` | item 7 |
| `whisperx/asr.py` e `whisperx/alignment.py` | aceitam `progress_callback` | caminho para progresso real |
| QSS `QPushButton[variant="danger"]` | sem regra `:disabled` | item 13 |
| `job_view_model.report_error` | grava `"Erro: ..."` em `log_lines` | item 11 |

---

## 2. Leitura executiva: 13 sintomas, 7 causas sistêmicas

| Causa | Descrição | Sintomas explicados |
|---|---|---|
| **C1** | O tema não governa o produto inteiro: sem `QPalette`, QSS restrito a dois seletores, popups e diálogos nativos fora do controle | 1, 3 (parte visual), 13 (visual) |
| **C2** | Estado da interface derivado de flags locais (`busy`, `worker_running`, `inspection_running`) duplicadas, e QSS sem regras de estado | 2 (botões), 11, 13 |
| **C3** | Contratos validados dentro do pipeline, depois das etapas caras | 8, 9, 12, sensação de travamento em 7 |
| **C4** | Modelo de idiomas implícito: destino travado no falado, tradução binária, auto-detecção proibida com tradução | 8, 9 |
| **C5** | Prontidão de recursos é reativa: download em tempo de execução, sem pré-voo | 9, 12 |
| **C6** | Etapas longas são caixas-pretas: sem heartbeat, sem subprogresso, sem granularidade | 7, 9 |
| **C7** | Layout monolítico de coluna única com mínimos fixos, sem política responsiva | 2, 6, 3 (indireto) |

Consequência prática: corrigir C1–C7 resolve os 13 pontos **e** previne a classe de
falha que os gerou (ex.: novos widgets nascem fora do tema, novos erros caem no log,
novos idiomas quebram no fim do pipeline).

---

## 3. Vertentes de execução

Cada vertente é independente o suficiente para virar um PR. A ordem recomendada
está na seção 5.

### 10.1. Sistema de design e tema completo (C1 → itens 1, 3-visual, 13-visual)

**Diagnóstico.** `theme.py` gera um QSS por interpolação de um `dict` e o aplica em
`self.setStyleSheet(...)` de `MainWindow` (`main_window.py:128, 831`). Nunca há
`QApplication.setPalette`. Resultado: tudo que não é widget pintado pelo QSS
(menus, tooltips, `QFileDialog` nativo, popup de combo, barra de rolagem horizontal,
fundo do `QScrollArea`) usa a paleta clara do estilo da plataforma. É exatamente o
"pedaço claro" do print. Além disso há cores hexadecimais fixas do tema claro em
`main_window.py:1299-1327` (`readiness_icon`), que permanecem claras no tema escuro,
e QSS inline em `dialogs.py:55,143`.

**Mudanças.**

1. `Theme` como `dataclass(frozen=True)` com tokens nomeados + `palette()` que
   devolve `QPalette` completo (`Window`, `WindowText`, `Base`, `AlternateBase`,
   `Text`, `Button`, `ButtonText`, `BrightText`, `Highlight`, `HighlightedText`,
   `ToolTipBase`, `ToolTipText`, `PlaceholderText`, `Light/Midlight/Dark/Mid` e
   `Disabled` para `Text`/`ButtonText`/`WindowText`).
2. `apply_theme(app, theme)` no bootstrap: `app.setStyle("Fusion")` +
   `app.setPalette(theme.palette())` + `app.setStyleSheet(theme.stylesheet())`.
   Fusion é obrigatório para o QSS ser determinístico entre XFCE/GNOME/Windows.
3. Completar o QSS (auditoria feita; seletores ausentes na lista abaixo):
   `QMenu`, `QMenu::item[:selected|:disabled]`, `QToolTip`, `QScrollBar:horizontal`
   com handle/add-line/sub-line, `QComboBox QAbstractItemView::item` (com
   `min-height`), `QComboBox::down-arrow` (SVG da marca), `QProgressBar[state]`,
   `QGroupBox`, `QToolButton:checked`, `QHeaderView`, `QSplitter::handle`,
   `QTabBar/QTabWidget`, `QSpinBox`, `QSlider`, `QStatusBar::item`,
   `QScrollArea > QWidget > QWidget` (fundo do conteúdo),
   `QLabel#statusPill[state="idle"]`, `QPushButton[variant="danger"]:disabled`,
   `[variant="ghost"]:disabled`.
4. Remover QSS inline e cores fixas: `readiness_icon` passa a usar
   `setProperty("state", "ok"|"warning")`; o `font-size` inline de `dialogs.py` sai.
5. `QFileDialog`: usar `QFileDialog.Option.DontUseNativeDialog` (decisão registrada
   em DECISOES), porque o diálogo nativo nunca será ajustável por QSS.
6. Contraste: ≥ 4.5:1 para texto normal e ≥ 3:1 para texto grande nos dois temas,
   com checagem automatizada.

**Impacto em outros pontos.** Resolve o "feio" do item 1, o corte visual do item 3 e
a aparência "habilitada" do item 13; cria a base para o item 5 (marca) e para o
item 6 (reflow sem artefatos).

**Testes novos.**

- `tests/gui/test_theme_tokens.py`: toda cor referenciada no QSS existe no `Theme`;
  nenhuma chave ausente; nenhuma cor hex literal fora de `theme.py`.
- `tests/gui/test_palette_coverage.py`: todo `ColorRole` consumido pelos widgets do
  produto está definido e coerente nos dois temas.
- `tests/gui/test_theme_render.py`: render offscreen 1280×800 e amostragem de 16
  pontos (viewport, statusbar, área da scrollbar, cantos, tooltip, menu, popup)
  exigindo luminância < 128 no escuro e > 128 no claro.
- `tests/gui/test_qss_state_matrix.py`: para cada `QPushButton[variant=X]` existe
  `[variant=X]:disabled`; para cada `QLabel#statusPill[state=Y]` existe regra.

**Riscos.** QSS + Fusion alteram métricas de alguns widgets; mitigado pelos testes de
layout da 10.2, que rodam depois.

### 10.2. Estado único da interface, janela e responsividade (C2+C7 → itens 2, 6, 13)

**Diagnóstico.** `_render` recalcula `busy`/`worker_running`/`inspection_running` e a
expressão `source_ready` está duplicada em `_update_status_pill`. Habilitar e
desabilitar cada widget é feito em vários pontos, com regras diferentes para o mesmo
estado — daí "o botão parece habilitado mas não clica" (QSS sem `:disabled` da 10.1
somado a regras divergentes). A geometria é persistida como `bytes`
(`main_window.py:1372`) e restaurada sem clamp (`:1366`); o tamanho inicial é fixo
(`:126-127`).

**Mudanças.**

1. `presentation/qt/ui_state.py`: `UiState` (`IDLE`, `READY`, `INSPECTING`,
   `CONFIRMING`, `STARTING`, `RUNNING`, `CANCELLING`, `COMPLETED`, `FAILED`,
   `CANCELLED`) + função pura `derive_ui_state(snapshot, *, inspection_running,
   starting, cancel_pending)` + tabela declarativa `CONTROLS: dict[UiState,
   dict[str, ControlSpec]]` (`enabled`, `visible`, `text`, `variant`).
   `MainWindow._apply_ui_state()` passa a ser o único ponto que chama `setEnabled`.
2. Invariantes testáveis: em estado terminal `cancel` desabilitado **e** com variante
   rebaixada para `ghost`; `generate` habilitado apenas em `READY`; `open_folder`
   habilitado apenas com artefato publicado.
3. Geometria: salvar `QByteArray` (`settings.setValue(key, window.saveGeometry())`),
   ler com `settings.value(key, type=QByteArray)`, restaurar antes de `show()` e
   validar contra `screen.availableGeometry()`, reencaixando quando a tela mudou;
   persistir `window/maximized`. Migração: chave legada ilegível é descartada e o
   default passa a ser derivado da tela (`min(1180, avail.width()-80)` ×
   `min(860, avail.height()-80)`), com `setMinimumSize(layout().minimumSize())` em
   lugar de `(680, 620)`.
4. Responsividade: `QGridLayout` de duas colunas para os cartões de formulário a
   partir de 1100 px de largura útil e uma coluna abaixo disso, em `resizeEvent`
   idempotente (mover widgets, nunca recriar); container de conteúdo com
   `maximumWidth` (≈1160 px) centralizado para não esticar em 4K.

**Item 6 (densidade) no mesmo PR.** Cartões compactos: `Origem` (2 linhas), `Idioma`
(2 colunas: falado/final + política de tradução), `Destino` (1 linha com "Salvar
como…"), ações em barra fixa no rodapé. `Avançado` colapsável concentra faixa,
modelo/dispositivo e log detalhado. Remover subtítulos redundantes (viram placeholder
ou tooltip). Metas medidas: conteúdo sem log ≤ 780 px de altura sem rolagem em
1280×800; nenhuma rolagem horizontal em ≥ 1024 px.

**Sobre o formato "wizard".** Avaliado e **não recomendado como padrão**: acrescenta
estado de navegação, impede revisar o conjunto antes de iniciar e aumenta cliques no
fluxo dominante (um arquivo, um idioma, um destino). Registrado como opção futura se o
número de etapas crescer (lote, correção manual). Decisão final do dono do produto
(seção 8, D1).

**Testes novos.**

- `tests/gui/test_ui_state.py`: matriz `UiState × controle` sem Qt (função pura) e
  verificação de que a janela aplica exatamente a tabela.
- `tests/gui/test_window_geometry.py`: roundtrip `QByteArray`; clamp em telas
  virtuais 800×600 e 1920×1080; chave legada ilegível não lança.
- `tests/gui/test_maximize.py`: `showMaximized()` → `isMaximized()` verdadeiro e
  `size() == availableGeometry().size()`.
- `tests/gui/test_responsive_layout.py`: 1024/1280/1920 px, colunas esperadas e
  `content.width() <= viewport.width()`.
- `tests/gui/test_compact_layout.py`: altura do conteúdo (sem log) ≤ 780 px em 1280×800.

### 10.3. Feedback ao usuário: notificações em vez de log (C2 → itens 11, 13, 4)

**Diagnóstico.** `JobViewModel.report_error`/`report_warning`
(`view_model/job_view_model.py:92-116`) escrevem `"Erro: …"` em `log_lines`; o erro que
interrompe o processamento também entra em `log_lines` pelo evento `JobFailed` (`:188`)
e ainda vira `status_text`. A mesma falha aparece em dois ou três lugares, sempre como
texto corrido no histórico, sem severidade, ação ou destaque. `QMessageBox.information`
aparece só em `main_window.py:1405, 1418`, gerando inconsistência de linguagem.

**Mudanças.**

1. `presentation/qt/notifications.py`: `Notice(severity, message, detail, action)`,
   `NoticeCenter` (fila, dedupe por `(severity, message)`, 6 s para
   informativo/sucesso, persistente até "Ok" para erro, `Esc` dispensa) e `ToastHost`
   (canto inferior direito, sem moldura, cobre a janela, respeita o tema,
   `accessibleName` = mensagem).
2. `JobViewSnapshot` ganha `notices: tuple[Notice, ...]` e `log_entries:
   tuple[LogEntry, ...]` (`level ∈ {step, info, warning, error}`, `timestamp`,
   `text`). `report_error` cria **notice** e, no máximo, uma entrada de log de nível
   `error` — nunca dois textos divergentes.
3. Política única de severidade (documentada em OPERACAO):
   - bloqueio antes de iniciar → toast de erro + foco no campo culpado + pílula
     "Atenção";
   - falha durante execução → toast persistente com "Ver detalhes" (expande a
     atividade e rola até a última entrada);
   - avisos do pipeline → entrada de log nível `warning` + contador no cabeçalho da
     atividade (sem toast, para não poluir áudios longos);
   - sucesso → toast de sucesso com "Abrir pasta";
   - confirmações destrutivas (cancelar, sobrescrever) continuam modais.
4. Log: `QPlainTextEdit` → `QTextEdit` somente leitura com HTML por nível (cores do
   tema) ou delegate colorido; o histórico continua íntegro sem ser canal de erro.
5. `presentation/qt/messages.py`: catálogo `ErrorCategory → (título, orientação)`,
   para a UI parar de exibir `str(exc)` cru.

**Testes novos.**

- `tests/gui/test_notice_center.py`: fila, dedupe, timeout, `Esc`, acessibilidade.
- `tests/gui/test_error_flow.py`: erro de validação em `_build_job` não cria job, não
  polui o histórico, emite 1 notice e não abre modal.
- `tests/gui/test_failure_state.py`: após `JobFailed`, `UiState.FAILED` desabilita
  cancelar e rebaixa a variante visual (regressão do item 13).
- `tests/presentation/test_messages_catalog.py`: toda `ErrorCategory` tem mensagem e
  orientação.

### 10.4. Contrato de idiomas explícito e tradução implícita (C4 → itens 8, 9)

**Diagnóstico.** `_sync_translation_controls()` copia o idioma falado para o destino e
o desabilita quando a tradução não está ativa — por isso "seleciono inglês e o final
trava em inglês". Com tradução ativa o destino é liberado, mas `_build_job` exige
idioma falado explícito (auto-detecção proibida) e o pipeline só descobre a
incompatibilidade **depois** de transcrever (`serial_pipeline.py:88`). `Language`
cobre apenas `pt`/`en` (Decisão 3) e `Language.parse` levanta erro quando o Whisper
detecta outro idioma — também depois da transcrição.

**Mudanças.**

1. `application/language_plan.py`: `LanguagePlan(spoken: Language | None, target:
   Language | None, policy: TranslationPolicy)` com
   `TranslationPolicy ∈ {AUTO, ALWAYS, NEVER}` e `resolve(detected: Language | None)
   -> ResolvedPlan(transcribe_language, target_language, translate, notes)`. Regras:
   - falado conhecido e igual ao destino → `translate=False`, sem erro;
   - falado conhecido e diferente do destino → `translate=True`
     (tradução **implícita**, exatamente o que o usuário espera);
   - falado automático e destino fixo → `transcribe_language=None`; após a detecção,
     `translate = detected != target`, com nota quando coincidem;
   - `NEVER` com destino diferente do detectado → erro no **pré-voo**;
   - `ALWAYS` com destino igual ao detectado → nota e `translate=False`.
2. `JobRequest` passa a carregar a política (`translation_policy`), preservando
   `translate` por derivação; `SerialPipeline` deixa de ter a checagem `:83-91` e
   consome `ResolvedPlan` (mantém apenas asserção defensiva).
3. UI: o destino **nunca** é travado pelo falado. A UI mostra o valor derivado com
   selo "igual ao falado" e permite editar; editar promove a política para `ALWAYS`
   (ou `AUTO`, conforme o controle escolhido). Trocar o falado recalcula o derivado
   sem sobrescrever escolha explícita (flag `target_touched`).
4. O checkbox binário vira três opções de política: "Automático (traduz se
   necessário)", "Sempre traduzir para …", "Nunca traduzir". Auto-detecção **com**
   tradução passa a ser estado válido e suportado.
5. Escopo de idiomas: manter PT/EN (Decisão 3) e torná-lo **explícito** na UI
   ("Escopo atual: português e inglês"), derivando os dois combos de um registry único
   (`domain/value_objects/language.py`: `SUPPORTED_LANGUAGES` com código, rótulos,
   `alignable`, `translatable`). Resposta objetiva ao item 9: o Whisper transcreve
   ~99 idiomas, mas o produto é limitado por (i) tokenização Punkt do alinhador
   (hoje PT/EN), (ii) pares NLLB declarados em `NLLB_CODES`, (iii) catálogo de erros.
   Ampliar exige mapear os idiomas de `whisperx.alignment.PUNKT_LANGUAGES`, pesos
   wav2vec2 por idioma e novos pares NLLB — escopo de uma fase futura (Fase 11
   opcional), com o registry como único ponto de mudança. Até lá, idioma fora do
   escopo é rejeitado no pré-voo (falado fixado) ou na detecção barata anterior à
   transcrição completa (ver 10.6, camada 1).
6. `SUPPORTED_LANGUAGES` e `NLLB_CODES` passam a ser validados entre si por teste.

**Testes novos/reescritos.**

- `tests/application/test_language_plan.py`: matriz falado × destino × política ×
  detectado (inclui auto+tradução e idiomas coincidentes).
- `tests/gui/test_language_controls.py`: destravar/derivar sem sobrescrever escolha;
  auto-detecção + tradução habilitada; selo "igual ao falado".
- Reescrita justificada de `test_translation_job_request_requires_a_spoken_language`
  (o contrato muda por decisão de produto).
- `tests/domain/test_language_registry.py`: registry coerente com `NLLB_CODES` e com
  os rótulos exibidos.

### 10.5. Pré-voo e prontidão de recursos (C3+C5 → itens 9, 12)

**Diagnóstico (item 12, reproduzido).** `settings`/`model_cache`/`logging` criam diretórios
com `mkdir(parents=True, exist_ok=True)` **sem `mode`**, então herdam o `umask` (aqui
`0002` → `drwxrwxr-x`). O NLTK 3.10.4 recusa instalar em diretório (ou ancestral) gravável
por terceiros:

```
UserWarning: NLTK will not authorize the non-private download directory
'~/.cache/legendar/models/whisperx-align/nltk_data': it (or an ancestor) is
world- or group-writable, so another local user could plant files there.
Refusing to install into '...': it is writable by, or owned by, another
account, so a file swapped in during the install would be installed as
trusted data. Make it private to its owner (chmod go-w).
result False
```

Ou seja: `_ensure_punkt_data()` só é chamado no alinhamento e falha **depois** de a
transcrição já ter consumido minutos de GPU/CPU. `chmod -R go-w` no cache faz o download
passar (verificado), o que confirma a causa. O cache é compartilhado por Whisper,
WhisperX e NLLB, então a mesma classe de problema atinge os três modelos.

**Mudanças.**

1. `settings.ensure_directories()` cria `cache/`, `logs/`, `tmp/` com `mode=0o700` e
   corrige permissões de diretórios existentes de forma idempotente e best-effort
   (falha de `chmod` não derruba o app, apenas registra diagnóstico).
2. `application/preflight.py`: `PreflightCheck` (protocolo), `PreflightReport(ok,
   blockers, warnings, details)` e checks:
   1. mídia existe, é arquivo, legível, não vazia e de extensão suportada;
   2. destino gravável/existente/diretório, com espaço livre mínimo por modelo;
   3. `LanguagePlan` coerente (`resolve`) e tradutor disponível quando necessário;
   4. modelos presentes em disco (whisper, alinhador wav2vec2, NLLB) com tamanho
      esperado;
   5. **`punkt_tab` presente** para o idioma de alinhamento (checagem, sem download);
   6. `ffmpeg`/`ffprobe` no PATH e versão mínima;
   7. dispositivo coerente com a preferência (CUDA/MPS/CPU) e VRAM mínima estimada.
3. Chamadas: (a) no clique de "Gerar legenda", **antes** de criar workspace/worker —
   bloqueadores viram notice de erro e nada roda; (b) em background no boot para
   alimentar o chip "Ambiente pronto" (10.7).
4. `punkt_tab` sem rede: `resources/nltk_data/tokenizers/punkt_tab/{english,
   portuguese}/` vendorizado (licença Apache-2.0, ~1,4 MB) e copiado para o cache no
   primeiro uso com `shutil.copytree` + `chmod` 0o600/0o700. Fallback de download só
   com `LEGENDAR_ALLOW_DOWNLOAD=1` (explícito, opt-in). Alinhador recebe
   `NLTK_DATA` apontando para o cache curado.
5. Falha de recurso passa a trazer `technical_detail` + remediação ("rode
   `legendar --doctor`", "instale ffmpeg via apt"), nunca só o texto da exceção.

**Testes novos.**

- `tests/application/test_preflight.py`: um teste por check (mídia inexistente,
  destino somente-leitura, espaço insuficiente, modelo ausente, punkt ausente,
  ffmpeg ausente) — todos sem tocar em rede/GPU (fakes).
- `tests/infrastructure/test_punkt_bootstrap.py`: cache recém-criado com `0o700`,
  seed copiado, `nltk.data.find` resolve sem rede. Regressão direta do item 12.
- `tests/gui/test_preflight_blocks_start.py`: com bloqueador, nenhum worker é criado
  e aparece 1 notice de erro com o campo em foco.

### 10.6. Transparência das etapas longas (C6 → item 7)

**Diagnóstico.** A faixa de transcrição é 15%–55% do progresso e não emite **nenhuma**
atualização intermediária por 10–20 min. Verificado na API instalada:
`openai-whisper` não expõe `progress_callback` (apenas `verbose`, que governa o tqdm em
stderr) e `whisperx.transcribe/align` **expõem** `progress_callback`. O usuário não
distingue "trabalhando" de "travado", e o cancelamento só tem efeito depois da etapa.

**Mudanças em três camadas, da mais barata à mais estrutural.**

1. **Heartbeat no view model (obrigatório).** `QTimer` de 1 s atualiza
   `status_detail` com etapa e tempo decorrido e ETA por throughput real (áudio
   processado ÷ tempo), exibindo "Transcrevendo · 07:12 decorridos · ~04:30
   restantes". ETA nunca estimado por chute; sem amostra suficiente, mostra só o
   decorrido. Não polui o histórico.
2. **Transcrição em blocos com `clip_timestamps` (recomendado).** Dividir o áudio em
   janelas de ~5 min (configurável) chamando `model.transcribe(waveform,
   clip_timestamps=[start, end], initial_prompt=<cauda anterior>,
   condition_on_previous_text=False)` em laço → progresso real ("bloco 37 de 58"),
   cancelamento entre blocos e detecção de estagnação por bloco. Mitigação de borda:
   1 s de sobreposição e `initial_prompt` com a cauda anterior; validação obrigatória
   no corpus de homologação (WER e emenda de texto) antes de ativar por padrão, com
   flag para desligar.
3. **Alinhador com progresso nativo (obrigatório).** Passar `progress_callback` ao
   `whisperx.align()` para que a faixa 55%–82% (hoje também caixa-preta) reporte por
   segmento.
4. **Opcional (ADR-10-3).** Migrar o ASR para `whisperx.transcribe(..., progress_callback)`
   com batching por VAD: progresso nativo e ganho de velocidade em CPU. Só executado se
   a camada 2 não atingir o critério de aceite, com critérios de saída registrados.
5. Rebalancear `_STAGE_RANGES` com pesos medidos (a transcrição deixou de ser 40% do
   tempo total em áudios longos) e adicionar watchdog: sem atualização por N minutos
   → mensagem "ainda trabalhando", nunca erro.

**Testes novos.**

- `tests/presentation/test_progress_heartbeat.py`: com relógio falso, 1 s produz texto
  de decorrido; sem amostras, não inventa ETA.
- `tests/infrastructure/test_chunked_transcription.py`: fakes de modelo verificam
  número de chamadas, `clip_timestamps` contíguos, sobreposição e emenda de texto;
  cancelamento entre blocos interrompe o laço.
- `tests/application/test_stage_ranges.py`: soma 100% e monotonicidade por etapa.

### 10.7. Chassi de UI: dropdowns, rodapé, faixas e marca (C1+C7 → itens 3, 4, 5, 10)

**a) Dropdowns (item 3).** Causa provada: o QSS aplica `padding`/`border` ao item, mas
a altura da popup é calculada por `sizeHintForRow` (26 px), então o segundo item exige
rolagem e o popup fica cortado dentro do `QScrollArea`. Correção: regra
`QComboBox QAbstractItemView::item { min-height: 30px; padding: 4px 10px; }`,
`setMaxVisibleItems(12)`, view sem `spacing`, e uma fábrica única
`presentation/qt/widgets.py::make_combo()` usada pelas cinco combos (origem, falado,
final, faixa, formato) — garantindo que novas combos nasçam corretas. Teste obrigatório:
para cada `QComboBox` da janela, abrir o popup e afirmar que a última linha está
integralmente visível e que ≤ 12 itens não exigem rolagem.

**b) Rodapé (item 4).** Trocar a parede de `readiness_details` por: pílula "Ambiente
pronto"/"Atenção" + botão "Diagnóstico" (`DiagnosticsDialog` com versões, caminhos,
cache, permissões, teste de `punkt` e "Copiar") + uma linha de versão. Detalhes vão
para o arquivo de log em `~/.cache/legendar/logs`, não para a tela.

**c) Faixas (item 10).** A faixa é dado derivado de `MediaInfo`: com uma única faixa,
exibir "Faixa 0 · aac · stereo · 48 kHz" desabilitado, com tooltip explicando origem e
que canais são informativos. A inspeção passa a ocorrer automaticamente ao escolher o
arquivo (com debounce) e o botão vira "Reinspecionar" — eliminando o estado em que a
UI permite escolher faixa inexistente.

**d) Marca (item 5).** Criar `assets/branding/` com `legendar-mark.svg` (símbolo de
legenda/onda + "L" geométrico, gradiente `#4659d8 → #9aa7ff`), `legendar-wordmark.svg`,
PNGs 16/24/32/48/64/128/256/512/1024, `legendar.ico` (Windows), `legendar.icns`
(macOS), `social-preview.png` (1280×630) e `avatar.png` (512×512). Uso:
`QApplication.setWindowIcon` com múltiplas resoluções no `QIcon` (HiDPI),
`setDesktopFileName("legendar")` para o WM associar a janela ao `.desktop`
(X11/Wayland), `MainWindow.setWindowIcon` e o `brandMark` do cabeçalho virando pixmap
2× com fallback SVG via `QtSvg` (acompanha o tema). Empacotamento:
`packaging/legendar.desktop` (`Icon=legendar`, `StartupWMClass=legendar`,
`Categories=AudioVideo;Audio;`) + `scripts/install_desktop_entry.sh` (copia ícones
para `~/.local/share/icons/hicolor/<size>/apps/`, instala o `.desktop`, roda
`update-desktop-database`), `--icon` documentado em INSTALACAO para PyInstaller e
cabeçalho com wordmark no README. `scripts/make_brand_assets.py` gera os binários a
partir do SVG usando apenas PySide6 (`QSvgRenderer` + `QPainter`) e escreve o ICO com
payload PNG (sem Pillow, que não é dependência). Observação: produto desktop não tem
"favicon"; o equivalente é ícone de janela/taskbar — se houver site de docs no futuro,
o `favicon.ico` sai do mesmo SVG (registrado, não implementado agora).

**Testes novos.**

- `tests/gui/test_combos_popup.py`: largura/altura do popup, última linha visível,
  `maxVisibleItems` respeitado em todas as combos.
- `tests/gui/test_brand_assets.py`: todos os tamanhos existem, PNGs decodificam,
  `.desktop` tem `Icon`/`StartupWMClass` e arquivo de ícone correspondente.
- `tests/gui/test_status_footer.py`: rodapé não expõe caminhos absolutos nem versões.

---

## 4. Rastreabilidade: os 13 achados → vertente → teste

| # | Achado da homologação | Causa | Vertente | Teste de aceite |
|---|---|---|---|---|
| 1 | Tema escuro com áreas claras | C1 | 10.1 | `test_theme_render`, `test_palette_coverage` |
| 2 | Janela cortada / maximizar errado | C2+C7 | 10.2 | `test_window_geometry`, `test_maximize`, `test_responsive_layout` |
| 3 | Dropdown de origem cortado | C1+C7 | 10.1, 10.7a | `test_combos_popup`, `test_qss_state_matrix` |
| 4 | Rodapé com detalhes técnicos | C7 | 10.7b | `test_status_footer` |
| 5 | Sem logo/ícone/identidade | — | 10.7d | `test_brand_assets` |
| 6 | Tela extensa demais | C7 | 10.2 | `test_compact_layout` |
| 7 | Progresso da transcrição grosseiro | C6 | 10.6 | `test_progress_heartbeat`, `test_chunked_transcription` |
| 8 | Idioma final travado no falado | C4 | 10.4 | `test_language_controls` |
| 9 | Erro de idiomas só no fim + tradução com auto-detecção | C3+C4+C5 | 10.4, 10.5 | `test_language_plan`, `test_preflight` |
| 10 | Faixa editável com 1 faixa | C7 | 10.7c | `test_preflight`, `test_main_window` (faixa) |
| 11 | Erro só no histórico | C2 | 10.3 | `test_error_flow`, `test_notice_center` |
| 12 | `punkt_tab` falha no alinhamento | C5 | 10.5 | `test_punkt_bootstrap`, `test_preflight` |
| 13 | Botões inconsistentes após erro | C2 | 10.1, 10.2, 10.3 | `test_qss_state_matrix`, `test_ui_state`, `test_failure_state` |

Cada linha tem teste automatizado: nenhum achado é encerrado por inspeção visual.

## 5. Ordem de execução, esforço e dependências

| Ordem | Vertente | Por que nesta posição | Esforço |
|---|---|---|---|
| 1 | 10.1 Tema | Base visual de tudo; sem ela o QSS `:disabled` continua enganando | 2 sessões |
| 2 | 10.2 Estado + janela + densidade | Elimina 2, 6, 13 e destrava medições estáveis | 3 sessões |
| 3 | 10.5 Pré-voo + `punkt_tab` | Desbloqueia o fail-fast do item 9 e o desbloqueio do caminho offline | 2 sessões |
| 4 | 10.4 Idiomas | Depende do pré-voo para validar cedo; maior impacto no fluxo | 2 sessões |
| 5 | 10.3 Notificações | Depende de 10.2 (estados) e serve 10.4/10.5 para reportar bloqueios | 2 sessões |
| 6 | 10.7 Dropdowns, rodapé, faixas, marca | Independente; consolida o acabamento | 2 sessões |
| 7 | 10.6 Progresso | Maior risco de qualidade (emenda de texto); último | 3 sessões |

**Marcos de re-homologação.** Ao fim das vertentes 1–2 é possível reavaliar 1, 2, 3, 6,
13 (UI). Ao fim de 3–5, os fluxos 8, 9, 11, 12. A 10.7 e a 10.6 fecham 4, 5, 7, 10.

**Não-objetivos desta fase.** (i) ampliar idiomas além de PT/EN (depende de Punkt e NLLB,
Fase 11 candidata); (ii) trocar o motor de ASR por whisper.cpp/faster-whisper (avaliado
em ADR própria); (iii) internacionalização da UI (textos em PT-BR apenas, como hoje);
(iv) instaladores assinados.

## 6. Validação e critérios de aceite globais

**Comandos obrigatórios antes de pedir re-homologação:**

```bash
uv run ruff check .
uv run pytest -q
QT_QPA_PLATFORM=offscreen uv run pytest -q -m gui
uv run python scripts/check_doc_links.py
```

**Critérios globais (todos verificáveis, nenhum subjetivo):**

| ID | Critério |
|---|---|
| G1 | Render escuro não tem nenhum ponto com luminância ≥ 200 (fora de texto e do preenchimento do progresso) em 1280×800 |
| G2 | Janela abre no tamanho salvo, nunca maior que `availableGeometry()`, e restaura o estado maximizado |
| G3 | Nenhum popup de combo corta o último item; ≤ 12 itens não exigem rolagem |
| G4 | Conteúdo sem log cabe em 1280×800 sem rolagem vertical e sem rolagem horizontal em ≥ 1024 px |
| G5 | Toda falha bloqueante produz exatamente 1 notice visível, 0 `QMessageBox` para erro e 0 linha de erro duplicada no histórico |
| G6 | Em qualquer estado terminal, nenhum botão fica visualmente habilitado sem estar habilitado de fato (matriz `UiState × controle`) |
| G7 | Idioma final pode ser diferente do falado sem travar o campo; auto-detecção + tradução é aceita; par impossível é rejeitado em < 1 s, antes de qualquer transcrição |
| G8 | `punkt_tab` presente sem rede (seed vendorizado) e cache `0o700`; alinhamento completa em máquina limpa e offline |
| G9 | Etapa de transcrição reporta progresso em intervalos ≤ 30 s e ETA baseado em throughput |
| G10 | `setWindowIcon` + `.desktop` fazem o ícone da marca aparecer na janela, taskbar e lançador |

**Re-homologação:** repetir os 13 cenários originais de [HOMOLOGACAO.md](HOMOLOGACAO.md)
mais três cenários novos: (a) cache com permissões hostis prévias, (b) execução sem rede
(MOCK de download) e (c) tela 1366×768.

## 7. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Transcrição em blocos degrada emenda de texto (item 7, camada 2) | média | alto | sobreposição + `initial_prompt`, validação em corpus antes de virar padrão, flag de desligamento |
| QSS + Fusion mudam métricas e quebram layouts existentes | alta | médio | testes de layout da 10.2 na mesma bateria; nenhum ajuste só visual sem teste |
| Refatoração de estados (10.2) quebra fluxos existentes | média | alto | matriz pura testável + manter `_render` como adaptador temporário até a matriz cobrir todos os controles |
| Vendorizar `punkt_tab` aumenta o repositório em ~1,4 MB | certa | baixo | aceitável; alternativa (download em runtime) é justamente o defeito 12 |
| Notificações não modais passam despercebidas | média | médio | persistência para erro + pílula de status + acessibilidade; erro de execução nunca expira sozinho |
| Mudança de contrato de idiomas quebra testes existentes | alta | baixo | reescrita justificada documentada na seção 10.4 e no HANDOFF |
| Tradução implícita surpreende quem não quer traduzir | baixa | médio | política explícita na UI (`AUTO`/`ALWAYS`/`NEVER`) e mensagem no resumo do job ("traduzir EN→PT") |

## 8. Decisões abertas (precisam do dono do produto)

| ID | Decisão | Opções | Recomendação |
|---|---|---|---|
| D1 | Formato da tela principal | página única compacta (2 colunas) vs. wizard | página única compacta; wizard só se o fluxo ganhar etapas |
| D2 | Controle de tradução | política `AUTO` como padrão vs. manter checkbox binário | `AUTO`, que cobre "traduzir se necessário" e torna auto-detecção+tradução válida |
| D3 | Escopo de idiomas | manter PT/EN vs. ampliar alinhamento para todos os idiomas com Punkt/wav2vec2 | manter PT/EN nesta fase, com escopo explícito na UI; ampliação em fase própria |
| D4 | Progresso real na transcrição | aceitar bloco com `clip_timestamps` vs. migrar para WhisperX com `progress_callback` | blocos (menor mudança); reavaliar com as medições |
| D5 | Canal de erro em execução | toast persistente com ação vs. modal | toast persistente; modal só para confirmação destrutiva |
| D6 | Distribuição do ícone | `.desktop` por script vs. pacote de instalação | script nesta fase; pacote quando houver instalador |

Decisões aprovadas aqui devem ser registradas em [DECISOES.md](DECISOES.md) antes da
implementação correspondente.

## 9. Sequência de PRs sugerida

| PR | Conteúdo | Definido como pronto quando |
|---|---|---|
| PR-1 | 10.1 tema: `Theme` dataclass, `apply_theme`, QSS completo, remoção de QSS inline | G1 + testes de tema verdes; nenhum widget órfão do QSS |
| PR-2 | 10.2 estados + geometria + densidade | G2, G4, G6 + matriz `UiState` cobrindo todos os controles |
| PR-3 | 10.5 pré-voo + `punkt_tab` vendorizado + permissões 0o700 | G8 + testes de pré-voo; cenário offline validado |
| PR-4 | 10.4 contrato de idiomas + registry | G7 + matriz de `LanguagePlan` |
| PR-5 | 10.3 notificações + log com níveis + catálogo de mensagens | G5 + testes de fluxo de erro |
| PR-6 | 10.7 dropdowns, rodapé/diagnóstico, faixas, marca | G3, G10 + assets versionados |
| PR-7 | 10.6 progresso (heartbeat + alinhador + blocos) | G9 + validação de emenda no corpus |

Cada PR atualiza o `docs/HANDOFF_FASE_10.md` (a criar no início do PR-1) com o que mudou,
evidências novas e o que ficou pendente, no mesmo formato dos handoffs anteriores.

## 10. Registro desta análise

- Nenhum arquivo de `src/` foi alterado: este documento é **plano**, não implementação.
- Todas as causas da seção 1 foram reproduzidas localmente com sondas descartáveis
  (render offscreen, medição de `sizeHint`/`minimumSizeHint`, roundtrip de `QSettings`,
  `showPopup` + `visualRect`, e execução real de `nltk.download` no cache do produto).
- As sondas **não** foram versionadas de propósito: cada uma delas deve renascer como
  teste de regressão permanente na vertente correspondente (ver "Testes novos").
- O que segue sem prova direta é apenas o comportamento do "botão maximizar" no
  gerenciador de janelas do usuário (XFCE); por isso o critério G2 é medido por
  `showMaximized()` + `availableGeometry()`, que independe do WM.
