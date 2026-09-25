# MAP — CURRENT STATE (Fase 0, 2026-09-25)

MAP = "Motor de Alta Performance". Hoje ele existe em **duas variantes
com o mesmo nome**, e parte das métricas vive no código do CRM.

## 1. Duas variantes

| | MAP de contas (produto vendido) | "Motor" (ferramenta interna CyberFort) |
|---|---|---|
| Router | `/saude-contas` (`saude_conta.py`), gate `_exige_map` | `/motor` (`motor.py`), gate `_exige_licenca` + papel `super_admin` |
| Serviço | `saude_conta_service.py` | `motor_service.py` |
| Sujeito | `Conta` de um tenant (cliente/prospect do tenant) | `Tenant` assinante da B2B ON (churn da própria plataforma) |
| Sinais | `InteracaoConta` (registradas manualmente) | `InteracaoTenant` (registradas manualmente) |
| Escopo | usuário vê o próprio tenant; admin a subárvore | cross-tenant (super_admin) |
| Frontend | `pages/map/MapContas.tsx` | `pages/map/MapTenants.tsx` |

## 2. Capacidades existentes vs Master Prompt §7

| Capacidade (§7) | Estado | Onde | Observação |
|---|---|---|---|
| Churn risk score | ✅ determinístico | `calcular_score_risco_da_conta` / `motor_service.calcular_score_risco` | Soma de pontos: dias sem contato (+10/20/30), reclamações (+15 cada, máx 45), concorrente (+20), reunião remarcada (+15), feedback positivo (−20). Base 10, faixa 0–100. Limiares de classificação configuráveis. **O algoritmo está duplicado** nos dois serviços. |
| "Análise preditiva" | ⚠️ não existe como ML/IA | — | O "predict" é a regra acima. Nenhum modelo estatístico e nenhuma IA calcula risco. |
| Identificação de sinais | ✅ manual | `InteracaoConta.tipo` | Sinais vêm de registro humano, não de ingestão automática (e-mail, reunião, uso). |
| Causas prováveis | ⚠️ parcial | `sinais` no retorno do score | Mostra quais regras somaram pontos; não é análise causal. |
| Recomendações / remediação | ✅ só texto por IA | `saude_conta_service.gerar_script_resgate`, `motor_service.gerar_script_resgate` | 1 chamada LLM gera uma mensagem para o humano copiar. Nunca é enviada. **Não é medida** (`llm_helpers.gerar`, sem `RegistroUsoIa`). Não existe entidade `Remediation` com estado ou acompanhamento. |
| Ranking de saúde / dashboard | ✅ | `ranking_saude_contas`, `dashboard_saude_contas` | Inclui valor de pipeline aberto por conta (lê `Negocio`). |
| CS Score | ✅ | `metricas_service.calcular_cs_score` | NPS médio (`PesquisaNps`, do PREDATOR) combinado com o inverso do risco. Retorna `None` sem dados. |
| LTV / CAC / churn rate | ✅, **mas no CRM** | `crm_service.dashboard_economia` | CAC vem de `CustoAquisicao` (manual, por tenant/mês). CAC/ROI ficam `None` por vendedor, para não fabricar número. |
| ROI | ✅ | `metricas_service.calcular_roi` (LTV/CAC) | Chamado via `crm_service`. |
| Padrões observados | ✅ | `metricas_service.calcular_padroes_observados` | Correlação com amostra mínima explícita, nunca causal. |
| Alerta de detrator (NPS) | ✅ | `nps_service._gerar_alerta_detrator` → `AlertaDetrator` | Está no PREDATOR (router `nps`), mas é sinal de retenção. |
| Atribuição de vendedor | ✅ | `saude_conta_service.atribuir_vendedor` | |
| Painel por vendedor | ✅ (commit `47c6532`) | `components/dashboard/PainelDesempenho.tsx` | Chama rotas `/crm/*`. Ver acoplamento C1. |

## 3. Acoplamentos (detalhe em `DOMAIN_DEPENDENCY_MAP.md`)

- **C1**: o frontend do MAP chama `/crm/dashboard/funil`,
  `/crm/dashboard/economia` e `/crm/vendedores-com-contas`, todas sob
  `_exige_crm`. Um tenant só-MAP recebe 403.
- **C2**: `saude_conta_service` importa `crm_service` (ROI) e lê
  `Negocio`/`EstagioFunil` direto.
- **C6**: a entrada de NPS está no gate do PREDATOR, mas alimenta o CS
  Score do MAP.
- O MAP só funciona sobre `Conta` do CRM interno. **Não existe
  contrato de entrada** que permita a um CRM externo alimentar o MAP.

## 4. O que falta para o MAP virar bounded context consumível por API (§7, §65)

1. Contrato de entrada canônico (Account + Interactions + Revenue + NPS)
   independente do ORM do CRM.
2. Mover LTV/CAC/ROI/CS para dentro do contexto MAP. O CRM passa a
   consumir essas métricas via interface.
3. Unificar o algoritmo de risco (tenant e conta), parametrizado pelo
   tipo de sujeito.
4. Endpoints `/api/v1/map/*` (Fase 3) sobre essa interface.
5. Medir a IA de remediação (Fases 4/5).
