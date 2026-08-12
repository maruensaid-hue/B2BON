from datetime import UTC, datetime

import pytest

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.schemas.campanha import DestinatarioAvulsoSchema
from app.services import campanha_service
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou
from tests.fakes import FakeEmailProvider, FakeWhatsAppProvider

TENANT_ID = "tenant-campanhas"


def _criar_decisor(db_session, nome: str, email: str | None = "fulano@teste.com", suprimido: bool = False) -> Decisor:
    conta = Conta(tenant_id=TENANT_ID, icp_id=None, nome=f"Empresa de {nome}", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(
        tenant_id=TENANT_ID,
        conta_id=conta.id,
        nome=nome,
        email=email,
        telefone="11999990000",
        suprimido_em=datetime.now(UTC) if suprimido else None,
    )
    db_session.add(decisor)
    db_session.commit()
    return decisor


def _criar_campanha_email(db_session, canais=None) -> int:
    campanha = campanha_service.criar(
        db_session,
        TENANT_ID,
        None,
        "Campanha Teste",
        "marketing",
        canais or ["email"],
        "Assunto de teste",
        "Corpo de teste",
        None,
    )
    return campanha.id


def test_criar_campanha_email_exige_assunto_e_conteudo(db_session):
    with pytest.raises(ValidacaoFalhou):
        campanha_service.criar(db_session, TENANT_ID, None, "Sem conteúdo", "marketing", ["email"], None, None, None)


def test_criar_campanha_whatsapp_exige_template(db_session):
    with pytest.raises(ValidacaoFalhou):
        campanha_service.criar(db_session, TENANT_ID, None, "Sem template", "vendas", ["whatsapp"], None, None, None)


def test_adicionar_de_decisores_pula_suprimido(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor_ativo = _criar_decisor(db_session, "Ativo")
    decisor_suprimido = _criar_decisor(db_session, "Suprimido", suprimido=True)

    adicionados = campanha_service.adicionar_de_decisores(
        db_session, TENANT_ID, None, campanha_id, [decisor_ativo.id, decisor_suprimido.id]
    )

    assert len(adicionados) == 1
    assert adicionados[0].decisor_id == decisor_ativo.id


def test_adicionar_de_decisores_nao_duplica(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")

    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    segunda_vez = campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])

    assert segunda_vez == []
    assert len(campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)) == 1


def test_adicionar_avulsos_dedupe_por_email(db_session):
    campanha_id = _criar_campanha_email(db_session)
    destinatarios = [
        DestinatarioAvulsoSchema(nome="Ciclano", email="ciclano@teste.com"),
        DestinatarioAvulsoSchema(nome="Ciclano Repetido", email="CICLANO@teste.com"),
        DestinatarioAvulsoSchema(nome="Sem contato", email=None, telefone=None),
    ]

    adicionados = campanha_service.adicionar_avulsos(db_session, TENANT_ID, None, campanha_id, destinatarios)

    assert len(adicionados) == 1
    assert adicionados[0].nome == "Ciclano"


def test_marcar_pronta_exige_destinatario(db_session):
    campanha_id = _criar_campanha_email(db_session)
    with pytest.raises(ValidacaoFalhou):
        campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)


def test_marcar_pronta_com_destinatario_funciona(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])

    campanha = campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    assert campanha.status == "pronta"


def test_excluir_campanha_fora_de_rascunho_falha(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    with pytest.raises(RegraNegocioViolada):
        campanha_service.excluir(db_session, TENANT_ID, None, campanha_id)


def test_processar_pendentes_envia_email_e_marca_concluida(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano", email="fulano@teste.com")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    fake_email = FakeEmailProvider()
    fake_whatsapp = FakeWhatsAppProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, fake_whatsapp)

    assert resultado == {"enviadas": 1, "falhas": 0}
    assert len(fake_email.envios) == 1
    assert fake_email.envios[0]["destinatario"] == "fulano@teste.com"

    campanha = campanha_service.obter(db_session, TENANT_ID, campanha_id)
    assert campanha.status == "concluida"
    destinatarios = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)
    assert destinatarios[0].status == "enviado"


def test_processar_pendentes_whatsapp_usa_template(db_session):
    campanha = campanha_service.criar(
        db_session, TENANT_ID, None, "Campanha WhatsApp", "vendas", ["whatsapp"], None, None, "prospeccao_inicial"
    )
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha.id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha.id)

    fake_email = FakeEmailProvider()
    fake_whatsapp = FakeWhatsAppProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, fake_whatsapp)

    assert resultado == {"enviadas": 1, "falhas": 0}
    assert fake_whatsapp.envios == [{"tipo": "template", "telefone": "11999990000", "template_id": "prospeccao_inicial"}]


def test_processar_pendentes_registra_falha(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    fake_email = FakeEmailProvider()
    fake_email.falhar_proximos = 1
    fake_whatsapp = FakeWhatsAppProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, fake_whatsapp)

    assert resultado == {"enviadas": 0, "falhas": 1}
    destinatarios = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)
    assert destinatarios[0].status == "falhou"
    assert destinatarios[0].motivo_falha


def test_optout_por_token_suprime_destinatario_e_decisor(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")
    destinatarios = campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    destinatario_id = destinatarios[0].id

    token = campanha_service.gerar_token_optout(TENANT_ID, destinatario_id)
    resultado = campanha_service.processar_optout_por_token(db_session, token)

    assert resultado == {"destinatario_id": destinatario_id, "suprimido": True}
    destinatario_atualizado = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[0]
    assert destinatario_atualizado.status == "optout"
    db_session.refresh(decisor)
    assert decisor.suprimido_em is not None


def test_optout_por_token_invalido_falha(db_session):
    with pytest.raises(ValidacaoFalhou):
        campanha_service.processar_optout_por_token(db_session, "token-invalido")
