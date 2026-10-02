# DECISIONS (ADR log)

Formato: ID · data · fase · decisão · contexto · consequências · status.

## D-001 · 2026-09-25 · Fase 0 · Adotar o Master Prompt v4 como plano de evolução, com execução por fases e memória em `docs/b2bon/`
- **Contexto**: o prompt exige memória persistente fora da conversa.
- **Decisão**: `docs/b2bon/PROJECT_STATE.md` define a fase corrente.
  Só essa fase é executada. Cada fase termina com `phases/PHASE_X_COMPLETION.md`.
- **Status**: ACEITA.

## D-002 · 2026-09-25 · Fase 0 · Manter o monólito modular. Sem microserviços
- **Contexto**: 1 instância Render, sem fila, 1 banco. A auditoria não
  encontrou nenhuma necessidade de escala ou isolamento operacional que
  justifique deploy separado.
- **Decisão**: separar CRM/MAP/PREDATOR como **bounded contexts dentro
  do mesmo processo** (pacotes, contratos, eventos internos), conforme §10.
- **Consequência**: extração futura continua possível se os contratos
  forem respeitados.
- **Status**: ACEITA (PO autorizou a Fase 1 e as seguintes em 2026-09-25).

## D-003 · 2026-09-25 · Fase 0 · `docs/b2bon/` é a fonte canônica. Docs de raiz ficam como histórico
- **Contexto**: já existiam `CURRENT_ARCHITECTURE.md`,
  `AI_CURRENT_ARCHITECTURE.md`, `SECURITY_BOUNDARIES.md`,
  `DATA_FLOW_MAP.md` e `NETWORK_GAP_ANALYSIS.md` na raiz (2026-09-17),
  com trechos desatualizados (ex.: "8 pontos de IA", "única tabela sem tenant_id").
- **Decisão**: não apagar nem mover (Fase 0 não refatora). Os
  documentos novos prevalecem. Na Fase 1, adicionar um aviso no topo
  dos docs de raiz apontando para `docs/b2bon/` (TD-036).
- **Status**: ACEITA.

## D-004 · 2026-09-25 · Fase 0 · "Business Network" do Master Prompt = módulo Shoal existente
- **Contexto**: o Shoal já tem perfis, conexões, feed, intents,
  relacionamento tipado, salas corporativas e buying rooms (`sala_compra`).
- **Decisão**: as Fases 7/8/11 evoluem o Shoal. Não criam um módulo paralelo.
- **Status**: PROPOSTA (OI-008).

## D-005 · 2026-09-25 · Fase 0 · Ponto único de saída de IA já existe (`LLMProvider`). O gateway da Fase 4 evolui, não substitui
- **Contexto**: nenhum código chama o SDK Anthropic fora de `ClaudeProvider`.
- **Decisão**: a Fase 4 enriquece `LLMRequest`/`llm_helpers` em vez de
  criar uma camada paralela.
- **Status**: PROPOSTA.

## D-006 · 2026-09-25 · Fase 0 · Não corrigir OI-001 (limites 0 dos planos PREDATOR) dentro da Fase 0
- **Contexto**: o §89 proíbe alterar planos na Fase 0, mas o defeito
  afeta clientes pagantes.
- **Decisão**: registrar como OPEN ISSUE crítica e pedir autorização
  explícita do PO para um hotfix isolado, fora do fluxo de fases.
- **Status**: ACEITA.

## D-007 · 2026-09-25 · Fase 1 · Conta/Decisor/lead são Shared Kernel: rotas aceitam CRM **ou** PREDATOR
- **Contexto**: OI-004. O Kanban do CRM cria conta por `/leads/contas`
  (gate PREDATOR); a geração de lista e o enriquecimento estavam sob o
  gate do CRM.
- **Decisão**: `contas`, `decisores` e `leads` usam `_exige_organizacao`
  (CRM ou PREDATOR). Prospecção (gerar lista, enriquecer, mapear
  decisores, franquia, limite de enriquecimento) vai para o router
  `prospeccao_contas` sob `_exige_predator`. `ofertas` aceita CRM ou
  PREDATOR; `nps` aceita MAP ou PREDATOR.
- **Consequência**: tenants só-CRM deixam de ver rotas de prospecção.
  Na prática já não conseguiam usá-las: os limites dos planos CRM
  avulsos são 0. Tenants só-PREDATOR passam a gerar lista e enriquecer
  (os limites continuam dependendo de OI-001).
- **Status**: ACEITA (tomada sob a autorização geral do PO; reversível).

## D-008 · 2026-09-25 · Fase 1 · Contratos por contexto + porta de dados do MAP; fitness function obrigatória
- **Decisão**: cada contexto expõe `contract.py`. O MAP lê dados
  comerciais só por `MapDataSource`. A regra é verificada por
  `tests/unit/test_fronteiras_contexto.py` (falha o CI).
- **Consequência**: o MAP pode receber dados de CRM externo trocando só
  a implementação da porta (fundação para as Fases 3 e 13).
- **Status**: ACEITA.

## D-009 · 2026-09-25 · Fase 1 · CI roda também em `staging`
- **Contexto**: OI-005. Todo o trabalho do Master Prompt é empurrado
  para `staging`, onde nenhum teste rodava.
- **Decisão**: `ci.yml` dispara em push/PR para `master` e `staging`.
- **Status**: ACEITA.

## D-010 · 2026-09-25 · Fase 2 · Modelo canônico em Pydantic no Shared Kernel, com proveniência e classificação obrigatórias
- **Decisão**: `app/contexts/shared/canonical/`. Toda entidade herda
  `CanonicalEntity(id, tenant_id, source, origin, classification)`.
  Classificação default INTERNAL; dado interno do comprador default
  CONFIDENTIAL. Nenhuma tabela nova por entidade canônica: o canônico
  é contrato de troca, não schema de persistência.
- **Consequência**: a barreira Buy/Sell (Fase 10) e a Business Network
  (Fase 7) têm um eixo de classificação para filtrar desde já.
- **Status**: ACEITA.

## D-011 · 2026-09-25 · Fase 2 · Eventos de domínio via transactional outbox (`evento_dominio`)
- **Decisão**: `publicar` grava na mesma transação; `processar_pendentes`
  entrega fora do request, com retry e limite. Sem broker externo.
- **Consequência**: sem fila/worker (TD-032), o dispatcher roda por cron
  (Fase 3). Migrar para broker só se o volume exigir.
- **Status**: ACEITA.

## D-012 · 2026-09-25 · Fase 2 · Revision ids do Alembic são aleatórios; migração testada também em Postgres
- **Contexto**: o id "legível" `a1b2c3d4e5f6` colidiu com uma migração
  existente e criou duas heads.
- **Decisão**: gerar ids com `uuid4().hex[:12]`. Toda migração nova é
  validada em Postgres 16 local (upgrade → downgrade -1 → upgrade),
  além do teste SQLite existente.
- **Status**: ACEITA.

## D-013 · 2026-09-25 · Fase 3 · API de produto separada, autenticada por chave de API do tenant com escopos
- **Decisão**: `/api/v1/map/*` e `/api/v1/predator/*` aceitam só chave
  `b2bk_…` (hash SHA-256), com escopos por módulo/operação, rate limit
  por chave, licença e módulo checados no backend. JWT não abre a API de
  produto.
- **Consequência**: integrações de clientes não usam credencial de
  usuário humano; revogação é por chave.
- **Status**: ACEITA.

## D-014 · 2026-09-25 · Fase 3 · MAP API aceita dados canônicos no corpo
- **Decisão**: sem conector instalado, um CRM externo pode enviar
  contas/oportunidades/interações no modelo canônico e receber a análise
  do MAP, sem persistência. `tenant_id` do corpo é sempre substituído.
- **Consequência**: o MAP é consumível por CRM externo já na Fase 3
  (§11), com resultado idêntico ao do CRM interno para os mesmos dados
  (teste de contrato).
- **Status**: ACEITA.

## D-015 · 2026-09-25 · Fase 3 · Webhooks de saída consomem o outbox; só PUBLIC/INTERNAL saem
- **Decisão**: entregas únicas por (assinatura, evento), assinatura
  HMAC com timestamp, segredo criptografado em repouso, retry com backoff.
- **Status**: ACEITA.

## D-016 · 2026-09-25 · Fase 4 · Toda chamada de IA passa pelo AI Gateway, com feature registrada e roteamento C0–C3
- **Decisão**: `intel.gerar(db, llm, ContextoIA, LLMRequest)` é o único
  caminho (fitness function). C2 = modelo que já estava em produção
  (sem troca silenciosa). Quatro features curtas (FAQ, explicar match,
  sugerir regra, amostra de tom) vão para C1 (econômico).
- **Consequência**: custo atribuível por tenant/módulo/feature/agente;
  base do Usage Ledger da Fase 5. Mudança de comportamento: as 4 features
  C1 respondem com modelo menor (reversível por env).
- **Status**: ACEITA.

## D-017 · 2026-09-25 · Fase 4 · Corporate Brain sem embeddings (busca por palavra-chave)
- **Contexto**: volume pequeno por tenant; pgvector exige extensão no
  Neon e pipeline de embeddings com custo e provider adicional.
- **Decisão**: busca lexical normalizada, com propósito e orçamento no
  Context Engine. Reavaliar na Fase 17 com métrica de recall.
- **Status**: ACEITA.

## D-018 · 2026-09-25 · Fase 4 · Ledger de IA grava em sessão própria, inclusive falhas e bloqueios
- **Decisão**: o registro de uso é independente da transação do
  chamador. Falha e bloqueio por teto também são linhas do ledger.
- **Consequência**: "nenhuma chamada não contabilizada" (§82) vale mesmo
  com rollback do chamador. Em SQLite de desenvolvimento, com transação
  de escrita aberta, a gravação pode esperar o lock (TD-046).
- **Status**: ACEITA.

## D-019 · 2026-09-25 · Fase 5 · Custo do provedor em tabela versionada; créditos só com política definida pelo PO
- **Decisão**: `preco_modelo_ia` (USD/MTok, com fonte e vigência) mede o
  custo de toda chamada. A conversão para créditos fica
  `PENDING_DEFINITION` até o PO definir a taxa: o sistema não inventa preço (§71 por analogia, §55).
- **Consequência**: FinOps de custo funciona já. Carteira, excedente e
  bloqueio por saldo ficam prontos e inertes até a política ser ativada.
- **Status**: ACEITA.

## D-020 · 2026-09-25 · Fase 5 · Tenant não vê custo em USD; limite em USD é só da operação
- **Decisão**: o custo do provedor é dado interno da B2B ON. O tenant vê
  chamadas e créditos, e define limites por número de chamadas.
- **Status**: ACEITA.

## D-021 · 2026-09-25 · Fase 6 · Portfólio (`disponivel_para_venda`) separado da oferta "ativa" da cadência
- **Contexto**: `Oferta.ativo` significa "a oferta que entra no prompt de
  cadência" e só uma por tenant fica ativa. Usar isso no Next Best Offer
  reduziria o portfólio a uma oferta.
- **Decisão**: coluna nova `disponivel_para_venda` (padrão verdadeiro)
  define o portfólio do NBO/White Space. `ativo` mantém o significado.
- **Status**: ACEITA.

## D-022 · 2026-09-25 · Fase 6 · Recomendações de oportunidade são determinísticas (C0); IA só extrai necessidades
- **Decisão**: NBO, NBA, Discovery Gap, White Space e o card são regras
  explicáveis sobre dados do tenant, sem chamada de IA (custo zero,
  reprodutível, testável). A IA só propõe necessidades com citação
  literal, e elas não contam como confirmadas até revisão humana.
- **Consequência**: explicabilidade garantida por construção
  (`explicavel.recomendacao` recusa item sem evidência). Qualidade do
  casamento depende de Offer Intelligence bem preenchida.
- **Status**: ACEITA.

## D-023 · 2026-09-25 · Fase 6 · C7: riscos de pipeline e expansão com gate CRM ou PREDATOR
- **Decisão**: `/inteligencia-rede/riscos-pipeline` e `/sugestoes-expansao`
  leem só dado de CRM e passam para gate CRM-ou-PREDATOR (mesmos paths).
  `/atribuicao-receita` (sinais da rede) e o Agente Corporativo continuam
  PREDATOR até a Fase 7 definir o módulo da Business Network.
- **Status**: ACEITA.

## D-024 · 2026-09-25 · Fase 7 · Business Graph em tabelas relacionais, sem graph database
- **Contexto**: §29 pede avaliar a infraestrutura existente antes de um
  graph database. O Neo4j legado (Aura Free) pausa sozinho e só modela
  dados internos do CRM.
- **Decisão**: arestas em `relacionamento_empresarial` (com identidade,
  fonte, validade) e CONNECTED_TO derivada de `conexao_empresa`. Leitura
  por vizinhança (1 salto) com a regra única de privacidade.
- **Consequência**: sem travessias profundas por enquanto; reavaliar na
  Fase 8 (matching) com volume real.
- **Status**: ACEITA.

## D-025 · 2026-09-25 · Fase 7 · Membership como projeção de usuário → tenant
- **Decisão**: sem tabela de membros enquanto 1 usuário pertence a 1
  empresa. Papel na rede: ADMIN (admin/super_admin) ou MEMBRO (user).
- **Status**: ACEITA.

## D-026 · 2026-09-25 · Fase 7 · Identidade pública da empresa só por admin
- **Contexto**: antes qualquer usuário editava o perfil da empresa (inclusive
  o site usado na checagem de domínio da verificação) e declarava
  relacionamentos em nome dela.
- **Decisão**: editar perfil, declarar/confirmar/remover relacionamento,
  reivindicar identidade e mudar visibilidade exigem admin. A UI esconde
  essas ações para `user`.
- **Consequência**: mudança de comportamento para usuários `user`
  (reversível em `membership.ACOES_ADMIN`).
- **Status**: ACEITA.

## D-027 · 2026-09-25 · Fase 7 · Aresta `privada` é só do autor
- **Contexto**: a listagem mostrava à empresa citada as arestas privadas
  que outra empresa declarou sobre ela (ex.: "LOOKING_FOR").
