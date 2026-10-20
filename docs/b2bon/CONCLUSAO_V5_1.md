# Conclusão do Prompt V5.1 — tratamento das cinco pendências (2026-10-20)

Estados usados: **Concluído e validado** · **Implementado, mas não validado em ambiente real** · **Parcial** · **Bloqueado externamente** · **Pendente**.
Nada abaixo foi publicado: as mudanças estão no repositório local; nenhuma migração foi aplicada em staging ou produção.

## Estado inicial confirmado

`git status` limpo na `feat/super-admin-acesso-total-modulos` (= `staging` em `93c8c87`). As cinco pendências eram reais: só a Anthropic integrada; PNCP sem rotina
agendada; `pip-audit`/`npm audit` nunca executados; backend sem `ruff` nem gate no CI; enriquecimento de site sem confirmação de domínio, sem indicadores
financeiros e sem tela de histórico.

## Resumo por pendência

| # | Pendência | Estado final |
|---|---|---|
| 1 | Provedores adicionais de IA | **Implementado, mas não validado em ambiente real** (adapters + fallback testados com respostas simuladas; ativação **bloqueada externamente**: credenciais, aprovação de privacidade, decisão de custo) |
| 2 | Coleta e monitoramento do PNCP | **Implementado e validado contra o serviço real em leitura** (adapter); a **ativação agendada em produção está pendente de validação externa** (`PNCP_HABILITADO`, merge no `master`, configuração do tenant) |
| 3 | Auditoria de dependências | **Concluído e validado** (com o limite: backend sem lock file) |
| 4 | Lint do backend e CI | **Concluído e validado localmente**; a execução no GitHub Actions só ocorre no próximo push (**Implementado, mas não validado em ambiente real** quanto ao CI) |
| 5 | Enriquecimento de site | **Concluído e validado** nos requisitos de domínio, histórico, isolamento e independência de IA; **Parcial** em indicadores financeiros (só páginas HTML; PDFs de RI não são lidos) |

## 1. Provedores adicionais de IA

- **Arquivos**: `app/llm/provedores.py` (adapters), `app/llm/fallback.py` (registro, regras, fallback), `app/llm/base.py` (`LLMFalhaDeProvedor`), `app/core/config.py`
  (variáveis), `app/api/deps.py` (`get_llm_provider`), `app/api/v1/admin_provedores_ia.py`, `docs/b2bon/PROVEDORES_IA.md`.
- **Implementação**: porta única preservada; Anthropic intocada e padrão. Adapters para Cloudflare Workers AI, Groq, OpenRouter e Gemini (chave só em cabeçalho,
  modelo do request nunca vaza para outro fornecedor). Fallback só em falha **do provedor**, com disjuntor por provedor, teto diário (ledger) e quatro travas
  (lista, credencial+modelo, aprovação de privacidade, custo). Sem configuração, `get_llm_provider` devolve o `ClaudeProvider` puro. `GET /admin/provedores-ia` mostra
  estado e bloqueios sem vazar credencial.
- **Pesquisa oficial (20/10/2026)**: limites, retenção e cobrança de cada provedor estão em `PROVEDORES_IA.md` com a ressalva do que a documentação **não** diz
  (ex.: Groq/Gemini não afirmam se exceder o gratuito cobra). Destaque: **Gemini gratuito usa os dados para melhorar produtos e há revisão humana — não aprovar para dados reais.**
- **Testes**: `tests/unit/test_provedores_ia.py` (75): contrato de cada adapter, 12 modos de falha × 4 adapters, vazio/cortado, fallback (ordem, erro de conteúdo não troca,
  todos falhando, teto diário, disjuntor), travas de habilitação, nada chamado sem configuração, endpoint de status, ledger registra o provedor do fallback.
- **Evidências**: ver testes; `construir_provedor` sem variáveis → `ClaudeProvider`; zero requisições nos testes de “configurado mas bloqueado”.
- **Riscos**: o plano `gratuito` é declaração do operador (não verificável); formato `messages`/`usage` do Workers AI sem confirmação real; fallback envia o mesmo prompt (com dados do cliente).
- **Ativação**: credenciais; avaliação LGPD e `*_APROVADO_DADOS_REAIS=true`; modelo explícito; teste real com dados fictícios; só então atualizar a coluna “teste real”.

| Provedor | Adapter | Teste simulado | Teste real | Habilitado | Aprovado dados reais |
|---|---|---|---|---|---|
| Anthropic | sim | sim | sim (produção) | sim | sim |
| Cloudflare Workers AI / Groq / OpenRouter / Gemini | sim | sim | **não** | **não** | **não** |

## 2. Coleta agendada do PNCP

