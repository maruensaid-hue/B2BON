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
