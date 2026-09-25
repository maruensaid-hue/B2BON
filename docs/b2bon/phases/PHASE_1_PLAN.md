# PHASE 1 — DOMAIN SEPARATION · Plano detalhado

> **Status: PROPOSTO. Não iniciado.** Requer autorização explícita do
> Product Owner (§1, §89).

## Objetivo

Separar CRM, MAP e PREDATOR em bounded contexts **dentro do monólito**
(D-002), com contratos explícitos, usando Strangler Pattern. O
comportamento deve ser preservado para planos de suíte. Os acoplamentos
que quebram planos avulsos (C1–C7) devem ser corrigidos.

## Fora de escopo

Modelo canônico completo (Fase 2), namespaces `/api/v1/map|predator`
(Fase 3), qualquer mudança em IA (Fase 4), preços e planos (OI-001 é
hotfix separado, D-006), microserviços.

## Estrutura alvo (incremental)

```
app/contexts/
  shared/        # Shared Kernel
    tenancy.py         TenantContext (tenant_id, usuario, escopo hierárquico)
    entitlements.py    Entitlements.has_module/has_feature (fachada sobre PlanLimitsProvider)
    organizations.py   OrganizationReader/Writer (contrato sobre Conta) + DTOs
    people.py          PersonReader/Writer (contrato sobre Decisor) + DTOs
  crm/
    contract.py        CrmOpportunities (lê/escreve Negocio/Funil/Atividade)
    ...                fachadas que delegam aos serviços atuais
  map/
    contract.py        MapService (health, ranking, economics) + MapDataSource (porta de entrada)
    risk.py            algoritmo único de risco (puro, parametrizado)
    economics.py       LTV/CAC/ROI/CS (movidos de crm_service/metricas_service)
    sources/crm_interno.py   MapDataSource sobre o CRM interno
  predator/
    contract.py        Prospecting (gerar lista, enriquecer, mapear decisores)
    prospeccao_service.py    extraído de conta_service
```

Os serviços atuais (`app/services/*`) continuam existindo. Cada função
movida deixa um *shim* que delega ao novo local. Os shims são removidos
só depois que a regressão passa e nenhum chamador sobra (último passo
do Strangler).

## Etapas

### 1.0 Rede de segurança (antes de qualquer movimento)
1. **Matriz de entitlement por plano (testes de caracterização)**:
   para cada plano (suíte, MAP-only, PREDATOR-only, CRM-only, sem
   licença) × cada rota relevante, registrar o status HTTP esperado.
   Primeiro registrar o comportamento **atual**, incluindo os 403
   indevidos, marcados como `xfail` com referência a C1–C7. Depois
   inverter conforme cada acoplamento for corrigido.
2. **Fitness function de imports**: um teste que percorre `app/contexts/**`
   e falha se um contexto importar internals de outro (só `contract.py`
   e `shared/` são permitidos). Começa valendo só para `app/contexts/`.
3. TD-034: marcar os testes de mídia com `skipif(shutil.which("ffprobe") is None)`.
   O CI mantém o ffmpeg e continua rodando esses testes.
4. TD-036: aviso no topo dos docs de raiz apontando para `docs/b2bon/`.

### 1.1 Shared Kernel
- `Entitlements` (fachada fina sobre `PlanLimitsProvider`), mais uma
  dependency `exigir_algum_modulo(*modulos)` para rotas legitimamente
  compartilhadas.
- `OrganizationReader/Writer` e `PersonReader/Writer` com DTOs Pydantic
  e implementação sobre `Conta`/`Decisor`. Nenhuma mudança de schema.

### 1.2 MAP
1. Extrair o algoritmo de risco para `map/risk.py` (função pura
   `score_risco(sinais, ultimo_contato, agora, limiares)`).
   `motor_service` e `saude_conta_service` passam a chamá-la (TD-003).
   Os testes existentes do score precisam continuar passando sem alteração.
