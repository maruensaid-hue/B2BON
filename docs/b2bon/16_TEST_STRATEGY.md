# 16 — TEST STRATEGY

## Camadas

| Camada | Onde | Roda no CI |
|---|---|---|
| Unit | `tests/unit/` | sim (`staging` e `master`, D-009) |
| Integração (TestClient + SQLite em memória por teste) | `tests/integration/` | sim |
| Migrações (cabeça única do Alembic) | `tests/test_alembic_upgrade.py` | sim |
| E2E Playwright (login, criar negócio, gerar proposta) | `frontend/e2e/` | sim |
| Lint + typecheck + build do frontend | `npm run lint`, `npm run build` | sim |

## Testes arquiteturais e críticos (Master Prompt §78–§82)

| Teste | Arquivo | Desde |
|---|---|---|
| Fronteiras de contexto (fitness function) | `tests/unit/test_fronteiras_contexto.py` | Fase 1 |
| Matriz de entitlement por plano (suíte × avulsos × rotas) | `tests/integration/test_matriz_entitlements.py` | Fase 1 |
| Isolamento de IA entre tenants (§79, parcial) | `tests/integration/test_isolamento_ia_critico.py` | pré-Fase 0 |
| Aprovação humana: não aprovado não envia (§81) | `tests/integration/test_aprovacoes.py`, `test_envios.py` | pré-Fase 0 |
| Barreira Buy/Sell (§80) | — | Fase 10 |
| Nenhuma chamada de IA sem medição (§82) | — | Fases 4/5 |
| Contrato da API de produto (OpenAPI, auth, isolamento, idempotência) | `tests/integration/test_api_produto.py` | Fase 3 |
| Webhooks de saída + Integration Hub | `tests/integration/test_webhooks_saida_e_hub.py` | Fase 3 |

## Regras

- Toda correção de acoplamento vem com um caso na matriz de entitlement.
- Toda nova fronteira de contexto entra na fitness function.
- Testes que dependem de binário externo usam marcador de skip
  (`tests/markers.py::requer_ffmpeg`). O CI instala o binário e roda o teste.
- E2E local neste ambiente: o Chromium pré-instalado exige
  `launchOptions.executablePath=/opt/pw-browsers/chromium` (config
  temporária, não commitada).

## Baseline por fase

| Fase | Backend | Frontend | E2E |
|---|---|---|---|
| 0 | 1.465 passed | lint OK (25 warnings), build OK | 4/4 |
| 1 | 1.530 passed | lint OK (25 warnings), build OK | 4/4 |
| 2 | 1.592 passed (+ migração em Postgres 16) | sem mudança | sem mudança |
| 3 | 1.625 passed | lint OK (25 warnings), build OK | 4/4 |
