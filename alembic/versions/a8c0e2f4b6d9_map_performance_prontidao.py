"""D-081: MAP Performance pronto para um time de tamanho variável e para a configuração pendente (OI-029).

- Summer Sales Challenge: `meta_equipe` deixa de ser fixa (R$ 192.500 = 7 × R$ 27.500) e passa a ser a meta individual
  × representantes ativos — os representantes estão em contratação e o número pode mudar.
- MAP_PERFORMANCE_POLICY: `definicoes.contato_efetivo_confirmado = false` — o critério de "contato efetivo" (ligação ou
  reunião) vale como provisório até a gestão comercial confirmar.
Cada mudança é uma versão nova da política (a anterior fica inativa); o downgrade remove a versão criada aqui.

Revision ID: a8c0e2f4b6d9
Revises: f3b5d7f9a1c4
Create Date: 2026-10-01
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "a8c0e2f4b6d9"
down_revision = "f3b5d7f9a1c4"
branch_labels = None
depends_on = None

MOTIVO = "D-081: time de tamanho variável e configuração pendente (OI-029)"
CAMPANHA = "CAMPAIGN:SUMMER_SALES_CHALLENGE_2026"
PERFORMANCE = "MAP_PERFORMANCE_POLICY"


def _ajustar(regras: dict, codigo: str) -> dict:
    regras = json.loads(json.dumps(regras))
    if codigo == CAMPANHA:
        regras["meta_equipe"] = None
    else:
        regras.setdefault("definicoes", {})["contato_efetivo_confirmado"] = False
    return regras


def upgrade() -> None:
    conn = op.get_bind()
    tabela = sa.table("politica_comissao", sa.column("codigo", sa.String), sa.column("versao", sa.Integer), sa.column("regras", sa.JSON),
                      sa.column("ativa", sa.Boolean), sa.column("motivo", sa.String), sa.column("criado_por", sa.String))
    for codigo in (CAMPANHA, PERFORMANCE):
        atual = conn.execute(sa.select(tabela.c.versao, tabela.c.regras).where(tabela.c.codigo == codigo, tabela.c.ativa.is_(True))
                             .order_by(tabela.c.versao.desc())).first()
        if atual is None:
            continue
        regras = atual.regras if isinstance(atual.regras, dict) else json.loads(atual.regras)
        conn.execute(tabela.update().where(tabela.c.codigo == codigo).values(ativa=False))
        op.bulk_insert(tabela, [{"codigo": codigo, "versao": atual.versao + 1, "regras": _ajustar(regras, codigo), "ativa": True,
                                 "motivo": MOTIVO, "criado_por": "migracao"}])


def downgrade() -> None:
    conn = op.get_bind()
    for codigo in (CAMPANHA, PERFORMANCE):
        conn.execute(sa.text("DELETE FROM politica_comissao WHERE codigo = :c AND motivo = :m AND criado_por = 'migracao'"),
                     {"c": codigo, "m": MOTIVO})
        conn.execute(sa.text("UPDATE politica_comissao SET ativa = true WHERE codigo = :c AND versao = "
                             "(SELECT max(versao) FROM politica_comissao WHERE codigo = :c)"), {"c": codigo})
