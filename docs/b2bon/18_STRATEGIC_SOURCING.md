# 18 — STRATEGIC SOURCING & BIDS (correção arquitetural, 2026-09-26)

> **Natureza**: correção de arquitetura, desenho de domínio e plano. **Nada
> foi implementado**: sem schema novo, sem UI de RFP Enterprise, sem
> workflows, agentes ou integrações novos. ADR: D-055.
> Documentos afetados: 00, 02, 03, 04, 05, 06, 10, 12, 13, 14.

## 0. Os quatro segmentos

```
B2B ON PLATFORM
│
├── REVENUE INTELLIGENCE
│   └── (1) B2B Sales ............ CRM · PREDATOR · MAP · Opportunity Intelligence · Business Network
│
└── STRATEGIC SOURCING & BIDS
    ├── SELL SIDE
    │   ├── (2a) Public Sector Bids ...... Opportunity Radar · Tender Intelligence · Requirement Analysis ·
    │   │                                   Compliance Matrix · Go/No-Go · Bid Workspace · Proposal Support ·
    │   │                                   Contract Intelligence
    │   └── (2b) Enterprise Bids ......... os mesmos, para RFP/RFI/RFQ privados (vendor questionnaire)
    └── BUY SIDE
        ├── (3) Public Procurement ....... Demand · Planning/PCA · Process · Supplier · Evaluation ·
        │                                   Contract · Risk · Audit
        └── (4) Enterprise Strategic Sourcing .. Supplier Discovery · RFI · RFP · RFQ · Vendor Qualification ·
                                            Proposal Comparison · Evaluation · Negotiation · Contract
```

O prompt de correção lista quatro segmentos de negócio: (1) Sales, (2) Public Sector Bids, (3) Public
Procurement e (4) Enterprise Strategic Sourcing. O **Enterprise Bids** (2b) é a metade vendedora do
Enterprise e entra no mesmo segmento (2), com outro *ruleset*. Os segmentos são **experiências
configuradas** sobre engines compartilhados, não quatro sistemas (§3 do prompt).

## 1. Gaps encontrados (auditoria do código em `staging`, commit `0c79518`)

### 1.1 Cobertura de negócio

| # | Gap | Evidência |
|---|---|---|
| G1 | **Enterprise Bids só existe como valor de enum.** `licitacao.modalidade` aceita RFP/RFI/RFQ/EOI/PRIVATE_RFP, mas o modelo e a UI são do setor público: `orgao_nome`/`orgao_cnpj` como emissor, status e textos de licitação, menu "Licitações", módulo `bids` vendido como *Public Sector*. Não há emissor empresa (Organization), vendor questionnaire nem ruleset privado | `app/models/licitacao.py`, `contexts/bids/tipos.py`, `pages/bids/*` |
| G2 | **Enterprise Strategic Sourcing (buy side privado) não existe.** Todo o buy side é público: `orgao_publico`, `regime_juridico`, PCA, demanda de órgão. Não há emissão de RFx para fornecedores, convite, recebimento e comparação de propostas, qualificação de fornecedor ou rodada de negociação | `contexts/procurement/*` |
| G3 | **Avaliação de proposta (buy) inexistente.** A matriz de conformidade responde "atendemos?" (sell); nada responde "esta proposta atende?" (buy) | `bids/conformidade.py` |
| G4 | Sem entidade de **Participante/Proposta**: concorrentes e parceiros são JSON em `licitacao`; `valor_proposta` é coluna do processo | `licitacao.concorrentes`, `parceiros` |
| G5 | **Lotes e itens** existem só no modelo canônico (`ProcurementLot/Item`), sem tabela | `04_CANONICAL_MODEL.md` §3 |

### 1.2 Duplicação já presente entre Bids (2.157 linhas nos dois contextos) e Procurement

