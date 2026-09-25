# Analytics & Revenue Intelligence — catálogo de métricas (Fase 16)

Contrato de toda métrica: `valor`, `unidade`, `metodologia`, `amostra`
(+ detalhes). Calculada do que está registrado, nunca estimada; sem
denominador, taxa `None` (não zero). Atribuição = toque registrado, não
causalidade (D-046).

## Lado vendedor — `GET /inteligencia/receita/metricas?inicio&fim` (módulo CRM)

Código: `app/contexts/analytics/receita.py`. Janela padrão: 90 dias. Pipeline = negócios abertos agora; receita e conversões = período.

| Métrica | Definição |
|---|---|
| `network_sourced_pipeline` | Negócios abertos originados pela rede: sinal convertido (`negocio_id_gerado`), conta nascida de sinal (`origem=rede_social_signal`) ou negócio com essa origem |
| `network_influenced_pipeline` | Negócios abertos não originados pela rede, com sala de compra ou cuja conta recebeu sinal |
| `ai_assisted_pipeline` | Negócios abertos com IA bem-sucedida no negócio ou na conta (ledger), necessidade extraída por IA não descartada, ou `origem=ia` |
| `ai_assisted_revenue` | Negócios ganhos no período com o mesmo critério |
| `signal_conversion` | Sinais gerados no período; convertidos / gerados; também convertidos em ganho e por tipo |
| `intent_conversion` | Idem, só `intent_compativel` (intenção de outra empresa compatível com a minha oferta) |
| `match_conversion` | Idem, `fit_icp` + `match_intent` |
| `offer_conversion` | Negócios fechados no período por oferta; ganhos / fechados e valor ganho |
| `churn_prevention_value` | Receita ganha em 12 meses de clientes que tiveram ação no período (roteiro de resgate por IA ou alerta de detrator) e continuam clientes; também taxa de retenção |
| `contract_renewal_risk` | Só com Bid Intelligence: valor dos contratos públicos vigentes que vencem em até 120 dias; não renováveis à parte; sem data de fim listados |

## Lado comprador — `GET /procurement/metricas` (módulo Procurement)

Código: `app/contexts/procurement/metricas.py` (barreira Buy/Sell: nunca misturado com receita).

| Métrica | Definição |
|---|---|
| `procurement_cycle_time` | Mediana de dias entre abertura do processo e o primeiro contrato registrado; em andamento só com idade |
| `pca_execution` | Valor contratado / planejado do PCA do ano corrente; também por itens e pago sobre contratado |
| `supplier_performance` | Nota média das fiscalizações; por fornecedor ocorrências, entregas e acréscimo médio por aditivo |
| `contract_renewal_risk` | Contratos vigentes com necessidade continuada que vencem em até 120 dias sem processo da mesma categoria em andamento (ALTO ≤ 60 dias) |

## Superfícies

- CRM → "Revenue Intelligence" (`/crm/receita`): cartões com valor, amostra e metodologia; conversão por oferta.
- Compras públicas: faixa de indicadores com a metodologia no tooltip.
