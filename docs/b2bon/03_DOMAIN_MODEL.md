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
