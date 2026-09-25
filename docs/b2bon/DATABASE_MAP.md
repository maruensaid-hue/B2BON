# DATABASE MAP — Fase 0 (2026-09-25)

Gerado a partir de `Base.metadata` (importando `app.models` e
`app/providers/account_data/receita_federal_models.py`) no HEAD `93dede8`.
Migrações: 71 revisões Alembic em `alembic/versions/`, com cabeça única
(validada por `tests/test_alembic_upgrade.py`).

- **Motor**: Postgres (Neon) em produção, SQLite em dev/test. O mesmo
  código precisa rodar nos dois; já houve incidente de literal inteiro
  em coluna boolean (commit `943c3df`).
- **Tenancy**: coluna `tenant_id` (ou `tenant_id_origem`/`_destino`/
  `_vendedor`/…) filtrada no código. **Sem RLS.**
- **Grafo**: Neo4j espelha `Conta`/`Decisor`/interação/indicação
  (`neo4j_node_id` em `conta`/`decisor`), em modo best-effort. O
  relacional é a fonte de verdade.
- **Sem pgvector/embeddings.**

## 1. Tabelas sem coluna `tenant_id*` (12)

| Tabela | Escopo real | Risco |
|---|---|---|
| `tenant`, `plano`, `rotulo_tipo_tenant` | globais por natureza | — |
| `cnpj_estabelecimento`, `cnpj_socio`, `recorte_cnpj_estado` | dado público nacional (Receita Federal) | — |
| `cache_mercado_externo` | cache global (cotação/notícias) | — |
| `registro_tratamento` | ROPA da plataforma (LGPD), mantido pelo Admin B2B ON | — |
| `campo_enriquecido` | herda de `conta` (FK) | isolamento depende de sempre fazer join com `conta` |
| `canal_sala` | herda de `sala_corporativa` (FK) | idem |
| `midia_post` | herda de `post_rede_social` (FK) | idem |
| `redefinicao_senha` | herda de `usuario` (FK) | idem |

O `SECURITY_BOUNDARIES.md` de raiz diz que o staging de CNPJ é a
"única tabela sem `tenant_id`". **Isso está incorreto** (ver §1 acima).

## 2. Agrupamento por domínio

| Domínio | Tabelas |
|---|---|
| Núcleo / tenancy / billing | tenant, usuario, plano, licenca, pagamento_licenca, convite_cadastro, convite_vitrine, rotulo_tipo_tenant, solicitacao_desconto, redefinicao_senha, conta_franquia_consumo, enriquecimento_semanal_consumo |
| CRM | conta, decisor, negocio, estagio_funil, atividade, proposta_negocio, template_proposta (+itens), descarte_conta, custo_aquisicao |
| MAP | interacao_conta, interacao_tenant, alerta_detrator (NPS detrator), configuracao_painel |
| PREDATOR — prospecção | icp, lista_prospeccao, fila_enriquecimento_conta, campo_enriquecido, oferta, material_oferta, cnpj_* , recorte_cnpj_estado |
| PREDATOR — engajamento | cadencia, toque_cadencia, mensagem, aprovacao, regra_auto_aprovacao, campanha, campanha_destinatario, pausa_canal, registro_envio_diario, registro_reputacao_canal, tarefa_linkedin, conexao_linkedin, email_direto, email_recebido, template_whatsapp |
| PREDATOR — qualificação/reunião | conversa_qualificacao, turno_conversa, qualificacao_score, configuracao_qualificacao, reuniao, pesquisa_nps, configuracao_nps, faq_item |
| PREDATOR — inteligência | regra_aprendida, sinal_oportunidade, configuracao_agente_corporativo, pergunta_agente_corporativo, registro_oportunidade, indicacao |
| Shoal (Business Network) | perfil_empresa, verificacao_empresa, conexao_empresa, seguidor_empresa, mensagem_rede_social, post_rede_social, midia_post, comentario_post, reacao_post, notificacao_rede_social, intent, relacionamento_empresarial, sala_corporativa, canal_sala, mensagem_sala, sala_compra |
| Configuração de canal | configuracao_whatsapp, configuracao_email_smtp, configuracao_comunicacao, configuracao_canal, configuracao_envio, configuracao_notificacao, configuracao_relatorio |
| IA | registro_uso_ia (ledger parcial — ver `AI_CURRENT_STATE.md`) |
| Compliance / auditoria | audit_log, registro_tratamento, registro_supressao_permanente |
| Parceiros | chave_api_parceiro, assinatura_webhook_parceiro, evento_webhook_parceiro |
| Notificação | notificacao_vendedor |
| Cache | cache_mercado_externo |