| # | Duplicação | Onde | Observação |
|---|---|---|---|
| D1 | Duas tabelas de documento com as mesmas 15 colunas (hash, fonte, texto por página, status da análise) | `documento_licitacao`, `documento_compras` | só diferem em FK do pai, `classificacao` e `achados` |
| D2 | Dois pipelines de extração com o mesmo laço (blocos → IA → âncora literal → página calculada → cláusula) | `bids/analise.py`, `procurement/documentos.analisar` | o *grounding* já está em `shared/grounding.py`; o laço e o destino do resultado, não |
| D3 | **Requisito armazenado de dois jeitos**: tabela `requisito_licitacao` (sell) × JSON `documento_compras.achados` (buy) | idem | buy não tem revisão por item, busca nem matriz |
| D4 | Dois contratos: `contrato_venda_publica` × `contrato_compra` | `bids/contratos.py`, `procurement/contratos.py` | mesmos campos centrais (objeto, valor, vigência, status) |
| D5 | Dois workspaces (backend e frontend) | `bids/workspace.py` + `LicitacaoWorkspace.tsx` (444) × `procurement/workspace.py` + `ProcessoWorkspace.tsx` (185) | mesmas seções: documentos, timeline, requisitos/achados, contrato, insights |
| D6 | Prazos e eventos com dois modelos: prazos calculados (sell) × `evento_processo` (buy) | `bids/prazos.py`, `evento_processo` | Tasks/Deadlines/Clarifications/Approvals sem entidade comum |
| D7 | Quatro implementações de *score* de aderência sem base comum | `predator/prospeccao.score_aderencia` (ICP), `opportunity/nbo.avaliar` (oferta), `services/sinal_oportunidade_service` (intenção e match da rede, com explicação por IA `network.explicar_match`), `procurement/fornecedores.ranking_por_categoria` (fornecedor) | cada uma com seu formato de fator, evidência e "desconhecido" |

### 1.3 Regras e fluxo

| # | Gap | Evidência |
|---|---|---|
| R1 | Fluxo codificado em tuplas de status por contexto (`STATUS_LICITACAO`, `STATUS_PROCESSO`) | `bids/tipos.py`, `procurement/tipos.py` ("parametrizável por órgão no futuro") |
| R2 | Regra regulatória espalhada: documentos esperados por etapa (dict), sigilo do valor estimado (coluna), fragmentação (`riscos.py` + `orgao.parametros`) | `procurement/tipos.DOCUMENTOS_ESPERADOS`, `riscos.py` |
| R3 | Regime jurídico já é parâmetro do órgão (D-036), mas não há objeto *ruleset* versionado que o processo referencie | `orgao_publico.parametros` |

### 1.4 Performance

| # | Gap | Evidência |
|---|---|---|
| P1 | Toda consulta de documento carrega o **arquivo binário** e o texto de todas as páginas, até para ler só o `tipo`, porque nenhuma usa `defer`/`load_only` | `bids/workspace.py:21`, `conformidade.py:83`, `grafo.py:32`, `procurement/workspace.py:22` |
| P2 | Sinais de risco consultam os documentos **por processo, dentro de um laço** (N+1 com blobs) | `procurement/riscos.py:71` |
| P3 | Análise documental **síncrona na requisição HTTP**: até 8 chamadas C3 em sequência | `api/v1/bids.py`, `api/v1/procurement.py` (`/analisar`) |
| P4 | Listas de licitações e de processos sem paginação | `bids/licitacoes.py`, `procurement/cadastros.py` |
| P5 | Métricas calculadas na hora, sem read model | TD-073 |

### 1.5 O que já está certo (preservar)

- *Grounding* compartilhado (`shared/grounding.py`, `shared/documentos.py`, `shared/texto.py`): a proveniência calculada pelo sistema (D-031) já é um engine.
- Barreira Buy/Sell estrutural e comportamental (D-034, `test_barreira_buy_sell.py`, `test_public_procurement.py`).
- Go/No-Go e matriz determinísticos (D-033). Risco como sinal para revisão, regime como parâmetro (D-036).
- Modelo canônico com `classification`, `origin`, `EvidenceRef` (Fase 2).
- Um único AI Gateway, orquestrador com ferramentas por lado (Fase 12) e créditos por workload (Fase 15).
- Salas de compra: comprador só vê o que o vendedor compartilha (D-037).

## 2. Arquitetura corrigida

### 2.1 Engines compartilhados → onde estão hoje → alvo

