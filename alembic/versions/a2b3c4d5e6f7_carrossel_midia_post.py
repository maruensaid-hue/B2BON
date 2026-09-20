"""Carrossel de fotos - tabela midia_post substitui midia_* em post_rede_social

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'midia_post',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('post_rede_social.id'), nullable=False),
        sa.Column('ordem', sa.Integer(), nullable=False),
        sa.Column('conteudo', sa.LargeBinary(), nullable=False),
        sa.Column('tipo_mime', sa.String(), nullable=False),
        sa.Column('tamanho_bytes', sa.Integer(), nullable=False),
    )
    op.create_index('ix_midia_post_post_id', 'midia_post', ['post_id'])

    # Migra o anexo único que já existisse (feature enviada minutos
    # antes desta) pra virar o item 0 do carrossel — sem isso, todo
    # post com foto/vídeo já publicado perderia o anexo.
    op.execute(
        """
        INSERT INTO midia_post (post_id, ordem, conteudo, tipo_mime, tamanho_bytes)
        SELECT id, 0, midia_conteudo, midia_tipo_mime, midia_tamanho_bytes
        FROM post_rede_social
        WHERE midia_conteudo IS NOT NULL
        """
    )

    with op.batch_alter_table('post_rede_social') as batch_op:
        batch_op.drop_column('midia_conteudo')
        batch_op.drop_column('midia_tipo_mime')
        batch_op.drop_column('midia_tamanho_bytes')


def downgrade() -> None:
    with op.batch_alter_table('post_rede_social') as batch_op:
        batch_op.add_column(sa.Column('midia_conteudo', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('midia_tipo_mime', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('midia_tamanho_bytes', sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE post_rede_social
        SET midia_conteudo = (SELECT conteudo FROM midia_post WHERE midia_post.post_id = post_rede_social.id AND ordem = 0),
            midia_tipo_mime = (SELECT tipo_mime FROM midia_post WHERE midia_post.post_id = post_rede_social.id AND ordem = 0),
            midia_tamanho_bytes = (SELECT tamanho_bytes FROM midia_post WHERE midia_post.post_id = post_rede_social.id AND ordem = 0)
        WHERE id IN (SELECT post_id FROM midia_post WHERE ordem = 0)
        """
    )

    op.drop_index('ix_midia_post_post_id', table_name='midia_post')
    op.drop_table('midia_post')
