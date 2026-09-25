# PHASE 0 — COMPLETE DISCOVERY & AUDIT · Completion Report

- **Data**: 2026-09-25
- **Branch**: `staging` (commit base `93dede8`)
- **Escopo executado**: auditoria e documentação, **sem refatoração**,
  **sem alteração de preços, planos ou entitlements**, sem novos módulos.

## 1. Entregáveis

| Exigido (§84 Fase 0) | Arquivo |
|---|---|
| 01_CURRENT_ARCHITECTURE.md | `docs/b2bon/01_CURRENT_ARCHITECTURE.md` |
| DOMAIN_DEPENDENCY_MAP.md | `docs/b2bon/DOMAIN_DEPENDENCY_MAP.md` |
| DATABASE_MAP.md | `docs/b2bon/DATABASE_MAP.md` |
| MAP_CURRENT_STATE.md | `docs/b2bon/MAP_CURRENT_STATE.md` |
| PREDATOR_CURRENT_STATE.md | `docs/b2bon/PREDATOR_CURRENT_STATE.md` |
| AI_CURRENT_STATE.md | `docs/b2bon/AI_CURRENT_STATE.md` |
| PRICING_CURRENT_STATE.md | `docs/b2bon/PRICING_CURRENT_STATE.md` |
| SECURITY_BOUNDARIES.md | `docs/b2bon/SECURITY_BOUNDARIES.md` |
| TECHNICAL_DEBT.md | `docs/b2bon/TECHNICAL_DEBT.md` |
| Memória persistente (§2) | `00_MASTER_ARCHITECTURE.md`, `PROJECT_STATE.md`, `DECISIONS.md`, `OPEN_ISSUES.md`, `CHANGELOG_IMPLEMENTATION.md`, placeholders `02`–`17` |
| Plano detalhado da Fase 1 | `phases/PHASE_1_PLAN.md` |

## 2. Respostas às perguntas obrigatórias da Fase 0

| Pergunta | Resposta curta | Detalhe |
|---|---|---|
| Onde o MAP está acoplado ao CRM? | Frontend do MAP chama `/crm/*` (C1); LTV/CAC/ROI estão em `crm_service` (C2); MAP lê `Negocio`/`EstagioFunil` direto; NPS está no gate do PREDATOR (C6) | `DOMAIN_DEPENDENCY_MAP.md` §4, `MAP_CURRENT_STATE.md` §3 |
| Onde o PREDATOR está acoplado? | Rotas de prospecção sob o gate do CRM (C3); Kanban do CRM cria conta via `/leads` (C4); `conta_service` mistura os dois (TD-001); escreve `Conta`/`Decisor` sem contrato | `PREDATOR_CURRENT_STATE.md` §3 |
| Onde acontecem chamadas de IA? | 14 call sites, todos via `llm_helpers` → `LLMProvider` → `ClaudeProvider`. Só 3 são medidos | `AI_CURRENT_STATE.md` §2 |
| Como os preços estão armazenados? | Tabela `plano` (`preco_mensal` Float), mais cópias hardcoded em `Planos.tsx` e `bootstrap_tenant.py` | `PRICING_CURRENT_STATE.md` §1 |
| Como planos são implementados? | 1 `Licenca` por tenant → 1 `Plano`; 14 planos (5 suíte + 9 avulsos); `modulos_contratados` JSON | idem §2–3 |
| Como feature access funciona? | Backend: `exigir_licenca_ativa` + `exigir_modulo` por router, e flags/limites via `PlanLimitsProvider`. Frontend espelha via `recursos_plano` | idem §3 |
| Como a página de vendas obtém preços? | **Hardcoded** (não chama API). Casa com o checkout pelo nome do plano | idem §1 |
| Como billing funciona? | Mercado Pago, cobrança mensal avulsa (não recorrente), webhook HMAC ativa a licença, cron cuida de lembrete/suspensão | idem §6 |

## 3. Achados principais (por severidade)

1. **[Crítico, produção] OI-001**: planos PREDATOR avulsos têm todos os
   limites = 0. Quem paga R$ 475,50–1.521,60/mês não consegue criar
   cadência nem campanha, consumir franquia ou enriquecer. **Não
   corrigido** (Fase 0 proíbe mexer em planos). Precisa de hotfix
   autorizado.
