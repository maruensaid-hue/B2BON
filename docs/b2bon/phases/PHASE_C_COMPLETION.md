# PHASE C — SELL SIDE (Public Bid + Enterprise Bid) · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO, pré-autorização das próximas fases (e da antiga S5, agora parte desta fase).
- **ADR**: D-063 · **Plano**: `18_STRATEGIC_SOURCING.md` §10.

## O que a Phase C pedia × o que existe

| Item (§39) | Estado | Onde |
|---|---|---|
| Public Bid | já existia (Fase 9) + andamento pelo workflow, resultado e contrato na tela | `bids/*`, `LicitacaoWorkspace` |
| Enterprise Bid | **novo, por configuração**: `PRIVATE_RFI`, `PRIVATE_RFQ`, `PRIVATE_TENDER` (+ `PRIVATE_RFP`) → segmento ENTERPRISE; workflow `ENTERPRISE_RFP_SELL@2` com `EM_NEGOCIACAO` só depois da proposta enviada | `bids/fluxo.py` |
| Qualification | fatores do Go/No-Go (o que falta aparece como UNKNOWN com motivo); sem entidade nova | `bids/go_no_go.py` |
| Compliance | matriz (Fase 9) com obrigatoriedade (Phase B) | `bids/conformidade.py` |
| Go/No-Go | **v2**: obrigatório técnico/comercial NON_COMPLIANT bloqueia; desejável e UNKNOWN não | `bids/go_no_go.py` |
| Workspace | **`ProcessWorkspace` compartilhado** (antiga S5): abas na URL; licitação e processo de compra usam | `components/sourcing/ProcessWorkspace.tsx` |
| Proposal support | **resposta por requisito** (categoria `PERGUNTA` para RFI) + **esboço C0** (itens, pendências REVISAR/RESPONDER/COMPROVAR, anexos do cofre, prontidão; JSON e Markdown) | `bids/proposta.py`, `GET /bids/licitacoes/{id}/proposta` |

Fluxos cobertos:
- **Public**: Tender → requisitos → conformidade → Go/No-Go → workspace → proposta → envio (`PROPOSTA_ENVIADA`) → resultado → contrato.
- **Enterprise**: oportunidade privada → requisitos/perguntas → conformidade → Go/No-Go → resposta → proposta → **negociação** → resultado.

Mudança visível no espelho: RFP privado passa de `ENTERPRISE_RFP_SELL@1` para `@2` (backfill diário atualiza; divergência COMPARAR esperada até ele rodar).

## Code size guard (§34)

| Métrica | Valor |
|---|---|
| Arquivos adicionados | 8: `bids/proposta.py`, migração `c6f8a0b2d4e5`, `ProcessWorkspace.tsx`, `PropostaAba.tsx`, `test_sourcing_fase_c.py`, `e2e/auth.setup.ts`, `e2e/workspace-sourcing.spec.ts`, `perf/fase_c.json` |
| Arquivos modificados | 23 |
| LOC da aplicação (`app/`, `alembic/`, `frontend/src/`) | +948 / −381. A maior parte é o `LicitacaoWorkspace.tsx` reorganizado em abas (cartões movidos e reindentados); código novo real ≈ +150 no backend e +260 no frontend |
| LOC de testes (unit/integration/E2E) | +209 / −8 |
| Duplicação | 45 blocos / ~2.185 linhas — **igual** |
| Compartilhado criado | `ProcessWorkspace` (UI), `Workflow.proximos` (núcleo) |
| Reutilizado | matriz, cofre, Go/No-Go, workflow/vínculo, espelho, `Badge/Card/Button` |

## Performance budget (§36)

| Medida | Baseline | Phase C |
|---|---|---|
| Consultas por rota e nos fluxos críticos | — | **idênticas** (o workspace ganhou o bloco `fluxo` sem consulta extra) |
| p95 das rotas | 13,9–64,7 ms | 11,2–62,0 ms; `comprador · riscos` 59,2 ms (rota não tocada; 40–50 ms em outras rodadas do mesmo código — ruído) |
| Bundle | 1.298,3 KB / 58 arquivos | 1.304,8 KB / 59 (+6,5 KB: `ProcessWorkspace` + chunk da aba de proposta) |
| Inicialização / memória | 3.403 ms / 246,8 MB | 3.398 ms / 247,0 MB |

## Validação

| Evidência | Resultado |
|---|---|
| `test_sourcing_fase_c.py`: Enterprise RFQ do recebimento ao resultado com negociação (e recusa de negociação cedo, com a mensagem); público sem negociação até o contrato; Go/No-Go v2 (desejável não bloqueia, obrigatório bloqueia); esboço de proposta com pendências, anexos do cofre, prontidão, Markdown e **zero chamadas de IA**; resposta em requisito descartado recusada; outro tenant não lê nem responde | ✅ 5/5 |
| Testes atualizados para a v2 (`test_sourcing_s3.py`, `test_sourcing_s4.py`, `test_sourcing_fase_a.py`); paridade da v1 mantida | ✅ |
| Migração up/down/up SQLite (com trigger de lado) e Postgres 16 (`PG_MIGRACOES_OK c6f8a0b2d4e5`) + testes PG | ✅ |
| Suíte completa (leitura dupla ESTRITA) | ✅ **2.056 passed** (+5 skipped) |
| E2E | ✅ **8/8** (setup de login + 7 specs, inclusive a nova do workspace: abas, andamento pelo workflow, esboço de proposta) |
| Ruff 40 · oxlint 25 · typecheck · build | ✅ sem novos |

Achado durante o E2E (pré-existente, não da fase): primeira abertura da página pública de planos dispara semente preguiçosa em paralelo; no SQLite uma chamada responde 500 `database is locked` (TD-091). Postgres não é afetado.

## Próximo passo

Phase D — Public buy side (demanda, planejamento, PCA, processo, fornecedor, avaliação, contrato, risco; TD-090).
