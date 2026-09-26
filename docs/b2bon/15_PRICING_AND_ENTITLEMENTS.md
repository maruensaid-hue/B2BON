# 15 — Catálogo comercial, entitlements, créditos (§69–75)

- **Fase responsável**: 14 (catálogo e visibilidade) e 15 (AI Credits, com valores do PO).
- **Regra**: nenhum preço de plano foi criado ou alterado. Os únicos preços novos são os pacotes de AI Credits enviados pelo PO na Fase 15. Estado anterior: `PRICING_CURRENT_STATE.md`.

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
| B2B ON AI Credits | franquia por módulo + pacotes | DISPONIVEL (Fase 15) | pacotes do catálogo versionado `pacote_credito` |

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

## 4. B2B ON AI Credits (Fase 15)

Fonte única de preço: `pacote_credito` (versionado). A página pública, a
área do cliente e o catálogo comercial leem `GET /ai-credits/pacotes`; o
frontend não tem preço fixo (teste `test_frontend_nao_tem_preco_de_pacote_fixo_no_codigo`).

| Pacote | Créditos | Preço | Preço efetivo / 1.000 |
|---|---|---|---|
| AI Start | 5.000 | R$ 99 | R$ 19,80 |
| AI 15K | 15.000 | R$ 249 | R$ 16,60 |
| AI 30K | 30.000 | R$ 449 | R$ 14,97 |
| AI 75K | 75.000 | R$ 899 | R$ 11,99 |
| AI 150K | 150.000 | R$ 1.499 | R$ 9,99 |
| AI 350K | 350.000 | R$ 2.999 | R$ 8,57 |
| AI 1M | 1.000.000 | R$ 6.990 | R$ 6,99 |
| Enterprise | sob medida | CONTACT_SALES | — |

Validade dos pacotes: 12 meses. Mudança de preço = nova versão auditada
(`POST /finops/pacotes/{codigo}/versoes`); compras guardam a versão paga.

Franquia mensal incluída (`finops/comercial.py::FRANQUIAS`), sem rollover:

| Produto | Créditos/mês | Estado |
|---|---|---|
| CRM | 5.000 | ativa |
| MAP | +10.000 | ativa |
| PREDATOR | +20.000 | ativa |
| Opportunity Intelligence | +10.000 | add-on (não vendido hoje: não concede) |
| Business Network Intelligence | +10.000 | add-on (não vendido hoje: não concede) |
| Bid Intelligence | +25.000 | ativa |
| Public Procurement | faixa 50.000–100.000 | PENDING_FINAL_DEFINITION (OI-017) |
| Full Suite | faixa 75.000–100.000 | PENDING_FINAL_DEFINITION; hoje = soma dos módulos |
| Enterprise | pool por contrato | `franquia_personalizada` |

Entitlements: a franquia segue os módulos do plano ativo (`Plano.modulos_contratados`);
o comparativo público mostra `ai_credits_mensais` por plano. API consome a
mesma carteira (`gatilho=api`), com limite próprio opcional.
Public Procurement: preço-base PENDING_DEFINITION, sem botão de compra.

## 5. Catálogo por job-to-be-done — especificação (D-059, OI-019 resolvido)

> **Implementada na Phase I (D-069, OI-021 resolvido)**, com estas escolhas de mecanismo: planos na tabela `plano`
> (migração `a3c5e7f9b1d2`) com `tipo_preco` FIXED/STARTING_AT; `moeda` e `periodo_cobranca` não viraram colunas
> (tudo é BRL mensal hoje); buyer users = `max_usuarios` do plano; tier Enterprise = chave `sourcing_enterprise` no
> plano, lida pela feature `SOURCING_ENTERPRISE`; página de vendas pelas **linhas comerciais** do `GET /catalogo`.
> Os valores abaixo são do PO; nenhum foi criado ou estimado. Usuários do Bid Intelligence: 10 incluídos (D-071, OI-023
> resolvido); limite de assentos = incluídos + `licenca.usuarios_adicionais`, pelo entitlement; papel externo não conta.

### 5.1 Produtos e planos

| Produto | Plano | Lado | Módulo (chave) | Tipo de preço | Preço | Período | Buyer users incluídos | AI Credits/mês | Estado comercial |
|---|---|---|---|---|---|---|---|---|---|
| B2B ON Bid Intelligence | Bid Intelligence | SELL | `bids` (existente) | FIXED | R$ 1.490 | mensal | 10 incluídos (D-071); adicionais suportados, preço PENDING_DEFINITION | 25.000 (franquia `bids` já existente; pool do tenant) | vendável |
| B2B ON Strategic Sourcing | Strategic Sourcing | BUY privado | `sourcing` (novo) | FIXED | R$ 2.990 | mensal | 5 | 50.000 | COMING_SOON até a S8 entregar o fluxo |
| B2B ON Strategic Sourcing | Strategic Sourcing Enterprise | BUY privado | `sourcing` + tier ENTERPRISE | **STARTING_AT** | a partir de R$ 5.990 | mensal | por contrato | 100.000 (pool por contrato, D-050) | CONTACT_SALES |
| B2B ON Public Procurement | — | BUY público | `procurement` (existente) | PENDING_DEFINITION | — | — | — | PENDING_FINAL_DEFINITION (OI-017) | EM_DEFINICAO (inalterado) |

