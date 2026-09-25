# DOMAIN DEPENDENCY MAP — Fase 0 (2026-09-25), status atualizado na Fase 1

Como CRM, MAP, PREDATOR e Shoal dependem uns dos outros **hoje**.
Extraído dos imports (`from app.services…`, `from app.models…`) de
`app/services/*.py`, das chamadas HTTP do frontend e dos gates em
`app/api/v1/router.py`.

## 1. Conclusão principal

A separação comercial por módulo (planos avulsos MAP/PREDATOR/CRM,
migração `807d7076f1df`, 2026-09-24) **não corresponde a uma separação
arquitetural**. O gate é por *router*, mas:

1. serviços de módulos diferentes leem e escrevem os mesmos modelos ORM
   (`Conta`, `Decisor`, `Negocio`, `EstagioFunil`, `Atividade`);
2. serviços chamam serviços de outros módulos diretamente;
3. o frontend de um módulo chama rotas protegidas pelo gate de outro;
4. routers misturam funcionalidades de módulos diferentes sob um único gate.

Consequência prática: **tenants com plano avulso recebem 403 em partes
do módulo que compraram** (ver §4).

## 2. Grafo de dependências (serviço → serviço)

```
                  ┌──────────────── tenant_service ◄──────────────┐
                  │                                                │
 saude_conta_service (MAP) ──► crm_service (CRM) ──► metricas_service (MAP)
          │                                                        ▲
          └──────────────► metricas_service ───────────────────────┘
 motor_service (MAP interno) ──► rede_social_service (Shoal)

 conta_service (CRM+PREDATOR) ──► enriquecimento_fila_service (PREDATOR)
                              ──► registro_oportunidade_service (PREDATOR)
                              ──► tenant_service
 sinal_oportunidade_service (PREDATOR) ──► conta_service
                                        ──► modelos Shoal (perfil_empresa, conexao_empresa,
                                            relacionamento_empresarial, intent, sala_corporativa,
                                            mensagem_sala, mensagem_rede_social, canal_sala)
 reuniao_service (PREDATOR) ──► atividade_service (CRM)
 intent_service (Shoal) ──► rede_social_service (Shoal)
```

(`errors`, `llm_helpers`, `auditoria_service` omitidos — transversais.)

## 3. Modelos compartilhados (candidatos a Shared Kernel)

| Modelo | Escrito por | Lido por |
|---|---|---|
| `Conta` | CRM (`crm_service`, `conta_service.criar_manual/atualizar`), PREDATOR (`conta_service.gerar_lista/enriquecer`, `lead`), Shoal (`criar_a_partir_de_convite_rede_social`) | MAP, PREDATOR, CRM, Shoal (`sinal_oportunidade_service`) |
| `Decisor` | CRM (`decisores`), PREDATOR (`mapear_decisores`, Receita QSA, Lusha) | cadências, envio, aprovação, qualificação, MAP |
| `Negocio`, `EstagioFunil` | CRM | MAP (`saude_conta_service`, `metricas_service`), PREDATOR (`sinal_oportunidade_service`, `registro_oportunidade`), Shoal (`sala_compra`) |
| `Atividade` | CRM, PREDATOR (`reuniao_service`, `meeting_bot_service`) | CRM, PREDATOR |
| `Oferta` | PREDATOR (router `ofertas`) | CRM (`crm_service`, `Negocio.oferta_id`), `icp_service`, `cadencia_service` |
| `PesquisaNps` | PREDATOR (router `nps`) | MAP (`metricas_service.calcular_cs_score`), CRM (`conta_service`) |
| `Usuario`, `Tenant`, `Licenca`, `Plano` | núcleo | todos |

`Conta`/`Decisor` são, semanticamente, **Organization/Person** do
modelo canônico — o shared kernel natural. `Negocio` é **Opportunity**,
propriedade do CRM.

## 4. Acoplamentos que quebram a contratação avulsa (confirmados)

