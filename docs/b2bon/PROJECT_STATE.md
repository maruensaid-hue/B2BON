# PROJECT STATE

| Campo | Valor |
|---|---|
| **CURRENT PHASE** | **PHASE J concluída** em 2026-09-26 (J1 troca S6 preparada e desligada; J2 TD-040/089/092; J3 OI-023). Próximas fases dependem de nova autorização do PO. Fases seguintes pré-autorizadas pelo PO, executadas uma por vez |
| Última fase concluída | PHASE 15 — PRICING, AI CREDITS & COMMERCIAL MONETIZATION (2026-09-25) |
| Fase 15 | Desbloqueada pelo PO em 2026-09-25 com o prompt "PHASE 15 — PRICING, AI CREDITS & COMMERCIAL MONETIZATION" (substitui o escopo "Public Procurement Pricing") e concluída no mesmo dia. Preço-base do Public Procurement e franquias do Procurement/Full Suite continuam PENDING_FINAL_DEFINITION por decisão do PO |
| Branch de trabalho | `staging` |
| Relatório da última fase | `phases/GOVERNMENT_COMPLETION.md` (antes: `PHASE_J_COMPLETION.md`, `PHASE_I_COMPLETION.md` com o aceite final §46–§47, `PHASE_H_COMPLETION.md`, `PHASE_G_COMPLETION.md`, `PHASE_F_COMPLETION.md`, `PHASE_E_COMPLETION.md`, `PHASE_D_COMPLETION.md`, `PHASE_C_COMPLETION.md`, `PHASE_B_COMPLETION.md`, `PHASE_A_COMPLETION.md`, `SOURCING_S4_COMPLETION.md`, `SOURCING_S3_COMPLETION.md`, `SOURCING_S0_S2_COMPLETION.md`, `PHASE_15_COMPLETION.md`) |
| B2B ON Government | 2026-10-01 — prompt do PO "B2B ON GOVERNMENT" (D-072): licença institucional + subscrição anual, três ofertas no catálogo central, pool anual de AI Credits, contratos/renovação/recebimentos, Bookings/ARR/TCV/Cash-In, comissão por componente (20% inicial, 10% renovação, PAYMENT_RECEIVED), pipeline Government, página pública e Admin → Planos. Relatório: `phases/GOVERNMENT_COMPLETION.md`. D-073 (adicionais Government a 10%) e D-074 (mesmo dia, correção definitiva): toda comissão sobre a Margem Comissionável Líquida, Commission Engine único. D-075: entitlements dos tiers (OI-024 resolvido), Tax Engine por tributo com os parâmetros do PO, câmbio por tabela. D-076: Infrastructure Cost Pool (plano máximo, custo real × provisionado, alocação ponderada 1/2/4, atribuição direta, capacidade e alertas), Tax Profiles 2026 revisados, PTAX, franquias de contas e Public Procurement BASIC/FULL. D-077: preços públicos verificados dos fornecedores (Render, Neon por Capacity Envelope, Lusha como provedor de dados), aplicabilidade à arquitetura, sem dupla contagem, capacidade não alocada. D-078: CBS/IBS 2026 dispensados mediante conformidade (alíquotas-teste preservadas, caixa zero, TaxStatusPeriod) |
| Documentação e onboarding | 2026-10-01 — pedido do PO ("Atualize toda a documentação e os tours"): tour guiado, tutoriais por módulo (Licitações, Compras públicas, Strategic Sourcing, Convites de compra), FAQ com IA, Manual do Usuário, README e `16_TEST_STRATEGY.md` atualizados. Sem mudança de regra de negócio. TD-093 resolvido com autorização do PO ("Sim pode agendar"): `/cron/creditos-ia` de hora em hora no workflow |
| Correção arquitetural | 2026-09-26 — Strategic Sourcing & Bids (D-055, `18_STRATEGIC_SOURCING.md`). Plano S0–S8; **S0–S4 autorizadas e concluídas** em 2026-09-26 (OI-020); S5–S8 não autorizadas. Após o deploy da S3: rodar o backfill (`/cron/sourcing-sincronizar`) uma vez |

## Autorizações

