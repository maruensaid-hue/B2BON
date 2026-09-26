# 06 — AI ARCHITECTURE (Fase 4)

Contexto: `app/contexts/intelligence/` (contrato: `contract.py`).

```
 serviço/feature ──► intel.gerar(db, llm, ContextoIA(tenant, feature, …), LLMRequest)
                        │
                        ├─ registro.FEATURES[feature] → módulo, agente, classe, gatilho, conteúdo externo?
                        ├─ C0? recusa (determinístico)
                        ├─ gatilho automático? teto por tenant/hora (AI_LIMITE_AUTOMATICO_POR_HORA)
                        ├─ roteador.modelo_para(classe) → id do modelo; amostragem só p/ quem aceita
                        ├─ conteúdo externo? + instrução anti-injeção no system
                        ├─ llm_helpers.gerar → LLMProvider (ClaudeProvider)  ── Anthropic API
                        └─ RegistroUsoIa (sucesso | falha | bloqueado), sessão própria
```

## 1. Gateway único (§52, §82)

- Todos os call sites passam pelo gateway (3 medidos na Fase 0; 18 features após a Fase 10: extração de necessidades na Fase 6, análise de edital e de TR na Fase 9, análise de documento de compras na Fase 10).
- Fitness function `tests/unit/test_gateway_ia_unico_caminho.py`:
  ninguém chama `.generate(` fora de `app/llm/`; `llm_helpers.gerar` só no
  gateway; SDK `anthropic` só em `claude_provider.py`; toda feature usada
  está registrada.
- Ledger em sessão independente: rollback do chamador não apaga uso
  incorrido. Falha e bloqueio também são registrados.

## 2. Model Router (§53)

| Classe | Uso | Modelo default | Env |
|---|---|---|---|
| C0 | determinístico (consolidação de perfis, scores) | nenhum | — |
| C1 | curto/barato: FAQ, explicar match, sugerir regra, amostra de tom | `claude-haiku-4-5` | `AI_MODELO_C1` |
| C2 | redação comercial, resumo, estratégia, qualificação | `ANTHROPIC_MODEL` (hoje `claude-sonnet-5`) | `AI_MODELO_C2` |
| C3 | análise documental longa (editais/TRs, Fases 9–10) | `claude-opus-5` | `AI_MODELO_C3` |

C2 mantém o modelo que já estava em produção: nenhuma feature C2 mudou de
modelo. As 4 features C1 passaram a usar o modelo econômico (D-016).

**Bug corrigido**: `claude-sonnet-5` (e Opus 4.7+/5, Fable) rejeitam
`temperature` com 400. O provider enviava `temperature=1.0` sempre.
Agora `LLMRequest.temperature` é `None` por padrão e o roteador só
repassa amostragem a modelos que aceitam (OI-010).

## 3. Registro de features, agentes e ferramentas (§19, §72)

`registro.py`: 19 features (cada uma → módulo, agente, classe, gatilho),
28 agentes (21 ATIVOS, 7 PLANEJADOS após a Fase 12 do §19, marcados como tal na UI),
6 ferramentas com sensibilidade READ / WRITE / EXTERNAL_ACTION /
SENSITIVE_ACTION. `agente_pode_usar(agente, ferramenta)` é a checagem
que o orquestrador da Fase 12 usa.

## 4. Context Engine (§58)

`context_engine.montar(db, tenant, Proposito, consulta)`:
- só busca no próprio tenant;
- **propósito** limita o que pode ser usado: `RESPOSTA_EXTERNA` só usa
  itens `visibilidade="rede"` e PUBLIC/INTERNAL; `USO_INTERNO` usa até
  CONFIDENTIAL; **RESTRICTED nunca vai para LLM**;
- orçamento de caracteres, só itens com aderência (sem aderência = vazio);
- devolve proveniência de cada item (id, tipo, título, origem, fonte).

## 5. Prompt injection (§62)

`prompt_seguro.bloco_dados_externos(fonte, conteudo)` com delimitador
neutralizado + instrução de sistema automática para features marcadas
`conteudo_externo` (agente corporativo, enriquecimento de site,
qualificação, resumo de reunião). Defesas estruturais continuam sendo
as principais: aprovação humana antes de envio, contratos de saída,
sensibilidade de ferramentas.

## 6. Learning Loop (§18)

Aprovar / editar / rejeitar rascunho de IA → `evento_aprendizado`
(evidência, sem conteúdo) + eventos `AIRecommendationAccepted/Rejected`.
Virar conhecimento é decisão humana (regra aprendida ou item do Brain).

