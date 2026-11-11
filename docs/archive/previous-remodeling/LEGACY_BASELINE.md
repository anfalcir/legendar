# Baseline legada — contratos caracterizados e política de migração

- **Projeto:** Legendar
- **Atualização:** 10/11/2026
- **Escopo:** aplicação anterior em `main.py`, `core/` e `gui/`
- **Status:** caracterizada e preservada como baseline histórica/compatibilidade
- **Não confundir com:** a nova arquitetura em `src/legendar/`

Este documento registra o que a aplicação anterior efetivamente faz, os limites que foram
verificados por testes e a política para sua convivência temporária com a arquitetura nova.
Não representa recomendação de arquitetura para funcionalidades novas.

## 1. Inventário da baseline

```text
main.py
core/
  __init__.py
  instagram.py
  transcription.py
  youtube.py
gui/
  __init__.py
  styles.py
  ui_main.py
  worker.py
```

A aplicação legada é uma GUI PySide6 com duas abas expostas: YouTube e arquivo MP4. O
trabalho é delegado a subclasses de `QThread`; o resultado é texto simples UTF-8 em
`.txt`, não SRT.

## 2. Contratos observados e caracterizados

| Área | Comportamento observado | Evidência automatizada |
|---|---|---|
| Inicialização | `main.py` cria `QApplication`, mostra `gui.ui_main.MainWindow` e entra no event loop | Compilação dos fontes legados; inspeção do entrypoint |
| Interface | Abas visíveis YouTube e Arquivo MP4; a aba Instagram está comentada | `test_legacy_window_exposes_youtube_and_mp4_tabs_and_rejects_other_formats` |
| Arquivo local | A entrada deve existir e ter extensão `.mp4`; a saída é escolhida em diretório separado | Mesmo teste da interface |
| Reconhecimento | Carrega `whisper.load_model("base")`, chama `model.transcribe(path)` e grava a chave `text` em UTF-8 sem normalização adicional | `test_legacy_transcription_loads_base_model_and_writes_utf8` |
| FFmpeg empacotado | Quando existe `ffmpeg/bin` ao lado do bundle, o diretório é anteposto a `PATH` apenas uma vez | `test_legacy_transcription_prepends_bundled_ffmpeg_only_once` |
| YouTube | `yt_dlp` seleciona `bestaudio/best`, usa o caminho de FFmpeg resolvido pelo helper e extrai MP3 em qualidade 192 | `test_legacy_youtube_download_uses_audio_extraction_and_bundled_ffmpeg` |
| Nome de saída | Arquivos existentes recebem sufixos incrementais (`nome_1.txt`, `nome_2.txt` etc.) | `test_legacy_worker_allocates_non_colliding_text_output_paths` |
| Worker local | Emite logs e o caminho final por sinal; falhas são enviadas pelo sinal de erro | `test_legacy_local_worker_emits_the_text_file_path` |
| Colisão de áudio YouTube | Ao selecionar um sufixo temporário alternativo, o caminho MP3 passado à transcrição acompanha o novo nome | `test_legacy_youtube_worker_updates_mp3_path_after_a_collision` |
| Instagram | A função cria o objeto Instaloader e termina com `NotImplementedError`; não há download funcional | `test_legacy_instagram_integration_is_explicitly_unimplemented` |
| Compatibilidade de sintaxe | Os arquivos Python de `main.py`, `core/` e `gui/` precisam continuar parseáveis em toda a faixa declarada | `test_legacy_python_sources_remain_parseable_on_supported_python` |

Os testes usam doubles para Whisper, yt-dlp e Instaloader. Não fazem chamadas de rede, download
de mídia, download de modelos ou inferência real. A suíte Qt usa a plataforma offscreen.

## 3. Limitações e riscos legados conhecidos

Estes comportamentos foram identificados na inspeção e não devem ser incorporados à arquitetura
nova:

1. A saída é texto corrido `.txt`; não há alinhamento por palavra, segmentação temporizada,
   tradução ou geração SRT.
2. O worker do YouTube usa o diretório relativo compartilhado `cache/` e remove seu conteúdo
   com `shutil.rmtree` no início de um trabalho. Isso não é isolamento seguro por job e pode
   apagar dados colocados nesse caminho por outros usos.
