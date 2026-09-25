# ENTITY MAPPING — B2B ON CRM → Modelo Canônico (Fase 2)

Implementação: `app/contexts/integrations/adapters/b2bon_crm.py`
(`SYSTEM = "b2bon_crm"`). Ids canônicos: `b2bon_crm:<entidade>:<id interno>`.

## Organization ← `Conta`

| Canônico | Origem | Regra |
|---|---|---|
| id | `organization:{conta.id}` | |
| legal_name / trade_name | `nome` / `nome_fantasia` | |
| tax_id | `cnpj` | já normalizado (14 dígitos) |
| domain / industry / size / region | `dominio` / `segmento` / `porte` / `regiao` | |
| origin | `origem` | `receita*` → OFFICIAL; senão INTERNAL |
| created_at / updated_at | `criado_em` / `atualizado_em` | |

## Account ← `Conta`

| Canônico | Origem | Regra |
|---|---|---|
| id | `account:{conta.id}` | |
| organization_id | `organization:{conta.id}` | 1:1 no CRM interno |
| owner_user_id | `vendedor_usuario_id` | `user:{id}` |
| lifecycle | `cliente_cancelado_em` → CHURNED; `cliente_desde` → CUSTOMER; `status=descartada` → DISQUALIFIED; `priorizada` → QUALIFIED; sem ICP → LEAD; senão PROSPECT | ordem de precedência exatamente essa |
| fit_score | `score_aderencia` | |
| next_step / next_step_at | `proximo_passo` / `proximo_passo_em` | |

## Customer ← `Conta` com `cliente_desde`

`customer_since = cliente_desde`, `churned_at = cliente_cancelado_em`.

## Person / Contact ← `Decisor`

| Canônico | Origem |
|---|---|
| Person.full_name / job_title / email / phone / linkedin_url | `nome` / `cargo` / `email` / `telefone` / `linkedin_url` |
| Person.suppressed_at | `suprimido_em` (opt-out LGPD) |
| Person.origin | `origem` `receita*` (QSA) → OFFICIAL |
| Contact.account_id | `account:{conta_id}` |
| Contact.buying_role | `papel_confirmado` se for um `BuyingRole` válido; senão UNKNOWN |
| Contact.last_interaction_at | `ultima_interacao_em` |

`papel_sugerido` (regra por cargo) **não** é mapeado: é inferência e não
fato confirmado.

## Pipeline / PipelineStage / Opportunity ← funil, `EstagioFunil`, `Negocio`

| Canônico | Origem | Regra |
|---|---|---|
| Pipeline | 1 por tenant (`pipeline:{tenant_id}`) | o CRM interno tem funil único |
| PipelineStage.stage_type | `EstagioFunil.tipo` | aberto→OPEN, ganho→WON, perdido→LOST |
| Opportunity.status | tipo do estágio atual | |
| Opportunity.amount | `valor` | `Money(Decimal(str(valor)), "BRL")` |
| Opportunity.closed_at | `ganho_em` ou `perdido_em` | |
| Opportunity.primary_contact_id / offer_id / owner_user_id | `decisor_id` / `oferta_id` / `vendedor_usuario_id` | |

## Activity ← `Atividade`

`kind`: ligacao→CALL, email→EMAIL, reuniao→MEETING, nota→NOTE,
tarefa→TASK, sistema→STAGE_CHANGE, outros→OTHER. O valor original fica
em `source_type`.

## Interaction ← `InteracaoConta` (MAP)

`kind = tipo` (vocabulário do MAP preservado: contato, reclamacao,
feedback_positivo, …).

## CSMetric ← `PesquisaNps` respondida

`metric="NPS"`, `value=nota`, `scale_max=10`, `collected_at=respondida_em`.

## Offer ← `Oferta`

`differentiators=diferenciais`, `proof_points=provas_sociais`,
`price_min/max=faixa_preco_min/max`, `icps=[icp:{icp_id}]`. Os demais
campos de Offer Intelligence ficam vazios até a Fase 6.

## Ainda não mapeados (sem uso nesta fase)

Lead (o CRM interno trata lead como Account sem ICP), Meeting
(`Reuniao`), Message (`Mensagem`), Proposal (`PropostaNegocio`),
Contract, Revenue, Invoice, BusinessIntent (`Intent`), Product.
Entram quando algum consumidor precisar (Fases 6–8, 13).
