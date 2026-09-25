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
