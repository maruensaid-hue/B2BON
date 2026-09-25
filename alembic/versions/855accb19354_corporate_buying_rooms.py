"""Corporate Rooms & Buying Rooms - Fase 11 do Master Prompt v4

Participantes por usuario (permissoes), documentos, tarefas, reunioes e
stakeholders da sala, cada um com escopo compartilhado | interno. A sala de
compra ganha titulo e fase compartilhados: o comprador nunca ve o nome
interno nem o estagio do funil do vendedor.

Revision ID: 855accb19354
Revises: 815caa6c49f8
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '855accb19354'
down_revision: Union[str, Sequence[str], None] = '815caa6c49f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base(nome: str, *colunas: sa.Column) -> None:
    op.create_table(
        nome,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sala_id", sa.Integer(), sa.ForeignKey("sala_corporativa.id"), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        *colunas,
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    _base(
        "participante_sala",
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("papel", sa.String(), nullable=False),
        sa.UniqueConstraint("sala_id", "usuario_id", name="uq_participante_sala"),
    )
    _base(
        "documento_sala",
        sa.Column("canal_id", sa.Integer(), sa.ForeignKey("canal_sala.id"), nullable=True),
        sa.Column("escopo", sa.String(), nullable=False),
        sa.Column("nome_arquivo", sa.String(), nullable=False),
        sa.Column("tipo_mime", sa.String(), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("conteudo", sa.LargeBinary(), nullable=False),
        sa.Column("enviado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
    )
    _base(
        "tarefa_sala",
        sa.Column("escopo", sa.String(), nullable=False),
        sa.Column("titulo", sa.String(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("responsavel_tenant_id", sa.String(), nullable=True),
        sa.Column("responsavel_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("prazo", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
    )
    _base(
        "reuniao_sala",
        sa.Column("escopo", sa.String(), nullable=False),
        sa.Column("titulo", sa.String(), nullable=False),
        sa.Column("inicio", sa.DateTime(), nullable=False),
        sa.Column("fim", sa.DateTime(), nullable=True),
        sa.Column("link", sa.String(), nullable=True),
        sa.Column("pauta", sa.Text(), nullable=True),
        sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
    )
    _base(
        "stakeholder_sala",
        sa.Column("escopo", sa.String(), nullable=False),
        sa.Column("lado", sa.String(), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("cargo", sa.String(), nullable=True),
        sa.Column("papel", sa.String(), nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
    )
    with op.batch_alter_table("sala_compra") as batch:
        batch.add_column(sa.Column("titulo_compartilhado", sa.String(), nullable=True))
        batch.add_column(sa.Column("fase_compartilhada", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sala_compra") as batch:
        batch.drop_column("fase_compartilhada")
        batch.drop_column("titulo_compartilhado")
    for nome in ("stakeholder_sala", "reuniao_sala", "tarefa_sala", "documento_sala", "participante_sala"):
        op.drop_table(nome)
