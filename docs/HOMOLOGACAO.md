# Homologação do Legendar — roteiro prático

- **Para quem:** responsável por executar a aplicação no computador-alvo.
- **Para quê:** validar sincronização, qualidade textual, tradução, desempenho e interface com mídia real.
- **Operação:** [OPERACAO.md](OPERACAO.md).
- **Plano de correção e desempenho:** [PLANO_CORRECAO_MELHORIA.md](PLANO_CORRECAO_MELHORIA.md).
- **Plano corretivo após os testes reais de 12/11/2026:** [FASE_8_1_PLANO.md](FASE_8_1_PLANO.md).
- **Instalação:** [INSTALACAO.md](INSTALACAO.md).

## 1. Preparar ambiente

Execute novamente o inventário atualizado antes de uma rodada de desempenho. O snapshot antigo do hardware está no histórico da Fase 0 e não deve ser tomado como prova de configuração atual.

```bash
python scripts/phase0_inventory.py --probe-torch
```

Confirme:
- versão Python e distribuição Linux/Windows/macOS;
- CPU, núcleos físicos/lógicos e RAM total/disponível;
- GPU, driver e disponibilidade de CUDA/MPS;
- FFmpeg/ffprobe e versões dos modelos instalados;
- espaço livre no disco.

Instale o perfil CPU ou CUDA compatível conforme [INSTALACAO.md](INSTALACAO.md). Não combine os dois extras.

## 2. Abrir o sistema

```bash
PYTHONPATH=src uv run --locked --no-sync python -m legendar
```

A jornada e os estados da interface estão em [OPERACAO.md](OPERACAO.md).

## 3. Teste A — PT-BR para PT-BR

Use 2–5 minutos de mídia real representativa:
1. selecione o arquivo e a faixa;
2. escolha português como idioma falado e final;
3. deixe a tradução desmarcada;
4. gere e abra o SRT no player de referência.

Observe fidelidade textual, nomes, números, omissões, repetições, alinhamento e conforto de leitura.

## 4. Teste B — PT-BR para inglês

Use a mesma mídia do Teste A, habilitando a tradução. Verifique:
- preservação de significado e negações;
- nomes, referências, números e siglas;
- frases divididas em cues vizinhas;
- timestamps preservados;
- texto completo e natural no idioma final.

## 5. Teste C — inglês para PT-BR e detecção

Repita com áudio em inglês e tradução para PT-BR. Teste também a detecção automática. Compare com o idioma explicitamente selecionado.

## 6. Teste D — cancelamento

Solicite cancelamento durante transcrição, alinhamento e tradução. Confirme:
- encerramento em ponto seguro;
- nenhum SRT parcial no destino;
- estado e controles retornam corretamente;
- workspace temporário é limpo.

## 7. Teste E — YouTube

Use URL de mídia autorizada e confira disponibilidade do `yt-dlp` e runtime JavaScript. Teste cancelamento durante download.

## 8. Teste F — mídia longa e desempenho

Use a mídia de referência de aproximadamente 37 minutos, quando disponível.

Registre:
- tempo total;
- tempo de cada estágio;
- tempo de carregamento de modelos separado da inferência;
- CPU média/pico e uso por núcleo;
- RAM máxima e memória livre por estágio;
- GPU/VRAM, se aplicável;
- modelos, dtype, beam, batch, threads e versões;
- tempo frio e quente;
- qualidade textual, alinhamento, CPS e legibilidade.

A baseline operacional consolidada em 11/11/2026 foi de aproximadamente **23min21s** para 37min10s de mídia nas execuções quentes (RTF ≈ 0,63), com NLLB consumindo cerca de 14 minutos. O relato inicial de aproximadamente uma hora foi substituído por essa medição reproduzida. A Fase 8 deve repetir o protocolo após as alterações de recursos, registrando cold/warm, memória e tempo por estágio.

## 9. Teste G — inspeção independente do SRT

