# TECHNICAL DEBT

Registro vivo. Cada item: ID, descrição, evidência, impacto, fase sugerida.
Status: `OPEN | IN_PROGRESS | PAID`.

## Arquitetura / domínio

| ID | Dívida | Evidência | Impacto | Fase | Status |
|---|---|---|---|---|---|
| TD-001 | `conta_service.py` (1.683 linhas, 53 funções) mistura CRM, PREDATOR e Intelligence | `DOMAIN_DEPENDENCY_MAP.md` §5 | Impede separar os contextos | 1 | IN_PROGRESS: prospecção (≈570 linhas) foi para `contexts/predator/prospeccao.py`; helpers de Organization para o Shared Kernel. Restam CRUD de conta/lead (Shared Kernel de escrita) e `sugerir_estrategia_venda` (Intelligence, Fase 6) |
| TD-002 | `crm_service.py` (1.022 linhas) contém LTV/CAC/ROI (MAP) e meeting brief (Intelligence) | idem | MAP depende do CRM | 1 | IN_PROGRESS: economia e vendedores-com-contas movidos para o MAP (shims no CRM). Meeting brief fica para a Fase 6 |
| TD-003 | Algoritmo de risco de churn duplicado (`motor_service` e `saude_conta_service`) | `MAP_CURRENT_STATE.md` §2 | Divergência silenciosa | 1 | PAID (Fase 1: `contexts/map/risk.py`) |
| TD-004 | Gates de módulo aplicados por router inteiro, com routers que misturam módulos | `router.py`, `contas.py` | 403 ou concessão indevida (C1–C7) | 1 | PAID para C1–C6 (Fase 1) e C7 (Fase 6, D-023); Agente Corporativo e atribuição da rede aguardam o módulo da Business Network (Fase 7) |
| TD-005 | Sem camada de contrato entre módulos. Serviços acessam ORM de outros módulos | `DOMAIN_DEPENDENCY_MAP.md` §2–3 | Acoplamento; dificulta API-first | 1–3 | IN_PROGRESS: contratos CRM/MAP/PREDATOR + fitness function. Ainda leem ORM de outro módulo: `sinal_oportunidade_service` (Negocio, Shoal), `reuniao_service` (Atividade), `cadencia_service` (Conta/Decisor) |
| TD-006 | Modelos com nomes de domínio em PT e sem mapeamento canônico (`Conta`, `Decisor`, `Negocio`) | — | Integração com CRMs externos | 2 | OPEN |
| TD-007 | `CrmProvider` é porta para o CRM **interno**, com nome que sugere conector externo | `app/providers/crm/` | Confusão na Fase 13 | 2/3 | OPEN |

## Comercial / billing

| ID | Dívida | Evidência | Impacto | Fase | Status |
|---|---|---|---|---|---|
| TD-010 | Preço em 3 lugares (DB, `Planos.tsx`, `bootstrap_tenant.py`) | `PRICING_CURRENT_STATE.md` §1 | Cobrança diferente do anunciado | 14 | OPEN |
| TD-011 | `preco_mensal` é `NOT NULL Float`, sem `price_status` nem moeda. Float para dinheiro | `app/models/plano.py` | Não representa "preço a definir" (§71); arredondamento | 14 | OPEN |
| TD-012 | Entitlements como colunas booleanas em `Plano` (1 migração por flag nova) | `plano.py`, `PlanLimitsProvider` | Não escala para feature/add-on/crédito | 14 (fundação na 1/5) | OPEN |
| TD-013 | 1 licença por tenant, sem add-ons | `licenca.py` (unique `tenant_id`) | Não suporta "base + módulos + créditos" (§73) | 14 | OPEN |

## IA

