"""Reacoes com emoji (tipo em reacao_post) + compartilhamento de post (post_original_id)

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-09-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reacao_post', sa.Column('tipo', sa.String(), nullable=False, server_default='curtir'))
    # FK auto-referenciada (post_rede_social -> post_rede_social) exige
    # batch mode no SQLite — mesmo ADD COLUMN simples vira ADD CONSTRAINT
    # por baixo quando a FK é pra própria tabela (achado real testando
    # localmente; FKs pra OUTRA tabela não precisam disso). Batch mode
    # recria a tabela por baixo, o que exige nomear a constraint
    # explicitamente (mesmo padrão já usado na Fase 7B).
    with op.batch_alter_table('post_rede_social') as batch_op:
        batch_op.add_column(
            sa.Column(
                'post_original_id',
                sa.Integer(),
                sa.ForeignKey('post_rede_social.id', name='fk_post_rede_social_post_original_id'),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('post_rede_social') as batch_op:
        batch_op.drop_column('post_original_id')
    with op.batch_alter_table('reacao_post') as batch_op:
        batch_op.drop_column('tipo')
