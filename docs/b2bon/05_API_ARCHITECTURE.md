# 05 — API ARCHITECTURE (Fase 3)

## 1. Três superfícies de API

| Superfície | Prefixo | Autenticação | Quem usa |
|---|---|---|---|
| API interna do app | `/api/v1/*` (routers em PT: `/crm`, `/saude-contas`, `/cadencias`…) | JWT (papel + tenant relidos do banco) | SPA da B2B ON |
| **API de produto** | `/api/v1/map/*`, `/api/v1/predator/*` | Chave de API do tenant (`X-API-Key` ou `Authorization: Bearer b2bk_…`) | Sistemas do cliente, CRMs externos |
| API de provisionamento (Distribuidores) | `/api/v1/parceiros/*` | `ChaveApiParceiro` | Sistema do Distribuidor (`docs/api-parceiros.md`) |

Gestão da API de produto pelo tenant (JWT, admin): `/api/v1/chaves-api`,
`/api/v1/webhooks-saida`, `/api/v1/hub-integracoes/*`. UI: **Admin → API & Webhooks**.

## 2. Versionamento

- Versão no path (`/api/v1`). Mudança incompatível = `/api/v2` convivendo.
- Adicionar campo opcional em resposta não quebra contrato. Remover ou renomear quebra.
- Contrato verificado em `tests/integration/test_api_produto.py::test_contrato_openapi_das_apis_de_produto` (paths, métodos, headers obrigatórios, schemas de resposta). OpenAPI completo em `/openapi.json`.

## 3. Autorização da API de produto (`autenticar_api(escopo, modulo)`)

Ordem de checagem, toda no backend (§74):

1. Chave existe (hash SHA-256) e não está revogada → senão **401**.
2. Rate limit por chave: 120 req/min (`limitador_api`) → **429**.
3. Escopo presente na chave (`map:read`, `predator:read`, `predator:write`) → **403**.
4. Licença do tenant ativa (mesma regra hierárquica do app) → **403**.
5. Módulo contratado no plano (`Entitlements.has_module`) → **403**.

`tenant.hasApiAccess(modulo)` = módulo no plano **e** escopo na chave.
Não há flag comercial de "API access" no plano ainda (Fase 14, TD-012).

Isolamento: o tenant vem **sempre** da chave. Dados canônicos enviados
no corpo têm `tenant_id` sobrescrito (`PayloadCrmAdapter`).

## 4. Endpoints de produto (Fase 3)

| Endpoint | Escopo | O que faz |
|---|---|---|
| `POST /map/analyze` | map:read | economia (LTV/CAC/churn/ROI/CS) + risco por conta. Sem `dados`: CRM da B2B ON. Com `dados` (canônico): dados enviados, sem persistir |
| `POST /map/churn/predict` | map:read | risco por conta, `metodologia.risco = RULE_BASED_V1` (declarado: não é ML) |
| `POST /map/customer-score` | map:read | CS Score por conta |
| `POST /map/ltv`, `/map/cac`, `/map/roi` | map:read | métrica isolada + detalhe; `null` quando não há dado |
| `GET /predator/icps` | predator:read | ICPs do tenant |
| `GET /predator/accounts` | predator:read | contas no modelo canônico, paginadas por cursor |
| `POST /predator/company/enrich` | predator:read | dados oficiais do CNPJ (BrasilAPI), `origin=OFFICIAL`, sem persistir |
| `POST /predator/lists/generate` | predator:write | gera lista por ICP; **exige `Idempotency-Key`** |

Não implementados por dependerem de IA medida (Fase 4): `/map/churn/remediation`,
`/predator/icp/generate`, `/predator/company/analyze` (site),
`/predator/decision-makers/find` via IA, `/predator/cadence|message/generate`,
`/predator/response/suggest`.

## 5. Idempotência

Toda escrita da API de produto exige `Idempotency-Key` (8–128 chars).
Mesma chave + mesmo corpo → resposta original gravada, header
`Idempotent-Replayed: true`, sem reexecutar. Mesma chave + corpo
diferente → **409**. Tabela `registro_idempotencia` (única por tenant+chave).

## 6. Erros

`{"detalhe": "<mensagem em português>"}` com 401/403/404/409/422/429/500,
mesmo formato do app. Validação de schema do FastAPI devolve 422 com `detail`.

## 7. Observabilidade

`X-Request-ID` aceito (se seguro) ou gerado, devolvido em toda resposta,
presente em cada linha de log (`[correlation_id]`) e gravado em
`evento_dominio.correlation_id`. Log de acesso por requisição:
método, rota, status, latência. Nunca corpo, query nem headers.

## 8. "Cliente zero"

A B2B ON já consome os próprios contratos internamente (`map.contract`,
`predator.contract`). A tela da B2B ON ainda chama as rotas internas em
PT, não a API de produto (TD-043): migrar as telas para a API de
produto exigiria autenticação por chave no navegador, o que não é
desejável. O princípio é atendido no nível de contrato, não de HTTP.

## 9. Correção 2026-09-26 — recursos canônicos de sourcing (D-055)

Alvo: `/sourcing/{sell|buy}/processes` e sub-recursos `requirements`, `documents`, `participants`,
`evaluations`, `tasks`, `contracts`, paginados por cursor, com **o lado vindo da rota e do módulo,
nunca do corpo**. Análise de documento vira assíncrona (202 + status). `/bids/*` e `/procurement/*`
(46 rotas) ficam como fachada durante a migração; permanecem só as rotas de comportamento exclusivo
(Go/No-Go, cofre, concorrentes, PCA, demandas, pesquisa de preço). Nada implementado ainda:
`18_STRATEGIC_SOURCING.md` §5.2.
