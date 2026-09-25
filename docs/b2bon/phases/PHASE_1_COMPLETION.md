# PHASE 1 — DOMAIN SEPARATION · Completion Report

- **Data**: 2026-09-25
- **Branch**: `staging`
- **Autorização**: PO, 2026-09-25 ("Siga para a Fase 1 […] fica previamente
  autorizado o commit e subir todas as fases seguintes").
- **Plano executado**: `phases/PHASE_1_PLAN.md`

## 1. O que foi feito

| Etapa do plano | Entrega |
|---|---|
| 1.0 Rede de segurança | `tests/integration/test_matriz_entitlements.py` (61 casos: 4 perfis de plano × 15 rotas + paridade de payload MAP×CRM); `tests/unit/test_fronteiras_contexto.py` (fitness function); `tests/markers.py::requer_ffmpeg` (TD-034); aviso nos 5 docs de raiz (TD-036) |
| 1.1 Shared Kernel | `app/contexts/shared/entitlements.py` (`Entitlements.has_module/has_any_module/has_feature`); `app/contexts/shared/organizations.py` (`OrganizationRef`, `PersonRef`, `listar_organizacoes`, `contato_principal`, `obter_conta`, `decisores_da_conta`, `normalizar_dominio`); `exigir_algum_modulo` em `app/api/deps.py` |
| 1.2 MAP | `app/contexts/map/{risk,saude,economics,data_source,contract}.py`; algoritmo de risco unificado (TD-003); economia movida do CRM (C2); `MapDataSource` + `CrmInternoMapDataSource`; rotas `/saude-contas/desempenho/*` e `/saude-contas/vendedores-com-contas` + frontend (`PainelDesempenho origem="map"`) (C1) |
| 1.3 PREDATOR | `app/contexts/predator/{prospeccao,contract}.py` (≈570 linhas extraídas de `conta_service`); router `app/api/v1/prospeccao_contas.py` sob `_exige_predator` com os mesmos paths (C3); gates `_exige_organizacao` (C4), `_exige_oferta` (C5), `_exige_nps` (C6) |
| 1.4 CRM | `app/contexts/crm/contract.py` (`funil`, `valor_ganho_por_conta`, `valor_pipeline_aberto`, `custo_aquisicao`), usado pela porta do MAP |
| 1.5 Remoção de acoplamento | ciclo `crm_service` ↔ `saude_conta_service` eliminado (TD-038); `saude_conta_service`, `metricas_service` e `motor_service` só falam com `map.contract` |
| Extra | CI habilitado em `staging` (D-009) |

## 2. Critérios de aceite (GATE)

| Critério | Resultado |
|---|---|
| Suite de backend verde | ✅ **1.530 passed**, 0 failed (baseline da Fase 0: 1.465; +61 matriz, +4 fitness) |
| Frontend lint + build | ✅ lint exit 0, 25 warnings (mesmo número da Fase 0); build OK |
| E2E Playwright | ✅ 4/4 |
| Matriz de entitlement | ✅ 61/61. **Contra o código da Fase 0 a mesma matriz falha 23 casos**, o que prova que os defeitos C1, C3–C6 existiam e foram corrigidos |
| MAP-only acessa o painel do MAP | ✅ (C1) |
| PREDATOR-only acessa gerar lista / enriquecer / franquia | ✅ na rota (C3). O uso real continua bloqueado pelos limites 0 (OI-001) |
| CRM-only cria conta pelo Kanban | ✅ (C4) |
| Fitness function passa | ✅ |
| Sem mudança de schema, preço ou plano | ✅ nenhuma migração nova; nenhum valor de plano tocado |

**CRM funcional ✓ · MAP funcional ✓ · PREDATOR funcional ✓ · regressão verde ✓.**

## 3. Mudanças de comportamento visíveis

1. Tenant só-MAP: o painel de desempenho do MAP passa a carregar
   (antes, erro "Não foi possível carregar os dados de desempenho").
2. Tenant só-PREDATOR: passa a alcançar geração de lista, enriquecimento,
   contas, leads, ofertas e NPS.
3. Tenant só-CRM: passa a criar conta pelo Kanban e a ver ofertas;
   **deixa de receber** as rotas de prospecção (gerar lista,
   enriquecer, mapear decisores, franquia). Os limites desses planos já
   eram 0, então não havia uso real (D-007).
4. Planos de suíte: nenhuma mudança (a matriz prova paridade de payload
   entre MAP e CRM).

## 4. Riscos e pendências

- **OI-001 (crítica) continua aberta**: limites 0 nos planos PREDATOR
  avulsos. Não corrigido por ser valor de plano; precisa de números do PO.
- **C7 adiado** para a Fase 6: `inteligencia_rede` e `agente_corporativo`
  seguem só PREDATOR.
- **TD-039**: shims em `conta_service`, `crm_service` e `metricas_service`.
  Remover quando não houver mais chamadores.
- **TD-040**: `decisores_da_conta` não filtra tenant (comportamento
  herdado, documentado).
- Ainda leem ORM de outro módulo, fora dos contextos:
  `sinal_oportunidade_service`, `reuniao_service`, `cadencia_service` (TD-005).

## 5. Próxima fase

**PHASE 2 — CANONICAL BUSINESS MODEL** (autorizada previamente pelo PO).