- **Decisão**: `privada` = só o autor; `conexoes` passa a funcionar
  (partes + conexões do autor); bloqueio esconde conteúdo nas duas direções.
- **Status**: ACEITA.

## D-028 · 2026-09-25 · Fase 8 · Conversão de sinal é idempotente por empresa-alvo
- **Decisão**: a unidade de deduplicação é (tenant, empresa-alvo). Conta
  reaproveitada por sinal anterior/CNPJ/domínio; negócio aberto
  reaproveitado; todos os sinais da empresa fecham juntos.
- **Consequência**: "Criar oportunidade" nunca gera segunda conta ou
  segundo negócio aberto para a mesma empresa.
- **Status**: ACEITA.

## D-029 · 2026-09-25 · Fase 8 · Sala corporativa só leitura sem conexão ativa
- **Decisão**: desconectar ou bloquear congela a sala (histórico mantido
  para as duas empresas, sem novas mensagens).
- **Status**: ACEITA.

## D-030 · 2026-09-25 · Fase 9 · Módulo `bids` sem entrar em plano existente
- **Decisão**: `bids` é um módulo novo do catálogo de entitlements. Nenhum
  plano o recebe automaticamente; o super_admin o inclui num plano.
  Nenhum preço criado (§71 por analogia; catálogo na Fase 14).
- **Status**: ACEITA.

## D-031 · 2026-09-25 · Fase 9 · Proveniência calculada pelo sistema, não confiada à IA
- **Decisão**: a IA propõe citação e cláusula; o sistema só grava o que
  encontra literalmente no texto, calcula a página e descarta cláusula que
  não aparece na página. Documento com hash e fonte.
- **Status**: ACEITA.

## D-032 · 2026-09-25 · Fase 9 · PNCP experimental e desligado
- **Contexto**: o ambiente de desenvolvimento não alcança pncp.gov.br.
- **Decisão**: adapter implementado e testado com transporte simulado,
  exposto como EXPERIMENTAL e desligado (`PNCP_HABILITADO=false`) até
  validação contra a API real.
- **Status**: ACEITA.

## D-033 · 2026-09-25 · Fase 9 · Go/No-Go e matriz de conformidade determinísticos (C0)
- **Decisão**: IA só na extração de requisitos (C3). Matriz, Go/No-Go,
  prazos e concorrência são regras explicáveis sem custo de IA. A decisão
  Go/No-Go é humana, com justificativa quando diverge da recomendação.
- **Status**: ACEITA.

## D-034 · 2026-09-25 · Fase 10 · Barreira Buy/Sell estrutural + testes de comportamento
- **Decisão**: além de tenant e módulo, a barreira é garantida por
  construção: só o contexto de procurement, a API do comprador e
  `app/models` conhecem os dados do comprador (fitness function). O lado
  comprador não escreve no Corporate Brain. A única direção entre os lados
  é público → comprador (perfil público no Supplier 360).
- **Status**: ACEITA.

## D-035 · 2026-09-25 · Fase 10 · Módulo `procurement` com preço PENDING_DEFINITION
- **Decisão**: módulo no catálogo de entitlements, fora de todos os planos,
  sem preço (§71). A Fase 15 só roda com os valores do PO.
- **Status**: ACEITA.

## D-036 · 2026-09-25 · Fase 10 · Risco é sinal para revisão; regime jurídico é parâmetro
- **Decisão**: o motor de risco nunca conclui irregularidade; mensagens
  com "requer revisão". Limites que dependem do regime (fragmentação,
  prazos de alerta) vêm de `orgao_publico.parametros`; sem parâmetro, o
  sinal não é avaliado e isso é declarado.
- **Status**: ACEITA.

## D-037 · 2026-09-25 · Fase 11 · Comprador vê só o que o vendedor compartilha na sala de compra
- **Contexto**: a sala de compra mostrava ao comprador o nome interno do
  negócio e o estágio do funil do vendedor.
- **Decisão**: título e fase compartilhados, escolhidos pelo vendedor; o
  resto fica no CRM dele. Stakeholders são internos por padrão e as notas
  nunca atravessam.
- **Status**: ACEITA.

## D-038 · 2026-09-25 · Fase 11 · Permissão por usuário opcional por lado da sala
- **Decisão**: sem participantes definidos, todos os usuários da empresa
  acessam (comportamento anterior); com participantes, só eles e os admins.
  Cada empresa governa só o próprio lado.
- **Status**: ACEITA.

## D-039 · 2026-09-25 · Fase 12 · Registro de ferramentas no Shared Kernel, populado pelos contextos
- **Decisão**: o orquestrador não importa contextos de negócio; cada contexto
  registra as próprias ferramentas. Mantém a barreira Buy/Sell estrutural e
  evita ciclo de import. Coerência com o registro declarado (sensibilidade,
  agente, módulo) é validada pelo orquestrador e por teste.
- **Status**: ACEITA.

## D-040 · 2026-09-25 · Fase 12 · Roteamento determinístico primeiro; IA só como fallback e só sobre o permitido
- **Decisão**: palavras-chave (custo zero, previsível); sem rota, IA C1 com
  o catálogo das ferramentas permitidas ao usuário. A escolha da IA é
  validada contra esse catálogo. Uma ferramenta por pergunta (sem cadeia
  multi-passo por enquanto); compra × venda ambíguo pede esclarecimento.
- **Status**: ACEITA.

## D-041 · 2026-09-25 · Fase 13 · Conectores externos: somente leitura, BETA e habilitados pelo operador
- **Contexto**: os conectores são testados contra o formato documentado das
  APIs, não contra contas reais (a rede de desenvolvimento não alcança os
  provedores). §72 proíbe apresentar como disponível o que não foi validado.
- **Decisão**: conector implementado entra como BETA e só conecta quando
  listado em `CONECTORES_CRM_HABILITADOS`. Leitura apenas; os dados são
  consumidos ao vivo pelo modelo canônico (MAP por `conexao_id`), sem upsert
  no CRM interno e sem escrita no CRM externo.
- **Status**: ACEITA.

## D-042 · 2026-09-25 · Fase 13 · Hosts fixos por conector (anti-SSRF)
- **Decisão**: URLs informadas pelo tenant (ex.: `instance_url` do
  Salesforce) só são aceitas em HTTPS, porta padrão e domínio do provedor;
  o cliente HTTP não segue redirects. Campos que entram em consultas
  (ex.: `campo_cnpj`) são validados como identificadores.
- **Status**: ACEITA.

## D-043 · 2026-09-25 · Fase 13 · Segredo nunca em log nem em erro de sync
- **Contexto**: a API v1 do RD Station CRM só aceita o token na query
  string, e o `httpx` loga a URL de cada requisição.
- **Decisão**: filtro no logger `httpx` e no erro gravado pelo sync mascara
  `token`, `api_token`, `access_token`, `refresh_token` e `client_secret`.
  Onde a API permite, o segredo vai em header (Pipedrive `x-api-token`,
  Bearer nos demais).
- **Status**: ACEITA.

## D-044 · 2026-09-25 · Fase 14 · Catálogo sem preço; preço só na tabela `plano`
- **Decisão**: o catálogo diz o que existe e em que estado; o preço vem do
  plano que o checkout cobra. Produto sem plano self-service nunca aparece
  como contratável; Public Procurement fica EM_DEFINICAO até a Fase 15,
  com a estrutura de precificação vazia pronta para os valores do PO.
- **Status**: ACEITA.

## D-045 · 2026-09-25 · Fase 15 · Não executada
- **Contexto**: o Master Prompt proíbe executar a Fase 15 sem os valores do
  Product Owner ("Nunca estimar ou inventar esses valores").
- **Decisão**: fase pulada e registrada como bloqueada. O projeto segue
  para a Fase 16; a Fase 15 é executada quando o PO enviar modelo, preços,
  usuários, créditos, limites, add-ons e regras de excedente.
- **Status**: ACEITA.

## D-046 · 2026-09-25 · Fase 16 · Métricas com metodologia, sem estimativa, divididas pela barreira
- **Decisão**: toda métrica devolve metodologia e amostra; taxa sem
  denominador é nula. "Assistido por IA" e "influenciado pela rede" são
  toque registrado, não causalidade, e a interface diz isso. Métricas do
  lado comprador ficam no contexto `procurement` e nunca aparecem nas de
  receita (mesma fitness function da Fase 10).
- **Status**: ACEITA.

## D-047 · 2026-09-25 · Fase 17 · Toda FK indexada, exceto colunas de autoria
- **Contexto**: 121 FKs sem índice (o Postgres não cria sozinho): joins por
  conta/negócio e o `ON DELETE` de uma conta varriam as tabelas filhas.
- **Decisão**: indexar as 92 FKs usadas em filtro/join; ficam de fora as
  colunas de autoria (criado/aprovado/revisado/enviado por), que só custam
  escrita. Fitness function impede FK nova sem índice.
- **Status**: ACEITA.

## D-048 · 2026-09-25 · Fase 17 · Toda rota com IA tem teto
- **Decisão**: rota autenticada com IA usa `limitar_ia_por_tenant`; gatilhos
  sem usuário (webhook, cron, link público) usam o teto por hora do gateway.
  Verificado por fitness function sobre a árvore de dependências.
- **Status**: ACEITA.

## D-049 · 2026-09-25 · Fase 15 · Crédito vem do peso do workload, não do custo
- **Contexto**: a Fase 5 converteria custo em créditos (`creditos_por_usd`,
  OI-013). O PO definiu na Fase 15 um catálogo de workloads com pesos (§14).
- **Decisão**: cada feature do gateway mapeia para um workload de um catálogo
  versionado; o crédito cobrado é o peso (fixo ou variável por páginas/
  documentos). O custo real é medido à parte e só alimenta margem. A política
  `politica_creditos_ia` vira legado só leitura.
- **Consequência**: preço previsível para o cliente; margem monitorada e
  recalibrada por nova versão do catálogo, nunca automaticamente.
- **Status**: ACEITA.

## D-050 · 2026-09-25 · Fase 15 · Carteira por lotes com FEFO e reserva antes do provedor
- **Decisão**: créditos vivem em lotes (SUBSCRIPTION, TOPUP, PROMOTIONAL,
  ADJUSTMENT, ENTERPRISE_OVERAGE) com validade; consumo FEFO com desempate
  PROMOTIONAL < ADJUSTMENT < SUBSCRIPTION < TOPUP. Toda execução reserva
  antes da chamada (carteira travada com `SELECT … FOR UPDATE`), liquida no
  sucesso e libera na falha. Operação de N chamadas = uma cobrança.
  Idempotência por `(tenant, idempotency_key)` em execução, lote e movimento.
- **Status**: ACEITA.

## D-051 · 2026-09-25 · Fase 15 · Receita de referência dos créditos da assinatura
- **Contexto**: o preço do plano não é separado entre software e IA.
- **Decisão**: para margem, crédito de franquia vale R$ 6,99/1.000 (o menor
  preço efetivo da tabela de pacotes, AI 1M) — referência conservadora,
  configurável (`AI_CREDITOS_RECEITA_REF_ASSINATURA_1K_BRL`). Top-up usa o
  preço pago ÷ créditos; promocional e ajuste, zero.
- **Status**: ACEITA (revisável pelo PO).

## D-052 · 2026-09-25 · Fase 15 · Modos ENFORCE e MEASURE
- **Decisão**: produção roda ENFORCE (sem saldo, sem chamada, salvo excedente
  Enterprise aprovado). MEASURE mede tudo e registra excedente não faturável —
  usado para rollout gradual e pela suíte de testes (fixture `cobranca_ativa`
  liga ENFORCE nos testes de cobrança).
- **Status**: ACEITA.

## D-053 · 2026-09-25 · Fase 15 · Recarga automática cria pedido, não cobra fora de sessão
- **Contexto**: a integração de pagamento (preferência avulsa do Mercado Pago)
  não guarda meio de pagamento para cobrança sem o cliente presente.
- **Decisão**: com consentimento explícito (quem e quando), saldo abaixo do
  limiar cria um pedido pendente do pacote escolhido (um por vez) e o admin
  conclui o pagamento. Créditos só entram pelo webhook assinado, com valor
  conferido. Cobrança fora de sessão fica em TD-076.
- **Status**: ACEITA.

## D-054 · 2026-09-25 · Fase 15 · Franquias pendentes não concedem nada
- **Decisão**: franquias do Public Procurement (faixa 50–100K) e da Full Suite
  (75–100K) ficam PENDING_FINAL_DEFINITION por decisão do PO; nada é concedido
  por elas e as páginas mostram "Em definição". Até lá, plano de suíte recebe
  a soma das franquias dos módulos que contém. Opportunity Intelligence e
  Business Network (+10K) são add-ons não vendidos hoje: não concedem.
  O preço-base do Public Procurement segue PENDING_DEFINITION.
- **Status**: ACEITA.

## D-055 · 2026-09-26 · Correção arquitetural · Unified Strategic Sourcing Engine instead of separate Public/Private engines
- **Contexto**: a plataforma cobre quatro segmentos: B2B Sales, Public Sector Bids, Public Procurement e
  Enterprise Strategic Sourcing. Enterprise Bids também existe, como metade vendedora do Enterprise. As
  Fases 9 e 10 construíram o lado vendedor público (`bids`) e o comprador público (`procurement`) em
  paralelo: há duas tabelas de documento, dois pipelines de extração, requisito em tabela × JSON, dois
  contratos e dois workspaces (backend e UI). Enterprise RFP/RFI/RFQ ficou só como valor de `modalidade`,
  e o buy side privado não existe. Copiar cada lado para o Enterprise dobraria essa duplicação
  (≈ 4.600 linhas estimadas, `18_STRATEGIC_SOURCING.md` §6).
- **Decisão**: um núcleo `sourcing` compartilhado por Sell e Buy, Público e Enterprise, com:
  - entidade canônica `SourcingProcess` (`segment`, `side` imutável, `process_type`, `ruleset`,
    `workflow`, `metadata`) e filhos compartilhados (Document, Requirement, Evaluation, Participant,
    Proposal, Lot/Item, eventos, Contract);
  - Requirement Engine com perfis por tipo de documento;
  - Evaluation Engine com direção (SELF/PROPOSAL);
  - Matching Engine com estratégias;
  - Workflow declarativo em código e rulesets versionados separados do processo.

  Os segmentos são configuração. `bids` e `procurement` continuam como contextos para o que é
  exclusivo de cada lado. Sem tabela por tipo de processo e sem microserviço (D-002).