Abra o SRT no VLC ou em outro player de referência e observe:
- início/fim em relação à fala;
- até duas linhas e largura dentro do limite;
- duração confortável e sem flashes;
- frases agrupadas de modo natural;
- nenhuma palavra omitida ou duplicada;
- ausência de sobreposição e cue fora da mídia;
- nomes próprios, números, referências e caracteres inesperados.

Para precisão temporal, marque fronteiras humanas em uma amostra de fala e compare com o SRT. Use o avaliador de alinhamento existente com manifesto local; áudio e texto privado não devem ser versionados.

## 9.1. Gate automatizado do SRT

Antes da inspeção no player, execute o avaliador estrutural sobre o SRT gerado:

```bash
uv run --locked --no-sync python scripts/phase8_srt_quality.py caminho/resultado.srt
```

Para comparar dois resultados do mesmo corpus:

```bash
uv run --locked --no-sync python scripts/phase8_srt_quality.py   caminho/candidato.srt --compare caminho/baseline.srt --json
```

O gate verifica, entre outros pontos, sobreposição, duração excessiva, CPS acima de 17, largura física acima de 42 caracteres por linha e candidatos de fragmentação sintática. Ele **não** decide sozinho se a legenda está natural nem comprova sincronização com o áudio; esses pontos continuam exigindo inspeção audiovisual.

## 9.2. Evidências da rodada de 12/11/2026

Os resultados reais desta rodada foram preservados em `temporario/`:

- `EN-baseline.srt`: SRT inglês automático de referência;
- `baseline.srt`: SRT PT anterior;
- `teste-2026.11.12.srt`: SRT PT da nova rota NLLB;
- `temporario/logs/`: sete relatórios JSON sanitizados.

**Resultados medidos:**

- NLLB concluiu a mídia de 37min10s em **45min49s**; transcrição 19min15s, alinhamento 5min43s e tradução 20min44s (geração 20min32s).
- As três execuções quentes anteriores têm mediana de **23min21s**.
- O job novo usou PyTorch intra-op/inter-op 2/1; as três execuções quentes anteriores usaram 4/4.
- Gemini encerrou após **32min29s**, com 3 requisições, 2 lotes completos, 64/927 unidades aceitas e 0 retries registrados.
- O SRT PT novo tem 925 cues; 71,0% têm até três palavras; 444 cues excedem 17 CPS; há três linhas acima de 42 caracteres.
- A tradução contém deriva para PT-PT e erros semânticos que exigem revisão humana. “Não, obrigado” aparece 15 vezes no PT; a comparação temporal confirma que várias ocorrências coincidem com “Thank you” no inglês automático, mas os limites de cues diferem e cada ocorrência precisa de revisão individual.

O relatório JSON não guarda o conteúdo das respostas Gemini, portanto a natureza exata da resposta rejeitada no terceiro lote permanece hipótese. A leitura técnica mais provável e a sequência de correção estão documentadas em [FASE_8_1_PLANO.md](FASE_8_1_PLANO.md).

**Regra para as próximas rodadas:** separar benchmark de pipeline completo de experimento de componente. Para isolar segmentação ou tradução, congelar a mesma transcrição/alinhamento de origem e reutilizá-los; comparar execuções completas não isola essas variáveis, pois Whisper pode produzir diferentes quantidades de palavras, segmentos e timestamps. Para desempenho completo, manter a mídia, hardware, perfil, cache, versão e parâmetros constantes; separar cold start de warm run e executar pelo menos três rodadas quentes.

## 9.3. Congelamento do corpus da Fase 8.1

O manifesto [temporario/manifesto-fase-8.1.0.json](../temporario/manifesto-fase-8.1.0.json) registra SHA-256, tamanho e Git blob SHA-1 dos três SRTs e sete relatórios JSON da rodada de 12/11/2026. Não altere esses arquivos; qualquer evidência nova deve receber novo nome e novo registro de hash.

As fixtures sintéticas versionadas estão em [tests/fixtures/phase_8_1/README.md](../tests/fixtures/phase_8_1/README.md). Elas cobrem falha Gemini com item vazio, candidato ausente, truncamento, composição, fronteiras de sentença, interjeição, layout, entidades protegidas, agradecimento e negação. Não são corpus-ouro de áudio real.