2. Mover `dashboard_economia` (LTV/CAC/churn), `calcular_roi` e
   `calcular_cs_score` para `map/economics.py`.
   `crm_service.dashboard_economia` vira shim (TD-002, C2).
3. Criar a porta `MapDataSource` (contas, interações, receita, NPS) e
   a implementação `crm_interno`. O MAP deixa de importar `crm_service`
   e os modelos do CRM diretamente. É a fundação para o MAP API e para
   CRM externo.
4. **C1**: expor o painel de desempenho por rotas do MAP (`/saude-contas/desempenho/*`,
   com os mesmos payloads) e apontar `MapContas.tsx` para elas. O
   Dashboard do CRM continua usando `/crm/dashboard/*`.

### 1.3 PREDATOR
1. Extrair de `conta_service` para `predator/prospeccao_service.py`:
   `gerar_lista`, `_score_aderencia`, `enriquecer*`,
   `enfileirar_enriquecimento_em_lote`, `mapear_decisores`,
   limpeza de leads. `conta_service` mantém shims (TD-001).
2. **C3**: mover as rotas de prospecção de `contas.py` para um novo
   router PREDATOR **com os mesmos paths** (sem mudança no frontend),
   sob `_exige_predator`.
3. **C4/C5/C6/C7**: aplicar `exigir_algum_modulo(...)` onde a operação
   é do shared kernel ou legitimamente compartilhada (criação de
   conta/decisor, ofertas, NPS, riscos de pipeline). A lista final
   depende de OI-004.
4. PREDATOR escreve Organization/Person **só** via contrato do Shared Kernel.

### 1.4 CRM
- `crm/contract.py` com `CrmOpportunities` (Negocio/Funil/Atividade).
  `CrmProvider` (porta existente) passa a delegar a ele. `reuniao_service`
  e `sinal_oportunidade_service` passam a usar o contrato em vez do ORM
  de `Negocio`.

### 1.5 Remoção de acoplamento legado
- Remover os shims sem chamadores. Ampliar a fitness function para
  `app/services/` de MAP e PREDATOR, com allowlist que só pode encolher.

## Critérios de aceite (GATE)

1. A suite completa de backend passa (baseline da Fase 0: 1.465 testes, 0 falhas reais).
2. `npm run lint` e `npm run build` passam. E2E Playwright passa.
3. A matriz de entitlement mostra:
   - suíte: nenhum 403 novo em relação à baseline;
   - MAP-only: o painel do MAP funciona (C1 resolvido);
   - PREDATOR-only: gerar lista, enriquecer e mapear decisores acessíveis
     (C3). Os **limites** continuam dependendo de OI-001;
   - CRM-only: criar conta pelo Kanban (C4).
4. A fitness function de imports passa para `app/contexts/**`.
5. Nenhuma alteração de schema de banco, preço ou plano.
6. Documentação atualizada (`02_TARGET_ARCHITECTURE.md`, `03_DOMAIN_MODEL.md`, estado, decisões, dívida).

## Riscos

| Risco | Mitigação |
|---|---|
| Tenants só-CRM **perdem** as rotas de prospecção que hoje recebem por engano (C3) | É mudança de comportamento visível. Precisa de confirmação do PO (OI-004) antes da etapa 1.3.2 |
| Regressão sutil ao mover cálculo de LTV/CAC | Testes existentes de `dashboard_economia`, mais testes de caracterização com valores fixos antes de mover |
| Import circular ao introduzir `app/contexts` | Contratos só com DTOs Pydantic. Implementações importam modelos, contratos nunca |
| Escopo cresce | Cada etapa é um commit independente e reversível. Parar se a regressão ficar vermelha |

## Estimativa de sequência de commits

1.0 (rede) → 1.1 → 1.2.1 → 1.2.2 → 1.2.3 → 1.2.4 → 1.3.1 → 1.3.2 → 1.3.3 → 1.4 → 1.5 → docs.
