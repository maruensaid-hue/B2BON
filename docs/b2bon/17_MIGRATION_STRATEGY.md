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

## Histórico

| Fase | Revisão | O quê |
|---|---|---|
| 2 | `1ca76a6cdfbc` | tabela `evento_dominio` |
| 3 | `494a19ef8c61` | chaves de API, idempotência, webhooks de saída, conexões e execuções de sync |
| 4 | `af4fcaf0098f` | colunas de auditoria em `registro_uso_ia`; Corporate Brain, perfis, eventos de aprendizado |
| merge | `b53c1ac42468` | merge das heads Fase 4 × representantes/captura de lead (outra sessão) |
| 5 | `f892ebf6e6f9` | FinOps: preços, política de créditos (PENDING_DEFINITION), carteira, extrato, orçamentos |
