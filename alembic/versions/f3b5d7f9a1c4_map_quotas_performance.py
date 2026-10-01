"""D-080: MAP Performance Comercial — quotas, funil, comissão recorrente privada e Summer Sales Challenge.

- `representante.usuario_id`: usuário do representante no CRM da CyberFort (de onde o MAP lê atividade e pipeline).
- `quota_comercial`: quota NEW_MRR versionada por competência (padrão por representante ou específica).
- Políticas versionadas em `politica_comissao`: MAP_PERFORMANCE_POLICY (funil, atividade, mix, velocidade, governo,
  alertas), PRIVATE_RECURRING_COMMISSION (20% recorrente sobre mensalidade paga; inadimplência/cancelamento) e
  CAMPAIGN:SUMMER_SALES_CHALLENGE_2026 (Dez/26 + Jan/27, aceleradores 100/120/150%).
- Quotas do PO (por representante): Out/26 R$ 7.500 (pipeline alvo R$ 30.000), Nov R$ 10.000, Dez R$ 12.500,
  Jan/27 R$ 15.000, Fev R$ 17.500, Mar R$ 20.000 (equipe de 7: R$ 52.500 → R$ 140.000).
- Índices compostos para as agregações dos painéis (atividade, reunião, negócio).

Revision ID: f3b5d7f9a1c4
Revises: e2a4c6e8f0b3
Create Date: 2026-10-01
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision = "f3b5d7f9a1c4"
down_revision = "e2a4c6e8f0b3"
branch_labels = None
depends_on = None

# Os valores iniciais vivem num só lugar (o contexto MAP); a migração os copia para as tabelas versionadas.
_spec = importlib.util.spec_from_file_location(
    "map_performance_tipos", Path(__file__).resolve().parents[2] / "app/contexts/map/performance/tipos.py")
TIPOS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TIPOS)

POLITICAS = (
    (TIPOS.CODIGO_POLITICA_PERFORMANCE, TIPOS.POLITICA_PERFORMANCE_INICIAL, "PO (D-080): quotas, funil, atividade, mix, velocidade e governo"),
    (TIPOS.CODIGO_POLITICA_COMISSAO_PRIVADA, TIPOS.POLITICA_COMISSAO_PRIVADA_INICIAL, "PO (D-080): 20% recorrente sobre mensalidade paga"),
    (TIPOS.PREFIXO_CAMPANHA + TIPOS.CODIGO_CAMPANHA_VERAO, TIPOS.CAMPANHA_VERAO_INICIAL, "PO (D-080): Summer Sales Challenge Dez/26 + Jan/27"),
)
INDICES = (("ix_atividade_tenant_usuario_criado", "atividade", ["tenant_id", "usuario_id", "criado_em"]),
           ("ix_reuniao_tenant_vendedor_data", "reuniao", ["tenant_id", "vendedor_id", "data_hora"]),
           ("ix_negocio_tenant_vendedor", "negocio", ["tenant_id", "vendedor_usuario_id"]))


def upgrade() -> None:
    with op.batch_alter_table("representante") as tabela:
        tabela.add_column(sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuario.id", name="fk_representante_usuario"), nullable=True))
        tabela.create_index("ix_representante_usuario_id", ["usuario_id"])
    op.create_table(
        "quota_comercial", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("representante_id", sa.Integer(), sa.ForeignKey("representante.id"), nullable=True),
        sa.Column("metrica", sa.String(), nullable=False), sa.Column("competencia", sa.String(), nullable=False),
        sa.Column("valor", sa.Float(), nullable=False), sa.Column("multiplo_cobertura", sa.Float(), nullable=True),
        sa.Column("pipeline_alvo", sa.Float(), nullable=True), sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False), sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True), sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("representante_id", "metrica", "competencia", "versao"),
    )
    op.create_index("ix_quota_comercial_representante_id", "quota_comercial", ["representante_id"])
    op.create_index("ix_quota_comercial_competencia", "quota_comercial", ["competencia"])
    for nome, tabela, colunas in INDICES:
        op.create_index(nome, tabela, colunas)
    quota = sa.table("quota_comercial", sa.column("representante_id"), sa.column("metrica"), sa.column("competencia"), sa.column("valor"),
                     sa.column("multiplo_cobertura"), sa.column("pipeline_alvo"), sa.column("versao"), sa.column("ativa"),
                     sa.column("motivo"), sa.column("criado_por"))
    op.bulk_insert(quota, [{"representante_id": None, "metrica": "NEW_MRR", "competencia": competencia, "valor": valor,
                            "multiplo_cobertura": 3.0, "pipeline_alvo": pipeline, "versao": 1, "ativa": True,
                            "motivo": "Quota do PO (D-080)", "criado_por": "migracao"}
                           for competencia, valor, pipeline in TIPOS.QUOTAS_INICIAIS])
    politica = sa.table("politica_comissao", sa.column("codigo", sa.String), sa.column("versao", sa.Integer), sa.column("regras", sa.JSON),
                        sa.column("ativa", sa.Boolean), sa.column("motivo", sa.String), sa.column("criado_por", sa.String))
    op.bulk_insert(politica, [{"codigo": codigo, "versao": 1, "regras": regras, "ativa": True, "motivo": motivo, "criado_por": "migracao"}
                              for codigo, regras, motivo in POLITICAS])


def downgrade() -> None:
    conn = op.get_bind()
    for codigo, _, _ in POLITICAS:
        conn.execute(sa.text("DELETE FROM politica_comissao WHERE codigo = :c"), {"c": codigo})
    for nome, tabela, _ in INDICES:
        op.drop_index(nome, table_name=tabela)
    op.drop_index("ix_quota_comercial_competencia", table_name="quota_comercial")
    op.drop_index("ix_quota_comercial_representante_id", table_name="quota_comercial")
    op.drop_table("quota_comercial")
    with op.batch_alter_table("representante") as tabela:
        tabela.drop_index("ix_representante_usuario_id")
        tabela.drop_constraint("fk_representante_usuario", type_="foreignkey")
        tabela.drop_column("usuario_id")
