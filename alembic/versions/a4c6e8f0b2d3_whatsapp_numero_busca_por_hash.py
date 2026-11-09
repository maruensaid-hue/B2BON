"""Busca do tenant pelo número de WhatsApp por hash (respostas do WhatsApp nunca eram tratadas).

O webhook da Meta identifica o tenant pelo `phone_number_id` que recebeu a mensagem. Essa coluna é cifrada com Fernet, que gera um valor
diferente a cada gravação: tanto a busca do código quanto a política do RLS (`phone_number_id = b2bon_chave()`) comparavam com o valor
cifrado e nunca achavam o tenant (visto em produção em 09/11/2026). Agora a busca usa `phone_number_id_hash` (sha256 do ID), preenchido
aqui para as linhas existentes (decifrando o ID com a mesma chave da aplicação) e pelo modelo nas gravações seguintes.

Revision ID: a4c6e8f0b2d3
Revises: f3b5d7a9c1e2
Create Date: 2026-11-09
"""
import logging

import sqlalchemy as sa
from alembic import op

from app.core.crypto import obter_fernet
from app.models.configuracao_whatsapp import hash_phone_number_id

revision = "a4c6e8f0b2d3"
down_revision = "f3b5d7a9c1e2"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_POLITICA = "rls_busca_whatsapp_numero"


def upgrade() -> None:
    op.add_column("configuracao_whatsapp", sa.Column("phone_number_id_hash", sa.String(), nullable=True))
    op.create_index("ix_configuracao_whatsapp_phone_number_id_hash", "configuracao_whatsapp", ["phone_number_id_hash"])

    conexao = op.get_bind()
    fernet = obter_fernet()
    for linha_id, cifrado in conexao.execute(sa.text("SELECT id, phone_number_id FROM configuracao_whatsapp")).fetchall():
        try:
            numero = fernet.decrypt(cifrado.encode()).decode()
        except Exception:  # noqa: BLE001 — linha com chave antiga: fica sem hash até alguém salvar a configuração de novo
            logger.warning("configuracao_whatsapp %s: phone_number_id não decifrou; o hash fica vazio até salvar a configuração", linha_id)
            continue
        conexao.execute(
            sa.text("UPDATE configuracao_whatsapp SET phone_number_id_hash = :h WHERE id = :id"),
            {"h": hash_phone_number_id(numero), "id": linha_id},
        )

    if conexao.dialect.name == "postgresql":
        op.execute(f"DROP POLICY IF EXISTS {_POLITICA} ON configuracao_whatsapp")
        op.execute(
            f"CREATE POLICY {_POLITICA} ON configuracao_whatsapp FOR SELECT "
            "USING (b2bon_escopo() = 'whatsapp-numero' AND phone_number_id_hash = b2bon_chave())"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP POLICY IF EXISTS {_POLITICA} ON configuracao_whatsapp")
        op.execute(
            f"CREATE POLICY {_POLITICA} ON configuracao_whatsapp FOR SELECT "
            "USING (b2bon_escopo() = 'whatsapp-numero' AND phone_number_id = b2bon_chave())"
        )
    op.drop_index("ix_configuracao_whatsapp_phone_number_id_hash", table_name="configuracao_whatsapp")
    op.drop_column("configuracao_whatsapp", "phone_number_id_hash")