| ID | Dívida | Evidência | Impacto | Fase | Status |
|---|---|---|---|---|---|
| TD-020 | 11 de 14 call sites de IA não medidos | `AI_CURRENT_STATE.md` §2 | FinOps impossível; gate §82 falha | 4/5 | PAID (Fase 4: 14/14 pelo gateway + fitness function) |
| TD-021 | Ledger `registro_uso_ia` best-effort, com campos insuficientes | idem §3 | Perda silenciosa de uso | 5 | PAID (Fases 4–5): ledger + custo + débito atômicos em sessão própria; falha de gravação vira log `LEDGER_IA_FALHOU` (alerta a configurar no Sentry, TD-049) |
| TD-022 | `LLMRequest` sem contexto (tenant, módulo, feature, classe de modelo) | `app/llm/schemas.py` | Não há roteamento nem atribuição | 4 | PAID (Fase 4: `ContextoIA` + roteador) |
| TD-023 | Sem delimitação de dado externo nos prompts | idem §6 | Prompt injection | 4 | PAID (Fase 4: `prompt_seguro` + instrução automática); testes adversariais na Fase 17 |
| TD-024 | Rate limit de IA só em 5 rotas. Webhooks e cron sem limite | idem §2 | Custo sem controle | 4/5 | PAID (Fase 4: teto automático por tenant/hora); quotas por plano na Fase 5 |

## Infra / processo

