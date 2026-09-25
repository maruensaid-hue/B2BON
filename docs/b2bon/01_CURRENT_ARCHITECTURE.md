# 01 — CURRENT ARCHITECTURE (Fase 0, auditoria 2026-09-25)

> Fonte de verdade da arquitetura **atual** a partir da Fase 0 do Master
> Prompt v4. Substitui, como referência canônica, os documentos de raiz
> `CURRENT_ARCHITECTURE.md`, `AI_CURRENT_ARCHITECTURE.md`,
> `SECURITY_BOUNDARIES.md`, `DATA_FLOW_MAP.md` e `NETWORK_GAP_ANALYSIS.md`
> (datados de 2026-09-17). Eles **não foram apagados** (ver `DECISIONS.md`
> D-003); onde esta auditoria diverge deles, vale este documento.
>
> Tudo aqui foi conferido no código do branch `staging` (HEAD `93dede8`).

## 1. Visão geral

B2B ON é um **monólito modular por convenção** (não por fronteira
imposta): um único backend FastAPI, um único banco relacional, um SPA
React. Os "módulos" comerciais (CRM, MAP, PREDATOR, Shoal) são
agrupamentos de routers com gates de licença diferentes — **não são
bounded contexts**: serviços importam modelos e serviços uns dos outros
livremente (ver `DOMAIN_DEPENDENCY_MAP.md`).

```
 Cloudflare Workers (SPA React/Vite, PWA)
            │  HTTPS + JWT (localStorage)
            ▼
 Render — 1 instância FastAPI  ── /api/v1/* (55 routers)
    │         │          │            │
    │         │          │            └─ Anthropic (ClaudeProvider, 1 modelo)
    │         │          └─ Neo4j AuraDB (best-effort, opcional)
    │         └─ Provedores externos (BrasilAPI, Receita Federal recorte,
    │            Lusha, Brave, SendGrid/SMTP, Meta WhatsApp, Google
    │            Calendar, Recall.ai, Mercado Pago, cotação/notícias)
    ▼
 Neon Postgres (dev/test: SQLite)  — 92 tabelas, 71 migrações Alembic
            ▲
 GitHub Actions cron ── POST /cron/* (X-Cron-Secret) — único "scheduler"
```

## 2. Stack

| Camada | Tecnologia | Observação |
|---|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic v2 | `pyproject.toml`, sem lock file |
| Migrações | Alembic (71 revisões) | `alembic/versions/` |
| DB | Postgres (Neon) / SQLite (dev/test) | tenancy por coluna `tenant_id` |
| Grafo | Neo4j AuraDB Free | `app/graph/client.py`, `sincronizar_com_tolerancia` nunca bloqueia |
| IA | Anthropic SDK `>=0.120.2,<1.0` | `app/llm/`, modelo único via `ANTHROPIC_MODEL` (default `claude-sonnet-5`) |
| Frontend | React + TS + Vite, Tailwind v4, PWA | `frontend/src/pages/<modulo>/` |
| Hospedagem | Render (API), Cloudflare Workers (SPA), Neon, AuraDB | `render.yaml`, `frontend/wrangler.toml`, `Dockerfile` |
| Observabilidade | `logging` stdlib + Sentry (`app/main.py`) | sem correlation ID, sem métricas |
| CI | GitHub Actions `ci.yml` (backend pytest, frontend lint+build, e2e Playwright) | dispara só em `master` — **não roda em `staging`** |

## 3. Estrutura do código

```
app/
  api/deps.py         injeção de providers + guards (auth, papel, licença, módulo, rate limit IA)
  api/v1/router.py    composição dos 55 routers + gates por módulo
  api/v1/*.py         routers (finos; chamam services)
  services/*.py       73 serviços de regra de negócio (15.9k linhas)
  models/*.py         92 arquivos de modelo ORM (92 tabelas no metadata, incl. 2 de staging CNPJ em providers/)
  schemas/*.py        Pydantic request/response
  providers/          portas (ABC) + implementações: account_data, calendar,
                      channels/{email,whatsapp}, contact_enrichment, crm,
                      email_validation, meeting_bot, payment, plan_limits,
                      rede_social, web_search
  integrations/       clientes HTTP diretos (brasilapi, site_fetcher, central_negocios)
  llm/                LLMProvider (ABC) + ClaudeProvider
  graph/              Neo4jClient
  core/               config, crypto (Fernet), logging, rate_limit (memória)
```

Padrão de camadas: **router → service → model**, com providers
injetados via `Depends`. Não há camada de repositório nem de domínio
separada; serviços manipulam ORM diretamente.

## 4. Autenticação, autorização, multi-tenancy

- JWT HS256; a cada request `get_usuario_atual` relê `Usuario` do banco
  (papel/tenant efetivos nunca vêm do token).
- Papéis: `super_admin | admin | user`. Hierarquia de tenants
  (`distribuidor → revendedor → cliente`, profundidade ≤ 5) amplia
  visibilidade só para a subárvore (`tenant_ids_no_escopo`).
- Segundo mecanismo: `ChaveApiParceiro` (hash SHA-256) para `/parceiros`.
- Isolamento: **disciplina de código** (filtro `tenant_id` em cada
  query). Sem RLS. 80 de 92 tabelas têm `tenant_id*`; as 12 restantes
  são globais ou herdam escopo por FK (ver `DATABASE_MAP.md`).
