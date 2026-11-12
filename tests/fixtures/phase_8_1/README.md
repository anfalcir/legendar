# Corpus sintético da Fase 8.1

Este diretório contém exclusivamente fixtures artificiais, pequenas e não sensíveis. Não reproduz o áudio, o roteiro, as transcrições ou as respostas privadas da homologação de 12/11/2026.

## Arquivos

- `gemini_responses.json`: resposta com um item vazio, ausência de candidato e resposta truncada.
- `subtitle_scenarios.json`: fragmentos contínuos, sentenças curtas distintas, interjeição legítima, texto longo, entidades protegidas, agradecimento e negação.
- `human_reference.template.json`: estrutura vazia para uma referência PT-BR humana. O exemplo não contém nem pretende representar uma transcrição real.

Os campos `illustrative_pt_br` são expectativas didáticas de fixtures sintéticas. Não constituem corpus-ouro nem aprovação editorial.

## Referência humana real (pendente)

Depois de ouvir uma amostra autorizada do áudio original e revisar o texto PT-BR, copie o template para:

```text
corpus/phase_8_1/human_reference.json
```

A pasta `corpus/` já está excluída do Git pelo `.gitignore`. Preencha a referência somente com material que possa ser armazenado localmente, informe hash do áudio, intervalo temporal, texto reconhecido, candidato traduzido e correções humanas. Anote separadamente erros que já existiam no ASR e erros introduzidos pelo tradutor. Não versionar áudio, legenda/transcrição protegida ou referência humana derivada de material protegido.

**Gate:** a etapa 8.1.0 permanece bloqueada para experimentos comparativos de qualidade até existir uma amostra real revisada por pessoa fluente em PT-BR. As fixtures sintéticas já podem ser usadas em testes determinísticos.