- Sem cobrança extra por oportunidade pública ou privada no Bid Intelligence.
- Sem plano "Pro".
- **Bundles futuros**, preparados e sem preço (OI-022):
  - *B2B ON Revenue & Bids*: CRM + PREDATOR + Opportunity Intelligence + Bid Intelligence;
  - *B2B ON Procurement Intelligence*: Strategic Sourcing + Supplier Intelligence + Contract Intelligence + AI.

  Um bundle é um plano com vários módulos, o mesmo mecanismo das suítes atuais.

### 5.2 Fonte única da verdade

Cada dado comercial tem um dono só. Frontend, billing e página de vendas derivam dele:

| Dado | Dono (existente → evolução) |
|---|---|
| produto, módulo, estado de cada capacidade | `platform/catalogo.py` + registro de capacidades com estado (AVAILABLE/BETA/COMING_SOON/CONTACT_SALES) |
| plano, preço, moeda, período, tipo de preço, usuários incluídos | tabela `plano`. Ganha `tipo_preco` (FIXED/STARTING_AT/PENDING_DEFINITION/CONTACT_SALES), `moeda`, `periodo_cobranca` e `buyer_users_incluidos` (resolve TD-011). STARTING_AT nunca vai para o checkout self-service |
| AI Credits incluídos | `finops/comercial.py::FRANQUIAS` (já é a fonte da Fase 15). Entradas novas: `sourcing` = 50.000 e `sourcing_enterprise` = 100.000. O tier Enterprise **substitui** a franquia `sourcing` (não soma); o pool por contrato vai em `franquia_personalizada` |
| pacotes de top-up | `pacote_credito` (versionado, Fase 15) |
| entitlements | `shared/entitlements.py` (módulos + features) sobre `PlanLimitsProvider` |

A página pública e a área logada leem `GET /catalogo`. As cópias antigas de preço em `Planos.tsx` são o OI-003, e os
planos novos não entram nelas.

### 5.3 Entitlements (desenho; nomes do pedido → mecanismo existente)

| Pedido | Mecanismo | Observação |
|---|---|---|
| BID_INTELLIGENCE | módulo `bids` (existente) | só muda o nome comercial |
| PUBLIC_BIDS, ENTERPRISE_BIDS | derivados de `bids` (`segment` do processo) | não são vendáveis separados; se virarem flag, respondem `has_module("bids")` |
| STRATEGIC_SOURCING | módulo novo `sourcing` em `MODULOS` | — |
| STRATEGIC_SOURCING_ENTERPRISE | feature `SOURCING_ENTERPRISE` no plano do módulo `sourcing` | tier do mesmo módulo, não módulo novo |
| SUPPLIER_PORTAL | feature incluída em `sourcing` (os dois tiers) | — |
| SUPPLIER_GUEST | **papel** (`supplier_guest`), não feature de plano | não conta como buyer seat; acesso só por convite, às peças que o comprador autorizou |
| Buyer seat | usuário do tenant com permissão de operar `sourcing` | limite = `buyer_users_incluidos` + adicionais (preço pendente, OI-022) |
| API_ACCESS | chaves de API por escopo (existentes) + escopos novos `sourcing:*`, `bids:*` | não duplica: API de produto já é "incluída nos planos" |
| PREMIUM_CONNECTORS | registro de conectores com liberação por plano (hoje por operador, D-041) | — |
| MULTI_BUSINESS_UNIT | feature nova. Avaliar reuso de `SUBTENANTS` na implementação | a carteira de créditos é por tenant (D-050) |
| ADVANCED_WORKFLOWS, ADVANCED_ANALYTICS, SSO, ENTERPRISE_SLA | features novas do tier Enterprise | SSO é COMING_SOON; SLA é contratual (CONTACT_SALES) |

### 5.4 Estado real das capacidades (o que pode ser anunciado)

| Produto | AVAILABLE | BETA | COMING_SOON | CONTACT_SALES |
|---|---|---|---|---|
| Bid Intelligence — Public | edital/TR, Compliance Matrix, Go/No-Go, Bid Workspace, cofre, prazos, concorrência, Contract Intelligence, atas/registro de preço como tipo de processo | fonte PNCP (experimental, D-032) | PCA e sinais de contratação de compradores, proposal support | — |
| Bid Intelligence — Enterprise | registro e análise de RFI/RFP/RFQ/EOI/Private Tender no mesmo workspace, resultado, contrato | — | Vendor Qualification, eventos de sourcing recebidos, vendor questionnaire, negociação (S7) | — |
| Strategic Sourcing | — | — | todas as capacidades da resolução (S8). Supplier 360 e matching da rede existem e serão reutilizados | — |
| Strategic Sourcing Enterprise | pool de AI Credits por contrato e excedente pós-pago (Fase 15) | — | advanced workflows/approvals, API de sourcing, conectores premium, multi business unit, advanced analytics, SSO/SAML | SLA enterprise, condições por contrato |
| Public Procurement | inalterado (Fase 10) | — | — | preço pendente |

### 5.5 AI Credits

- Carteira única do tenant (D-050), sem carteira por módulo.
- Só workloads de inteligência consomem créditos; operação determinística é 0 (C0), como hoje.
- Workloads Enterprise/Sourcing entram no catálogo versionado como nova versão (`CREDIT_CATALOG_V2`, na
  implementação): proposal analysis, proposal comparison, AI evaluation, supplier intelligence e contract intelligence.
- Tudo passa pelo AI Gateway e pelo Usage Ledger existentes.
