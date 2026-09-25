# 09 — AI FINOPS & B2B ON AI CREDITS (Fases 5 e 15)

Contexto: `app/contexts/finops/` (contrato: `contract.py`). Integrado ao
AI Gateway (`app/contexts/intelligence/gateway.py`). A Fase 15 trocou o
modelo "créditos = custo × taxa" (política `PENDING_DEFINITION`) pelo
modelo definitivo: **créditos vêm do peso do workload** num catálogo
versionado, e o custo real é medido à parte para calcular a margem.

```
MÓDULO → AI GATEWAY
   │  1. limite automático/hora + orçamentos legados (chamadas/USD)
   │  2. EXECUÇÃO: workload da feature → catálogo ativo → estimativa
   │     → confirmação (≥ limiar) → orçamento do tenant (budget guard)
   │     → saldo (FEFO) ou excedente aprovado → RESERVA (CREDIT_RESERVED)
   │  3. MODEL ROUTER + COST GUARD (rebaixa só até a classe mínima)
   │  4. CACHE de resposta (por tenant; hit = crédito cobrado, custo 0)
   │  5. PROVIDER ──falha──► reserva liberada (CREDIT_RELEASED), nada cobrado
   │  6. USAGE EVENT (registro_uso_ia) + custo USD (preco_modelo_ia)
   ▼  7. LIQUIDAÇÃO: CREDIT_RELEASED + CREDIT_CONSUMED (por lote, FEFO)
EXECUÇÃO (execucao_ia): créditos, custo, receita, lucro, margem
   │
   ▼
ECONOMIA (margens, alertas, matriz, recomendações, relatório de calibração)
```

## 1. Unidades

| Conceito | Tabela | Observação |
|---|---|---|
| Pacote de top-up (preço) | `pacote_credito` | versionado; mudança de preço = nova versão auditada |
| Catálogo de workloads (peso) | `catalogo_credito` + `workload_ia` | versões RASCUNHO → ATIVO → ARQUIVADO |
| Lote de créditos | `lote_credito` | SUBSCRIPTION, TOPUP, PROMOTIONAL, ADJUSTMENT, ENTERPRISE_OVERAGE |
| Extrato (ledger) | `movimento_credito` | imutável, eventos `CREDIT_*`, idempotente por `(tenant, idempotency_key)` |
| Execução | `execucao_ia` | uma operação de negócio = uma cobrança, mesmo com N chamadas |
| Evento de uso | `registro_uso_ia` | uma linha por chamada ao provedor (ou cache) |
| Compra | `compra_credito` | pedido → checkout → webhook assinado |
| Configuração do tenant | `configuracao_credito_tenant` | pool Enterprise, recarga, excedente, limites |
| Alertas de uso | `alerta_credito` | 80/95/100% por período, um por nível |
| Cache | `cache_resposta_ia` | só features cacheáveis; chave inclui o tenant |

## 2. Carteira e lotes

- Uma carteira por tenant, compartilhada por usuários e módulos.
- **FEFO**: consome primeiro o lote que vence primeiro; empate por tipo:
  PROMOTIONAL < ADJUSTMENT < SUBSCRIPTION < TOPUP (o comprado sai por último).
- Validade:
  - franquia do plano (SUBSCRIPTION): mensal, vence no dia 1 do mês
    seguinte, **sem rollover**, concedida uma vez por período
    (`franquia:{AAAA-MM}`);
  - top-up: 12 meses (`ai_creditos_validade_topup_meses`);
  - promocional: validade da campanha (informada no ajuste).
- Invariante (verificada por `carteira.reconciliar`):
  soma dos movimentos da Fase 15 (sem CREDIT_OVERAGE) = lotes vigentes + vencidos
  ainda não processados − reservas abertas.
- Receita por crédito: top-up = preço ÷ créditos do pacote pago;
  franquia = referência conservadora `ai_creditos_receita_ref_assinatura_1k_brl`
  (R$ 6,99/1.000, o menor preço efetivo da tabela); promocional/ajuste = 0.

## 3. Catálogo de workloads (`CREDIT_CATALOG_V1`)

Classes: C0 determinístico (0), C1 econômico, C2 padrão, C3 avançado. Os
pesos iniciais são os do PO (§14). Workloads variáveis (documentos) usam
base + por página + OCR, com mínimo e máximo; `complex_multi_document_analysis`
(150–300) exige aprovação. Procurement:
`procurement_deterministic` = 0 e `procurement_document_intelligence` = 25 +
1/página (+0,5 OCR), mín. 25, máx. 300. Um documento de 200 páginas estima 225.

