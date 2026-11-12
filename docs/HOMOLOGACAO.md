# Homologação do Legendar — roteiro prático

- **Para quem:** responsável por executar a aplicação no computador-alvo.
- **Para quê:** validar sincronização, qualidade textual, tradução, desempenho e interface com mídia real.
- **Operação:** [OPERACAO.md](OPERACAO.md).
- **Plano de correção e desempenho:** [PLANO_CORRECAO_MELHORIA.md](PLANO_CORRECAO_MELHORIA.md).
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

O tempo global reportado inicialmente foi cerca de 60 minutos para 37 minutos de áudio (RTF ≈ 1,62). Esse é um relato inicial, não uma baseline de estágio nem uma medição reproduzida. A Fase 1 do [plano vigente](PLANO_CORRECAO_MELHORIA.md) criará o benchmark comparável.

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
