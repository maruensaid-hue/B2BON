import pytest

from app.models.conta import Conta
from app.services import atividade_service
from app.services.errors import ValidacaoFalhou

TENANT_ID = "tenant-atividade"


def _criar_conta(db_session) -> Conta:
    conta = Conta(tenant_id=TENANT_ID, icp_id=None, nome="Alpha Tech", status="prospectada")
    db_session.add(conta)
    db_session.commit()
    return conta


def test_registrar_exige_conta_ou_negocio(db_session):
    with pytest.raises(ValidacaoFalhou):
        atividade_service.registrar(db_session, TENANT_ID, tipo="sistema", descricao="Sem vínculo nenhum")


def test_registrar_e_listar_por_conta(db_session):
    conta = _criar_conta(db_session)

    atividade_service.registrar(db_session, TENANT_ID, conta_id=conta.id, tipo="sistema", descricao="Primeiro evento")
    atividade_service.registrar(db_session, TENANT_ID, conta_id=conta.id, tipo="nota", descricao="Segundo evento", ator_id="1")
    db_session.commit()

    atividades = atividade_service.listar_por_conta(db_session, TENANT_ID, conta.id)

    assert len(atividades) == 2
    # ordenado do mais recente para o mais antigo
    assert atividades[0].descricao == "Segundo evento"
    assert atividades[0].usuario_id == 1
    assert atividades[1].usuario_id is None


def test_listar_por_conta_nao_traz_atividade_de_outra_conta(db_session):
    conta1 = _criar_conta(db_session)
    conta2 = _criar_conta(db_session)
    atividade_service.registrar(db_session, TENANT_ID, conta_id=conta1.id, tipo="sistema", descricao="Evento da conta 1")
    db_session.commit()

    assert atividade_service.listar_por_conta(db_session, TENANT_ID, conta2.id) == []


def test_contexto_recentes_texto_sem_atividade_retorna_mensagem_padrao(db_session):
    conta = _criar_conta(db_session)

    texto = atividade_service.contexto_recentes_texto(db_session, TENANT_ID, conta_id=conta.id)

    assert texto == "Nenhuma atividade registrada ainda."


def test_contexto_recentes_texto_por_conta(db_session):
    conta = _criar_conta(db_session)
    atividade_service.registrar(db_session, TENANT_ID, conta_id=conta.id, tipo="nota", descricao="Ligação de descoberta")
    db_session.commit()

    texto = atividade_service.contexto_recentes_texto(db_session, TENANT_ID, conta_id=conta.id)

    assert "Ligação de descoberta" in texto
    assert "(nota)" in texto


def test_contexto_recentes_texto_por_negocio_nao_traz_atividade_so_de_conta(db_session):
    conta = _criar_conta(db_session)
    atividade_service.registrar(db_session, TENANT_ID, conta_id=conta.id, tipo="nota", descricao="Só da conta, sem negócio")
    db_session.commit()

    texto = atividade_service.contexto_recentes_texto(db_session, TENANT_ID, negocio_id=9999)

    assert texto == "Nenhuma atividade registrada ainda."


def test_contexto_recentes_texto_respeita_limite(db_session):
    conta = _criar_conta(db_session)
    for i in range(7):
        atividade_service.registrar(db_session, TENANT_ID, conta_id=conta.id, tipo="nota", descricao=f"Evento {i}")
    db_session.commit()

    texto = atividade_service.contexto_recentes_texto(db_session, TENANT_ID, conta_id=conta.id, limite=3)

    assert texto.count("Evento") == 3
