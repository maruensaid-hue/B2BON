# Auditoria do estado real — Master Prompt V5.0 (Fase 00)

Data: 2026-10-20 · Branch: `feat/super-admin-acesso-total-modulos` · Base: `master` = `staging` = `46643b5`.
Método: leitura do código e do histórico, execução da suíte e testes novos escritos para cada correção. Onde um item **não foi
reauditado nesta rodada**, está escrito assim; nada foi marcado como concluído sem teste ou leitura de código.

## 1. Estado atual

- **Stack**: FastAPI + SQLAlchemy + Alembic (head `d2e4f6a8b0c2` em produção; `e5b7d9f1a3c5` e `f6c8e0a2b4d6` criadas aqui, **não aplicadas em produção**), PostgreSQL
  (Neon) / SQLite em testes, React + Vite, Cloudflare Worker (proxy `/api`), Render (API Free + Static Site), Sentry, SendGrid, Redis
  (rate limit). 555 commits. Suíte após as correções desta rodada: **1.091 unitários + 1.340 de integração passando (12 ignorados)**, 0 falhas; E2E Playwright (19) roda no CI e **não foi executado aqui**.
- **CI** (`.github/workflows/ci.yml`): pytest completo, `alembic upgrade head` em PostgreSQL limpo, lint+build do frontend, E2E.
  **Não há lint nem checagem de tipos do backend no CI** (não existe configuração de `ruff` no repositório).
- **Autoria**: o histórico tem três autores Git (`Claude` 75, `Maruen Said` 279, `maruensaid-hue` 201, mesmo e-mail do dono). **Não há
  evidência técnica de commits do Codex** (nenhuma branch, mensagem ou arquivo o identifica); não atribuo autoria a ele. O estado do
  projeto está documentado em `PROJECT_STATE.md`, `DECISIONS.md` (D-001…D-088) e `phases/*`, e foi **conferido contra o código** abaixo.
- **O que já existia e foi preservado**: gateway único de IA com orçamento, AI Credits, ledger, cache e cost guard; defesa de prompt
  injection (`prompt_seguro`); outbox de eventos; webhooks de saída com HMAC e retentativa; multi-tenancy por `tenant_id` derivado do
  token; RBAC; LGPD (titular, ROPA, opt-out, retenção).

## 2. Achados (priorizados) e situação

| # | Sev. | Achado (evidência) | Situação |
|---|---|---|---|
| F1 | Alta | **Webhooks de saída do tenant sem proteção SSRF**: `webhooks._validar_url` só checava o esquema e `_enviar_httpx` conectava em qualquer host. Um tenant podia apontar para `localhost`, rede interna ou metadata de nuvem. | **Corrigido** (`app/core/ssrf.py`; cadastro recusa destino interno, envio valida o IP e conecta nele). Testes: `test_ssrf.py`, `test_webhooks_saida_e_hub.py`. |
| F2 | Alta | **Webhook de parceiro (Distribuidor) idem**: `webhook_parceiro_service` fazia `httpx.post(url_callback)` sem checar o destino. | **Corrigido** (mesmo núcleo; cadastro em `PUT /integracoes/webhook` recusa interno). |
| F3 | Média-alta | **Crawler do site** (`site_fetcher`): (a) validava o DNS e deixava o `httpx` resolver de novo → **DNS rebinding**; (b) corpo inteiro em memória, sem teto (resposta gigante / compressão abusiva); (c) CGNAT `100.64/10` não era bloqueado; (d) qualquer porta. | **Corrigido**: conexão no IP validado (Host/SNI originais), corpo cortado em 500 KB já descompactado, `is_global`, só portas 80/443, cada redirecionamento revalidado. Teste de servidor real em loopback prova o corte e o Host. |
| F4 | Alta | **A coleta do site era descartada se a IA falhasse** (`enriquecer` só gravava depois de `intel.gerar`). Violava “a coleta deve funcionar sem IA”. | **Corrigido**: domínio descoberto, páginas pesquisadas (URL, fonte, data) e a marca `analise_ia=pendente` são gravados antes de a IA ser exigida. |
| F5 | Média | **Fila de enriquecimento**: IA fora do ar marcava a conta `falhou` em definitivo (sem retentativa). | **Corrigido**: volta para a fila com espera 15/30/60/120 min, máx. 5 tentativas, depois `falhou` com o motivo. Migração `e5b7d9f1a3c5` (colunas `tentativas`, `proxima_tentativa_em`). |
| F6 | Média | **Gateway sem circuit breaker**: provedor fora do ar custava ~25 s por chamada e reservava crédito a cada tentativa. | **Corrigido**: disjuntor (5 falhas seguidas do provedor → 60 s de pausa, uma chamada de teste, reabre se falhar); reserva de créditos liberada; resposta vazia/cortada **não** conta como provedor fora do ar. Configurável (`AI_DISJUNTOR_*`, 0 desliga). |
| F7 | Média | Um único provedor de IA (Anthropic). | **Arquitetura entregue na V5.1 (2026-10-20)**: adapters Cloudflare Workers AI, Groq, OpenRouter e Gemini + fallback controlado, **todos desligados e sem teste real** (sem credenciais/aprovação). Ver `PROVEDORES_IA.md`. Ativação: bloqueada externamente. |
| F8 | Média | **RAG sem vetores**: busca por palavras-chave (`texto.py`), sem pgvector. | **Pendente**: avaliar pgvector no Neon antes de qualquer banco vetorial; só se houver necessidade comprovada. |
| F9 | Média | Coleta PNCP sem rotina agendada e com o adapter fora do contrato real (modalidade obrigatória). | **Corrigido na V5.1**: adapter alinhado ao serviço real (validado por consulta de leitura), coleta agendada a cada 6 h com cursor, idempotência, execução única, saúde e alertas. Ativação real pendente (`PNCP_HABILITADO`, configuração do tenant). Ver `COLETA_PNCP.md`. |
| F10 | Baixa | Lint do backend sem configuração/gate. | **Corrigido na V5.1**: `[tool.ruff]` no `pyproject.toml` (regras de bug/risco), 44 achados tratados, passo `ruff check .` no job `backend` do CI. |
| F11 | Info | `pip-audit`/`npm audit` não executados. | **Executados na V5.1**: Python 0 vulnerabilidades (58 pacotes); Node 2 altas de build corrigidas (`npm audit fix`, sem `--force`) → 0. Sem lock no backend (limite registrado). Ver `AUDITORIA_DEPENDENCIAS.md`. |
| F12 | Baixa | RSS de portais (`central_negocios_client`) usa `follow_redirects=True`, mas as URLs são fixas no código (sem entrada de usuário). | **Registrado**, risco baixo. |
| F13 | Baixa | O limite semanal de enriquecimento (`verificar_e_registrar`) conta cada tentativa, inclusive as retentativas por IA fora do ar. | **Registrado**. |
| F14 | Decisão | O conteúdo das páginas coletadas não era persistido (só URLs/data/fonte). | **Corrigido por decisão do PO (2026-10-20)**: tabela `conteudo_pagina_site` (migração `f6c8e0a2b4d6`), uma linha por conta+URL (a coleta nova substitui a anterior, ≈2.500 caracteres × no máx. 8 páginas), apagada junto com a conta e na exclusão do tenant. Ainda **não há** rotina que reanalise a partir do conteúdo guardado (hoje a retentativa coleta de novo). |

