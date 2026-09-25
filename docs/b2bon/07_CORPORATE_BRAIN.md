# 07 — CORPORATE BRAIN, INTELLIGENCE PROFILES, MEMORY CONSOLIDATION (Fase 4)

## Corporate Brain (§15)

- Tabela `conhecimento_corporativo`, sempre por tenant. Tipos: produto,
  serviço, oferta, case, objeção, concorrente, persona, estratégia, ICP,
  aprendizado, política, outro.
- Cada item tem `origem` (OFFICIAL/INTERNAL/SELF_DECLARED/AI_INFERENCE),
  `classificacao`, `visibilidade` (`interno` | `rede`), `fonte` e `evidencia`.
- Item CONFIDENTIAL/RESTRICTED não pode ter visibilidade `rede` (validado).
- Escrita: admin/super_admin. Leitura: qualquer usuário do tenant.
  UI: **Cérebro Corporativo**. API: `/api/v1/inteligencia/conhecimento`.
- Busca por palavra-chave com normalização de acento. Sem embeddings
  nesta fase (D-017).
- Consumido pelo Agente Corporativo (só itens `rede`, via Context Engine
  com propósito `RESPOSTA_EXTERNA`). As features internas passam a
  consumir pelo propósito `USO_INTERNO` na Fase 6 (Opportunity Intelligence).

## Intelligence Profiles (§16)

| Perfil | Tabela | Conteúdo (Fase 4) |
|---|---|---|
| Company Intelligence | `perfil_inteligencia` (escopo `empresa`) | tom e restrições de comunicação, ofertas/ICPs ativos, regras aprendidas, taxas de aprovação/rejeição de rascunhos de IA, canais mais usados, padrões observados (correlação, não causa) |
| User Intelligence | `perfil_inteligencia` (escopo `usuario`) | volume de decisões de aprovação, taxa de edição antes de aprovar, taxa de rejeição |
| Network Intelligence | — | Fases 7–8, só com dado legal e contratualmente permitido |
| Procurement Intelligence | — | Fase 10, isolado pela barreira Buy/Sell |

## Memory Consolidation (§59)

`perfis.consolidar_empresa/consolidar_usuario`: determinístico (classe
C0, sem LLM), versionado, com a fonte e o tamanho de amostra de cada
campo em `fontes`. Abaixo de 5 amostras o campo fica `None` ("Dados
insuficientes" na UI): UNKNOWN é preferível a invenção (§63).

## Isolamento

Nunca `PRIVATE TENANT A DATA → TENANT B` (§16). Garantido por:
- filtro de tenant em toda query do Brain e do Context Engine;
- propósito `RESPOSTA_EXTERNA` restrito a itens `rede`;
- teste crítico `tests/integration/test_inteligencia_brain.py::test_critico_agente_corporativo_nao_vaza_brain_de_terceiro_nem_interno`,
  que inspeciona o prompt efetivamente enviado ao LLM.
