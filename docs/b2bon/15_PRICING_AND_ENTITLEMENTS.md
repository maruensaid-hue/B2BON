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

## 6A. Comissão privada recorrente e Summer Sales Challenge (D-080)

- `PRIVATE_RECURRING_COMMISSION` v1: 20% recorrente; só mensalidade efetivamente paga gera comissão (PAYMENT_RECEIVED);
  base = Margem Comissionável Líquida da mensalidade (D-074, confirmada pelo PO — OI-028 resolvido); inadimplência (30 + 10 dias) retém a comissão a
  pagar (HOLD); cancelamento encerra as futuras (STOP_FUTURE). Configurável e versionada.
- Quota NEW_MRR por representante: R$ 7.500 (Out/26) → R$ 20.000 (Mar/27); equipe de 7: R$ 52.500 → R$ 140.000.
  Pipeline alvo de Out/26: R$ 30.000 por representante; depois, 3x a quota (configurável). Ticket baseline R$ 1.750.
- Summer Sales Challenge (Dez/26 + Jan/27): meta R$ 27.500 por representante (equipe = R$ 27.500 × representantes ativos; 7 = R$ 192.500); bônus sobre a comissão das
  novas vendas da janela: 100–119% +20%, 120–149% +35%, ≥150% +50% (abaixo de 100%: sem bônus); elegibilidade com venda
  em cada mês, CRM atualizado, carteira adimplente e política comercial cumprida.
- Government Bookings nunca entram no New MRR privado; a comissão Government segue a própria política.

## 6. B2B ON Government (D-072)

Modelo comercial próprio para órgãos públicos, no **mesmo catálogo** (tabela `plano`) e nos mesmos mecanismos (entitlements,
carteira de AI Credits, comissões, auditoria). O modelo privado mensal não muda.

| Campo do plano | Privado | Government |
|---|---|---|
| `segmento` | PRIVATE | GOVERNMENT |
| `modelo_cobranca` | MONTHLY_SUBSCRIPTION | GOVERNMENT_LICENSE_PLUS_ANNUAL_SUBSCRIPTION (preferencial) · GOVERNMENT_ANNUAL_SUBSCRIPTION_ONLY |
| `tipo_preco` | FIXED / STARTING_AT | CONTRACT (nunca no checkout) |
| preço | `preco_mensal` | `preco_licenca`, `preco_implantacao`, `preco_assinatura_anual` (o `preco_mensal` fica 0 e não é usado) |
| AI Credits | franquia mensal por módulo (`FRANQUIAS`) | `creditos_ia_anuais` (pool por período do contrato) |
| entitlements | colunas do plano | usuários = `max_usuarios`; módulos = `modulos_contratados`; API = `permite_api_parceiros`; demais = `entitlements` (JSON validado; vazio = "conforme contrato") |

| Oferta | Licença | Implantação | Subscrição anual | Contratação inicial | AI Credits/ano |
|---|---|---|---|---|---|
| Department | R$ 72.000 | R$ 12.000 | R$ 24.000 | R$ 108.000 | 300.000 |
| **Professional (recomendada)** | R$ 120.000 | R$ 20.000 | R$ 36.000 | R$ 176.000 | 600.000 |
| Enterprise | R$ 180.000 | R$ 30.000 | R$ 54.000 | R$ 264.000 | 1.200.000 |

**Entitlements (D-075, OI-024 resolvido)** — no catálogo central, exibidos pela página pública e pelo Admin → Planos:

| Entitlement | Department | Professional | Enterprise |
|---|---|---|---|
| internal_users | 20 | 50 | 100 |
| administrative_units | 1 | 5 | 20 |
| monthly_accounts (franquia de contas MAP/PREDATOR, `franquia_contas_mes`, D-076) | 1.000 | 3.000 | 10.000 |
| ai_credits_annual (separado da franquia de contas) | 300.000 | 600.000 | 1.200.000 |
| storage_gb | 100 | 500 | 2.048 |
| operational_retention_months | 12 | 24 | 60 |
| crm · map · predator · bid_intelligence | sim | sim | sim |
| public_procurement | BASIC | FULL | FULL |
| business_network · corporate_brain | sim | sim | sim |
| api_access | não | sim | sim |
| sso | não | OPTIONAL | sim |
| support_sla | BUSINESS_HOURS_8X5 | PRIORITY_BUSINESS_HOURS_8X5 | CRITICAL_BUSINESS_HOURS_8X5 |
| onboarding | STANDARD | ADVANCED | DEDICATED |

Aplicados pela plataforma: usuários (assentos), módulos (acesso), API, franquia mensal de contas e o nível do Public
Procurement (D-076). Contratuais/declarativos: unidades administrativas, armazenamento, retenção, SSO, suporte e onboarding.

