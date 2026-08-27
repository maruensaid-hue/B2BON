from app.models.conta import Conta
from app.models.fila_enriquecimento_conta import FilaEnriquecimentoConta
from app.services import conta_service

TENANT_ID = "tenant-enriquecimento-lote"
OUTRO_TENANT_ID = "tenant-enriquecimento-lote-outro"


def _criar_conta(db_session, tenant_id: str = TENANT_ID, nome: str = "Alpha Tech") -> Conta:
    conta = Conta(tenant_id=tenant_id, icp_id=None, nome=nome, status="prospectada")
    db_session.add(conta)
    db_session.commit()
    return conta


def test_enfileira_as_contas_selecionadas(db_session):
    conta1 = _criar_conta(db_session, nome="Empresa A")
    conta2 = _criar_conta(db_session, nome="Empresa B")

    resultado = conta_service.enfileirar_enriquecimento_em_lote(db_session, TENANT_ID, [conta1.id, conta2.id])

    assert resultado == {"contas_enfileiradas": 2}
    itens = db_session.query(FilaEnriquecimentoConta).order_by(FilaEnriquecimentoConta.id).all()
    assert {item.conta_id for item in itens} == {conta1.id, conta2.id}
    assert all(item.status == "pendente" for item in itens)


def test_ignora_ids_de_outro_tenant(db_session):
    conta_do_tenant = _criar_conta(db_session, nome="Empresa A")
    conta_de_outro_tenant = _criar_conta(db_session, tenant_id=OUTRO_TENANT_ID, nome="Empresa de outro tenant")

    resultado = conta_service.enfileirar_enriquecimento_em_lote(
        db_session, TENANT_ID, [conta_do_tenant.id, conta_de_outro_tenant.id]
    )

    assert resultado == {"contas_enfileiradas": 1}
    itens = db_session.query(FilaEnriquecimentoConta).all()
    assert {item.conta_id for item in itens} == {conta_do_tenant.id}


def test_nao_duplica_conta_que_ja_tem_item_pendente(db_session):
    conta = _criar_conta(db_session)
    conta_service.enfileirar_enriquecimento_em_lote(db_session, TENANT_ID, [conta.id])

    resultado = conta_service.enfileirar_enriquecimento_em_lote(db_session, TENANT_ID, [conta.id])

    assert resultado == {"contas_enfileiradas": 0}
    assert db_session.query(FilaEnriquecimentoConta).filter_by(conta_id=conta.id).count() == 1


def test_reenfileira_conta_ja_processada(db_session):
    """Uma conta cujo último item da fila já concluiu ou falhou pode
    entrar de novo — só o item "pendente" bloqueia duplicidade."""
    conta = _criar_conta(db_session)
    item_antigo = FilaEnriquecimentoConta(tenant_id=TENANT_ID, conta_id=conta.id, status="concluido")
    db_session.add(item_antigo)
    db_session.commit()

    resultado = conta_service.enfileirar_enriquecimento_em_lote(db_session, TENANT_ID, [conta.id])

    assert resultado == {"contas_enfileiradas": 1}
    assert db_session.query(FilaEnriquecimentoConta).filter_by(conta_id=conta.id, status="pendente").count() == 1
