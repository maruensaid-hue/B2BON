from app.models.aprovacao import Aprovacao
from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.oferta import Oferta
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import aprovacao_service, regra_aprendida_service, resposta_service

TENANT_ID = "tenant-performance-ia"


def _criar_cadencia_e_decisor(db_session) -> tuple[Decisor, Cadencia]:
    icp = ICP(tenant_id=TENANT_ID, grupo_id="grupo-1", nome="ICP", segmento="Tecnologia", porte="PEQUENO", regiao="SP")
    db_session.add(icp)
    oferta = Oferta(tenant_id=TENANT_ID, nome="Oferta", descricao="Descrição")
    db_session.add(oferta)
    db_session.commit()
    conta = Conta(tenant_id=TENANT_ID, nome="Conta Teste", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste", email="d@teste.com")
    db_session.add(decisor)
    cadencia = Cadencia(
        tenant_id=TENANT_ID, nome="Cadência", status="ativa", canais=["email"], icp_id=icp.id, oferta_id=oferta.id,
    )
    db_session.add(cadencia)
    db_session.flush()
    return decisor, cadencia


def _criar_proposta(db_session, decisor: Decisor, cadencia: Cadencia, texto: str = "Texto original"):
    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", None, texto, StubPlanLimitsProvider(),
    )
    aprovacao = db_session.query(Aprovacao).filter_by(mensagem_id=mensagem.id).one()
    return mensagem, aprovacao


def test_calcular_performance_ia_sem_dados_retorna_zero_sem_dividir_por_zero(db_session):
    resultado = regra_aprendida_service.calcular_performance_ia(db_session, TENANT_ID)

    assert resultado["total_propostas"] == 0
    assert resultado["taxa_aceitacao"] == 0.0
    assert resultado["taxa_edicao"] == 0.0
    assert resultado["taxa_rejeicao"] == 0.0
    assert resultado["taxa_resposta"] == 0.0


def test_calcular_performance_ia_aprovada_sem_edicao_conta_como_aceita(db_session):
    decisor, cadencia = _criar_cadencia_e_decisor(db_session)
    mensagem, aprovacao = _criar_proposta(db_session, decisor, cadencia)
    aprovacao_service.aprovar(db_session, TENANT_ID, "usuario-1", aprovacao.id)

    resultado = regra_aprendida_service.calcular_performance_ia(db_session, TENANT_ID)

    assert resultado["total_propostas"] == 1
    assert resultado["mensagens_editadas"] == 0
    assert resultado["taxa_aceitacao"] == 1.0
    assert resultado["taxa_edicao"] == 0.0


def test_calcular_performance_ia_mensagem_editada_reduz_taxa_aceitacao(db_session):
    decisor, cadencia = _criar_cadencia_e_decisor(db_session)
    mensagem, aprovacao = _criar_proposta(db_session, decisor, cadencia)
    aprovacao_service.editar_mensagem(db_session, TENANT_ID, "usuario-1", aprovacao.id, "Texto editado")

    resultado = regra_aprendida_service.calcular_performance_ia(db_session, TENANT_ID)

    assert resultado["mensagens_editadas"] == 1
    assert resultado["taxa_edicao"] == 1.0
    assert resultado["taxa_aceitacao"] == 0.0


def test_calcular_performance_ia_rejeicao_conta_taxa_rejeicao(db_session):
    decisor, cadencia = _criar_cadencia_e_decisor(db_session)
    mensagem, aprovacao = _criar_proposta(db_session, decisor, cadencia)
    aprovacao_service.rejeitar(db_session, TENANT_ID, "usuario-1", aprovacao.id, "Tom agressivo demais")

    resultado = regra_aprendida_service.calcular_performance_ia(db_session, TENANT_ID)

    assert resultado["aprovacoes_rejeitadas"] == 1
    assert resultado["taxa_rejeicao"] == 1.0


def test_calcular_performance_ia_resposta_detectada_conta_taxa_resposta(db_session):
    decisor, cadencia = _criar_cadencia_e_decisor(db_session)
    mensagem, aprovacao = _criar_proposta(db_session, decisor, cadencia)
    aprovacao_service.aprovar(db_session, TENANT_ID, "usuario-1", aprovacao.id)
    aprovacao_service.marcar_enviada(db_session, TENANT_ID, mensagem.id)
    resposta_service.marcar_resposta(db_session, TENANT_ID, decisor.id)

    resultado = regra_aprendida_service.calcular_performance_ia(db_session, TENANT_ID)

    assert resultado["mensagens_enviadas"] == 1
    assert resultado["respostas_detectadas"] == 1
    assert resultado["taxa_resposta"] == 1.0


def test_calcular_performance_ia_isolamento_tenant(db_session):
    decisor, cadencia = _criar_cadencia_e_decisor(db_session)
    _criar_proposta(db_session, decisor, cadencia)

    resultado = regra_aprendida_service.calcular_performance_ia(db_session, "tenant-outro")

    assert resultado["total_propostas"] == 0
