# PHASE 15 — PRICING, AI CREDITS & COMMERCIAL MONETIZATION · Completion Report

- **Data**: 2026-09-25 · **Branch**: `staging`
- **Autorização**: PO, com o prompt da Fase 15 e "pode prosseguir e concluir a fase". As franquias do Public Procurement e da Full Suite ficam para decisão futura (OI-017).
- Substitui `PHASE_15_BLOCKED.md`, que fica como histórico.

## Objective

Implantar o B2B ON AI Credits como modelo comercial de IA: franquia mensal por módulo, pacotes de top-up e carteira compartilhada com validade e FEFO. O crédito vem do peso do workload, desacoplado de modelo, provedor e custo de token. O custo real fica medido para proteger a margem (alvo 80%).

## Architecture Implemented

```
REAL COMPUTE COST → AI GATEWAY → MODEL ROUTING (+cost guard) → WORKLOAD (catálogo versionado)
→ INTERNAL COST (execucao_ia) → CREDIT WEIGHT → AI CREDIT (lote FEFO) → REVENUE (receita/crédito do lote) → GROSS MARGIN
```

O fluxo no gateway é entitlement/limites → execução (estimativa, confirmação, budget guard, reserva) → roteador e cost guard → cache → provedor → evento de uso → custo → liquidação no ledger.

Módulos novos em `app/contexts/finops/`:
- `comercial`: regras e franquias;
- `catalogos`: pacotes e workloads;
- `carteira`: lotes, FEFO, ledger e reconciliação;
- `execucoes`: reserva, liquidação, liberação e estorno;
- `limites`: budget guard, avisos e anomalia;
- `compras`: top-up e recarga automática;
- `economia`: margens, KPIs, matriz, recomendações e calibração;
- `rotinas`: cron horário.

Detalhe em `09_AI_FINOPS.md`.

## Database Changes

A migração `e7b3c1a9f5d2` (down_revision `c4f1a9e7d2b3`) cria as tabelas:
- `pacote_credito`
- `catalogo_credito`
- `workload_ia`
- `lote_credito`
- `execucao_ia`
- `compra_credito`
- `configuracao_credito_tenant`
- `alerta_credito`
- `cache_resposta_ia`

`movimento_credito` ganha as colunas lote, execução, `idempotency_key` (única por tenant), receita, versão do catálogo e `faturavel`. `registro_uso_ia` ganha execução, workload, versão, cache, custo de dados, embeddings, ferramentas e decisão de roteamento.

Na migração de dados, cada saldo da Fase 5 vira um lote ADJUSTMENT `MIGRACAO_FASE_15` mais um `CREDIT_ADJUSTED`, e o histórico antigo fica intacto.

A migração foi validada em SQLite e em Postgres 16 (upgrade, downgrade e upgrade), com teste de reconciliação pós-migração.

## Credit Wallet

- Uma carteira por tenant, com lotes SUBSCRIPTION, TOPUP, PROMOTIONAL, ADJUSTMENT e ENTERPRISE_OVERAGE.
- Consumo FEFO; no empate, promocional < ajuste < assinatura < top-up.
- A franquia mensal é concedida uma vez por período, vence no dia 1 do mês seguinte e não tem rollover.
- O top-up vale 12 meses.
- Reserva antes do provedor com `SELECT … FOR UPDATE`, no máximo 20 reservas abertas por tenant, e liberação de reservas órfãs pelo cron.
- A primeira criação simultânea de carteira ou configuração é segura (savepoint e releitura).

## Credit Ledger

- `movimento_credito` é imutável e registra os eventos:
  - CREDIT_GRANTED
  - CREDIT_PURCHASED
  - CREDIT_PROMOTIONAL
  - CREDIT_ADJUSTED
  - CREDIT_RESERVED
  - CREDIT_RELEASED
  - CREDIT_CONSUMED
  - CREDIT_REFUNDED
  - CREDIT_EXPIRED
  - CREDIT_OVERAGE
- É idempotente por `(tenant, idempotency_key)`.
- `saldo_apos` é igual ao disponível.
- `carteira.reconciliar` compara extrato, lotes e reservas, e está exposto em `/finops/reconciliacao`.

## Usage Metering

Cada chamada gera um evento em `registro_uso_ia` com:
- tenant, usuário, módulo, feature, agente e gatilho (usuário, automático ou API);
- workload e versão do catálogo;
- tokens das quatro categorias;
- custo, cache e economia de cache;
- decisão de roteamento;
- id da execução.

Uma operação com N chamadas gera uma execução e uma cobrança. O GATE parametrizado sobre todas as features garante evento, execução liquidada, CREDIT_CONSUMED e reconciliação consistente.

## Cost Attribution