3. O worker legado não oferece o contrato completo de cancelamento cooperativo, estados,
   checkpoints, progresso mensurável ou publicação atômica exigido pelo novo produto.
4. A função de download do YouTube captura exceções e apenas imprime a mensagem; o chamador
   pode prosseguir para a etapa de transcrição mesmo após uma falha de download.
5. A integração Instagram é somente um placeholder não funcional.
6. As dependências legadas são importadas no topo de módulos de GUI/worker; isso dificulta
   importar e testar essas partes em ambientes sem os pacotes opcionais.
7. O código histórico não está integralmente formatado/lintado segundo a política Ruff nova.

O objetivo dos testes de caracterização é tornar mudanças nesses contratos visíveis, não
declarar tais limitações como requisitos desejáveis.

## 4. Correção de compatibilidade realizada nesta fase

A caracterização identificou uma expressão f-string em `gui/worker.py` que não era parseável
em Python 3.10/3.11, apesar de a matriz declarada do produto incluir Python `>=3.10,<3.14`.
A expressão foi reescrita sem sintaxe dependente do Python 3.12.

Também foi corrigido o caminho do MP3 após colisão de nome no worker do YouTube: quando um
arquivo temporário já existe, o caminho de entrada da transcrição agora acompanha o nome
alternativo escolhido. Essa correção é coberta diretamente por teste de regressão e
permite que o módulo legado seja importado na faixa de Python suportada.

Nenhuma integração real, dependência de runtime ou fluxo de produto novo foi introduzido.

## 5. Política de convivência e migração

- `src/legendar/` é a arquitetura-alvo e a única base permitida para funcionalidades novas.
- A aplicação em `main.py`, `core/` e `gui/` fica preservada durante a transição para não
  descartar o comportamento da versão anterior antes de existir fluxo substituto homologado.
- Não criar novas dependências entre o legado e `src/legendar/`, nem fazer a aplicação nova
  importar módulos de `core/` ou `gui/`.
- Mudanças no legado ficam limitadas a correções de segurança/compatibilidade necessárias para
  mantê-lo executável ou testável durante a transição; cada alteração exige teste e registro.
- Não fazer refatoração cosmética ou migração em massa do legado como parte da Fase 1.
- A aposentadoria física de `main.py`, `core/` e `gui/` fica condicionada à paridade dos fluxos
  substitutos e à homologação end-to-end das fases de integração/testes. Antes disso, a remoção
  causaria regressão sem benefício funcional.
- A preservação do legado é temporária e explícita, não uma segunda arquitetura a evoluir.

## 6. Política de qualidade e lint

O escopo mantido sob Ruff é:

- `src/legendar/`;
- `tests/unit/`, `tests/integration/`, `tests/gui/`, `tests/helpers/` e `tests/legacy/`;
- os módulos compartilhados atuais de teste (`tests/conftest.py`,
  `tests/test_architecture.py` e `tests/__init__.py`).

Os arquivos legados `main.py`, `core/` e `gui/` e os scripts de evidência da Fase 0 não
recebem reformatação ou lint retroativo nesta fase. Eles são cobertos por testes de
caracterização e compilação na matriz da CI. Essa exclusão é uma política documentada para
evitar que mudanças cosméticas incidentais se misturem à migração; não significa que os
problemas conhecidos foram corrigidos.

Qualquer módulo novo deve entrar no escopo mantido de Ruff desde sua criação. A política pode
ser ampliada depois, em alteração específica e revisada, sem mascarar falhas do código novo.

## 7. Critério para remover a baseline

A remoção só poderá ser proposta quando todos os itens abaixo forem verdadeiros:

- Os fluxos de entrada que permanecerão no produto estiverem implementados na nova arquitetura.
- Reconhecimento, alinhamento, segmentação e exportação substituírem o comportamento legado
  necessário.
- Os casos de uso equivalentes tiverem testes de integração/end-to-end e homologação manual.
- O entrypoint suportado estiver documentado e os usuários não dependerem mais do caminho antigo.
- O plano mestre, o estado vivo e o histórico de decisões registrarem a aposentadoria.

Até lá, a baseline permanece identificável, testada e congelada fora do caminho da arquitetura
nova.
