"""Corporate Profile - campos de identidade/richness (master prompt Fase 1)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('perfil_empresa', sa.Column('logo_url', sa.String(), nullable=True))
    op.add_column('perfil_empresa', sa.Column('capa_url', sa.String(), nullable=True))
    op.add_column('perfil_empresa', sa.Column('cnae_principal', sa.String(), nullable=True))
    op.add_column('perfil_empresa', sa.Column('porte', sa.String(), nullable=True))
    op.add_column('perfil_empresa', sa.Column('sede_cidade', sa.String(), nullable=True))
    op.add_column('perfil_empresa', sa.Column('sede_uf', sa.String(), nullable=True))
    op.add_column('perfil_empresa', sa.Column('mercados', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('perfil_empresa', sa.Column('produtos_servicos', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('perfil_empresa', sa.Column('tecnologias', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('perfil_empresa', sa.Column('certificacoes', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('perfil_empresa', sa.Column('redes_sociais', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column(
        'perfil_empresa',
        sa.Column('status_verificacao', sa.String(), nullable=False, server_default='nao_verificada'),
    )


def downgrade() -> None:
    op.drop_column('perfil_empresa', 'status_verificacao')
    op.drop_column('perfil_empresa', 'redes_sociais')
    op.drop_column('perfil_empresa', 'certificacoes')
    op.drop_column('perfil_empresa', 'tecnologias')
    op.drop_column('perfil_empresa', 'produtos_servicos')
    op.drop_column('perfil_empresa', 'mercados')
    op.drop_column('perfil_empresa', 'sede_uf')
    op.drop_column('perfil_empresa', 'sede_cidade')
    op.drop_column('perfil_empresa', 'porte')
    op.drop_column('perfil_empresa', 'cnae_principal')
    op.drop_column('perfil_empresa', 'capa_url')
    op.drop_column('perfil_empresa', 'logo_url')