- O custo em USD vem de `preco_modelo_ia`. O custo em BRL usa `FINOPS_CAMBIO_USD_BRL`; sem câmbio, lucro e margem ficam `null` com motivo.
- A execução agrega custo de LLM, custo de dados (coluna separada), receita, lucro e margem.
- As margens podem ser vistas por tenant, módulo, workload, agente, plano, provider, modelo e pacote.
- O cliente nunca vê USD.

## Pricing Catalog

`pacote_credito` guarda versão, moeda (BRL; estrutura pronta para outras moedas), créditos, preço, status, validade e `valido_de`/`valido_ate`.

| Pacote | Créditos | Preço |
|---|---|---|
| AI Start | 5K | R$ 99 |
| AI 15K | 15K | R$ 249 |
| AI 30K | 30K | R$ 449 |
| AI 75K | 75K | R$ 899 |
| AI 150K | 150K | R$ 1.499 |
| AI 350K | 350K | R$ 2.999 |
| AI 1M | 1M | R$ 6.990 |
| Enterprise | — | CONTACT_SALES |

Esses são exatamente os valores do PO. Mudar preço cria uma nova versão auditada. A única fonte de preço é o catálogo: a UI e o catálogo comercial leem a API, e um teste impede preço de pacote fixo no frontend.

## Credit Catalog

- `CREDIT_CATALOG_V1` tem os pesos do PO para C0–C3 e os workloads de procurement.
- Os workloads variáveis têm mínimo e máximo; o multi-documento complexo exige aprovação.
- O fluxo é rascunho → ativação, ambos auditados com valor anterior, valor novo e motivo.
- Cada execução, movimento e evento de uso guarda a versão do catálogo usada.

## Billing Integration

- `POST /ai-credits/compras` congela a versão e o preço e gera o checkout Mercado Pago com referência `creditos:{id}`.
- O webhook assinado despacha para a licença ou para os créditos, credita só com status aprovado e valor igual ao do pedido, e é idempotente.
- A recarga automática exige consentimento explícito e cria um pedido pendente (TD-076).
- O excedente Enterprise é configurado pelo super_admin com limite rígido e fica marcado como faturável (TD-077).

## Sales Page Changes

A página `/planos` ganhou a seção "B2B ON AI Credits": franquia por módulo, com Procurement "Em definição" e Enterprise como pool por contrato, e os pacotes com preço efetivo por 1.000 créditos, todos vindos da API.

A página pública nova "Como funcionam os AI Credits" (`/como-funcionam-ai-credits`) traz perguntas e respostas mais a tabela de consumo por operação, também vinda da API.

## Plans Page Changes

- No catálogo comercial, o produto `ai_credits` fica DISPONIVEL, com pacotes e franquias do FinOps.
- Cada plano do comparativo traz `ai_credits_mensais`.
- A área "Assinatura" mostra créditos consumidos, disponíveis e incluídos, com link para a carteira.
- Os preços dos planos não mudaram (teste de preços preservados).

## Public Procurement Status

- O preço-base continua PENDING_DEFINITION, EM_DEFINICAO, sem botão de compra e com `precificacao_pendente` vazio.
- A franquia continua PENDING_FINAL_DEFINITION (faixa 50–100K), sem nada concedido (OI-017).
- Workloads: atualização determinística = 0 crédito. Documento de 200 páginas: estimativa 225, confirmação, reserva e liquidação de 225 (teste crítico).

## Tests

| Arquivo | Cobertura |
|---|---|
| `test_ai_credits_carteira.py` (12) | semente, estimativa variável, FEFO/idempotência, reserva/liquidação/receita, **cobrança dupla**, **100 vs 75+75**, **isolamento**, liberação/estorno, expiração, confirmação, franquia, MEASURE |
| `test_ai_credits_api.py` (18) | pacotes públicos, carteira, compra via webhook uma vez, valor divergente, Enterprise, recarga com consentimento, budget por módulo, estimativa sem custo, isolamento via API, papéis, catálogo versionado, versão de pacote, economia/reconciliação, estorno, excedente, cron idempotente |
| `test_ai_credits_gateway.py` (8) | feature → workload, cache hit cobrado e medido, cache por tenant, falha do provedor sem cobrança, API cobrada, limite de API, cost guard até a classe mínima |
| `test_ai_credits_procurement.py` (3) | **Public Procurement crítico** (0 crédito determinístico; 225 com confirmação), preço pendente |
| `test_ai_credits_concorrencia_pg.py` (2) | **concorrência real em Postgres** (2×75 com saldo 100 → uma passa; primeiro uso simultâneo) |
| `test_finops.py` (reescrito), `test_finops_api.py`, `test_catalogo_comercial.py`, `test_precos_preservados.py`, `test_alembic_upgrade.py` | GATE por feature, ajuste auditado, catálogo, preços dos pacotes, migração com reconciliação |
| E2E `planos.spec.ts` | seção AI Credits e página explicativa com dados da API |

