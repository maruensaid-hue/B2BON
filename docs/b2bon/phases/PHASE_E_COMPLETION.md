# PHASE E — ENTERPRISE BUY SIDE (Strategic Sourcing) · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO, pré-autorização das próximas fases.
- **ADR**: D-065 · **Plano**: `18_STRATEGIC_SOURCING.md` §10.

## O que a Phase E pedia × o que existe

| Item (§41) | Estado | Onde |
|---|---|---|
| Strategic Sourcing (projeto) | **novo**: processo privado no modelo unificado (lado BUY, segmento ENTERPRISE, nativo) | `procurement/estrategico.py`, `sourcing/nativo.py` |
| Supplier Discovery (§16) | **novo**: Matching Engine (`criterios_fornecedor`) sobre o cadastro interno e os perfis da rede que o comprador pode ver; só campos públicos; oculto/bloqueado não aparece nem é convidável | `estrategico.descobrir`, `shared/matching.py` |
| RFI (§13) | **novo**: perguntas (`PERGUNTA`), respostas por participante, avaliação; `ENTERPRISE_RFI_BUY@1` sem adjudicação | |
| RFP (§14) | **novo**: requisitos técnicos/comerciais/obrigatórios com peso, propostas, avaliação por requisito, negociação | `ENTERPRISE_SOURCING_BUY@1` |
| RFQ (§15) | **novo, leve**: itens com quantidade, preço por item (total calculado), prazo, pagamento, impostos; sem avaliação técnica nem shortlist | `ENTERPRISE_RFQ_BUY@1` |
| Vendor Qualification | **novo**: processo `VENDOR_QUALIFICATION` (fluxo de consulta) + situação do participante (qualificado/desqualificado com motivo) | |
| Proposal Comparison (§20) | **novo, C0**: obrigatórios atendidos, nota ponderada, valor, prazo, pagamento, risco; destaques só entre quem não falhou obrigatório; sem vencedor automático | `estrategico.comparar` |
| Shortlist / Negotiation | **novo**: shortlist; na negociação só a shortlist envia nova rodada (RFQ: qualquer participante) | |
| Approval | **novo**: pedido com justificativa → administrador aprova (adjudica) ou recusa com motivo (volta) | |
| Contract | **novo**: contrato no modelo unificado (lado BUY) com a última rodada do adjudicado | |
| Tela | **nova**: lista + workspace com abas sobre o `ProcessWorkspace` (Visão geral, Requisitos/Itens, Fornecedores, Propostas/Respostas, Comparação) e menu próprio | `pages/sourcing/*` |

Correção encontrada no E2E: o menu lateral de **desktop** nunca mostrou Licitações nem Compras públicas (só o menu mobile); agora mostra, junto com Strategic Sourcing, cada um com o seu módulo.

Fora do escopo (próximas fases): acesso do fornecedor e documentos anexados à proposta (Phase F), IA de avaliação/comparação (Phase G), plano e preço comercial do módulo (Phase I).

## Code size guard (§34)

| Métrica | Valor |
|---|---|
| Arquivos adicionados | 12: migração `d8a0c2e4f6b7`, `sourcing/nativo.py`, `procurement/estrategico.py`, `api/v1/strategic_sourcing.py`, `pages/sourcing/{SourcingProcessos,SourcingWorkspace,tipos}`, `components/sourcing/ProximosStatus.tsx`, `test_sourcing_fase_e.py`, `test_sourcing_fase_e_pg.py`, `e2e/strategic-sourcing.spec.ts`, `perf/fase_e.json` |
| Arquivos modificados | 24 |
| LOC da aplicação | +2.177 / −68 (produto novo: backend ≈ 900, tela ≈ 1.000 com formatação, migração ≈ 110) |
| LOC de testes | +412 / −8 |
| Duplicação | 45 → 46 blocos (~2.185 → ~2.193 linhas): sobra um fragmento de 8 linhas entre duas telas. Extraídos nesta fase: `ProximosStatus` (botões do workflow, usado pelas 3 telas de processo) e `mensagemErro` (usado pelas 5 telas tocadas em C–E) |
| Compartilhado criado | repositório nativo do núcleo, estratégia de matching de fornecedor, `ProximosStatus`, `mensagemErro` |
| Reutilizado | workflow/vínculo/ruleset, Evaluation (direção PROPOSTA), Matching, `ProcessWorkspace`, privacidade da rede, auditoria, lado imutável |

## Performance budget (§36)

| Medida | Baseline | Phase E |
|---|---|---|
| Rotas anteriores | — | consultas **iguais às da Phase D** (TD-090 mantido) |
| Workspace do comprador privado (10 participantes × 5 requisitos avaliados) | nova | **10** consultas · p95 ≈ 26 ms |
| Comparação | nova | **10** consultas · p95 ≈ 25 ms |
| Consultas vs volume | — | iguais com 2 ou 8 participantes (`test_workspace_e_comparacao_nao_crescem_com_participantes`) |
| Bundle | 1.298,3 KB / 58 | 1.325,2 KB / 62 (+27 KB: páginas de sourcing em chunks próprios, carregadas só na rota) |
| Inicialização / memória | 3.403 ms / 246,8 MB | 3.661 ms / 249,3 MB (ruído + um router e um contexto a mais) |

Observação: numa das rodadas o critério de latência (p95 > 1,5x) disparou por ruído e na seguinte passou; o critério de **consultas** é o confiável nesta máquina compartilhada.

## Validação

| Evidência | Resultado |
|---|---|
| `test_sourcing_fase_e.py`: RFP da descoberta ao contrato (rede só visível, oculto recusado, avaliação com justificativa, nota ponderada, destaques sem quem falhou obrigatório, shortlist, rodada 2 só da shortlist, aprovação só por admin, contrato BUY, zero IA); RFQ leve com total calculado e recusa de aprovação; RFI sem adjudicação; tenant, lado e módulo; processo público do comprador fora do sourcing privado; lado imutável nas tabelas novas (trigger + ORM); consultas não crescem com participantes | ✅ 7/7 |
| Postgres 16: migração up/down/up (`PG_MIGRACOES_OK d8a0c2e4f6b7`), fluxo RFQ nativo completo, trigger nas 4 tabelas novas, **inserções nativas concorrentes sem bloqueio** (provado que o provisório 0 bloqueava) | ✅ `test_sourcing_fase_e_pg.py` 2/2 (+4 PG anteriores) |
| Fitness: barreira Buy/Sell (API nova declarada do lado comprador), tabelas unificadas só pelo núcleo (inclui as novas), toda FK com índice | ✅ |
| Suíte completa (leitura dupla ESTRITA) | ✅ **2.067 passed** (+7 skipped: 6 Postgres, 1 medição) |
| E2E | ✅ **9/9** (inclui RFQ pela tela: item, convite, publicação, proposta com preço, comparação, aprovação, contrato) |
| Ruff 40 · oxlint 25 · typecheck · build | ✅ sem novos |

## Próximo passo

Phase F — Business Network Integration (publicação/convite, matching de fornecedores, visibilidade controlada, acesso do fornecedor para responder).
