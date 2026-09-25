# AI — CURRENT STATE (Fase 0, 2026-09-25)

Substitui `AI_CURRENT_ARCHITECTURE.md` (raiz, 2026-09-17), que está
**desatualizado**: ele lista 8 pontos de IA e diz que não há ledger de
uso. Hoje há 14 call sites, e existe um ledger parcial (`registro_uso_ia`).

## 1. Camada existente

```
service ──► llm_helpers.gerar(llm, req)               (11 call sites — NÃO medidos)
        └─► llm_helpers.gerar_e_registrar(db, tenant, agente, llm, req)  (3 — medidos)
                    │
                    ▼
            LLMProvider (ABC, app/llm/base.py)
                    │
            ClaudeProvider (único; modelo fixo settings.anthropic_model, timeout 25s)
                    │
                    ▼
               Anthropic API
```

- `get_llm_provider()` (`app/api/deps.py:79`) sempre devolve `ClaudeProvider()`.
- `LLMRequest` tem só `prompt`, `system`, `max_tokens`, `temperature`.
  Não carrega tenant, feature, módulo nem classe de modelo.
- `LLMResponse` retorna `content`, `model`, `input_tokens`, `output_tokens`.
  **Não retorna** `cache_read/creation tokens`, nem custo.
- Não há roteamento de modelo (C0–C3), fallback de provider,
  streaming, tool use, prompt caching, embeddings ou RAG.
- `llm_helpers.gerar` converte `LLMIndisponivel` em `RegraNegocioViolada`,
  então falha de IA nunca vira 500.
- **Nenhum código chama o SDK Anthropic fora de `claude_provider.py`**
  (grep por `anthropic` em `app/`). O "gateway" de fato já existe como
  ponto único de saída. O que falta é a medição universal.

## 2. Inventário de chamadas (14)

| # | Serviço.função | Módulo | Gatilho | Saída chega a terceiro? | Medida em `registro_uso_ia`? | Rate limit IA |
|---|---|---|---|---|---|---|
| 1 | `agente_corporativo_service._gerar_resposta` | Shoal/PREDATOR | usuário (outra empresa) | Sim, **após aprovação humana** | ✅ `corporate_ai_agent` | ✅ |
| 2 | `crm_service.gerar_meeting_brief` | CRM/Intelligence | usuário | Não | ✅ `meeting_agent` | ✅ |
| 3 | `conta_service.sugerir_estrategia_venda` | Intelligence | usuário | Não | ✅ `sales_strategy_agent` | ✅ |
| 4 | `conta_service.enriquecer` (resumo do site) | PREDATOR | usuário **e cron** (fila semanal) | Não | ❌ | ✅ na rota, ❌ no cron |
| 5 | `cadencia_service._gerar_conteudo_toque` / `gerar_para_lote` | PREDATOR | usuário | Sim, **após aprovação** | ❌ | ❌ |
| 6 | `indicacao_service.solicitar` | PREDATOR | usuário | Sim, **após aprovação** | ❌ | ❌ |
| 7 | `qualificacao_service.processar_mensagem_recebida` | PREDATOR | **webhook externo** (WhatsApp/e-mail inbound) | Não. Grava em `TurnoConversa` e notifica o vendedor | ❌ | ❌ |
| 8 | `meeting_bot_service.processar_transcricao` | PREDATOR | webhook Recall | Não (vira `Atividade`) | ❌ | ❌ |
| 9 | `saude_conta_service.gerar_script_resgate` | MAP | usuário | Não (texto para copiar) | ❌ | ❌ |
| 10 | `motor_service.gerar_script_resgate` | MAP interno | super_admin | Não | ❌ | ❌ |
| 11 | `sinal_oportunidade_service.explicar_match_com_ia` | PREDATOR/Intelligence | usuário | Não | ❌ | ❌ |
| 12 | `regra_aprendida_service.sugerir_regra_com_ia` | PREDATOR | usuário | Não | ❌ | ❌ |
| 13 | `comunicacao_service.gerar_amostra` | transversal | usuário | Não (preview) | ❌ | ❌ |
| 14 | `faq_service.responder` | transversal | usuário | Não | ❌ | ❌ |