- **Benefícios**:
  - a lógica comum é escrita e testada uma vez;
  - Enterprise sell e buy passam a exigir só as capacidades realmente novas (convite, propostas,
    comparação, qualificação, negociação), não uma cópia;
  - regras regulatórias ficam num lugar;
  - uma UI de workspace e um conjunto de recursos de API.
- **Tradeoffs**:
  - a barreira Buy/Sell deixa de vir de "tabelas diferentes" e passa a exigir repositório com lado
    obrigatório, `side` imutável e fitness function reescrita (mais disciplina, mais testes);
  - a migração de dados precisa de Strangler (expand/backfill/leitura dupla/switch);
  - existe o risco de generalizar cedo demais, mitigado por workflow em código sem editor e por
    criar cada workflow só quando o fluxo for construído.
- **Impacto de migração**:
  - 9 tabelas migram para 9 `*_sourcing` (lote/item quando houver uso);
  - 46 rotas `/bids` e `/procurement` viram fachada e depois só ficam as de comportamento exclusivo;
  - duas telas de workspace viram `ProcessWorkspace` com painéis;
  - features de IA e workloads de crédito mantêm os códigos;
  - `audit_log`/`execucao_ia` antigos não são reescritos (mapa de ids).

  Fases S0–S8 propostas, nenhuma autorizada.
- **Status**: ACEITA como arquitetura-alvo; implementação depende do PO.

## D-056 · 2026-09-26 · Sourcing S0 · Paginação por cursor com a resposta ainda em lista
- **Contexto**: `/bids/licitacoes` e `/procurement/{recurso}` devolviam tudo. Trocar o formato da resposta
  quebraria as telas e integrações existentes.
- **Decisão**: cursor opaco *keyset* (posição da última linha), `limite` 1–500 (padrão 100), próximo cursor no
  header `X-Proximo-Cursor` (exposto no CORS). A resposta continua uma lista; as telas ganham "Carregar mais".
  Listas pequenas usadas em seletores (órgãos, planos) pedem `limite=500`.
- **Status**: ACEITA.

## D-057 · 2026-09-26 · Sourcing S2 · Barreira por repositório convive com a barreira por tabela
- **Decisão**: cada lado implementa `sourcing.repositorio.RepositorioSourcing` com o lado fixo
  (`RepositorioVenda` em `bids`, `RepositorioCompra` em `procurement`). Quem está fora de um lado lê por ele
  (FinOps e Analytics já leem a venda assim). A fitness `test_barreira_sourcing.py` roda junto com a antiga
  (`test_barreira_buy_sell.py`): tabelas de cada lado só no próprio contexto, núcleo `sourcing` neutro,
  `RepositorioCompra` só no comprador, ferramentas do agente com o lado de quem as registra.
- **Consequência**: na S3 só a implementação dos repositórios troca de tabela; chamadores e fitness não mudam.
- **Status**: ACEITA.

## D-058 · 2026-09-26 · Sourcing S3 · Expand com espelho por eventos do ORM e leitura dupla
- **Contexto**: S3 cria as tabelas unificadas sem trocar a fonte da verdade (Strangler).
- **Decisão**:
  - **Tabelas**: 6 tabelas `*_sourcing` (processo, documento, requisito, contrato, evento, evento_contrato) com
    `lado` em CHECK e imutável (evento do ORM e trigger no banco) e mapa de origem único.
  - **Espelho**: cada lado copia as próprias escritas pelos eventos do ORM (`after_insert/update/delete`), com o
    lado fixo, chamando o núcleo neutro. Roda em SAVEPOINT: falha vira log `SOURCING_ESPELHO_FALHOU` e não derruba
    a escrita do usuário.
  - **Backfill**: idempotente, em lotes, com remoção de órfãos, por `/cron/sourcing-sincronizar`. Serve para os
    dados anteriores e como rede de segurança.
  - **Leitura dupla**: os repositórios continuam respondendo pelas tabelas antigas e conferem as novas
    (`SOURCING_LEITURA_DUPLA`: COMPARAR em produção, ESTRITA na suíte).
  - **Barreira**: só o núcleo acessa as tabelas novas. Quem passa `Lado.COMPRA` ao núcleo é só o comprador;
    `Lado.VENDA`, só o vendedor (fitness).
- **Alternativas**:
  - dual-write espalhado pelos serviços: dezenas de pontos de escrita;
  - backfill periódico apenas: janela de divergência;
  - triggers de banco para copiar: regra de mapeamento duplicada em SQL por dialeto.
- **Consequência**: S6 troca a leitura para as tabelas novas sem mudar os chamadores; a duplicação de escrita
  some junto com as tabelas antigas.
- **Status**: ACEITA.

## D-059 · 2026-09-26 · Comercial · Commercial separation by job-to-be-done while sharing the Unified Strategic Sourcing Engine
- **Contexto**: OI-019 (empacotamento Enterprise) e OI-015 (empacotamento e preço do Bid Intelligence). Resolução
  do PO em 2026-09-26.
- **Decisão**: produtos organizados por job-to-be-done, tecnologia compartilhada.

  | Lado | Produto | Job-to-be-done | Preço | AI Credits/mês |
  |---|---|---|---|---|
  | SELL | **B2B ON Bid Intelligence** (Public Sector Bids + Enterprise Bids) | encontrar, qualificar, analisar e responder oportunidades públicas e privadas | R$ 1.490/mês | 25.000 |
  | BUY privado | **B2B ON Strategic Sourcing** | encontrar, qualificar, comparar e contratar fornecedores | R$ 2.990/mês, 5 buyer users | 50.000 |
  | BUY privado | **B2B ON Strategic Sourcing Enterprise** | idem, com condições enterprise | a partir de R$ 5.990/mês (STARTING_AT) | 100.000 |
  | BUY público | **B2B ON Public Procurement** | planejar e executar contratações públicas | PENDING_DEFINITION (inalterado) | PENDING_FINAL_DEFINITION (OI-017) |

  - Enterprise Bids **não** é módulo à parte: entra no Bid Intelligence sem cobrança adicional por a oportunidade
    ser pública ou privada.
  - Sem plano "Strategic Sourcing Pro" por ora.
  - Bundles futuros (Revenue & Bids; Procurement Intelligence) preparados no catálogo, sem preço.
  - Supplier Guest é papel, não consome buyer seat e só acessa o que o comprador autorizou.
  - Todos os créditos vão para a carteira única do tenant (D-050); nada de carteira por módulo.
- **Justificativa**:
  - Bid Intelligence atende o SELL SIDE; Public e Enterprise Bids são o mesmo problema do fornecedor.
  - Strategic Sourcing atende o BUY SIDE privado.
  - Public Procurement tem requisitos e rulesets próprios, mas reutiliza os engines.
- **Consequência**:
  - Continua **um** engine de sourcing (D-055). O que difere entre produtos é `segment`, `side`, `process_type`,
    `ruleset`, `workflow`, entitlement e papel, sem engine por segmento.
  - Nenhuma capacidade não implementada é exibida como disponível: o catálogo usa AVAILABLE, BETA, COMING_SOON e
    CONTACT_SALES conforme o estado real (`15_PRICING_AND_ENTITLEMENTS.md` §5).
  - A implementação comercial (planos, catálogo central, página de vendas, entitlements no código) fica para fase
    autorizada (OI-021), pela regra de fase da própria resolução.
- **Status**: ACEITA. Resolve OI-019 e OI-015.


## D-060 · 2026-09-26 · Sourcing S4 · Workflow e ruleset declarados por lado, validados por motor neutro
- **Contexto**: S4 do plano (`18_STRATEGIC_SOURCING.md` §8), autorizada pelo PO ("S4: pode trocar"). Estados de
  licitação e de processo de compra viviam em tuplas; as regras da Lei 14.133 (documentos por etapa, limites de
  sinal) em constantes soltas; as transições reservadas (GO/NO_GO, GANHA/PERDIDA) em `if`s no serviço.
- **Decisão**:
  - **Motor neutro** no núcleo: `sourcing/workflow.py` (estados, inicial, finais, transições marcadas pela ação que
    as alcança — `status`, `go_no_go`, `resultado` — e origem opcional) e `sourcing/ruleset.py` (documentos
    esperados por etapa e parâmetros com padrão, sobrescritos pela configuração do cliente). Registro por código
    versionado; registrar outra definição com o mesmo código é recusado (mudança = nova versão).
  - **Definições por lado**, porque o núcleo não conhece estado de nenhum lado e só o comprador usa
    `Lado.COMPRA`: `bids/fluxo.py` (`PUBLIC_TENDER_SELL@1`, `ENTERPRISE_RFP_SELL@1`, `PRIVATE_RFP@1`) e
    `procurement/fluxo.py` (`PUBLIC_PROCUREMENT_BUY@1`, `PUBLIC_PROCUREMENT_BR_14133@1`).
  - **Paridade**: v1 reproduz o comportamento anterior (sem restrição de origem; mesmas mensagens e códigos HTTP).
    As tuplas, `DOCUMENTOS_ESPERADOS` e as constantes viram aliases derivados; o espelho grava os códigos do
    registro.
  - `ENTERPRISE_RFP_SELL@1` é o fluxo atual aplicado ao RFP privado, com código próprio (o fluxo enterprise da S7
    nasce como nova versão). `PRIVATE_RFP@1` não tem regra: contratação privada, sem regime legal.
  - `limite_fragmentacao` não tem padrão: sem configuração do órgão, o sinal fica sem avaliação (nunca inventado).
- **Desvio de comportamento (único)**: `mudar_status` agora carrega a licitação antes de validar (o fluxo depende da
  modalidade). Licitação inexistente ou de outro tenant com status inválido/reservado responde 404 em vez de
  422/409. Não vaza nada (antes o 409 confirmava a regra sem dizer se o id existia; agora nem isso).
- **Fora do escopo**: estados de demanda, plano, item do PCA e contrato continuam em tuplas (não são processo de
  sourcing); limiares analíticos de risco sem base regulatória (`DIAS_PLANEJAMENTO`, `ACRESCIMO_ALERTA`,
  `ADITIVOS_ALERTA`, `CONCENTRACAO_ALERTA`) continuam em `riscos.py` (TD-089).
- **Status**: ACEITA.

## D-061 · 2026-09-26 · Plano unificado A–I · Phase A fecha a fundação sem tabela nova
- **Contexto**: PO autorizou S5 e OI-021 e enviou o plano "UNIFIED BUSINESS & SOURCING IMPLEMENTATION" (fases A–I,
  uma por vez). Perguntado sobre a ordem, o PO escolheu a Phase A.
- **Decisão**:
  - O plano A–I passa a ser a ordem de execução; S0–S4 contam para ele (mapa em `18_STRATEGIC_SOURCING.md` §10).
    S5 vira parte da Phase C (`ProcessWorkspace`) e OI-021 é a Phase I, ambas autorizadas e executadas na vez delas.
  - **Resolução central** (§21): `sourcing.workflow.vincular/resolver` decide workflow e ruleset por (lado,
    segmento[, tipo de processo]); o mais específico vence; sem vínculo, erro (falha fechado). A regra "RFP privado é
    Enterprise" existe só em `bids/fluxo.classificar`, usada pelo espelho e pela validação.
  - **Ruleset** (§22): versão (do código), vigência (`vigente_desde`), fonte (obrigatória) e configuração
    (parâmetros). Lei 14.133: vigente desde 2021-04-01 (art. 194); os parâmetros são padrões analíticos do produto,
    não limites legais, e isso está escrito na descrição.
  - **Entidades compartilhadas** (§6): nenhuma tabela nova. Cada entidade foi mapeada para onde já vive; Proposal,
    Evaluation, Lot, Item e Deliverable nascem com o primeiro fluxo que grava nelas (Phase C/E), como em D-058.
  - **Duplicação** (§35): eventos do ORM e backfill do espelho iguais nos dois lados foram para
    `sourcing.espelho.instalar`; cada lado declara só o mapeamento.
  - **Orçamento de desempenho** (§36): `tests/desempenho` (sob demanda) mede e compara com
    `docs/b2bon/perf/baseline.json`; `scripts/qualidade/duplicacao.py` é a análise de duplicação do projeto.
- **Alternativas**: criar as 17 entidades do §6 como tabelas agora (vazias, sem fluxo que grave: contraria §29/§49);
  resolução por `if` em cada contexto (o que §21 pede para evitar).
- **Status**: ACEITA.

## D-062 · 2026-09-26 · Phase B · Requisito normalizado com obrigatoriedade lida do trecho
- **Contexto**: Phase B do plano unificado (§38): unificar documentos, extração, requisitos, evidência,
  proveniência e base de conformidade, validando com edital público e RFP enterprise. Os engines de documento e de
  extração já eram únicos (S1); faltavam, do §18, a **obrigatoriedade** e a regra de proveniência do requisito digitado
  por humano fora do contexto de venda.
- **Decisão**:
  - `sourcing.requisitos.obrigatoriedade(trecho)`: obrigatório só com linguagem de obrigação no trecho literal
    ("deverá", "sob pena", "vedado", "must", "shall"…), desejável só com linguagem de preferência ("desejável",
    "preferencialmente", "poderá", "should"…); nenhuma ou as duas → **UNKNOWN** (`None`). Não se pergunta ao modelo:
    a obrigatoriedade tem de ser verificável no mesmo trecho que prova o requisito.
  - `sourcing.requisitos.ancorar_evidencia`: requisito manual que aponta para documento precisa do trecho no texto;
    a página é calculada. Mesmas mensagens de antes.
  - Coluna `obrigatorio` (nula) em `requisito_licitacao` e `requisito_sourcing`; chave `obrigatorio` nos achados do
    comprador. Linhas anteriores ficam UNKNOWN: a migração não infere nada; nova análise classifica.
  - Humano pode informar a obrigatoriedade no requisito manual (prevalece sobre a dedução).
  - A matriz de conformidade e a tela mostram o campo. **Go/No-Go não muda** nesta fase: usar a obrigatoriedade na
    recomendação é decisão de produto da Phase C.
