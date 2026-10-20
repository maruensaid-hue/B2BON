# Auditoria de isolamento de tenant, rota a rota — V5.2.1 (2026-10-20)

Estados: **Concluído e validado** · **Implementado, aguardando validação externa** · **Parcial** · **Risco residual aceito**.
Nada foi publicado: sem push, sem deploy, sem alteração de produção.

## 1. Método (como cada número foi obtido)

| Etapa | Ferramenta | Resultado verificado |
|---|---|---|
| Inventário das rotas **efetivas** (inclui routers aninhados, que um `grep` de decorators não enxerga) | `scripts/qualidade/inventario_rotas.py` (percorre `effective_route_contexts()` do FastAPI e a árvore de dependências) | **662 rotas**: 587 por sessão, 15 por chave de API de parceiro, 60 públicas |
| Rotas públicas | `tests/test_rotas_publicas_aprovadas.py` (guarda de CI) | as 60 estão classificadas; rota pública nova sem classificação **quebra o CI** |
| Consultas sem filtro de tenant (todo o código de `app/`) | `scripts/qualidade/varredura_consultas_sem_tenant.py` (AST) | 146 modelos com `tenant_id`; 313 candidatos, **todos triados** (ver §4) |
| Ataque dinâmico em todas as rotas de sessão | `tests/integration/test_isolamento_sistematico.py` | **587 rotas, 1.857 requisições**, ids reais da vítima em caminho, query, corpo e termos de busca; **0 vazamentos, 0 alterações/exclusões/referências cruzadas no banco, 0 erros 5xx** |
| Controle positivo do detector | mesmo arquivo | o dono (B) acionando as mesmas rotas **é** detectado — sem isso o "zero" não valeria |
| Ataques dirigidos (corpos com regras próprias) | mesmo arquivo | conta, decisor, reunião, funil, interações, licitação, registro de oportunidade |
| Hierarquia pai/filho/irmão/estranho e chaves de parceiro | `tests/integration/test_isolamento_hierarquia.py` | 42 casos |

**Como a varredura dinâmica funciona.** O tenant B (vítima) recebe o seed de demonstração (CRM, prospecção, licitações) e conteúdo de rede; o tenant A (atacante) é um admin com licença e plano com todos os módulos, sem dados. A chama cada rota de sessão com ids reais de B. Dois detectores independentes: (1) comparação do **banco inteiro** antes/depois — qualquer linha de B alterada/excluída, ou linha nova que aponte por FK a objeto de B (resolvendo dono por `tenant_id` ou pela cadeia de FK), é violação; (2) busca de textos distintivos de B (nomes, e-mails, títulos) nas respostas 2xx entregues a A. Resultados da varredura (587 rotas de sessão): 225 negadas com 404 usando ids reais de B, 203 executadas sem vazamento, 114 negadas por papel (rotas de super admin), 45 recusadas por validação/regra de negócio do corpo (as de objeto delas têm teste dirigido ou revisão de código — §5).

Matriz completa, rota a rota: [MATRIZ_ISOLAMENTO_ROTAS.md](MATRIZ_ISOLAMENTO_ROTAS.md) (gerada; regenerar com o script).

## 2. Falhas encontradas (todas comprovadas por teste antes da correção) e correções

