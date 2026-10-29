# RLS — isolamento por tenant no PostgreSQL (D-110 e D-111)

Resposta ao achado **A01** da auditoria de 28/10/2026: o isolamento entre empresas dependia de cada consulta filtrar `tenant_id`. Isto acrescenta uma **segunda barreira no banco**
(Row-Level Security), sem trocar a primeira. **Primeira etapa (D-110)**: mecanismo e 81 tabelas. **Segunda etapa (D-111)**: as outras 98 tabelas com `tenant_id`, os contextos privilegiados
(plataforma e sistema) e os fluxos entre empresas. Hoje **todas as 179 tabelas com dado de empresa têm política** e as 33 restantes são globais por natureza. **Desde
29/10/2026 a API de produção conecta com o papel de execução e o A01 está encerrado (D-112)**; os limites que permanecem estão em "O que ainda não está coberto".

> Enquanto a aplicação conectar com o papel dono das tabelas (ou com qualquer papel com `BYPASSRLS`), o RLS **não tem efeito nenhum**. Ele só protege depois do passo
> "Ligar" abaixo. Por isso a migração é segura de aplicar sozinha.

## 1. Como funciona

**Contexto transacional.** O banco decide o que cada transação enxerga lendo quatro variáveis de sessão, gravadas pelo backend com `set_config(..., is_local => true)` (equivale a `SET LOCAL`):

| Variável | Conteúdo |
|---|---|
| `app.tenant_id` | tenant do usuário já validado no banco (nunca um valor vindo da requisição) |
| `app.escopo` | `tenant`, uma busca pré-tenant (`login`, `autenticacao`…), `sistema:<nome>` ou `plataforma` |
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

**Tipos de contexto** (todos explícitos, nenhum vem de dado enviado pelo cliente; não existe tenant curinga):

1. `tenant` — usuário autenticado, cron por tenant (`rls.contexto_tenant` a cada volta), webhooks depois de achar o tenant. Lê e grava só o próprio `tenant_id`.
2. **Hierarquia (só leitura)** — `tenant_service.tenant_ids_no_escopo` amplia `app.visiveis` exatamente para o que a regra de hierarquia já autoriza. A escrita continua só no tenant do contexto.
   O RLS não dá a admin ou super_admin nada que a aplicação já não desse.
3. **Busca pré-tenant** (`BUSCAS` em `app/db/rls_registro.py`) — achar UMA linha antes de saber o tenant: só `SELECT`, só no escopo nomeado, só a linha cuja chave coincide. Depois da busca o código troca para o contexto do tenant achado.
4. **Sistema** (`CONTEXTOS_SISTEMA`) — tarefas sem usuário (cron, webhooks depois da assinatura ou do segredo conferidos). O nome precisa estar registrado (rastreabilidade e teste), e **a partir da
   segunda etapa o banco libera todas as tabelas protegidas a qualquer contexto de sistema** (`rls_privilegiado`). Motivo: leitura negada pelo RLS não dá erro, devolve zero linhas; uma rotina
   agendada com a lista de tabelas incompleta pararia de trabalhar sem nenhum aviso. O que o RLS garante na API de usuários não se estende a esses caminhos, que já são autenticados por segredo.
5. **Plataforma** (`plataforma`) — rotas EXCLUSIVAS de `super_admin` (`exigir_papel("super_admin")`, `exigir_gestor_do_tenant` quando quem chama é super_admin) e a gestão comercial do MAP para quem o
   próprio serviço autoriza (`map_performance`). Só é fixado depois de o papel ter sido conferido no banco; rotas `exigir_papel("super_admin", "admin")` (configuração do próprio tenant) continuam no
   contexto de tenant. Mesmo acesso total do sistema.
6. **Ação entre empresas por desenho**, sempre depois de a aplicação conferir a relação: `contexto_tenant` do tenant-alvo (agente corporativo respondendo a quem está conectado, portal do fornecedor
   convidado, conta de um tenant filho atribuída pelo distribuidor, solicitação de desconto decidida pelo tenant raiz, retorno do OAuth identificado pelo `state` cifrado, chave de API de parceiro).

