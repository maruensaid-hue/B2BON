import pytest

from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import aprovacao_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

TENANT_ID = "tenant-teste"
PLAN_LIMITS = StubPlanLimitsProvider()


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
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", "template-1", "Olá {{nome}}", PLAN_LIMITS
    )

    with pytest.raises(RegraNegocioViolada):
        aprovacao_service.marcar_enviada(db_session, TENANT_ID, mensagem.id)


def test_mensagem_e_enviada_apos_aprovacao(db_session, decisor_de_teste):
    decisor, cadencia = decisor_de_teste
    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", "template-1", "Olá {{nome}}", PLAN_LIMITS
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
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", "template-1", "Olá {{nome}}", PLAN_LIMITS
    )
    item_fila = aprovacao_service.listar_fila(db_session, TENANT_ID)[0]

    editada = aprovacao_service.editar_mensagem(
        db_session, TENANT_ID, "editor-1", item_fila["aprovacao_id"], "Olá {{nome}}, tudo bem na {{empresa}}?"
    )

    assert editada.conteudo == "Olá {{nome}}, tudo bem na {{empresa}}?"


def test_editar_mensagem_rejeita_variavel_invalida(db_session, decisor_de_teste):
    decisor, cadencia = decisor_de_teste
    aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", "template-1", "Olá {{nome}}", PLAN_LIMITS
    )
    item_fila = aprovacao_service.listar_fila(db_session, TENANT_ID)[0]

    with pytest.raises(ValidacaoFalhou):
        aprovacao_service.editar_mensagem(
            db_session, TENANT_ID, "editor-1", item_fila["aprovacao_id"], "Use o cupom {{codigo_secreto}}"
        )


def test_definir_regra_bloqueada_pelo_plano_recusa(db_session):
    plan_limits_restrito = StubPlanLimitsProvider(recursos_desabilitados={TENANT_ID: {"auto_aprovacao"}})

    with pytest.raises(RegraNegocioViolada):
        aprovacao_service.definir_regra(db_session, TENANT_ID, "1", "tpl-x", True, plan_limits_restrito)


def test_definir_regra_desligar_funciona_mesmo_com_plano_restrito(db_session):
    """Desligar uma regra nunca deveria ser bloqueado — só ligar exige o plano certo."""
    plan_limits_restrito = StubPlanLimitsProvider(recursos_desabilitados={TENANT_ID: {"auto_aprovacao"}})

    regra = aprovacao_service.definir_regra(db_session, TENANT_ID, "1", "tpl-x", False, plan_limits_restrito)

    assert regra.habilitada is False


def test_downgrade_depois_de_regra_ligada_nao_auto_aprova_mais(db_session, decisor_de_teste):
    """Regra criada com o plano permitindo; downgrade depois disso faz a
    regra ser ignorada (mensagem cai na aprovação humana normal), sem
    erro no meio da criação da mensagem."""
    decisor, cadencia = decisor_de_teste
    aprovacao_service.definir_regra(db_session, TENANT_ID, "1", "tpl-auto", True, PLAN_LIMITS)

    plan_limits_apos_downgrade = StubPlanLimitsProvider(recursos_desabilitados={TENANT_ID: {"auto_aprovacao"}})
    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", "tpl-auto", "Olá {{nome}}", plan_limits_apos_downgrade
    )

    aprovacao = aprovacao_service.listar_fila(db_session, TENANT_ID)[0]
    assert aprovacao["status"] == "pendente"
    assert mensagem.status == "aguardando_aprovacao"
