"""usuario gratuito com mesmos recursos - limite semanal e email smtp por tenant

Revision ID: 0363630be266
Revises: ff8579321bae
Create Date: 2026-08-28 20:00:37.837685

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0363630be266'
down_revision: Union[str, Sequence[str], None] = 'ff8579321bae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Limite semanal por plano (raio-X 2026-08-28) — proporcional à franquia
# mensal de cada um, na mesma razão validada no Teste (50/semana pra 200
# de franquia/mês = 25%). Vale pra todo plano, não só o gratuito — mesmos
# valores de `scripts/bootstrap_tenant.py::PLANOS_PADRAO`, pra ambiente
# recriado do zero e produção existente baterem.
LIMITES_POR_PLANO = {
    "POC": 15,
    "Teste": 50,
    "Starter": 50,
    "Professional": 200,
    "Enterprise": 1250,
}


def upgrade() -> None:
    op.add_column('plano', sa.Column('limite_enriquecimento_site_semanal', sa.Integer(), nullable=True))
    op.add_column('plano', sa.Column('limite_enriquecimento_contatos_semanal', sa.Integer(), nullable=True))

    conn = op.get_bind()
    for nome, limite in LIMITES_POR_PLANO.items():
        conn.execute(
            sa.text(
                "UPDATE plano SET limite_enriquecimento_site_semanal = :limite, "
                "limite_enriquecimento_contatos_semanal = :limite WHERE nome = :nome"
            ),
            {"limite": limite, "nome": nome},
        )

    op.create_table(
        'enriquecimento_semanal_consumo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('semana', sa.String(), nullable=False),
        sa.Column('consumido_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_enriquecimento_semanal_consumo_tenant_id'),
        'enriquecimento_semanal_consumo', ['tenant_id'],
    )

    op.create_table(
        'configuracao_email_smtp',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('host', sa.String(), nullable=False),
        sa.Column('porta', sa.Integer(), nullable=False),
        sa.Column('usuario', sa.String(), nullable=False),
        sa.Column('senha', sa.String(), nullable=False),
        sa.Column('usar_tls', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id'),
    )
    op.create_index(
        op.f('ix_configuracao_email_smtp_tenant_id'),
        'configuracao_email_smtp', ['tenant_id'],
    )


def downgrade() -> None:
    op.drop_table('configuracao_email_smtp')
    op.drop_table('enriquecimento_semanal_consumo')
    op.drop_column('plano', 'limite_enriquecimento_contatos_semanal')
    op.drop_column('plano', 'limite_enriquecimento_site_semanal')