| Fase | Autorizada por | Data | Observações |
|---|---|---|---|
| 0 | Product Owner ("COMEÇAR AGORA PELA PHASE 0") | 2026-09-25 | — |
| 15 | Product Owner ("pode prosseguir e concluir a fase") | 2026-09-25 | Franquias do Public Procurement e da Full Suite: decisão futura do PO |
| S0–S2 (sourcing) | Product Owner ("Autorizado", sobre "S0–S2 são as fases de menor risco para começar") | 2026-09-26 | Sem mudança de schema nem de comportamento; S3–S8 continuam pendentes |
| S3 (sourcing) | Product Owner ("Autorizado", sobre "S3: criar as tabelas unificadas e migrar os dados aos poucos, mantendo as tabelas antigas até os resultados baterem") | 2026-09-26 | Primeira fase com mudança de schema; S4–S8 continuam pendentes |
| S4 (sourcing) + master | Product Owner ("S4: pode trocar" · "master: pode atualizar") | 2026-09-26 | `master` só depois de CI verde no `staging` |
| Plano unificado A–I · Phase A | Product Owner ("Autorizado" sobre S5 e OI-021 + prompt "UNIFIED BUSINESS & SOURCING IMPLEMENTATION"; escolheu "Phase A" quando perguntado) | 2026-09-26 | O plano A–I passa a ser a ordem (D-061). S5 = parte da Phase C; OI-021 = Phase I; ambas autorizadas, executadas na vez delas. Uma fase por vez |
| Plano A–I · B em diante + master | Product Owner ("Está previamente autorizado subir para o master e passar para as próximas fases") | 2026-09-26 | Uma fase por vez, cada uma com teste, medição, documentação e relatório; `master` só com CI verde |
| OI-019 (resolução) | Product Owner ("RESOLUÇÃO OI-019 — ENTERPRISE BIDS & STRATEGIC SOURCING") | 2026-09-26 | Pela regra §25 da própria resolução, a fase corrente (S4) só permite registrar arquitetura, especificação do catálogo, entitlements e documentação; a implementação comercial (planos, catálogo, página de vendas, entitlements no código) depende de fase autorizada (OI-021) |
| 1–17 | Product Owner ("Siga para a Fase 1 […] seguir para a Fase 2 e assim sucessivamente até o final do projeto, fica previamente autorizado o commit e subir todas as fases seguintes") | 2026-09-25 | **Exceções que continuam valendo, por regra do próprio Master Prompt:** Fase 15 só com valores de preço fornecidos pelo PO; nenhum preço ou valor de plano é alterado ou inventado (inclui OI-001) |

## Pendências abertas relevantes

- **OI-001** (crítica): limites 0 nos planos PREDATOR avulsos. Depende de valores do PO.
- **OI-017** (comercial): franquias de AI Credits do Public Procurement (50–100K) e da Full Suite (75–100K) e preço-base do Public Procurement — decisão futura do PO; hoje nada concedido por elas.
- **OI-018** (RESOLVED quanto à política, D-076): PTAX de fechamento do Banco Central (rotina horária/Admin); sem PTAX gravada, `AWAITING_FX_RATE`.
- **OI-026** (financeiro, alta, PARTIALLY_RESOLVED, D-077): preços públicos dos fornecedores cadastrados (Render, Neon, Lusha); faltam confirmar os componentes Render em uso, o Capacity Envelope do Neon (sem ele toda comissão fica `AWAITING_INFRASTRUCTURE_COST`), o storage envelope, outros fornecedores em uso, ISS da subscrição SaaS e perfis de consultoria/suporte. CBS/IBS 2026 resolvido (D-078: WAIVED_BY_COMPLIANCE).
- **Troca S6**: pronta atrás de `sourcing_leitura_fonte` (D-070); ligar só após o portão TD-087/088.
- **OI-022** (comercial): preço do buyer seat adicional e dos bundles futuros.
- **Plano A–I**: A–I concluídas, uma por vez (`18_STRATEGIC_SOURCING.md` §10).
- **Portão operacional S6** (TD-087/088): trocar a leitura para as tabelas unificadas só depois do backfill em produção e de uma release sem `SOURCING_DIVERGENCIA`.
- **OI-014** (produto): visibilidade padrão de empresas novas no diretório da rede.
- **OI-010** (alta): verificar em produção se as features de IA falhavam por `temperature` com `claude-sonnet-5` (corrigido no código).
- **OI-016** (operação): metas de RPO/RTO.
- OI-003, OI-006 a OI-009: ver `OPEN_ISSUES.md`.
- Conectores de CRM (Fase 13) estão BETA e desligados: habilitar em produção só após validar contra contas reais (TD-069).

## Baseline de qualidade (após a Phase J)

- Desempenho: `docs/b2bon/perf/baseline.json` (antes da expansão) e `fase_a.json` … `fase_i.json`; repetir com `tests/desempenho` a cada fase (§36).
- Duplicação: `scripts/qualidade/duplicacao.py` — 42 blocos / ~1.877 linhas repetidas (janela 8).

- Backend: 2.181 passed, 10 skipped (medição de desempenho sob demanda + 9 testes de Postgres rodam com `B2BON_TESTE_PG_URL`: 9/9 em Postgres 16). Leitura dupla de sourcing ESTRITA em toda a suíte. Migrações validadas também em Postgres 16 (head `d0f2b4c6e8a1`).
- Ruff: 40 (sem novos). Frontend: lint OK (25 warnings), build OK.
- E2E: 12/12 (setup de login + 11 specs).