- **Não feito (e por quê)**: trocar a leitura para as tabelas unificadas (TD-087/088) exige evidência de produção —
  backfill rodado e zero `SOURCING_DIVERGENCIA` por uma release — que não se obtém daqui. Fica como portão operacional.
- **Migração**: ADD/DROP COLUMN direto, sem `batch_alter_table`, para o SQLite não recriar `requisito_sourcing` e
  perder o trigger de lado imutável (coberto por teste no upgrade e no downgrade).
- **Status**: ACEITA.

## D-063 · 2026-09-26 · Phase C · Enterprise Bid por configuração, workflow v2 com negociação e proposta C0
- **Contexto**: Phase C do plano unificado (§39): concluir Public Bid + Enterprise Bid com qualificação, conformidade,
  Go/No-Go, workspace e apoio à proposta; e a UI compartilhada (§28, antiga S5).
- **Decisão**:
  - **Enterprise Bid é configuração**, não entidade: modalidades `PRIVATE_RFI`, `PRIVATE_RFQ`, `PRIVATE_TENDER` (além de
    `PRIVATE_RFP`) classificadas em (ENTERPRISE, RFI/RFQ/PRIVATE_TENDER/RFP) num único mapa (`bids/fluxo.PRIVADAS`).
  - **`ENTERPRISE_RFP_SELL@2`**: a v1 + `EM_NEGOCIACAO`, alcançável só a partir de `PROPOSTA_ENVIADA`. A v1 segue
    registrada (histórico); o vínculo do segmento aponta para a v2. O público não tem negociação (`Status inválido`).
    Em produção, as linhas espelhadas de RFP privado passam de `@1` para `@2` no próximo backfill diário; até lá a
    leitura dupla em COMPARAR pode logar essa divergência (esperada).
  - **Tela sem estados fixos**: o workspace devolve `fluxo` (código, segmento, tipo, `proximos_status`,
    `aceita_resultado`, `final`) calculado por `Workflow.proximos`; os botões de andamento vêm daí.
  - **Qualificação**: continua sendo os fatores do Go/No-Go (dados que faltam aparecem como UNKNOWN com o motivo);
    nenhuma tela ou entidade nova.
  - **Go/No-Go v2** (`bids.go_no_go.v2`): requisito técnico/comercial **obrigatório** NON_COMPLIANT é bloqueio;
    desejável ou UNKNOWN não bloqueia. Documental segue igual.
  - **Resposta por requisito** (`resposta`, texto humano; categoria nova `PERGUNTA` para RFI/questionário). A
    plataforma não escreve em nome da empresa. Log de auditoria sem o texto.
  - **Proposta C0** (`bids/proposta.py`): esboço determinístico com itens, pendências (REVISAR, RESPONDER,
    COMPROVAR), documentos do cofre a anexar e prontidão; JSON ou Markdown. Sem IA, 0 AI Credits. Proposal como
    entidade (versões, envio) fica para quando houver fluxo que grave (Phase E, lado comprador).
  - **`ProcessWorkspace`** (frontend): moldura de abas compartilhada, aba ativa na URL; licitação (Visão geral,
    Documentos, Requisitos, Conformidade, Proposta/Resposta) e processo de compra (Visão geral, Documentos, Pesquisa
    de preços, Timeline) usam o mesmo componente.
  - **E2E**: um login real por rodada (`auth.setup.ts`) reaproveitado pelas specs que não testam o login, porque o
    `/auth/login` tem rate limit por IP (5/5min) e a suíte já estava no limite. O limite não foi afrouxado.
- **Status**: ACEITA.

## D-064 · 2026-09-26 · Phase D · Lado comprador público sobre os engines, sem N+1 e com a regra à vista
- **Contexto**: Phase D (§40): demanda, planejamento, PCA, processo, fornecedor, avaliação, contrato e risco sobre os
  engines compartilhados; testar a barreira. Quase tudo existia desde a Fase 10.
- **Decisão**:
  - **TD-090 resolvido**: `precos.resumo_por_processo` e `contratos.inteligencia_em_lote` (uma consulta cada) usados
    por riscos, workspace, Supplier 360, ranking e ferramenta do agente; itens do PCA carregados de uma vez. As funções
    antigas viram atalhos para as versões em lote.
  - **Workflow e ruleset na tela do comprador**: o workspace do processo devolve `fluxo` (próximas etapas pelo
    workflow, ruleset com fonte e os **documentos que a Lei 14.133 espera na etapa atual**, presentes ou não); a aba
    Visão geral mostra o andamento com os botões vindos do servidor.
  - **Cadastro sem campo obrigatório** responde 422 com o nome do campo (derivado das colunas NOT NULL sem padrão do
    modelo), não mais 500 do banco.
  - **Avaliação**: do fornecedor, já existe (fiscalização, ocorrências, nota, Supplier 360, ranking). A avaliação de
    propostas usa a entidade compartilhada que nasce na Phase E (lado comprador) e vale também para o processo
    público — nada criado aqui para não haver duas.
- **Barreira**: testes estendidos às superfícies novas (esboço de proposta JSON/Markdown, resposta do vendedor,
  bloco `fluxo`) nos dois sentidos, no mesmo tenant com os dois módulos.
- **Status**: ACEITA.

## D-065 · 2026-09-26 · Phase E · Enterprise Strategic Sourcing nativo no modelo unificado
- **Contexto**: Phase E (§41): Strategic Sourcing, descoberta, RFI/RFP/RFQ, qualificação, comparação, shortlist,
  negociação, contrato — produto novo, sem tabela antiga.
- **Decisão**:
  - **Nativo no modelo unificado**: o comprador privado grava direto em `*_sourcing` (processo, requisito, contrato
    com `origem_tabela = "nativo"`; espelho, backfill e leitura dupla nunca tocam essas linhas). Só o núcleo acessa as
    tabelas: `sourcing/nativo.py` (criar/obter/listar/atualizar por nome de entidade, **sempre filtrando tenant e
    lado**). A lógica de compra fica no lado comprador (`procurement/estrategico.py`, `Lado.COMPRA`).
  - **Entidades que nascem aqui** (D-058/D-061): participante, item, proposta (uma linha por rodada), preço por
    item e avaliação (proposta × requisito: resposta do fornecedor + status/nota/justificativa do comprador), todas
    com `lado` em CHECK e imutável (trigger + ORM); `peso` no requisito.
  - **Um workflow por natureza** (§21), escolhido pelo vínculo (lado, segmento, tipo): `ENTERPRISE_SOURCING_BUY@1`
    (RFP, concorrência privada, evento estratégico), `ENTERPRISE_RFQ_BUY@1` (cotação leve: sem avaliação técnica nem
    shortlist, §15), `ENTERPRISE_RFI_BUY@1` (RFI, EOI, qualificação: coleta e encerra, sem adjudicação). Ruleset
    `ENTERPRISE_SOURCING_POLICY@1` (política do próprio cliente, sem parâmetro inventado).
  - **Aprovação humana antes da adjudicação**: pedido com justificativa → administrador aprova (adjudica e marca os
    demais como não selecionados) ou recusa com motivo (volta à etapa anterior). Decisão sempre humana.
  - **Descoberta (§16)** pelo Matching Engine (estratégia nova `criterios_fornecedor`): cadastro interno do comprador
    e perfis da Business Network **que ele pode ver** (diretório ou conexões, sem bloqueados; só campos públicos).
    Empresa oculta não aparece nem pode ser convidada. Nada do processo vai para a rede.
  - **Comparação (§20)** determinística (C0): obrigatórios atendidos, nota ponderada pelos pesos, valor, prazo,
    pagamento, risco; destaques (menor valor, maior nota) só entre quem não falhou obrigatório. Sem vencedor automático.
  - **Gate** `sourcing` (Strategic Sourcing); API em `/sourcing` (§30). O preço e o plano comercial ficam na Phase I.
  - **Fitness**: `app/api/v1/strategic_sourcing.py` declarado como API do lado comprador; regex das tabelas unificadas
    inclui as novas.
  - Provisório de `origem_id` na inserção nativa é negativo e único (não zero), para inserções concorrentes não
    esperarem umas pelas outras no índice único (provado em Postgres).
- **Fora do escopo**: portal do fornecedor (Phase F), IA de avaliação/comparação (Phase G), documentos anexados às
  propostas (fica para a Phase F, com o acesso do fornecedor).
- **Status**: ACEITA.

## D-066 · 2026-09-26 · Phase F · Acesso do fornecedor por convite, sem vitrine e sem assento
- **Contexto**: Phase F (§42, §17, §23): publicação/convite de RFP, matching de fornecedores, visibilidade controlada
  e acesso do fornecedor para responder, sem transformar a rede em canal de informação restrita.
- **Decisão**:
  - **Só por convite**: não há listagem pública de processos na rede. Matching e convite continuam os da Phase E
    (perfis que o comprador pode ver). O processo só existe para o fornecedor depois de publicado.
  - **Duas entradas para o mesmo convite** (`procurement/portal.py`):
    - **link secreto** (Supplier Guest, sem login e **sem assento**): `secrets.token_urlsafe(32)`, só o SHA-256 é
      guardado; gerar de novo revoga o anterior; o segredo vai no cabeçalho `X-Convite-Token` (o log de acesso
      registra caminhos) e a página o lê do fragmento `#` (que o navegador não envia a servidor nenhum); rate
      limit por IP; link inválido ou revogado responde 404 genérico;
    - **conta da Business Network**: a empresa convidada vê "Convites de compra" e responde logada, só nos convites
      em que ela é o participante.
  - **Visão restrita**: título, descrição, tipo, prazo, requisitos **sem peso**, itens, esclarecimentos respondidos
    **sem dizer quem perguntou**, as próprias perguntas, propostas e situação. Nunca: outros participantes, avaliações,
    notas, valor estimado, aprovação, comparação. Situação do processo traduzida (ABERTO, EM_ANALISE, EM_NEGOCIACAO só
    para quem está na shortlist, ENCERRADO, CANCELADO).
  - **O fornecedor**: pergunta enquanto aberto, envia proposta/resposta (mesma regra da Phase E: negociação só para a
    shortlist; RFQ para todos), anexa evidência (PDF/texto, validação do Document Engine, até 10 por proposta,
    arquivo só lido no download), declina. Proposta marcada `canal = PORTAL`.
  - **O comprador**: gera o link (mostrado uma vez), responde esclarecimentos (resposta vai para todos), baixa anexos.
  - **Tabelas novas**: `esclarecimento_sourcing`, `anexo_sourcing` (lado imutável); acesso e e-mail no participante.
  - Nada disso usa IA nem escreve no CRM, no Bid Intelligence ou no Corporate Brain da empresa convidada.
- **Status**: ACEITA.

## D-067 · 2026-09-26 · Phase G · Intelligence do Strategic Sourcing pela arquitetura de IA existente
- **Contexto**: Phase G (§43, §18–§20, §25, §32): Requirement AI, Evaluation AI, Bid Intelligence, Procurement Intelligence,
  Supplier Intelligence, Risk e Recommendation, tudo pela arquitetura de IA existente, com teste de grounding. Bid
  Intelligence (Fases 9 e C) e Procurement Intelligence público (Fases 10 e D) já existiam; faltava o comprador privado.
- **Decisão**:
  - **Sem agente novo (D-055)**: tudo é capability do `procurement_intelligence_agent` existente; os agentes PLANEJADOS
    continuam planejados.
  - **Requirement AI**: especificação enviada ao processo (`documento_sourcing` nativo, com texto por página e arquivo)
    → Requirement Engine, perfil `especificacao_compra` → requisito **sugerido** (`fonte=AI`, trecho, página calculada,
    cláusula só se estiver na página, obrigatoriedade lida do trecho). Sugestão não publica, não aparece ao fornecedor,
    não entra em proposta, avaliação nem comparação até um humano confirmar. RESTRICTED não vai para IA.
  - **Evaluation AI**: sugestão de status por requisito, **uma chamada por proposta só com o texto dela** (respostas,
    observações, condições, anexos). A citação tem de estar no que o fornecedor escreveu (o rótulo com o texto do
    requisito não conta); sem trecho, a sugestão cai (falta de evidência é UNKNOWN, nunca "não atende"). Nada é gravado
    como avaliação: o avaliador aplica, e a justificativa leva o trecho.
  - **Medição**: uma execução de crédito por operação, pelo AI Gateway; workloads já existentes no catálogo
    (`procurement_document_intelligence`, `procurement_complex_comparison`); nenhum peso de crédito novo, nenhum preço.
  - **C0 (0 créditos)**: Supplier Intelligence (histórico do mesmo fornecedor por cadastro, rede, CNPJ ou nome nos
    outros processos do comprador), alertas com a evidência que os gerou (sugestões pendentes, perguntas sem resposta,
    prazo, participação baixa, proposta única, obrigatório não atendido, preço fora da mediana, histórico) e próxima
    ação por etapa do workflow. Três ferramentas READ do lado BUY no orquestrador.
  - **Barreira**: dados do comprador privado nunca vão para o lado vendedor; entre fornecedores, a IA nunca vê a
    proposta de um ao avaliar a de outro.
- **Status**: ACEITA.

## D-068 · 2026-09-26 · Phase H · Otimização medida, sem refactor cosmético
- **Contexto**: Phase H (§44): medir duplicação, bundle, latência, consultas, memória, custo de IA, cache e jobs;
  eliminar duplicação real; não fazer refactor sem benefício.
