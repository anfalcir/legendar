# Handoff — Fase 10: correções pós-homologação

- **Status:** implementado e verificado localmente; aguarda homologação do usuário.
- **CI:** run [#43030902623](https://github.com/anfalcir/legendar/actions/runs/43030902623) aprovado em 5/5 jobs (Python 3.10–3.13 + documentação).
- **Origem:** 13 achados da rodada de 11/11/2026, registrados em
  [HOMOLOGACAO.md](HOMOLOGACAO.md) e provados em [FASE_10_PLANO.md](FASE_10_PLANO.md).
- **Regra desta fase:** nenhuma correção de sintoma. Cada achado recebeu a causa
  sistêmica correspondente e um teste que falha se a causa voltar.

---

## 1. O que mudou, achado por achado

| # | Achado | Causa corrigida | Evidência automatizada |
|---|---|---|---|
| 1 | Tema escuro com pedaços claros | `apply_theme()` aplica Fusion + paleta completa + QSS no `QApplication`; QSS cobre menus, tooltips, popups de combo, barra horizontal, viewport do scroll e `[variant="danger"]:disabled` | `tests/unit/presentation/test_theme.py` |
| 2 | Janela cortada, maximizar falhava | geometria salva como `QByteArray`, lida com `_as_byte_array`, reencaixada na tela atual, `window/maximized` persistido e piso mínimo derivado do layout | `tests/gui/test_window_geometry.py` |
| 3 | Dropdown de origem cortado | `prepare_combo()` instala `ComboItemDelegate`, que soma o respiro do QSS ao `sizeHint` (o Qt mede o delegate padrão) | `tests/gui/test_widgets.py` |
| 4 | Rodapé com textos cinzas redundantes | rodapé diz uma frase; inventário técnico vai para tooltip e log; o rótulo de faixa só aparece quando há informação real; painel de detalhes recolhido por padrão | `tests/gui/test_main_window.py` |
| 5 | Sem logo, ícone ou identidade | `assets/legendar.svg` + `branding.app_icon()` com desenho de reserva; ícone no `QApplication` e na janela; `packaging/legendar.desktop` | inspeção visual offscreen + `test_widgets.py` |
| 6 | Tela muito extensa | cartões compactos, duas colunas para idioma/destino com reflow em 940 px, campos de idioma empilhados em janela estreita, largura máxima de 1180 px, subtítulos redundantes removidos | `test_content_height_stays_compact_without_the_log`, `test_narrow_window_stacks_the_form_without_clipping_labels` |
| 7 | “Transcrevendo” sem subetapas por 15 min | relógio visível por etapa (`QTimer` + `_format_elapsed`): “Transcrevendo · 4 min 12 s · sem percentual medido” | `test_elapsed_labels_are_human_readable` |
| 8 | Idioma falado travava o idioma final | campos independentes; a consequência aparece em `language_hint`; “mesmo idioma + tradução” virou no-op explicado, não erro | `test_source_language_does_not_hijack_the_target_language` |
| 9 | Erro de par de idiomas só após 15 min | validação permanece no pré-voo (`_build_job` → `_resolved_languages`), com mensagem acionável e sem depender do pipeline | `test_without_translation_the_target_must_match_the_spoken_language` |
| 10 | Faixa editável apesar de única | `_stream_choice_available()` exige mais de uma faixa; faixa única fica desabilitada com tooltip | `test_single_audio_stream_is_not_editable` |
| 11 | Erro registrado só no histórico | `JobViewSnapshot.notice_*` + `QLabel#alertBanner` no topo, com severidade e tooltip para o log; limpo ao iniciar o próximo job | `test_local_validation_failure_is_shown_in_a_banner` |
| 12 | NLTK `punkt_tab` falhava após 11 min | `ensure_private_directory()` cria/corrige cache em `0o700` (umask 002) antes de qualquer download; o zip baixado é removido | `tests/unit/infrastructure/test_paths.py` |
| 13 | Botões inconsistentes após falha | estados de `danger`/`ghost` desabilitados no QSS; `_render` segue como único ponto que habilita controles | `tests/unit/presentation/test_theme.py` |

## 2. Decisões adotadas nesta rodada (D1–D6)

Registradas em [DECISOES.md](DECISOES.md), seção “Fase 10”. São o padrão
recomendado no plano e continuam reversíveis se a homologação indicar o
contrário.

| # | Tema | Decisão adotada |
|---|---|---|
| D1 | Navegação | página única compacta (sem wizard); formulário em uma ou duas colunas |
| D2 | Política de tradução | tradução opcional (AUTO): sem tradução, a legenda sai no idioma falado; “mesmo idioma” não consome etapa de tradução |
| D3 | Pares de idiomas | mantidos PT-BR e inglês |
| D4 | Progresso | percentual quando existe medida; relógio de etapa quando não existe |
| D5 | Notificações | banner persistente no topo + status bar; log continua com o detalhe |
| D6 | Distribuição Linux | `.desktop` em `packaging/`; PyInstaller segue pendente |

## 3. Como verificar (roteiro mínimo)

```bash
cd ~/Documentos/Codes/legendar
export PATH="$PWD/ffmpeg/bin:$PATH"
PYTHONPATH=src uv run --locked --no-sync python -m legendar
```

1. **Tema** — Preferências → Escuro. Abra um combo, um tooltip e uma barra de
   rolagem horizontal: nada deve ficar claro. Feche e reabra: o tema persiste.
2. **Geometria** — redimensione a janela (ex.: 900×700), feche e reabra: o
   tamanho é restaurado. Maximize, feche e reabra: continua maximizada.
3. **Combos** — abra o combo de idioma falado: “Detectar automaticamente” e
   “Português (BR)” aparecem inteiros, sem barra e sem sobreposição.
4. **Idioma** — falado = Inglês e final = Português (BR) sem tradução: o campo
   final continua editável e a frase explica o efeito. Marque a tradução e
   confirme que o resumo mostra o par correto.
5. **Faixa única** — mídia com uma só faixa de áudio: “Inspecionar faixas”
   deixa o campo desabilitado, com tooltip explicando o motivo.
6. **Feedback** — tente gerar sem selecionar arquivo: a mensagem aparece em
   banner no topo (vermelho para erro, âmbar para aviso) e no log.
7. **Compactação** — 1280×800 com o painel de detalhes recolhido: sem rolagem
   vertical; em 1024 px de largura os cartões empilham.
8. **Punkt/NLTK** — `ls -ld ~/.cache/legendar/models/nltk_data` deve mostrar
   `drwx------` (ou ser criado assim no primeiro alinhamento).

## 4. Limites conhecidos (não são regressões)

- **Whisper não expõe progresso por trecho.** O relógio de etapa dá sinal de
  vida, mas não percentual real; medir por `clip_timestamps` exige fatiar áudio
  e muda o resultado da transcrição — decisão adiada.
- **Empacotamento** continua não homologado: PyInstaller precisa incluir
  `src/legendar/presentation/qt/assets/` quando o fluxo for criado.
- **Ícone SVG** depende do plugin de imagem SVG; sem ele o desenho de reserva
  (`branding._painted_icon`) assume, então a janela nunca fica sem ícone.
- **Acessibilidade fina** (contraste medido, leitor de tela) segue como
  verificação manual na seção 9 de [HOMOLOGACAO.md](HOMOLOGACAO.md).

## 5. Mapa dos arquivos tocados

| Arquivo | Papel |
|---|---|
| `presentation/qt/theme.py` | `palette_for`, `apply_theme`, QSS completo (menus, tooltips, popups, barras, banner) |
| `presentation/qt/widgets.py` | `ComboItemDelegate` e `prepare_combo` |
| `presentation/qt/branding.py` + `assets/legendar.svg` | ícone e marca |
| `presentation/qt/main_window.py` | tema na aplicação, geometria tipada, layout compacto/responsivo, banner, relógio de etapa, idioma desacoplado, faixa única, rodapé enxuto |
| `presentation/qt/preferences.py` | geometria `QByteArray` e `window/maximized` |
| `presentation/qt/view_model/job_view_model.py` | `notice_message`/`notice_level` |
| `presentation/qt/dialogs.py` | combos preparados, título sem QSS inline |
| `infrastructure/filesystem/paths.py` | `ensure_private_directory` |
| `infrastructure/alignment/whisperx.py` | cache do NLTK privado e limpeza do zip |
| `infrastructure/config/settings.py` | cache/temp privados na criação |
| `bootstrap/app.py` | ícone do aplicativo |
| `packaging/legendar.desktop` | integração com o ambiente Linux |

