# Matriz de isolamento por rota — V5.2.1 (gerada)

Gerada por `python scripts/qualidade/inventario_rotas.py --md --cobertura=<relatorio>` a partir das rotas **efetivas** do FastAPI (inclui routers aninhados), cruzada com o resultado de `tests/integration/test_isolamento_sistematico.py`. Não editar à mão: regenerar.

- **Autenticação**: `sessao` (JWT/cookie do usuário), `chave_api` (parceiro), `nenhuma` (pública; aprovada e classificada em `tests/test_rotas_publicas_aprovadas.py`).
- **Origem do tenant**: sempre do token/chave; nenhuma rota de sessão aceita o tenant como identidade vinda do cliente. Onde o cliente envia um `tenant_id` (coluna *Tenant vindo do cliente*) ele é só **alvo** e passa por checagem de papel/hierarquia/conexão.
- **Resultado da varredura**: o atacante (admin de outro tenant, plano com todos os módulos) chamou a rota com ids reais da vítima no caminho, query e corpo. *negada (404)* = objeto real da vítima respondeu como inexistente; *executada (2xx), sem vazamento* = a rota rodou para o atacante e nenhum dado da vítima voltou nem foi alterado; *validação (422)* = o corpo automático não passou nas regras de domínio (cobertas por revisão de código e testes dirigidos, ver relatório).