**Políticas por tipo de tabela** (`app/db/rls_sql.py`): `rls_tenant` (`tenant_id = b2bon_tenant()`, `FOR ALL`, com `WITH CHECK`), `rls_leitura_hierarquia` (`SELECT` para `app.visiveis`), `rls_partes`
(tabela que liga duas empresas por desenho), `rls_busca_*`, `rls_herdada` (escopo herdado do pai por função `SECURITY DEFINER` que só devolve um booleano, para não haver recursão entre políticas),
`rls_leitura_compartilhada` + `rls_dono_escreve` (o que o Shoal mostra a todos, gravado só pelo dono), `rls_privilegiado` (plataforma e sistema, em todas as tabelas protegidas) e políticas avulsas
por tabela (`POLITICAS_ESPECIAIS_ETAPA2`: licença do tenant que paga, registro de oportunidade na rede, remoção de reposts, visibilidade do relacionamento comercial, convite de fornecedor…).
As funções `SECURITY DEFINER` que devolvem dado de outra empresa devolvem o mínimo: `b2bon_nome_do_autor` (só o nome, só de quem tem post ou comentário) e `b2bon_oferta_principal` (só nome e
descrição, só de perfil que o diretório mostraria).

## 2. Papéis no PostgreSQL

| Papel | Uso | Requisitos |
|---|---|---|
| **dono** (hoje o usuário da connection string do Neon) | migrações Alembic e operação de banco | dono das tabelas; **não** é usado pela aplicação depois do rollout |
| **`b2bon_app`** (execução) | a API e os jobs | `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, sem DDL, sem `TRUNCATE`, sem acesso a `alembic_version` |

- O RLS vale para quem **não é dono** das tabelas. Por isso `FORCE ROW LEVEL SECURITY` **não** foi usado: com `FORCE`, o dono (migrações com `UPDATE` de dados, manutenção, backup lógico) também ficaria preso às políticas.
- No Neon, o papel criado pelo console costuma ter `BYPASSRLS` (herdado de `neon_superuser`). **Não use esse papel na aplicação**; crie `b2bon_app` com o SQL abaixo.
- Variáveis de ambiente: `DATABASE_URL` = papel de execução; `MIGRATION_DATABASE_URL` = papel dono (só o Alembic usa; vazio = usa `DATABASE_URL`).

## 3. Rollout (nesta ordem, primeiro em staging)

> Executado em 29/10/2026: staging com o roteiro de leitura, produção com o papel `b2bon_app` (deploy das 19:55 UTC). Registro e ressalvas em D-112; passo a passo da produção em `RLS_PRODUCAO_PASSO_A_PASSO.md`.

1. **Aplicar as migrações** `e7a9c1d3f5b8` (primeira etapa) e `a3c5e7b9d1f2` (segunda etapa) com o papel dono (`alembic upgrade head`). Criam as funções e as políticas e ligam o RLS nas tabelas protegidas. Sem efeito enquanto a API usar o dono.
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
- **Voltar só a segunda etapa:** `alembic downgrade e7a9c1d3f5b8` com o papel dono (as 98 tabelas novas ficam sem política e sem RLS; as da primeira só perdem `rls_privilegiado`).
- **Remover todas as políticas:** `alembic downgrade d4f6a8c0e2b4` com o papel dono (remove as políticas `rls_*`, desliga o RLS e apaga as funções `b2bon_*`).
- O papel `b2bon_app` pode ficar (sem políticas ele é só um papel de leitura/escrita comum) ou ser removido com `DROP OWNED BY b2bon_app; DROP ROLE b2bon_app;`.

## 5. Verificação automática

- `tests/integration/test_rls_postgres.py` (PostgreSQL real, `B2BON_TESTE_PG_URL`): dois tenants, leitura/inserção/atualização/exclusão, escopo herdado, sem contexto, hierarquia, busca pré-tenant,
  contexto de sistema, tabela de duas partes, reaproveitamento da mesma conexão depois de `commit`, `rollback` e erro. No CI roda no job `postgres-migrations`.
- `tests/integration/test_rls_postgres_etapa2.py` (PostgreSQL real): `usuario` e suas buscas, hierarquia (só leitura), contextos privilegiados, licença do tenant que paga, feed e remoção de reposts,
  notificação entre empresas (inserir sem `RETURNING`), relacionamento comercial por visibilidade, filhos de sala, registro de oportunidade na rede, vitrine do diretório.
- **Testes HTTP contra PostgreSQL com RLS** (`B2BON_TESTE_PG_RLS_URL=postgresql+psycopg://<superusuário>@host/postgres python -m pytest tests/integration`): o `conftest.py` cria um banco descartável, aplica
  `alembic upgrade head` e cria o papel de execução; o teste semeia e confere com o dono (sem chave estrangeira, como no SQLite) e cada requisição usa uma sessão do papel restrito. Pega o que a sonda não vê:
  consulta que, sob o RLS, devolve menos linhas sem dar erro. Rodou em D-111 e achou três bugs reais (o `INSERT` de notificação com `RETURNING`, a identidade de rede do outro lado e a demonstração reservada);
  as falhas que sobram são do próprio modo (id inexistente sob chave estrangeira, SQL de SQLite, gatilhos desligados no semeio) e a categoria "404 em vez de 403" abaixo.
