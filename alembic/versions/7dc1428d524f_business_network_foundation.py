"""Business Network Foundation - Fase 7 do Master Prompt v4

Company Identity (`empresa_rede`): a empresa como objeto da rede,
reivindicada por um tenant ou ainda nao reivindicada (citada por CNPJ por
outra empresa). Arestas do Business Graph (`relacionamento_empresarial`)
ganham identidade de origem/destino, fonte e validade; o destino pode ser
uma empresa ainda sem tenant. `perfil_empresa.visivel_no_diretorio` da
ao tenant o controle de aparecer no diretorio (padrao: comportamento atual).

Revision ID: 7dc1428d524f
Revises: a8390a098f04
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7dc1428d524f'
down_revision: Union[str, Sequence[str], None] = 'a8390a098f04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _digitos(valor):
    digitos = "".join(c for c in (valor or "") if c.isdigit())
    return digitos or None


def upgrade() -> None:
    op.create_table(
        "empresa_rede",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=True, unique=True),
        sa.Column("cnpj", sa.String(), nullable=True, index=True),
        sa.Column("razao_social", sa.String(), nullable=True),
        sa.Column("nome_exibicao", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("origem", sa.String(), nullable=False),
        sa.Column("criado_por_tenant_id", sa.String(), nullable=True),
        sa.Column("mesclada_em_id", sa.Integer(), sa.ForeignKey("empresa_rede.id"), nullable=True),
        sa.Column("reivindicada_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    with op.batch_alter_table("perfil_empresa") as batch:
        batch.add_column(sa.Column("visivel_no_diretorio", sa.Boolean(), nullable=False, server_default=sa.true()))

    with op.batch_alter_table("relacionamento_empresarial") as batch:
        batch.alter_column("tenant_id_destino", existing_type=sa.String(), nullable=True)
        batch.add_column(sa.Column("empresa_origem_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("empresa_destino_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("fonte", sa.String(), nullable=False, server_default="DECLARADA"))
        batch.add_column(sa.Column("valido_desde", sa.Date(), nullable=True))
        batch.add_column(sa.Column("valido_ate", sa.Date(), nullable=True))
        batch.create_foreign_key("fk_relacionamento_empresa_origem", "empresa_rede", ["empresa_origem_id"], ["id"])
        batch.create_foreign_key("fk_relacionamento_empresa_destino", "empresa_rede", ["empresa_destino_id"], ["id"])
        batch.create_index("ix_relacionamento_empresa_destino", ["empresa_destino_id"])

    conexao = op.get_bind()
    perfis = conexao.execute(
        sa.text(
            "SELECT p.tenant_id, p.nome_exibicao, p.status_verificacao, t.razao_social, t.cnpj "
            "FROM perfil_empresa p JOIN tenant t ON t.id = p.tenant_id"
        )
    ).fetchall()
    empresa = sa.table(
        "empresa_rede",
        sa.column("tenant_id", sa.String), sa.column("cnpj", sa.String), sa.column("razao_social", sa.String),
        sa.column("nome_exibicao", sa.String), sa.column("status", sa.String), sa.column("origem", sa.String),
    )
    if perfis:
        op.bulk_insert(empresa, [
            {
                "tenant_id": tenant_id, "cnpj": _digitos(cnpj), "razao_social": razao_social,
                "nome_exibicao": nome or razao_social or tenant_id,
                "status": "VERIFICADA" if status == "verificada" else "REIVINDICADA", "origem": "TENANT",
            }
            for tenant_id, nome, status, razao_social, cnpj in perfis
        ])
    conexao.execute(sa.text(
        "UPDATE relacionamento_empresarial SET "
        "empresa_origem_id = (SELECT e.id FROM empresa_rede e WHERE e.tenant_id = relacionamento_empresarial.tenant_id_origem), "
        "empresa_destino_id = (SELECT e.id FROM empresa_rede e WHERE e.tenant_id = relacionamento_empresarial.tenant_id_destino), "
        "fonte = CASE WHEN confianca = 'confirmada_pela_contraparte' THEN 'CONFIRMADA' ELSE 'DECLARADA' END"
    ))


def downgrade() -> None:
    op.execute("DELETE FROM relacionamento_empresarial WHERE tenant_id_destino IS NULL")
    with op.batch_alter_table("relacionamento_empresarial") as batch:
        batch.drop_index("ix_relacionamento_empresa_destino")
        batch.drop_constraint("fk_relacionamento_empresa_destino", type_="foreignkey")
        batch.drop_constraint("fk_relacionamento_empresa_origem", type_="foreignkey")
        batch.drop_column("valido_ate")
        batch.drop_column("valido_desde")
        batch.drop_column("fonte")
        batch.drop_column("empresa_destino_id")
        batch.drop_column("empresa_origem_id")
        batch.alter_column("tenant_id_destino", existing_type=sa.String(), nullable=False)
    with op.batch_alter_table("perfil_empresa") as batch:
        batch.drop_column("visivel_no_diretorio")
    op.drop_table("empresa_rede")
