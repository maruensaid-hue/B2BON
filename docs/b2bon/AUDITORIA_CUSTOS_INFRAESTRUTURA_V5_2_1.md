# Auditoria de custos e infraestrutura — V5.2.1 (2026-10-20)

**Limite desta auditoria.** Não tenho acesso a faturas, painéis (Render, Neon, Sentry, SendGrid, Redis, Meta, Mercado Pago) nem a variáveis de ambiente de produção. Por isso cada informação abaixo é classificada:

- **[Repo]** declarado em arquivo do projeto, verificável;
- **[Medido]** medido por mim, localmente, com o comando indicado;
- **[Informado]** dito no prompt/memória do projeto, não verificável por mim;
- **[Hipótese]** inferência que precisa de confirmação no painel.

**Nenhum valor monetário foi inventado.** Onde falta o preço, a coluna diz "confirmar no painel" e o §5 diz onde olhar.

## 1. Inventário

| Recurso | Para que serve | O que o repositório prova | Custo / plano |
|---|---|---|---|
| **Render — API** `b2bon-api` | API FastAPI em Docker | `plan: free`, health check `/health` [Repo] (`render.yaml`). A memória do projeto registra que o plano Free foi **mantido** após o incidente de cold start de 19/10 [Informado]. | Prompt diz "cobrança mensal" [Informado] — **não confirmo**: o `render.yaml` declara `free`. Confirmar no painel se a cobrança é de outro serviço (static site, Key Value/Redis, domínio) |
| **Render — Static Site** `B2BON` | Frontend (build Vite) | tipo `static` com rewrite SPA [Repo] | idem |
| **Neon (Postgres)** | Banco de produção + branch de staging (cópia) | `DEPLOY.md`: cota de armazenamento estourou em 2026-09-11 e o plano foi elevado; `STAGING.md`: staging é um branch com dados reais [Repo] | plano atual e valor: **confirmar no painel** |
| **Redis gerenciado** | Rate limit compartilhado — `REDIS_URL` é **obrigatório em produção** (a API recusa subir sem ele: `validar_segredos_de_producao`) [Repo] | `DEPLOY.md` manda "provisionar instância Redis gerenciada", mas **não está no `render.yaml`** [Repo] | **fornecedor e plano desconhecidos** — é o único item de infraestrutura obrigatório sem declaração no repositório |
| **Sentry** | Erros e traces | DSN opcional; `traces_sample_rate=0.1` [Repo] | plano: confirmar |
| **E-mail transacional** | Cadências, convites, cobrança | **SendGrid** (`sendgrid_api_key`) ou SMTP por tenant [Repo]. "Sender Authentication" no `DEPLOY.md` é recurso do SendGrid. O "Sender" citado no prompt **não corresponde a nenhuma integração do código** — confirmar se é outro serviço contratado e não usado | plano SendGrid: confirmar |
| **Anthropic API** | Todas as chamadas de IA (única integrada para uso real) | Gateway único com orçamento, créditos, cache (tenant na chave) e *cost guard* [Repo] | pré-pago por token; consumo em `registro_uso_ia`/`execucao_ia` (ver §3) |
| **GitHub Actions** | CI + crons | **Repositório público** [Medido: API do GitHub devolve `private:false`] → minutos de Actions **gratuitos** | R$ 0 enquanto o repositório for público |
| Neo4j Aura | Grafo | instância **deletada** em 2026-09-08 [Informado/Repo `DISASTER_RECOVERY.md`]; o código ainda tem o cliente | R$ 0; ver oportunidade O6 |
| Lusha / Brave Search | Enriquecimento de contato / busca web | variáveis `contact_enrichment_api_key`, `brave_search_api_key` [Repo] | pago por uso; controlado por franquia do plano |
| Meta WhatsApp Cloud API | Mensagens | `whatsapp_*` [Repo] | cobrança por conversa/template pela Meta |
| Mercado Pago | Cobrança de licença | `mercadopago_*` [Repo] | taxa por transação |
| Recall.ai | Bot de reunião/transcrição | `recall_api_key` [Repo]; "falta validar API real" [memória] | pago por hora; verificar se está contratado |
| Cloudflare Workers | Proxy do frontend (produção publicada à mão) | [memória] | confirmar plano |
| HostGator | WordPress legado do domínio `ovendedortubarao.com.br` | [memória] achado em 2026-09-08 | hospedagem paga provável; ver O7 |
| Demonstração pública | Ambientes semeados sob demanda | `demo_habilitada=False` por padrão; reserva de 3 ambientes semeados [Repo] | custo é de banco/CPU; confirmar se está ligada em produção |

