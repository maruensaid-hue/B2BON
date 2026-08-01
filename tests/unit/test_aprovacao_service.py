import pytest

from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.services import aprovacao_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

TENANT_ID = "tenant-teste"


@pytest.fixture()
def decisor_de_teste(db_session):
    icp = ICP(
        tenant_id=TENANT_ID,
        grupo_id="grupo-1",
        nome="ICP",
        segmento="Tecnologia",
        porte="PEQUENO",
        regiao="SP",
        ativo=True,
    )
    db_session.add(icp)
    db_session.flush()

    conta = Conta(tenant_id=TENANT_ID, icp_id=icp.id, nome="Conta Teste", status="prospectada")
    db_session.add(conta)
    db_session.flush()

    cadencia = Cadencia(tenant_id=TENANT_ID, conta_id=conta.id, nome="Cadência Teste", status="rascunho")
    db_session.add(cadencia)
    db_session.flush()

    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste")
    db_session.add(decisor)
    db_session.commit()

    return decisor, cadencia


def test_mensagem_nao_e_enviada_sem_aprovacao(db_session, decisor_de_teste):
    """E4-H1: nenhuma mensagem é enviada sem estado 'aprovado'."""
    decisor, cadencia = decisor_de_teste
    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", "template-1", "Olá {{nome}}"
    )

    with pytest.raises(RegraNegocioViolada):
        aprovacao_service.marcar_enviada(db_session, TENANT_ID, mensagem.id)


def test_mensagem_e_enviada_apos_aprovacao(db_session, decisor_de_teste):
    decisor, cadencia = decisor_de_teste
    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", "template-1", "Olá {{nome}}"
    )
    aprovacao = aprovacao_service.listar_fila(db_session, TENANT_ID)[0]
    aprovacao_service.aprovar(db_session, TENANT_ID, "aprovador-1", aprovacao["aprovacao_id"])

    enviada = aprovacao_service.marcar_enviada(db_session, TENANT_ID, mensagem.id)

    assert enviada.status == "enviado"
    assert enviada.enviado_em is not None


def test_marcar_enviada_mensagem_inexistente_levanta_nao_encontrado(db_session):
    with pytest.raises(NaoEncontrado):
        aprovacao_service.marcar_enviada(db_session, TENANT_ID, 9999)


def test_editar_mensagem_preserva_variaveis_validas(db_session, decisor_de_teste):
    decisor, cadencia = decisor_de_teste
    aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", "template-1", "Olá {{nome}}"
    )
    item_fila = aprovacao_service.listar_fila(db_session, TENANT_ID)[0]

    editada = aprovacao_service.editar_mensagem(
        db_session, TENANT_ID, "editor-1", item_fila["aprovacao_id"], "Olá {{nome}}, tudo bem na {{empresa}}?"
    )

    assert editada.conteudo == "Olá {{nome}}, tudo bem na {{empresa}}?"


def test_editar_mensagem_rejeita_variavel_invalida(db_session, decisor_de_teste):
    decisor, cadencia = decisor_de_teste
    aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", "template-1", "Olá {{nome}}"
    )
    item_fila = aprovacao_service.listar_fila(db_session, TENANT_ID)[0]

    with pytest.raises(ValidacaoFalhou):
        aprovacao_service.editar_mensagem(
            db_session, TENANT_ID, "editor-1", item_fila["aprovacao_id"], "Use o cupom {{codigo_secreto}}"
        )
