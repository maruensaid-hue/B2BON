"""Libera a pesquisa de decisores nos planos da matriz que ainda não tinham franquia configurada.

A matriz de franquias (Starter 30/5, Professional 60/10 etc.) foi aprovada pelo PO, mas só o plano "Teste" recebeu a linha na primeira migração (o resto
dos planos tinha outros nomes no banco, como "PREDATOR Starter"). Esta migração aplica a mesma matriz aos planos existentes que correspondem aos nomes da
linha (Starter, Professional e os planos de módulo PREDATOR equivalentes) e que ainda NÃO têm nenhuma configuração de enriquecimento: nunca sobrescreve uma
configuração que um administrador já definiu. Plano que não existe não é criado (exigiria preço) e Enterprise segue configurável por tenant.

Downgrade: remove só as linhas criadas por esta migração.

Revision ID: e8a0c2d4f6b8
Revises: d7f9b1c3e5a7
Create Date: 2026-10-22
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

from app.contexts.enriquecimento.matriz_dados import APROVADOR_MATRIZ, MOTIVO_MATRIZ, PLANOS

revision = "e8a0c2d4f6b8"
down_revision = "d7f9b1c3e5a7"
branch_labels = None
depends_on = None

_MOTIVO = MOTIVO_MATRIZ + " (aplicada aos planos de módulo equivalentes em 2026-10-22)"


def upgrade() -> None:
    conexao = op.get_bind()
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    configs = sa.table(
        "enriquecimento_config_plano",
        sa.column("plano_id", sa.Integer), sa.column("versao", sa.Integer), sa.column("modo", sa.String), sa.column("franquia_creditos", sa.Integer),
        sa.column("periodicidade", sa.String), sa.column("decisores_por_empresa_max", sa.Integer), sa.column("limite_creditos_pesquisa", sa.Integer),
        sa.column("motivo", sa.String), sa.column("criado_por", sa.String), sa.column("aprovado_por", sa.String), sa.column("aprovado_em", sa.DateTime),
        sa.column("valido_de", sa.DateTime),
    )
    plano = sa.table("plano", sa.column("id", sa.Integer), sa.column("nome", sa.String))
    for spec in PLANOS.values():
        cfg = spec["config"]
        if cfg is None or cfg["modo"] != "franquia_fixa":
            continue
        for linha in conexao.execute(sa.select(plano.c.id).where(plano.c.nome.in_(spec["aliases"]))).fetchall():
            ja_tem = conexao.execute(sa.select(configs.c.plano_id).where(configs.c.plano_id == linha[0])).first()
            if ja_tem is not None:
                continue
            op.bulk_insert(configs, [{
                "plano_id": linha[0], "versao": 1, "modo": cfg["modo"], "franquia_creditos": cfg.get("franquia_creditos"),
                "periodicidade": cfg.get("periodicidade"), "decisores_por_empresa_max": cfg.get("decisores_por_empresa_max"),
                "limite_creditos_pesquisa": cfg.get("limite_creditos_pesquisa"), "motivo": _MOTIVO, "criado_por": "migracao",
                "aprovado_por": APROVADOR_MATRIZ, "aprovado_em": agora, "valido_de": agora,
            }])


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM enriquecimento_config_plano WHERE motivo = :motivo").bindparams(motivo=_MOTIVO))