## Test Results

| Evidência | Resultado |
|---|---|
| Suíte completa (SQLite) | ✅ **1.996 passed** (+2 skipped: Postgres) |
| Concorrência em Postgres 16 | ✅ 2/2 (3 rodadas em banco novo) |
| Migração em SQLite e Postgres 16 | ✅ `PG_MIGRACOES_OK e7b3c1a9f5d2` |
| Frontend: typecheck + build; oxlint | ✅ 25 warnings (baseline) |
| Ruff | 40, idêntico ao HEAD da Fase 17 (nenhum novo) |
| E2E | ✅ 6/6 |

Validações do §72:

| Validação | Evidência |
|---|---|
| Reconciliação | `reconciliar` consistente em todos os testes de carteira, API, gateway, procurement e migração |
| Isolamento | Serviço, API, cache e Postgres |
| Ledger | Idempotência, FEFO, expiração e estorno |
| Metering | GATE por feature, cache e API |
| Margens | KPIs, faixas, alertas por janela e amostra, margem `null` sem câmbio |

## Security Tests

- Isolamento entre tenants (carteira, lote, extrato, cache).
- Papéis: vendedor não compra nem vê o extrato; admin do tenant não acessa o FinOps nem ajusta créditos.
- Webhook com assinatura e valor conferido; webhook repetido não credita de novo.
- Corpo com campo extra é rejeitado (`extra="forbid"`).
- Abuso:
  - limite de reservas abertas;
  - teto automático por hora;
  - limite de API;
  - detecção de pico de consumo;
  - confirmação obrigatória acima do limiar.
- Auditoria com ator, data, valor anterior, valor novo e motivo em ajustes, catálogo, pacotes, excedente, orçamento, recarga e estorno.

## Margin Model

Receita = créditos consumidos × receita por crédito do lote:
- top-up: preço ÷ créditos;
- franquia: referência R$ 6,99 por 1.000 (D-051);
- promocional e ajuste: 0.

Faixas (configuráveis):

| Faixa | Margem |
|---|---|
| Alvo | 80% |
| MARGIN_WARNING | abaixo de 75% |
| MARGIN_CRITICAL | abaixo de 65% |

Os alertas usam janelas de 7 e 30 dias e só disparam com pelo menos 20 execuções.

Os KPIs de 90 dias (§39) ficam disponíveis em `/finops/economia?dias=90` e no relatório `/finops/relatorio-calibracao?dias=90`:
- AI Revenue, Variable Cost, Gross Profit, Gross Margin;
- Credits Sold, Granted, Consumed, Expired;
- Unused Credit Liability;
- custo e receita por 1.000 créditos;
- Cache Savings;
- distribuição por provider e por modelo.

Não há dados de produção ainda.

## Known Issues

| ID | Pendência |
|---|---|
| OI-017 | Franquias Procurement e Full Suite, e preço-base do Procurement: decisão futura do PO |
| OI-018 | Câmbio para a margem em BRL; sem ele, a margem aparece como indisponível |

Continuam valendo OI-001, OI-014, OI-015 e OI-016. OI-013 foi resolvido pelo modelo da Fase 15.

## Technical Debt

| ID | Dívida |
|---|---|
| TD-076 | Recarga sem cobrança fora de sessão |
| TD-077 | Excedente sem fatura automática |
| TD-078 | Teste Postgres fora do CI |
| TD-079 | Receita de assinatura por referência |
| TD-080 | Custo de dados, embeddings e ferramentas sem provedor que preencha |

TD-012 passou a IN_PROGRESS.

## Deferred Items

- Premium Data: colunas prontas, nada ativado.
- Cobrança recorrente com cartão salvo para a recarga.
- Fatura pós-paga do excedente.
- Multimoeda (a estrutura existe; só BRL está ativo).
- Add-ons Opportunity Intelligence e Business Network: franquia definida, mas o produto não é vendido separadamente.

## Recommended Calibration Actions

1. Configurar `FINOPS_CAMBIO_USD_BRL` em produção, para a margem sair de "indisponível".
2. Agendar `/cron/creditos-ia` de hora em hora.
3. Após 7, 30 e 90 dias, rodar `/finops/relatorio-calibracao` e revisar a matriz e as recomendações de peso. Ajustar pesos só por rascunho e ativação, nunca preço sem o PO.
4. Rodar inicialmente em ENFORCE com observação dos 402. Se quiser rollout gradual, usar MEASURE por período e ler o excedente não faturável.
5. O PO define as franquias de Procurement e Full Suite e o preço-base do Procurement (OI-017).

## Next Phase

Não há. As Fases 0–17 do Master Prompt v4 estão concluídas. Qualquer trabalho novo depende de instrução do Product Owner.