| # | Acoplamento | Evidência | Efeito |
|---|---|---|---|
| C1 | Tela MAP (`MapContas.tsx` via `components/dashboard/PainelDesempenho.tsx`) chama `/crm/dashboard/funil`, `/crm/dashboard/economia`, `/crm/vendedores-com-contas` | grep em `frontend/src/pages/map/`, `components/dashboard/`; routers `crm` sob `_exige_crm` | Tenant só-MAP recebe 403 no painel de desempenho do MAP |
| C2 | LTV/CAC/ROI (métricas do MAP) calculados em `crm_service.dashboard_economia`; `saude_conta_service` importa `crm_service` | `saude_conta_service.py:255` | MAP depende de código do CRM |
| C3 | Geração de lista por ICP (Receita Federal), enriquecimento de site/BrasilAPI, mapeamento de decisores ficam no router `contas` sob `_exige_crm` | `app/api/v1/contas.py:83,151,278-305` | Tenant só-PREDATOR **não gera lista nem enriquece**; tenant só-CRM ganha rotas de prospecção |
| C4 | Criação de conta/lead fica em `leads` (`_exige_predator`); tela e testes do CRM criam conta por `/leads/contas` | `frontend/src/pages/crm/Kanban.tsx:370` faz `POST /leads/contas` | Tenant só-CRM não cria conta pelo caminho usado hoje |
| C5 | `ofertas` sob `_exige_predator`, mas `Negocio.oferta_id` é do CRM | `router.py`, `crm_service` | Tenant só-CRM não gerencia ofertas que o CRM referencia |
| C6 | `nps` sob `_exige_predator`, mas NPS alimenta CS Score (MAP) | `metricas_service.calcular_cs_score` | Tenant só-MAP não registra NPS |
| C7 | `inteligencia_rede` (riscos de pipeline = dado de CRM) e `agente_corporativo` sob `_exige_predator` | `router.py` | Recursos de CRM/Intelligence presos ao PREDATOR |

### Status após a Fase 1

| # | Status | Como |
|---|---|---|
| C1 | ✅ resolvido | Rotas `/saude-contas/desempenho/{funil,economia}` e `/saude-contas/vendedores-com-contas` (MAP); `PainelDesempenho` recebe `origem="map"` |
| C2 | ✅ resolvido | LTV/CAC/ROI/CS em `app/contexts/map/economics.py`; `saude_conta_service` e `metricas_service` usam só `map.contract`; o CRM consome o MAP pelo contrato |
| C3 | ✅ resolvido | Rotas de prospecção em `app/api/v1/prospeccao_contas.py` sob `_exige_predator` (mesmos paths) |
| C4 | ✅ resolvido | `leads`, `contas`, `decisores` sob `_exige_organizacao` (CRM **ou** PREDATOR) |
| C5 | ✅ resolvido | `ofertas` sob CRM ou PREDATOR |
| C6 | ✅ resolvido | `nps` sob MAP ou PREDATOR |
| C7 | ✅ Fase 6 (D-023) | riscos de pipeline e sugestões de expansão com gate CRM-ou-PREDATOR; atribuição da rede e Agente Corporativo seguem PREDATOR até a Fase 7 |

Evidência: `tests/integration/test_matriz_entitlements.py`. Contra o
código da Fase 0 a matriz falha 23 casos; na Fase 1 passam os 61.

Separadamente, os limites dos planos avulsos PREDATOR são todos 0
(ver `PRICING_CURRENT_STATE.md` §4). Isso é um defeito de dados, não de
acoplamento.

## 5. Acoplamentos de código (não visíveis ao usuário)

- `conta_service.py` (1.683 linhas, 53 funções) mistura CRM (CRUD de
  conta, próximo passo, exclusão, PDF), PREDATOR (geração de lista,
  enriquecimento, mapeamento de decisores, limpeza de leads) e
  Intelligence (`sugerir_estrategia_venda`, `sugerir_papel_comite_compra`).
  É o maior ponto de acoplamento do sistema.
- `crm_service.py` (1.022 linhas) mistura funil (CRM), economia/LTV/CAC
  (MAP), `gerar_meeting_brief` (Intelligence) e `dashboard_flywheel`.
- ~~`motor_service.calcular_score_risco` e
  `saude_conta_service.calcular_score_risco_da_conta` são o mesmo
  algoritmo duplicado~~ → unificado em `app/contexts/map/risk.py` (Fase 1).
- `sinal_oportunidade_service` (PREDATOR) lê diretamente 8 modelos do
  Shoal. É o embrião de Opportunity Intelligence, mas sem contrato.

## 6. Portas (ABC) que já existem e servem de padrão

`PlanLimitsProvider`, `CrmProvider` (porta PREDATOR → CRM interno),
`RedeSocialProvider`, `AccountDataProvider`, `LLMProvider`,
`PaymentProvider`, `EmailProvider`, `WhatsAppProvider`,
`CalendarProvider`, `MeetingBotProvider`, `ContactEnrichmentProvider`,
`WebSearchProvider`, `EmailVerificationProvider`.

`CrmProvider` e `RedeSocialProvider` já são contratos entre módulos.
O próprio docstring diz: *"dado que pertence ao núcleo, não ao
PREDATOR"*. A Fase 1 deve generalizar esse padrão.