| # | Gravidade | Falha | Correção | Prova |
|---|---|---|---|---|
| F1 | **Crítica** | `POST /webhooks/whatsapp`, `/webhooks/email` e `/webhooks/reputacao` eram **públicos, sem segredo, com `tenant_id` no corpo**. Qualquer pessoa que conhecesse um `tenant_id` podia: registrar opt-out de qualquer contato do tenant, cancelar cadências, disparar IA e mensagens de WhatsApp do tenant, e **forçar a pausa automática do canal de e-mail** (`quantidade` arbitrária). Nenhum provedor real chama essas rotas. | Segredo interno `X-Webhook-Secret` (`WEBHOOK_INTERNO_SECRET`); vazio **nunca** autoriza (mesma regra do `CRON_SECRET`). | `test_seguranca_webhooks.py` (13): sem segredo/errado/não configurado → 403 e **nenhum efeito** (sem evento de reputação, sem pausa, decisor não suprimido) |
| F2 | **Alta** | `POST /webhooks/whatsapp/meta` não verificava a assinatura da Meta (`X-Hub-Signature-256`): o `phone_number_id` não é segredo e bastava um telefone de contato para forjar resposta/opt-out. | HMAC-SHA256 do corpo bruto com o App Secret (`WHATSAPP_APP_SECRET`), comparação em tempo constante; sem segredo → recusa (falha fechada, como SendGrid/Mercado Pago/Recall). | corpo sem assinatura, com segredo errado, adulterado depois de assinado e segredo vazio → 403; assinatura válida → 200 |
| F3 | **Alta** | `POST/PUT /bids/licitacoes` aceitavam `conta_id`, `oferta_id` e `responsavel_usuario_id` **de outro tenant** (201). O `go_no_go.recomendar` lia a oferta alheia (`ticket_medio` de B entrava na análise de A). Idem `criar_contrato` com `conta_id`. | `_validar_referencias` (404 se o objeto não for do tenant) em criar/atualizar/criar contrato; `go_no_go` passa a filtrar a oferta pelo tenant (defesa em profundidade; `conformidade` já filtrava). | `test_atacante_nao_cria_licitacao_apontando_para_conta_ou_oferta_de_b` |
| F4 | Média | `GET /rede-social/posts/{id}/comentarios` e `/midia/{id}` eram **públicos e enumeráveis por id** (exibem nome de pessoa e empresa dos comentaristas e a mídia), enquanto o feed exige login e esconde empresas bloqueadas. | Exigem sessão e seguem a regra de bloqueio do feed (404 igual ao de post inexistente). O frontend já baixava com requisição autenticada. | `test_post_rede_social.py` (+2) |
| F5 | Média/Baixa | `POST/PUT /ofertas` aceitavam `icp_id` de outro tenant (referência cruzada e oráculo de existência de ids; em Postgres o FK falharia só para id inexistente). | `_exigir_icp_do_tenant`. | `test_ofertas.py` (+3) |

**Ação obrigatória antes do deploy (F1/F2):** configurar `WHATSAPP_APP_SECRET` (App Secret do app da Meta) e `WEBHOOK_INTERNO_SECRET` no Render. Sem o primeiro, o webhook da Meta passa a responder 403 e as respostas/opt-outs recebidos por WhatsApp **deixam de ser processados** — é o custo deliberado de falhar fechado. Não foi alterado nenhum ambiente.

## 3. O que foi verificado e estava correto (sem mudança de código)

Tenant sempre derivado do JWT (`get_tenant_id`); nenhuma rota de sessão usa o tenant do cliente como identidade. Rotas que recebem `tenant_id` do cliente são só de `super_admin`, de hierarquia (`tenant_ids_no_escopo`) ou de conexão aceita. Salas corporativas (participação e escopo antes de entregar documento/tarefa), portal do fornecedor (posse de proposta/itens/requisitos), hub de integrações (token só por hash, `state` OAuth cifrado, 404 genérico), reivindicação de empresa (CNPJ e verificação), intents (visibilidade e bloqueio), registro de oportunidade, cache de respostas de IA (tenant na chave **e** na leitura), webhooks assinados (SendGrid, Mercado Pago, Recall), opt-out por token HMAC, captura de lead, API de parceiros (`_exigir_tenant_na_arvore` em todas as rotas).

## 4. Triagem das 313 consultas candidatas

