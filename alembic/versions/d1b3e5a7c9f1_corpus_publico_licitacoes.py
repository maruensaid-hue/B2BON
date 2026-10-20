"""Corpus público comum de licitações (V5.2.1, Fase 3): fato público único por (fonte, id externo) + vínculo da cópia privada do tenant.

Cria `licitacao_publica` e `evento_licitacao_publica`, adiciona `licitacao.corpus_id` e faz o backfill idempotente dos editais já ingeridos
por tenants (uma linha pública por (fonte, id externo), a partir da cópia mais recente). Licitação manual não entra no corpus.

Downgrade: remove o vínculo e as duas tabelas. **Perde** o histórico de retificações e as colunas uf/município do corpus; as licitações dos
tenants (privadas) permanecem intactas com os mesmos dados públicos que já tinham.

Revision ID: d1b3e5a7c9f1
Revises: c9f1b3d5e7a9
Create Date: 2026-10-20
"""
import hashlib
import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "d1b3e5a7c9f1"
down_revision = "c9f1b3d5e7a9"
branch_labels = None
depends_on = None

_LOTE = 500


def _hash_congelado(c: dict) -> str:
    """Cópia CONGELADA do algoritmo de `app.contexts.bids.corpus.hash_conteudo` na data desta migração (uma migração não pode mudar de
    comportamento quando o código evolui). Mesmos campos, mesma ordem, mesmo JSON canônico."""
    def iso(v):
        return v.isoformat() if isinstance(v, datetime) else v

    campos = [c["titulo"], c["objeto"], c["orgao_nome"], c["orgao_cnpj"], c["modalidade"], iso(c["data_publicacao"]), iso(c["prazo_proposta"]),
              c["valor_estimado"], c["situacao_externa"], c["url"]]
    return hashlib.sha256(json.dumps(campos, ensure_ascii=False, separators=(",", ":"), default=str).encode()).hexdigest()


