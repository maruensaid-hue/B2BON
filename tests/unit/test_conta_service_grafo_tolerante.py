import pytest

from app.models.conta import Conta
from app.models.icp import ICP
from app.schemas.decisor import DecisorCreateSchema
from app.services import conta_service

TENANT_ID = "tenant-grafo-tolerante"


class FakeGraphIndisponivel:
    """Simula o Neo4j fora do ar — qualquer chamada de escrita explode,
    igual acontece de verdade quando a AuraDB está pausada ou a rede
    falha (raio-X de produção: cadastro de contato quebrava por completo
    nesse cenário, sem explicar o motivo pro usuário)."""

    def upsert_conta(self, tenant_id: str, conta_id: int, propriedades: dict) -> None:
        raise ConnectionError("Neo4j indisponível")

    def upsert_decisor(self, tenant_id: str, decisor_id: int, conta_id: int, propriedades: dict) -> None:
        raise ConnectionError("Neo4j indisponível")


def _criar_conta(db_session) -> Conta:
    icp = ICP(
        tenant_id=TENANT_ID,
        grupo_id="grupo-1",
        nome="ICP Teste",
        segmento="Tecnologia",
        porte="PEQUENO",
        regiao="SP",
        cnae_codigos=["6201500"],
        ufs=["SP"],
    )
    db_session.add(icp)
    db_session.flush()

    conta = Conta(tenant_id=TENANT_ID, icp_id=icp.id, nome="Alpha Tech", status="prospectada")
    db_session.add(conta)
    db_session.commit()
    return conta


def test_criar_decisor_manual_funciona_mesmo_com_neo4j_fora_do_ar(db_session):
    conta = _criar_conta(db_session)
    dados = DecisorCreateSchema(nome="Fulano de Tal", cargo="Diretor", email="fulano@teste.com")

    decisor = conta_service.criar_decisor_manual(
        db_session, TENANT_ID, None, conta.id, dados, FakeGraphIndisponivel()
    )

    assert decisor.id is not None
    assert decisor.nome == "Fulano de Tal"
    assert decisor.neo4j_node_id is None