## 2. O que medi (reprodutível)

**Consumo gerado pelos crons em repouso** (GitHub Actions → API → Neon). Medido com contador de instruções SQL (`before_cursor_execute`) chamando as 7 rotas que rodam a cada 15 minutos, sem trabalho pendente:

| Cenário | Instruções SQL por ciclo (7 rotas) |
|---|---|
| 1 tenant real | **58** (envios 18, campanhas 14, retorno 20, eventos 2, CRM 2, webhooks 1, enriquecimento 1) |
| 20 tenants | **552** (envios 189, campanhas 147, retorno 210) |

Crescimento linear: **~26 instruções por tenant por ciclo**, só para descobrir que não há nada a fazer. Com 96 ciclos/dia isso é ~2.500 consultas/tenant/dia ociosas (100 tenants ≈ 250 mil/dia).

*O que isso custa de fato:* o plano do Neon cobra tempo de computação e armazenamento, **não** quantidade de consultas. Como o ciclo de 15 min já impede que o banco "durma" [Hipótese: o Neon suspende por inatividade e cada ciclo o acorda — confirmar no painel o *compute time*], reduzir consultas ociosas não reduz a fatura sozinho; reduz latência e CPU da instância Free (que é compartilhada com a API).

**Frequência dos agendamentos** [Repo, `cron-envios.yml`]: 7 chamadas/15 min (672/dia), recorte de CNPJ a cada 30 min (48 execuções/dia, instala dependências e fala com o Neon), créditos de IA a cada hora, coleta PNCP a cada 6 h (desligada), diária para retenção/LGPD/comissões. Comentário do próprio arquivo: o ciclo de 15 min também **mantém o Render Free acordado** — é uma decisão funcional, não só de custo.

**Armazenamento (principal vetor de custo do Neon)** [Medido nos modelos]: 10 colunas binárias guardam arquivos **dentro do Postgres** (`documento_licitacao`, `documento_sourcing`, `documento_compras`, `documento_cofre`, `documento_sala`, `anexo_sourcing`, `proposta_negocio`, `material_oferta`, `midia_post`, `template_proposta.logo`). Tabelas de crescimento contínuo **sem poda por idade** antes desta auditoria: `evento_dominio` (outbox), `entrega_webhook`; com política de conformidade que **não** deve ser podada por custo: `audit_log`, ledger de IA, `execucao_ia`.

## 3. Consumo de IA (o que o código mede)

O gateway registra tokens, custo em USD (preço versionado por modelo) e créditos por execução; há orçamento por tenant, limite por hora, cache de respostas (24 h configurável), *cost guard* que troca para classe de modelo mais barata e bloqueia estimativa acima do teto do workload. **Não há dado real de consumo neste ambiente** (base local sem uso de produção), então não estimo gasto mensal. Para obter: `GET /finops/meu-uso` (admin) e `GET /finops/economia` (super admin) em produção.

## 4. Matriz de oportunidades

### 4.1 Economia de baixo risco — **implementado localmente nesta fase**

| ID | Mudança | Evidência | Efeito |
|---|---|---|---|
| E1 | **Sentry: não amostrar crons nem `/health`** (`amostrar_traces` em `app/core/observability.py`; erros continuam sendo capturados) | 672 chamadas/dia dos crons + health check são a maior parte do tráfego da API; antes todas eram amostradas a 10% [Repo] | menos transações contra a cota do Sentry; **efeito monetário depende do plano — confirmar** |
| E2 | **Retenção de `evento_dominio` processado (60 dias) e `entrega_webhook` concluída (90 dias)** na poda diária existente | só o processador lê o outbox, uma vez; entrega pendente e evento não processado **nunca** são apagados; configurável | evita crescimento ilimitado do banco; 5 testes novos |

