"""E-mail sem assunto não é aprovado nem enviado (12/11/2026: a IA respondeu fora do formato ASSUNTO/CORPO e e-mails sem assunto
chegaram à fila; alguns foram aprovados por engano)."""

import pytest

from app.contexts.predator import portao_envio
from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import aprovacao_service
from app.services.cadencia_service import separar_assunto_corpo
from app.services.errors import RegraNegocioViolada

TENANT_ID = "tenant-teste"
PLAN_LIMITS = StubPlanLimitsProvider()


@pytest.mark.parametrize(
    ("texto", "assunto", "corpo"),
    [
        ("ASSUNTO: Palestra em dezembro\nCORPO:\nOlá, Ana.", "Palestra em dezembro", "Olá, Ana."),
        ("Assunto: Palestra em dezembro\n\nOlá, Ana.", "Palestra em dezembro", "Olá, Ana."),
        ("**Toque 2 — Canal: E-mail**\n---\n**Assunto:** Ana, sobre a convenção\n---\nOlá, Ana.", "Ana, sobre a convenção", "---\nOlá, Ana."),
        ("assunto : Datas de dezembro\ncorpo: Olá, Ana.", "Datas de dezembro", "Olá, Ana."),
    ],
)
def test_separar_assunto_corpo_aceita_variacoes_de_formato(texto, assunto, corpo):
    assert separar_assunto_corpo(texto) == (assunto, corpo)


def test_separar_assunto_corpo_sem_linha_de_assunto():
    assert separar_assunto_corpo("Olá, Ana. Tudo bem?") == (None, "Olá, Ana. Tudo bem?")


def test_portao_aponta_email_sem_assunto_como_grave():
    graves = {p.codigo for p in portao_envio.verificar("Olá, Ana.", None, "email", set()) if p.grave}
    assert "assunto_vazio" in graves
    assert "assunto_vazio" not in {p.codigo for p in portao_envio.verificar("Olá, Ana.", "Oi", "email", set())}
    assert "assunto_vazio" not in {p.codigo for p in portao_envio.verificar("Olá, Ana.", None, "linkedin", set())}


@pytest.fixture()
def cadencia_e_decisor(db_session):
    conta = Conta(tenant_id=TENANT_ID, nome="Conta Teste", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    cadencia = Cadencia(tenant_id=TENANT_ID, conta_id=conta.id, nome="Cadência", status="rascunho")
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Ana Souza")
    db_session.add_all([cadencia, decisor])
    db_session.commit()
    return cadencia, decisor


def test_aprovar_recusa_email_sem_assunto(db_session, cadencia_e_decisor):
    cadencia, decisor = cadencia_e_decisor
    aprovacao_service.criar_proposta(db_session, TENANT_ID, cadencia.id, decisor.id, "email", "t", "Olá", PLAN_LIMITS)
    aprovacao = aprovacao_service.listar_fila(db_session, TENANT_ID)[0]
    with pytest.raises(RegraNegocioViolada, match="sem assunto"):
        aprovacao_service.aprovar(db_session, TENANT_ID, None, aprovacao["aprovacao_id"])
    with pytest.raises(RegraNegocioViolada, match="sem assunto"):
        aprovacao_service.aprovar_lote(db_session, TENANT_ID, None, [aprovacao["aprovacao_id"]])


def test_aprovar_aceita_email_com_assunto_e_linkedin_sem_assunto(db_session, cadencia_e_decisor):
    cadencia, decisor = cadencia_e_decisor
    aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", "t", "Olá", PLAN_LIMITS, assunto="Datas de dezembro"
    )
    aprovacao_service.criar_proposta(db_session, TENANT_ID, cadencia.id, decisor.id, "linkedin", "t", "Olá", PLAN_LIMITS)
    for item in aprovacao_service.listar_fila(db_session, TENANT_ID):
        assert aprovacao_service.aprovar(db_session, TENANT_ID, None, item["aprovacao_id"]).status == "aprovado"
