# MAP PERFORMANCE COMERCIAL — Completion Report

- **Data**: 2026-10-01 · **Branch**: `staging` · **ADR**: D-080 · **Migração**: `f3b5d7f9a1c4` (reversível)
- **Pedido**: prompt do PO "Ajuste do MAP: Quotas, Funil, Comissão e Campanha" — gerir quotas, ramp-up, funil,
  produtividade, comissão, campanha e exceções dos 7 representantes autônomos, sem subsistema redundante.

## Reuso (sem engine nova)

| Mecanismo existente | Como foi usado |
|---|---|
| `Representante` (comissão) | + `usuario_id`: o usuário do representante no CRM da CyberFort (fonte de atividade e pipeline) |
| CRM interno (`Atividade`, `Reuniao`, `Negocio`, `PropostaNegocio`, `Conta`, `Decisor`) | lido só via `crm.contract` (fronteira de contexto preservada), em consultas agrupadas por vendedor |
| Pagamentos (`PagamentoLicenca`) + `Tenant.representante_id` | New MRR = 1ª mensalidade aprovada de cliente novo, só PRIVATE |
| Commission Engine (D-074) | comissão recorrente lida e agregada; repasse respeita a retenção por inadimplência |
| Pipeline Government (`OportunidadeGoverno`, `ContratoGoverno`) | Government Pipeline separado da quota privada |
| `politica_comissao` (versionada, auditada) | MAP_PERFORMANCE_POLICY, PRIVATE_RECURRING_COMMISSION e CAMPAIGN:SUMMER_SALES_CHALLENGE_2026 |
| Eventos de domínio | `MeetingCompleted` passa a ser publicado; `ProposalSent` criado (os únicos que faltavam) |

Única tabela nova: `quota_comercial` (quota NEW_MRR versionada, padrão ou por representante).

## Entregue (prompt §2–§15)

- **Quota** (§2): R$ 7.500 → R$ 20.000 por representante (Out/26–Mar/27); equipe = soma (R$ 52.500 → R$ 140.000);
  configurável por período e representante, com versão e auditoria; nada no frontend.
- **Cobertura** (§3): alvo gerencial de Out/26 R$ 30.000 de pipeline qualificado; depois 3x a quota (configurável).
- **Funil** (§4): baseline de outubro na política; taxas observadas (janela de 90 dias) substituem o baseline só com
  amostra mínima — nunca constantes imutáveis.
- **Atividade** (§5): metas diária e semanal; "conta trabalhada" = ICP validado + persona/contato alvo + ação humana;
  disparo automático não conta.
- **Mix e ticket** (§6): ticket baseline R$ 1.750; mix por família; Mix Quality (≥ 50% em Suite + Bid Intelligence +
  Strategic Sourcing) como indicador, sem bloquear venda.
- **Sales velocity** (§7): FAST 15 / CORE 45 / STRATEGIC 180 dias; forecast pelo fechamento previsto; Government em TCV,
  nunca misturado ao New MRR.
- **Governo** (§8): 2 oportunidades qualificadas/semana; Qualified, License, Annual Subscription Pipeline e Expected
  Close; a política rejeita compensar a quota privada com pipeline governamental.
- **Comissão privada** (§9): 20% recorrente sobre mensalidade efetivamente paga (base: margem do recebimento, D-074 —
  OI-028), por representante, cliente, produto, competência, status e situação da carteira; inadimplência HOLD e
  cancelamento STOP_FUTURE configuráveis; Government com política própria.
- **Summer Sales Challenge** (§10): Dez/26 + Jan/27, R$ 27.500 individual / R$ 192.500 equipe, faixas +20/+35/+50%,
  bônus só sobre a comissão das novas vendas da janela, elegibilidade configurável.
- **Painel individual** (§11) e **gestor** (§12): quota, realizado, attainment, gap, cobertura, forecast, ticket, mix,
  funil, velocidade, comissão, campanha e Government Pipeline; comparação dos 7 por attainment e indicadores
  operacionais, com exceções destacadas.
- **MAP Intelligence** (§13): 8 regras determinísticas com ação recomendada e evidências; sem IA (o sinal é a regra).
- **Daily Comercial** (§14): só exceções, gap, até 5 negócios que destravam a quota por representante e próximas ações.

## Testes (§16)

`tests/integration/test_map_performance.py` (25): quotas do PO e da equipe, quota específica versionada e auditada,
attainment/gap/cobertura 3x/forecast, forecast pela velocidade, conta trabalhada (ICP + persona + ação humana; automação
não conta), funil completo e metas, aprendizado com amostra mínima, mix quality sem bloqueio, comissão recorrente por
competência e status, inadimplência retida (painel e repasse) e política sem retenção, cancelamento, faixas 80/100/120/150%,
bônus só sobre novas vendas (carteira histórica fora), inelegibilidade por mês sem venda, Government separado e política
que recusa compensar a quota, isolamento por tenant, permissões (rep só o próprio; gestor equipe/Daily/configuração),
configuração pela API, pendência sem vínculo, eventos e custo de consultas constante (1 vs 7 representantes).
`tests/integration/test_map_performance_pg.py`: as agregações em Postgres 16 migrado. E2E: `e2e/map-performance.spec.ts`.

## Desempenho (§17) — `docs/b2bon/perf/map_performance.json`

| Rota | p50 | p95 | Consultas |
|---|---|---|---|
| map performance · painel (1 representante, 40 negócios) | 31,8 ms | 45,8 ms | 53 |
| map performance · equipe (7 representantes) | 33,6 ms | 43,9 ms | 44 |
| map performance · daily | 33,5 ms | 37,3 ms | 45 |

Antes/depois: as rotas existentes do MAP/CRM mantêm o mesmo número de consultas (painel 5, funil 5, economia 10, negócios 6).
O custo das rotas novas não cresce com o número de representantes nem de negócios (consultas agrupadas; teste
`test_numero_de_consultas_nao_cresce_com_a_equipe`). Índices compostos em atividade (tenant, usuário, data), reunião
(tenant, vendedor, data) e negócio (tenant, vendedor). Telas: abas carregadas sob demanda (chunk próprio de 19 kB + 6 kB
da configuração).

## Pendências

- **OI-028**: base da comissão privada (texto do prompt × D-074) — mantida D-074 até decisão do PO.
- **OI-029**: vincular cada representante ao usuário do CRM, mapear oferta → família no CRM e confirmar o critério de
  "contato efetivo".