2. **[Alto] OI-002**: 7 acoplamentos (C1–C7) fazem tenants de plano
   avulso receberem 403 dentro do módulo que compraram. O caso inverso
   também ocorre (CRM-only recebe rotas do PREDATOR).
3. **[Alto] IA não medida**: 11/14 call sites, 3 deles disparados por
   webhook ou cron sem rate limit. O gate §82 não é atendido hoje.
4. **[Médio] Preço em 3 lugares** (DB, página pública, script de seed).
5. **[Médio] CI não roda em `staging`**, que é o branch de desenvolvimento.
6. **[Médio] Isolamento de tenant só por disciplina de código**, sem
   teste genérico. 12 tabelas sem `tenant_id`, 4 delas escopadas por FK.
   O doc de raiz dizia que era só 1.
7. **[Info] Docs de raiz desatualizados** (ex.: "8 pontos de IA").
   `docs/b2bon/` passa a ser a fonte (D-003).

## 4. Pontos fortes a preservar

- Human-in-the-loop estrutural: o disparador só enxerga
  `status in ("aprovado","falhou")`. LinkedIn nunca é auto-enviado.
- Ponto único de saída de IA (`LLMProvider`). Nenhuma chamada direta ao SDK.
- Padrão de portas (ABC) para todos os provedores externos, incluindo
  `CrmProvider` e `PlanLimitsProvider`, que já são contratos entre módulos.
- Papel e tenant relidos do banco a cada request. Guardas de segredo em produção.
- Cultura de "não inventar número" (CAC/ROI `None` quando não calculável;
  padrões com amostra mínima), alinhada aos §23 e §63.

## 5. Testes executados nesta fase

| Suite | Comando | Resultado |
|---|---|---|
| Backend (unit + integration + alembic) | `python -m pytest -q` | **1.459 passed, 6 failed** na primeira execução. As 6 falhas eram só `FileNotFoundError: ffprobe` (ffmpeg ausente no container; o CI instala). Depois de instalar o ffmpeg, as 49 dos 3 arquivos afetados passaram. **Baseline efetiva: 1.465 passed, 0 falhas de código** |
| Frontend lint | `npm run lint` | OK (exit 0), 25 warnings `react-hooks/exhaustive-deps` |
| Frontend build (tsc + vite) | `npm run build` | OK |
| E2E Playwright | `npx playwright test` | 1ª execução: 4 falhas por versão de browser do ambiente (`chromium_headless_shell-1234` ausente). Com config temporária (não commitada) apontando para `/opt/pw-browsers/chromium`: **4/4 passed**. Neo4j ausente foi tolerado (best-effort) |

Nenhum código foi alterado, então não há regressão possível nesta fase.

Ajuste de ambiente (não commitado): `pip install --ignore-installed PyJWT`
(o PyJWT vinha instalado pelo Debian) e `apt-get install ffmpeg`.

## 6. Riscos e pendências

Ver `OPEN_ISSUES.md` (OI-001 a OI-009), `TECHNICAL_DEBT.md` (TD-001 a
TD-037) e `SECURITY_BOUNDARIES.md` §9 (S1–S6). Os que dependem de
decisão do PO antes ou durante a Fase 1:

- **OI-001**: autorizar o hotfix dos limites PREDATOR (fora do fluxo de fases).
- **OI-004**: quais operações de Conta/Decisor são compartilhadas
  CRM↔PREDATOR. Retirar do CRM-only as rotas de prospecção é mudança
  visível.
- **OI-005**: habilitar CI em `staging`.

## 7. git status ao final da fase

```
On branch staging
Untracked: docs/b2bon/   (antes do commit desta fase)
```

Nenhum arquivo de código, migração ou configuração foi modificado.

## 8. Próxima fase

**PHASE 1 — DOMAIN SEPARATION**. Plano em `phases/PHASE_1_PLAN.md`.
**Aguardando autorização explícita do Product Owner.**

**FASE 0 ENCERRADA. PARADO.**
