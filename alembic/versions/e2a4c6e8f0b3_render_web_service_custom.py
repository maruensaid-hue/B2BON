"""D-079: Render Web Service 12c-96g passa a CUSTOM (sem preço público verificável).

- A página oficial do Render não publica preço para o Web Service 12 CPU / 96 GB (o maior plano padrão com preço é o Pro
  Ultra; instâncias maiores são sob consulta). Os USD 1.500/mês semeados na D-077 não têm fonte e saem.
- O componente continua aplicável (APPLICABLE_PENDING_CONFIRMATION) e provisionado para comissão: sem valor de contrato,
  proposta ou fatura, o pool aguarda (AWAITING_COST_PARAMETERS) — nunca um valor inventado.
- Inventário real do Render em 2026-10-01: b2bon-api e b2bon-api-staging no plano free, sem Postgres nem Key Value.
- A alteração fica no audit_log (antes/depois e motivo), como numa alteração pelo Admin.

Revision ID: e2a4c6e8f0b3
Revises: d0f2b4c6e8a1
Create Date: 2026-10-01
"""

import json
from datetime import date

import sqlalchemy as sa

from alembic import op

revision = "e2a4c6e8f0b3"
down_revision = "d0f2b4c6e8a1"
branch_labels = None
depends_on = None

VERIFICADO = date(2026, 10, 1)
FILTRO = "fornecedor = 'RENDER' AND servico = 'WEB_SERVICE_COMPUTE' AND plano_referencia = '12c-96g' AND criado_por = 'migracao'"
ANTES = {"modelo_preco": "FIXED_PLAN", "custo_referencia": 1500.00,
         "observacoes": "Maior Web Service público (12 CPU, 96 GB) como envelope conservador do serviço principal (b2bon-api)."}
DEPOIS = {"modelo_preco": "CUSTOM", "custo_referencia": None,
          "observacoes": "CUSTOM: o Render não publica preço para 12 CPU / 96 GB (sob consulta). Sem valor até contrato, proposta "
                         "ou fatura. Em uso hoje: b2bon-api e b2bon-api-staging no plano free."}
MOTIVO = "PO (2026-10-01): 12c-96g sem preço público verificável no Render — marcado como CUSTOM"


def _aplicar(valores: dict, auditoria: tuple[dict, dict]) -> None:
    conn = op.get_bind()
    ids = [linha[0] for linha in conn.execute(sa.text(f"SELECT id FROM componente_infra WHERE {FILTRO}"))]
    conn.execute(sa.text(f"UPDATE componente_infra SET modelo_preco = :modelo_preco, custo_referencia = :custo_referencia, "
                         f"observacoes = :observacoes, verificado_em = :verificado_em WHERE {FILTRO}"),
                 {**valores, "verificado_em": VERIFICADO})
    log = sa.table("audit_log", sa.column("tenant_id"), sa.column("evento_tipo"), sa.column("entidade_tipo"), sa.column("entidade_id"),
                   sa.column("ator_id"), sa.column("detalhes", sa.JSON))
    antes, depois = auditoria
    op.bulk_insert(log, [{"tenant_id": "plataforma", "evento_tipo": "componente_infra_alterado", "entidade_tipo": "componente_infra",
                          "entidade_id": i, "ator_id": "migracao",
                          "detalhes": json.loads(json.dumps({"antes": antes, "depois": depois, "motivo": MOTIVO, "origem": "migracao"}))}
                         for i in ids])


def upgrade() -> None:
    _aplicar(DEPOIS, (ANTES, DEPOIS))


def downgrade() -> None:
    _aplicar(ANTES, (DEPOIS, ANTES))