- `tests/unit/test_rls_registro.py`: toda tabela do modelo está classificada (protegida, pendente com motivo ou global) e o registro bate com o que cada migração cria.
- `tests/unit/test_rls_contexto.py`: o mecanismo de contexto, sem banco.
- **Sonda** (`tests/rls_sonda.py`, `B2BON_RLS_SONDA=<arquivo.json>`): roda a suíte inteira marcando, nas requisições HTTP, toda consulta a tabela protegida sem o contexto exigido, leitura de outro tenant e escrita
  em outro tenant. É a ferramenta usada para decidir quais tabelas já podem ser protegidas e para ampliar a cobertura nas próximas etapas. O SQLite **não** prova enforcement; a sonda aponta lacunas, o PostgreSQL prova.

## 6. Matriz de cobertura por tabela

Total de tabelas do modelo: **212**. Protegidas com política: **179** (81 na primeira etapa, 98 na segunda). Pendentes (sem política): **0**.
Globais (sem escopo de empresa): **33**. O teste `test_rls_registro.py` impede que o registro fique diferente das migrações e que o modelo tenha tabela sem classificação, e
`test_o_registro_bate_com_o_que_o_banco_tem` confere no PostgreSQL que o RLS está ligado em exatamente as tabelas protegidas. Todas as protegidas também têm `rls_privilegiado` (plataforma e sistema).

### Primeira etapa (D-110, migração `e7a9c1d3f5b8`)

Por tenant direto (`rls_tenant` + leitura ampliada pela hierarquia): `alerta_credito`, `alerta_detrator`, `anexo_sourcing`, `aprovacao`, `avaliacao_sourcing`, `bloqueio_contato`, `cadencia`, `campanha`, `chave_api_tenant`, `compra_credito`, `conexao_integracao`, `conexao_linkedin`, `configuracao_canal`, `configuracao_comunicacao`, `configuracao_envio`, `configuracao_notificacao`, `configuracao_nps`, `configuracao_qualificacao`, `configuracao_whatsapp`, `conversa_qualificacao`, `convite_cadastro`, `custo_aquisicao`, `custo_direto_infra`, `decisao_go_no_go`, `demanda_compra`, `descarte_conta`, `documento_cofre`, `documento_ri`, `email_direto`, `email_recebido`, `enriquecimento_nota_fiscal`, `enriquecimento_semanal_consumo`, `envio_crm`, `esclarecimento_sourcing`, `estado_alertas_licitacao`, `estagio_funil`, `evento_aprendizado`, `execucao_sync`, `faq_item`, `fornecedor_compras`, `indicacao`, `indicador_financeiro_conta`, `indicador_ri`, `item_pca`, `item_template_proposta`, `link_captura_lead`, `lista_prospeccao`, `material_oferta`, `mensagem`, `negocio`, `notificacao_vendedor`, `orgao_publico`, `pagamento_licenca`, `pausa_canal`, `perfil_inteligencia`, `pesquisa_decisores`, `pesquisa_decisores_empresa`, `pesquisa_decisores_transicao`, `pesquisa_nps`, `pesquisa_preco`, `plano_contratacao`, `proposta_negocio`, `qualificacao_score`, `recebimento_governo`, `registro_crm_externo`, `registro_envio_diario`, `registro_idempotencia`, `registro_reputacao_canal`, `registro_supressao_permanente`, `regra_aprendida`, `regra_auto_aprovacao`, `tarefa_linkedin`, `template_proposta`, `template_whatsapp`, `toque_cadencia`, `turno_conversa`, `unidade_compras`, `vinculo_externo`.

Duas partes (`rls_partes`): `conexao_empresa` (tenant_id_origem, tenant_id_destino), `mensagem_rede_social` (tenant_id_remetente, tenant_id_destinatario), `sala_corporativa` (tenant_id_a, tenant_id_b).

### Segunda etapa (D-111, migração `a3c5e7b9d1f2`)

