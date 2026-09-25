# PHASE 13 — EXTERNAL CRM CONNECTORS · Completion Report

- **Data**: 2026-09-25 · **Branch**: `staging` · **Autorização**: PO (autorização geral das Fases 1–17)
- **Regra da fase**: um conector por vez (Salesforce → HubSpot → Pipedrive → RD Station), cada um com IMPLEMENT / TEST / DOCUMENT / VALIDATE / GATE e commit próprio.

## Progresso

| Conector | Estado | Testes | Commit |
|---|---|---|---|
| Salesforce | ✅ BETA (desligado por padrão, D-041) | `test_conector_salesforce.py` (23) | conector 1/4 |
| HubSpot | ✅ BETA (desligado por padrão) | `test_conector_hubspot.py` (14) | conector 2/4 |
| Pipedrive | ✅ BETA (desligado por padrão) | `test_conector_pipedrive.py` (11) | conector 3/4 |
| RD Station CRM | ⏳ | — | — |

## Base comum (entregue com o Salesforce)

- `adapters/http_base.py`: 429/5xx → `ErroTransitorio` (retry com backoff), 401/403 → `ErroCredencial` (sem retry, conexão fica `erro`), sem redirects, hosts fixos por conector (D-042).
- Hub: credenciais e configuração validadas por conector, gravadas criptografadas e nunca devolvidas; reconexão; `conectavel`; desabilitar bloqueia sync.
- `tests/conectores_crm.py`: suíte de conformidade compartilhada (tenant forçado, proveniência, ids canônicos, paginação até o fim, referências consistentes, isolamento).
- MAP API por `conexao_id`.

## GATE — Salesforce

| Evidência | Resultado |
|---|---|
| Suíte de conformidade do contrato (paginação por `nextRecordsUrl`, tenant, proveniência, referências, isolamento) | ✅ |
| Mapeamento campo a campo (contas, CNPJ, domínio, ciclo de vida, opt-out, estágios, oportunidades, moeda, clientes, atividades, interações, produtos) | ✅ |
| `instance_url`/`login_url` fora do Salesforce recusados (SSRF); configuração não injeta SOQL; id malicioso não vira consulta | ✅ |
| 429 retentado; 401 não retentado, conexão marcada `erro`, token fora da mensagem | ✅ |
| Token expirado renovado uma vez e persistido criptografado; refresh revogado = `ErroCredencial` | ✅ |
| Sync incremental usa `LastModifiedDate` a partir da última execução com sucesso | ✅ |
| Hub: BETA não conecta sem habilitação; credencial nunca volta na API; outro tenant = 404; reconectar reativa | ✅ |
| MAP via conexão = MAP via payload canônico (paridade) | ✅ |
| Suite completa | ✅ **1.880 passed** |
| Frontend lint (25) + typecheck | ✅ |
| E2E | ✅ 4/4 |

Decisões: D-041, D-042. Dívidas: TD-068 (OAuth pela UI), TD-069 (validação
contra conta real), TD-070 (somente leitura). Sem migração. Pendências do
PO inalteradas.

## GATE — HubSpot

| Evidência | Resultado |
|---|---|
| Suíte de conformidade compartilhada (paginação por `after`, tenant, proveniência, referências, isolamento); só `api.hubapi.com` é chamado | ✅ |
| Mapeamento (empresas, CNPJ, ciclo de vida, cliente só com data, contatos e opt-out, estágios, negócios com empresa via Associations v4, moeda do negócio ou padrão, engajamentos, notas sem HTML, produtos) | ✅ |
| Credenciais/configuração inválidas recusadas (inclui chave extra como `base_url`); cursor forjado recusado | ✅ |
| Incremental pela Search API (epoch ms, propriedade certa por objeto) a partir da última execução com sucesso | ✅ |
| 429 retentado; 401 não retentado e conexão `erro`; token OAuth renovado uma vez e persistido (inclui refresh token novo); refresh revogado = `ErroCredencial` | ✅ |
| Interações lidas uma vez por execução (MAP conta a conta sem N chamadas) | ✅ |
| Hub: BETA não conecta sem habilitação; credencial nunca volta; sync via API | ✅ |
| MAP via conexão = MAP via payload canônico | ✅ |
| Suite completa | ✅ **1.894 passed** |
| Frontend lint (25) + typecheck | ✅ |
| E2E | ✅ 4/4 |

Dívida nova: TD-071 (NPS de CRM externo). Sem migração.

## GATE — Pipedrive

| Evidência | Resultado |
|---|---|
| Suíte de conformidade compartilhada (paginação `start`/`next_start`, tenant, proveniência, referências, isolamento); só `api.pipedrive.com` | ✅ |
| Token só no header `x-api-token`, nunca na URL; token malformado/extra recusado; cursor forjado recusado | ✅ |
| Mapeamento (organizações, CNPJ por campo personalizado, cliente por negócio ganho, pessoas com e-mail principal e descadastro, negócios won/lost/open com data e motivo, atividades, produtos) | ✅ |
| Incremental por `/recents` a partir da última execução com sucesso | ✅ |
| 429 retentado; 401 não retentado, conexão `erro`, token fora da mensagem | ✅ |
| Hub (BETA só habilitado, credencial nunca volta) e MAP via conexão = payload canônico | ✅ |
| Suite completa | ✅ **1.905 passed** |
| Frontend lint (25) + typecheck | ✅ |
| E2E | ✅ 4/4 |

Sem migração, sem dívida nova.