A grande maioria é filha de um pai já validado por tenant na mesma função (`conexao.id`, `cadencia.id`, `aprovacao.mensagem_id`, `conta_ids` carregados com tenant); outra parte são módulos de plataforma exclusivos de `super_admin` (`finops`, `governo`, `comissoes`, `map/performance`) ou webhooks assinados e jobs de cron (a triagem foi manual, sem contagem por categoria); os pontos com id vindo direto do cliente foram lidos caso a caso (salas, identidade, registro de oportunidade, intents, saúde da conta) e estava correto. Os achados F3 e F5 vieram da varredura dinâmica, não da estática: a falha era **ausência de validação de uma referência vinda do cliente**, que nenhuma consulta isolada mostra.

## 5. Rotas que a varredura não exercita por validação de corpo (35) — disposição

| Tipo | Rotas | Disposição |
|---|---|---|
| Objeto de outro tenant no caminho/corpo | decisor `/papel`, `/reunioes/{id}/marcar-resultado`, `/crm/estagios/reordenar`, `/saude-contas/interacoes`, `/bids/licitacoes`, `/registro-oportunidade` | **teste dirigido** (passa) |
| Objeto por id, sem dados de B no seed | `/registro-oportunidade/{id}/status`, `/hub-integracoes/conexoes/{id}/status`, `/rede/convites-sourcing/{id}/*`, `/procurement/documentos`, `/campanhas` | **revisão de código**: escopo por tenant confirmado (`_obter_registro`+escopo, `_conexao_do_tenant`, `por_empresa`, `cadastros.obter(tenant)`, `filter_by(tenant_id)`) |
| Configuração do próprio tenant, sem id de objeto | `configuracao-*`, `template-proposta/*`, `chaves-api`, `webhooks-saida`, `painel/preferencias-dashboard`, `agente-corporativo/modo`, `inteligencia/conhecimento`, `finops/orcamentos`, `bids/cofre`, `bids/ingestao/pncp`, `linkedin/conexoes/importar`, `rede-social/posts` e `relacionamentos` | tenant vem do token; sem superfície de id estrangeiro |
| Token de uso único | `reunioes/reagendar/{token}`, `nps/responder/{token}`, `hub-integracoes/oauth/*` | token HMAC/`state` cifrado |

## 6. Riscos residuais (nenhum bloqueia a fase; todos precisam de decisão ou de ambiente que não tenho)

1. **Banco de teste é SQLite.** A varredura prova a lógica da aplicação; não prova comportamento de FK/colação do PostgreSQL. Roda no CI contra SQLite também. *Recomendação (decisão do PO):* avaliar **Row-Level Security** no Postgres/Neon como segunda camada — hoje o isolamento depende só do código.
2. **Um papel atacante na varredura (admin de outro tenant).** Hierarquia e chaves de parceiro têm testes próprios; o escopo **interno ao tenant** (vendedor `user` vs. admin) não foi reauditado nesta fase.
3. **Registro de oportunidade** aceita `conta_id` de qualquer tenant **da mesma rede** (irmãos/pai), por desenho (conflito de PRIME na rede inteira). Expõe só o id inteiro; confirmar com o PO se o escopo deve ser a sub-árvore.
4. **`POST /webhooks/email/inbound`** não tem assinatura (o Inbound Parse do SendGrid não assina); é protegido por token HMAC no endereço de resposta. Quem recebeu um e-mail do tenant conhece o token do próprio decisor e pode inserir uma "resposta" falsa para aquele decisor. Impacto limitado a um contato; mitigação possível: restringir o IP de origem do SendGrid no proxy.
5. Dados de B com texto curto/genérico podem não ser detectáveis pelo detector de respostas (só marca textos distintivos de ≥12 caracteres com espaço, `@` ou dígito); a comparação de banco não depende disso.

## 7. Como manter

Rota pública nova → classificar em `tests/test_rotas_publicas_aprovadas.py`. Rota nova que receba `tenant_id` do cliente sem `exigir_papel` → o mesmo arquivo falha. Qualquer rota nova de sessão entra automaticamente na varredura dinâmica. Regenerar a matriz: `ISOLAMENTO_RELATORIO=<json> pytest tests/integration/test_isolamento_sistematico.py` e `python scripts/qualidade/inventario_rotas.py --md --cobertura=<json>`.
