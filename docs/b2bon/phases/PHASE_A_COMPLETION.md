# PHASE A — FOUNDATION (plano unificado) · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO, "Autorizado" + prompt "UNIFIED BUSINESS & SOURCING IMPLEMENTATION"; escolheu a Phase A quando perguntado sobre a ordem.
- **ADR**: D-061 · **Plano**: `18_STRATEGIC_SOURCING.md` §10 (A–I mapeado sobre S0–S8). Fases B–I não autorizadas; S5 e OI-021 autorizadas e executadas na vez delas (C e I).

## O que a Phase A pedia × o que existe

| Item (§37) | Estado | Onde |
|---|---|---|
| SourcingProcess | já existia (S3) | `processo_sourcing` com lado, segmento, tipo, workflow e ruleset |
| Entidades compartilhadas (§6) | **mapeadas, sem tabela nova** | `18` §10: cada entidade aponta para onde já vive; Proposal, Evaluation, Lot, Item e Deliverable nascem no primeiro fluxo que grava (C/E) |
| Tipos de processo (§5) | já existiam (S1); agora cobertos por teste | `sourcing/tipos.py` — os 11 tipos |
| Lado e segmento | já existiam (S1–S3) | `Lado`, `Segmento`, `lado` imutável |
| Rulesets (§22) | **completado** | versão, vigência (`vigente_desde`), fonte obrigatória, configuração (`parametros`) |
| Fundação de workflow (§21) | **completado** | `sourcing.workflow.vincular/resolver`: (lado, segmento[, tipo]) → workflow + ruleset, num lugar só; sem vínculo, erro |
| Migrar conceitos do Bid Intelligence sem quebrar | já feito (S3 espelho, S4 fluxos) | leitura dupla ESTRITA em toda a suíte |

Também na fase:
- **Duplicação (§35)**: eventos do ORM e backfill iguais nos dois espelhos viraram `sourcing.espelho.instalar`. Cada lado declara só o mapeamento.
- **Classificação única**: "RFP privado é Enterprise" vive só em `bids/fluxo.classificar`, usada pelo espelho e pela validação.

## Code size guard (§34)

| Métrica | Valor |
|---|---|
| Arquivos adicionados | 6: `tests/desempenho/{__init__,test_orcamento_desempenho}.py`, `tests/unit/test_sourcing_fase_a.py`, `scripts/qualidade/duplicacao.py`, `docs/b2bon/perf/{baseline,fase_a}.json` |
| Arquivos modificados (código) | 9 |
| LOC da aplicação (`app/`) | +162 / −120 (**líquido +42**) |
| LOC de testes e ferramentas | +342 / −1 |
| Duplicação detectada | 46 blocos / ~2.211 linhas repetidas → **45 / ~2.185** (−1 bloco, −26 linhas; a fase não criou duplicação) |
| Componentes compartilhados criados | `workflow.vincular/resolver`, `espelho.instalar`, metadados do `Ruleset` |
| Serviços compartilhados reutilizados | motor de workflow e ruleset (S4), espelho e paridade (S3), percentil do script de carga (Fase 17) |

Duplicações maiores que continuam (fora do escopo da Phase A, candidatas da Phase H): telas MAP (`MapContas`/`MapTenants`, 91 linhas), ações de conta em Leads (61), `ConviteVitrine` (58), adaptadores de CRM (27).

## Performance budget (§36)

Baseline medida **antes** de qualquer mudança da fase (`docs/b2bon/perf/baseline.json`), comparada depois (`fase_a.json`). SQLite em memória, 40 registros por entidade, 25 repetições por medida.

| Medida | Baseline | Phase A |
|---|---|---|
| Consultas por rota (11 rotas: painel, CRM, vendedor, comprador) | 4–58 | **idênticas** |
| Consultas nos fluxos críticos (vendedor: 55; comprador: 127) | 55 / 127 | **idênticas** |
| p95 das rotas | 13,9–64,7 ms | 12,4–64,4 ms (variação de ruído; nenhuma acima de 1,5x) |
| Inicialização (`import app.main`) | 3.403 ms | 3.529 ms (ruído de processo; nenhum import novo pesado) |
| Pico de memória do processo de medição | 246,8 MB | 246,8 MB |
| Bundle do frontend | 1.298,3 KB, 58 arquivos, maior 362,9 KB | igual (frontend sem mudança) |

Achado da baseline (pré-existente, não é regressão): `/procurement/riscos` faz 49 consultas e o workspace do processo 58 com 40 processos, porque a pesquisa de preços é consultada por processo (TD-090, Phase D).

Como repetir: `B2BON_MEDIR=docs/b2bon/perf/<fase>.json B2BON_BASELINE=docs/b2bon/perf/baseline.json python -m pytest -q tests/desempenho` (falha se uma rota ganhar consulta ou se o p95 passar de 1,5x a baseline).

## Validação

| Evidência | Resultado |
|---|---|
| `test_sourcing_fase_a.py`: 11 tipos universais; ruleset com versão/vigência/fonte; toda modalidade de venda e de compra resolve pelo ponto central para o mesmo fluxo de antes; sem vínculo falha fechado (comprador Enterprise ainda sem fluxo); vínculo confere lado e tipo, não é sobrescrito, o mais específico vence | ✅ 7/7 |
| Paridade da S4 (todas as transições) e API | ✅ |
| Espelho, backfill (instalador novo), leitura dupla ESTRITA, migração e barreiras | ✅ |
| Postgres 16 (`test_sourcing_s3_pg.py`, concorrência) | ✅ 4/4 |
| Suíte completa | ver `PROJECT_STATE.md` (baseline de qualidade) |
| Ruff | 40 (sem novos) |

## Fora do escopo (próximas fases)

- Tabelas de proposta, avaliação, lote, item: Phase E (RFQ/RFP do comprador) e C.
- Troca da leitura para as tabelas unificadas e blobs (TD-087/088): Phase B.
- `ProcessWorkspace` (antiga S5): Phase C. Comercialização (OI-021): Phase I.

## Próximo passo (não autorizado)

Phase B — Shared Document & Requirement Engine.
