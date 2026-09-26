# 03 — DOMAIN MODEL (por bounded context)

> Escrito na Fase 1. O modelo canônico, independente de fornecedor, é o
> `04_CANONICAL_MODEL.md` (Fase 2). Este documento descreve **quem é dono
> de quê** no sistema atual.

## Shared Kernel (`app/contexts/shared/`)

| Conceito | Modelo | Contrato | Observação |
|---|---|---|---|
| Organization | `Conta` | `organizations.OrganizationRef`, `listar_organizacoes`, `obter_conta`, `normalizar_dominio` | Escrita por CRM (cadastro manual), PREDATOR (geração de lista, lead, enriquecimento) e Shoal (convite) |
| Person | `Decisor` | `organizations.PersonRef`, `contato_principal`, `decisores_da_conta` | Escrita por CRM e PREDATOR |
| Entitlement | `Plano`/`Licenca` via `PlanLimitsProvider` | `entitlements.Entitlements` (`has_module`, `has_any_module`, `has_feature`) | Fonte de dados continua sendo o plano (Fase 14 revisa o catálogo) |
| Tenant / Usuário | `Tenant`, `Usuario` | (ainda não há contrato; todos usam o ORM) | — |

Rotas do Shared Kernel aceitam o plano com CRM **ou** PREDATOR
(`_exige_organizacao`, D-007): `contas`, `decisores`, `leads`.

## CRM (`app/contexts/crm/`)

Dono de: `Negocio`, `EstagioFunil`, `Atividade`, `PropostaNegocio`,
`TemplateProposta`, `CustoAquisicao`, `DescarteConta`.
Contrato: `crm.contract.funil`, `valor_ganho_por_conta`,
`valor_pipeline_aberto`, `custo_aquisicao`.

## MAP (`app/contexts/map/`)

Dono de: `InteracaoConta`, `InteracaoTenant` (motor interno),
`AlertaDetrator` (gerado a partir do NPS), algoritmo de risco,
economia de cliente (LTV/CAC/churn/ROI/CS).
Contrato: `map.contract.score_risco_conta`, `economia`, `funil`,
`vendedores_com_contas`, `cs_score`, `valor_pipeline_aberto`,
`calcular_score`, `classificar`, `listar_interacoes`.
Porta de entrada: `map.data_source.MapDataSource` (implementação:
`CrmInternoMapDataSource`).

## PREDATOR (`app/contexts/predator/`)

Dono de: `ICP`, `ListaProspeccao`, `FilaEnriquecimentoConta`,
`CampoEnriquecido`, `Cadencia`, `ToqueCadencia`, `Mensagem`,
`Aprovacao`, `Campanha`, qualificação, reuniões, regras aprendidas,
sinais de oportunidade.
Contrato (Fase 1): `predator.contract.gerar_lista`, `enriquecer`,
`enriquecer_via_brasilapi`, `enfileirar_enriquecimento_em_lote`,
`mapear_decisores`, `score_aderencia`.
Ainda em `app/services/`: cadência, aprovação, envio, qualificação
(migram quando forem tocados pelas Fases 3/4).

## Compartilhados por regra de negócio (não por kernel)

| Conceito | Dono | Consumidores | Gate |
|---|---|---|---|
| `Oferta` | PREDATOR (cadastro) | CRM (`Negocio.oferta_id`), Intelligence | CRM ou PREDATOR (C5) |
| `PesquisaNps` | PREDATOR (envio) | MAP (CS Score) | MAP ou PREDATOR (C6) |

## Shoal (Business Network)

Ainda sem contexto próprio. Entra em `app/contexts/network/` na Fase 7.

## Strategic Sourcing & Bids (correção 2026-09-26, D-055)

| Contexto | Dono de (alvo) | Hoje |
|---|---|---|
| `sourcing` (núcleo) | `SourcingProcess` e filhos: Document, Requirement, Evaluation, Participant, Proposal, Lot/Item, Task/Deadline/Clarification/Approval, Contract/Deliverable | não existe; os mesmos conceitos estão duplicados em `bids` e `procurement` |
| `bids` (SELL) | Go/No-Go, cofre de documentos, radar/fontes, inteligência competitiva, proposta | `licitacao`, `documento_licitacao`, `requisito_licitacao`, `contrato_venda_publica`, `decisao_go_no_go`, `documento_cofre` |
| `procurement` (BUY público) | PCA, demanda, pesquisa de preço, sinais de risco regulatório, fornecedor do comprador | `orgao_publico`, `unidade_compras`, `plano_contratacao`, `item_pca`, `demanda_compra`, `processo_contratacao`, `documento_compras`, `contrato_compra`, `fornecedor_compras`, `pesquisa_preco` |
| Enterprise Sourcing (BUY privado) | configuração de `sourcing` + ruleset `ENTERPRISE_SOURCING` | não existe |

Mapa campo a campo e o que migra: `18_STRATEGIC_SOURCING.md` §3 e §5.1.