- **Decisão**:
  - **Duplicação real eliminada**: detalhe de risco do MAP (contas × tenants: score, script de resgate, histórico,
    modal de interação) → `DetalheRisco`; regra de convite utilizável (revogado, usado, vencido) → uma função em
    `auth_service` usada também pela vitrine; resposta de download de evidência com hash → `api/respostas.py` (5 rotas);
    tratamento de erro/401 da API no frontend → `exigirSucesso`.
  - **Mantido de propósito**: blocos que só se parecem (handlers de formulário, listas de import dos conectores,
    marcação de telas diferentes). Os 12 linhas repetidas nos conectores BETA desligados ficam como TD-092.
  - **Bundle**: páginas públicas além do login saem do chunk de entrada (lazy, um `Suspense` só).
  - **Jobs**: o backfill do sourcing carrega as linhas unificadas existentes do lote numa consulta e memoriza os pais
    resolvidos (`LoteBackfill`); semântica do upsert inalterada.
  - **Cache/semente (TD-091)**: catálogo de AI Credits semeado na subida (lifespan); a semente preguiçosa continua
    idempotente como rede de segurança; o seed do E2E faz o mesmo, porque o Playwright recria o banco depois de subir
    o servidor.
  - **Custo de IA**: nenhuma mudança de política; toda chamada segue pelo AI Gateway (fitness do caminho único), C0
    antes de IA, uma execução de crédito por operação. Custo real por feature só com uso de produção (UNKNOWN aqui).
- **Status**: ACEITA.

## D-069 · 2026-09-26 · Phase I · Implementação comercial de D-059 sobre os mecanismos existentes
- **Contexto**: Phase I (§45, OI-021): planos, módulos, entitlements, AI Credits, página de vendas e assinatura para
  Revenue Intelligence, Bid Intelligence, Public Procurement, Strategic Sourcing e Suite; preservar preços aprovados e
  não inventar os pendentes.
- **Decisão**:
  - **Planos** (tabela `plano`, migração de dados idempotente): Bid Intelligence R$ 1.490 (FIXED); Strategic Sourcing
    R$ 2.990 com 5 usuários (FIXED); Strategic Sourcing Enterprise a partir de R$ 5.990 (**STARTING_AT**, fora do
    self-service). Public Procurement e Suite **sem plano**. Revenue Intelligence = os planos de suíte e avulsos que já
    existem (preços da Fase 14 inalterados).
  - **`tipo_preco`**: só FIXED vai para cadastro e checkout; STARTING_AT aparece como "a partir de" com contato comercial
    e é recusado no servidor mesmo se marcado self-service por engano.
  - **Entitlements**: `sourcing` é o módulo; o tier Enterprise é a feature `SOURCING_ENTERPRISE` (chave
    `sourcing_enterprise` no plano), sem módulo novo. Supplier Guest segue como acesso por link, sem assento (D-066).
  - **AI Credits**: `FRANQUIAS` ganha `sourcing` 50.000 e `sourcing_enterprise` 100.000, que **substitui** a do
    Strategic Sourcing; carteira única do tenant (D-050). Nenhum workload ou peso novo.
  - **Página de vendas**: `GET /catalogo` devolve `linhas` (produto por job-to-be-done, lado, planos com preço, tipo de
    preço, AI Credits e usuários, e `pendencias`). O que está pendente aparece "a definir"/"preço em definição", sem
    número e sem botão de compra. **Assinatura** mostra "condições por contrato (a partir de …)" para STARTING_AT.
  - **Pendência nova**: limite de usuários do Bid Intelligence não foi definido pelo PO (OI-023); hoje sem limite.
- **Status**: ACEITA. Resolve OI-021.

## D-070 · 2026-09-26 · Phase J1 · Troca de leitura da S6 preparada atrás de configuração (desligada)
- **Contexto**: autorização do PO após o plano A–I ("preparar a troca S6"). O portão operacional continua: trocar a
  leitura só depois do backfill em produção e de uma release sem `SOURCING_DIVERGENCIA` (TD-087/088).
- **Decisão**:
  - Configuração `sourcing_leitura_fonte` = **ANTIGA** (padrão) | UNIFICADA.
  - Em UNIFICADA, as leituras de **listagem** dos repositórios por lado vêm de `*_sourcing`, filtradas por tenant e pelo
    lado de quem pergunta, e voltam no formato antigo (ids de origem, mesmos campos): vendedor — processos (mesma ordem e
    keyset), documentos, requisitos (ordem do banco para vazios), tipos de documento; comprador — tipos de documento.
    Consulta no núcleo neutro (`sourcing/leitura.py`); a volta de cada lado fica ao lado do mapeamento de ida (`bids/espelho.py`).
  - **Fica nas tabelas antigas** (próximos passos da S6): `obter_processo` (o registro é alterado por quem chama — a escrita
    precisa mudar antes); processo e documentos do comprador (achados em JSON); arquivo e texto das páginas (TD-088).
  - Prova: a mesma API responde igual nos dois modos depois do backfill (SQLite e Postgres 16); em UNIFICADA a leitura
    dupla dessas rotas some (workspace do vendedor 26 → 22 consultas).
- **Status**: ACEITA. Não liga a troca em produção.

## D-071 · 2026-09-26 · Phase J3 · Usuários do B2B ON Bid Intelligence (resolve OI-023)
- **Contexto**: D-059 definiu preço (R$ 1.490/mês) e AI Credits (25.000/mês) do Bid Intelligence, não os usuários.
  Decisão do PO em 2026-09-26.
- **Decisão**:
  - **10 usuários incluídos por tenant** (`plano.max_usuarios` = included_users), Public Sector Bids + Enterprise Bids.
  - **Usuários adicionais suportados** pela arquitetura: `licenca.usuarios_adicionais` (additional_user_quantity). O
    limite de assentos = incluídos + adicionais, lido pelo **entitlement** (`PlanLimitsProvider.obter_limite_usuarios`,
    `Entitlements.limite_usuarios`), sem número no código. **Preço por usuário adicional: PENDING_DEFINITION** — nenhum
    valor criado; a página mostra "Usuário adicional: preço em definição".
  - **AI Credits** continuam um pool do tenant (D-050), não multiplicado por usuário.
  - **Papéis externos não ocupam assento** (`PAPEIS_EXTERNOS`, hoje `supplier_guest`); o Supplier Guest segue entrando por
    link, sem usuário (D-066).
  - Migração `c5e7a9b1d3f4` preenche os 10 só onde ainda estava indefinido (não sobrescreve edição do Admin).
- **Status**: ACEITA. Resolve OI-023.

## D-072 · 2026-10-01 · Government Commercial Model (B2B ON Government)
- **Contexto**: prompt do PO "B2B ON GOVERNMENT — Licenciamento governamental + subscrição anual + pricing + publicação",
  com preços, AI Credits e política de comissão definidos por ele. O modelo privado (assinatura mensal) não muda.
- **Decisão**:
  - **Modelos de cobrança** (`plano.modelo_cobranca`): `MONTHLY_SUBSCRIPTION` (privado, inalterado),
    `GOVERNMENT_LICENSE_PLUS_ANNUAL_SUBSCRIPTION` (**oferta preferencial**: licença institucional + implantação +
    subscrição anual) e `GOVERNMENT_ANNUAL_SUBSCRIPTION_ONLY` (alternativa para edital/ETP/TR que exija só subscrição:
    licença 0; implantação, subscrição e pool informados na contratação; **sem preço público**).
  - **Ofertas iniciais** (catálogo central, tabela `plano`, `segmento = GOVERNMENT`, `tipo_preco = CONTRACT`, fora do checkout):
    | Oferta | Licença | Implantação | Subscrição anual | Contratação inicial | AI Credits/ano |
    |---|---|---|---|---|---|
    | B2B ON Government Department | R$ 72.000 | R$ 12.000 | R$ 24.000 | R$ 108.000 | 300.000 |
    | B2B ON Government Professional (**recomendada**) | R$ 120.000 | R$ 20.000 | R$ 36.000 | R$ 176.000 | 600.000 |
    | B2B ON Government Enterprise | R$ 180.000 | R$ 30.000 | R$ 54.000 | R$ 264.000 | 1.200.000 |
    Contratação inicial = Licença + Implantação + Subscrição Anual (calculada, não guardada). Diferenciação por
    **entitlements configuráveis** (`plano.entitlements`); limites por tier não definidos ficam "conforme contrato" (OI-024).
    Módulo inicial: Compras públicas (`procurement`).
  - **AI Credits anuais**: pool por período do contrato = um lote SUBSCRIPTION da **carteira universal** (mesmo ledger,
    FEFO, AI Gateway e trava de linha), com validade até o fim do período; o período seguinte concede um pool novo; plano
    com pool anual não recebe franquia mensal. Pacotes adicionais pelo catálogo existente ou como componente do contrato.
  - **Renovação**: período anual novo só com a subscrição (reajuste informado com o motivo/regra contratual; nenhum índice no
    código). A licença nunca é cobrada de novo. Aviso de renovação dentro da janela configurável
    (`GOVERNO_AVISO_RENOVACAO_DIAS`, padrão 90), pela rotina horária de AI Credits.
  - **Separação contábil**: componentes por tipo (LICENSE, IMPLEMENTATION, INITIAL/RENEWAL_ANNUAL_SUBSCRIPTION,
    ADDITIONAL_SERVICES, ADDITIONAL_AI_CREDITS). Bookings por tipo; **ARR só com subscrição**; New ARR = subscrição inicial;
    Renewal ARR = renovações; TCV inicial = licença + implantação + subscrição inicial; **Cash-In = recebimentos**.
  - **Pricing Catalog como source of truth**: página pública (`GET /catalogo` → seção "B2B ON Government"), Admin → Planos,
    proposta e contrato leem a tabela `plano`. Contrato guarda a cópia dos valores: mudar o preço não muda contrato antigo.
    Toda criação/alteração de plano é auditada (antes/depois, motivo, ator).
  - **Publicação**: seção "B2B ON Government" em `/planos` (sem "/mês", Professional destacado, textos de composição,
    renovação e adaptação ao edital) e link "Planos e preços" na página inicial (login). Admin → Planos ganha a tabela
    Government; Admin → Government opera pipeline, contratos, recebimentos, renovações e comissões.
  - **Comissão Government** sobre o motor existente (`comissao_representante` + repasse mensal): por componente, política
    versionada (`politica_comissao`, cópia no contrato). Inicial: licença 20%, subscrição inicial 20%, renovações 10% (todas),
    implantação não comissionável (flag configurável), serviços e créditos adicionais não comissionáveis até o PO configurar;
    gatilho **PAYMENT_RECEIVED** (proporcional a cada parcela). Base de cálculo: corrigida pela D-074 (Margem Comissionável
    Líquida, nunca a receita bruta); CONTRACT_SIGNED removido na D-074. Estorno: anula o não pago; o já pago vira
    CLAWBACK "a compensar". Dono = representante do contrato ou divisão; transferência e override exigem motivo e aprovador
    e são auditados; histórico preservado.
  - **Pipeline Government** (`oportunidade_governo`, super_admin) separado da quota de New MRR; ponderado = TCV × probabilidade.
  - **Proposta** por template versionado e configurável (`template_documento_comercial`), sem texto jurídico.
  - **MAP**: margem de contribuição por tenant — substituída pela waterfall da D-074.
- **Status**: ACEITA. Migração `d9e1f3a5b7c9` (reversível; não converte nenhum cliente privado).

## D-073 · 2026-10-01 · Comissão sobre o lucro líquido (todas as vendas) e adicionais Government a 10%
- **Contexto**: respostas do PO às pendências de D-072 (OI-024 e OI-025).
- **Decisão**:
  - **Base de toda comissão de representante** (planos privados e Government): o **lucro líquido** da CyberFort com o
    B2B ON naquele recebimento = valor recebido − impostos − custo de infraestrutura. Comissão = base líquida × taxa do
    representante (privado) ou do componente (Government) × fração da divisão.
  - Impostos e infraestrutura são **alíquotas sobre o valor recebido**, numa política versionada e auditada (`BASE_LIQUIDA`,
    Admin → Representantes / Government). O PO ainda não informou os valores: a versão 1 nasce **vazia** e, enquanto isso,
    a comissão é registrada como `pendente_parametros` (valor 0, nunca repassada). Ao definir as alíquotas, as pendentes
    são recalculadas; comissões já calculadas não mudam. Cada comissão guarda base bruta, alíquotas e versão aplicadas.
  - **Serviços adicionais e AI Credits adicionais** (Government): comissionáveis a **10%** (política Government versão 2).
  - A **margem de contribuição** do MAP usa as mesmas alíquotas (antes: variável de ambiente sem valor).
  - **Composição dos tiers** Government: confirmado pelo PO que a composição (módulos, usuários, unidades, SLA etc.) é o
    que diferencia Department, Professional e Enterprise; os valores por tier continuam a definir (OI-024).
- **Status**: **SUBSTITUÍDA pela D-074** quanto à base de cálculo (alíquotas soltas → Tax Profile e Infrastructure Cost
  Model; "lucro líquido" → Margem Comissionável Líquida). Continuam valendo: adicionais Government a 10% e a confirmação da
  composição dos tiers. Migração `e1f3a5b7c9d2` (reversível).

## D-074 · 2026-10-01 · COMMISSION POLICY DECISION — Margem Comissionável Líquida (correção definitiva do PO)
- **Contexto**: prompt do PO "CORREÇÃO DEFINITIVA — BASE DE CÁLCULO DAS COMISSÕES B2B ON". Substitui a base de cálculo da
  D-073 e corrige a D-072 (que calculava sobre a receita bruta).
