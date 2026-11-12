# Matriz e política de dependências do Legendar

- **Fonte canônica de requisitos diretos:** `pyproject.toml`.
- **Fonte canônica de resolução exata:** `uv.lock`.
- **Gerenciador:** `uv`.
- **Plano de otimização:** [PLANO_CORRECAO_MELHORIA.md](PLANO_CORRECAO_MELHORIA.md).

## 1. Princípio de governança

O repositório é a fonte de verdade dos requisitos. O computador-alvo é um perfil de validação, não a autoridade que define dependências, versões ou arquitetura.

Toda alteração deve considerar contratos do produto, compatibilidade upstream, interseção de dependências, disponibilidade de wheels/binários, CI, segurança, licença, manutenção, privacidade e reprodutibilidade.

Nenhuma instalação/update global deve ser executada silenciosamente pelo aplicativo. Alterações de runtime ocorrem em ambiente isolado e ficam registradas no manifesto e no lockfile.

## 2. Fontes de verdade

| Artefato | Responsabilidade | Regra |
|---|---|---|
| `pyproject.toml` | Dependências diretas, intervalos, extras e grupos | Fonte canônica |
| `uv.lock` | Resolução exata, transitivas, marcadores e origem de wheels | Versionar e instalar com `--locked` |
| `docs/MATRIZ_DEPENDENCIAS.md` | Política, compatibilidade e justificativas | Não substitui os artefatos executáveis |
| `requirements.txt` | — | Removido; exportação por `uv export` |

## 3. Runtime atual

| Componente | Requisito atual | Categoria |
|---|---|---|
| PySide6 | `>=6.9,<7` | GUI |
| openai-whisper | `>=20250625` | Reconhecimento |
| yt-dlp | `>=2025.4.30` | Entrada YouTube |
| yt-dlp-ejs | `>=0.8,<1` | JavaScript do fluxo YouTube |
| torch | `>=2.8,<2.9` | Backend |
| torchvision | `>=0.23,<0.24` | Pareado com Torch |
| torchaudio | `>=2.8,<2.9` | Pareado com Torch |
| whisperx | `>=3.8.6,<3.8.7` | Alinhamento |
| transformers | `>=4.57,<5` | Tradução local |
| sentencepiece | `>=0.2,<1` | Tokenização NLLB |

O perfil CPU e CUDA 12.8 são extras mutuamente exclusivos. O perfil ROCm não está declarado porque a interseção validada com o WhisperX atual não foi estabelecida.

## 4. Perfis

| Extra | Seleção PyTorch | Plataformas pretendidas | Observação |
|---|---|---|---|
| `runtime-cpu` | Índice oficial CPU em Linux/Windows; wheels PyPI em macOS | Linux, Windows, macOS | Perfil de compatibilidade |
| `runtime-cu128` | Índice oficial CUDA 12.8 | Linux/Windows compatíveis | Depende de GPU/driver NVIDIA |
| Apple MPS | Wheel PyTorch PyPI no perfil CPU | macOS/Apple Silicon compatível | Detectado em runtime |
| ROCm | Não exposto | — | Não homologado com o stack atual |

Não combinar extras de runtime. Não ampliar a faixa do WhisperX sem revalidar lock, Python, Torch e todos os workflows.

## 5. Opções em avaliação para desempenho

As opções abaixo **não são dependências adotadas**. Só devem entrar no manifesto quando uma prova de conceito demonstrar ganho real e equivalência de qualidade.

### 5.1. faster-whisper / CTranslate2 para ASR

O faster-whisper é uma implementação de Whisper baseada em CTranslate2. Sua documentação demonstra INT8 em CPU, FP16 em GPU, timestamps por palavra e VAD opcional.

Estado da Fase 5: adaptador e benchmark pareado integrados; OpenAI Whisper continua padrão. A avaliação operacional do candidato ainda depende de corpus humano e hardware de referência.

Avaliar:
- compatibilidade de versão com Python, Torch/WhisperX e wheels disponíveis;
- suporte INT8 no hardware AMD do perfil de referência;
- WER/CER e alinhamento em comparação com OpenAI Whisper atual;
- equivalência de parâmetros e comportamento de janelas;
- uso de CPU/RAM, threads e tempo de inferência.

O adaptador da Fase 5 está integrado. O perfil `runtime-cpu`/`runtime-cu128` já recebe faster-whisper/CTranslate2 transitivamente por `whisperx`; a implementação não adicionou dependência direta redundante. Antes de alterar essa relação, revisar o lock e a compatibilidade do stack completo.

Referência: [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper).

### 5.2. CTranslate2 para NLLB-200

A documentação CTranslate2 demonstra conversão de NLLB a partir de Transformers e execução via `translate_batch`. A quantização pode reduzir tamanho e acelerar, mas o tipo efetivo depende do backend.

Avaliar:
- conversão e reprodução do checkpoint NLLB-200 distilled 600M atual;
- correspondência de códigos `por_Latn` e `eng_Latn`;
- INT8 no hardware real, verificando `get_supported_compute_types`;
- beam 4, 2 e 1;
- batches por tokens e bucketing por comprimento;
- qualidade contextual e terminológica, com revisão humana;
- lock, wheel, plataforma e licença do modelo.

Referências: [conversão NLLB](https://opennmt.net/CTranslate2/guides/transformers.html), [desempenho](https://opennmt.net/CTranslate2/performance.html), [quantização](https://opennmt.net/CTranslate2/quantization.html).

### 5.3. Licença do checkpoint NLLB

O model card do `facebook/nllb-200-distilled-600M` informa CC-BY-NC-4.0 e descreve limites de finalidade/uso. O código MIT do Legendar não altera a licença dos pesos. Qualquer distribuição ou mudança de checkpoint exige revisão da licença do modelo selecionado.

Referência: [NLLB-200 distilled 600M](https://huggingface.co/facebook/nllb-200-distilled-600M).

## 6. Política de atualização

1. Criar experimento isolado e reproduzível.
2. Fixar versões candidatas e registrar ambiente.
3. Comparar qualidade e desempenho no mesmo corpus/hardware.
4. Revisar licença, segurança, plataformas e impacto no pacote.
5. Declarar dependência direta somente se o código passar a depender diretamente da API.
6. Atualizar `pyproject.toml`, executar `uv lock`, revisar diff e validar com `uv lock --check`.
7. Executar matriz Python, testes e documentação.
8. Registrar a decisão em [DECISOES.md](DECISOES.md) e [ESTADO_ATUAL.md](ESTADO_ATUAL.md).
