from app.models.atividade import Atividade
from app.models.conta import Conta
from app.models.icp import ICP
from app.models.negocio import Negocio
from app.providers.crm.nucleo import NucleoCrmProvider

TENANT_ID = "tenant-teste"


def _criar_conta(db_session) -> Conta:
    icp = ICP(
        tenant_id=TENANT_ID, grupo_id="grupo-1", nome="ICP", segmento="Tecnologia", porte="PEQUENO",
        regiao="SP", ativo=True,
    )
    db_session.add(icp)
    db_session.flush()
    conta = Conta(tenant_id=TENANT_ID, icp_id=icp.id, nome="Conta Teste", status="prospectada")
    db_session.add(conta)
    db_session.commit()
    return conta


def test_criar_ou_atualizar_oportunidade_e_idempotente(db_session):
    """Onda B: mesma conta não gera dois negócios ao confirmar reunião mais de uma vez."""
    conta = _criar_conta(db_session)
    provider = NucleoCrmProvider(db_session)

    id1 = provider.criar_ou_atualizar_oportunidade(TENANT_ID, conta.id, {"decisor_id": 1})
    id2 = provider.criar_ou_atualizar_oportunidade(TENANT_ID, conta.id, {"decisor_id": 1})

    assert id1 == id2
    assert db_session.query(Negocio).filter_by(tenant_id=TENANT_ID, conta_id=conta.id).count() == 1


def test_criar_oportunidade_registra_atividade_de_sistema(db_session):
    conta = _criar_conta(db_session)
    provider = NucleoCrmProvider(db_session)

    negocio_id = provider.criar_ou_atualizar_oportunidade(TENANT_ID, conta.id, {"decisor_id": 5})

    atividades = db_session.query(Atividade).filter_by(negocio_id=int(negocio_id)).all()
    assert any(a.tipo == "sistema" for a in atividades)


def test_anexar_nota_cria_atividade(db_session):
    conta = _criar_conta(db_session)
    provider = NucleoCrmProvider(db_session)
    negocio_id = provider.criar_ou_atualizar_oportunidade(TENANT_ID, conta.id, {"decisor_id": 1})

    provider.anexar_nota(TENANT_ID, negocio_id, "Dossiê de handoff — texto de teste")

    notas = db_session.query(Atividade).filter_by(negocio_id=int(negocio_id), tipo="nota").all()
    assert len(notas) == 1
    assert "Dossiê" in notas[0].descricao