| Engine | Hoje | Alvo (contexto `sourcing` + Shared Kernel) |
|---|---|---|
| Identity & Tenant | `Tenant`, `Usuario`, `network/identidade` | sem mudança; emissor/comprador/fornecedor referenciam **Organization** (Shared Kernel) ou `empresa_rede` |
| CRM Core | `contexts/crm` | sem mudança; Enterprise Bids liga processo a `Conta`/`Negocio` como hoje (`licitacao.conta_id`) |
| Workflow Engine | tuplas de status (R1) | `sourcing/workflow.py`: definições declarativas em código (stages, transitions, roles, approvals, deadlines, required_documents, rules), versionadas no repositório. **Sem tabela** até existir edição por cliente |
| Document Engine | D1 + `shared/documentos` | `sourcing/documentos.py` + tabela única `documento_sourcing` (`document_type`, `source`, `classification`, `permissions`, `version`, provenance, `extraction_status`) |
| Requirement Engine | D2/D3 + `shared/grounding` | `sourcing/requisitos.py`: um extrator com **perfis de extração** por `document_type` (Edital, TR, ETP, RFP, RFI, RFQ, Vendor Questionnaire, Technical Specification); saída normalizada (§3.3) |
| Evaluation Engine | `bids/conformidade.py` (sell) | `sourcing/avaliacao.py`: a mesma regra de status (COMPLIANT/PARTIAL/NON/UNKNOWN/REQUIRES_REVIEW) com **direção** do contexto: sell = "atendemos?" (evidência = cofre + portfólio), buy = "a proposta atende?" (evidência = documentos da proposta) |
| Matching Engine | D7 | `shared/matching.py`: critério, peso, evidência, `UNKNOWN`, explicação; **estratégias** Customer/Supplier/Partner/Offer/Bid/RFP/Intent. Migração por toque (§6) |
| Supplier Engine | `fornecedor_compras` (buy público) | `sourcing/fornecedores.py`: fornecedor do comprador (público ou privado), OFFICIAL/INTERNAL/SELF_DECLARED como hoje; qualificação = requisitos + avaliação |
| Contract Engine | D4 | `sourcing/contratos.py` + `contrato_sourcing` com `side`; eventos (aditivo, entrega, fiscalização, renovação) comuns |
| Graph Engine | Business Graph relacional (D-024) + grafo derivado do workspace | sem mudança de estilo; o Procurement Graph lê `processo_sourcing` + filhos sob demanda (nunca o grafo inteiro) |
| Intelligence Engine / AI Gateway | `contexts/intelligence` | sem mudança; novas *capabilities*, não agentes (§8) |
| Notification / Audit Engine | notificações, `audit_log`, `evento_dominio` | sem mudança; eventos `Sourcing*` versionados |
| Integration Hub | `contexts/integrations` | adapters de fonte de oportunidade (PNCP hoje; portais privados depois) escrevem `processo_sourcing` com `source` |

### 2.2 Contextos (monólito modular, D-002)

```
app/contexts/
  shared/        Organization, Person, entitlements, documentos, grounding, texto, matching (novo), ferramentas
  sourcing/      NOVO núcleo compartilhado: processo, documentos, requisitos, avaliação, participantes,
                 eventos (tarefa/prazo/esclarecimento/aprovação), contratos, workflow, rulesets, repositório
  bids/          SELL: Go/No-Go, cofre, radar, inteligência competitiva, proposta — usa sourcing via repositório SELL
  procurement/   BUY público: PCA, demanda, pesquisa de preço, risco regulatório — usa sourcing via repositório BUY
  (sourcing buy enterprise = configuração de sourcing + ruleset; só vira contexto próprio se surgir regra
   que não caiba em ruleset — ex.: leilão reverso)
```

`bids` e `procurement` **continuam** como contextos: eles guardam o que é específico de cada lado.
O que é comum desce para `sourcing`. Microserviço não se justifica (§5 do prompt): mesma escala,
mesmo deploy e mesma equipe; a barreira é de dados, não de rede.

### 2.3 Barreira Buy/Sell (inegociável)

Unificar tabelas **não pode** abrir caminho entre os lados. A proteção passa de "tabelas diferentes"
para "acesso obrigatório por repositório com lado":

1. `processo_sourcing.side` é NOT NULL, com CHECK, **imutável** (UPDATE proibido por trigger/ORM event).
   Filhos herdam o lado pelo pai; nenhuma consulta de filho existe sem `JOIN` no pai.