**Fase 2:** nova tabela `evento_dominio` (outbox de eventos, `tenant_id` + FK). Total: 93 tabelas.

**Fase 3:** `chave_api_tenant`, `registro_idempotencia`, `assinatura_webhook_tenant`, `entrega_webhook`, `conexao_integracao`, `execucao_sync` (todas com `tenant_id`; segredos/credenciais com Fernet). Total: 99 tabelas.

**Fase 4:** `conhecimento_corporativo`, `perfil_inteligencia`, `evento_aprendizado`; `registro_uso_ia` ganhou 12 colunas. Total: 102 tabelas.

Nenhuma tabela de Procurement, Bid, Credit Wallet, Usage Ledger
completo, Entitlement, Integration Registry ou vetores existe.

## 3. Inventário completo

`FKs` lista as tabelas referenciadas, exceto `tenant`.

| Tabela | Colunas | Coluna(s) tenant | FKs |
|---|---|---|---|
| `alerta_detrator` | 8 | tenant_id | conta, decisor, pesquisa_nps |
| `aprovacao` | 7 | tenant_id | mensagem |
| `atividade` | 8 | tenant_id | conta, negocio, usuario |
| `audit_log` | 10 | tenant_id | — |
| `cache_mercado_externo` | 3 | **—** | — |
| `cadencia` | 12 | tenant_id | conta, icp, oferta |
| `campanha` | 11 | tenant_id | — |
| `campanha_destinatario` | 13 | tenant_id | campanha, decisor |
| `campo_enriquecido` | 6 | **—** | conta |
| `canal_sala` | 7 | **—** | sala_corporativa |
| `cnpj_estabelecimento` | 12 | **—** | — |
| `cnpj_socio` | 5 | **—** | — |
| `comentario_post` | 6 | tenant_id | post_rede_social, usuario |
| `conexao_empresa` | 6 | tenant_id_origem, tenant_id_destino | — |
| `conexao_linkedin` | 10 | tenant_id | usuario |
| `configuracao_agente_corporativo` | 5 | tenant_id | — |
| `configuracao_canal` | 4 | tenant_id | — |
| `configuracao_comunicacao` | 6 | tenant_id | — |
| `configuracao_email_smtp` | 9 | tenant_id | — |
| `configuracao_envio` | 9 | tenant_id | — |
| `configuracao_notificacao` | 6 | tenant_id | — |
| `configuracao_nps` | 4 | tenant_id | — |
| `configuracao_painel` | 4 | tenant_id | — |
| `configuracao_qualificacao` | 5 | tenant_id | — |
| `configuracao_whatsapp` | 7 | tenant_id | — |
| `conta` | 27 | tenant_id | icp, lista_prospeccao, usuario |
| `conta_franquia_consumo` | 5 | tenant_id | conta |
| `conversa_qualificacao` | 11 | tenant_id | conta, decisor |
| `convite_cadastro` | 9 | tenant_id | usuario |
| `convite_vitrine` | 9 | tenant_id_origem, tenant_id_gerado | usuario |
| `custo_aquisicao` | 4 | tenant_id | — |
| `decisor` | 15 | tenant_id | conta |
| `descarte_conta` | 8 | tenant_id | conta |
| `email_direto` | 12 | tenant_id | conta, decisor, usuario |
| `email_recebido` | 9 | tenant_id | conta, decisor |
| `enriquecimento_semanal_consumo` | 5 | tenant_id | — |
| `estagio_funil` | 5 | tenant_id | — |
| `faq_item` | 5 | tenant_id | — |
| `fila_enriquecimento_conta` | 7 | tenant_id | conta |
| `icp` | 16 | tenant_id | icp |
| `indicacao` | 13 | tenant_id | conta, decisor |
| `intent` | 14 | tenant_id | — |
| `interacao_conta` | 7 | tenant_id | conta, usuario |
| `interacao_tenant` | 6 | tenant_id | usuario |
| `item_template_proposta` | 7 | tenant_id | template_proposta |
| `licenca` | 8 | tenant_id | plano |
| `lista_prospeccao` | 7 | tenant_id | icp, usuario |
| `material_oferta` | 8 | tenant_id | oferta |
| `mensagem` | 19 | tenant_id | cadencia, decisor, toque_cadencia |
| `mensagem_rede_social` | 7 | tenant_id_remetente, tenant_id_destinatario | usuario |
| `mensagem_sala` | 7 | tenant_id_remetente | canal_sala, usuario |
| `midia_post` | 6 | **—** | post_rede_social |
| `negocio` | 17 | tenant_id | conta, decisor, estagio_funil, oferta, usuario |
| `notificacao_rede_social` | 8 | tenant_id | — |
| `notificacao_vendedor` | 7 | tenant_id | conversa_qualificacao |
| `oferta` | 11 | tenant_id | icp |
| `pagamento_licenca` | 9 | tenant_id | plano |
| `pausa_canal` | 6 | tenant_id | — |
| `perfil_empresa` | 20 | tenant_id | — |
| `pergunta_agente_corporativo` | 11 | tenant_id_alvo, tenant_id_perguntante | — |
| `pesquisa_nps` | 10 | tenant_id | conta, decisor |
| `plano` | 20 | **—** | — |
| `post_rede_social` | 8 | tenant_id | post_rede_social, usuario |
| `proposta_negocio` | 13 | tenant_id | negocio, usuario |
| `qualificacao_score` | 9 | tenant_id | conta, conversa_qualificacao, decisor |
| `reacao_post` | 6 | tenant_id | post_rede_social, usuario |
| `recorte_cnpj_estado` | 5 | **—** | — |
| `redefinicao_senha` | 6 | **—** | usuario |
| `registro_envio_diario` | 5 | tenant_id | — |
| `registro_oportunidade` | 11 | tenant_id | conta, usuario |
| `registro_reputacao_canal` | 7 | tenant_id | — |
| `registro_supressao_permanente` | 4 | tenant_id | — |
| `registro_tratamento` | 9 | **—** | — |
| `registro_uso_ia` | 10 | tenant_id | — |
| `regra_aprendida` | 9 | tenant_id | icp, oferta |
| `regra_auto_aprovacao` | 6 | tenant_id | — |
| `relacionamento_empresarial` | 9 | tenant_id_origem, tenant_id_destino | — |
| `reuniao` | 22 | tenant_id | conta, decisor, reuniao |
| `rotulo_tipo_tenant` | 2 | **—** | — |
| `sala_compra` | 6 | tenant_id_vendedor | negocio, sala_corporativa |
| `sala_corporativa` | 4 | tenant_id_a, tenant_id_b | — |
| `seguidor_empresa` | 4 | tenant_id_seguidor, tenant_id_seguido | — |
| `sinal_oportunidade` | 12 | tenant_id, tenant_id_alvo | conta |
| `solicitacao_desconto` | 11 | tenant_id | registro_oportunidade, usuario |
| `tarefa_linkedin` | 9 | tenant_id | decisor, mensagem |
| `template_proposta` | 9 | tenant_id | — |
| `template_whatsapp` | 6 | tenant_id | — |
| `tenant` | 9 | **—** | — |
| `toque_cadencia` | 8 | tenant_id | cadencia |
| `turno_conversa` | 6 | tenant_id | conversa_qualificacao |
| `usuario` | 17 | tenant_id | — |
| `verificacao_empresa` | 11 | tenant_id | — |
