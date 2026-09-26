# PHASE G — INTELLIGENCE · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO, pré-autorização das próximas fases.
- **ADR**: D-067 · **Plano**: `18_STRATEGIC_SOURCING.md` §10 · **IA**: `06_AI_ARCHITECTURE.md` §3, §9, §10.

## O que a Phase G pedia × o que existe

| Item (§43) | Estado | Onde |
|---|---|---|
| Requirement AI | **já existia** para edital/TR (vendedor, perfil `edital_tr`, extrai também `PERGUNTA`) e documento de compras (comprador público, `documento_compras`). **Novo** para o comprador privado: especificação enviada ao processo → perfil `especificacao_compra` do mesmo Requirement Engine → requisito **sugerido** com trecho, página e obrigatoriedade; vale só depois de confirmado | `procurement/estrategico_ia.py`, `sourcing/requisitos.py` (reuso) |
| Evaluation AI | **novo**: sugestão de status por requisito para cada proposta, ancorada no texto da própria proposta; o avaliador aplica. Lado vendedor já tinha a matriz de conformidade C0 (Fase 9) | `estrategico_ia.sugerir_avaliacoes` |
| Bid Intelligence | **já existia** (análise de edital, conformidade, Go/No-Go v2, concorrência, esboço de proposta), sem mudança | `contexts/bids` |
| Procurement Intelligence | **já existia** no público (documentos, riscos, PCA, contratos); **novo** no privado como capability do `procurement_intelligence_agent` (D-055: sem agente novo) | `procurement/ferramentas.py` |
| Supplier Intelligence | **novo, C0**: histórico do mesmo fornecedor (cadastro, rede, CNPJ ou nome) nos outros processos do comprador: processos, respostas, declínios, adjudicações, desqualificações | `estrategico_sinais.historico` |
| Risk | **novo, C0**: alertas com a evidência que os gerou — sugestões pendentes, perguntas sem resposta, prazo vencido, participação baixa, proposta única, obrigatório não atendido, preço fora da mediana, histórico do fornecedor | `estrategico_sinais.alertas` |
| Recommendation | **novo, C0**: próxima ação por etapa, a partir do workflow do processo (RFQ vai da cotação à aprovação; RFP passa pela avaliação) | `estrategico_sinais.proxima_acao` |
| Orquestrador (§25) | "Compare as propostas", "Histórico do fornecedor X", "Processos de sourcing que precisam de atenção": ferramentas READ, lado BUY, módulo `sourcing`, sem IA quando a palavra-chave casa | `procurement/ferramentas.py` |
| Tela | Visão geral: próxima ação e alertas; Requisitos: especificação, sugestões com trecho e Confirmar/Descartar; Fornecedores: histórico; Propostas: avaliação assistida com "Aplicar" por requisito | `pages/sourcing/InteligenciaSourcing.tsx` |

**AI cost (§32)**: as duas operações com IA passam por AI Gateway → Model Router → Usage Ledger → AI Credits, com estimativa e confirmação antes, **uma execução de crédito por operação**, em workloads que já existiam no catálogo (`procurement_document_intelligence`, `procurement_complex_comparison`). Nenhum peso novo, nenhum preço. Histórico, riscos, recomendação e as três ferramentas são C0 (0 créditos).

## TEST grounding

| Regra | Teste |
|---|---|
| Requisito só com trecho literal da especificação; página calculada; cláusula que não está na página cai; "deverá" → obrigatório, "preferencialmente" → desejável | `test_requirement_ai_so_grava_o_que_esta_no_documento_e_espera_revisao` |
| Sugestão não publica, não aparece no portal do fornecedor (nem o trecho), não é avaliável; descartada some; processo recebendo propostas não gera requisito | idem |
| RESTRICTED nunca chega ao modelo (zero chamadas, zero uso); outro tenant não baixa o documento | `test_documento_restrito_nao_vai_para_a_ia_e_outro_tenant_nao_ve` |
| Evaluation AI descarta citação do texto do requisito, de requisito inventado e do texto de **outro** fornecedor; aceita trecho de anexo | `test_evaluation_ai_ancora_na_propria_proposta_e_nao_grava` |
| Cada chamada leva só a própria proposta (o segredo do fornecedor A não aparece no prompt do B) | idem |
| Uma execução de crédito para a operação, workload do catálogo; nada vira avaliação | idem |
| C0 sem IA e sem uso registrado; evidência de cada alerta; agente roteia para a ferramenta do comprador | `test_inteligencia_c0_alertas_proxima_acao_e_historico` |
| Ferramentas somem do catálogo sem o módulo `sourcing` | `test_ferramentas_de_sourcing_exigem_o_modulo` |

## Code size guard (§34)

| Métrica | Valor |
|---|---|
| Arquivos adicionados | 7: migração `f2c4e6a8b0d1`, `procurement/estrategico_ia.py` (234), `procurement/estrategico_sinais.py` (175), `pages/sourcing/InteligenciaSourcing.tsx` (269), `test_sourcing_fase_g.py`, `test_sourcing_fase_g_pg.py`, `perf/fase_g.json` |
| Arquivos modificados | 14 |
| LOC da aplicação | +1.012 / −32 |
| LOC de testes | +277 |
| Duplicação | 46 → **46** blocos (~2.193 linhas, sem novo) |
| Compartilhado criado | `requisitos_vigentes` e `ultimas_rodadas` (usados pela comparação, pelo portal, pela IA e pelos sinais), `nativo.listar_qualquer`, `documento` no repositório nativo |
| Reutilizado | Requirement Engine, grounding, `prompt_seguro`, AI Gateway (`execucao`, `estimar`), workloads do catálogo, `confirmarConsumo` da tela, `procurement_intelligence_agent`, orquestrador |
| Sem agente novo | o agente existente ganhou 3 ferramentas; os agentes PLANEJADOS continuam planejados (D-055) |

## Performance budget (§36)

| Medida | Phase F | Phase G |
|---|---|---|
| Rotas anteriores | — | consultas **iguais** |
| Workspace do comprador privado | 12 consultas · p95 ≈ 28 ms | **14** (+ documentos, + histórico; 15 quando o fornecedor tem outros processos; constante com o volume) · p95 ≈ 28 ms |
| Comparação | 10 · p95 ≈ 25 ms | 10 · p95 ≈ 25 ms |
| Bundle | 1.335,1 KB / 66 | 1.340,5 KB / 66 (+5 KB, no chunk do sourcing) |
| Inicialização / memória | 3.790 ms / 250,1 MB | 3.624 ms / 251,1 MB |

O texto e o arquivo do documento são colunas adiadas: listar documentos no workspace não os carrega.

## Validação

| Evidência | Resultado |
|---|---|
| `test_sourcing_fase_g.py` | ✅ 5/5 |
| Postgres 16: migração up/down/up (`PG_MIGRACOES_OK f2c4e6a8b0d1`); documento nativo (JSON e arquivo), lado imutável nele, histórico por CNPJ, prazo com fuso nos sinais | ✅ `test_sourcing_fase_g_pg.py` + 6 PG anteriores = 7/7 |
| Fitness: barreira Buy/Sell, tabelas unificadas só pelo núcleo, toda FK com índice, gateway único | ✅ |
| Suíte completa | ✅ **2.078 passed** (+8 skipped: 7 Postgres, 1 medição) |
| E2E | ✅ **10/10** (RFQ agora confere a próxima ação no início e na decisão) |
| Ruff 40 · oxlint 25 · build | ✅ sem novos |

## Próximo passo

Phase H — Optimization (duplicação real, bundle, latência, consultas, memória, custo de IA, cache, jobs).
