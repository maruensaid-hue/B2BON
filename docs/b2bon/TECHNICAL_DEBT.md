# TECHNICAL DEBT

Registro vivo. Cada item: ID, descrição, evidência, impacto, fase sugerida.
Status: `OPEN | IN_PROGRESS | PAID`.

## Arquitetura / domínio

| ID | Dívida | Evidência | Impacto | Fase | Status |
|---|---|---|---|---|---|
| TD-001 | `conta_service.py` (1.683 linhas, 53 funções) mistura CRM, PREDATOR e Intelligence | `DOMAIN_DEPENDENCY_MAP.md` §5 | Impede separar os contextos | 1 | OPEN |
| TD-002 | `crm_service.py` (1.022 linhas) contém LTV/CAC/ROI (MAP) e meeting brief (Intelligence) | idem | MAP depende do CRM | 1 | OPEN |
| TD-003 | Algoritmo de risco de churn duplicado (`motor_service` e `saude_conta_service`) | `MAP_CURRENT_STATE.md` §2 | Divergência silenciosa | 1 | OPEN |
| TD-004 | Gates de módulo aplicados por router inteiro, com routers que misturam módulos | `router.py`, `contas.py` | 403 ou concessão indevida (C1–C7) | 1 | OPEN |
| TD-005 | Sem camada de contrato entre módulos. Serviços acessam ORM de outros módulos | `DOMAIN_DEPENDENCY_MAP.md` §2–3 | Acoplamento; dificulta API-first | 1–3 | OPEN |
| TD-006 | Modelos com nomes de domínio em PT e sem mapeamento canônico (`Conta`, `Decisor`, `Negocio`) | — | Integração com CRMs externos | 2 | OPEN |
| TD-007 | `CrmProvider` é porta para o CRM **interno**, com nome que sugere conector externo | `app/providers/crm/` | Confusão na Fase 13 | 2/3 | OPEN |

## Comercial / billing

| ID | Dívida | Evidência | Impacto | Fase | Status |
|---|---|---|---|---|---|
| TD-010 | Preço em 3 lugares (DB, `Planos.tsx`, `bootstrap_tenant.py`) | `PRICING_CURRENT_STATE.md` §1 | Cobrança diferente do anunciado | 14 | OPEN |
| TD-011 | `preco_mensal` é `NOT NULL Float`, sem `price_status` nem moeda. Float para dinheiro | `app/models/plano.py` | Não representa "preço a definir" (§71); arredondamento | 14 | OPEN |
| TD-012 | Entitlements como colunas booleanas em `Plano` (1 migração por flag nova) | `plano.py`, `PlanLimitsProvider` | Não escala para feature/add-on/crédito | 14 (fundação na 1/5) | OPEN |
| TD-013 | 1 licença por tenant, sem add-ons | `licenca.py` (unique `tenant_id`) | Não suporta "base + módulos + créditos" (§73) | 14 | OPEN |

## IA

| ID | Dívida | Evidência | Impacto | Fase | Status |
|---|---|---|---|---|---|
| TD-020 | 11 de 14 call sites de IA não medidos | `AI_CURRENT_STATE.md` §2 | FinOps impossível; gate §82 falha | 4/5 | OPEN |
| TD-021 | Ledger `registro_uso_ia` best-effort, com campos insuficientes | idem §3 | Perda silenciosa de uso | 5 | OPEN |
| TD-022 | `LLMRequest` sem contexto (tenant, módulo, feature, classe de modelo) | `app/llm/schemas.py` | Não há roteamento nem atribuição | 4 | OPEN |
| TD-023 | Sem delimitação de dado externo nos prompts | idem §6 | Prompt injection | 4 | OPEN |
| TD-024 | Rate limit de IA só em 5 rotas. Webhooks e cron sem limite | idem §2 | Custo sem controle | 4/5 | OPEN |

## Infra / processo

| ID | Dívida | Evidência | Impacto | Fase | Status |
|---|---|---|---|---|---|
| TD-030 | CI só em `master`; `staging` sem CI | `.github/workflows/ci.yml` | Regressões chegam ao staging | — (OI-005) | OPEN |
| TD-031 | Sem lock file Python (`pyproject.toml` com ranges) | comentários no próprio `pyproject`/`claude_provider.py` | Drift de SDK já causou incidente | 17 | OPEN |
| TD-032 | Rate limit em memória, 1 instância, sem fila/worker | `app/core/rate_limit.py` | Não escala horizontalmente | 17 | OPEN |
| TD-033 | Sem correlation ID nem métricas; só logging + Sentry | `app/core/logging.py` | Observabilidade (§76) | 3 | OPEN |
| TD-034 | Testes de mídia dependem de `ffmpeg` no host, sem skip quando ausente | 6 falhas no ambiente sem ffmpeg | Suite falha fora do CI | 1 | OPEN |
| TD-035 | 25 warnings de lint (`react-hooks/exhaustive-deps`) no frontend | `npm run lint` | Bugs sutis de re-render | oportunista | OPEN |
| TD-036 | Documentação de arquitetura duplicada (raiz × `docs/b2bon/`) | D-003 | Confusão sobre qual é a fonte | 1 | OPEN |
| TD-037 | `starlette.testclient` com `httpx` deprecated (warning) | saída do pytest | Quebra futura na atualização | oportunista | OPEN |
