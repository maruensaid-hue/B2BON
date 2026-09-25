# PROJECT STATE

| Campo | Valor |
|---|---|
| **CURRENT PHASE** | **CONCLUÍDO (Fases 0–14, 16, 17). Aguardando o PO para a Fase 15** |
| Última fase concluída | PHASE 17 — SCALE, SECURITY & HARDENING (2026-09-25) |
| Fase bloqueada | **PHASE 15 — PUBLIC PROCUREMENT PRICING: não executada, aguarda valores do PO (D-045)** |
| Branch de trabalho | `staging` |
| Relatório da última fase | `phases/PHASE_17_COMPLETION.md` (Fase 15: `phases/PHASE_15_BLOCKED.md`) |

## Autorizações

| Fase | Autorizada por | Data | Observações |
|---|---|---|---|
| 0 | Product Owner ("COMEÇAR AGORA PELA PHASE 0") | 2026-09-25 | — |
| 1–17 | Product Owner ("Siga para a Fase 1 […] seguir para a Fase 2 e assim sucessivamente até o final do projeto, fica previamente autorizado o commit e subir todas as fases seguintes") | 2026-09-25 | **Exceções que continuam valendo, por regra do próprio Master Prompt:** Fase 15 só com valores de preço fornecidos pelo PO; nenhum preço ou valor de plano é alterado ou inventado (inclui OI-001) |

## Pendências abertas relevantes

- **OI-001** (crítica): limites 0 nos planos PREDATOR avulsos. Depende de valores do PO.
- **Public Procurement**: módulo criado, preço PENDING_DEFINITION; Fase 15 só com valores do PO.
- **OI-015** (comercial): empacotamento e preço do módulo Bid Intelligence (B2B ON Public Sector). Módulo existe, nenhum plano o inclui.
- **OI-014** (produto): visibilidade padrão de empresas novas no diretório da rede.
- **OI-013** (comercial): taxa de conversão custo → créditos de IA.
- **OI-010** (alta): verificar em produção se as features de IA falhavam por `temperature` com `claude-sonnet-5` (corrigido no código).
- **OI-016** (operação): metas de RPO/RTO.
- OI-003, OI-006 a OI-009: ver `OPEN_ISSUES.md`.
- Conectores de CRM (Fase 13) estão BETA e desligados: habilitar em produção só após validar contra contas reais (TD-069).

## Baseline de qualidade (após a Fase 17)

- Backend: 1.953 passed. Migrações validadas também em Postgres 16.
- Frontend: lint OK (25 warnings), build OK.
- E2E: 5/5.