Cada feature do gateway mapeia para um workload (`registro.WORKLOAD_POR_FEATURE`;
teste garante que todos existem no catálogo ativo). Mudança de peso: rascunho
(`POST /finops/catalogo/rascunhos`) + ativação (`/ativar`), ambos auditados
com valor anterior, novo e motivo. Execuções guardam a versão usada.

## 4. Execução, reserva e idempotência

- `abrir`: idempotente por `(tenant, idempotency_key)`; trava a carteira
  (`SELECT … FOR UPDATE`), expira o vencido, concede a franquia do mês,
  limita reservas abertas (20), pede confirmação ≥ `ai_creditos_limiar_confirmacao`
  (100) ou quando o workload exige, aplica o budget guard e reserva.
- `liquidar`: idempotente; libera a reserva e consome FEFO. O que faltar
  vira excedente Enterprise faturável (se aprovado e dentro do limite
  rígido) ou excedente não faturável (modo MEASURE).
- `liberar`: falha sem resultado → nada cobrado. `estornar`: devolve o
  consumido (CREDIT_REFUNDED), auditado. `liberar_reservas_orfas`: cron.
- Operação longa (edital, documento de compras): `gateway.execucao(...)`
  abre uma execução explícita; as chamadas do bloco não cobram de novo.
- Modos (`AI_CREDITOS_MODO`): **ENFORCE** (produção) bloqueia sem saldo;
  **MEASURE** mede tudo e registra excedente não faturável (usado pela suíte
  de testes e para rollout gradual).

## 5. Custo, cache, roteamento

- Custo: `preco_modelo_ia` (USD/MTok versionado) × tokens das quatro
  categorias. Modelo sem preço → custo desconhecido, nunca zero.
- Custo em BRL = USD × `FINOPS_CAMBIO_USD_BRL`. Sem câmbio, lucro e margem
  são `null` com motivo (UNKNOWN em vez de invenção).
- Cache de resposta (FAQ e orquestrador): hit registra `cache_hit`,
  custo 0 e `economia_cache_usd`; o crédito é cobrado (política comercial).
- Cost guard: se o custo estimado passar do teto do workload
  (`custo_max_usd` por classe), tenta modelo mais barato só até a
  `classe_minima`; sem alternativa, segue e registra `decisao_roteamento`.

## 6. Budget guard e limites

`configuracao_credito_tenant`: orçamento mensal, limite diário, por usuário,
por API, por agente e percentual por módulo (ex.: PREDATOR ≤ 40%),
percentual de aviso e parada rígida. Estouro com parada rígida →
`OrcamentoIaExcedido` antes do provedor. Avisos de uso em 80/95/100%
(`alerta_credito`) e estimativa de dias restantes (≥ 3 dias de uso em 7).

## 7. Margem e economia (`economia.py`)

- Faixas configuráveis: alvo 80%, WARNING < 75%, CRITICAL < 65%.
- Alertas por janela (7 e 30 dias) e amostra mínima (20 execuções).
- Margens por tenant, módulo, workload, agente, plano, provider, modelo, pacote.
- KPIs: receita, custo, lucro, margem, créditos vendidos/concedidos/
  consumidos/expirados, passivo de créditos não usados, excedente,
  receita e custo por 1.000 créditos, economia e taxa de cache,
  distribuição por provider e modelo.
- Matriz de rentabilidade (workload economicamente inadequado),
  recomendações de peso (faixa sugerida, `requer_aprovacao`), economia
  unitária (custo por usuário, tenant, oportunidade, reunião, lead
  qualificado, cadência, licitação, churn…), valor de negócio (correlação,
  não causalidade) e relatório de calibração 7/30/90 dias.
- Nada disso altera preço, peso ou franquia sozinho.
- Custo de dados/enriquecimento: coluna `custo_dados_usd` separada no
  evento e na execução. Premium Data preparado, não ativado.

## 8. Dashboard legado (Fase 5)

`GET /finops/resumo` continua (custo por tenant, módulo, feature, modelo);
receita/lucro/margem agora vêm de `economia.kpis`. A política
`politica_creditos_ia` fica só leitura (legado).

## 9. GATE — nenhuma chamada de IA sem contabilização

- Estrutural: `test_gateway_ia_unico_caminho.py`.
- Contábil: `test_finops.py::test_gate_nenhuma_chamada_de_ia_sem_contabilizacao`,
  parametrizado por todas as features: evento de uso com workload e versão
  do catálogo, execução LIQUIDADA, CREDIT_CONSUMED no extrato e
  reconciliação consistente.