2. Só `sourcing/repositorio.py` consulta as tabelas `*_sourcing`. Ele expõe `RepositorioVenda` e
   `RepositorioCompra`; cada um fixa `side` em toda consulta.
3. Fitness function (evolução de `test_barreira_buy_sell.py`):
   - nenhum módulo fora de `sourcing/` cita as tabelas;
   - `bids`, PREDATOR, CRM, MAP, Opportunity, Network e Intelligence só importam `RepositorioVenda`;
   - só `procurement` e a API do comprador importam `RepositorioCompra`.
4. Classificação por linha: BUY nasce CONFIDENTIAL (hoje já é); RESTRICTED nunca vai para a IA.
   O Context Engine filtra por `side` além do propósito.
5. Opcional em Postgres: *row-level security* por `side` na role usada pelos contextos de venda.
   Avaliar na fase de migração; a fitness function vem antes.
6. O teste comportamental atual (sem acesso, sem recuperação, sem vazamento, sem revelação por IA,
   mesmo tenant com os dois módulos) roda **igual** contra o schema novo antes de desligar o antigo.

Direção permitida continua: público → comprador (perfil público do fornecedor). Nunca comprador → vendedor.

## 3. Entidades reutilizáveis

### 3.1 SourcingProcess (entidade canônica e tabela `processo_sourcing`)

| Campo | Tipo/valores | De onde vem hoje |
|---|---|---|
| id, tenant_id | — | — |
| segment | PUBLIC · ENTERPRISE | implícito no módulo |
| side | BUY · SELL (imutável) | implícito na tabela |
| process_type | PUBLIC_TENDER · RFP · RFI · RFQ · EOI · DIRECT_AWARD · PRICE_REGISTRATION · FRAMEWORK_AGREEMENT · PRIVATE_TENDER · STRATEGIC_SOURCING_EVENT · VENDOR_QUALIFICATION | `licitacao.modalidade`, `processo_contratacao.modalidade` |
| issuer_ref | Organization/`empresa_rede`/`orgao_publico` (ref) + nome/CNPJ quando não identificado | `orgao_nome/orgao_cnpj`, `orgao_id` |
| buyer_ref | Organization do comprador (BUY: o próprio tenant) | `orgao_id` |
| seller_context | SELL: `conta_id`, `oferta_id`, responsável | `licitacao.conta_id/oferta_id` |
| title, description | — | `titulo`/`objeto`, `objeto` |
| status | estado do **workflow** (não enum global) | `status` |
| visibility | PRIVATE · INVITED · PUBLIC (projeção para fornecedores, futura) | — |
| ruleset, ruleset_version | ex.: `PUBLIC_PROCUREMENT_BR_14133@1` | `orgao.regime_juridico/parametros` |
| workflow, workflow_version | ex.: `PUBLIC_TENDER_SELL@1` | tuplas de status |
| publication_date, deadline | — | `data_publicacao/prazo_proposta`, `publicado_em/prazo_previsto` |
| estimated_value, currency, value_confidential | Money | `valor_estimado`, `valor_sigiloso` |
| owner | usuário responsável | `responsavel_usuario_id` |
| source | MANUAL · UPLOAD · PNCP · … + `external_id`, `url` | `fonte*` |
| metadata | JSON **validado pelo ruleset** (extensões regulatórias) | `unidade_id`, `item_pca_id`, `categoria`, `demanda_ids` |

Não há tabela por `process_type`. O que muda por tipo vive no workflow e no ruleset.
Extensões que precisam de integridade referencial continuam em tabelas do contexto dono
(ex.: `item_pca` em procurement, `decisao_go_no_go` em bids) apontando para `processo_sourcing.id`.

### 3.2 Filhos compartilhados

