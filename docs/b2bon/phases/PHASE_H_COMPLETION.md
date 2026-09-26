# PHASE H — OPTIMIZATION · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO, pré-autorização das próximas fases.
- **ADR**: D-068 · **Plano**: `18_STRATEGIC_SOURCING.md` §10.

Regra da fase (§44): medir; eliminar duplicação **real**; nada de refactor cosmético.

## Medições (baseline da Phase A → Phase H)

| Medida | Baseline | Phase H |
|---|---|---|
| Duplicação (janela 8) | 46 blocos / ~2.193 linhas (antes da Phase H) | **43 / ~1.889** (−14% linhas) |
| Bundle — chunk de entrada (baixado por toda visita) | 368 KB | **320 KB** (−13%) |
| Bundle total | 1.298,3 KB / 58 arquivos | 1.339,6 KB / 80 (produtos novos das fases C–G em chunks sob demanda) |
| Inicialização da API | 3.403 ms | 3.226 ms |
| Memória de pico | 246,8 MB | 251,1 MB (+1,7%: routers e contextos novos) |
| Painel (3 rotas) · CRM (2) | 5/5/10 · 6/4 consultas | iguais; p95 menor em todas |
| Workspace do vendedor · Go/No-Go | 26 · 10 consultas | iguais; **constantes com o volume** (2 e 20 requisitos: 24/10/15 consultas em workspace/go-no-go/proposta) |
| Workspace do comprador público · riscos | 58 · 49 consultas | 19 · 10 (Phase D) |
| Comprador privado: workspace · comparação | — | 14 · 10, constantes com o volume |
| Fluxo do comprador de ponta a ponta | 127 consultas / p95 198 ms | 63 / 106 ms |
| Job de backfill do sourcing (200 licitações + requisitos) | 1.021 consultas / 238 ms | **623 / 187 ms** (−39% consultas) |
| Job de AI Credits (expiração, franquia, alertas) | — | 21–33 consultas, não cresce com o volume |
| E2E: erros `database is locked` / respostas 500 | 8 / 2 por rodada (TD-091) | **0 / 0** |

Latência: todas as rotas medidas ficaram iguais ou mais rápidas que o baseline (máquina compartilhada; o critério
confiável é o de consultas).

## O que mudou

| Item | Mudança | Por quê |
|---|---|---|
| Duplicação real | `pages/map/DetalheRisco.tsx`: score, sinais, script de resgate, histórico e modal de interação, usados por MAP de contas e de tenants (−355 linhas nas duas telas) | mesma regra e mesma tela em dois lugares |
| | `auth_service.validar_convite_disponivel`: regra de convite (revogado, usado, vencido → expirado) também para o convite de vitrine | regra de segurança repetida |
| | `app/api/respostas.py::arquivo_com_hash`: download de evidência com nome neutro e SHA-256 (bids, procurement, rede, sourcing ×2) | 5 cópias |
| | `lib/api.ts::exigirSucesso`: erro e 401 (sessão expirada × credencial errada) iguais para JSON e upload | lógica de sessão duplicada |
| Bundle | 11 páginas públicas além do login em chunks próprios, sob um `Suspense` | entrada −48 KB |
| Jobs | `espelho.LoteBackfill`: linhas existentes do lote em uma consulta; pais memorizados no lote | backfill diário sobre todas as linhas |
| Cache / semente | catálogo de AI Credits semeado na subida (lifespan) e no seed do E2E; semente preguiçosa segue idempotente | TD-091 |
| Custo de IA | sem mudança de política: tudo pelo AI Gateway (fitness), C0 antes de IA, uma execução por operação, cache só nas features cacheáveis | custo real por feature só com uso de produção (UNKNOWN aqui) |

**Não mudado de propósito** (detector aponta, mas não é lógica repetida): handlers de formulário parecidos em
`LeadsAcoesConta`, listas de import dos conectores, marcação de telas públicas diferentes. As 12 linhas repetidas nos
conectores Pipedrive/RD Station (BETA, desligados) viraram TD-092.

## Code size guard (§34)

| Métrica | Valor |
|---|---|
| Arquivos adicionados | 6: `api/respostas.py`, `pages/map/DetalheRisco.tsx`, `pages/map/risco.ts`, `test_semente_na_subida.py`, `e2e/map-risco.spec.ts`, `perf/fase_h.json` |
| Arquivos modificados | 15 |
| LOC da aplicação | **+356 / −447** (saldo −91) |
| LOC de testes | +51 |
| Duplicação | 46 → 43 blocos; ~2.193 → ~1.889 linhas |
| Compartilhado criado | `DetalheRisco`, `arquivo_com_hash`, `exigirSucesso`, `validar_convite_disponivel`, `LoteBackfill` |

## Validação

| Evidência | Resultado |
|---|---|
| Suíte completa | ✅ **2.080 passed** (+8 skipped: 7 Postgres, 1 medição) |
| Postgres 16: backfill S3, créditos concorrentes, Phases E/G | ✅ 7/7 |
| E2E | ✅ **11/11** (novo: MAP — detalhe de risco e registro de interação pelo componente compartilhado), 0 `database is locked`, 0 respostas 500 |
| Semente na subida: idempotente; falha não impede a subida | ✅ `test_semente_na_subida.py` |
| Ruff 40 · oxlint 25 · build | ✅ sem novos |

## Próximo passo

Phase I — Commercialization (OI-021): planos, módulos, entitlements, AI Credits, página de vendas e assinatura, com os
preços já aprovados (D-059) e o Public Procurement como PENDING_DEFINITION.