**Por tenant direto** (74): `alerta_licitacao`, `apuracao_comissao`, `assinatura_webhook_parceiro`, `assinatura_webhook_tenant`, `atividade`, `audit_log`, `autorizacao_oauth_pendente`, `cache_resposta_ia`, `campanha_destinatario`, `carteira_creditos`, `chave_api_parceiro`, `coleta_site_conta`, `comissao_representante`, `componente_contrato_governo`, `configuracao_agente_corporativo`, `configuracao_coleta_fonte`, `configuracao_credito_tenant`, `configuracao_email_api`, `configuracao_email_smtp`, `configuracao_painel`, `configuracao_relatorio`, `conhecimento_corporativo`, `conta`, `conta_franquia_consumo`, `conteudo_pagina_site`, `contrato_compra`, `contrato_governo`, `contrato_sourcing`, `contrato_venda_publica`, `decisor`, `documento_compras`, `documento_licitacao`, `documento_sourcing`, `enriquecimento_carteira`, `enriquecimento_compra`, `enriquecimento_estorno_compra`, `enriquecimento_movimento`, `entrega_webhook`, `evento_contrato_compra`, `evento_contrato_sourcing`, `evento_dominio`, `evento_processo`, `evento_sourcing`, `execucao_coleta_fonte`, `execucao_ia`, `fila_enriquecimento_conta`, `icp`, `interacao_conta`, `interacao_tenant`, `item_sourcing`, `licenca`, `licitacao`, `lote_credito`, `movimento_credito`, `necessidade_oportunidade`, `notificacao_rede_social`, `oferta`, `orcamento_ia`, `participante_sourcing`, `periodo_assinatura_governo`, `processo_contratacao`, `processo_sourcing`, `proposta_item_sourcing`, `proposta_sourcing`, `registro_oportunidade`, `registro_uso_ia`, `regra_alerta_licitacao`, `requisito_licitacao`, `requisito_sourcing`, `reuniao`, `sinal_oportunidade`, `solicitacao_desconto`, `usuario`, `verificacao_empresa`.

**Com `tenant_id` nulo** (a linha sem dono é de plataforma): `empresa_rede`, `enriquecimento_config_plano`, `oportunidade_governo`. `enriquecimento_config_plano` ganha leitura da linha sem dono (padrão do plano) por todo tenant;
`empresa_rede` é o cadastro público de identidades da rede (qualquer tenant lê, cria e ajusta; apagar só os contextos privilegiados).

**Dono em outra coluna**: `sala_compra` (tenant_id_vendedor).

**Duas partes**: `convite_vitrine` (tenant_id_origem, tenant_id_gerado), `seguidor_empresa` (tenant_id_seguidor, tenant_id_seguido), `relacionamento_empresarial` (tenant_id_origem, tenant_id_destino), `pergunta_agente_corporativo` (tenant_id_alvo, tenant_id_perguntante).

**Leitura compartilhada** (qualquer tenant lê, só o dono grava; a visibilidade fina segue nos filtros do código): `comentario_post`, `intent`, `perfil_empresa`, `post_rede_social`, `reacao_post`.

**Escopo herdado** (tabela -> coluna do pai, função): `midia_post` (post_id, `b2bon_post_cascata_do_tenant`); `campo_enriquecido` (conta_id, `b2bon_conta_do_tenant`); `redefinicao_senha` (usuario_id, `b2bon_usuario_do_tenant`); `evento_webhook_parceiro` (assinatura_id, `b2bon_assinatura_parceiro_do_tenant`); `canal_sala` (sala_id, `b2bon_sala_do_tenant`); `mensagem_sala` (canal_id, `b2bon_canal_do_tenant`); `documento_sala` (sala_id, `b2bon_sala_do_tenant`); `participante_sala` (sala_id, `b2bon_sala_do_tenant`); `reuniao_sala` (sala_id, `b2bon_sala_do_tenant`); `stakeholder_sala` (sala_id, `b2bon_sala_do_tenant`); `tarefa_sala` (sala_id, `b2bon_sala_do_tenant`).

**Políticas avulsas**: `comentario_post`, `empresa_rede`, `enriquecimento_config_plano`, `licenca`, `notificacao_rede_social`, `participante_sourcing`, `post_rede_social`, `processo_sourcing`, `reacao_post`, `registro_oportunidade`, `relacionamento_empresarial`, `sala_compra`.

### Buscas antes de saber o tenant (política só de `SELECT`, pela chave)