- Entitlements: `exigir_licenca_ativa` + `exigir_modulo("map"|"predator"|"crm")`
  aplicados por router em `router.py`; flags finas via `PlanLimitsProvider`
  (ver `PRICING_CURRENT_STATE.md`).

## 5. Módulos como existem hoje

| Módulo | Routers (gate) | Serviços principais |
|---|---|---|
| **CRM** | `crm`, `contas`, `decisores`, `template_proposta` (`_exige_crm`) | `crm_service`, `conta_service` (parcial), `atividade_service`, `proposta_service` |
| **MAP** | `saude_conta` (`_exige_map`); `motor` (interno CyberFort, só `_exige_licenca` + super_admin) | `saude_conta_service`, `motor_service`, `metricas_service`, parte de `crm_service` (LTV/CAC/ROI) |
| **PREDATOR** | 26 routers com `_exige_predator` (icp, ofertas, listas, leads, cadencias, aprovacoes, envios, campanhas, whatsapp, linkedin, reunioes, nps, qualificacao, conversas, regras_aprendidas, inteligencia_rede, agente_corporativo, registro_oportunidade, email_direto, busca, ropa, canais, config_*) | `cadencia_service`, `aprovacao_service`, `envio_service`, `icp_service`, `lista_prospeccao_service`, `conta_service` (geração/enriquecimento), `qualificacao_service`, `reuniao_service`, `sinal_oportunidade_service`, `agente_corporativo_service` … |
| **Shoal** (Business Network) | `rede_social`, `verificacao_empresa`, `central_negocios` (sem gate de licença) | `rede_social_service`, `post_rede_social_service`, `sala_corporativa_service`, `sala_compra_service`, `intent_service`, `relacionamento_empresarial_service`, `seguidor_empresa_service` |
| **Transversal** | auth, convites, planos, admin_tenants, usuarios, painel, faq, onboarding, notificacoes, titulares, auditoria, integracoes, parceiros, webhooks, optout, cron, relatorios | `tenant_service`, `auth_service`, `pagamento_licenca_service`, `auditoria_service`, `webhook_parceiro_service` … |

**Public Procurement / Bid Intelligence**: nenhum código existe
(grep por licitação/edital/PNCP/procurement/tender → só falsos
positivos como "solicitação").

## 6. Processamento assíncrono

Não há fila, worker, Redis ou broker. Todo trabalho assíncrono é
`POST /cron/*` disparado por `.github/workflows/cron-envios.yml`
(`*/15`, `*/30`, diário). Rate limit (`app/core/rate_limit.py`) é em
memória por processo — válido só enquanto houver 1 instância.

## 7. Integrações externas

| Direção | Integração | Onde |
|---|---|---|
| Saída | Anthropic | `app/llm/claude_provider.py` |
| Saída | BrasilAPI, site institucional (fetch HTML) | `app/integrations/` |
| Saída | Receita Federal (recorte CNPJ carregado por script no runner do GH Actions) | `app/providers/account_data/`, `scripts/` |
| Saída | Lusha (contatos), Brave (web search) | `app/providers/contact_enrichment`, `web_search` |
| Saída | SendGrid / SMTP do tenant, Meta WhatsApp Cloud | `app/providers/channels/` |
| Saída | Google Calendar, Recall.ai (bot de reunião) | `calendar`, `meeting_bot` |
| Saída | Mercado Pago (checkout) | `app/providers/payment/mercadopago.py` |
| Saída | Webhooks para parceiros (Distribuidores) | `webhook_parceiro_service` |
| Entrada | Webhooks Meta WhatsApp, SendGrid (ECDSA), Mercado Pago (HMAC), Recall (HMAC) | `app/api/v1/webhooks.py` |
| Entrada | API de parceiros (chave de API) | `app/api/v1/parceiros.py`, `docs/api-parceiros.md` |

`CrmProvider` (`app/providers/crm/`) é uma porta para o **CRM interno**
(`nucleo.py`), não um conector para CRMs externos — não existe nenhum
conector Salesforce/HubSpot/Pipedrive/RD.

## 8. Frontend

- Lazy routes por módulo em `App.tsx`; kit UI próprio
  (`components/ui/`); `lib/api.ts` (fetch fino), `lib/auth.tsx`
  (sessão + `recursos_plano`, espelho client-side dos entitlements).
- Página pública de preços: `pages/Planos.tsx` — **preços hardcoded**
  (ver `PRICING_CURRENT_STATE.md`). Checkout em `pages/CriarConta.tsx`
  lê `GET /planos` (preço do banco).
- Sem WebSocket/SSE.

## 9. Testes e qualidade (estado em 2026-09-25)

Ver `phases/PHASE_0_COMPLETION.md` §Testes para os números desta
auditoria. Estrutura: `tests/unit/`, `tests/integration/` (TestClient +
SQLite por teste), `tests/test_alembic_upgrade.py`, e2e Playwright em
`frontend/e2e/` (3 specs, 4 testes).

## 10. Documentos relacionados

`DOMAIN_DEPENDENCY_MAP.md`, `DATABASE_MAP.md`, `MAP_CURRENT_STATE.md`,
`PREDATOR_CURRENT_STATE.md`, `AI_CURRENT_STATE.md`,
`PRICING_CURRENT_STATE.md`, `SECURITY_BOUNDARIES.md`, `TECHNICAL_DEBT.md`.
