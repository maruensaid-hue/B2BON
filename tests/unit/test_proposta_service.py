import pytest

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.services import crm_service, proposta_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

TENANT_ID = "tenant-teste"


def _criar_conta(db_session, **overrides) -> Conta:
    icp = ICP(
        tenant_id=TENANT_ID, grupo_id="grupo-1", nome="ICP", segmento="Tecnologia", porte="PEQUENO",
        regiao="SP", ativo=True,
    )
    db_session.add(icp)
    db_session.flush()
    dados = {"tenant_id": TENANT_ID, "icp_id": icp.id, "nome": "Conta Teste", "status": "prospectada"}
    dados.update(overrides)
    conta = Conta(**dados)
    db_session.add(conta)
    db_session.commit()
    return conta


def _criar_decisor(db_session, conta: Conta, nome: str = "Decisor Teste") -> Decisor:
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome=nome)
    db_session.add(decisor)
    db_session.commit()
    return decisor


def _criar_negocio(db_session):
    conta = _criar_conta(db_session)
    decisor = _criar_decisor(db_session, conta)
    return crm_service.criar_negocio(db_session, TENANT_ID, "1", conta.id, decisor.id, "Negócio Teste", valor=1000.0)


def test_anexar_primeira_versao(db_session):
    negocio = _criar_negocio(db_session)

    proposta = proposta_service.anexar(
        db_session, TENANT_ID, "1", negocio.id, "proposta.pdf", "application/pdf", b"conteudo-pdf"
    )

    assert proposta.versao == 1
    assert proposta.tamanho_bytes == len(b"conteudo-pdf")
    assert proposta.enviada_por_usuario_id == 1
    assert proposta.gerada_automaticamente is False


def test_anexar_incrementa_versao(db_session):
    negocio = _criar_negocio(db_session)
    proposta_service.anexar(db_session, TENANT_ID, "1", negocio.id, "v1.pdf", "application/pdf", b"a")

    segunda = proposta_service.anexar(db_session, TENANT_ID, "1", negocio.id, "v2.pdf", "application/pdf", b"bb")

    assert segunda.versao == 2


def test_anexar_gerada_automaticamente_nao_tem_usuario(db_session):
    negocio = _criar_negocio(db_session)

    proposta = proposta_service.anexar(
        db_session, TENANT_ID, "1", negocio.id, "auto.pdf", "application/pdf", b"x", gerada_automaticamente=True
    )

    assert proposta.gerada_automaticamente is True
    assert proposta.enviada_por_usuario_id is None


def test_anexar_recusa_mime_invalido(db_session):
    negocio = _criar_negocio(db_session)

    with pytest.raises(ValidacaoFalhou):
        proposta_service.anexar(db_session, TENANT_ID, "1", negocio.id, "malware.exe", "application/x-msdownload", b"x")


def test_anexar_recusa_tamanho_excessivo(db_session):
    negocio = _criar_negocio(db_session)
    conteudo_grande = b"a" * (proposta_service.TAMANHO_MAXIMO_BYTES + 1)

    with pytest.raises(ValidacaoFalhou):
        proposta_service.anexar(db_session, TENANT_ID, "1", negocio.id, "grande.pdf", "application/pdf", conteudo_grande)


def test_anexar_negocio_inexistente_falha(db_session):
    with pytest.raises(NaoEncontrado):
        proposta_service.anexar(db_session, TENANT_ID, "1", 99999, "proposta.pdf", "application/pdf", b"x")


def test_listar_ordena_versao_mais_nova_primeiro(db_session):
    negocio = _criar_negocio(db_session)
    proposta_service.anexar(db_session, TENANT_ID, "1", negocio.id, "v1.pdf", "application/pdf", b"a")
    proposta_service.anexar(db_session, TENANT_ID, "1", negocio.id, "v2.pdf", "application/pdf", b"b")

    listagem = proposta_service.listar(db_session, TENANT_ID, negocio.id)

    assert [p.versao for p in listagem] == [2, 1]


def test_obter_proposta_inexistente_falha(db_session):
    negocio = _criar_negocio(db_session)
    with pytest.raises(NaoEncontrado):
        proposta_service.obter(db_session, TENANT_ID, negocio.id, 99999)