| Entidade | Tabela alvo | Unifica / substitui | Observação |
|---|---|---|---|
| Document | `documento_sourcing` | `documento_licitacao`, `documento_compras` | `document_type`, `classification`, `version`, `extraction_status`; conteúdo binário **fora** da linha quente (§7) |
| Requirement | `requisito_sourcing` | `requisito_licitacao`, `documento_compras.achados` | campos em §3.3 |
| Evaluation | `avaliacao_sourcing` | matriz calculada (hoje não persistida) | `direction` (SELF · PROPOSAL), alvo (requisito × participante), status, motivo, evidência, ajuste humano |
| Participant | `participante_sourcing` | `licitacao.concorrentes/parceiros` JSON | papel: ISSUER · BIDDER · INVITED_SUPPLIER · COMPETITOR · PARTNER |
| Proposal | `proposta_sourcing` | `licitacao.valor_proposta` | participante, valor, versão/rodada (negociação), documentos |
| Lot / Item | `lote_sourcing`, `item_sourcing` | canônico sem tabela | criar quando o primeiro fluxo precisar |
| Task / Deadline / Clarification / Approval | `evento_sourcing` (tipado) | `evento_processo`, prazos calculados | prazos de documento continuam **derivados** (não gravados) |
| Contract / Deliverable | `contrato_sourcing` + `evento_contrato_sourcing` | `contrato_venda_publica`, `contrato_compra`, `evento_contrato_compra` | `side` herdado |
| Supplier | `fornecedor_compras` (renomeada para `fornecedor`, só BUY) | — | o lado vendedor não tem "fornecedor": ele é o fornecedor |
| Evidence | `documento_cofre` (sell) + documentos de proposta (buy) | — | o cofre continua do vendedor; qualificação de fornecedor usa `requisito` + `avaliacao` |
| RiskSignal | calculado (não gravado) | `procurement/riscos.py`, fatores do Go/No-Go | uma estrutura comum de sinal (código, severidade, evidência, "requer revisão") |
| AuditEvent | `audit_log` + `evento_dominio` | — | sem mudança |

**Ficam específicos** (não unificar sem necessidade real):
- `plano_contratacao`, `item_pca`, `demanda_compra`, `pesquisa_preco`: regulatórios do setor público.
  `demanda_compra` é candidata a virar *requisition* do Enterprise quando esse fluxo existir; decidir então.
- `decisao_go_no_go`, `documento_cofre`: exclusivos do vendedor.
- `sala_compra`: continua o canal vendedor↔comprador (D-037); passa a referenciar `processo_sourcing` quando houver.

### 3.3 Saída normalizada do Requirement Engine

`Requirement { process_id, document_id, category, text, mandatory, evidence_required, source (AI|MANUAL|IMPORT),
page, clause, excerpt, confidence (grounded | manual), compliance_status, review_status (sugerido|confirmado|descartado),
reviewed_by, correlation_id }`

`confidence` **não** vem da IA: `grounded` = trecho literal ancorado pelo sistema (D-031); o resto é
`manual`. Categorias são o vocabulário do perfil de extração, não um enum global.

### 3.4 Workflows e rulesets (código, versionados)

| Workflow | Segmento/lado | Estados (resumo) |
|---|---|---|
| `PUBLIC_TENDER_SELL@1` | 2a | IDENTIFICADA → EM_ANALISE → GO/NO_GO → PROPOSTA_ENVIADA → GANHA/PERDIDA (hoje `STATUS_LICITACAO`) |
| `ENTERPRISE_RFP_SELL@1` | 2b | RECEBIDA → QUALIFICACAO → GO/NO_GO → RESPOSTA → SHORTLIST → NEGOCIACAO → GANHA/PERDIDA |
| `PUBLIC_PROCUREMENT_BUY@1` | 3 | PLANEJAMENTO → ETP → TR → PESQUISA_PRECOS → APROVACAO → PUBLICADO → SELECAO → HOMOLOGADO → CONTRATADO (hoje `STATUS_PROCESSO`) |
| `ENTERPRISE_RFP_BUY@1` | 4 | RASCUNHO → CONVITE → PERGUNTAS → PROPOSTAS → AVALIACAO → NEGOCIACAO → ADJUDICACAO → CONTRATO |

Cada definição declara `stages, transitions, roles, approvals, deadlines, required_documents, rules`.