Já feito na V5.2 e continua valendo: poda do cache de IA vencido, execuções de coleta e coletas de site (§ `retencao_historicos_service`).

### 4.2 Otimização que exige teste ou alteração arquitetural — **não implementada**, com a razão

| ID | Oportunidade | Por que não fiz agora | Como fazer |
|---|---|---|---|
| O1 | **Pular tenants sem pendência nos crons** (reduz ~26 consultas/tenant/ciclo ociosas) | Muda comportamento protegido por teste: hoje uma credencial quebrada de um tenant é detectada e registrada a cada ciclo **mesmo sem fila** (`tenants_com_falha`). Pular silenciosamente perderia essa detecção | pré-consulta única de tenants com pendência + checagem de credencial 1×/dia; precisa de decisão sobre a regra de detecção |
| O2 | **Mover binários do Postgres para armazenamento de objetos** (R2/S3) | Decisão com custo e LGPD (a memória do projeto manda **perguntar antes** de escolher storage externo para upload); migração de dados | escolher provedor; copiar por lote; manter hash no banco |
| O3 | **Reduzir o recorte de CNPJ de 30 para 60 min ou por demanda** | Pedido explícito anterior do usuário (reduzir a espera de ICP novo); custo hoje é R$ 0 (Actions público) mas conecta ao Neon 48×/dia | só se o Neon cobrar por *compute time*; medir antes |
| O4 | **Cron de 15 min por gatilho** (acordar quando houver mensagem agendada) | Perde o efeito de manter o Render Free acordado, que é o que mitigou o incidente de login de 19/10 | só junto com plano pago do Render (sem spin-down) |
| O5 | **Substituir Redis por limitador em Postgres** | Hoje o boot em produção **exige** Redis; trocar enfraquece o rate limit sob carga e muda a regra de segurança | só se o Redis for um custo relevante (**fornecedor desconhecido**) |
| O6 | Remover o cliente Neo4j do código | Sem custo ativo (instância deletada); é dívida técnica, não economia | limpeza de código quando o grafo for descartado |

### 4.3 Depende de autorização, credenciais ou intervenção em produção — **não tocado**

| ID | Item | Ação necessária |
|---|---|---|
| A1 | Confirmar plano e fatura de Render, Neon, Sentry, SendGrid, Redis | olhar os painéis (ver §5) |
| A2 | "Sender" do prompt não existe no código | confirmar se é um serviço pago sem uso (candidato a cancelamento) |
| A3 | O7: **HostGator** (WordPress legado, sem DMARC, já alvo de spam de formulário) | decidir migrar/encerrar; risco de segurança além do custo |
| A4 | Recall.ai, Lusha, Brave | confirmar se estão contratados e usados |
| A5 | Plano Render pago para a API (elimina cold start e a dependência do cron de 15 min como "mantenedor") | decisão de custo do PO; já registrada como mantido em Free |
| A6 | Demonstração pública em produção (`DEMO_HABILITADA`) | confirmar se está ligada e quantas reservas |

Não recomendo cortar monitoramento (Sentry), backups (PITR do Neon) nem controles de segurança (Redis do rate limit) para economizar.

## 5. Onde confirmar cada valor (sem eu inventar)

| Item | Onde |
|---|---|
| Render | Dashboard → *Billing* e a aba de cada serviço (plano) |
| Neon | Console → *Billing* e *Usage* (compute hours e *storage*); ver também o tamanho por tabela com `SELECT relname, pg_total_relation_size(relid) FROM pg_catalog.pg_statio_user_tables ORDER BY 2 DESC` |
| Sentry | *Settings → Subscription* e *Stats* (transações e erros aceitos/descartados) |
| SendGrid | *Settings → Plan & Billing* e *Stats* |
| Redis | o provedor onde `REDIS_URL` aponta (host na própria URL, sem expor credencial) |
| IA | `GET /finops/meu-uso`, `GET /finops/economia`; console da Anthropic para a fatura real |
| GitHub Actions | *Settings → Billing → Actions* (esperado: R$ 0) |
