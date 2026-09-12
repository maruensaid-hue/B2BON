"""Registro de Oportunidade (RO) - deal registration entre revendedores

Revision ID: 70b0e2b13c18
Revises: c1a8e56d9f04
Create Date: 2026-09-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '70b0e2b13c18'
down_revision: Union[str, Sequence[str], None] = 'c1a8e56d9f04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'plano', sa.Column('permite_registro_oportunidade', sa.Boolean(), server_default='false', nullable=False)
    )

    op.create_table(
        'registro_oportunidade',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('rede_raiz_tenant_id', sa.String(), nullable=False),
        sa.Column('vendedor_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=False),
        sa.Column('cnpj', sa.String(), nullable=False),
        sa.Column('nome_empresa', sa.String(), nullable=False),
        sa.Column('conta_id', sa.Integer(), sa.ForeignKey('conta.id'), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('expira_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_registro_oportunidade_tenant_id', 'registro_oportunidade', ['tenant_id'])
    op.create_index('ix_registro_oportunidade_rede_raiz_tenant_id', 'registro_oportunidade', ['rede_raiz_tenant_id'])
    op.create_index('ix_registro_oportunidade_cnpj', 'registro_oportunidade', ['cnpj'])
    # Só um RO "ativo" por CNPJ dentro de uma mesma rede — garantido no
    # banco (índice único parcial), não por uma checagem prévia em
    # código, pra não abrir uma corrida entre dois revendedores
    # registrando a mesma empresa ao mesmo tempo.
    op.create_index(
        'ix_registro_oportunidade_ativo_unico',
        'registro_oportunidade',
        ['rede_raiz_tenant_id', 'cnpj'],
        unique=True,
        postgresql_where=sa.text("status = 'ativo'"),
    )

    op.create_table(
        'solicitacao_desconto',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column(
            'registro_oportunidade_id', sa.Integer(), sa.ForeignKey('registro_oportunidade.id'), nullable=False
        ),
        sa.Column('solicitante_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=False),
        sa.Column('percentual_solicitado', sa.Float(), nullable=False),
        sa.Column('justificativa', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('aprovador_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('motivo_decisao', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('decidido_em', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_solicitacao_desconto_tenant_id', 'solicitacao_desconto', ['tenant_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_solicitacao_desconto_tenant_id', table_name='solicitacao_desconto')
    op.drop_table('solicitacao_desconto')

    op.drop_index('ix_registro_oportunidade_ativo_unico', table_name='registro_oportunidade')
    op.drop_index('ix_registro_oportunidade_cnpj', table_name='registro_oportunidade')
    op.drop_index('ix_registro_oportunidade_rede_raiz_tenant_id', table_name='registro_oportunidade')
    op.drop_index('ix_registro_oportunidade_tenant_id', table_name='registro_oportunidade')
    op.drop_table('registro_oportunidade')

    op.drop_column('plano', 'permite_registro_oportunidade')
