# 02 — TARGET ARCHITECTURE

> Primeira versão escrita na Fase 1. Revisada a cada fase.

## 1. Estilo: monólito modular com bounded contexts (D-002)

Um processo FastAPI, um banco, um SPA. A separação é por **contexto de
código**, não por deploy:

```
app/
  contexts/
    shared/     Shared Kernel: entitlements, Organization/Person (Conta/Decisor)
    crm/        pipeline, negócios, atividades     → contract.py
    map/        saúde, churn, economia de cliente  → contract.py, data_source.py (porta)
    predator/   prospecção, engajamento            → contract.py
    (futuros: network, opportunity, bids, procurement, intelligence, integrations, finops)
  services/     serviços legados; migram para contexts/ por Strangler
  api/v1/       routers (finos), gates de entitlement por router ou rota
```

## 2. Regras de fronteira (testadas em `tests/unit/test_fronteiras_contexto.py`)

1. Fora de um contexto, só se importa `app.contexts.<ctx>.contract`.
   `shared` é livre para todos.
2. O MAP nunca lê o ORM de pipeline do CRM (`Negocio`, `EstagioFunil`,
   `CustoAquisicao`) nem `crm_service`. Ele lê pela porta
   `MapDataSource`, que o CRM interno implementa via `crm.contract`. Um
   CRM externo (Fase 13) vira outra implementação da mesma porta.
3. Contratos expõem funções e DTOs. O ORM só atravessa fronteira em
   operações de escrita do Shared Kernel (`obter_conta`).

## 3. Fluxo de dependência atual (pós-Fase 1)

```
 api/v1/crm ──► services/crm_service ──► contexts/map/contract (economia, vendedores)
 api/v1/saude_conta ──► contexts/map/contract ──► map/{saude,economics,risk}
                                           └──► map/data_source ──► crm/contract ──► ORM CRM
 api/v1/prospeccao_contas ──► contexts/predator/contract ──► predator/prospeccao ──► shared/organizations
 services/{saude_conta,motor,metricas}_service ──► contexts/map/contract
 api/deps (exigir_modulo / exigir_algum_modulo) ──► shared/entitlements ──► PlanLimitsProvider
```

## 4. Evolução prevista

| Fase | Mudança arquitetural |
|---|---|
| 2 | Modelo canônico (`contexts/shared/canonical/`) + mapeadores CRM interno → canônico + eventos de domínio |
| 3 | API `/api/v1/{map,predator}/*` sobre os contratos; chaves de API por tenant; idempotência; registro de integrações |
| 4 | AI Gateway sobre `LLMProvider` (D-005); Context Engine; registries |
| 5 | Usage Ledger transacional + Credit Engine |
| 6+ | Novos contextos (opportunity, network, bids, procurement) nascem já em `app/contexts/` |

## 5. O que continua fora dos contextos (dívida conhecida)

`conta_service` (CRM + Shared Kernel de escrita), `crm_service`,
`sinal_oportunidade_service` (lê `Negocio` direto) e a maior parte dos
serviços do PREDATOR (cadência, aprovação, envio) ainda vivem em
`app/services/`. Ver `TECHNICAL_DEBT.md` TD-001/TD-005.