- **Achado real**: o adapter tratava `codigoModalidadeContratacao` como opcional; o serviço real devolve **400** sem ele (e recusa `tamanhoPagina=100`). Corrigido e
  validado com uma consulta real de leitura (50 itens normalizados).
- **Arquivos**: `app/contexts/bids/fontes/pncp.py`, `app/contexts/bids/coleta.py`, `app/models/coleta_fonte.py`, migração `a7d9f1b3c5e7`, `app/api/v1/bids.py`
  (config/saúde/execuções/executar), `app/api/v1/cron.py` (`/cron/coletar-licitacoes`), `.github/workflows/cron-envios.yml` (job a cada 6 h), `docs/b2bon/COLETA_PNCP.md`.
- **Implementação**: rotina idempotente com cursor, janela de no máx. 7 dias, execução única (índice parcial), execução esquecida encerrada em 30 min, pausa entre páginas,
  retentativa 1 s/2 s com `Retry-After`, teto de páginas e de novas, filtro obrigatório (UF/palavras-chave), rodada compartilhada entre tenants; registro de início, conclusão,
  duração, consultados/inseridos/atualizados/ignorados, tentativas, erro, estado e cursor; saúde (`desabilitada/nunca_executada/saudavel/atrasada/falhando`) e logs
  `COLETA_FONTE_FALHANDO`/`COLETA_FONTE_ATRASADA` (+ Sentry). Sem IA.
- **Testes**: `tests/unit/test_pncp_adapter.py` (retentativa, 429, 400, JSON inválido, 204, paginação) e `tests/integration/test_coleta_pncp.py` (configuração, idempotência,
  recuperação sem duplicar, falha no meio, janela, teto parcial, concorrência, saúde, alerta no log, cron, isolamento por tenant, permissões).
- **Riscos**: coleta por tenant (sem corpus comum); sem histórico de retificações; sem anexos; limite de requisições do portal não publicado.
- **Ativação**: merge no `master` (o cron só existe na branch padrão), `PNCP_HABILITADO=true`, `CRON_SECRET` (já existe), configuração do tenant, migração.

## 3. Auditoria de dependências

Detalhe em `AUDITORIA_DEPENDENCIAS.md`. `pip-audit`: 0 em 58 pacotes. `npm audit`: 2 altas transitivas só de build (`brace-expansion`, `source-map-js`) corrigidas com
`npm audit fix` (sem `--force`), build e lint iguais → 0. Workflow semanal `auditoria-dependencias.yml` (não bloqueia PRs). **Limite**: backend sem lock file.

## 4. Lint e CI

- **Arquivos**: `pyproject.toml` (`[tool.ruff]`, `ruff` em `dev`), `.github/workflows/ci.yml` (`ruff check .` antes do `pytest`), `README.md` (como rodar/interpretar).
- **Implementação**: stack confirmado (Python/FastAPI). Regras de bug/risco: `E4,E7,E9,F,B,PLE,ASYNC` + chamadas perigosas do bandit; `B008` (Depends do FastAPI) e `E741`
  ignoradas com motivo; `B011` só nos testes. Diagnóstico inicial: 112 achados (51 `B011` em testes + 17 `E741` já fora das regras) → 44 relevantes: 17 imports mortos (autofix seguro),
  `B023` (5 falsos positivos documentados com `noqa` e motivo), `F841` (9 variáveis sem uso em testes), `F821` (nome indefinido num teste), `B905`, `B007`, `B017`, `E702`, `B033`, e reexportações
  (`orquestrador`, `ConexaoLinkedin`) declaradas em `__all__`. **Nenhuma regra relevante foi desligada para passar.** Sem reformatação em massa.
- **Evidência**: `ruff check .` → “All checks passed!”; suíte completa sem regressão (abaixo).

## 5. Enriquecimento de site

- **Arquivos**: `app/contexts/predator/inteligencia_site.py` (regras determinísticas), `app/contexts/predator/prospeccao.py` (`enriquecer`), `app/integrations/site_fetcher.py`
  (HTML → texto visível), `app/models/coleta_site.py`, migração `b8e0a2c4d6f8`, `app/services/coleta_site_service.py`, `app/api/v1/coletas_site.py`,
  `frontend/src/pages/coletas-site/HistoricoColetas.tsx` (rota `/historico-coletas`, item de menu e atalho na ficha da conta).
- **Domínio**: evidências = CNPJ exibido no site (exato ou mesma raiz), e-mail do cadastro público no mesmo domínio, CEP, logradouro + número, telefone; nome só como indício
  fraco. Estados `confirmado` / `provável` / `inconclusivo` / `divergente` / `confirmado manualmente`; limitações registradas (CNPJ ausente, cadastro indisponível…).
  Divergente (site exibe **outro** CNPJ sem outra prova) **não gera indicadores, resumo nem chamada à IA** e não grava o domínio descoberto. Confirmação manual vale para as próximas coletas.