A amostra humana PT-BR deve ser revisada a partir do áudio autorizado e armazenada localmente em `corpus/phase_8_1/human_reference.json` (a pasta `corpus/` é ignorada pelo Git). O template vazio está em `tests/fixtures/phase_8_1/human_reference.template.json`. Também é necessário congelar/hash dos mesmos intermediários ASR/alinhamento a serem reutilizados nos testes isolados de segmentação e tradução. Enquanto isso não for feito, comparações de qualidade permanecem bloqueadas.

## 9.4. Gate único de TranslateGemma — homologação inicial

A integração de software está na `main`, mas o modelo real ainda não foi homologado. A primeira validação operacional deve ser **uma única execução representativa**, no Linux Mint do hardware de referência, sem repetir matrizes de teste.

1. Abra o Legendar e selecione **TranslateGemma** como backend local.
2. Na primeira preparação, confira o diagnóstico apresentado pelo aplicativo. Autorize a instalação do runtime llama.cpp quando solicitado. A instalação é privada ao cache do Legendar, sem `sudo` e sem alterar o PATH do sistema.
3. Autorize o download do GGUF somente depois de conferir o modelo/licença. Se o Hugging Face exigir autenticação ou aceite de termos, faça isso explicitamente; o aplicativo não deve aceitar termos nem armazenar/exibir o token em logs.
4. Use o SRT em inglês já gerado para o episódio Wingfeather Saga S4E2 e traduza para **português brasileiro**. Não rode uma nova transcrição nesta primeira etapa: o objetivo inicial é isolar a tradução e permitir comparação com a mesma origem.
5. Confirme que o processo de tradução inicia o servidor automaticamente, que uma segunda preparação reutiliza runtime/modelo/servidor sem download duplicado e que a saída JSON interna não aparece no SRT. O adaptador deve validar GBNF/JSON e todos os IDs antes de aceitar cada lote.
6. Revise no resultado: cardinalidade e ordem das cues, timestamps inalterados, nomes próprios/cidades/raças/clãs, negações, naturalidade PT-BR, frases fragmentadas e ausência de texto em inglês residual.
7. Registre duração de preparação (separada do tempo de tradução), tempo de geração, chamadas, lotes aceitos, maior lote, subdivisões, tokens de prompt/saída, RAM máxima e versão do runtime/modelo. Para 981 unidades curtas, um resultado próximo de 31 lotes aceitos sem subdivisões excessivas é a expectativa inicial (limites de contexto/caracteres podem reduzir o lote efetivo). O relatório sanitizado fica em `~/.cache/legendar/logs/performance/`; não envie áudio, vídeo, transcrição ou credenciais.

**Critério de decisão:** falha de runtime, perda/reordenação de cue, ID ausente/duplicado, JSON inválido ou saída estruturada exposta bloqueia a homologação técnica. Um padrão persistente de uma geração por cue também bloqueia a aceitação de desempenho e exige inspeção das métricas de subdivisão. Qualidade PT-BR e preservação de nomes exigem revisão editorial; CI verde e SRT estruturalmente válido não bastam. NLLB continua disponível apenas como baseline selecionável até a aprovação explícita do resultado. Não há fallback automático.

## 10. Registro de resultado

| Campo | Valor |
|---|---|
| Data e hardware | |
| Sistema operacional/Python | |
| Modelos e versões | |
| Duração da mídia | |
| Tempo frio / quente | |
| Tempo por estágio | |
| CPU/RAM/GPU | |
| WER/CER ou revisão textual | |
| Erro temporal mediano/P95 | |
| Cobertura de alinhamento | |
| Cues abaixo de 1 s / acima de CPS | |
| Palavras omitidas/duplicadas | |
| Qualidade da tradução | |
| Observações e decisão | |

Não inclua no repositório áudio, transcrição ou caminho pessoal. Registre somente IDs sintéticos e métricas sanitizadas, com arquivos privados mantidos localmente.
