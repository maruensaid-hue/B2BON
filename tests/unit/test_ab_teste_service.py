from datetime import UTC, datetime

from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.mensagem import Mensagem
from app.services import ab_teste_service

TENANT_ID = "tenant-teste"


def _preparar_cadencia(db_session) -> int:
    icp = ICP(tenant_id=TENANT_ID, grupo_id="grupo-1", nome="ICP", segmento="Tecnologia", porte="PEQUENO", regiao="SP", ativo=True)
    db_session.add(icp)
    db_session.flush()
    conta = Conta(tenant_id=TENANT_ID, icp_id=icp.id, nome="Conta", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    cadencia = Cadencia(tenant_id=TENANT_ID, nome="Cadência", status="ativa")
    db_session.add(cadencia)
    db_session.flush()
    return cadencia.id


def _decisor_com_resposta(db_session, conta_id: int, respondeu: bool) -> int:
    decisor = Decisor(
        tenant_id=TENANT_ID,
        conta_id=conta_id,
        nome="Decisor",
        ultima_interacao_em=datetime.now(UTC) if respondeu else None,
    )
    db_session.add(decisor)
    db_session.flush()
    return decisor.id


def _mensagem_enviada(db_session, cadencia_id: int, decisor_id: int, variante: str) -> None:
    db_session.add(
        Mensagem(
            tenant_id=TENANT_ID,
            cadencia_id=cadencia_id,
            decisor_id=decisor_id,
            canal="email",
            conteudo="x",
            variante_ab=variante,
            status="enviado",
        )
    )


def test_relatorio_sem_amostra_suficiente_nao_declara_vencedora(db_session):
    """E3-H5: sem significância mínima, não há vencedora declarada."""
    cadencia_id = _preparar_cadencia(db_session)
    conta = db_session.query(Conta).filter_by(tenant_id=TENANT_ID).first()

    for _ in range(2):
        decisor_a = _decisor_com_resposta(db_session, conta.id, respondeu=True)
        _mensagem_enviada(db_session, cadencia_id, decisor_a, "A")
    for _ in range(2):
        decisor_b = _decisor_com_resposta(db_session, conta.id, respondeu=True)
        _mensagem_enviada(db_session, cadencia_id, decisor_b, "B")
    db_session.commit()

    relatorio = ab_teste_service.relatorio(db_session, TENANT_ID, cadencia_id)

    assert relatorio["significativo"] is False
    assert relatorio["vencedora"] is None


def test_relatorio_com_diferenca_grande_declara_vencedora(db_session):
    """E3-H5: relatório de vencedora por taxa de resposta com significância mínima."""
    cadencia_id = _preparar_cadencia(db_session)
    conta = db_session.query(Conta).filter_by(tenant_id=TENANT_ID).first()

    for i in range(30):
        decisor_a = _decisor_com_resposta(db_session, conta.id, respondeu=(i < 27))  # 90% resposta
        _mensagem_enviada(db_session, cadencia_id, decisor_a, "A")
    for i in range(30):
        decisor_b = _decisor_com_resposta(db_session, conta.id, respondeu=(i < 3))  # 10% resposta
        _mensagem_enviada(db_session, cadencia_id, decisor_b, "B")
    db_session.commit()

    relatorio = ab_teste_service.relatorio(db_session, TENANT_ID, cadencia_id)

    assert relatorio["significativo"] is True
    assert relatorio["vencedora"] == "A"


def test_relatorio_sem_dados_retorna_totais_zerados(db_session):
    cadencia_id = _preparar_cadencia(db_session)

    relatorio = ab_teste_service.relatorio(db_session, TENANT_ID, cadencia_id)

    assert relatorio["variante_a"]["total"] == 0
    assert relatorio["variante_b"]["total"] == 0
    assert relatorio["vencedora"] is None