| Ruleset | Conteúdo |
|---|---|
| `PUBLIC_PROCUREMENT_BR_14133` | documentos esperados por etapa (hoje `DOCUMENTOS_ESPERADOS`), sigilo do valor, limite de fragmentação por órgão (hoje `orgao.parametros`), linguagem de risco (D-036) |
| `ENTERPRISE_SOURCING` | nº mínimo de propostas, pesos de avaliação, aprovação por alçada de valor |
| `PRIVATE_RFP` (sell) | documentos do vendor questionnaire, prazos de pergunta/resposta |

Controllers e componentes perguntam ao ruleset; nenhum `if regime == ...` fora dele.

## 4. Componentes eliminados ou unificados

| Hoje | Depois |
|---|---|
| `bids/documentos.py` + `procurement/documentos.registrar` | `sourcing/documentos.py` |
| `bids/analise.py` + `procurement/documentos.analisar` | `sourcing/requisitos.py` (perfis: edital, TR, documento de compras, RFP…) |
| `requisito_licitacao` + `achados` JSON | `requisito_sourcing` |
| `bids/conformidade.py` (sell) + avaliação de proposta (não construída) | `sourcing/avaliacao.py` com direção |
| `bids/contratos.py` + `procurement/contratos.py` | `sourcing/contratos.py` |
| `bids/workspace.py` + `procurement/workspace.py` | `sourcing/workspace.py` com seções pedidas pela configuração |
| `LicitacaoWorkspace.tsx` + `ProcessoWorkspace.tsx` | `ProcessWorkspace` + painéis (§5.3) |
| 4 scores de aderência | `shared/matching.py` + estratégias (migração por toque) |
| `bids/ferramentas.py` + `procurement/ferramentas.py` (contratos vencendo nos dois) | ferramentas por *capability*, parametrizadas por lado |

## 5. Impactos

### 5.1 Schema

- **Novas tabelas**, criadas só na fase de migração: `processo_sourcing`, `documento_sourcing`,
  `requisito_sourcing`, `avaliacao_sourcing`, `participante_sourcing`, `proposta_sourcing`,
  `evento_sourcing`, `contrato_sourcing`, `evento_contrato_sourcing`. Lote/item quando houver uso.
- **Migram** e depois são removidas: `licitacao`, `documento_licitacao`, `requisito_licitacao`,
  `contrato_venda_publica`, `processo_contratacao`, `documento_compras`, `evento_processo`,
  `contrato_compra`, `evento_contrato_compra`.
- **Recebem FK nova**: `decisao_go_no_go`, `item_pca`, `pesquisa_preco`, `sala_compra`, `documento_cofre`
  (se ligado a processo).
- Documento: coluna `conteudo` sai para tabela `documento_sourcing_arquivo` (1:1) ou armazenamento de
  objetos. `paginas_texto` fica em coluna só lida pelo extrator (`deferred`).
- Índices: `(tenant_id, side, status)`, `(tenant_id, side, deadline)`, `(process_id)` em todos os filhos (D-047).
- Créditos (Fase 15): workloads e features de IA **não mudam de código** (histórico financeiro reproduzível);
  `execucao_ia.entidade_tipo` passa a `processo_sourcing`/`documento_sourcing`, com as linhas antigas preservadas.

### 5.2 APIs

Recursos canônicos, com o lado **derivado da rota e do módulo**, nunca do corpo:

```
/sourcing/{sell|buy}/processes                     GET (cursor) · POST
/sourcing/{sell|buy}/processes/{id}                GET · PATCH (transição validada pelo workflow)
/sourcing/{sell|buy}/processes/{id}/documents      GET · POST · /{doc}/estimate · /{doc}/analyze (assíncrono → 202)
/sourcing/{sell|buy}/processes/{id}/requirements   GET · POST · PATCH (revisão humana)
/sourcing/{sell|buy}/processes/{id}/evaluations    GET (sell: matriz · buy: por proposta) · PATCH (ajuste com justificativa)
/sourcing/{sell|buy}/processes/{id}/participants   GET · POST
/sourcing/{sell|buy}/processes/{id}/tasks          GET · POST
/sourcing/{sell|buy}/processes/{id}/contracts      GET · POST
```

- `sell` exige módulo `bids`; `buy` exige `procurement` (público) ou o módulo de sourcing Enterprise (OI-019).
- Especializadas ficam onde o comportamento é único: `/bids/go-no-go`, `/bids/cofre`, `/bids/concorrentes`,
  `/procurement/pca`, `/procurement/demandas`, `/procurement/precos`.
