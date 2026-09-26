# 00 — MASTER ARCHITECTURE (índice e regras de execução)

Ponto de entrada da memória persistente do projeto de evolução da B2B ON
para a **Business, Revenue & Procurement Intelligence Platform**
(Master Prompt v4).

## Regras de execução (resumo do Master Prompt §1–§3)

1. Executar **somente** a `CURRENT PHASE` definida em `PROJECT_STATE.md`.
2. Nunca iniciar a fase seguinte sem autorização explícita do Product Owner.
3. Ao iniciar uma sessão: ler este arquivo, `PROJECT_STATE.md`,
   `DECISIONS.md`, `OPEN_ISSUES.md`, `TECHNICAL_DEBT.md` e o último
   `phases/PHASE_X_COMPLETION.md`. Depois, `git status`.
4. Ao encerrar uma fase: testes, regressão, critérios de aceite,
   atualização de todos os documentos de estado, `PHASE_X_COMPLETION.md`, PARAR.
5. Nunca inventar preços. Public Procurement fica com preço
   `PENDING_DEFINITION` até instrução do PO (§71, Fase 15).
6. Não fazer big-bang rewrite. Usar Strangler Pattern. Sem
   microserviços prematuros (D-002).

## Mapa de documentos

| Documento | Conteúdo | Atualizado na fase |
|---|---|---|
| `PROJECT_STATE.md` | fase corrente, status, próximos passos | toda |
| `DECISIONS.md` | ADRs | toda |
| `OPEN_ISSUES.md` | pendências para o PO | toda |
| `TECHNICAL_DEBT.md` | dívida técnica | toda |
| `CHANGELOG_IMPLEMENTATION.md` | o que mudou por fase | toda |
| `01_CURRENT_ARCHITECTURE.md` | arquitetura atual | 0 |
| `DOMAIN_DEPENDENCY_MAP.md` | acoplamento CRM/MAP/PREDATOR/Shoal | 0 |
| `DATABASE_MAP.md` | 92 tabelas, tenancy | 0 |
| `MAP_CURRENT_STATE.md`, `PREDATOR_CURRENT_STATE.md` | estado dos módulos | 0 |
| `AI_CURRENT_STATE.md` | 14 call sites de IA, ledger, HITL | 0 |
| `PRICING_CURRENT_STATE.md` | preços, planos, entitlements, billing | 0 |
| `SECURITY_BOUNDARIES.md` | fronteiras e riscos | 0 |
| `02`–`17` | arquitetura alvo por tema (placeholders até a fase dona) | 1–17 |
| `18_STRATEGIC_SOURCING.md` | correção: 4 segmentos, engines de sourcing compartilhados, plano S0–S8 | correção 2026-09-26 |
| `phases/` | `PHASE_X_COMPLETION.md` e planos de fase | toda |

## Segmentos da plataforma (correção 2026-09-26, D-055)

```
B2B ON PLATFORM
├── REVENUE INTELLIGENCE ........ (1) B2B Sales: CRM · PREDATOR · MAP · Opportunity · Business Network
└── STRATEGIC SOURCING & BIDS
    ├── SELL ... (2) Public Sector Bids · Enterprise Bids (RFP/RFI/RFQ privados)
    └── BUY .... (3) Public Procurement · (4) Enterprise Strategic Sourcing
```

Produtos (D-059, por job-to-be-done):
- **B2B ON Bid Intelligence** (SELL; Public + Enterprise Bids; R$ 1.490/mês; 25K AI Credits);
- **B2B ON Strategic Sourcing** (BUY privado; R$ 2.990/mês; 5 buyer users; 50K);
- **Strategic Sourcing Enterprise** (a partir de R$ 5.990/mês; 100K);
- **B2B ON Public Procurement** (BUY público; preço pendente).

Os segmentos são experiências configuradas sobre engines compartilhados (Workflow, Document,
Requirement, Evaluation, Matching, Supplier, Contract, Graph, Intelligence, AI Gateway, Notification,
Audit, Integration Hub), não sistemas separados. Enterprise Bids e Enterprise Strategic Sourcing estão
**desenhados, não implementados**. Detalhe, gaps e plano: `18_STRATEGIC_SOURCING.md`.

## Arquitetura em uma frase (estado atual)

Monólito FastAPI + Postgres + SPA React, multi-tenant por coluna, com 4
"módulos" comerciais (CRM, MAP, PREDATOR, Shoal). Eles são separados
por gate de licença, **mas não por fronteira de código**. A IA passa
por um único `LLMProvider` (Anthropic) e só 3 de 14 chamadas são medidas.
Procurement e Bid Intelligence não existem.

## Roadmap (Master Prompt §84)

0 Discovery ✅ · 1 Domain Separation · 2 Canonical Model · 3 API &
Integration Foundation · 4 AI Foundation · 5 AI FinOps & Credits ·
6 Opportunity Intelligence · 7 Business Network Foundation · 8 Network
Intelligence · 9 Bid Intelligence · 10 Public Procurement · 11 Rooms ·
12 Agent Orchestration · 13 External CRM Connectors · 14 Catalog/Plans/
Sales Page · 15 Public Procurement Pricing (**só com instrução do PO**) ·
16 Analytics · 17 Hardening.

**Plano unificado de sourcing (2026-09-26, D-061):** depois das fases 0–17 e de S0–S4, a ordem passa a ser A · Foundation ✅ ·
B · Document & Requirement Engine · C · Sell side · D · Public buy side · E · Enterprise buy side · F · Business Network ·
G · Intelligence · H · Optimization · I · Commercialization — uma por vez, cada uma com autorização do PO
(`18_STRATEGIC_SOURCING.md` §10). Toda fase mede desempenho contra `docs/b2bon/perf/baseline.json` e roda a análise de
duplicação (`scripts/qualidade/duplicacao.py`).