| Método | Caminho | Autenticação | Papéis | Origem do tenant | Escopo de objeto | Tenant vindo do cliente | Resultado da varredura |
|---|---|---|---|---|---|---|---|
| GET | `/api/v1/admin/enriquecimento/auditoria` | sessao | super_admin | token(usuario) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/compras` | sessao | super_admin | token(usuario) | — | tenant_id | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/compras/{compra_id}/emitir-nota` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/compras/{compra_id}/estornos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/config` | sessao | super_admin | token(usuario) | — | tenant_id | negada por papel/autenticação |
| PUT | `/api/v1/admin/enriquecimento/config` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/config/{config_id}/aprovar` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/custo` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| PUT | `/api/v1/admin/enriquecimento/custo` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/custo/efetivo` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/custo/{custo_id}/aprovar` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/estornos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/estornos/{estorno_id}/decidir` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/lotes-compra` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/matriz` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/matriz/aplicar` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/orcamento-global` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| PUT | `/api/v1/admin/enriquecimento/orcamento-global` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/orcamento-global/{orcamento_id}/aprovar` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/pacotes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| PUT | `/api/v1/admin/enriquecimento/pacotes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/pacotes/rentabilidade` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/pacotes/{pacote_id}/aprovar` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/pagamentos-provedor` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/pesquisas/{pesquisa_id}/encerrar-reconciliacao` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/pesquisas/{pesquisa_id}/itens/{item_id}/reconciliar` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/planos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/poc/autorizar` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/poc/teto` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/politica` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| PUT | `/api/v1/admin/enriquecimento/politica` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/politica/{politica_id}/aprovar` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/provedores/{provedor}/conciliar` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/provedores/{provedor}/sincronizar-politica` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/provedores/{provedor}/tarifas-do-provedor` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/tenants/{tenant_id}/ajustes` | sessao | super_admin | token(usuario) | — | tenant_id | negada por papel/autenticação |
| POST | `/api/v1/admin/enriquecimento/tenants/{tenant_id}/estornos` | sessao | super_admin | token(usuario) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/admin/enriquecimento/vendas` | sessao | super_admin | token(usuario) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/admin/provedores-ia` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/admin/tenants` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/admin/tenants` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| DELETE | `/api/v1/admin/tenants/{tenant_id}` | sessao | — | token(usuario) | — | tenant_id | negada por papel/autenticação |
| POST | `/api/v1/admin/tenants/{tenant_id}/desativar` | sessao | — | token(usuario) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/admin/tenants/{tenant_id}/licenca` | sessao | — | token(usuario) | — | tenant_id | negada por papel/autenticação |
| PUT | `/api/v1/admin/tenants/{tenant_id}/licenca` | sessao | — | token(usuario) | — | tenant_id | negada por papel/autenticação |
| POST | `/api/v1/admin/tenants/{tenant_id}/reativar` | sessao | — | token(usuario) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/agente-corporativo/minhas-perguntas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/agente-corporativo/modo` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/agente-corporativo/modo` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/agente-corporativo/pendentes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/agente-corporativo/pendentes/{pergunta_id}/aprovar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/agente-corporativo/pendentes/{pergunta_id}/recusar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/agente-corporativo/perguntar` | sessao | — | token(get_tenant_id) | — | — | negada/validação (409) |
| POST | `/api/v1/agente-corporativo/testar` | sessao | — | token(get_tenant_id) | — | — | negada/validação (409) |
| GET | `/api/v1/ai-credits/alertas` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/ai-credits/carteira` | sessao | — | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/ai-credits/compras` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/ai-credits/compras` | sessao | admin, super_admin | token(usuario) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/ai-credits/compras/{compra_id}/checkout` | sessao | admin, super_admin | token(usuario) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/ai-credits/consumo` | sessao | — | token(usuario) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/ai-credits/estimativas` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/ai-credits/execucoes` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/ai-credits/extrato` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/ai-credits/lotes/{lote_id}` | sessao | admin, super_admin | token(usuario) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/ai-credits/orcamento` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/ai-credits/orcamento` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/ai-credits/pacotes` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/ai-credits/recarga-automatica` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/ai-credits/recarga-automatica` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/ai-credits/valor-de-negocio` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/ai-credits/workloads` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/aprovacoes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/aprovacoes/aprovar-lote` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/aprovacoes/excluir-lote` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/aprovacoes/mensagens/{mensagem_id}/cancelar` | sessao | — | token(get_tenant_id) | mensagem | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/aprovacoes/regras` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/aprovacoes/regras/{template_id}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/aprovacoes/{aprovacao_id}` | sessao | — | token(get_tenant_id) | aprovacao | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/aprovacoes/{aprovacao_id}/aprovar` | sessao | — | token(get_tenant_id) | aprovacao | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/aprovacoes/{aprovacao_id}/mensagem` | sessao | — | token(get_tenant_id) | aprovacao | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/aprovacoes/{aprovacao_id}/rejeitar` | sessao | — | token(get_tenant_id) | aprovacao | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/assinatura` | sessao | — | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/auditoria` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/auditoria/exportar.csv` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/auth/declarar-pagamento` | sessao | — | token(usuario) | — | — | negada/validação (409) |
| GET | `/api/v1/auth/demonstracao` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/auth/demonstracao` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/auth/dispensar-banner-boas-vindas` | sessao | — | token(usuario) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/auth/esqueci-senha` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/auth/eu` | sessao | — | token(usuario) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/auth/google` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/auth/licenca-status` | sessao | — | token(usuario) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/auth/login` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/auth/logout` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/auth/marcar-tutorial-modulo-visto` | sessao | — | token(usuario) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/auth/preferencia-tema` | sessao | — | token(usuario) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/auth/redefinir-senha` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/auth/registrar` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/auth/registrar-publico` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/auth/registrar-vitrine` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| PUT | `/api/v1/auth/whatsapp-pessoal` | sessao | — | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/bids/alertas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/bids/alertas/avaliar` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/bids/alertas/regras` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/bids/alertas/regras` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| DELETE | `/api/v1/bids/alertas/regras/{regra_id}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/bids/alertas/regras/{regra_id}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/alertas/resumo` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/bids/alertas/{alerta_id}/acompanhar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/bids/alertas/{alerta_id}/dispensar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/bids/alertas/{alerta_id}/visto` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/cofre` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/bids/cofre` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/bids/cofre/alertas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/bids/cofre/{documento_id}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/coleta/pncp/configuracao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/bids/coleta/pncp/configuracao` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/bids/coleta/pncp/execucoes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/bids/coleta/pncp/executar` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada/validação (409) |
| GET | `/api/v1/bids/coleta/pncp/saude` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/bids/concorrentes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/bids/contratos` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/bids/contratos` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/contratos/sinais` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/bids/corpus` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/bids/corpus/{corpus_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/bids/corpus/{corpus_id}/acompanhar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/bids/documentos/{documento_id}/analisar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/documentos/{documento_id}/arquivo` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/documentos/{documento_id}/estimativa` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/fontes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/bids/ingestao/pncp` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/bids/licitacoes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/bids/licitacoes` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| PATCH | `/api/v1/bids/licitacoes/{licitacao_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/bids/licitacoes/{licitacao_id}/documentos` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/licitacoes/{licitacao_id}/go-no-go` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/bids/licitacoes/{licitacao_id}/go-no-go` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/licitacoes/{licitacao_id}/matriz` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/licitacoes/{licitacao_id}/proposta` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/licitacoes/{licitacao_id}/requisitos` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/bids/licitacoes/{licitacao_id}/requisitos` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/bids/licitacoes/{licitacao_id}/resultado` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/bids/licitacoes/{licitacao_id}/status` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/licitacoes/{licitacao_id}/workspace` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bids/prazos` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PATCH | `/api/v1/bids/requisitos/{requisito_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/bids/requisitos/{requisito_id}/conformidade` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/bids/requisitos/{requisito_id}/resposta` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/bloqueios-contato` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/bloqueios-contato/{bloqueio_id}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/busca` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/cadencias` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/cadencias` | sessao | — | token(get_tenant_id) | — | — | negada/validação (409) |
| DELETE | `/api/v1/cadencias/{cadencia_id}` | sessao | — | token(get_tenant_id) | cadencia | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/cadencias/{cadencia_id}` | sessao | — | token(get_tenant_id) | cadencia | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/cadencias/{cadencia_id}` | sessao | — | token(get_tenant_id) | cadencia | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/cadencias/{cadencia_id}/ativar` | sessao | — | token(get_tenant_id) | cadencia | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/cadencias/{cadencia_id}/cancelamento-ao-responder` | sessao | — | token(get_tenant_id) | cadencia | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/cadencias/{cadencia_id}/cancelar` | sessao | — | token(get_tenant_id) | cadencia | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/cadencias/{cadencia_id}/gerar` | sessao | — | token(get_tenant_id) | cadencia | — | negada/validação (404,409) |
| GET | `/api/v1/cadencias/{cadencia_id}/teste-ab` | sessao | — | token(get_tenant_id) | cadencia | — | executada (2xx), sem vazamento |
| GET | `/api/v1/cadencias/{cadencia_id}/toques` | sessao | — | token(get_tenant_id) | cadencia | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/cadencias/{cadencia_id}/toques` | sessao | — | token(get_tenant_id) | cadencia | — | negada (404) com ids de outro tenant |
| DELETE | `/api/v1/cadencias/{cadencia_id}/toques/{toque_id}` | sessao | — | token(get_tenant_id) | cadencia | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/cadencias/{cadencia_id}/toques/{toque_id}` | sessao | — | token(get_tenant_id) | cadencia | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/cadencias/{cadencia_id}/toques/{toque_id}/template-whatsapp` | sessao | — | token(get_tenant_id) | cadencia | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/campanhas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/campanhas` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| DELETE | `/api/v1/campanhas/{campanha_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/campanhas/{campanha_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/campanhas/{campanha_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/campanhas/{campanha_id}/destinatarios/avulsos` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/campanhas/{campanha_id}/destinatarios/decisores` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| DELETE | `/api/v1/campanhas/{campanha_id}/destinatarios/{destinatario_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/campanhas/{campanha_id}/destinatarios/{destinatario_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/campanhas/{campanha_id}/destinatarios/{destinatario_id}/nao-quer-receber` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/campanhas/{campanha_id}/marcar-pronta` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/campanhas/{campanha_id}/previa` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/campanhas/{campanha_id}/voltar-para-rascunho` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/canais/{canal}/rampa` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/canais/{canal}/reativar` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/canais/{canal}/saude` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/captura-lead/config` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/captura-lead/{codigo}` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/captura-lead/{codigo}/info` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/catalogo` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/central-negocios/mercado` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/central-negocios/noticias` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/chaves-api` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/chaves-api` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/chaves-api/escopos` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/chaves-api/{chave_id}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/coletas-site` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/coletas-site/{coleta_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/coletas-site/{coleta_id}/confirmar-dominio` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/coletas-site/{coleta_id}/reprocessar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/comissoes/apuracoes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/cotacoes-cambio` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/cotacoes-cambio/sincronizar` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/comissoes/infraestrutura` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/infraestrutura/alertas/{alerta_id}/decisao` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/infraestrutura/componentes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| PATCH | `/api/v1/comissoes/infraestrutura/componentes/{componente_id}` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/infraestrutura/componentes/{componente_id}/envelopes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/infraestrutura/componentes/{componente_id}/uso` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/infraestrutura/custos-diretos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/comissoes/parametros` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/perfis-tributarios` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/politica-infraestrutura` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/politica-margem` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/recalculo` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/comissoes/status-tributario` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/comissoes/waterfall` | sessao | super_admin | token(usuario) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/comunicacao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/comunicacao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/comunicacao/amostra` | sessao | — | token(get_tenant_id) | — | — | negada/validação (409) |
| POST | `/api/v1/comunicacao/validar-texto` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/configuracao-email-api` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/configuracao-email-api` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/configuracao-email-api` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/configuracao-email-api/testar` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/configuracao-email-smtp` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/configuracao-email-smtp` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/configuracao-email-smtp/testar` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/configuracao-envio` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/configuracao-envio` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/configuracao-whatsapp` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/configuracao-whatsapp` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/configuracao-whatsapp/confirmar-aviso-template` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/contas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/contas/enriquecer-em-lote` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/contas/franquia` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/contas/limite-enriquecimento` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/contas/{conta_id}` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/contas/{conta_id}` | sessao | — | token(get_tenant_id) | conta_leitura | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/contas/{conta_id}` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/contas/{conta_id}/atividades` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/contas/{conta_id}/crm-externo` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/contas/{conta_id}/decisores` | sessao | — | token(get_tenant_id) | conta_leitura | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/decisores` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/decisores/mapear` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/contas/{conta_id}/decisores/{decisor_id}` | sessao | — | token(get_tenant_id) | conta, decisor | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/decisores/{decisor_id}/papel` | sessao | — | token(get_tenant_id) | conta, decisor | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/contas/{conta_id}/decisores/{decisor_id}/suprimir` | sessao | — | token(get_tenant_id) | conta, decisor | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/descartar` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/enriquecer` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/enriquecer-cadastro` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/enviar-crm` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/estrategia-venda` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/contas/{conta_id}/export/pdf` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/contas/{conta_id}/grafo` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/priorizar` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/contas/{conta_id}/proximo-passo` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/contas/{conta_id}/ri/documentos` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/ri/documentos` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/ri/documentos/url` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| DELETE | `/api/v1/contas/{conta_id}/ri/documentos/{documento_id}` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/contas/{conta_id}/ri/documentos/{documento_id}` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/contas/{conta_id}/ri/documentos/{documento_id}/indicadores/{indicador_id}/validar` | sessao | — | token(get_tenant_id) | conta | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/contas/{conta_id}/ri/documentos/{documento_id}/reprocessar` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/contas/{conta_id}/ri/financeiro` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/conversas/{conversa_id}` | sessao | — | token(get_tenant_id) | conversa | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/convites` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/convites` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/convites/vitrine` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/convites/vitrine` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/convites/vitrine/{codigo}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/convites/vitrine/{codigo}/info` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/convites/vitrine/{codigo}/reativar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/convites/vitrine/{codigo}/revogar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| DELETE | `/api/v1/convites/{codigo}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/convites/{codigo}/reativar` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/convites/{codigo}/revogar` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/crm/contas/{conta_id}/cancelar-cliente` | sessao | — | token(get_tenant_id) | conta_crm | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/crm/custo-aquisicao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/crm/dashboard/atividade` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/crm/dashboard/economia` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/crm/dashboard/flywheel` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/crm/dashboard/funil` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/crm/estagios` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/crm/estagios` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/crm/estagios/reordenar` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| DELETE | `/api/v1/crm/estagios/{estagio_id}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/crm/estagios/{estagio_id}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/crm/negocios` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/crm/negocios` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/crm/negocios/exportar.csv` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/crm/negocios/importar` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/crm/negocios/{negocio_id}` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/crm/negocios/{negocio_id}` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/crm/negocios/{negocio_id}/atividades` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/crm/negocios/{negocio_id}/atividades` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/crm/negocios/{negocio_id}/estagio` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/crm/negocios/{negocio_id}/meeting-brief` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/crm/negocios/{negocio_id}/propostas` | sessao | — | token(get_tenant_id) | negocio | — | executada (2xx), sem vazamento |
| POST | `/api/v1/crm/negocios/{negocio_id}/propostas` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/crm/negocios/{negocio_id}/propostas/gerar` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/crm/negocios/{negocio_id}/propostas/{proposta_id}/download` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/crm/negocios/{negocio_id}/vendedor` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/crm/vendedores-com-contas` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/cron/coletar-licitacoes` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/creditos-ia` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/disparar-relatorios-periodicos` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/disparar-webhooks-parceiros` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/enviar-lembretes-cobranca` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/expirar-registros-oportunidade` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/expirar-titulares` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/integracoes-crm` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/integracoes-crm-diario` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/podar-historicos` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/podar-recorte-cnpj` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/processar-alertas-licitacoes` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/processar-campanhas` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/processar-envios` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/processar-eventos` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/processar-fila-enriquecimento` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/processar-retorno` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/repassar-comissoes` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/sourcing-sincronizar` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/cron/suspender-licencas-vencidas` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/decisores/{decisor_id}/devolver` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/decisores/{decisor_id}/marco-entrega` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/decisores/{decisor_id}/reunioes/propor` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/email-direto` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/email-direto` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/email-direto/arquivar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/email-direto/configuracao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/email-direto/configuracao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/email-direto/pendentes-arquivamento` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/email-direto/recebidos` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/envios/processar` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/faq` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/faq` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/faq/perguntar` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/finops/alertas-margem` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/finops/catalogo` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/finops/catalogo/rascunhos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/finops/catalogo/{versao}/ativar` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/finops/economia` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/finops/economia-unitaria` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/finops/execucoes/{execucao_id}/estorno` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/finops/extrato` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/finops/margens` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/finops/matriz-rentabilidade` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/finops/meu-uso` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/finops/orcamentos` | sessao | admin, super_admin | token(usuario) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/finops/orcamentos` | sessao | admin, super_admin | token(usuario) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/finops/pacotes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/finops/pacotes/{codigo}/versoes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/finops/politica-creditos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/finops/precos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/finops/recomendacoes-peso` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/finops/reconciliacao` | sessao | super_admin | token(usuario) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/finops/relatorio-calibracao` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/finops/resumo` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/finops/tenants/{tenant_id}/creditos` | sessao | super_admin | token(usuario) | — | tenant_id | negada por papel/autenticação |
| PUT | `/api/v1/finops/tenants/{tenant_id}/excedente` | sessao | super_admin | token(usuario) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/governo/comissoes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| PATCH | `/api/v1/governo/componentes/{componente_id}/comissao` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/governo/contratos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/governo/contratos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/governo/contratos/{contrato_id}` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/governo/contratos/{contrato_id}/cancelamento` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/governo/contratos/{contrato_id}/componentes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/governo/contratos/{contrato_id}/recebimentos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/governo/contratos/{contrato_id}/recebimentos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/governo/contratos/{contrato_id}/renovacoes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/governo/contratos/{contrato_id}/transferencia-comissao` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/governo/metricas` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/governo/meu-contrato` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/governo/oportunidades` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/governo/oportunidades` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| PATCH | `/api/v1/governo/oportunidades/{oportunidade_id}` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/governo/planos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/governo/planos/{plano_id}/proposta` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/governo/politica-comissao` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/governo/politica-comissao` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/governo/recebimentos/{recebimento_id}/estorno` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/governo/template-proposta` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/governo/template-proposta` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/governo/tenants/{tenant_id}/margem-contribuicao` | sessao | super_admin | token(usuario) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/hub-integracoes/conectores` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/hub-integracoes/conexoes` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/hub-integracoes/conexoes` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| PUT | `/api/v1/hub-integracoes/conexoes/{conexao_id}/credenciais` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/hub-integracoes/conexoes/{conexao_id}/escrita` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/hub-integracoes/conexoes/{conexao_id}/escrita` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/hub-integracoes/conexoes/{conexao_id}/funis` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/hub-integracoes/conexoes/{conexao_id}/indice` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/hub-integracoes/conexoes/{conexao_id}/preparar-campos` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/hub-integracoes/conexoes/{conexao_id}/sinais-map` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/hub-integracoes/conexoes/{conexao_id}/sincronizar/{entidade}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/hub-integracoes/conexoes/{conexao_id}/status` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| DELETE | `/api/v1/hub-integracoes/conexoes/{conexao_id}/webhook-entrada` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/hub-integracoes/conexoes/{conexao_id}/webhook-entrada` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/hub-integracoes/envios` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/hub-integracoes/envios/{envio_id}/reprocessar` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/hub-integracoes/oauth/concluir` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/hub-integracoes/oauth/{sistema}/callback` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/hub-integracoes/oauth/{sistema}/iniciar` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/hub-integracoes/webhook/{token}` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/icp` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/icp` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/icp/grupo/{grupo_id}` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/icp/performance` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/icp/{icp_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/icp/{icp_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/icp/{icp_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/icp/{icp_id}/clonar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/icp/{icp_id}/contas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/icp/{icp_id}/contas` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/icp/{icp_id}/contas/gerar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/indicacoes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/indicacoes/{codigo}/converter` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/integracoes/chaves-api` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/integracoes/chaves-api` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| DELETE | `/api/v1/integracoes/chaves-api/{chave_id}` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| DELETE | `/api/v1/integracoes/webhook` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/integracoes/webhook` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| PUT | `/api/v1/integracoes/webhook` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/inteligencia-rede/atribuicao-receita` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/inteligencia-rede/fit-icp` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/inteligencia-rede/intents/{intent_id}/matches` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/inteligencia-rede/intents/{intent_id}/matches/{tenant_id_candidato}/explicar-com-ia` | sessao | — | token(get_tenant_id) | — | tenant_id_candidato | negada (404) com ids de outro tenant |
| GET | `/api/v1/inteligencia-rede/riscos-pipeline` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/inteligencia-rede/saude-relacionamentos` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/inteligencia-rede/sinais` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/inteligencia-rede/sinais/gerar` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/inteligencia-rede/sinais/{sinal_id}/converter` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/inteligencia-rede/sinais/{sinal_id}/descartar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/inteligencia-rede/sinais/{sinal_id}/visto` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/inteligencia-rede/sugestoes-expansao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/inteligencia/agente` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/inteligencia/agente/ferramentas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/inteligencia/agentes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/inteligencia/aprendizado` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/inteligencia/conhecimento` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/inteligencia/conhecimento` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/inteligencia/conhecimento/tipos` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/inteligencia/conhecimento/{item_id}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/inteligencia/features` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/inteligencia/oportunidades/contas/{conta_id}/white-space` | sessao | — | token(get_tenant_id) | conta | — | negada (404) com ids de outro tenant |
| PATCH | `/api/v1/inteligencia/oportunidades/necessidades/{necessidade_id}` | sessao | — | token(get_tenant_id) | necessidade | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/inteligencia/oportunidades/{negocio_id}/card` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/inteligencia/oportunidades/{negocio_id}/necessidades` | sessao | — | token(get_tenant_id) | negocio | — | executada (2xx), sem vazamento |
| POST | `/api/v1/inteligencia/oportunidades/{negocio_id}/necessidades` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/inteligencia/oportunidades/{negocio_id}/necessidades/extrair` | sessao | — | token(get_tenant_id) | negocio | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/inteligencia/perfil-empresa/consolidar` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/inteligencia/perfil-usuario/consolidar` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/inteligencia/receita/metricas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/inteligencia/uso-ia` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/leads/contas` | sessao | super_admin | token(get_tenant_id) | — | — | negada por papel/autenticação |
| GET | `/api/v1/leads/contas` | sessao | — | token(get_tenant_id) | — | tenant_id_selecionado | negada por papel/autenticação |
| POST | `/api/v1/leads/contas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/leads/contas/elegibilidade-exclusao` | sessao | super_admin | token(get_tenant_id) | — | — | negada por papel/autenticação |
| POST | `/api/v1/leads/contas/limpeza-nao-trabalhados` | sessao | super_admin | token(get_tenant_id) | — | — | negada por papel/autenticação |
| GET | `/api/v1/leads/contas/preview-limpeza-nao-trabalhados` | sessao | super_admin | token(get_tenant_id) | — | — | negada por papel/autenticação |
| GET | `/api/v1/leads/decisores` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/linkedin/conexoes/importar` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/linkedin/conexoes/status` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/linkedin/tarefas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/linkedin/tarefas/contagem` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/linkedin/tarefas/{tarefa_id}/marcar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/listas-prospeccao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/listas-prospeccao` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| DELETE | `/api/v1/listas-prospeccao/{lista_id}/contas` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/listas-prospeccao/{lista_id}/contas` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/listas-prospeccao/{lista_id}/contas/elegibilidade-exclusao` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/listas-prospeccao/{lista_id}/contas/importar-participantes` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/map/analyze` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/map/cac` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/map/churn/predict` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/map/customer-score` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/map/ltv` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/map/performance/acesso` | sessao | — | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/map/performance/configuracao` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| PUT | `/api/v1/map/performance/contato-efetivo` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/map/performance/daily` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/map/performance/equipe` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| PUT | `/api/v1/map/performance/ofertas-familias` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/map/performance/painel` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/map/performance/politicas` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/map/performance/quotas` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| PUT | `/api/v1/map/performance/representantes/{representante_id}/usuario` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/map/performance/usuarios-crm` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/map/roi` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/motor/comissoes/waterfall` | sessao | super_admin | token(get_tenant_id) | — | — | negada por papel/autenticação |
| GET | `/api/v1/motor/dashboard` | sessao | super_admin | token(get_tenant_id) | — | — | negada por papel/autenticação |
| POST | `/api/v1/motor/interacoes` | sessao | super_admin | token(get_tenant_id) | — | — | negada por papel/autenticação |
| GET | `/api/v1/motor/saude-tenants` | sessao | super_admin | token(get_tenant_id) | — | — | negada por papel/autenticação |
| GET | `/api/v1/motor/tenants/{tenant_id}/interacoes` | sessao | super_admin | token(get_tenant_id) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/motor/tenants/{tenant_id}/margem-contribuicao` | sessao | super_admin | token(get_tenant_id) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/motor/tenants/{tenant_id}/score-risco` | sessao | super_admin | token(get_tenant_id) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/motor/tenants/{tenant_id}/script-resgate` | sessao | super_admin | token(get_tenant_id) | — | tenant_id | negada por papel/autenticação |
| GET | `/api/v1/notificacoes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/notificacoes/configuracao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/notificacoes/{notificacao_id}/confirmar-contato` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/nps/configuracao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/nps/configuracao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/nps/disparar-pendentes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/nps/responder/{token}` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/nps/responder/{token}` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/ofertas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/ofertas` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| DELETE | `/api/v1/ofertas/{oferta_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/ofertas/{oferta_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/ofertas/{oferta_id}/ativar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/ofertas/{oferta_id}/desativar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/ofertas/{oferta_id}/materiais` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/ofertas/{oferta_id}/materiais/{material_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/onboarding/status` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/opt-out/campanha/{token}` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/opt-out/email/{token}` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/painel/admin/ranking` | sessao | super_admin | token(get_tenant_id) | — | — | negada por papel/autenticação |
| GET | `/api/v1/painel/configuracao-meta` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/painel/configuracao-meta` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/painel/indicadores` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/painel/indicadores/export.csv` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/painel/metrica-norte` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/painel/nps` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/painel/preferencias-dashboard` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/painel/preferencias-dashboard` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/parceiros/tenants` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/parceiros/tenants` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/parceiros/tenants/{tenant_id}/billing` | chave_api | — | chave_api | — | tenant_id | fora do escopo da varredura (ver guarda de rotas públicas) |
| PUT | `/api/v1/parceiros/tenants/{tenant_id}/licenca` | chave_api | — | chave_api | — | tenant_id | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/parceiros/tenants/{tenant_id}/uso` | chave_api | — | chave_api | — | tenant_id | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/pesquisas-decisores` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/pesquisas-decisores/compras` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/pesquisas-decisores/compras` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/pesquisas-decisores/movimentacoes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/pesquisas-decisores/pacotes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/pesquisas-decisores/painel` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/pesquisas-decisores/previa` | sessao | — | token(get_tenant_id) | — | — | negada/validação (409) |
| GET | `/api/v1/pesquisas-decisores/{pesquisa_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/pesquisas-decisores/{pesquisa_id}/cancelar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/pesquisas-decisores/{pesquisa_id}/confirmar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/pesquisas-decisores/{pesquisa_id}/retomar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/planos` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/planos` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/planos/enriquecimento` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| PUT | `/api/v1/planos/{plano_id}` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/portal-fornecedor` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/portal-fornecedor/declinar` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/portal-fornecedor/perguntas` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/portal-fornecedor/propostas` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/portal-fornecedor/propostas/{proposta_id}/anexos` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/predator/accounts` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/predator/company/enrich` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/predator/icps` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/predator/lists/generate` | chave_api | — | chave_api | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/procurement/contratos/{contrato_id}/inteligencia` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/procurement/demandas/{demanda_id}/analise` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/procurement/documentos` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/procurement/documentos/{documento_id}/analisar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/procurement/documentos/{documento_id}/arquivo` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/procurement/documentos/{documento_id}/estimativa` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/procurement/fornecedores/ranking` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/procurement/fornecedores/{fornecedor_id}/360` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/procurement/metricas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/procurement/planos/{plano_id}/painel` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/procurement/processos/{processo_id}/workspace` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/procurement/proximas-acoes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/procurement/riscos` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/procurement/{recurso}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/procurement/{recurso}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/procurement/{recurso}/{registro_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PATCH | `/api/v1/procurement/{recurso}/{registro_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/procurement/{recurso}/{registro_id}/aprovar` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/qualificacao/configuracao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/qualificacao/configuracao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/bloquear/{tenant_id_outro}` | sessao | — | token(get_tenant_id) | — | tenant_id_outro | executada (2xx), sem vazamento |
| GET | `/api/v1/rede-social/conexoes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/conexoes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/rede-social/conexoes/{conexao_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/conexoes/{conexao_id}/desbloquear` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/conexoes/{conexao_id}/desconectar` | sessao | — | token(get_tenant_id) | — | — | negada/validação (409) |
| GET | `/api/v1/rede-social/empresas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/rede-social/grafo/{empresa_id}` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/rede-social/identidade` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/identidades/{empresa_id}/reivindicar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/rede-social/intents` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/intents` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/rede-social/intents/{intent_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/intents/{intent_id}/atender` | sessao | — | token(get_tenant_id) | — | — | negada por papel/autenticação |
| POST | `/api/v1/rede-social/intents/{intent_id}/encerrar` | sessao | — | token(get_tenant_id) | — | — | negada por papel/autenticação |
| GET | `/api/v1/rede-social/membros` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/mensagens` | sessao | — | token(get_tenant_id) | — | — | negada/validação (409) |
| GET | `/api/v1/rede-social/mensagens/{com_tenant_id}` | sessao | — | token(get_tenant_id) | — | com_tenant_id | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/mensagens/{mensagem_id}/marcar-lida` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/rede-social/notificacoes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/rede-social/notificacoes/contagem-nao-lidas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/notificacoes/marcar-todas-lidas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/notificacoes/{notificacao_id}/marcar-lida` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/rede-social/perfil` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/rede-social/perfil` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/rede-social/perfil/visibilidade` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/rede-social/posts` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/posts` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| DELETE | `/api/v1/rede-social/posts/{post_id}` | sessao | — | token(get_tenant_id) | — | — | negada por papel/autenticação |
| GET | `/api/v1/rede-social/posts/{post_id}/comentarios` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/posts/{post_id}/comentarios` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/posts/{post_id}/compartilhar` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/rede-social/posts/{post_id}/midia/{midia_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/posts/{post_id}/reagir` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/relacionamentos` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/rede-social/relacionamentos/por-cnpj` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| DELETE | `/api/v1/rede-social/relacionamentos/{relacionamento_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/relacionamentos/{relacionamento_id}/confirmar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/rede-social/relacionamentos/{tenant_id_alvo}` | sessao | — | token(get_tenant_id) | — | tenant_id_alvo | executada (2xx), sem vazamento |
| GET | `/api/v1/rede-social/salas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/rede-social/salas` | sessao | — | token(get_tenant_id) | — | — | negada/validação (409) |
| GET | `/api/v1/rede-social/salas/canais/{canal_id}/mensagens` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/salas/canais/{canal_id}/mensagens` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/rede-social/salas/documentos/{documento_id}/arquivo` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| PATCH | `/api/v1/rede-social/salas/tarefas/{tarefa_id}` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/rede-social/salas/{sala_id}/canais` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/salas/{sala_id}/canais` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/salas/{sala_id}/documentos` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/rede-social/salas/{sala_id}/negocio` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/salas/{sala_id}/negocio` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/rede-social/salas/{sala_id}/negocio/compartilhado` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/rede-social/salas/{sala_id}/participantes` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/rede-social/salas/{sala_id}/participantes` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/salas/{sala_id}/reunioes` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/salas/{sala_id}/stakeholders` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/salas/{sala_id}/tarefas` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/rede-social/salas/{sala_id}/workspace` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede-social/seguir` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/rede-social/seguir/{tenant_id_seguido}` | sessao | — | token(get_tenant_id) | — | tenant_id_seguido | executada (2xx), sem vazamento |
| GET | `/api/v1/rede/convites-sourcing` | sessao | — | token(usuario) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/rede/convites-sourcing/{participante_id}` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede/convites-sourcing/{participante_id}/declinar` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede/convites-sourcing/{participante_id}/perguntas` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede/convites-sourcing/{participante_id}/propostas` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/rede/convites-sourcing/{participante_id}/propostas/{proposta_id}/anexos` | sessao | — | token(usuario) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/registro-oportunidade` | sessao | — | token(get_tenant_id) | — | tenant_id_selecionado | negada por papel/autenticação |
| POST | `/api/v1/registro-oportunidade` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/registro-oportunidade/solicitacoes-desconto` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/registro-oportunidade/solicitacoes-desconto/{solicitacao_id}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/registro-oportunidade/{registro_id}/solicitar-desconto` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/registro-oportunidade/{registro_id}/status` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/regras-aprendidas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/regras-aprendidas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/regras-aprendidas/correcoes-recentes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/regras-aprendidas/correcoes-recentes/{log_id}/sugerir-regra` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/regras-aprendidas/padroes-observados` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/regras-aprendidas/performance-ia` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/regras-aprendidas/{regra_id}` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/regras-aprendidas/{regra_id}` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/regras-aprendidas/{regra_id}/ativar` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/regras-aprendidas/{regra_id}/desativar` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/relatorio-consumo-creditos` | sessao | admin, super_admin | token(usuario) | — | tenant_id | negada (404) com ids de outro tenant |
| GET | `/api/v1/relatorio-consumo-creditos/csv` | sessao | admin, super_admin | token(usuario) | — | tenant_id | negada (404) com ids de outro tenant |
| GET | `/api/v1/relatorio-entrega` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/relatorio-entrega/bounces-manuais` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/relatorio-entrega/envios` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/relatorios/configuracao` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| PUT | `/api/v1/relatorios/configuracao` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/relatorios/dashboard` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/representantes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/representantes` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/representantes/self-service` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| PUT | `/api/v1/representantes/{representante_id}` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/reunioes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/reunioes/processar-lembretes` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/reunioes/reagendar/{token}` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/reunioes/reagendar/{token}` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/reunioes/{reuniao_id}/confirmar` | sessao | — | token(get_tenant_id) | reuniao | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/reunioes/{reuniao_id}/confirmar-qualificacao` | sessao | — | token(get_tenant_id) | reuniao | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/reunioes/{reuniao_id}/dossie` | sessao | — | token(get_tenant_id) | reuniao | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/reunioes/{reuniao_id}/marcar-resultado` | sessao | — | token(get_tenant_id) | reuniao | — | validação (422) — ver testes dirigidos |
| POST | `/api/v1/reunioes/{reuniao_id}/reprocessar-transcricao` | sessao | — | token(get_tenant_id) | reuniao | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/ropa` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/ropa` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/ropa/minimizacao` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/ropa/tenant` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/rotulos-hierarquia` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| PUT | `/api/v1/rotulos-hierarquia` | sessao | super_admin | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/saude-contas/contas/{conta_id}/interacoes` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/saude-contas/contas/{conta_id}/score-risco` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/saude-contas/contas/{conta_id}/script-resgate` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/saude-contas/contas/{conta_id}/vendedor` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/saude-contas/contas/{conta_id}/vendedores-disponiveis` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/saude-contas/dashboard` | sessao | — | token(get_tenant_id) | — | tenant_id_selecionado | negada por papel/autenticação |
| GET | `/api/v1/saude-contas/desempenho/economia` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/saude-contas/desempenho/funil` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/saude-contas/interacoes` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/saude-contas/ranking` | sessao | — | token(get_tenant_id) | — | tenant_id_selecionado | negada por papel/autenticação |
| GET | `/api/v1/saude-contas/vendedores-com-contas` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/sourcing/anexos/{anexo_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/sourcing/documentos/{documento_id}/analisar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/sourcing/documentos/{documento_id}/arquivo` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/sourcing/documentos/{documento_id}/estimativa` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/sourcing/esclarecimentos/{esclarecimento_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/sourcing/processos` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/sourcing/processos` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/sourcing/processos/{processo_id}/aprovacao` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/sourcing/processos/{processo_id}/aprovacao` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/sourcing/processos/{processo_id}/avaliacao-ia` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/sourcing/processos/{processo_id}/avaliacao-ia/estimativa` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/sourcing/processos/{processo_id}/comparacao` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/sourcing/processos/{processo_id}/contrato` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/sourcing/processos/{processo_id}/descoberta` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/sourcing/processos/{processo_id}/documentos` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/sourcing/processos/{processo_id}/itens` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/sourcing/processos/{processo_id}/participantes` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/sourcing/processos/{processo_id}/participantes/{participante_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/sourcing/processos/{processo_id}/participantes/{participante_id}/acesso` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/sourcing/processos/{processo_id}/propostas` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/sourcing/processos/{processo_id}/requisitos` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/sourcing/processos/{processo_id}/status` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/sourcing/processos/{processo_id}/workspace` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/sourcing/propostas/{proposta_id}/avaliacoes` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/sourcing/requisitos/{requisito_id}/revisao` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/template-proposta` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| PUT | `/api/v1/template-proposta` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/template-proposta/itens` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/template-proposta/itens` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| DELETE | `/api/v1/template-proposta/itens/{item_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| PUT | `/api/v1/template-proposta/itens/{item_id}` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/template-proposta/logo` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| POST | `/api/v1/template-proposta/logo` | sessao | — | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| DELETE | `/api/v1/titulares` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/titulares/buscar` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/titulares/exportar` | sessao | — | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/usuarios` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/verificacao-empresa` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/api/v1/verificacao-empresa/pendentes` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| POST | `/api/v1/verificacao-empresa/{verificacao_id}/revisar` | sessao | — | token(usuario) | — | — | negada por papel/autenticação |
| GET | `/api/v1/webhooks-saida` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/webhooks-saida` | sessao | admin, super_admin | token(get_tenant_id) | — | — | validação (422) — ver testes dirigidos |
| GET | `/api/v1/webhooks-saida/eventos` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| DELETE | `/api/v1/webhooks-saida/{assinatura_id}` | sessao | admin, super_admin | token(get_tenant_id) | — | — | negada (404) com ids de outro tenant |
| GET | `/api/v1/webhooks-saida/{assinatura_id}/entregas` | sessao | admin, super_admin | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| POST | `/api/v1/webhooks/email` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/webhooks/email/aberto/{token}.png` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/webhooks/email/inbound` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/webhooks/envio/eventos` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/webhooks/mercadopago` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/webhooks/recall/eventos` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/webhooks/reputacao` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/webhooks/sendgrid/eventos` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/webhooks/whatsapp` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/webhooks/whatsapp/meta` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| POST | `/api/v1/webhooks/whatsapp/meta` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
| GET | `/api/v1/whatsapp/templates` | sessao | — | token(get_tenant_id) | — | — | executada (2xx), sem vazamento |
| GET | `/health` | nenhuma | — | nao_aplicavel | — | — | fora do escopo da varredura (ver guarda de rotas públicas) |
