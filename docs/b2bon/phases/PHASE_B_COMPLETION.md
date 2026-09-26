# PHASE B — SHARED DOCUMENT & REQUIREMENT ENGINE · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO, "Está previamente autorizado subir para o master e passar para as próximas fases".
- **ADR**: D-062 · **Plano**: `18_STRATEGIC_SOURCING.md` §10.

## O que a Phase B pedia × o que existe

| Item (§38) | Estado | Onde |
|---|---|---|
| Documents | já único (S1): validação, hash, texto por página, SEM_TEXTO declarado, RESTRICTED fora da IA | `sourcing/documentos.py` |
| Extraction | já único (S1): perfis por tipo de documento, uma execução de crédito por documento | `sourcing/requisitos.extrair` |
| Requirements — saída normalizada (§18) | **completado**: categoria, descrição, evidência, fonte, página/cláusula calculadas, confiança (grounded/manual) e **obrigatoriedade** | `ItemExtraido.obrigatorio`, `obrigatoriedade()` |
| Evidence / provenance | **completado**: a regra do requisito manual (trecho tem de estar no texto; página calculada) foi para o engine | `sourcing/requisitos.ancorar_evidencia` |
| Compliance foundation | já única (S1): `sourcing.avaliacao` com direção; a matriz agora mostra a obrigatoriedade | `bids/conformidade.py` |
| Validar com public tender + enterprise RFP | ✅ | `test_sourcing_fase_b.py` |

**Obrigatoriedade** (D-062): lida da linguagem do próprio trecho literal — obrigação ("deverá", "sob pena", "vedado", "must", "shall"…) ou preferência ("desejável", "preferencialmente", "poderá", "should"…). Nenhum sinal ou sinais opostos → **UNKNOWN**. O modelo não é consultado. O humano pode informar no requisito manual. Requisitos anteriores ficam UNKNOWN (nada inferido pela migração).

**Migração** `b4e6f8a0c2d3`: coluna `obrigatorio` em `requisito_licitacao` e `requisito_sourcing`. ADD/DROP COLUMN direto para o SQLite não recriar a tabela e perder o trigger de lado imutável.

**Tela**: requisitos mostram "Obrigatório" / "Desejável" (nada quando UNKNOWN).

## Não feito (portão operacional)

Trocar a leitura para as tabelas unificadas e mover os blobs (TD-087/088). Pré-requisito que não se prova daqui: o backfill rodou em produção e os logs `SOURCING_DIVERGENCIA`/`SOURCING_ESPELHO_FALHOU` ficaram zerados por uma release. Até lá, a leitura dupla segue conferindo.

## Code size guard (§34)

| Métrica | Valor |
|---|---|
| Arquivos adicionados | 3: migração `b4e6f8a0c2d3`, `tests/integration/test_sourcing_fase_b.py`, `docs/b2bon/perf/fase_b.json` |
| Arquivos modificados (código) | 12 (núcleo, bids, procurement, modelos, API, tela de requisitos) |
| LOC da aplicação (`app/`, `alembic/`, `frontend/src/`) | +100 / −20 (líquido +80) |
| LOC de testes | +169 |
| Duplicação | 45 blocos / ~2.185 linhas — **igual** (a fase não criou duplicação) |
| Compartilhado criado | `obrigatoriedade`, `ancorar_evidencia` (núcleo) |
| Reutilizado | `extrair`, grounding, `preparar`, espelho/paridade, `localizar_pagina` |

## Performance budget (§36)

| Medida | Baseline | Phase B |
|---|---|---|
| Consultas por rota e nos fluxos críticos | — | **idênticas** às da baseline |
| p95 das rotas | 13,9–64,7 ms | 15,2–59,0 ms (≈ +10% uniforme, inclusive em rotas de CRM não tocadas: ruído da máquina; nenhuma acima do limite) |
| Inicialização / memória / bundle | 3.403 ms / 246,8 MB / 1.298,3 KB | 3.091 ms / 246,9 MB / 1.298,4 KB |

## Validação

| Evidência | Resultado |
|---|---|
| `test_sourcing_fase_b.py`: edital público, RFP enterprise e documento do comprador passam pelo mesmo `extrair` (perfis `edital_tr`, `edital_tr`, `documento_compras`); saída normalizada igual; citação inventada descartada; cláusula só se estiver na página; obrigatório/desejável/UNKNOWN; tudo chega a `requisito_sourcing` no lado e segmento certos; requisito manual com as mesmas mensagens de proveniência; humano decide a obrigatoriedade; matriz mostra o campo | ✅ 2/2 |
| `test_sourcing_nucleo.py`: regras da obrigatoriedade (inclusive sinais opostos → UNKNOWN) | ✅ |
| `test_alembic_upgrade.py`: requisito anterior fica UNKNOWN, leitura dupla estrita bate, trigger de lado sobrevive a upgrade e downgrade | ✅ |
| Postgres 16: migração up/down/up (`PG_MIGRACOES_OK b4e6f8a0c2d3`), `test_sourcing_s3_pg.py`, concorrência | ✅ 4/4 |
| Suíte completa (leitura dupla ESTRITA) | ✅ **2.051 passed** (+5 skipped) |
| E2E | ✅ 6/6 |
| Ruff 40 · oxlint 25 · build | ✅ sem novos |

## Próximo passo

Phase C — Sell side (Public Bid + Enterprise Bid: qualificação, conformidade, Go/No-Go, workspace, apoio à proposta).
