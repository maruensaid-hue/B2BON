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
