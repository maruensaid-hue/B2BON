# RLS — isolamento por tenant no PostgreSQL (D-110)

Resposta ao achado **A01** da auditoria de 28/10/2026: o isolamento entre empresas dependia de cada consulta filtrar `tenant_id`. Esta etapa acrescenta uma **segunda barreira no banco**
(Row-Level Security), sem trocar a primeira. **A01 NÃO está resolvido**: esta é a primeira etapa, com cobertura parcial e delimitada (veja "O que ainda não está coberto").

> Enquanto a aplicação conectar com o papel dono das tabelas (ou com qualquer papel com `BYPASSRLS`), o RLS **não tem efeito nenhum**. Ele só protege depois do passo
> "Ligar" abaixo. Por isso a migração é segura de aplicar sozinha.

## 1. Como funciona

**Contexto transacional.** O banco decide o que cada transação enxerga lendo quatro variáveis de sessão, gravadas pelo backend com `set_config(..., is_local => true)` (equivale a `SET LOCAL`):

| Variável | Conteúdo |
|---|---|
| `app.tenant_id` | tenant do usuário já validado no banco (nunca um valor vindo da requisição) |
| `app.escopo` | `tenant`, uma busca pré-tenant (`login`, `autenticacao`…) ou `sistema:<nome>` |
| `app.visiveis` | tenants cuja **leitura** a regra de hierarquia da aplicação já autorizou (`*` = super_admin) |
| `app.chave` | a chave da busca pré-tenant (e-mail do login, código do convite, hash do token) |

- O contexto mora em `Session.info` (`app/db/rls.py`). O evento `after_begin` o grava no início de **cada** transação. A sessão do SQLAlchemy abre uma transação nova depois de cada
  `commit` e de cada `rollback`, então o contexto é regravado sozinho; um `SAVEPOINT` não o altera.
- Como é local à transação, **nada persiste na conexão**: a próxima requisição que reaproveitar a mesma conexão do pool (inclusive atrás do pgbouncer em modo de transação) começa sem contexto.
- **Negar por padrão.** Sem contexto a variável fica ausente, as funções devolvem `NULL` e `NULL` nunca é igual a nada: as políticas não liberam linha alguma.
- **De onde vem o tenant.** `auth_service.validar_token` confere a assinatura do JWT, busca **uma** linha de `usuario` (política `autenticacao`, pela chave do id) e só então fixa `definir_tenant` com o
  `tenant_id` lido do banco. Rotas por token assinado (opt-out, pixel, reagendamento, NPS) fixam o tenant que está dentro do token HMAC.
- **Autoflush desligado.** O que está pendente na sessão é gravado (`flush`) sob o contexto anterior antes de trocar de contexto; senão seria gravado depois, sob outro, e o `WITH CHECK` o recusaria.
- **Sessões irmãs.** O gateway de IA e o financeiro gravam em transação própria; `rls.sessao_irma` copia o contexto para elas.

**Tipos de contexto** (todos explícitos; não existe contexto "tudo", nem tenant curinga):

1. `tenant` — usuário autenticado, cron por tenant (`rls.contexto_tenant` a cada volta), webhooks depois de achar o tenant. Lê e grava só o próprio `tenant_id`.
2. **Hierarquia (só leitura)** — `tenant_service.tenant_ids_no_escopo` amplia `app.visiveis` exatamente para o que a regra de hierarquia já autoriza. A escrita continua só no tenant do contexto.
   O RLS não dá a admin ou super_admin nada que a aplicação já não desse.
3. **Busca pré-tenant** (`BUSCAS` em `app/db/rls_registro.py`) — achar UMA linha antes de saber o tenant: só `SELECT`, só no escopo nomeado, só a linha cuja chave coincide. Depois da busca o código troca para o contexto do tenant achado.
4. **Sistema** (`CONTEXTOS_SISTEMA`) — tarefas sem usuário. Cada nome lista as tabelas que pode tocar e se escreve.

