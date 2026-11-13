# Matriz e política de dependências do Legendar

- **Dependências diretas:** `pyproject.toml`.
- **Resolução exata:** `uv.lock`.
- **Gerenciador:** `uv`.
- **Estado:** motor local TranslateGemma funcionalmente homologado; Gemini é opção remota explícita.

## Runtime principal

| Componente | Origem | Uso |
|---|---|---|
| Python | `requires-python >=3.10,<3.14` | Aplicação e ferramentas |
| PySide6 | Dependência base | Interface desktop |
| OpenAI Whisper | Extra `runtime-cpu` ou `runtime-cu128` | ASR padrão |
| faster-whisper/CTranslate2 | Extra de runtime, conforme configuração | ASR alternativo selecionável; não é o padrão |
| PyTorch / torchaudio / torchvision | Índice CPU ou CUDA 12.8 | ASR e stack de alinhamento |
| WhisperX | Extra de runtime | Alinhamento temporal |
| FFmpeg / ffprobe | Ferramentas do sistema | Inspeção e preparação de mídia |
| yt-dlp / yt-dlp-ejs | Extra de runtime | Aquisição de mídia do YouTube |
| llama.cpp | Binário runtime gerenciado | Execução local do TranslateGemma |
| TranslateGemma GGUF Q4_K_M | Download sob demanda, após consentimento | Tradução local PT-BR ↔ inglês |
| Gemini Developer API | Serviço externo opcional; HTTPS via biblioteca padrão | Tradução remota quando selecionada |

O runtime llama.cpp e os pesos GGUF não são dependências Python do `uv.lock`. O aplicativo os prepara em cache privado, sob demanda, com validação de integridade. A tradução local não envia o texto à nuvem.

## Perfis de instalação

- `runtime-cpu`: stack PyTorch CPU, Whisper, WhisperX, yt-dlp e componentes necessários ao processamento local.
- `runtime-cu128`: variante CUDA 12.8 para plataformas suportadas pelo lockfile.
- Os perfis CPU e CUDA são conflitantes e não devem ser combinados.
- `phase0`: utilitários de inventário/avaliação e bibliotecas de suporte a ferramentas de desenvolvimento.
- `dev`: pytest, pytest-qt, pytest-cov e Ruff.

Transformers pode aparecer no lock como dependência transitiva do stack WhisperX/alinhamento. Não é selecionado pelo Legendar como motor de tradução. SentencePiece e dependências exclusivas do antigo motor local não fazem parte dos extras mantidos.

## Tradução

TranslateGemma é o único motor local. O modelo GGUF é preparado sob demanda, com consentimento explícito, e o servidor fica restrito a loopback. Gemini é remoto, opcional e configurado pelo usuário; a aplicação não alterna automaticamente entre eles. Nenhuma credencial deve ser versionada.

## Política de atualização

1. Alterar dependências diretas somente quando o código mantido depender da API.
2. Revisar compatibilidade Python, sistemas operacionais, wheels/binários, segurança e licenças.
3. Atualizar `pyproject.toml` e executar `uv lock`.
4. Revisar o diff do lockfile e validar com `uv lock --check`.
5. Executar a matriz Python, os testes, o lint, a formatação e o verificador de links.
6. Atualizar [DECISOES.md](DECISOES.md) e [ESTADO_ATUAL.md](ESTADO_ATUAL.md) quando a mudança alterar comportamento ou suporte.