## 3. Matriz de requisitos

Legenda: ✅ concluído e validado · 🟡 parcial · 🔴 pendente · ⛔ bloqueado externamente · ➖ não reauditado nesta rodada (vale o que consta nos relatórios de fase).

| Requisito (prompt) | Estado | Evidência / lacuna |
|---|---|---|
| §5 Núcleo independente de IA | ✅ | `test_nucleo_sem_ia.py`: com o provedor falhando, CRM, funil, economia, métrica-norte e atividade respondem sem tocar a IA; função de IA devolve 409 claro, sem detalhe interno. |
| §5.2 Fila persistida de tarefas de IA | 🟡 | Enriquecimento em lote: sim (F5). Demais usos de IA são síncronos e devolvem erro claro; não há fila genérica de “tarefas de IA”. |
| §6 Gateway de IA | 🟡 | Orçamento, créditos, ledger, cache, cost guard, caminho único (teste `gateway_ia_unico_caminho`) ✅; disjuntor ✅ (F6); múltiplos provedores/fallback 🔴 (F7); backoff entre tentativas dentro de uma chamada: não há (a retentativa é da fila). |
| §7 Filas e recuperação | 🟡 | Outbox de eventos e webhooks com backoff ✅ ➖; fila de enriquecimento ✅ (F5); fila `envio_crm` ➖. Sem DLQ administrativa para a fila de enriquecimento (estado `falhou`, reenfileirável). |
| §8.1 Banco / migrações | ✅ | Cadeia Alembic validada em PostgreSQL limpo no CI; `DISASTER_RECOVERY.md`; migração nova é aditiva (2 colunas, `server_default`). |
| §8.2 Isolamento entre tenants | 🟡 ➖ | 91 arquivos de teste citam isolamento; `tenant_id` vem do token. Não reauditei rota por rota. |
| §8.3 RAG / busca semântica | 🟡 | Palavra-chave com filtro de tenant ➖; sem vetores (F8). |
| §9 CRM e KPIs | ✅ ➖ | Funcionam sem IA (teste novo); fórmulas de CAC/LTV/churn documentadas em `REVENUE_INTELLIGENCE_METRICS.md`. |
| §9.3 Integrações Salesforce/HubSpot/Pipedrive/RD | ⛔ | Escrita implementada, **BETA e desligada** (TD-069): falta validar em sandbox real. |
| §10 Website Intelligence | 🟡 | Ver tabela 4. |
| §11 PREDATOR | ✅ ➖ | Aprovação humana antes de envio; opt-out; limites; cadências travam ICP/Oferta. |
| §12 MAP | ✅ ➖ | `MAP_CURRENT_STATE.md`, `phases/MAP_PERFORMANCE_COMPLETION.md`. |
| §13 SHOAL | ✅ ➖ | Fases 1–7 do roteiro anterior. |
| §14 Licitações | 🟡 | PNCP + ingestão idempotente ✅; sem cron de coleta/alerta/saúde (F9). IA só como camada de análise. |
| §15 Strategic Sourcing | ✅ ➖ | S0–S4 e plano A–I concluídos; acesso por papel reforçado hoje (D-088). |
| §16 Document Intelligence | 🟡 ➖ | Cofre e extração de texto de PDF (`pypdf`) existem; validação de upload, versionamento e permissões por documento **não reauditados**; não há OCR. |
| §17 Assistente corporativo | ✅ ➖ | Limites por tenant, prompt seguro, fontes. |
| §18 Créditos e planos | ✅ ➖ | `AI_CREDITS_OPERACAO.md`; preços pendentes do PO continuam pendentes (OI-017/OI-022). |
| §19 Custos de infraestrutura | 🟡 ➖ | D-077 (preços públicos); sem proposta de migração de custo nesta rodada. |
| §20 LGPD | 🟡 | Mecanismos existem (titular, ROPA, retenção). **Não declaro conformidade integral**; exige avaliação jurídica. |

