# PHASE D — PUBLIC BUY SIDE · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO, pré-autorização das próximas fases.
- **ADR**: D-064 · **Plano**: `18_STRATEGIC_SOURCING.md` §10.

## O que a Phase D pedia × o que existe

| Item (§40) | Estado | Onde |
|---|---|---|
| Demand | existia (Fase 10): demanda com aprovação só por admin, consolidação | `procurement/demandas.py`, `cadastros.py` |
| Planning / PCA | existia: plano, itens, painel, prazo e orçamento comprometido | `procurement/planejamento.py` |
| Procurement (processo) | existia + **andamento pelo workflow e documentos que a Lei 14.133 espera na etapa** na tela | `procurement/workspace.py`, `ProcessoWorkspace.tsx` |
| Supplier | existia: Supplier 360 (OFFICIAL / INTERNAL / SELF_DECLARED), ranking por categoria — **sem N+1** | `procurement/fornecedores.py` |
| Evaluation | do fornecedor: existia (fiscalização, nota, ocorrências). De propostas: entidade compartilhada da Phase E, que valerá também para o processo público (sem duplicar) | — |
| Contract | existia: saldo, execução, aditivos, desempenho — **em lote** | `procurement/contratos.py` |
| Risk | existia; **TD-090 resolvido** (preços, itens do PCA e eventos de contrato numa consulta cada) | `procurement/riscos.py` |
| Shared engines | workflow, ruleset, documentos, requisitos, espelho, repositório por lado | `sourcing/*` |
| Testar barreiras | ✅ estendido às superfícies novas (proposta JSON/Markdown, resposta do vendedor, bloco `fluxo`) nos dois sentidos | `test_public_procurement.py` |

Correção: cadastro do comprador sem campo obrigatório (`plano_id`, `orgao_id`…) respondia **500** (erro do banco); agora **422** com o nome do campo, derivado do modelo.

## Code size guard (§34)

| Métrica | Valor |
|---|---|
| Arquivos adicionados | 1 (`perf/fase_d.json`) |
| Arquivos modificados | 14 |
| LOC da aplicação | +180 / −26 |
| LOC de testes | +79 / −2 |
| Duplicação | 45 blocos / ~2.185 linhas — igual |
| Compartilhado criado | `resumo_por_processo`, `inteligencia_em_lote` (substituem os usos em laço; as funções antigas delegam) |
| Reutilizado | `Workflow.proximos`, `Ruleset.documentos`, `ProcessWorkspace` |

## Performance budget (§36) — melhora

| Medida | Baseline | Phase D |
|---|---|---|
| `/procurement/riscos` (40 processos) | 49 consultas · p95 39,9 ms | **10** consultas · p95 30,8 ms |
| Workspace do processo | 58 consultas · p95 64,7 ms | **19** consultas · p95 45,7 ms |
| Fluxo do comprador (criar → 3 etapas → workspace) | 127 consultas · p95 198,4 ms | **63** consultas · p95 137,1 ms |
| Demais rotas | — | consultas idênticas; p95 dentro do ruído |
| Bundle / inicialização / memória | 1.298,3 KB / 3.403 ms / 246,8 MB | 1.306,5 KB / 3.532 ms / 244,4 MB |

Garantia contínua: `test_sourcing_desempenho.py::test_phase_d_sinais_e_workspace_do_comprador_nao_crescem_com_o_volume` (mesmo número de consultas com 3 ou 15 processos e contratos em riscos, workspace e Supplier 360).

## Validação

| Evidência | Resultado |
|---|---|
| Orçamento de consultas por volume + cadastro 422 | ✅ `test_sourcing_desempenho.py` (6/6) |
| Workspace do processo: próximas etapas, ruleset com fonte, documentos da etapa presentes/pendentes | ✅ `test_public_procurement.py` |
| Barreira nos dois sentidos com as superfícies novas (mesmo tenant com os dois módulos) | ✅ |
| Suíte completa (leitura dupla ESTRITA) | ✅ **2.060 passed** (+5 skipped) |
| E2E | ✅ 8/8 |
| Ruff 40 · oxlint 25 · typecheck · build | ✅ sem novos |

## Próximo passo

Phase E — Enterprise buy side (Strategic Sourcing, descoberta de fornecedores, RFI/RFP/RFQ, qualificação, comparação, shortlist, negociação, contrato).
