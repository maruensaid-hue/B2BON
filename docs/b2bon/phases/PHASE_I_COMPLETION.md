# PHASE I — COMMERCIALIZATION · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO (OI-021 autorizada como Phase I; pré-autorização das próximas fases).
- **ADR**: D-069 (implementa D-059) · **Plano**: `18_STRATEGIC_SOURCING.md` §10 · **Preços**: `15_PRICING_AND_ENTITLEMENTS.md` §5.

## O que a Phase I pedia × o que existe

| Item (§45) | Estado | Onde |
|---|---|---|
| Plans | **novos**, só com valores aprovados (D-059): Bid Intelligence R$ 1.490 · Strategic Sourcing R$ 2.990 (5 usuários) · Strategic Sourcing Enterprise **a partir de** R$ 5.990. Migração de dados idempotente | `alembic/versions/a3c5e7f9b1d2_*` |
| Modules | `bids` e `sourcing` (existentes) vendidos pelos planos; Enterprise é tier (`sourcing_enterprise`), não módulo | `plano.modulos_contratados` |
| Entitlements | feature `SOURCING_ENTERPRISE`; módulos como antes; Supplier Guest segue sem assento (D-066) | `shared/entitlements.py` |
| AI Credits | franquias `sourcing` 50.000 e `sourcing_enterprise` 100.000 (substitui, não soma); `bids` 25.000 já existia; carteira única | `finops/comercial.py` |
| Sales page | seção **Produtos** por job-to-be-done a partir de `GET /catalogo` → `linhas`: preço (FIXED ou "a partir de"), AI Credits, usuários, assinar × falar com o comercial; pendente = "preço em definição", sem número | `components/LinhasComerciais.tsx`, `platform/catalogo.py` |
| Subscription UI | cadastro lista só planos FIXED self-service; assinatura mostra "condições por contrato" para STARTING_AT e os AI Credits do plano | `tenant_service`, `pages/Assinatura.tsx`, `pages/CriarConta.tsx` |

| Produto comercial (§45) | Estado |
|---|---|
| B2B ON Revenue Intelligence | planos de suíte e avulsos existentes (preços da Fase 14 **inalterados**, teste de preços preservados) |
| B2B ON Bid Intelligence | R$ 1.490/mês, 25.000 AI Credits, Public + Enterprise Bids sem cobrança extra; usuários **a definir** (OI-023) |
| B2B ON Public Procurement | **PENDING_DEFINITION**: sem plano; mesmo um plano criado por engano não é oferecido |
| B2B ON Strategic Sourcing | R$ 2.990/mês, 5 usuários, 50.000 AI Credits; Enterprise a partir de R$ 5.990, 100.000, venda assistida |
| B2B ON Suite | **PENDING_DEFINITION** (preço e franquia da suíte completa, OI-017) |

Nenhum preço foi inventado ou alterado. Pendências novas: OI-023 (usuários do Bid Intelligence).

## Code size guard (§34)

| Métrica | Valor |
|---|---|
| Arquivos adicionados | 5: migração `a3c5e7f9b1d2`, `components/LinhasComerciais.tsx`, `test_comercializacao_fase_i.py`, `perf/fase_i.json`, este relatório |
| Arquivos modificados | 16 (catálogo, franquias, entitlements, plano + schemas, cadastro, Planos/Assinatura/CriarConta, seed e specs do E2E, testes de preço e de migração) |
| LOC da aplicação | +347 / −20 |
| LOC de testes | +233 / −4 |
| Duplicação | 43 blocos / ~1.889 linhas (sem novo); formatador `brl` reutilizado |
| Reutilizado | tabela `plano`, checkout e cadastro existentes, `FRANQUIAS`, catálogo central, `PlanLimitsProvider`, carteira única |

## Performance budget (§36)

Rotas medidas com as mesmas consultas da Phase H; `/catalogo` ganhou 1 consulta (planos "a partir de") e segue com
cache público de 5 min. Bundle 1.343,0 KB / 80 (+3,4 KB: seção de produtos). Inicialização 3.229 ms, memória 251,4 MB.

## Validação

| Evidência | Resultado |
|---|---|
| `test_comercializacao_fase_i.py`: linhas com preços aprovados; Enterprise "a partir de" fora do cadastro e recusado no servidor mesmo marcado self-service; Procurement nunca oferecido; entitlements e franquia pelo plano real (50K → 100K substitui; 25K) | ✅ 4/4 |
| Preços congelados: migração = D-059 (preço, usuários, créditos, tipo); Procurement sem franquia | ✅ `test_precos_preservados.py` |
| Migração real: SQLite up/down/up idempotente (`test_alembic_upgrade.py`); Postgres 16 `PG_MIGRACOES_OK a3c5e7f9b1d2` com os 3 planos | ✅ |
| Suíte completa | ✅ **2.086 passed** (+8 skipped) |
| E2E | ✅ **12/12** (novo: página de vendas com os preços aprovados, "a partir de" sem botão de compra, pendentes sem valor, assinar leva ao cadastro) |
| Ruff 40 · oxlint 25 · build | ✅ sem novos |

## Aceite final do plano A–I (§46–§47)

| Critério | Evidência |
|---|---|
| **S1** empresa prospecta, vende e expande | PREDATOR/CRM/MAP/Opportunity (Fases 1–12) — E2E `criar-negocio`, `gerar-proposta`, `map-risco`; suíte de integração |
| **S2** fornecedor identifica, analisa e responde oportunidade pública | Bid Intelligence (Fases 9, B, C) — E2E `workspace-sourcing`; `test_sourcing_fase_b/c` |
| **S3** comprador público planeja, contrata e acompanha | Public Procurement (Fases 10, D) — `test_public_procurement.py`, workspace e riscos com consultas constantes |
| **S4** comprador enterprise executa RFI/RFP/RFQ e strategic sourcing | Phases E e G — E2E `strategic-sourcing`; `test_sourcing_fase_e/g` (+ Postgres) |
| **Enterprise supplier** responde processos privados | Phase F — E2E `portal-fornecedor` (sem login); `test_sourcing_fase_f` |
| Sem plataforma duplicada / engines compartilhados | um núcleo `sourcing` (workflow, ruleset, requisitos, avaliação, documentos, nativo) usado pelos quatro segmentos (D-055, D-061) |
| Isolamento de tenant | testes por fase (outro tenant → 404/vazio); leitura dupla ESTRITA na suíte |
| Barreira Buy/Sell | fitness `test_barreira_buy_sell.py`, `test_barreira_sourcing.py`; lado imutável por trigger (SQLite e Postgres) |
| AI metering | fitness do caminho único do AI Gateway; C0 = 0 crédito; uma execução por operação (Phase G) |
| Auditoria · permissões | eventos `sourcing_*`, aprovação só por admin, módulos por plano, ferramentas do agente por módulo |
| Performance | orçamento por fase contra `perf/baseline.json`; consultas iguais ou menores e constantes com o volume |
| Testes · documentação | 2.086 backend + 12 E2E + 7 Postgres; completion report e ADR por fase (D-061 … D-069) |

## Operação após o deploy

- Rodar `/cron/sourcing-sincronizar` uma vez (backfill das tabelas unificadas; S3).
- `alembic upgrade head` cria os planos D-059; conferir no Admin → Planos.
- Portão operacional S6 (TD-087/088): trocar a leitura para as tabelas unificadas só com evidência do backfill em produção.
