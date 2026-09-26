# PROJECT STATE

| Campo | Valor |
|---|---|
| **CURRENT PHASE** | **NENHUMA** — SOURCING S4 concluída em 2026-09-26. Aguardando o PO: S5 (UI compartilhada, OI-020) e a implementação comercial de D-059 (OI-021) |
| Última fase concluída | PHASE 15 — PRICING, AI CREDITS & COMMERCIAL MONETIZATION (2026-09-25) |
| Fase 15 | Desbloqueada pelo PO em 2026-09-25 com o prompt "PHASE 15 — PRICING, AI CREDITS & COMMERCIAL MONETIZATION" (substitui o escopo "Public Procurement Pricing") e concluída no mesmo dia. Preço-base do Public Procurement e franquias do Procurement/Full Suite continuam PENDING_FINAL_DEFINITION por decisão do PO |
| Branch de trabalho | `staging` |
| Relatório da última fase | `phases/SOURCING_S4_COMPLETION.md` (antes: `SOURCING_S3_COMPLETION.md`, `SOURCING_S0_S2_COMPLETION.md`, `PHASE_15_COMPLETION.md`) |
| Correção arquitetural | 2026-09-26 — Strategic Sourcing & Bids (D-055, `18_STRATEGIC_SOURCING.md`). Plano S0–S8; **S0–S4 autorizadas e concluídas** em 2026-09-26 (OI-020); S5–S8 não autorizadas. Após o deploy da S3: rodar o backfill (`/cron/sourcing-sincronizar`) uma vez |

## Autorizações

| Fase | Autorizada por | Data | Observações |
|---|---|---|---|
| 0 | Product Owner ("COMEÇAR AGORA PELA PHASE 0") | 2026-09-25 | — |
| 15 | Product Owner ("pode prosseguir e concluir a fase") | 2026-09-25 | Franquias do Public Procurement e da Full Suite: decisão futura do PO |
| S0–S2 (sourcing) | Product Owner ("Autorizado", sobre "S0–S2 são as fases de menor risco para começar") | 2026-09-26 | Sem mudança de schema nem de comportamento; S3–S8 continuam pendentes |
| S3 (sourcing) | Product Owner ("Autorizado", sobre "S3: criar as tabelas unificadas e migrar os dados aos poucos, mantendo as tabelas antigas até os resultados baterem") | 2026-09-26 | Primeira fase com mudança de schema; S4–S8 continuam pendentes |
| S4 (sourcing) + master | Product Owner ("S4: pode trocar" · "master: pode atualizar") | 2026-09-26 | `master` só depois de CI verde no `staging` |
| OI-019 (resolução) | Product Owner ("RESOLUÇÃO OI-019 — ENTERPRISE BIDS & STRATEGIC SOURCING") | 2026-09-26 | Pela regra §25 da própria resolução, a fase corrente (S4) só permite registrar arquitetura, especificação do catálogo, entitlements e documentação; a implementação comercial (planos, catálogo, página de vendas, entitlements no código) depende de fase autorizada (OI-021) |
| 1–17 | Product Owner ("Siga para a Fase 1 […] seguir para a Fase 2 e assim sucessivamente até o final do projeto, fica previamente autorizado o commit e subir todas as fases seguintes") | 2026-09-25 | **Exceções que continuam valendo, por regra do próprio Master Prompt:** Fase 15 só com valores de preço fornecidos pelo PO; nenhum preço ou valor de plano é alterado ou inventado (inclui OI-001) |

## Pendências abertas relevantes

- **OI-001** (crítica): limites 0 nos planos PREDATOR avulsos. Depende de valores do PO.
- **OI-017** (comercial): franquias de AI Credits do Public Procurement (50–100K) e da Full Suite (75–100K) e preço-base do Public Procurement — decisão futura do PO; hoje nada concedido por elas.
- **OI-018** (financeiro): câmbio USD→BRL para a margem de IA (sem ele a margem aparece indisponível).
- **OI-021** (priorização): autorizar a implementação comercial de D-059 (planos, catálogo, entitlements, página de vendas).
- **OI-022** (comercial): preço do buyer seat adicional e dos bundles futuros.
- **OI-020** (priorização): S0–S4 concluídas; S5 (UI compartilhada) e seguintes aguardam o PO.
- **OI-014** (produto): visibilidade padrão de empresas novas no diretório da rede.
- **OI-010** (alta): verificar em produção se as features de IA falhavam por `temperature` com `claude-sonnet-5` (corrigido no código).
- **OI-016** (operação): metas de RPO/RTO.
- OI-003, OI-006 a OI-009: ver `OPEN_ISSUES.md`.
- Conectores de CRM (Fase 13) estão BETA e desligados: habilitar em produção só após validar contra contas reais (TD-069).

## Baseline de qualidade (após a Fase 15)

- Backend: 2.027 passed, 4 skipped (4 testes de Postgres rodam com `B2BON_TESTE_PG_URL`: 4/4 em Postgres 16). Leitura dupla de sourcing ESTRITA em toda a suíte. Migrações validadas também em Postgres 16 (head `a3d5f7b9c1e2`).
- Ruff: 40 (sem novos). Frontend: lint OK (25 warnings), build OK.
- E2E: 6/6.
