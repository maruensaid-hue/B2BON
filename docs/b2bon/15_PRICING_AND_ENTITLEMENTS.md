# 15 — Catálogo comercial, entitlements, créditos (§69–75)

- **Fase responsável**: 14 (catálogo e visibilidade). Preços da Fase 15 só com valores do PO.
- **Regra**: nenhum preço, plano ou limite foi criado ou alterado. Estado anterior: `PRICING_CURRENT_STATE.md`.

## 1. Catálogo (`app/contexts/platform/catalogo.py`)

Fonte única do **que** é vendido e em que estado. O catálogo não guarda
preço: preço é o `preco_mensal` da tabela `plano`, o mesmo que o checkout
cobra (D-044).

| Produto | Entitlement | Estado hoje | Preço |
|---|---|---|---|
| CRM | módulo `crm` | DISPONIVEL | planos (DEFINIDO) |
| MAP | módulo `map` | DISPONIVEL | planos |
| PREDATOR | módulo `predator` | DISPONIVEL | planos (ver OI-001) |
| Business Network (Shoal) | sem gate | GRATUITO | — |
| Opportunity Intelligence | incluído no `crm` | INCLUIDO | — |
| Bid Intelligence | módulo `bids` | SOB_CONSULTA (liberado pelo super_admin) | PENDING_DEFINITION (OI-015) |
| Public Procurement | módulo `procurement` | EM_DEFINICAO, sempre | PENDING_DEFINITION (Fase 15) |
| API Access | chaves com escopo + módulo | INCLUIDO nos planos | — |
| Conectores de CRM | `CONECTORES_CRM_HABILITADOS` | b2bon_crm INCLUIDO; externos BETA | — |
| Créditos de IA | política de créditos | EM_DEFINICAO enquanto a política for PENDING_DEFINITION | OI-013 |

Regras (testadas em `test_catalogo_comercial.py`):
- DISPONIVEL só com plano self-service que inclua o módulo e preço definido.
- Public Procurement fica EM_DEFINICAO mesmo se um plano o incluir por
  engano; traz `precificacao_pendente` com os campos da Fase 15
  (`modelo_de_preco`, `preco_mensal`, `preco_anual`, `usuarios_incluidos`,
  `creditos_ia`, `limites_api`, `limites_procurement`, `addons`,
  `regras_de_excedente`), todos vazios.
- Conector só aparece "liberado" quando o operador o habilitou.

## 2. Superfícies

| Superfície | Onde | O que mostra |
|---|---|---|
| `GET /catalogo` (público) | `api/v1/catalogo.py` | produtos + estado + comparativo dos planos self-service (limites e recursos) |
| `GET /assinatura` (logado, sem exigir licença ativa) | idem | plano, licença, módulos contratados × disponíveis, uso do mês (usuários, franquia, cadências, campanhas), IA (chamadas, créditos, saldo; sem custo em dólar), conectores |
| Página pública `/planos` | `Planos.tsx` + `CatalogoProdutos.tsx` | preços existentes (inalterados) + todos os produtos com estado + comparativo de recursos por plano |
| Área interna `/assinatura` | `Assinatura.tsx` (menu admin "Assinatura") | o `GET /assinatura`; contratar só o que está DISPONIVEL, o resto vai ao comercial |

## 3. Preços preservados

`tests/unit/test_precos_preservados.py` congela os 12 preços vigentes e
confere as três cópias (página pública, seed, migração). Mudança de preço
exige instrução do PO e atualização consciente do teste. A duplicação em
si (OI-003) continua: a página pública ainda tem os preços no código.

## Fase 5 — créditos de IA

Política de créditos existe (`politica_creditos_ia`), semeada `PENDING_DEFINITION`. Alocação de créditos por plano depende do PO (OI-013); hoje só alocação manual pelo super_admin. Ver `09_AI_FINOPS.md`.
