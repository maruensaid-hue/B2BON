# B2B ON GOVERNMENT — Completion Report

- **Data**: 2026-10-01 · **Branch**: `staging` · **ADR**: D-072 · **Migração**: `d9e1f3a5b7c9` (reversível)
- **Pedido**: prompt do PO "B2B ON GOVERNMENT — Licenciamento governamental + subscrição anual + pricing + publicação"
  (preços, AI Credits e política de comissão definidos pelo PO).

## Impacto e reuso

| Mecanismo existente | Como foi evoluído (sem engine nova) |
|---|---|
| Catálogo central (tabela `plano`) | segmento, modelo de cobrança, licença, implantação, subscrição anual, AI Credits anuais, recomendado, entitlements JSON |
| Carteira de AI Credits (lotes + ledger + FEFO + trava) | pool anual = lote SUBSCRIPTION por período do contrato; plano anual sem franquia mensal |
| Comissões (`comissao_representante` + repasse mensal) | comissão por componente e por recebimento, CLAWBACK, divisão, override |
| Auditoria (`audit_log`) | plano, contrato, desconto, renovação, recebimento, estorno, política, template, comissão, pipeline |
| Rotina horária de AI Credits | concede o pool do período que começou, encerra o que terminou e marca o aviso de renovação |
| Página `/planos` + `GET /catalogo` | seção "B2B ON Government" do catálogo; link "Planos e preços" na página inicial (login) |
| Admin → Planos | tabela Government (licença, implantação, subscrição, periodicidade, entitlements, AI Credits, status, módulos, contratação inicial) e formulário por segmento |

Novo: contexto `app/contexts/governo` (ofertas, contratos, recebimentos, comissões, pipeline, analytics, políticas),
`/api/v1/governo/*` (operação: super_admin; `meu-contrato`: cliente, sem comissões), Admin → Government, cartão do contrato
em Assinatura, margem de contribuição no MAP (`/motor/tenants/{id}/margem-contribuicao`).

## Critérios de aceite

| Critério | Estado | Evidência |
|---|---|---|
| Três planos Government no Pricing Catalog | ✅ | migração; `test_migracao_government_cria_ofertas_e_volta` (SQLite e Postgres 16) |
| Department 72k + 12k + 24k; Professional 120k + 20k + 36k; Enterprise 180k + 30k + 54k | ✅ | `test_contratacao_inicial_e_componentes_separados` |
| AI Credits anuais 300k / 600k / 1,2M | ✅ | idem; pool na carteira (`test_pool_anual_de_ai_credits_expira_e_renova`) |
| Professional recomendada | ✅ | catálogo + E2E "Recomendado" |
| Página pública mostra os três planos, sem "/mês" | ✅ | `e2e/governo.spec.ts` (desktop, tablet, celular) |
| Página de preços acessível pela página inicial | ✅ | link "Planos e preços" no login → `/planos` (E2E) |
| Admin → Planos mostra os planos Government | ✅ | E2E "Admin → Planos" |
| Público e Admin com a mesma fonte | ✅ | `test_pagina_publica_e_admin_iguais_ao_catalogo` (+ nenhum preço Government no frontend) |
| License, Implementation e Subscription separados | ✅ | componentes por tipo |
| ARR só com receita recorrente; licença e implantação fora | ✅ | `test_arr_bookings_tcv_e_cash_in` |
| TCV inicial correto | ✅ | idem (176.000 no Professional) |
| Renovação não cobra licença | ✅ | `test_renovacao_nao_cobra_licenca_e_comissao_fica_em_10` |
| AI Credits pelo ledger universal | ✅ | lote da carteira, consumo pelo AI Gateway existente |
| Subscription Only suportado | ✅ | `test_subscription_only_licenca_zero_valores_configuraveis_20_e_10` |
| Planos privados sem regressão | ✅ | `test_planos_privados_sem_regressao`; preços privados congelados (`test_precos_preservados`) |
| Comissão: 20% inicial (licença + subscrição), 10% em todas as renovações, implantação fora, flag configurável, PAYMENT_RECEIVED, parcelas, estorno, reajuste, transferência, override auditado, Subscription Only, isolamento, MAP | ✅ | 9 testes de comissão em `test_governo.py` |
| Testes, build, typecheck, lint | ✅ | ver abaixo |
| Documentação | ✅ | D-072, 15 §6, 13 §6, PRICING_CURRENT_STATE, OPEN_ISSUES (OI-024/025), Manual, PROJECT_STATE, CHANGELOG |

## Code size guard (§34) e duplicação (§35)

| Métrica | Valor |
|---|---|
| Aplicação (app + migração) | +1.873 / −20 (27 arquivos; contexto `governo` ≈ 1.050) |
| Frontend | +1.229 / −90 (Admin → Government ≈ 585, já formatado) |
| Testes | +427 / −1 (`test_governo.py` 22 casos, `test_governo_pg.py`, migração) + `e2e/governo.spec.ts` (4 casos) |
| Duplicação | **42** blocos / ~1.877 linhas (inalterada) |

## Desempenho (§36) — `perf/governo.json` contra `perf/fase_i.json`

Consultas por rota **iguais** em todas as 13 rotas medidas; latências dentro da variação da medição. `GET /catalogo` e
`GET /assinatura` ganham uma consulta pelas ofertas Government e uma pelo contrato do tenant.

## Validação

| Evidência | Resultado |
|---|---|
| Suíte completa | ✅ **2.117 passed** (+10 skipped: 9 Postgres, 1 medição) — eram 2.094 |
| Postgres 16 | ✅ `PG_MIGRACOES_OK d9e1f3a5b7c9` (subida, descida até `c5e7a9b1d3f4`, subida); testes PG **9/9** |
| E2E | ✅ **17/17** (+4 Government; +1 tutoriais da rodada anterior) |
| Ruff 40 · oxlint 25 · build (typecheck) | ✅ sem novos |

## Não feito / pendente do PO

- Composição de cada tier (módulos além de Compras públicas, usuários, unidades, SLA, armazenamento etc.): OI-024.
- Comissão sobre serviços e créditos adicionais, alíquota de impostos, rateio de infraestrutura e gatilho por nota fiscal
  (não existe integração fiscal): OI-025.
- Preço do Public Procurement para clientes privados continua PENDING_DEFINITION (OI-017).

## Adendo D-073 (mesmo dia) — comissão sobre o lucro líquido

- Base de **toda** comissão (privada e Government) = recebido − impostos − infraestrutura (`app/services/comissao_service.py`,
  política `BASE_LIQUIDA`). Sem alíquotas: `pendente_parametros`, recalculada ao definir (OI-026).
- Serviços e AI Credits adicionais: 10% (política Government v2). Margem de contribuição do MAP usa as mesmas alíquotas.
- Migração `e1f3a5b7c9d2` (SQLite e Postgres 16, subida/descida). Suíte **2.121 passed**, Postgres 9/9, E2E 17/17,
  ruff 40, lint 25, duplicação 42.
