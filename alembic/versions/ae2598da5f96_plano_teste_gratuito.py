"""Plano de teste gratuito, sem prazo de expiracao

Revision ID: ae2598da5f96
Revises: 2e7a6f9c0d70
Create Date: 2026-08-20 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae2598da5f96'
down_revision: Union[str, Sequence[str], None] = '2e7a6f9c0d70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOME_PLANO = "Teste"


def upgrade() -> None:
    """Cria o plano 'Teste' (R$0/mês, franquia igual ao Starter) se ainda
    não existir. Tenants nascidos com este plano via POST /admin/tenants já
    ficam sem prazo de expiração por padrão — a Licenca é criada com
    data_expiracao=None, e suspender_licencas_vencidas nunca toca licença
    sem data_expiracao (ver app/services/tenant_service.py)."""
    conn = op.get_bind()
    ja_existe = conn.execute(sa.text("SELECT 1 FROM plano WHERE nome = :nome"), {"nome": NOME_PLANO}).first()
    if ja_existe is None:
        conn.execute(
            sa.text(
                "INSERT INTO plano (nome, franquia_contas_mes, max_usuarios, preco_mensal) "
                "VALUES (:nome, :franquia, :usuarios, :preco)"
            ),
            {"nome": NOME_PLANO, "franquia": 200, "usuarios": 10, "preco": 0.0},
        )


def downgrade() -> None:
    """Remove o plano 'Teste' — só se nenhum tenant estiver usando (evita
    quebrar Licenca.plano_id de tenant já criado com ele)."""
    conn = op.get_bind()
    em_uso = conn.execute(
        sa.text("SELECT 1 FROM licenca l JOIN plano p ON p.id = l.plano_id WHERE p.nome = :nome"),
        {"nome": NOME_PLANO},
    ).first()
    if em_uso is None:
        conn.execute(sa.text("DELETE FROM plano WHERE nome = :nome"), {"nome": NOME_PLANO})