**Public Procurement BASIC × FULL (D-076)** — capabilities do mesmo motor (`Entitlements.has_capability`), sem dois motores:
BASIC = gestão de demandas, workspace de processos, PCA, cadastro de fornecedores, pesquisa de preços básica, documentos,
tarefas, prazos, workflow básico, acompanhamento de contratos, painel e trilha de auditoria; FULL = BASIC + Supplier 360,
grafo, Document Intelligence/RAG, ETP/TR/Edital Intelligence, matriz de conformidade, avaliação, agente, Next Best Action,
Risk Engine, comparação de propostas, inteligência de contrato, SLA, aditivos, renovação, analytics avançado e APIs. As
rotas de inteligência (`/procurement/riscos`, `/proximas-acoes`, `/fornecedores/ranking`, `/fornecedores/{id}/360`,
`/contratos/{id}/inteligencia`, `/documentos/{id}/estimativa` e `/analisar`) exigem FULL. Plano sem nível (privado) = FULL.

- **Fonte única**: `GET /catalogo` (seção `governo`), `GET /planos` e `GET /governo/planos` leem a tabela `plano`; o frontend não
  tem preço Government no código (teste `test_pagina_publica_e_admin_iguais_ao_catalogo`). Mudar preço = Admin → Planos (auditado);
  contratos guardam a cópia e não mudam.
- **Contrato** (`contrato_governo` + `periodo_assinatura_governo` + `componente_contrato_governo` + `recebimento_governo`):
  ano 1 = licença + implantação + subscrição inicial; ano 2+ = renovação da subscrição (+ serviços/créditos adicionais).
- **Métricas** (`GET /governo/metricas`): bookings por tipo, ARR (só subscrição vigente), New/Renewal ARR, TCV inicial, Cash-In,
  receita comissionável × não comissionável, comissões (inicial, renovação, paga, pendente, a compensar; por representante,
  contrato, cliente) e pipeline ponderado.
- **Comissão**: política versionada `politica_comissao` (licença 20%, subscrição inicial 20%, renovações 10%, serviços e
  AI Credits adicionais 10% — D-073 —, implantação não comissionável; gatilho PAYMENT_RECEIVED), sobre
  `comissao_representante` e o repasse mensal existente.
- **Base de cálculo (D-074/D-076, todas as vendas)**: **Margem Comissionável Líquida** = receita recebida − impostos
  atribuíveis (Tax Engine) − infraestrutura **provisionada** atribuível (Infrastructure Cost Pool, plano máximo, alocação
  ponderada 1/2/4 por tier + custos diretos); comissão = margem × taxa (20% inicial, 10% renovação Government). Nunca sobre a
  receita bruta. Sem valores no pool: AWAITING_INFRASTRUCTURE_COST (OI-026). Engine único: `app/contexts/comissoes`.
- **Tax Engine (D-075/D-076)**: Lucro Presumido, um componente por tributo — PIS 0,65% e COFINS 3%; IRPJ 15% e CSLL 9% sobre a
  base presumida de 32% (licença de software, SaaS para simulação, implantação), com o acréscimo de 2026 (presunção × 1,10 acima
  de R$ 5 milhões/ano) e o adicional de IRPJ (10% acima de R$ 20.000 × meses do período); ISS São Paulo/SP 2,90% para 1.05/2800
  (licença) e 1.07/2919 (implantação de suporte/instalação/configuração/manutenção); CBS 0,9%/IBS 0,1% de 2026 com situação
  registrada (só PAYABLE entra). Custo de IA só entra na margem se a política da margem mandar (v1: não). Câmbio: PTAX de
  fechamento do Banco Central (OI-018 resolvido quanto à política).
- **Infrastructure Cost Pool (D-077)**: preços públicos verificados em 2026-10-01 — Render Scale USD 499/mês e Web Service
  12c-96g CUSTOM (D-079: sem preço público; aguarda contrato/proposta/fatura), Neon Scale por uso (USD 0,222/CU-h, USD 0,35/GB-mês, via Capacity Envelope), Lusha
  Premium USD 399,90/mês (provedor de dados); Render Postgres/Key Value/disco disponíveis mas não alocados; Render Enterprise e
  Lusha Scale CUSTOM sem preço. Pesos: STARTER/DEPARTMENT 1, PROFESSIONAL 2, ENTERPRISE 4, BID_INTELLIGENCE 2,
  STRATEGIC_SOURCING 4.
- **CBS/IBS 2026 (D-078)**: WAIVED_BY_COMPLIANCE — alíquotas-teste CBS 0,90% e IBS 0,10% preservadas, caixa zero, sem efeito
  na Margem Comissionável Líquida; COMPENSATED abate do PIS/COFINS (sem dupla contagem); PAYABLE suportado; mudança por
  TaxStatusPeriod (EC 132/2023, ADCT art. 125; LC 214/2025).
- Pendências (OI-026): confirmar componentes Render em uso; Capacity Envelope do Neon; storage envelope; outros fornecedores em
  uso; ISS da subscrição SaaS; perfis de consultoria e suporte.