## 4. Corporate Website Intelligence — critérios de aceite (§10.7)

| # | Critério | Estado |
|---|---|---|
| 1 | Identificar/confirmar o site oficial | ✅ (V5.1) confirmação por evidências (CNPJ exibido, e-mail do cadastro público, CEP/endereço, telefone); nome parecido nunca confirma; estados confirmado/provável/inconclusivo/divergente e validação manual |
| 2 | Coleta sem inferência de IA | ✅ (teste `test_ia_fora_do_ar_nao_perde_a_coleta_do_site`) |
| 3 | Dados persistidos e rastreáveis | ✅ URL, fonte, data e conteúdo de cada página gravados (teste com e sem IA) |
| 4 | Páginas relevantes identificadas | ✅ 22 caminhos candidatos + links da home por palavra-chave (máx. 8 páginas) |
| 5 | Fontes e datas apresentadas | ✅ (V5.1) tela `Histórico de Coletas` mostra páginas, datas, evidências e indicadores com URL |
| 6 | Ausência não vira invenção | 🟡 instrução no prompt + delimitação; sem verificação automática da resposta |
| 7 | Análise posterior por IA | ✅ (V5.1) fila com retentativa e botão de reprocesso que gera nova coleta ligada à anterior |
| 8 | Indisponibilidade de IA não impede a coleta | ✅ |
| 9 | Resultado no CRM e envio ao PREDATOR | 🟡 ficha da conta ✅; alimentação do contexto do PREDATOR não verificada |
| 10 | Testes de SSRF, redirecionamento, DNS, limites | ✅ `test_ssrf.py` (rebinding, redirect interno, laço, porta, esquema, corpo gigante, gzip) |
| 11 | Conteúdo malicioso não altera instruções | ✅ delimitador neutralizado + instrução de sistema (`test_enriquecer_delimita_conteudo_externo_no_prompt`); defesa estrutural: nenhuma ferramenta privilegiada é acionada pela análise |
| 12 | Isolamento entre tenants | ✅ `obter_conta` filtra por `tenant_id` |
| — | Relatórios financeiros públicos com indicador/período/URL (§10.3) | 🟡 (V5.1) extração determinística de receita, lucro, EBITDA e dívida em páginas HTML com valor, moeda, escala, período, trecho e URL; margem derivada com fórmula; **PDFs de RI não são lidos** |
| — | Histórico de coletas e reprocesso por botão (§10.6) | ✅ (V5.1) `coleta_site_conta` persistida, tela e reprocesso, isolados por tenant |

## 5. Plano derivado das evidências

1. (feito) Segurança: SSRF compartilhado, webhooks, crawler. 2. (feito) Núcleo sem IA: coleta persistida, fila com retentativa,
disjuntor. 3. **Sua decisão**: provedores adicionais de IA (F7). Reanálise a partir do conteúdo guardado (F14). 4. Rotina de coleta PNCP
com saúde da fonte e alerta (F9). 5. Lint/tipos do backend no CI e auditoria de dependências (F10, F11). 6. Website Intelligence:
confirmação do domínio por CNPJ/endereço, indicadores financeiros estruturados, tela de histórico. 7. Reauditar isolamento de
tenant rota por rota com teste negativo automático.

## 6. Autorizações necessárias antes de implantar

- Aplicar as migrações `e5b7d9f1a3c5` e `f6c8e0a2b4d6` em produção (aditivas, não destrutivas) — vão junto do deploy.
- Qualquer provedor de IA novo (credenciais, custo, privacidade).

## 7. Atualização V5.1 (2026-10-20)

As cinco pendências desta auditoria foram tratadas; o resultado item a item (estado, evidências, riscos e ativação) está em `CONCLUSAO_V5_1.md`.
