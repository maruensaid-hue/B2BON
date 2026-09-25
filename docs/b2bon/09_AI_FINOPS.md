# 09 — AI FINOPS & CREDITS (Fase 5)

Contexto: `app/contexts/finops/` (contrato: `contract.py`). Integrado ao
AI Gateway (`app/contexts/intelligence/gateway.py`).

```
MODULE → AI GATEWAY ──► orçamentos/quota/saldo? (bloqueia antes do provedor)
              │
              ▼
        MODEL ROUTER → PROVIDER
              │
              ▼  (sessão própria, 1 transação)
        USAGE LEDGER (registro_uso_ia) + custo USD (preco_modelo_ia) + créditos (politica_creditos_ia)
              │
              ▼
        CREDIT ENGINE → carteira_creditos / movimento_credito
              │
              ▼
        FINOPS DASHBOARD (/api/v1/finops/*, Admin → IA & Créditos)
```

## 1. Usage Event (§54) — o que cada linha do ledger tem

| Campo §54 | Coluna |
|---|---|
| tenant_id, user_id | `tenant_id`, `usuario_id` |
| module, feature, agent, workflow | `modulo`, `feature`, `agente`, `workflow` |
| provider, model | `provider`, `model` (+ `classe_modelo`, `preco_id`) |
| input/cached/output tokens | `tokens_entrada`, `tokens_cache_leitura`, `tokens_cache_escrita`, `tokens_saida` |
| embedding_tokens, tool_calls | não há embeddings nem tool calling ainda (D-017, Fase 12) |
| external_api_cost, compute_cost | não medidos (Brave/Lusha/BrasilAPI têm franquia própria; TD-048) |
| total_cost | `custo_usd` (None = modelo sem preço, contado em `chamadas_sem_preco`) |
| credits_consumed | `creditos_consumidos` (None = política pendente) |
| timestamp | `criado_em` (+ `status`, `erro`, `gatilho`, `correlation_id`) |

## 2. Custo do provedor

- `preco_modelo_ia`, versionado por `vigente_desde`, com `fonte`.
  Semente: tabela pública da Anthropic (USD/MTok) para Haiku 4.5,
  Sonnet 5, Sonnet 4.6, Opus 5, Opus 5.5 e Opus 4.8. Cache: escrita
  1,25× entrada, leitura 0,1× entrada.
- `custo = (in×P_in + out×P_out + cw×P_cw + cr×P_cr) / 1e6`. Os tokens de
  cache não se sobrepõem a `input_tokens` na API da Anthropic.
- Match de modelo por id exato ou maior prefixo. Modelo desconhecido
  fica sem custo, e isso aparece no dashboard (nunca vira zero).

## 3. Créditos (§55, §56)

- Política `politica_creditos_ia`: **semeada como `PENDING_DEFINITION`**.
  A taxa `creditos_por_usd` é decisão comercial do PO (OI-013). Enquanto
  isso, o custo é medido e nenhum crédito é debitado.
- Com a política ATIVA, cada chamada debita a carteira do tenant na mesma
  transação do ledger (`CONSUMO`). Saldo insuficiente com excedente
  permitido vira `EXCEDENTE` (base do overage). `exige_saldo` sem
  excedente bloqueia antes do provedor.
- A carteira é compartilhada pelo tenant e consumida por todos os módulos.
  O extrato (`movimento_credito`) é imutável, com `saldo_apos`.
- A alocação é feita pelo super_admin (`POST /finops/tenants/{id}/creditos`).
  A alocação automática por plano fica para a Fase 14 (catálogo).
- **Nunca** "1 crédito = X tokens": créditos derivam de custo, e a UI do
  tenant não mostra USD.

## 4. Budgets e quotas

`orcamento_ia`: escopo tenant/módulo/feature, limite em USD (só
super_admin) ou em chamadas (admin do tenant), ação ALERTAR ou BLOQUEAR,
janela mensal. `BLOQUEAR` estourado impede a chamada e fica registrado
no ledger como `bloqueado`.

## 5. Dashboard (§57)

Super_admin (`GET /finops/resumo`): custo, chamadas por status, tokens,
cache ratio, créditos; agrupamentos por tenant, módulo, agente, feature,
provider e modelo; custo por usuário ativo, por tenant, por oportunidade
e por reunião. Métricas **sem base honesta voltam `null` com motivo**:
AI Revenue / Gross Profit / Margin (sem preço de crédito), custo por Bid
ou por Processo de compra (módulos das Fases 9–10), custo sobre receita
(exige `FINOPS_CAMBIO_USD_BRL`).

Tenant (`GET /finops/meu-uso`): chamadas e créditos por módulo e feature,
saldo e extrato. Sem custo em USD.

## 6. GATE — nenhuma chamada AI não contabilizada

- Estrutural: `test_gateway_ia_unico_caminho.py` (Fase 4).
- Contábil: `test_finops.py::test_gate_nenhuma_chamada_de_ia_sem_contabilizacao`,
  parametrizado pelas 14 features registradas. Cada chamada gera 1 linha
  de ledger com custo e créditos e 1 movimento na carteira.
