"""Custo de infraestrutura dos planos Business (+30%) e Corporate (+40%).

O custo de infraestrutura de cada cliente é o pool provisionado dividido por unidades ponderadas; o peso vem do `tier_infraestrutura` do plano na política
versionada `INFRASTRUCTURE_COST_POLICY`. O Enterprise pesa 4,0, então Business = 4,0 × 1,30 = 5,2 e Corporate = 4,0 × 1,40 = 5,6.

* Os planos Business e Corporate passam dos tiers herdados do Enterprise para os tiers BUSINESS e CORPORATE (só se ainda estão com ENTERPRISE).
* A política vigente ganha uma versão nova com os dois pesos, preservando todos os outros valores (pesos, limiares, base de custo e pools) como estão hoje.
  Se a política já tem os dois pesos, nada é publicado. Sem política publicada (banco novo), a política inicial do código já traz os pesos.

Downgrade: devolve os tiers ao ENTERPRISE e remove a versão publicada por esta migração, reativando a anterior.

Revision ID: d4f6b8c0e2a5
Revises: c3e5a7b9d1f4
Create Date: 2026-10-24
"""
import sqlalchemy as sa
from alembic import op

revision = "d4f6b8c0e2a5"
down_revision = "c3e5a7b9d1f4"
branch_labels = None
depends_on = None

CODIGO = "INFRASTRUCTURE_COST_POLICY"
MOTIVO = "D-105: Business = Enterprise + 30% (peso 5,2) e Corporate = Enterprise + 40% (peso 5,6)"
PLANOS_TIER = (("Business", "BUSINESS"), ("Corporate", "CORPORATE"))


def _politica() -> sa.Table:
    return sa.table("politica_comissao", sa.column("id", sa.Integer), sa.column("codigo", sa.String), sa.column("versao", sa.Integer),
                    sa.column("regras", sa.JSON), sa.column("ativa", sa.Boolean), sa.column("motivo", sa.String), sa.column("criado_por", sa.String))


def upgrade() -> None:
    conexao = op.get_bind()
    plano = sa.table("plano", sa.column("nome", sa.String), sa.column("tier_infraestrutura", sa.String))
    for nome, tier in PLANOS_TIER:
        conexao.execute(sa.update(plano).where(plano.c.nome == nome, plano.c.tier_infraestrutura == "ENTERPRISE").values(tier_infraestrutura=tier))

    politica = _politica()
    atual = conexao.execute(sa.select(politica).where(politica.c.codigo == CODIGO, politica.c.ativa.is_(True)).order_by(politica.c.versao.desc())).mappings().first()
    if atual is None:
        return
    regras = dict(atual["regras"])
    pesos = dict(regras.get("pesos") or {})
    if "BUSINESS" in pesos and "CORPORATE" in pesos:
        return
    base = float(pesos.get("ENTERPRISE", 4.0))
    pesos.setdefault("BUSINESS", round(base * 1.3, 4))
    pesos.setdefault("CORPORATE", round(base * 1.4, 4))
    regras["pesos"] = pesos
    ultima = conexao.execute(sa.select(sa.func.max(politica.c.versao)).where(politica.c.codigo == CODIGO)).scalar() or 0
    conexao.execute(sa.update(politica).where(politica.c.codigo == CODIGO).values(ativa=False))
    conexao.execute(sa.insert(politica).values(codigo=CODIGO, versao=ultima + 1, regras=regras, ativa=True, motivo=MOTIVO, criado_por="migracao"))


def downgrade() -> None:
    conexao = op.get_bind()
    plano = sa.table("plano", sa.column("nome", sa.String), sa.column("tier_infraestrutura", sa.String))
    for nome, tier in PLANOS_TIER:
        conexao.execute(sa.update(plano).where(plano.c.nome == nome, plano.c.tier_infraestrutura == tier).values(tier_infraestrutura="ENTERPRISE"))

    politica = _politica()
    conexao.execute(sa.delete(politica).where(politica.c.codigo == CODIGO, politica.c.motivo == MOTIVO, politica.c.criado_por == "migracao"))
    restante = conexao.execute(sa.select(sa.func.max(politica.c.versao)).where(politica.c.codigo == CODIGO)).scalar()
    if restante is not None and conexao.execute(sa.select(politica.c.id).where(politica.c.codigo == CODIGO, politica.c.ativa.is_(True))).first() is None:
        conexao.execute(sa.update(politica).where(politica.c.codigo == CODIGO, politica.c.versao == restante).values(ativa=True))