**Resumo**: 3 de 14 call sites são medidos. O gate §82 ("NO UNMETERED
AI CALL") **não é atendido hoje**. Dois gatilhos são externos (#7
webhook inbound, #8 webhook Recall) e um é cron (#4 em lote). Nesses
três, o custo é disparado sem ação do usuário e sem rate limit por tenant.

## 3. Ledger atual: `registro_uso_ia`

Colunas: `tenant_id, agente, tokens_entrada, tokens_saida, latencia_ms,
model, entidade_tipo, entidade_id, criado_em`.

Comparado ao Usage Event do §54, **faltam**: `user_id`, `module`,
`feature`, `workflow`, `provider`, `cached_tokens`, `embedding_tokens`,
`tool_calls`, `external_api_cost`, `compute_cost`, `total_cost` e
`credits_consumed`. A escolha de não gravar custo foi deliberada
(docstring: tabela de preço desatualizaria em silêncio) e é compatível
com o §55, desde que a Fase 5 introduza uma tabela de preço versionada.

A gravação é best-effort (`try/except` + rollback). Uma falha de
persistência não derruba a resposta. Isso **conflita com "nenhuma
chamada não contabilizada"** e precisa ser revisto na Fase 5.

## 4. Human-in-the-loop (§17, §81)

Implementado e testado:

- `Mensagem.status`: `rascunho | aguardando_aprovacao | aprovado | enviado | falhou | cancelado`.
- `Aprovacao.status`: `pendente | aprovado | editado | rejeitado`.
- `envio_service.processar_pendentes` só seleciona `status in ("aprovado","falhou")`.
  Uma mensagem não aprovada é estruturalmente invisível ao disparador.
- A auto-aprovação existe só por `RegraAutoAprovacao`, restrita ao flag
  de plano `permite_auto_aprovacao`, e é auditada.
- LinkedIn nunca é auto-enviado.
- Comparado aos estados do §17, faltam `AI_GENERATED`, `SCHEDULED`,
  `DELIVERED` e `EDITED` como estados de `Mensagem`. Hoje a informação
  equivalente está espalhada entre `Aprovacao`, `AuditLog` e colunas
  `enviado_em/aberto_em/bounce_em`.

## 5. Contexto, memória, aprendizado

- Não há Context Engine, Corporate Brain, RAG, embeddings nem memória
  persistente de conversa. Cada call site monta o próprio prompt com
  dados do tenant, já filtrados por `tenant_id`.
- "Aprendizado" existente: `RegraAprendida` (regras escritas por
  humano, injetadas no prompt de cadência) e
  `metricas_service.calcular_padroes_observados` (correlação com
  amostra mínima). É o embrião do Learning Loop do §18.
- Isolamento entre tenants na IA: testado para o Agente Corporativo em
  `tests/integration/test_isolamento_ia_critico.py` (segredo de tenant
  terceiro não aparece). Não há teste genérico para os outros call sites.

## 6. Prompt injection (§62)

Não há convenção de delimitação entre dado e instrução. Exposição por
call site:

- **Alta**: #4 (HTML de site de terceiro vai direto no prompt), #7
  (texto livre de lead desconhecido via WhatsApp/e-mail), #8
  (transcrição de reunião).
- Mitigação existente no #7: contrato de saída com 3 prefixos, em que
  prefixo desconhecido vira transferência para humano, e a resposta de
  FAQ usa só texto curado, nunca texto gerado.

## 7. Implicações para as fases seguintes

- **Fase 4 (AI Gateway)**: o ponto de saída único já existe (`LLMProvider`).
  O trabalho principal é enriquecer `LLMRequest` com contexto (tenant,
  user, module, feature, agent, model class) e tornar `gerar_e_registrar`
  o único caminho (com os 11 call sites migrados).
- **Fase 5 (FinOps)**: o ledger precisa deixar de ser best-effort e
  virar transacional (ou outbox), e ganhar custo por tabela versionada.
