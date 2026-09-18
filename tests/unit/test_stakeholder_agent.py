from app.models.conta import Conta
from app.models.decisor import Decisor
from app.services import conta_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"


def test_sugerir_papel_economic_buyer(db_session):
    assert conta_service.sugerir_papel_comite_compra("Diretor Financeiro") == "ECONOMIC_BUYER"
    assert conta_service.sugerir_papel_comite_compra("CEO") == "ECONOMIC_BUYER"


def test_sugerir_papel_procurement(db_session):
    assert conta_service.sugerir_papel_comite_compra("Gerente de Compras") == "PROCUREMENT"


def test_sugerir_papel_legal(db_session):
    assert conta_service.sugerir_papel_comite_compra("Advogada Sênior") == "LEGAL"


def test_sugerir_papel_technical_evaluator(db_session):
    assert conta_service.sugerir_papel_comite_compra("Coordenador de TI") == "TECHNICAL_EVALUATOR"


def test_sugerir_papel_unknown_sem_cargo(db_session):
    assert conta_service.sugerir_papel_comite_compra(None) == "UNKNOWN"
    assert conta_service.sugerir_papel_comite_compra("Analista de Marketing") == "UNKNOWN"


def _criar_decisor(db_session, tenant_id, **overrides) -> tuple[Conta, Decisor]:
    conta = Conta(tenant_id=tenant_id, nome="Conta Teste", status="priorizada")
    db_session.add(conta)
    db_session.flush()
    dados = {"tenant_id": tenant_id, "conta_id": conta.id, "nome": "Decisor Teste"}
    dados.update(overrides)
    decisor = Decisor(**dados)
    db_session.add(decisor)
    db_session.commit()
    return conta, decisor


def test_confirmar_papel_decisor(db_session):
    conta, decisor = _criar_decisor(db_session, TENANT_A)

    atualizado = conta_service.confirmar_papel_decisor(db_session, TENANT_A, None, conta.id, decisor.id, "CHAMPION")

    assert atualizado.papel_confirmado == "CHAMPION"


def test_confirmar_papel_invalido_levanta_erro(db_session):
    conta, decisor = _criar_decisor(db_session, TENANT_A)

    try:
        conta_service.confirmar_papel_decisor(db_session, TENANT_A, None, conta.id, decisor.id, "INVALIDO")
        assert False, "deveria ter levantado ValidacaoFalhou"
    except ValidacaoFalhou:
        pass


def test_confirmar_papel_decisor_de_outro_tenant_levanta_erro(db_session):
    conta, decisor = _criar_decisor(db_session, TENANT_A)

    try:
        conta_service.confirmar_papel_decisor(db_session, TENANT_B, None, conta.id, decisor.id, "CHAMPION")
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_contexto_decisores_texto_sem_decisor_retorna_mensagem_padrao(db_session):
    """Fase 0.5-A, hardening: Context Engine mínimo — mesmo bloco que
    `gerar_meeting_brief`/`sugerir_estrategia_venda` reimplementavam."""
    conta = Conta(tenant_id=TENANT_A, nome="Conta Teste", status="priorizada")
    db_session.add(conta)
    db_session.commit()

    texto = conta_service.contexto_decisores_texto(db_session, TENANT_A, conta.id)

    assert texto == "Nenhum decisor cadastrado ainda."


def test_contexto_decisores_texto_cita_papel_sugerido_quando_nao_confirmado(db_session):
    conta, decisor = _criar_decisor(db_session, TENANT_A, cargo="Diretor Financeiro")

    texto = conta_service.contexto_decisores_texto(db_session, TENANT_A, conta.id)

    assert "ECONOMIC_BUYER" in texto
    assert "não confirmado" in texto


def test_contexto_decisores_texto_cita_papel_confirmado(db_session):
    conta, decisor = _criar_decisor(db_session, TENANT_A, cargo="Diretor Financeiro")
    conta_service.confirmar_papel_decisor(db_session, TENANT_A, None, conta.id, decisor.id, "DECISION_MAKER")

    texto = conta_service.contexto_decisores_texto(db_session, TENANT_A, conta.id)

    assert "DECISION_MAKER" in texto
    assert "não confirmado" not in texto
