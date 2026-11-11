# Handoff técnico — Fase 7: integração de ponta a ponta da GUI

- **Status:** implementação concluída na branch `phase-7/gui-pipeline-integration`, com suíte determinística verde e integração por squash na `main`.
- **Plano operacional:** [FASE_7_PLANO.md](FASE_7_PLANO.md)
- **Fronteira:** a janela executa o pipeline real, sem simulação, com progresso, cancelamento, log e recuperação.
- **Fora de escopo:** homologação com mídia real, modelos completos e corpus humano (Fase 8).

## 1. Arquitetura entregue

| Arquivo | Responsabilidade |
|---|---|
| `src/legendar/presentation/qt/main_window.py` | Confirmação, montagem do `JobRequest`/`JobContext`, `QThread`, renderização do snapshot, cancelamento, fechamento seguro e abertura da pasta publicada |
| `src/legendar/presentation/qt/workers/job_worker.py` | `JobController.run` na thread de trabalho; `event_received` e `completed` |
| `src/legendar/presentation/qt/workers/media_inspection_worker.py` | Inspeção ffprobe em `QThread` com token próprio |
| `src/legendar/presentation/qt/view_model/job_view_model.py` | Eventos → `JobViewSnapshot`: estado, progresso, log, saída, erro e permissões |
| `src/legendar/presentation/qt/dialogs.py` | Resumo de confirmação, substituição de arquivo e preferências |
| `src/legendar/bootstrap/app.py` | Composição das portas reais e preflight de FFmpeg, Whisper, WhisperX, NLLB e yt-dlp |

## 2. Modelo de threads

1. A janela vive na thread principal do Qt e nunca executa FFmpeg, Whisper, WhisperX, NLLB ou rede.
2. `JobWorker` é movido para `QThread`; `thread.started → worker.run`; `worker.completed → thread.quit` em conexão direta.
3. Eventos atravessam por `Signal(object)` em conexão enfileirada; a UI só é tocada na thread principal.
4. `thread.finished` libera worker, thread e contexto; o workspace é limpo em `_on_job_finished`.
5. A inspeção de mídia usa uma `QThread` dedicada que executa ffprobe em `run()`, sem QObject worker separado.

Consequência prática: qualquer bloqueio de I/O em uma nova etapa deve continuar dentro de adaptadores, nunca em um slot da janela.

## 3. Estados e permissões

O controlador é a única autoridade de transição. A janela apenas renderiza:

| Snapshot | Gerar | Cancelar | Campos | Abrir pasta |
|---|---|---|---|---|
| `IDLE` / terminal | habilitado quando o ambiente está pronto | desabilitado | habilitados | habilitado se houver SRT desta sessão |
| Etapas ativas | desabilitado | habilitado até o primeiro pedido | bloqueados | desabilitado |
| `CANCELLING` | desabilitado | desabilitado | bloqueados | desabilitado |
| `PUBLISHING` | desabilitado | recusado com explicação | bloqueados | desabilitado |

O indicador do cabeçalho resume o estado: ambiente pronto, em andamento, concluído, cancelado, atenção necessária.

## 4. Cancelamento e encerramento

- `JobWorker.request_cancel` delega a `JobController.cancel`, que retorna `False` fora de etapa cancelável.
- O token é consultado nas fronteiras de etapa, entre lotes de tradução e nos adaptadores de subprocesso.
- A publicação não consulta cancelamento: depois da troca atômica, o job é concluído.
- Fechar a janela durante o trabalho pede confirmação, solicita cancelamento e espera até 5 s; se não encerrar, o fechamento é recusado com mensagem no painel.
- Cancelar a inspeção usa o token da `MediaInspectionWorker` e restaura os controles ao final.

## 5. Erros e recuperação

- Erros de domínio chegam como `JobFailed` com `category`, mensagem e detalhe técnico; a UI mostra a mensagem e mantém o log.
- Falhas de preparação (validação de entrada, workspace, criação do worker) são capturadas antes da thread e limpam o workspace parcial.
- O SRT anterior permanece intacto em qualquer falha: a publicação só troca o arquivo depois do roundtrip.
- Após falha ou cancelamento, os campos voltam a ficar ativos e o usuário pode corrigir a entrada e tentar novamente.
- A limpeza do diretório temporário nunca derruba a janela: falhas viram aviso no log.

## 6. Resultado publicado

- `JobCompleted` traz `output_path` e `cue_count`; a barra de status mostra o caminho salvo.
- **Abrir pasta** habilita somente quando existe SRT desta sessão e o diretório existe.
- A abertura usa `QDesktopServices.openUrl(QUrl.fromLocalFile(...))`; falha do sistema é reportada na barra de status, sem exceção.
- Um novo job limpa o estado anterior, desabilitando o botão até a próxima publicação.


## 7. Evidências de teste

| Arquivo | Cobre |
|---|---|
| `tests/gui/test_main_window.py` | 39 testes offscreen: fluxo completo, reentrância, confirmações, cancelamento aceito e recusado, progresso indeterminado, log recolhível, inspeção cancelável, fechamento durante o job, pasta do SRT |
| `tests/gui/test_dialogs.py` | Resumo de confirmação, escolha padrão segura e preferências |
| `tests/unit/presentation/test_job_view_model.py` | Mapeamento de eventos, log limitado e permissões |
| `tests/unit/presentation/test_preferences.py` | Persistência QSettings de tema, idioma e log |
| `tests/integration/test_translation_publication.py` | Pipeline real com publicador real, sem GUI |
| `tests/test_architecture.py` | Isolamento de domínio, portas e dependências opcionais |

Comando local:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked --no-sync pytest -q tests/gui tests/unit/presentation
```

## 8. Decisões congeladas

1. O pipeline é criado por `pipeline_factory` a cada job; não há reutilização de pipeline entre execuções.
2. O workspace é criado antes da thread e descartado em qualquer caminho terminal.
3. A confirmação de início acontece antes da criação do workspace; recusar não deixa lixo em disco.
4. O botão de gerar valida o ambiente (FFmpeg, Whisper, WhisperX, publicador, YouTube) antes de abrir o diálogo.
5. O caminho de saída não pode sobrescrever a mídia, ficar dentro do cache de modelos nem terminar sem `.srt`.
6. A pasta publicada é aberta pelo serviço de desktop e nunca por `subprocess` próprio.

## 9. Limites conhecidos

- Cancelamento não interrompe uma inferência em andamento; é observado na próxima fronteira segura.
- Fechar durante `PUBLISHING` é recusado para não interromper a troca atômica.
- O log é limitado a 500 linhas; o histórico completo fica nos arquivos de log da aplicação.
- A UI não corrige automaticamente idioma detectado divergente: apenas reporta o aviso do pipeline.
- Não há fila de jobs: uma instância processa um trabalho por vez.

## 10. Próxima fronteira

A Fase 8 deve produzir a matriz de testes e homologação: unitários, integração com FFmpeg/ffprobe reais, GUI, E2E dos quatro pares de idioma, modos de falha, relatório de regressão e gates de CI com cobertura. A homologação humana de tradução, precisão temporal e leitura em mídia real permanece explicitamente atribuída ao usuário nesta fase.