## 7. Auditoria (§73)

`registro_uso_ia` por chamada: tenant, usuário, módulo, feature, agente,
workflow, provider, classe, modelo, tokens (entrada, saída, cache
leitura/escrita), latência, entidade, gatilho, status, erro, correlation
id. Visão do tenant: `GET /api/v1/inteligencia/uso-ia`. Custo e créditos: Fase 5.

## 8. Fora do escopo desta fase

Embeddings/RAG vetorial (D-017), tool calling pelo LLM e orquestrador
multi-agente (Fase 12), endpoints de IA na API de produto (dependem da
Fase 5 para cobrança).

## 9. B2B ON Intelligence Agent — orquestração (Fase 12)

`app/contexts/intelligence/orquestrador.py`; registro de ferramentas no
Shared Kernel (`shared/ferramentas.py`), populado por cada contexto
(`<contexto>/ferramentas.py`, carregado pelo contrato do contexto). API:
`POST /inteligencia/agente`, `GET /inteligencia/agente/ferramentas`. UI:
painel no Cérebro Corporativo.

```
pergunta ──► ferramentas PERMITIDAS ao usuário (declarada + agente autorizado + módulo do plano + papel)
               │
               ├─ roteamento por palavras-chave (C0)  ──┐
               └─ sem rota: IA C1 `intelligence.orquestrador`, vendo só o catálogo permitido
                                                        ▼
               compra × venda? → ESCLARECER (nunca mistura)
               READ → executa no tenant do usuário │ WRITE/EXTERNAL → proposta │ SENSITIVE → RECUSADO
```

| Ferramenta | Agente | Módulo | Sensibilidade | Lado |
|---|---|---|---|---|
| `opportunity.analisar_oportunidade` | opportunity_agent | crm | READ | SELL |
| `opportunity.clientes_expansao` | revenue_agent | crm | READ | SELL |
| `crm.listar_oportunidades` | pipeline_agent | crm | READ | SELL |
| `crm.mover_estagio` | pipeline_agent | crm | WRITE (proposta) | SELL |
| `map.saude_conta` | remediation_agent | map | READ | SELL |
| `bids.analisar_licitacao`, `bids.prazos` | bid_qualification_agent | bids | READ | SELL |
| `bids.contratos_vencendo` | contract_intelligence_agent | bids | READ | SELL |
| `procurement.contratos_vencendo` | contract_intelligence_agent | procurement | READ | BUY |
| `procurement.pca_atrasado` | procurement_planning_agent | procurement | READ | BUY |
| `brain.buscar` | sales_strategy_agent | — | READ | NEUTRO |
| `predator.rascunho_mensagem` | cadence_agent | predator | EXTERNAL_ACTION (proposta, vai para aprovação) | SELL |
| `plataforma.alterar_plano` | b2bon_intelligence_agent | — | SENSITIVE_ACTION (recusada) | NEUTRO |

Os cinco exemplos do §84 Fase 12 funcionam: "Analise esta oportunidade…",
"Analise este edital", "Mostre contratos próximos do vencimento" (pergunta
o lado se ambíguo), "Quais compras do PCA estão atrasadas?", "Quais
clientes possuem oportunidade de expansão?".

Agentes: 28 (21 ATIVOS, 7 PLANEJADOS). O orquestrador é o 28º.

## 10. Correção 2026-09-26 — capabilities, não agentes (D-055)

Estrutura mantida: **B2B ON Intelligence Agent → orquestrador → capabilities**, todas pelo AI Gateway.
Capabilities: Research, Extraction, Requirement Analysis, Matching, Evaluation, Recommendation, Risk
Analysis, Document Intelligence, Meeting Intelligence, Revenue Intelligence, Procurement Intelligence.
`tender_analyzer`, `tr_analyzer` e `procurement_intelligence_agent` viram **perfis** de Requirement
Analysis (um extrator, perfis por tipo de documento). Nenhum agente novo para o Enterprise; agentes
PLANEJADOS que só repetem uma capability não serão construídos. Toda capability declara o lado; a regra
"compra × venda → esclarecer" (D-040) continua. Contexto mínimo: intenção → permissão → recuperação só
do processo/documento → blocos ancorados → modelo; regras, SQL e scoring antes de IA. Códigos de feature
e workloads de crédito (Fase 15) **não mudam**, para o histórico continuar reproduzível.
