# PRICING, PLANS & ENTITLEMENTS — CURRENT STATE (Fase 0, 2026-09-25)

> Fase 0: **nenhum preço, plano ou entitlement foi alterado.** Este
> documento só descreve o que existe.

## 1. Onde os preços estão

Há **três lugares que definem preço**, sincronizados à mão:

| Fonte | Conteúdo | Consumido por |
|---|---|---|
| Tabela `plano` (Postgres). Os planos de suíte (POC/Teste/Starter/…) são criados por `scripts/bootstrap_tenant.py` e depois ajustados por migrações; os 9 avulsos, pela migração `807d7076f1df` | `preco_mensal`, `max_usuarios`, limites, flags, `modulos_contratados`, `categoria`, `visivel_self_service` | `GET /planos` → `pages/CriarConta.tsx` (checkout) → `pagamento_licenca_service.iniciar` → Mercado Pago (`valor=plano.preco_mensal`). Também admin (`AdminPlanos.tsx`) e `motor_service` |
| **Hardcoded** em `frontend/src/pages/Planos.tsx` (página pública "Planos e Valores") | constantes `MODULOS`, `CONTRATACAO_POR_MODULO`, `PLANOS`, com preços como strings ("R$ 924,50") e `checkoutPlanoNome` para casar pelo **nome** | visitante anônimo |
| `scripts/bootstrap_tenant.py` (constantes com `preco_mensal` dos planos de suíte) | seed inicial de um banco novo | quem sobe um ambiente do zero |

O vínculo entre as duas fontes é o **nome do plano** (string). Se
alguém alterar um preço via Admin → Planos, a página pública continua
mostrando o preço antigo, e o cliente paga o do banco. A migração
`b5a3d9c48786` existiu justamente para corrigir essa divergência uma vez.

Os preços "On Demand" (por usuário, acima de 20 usuários) e os preços
por usuário por módulo (R$ 29,90 / 95,10 / 59,90) **existem só no
frontend**. Não há `Plano` correspondente, e o CTA é e-mail para o comercial.

## 2. Catálogo atual (banco, após todas as migrações)

Valores lidos de `scripts/bootstrap_tenant.py` (seed inicial dos planos de suíte) e das migrações `ae2598da5f96`,
`1e5087198fab`, `b5a3d9c48786`, `807d7076f1df` e `bd1685385a43`. `scripts/bootstrap_tenant.py` é a **terceira** cópia de valores comerciais. Em
produção, os valores podem ter sido editados via Admin. **Conferir no
banco antes de qualquer decisão comercial.**

| Plano | Categoria | Módulos | Usuários | Preço/mês (R$) | Self-service |
|---|---|---|---|---|---|
| POC | suite | map, predator, crm | 3 | 0,00 | sim |
| Teste | suite | map, predator, crm | ilimitado | 0,00 | **não** (só convite) |
| Starter | suite | map, predator, crm | 5 | 924,50 | sim |
| Professional | suite | map, predator, crm | 10 | 1.664,10 | sim |
| Enterprise | suite | map, predator, crm | 20 | 2.958,40 | sim |
| MAP Starter / Professional / Enterprise | modulo | map | 5 / 10 / 20 | 149,50 / 269,10 / 478,40 | sim |
| PREDATOR Starter / Professional / Enterprise | modulo | predator | 5 / 10 / 20 | 475,50 / 855,90 / 1.521,60 | sim |
| CRM Starter / Professional / Enterprise | modulo | crm | 5 / 10 / 20 | 299,50 / 539,10 / 958,40 | sim |
| Bid Intelligence (Phase I, D-059, migração `a3c5e7f9b1d2`) | modulo | bids | a definir (OI-023) | 1.490,00 · FIXED | sim |
| Strategic Sourcing (idem) | modulo | sourcing | 5 | 2.990,00 · FIXED | sim |
| Strategic Sourcing Enterprise (idem) | modulo | sourcing + tier `sourcing_enterprise` | por contrato | a partir de 5.990,00 · STARTING_AT | **não** (venda assistida) |

Public Procurement e a B2B ON Suite continuam **sem plano** (PENDING_DEFINITION). AI Credits por plano ficam em
`finops/comercial.FRANQUIAS`: Bid Intelligence 25.000, Strategic Sourcing 50.000, Enterprise 100.000 (substitui).

Os valores da página pública batem com o banco na data desta
auditoria (conferido linha a linha em `Planos.tsx`).

