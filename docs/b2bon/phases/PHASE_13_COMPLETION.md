# PHASE 13 — EXTERNAL CRM CONNECTORS · Completion Report

- **Data**: 2026-09-25 · **Branch**: `staging` · **Autorização**: PO (autorização geral das Fases 1–17)
- **Regra da fase**: um conector por vez (Salesforce → HubSpot → Pipedrive → RD Station), cada um com IMPLEMENT / TEST / DOCUMENT / VALIDATE / GATE e commit próprio.

## Progresso

| Conector | Estado | Testes | Commit |
|---|---|---|---|
| Salesforce | ✅ BETA (desligado por padrão, D-041) | `test_conector_salesforce.py` (23) | conector 1/4 |
| HubSpot | ⏳ | — | — |
| Pipedrive | ⏳ | — | — |
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
