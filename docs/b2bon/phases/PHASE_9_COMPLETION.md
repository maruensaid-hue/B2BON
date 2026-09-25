# PHASE 9 — BID INTELLIGENCE / SELL SIDE · Completion Report

- **Data**: 2026-09-25 · **Branch**: `staging` · **Autorização**: PO (autorização geral das Fases 1–17)

## 1. Entregas (§84 Fase 9)

| Item | Entrega |
|---|---|
| Procurement Graph foundation | grafo derivado por licitação no vocabulário canônico de procurement |
| Bid Opportunity | `licitacao` (§32: órgão, conta, fonte, datas, valor, modalidade, objeto, concorrentes, parceiros, responsável, status) |
| Tender ingestion | manual, upload (PDF/texto), PNCP experimental e idempotente |
| Tender Analyzer / TR Analyzer | features `bids.analise_edital` e `bids.analise_tr` (C3), agentes ativos, grounding e proveniência |
| Compliance Matrix | 5 status do §34, evidência interna e do edital, ajuste humano justificado |
| Go/No-Go | 10 fatores explicados, recomendação C0, decisão humana autorizada |
| Bid Workspace | endpoint e tela únicos por licitação |
| Document Vault | validade, emissor, escopo, hash, alertas |
| Deadline Engine | proposta, esclarecimento, cofre, contratos, prazos do edital |
| Competitive Intelligence | histórico do tenant contra cada concorrente |
| Contract Intelligence | contratos ganhos + sinais de renovação |
| Entitlement | módulo `bids`, fora de todos os planos (D-030) |

## 2. GATE — proveniência de documento validada

| Evidência | Resultado |
|---|---|
| Documento com SHA-256 igual ao do arquivo, fonte, texto por página; download com hash; duplicata = 409 | ✅ |
| Só requisito com trecho literal é gravado; página calculada (a IA disse 1, o texto diz 2 → 2); cláusula fora da página descartada; categoria inválida descartada | ✅ |
| **Todo requisito do edital e do TR: trecho literal na página indicada do documento indicado** | ✅ `test_gate_todo_requisito_aponta_para_documento_pagina_e_trecho_literais` |
| Matriz repete documento, hash, fonte, página, cláusula e trecho | ✅ |
| Documento longo em blocos medidos; análise parcial declarada | ✅ |
| Documento sem texto não é analisado (sem chamada de IA) | ✅ |
| Requisito manual com documento exige trecho existente | ✅ |
| Isolamento entre tenants (lista, workspace, download, envio, análise) | ✅ |
| `tests/integration/test_bid_intelligence.py` | ✅ 19 testes |
| Suite completa | ✅ **1.825 passed** |
| Frontend lint (25) + typecheck + build | ✅ |
| E2E | ✅ 4/4 |
| Migração `5ddf7b14a837` em SQLite e Postgres 16 | ✅ |

Teste ajustado: `test_registro_de_agentes_mostra_planejados_como_planejados`
usava `tender_analyzer` como exemplo de agente planejado; ele agora é ativo.

## 3. Decisões e pendências

D-030 a D-033. **OI-015** (PO): empacotamento/preço do Bid Intelligence.
TD-059 (OCR), TD-060 (PNCP real), TD-061 (arquivos no banco), TD-062
(casamento lexical). OI-001, OI-010, OI-012, OI-013, OI-014 continuam.
Nenhum preço ou plano alterado.

## 4. Próxima fase

**PHASE 10 — PUBLIC PROCUREMENT / BUY SIDE.**