- `/api/v1/bids/*` e `/api/v1/procurement/*` (46 rotas) ficam como **fachada** sobre o núcleo durante a
  migração e são removidas depois que a UI trocar (Strangler).

### 5.3 UI

Componentes compartilhados em `frontend/src/components/sourcing/`: `ProcessWorkspace`, `RequirementMatrix`,
`DocumentPanel`, `Timeline`, `ParticipantsPanel`, `SupplierPanel`, `EvaluationPanel`, `RiskPanel`,
`TasksPanel`, `ContractPanel`, `AIInsightsPanel`. Uma **configuração por segmento** define rótulos
("Licitação" × "RFP" × "Processo de contratação" × "Evento de sourcing"), abas, ações e permissões.
As rotas continuam por segmento (`/bids`, `/compras`, `/sourcing`), cada uma em chunk próprio (lazy).
Nenhuma UI Enterprise é construída nesta correção.

### 5.4 Agentes e IA

- Nenhum agente novo. O **B2B ON Intelligence Agent → orquestrador → capabilities** continua (Fase 12).
- Capabilities (ferramentas registradas pelos contextos): Research, Extraction, Requirement Analysis,
  Matching, Evaluation, Recommendation, Risk Analysis, Document Intelligence, Meeting Intelligence,
  Revenue Intelligence, Procurement Intelligence.
- `tender_analyzer`, `tr_analyzer` e `procurement_intelligence_agent` viram **perfis** da capability
  Requirement Analysis. Agentes PLANEJADOS que só repetem uma capability não são construídos.
- Toda capability declara `side`; o orquestrador mantém "compra × venda? → ESCLARECER" (D-040).
- Contexto mínimo: intenção → permissão (lado, módulo, papel) → recuperação só do processo/documento em
  questão → blocos com âncora → modelo. Regras, SQL e scoring antes de IA (D-022, D-033).

### 5.5 Fases (roadmap)

As Fases 0–17 do Master Prompt v4 estão concluídas. A correção **não reabre** nenhuma. O trabalho
entra como fases novas, que dependem de autorização do PO (§7). `CURRENT PHASE` não muda.

## 6. Estimativa de duplicação evitada

**Método**: linhas atuais medidas em `staging` (contextos, APIs e telas de sourcing); cenário "fork"
supõe copiar o lado equivalente para cada segmento Enterprise, descontando o que é só regulatório público.
É estimativa de ordem de grandeza, não medição.

| Item | Linhas |
|---|---|
| Código de sourcing hoje: contextos `bids` 1.146 + `procurement` 1.011 + APIs 615 + telas 1.388 | **4.160** |
| Fork Enterprise Bids (cópia de bids + API + telas) | ≈ 2.300 |
| Fork Enterprise Sourcing (cópia de procurement sem PCA, pesquisa de preço e demanda) | ≈ 1.700 |
| Testes duplicados junto com os forks (bids + procurement hoje: 659) | ≈ 600 |
| **Total que um fork criaria** | **≈ 4.600** |
| Com engines: rulesets + workflows declarativos + configuração de UI | ≈ 350–500 |
| Capacidades realmente novas (convite, propostas, comparação, qualificação, negociação) | ≈ 900–1.300 (necessárias em qualquer cenário) |
| Duplicação **existente** removida pela unificação (D1–D6, backend e UI) | ≈ 350–500 |

Resultado: evita-se ≈ **4.000 linhas** de código paralelo e ≈ 600 de testes paralelos, e remove-se
≈ 400 já duplicadas. O custo é a migração de dados (§8) e a reescrita da fitness function da barreira.

## 7. Riscos

