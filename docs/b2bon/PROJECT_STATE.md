# PROJECT STATE

| Campo | Valor |
|---|---|
| **CURRENT PHASE** | **PHASE 7 — BUSINESS NETWORK FOUNDATION** |
| Última fase concluída | PHASE 6 — OPPORTUNITY INTELLIGENCE (2026-09-25) |
| Branch de trabalho | `staging` |
| Relatório da última fase | `phases/PHASE_6_COMPLETION.md` |

## Autorizações

| Fase | Autorizada por | Data | Observações |
|---|---|---|---|
| 0 | Product Owner ("COMEÇAR AGORA PELA PHASE 0") | 2026-09-25 | — |
| 1–17 | Product Owner ("Siga para a Fase 1 […] seguir para a Fase 2 e assim sucessivamente até o final do projeto, fica previamente autorizado o commit e subir todas as fases seguintes") | 2026-09-25 | **Exceções que continuam valendo, por regra do próprio Master Prompt:** Fase 15 só com valores de preço fornecidos pelo PO; nenhum preço ou valor de plano é alterado ou inventado (inclui OI-001) |

## Pendências abertas relevantes

- **OI-001** (crítica): limites 0 nos planos PREDATOR avulsos. Depende de valores do PO.
- **OI-013** (comercial): taxa de conversão custo → créditos de IA.
- **OI-010** (alta): verificar em produção se as features de IA falhavam por `temperature` com `claude-sonnet-5` (corrigido no código).
- OI-003, OI-006 a OI-009: ver `OPEN_ISSUES.md`.

## Baseline de qualidade (após a Fase 6)

- Backend: 1.761 passed. Migrações validadas também em Postgres 16.
- Frontend: lint OK (25 warnings), build OK.
- E2E: 4/4.
