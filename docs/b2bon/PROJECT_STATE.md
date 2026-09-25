# PROJECT STATE

| Campo | Valor |
|---|---|
| **CURRENT PHASE** | **PHASE 1 — DOMAIN SEPARATION (AGUARDANDO AUTORIZAÇÃO DO PO)** |
| Última fase concluída | PHASE 0 — COMPLETE DISCOVERY & AUDIT (2026-09-25) |
| Branch de trabalho | `staging` |
| Commit base da auditoria | `93dede8` |
| Plano da próxima fase | `phases/PHASE_1_PLAN.md` |
| Relatório da última fase | `phases/PHASE_0_COMPLETION.md` |

## Regra

A Fase 1 **não deve ser iniciada** até o Product Owner autorizar
explicitamente. Se uma sessão nova ler este arquivo sem que a
autorização esteja registrada abaixo, deve parar e pedir autorização.

## Autorizações

| Fase | Autorizada por | Data | Observações |
|---|---|---|---|
| 0 | Product Owner (Master Prompt v4, "COMEÇAR AGORA PELA PHASE 0") | 2026-09-25 | — |
| 1 | — | — | pendente |

## Pendências que bloqueiam ou condicionam a Fase 1

- **OI-004**: definir quais operações de Conta/Decisor são compartilhadas
  entre CRM e PREDATOR. Condiciona a etapa 1.3.3 do plano.
- **OI-001** (crítica, independente da Fase 1): hotfix dos limites 0 nos
  planos PREDATOR avulsos. Precisa de autorização separada (D-006).

## Baseline de qualidade (Fase 0)

- Backend: 1.465 testes passando. Sem ffmpeg, 6 falham por ambiente
  (TD-034); com ffmpeg, 0 falhas.
- Frontend: lint OK (25 warnings), build OK.
- E2E Playwright: 4/4 passando (com Chromium pré-instalado; Neo4j ausente é tolerado).