| Risco | Mitigação |
|---|---|
| **Vazamento Buy→Sell** ao juntar tabelas | §2.3: repositório por lado, `side` imutável, fitness function reescrita **antes** da migração, teste comportamental atual rodando contra o schema novo, RLS opcional |
| Abstração prematura (workflow engine genérico demais) | workflow declarativo em código, sem editor e sem tabela; criar o 2º workflow só quando o fluxo Enterprise for construído |
| Regressão em Bids/Procurement em produção | Strangler: tabelas novas + backfill + leitura dupla com comparação + fachada das rotas antigas + remoção só com paridade |
| Histórico de créditos e auditoria com ids antigos | mapa `id_antigo → id_novo` persistido; `audit_log`/`execucao_ia` antigos não são reescritos |
| Matching unificado mudar resultados (ICP, NBO) | migrar uma estratégia por vez, com teste de paridade de score |
| Módulo/entitlement do Enterprise indefinido | OI-019 (PO); nenhuma venda antes da definição (regra de preço) |
| Análise assíncrona mudar a UX | 202 + status no documento + notificação; estimativa/confirmação de créditos (Fase 15) antes de enfileirar |

## 8. Plano de migração (fases propostas, nenhuma autorizada)

| Fase | Entrega | Critério de saída |
|---|---|---|
| **S0 · Performance sem schema** | `defer` de `conteudo`/`paginas_texto` (P1); consulta única por tipo em `riscos` (P2); paginação por cursor nas listas (P4) | orçamento de consultas em teste (padrão Fase 17) |
| **S1 · Núcleo `sourcing` sobre as tabelas atuais** | `sourcing/requisitos.py` (extrator único com perfis), `sourcing/documentos.py`, `sourcing/avaliacao.py` (direção), `shared/matching.py` (base); `bids` e `procurement` passam a chamá-los | suíte atual verde sem mudar comportamento; zero mudança de schema |
| **S2 · Barreira nova primeiro** | `sourcing/repositorio.py` (Venda/Compra) e fitness function nova rodando junto com a antiga | as duas fitness passam |
| **S3 · Schema unificado (expand)** | tabelas `*_sourcing`, backfill idempotente, leitura dupla com comparação, `side` imutável | paridade 100% nos testes de bids/procurement e no teste crítico da barreira, em SQLite e Postgres |
| **S4 · Workflow + rulesets** | `PUBLIC_TENDER_SELL@1`, `PUBLIC_PROCUREMENT_BUY@1`, `PUBLIC_PROCUREMENT_BR_14133@1` substituem tuplas e `DOCUMENTOS_ESPERADOS` | transições atuais reproduzidas por teste |
| **S5 · UI compartilhada** | `ProcessWorkspace` + painéis; telas de Licitações e Compras trocam para ela | E2E sem regressão |
| **S6 · Contract (switch)** | rotas antigas viram fachada; análise assíncrona; remoção das tabelas antigas | uma release inteira sem leitura das tabelas antigas |
| **S7 · Enterprise Bids (sell)** | `ENTERPRISE_RFP_SELL@1` + `PRIVATE_RFP`, emissor Organization, vendor questionnaire | depende de OI-019 |
| **S8 · Enterprise Strategic Sourcing (buy)** | `ENTERPRISE_RFP_BUY@1` + `ENTERPRISE_SOURCING`, convite, propostas, avaliação, negociação | depende de OI-019 e de preço definido pelo PO |

S0–S2 não mudam schema nem comportamento e podem ir primeiro. S3–S6 são o Strangler. S7–S8 são produto novo.

### Execução

| Fase | Estado | Evidência |
|---|---|---|
| S0 | ✅ 2026-09-26 | colunas deferidas nos 3 modelos de documento; riscos com 1 consulta; cursor keyset + "Carregar mais"; `test_sourcing_desempenho.py` |
| S1 | ✅ 2026-09-26 | `contexts/sourcing/{requisitos,documentos,avaliacao,tipos}.py`, `shared/matching.py`; `bids` e `procurement` usam os engines; ICP (PREDATOR e rede) na estratégia única; `test_sourcing_nucleo.py`. Única mudança de resultado: o fit de ICP da rede passa a casar CNAE pontuado com dígitos (bug) |
| S2 | ✅ 2026-09-26 | protocolo `sourcing/repositorio.py`; `RepositorioVenda` (`bids`) e `RepositorioCompra` (`procurement`) com lado fixo; FinOps e Analytics leem venda só pelo repositório; fitness `test_barreira_sourcing.py` junto com `test_barreira_buy_sell.py`; `test_sourcing_repositorio.py` |
| S3–S8 | aguardando o PO (OI-020) | — |
