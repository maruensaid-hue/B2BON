# PROJECT STATE

| Campo | Valor |
|---|---|
| **CURRENT PHASE** | **NENHUMA** — Sourcing S0–S2 concluídas; S3–S8 aguardam autorização do PO |
| Última fase concluída | PHASE 15 — PRICING, AI CREDITS & COMMERCIAL MONETIZATION (2026-09-25) |
| Fase 15 | Desbloqueada pelo PO em 2026-09-25 com o prompt "PHASE 15 — PRICING, AI CREDITS & COMMERCIAL MONETIZATION" (substitui o escopo "Public Procurement Pricing") e concluída no mesmo dia. Preço-base do Public Procurement e franquias do Procurement/Full Suite continuam PENDING_FINAL_DEFINITION por decisão do PO |
| Branch de trabalho | `staging` |
| Relatório da última fase | `phases/SOURCING_S0_S2_COMPLETION.md` (antes: `phases/PHASE_15_COMPLETION.md`) |
| Correção arquitetural | 2026-09-26 — Strategic Sourcing & Bids (D-055, `18_STRATEGIC_SOURCING.md`). Plano S0–S8; **S0–S2 autorizadas e concluídas** em 2026-09-26 (OI-020); S3–S8 não autorizadas |

## Autorizações

| Fase | Autorizada por | Data | Observações |
|---|---|---|---|
| 0 | Product Owner ("COMEÇAR AGORA PELA PHASE 0") | 2026-09-25 | — |
| 15 | Product Owner ("pode prosseguir e concluir a fase") | 2026-09-25 | Franquias do Public Procurement e da Full Suite: decisão futura do PO |
| S0–S2 (sourcing) | Product Owner ("Autorizado", sobre "S0–S2 são as fases de menor risco para começar") | 2026-09-26 | Sem mudança de schema nem de comportamento; S3–S8 continuam pendentes |
| 1–17 | Product Owner ("Siga para a Fase 1 […] seguir para a Fase 2 e assim sucessivamente até o final do projeto, fica previamente autorizado o commit e subir todas as fases seguintes") | 2026-09-25 | **Exceções que continuam valendo, por regra do próprio Master Prompt:** Fase 15 só com valores de preço fornecidos pelo PO; nenhum preço ou valor de plano é alterado ou inventado (inclui OI-001) |

## Pendências abertas relevantes

- **OI-001** (crítica): limites 0 nos planos PREDATOR avulsos. Depende de valores do PO.
- **OI-017** (comercial): franquias de AI Credits do Public Procurement (50–100K) e da Full Suite (75–100K) e preço-base do Public Procurement — decisão futura do PO; hoje nada concedido por elas.
- **OI-018** (financeiro): câmbio USD→BRL para a margem de IA (sem ele a margem aparece indisponível).
- **OI-019** (comercial/produto): empacotamento de Enterprise Bids e Enterprise Strategic Sourcing (módulo, preço, franquia).
- **OI-020** (priorização): S0–S2 concluídas; S3 (schema unificado, Strangler) e seguintes aguardam o PO.
- **OI-015** (comercial): empacotamento e preço do módulo Bid Intelligence (B2B ON Public Sector). Módulo existe, nenhum plano o inclui.
- **OI-014** (produto): visibilidade padrão de empresas novas no diretório da rede.
- **OI-010** (alta): verificar em produção se as features de IA falhavam por `temperature` com `claude-sonnet-5` (corrigido no código).
- **OI-016** (operação): metas de RPO/RTO.
- OI-003, OI-006 a OI-009: ver `OPEN_ISSUES.md`.
- Conectores de CRM (Fase 13) estão BETA e desligados: habilitar em produção só após validar contra contas reais (TD-069).

## Baseline de qualidade (após a Fase 15)

- Backend: 2.015 passed, 2 skipped (+2 testes de concorrência que rodam com `B2BON_TESTE_PG_URL`, 2/2 em Postgres 16). Migrações validadas também em Postgres 16 (head `e7b3c1a9f5d2`).
- Ruff: 40 (sem novos). Frontend: lint OK (25 warnings), build OK.
- E2E: 6/6.