**Políticas por tipo de tabela** (`app/db/rls_sql.py`): `rls_tenant` (`tenant_id = b2bon_tenant()`, `FOR ALL`, com `WITH CHECK`), `rls_leitura_hierarquia` (`SELECT` para `app.visiveis`), `rls_partes`
(tabela que liga duas empresas por desenho), `rls_busca_*`, `rls_sistema_*`, `rls_herdada` (escopo herdado do pai por função `SECURITY DEFINER` que só devolve um booleano, para não haver recursão entre políticas).

## 2. Papéis no PostgreSQL

| Papel | Uso | Requisitos |
|---|---|---|
| **dono** (hoje o usuário da connection string do Neon) | migrações Alembic e operação de banco | dono das tabelas; **não** é usado pela aplicação depois do rollout |
| **`b2bon_app`** (execução) | a API e os jobs | `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, sem DDL, sem `TRUNCATE`, sem acesso a `alembic_version` |

- O RLS vale para quem **não é dono** das tabelas. Por isso `FORCE ROW LEVEL SECURITY` **não** foi usado: com `FORCE`, o dono (migrações com `UPDATE` de dados, manutenção, backup lógico) também ficaria preso às políticas.
- No Neon, o papel criado pelo console costuma ter `BYPASSRLS` (herdado de `neon_superuser`). **Não use esse papel na aplicação**; crie `b2bon_app` com o SQL abaixo.
- Variáveis de ambiente: `DATABASE_URL` = papel de execução; `MIGRATION_DATABASE_URL` = papel dono (só o Alembic usa; vazio = usa `DATABASE_URL`).

## 3. Rollout (nesta ordem, primeiro em staging)

1. **Aplicar a migração** `e7a9c1d3f5b8` com o papel dono (`alembic upgrade head`). Cria as funções e as políticas e liga o RLS nas tabelas protegidas. Sem efeito enquanto a API usar o dono.
2. **Criar o papel de execução** (revisar o SQL antes de rodar, com o papel dono; a senha vem do ambiente):
   ```bash
   RLS_SENHA_APP='<senha forte>' python scripts/ops/rls_papel_aplicacao.py b2bon_app > papel.sql   # confira papel.sql e rode no banco como dono
   ```
3. **Conferir o papel**: `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'b2bon_app';` deve devolver `f | f`.
4. **Ligar** (no Render): `MIGRATION_DATABASE_URL` = URL atual (dono); `DATABASE_URL` = URL com `b2bon_app`. Redeploy.
5. **Verificar** (roteiro mínimo): login, abrir CRM/Prospecção/MAP, criar e editar uma conta, aprovar uma mensagem, enviar uma campanha de teste, abrir o Relatório de Entrega, um cron por tenant
   (`POST /cron/processar-envios`). Acompanhar os logs por `row-level security` e `permission denied`.
6. **Staging antes de produção.** O mesmo roteiro, com um usuário comum e um administrador de distribuidor.

## 4. Reversão

- **Mais rápida (segundos, sem migração):** voltar `DATABASE_URL` para a URL do papel dono e redeployar. O RLS deixa de valer; nada é perdido.
- **Remover as políticas:** `alembic downgrade d4f6a8c0e2b4` com o papel dono (remove as políticas `rls_*`, desliga o RLS e apaga as funções `b2bon_*`).
- O papel `b2bon_app` pode ficar (sem políticas ele é só um papel de leitura/escrita comum) ou ser removido com `DROP OWNED BY b2bon_app; DROP ROLE b2bon_app;`.

## 5. Verificação automática

- `tests/integration/test_rls_postgres.py` (PostgreSQL real, `B2BON_TESTE_PG_URL`): dois tenants, leitura/inserção/atualização/exclusão, escopo herdado, sem contexto, hierarquia, busca pré-tenant,
  contexto de sistema, tabela de duas partes, reaproveitamento da mesma conexão depois de `commit`, `rollback` e erro. No CI roda no job `postgres-migrations`.
- `tests/unit/test_rls_registro.py`: toda tabela do modelo está classificada (protegida, pendente com motivo ou global) e o registro bate com o que a migração cria.
- `tests/unit/test_rls_contexto.py`: o mecanismo de contexto, sem banco.
- **Sonda** (`tests/rls_sonda.py`, `B2BON_RLS_SONDA=<arquivo.json>`): roda a suíte inteira marcando, nas requisições HTTP, toda consulta a tabela protegida sem o contexto exigido, leitura de outro tenant e escrita
  em outro tenant. É a ferramenta usada para decidir quais tabelas já podem ser protegidas e para ampliar a cobertura nas próximas etapas. O SQLite **não** prova enforcement; a sonda aponta lacunas, o PostgreSQL prova.

## 6. Matriz de cobertura por tabela (primeira etapa)

Total de tabelas do modelo: **212**. Protegidas com política: **81**. Pendentes (sem política, com motivo): **98**. Globais (sem escopo de empresa): **33**. Este bloco é gerado do registro `app/db/rls_registro.py`; o teste `test_rls_registro.py` impede que o registro fique diferente da migração e de o modelo ter tabela sem classificação (esta tabela em Markdown é regenerada à mão quando o registro muda).

### Protegidas por tenant direto (`rls_tenant` + leitura ampliada pela hierarquia)

`alerta_credito`, `alerta_detrator`, `anexo_sourcing`, `aprovacao`, `avaliacao_sourcing`, `bloqueio_contato`, `cadencia`, `campanha`, `chave_api_tenant`, `compra_credito`, `conexao_integracao`, `conexao_linkedin`, `configuracao_canal`, `configuracao_comunicacao`, `configuracao_envio`, `configuracao_notificacao`, `configuracao_nps`, `configuracao_qualificacao`, `configuracao_whatsapp`, `conversa_qualificacao`, `convite_cadastro`, `custo_aquisicao`, `custo_direto_infra`, `decisao_go_no_go`, `demanda_compra`, `descarte_conta`, `documento_cofre`, `documento_ri`, `email_direto`, `email_recebido`, `enriquecimento_nota_fiscal`, `enriquecimento_semanal_consumo`, `envio_crm`, `esclarecimento_sourcing`, `estado_alertas_licitacao`, `estagio_funil`, `evento_aprendizado`, `execucao_sync`, `faq_item`, `fornecedor_compras`, `indicacao`, `indicador_financeiro_conta`, `indicador_ri`, `item_pca`, `item_template_proposta`, `link_captura_lead`, `lista_prospeccao`, `material_oferta`, `mensagem`, `negocio`, `notificacao_vendedor`, `orgao_publico`, `pagamento_licenca`, `pausa_canal`, `perfil_inteligencia`, `pesquisa_decisores`, `pesquisa_decisores_empresa`, `pesquisa_decisores_transicao`, `pesquisa_nps`, `pesquisa_preco`, `plano_contratacao`, `proposta_negocio`, `qualificacao_score`, `recebimento_governo`, `registro_crm_externo`, `registro_envio_diario`, `registro_idempotencia`, `registro_reputacao_canal`, `registro_supressao_permanente`, `regra_aprendida`, `regra_auto_aprovacao`, `tarefa_linkedin`, `template_proposta`, `template_whatsapp`, `toque_cadencia`, `turno_conversa`, `unidade_compras`, `vinculo_externo`

### Protegidas, tabelas de duas partes (`rls_partes`)

| Tabela | Partes |
|---|---|
| `conexao_empresa` | `tenant_id_origem`, `tenant_id_destino` |
| `mensagem_rede_social` | `tenant_id_remetente`, `tenant_id_destinatario` |
| `sala_corporativa` | `tenant_id_a`, `tenant_id_b` |

### Buscas antes de saber o tenant (política só de `SELECT`, pela chave)

| Escopo | Tabela | Condição |
|---|---|---|
| `convite-cadastro` | `convite_cadastro` | `codigo = b2bon_chave()` |
| `whatsapp-numero` | `configuracao_whatsapp` | `phone_number_id = b2bon_chave()` |
| `captura-lead` | `link_captura_lead` | `codigo = b2bon_chave()` |
| `integracao-webhook` | `conexao_integracao` | `webhook_token_hash = b2bon_chave()` |
| `chave-api` | `chave_api_tenant` | `chave_hash = b2bon_chave()` |
| `pagamento-referencia` | `pagamento_licenca` | `id::text = b2bon_chave()` |
| `pagamento-referencia` | `compra_credito` | `id::text = b2bon_chave()` |

Buscas já definidas no código e **ainda sem política** (a tabela é pendente): `autenticacao` → `usuario`, `login` → `usuario`, `redefinicao` → `redefinicao_senha`, `redefinicao` → `usuario`, `convite-vitrine` → `convite_vitrine`, `portal-fornecedor` → `participante_sourcing`, `recall-bot` → `reuniao`, `pagamento-referencia` → `enriquecimento_compra`.

### Pendentes: ainda dependem só dos filtros do código

| Tabela | Por quê |
|---|---|
| `alerta_licitacao` | tocada fora do contexto do tenant em: cron:podar_historicos |
| `apuracao_comissao` | tocada fora do contexto do tenant em: comissoes:apuracoes, comissoes:criar_perfil, comissoes:recalcular, comissoes:registrar_cotacao, comissoes:waterfall, motor:margem_contribuicao, motor:waterfall_comissoes |
| `assinatura_webhook_parceiro` | tocada fora do contexto do tenant em: cron (suspender licenças, webhooks de parceiros) e provisionamento por chave de parceiro |
| `assinatura_webhook_tenant` | tocada fora do contexto do tenant em: cron:processar_eventos |
| `atividade` | tocada fora do contexto do tenant em: cron:processar_fila_enriquecimento |
| `audit_log` | tocada fora do contexto do tenant em: admin_enriquecimento:auditoria, admin_enriquecimento:decidir_estorno, admin_tenants:atualizar_licenca, admin_tenants:criar_tenant, admin_tenants:desativar_tenant, admin_tenants:reativar_tenant, agente_corporativo:perguntar, comissoes:alterar_politica_infra, comissoes:alterar_politica_margem, comissoes:atualizar_componente, comissoes:criar_componente, comissoes:criar_perfil, comissoes:criar_status_tributario, comissoes:decidir_alerta, comissoes:recalcular, comissoes:registrar_cotacao, cron:coletar_licitacoes, cron:processar_fila_enriquecimento, cron:suspender_licencas_vencidas, finops:ativar_catalogo, finops:criar_rascunho, finops:nova_versao_pacote, governo:criar_oportunidade, governo:nova_politica, governo:override_comissao, governo:transferir, map_performance:contato_efetivo, map_performance:definir_quota, map_performance:ofertas_familias, map_performance:vincular, motor:registrar_interacao, parceiros:provisionar_tenant, planos:atualizar_plano, planos:criar_plano, portal_fornecedor:enviar, ropa:criar_versao_ropa_plataforma, saude_conta:atribuir_vendedor, saude_conta:registrar_interacao |
| `autorizacao_oauth_pendente` | tocada fora do contexto do tenant em: integracoes_crm_publico:callback_oauth |
| `cache_resposta_ia` | tocada fora do contexto do tenant em: cron:podar_historicos |
| `campanha_destinatario` | tocada fora do contexto do tenant em: app/api/deps:(dependência) |
| `campo_enriquecido` | escopo herdado de `conta` (sem `tenant_id` próprio); a política só entra junto com a do pai, ainda pendente |
| `canal_sala` | escopo herdado de `sala_corporativa` (sem `tenant_id` próprio); a política só entra junto com a do pai, ainda pendente |
| `carteira_creditos` | tocada fora do contexto do tenant em: agente_corporativo:perguntar, cron:creditos_ia, cron:processar_fila_enriquecimento |
| `chave_api_parceiro` | autenticada por hash de chave do parceiro, sem usuário, antes de saber o tenant (deps.get_chave_api_atual): falta a busca pré-tenant |
| `coleta_site_conta` | tocada fora do contexto do tenant em: cron:podar_historicos, cron:processar_fila_enriquecimento |
| `comentario_post` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `comissao_representante` | tocada fora do contexto do tenant em: comissoes:criar_perfil, comissoes:recalcular, comissoes:registrar_cotacao, comissoes:waterfall, motor:margem_contribuicao, motor:waterfall_comissoes |
| `componente_contrato_governo` | tocada fora do contexto do tenant em: governo:override_comissao, governo:transferir, motor:margem_contribuicao |
| `configuracao_agente_corporativo` | tocada fora do contexto do tenant em: agente_corporativo:perguntar |
| `configuracao_coleta_fonte` | tocada fora do contexto do tenant em: cron:coletar_licitacoes |
| `configuracao_credito_tenant` | tocada fora do contexto do tenant em: agente_corporativo:perguntar, cron:creditos_ia, cron:processar_fila_enriquecimento |
| `configuracao_email_api` | tocada fora do contexto do tenant em: app/api/deps:(dependência) |
| `configuracao_email_smtp` | tocada fora do contexto do tenant em: app/api/deps:(dependência) |
| `configuracao_painel` | tocada fora do contexto do tenant em: painel:ranking_assinantes |
| `configuracao_relatorio` | lida por cron global (disparar relatórios periódicos) em todos os tenants: falta revisar a lista do contexto de sistema |
| `conhecimento_corporativo` | tocada fora do contexto do tenant em: agente_corporativo:perguntar |
| `conta` | tocada fora do contexto do tenant em: auth:demonstracao, cron:processar_fila_enriquecimento, saude_conta:atribuir_vendedor, saude_conta:listar_interacoes, saude_conta:score_risco, saude_conta:script_resgate, saude_conta:vendedores_disponiveis |
| `conta_franquia_consumo` | tocada fora do contexto do tenant em: parceiros:obter_uso |
| `conteudo_pagina_site` | tocada fora do contexto do tenant em: cron:processar_fila_enriquecimento |
| `contrato_compra` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `contrato_governo` | tocada fora do contexto do tenant em: governo:transferir |
| `contrato_sourcing` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `contrato_venda_publica` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `convite_vitrine` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `decisor` | tocada fora do contexto do tenant em: cron:processar_fila_enriquecimento |
| `documento_compras` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `documento_licitacao` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `documento_sala` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `documento_sourcing` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `empresa_rede` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `enriquecimento_carteira` | tocada fora do contexto do tenant em: admin_enriquecimento:decidir_estorno, cron:creditos_ia |
| `enriquecimento_compra` | tocada fora do contexto do tenant em: admin_enriquecimento:decidir_estorno |
| `enriquecimento_config_plano` | tocada fora do contexto do tenant em: admin_enriquecimento:aplicar_matriz, admin_enriquecimento:situacao_dos_planos, cron:creditos_ia, pesquisas_decisores:comprar_pacote, pesquisas_decisores:confirmar, pesquisas_decisores:criar_previa, pesquisas_decisores:pacotes_adicionais, pesquisas_decisores:painel_do_tenant, planos:criar_plano, relatorio_consumo:relatorio, relatorio_consumo:relatorio_csv |
| `enriquecimento_estorno_compra` | tocada fora do contexto do tenant em: admin_enriquecimento:decidir_estorno, admin_enriquecimento:listar_estornos |
| `enriquecimento_movimento` | tocada fora do contexto do tenant em: admin_enriquecimento:decidir_estorno, cron:processar_fila_enriquecimento |
| `entrega_webhook` | tocada fora do contexto do tenant em: cron:podar_historicos, cron:processar_eventos |
| `evento_contrato_compra` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `evento_contrato_sourcing` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `evento_dominio` | tocada fora do contexto do tenant em: cron:podar_historicos, cron:processar_eventos |
| `evento_processo` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `evento_sourcing` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `evento_webhook_parceiro` | sem tenant_id próprio (escopo herdado de `assinatura_webhook_parceiro`, também pendente) |
| `execucao_coleta_fonte` | tocada fora do contexto do tenant em: cron:coletar_licitacoes, cron:podar_historicos |
| `execucao_ia` | tocada fora do contexto do tenant em: agente_corporativo:perguntar, comissoes:registrar_cotacao, cron:creditos_ia, cron:processar_fila_enriquecimento, finops:resumo_plataforma |
| `fila_enriquecimento_conta` | tocada fora do contexto do tenant em: cron:processar_fila_enriquecimento |
| `icp` | tocada fora do contexto do tenant em: cron:podar_recorte_cnpj |
| `intent` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `interacao_conta` | tocada fora do contexto do tenant em: saude_conta:registrar_interacao |
| `interacao_tenant` | tocada fora do contexto do tenant em: motor:dashboard, motor:listar_interacoes, motor:registrar_interacao, motor:saude_tenants, motor:score_risco, motor:script_resgate |
| `item_sourcing` | tocada fora do contexto do tenant em: portal_fornecedor:enviar, portal_fornecedor:ver |
| `licenca` | tocada fora do contexto do tenant em: admin_tenants:atualizar_licenca, admin_tenants:criar_tenant, admin_tenants:obter_licenca, agente_corporativo:perguntar, app/api/deps:(dependência), auth:demonstracao, cron:creditos_ia, cron:enviar_lembretes_cobranca, cron:processar_fila_enriquecimento, cron:suspender_licencas_vencidas, motor:score_risco, motor:script_resgate, parceiros:obter_billing, parceiros:provisionar_tenant |
| `licitacao` | tocada fora do contexto do tenant em: cron:coletar_licitacoes, cron:podar_historicos, cron:sourcing_sincronizar |
| `lote_credito` | tocada fora do contexto do tenant em: agente_corporativo:perguntar, cron:creditos_ia, cron:processar_fila_enriquecimento, governo:transferir, motor:margem_contribuicao |
| `mensagem_sala` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `midia_post` | escopo herdado de `post_rede_social` (sem `tenant_id` próprio); a política só entra junto com a do pai, ainda pendente |
| `movimento_credito` | tocada fora do contexto do tenant em: agente_corporativo:perguntar, cron:creditos_ia, cron:processar_fila_enriquecimento |
| `necessidade_oportunidade` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `notificacao_rede_social` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `oferta` | tocada fora do contexto do tenant em: agente_corporativo:perguntar, map_performance:configuracao, map_performance:contato_efetivo, map_performance:daily, map_performance:ofertas_familias, rede_social:listar_empresas |
| `oportunidade_governo` | tocada fora do contexto do tenant em: governo:criar_oportunidade |
| `orcamento_ia` | tocada fora do contexto do tenant em: cron:processar_fila_enriquecimento |
| `participante_sala` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `participante_sourcing` | tocada fora do contexto do tenant em: portal_fornecedor:_por_conta, portal_fornecedor:convites, portal_fornecedor:enviar |
| `perfil_empresa` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `pergunta_agente_corporativo` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `periodo_assinatura_governo` | tocada fora do contexto do tenant em: cron:creditos_ia, governo:transferir, motor:margem_contribuicao |
| `post_rede_social` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `processo_contratacao` | tocada fora do contexto do tenant em: app/api/deps:(dependência), cron:sourcing_sincronizar |
| `processo_sourcing` | tocada fora do contexto do tenant em: app/api/deps:(dependência), cron:coletar_licitacoes, cron:sourcing_sincronizar, portal_fornecedor:convites, portal_fornecedor:enviar, portal_fornecedor:ver |
| `proposta_item_sourcing` | tocada fora do contexto do tenant em: portal_fornecedor:enviar |
| `proposta_sourcing` | tocada fora do contexto do tenant em: portal_fornecedor:enviar, portal_fornecedor:ver |
| `reacao_post` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `redefinicao_senha` | escopo herdado de `usuario` (sem `tenant_id` próprio); a política só entra junto com a do pai, ainda pendente |
| `registro_oportunidade` | tocada fora do contexto do tenant em: cron:expirar_registros_oportunidade, leads:criar_lead, registro_oportunidade:solicitar_desconto |
| `registro_uso_ia` | tocada fora do contexto do tenant em: agente_corporativo:perguntar, cron:processar_fila_enriquecimento |
| `regra_alerta_licitacao` | tocada fora do contexto do tenant em: cron:processar_alertas_licitacoes |
| `relacionamento_empresarial` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `requisito_licitacao` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `requisito_sourcing` | tocada fora do contexto do tenant em: cron:sourcing_sincronizar |
| `reuniao` | tocada fora do contexto do tenant em: painel:ranking_assinantes |
| `reuniao_sala` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `sala_compra` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `seguidor_empresa` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `sinal_oportunidade` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `solicitacao_desconto` | tocada fora do contexto do tenant em: registro_oportunidade:decidir_solicitacao_desconto |
| `stakeholder_sala` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `tarefa_sala` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |
| `usuario` | tocada fora do contexto do tenant em: admin_tenants:criar_tenant, auth:demonstracao, indicacoes:converter_indicacao, map_performance:configuracao, map_performance:contato_efetivo, map_performance:daily, map_performance:equipe, map_performance:ofertas_familias, map_performance:usuarios_crm, parceiros:provisionar_tenant, rede_social:comentar_post, rede_social:compartilhar_post, rede_social:enviar_mensagem, rede_social:enviar_mensagem_canal, rede_social:listar_comentarios, rede_social:listar_feed, rede_social:reagir_post, rede_social:responder_conexao, rede_social:solicitar_conexao |
| `verificacao_empresa` | cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos |

### Globais por natureza (nunca recebem política por tenant)

| Tabela | Motivo |
|---|---|
| `alerta_capacidade_infra` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `cache_mercado_externo` | cache global de cotação e notícias |
| `catalogo_credito` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `cnpj_estabelecimento` | dado público nacional (Receita Federal) |
| `cnpj_socio` | dado público nacional (Receita Federal) |
| `componente_infra` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `cotacao_cambio` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `enriquecimento_custo_provedor` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `enriquecimento_lote_compra` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `enriquecimento_orcamento_global` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `enriquecimento_pacote` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `enriquecimento_pagamento_provedor` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `enriquecimento_politica_provedor` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `enriquecimento_uso_provedor` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `envelope_capacidade` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `evento_licitacao_publica` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `licitacao_publica` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `pacote_credito` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `perfil_tributario` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `periodo_status_tributario` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `plano` | catálogo comercial de planos |
| `politica_comissao` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `politica_creditos_ia` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `preco_modelo_ia` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `quota_comercial` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `recorte_cnpj_estado` | controle do recorte público de CNPJ |
| `registro_tratamento` | ROPA da plataforma (LGPD) |
| `representante` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `rotulo_tipo_tenant` | rótulos de plataforma |
| `template_documento_comercial` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `tenant` | cadastro das empresas; lido por hierarquia, rede e administração (não é dado de uma empresa só) |
| `uso_capacidade_infra` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |
| `workload_ia` | dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação) |

## 7. O que ainda não está coberto (risco residual)

- **98 tabelas** seguem protegidas só pelos filtros do código, entre elas as centrais do CRM (`conta`, `decisor`, `atividade`), `usuario`, `licenca`, `audit_log` e as de IA/créditos. Elas são tocadas por webhooks, cron globais, cadastros, administração entre tenants (distribuidor, super_admin) e parceiros, e cada um desses fluxos precisa de um contexto verificado antes de a tabela entrar.
- **Contextos de sistema** (`CONTEXTOS_SISTEMA`) estão cabeados nas rotinas de cron, mas as listas de tabelas são PROVISÓRIAS (vêm do que os testes exercitam). Nenhuma política de sistema foi criada nesta etapa.
- **Tabelas que cruzam empresas por desenho** (Shoal: feed, salas, relacionamentos, diretório) só estão protegidas quando têm duas partes claras (`conexao_empresa`, `mensagem_rede_social`, `sala_corporativa`). A visibilidade fina (pública, só conexões, privada) continua regra da aplicação.
- **O RLS não protege contra SQL arbitrário** executado pela própria aplicação (injeção de SQL): as variáveis de sessão são escritas pelo backend. Ele cobre o erro de código que esquece o filtro, que é o risco de A01.
- **Custo:** um `SELECT set_config(...)` extra por transação (uma ida ao banco a mais; medir em staging antes da produção).
- **Cobertura medida pelos testes:** caminhos que nenhum teste exercita podem faltar contexto. Por isso o rollout é primeiro em staging e a reversão é só voltar a `DATABASE_URL` ao papel dono.
- **A01 só pode ser considerado resolvido** quando `PENDENTES` estiver vazio, os contextos de sistema estiverem revisados e a aplicação estiver rodando em produção com o papel de execução.