- **Decisão**:
  - **Representative commission is calculated over Net Commissionable Margin**, defined as commissionable revenue received
    minus attributable taxes and attributable infrastructure costs. Em português: **Margem Comissionável Líquida** = receita
    comissionável recebida − impostos atribuíveis − custo de infraestrutura atribuível. Nunca sobre Gross Revenue, MRR, ARR,
    Bookings, TCV ou Cash-In bruto. Não é "lucro líquido da empresa" (despesas corporativas não atribuídas à venda não entram).
  - **Taxas**: venda privada B2B ON e contratação inicial Government (licença e subscrição inicial) **20%**; renovação da
    subscrição Government **10%** (em todas as renovações, salvo mudança explícita da política); serviços e AI Credits
    adicionais 10% (D-073); **implantação Government não comissionável por padrão**. Privado: taxa do representante.
  - **Commission amount requires valid tax and infrastructure parameters.** Sem Tax Profile ou Infrastructure Cost Model
    vigentes na data do recebimento, a comissão fica `AWAITING_COST_PARAMETERS` (taxa conhecida, valor não afirmado) com o
    parâmetro faltante (`TAX_PROFILE`, `INFRASTRUCTURE_COST`) e é recalculada automaticamente quando ele é informado.
  - **Commission Engine único** (`app/contexts/comissoes`): recebimento → classificação da receita → Tax Profile → alocação
    de infraestrutura → Margem Comissionável Líquida → política → CALCULATED → ACCRUED → PAYABLE → PAID. Vendas privadas e
    Government só registram o recebimento; nenhum módulo calcula comissão. Gatilho financeiro: **PAYMENT_RECEIVED**
    (CONTRACT_SIGNED removido; nota fiscal não existe na plataforma). PAYABLE exige parâmetros + receita recebida; parcela
    = base proporcional ao recebido.
  - **Tax Profile** (`perfil_tributario`): regime (PO: Lucro Presumido), vigência, tipo de receita, município, componentes,
    alíquota efetiva, método, fonte e notas — nenhuma alíquota no código; mudança tributária = perfil novo, sem mexer no motor.
  - **Infrastructure Cost Model** (`modelo_custo_infra`): componentes percentual, fixo por recebimento, por tenant, por
    produto/segmento e uso real de IA do tenant (ledger do AI Gateway), combináveis (HYBRID), com vigência. O custo de IA entra
    só pelo componente de uso, uma vez por recebimento (marca d'água), evitando dupla contagem com o percentual.
  - **Memória de cálculo** (`apuracao_comissao`, uma por recebimento): receita bruta, Tax Profile e valor dos impostos,
    modelo e valor de infraestrutura (e de IA), Margem Comissionável Líquida, taxa, valor e data. Mudança futura de parâmetro
    não altera comissão calculada; só recálculo explícito e auditado altera as **não pagas**; **PAID nunca muda**.
  - **MAP**: waterfall receita bruta → impostos → infraestrutura → Margem Comissionável Líquida → comissão → margem CyberFort
    após comissão, com percentuais, por venda, representante, produto, tenant e período.
  - **Legado**: comissões não pagas calculadas sobre o bruto voltam a `AWAITING_COST_PARAMETERS` (valor antigo guardado em
    `valor_bruto_legado`) e são recalculadas sobre a margem quando houver parâmetros; pagas ficam como estão.
- **Status**: ACEITA. Migração `f4a6b8c0d2e3` (reversível). Parâmetros (valores) pendentes do PO: OI-026.

## D-075 · 2026-10-01 · Resolução dos Open Issues OI-024, OI-026 e OI-018 (parâmetros do PO)
- **Contexto**: prompt do PO "RESOLUÇÃO DOS OPEN ISSUES — OI-024, OI-026 E OI-018". Complementa a D-072 (catálogo
  Government) e a D-074 (Commission Engine); a fórmula da comissão não muda.
- **OI-024 — entitlements Government (RESOLVED)**. Preços inalterados (Department 72k + 12k + 24k = 108k, 300k AI
  Credits/ano; Professional 120k + 20k + 36k = 176k, 600k, recomendado; Enterprise 180k + 30k + 54k = 264k, 1,2M).
  Entitlements do PO por tier — usuários internos 20/50/100; unidades administrativas 1/5/20; armazenamento 100/500/2.048 GB;
  retenção operacional 12/24/60 meses; CRM, MAP, PREDATOR, Bid Intelligence, Business Network e Corporate Brain em todos;
  Public Procurement BASIC/FULL/FULL; API não/sim/sim; SSO não/opcional/sim; suporte 8x5 horário comercial / 8x5
  prioritário / 8x5 crítico; onboarding padrão/avançado/dedicado. Persistidos no catálogo central (migração), cada valor num
  lugar só: usuários em `max_usuarios` (limite de assentos já aplicado), módulos em `modulos_contratados` (acesso real), API
  em `permite_api_parceiros`, o restante no JSON `entitlements` (validado). Página pública e Admin → Planos leem do mesmo
  `GET /catalogo`; o frontend só tem rótulos.
- **OI-026 — Tax Engine (PARTIALLY_RESOLVED)**. Regime **LUCRO_PRESUMIDO**. Nenhuma alíquota efetiva única vira regra: o
  Tax Profile é versionado por vigência (`effective_from/until`), tipo de receita, município e código de serviço, com um
  componente por tributo (IRPJ, IRPJ_ADDITIONAL, CSLL, PIS, COFINS, ISS, CBS, IBS, OTHER_TAX), e a comissão usa o imposto
  calculado tributo a tributo:
  - PIS 0,65% e COFINS 3,00% (cumulativos) sobre a receita;
  - IRPJ 15% e CSLL 9% sobre a **base presumida** (receita × percentual de presunção do tipo de receita). Serviços: 32%.
    Licença de software e SaaS: presunção **não assumida** (a informar);
  - adicional de IRPJ suportado (alíquota sobre a base presumida do período de apuração acima do limite configurado,
    rateada pelos recebimentos do período), sem valor criado;
  - ISS por município e código de serviço: **São Paulo/SP, 1.05** (licenciamento ou cessão de direito de uso de programas de
    computação) **2,90%** — não nacional; ISS de SaaS e de serviços de implantação a informar;
  - CBS 0,90% e IBS 0,10% (2026) como **alíquota-teste informativa**, com `aliquota_caixa_efetiva`, `compensado`,
    `dispensado` e `status_conformidade`: só o imposto de caixa efetivo entra na carga, e nada quando compensado ou
    dispensado — o 1% nunca é somado automaticamente.
  Perfis iniciais (São Paulo/SP, vigência 2026) para LICENCA_SOFTWARE, SAAS e SERVICO; componente sem valor deixa a
  apuração em `AWAITING_COST_PARAMETERS` com `TAX_PROFILE` faltante e os demais tributos como simulação no detalhe.
- **Infrastructure Cost Model**: estrutura pronta, **sem valor** (o PO não informou custo real validado). Categorias
  cloud, database, storage, network, observability, third_party e allocated_ai_infrastructure_cost; métodos FIXED,
  PER_TENANT, PER_USER, USAGE_BASED (só IA, medida no ledger) e PERCENTAGE; vários componentes = HYBRID. Enquanto não houver
  modelo, `commission_amount_status = AWAITING_INFRASTRUCTURE_COST` (prioridade sobre os demais faltantes; a lista completa
  fica em `missing_parameters`).
- **OI-018 — câmbio (OPEN)**: `FINOPS_CAMBIO_USD_BRL` (variável de ambiente) sai; a cotação vem da tabela
  `cotacao_cambio` (base, cotação, taxa, fonte, vigência), registrada no Admin e auditada. `AI_COST_BRL = AI_COST_USD ×
  cotação USD/BRL vigente no instante do custo`. Sem cotação: `AWAITING_FX_RATE` (FinOps e comissão), nunca estimado.
- **Custo de IA na comissão**: só quando a **Commission Policy da margem** (`NET_COMMISSIONABLE_MARGIN`, versionada e
  auditada) define `deduzir_custo_ia = true`. A versão 1 não deduz: existir no FinOps não basta. Impostos e infraestrutura
  continuam sempre deduzidos.
- **Fórmula mantida**: NET_COMMISSIONABLE_MARGIN = receita comissionável recebida − impostos atribuíveis − infraestrutura
  atribuível; 20% inicial, 10% renovação Government, implantação não comissionável por padrão; nunca Gross Revenue × taxa.
- **Status**: ACEITA. Migração `a6c8e0f2b4d7` (reversível).

## D-076 · 2026-10-01 · Infrastructure Cost Policy (conservadora) e parâmetros pendentes de OI-018/OI-024/OI-026
- **Contexto**: prompts do PO "RESOLUÇÃO OI-026 — INFRASTRUCTURE COST POLICY" e "RESOLUÇÃO DOS PARÂMETROS PENDENTES —
  OI-018 / OI-024 / OI-026". Substitui o Infrastructure Cost Model da D-075 (sem dados em produção) pelo pool de fornecedores;
  fórmula da comissão mantida.
- **Decisão (texto do PO)**: "CyberFort adopts a conservative provisioned infrastructure cost policy for commission
  calculations, initially based on the selected maximum provider plan/capacity, while maintaining actual infrastructure costs
  separately for FinOps and profitability analysis."
- **Infrastructure Cost Pool** (`componente_infra`, um motor só em `app/contexts/comissoes/infraestrutura.py`): fornecedor,
  serviço, categoria, plano atual e plano de referência (máximo), ciclo, moeda, custo contratado, custo de referência, custo
  real, capacidade, uso, unidade, vigência, método de alocação e notas — nenhum fornecedor ou valor no código.
  - **ACTUAL** (custo real) e **PROVISIONED** coexistem e nunca se misturam. Com `MAX_CONTRACTED_PLAN`, o provisionado é o
    custo integral do plano de referência, mesmo com uso baixo.
  - **Weighted Allocation**: unidades ponderadas = Σ tenants ativos × peso do tier do plano; custo por unidade = pool
    provisionado do mês ÷ unidades; custo do tenant = custo por unidade × peso. Pesos iniciais ENTRY/DEPARTMENT 1,
    PROFESSIONAL 2, ENTERPRISE 4, configuráveis (política `INFRASTRUCTURE_COST_POLICY`, versionada e auditada). Tier do plano
    no catálogo (`plano.tier_infraestrutura`): ofertas Government pelo tier; privados pelo nome (Starter = ENTRY, Professional,
    Enterprise); plano sem tier não entra na alocação e a comissão dele aguarda.
  - **Direct Attribution** tem prioridade: componente DIRECT recebe o consumo medido por tenant (`custo_direto_infra`); o
    restante do plano provisionado volta ao pool ponderado. Marca d'água por competência: um custo direto vai a um
    recebimento só.
  - **Sem dupla contagem**: componente contabilizado como `AI_COST` (IA, APIs e dados já medidos pelo FinOps) nunca entra no
    custo de infraestrutura; o custo de IA continua separado e só entra na margem pela política da margem (D-075).
  - **Atribuição temporal (metodologia)**: o custo do tenant-mês vai uma vez para a receita que remunera a operação daquele
    mês — mensalidade privada = 1 mês; subscrição anual Government = meses do período × fração recebida; licença, implantação
    e adicionais não carregam meses de operação. Sem pool com valores, toda comissão fica `AWAITING_INFRASTRUCTURE_COST`.
- **Comissão**: NET_COMMISSIONABLE_MARGIN = receita comissionável recebida − impostos atribuíveis − infraestrutura
  PROVISIONADA (política `custo_comissao`); 20% inicial, 10% renovação Government; nunca sobre Gross Revenue.
- **Capacidade**: status NORMAL < 70%, ATTENTION ≥ 70%, REVIEW ≥ 80%, CRITICAL ≥ 90%, CAPACITY_REACHED ≥ 100% (limiares
  configuráveis). REVIEW gera a recomendação "Revisar capacidade e condições comerciais do fornecedor."; CRITICAL, o alerta
  "Capacidade próxima do limite. Avaliar upgrade, contrato Enterprise, desconto por volume ou parceria estratégica."; 100%,
  "Contracted capacity reached.". Nenhum upgrade ou contratação automática: o alerta fecha com a decisão registrada.
- **Provider Economics e forecast**: por fornecedor — plano atual × referência, custos, capacidade, uso, utilização, custo por
  tenant, por unidade ponderada e ÷ receita, participação no pool (concentração, dependência), utilização projetada
  (30/90/180 dias) e data estimada de esgotamento por regressão linear do uso medido; projeção de custo e de custo ÷ receita
  pela tendência de tenants. Determinístico, sem LLM.
- **MAP**: receita, impostos, infraestrutura real, infraestrutura provisionada, custo de IA, Margem Comissionável Líquida,
  comissão, margem CyberFort após comissão, Actual Contribution Margin, Conservative Contribution Margin e reserva de
  infraestrutura (provisionado − real).
- **Tax Engine (OI-026)**:
  - tipos de receita separados: SOFTWARE_LICENSE, SAAS_SUBSCRIPTION, IMPLEMENTATION, CONSULTING, SUPPORT; serviço adicional
    leva a classificação no componente (sem ela, aguarda);
  - SOFTWARE_LICENSE: IRPJ 15% e CSLL 9% sobre base presumida de 32% (32% é base, não imposto); ISS São Paulo/SP item 1.05,
    código municipal 2800, 2,90%;
  - SAAS_SUBSCRIPTION: na categoria de serviço (presunção 32%) para simulação, classificação versionada para validação
    contábil; ISS/código de serviço a informar;
  - IMPLEMENTATION (suporte técnico, instalação, configuração, manutenção de software/banco de dados): item 1.07, código 2919,
    2,90%; consultoria ou outra atividade usa o perfil correspondente (CONSULTING/SUPPORT sem perfil ainda);
  - adicional de IRPJ: 10% sobre a parcela da base do IRPJ acima de R$ 20.000 × meses do período (trimestre: R$ 60.000);
  - regra de 2026: acréscimo de 10% nos percentuais de presunção sobre a parcela da receita acima de R$ 5.000.000/ano,
    proporcional ao período de apuração (35,2% em vez de 32%, nunca +10 pontos), versionada no perfil;
  - CBS 0,90% / IBS 0,10% (2026) com situação COMPENSATED, WAIVED_BY_COMPLIANCE, PAYABLE ou PENDING_COMPLIANCE_CONFIRMATION
    (só PAYABLE entra na carga; inicial: PENDING);
  - perfis por vigência com `effective_from/until`, `legal_version`, regime, tipo de receita, município, item LC 116 e código
    municipal; 2027+ exige perfil novo (nada estendido nem alíquota CBS definitiva inventada). Perfis da D-075 encerrados na
    própria vigência (histórico preservado).
  - Os cálculos de limite (adicional, acréscimo) consideram as receitas do B2B ON apuradas pelo motor.
- **Câmbio (OI-018)**: fonte BANCO_CENTRAL_DO_BRASIL, PTAX de fechamento (cotação de venda), par USD/BRL, do dia útil da
  contabilização; sem PTAX no dia, a última anterior. Obtida da API pública do Banco Central (rotina horária e botão no Admin)
  ou cadastrada; snapshot fx_rate, fx_date, source, retrieved_at; custo já fechado não é recalculado.
- **Government (OI-024)**: franquia mensal de contas do MAP/PREDATOR 1.000 / 3.000 / 10.000 (separada dos AI Credits
  300.000 / 600.000 / 1.200.000 por ano). Public Procurement BASIC (gestão de demandas, workspace de processos, PCA, cadastro
  de fornecedores, pesquisa de preços básica, documentos, tarefas, prazos, workflow básico, acompanhamento de contratos,
  painel, trilha de auditoria) e FULL (BASIC + Supplier 360, grafo, Document Intelligence/RAG, ETP/TR/Edital Intelligence,
  matriz de conformidade, avaliação, agente, Next Best Action, Risk Engine, comparação de propostas, inteligência de
  contrato, SLA, aditivos, renovação, analytics avançado, APIs) como capabilities do mesmo motor (`has_capability`); plano sem
  nível (privado) mantém todas.
- **Status**: ACEITA. Migração `b7d9f1a3c5e8` (reversível).

## D-077 · 2026-10-01 · Preços públicos verificados dos fornecedores no Infrastructure Cost Pool (OI-026)
- **Contexto**: prompt do PO "RESOLUÇÃO OI-026 — INFRASTRUCTURE COST POOL COM VALORES PÚBLICOS VERIFICADOS DOS FORNECEDORES".
- **Decisão (texto do PO)**: "Provider pricing researched and verified on 2026-10-01. Use the highest publicly priced
  plan/capacity applicable to the actual B2B ON architecture. Custom-priced plans must never receive invented prices."
- **Pool da comissão** = componentes vigentes **E** aplicáveis à arquitetura (APPLICABLE ou APPLICABLE_PENDING_CONFIRMATION)
  **E** `provisionado_para_comissao`, dos pools que a política inclui (INFRASTRUCTURE e DATA_PROVIDER). AI_COST nunca entra.
  Mesmo fornecedor/serviço: vale a fonte de maior prioridade (fatura/contrato > proposta comercial > preço público > manual).
- **Preços verificados (páginas oficiais, 2026-10-01; revisão prevista 2026-12-30)**:
  - Render Workspace **Scale USD 499/mês** e Web Service **12 CPU/96 GB USD 1.500/mês** — envelope base USD 1.999/mês; em uso
    pelo que o repositório mostra (`render.yaml`: API `b2bon-api`), **a confirmar**; Enterprise **CUSTOM** (sem preço).
  - Render Postgres (até USD 11.000/mês) e Key Value (até USD 1.100/mês): **AVAILABLE_NOT_ALLOCATED** — o banco principal é o
    Neon (DEPLOY.md) e não há Key Value na arquitetura; entram só se passarem a ser usados.
  - Render Persistent Disk USD 0,25/GB-mês: por uso, **não alocado** (sem disco na arquitetura; depende de storage envelope).
  - Neon **Scale por uso** (USD 0,222/CU-hora, USD 0,35/GB-mês), banco principal: sem preço mensal fixo — o provisionado vem do
    **Capacity Envelope** (horas de CU e GB decididos pela CyberFort). O exemplo oficial (4–10 CU, 100 GB ≈ USD 1.404/mês) é só
    `benchmark_only`.
  - Lusha **Premium USD 399,90/mês** (3.400 créditos, 5 assentos) no pool **DATA_PROVIDER**, alocação direta com prioridade;
    Lusha Scale **CUSTOM** (contrato anual) sem preço — se contratado, entra o valor do contrato com nova vigência.
- **Capacity Envelope** (`envelope_capacidade`): fornecedor, serviço, máximo de CU, horas de CU e GB provisionados, preços
  unitários, outros custos, custo mensal estimado, moeda, vigência, fonte, verificação e `benchmark_only`.
- **Dupla contagem**: cada despesa pertence a um pool só; o mesmo fornecedor/serviço/plano/fonte não entra duas vezes;
  dois componentes aplicáveis na mesma função arquitetural (ex.: Neon e Render Postgres como PRIMARY_DATABASE) só coexistem
  com a coexistência justificada (uso real dos dois).
- **Fonte e auditoria** de cada custo: fornecedor, serviço, plano, modelo de preço (FIXED_PLAN, USAGE_BASED, CUSTOM), preço
  publicado, moeda, ciclo, URL e tipo da fonte (OFFICIAL_PUBLIC_PRICING, CONTRACT, COMMERCIAL_PROPOSAL, INVOICE,
  MANUAL_APPROVED), verificado em, próxima revisão, vigência, override manual com motivo. Revisão vencida aparece nas
  pendências. Mudança de preço **não recalcula** comissão PAYABLE ou PAID (snapshot da apuração).
- **Pesos**: STARTER/DEPARTMENT 1, PROFESSIONAL 2, ENTERPRISE 4, BID_INTELLIGENCE 2, STRATEGIC_SOURCING 4 (configuráveis; o
  tier ENTRY passa a STARTER; Strategic Sourcing e Strategic Sourcing Enterprise = STRATEGIC_SOURCING).
- **Capacidade não alocada**: sem tenants, nada é dividido (sem divisão por zero) e o pool inteiro aparece como
  UNALLOCATED_INFRASTRUCTURE_CAPACITY. Com `capacidade_unidades` na política (capacidade compartilhada para a qual o pool foi
  dimensionado), cada unidade custa pool ÷ capacidade e a parte não absorvida pela base fica separada como custo de
  capacidade ociosa da plataforma — uma venda não carrega 100% do envelope.
- **Comissão**: NET_COMMISSIONABLE_MARGIN = receita comissionável recebida − impostos atribuíveis − infraestrutura
  provisionada atribuível; 20% inicial; 10% renovação Government. Custos em USD pela PTAX de fechamento do Banco Central.
- **Status**: ACEITA. Migração `c8e0a2b4d6f9` (reversível).

## D-078 · 2026-10-01 · CBS/IBS 2026 — WAIVED_BY_COMPLIANCE (resolução definitiva)
- **Contexto**: prompt do PO "RESOLUÇÃO DEFINITIVA — CBS / IBS 2026".
- **Referência legal**: EC 132/2023 (ADCT, art. 125 — em 2026 CBS à alíquota de 0,9% e IBS de 0,1%, compensáveis com
  PIS/COFINS) e LC 214/2025 (regras de transição de 2026 — dispensa do recolhimento da CBS/IBS para os contribuintes que
  cumprem as obrigações acessórias). Configuração aprovada pelo PO em 2026-10-01.
- **Decisão**: "2026 default operational status for CyberFort = WAIVED_BY_COMPLIANCE. CBS test rate = 0.90%. IBS test rate =
  0.10%. Cash tax effect = zero while compliance conditions for statutory waiver are satisfied. If actual accounting status
  changes, create a new effective TaxStatusPeriod."
- **Implementação**:
  - `periodo_status_tributario` (TaxStatusPeriod): grupo CBS_IBS, situação, vigência (2026-01-01 a 2026-12-31), motivo,
    aprovador, evidência, referência legal, data da alteração. A situação do período prevalece sobre a do componente.
  - Alíquotas-teste preservadas nos Tax Profiles (CBS 0,90%, IBS 0,10%, vigência 2026). NOMINAL_TEST_TAX (alíquota × receita,
    para auditoria) separado do CASH_TAX.
  - WAIVED_BY_COMPLIANCE e PENDING_COMPLIANCE_CONFIRMATION: caixa zero — CBS/IBS não reduzem a Margem Comissionável Líquida.
    PAYABLE: recolhimento entra na carga. COMPENSATED: registra CBS_IBS_PAID, PIS_COFINS_OFFSET (até o PIS/COFINS da mesma
    receita) e NET_TAX_EFFECT (só o excedente) — nunca CBS/IBS + PIS/COFINS integrais. Nenhuma situação é assumida PAYABLE.
  - NET_COMMISSIONABLE_MARGIN = receita comissionável recebida − impostos de CAIXA atribuíveis − infraestrutura provisionada.
  - Mudança de situação = nova vigência (o período aberto anterior é encerrado no dia anterior; histórico nunca reescrito),
    auditada; comissões PAYABLE/PAID guardam o snapshot (tax_profile_id, alíquotas-teste, situação, caixa de CBS e IBS,
    compensação, total atribuível, calculado em).
  - MAP: CBS Test Rate 0,90%, IBS Test Rate 0,10%, situação 2026 ("Dispensado de recolhimento mediante conformidade"), CBS e IBS
    Cash Tax R$ 0 — nunca "CBS = 0%".
- **Status**: ACEITA. Migração `d0f2b4c6e8a1` (reversível).

## D-079 · 2026-10-01 · Render Web Service 12c-96g como CUSTOM
- **Contexto**: validação dos preços da D-077 nas fontes dos fornecedores. A página oficial do Render não publica preço para o
  Web Service 12 CPU / 96 GB (o maior plano padrão com preço é o Pro Ultra; instâncias maiores são sob consulta), então os
  USD 1.500/mês da D-077 não tinham fonte. O inventário real do Render (2026-10-01) mostra `b2bon-api` e `b2bon-api-staging` no
  plano free, sem Render Postgres nem Key Value. Os preços do Neon (USD 0,222/CU-hora, USD 0,35/GB-mês) foram confirmados na
  página oficial; o exemplo de USD 1.404 não aparece nela e segue apenas como benchmark.
- **Decisão do PO**: "Marque 12c-96g como CUSTOM e aplique a migração."
- **Implementação**: o componente RENDER · WEB_SERVICE_COMPUTE (12c-96g) passa a `modelo_preco = CUSTOM`, sem
  `custo_referencia`; continua APPLICABLE_PENDING_CONFIRMATION e provisionado para comissão. Sem contrato, proposta ou fatura,
  o pool fica com INFRASTRUCTURE_COST faltante e as comissões aguardam — nunca um valor inventado. A pendência aparece como
  "Valor de contrato, proposta ou fatura (CUSTOM)". A alteração é registrada no audit_log (antes/depois, motivo).
- **Status**: ACEITA. Migração `e2a4c6e8f0b3` (reversível).

## D-080 · 2026-10-01 · MAP Performance Comercial — quotas, funil, comissão recorrente e Summer Sales Challenge
- **Contexto**: prompt do PO "Ajuste do MAP: Quotas, Funil, Comissão e Campanha" — gerir quota, ramp-up, funil,
  produtividade, comissão, campanha e exceções dos 7 representantes autônomos reutilizando CRM/PREDATOR/MAP.
- **Reuso (sem subsistema novo)**: `Representante` (+ `usuario_id`, o usuário dele no CRM da CyberFort); CRM interno
  (`Atividade`, `Reuniao`, `Negocio`, `PropostaNegocio`, `Conta`, `Decisor`) lido só via `crm.contract`; New MRR pela 1ª
  mensalidade aprovada (`PagamentoLicenca` de tenants com `representante_id`); comissão do Commission Engine (D-074);
  Government pelo pipeline existente (`OportunidadeGoverno`, `ContratoGoverno`); políticas versionadas em
  `politica_comissao`; eventos de domínio existentes. Única tabela nova: `quota_comercial` (versionada).
- **Quota**: métrica NEW_MRR = 1ª mensalidade efetivamente paga de cliente novo do representante (PRIVATE).
  Por representante: Out/26 R$ 7.500, Nov R$ 10.000, Dez R$ 12.500, Jan/27 R$ 15.000, Fev R$ 17.500, Mar R$ 20.000
  (equipe de 7: R$ 52.500 → R$ 140.000, soma das quotas efetivas). Quota padrão por competência ou específica do
  representante, versionada e auditada. Ganho no CRM sem 1ª mensalidade aparece como "fechado no CRM", não como New MRR.
- **Cobertura**: alvo = `pipeline_alvo` da quota (Out/26: R$ 30.000 por representante) ou múltiplo × quota (padrão 3x).
  Pipeline qualificado = negócios abertos do representante no CRM (valor = MRR esperado).
- **Funil e atividade**: baseline Out/26 (400 contas → 30% → 35% → 60% → 60% → 33%) e metas diária/semanal na política;
  taxas observadas numa janela de 90 dias substituem o baseline só com amostra mínima (20). "Conta trabalhada" = ICP
  validado (ICP vinculado ou aderência ≥ 0,6) + persona/contato alvo (decisor) + ação comercial registrada por uma pessoa;
  atividade automática (sem usuário) nunca conta — o MAP não premia spam.
- **Mix e ticket**: ticket baseline R$ 1.750; alvo Suite 50%, PREDATOR 20%, Bid Intelligence 15%, Strategic Sourcing 10%,
  MAP/CRM 5%; Mix Quality = participação de Suite + Bid Intelligence + Strategic Sourcing ≥ 50% — indicador, nunca bloqueio.
  Família do plano por regra da política (segmento, categoria ou módulo); do negócio no CRM, por `familia_por_oferta`.
- **Sales velocity**: FAST (módulos, ~15 dias), CORE (Suite, ~45), STRATEGIC (Government, ~90–180); forecast = New MRR +
  ponderado dos negócios cujo fechamento previsto (criação + dias da classe) cai na competência. Government aparece em TCV,
  separado do MRR privado.
- **Governo**: meta de 2 oportunidades governamentais qualificadas/semana; Government Qualified, License, Annual
  Subscription Pipeline e Expected Close. A política rejeita `conta_na_quota_privada = true`: pipeline e bookings
  governamentais nunca compensam a quota privada. Comissão Government segue a política própria (D-072/D-074).
- **Comissão privada**: política `PRIVATE_RECURRING_COMMISSION` v1 — 20% recorrente, gatilho PAYMENT_RECEIVED (só
  mensalidade paga gera comissão), por representante, cliente, produto, competência, status e situação da carteira.
  A base continua a Margem Comissionável Líquida do recebimento (D-074, decisão definitiva do PO); confirmado pelo PO em
  2026-10-01 (OI-028 resolvido: "mantenha essa informação, o texto está desatualizado").
  Inadimplência (ciclo 30 + tolerância 10 dias) com ação HOLD: a comissão PAYABLE do cliente fica retida no repasse até ele
  voltar a pagar. Cancelamento STOP_FUTURE: sem mensalidade paga, sem comissão.
- **Summer Sales Challenge** (`CAMPAIGN:SUMMER_SALES_CHALLENGE_2026`): Dez/26 + Jan/27, meta individual R$ 27.500 (equipe
  R$ 192.500); bônus sobre a comissão das NOVAS vendas da janela (clientes com 1ª mensalidade na janela) — a carteira
  histórica nunca entra; faixas <100% 0, 100–119% +20%, 120–149% +35%, ≥150% +50%; elegibilidade: venda em cada mês,
  CRM atualizado (≥ 90% das oportunidades com ação nos últimos 7 dias), carteira adimplente e sem bloqueio por política
  comercial. Bônus PROJECTED durante a campanha e FINAL depois dela.
- **MAP Intelligence**: regras determinísticas (atividade alta + ticket baixo, cobertura < alvo, proposta sem atividade,
  oportunidade estagnada, conversão baixa, mix low-ticket, risco de quota, gap coberto pelo pipeline do mês). IA não é
  usada: o sinal é reproduzível pela regra. Daily Comercial: só exceções (CRITICAL/HIGH ou pendência), gap, até 5 negócios
  que destravam a quota e próximas ações.
- **Permissões**: super_admin = gestão comercial (equipe, Daily, configuração, painel de qualquer representante);
  usuário vinculado a um representante vê só o próprio painel; dados de CRM sempre do tenant do usuário vinculado.
- **Eventos**: `MeetingCompleted` passa a ser publicado (`reuniao_service.marcar_resultado`); novo `ProposalSent`
  (`proposta_service.anexar`). Quota e políticas: versões + `audit_log`.
- **Desempenho**: agregações agrupadas por vendedor com número fixo de consultas (painel de 1 ou de 7 representantes custa
  o mesmo); índices compostos em atividade, reunião e negócio; abas carregadas sob demanda; no máximo 20 negócios no
  painel individual e 5 por representante no Daily. Sem tabela de read model: as agregações medidas (p95 ≈ 45 ms) não
  justificam a complexidade de manter um snapshot.
- **Status**: ACEITA. Migração `f3b5d7f9a1c4` (reversível).

## D-081 · 2026-10-01 · MAP Performance pronto para receber a configuração depois (time de tamanho variável)
- **Contexto**: o PO pediu para deixar tudo pronto para receber depois o vínculo dos representantes, o produto de cada
  oferta e o critério de contato efetivo: "os representantes estão em processo de contratação e eventualmente o número
  pode ser diferente de 7 (maior ou menor)".
- **Decisão**:
  - Nenhum número de representantes é fixo: quota da equipe = soma das quotas efetivas dos ativos; a quota padrão vale
    para todo representante ativo (novo entra automaticamente; inativo sai); a meta de equipe do Summer Sales Challenge
    deixa de ser R$ 192.500 fixos e passa a ser a meta individual × representantes ativos (`meta_equipe` = null, nova
    versão da campanha). Representantes entram e saem por Admin → Representantes.
  - Prontidão (`/map/performance/configuracao` → `prontidao`): representantes ativos, vinculados e sem vínculo, ofertas do
    CRM dos representantes ainda sem produto, critério de contato efetivo provisório ou confirmado e a lista de pendências.
    As pendências aparecem também no Daily e na Equipe até tudo estar configurado.
  - Configuração guiada (só gestor, com motivo, versão nova e auditoria): busca de usuário por nome/e-mail para o vínculo
    (mostra o tenant e se já está vinculado); oferta → produto (só ofertas do CRM dos representantes); confirmação dos tipos
    de ação que contam como contato efetivo (`definicoes.contato_efetivo_confirmado`). Até lá, ligação e reunião valem
    como critério provisório.
  - Semente das políticas segura contra requisições simultâneas (savepoint e releitura) e listagem de quotas com uma
    linha por escopo.
- **Status**: ACEITA. Migração `a8c0e2f4b6d9` (reversível).

## D-082 · 2026-10-01 · Ambiente de demonstração público, isolado por sessão e com dados fictícios
- **Contexto**: o PO pediu uma conta de demonstração com dados fictícios em todos os módulos (empresas, vendedores,
  oportunidades, RFP, pregão eletrônico, negócios futuros com governo, fornecedores, mapeamento de oportunidades,
  prospecção, cadência, agenda) e um link para publicar no site, sem login e senha reais, usável pelos representantes
  ao mesmo tempo.
- **Decisão**: em vez de uma conta compartilhada (em que um representante mexeria nos dados do outro durante uma
  apresentação e alguém poderia apagar tudo), **cada acesso ao link cria um tenant de demonstração próprio** — já
  preenchido, expira em 8 horas e é apagado depois. Desligado por padrão (`DEMO_HABILITADA`).
- **Implementação**:
  - `tenant.demo_expira_em` (nulo = tenant real); rota pública `POST /auth/demonstracao` (limite por IP) devolve um
    token sem senha, marcado `demo`, que expira junto com o ambiente; `GET /auth/demonstracao` diz se está ligada.
  - Semente (`app/services/demo/semente.py`): empresa fictícia Atlas Soluções Industriais com equipe, ICPs, ofertas,
    contas, decisores, negócios em todos os estágios, propostas, atividades, reuniões, cadências, fila de aprovação,
    campanha, sinais do MAP, NPS e necessidades; licitações (pregão, SRP, RFP privado, futuras do PCA, NO-GO, ganha),
    compras públicas (PCA, demandas, processo em pesquisa de preços, fornecedores, contratos) e sourcing (RFP avaliado,
    RFQ). Fluxos com regra passam pelas mesmas funções da API. E-mails `*.demo.invalid`, sem CNPJ real. O lado
    comprador semeia a si mesmo (`procurement/demonstracao.py`), registrado em `shared/demonstracao.py` — a barreira
    Buy/Sell continua intacta (quem monta a demonstração nunca importa procurement).
  - Salvaguardas: e-mail e WhatsApp do tenant de demonstração por provedores simulados; middleware bloqueia rede de
    empresas, administração da plataforma e ações que geram custo, acesso ou contato externo; perfil fora do diretório;
    sem franquia mensal de IA (só os créditos da demonstração, que expiram); teto de sessões ativas; tenants de
    demonstração fora das visões da plataforma (lista de tenants, motor de churn).
  - Limpeza: varredura do schema (`tenant_service.apagar_dados`, a mesma da exclusão definitiva) a cada nova sessão e
    na rotina horária `/cron/creditos-ia`.
  - Correção encontrada no caminho: o vínculo representante → usuário (D-080) criava um ciclo de FKs que desordenava a
    exclusão definitiva de tenants; `use_alter` na FK resolve.
- **Publicação**: `docs/b2bon/DEMONSTRACAO.md` (passo a passo).
- **Status**: ACEITA. Migração `b9d1f3a5c7e0` (reversível).

## D-083 · 2026-10-01 · Endurecimento da demonstração pública antes de ligar em produção
- **Contexto**: o PO autorizou ligar a demonstração com a condição de que ela não seja "uma porta aberta" para invasores.
- **Achados da revisão** (corrigidos antes de ligar): a lista de bloqueio da D-082 deixava passar, numa sessão anônima,
  serviços pagos ou reais da CyberFort — e-mail de sistema (SendGrid), agenda Google, robô de gravação (Recall.ai),
  enriquecimento (Lusha), busca web (Brave), pagamento (Mercado Pago), acesso a sites e gravação no Neo4j compartilhado
  — e toda rota nova nasceria aberta para a demonstração. O limite por IP olhava o IP do proxy do Render.
- **Decisão**:
  - **Negação por padrão**: o token de demonstração só alcança as rotas das telas de produto listadas em
    `app/services/demo/bloqueio.py` (dados do próprio tenant fictício); todo o resto — administração, usuários, convites,
    credenciais, integrações, rede de empresas, pagamentos, LGPD, API de parceiros e qualquer rota futura — responde 403.
  - **Todo provedor externo simulado** na requisição de demonstração (`demo_contexto`): e-mail, WhatsApp, agenda, robô de
    reunião, enriquecimento, busca web, pagamento, acesso a sites e grafo (`GrafoNulo`). A IA (Claude) continua real,
    limitada aos créditos da sessão.
  - **Desligar invalida na hora**: com `DEMO_HABILITADA=false`, tokens de demonstração já emitidos recebem 403.
  - **Limites**: 10 novas demonstrações por hora por IP real (último item do X-Forwarded-For, que o cliente não forja),
    120 por hora no total e 60 abertas ao mesmo tempo.
  - Mantidos da D-082: tenant isolado e efêmero, usuário sem senha, token assinado que expira com o ambiente, dados de
    outros tenants inalcançáveis, fora do diretório da rede, créditos de IA próprios, limpeza automática.
- **Verificação**: testes de rota proibida (incluindo rota inexistente), token adulterado, demonstração desligada,
  provedores simulados com credenciais reais configuradas, marca de demonstração propagada até a rota e limite por IP
  real; varredura das 27 telas da demonstração no navegador (146 chamadas, nenhuma bloqueada indevidamente).
- **Status**: ACEITA. Sem migração.

## D-084 · 2026-10-01 · Exclusão definitiva com referências de outros tenants; câmbio com fonte de reserva
- **Contexto** (produção): excluir o revendedor desligado "Dayanne Mendes" falhava com HTTP 500 para o gestor e para o
  Super Admin — `ForeignKeyViolation` em `fk_conta_vendedor_usuario_id`: o distribuidor (tenant pai) tinha uma conta
  atribuída à vendedora do revendedor, e a varredura só apaga linhas do próprio tenant. Além disso, a FK
  `pagamento_licenca.tenant_id` impedia apagar qualquer tenant que já tivesse pago, embora a tabela já ficasse fora da
  varredura justamente para sobreviver (retenção fiscal). Na Central de Negócios, o câmbio seguia "não disponível": a
  AwesomeAPI devolve 429 de forma sustentada ao IP de saída do Render (os índices, do Yahoo, funcionavam).
- **Decisão**:
  - Antes de varrer, `apagar_dados` solta as referências aos usuários do tenant: coluna anulável → NULL (a conta ou
    negócio da outra empresa fica sem responsável, não some); coluna obrigatória em tabela sem tenant (ex.: token de
    redefinição de senha) → apagada com o usuário; coluna obrigatória em linha de OUTRO tenant → recusa com mensagem
    clara antes de apagar qualquer coisa. Qualquer erro de integridade restante vira mensagem (nunca 500).
  - `pagamento_licenca.tenant_id` deixa de ter FK (coluna e índice mantidos): o histórico de pagamento sobrevive ao
    tenant, como já estava decidido.
  - Câmbio: AwesomeAPI primeiro; o que faltar (moedas e cripto) vem do Yahoo Finance em BRL. Ouro fica fora do reserva
    (o Yahoo cota em USD por onça — outra unidade; ausente é melhor que um número diferente). Notícias: cache de 10 min,
    a página consulta a cada 5 min, mais recentes primeiro, portal fora do ar mantém as últimas matérias dele, e a tela
    mostra "atualizado às" e há quanto tempo cada matéria saiu.
- **Acesso**: o usuário Admin do PO no tenant CyberFort passou a Super Admin (operação registrada em `audit_log`,
  reversível) — gerir tenants de todas as redes e representantes é atribuição do Super Admin, que continua não podendo
  ser concedido pela interface.
- **Status**: ACEITA. Migração `c0e2a4b6d8f1` (reversível; o downgrade descarta pagamentos de tenants já apagados).

## D-085 · 2026-10-02 · Demonstração abre na hora: reserva de ambientes já preenchidos
- **Contexto**: com a demonstração ligada em produção, cada clique levava de 65 a 171 s (logs do Render) e 4 de 7
  tentativas foram abandonadas pelo navegador. Preencher um ambiente custa ~635 consultas (e a limpeza de vencidos, ~200
  por ambiente); no Postgres local é 1,5 s, mas em produção cada consulta é uma ida e volta de rede até o Neon.
- **Decisão**: manter `DEMO_RESERVAS` (padrão 3) ambientes já preenchidos. Reserva = tenant de demonstração com
  `demo_expira_em` além de agora + TTL + 1 h (vale TTL + 24 h); o clique reivindica a mais antiga com
  `FOR UPDATE SKIP LOCKED` (dois cliques nunca levam a mesma), traz a expiração para agora + TTL e entra como a
  gestora — 5 consultas. Sem reserva, preenche na hora (comportamento anterior). A limpeza de vencidos e a reposição
  rodam em segundo plano (após cada clique, na consulta de disponibilidade e na rotina horária), uma por processo de
  cada vez. Reservas não contam no teto de sessões ativas.
- **Segurança**: inalterada — cada sessão continua com tenant próprio, token que expira com ele, negação por padrão
  e provedores simulados (D-083). A reserva nunca é entregue a duas sessões.
- **Status**: ACEITA. Sem migração.
- **Adendo (2026-10-02)**: no celular (Samsung Internet, base Chrome 143) o /demo mostrava "Não foi possível abrir a
  demonstração agora" — a checagem prévia de CORS (OPTIONS) voltava 400 antes de chegar à rota. Navegadores recentes
  (Private/Local Network Access) pedem `Access-Control-Request-Private-Network`, que o Starlette recusa por padrão.
  `allow_private_network=True` (a origem continua restrita a `CORS_ORIGINS`; a API já é pública) e toda recusa de
  checagem prévia passa a ser registrada com o motivo (`b2bon.cors`).
- **Adendo 2 (2026-10-02)**: o Sentry acusou `TypeError` no cron `/processar-retorno` em cada ambiente de
  demonstração — `horario_confirmado` volta do Postgres sem fuso e era subtraído de `datetime.now(UTC)` (afetaria
  qualquer tenant com reunião confirmada). Corrigido em `reuniao_service.processar_lembretes`. E as rotinas de envio,
  retorno (lembretes/NPS), campanhas e retenção passam a ignorar tenants de demonstração (`_tenants_reais`): nada sai
  deles fora da sessão do visitante. Verificado em produção que nenhum envio real partiu das demonstrações.
