# CHANGELOG — IMPLEMENTATION

## Fase 1 — Domain Separation (2026-09-25)

- Novo pacote `app/contexts/` com `shared` (entitlements, Organization/Person),
  `crm`, `map` e `predator`, cada um com `contract.py`.
- MAP: algoritmo de risco único; economia (LTV/CAC/churn/ROI/CS) movida
  do CRM; porta `MapDataSource`; painel próprio (`/saude-contas/desempenho/*`,
  `/saude-contas/vendedores-com-contas`).
- PREDATOR: prospecção extraída de `conta_service` para
  `contexts/predator/prospeccao.py`; rotas movidas para `prospeccao_contas.py`
  (mesmos paths, gate PREDATOR).
- Gates: `exigir_algum_modulo`; contas/decisores/leads/ofertas → CRM ou
  PREDATOR; nps → MAP ou PREDATOR.
- Frontend: `PainelDesempenho` com `origem`; `MapContas` usa as rotas do MAP.
- Testes: matriz de entitlement (61), fitness function de fronteiras (4),
  skip de ffmpeg.
- CI: roda também em `staging`.
- Docs: aviso nos docs de raiz; 02/03 escritos; estado atualizado.
- **Sem migração, sem mudança de preço ou plano.**

## Fase 0 — Complete Discovery & Audit (2026-09-25)

**Código de produção alterado: nenhum.** Preços, planos e entitlements
não foram tocados.

Adicionado (só documentação, em `docs/b2bon/`):
- Estrutura de memória persistente: `00_MASTER_ARCHITECTURE.md`,
  `PROJECT_STATE.md`, `DECISIONS.md`, `OPEN_ISSUES.md`,
  `TECHNICAL_DEBT.md` e este changelog.
- Entregáveis da Fase 0: `01_CURRENT_ARCHITECTURE.md`,
  `DOMAIN_DEPENDENCY_MAP.md`, `DATABASE_MAP.md`, `MAP_CURRENT_STATE.md`,
  `PREDATOR_CURRENT_STATE.md`, `AI_CURRENT_STATE.md`,
  `PRICING_CURRENT_STATE.md`, `SECURITY_BOUNDARIES.md`.
- Placeholders `02`–`17` para as fases seguintes.
- `phases/PHASE_0_COMPLETION.md`, `phases/PHASE_1_PLAN.md`.

Principais achados: planos PREDATOR avulsos com limites 0 (OI-001);
7 acoplamentos que quebram a contratação avulsa (C1–C7); 11 de 14
chamadas de IA sem medição; preço em 3 lugares; CI não roda em `staging`.
