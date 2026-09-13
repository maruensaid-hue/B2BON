"""Cadencia.icp_id/oferta_id - trava a campanha da cadencia na criacao

Raio-X de producao real: a geracao de mensagens usava "o ICP/Oferta que
estiver ativo agora pro tenant", sem vinculo com a cadencia sendo gerada.
Multiplos ICPs ativos ao mesmo tempo sao suportados de proposito (ver
icp_service.performance, comparacao entre campanhas) - trocar a Oferta
ativa pra uma campanha diferente corrompia silenciosamente a geracao de
QUALQUER cadencia ja criada antes (ICP de uma campanha + Oferta de outra).

Revision ID: 32e487955942
Revises: 70b0e2b13c18
Create Date: 2026-09-13 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32e487955942'
down_revision: Union[str, Sequence[str], None] = '70b0e2b13c18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('cadencia', sa.Column('icp_id', sa.Integer(), sa.ForeignKey('icp.id'), nullable=True))
    op.add_column('cadencia', sa.Column('oferta_id', sa.Integer(), sa.ForeignKey('oferta.id'), nullable=True))

    # Backfill best-esforço: cadências já existentes ficam travadas no
    # ICP/Oferta ativos HOJE (mesmo comportamento implícito que já valia
    # pra elas até agora) — sem isso, ficariam com NULL pra sempre e
    # continuariam caindo no fallback "o que estiver ativo agora",
    # vulneráveis ao mesmo bug que esta migração corrige.
    op.execute(
        """
        UPDATE cadencia
        SET oferta_id = (
            SELECT id FROM oferta
            WHERE oferta.tenant_id = cadencia.tenant_id AND oferta.ativo = true
            LIMIT 1
        )
        WHERE oferta_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE cadencia
        SET icp_id = (
            SELECT id FROM icp
            WHERE icp.tenant_id = cadencia.tenant_id AND icp.ativo = true
            LIMIT 1
        )
        WHERE icp_id IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('cadencia', 'oferta_id')
    op.drop_column('cadencia', 'icp_id')