## 3. Como os entitlements funcionam

- **Modelo**: 1 `Licenca` por tenant (unique `tenant_id`) → 1 `Plano`.
  Não há add-ons, múltiplas assinaturas, créditos de IA nem entitlement
  por feature separado do plano.
- **Backend** (autoritativo):
  - `exigir_licenca_ativa`: 40 dos 55 routers, direto ou via os helpers `_exige_map/_predator/_crm`.
  - `exigir_modulo("map"|"predator"|"crm")` → `PlanLimitsProvider.permite_modulo`
    → `Plano.modulos_contratados`. Aplicado **por router inteiro** em `router.py`.
  - Flags de plano: `permite_ab_teste_cadencia`, `permite_auto_aprovacao`,
    `permite_webhook_relatorio`, `permite_api_parceiros`, `permite_subtenants`,
    `permite_registro_oportunidade`. Checados nos serviços e rotas relevantes.
  - Limites de volume: `franquia_contas_mes`, `limite_enriquecimento_{site,contatos}_semanal`,
    `limite_cadencias_mes`, `limite_campanhas_mes`, `max_usuarios`,
    `retencao_dias_{relatorio,auditoria}`. `None` significa sem teto, e `0` bloqueia.
- **Frontend** (espelho, não autoritativo): `Usuario.recursos_plano`
  (`RecursosPlanoSchema`, montado em `app/api/v1/auth.py:92`) esconde
  menus e botões. Não há entitlement só no frontend: toda restrição
  visível tem par no backend. O inverso não vale, porque o frontend
  chama rotas de outro módulo (ver `DOMAIN_DEPENDENCY_MAP.md` C1/C4).
- **Shoal (rede)**: sem gate de licença. É o funil de entrada gratuito.

## 4. Defeitos encontrados (não corrigidos; Fase 0 proíbe mexer em planos)

| ID | Defeito | Evidência | Impacto |
|---|---|---|---|
| OI-001 | Planos "PREDATOR *" foram criados com `franquia_contas_mes=0`, `limite_cadencias_mes=0`, `limite_campanhas_mes=0` e `limite_enriquecimento_*=0`. O comentário na própria migração diz que o zero deveria valer só para MAP/CRM. | `alembic/versions/807d7076f1df_contratacao_avulsa_por_modulo.py:95-110`; `limite_criacao_service.py:32`, `franquia_service` tratam 0 como teto atingido | **Cliente que paga PREDATOR avulso (R$ 475,50–1.521,60) não consegue criar cadência nem campanha, consumir franquia ou enriquecer.** |
| OI-002 | O gate por router não bate com o módulo (C1, C3–C7) | `DOMAIN_DEPENDENCY_MAP.md` §4 | 403 dentro do módulo comprado |
| OI-003 | Preço duplicado entre banco e `Planos.tsx` | §1 | Risco de cobrar valor diferente do anunciado |

## 5. Distância para o alvo (§69–§75)

| Conceito alvo | Hoje |
|---|---|
| PRODUCT / MODULE | implícito em `modulos_contratados` (strings livres) |
| PLAN | `Plano` (ok) |
| ADD-ON | não existe |
| FEATURE / ENTITLEMENT | 6 colunas booleanas em `Plano` + módulo por router |
| USAGE LIMIT | 7 colunas em `Plano` |
| AI CREDIT ALLOCATION / OVERAGE | não existe |
| API ACCESS | só `permite_api_parceiros` (API de provisionamento, não API de produto) |
| CONNECTOR ACCESS | não existe |
| `PRICE_STATUS` (ex.: `PENDING_DEFINITION`) | não existe. `preco_mensal` é `NOT NULL` Float. Não há como representar "preço a definir" sem usar 0, o que o §71 proíbe. **Precisa de schema novo antes de cadastrar Public Procurement.** |
| Commercial source of truth única | não existe (§1) |
| `tenant.hasFeature(...)` | `PlanLimitsProvider` é o embrião certo, mas com um método por flag |

## 6. Billing

Mercado Pago, cobrança **avulsa mensal** (preferência de pagamento),
não assinatura recorrente. O webhook (HMAC) confirma o pagamento e
ativa ou renova a `Licenca`. O cron diário cuida de lembrete e
suspensão; `declarar_pagamento` dá carência de 3 dias. Plano com preço 0
ativa a licença sem cobrança (plano "Teste").
