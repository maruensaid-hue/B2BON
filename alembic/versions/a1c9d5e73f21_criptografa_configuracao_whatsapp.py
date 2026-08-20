"""Criptografa em repouso os campos sensiveis de configuracao_whatsapp

Achado de seguranca do raio-X de compliance: access_token, phone_number_id
e business_account_id ficavam em texto puro no Postgres. O tipo da coluna
nao muda (continua VARCHAR); só o conteúdo passa a ser um token Fernet
cifrado com `configuracao_whatsapp_encryption_key`
(ver `app/core/crypto.py`). Idempotente: uma linha já cifrada (decrypt
bem-sucedido) é deixada como está, então rodar de novo por engano não
corrompe o dado.

Revision ID: a1c9d5e73f21
Revises: 2e7a6f9c0d70
Create Date: 2026-08-20 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import InvalidToken

from app.core.crypto import obter_fernet

# revision identifiers, used by Alembic.
revision: str = 'a1c9d5e73f21'
down_revision: Union[str, Sequence[str], None] = '2e7a6f9c0d70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_tabela = sa.table(
    "configuracao_whatsapp",
    sa.column("id", sa.Integer),
    sa.column("access_token", sa.String),
    sa.column("phone_number_id", sa.String),
    sa.column("business_account_id", sa.String),
)
_COLUNAS = ("access_token", "phone_number_id", "business_account_id")


def upgrade() -> None:
    """Criptografa quem ainda estiver em texto puro."""
    fernet = obter_fernet()
    conn = op.get_bind()
    linhas = conn.execute(sa.select(_tabela.c.id, *[_tabela.c[c] for c in _COLUNAS])).fetchall()

    for linha in linhas:
        valores_novos = {}
        for coluna in _COLUNAS:
            valor = getattr(linha, coluna)
            try:
                fernet.decrypt(valor.encode())
                continue  # já cifrado, não mexe
            except InvalidToken:
                valores_novos[coluna] = fernet.encrypt(valor.encode()).decode()
        if valores_novos:
            conn.execute(_tabela.update().where(_tabela.c.id == linha.id).values(**valores_novos))


def downgrade() -> None:
    """Descriptografa de volta pra texto puro quem estiver cifrado."""
    fernet = obter_fernet()
    conn = op.get_bind()
    linhas = conn.execute(sa.select(_tabela.c.id, *[_tabela.c[c] for c in _COLUNAS])).fetchall()

    for linha in linhas:
        valores_novos = {}
        for coluna in _COLUNAS:
            valor = getattr(linha, coluna)
            try:
                valores_novos[coluna] = fernet.decrypt(valor.encode()).decode()
            except InvalidToken:
                continue  # já era texto puro, não mexe
        if valores_novos:
            conn.execute(_tabela.update().where(_tabela.c.id == linha.id).values(**valores_novos))
