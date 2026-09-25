"""Orçamento de consultas (Fase 17): telas que avaliam a carteira inteira
não podem fazer uma consulta por conta (N+1). Achado no teste de carga:
`/crm/dashboard/economia` fazia 303 consultas com 300 contas."""

from datetime import UTC, datetime

from sqlalchemy import event

from app.contexts.map import contract as map_contract
from app.models.conta import Conta
from app.models.interacao_conta import InteracaoConta

TENANT = "tenant-teste"


class _Contador:
    def __init__(self, engine) -> None:
        self.total = 0
        self._engine = engine

    def __enter__(self):
        event.listen(self._engine, "before_cursor_execute", self._contar)
        return self

    def __exit__(self, *exc):
        event.remove(self._engine, "before_cursor_execute", self._contar)

    def _contar(self, *args):
        self.total += 1


def _carteira(db, quantidade: int) -> None:
    for i in range(quantidade):
        conta = Conta(tenant_id=TENANT, nome=f"Conta {i}", status="prospectada", cliente_desde=datetime(2025, 1, 1))
        db.add(conta)
        db.flush()
        db.add(InteracaoConta(tenant_id=TENANT, conta_id=conta.id, tipo="contato", criado_em=datetime.now(UTC)))
    db.commit()


def test_economia_da_carteira_nao_faz_uma_consulta_por_conta(db_session):
    _carteira(db_session, 40)
    periodo = datetime.now(UTC).strftime("%Y-%m")
    with _Contador(db_session.get_bind()) as contador:
        resultado = map_contract.economia(db_session, TENANT, periodo)
    assert resultado["periodo"] == periodo
    assert contador.total <= 12, f"{contador.total} consultas para 40 contas"


def test_score_de_uma_conta_continua_lendo_so_ela(db_session):
    _carteira(db_session, 5)
    fonte = map_contract.CrmInternoMapDataSource(db_session)
    conta = db_session.query(Conta).filter_by(tenant_id=TENANT).first()
    assert len(fonte.interacoes(TENANT, conta.id)) == 1
    outra = db_session.query(Conta).filter(Conta.tenant_id == TENANT, Conta.id != conta.id).first()
    assert len(fonte.interacoes(TENANT, outra.id)) == 1 and len(fonte.interacoes(TENANT, conta.id)) == 1
