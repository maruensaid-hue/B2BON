# Conclusão do Master Prompt V5.2 (2026-10-20)

Estados usados: **Concluído e validado** · **Implementado, aguardando validação externa** · **Parcial** · **Bloqueado externamente** · **Não feito (decisão)**.
Nada foi publicado: sem push, sem merge, sem deploy, sem migração em ambiente compartilhado, sem serviço pago, sem chamada real de IA. Produção continua em `46643b5`.

## A. Estado inicial

Branch `feat/super-admin-acesso-total-modulos` = `origin/staging` em `8254949` (V5.1 + correção do fluxo de convite). Migração head local `d2e4f6a8b0c2`; produção ainda anterior a ela.
Baseline de testes: unit 1214, integração 1413. Havia alterações locais não commitadas de outro trabalho (o `git status` mostrava arquivos modificados); foram preservadas e incorporadas, nada foi descartado.
`.claude/settings.backup.json` é arquivo local e **não** entra em commit.

## B. Trabalho realizado

Cada falha abaixo foi **provada por teste antes** de ser corrigida.

| # | Achado | Correção | Estado |
|---|---|---|---|
| 1 | Excluir conta com histórico de coleta/indicadores violava FK (erro 500) | `conta_service._apagar_dados_do_site` (indicadores → coletas → conteúdo) na exclusão individual e em lote | Concluído e validado |
| 2 | `conteudo_pagina_site`: sem teto no backend, sobrescrita cega, corrida entre coletas | Máx. 8 páginas/conta, 8.000 caracteres/página, upsert que só troca por conteúdo mais novo, poda das excedentes, tolerância a `IntegrityError` | Concluído e validado |
| 3 | Crawler aceitava qualquer tipo de conteúdo | Allowlist de MIME (HTML/texto), `ConteudoNaoSuportado`; testes de formas hostis de IP (SSRF) | Concluído e validado |
| 4 | PNCP só enxergava edital **novo** | Consulta por `/contratacoes/atualizacao`; `situacao_externa` e `atualizado_externo_em`; contador `alterados_na_fonte`; selo na tela; **status interno não muda sozinho** | Concluído e validado (simulado); ativação real pendente |
| 5 | Churn do MAP passava de 100% (cancelados do mês ÷ base inicial, incluindo quem entrou e saiu no mês); ROI com LTV 0 virava "sem dado"; `periodo` inválido dava 500 | Churn por coorte, `calcular_roi` com `is None`, `Query(pattern=...)` → 422; fórmulas documentadas | Concluído e validado |
| 6 | Históricos cresciam sem limite | `retencao_historicos_service` + `POST /cron/podar-historicos` + passo diário no workflow (180 d coletas de site, 90 d execuções, cache de IA vencido) preservando cursor, última coleta boa e confirmadas manualmente | Concluído e validado |
| 7 | Migrações V5.x nunca testadas sobre dados anteriores | `tests/test_migracoes_v5.py` (SQLite validado) + passo novo no CI para PostgreSQL | SQLite validado; **PostgreSQL só no CI** |
| 8 | "Sem aprovação não envia" estava garantido no código, mas sem teste | `tests/integration/test_envio_exige_aprovacao.py` (5 casos, incluindo defesa em profundidade) | Concluído e validado |
| 9 | **Regressão minha, achada pela suíte**: `licitacoes.como_dict` passou a ler campos que o espelho unificado (`espelho.py`) não carregava → `AttributeError` na leitura unificada | Campos incluídos em `metadados` (`processo`) e lidos de volta em `licitacao_de`; teste de ida e volta | Concluído e validado |

Decisão registrada: **D-092** em `DECISIONS.md`. Documentação atualizada: `REVENUE_INTELLIGENCE_METRICS.md` (fórmulas de economia; corrige a afirmação anterior de que o churn era sempre coerente), `COLETA_PNCP.md` (endpoint de atualização, retificações, teto de 100 páginas, retenção).

### Auditoria de `conteudo_pagina_site` (checklist de 13 itens do §3)

Unicidade por tenant/conta/URL, concorrência, limite de 8 páginas, limites de caracteres, páginas vazias/duplicadas, exclusão em todos os locais e funcionamento sem IA: **cobertos por teste** (`test_conteudo_paginas_site.py`, `test_exclusao_dados_do_site.py`).
Migração em estrutura anterior: **SQLite validado; PostgreSQL limpo ainda não executado localmente** (sem servidor PG no ambiente; roda no CI). Downgrade: remove as colunas novas e perde apenas esses metadados.

## C. Validação por comando (execução real, 2026-10-20)

| Comando | Resultado |
|---|---|
| `python -m pytest -q tests/unit` | **1277 passaram** (baseline 1214) |
| `python -m pytest -q tests/integration tests/test_migracoes_v5.py tests/test_alembic_upgrade.py tests/test_health.py tests/test_lock_sincronizado.py` | **1440 passaram, 15 skipped** (baseline 1413) |
| `python -m ruff check .` | All checks passed |
| `npx tsc --noEmit` / `npm run build` | sem erros; build e PWA gerados |
| `npm run lint` (oxlint) | só avisos antigos de `exhaustive-deps`, nenhum em arquivo alterado |

Não executado: `tests/desempenho` (importa o módulo `resource`, exclusivo de POSIX; falha de coleta no Windows, roda no CI Linux — arquivo não alterado); suíte E2E (Playwright); `pytest tests/test_migracoes_v5.py` contra PostgreSQL real; build da imagem Docker com o lock em Python 3.12.

## D. Matriz final

| Item do prompt | Estado |
|---|---|
| Persistência do conteúdo das páginas (§3) | Concluído e validado (PG real: aguardando CI) |
| Segurança do crawler: SSRF, MIME, tamanho (§5) | Concluído e validado |
| Dependências e lint no CI (§5) | Concluído e validado (V5.1 + passo novo de migração) |
| Histórico de coletas e retenção (§6) | Concluído e validado |
| PNCP incremental, retificações, suspensão, cancelamento (§7) | Concluído e validado (simulado); **ativação real pendente** |
| Provedores de IA adicionais (§8) | Implementado na V5.1; **bloqueado externamente** (credenciais, LGPD, custo) |
| Fórmulas do MAP (§9) | Concluído e validado |
| Aprovação humana antes do envio (§11) | Concluído e validado |
| Isolamento de tenants, rota a rota (§11) | Parcial: coberto onde há teste; reauditoria sistemática de todas as rotas **não feita** |
| Custos e infraestrutura (§10) | Parcial: sem custo novo introduzido; auditoria dedicada **não feita** |
| Alerta de oportunidades PNCP por ICP | Não feito |
| Leitura de PDFs de RI (indicadores financeiros) | Não feito |
| Corpus público comum de licitações | Não feito (decisão de arquitetura própria) |

## E. Pendências externas

1. Autorização para enviar ao staging e deixar o CI validar PostgreSQL real, o passo novo e o build Docker.
2. Ativar PNCP: `PNCP_HABILITADO=true`, configuração do tenant (UFs/palavras-chave), merge no `master`.
3. Provedores de IA: credenciais, avaliação LGPD, decisão de custo.
4. Decisões do PO já registradas: normalização de caixa do e-mail e teto de convites gratuitos.

## F. Próximos passos recomendados

1. Autorizar push para `staging` e conferir o CI.
2. Reauditoria de isolamento de tenant rota a rota (maior risco residual não coberto).
3. Decidir o corpus público comum e o alerta de novas oportunidades por ICP antes de ativar o PNCP.
