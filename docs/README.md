# Documentação viva do Legendar

A raiz de `docs/` contém somente documentos que descrevem o produto, a configuração, a operação ou decisões técnicas ainda aplicáveis. Planos encerrados, handoffs e relatórios substituídos ficam em [archive/](archive/README.md).

## Estado e aceitação

- [Estado atual](ESTADO_ATUAL.md) — fonte de verdade do produto, situação de pausa, motor vigente, evidências e melhorias possíveis.
- [Homologação](HOMOLOGACAO.md) — resultado funcional real, avaliação de qualidade e limites da evidência.
- [Decisão técnica TranslateGemma](DECISAO_TRANSLATEGEMMA.md) — modelo local, runtime, protocolo, privacidade e operação.

## Referência técnica e operacional

- [Arquitetura](ARQUITETURA.md) — camadas, pipeline, portas, runtime e publicação.
- [Operação](OPERACAO.md) — uso da interface, fontes de entrada, tradução, cancelamento e diagnóstico.
- [Instalação](INSTALACAO.md) — dependências, perfis e execução.
- [Distribuição Linux](DISTRIBUICAO_LINUX.md) — bundle de usuário, instalação, atualização e publicação.
- [Decisões](DECISOES.md) — decisões vigentes e possibilidades ainda não aprovadas.
- [Matriz de dependências](MATRIZ_DEPENDENCIAS.md) — dependências diretas, runtimes externos e política de atualização.

## Histórico

- [Fase 8 e Fase 8.1](archive/phase-8.1/README.md) — auditoria, plano corretivo, decisões de migração e encerramento da homologação atual.
- [Fases concluídas 5 e 6](archive/completed-phases/README.md) — planos e evidências históricas.
- [Remodelação arquitetural anterior](archive/previous-remodeling/README.md) — fases 0–10, handoffs, relatório e baseline legada.
- [Índice do arquivo histórico](archive/README.md).

Os documentos arquivados são evidência histórica, não instruções operacionais. Em caso de divergência, prevalecem os documentos vivos e o comportamento integrado à `main`.