| Escopo | Tabela | Condição |
|---|---|---|
| `autenticacao` | `usuario` | `id::text = b2bon_chave()` |
| `captura-lead` | `link_captura_lead` | `codigo = b2bon_chave()` |
| `chave-api` | `chave_api_tenant` | `chave_hash = b2bon_chave()` |
| `chave-api-parceiro` | `chave_api_parceiro` | `chave_hash = b2bon_chave()` |
| `convite-cadastro` | `convite_cadastro` | `codigo = b2bon_chave()` |
| `convite-vitrine` | `convite_vitrine` | `codigo = b2bon_chave()` |
| `integracao-webhook` | `conexao_integracao` | `webhook_token_hash = b2bon_chave()` |
| `login` | `usuario` | `lower(email) = b2bon_chave()` |
| `pagamento-referencia` | `pagamento_licenca` | `id::text = b2bon_chave()` |
| `pagamento-referencia` | `compra_credito` | `id::text = b2bon_chave()` |
| `pagamento-referencia` | `enriquecimento_compra` | `id::text = b2bon_chave()` |
| `portal-fornecedor` | `participante_sourcing` | `token_hash = b2bon_chave()` |
| `recall-bot` | `reuniao` | `bot_id = b2bon_chave()` |
| `redefinicao` | `redefinicao_senha` | `token = b2bon_chave()` |
| `redefinicao` | `usuario` | `b2bon_usuario_tem_redefinicao(id)` |
| `whatsapp-numero` | `configuracao_whatsapp` | `phone_number_id = b2bon_chave()` |

### Pendentes: ainda dependem só dos filtros do código

Nenhuma.

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

- **Contextos privilegiados (`plataforma` e `sistema:*`) têm acesso total.** O RLS protege a API usada por usuários de empresas (a superfície de ataque comum), não as rotas de `super_admin`, o cron, os
  webhooks depois da assinatura/segredo conferidos e a gestão comercial do MAP. Nesses caminhos o isolamento continua nos filtros do código. Para impedir que um contexto privilegiado apareça por
  engano, o nome do contexto de sistema precisa estar em `rls_registro.CONTEXTOS_SISTEMA` e `plataforma` só é fixado em `deps.exigir_papel` (rota exclusiva de super_admin), `deps.exigir_gestor_do_tenant`
  (super_admin) e `map_performance` (quem passa em `acesso`).
- **Leitura compartilhada do Shoal é mais larga que a regra da aplicação.** Posts, comentários, reações, necessidades (`intent`) e perfis são legíveis por qualquer tenant no banco; a regra fina
  (`publica` x `conexoes`, bloqueio entre empresas) continua no código. O banco só garante que uma empresa não grave nem apague o que é de outra (exceto o autor do original apagar os reposts).
- **Cruzamentos entre empresas dependem da conferência da aplicação.** Agente corporativo, portal do fornecedor convidado, tenant filho, solicitação de desconto e chave de parceiro abrem o contexto do
  tenant-alvo DEPOIS de o código conferir a relação (conexão aceita, convite, árvore, rede). O banco não repete essa conferência.
- **O RLS não protege contra SQL arbitrário** executado pela própria aplicação (injeção de SQL): as variáveis de sessão são escritas pelo backend. Ele cobre o erro de código que esquece o filtro, que é o risco de A01.
- **Leitura negada não dá erro.** Uma consulta que deveria enxergar outro tenant e não ampliou a leitura devolve zero linhas, sem aviso (a sonda só aponta o que carregou linha de outro tenant; ausência não aparece).
  Foi o caso de `saude_conta._obter_conta`, que consultava antes de ampliar a leitura, e dos relatórios gerenciais; ao criar fluxo novo entre tenants, ampliar a leitura ANTES de consultar.
- **Comportamento visível diferente:** com a API no papel restrito, quem NÃO é parte de uma sala corporativa recebe **404** (o banco esconde a sala) em vez de **403**. Não há acesso em nenhum dos dois casos;
  os testes aceitam os dois. O mesmo vale para qualquer rota que antes achava a linha de outra empresa para só depois recusar: agora a linha nem aparece.
- **Custo:** um `SELECT set_config(...)` extra por transação e mais um a cada troca de contexto dentro da requisição (agente corporativo, tenant filho). Medido no staging: sem diferença visível.
- **Cobertura medida pelos testes:** caminhos que nenhum teste exercita podem faltar contexto. Por isso o rollout é primeiro em staging e a reversão é só voltar a `DATABASE_URL` ao papel dono.
- **A01 foi encerrado em 29/10/2026 (D-112)** com a aplicação rodando em produção com o papel de execução, **sem** a janela de observação de 24 a 48 horas prevista e sem o roteiro completo de escrita em
  staging (Shoal, Aprovações, Configuração, Registro de Oportunidade e atribuição de vendedor ficaram de fora). Tela vazia ou com zeros onde antes havia dado é o sintoma a procurar; a reversão é voltar `DATABASE_URL` ao papel dono.