- **Indicadores**: receita líquida/bruta, lucro líquido, EBITDA, dívida líquida — só com moeda explícita ao lado do rótulo; valor normalizado + como estava escrito, escala, moeda,
  período mais próximo (trimestre/semestre/ano), trecho, URL, método e confiança; **margem líquida derivada** só da mesma página, período e moeda, com fórmula e origens. Ausência = “não
  encontrado”, com texto que explica que não é resultado negativo; empresa sem dados é exibida assim.
- **Histórico**: cada execução vira uma linha (estado, domínio, páginas, fontes, avisos, erro, resumo); reprocessar cria **nova** linha ligada à original; falhas também ficam registradas;
  tela com lista, detalhe, evidências, indicadores com fonte e páginas lidas; tudo isolado por tenant.
- **Independência de IA e segurança**: coleta, verificação, extração e gravação ocorrem antes da IA; IA fora do ar → `concluida_sem_ia`. Controles SSRF/DNS/limites preservados (testes) e conteúdo do site continua delimitado/neutralizado no prompt.
- **Achado extra (não alterado)**: `tenant_service.criar_tenant_vitrine` chama `enriquecer`/`mapear_decisores` **sem `plan_limits`**; o `TypeError` é engolido por `except Exception`, então o enriquecimento “best-effort”
  do fluxo de convite de Rede Social nunca roda. Corrigir ligaria um consumo de IA hoje inexistente: decisão do PO.
- **Testes**: `test_inteligencia_site.py` (25: domínio e indicadores, sem rede/IA), `test_coletas_site.py` (18: fluxo completo, histórico, reprocesso, isolamento, IA fora, SSRF, conteúdo malicioso), regressão dos existentes.
  Verificação visual da tela (Playwright, banco descartável) com os três blocos renderizados.
- **Riscos**: PDFs de relações com investidores não são lidos; extração por regra cobre frases comuns, não demonstrações tabulares; o conteúdo exibido de cada página é o da última coleta; cadastro público (BrasilAPI) é de terceiro e pode falhar.
- **Ativação**: aplicar as migrações `e5b7d9f1a3c5`, `f6c8e0a2b4d6`, `a7d9f1b3c5e7`, `b8e0a2c4d6f8` (todas aditivas) junto do deploy.

## Validação final

| Verificação | Resultado |
|---|---|
| `ruff check .` | All checks passed |
| `pytest` unitários (`tests/unit`) | **1209 passaram**, 0 falhas |
| `pytest` integração e demais (`tests`, sem `unit` e sem `desempenho`) | **1383 passaram**, 12 ignorados, 0 falhas (inclui `test_alembic_upgrade.py`: cadeia até `b8e0a2c4d6f8` em SQLite) |
| Suíte em PostgreSQL / `alembic upgrade head` em PG limpo | **não executado localmente** (sem PG); roda no job `postgres-migrations` do CI |
| Frontend: `tsc --noEmit`, `npm run build`, `npm run lint` | sem erros de tipo; build OK; lint com os mesmos 25 avisos preexistentes |
| `npm audit` / `pip-audit .` | 0 / 0 vulnerabilidades |
| E2E Playwright | **não executado** (roda no CI); a tela nova foi verificada com Playwright local contra banco descartável |
| Isolamento entre tenants | testes negativos novos: coleta PNCP (config/saúde/execuções), histórico de coletas (lista, detalhe, reprocesso, confirmação), `/admin/provedores-ia` |
| Indisponibilidade de IA | `test_nucleo_sem_ia.py`, disjuntor, `concluida_sem_ia`, fila com retentativa |
| Falha e recuperação do PNCP | `test_coleta_pncp.py` (falha, falha no meio, retomada sem duplicar, execução esquecida, falhando/atrasada) |
| Enriquecimento: domínio confirmado, ambíguo/divergente, ausência de dados financeiros | `test_coletas_site.py` e `test_inteligencia_site.py` |
| Validação contra serviço real | PNCP: consulta de leitura (adapter corrigido). Provedores de IA: **nenhuma** (sem credenciais) |

## Ações para ativação em produção (todas dependem de autorização)

1. Commit/push e deploy (inclui 4 migrações aditivas já listadas). 2. `PNCP_HABILITADO=true` e configuração do tenant. 3. Credenciais, avaliação LGPD e decisão de custo para qualquer provedor adicional.
4. Decisão sobre o lock de dependências do backend e sobre o bug do fluxo de convite. 5. Executar o E2E (Playwright) no CI e validar as migrações em PostgreSQL (job existente).
