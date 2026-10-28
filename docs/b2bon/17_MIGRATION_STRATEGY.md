# 17 — MIGRATION STRATEGY

## Código: Strangler Pattern (Fases 1+)

1. Criar o destino em `app/contexts/<ctx>/` com contrato.
2. Mover a implementação; deixar alias/shim no local antigo (TD-039).
3. Apontar chamadores novos para o contrato; a fitness function impede regressão.
4. Remover o shim quando não houver mais chamadores.

## Banco: Alembic

- Cabeça única obrigatória (`tests/test_alembic_upgrade.py` roda `upgrade head` em SQLite).
- Revision id aleatório (`uuid4().hex[:12]`) — D-012.
- Toda migração nova é testada em Postgres 16 local: upgrade → downgrade -1 → upgrade.
- Migração compatível com SQLite e Postgres (`sa.func.now()`, booleans como `sa.true()`/strings, sem SQL específico de dialeto).
- Migração de dados que mexe em preço/plano **só** com instrução do PO.
- **`lock_timeout` em PostgreSQL**: `alembic/env.py` aplica `SET LOCAL lock_timeout` (`app/db/migracao.py`, padrão `30s`, ajustável por `ALEMBIC_LOCK_TIMEOUT`).
  Se a tabela estiver em uso, a migração falha em segundos e o deploy não vai ao ar (a versão anterior segue atendendo). Testes: `tests/unit/test_migracao_limite_de_espera.py`
  e, em PostgreSQL real, `tests/test_migracao_limite_de_espera_pg.py` (job `postgres-migrations` do CI). `SET LOCAL` vale só na transação, então funciona atrás de pgbouncer.
- **Revision id duplicado**: antes de criar uma migração, confira os ids existentes (`ls alembic/versions`); um id repetido quebra a cabeça única.

## Histórico

| Fase | Revisão | O quê |
|---|---|---|
| 2 | `1ca76a6cdfbc` | tabela `evento_dominio` |
| 3 | `494a19ef8c61` | chaves de API, idempotência, webhooks de saída, conexões e execuções de sync |
| 4 | `af4fcaf0098f` | colunas de auditoria em `registro_uso_ia`; Corporate Brain, perfis, eventos de aprendizado |
| merge | `b53c1ac42468` | merge das heads Fase 4 × representantes/captura de lead (outra sessão) |
| 5 | `f892ebf6e6f9` | FinOps: preços, política de créditos (PENDING_DEFINITION), carteira, extrato, orçamentos |
| 2026-10-24 | `c3e5a7b9d1f4` | novos limites da planilha comercial e planos Business e Corporate (só altera coluna que ainda tem o valor anterior) |
| 2026-10-24 | `d4f6b8c0e2a5` | custo de infraestrutura dos tiers Business (+30%) e Corporate (+40%) |
| 2026-10-26 | `e5a7c9d1f3b6` | `campanha.processando_ate` (reserva do disparo) |
| 2026-10-27 | `f6b8d0e2a4c7` | `campanha_destinatario.empresa` |
| 2026-10-27 | `c1e3a5b7d9f4` | `configuracao_email_api`; `campanha_destinatario.aberto_em/entregue_em/pixel_incluido`; `mensagem.entregue_em` |
| 2026-10-28 | `d4f6a8c0e2b4` | `bloqueio_contato` (cabeça atual) |