| ID | Dívida | Evidência | Impacto | Fase | Status |
|---|---|---|---|---|---|
| TD-030 | CI só em `master`; `staging` sem CI | `.github/workflows/ci.yml` | Regressões chegam ao staging | — (OI-005) | PAID (Fase 1, D-009) |
| TD-031 | Sem lock file Python (`pyproject.toml` com ranges) | comentários no próprio `pyproject`/`claude_provider.py` | Drift de SDK já causou incidente | 17 | OPEN |
| TD-032 | Rate limit em memória, 1 instância, sem fila/worker | `app/core/rate_limit.py` | Não escala horizontalmente | 17 | OPEN |
| TD-033 | Sem correlation ID nem métricas; só logging + Sentry | `app/core/logging.py` | Observabilidade (§76) | 3 | IN_PROGRESS: correlation ID + log de acesso (Fase 3); métricas agregadas na Fase 17 |
| TD-034 | Testes de mídia dependem de `ffmpeg` no host, sem skip quando ausente | 6 falhas no ambiente sem ffmpeg | Suite falha fora do CI | 1 | PAID (Fase 1: `tests/markers.py::requer_ffmpeg`) |
| TD-035 | 25 warnings de lint (`react-hooks/exhaustive-deps`) no frontend | `npm run lint` | Bugs sutis de re-render | oportunista | OPEN |
| TD-036 | Documentação de arquitetura duplicada (raiz × `docs/b2bon/`) | D-003 | Confusão sobre qual é a fonte | 1 | PAID (Fase 1: aviso no topo dos 5 docs de raiz) |
| TD-038 | `crm_service` ↔ `saude_conta_service` tinham import circular (mitigado com import local) | Fase 0 | Frágil | 1 | PAID (Fase 1: nenhum dos dois importa mais o outro) |
| TD-039 | Shims de compatibilidade em `conta_service`, `crm_service` e `metricas_service` (aliases para os contextos) | Fase 1 | Dois caminhos para a mesma função | 2–3 (remover quando não houver chamador) | OPEN |
| TD-040 | `decisores_da_conta(db, conta_id)` não filtra por tenant (confia em validação prévia do chamador) | `contexts/shared/organizations.py` | Risco de isolamento se chamado sem `obter_conta` antes | 2 | OPEN |
| TD-043 | Telas da B2B ON chamam rotas internas, não a API de produto (cliente zero só no nível de contrato) | `05_API_ARCHITECTURE.md` §8 | Duas superfícies HTTP para a mesma regra | 14/17 | OPEN |
| TD-044 | `AssinaturaWebhookParceiro.segredo` (API de Distribuidor, pré-Fase 3) grava o segredo HMAC em texto puro | `app/models/assinatura_webhook_parceiro.py` | Vazamento do banco expõe segredo de assinatura | 17 | OPEN |
| TD-045 | Rate limit da API de produto é em memória (1 instância) | `app/core/rate_limit.py` | Limite não vale entre instâncias | 17 | OPEN |
| TD-046 | Ledger de IA em sessão própria pode esperar lock em SQLite de dev com transação de escrita aberta | `gateway.py` | Só desenvolvimento local | 17 | OPEN |
| TD-047 | Teto de IA automática e rate limit em memória (1 instância) | `gateway.limitador_automatico` | Não vale entre instâncias | 17 | OPEN |
| TD-048 | Custo de APIs externas (Brave, Lusha, BrasilAPI) e de compute não entra no ledger de IA | `09_AI_FINOPS.md` §1 | Custo por feature subestimado quando há enriquecimento | 16/17 | OPEN |
| TD-049 | Sem alerta automático para `LEDGER_IA_FALHOU` e orçamento em alerta | logs | Perda de ledger passaria despercebida | 17 | OPEN |
| TD-050 | Carteira usa `SELECT … FOR UPDATE` (no-op em SQLite); concorrência real só testada em Postgres na Fase 17 | `finops/creditos.py` | Débito concorrente em SQLite dev | 17 | OPEN |
| TD-051 | Casamento necessidade × oferta é lexical (sem sinônimos/embeddings) | `opportunity/texto.py` | Recomendação perdida quando o cliente usa outras palavras | 17 | OPEN |
| TD-052 | Pesos do NBO e limiares do NBA (14 dias, 60%) sem calibração com resultado real | `opportunity/nbo.py`, `nba.py` | Ordem de recomendação subótima | 17 | OPEN |
| TD-053 | Tela de riscos de pipeline fica no menu da Rede (PREDATOR); cliente só CRM tem a API mas não a tela | `InteligenciaRede.tsx` | CRM-only vê riscos só no card do negócio | 7 | OPEN |
| TD-054 | Neo4j legado (`app/graph`) segue ativo para Conta/Decisor, paralelo ao Business Graph relacional | `app/graph/client.py` | Dois grafos; instância Aura pausa | 17 | OPEN |
| TD-055 | Bloqueio não registra quem bloqueou (conexão reaproveitada); regra é simétrica | `rede_social_service.bloquear` | Ambos deixam de se ver | 8 | OPEN |
| TD-056 | Nome de empresa não reivindicada é o informado por quem citou, não o oficial (BrasilAPI) | `network/identidade.por_cnpj` | Nome pode divergir da razão social | 8 | OPEN |
| TD-057 | Conversão de sinal sem lock: cliques simultâneos em sinais diferentes da mesma empresa podem criar duas contas | `network/conversao.py` | Duplicata rara | 17 | OPEN |
| TD-058 | Matching de intent/ICP ainda por palavra-chave do perfil; não usa Offer Intelligence (Fase 6) do vendedor | `sinal_oportunidade_service` | Matches perdidos | 17 | OPEN |
| TD-059 | Sem OCR: PDF digitalizado fica SEM_TEXTO | `bids/documentos.py` | Edital escaneado exige leitura humana | 17 | OPEN |
| TD-060 | Adapter PNCP não validado contra a API real (egress bloqueado no dev) | `bids/fontes/pncp.py` | Ingestão automática desligada | 17 | OPEN |
| TD-061 | Arquivos de edital/cofre em `LargeBinary` no Postgres | `documento_licitacao`, `documento_cofre` | Crescimento do banco; mover para object storage | 17 | OPEN |
| TD-062 | Casamento requisito × cofre/oferta é lexical | `bids/conformidade.py` | Requisito com outras palavras vira UNKNOWN | 17 | OPEN |
| TD-041 | Eventos publicados em só 3 fluxos (negócio, estágio, aprovação); dispatcher com gatilho por cron desde a Fase 3 | `EVENT_MODEL.md` | Consumidores não recebem os demais fatos | 3, 6–10 | OPEN |
| TD-042 | `B2BOnCrmAdapter.list_*` sem paginação para pipelines/estágios/ofertas e `CanonicalMapDataSource` carrega tudo em memória | `adapters/b2bon_crm.py`, `map/data_source.py` | Custo em tenants grandes | 17 | OPEN |
| TD-037 | `starlette.testclient` com `httpx` deprecated (warning) | saída do pytest | Quebra futura na atualização | oportunista | OPEN |
