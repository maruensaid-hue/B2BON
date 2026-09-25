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

`registro.py`: 18 features (cada uma → módulo, agente, classe, gatilho),
27 agentes (16 ATIVOS, 11 PLANEJADOS do §19, marcados como tal na UI),
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
