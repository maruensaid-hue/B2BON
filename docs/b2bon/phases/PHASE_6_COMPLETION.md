# PHASE 6 — OPPORTUNITY INTELLIGENCE · Completion Report

- **Data**: 2026-09-25 · **Branch**: `staging` · **Autorização**: PO (autorização geral das Fases 1–17)

## 1. Entregas (§84 Fase 6)

| Item | Entrega |
|---|---|
| Meeting Intelligence | Card lista reuniões da conta (status, transcrição, resumo) e necessidades extraídas |
| Need Extraction | Feature de IA `opportunity.extracao_necessidades` (Opportunity Agent, ativo) com citação literal obrigatória; `necessidade_oportunidade` sugerida → confirmada/descartada por humano; Learning Loop |
| Offer Intelligence | 21 campos do §25 na `oferta`, editáveis na tela de ofertas; `disponivel_para_venda` (D-021) |
| Next Best Offer | `opportunity/nbo.py`: fit_score, motivo, evidências, confiança, riscos, cross-sell, upsell |
| Next Best Action | `opportunity/nba.py`: 10 ações do §22, incluindo "não enviar proposta ainda" e "priorizar remediação" |
| Discovery Gap | `opportunity/discovery.py`: 5 dimensões, INSUFFICIENT_INFORMATION + o que falta + perguntas |
| White Space | `opportunity/white_space.py`: atuais, potenciais, cross/upsell, necessidades sem oferta; valor só com ticket médio |
| MAP Integration | Churn crítico suprime expansão e prioriza remediação; saudável + promotor + espaço em branco = expansão (§26) |
| Evidence | `explicavel.Recomendacao` com evidências tipadas e natureza (confirmado, sugestão IA, cadastro, cálculo, ausência) |
| **Opportunity Intelligence Card** | `GET /inteligencia/oportunidades/{negocio}/card`; card na tela completa do negócio |
| C7 (adiado da Fase 1) | Riscos de pipeline e sugestões de expansão com gate CRM-ou-PREDATOR (D-023) |

## 2. GATE — recomendações explicáveis

| Evidência | Resultado |
|---|---|
| Recomendação sem motivo/evidência/fonte não pode ser construída | ✅ `test_recomendacao_sem_evidencia_ou_motivo_nao_pode_ser_construida` |
| **Todo item recomendável do card tem motivo, evidência (tipo, trecho, natureza), confiança, fonte e data** | ✅ `test_gate_toda_recomendacao_do_card_e_explicavel` |
| Sem dados → INSUFFICIENT_INFORMATION com a lista do que falta, sem palpite | ✅ 2 testes (sem necessidades/inteligência; sem portfólio) |
| Sugestão da IA não conta como confirmada; evidência marcada | ✅ |
| Extração: só grava com citação literal; bloco anti-injeção; medida no ledger | ✅ |
| Churn alto suprime upsell/cross-sell e prioriza remediação | ✅ |
| White Space não estima valor sem ticket médio | ✅ |
| Isolamento entre tenants (card, revisão, white space, ofertas de outro tenant) | ✅ |
| Matriz de entitlement: rotas de oportunidade exigem CRM; C7 | ✅ (+24 casos) |
| Suite completa | ✅ **1.761 passed** |
| Frontend lint (25) + typecheck + build | ✅ |
| E2E | ✅ 4/4 (`criar-negocio` abre a tela completa e valida o card) |
| Migração `a8390a098f04` em SQLite e Postgres 16 (upgrade/downgrade/upgrade) | ✅ |

## 3. Decisões

D-021 (portfólio separado da oferta ativa), D-022 (recomendações C0; IA
só extrai necessidades), D-023 (C7).

## 4. Pendências

- TD-051 (casamento lexical), TD-052 (pesos sem calibração), TD-053 (tela de riscos no menu da Rede).
- OI-001, OI-010, OI-012, OI-013 continuam. Nenhum preço ou plano foi alterado.

## 5. Próxima fase

**PHASE 7 — BUSINESS NETWORK FOUNDATION.**