def upgrade() -> None:
    op.create_table(
        "licitacao_publica",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fonte", sa.String(), nullable=False),
        sa.Column("fonte_id_externo", sa.String(), nullable=False),
        sa.Column("titulo", sa.String(), nullable=False),
        sa.Column("objeto", sa.Text(), nullable=True),
        sa.Column("orgao_nome", sa.String(), nullable=True),
        sa.Column("orgao_cnpj", sa.String(), nullable=True),
        sa.Column("uf", sa.String(2), nullable=True),
        sa.Column("municipio", sa.String(), nullable=True),
        sa.Column("modalidade", sa.String(), nullable=False),
        sa.Column("modalidade_codigo", sa.Integer(), nullable=True),
        sa.Column("data_publicacao", sa.DateTime(), nullable=True),
        sa.Column("prazo_proposta", sa.DateTime(), nullable=True),
        sa.Column("valor_estimado", sa.Float(), nullable=True),
        sa.Column("situacao_externa", sa.String(), nullable=True),
        sa.Column("atualizado_externo_em", sa.DateTime(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("hash_conteudo", sa.String(64), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("primeira_coleta_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("ultima_coleta_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("ultima_alteracao_em", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("fonte", "fonte_id_externo", name="uq_licitacao_publica_fonte_id"),
    )
    op.create_index("ix_licitacao_publica_orgao_cnpj", "licitacao_publica", ["orgao_cnpj"])
    op.create_index("ix_licitacao_publica_uf_publicacao", "licitacao_publica", ["uf", "data_publicacao"])
    op.create_table(
        "evento_licitacao_publica",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("licitacao_publica_id", sa.Integer(), sa.ForeignKey("licitacao_publica.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("mudancas", sa.JSON(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("observado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_evento_licitacao_publica_licitacao_publica_id", "evento_licitacao_publica", ["licitacao_publica_id"])

    with op.batch_alter_table("licitacao") as batch_op:
        batch_op.add_column(sa.Column("corpus_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_licitacao_corpus_id", ["corpus_id"])
        batch_op.create_foreign_key("fk_licitacao_corpus_id", "licitacao_publica", ["corpus_id"], ["id"])

    _backfill()


def _backfill() -> None:
    bind = op.get_bind()
    licitacao = sa.table(
        "licitacao", sa.column("id"), sa.column("titulo"), sa.column("objeto"), sa.column("orgao_nome"), sa.column("orgao_cnpj"), sa.column("modalidade"),
        sa.column("fonte"), sa.column("fonte_id_externo"), sa.column("fonte_url"), sa.column("data_publicacao"), sa.column("prazo_proposta"),
        sa.column("valor_estimado"), sa.column("situacao_externa"), sa.column("atualizado_externo_em"), sa.column("criado_em"), sa.column("corpus_id"),
    )
    publica = sa.table(
        "licitacao_publica", sa.column("id"), sa.column("fonte"), sa.column("fonte_id_externo"), sa.column("titulo"), sa.column("objeto"),
        sa.column("orgao_nome"), sa.column("orgao_cnpj"), sa.column("modalidade"), sa.column("data_publicacao"), sa.column("prazo_proposta"),
        sa.column("valor_estimado"), sa.column("situacao_externa"), sa.column("atualizado_externo_em"), sa.column("url"), sa.column("hash_conteudo"),
        sa.column("versao"), sa.column("primeira_coleta_em"), sa.column("ultima_coleta_em"),
    )
    externa = sa.and_(licitacao.c.fonte != "MANUAL", licitacao.c.fonte_id_externo.isnot(None))
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    mais_recente = sa.select(sa.func.max(licitacao.c.id)).where(externa).group_by(licitacao.c.fonte, licitacao.c.fonte_id_externo)
    linhas = bind.execute(sa.select(licitacao).where(licitacao.c.id.in_(mais_recente))).mappings().all()
    lote = []
    for r in linhas:
        c = {"titulo": r["titulo"], "objeto": r["objeto"], "orgao_nome": r["orgao_nome"], "orgao_cnpj": r["orgao_cnpj"], "modalidade": r["modalidade"],
             "data_publicacao": r["data_publicacao"], "prazo_proposta": r["prazo_proposta"], "valor_estimado": r["valor_estimado"],
             "situacao_externa": r["situacao_externa"], "url": r["fonte_url"]}
        lote.append({
            "fonte": r["fonte"], "fonte_id_externo": r["fonte_id_externo"], **{k: c[k] for k in ("titulo", "objeto", "orgao_nome", "orgao_cnpj", "modalidade")},
            "data_publicacao": c["data_publicacao"], "prazo_proposta": c["prazo_proposta"], "valor_estimado": c["valor_estimado"],
            "situacao_externa": c["situacao_externa"], "atualizado_externo_em": r["atualizado_externo_em"], "url": c["url"],
            "hash_conteudo": _hash_congelado(c), "versao": 1,
            "primeira_coleta_em": r["criado_em"] or agora, "ultima_coleta_em": r["criado_em"] or agora,
        })
        if len(lote) >= _LOTE:
            bind.execute(sa.insert(publica), lote)
            lote = []
    if lote:
        bind.execute(sa.insert(publica), lote)
    # Vincula TODAS as cópias privadas (não só a mais recente) ao fato público da mesma chave.
    alvo = (
        sa.select(publica.c.id).where(publica.c.fonte == licitacao.c.fonte, publica.c.fonte_id_externo == licitacao.c.fonte_id_externo).scalar_subquery()
    )
    bind.execute(sa.update(licitacao).where(externa).values(corpus_id=alvo))


def downgrade() -> None:
    with op.batch_alter_table("licitacao") as batch_op:
        batch_op.drop_constraint("fk_licitacao_corpus_id", type_="foreignkey")
        batch_op.drop_index("ix_licitacao_corpus_id")
        batch_op.drop_column("corpus_id")
    op.drop_index("ix_evento_licitacao_publica_licitacao_publica_id", table_name="evento_licitacao_publica")
    op.drop_table("evento_licitacao_publica")
    op.drop_index("ix_licitacao_publica_uf_publicacao", table_name="licitacao_publica")
    op.drop_index("ix_licitacao_publica_orgao_cnpj", table_name="licitacao_publica")
    op.drop_table("licitacao_publica")
