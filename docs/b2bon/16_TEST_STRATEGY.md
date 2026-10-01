# 16 — TEST STRATEGY

## Camadas

| Camada | Onde | Roda no CI |
|---|---|---|
| Unit | `tests/unit/` | sim (`staging` e `master`, D-009) |
| Integração (TestClient + SQLite em memória por teste) | `tests/integration/` | sim |
| Migrações (cabeça única do Alembic) | `tests/test_alembic_upgrade.py` | sim |
| Postgres 16 (concorrência, índices parciais, ordem de NULLs) | `tests/**/*_pg.py`, com `B2BON_TESTE_PG_URL` | não (sob demanda; pulados sem a variável) |
| Orçamento de desempenho contra o baseline | `tests/desempenho/`, com `B2BON_MEDIR` e `B2BON_BASELINE` | não (sob demanda) |
| E2E Playwright (login, negócio, proposta, planos, MAP, workspace de licitação, Strategic Sourcing, portal do fornecedor, tutoriais dos módulos) | `frontend/e2e/` | sim |
| Lint + typecheck + build do frontend | `npm run lint`, `npm run build` | sim |

## Testes arquiteturais e críticos (Master Prompt §78–§82)

| Teste | Arquivo | Desde |
|---|---|---|
| Fronteiras de contexto (fitness function) | `tests/unit/test_fronteiras_contexto.py` | Fase 1 |
| Matriz de entitlement por plano (suíte × avulsos × rotas) | `tests/integration/test_matriz_entitlements.py` | Fase 1 |
| Isolamento de IA entre tenants (§79, parcial) | `tests/integration/test_isolamento_ia_critico.py` | pré-Fase 0 |
| Aprovação humana: não aprovado não envia (§81) | `tests/integration/test_aprovacoes.py`, `test_envios.py` | pré-Fase 0 |
| Fronteira compartilhado/interno das salas (GATE Fase 11) | `tests/integration/test_salas_corporativas.py` | Fase 11 |
| Permissões e ferramentas do Intelligence Agent (GATE Fase 12) | `tests/integration/test_intelligence_agent.py` | Fase 12 |
| Barreira Buy/Sell (§80) | `tests/unit/test_barreira_buy_sell.py` (estrutural), `tests/integration/test_public_procurement.py` (comportamento) | Fase 10 |
| Nenhuma chamada de IA fora do gateway (§82) | `tests/unit/test_gateway_ia_unico_caminho.py` | Fase 4 |
| Nenhuma chamada de IA sem custo/créditos (§82, todas as features registradas) | `tests/unit/test_finops.py` | Fase 5 |
| Isolamento do Corporate Brain / prompt real (§79) | `tests/integration/test_inteligencia_brain.py` | Fase 4 |
| Contrato da API de produto (OpenAPI, auth, isolamento, idempotência) | `tests/integration/test_api_produto.py` | Fase 3 |
| Webhooks de saída + Integration Hub | `tests/integration/test_webhooks_saida_e_hub.py` | Fase 3 |
| Recomendações explicáveis + INSUFFICIENT_INFORMATION (GATE Fase 6) | `tests/integration/test_opportunity_intelligence.py` | Fase 6 |
| Privacidade e fronteiras de tenant na Business Network (GATE Fase 7) | `tests/integration/test_privacidade_rede.py` | Fase 7 |
| Sinal → oportunidade sem duplicação + privacidade do matching (GATE Fase 8) | `tests/integration/test_network_intelligence.py` | Fase 8 |
| Proveniência de documento de licitação (GATE Fase 9) | `tests/integration/test_bid_intelligence.py` | Fase 9 |
| Conformidade dos conectores de CRM (suíte compartilhada) | `tests/conectores_crm.py` + `tests/integration/test_conector_*.py` | Fase 13 |
| Preços preservados nas três cópias | `tests/unit/test_precos_preservados.py` | Fase 14 |
| Métricas de receita e de compras com valor exato + barreira | `tests/integration/test_revenue_intelligence.py` | Fase 16 |
| **Varredura de isolamento**: toda rota GET, tenant × tenant e Buy × Sell, com controle positivo e sem 5xx | `tests/integration/test_varredura_isolamento.py` | Fase 17 |
| Prompt injection ponta a ponta (delimitação, contrato de saída, sensibilidade, ancoragem) | `tests/integration/test_seguranca_ia.py` | Fase 17 |
| Toda rota com IA tem teto de uso (fitness) | `tests/unit/test_limite_ia_nas_rotas.py` | Fase 17 |
| Toda FK tem índice, exceto autoria (fitness) | `tests/unit/test_indices_fk.py` | Fase 17 |
| Orçamento de consultas (sem N+1 na carteira) | `tests/integration/test_desempenho_consultas.py` | Fase 17 |
| Barreira Buy/Sell no núcleo de sourcing (repositório por lado + fitness) | `tests/unit/test_barreira_sourcing.py`, `tests/integration/test_sourcing_repositorio.py` | S2 |
| Espelho, backfill e leitura dupla das tabelas unificadas | `tests/integration/test_sourcing_s3.py` (+ `_pg`) | S3 |
| Workflow e ruleset versionados | `tests/unit/test_sourcing_s4.py`, `test_sourcing_fase_a.py` | S4 / Phase A |
| Comprador privado: fluxos RFP/RFQ/RFI, lado imutável, concorrência | `tests/integration/test_sourcing_fase_e.py` (+ `_pg`) | Phase E |
| Portal do fornecedor: link secreto, visão restrita, esclarecimento anônimo | `tests/integration/test_sourcing_fase_f.py` | Phase F |
| IA do comprador ancorada no texto do fornecedor, créditos, RESTRICTED fora da IA | `tests/integration/test_sourcing_fase_g.py` (+ `_pg`) | Phase G |
| Planos D-059 e preços congelados | `tests/integration/test_comercializacao_fase_i.py`, `tests/unit/test_precos_preservados.py` | Phase I |
| Leitura unificada responde igual à antiga | `tests/integration/test_leitura_unificada_j1.py` (+ `_pg`) | Phase J |
| Usuários do Bid Intelligence por entitlement; Supplier Guest não conta; pool de créditos do tenant | `tests/integration/test_usuarios_bid_intelligence_j3.py` | Phase J |
| Government: componentes, ARR/TCV/Cash-In, renovação, pool anual, catálogo único, comissão por componente | `tests/integration/test_governo.py` (+ `_pg`), `e2e/governo.spec.ts` | D-072 |
| Comissão sobre a Margem Comissionável Líquida: impostos, infraestrutura e IA antes da taxa, AWAITING_COST_PARAMETERS, recálculo, snapshot, PAID imutável, waterfall | `tests/integration/test_comissao_margem.py` | D-074 |
| CBS/IBS 2026: alíquotas-teste preservadas, WAIVED = caixa zero e margem intacta, COMPENSATED sem dupla contagem, PAYABLE, vigência do status, PAID imutável, snapshot e MAP | `tests/integration/test_cbs_ibs_2026.py` | D-078 |
| Render Web Service 12c-96g CUSTOM: sem preço, pool aguarda, pendência CUSTOM, migração auditada e reversível | `tests/integration/test_precos_fornecedores.py`, `tests/test_alembic_upgrade.py` | D-079 |
| Preços públicos dos fornecedores: Render Scale/Web Service, Postgres e Key Value fora do pool, Neon por envelope (benchmark não é custo), Lusha Premium no pool de dados, CUSTOM sem preço, PTAX, dupla contagem, prioridade da fonte, pesos BID/SOURCING, capacidade não alocada, snapshot imutável | `tests/integration/test_precos_fornecedores.py` | D-077 |
| Infrastructure Cost Pool: real × provisionado, plano máximo, pesos 1/2/4 configuráveis, atribuição direta, sem dupla contagem IA/API, limiares 70/80/90/100, alertas sem upgrade automático, projeção, Provider Economics, PTAX, isolamento | `tests/integration/test_infraestrutura_pool.py` | D-076 |
| Entitlements Government do PO no catálogo único; Tax Engine (presunção, ISS SP 1.05, CBS/IBS-teste fora da carga, adicional de IRPJ, pendências); infraestrutura por categoria/método; câmbio por vigência e AWAITING_FX_RATE; IA só pela política | `tests/integration/test_parametros_financeiros.py` | D-075 |

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
| 4 | 1.648 passed | lint OK (25 warnings), build OK | 4/4 |
| merge | 1.681 passed | build OK | — |
| 5 | 1.711 passed | lint OK (25 warnings), build OK | 4/4 |
| 6 | 1.761 passed | lint OK (25 warnings), build OK | 4/4 (criar-negocio cobre o card de inteligência) |
| 7 | 1.795 passed | lint OK (25 warnings), build OK | 4/4 |
| 8 | 1.805 passed | lint OK (25 warnings), build OK | 4/4 |
| 9 | 1.825 passed | lint OK (25 warnings), build OK | 4/4 |
| 10 | 1.840 passed | lint OK (25 warnings), build OK | 4/4 |
| 11 | 1.844 passed | lint OK (25 warnings), build OK | 4/4 |
| 12 | 1.857 passed | lint OK (25 warnings), build OK | 4/4 |
| 13 | 1.917 passed | lint OK (25 warnings), build OK | 4/4 |
| 14 | 1.926 passed | lint OK (25 warnings), build OK | 5/5 (+ página pública de planos) |
| 16 | 1.933 passed | lint OK (25 warnings), build OK | 5/5 |
| 17 | 1.953 passed (+ carga e restore em Postgres 16) | lint OK (25 warnings), build OK, 0 vulnerabilidades | 5/5 |
| 15 | 1.996 passed | lint OK (25 warnings), build OK | 6/6 |
| A | 2.047 passed | lint OK (25 warnings), build OK | 6/6 |
| B | 2.051 passed | lint OK (25 warnings), build OK | 6/6 |
| C | 2.056 passed | lint OK (25 warnings), build OK | 8/8 |
| D | 2.060 passed | lint OK (25 warnings), build OK | 8/8 |
| E | 2.067 passed (+ Postgres) | lint OK (25 warnings), build OK | 9/9 |
| F | 2.071 passed | lint OK (25 warnings), build OK | 10/10 |
| G | 2.078 passed (+ Postgres) | lint OK (25 warnings), build OK | 10/10 |
| H | 2.080 passed | lint OK (25 warnings), build OK | 11/11 |
| I | 2.086 passed (+ Postgres 7/7) | lint OK (25 warnings), build OK | 12/12 |
| J | 2.094 passed (+ Postgres 8/8) | lint OK (25 warnings), build OK | 12/12 |
| Docs/onboarding (2026-10-01) | 2.094 passed | lint OK (25 warnings), build OK | 13/13 (+ tutoriais dos módulos) |
| Government (2026-10-01) | 2.117 passed (+ Postgres 9/9) | lint OK (25 warnings), build OK | 17/17 |
| D-074 margem comissionável (2026-10-01) | 2.128 passed (+ Postgres 9/9) | lint OK (25 warnings), build OK | 17/17 |
| D-075 parâmetros do PO (2026-10-01) | 2.143 passed (+ Postgres 9/9) | lint OK (25 warnings), build OK | 17/17 |
| D-076 infraestrutura conservadora (2026-10-01) | 2.163 passed (+ Postgres 9/9) | lint OK (25 warnings), build OK | 17/17 |
| D-077 preços públicos dos fornecedores (2026-10-01) | 2.175 passed (+ Postgres 9/9) | lint OK (25 warnings), build OK | 17/17 |
| D-078 CBS/IBS 2026 (2026-10-01) | 2.181 passed (+ Postgres 9/9) | lint OK (25 warnings), build OK | 17/17 |
| D-079 Render 12c-96g CUSTOM (2026-10-01) | 2.182 passed (+ Postgres 9/9) | ruff 40 (baseline), frontend sem mudança | não afetado |
