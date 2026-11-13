# Fase 8 e Fase 8.1 — arquivo de encerramento

Este diretório preserva os planos detalhados e evidências que conduziram a correção do pipeline, a integração de TranslateGemma e a inclusão da entrada SRT direta.

## Documentos preservados

- [Plano corretivo detalhado da Fase 8.1](FASE_8_1_PLANO.md).
- [Plano mestre de qualidade e desempenho](PLANO_CORRECAO_MELHORIA.md).

## Relação com a PR #44

A PR [#44](https://github.com/anfalcir/legendar/pull/44) foi uma proposta documental com duas alterações: atualizar `ESTADO_ATUAL.md` e registrar a entrada SRT da PR #43 em `FASE_8_1_PLANO.md`. Ela foi fechada sem merge independente quando a consolidação maior foi preparada na PR #45. A versão viva do estado atual foi substituída pelo documento consolidado; a alteração específica do plano SRT não havia sido levada ao arquivo histórico e foi recuperada nesta revisão. Assim, o conteúdo documental efetivo da PR #44 está agora preservado na `main`, embora a PR #44 permaneça fechada como não mergeada.

## Resultado atual

A integração técnica foi concluída. A entrada por arquivo SRT está integrada à `main` pela PR #43. TranslateGemma foi exercitado com pesos reais e aprovado funcionalmente pelo usuário. A tradução e a composição das frases melhoraram e foram consideradas suficientes para a necessidade atual, sem serem consideradas ótimas. O projeto foi pausado em 13/11/2026, com possibilidade de melhorias futuras e sem cronograma.

O motor local anterior deixou de fazer parte do código mantido. Os documentos desta pasta registram como o projeto chegou ao estado atual; instruções ou decisões transitórias neles descritas não representam a configuração vigente.

Consulte a documentação ativa em [docs/README.md](../../README.md), especialmente [estado atual](../../ESTADO_ATUAL.md) e [homologação](../../HOMOLOGACAO.md).
