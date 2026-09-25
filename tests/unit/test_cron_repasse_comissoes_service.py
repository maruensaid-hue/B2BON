from app.models.comissao_representante import ComissaoRepresentante
from app.models.representante import Representante
from app.models.tenant import Tenant
from app.providers.channels.email.stub import StubEmailProvider
from app.services import cron_repasse_comissoes_service
from tests.fakes import FakePayoutProvider

TENANT_ID = "tenant-teste"


def _representante(db_session, **overrides) -> Representante:
    dados = {
        "nome": "Fulano Vendedor",
        "email": "fulano@vendedor.com.br",
        "chave_pix": "fulano@pix.com.br",
        "percentual_comissao": 0.1,
    }
    dados.update(overrides)
    representante = Representante(**dados)
    db_session.add(representante)
    db_session.commit()
    return representante


def _tenant(db_session, tenant_id: str = TENANT_ID) -> Tenant:
    tenant = db_session.query(Tenant).filter_by(id=tenant_id).one_or_none()
    if tenant is None:
        tenant = Tenant(id=tenant_id, razao_social="Empresa Teste")
        db_session.add(tenant)
        db_session.commit()
    return tenant


def _comissao(db_session, representante_id: int, valor: float, pagamento_licenca_id: int = 1) -> ComissaoRepresentante:
    comissao = ComissaoRepresentante(
        representante_id=representante_id, tenant_id=TENANT_ID, pagamento_licenca_id=pagamento_licenca_id,
        valor_comissao=valor, status="calculada",
    )
    db_session.add(comissao)
    db_session.commit()
    return comissao


def test_repassar_pendentes_marca_paga_em_sucesso(db_session):
    _tenant(db_session)
    representante = _representante(db_session)
    comissao = _comissao(db_session, representante.id, 50.0)
    payout = FakePayoutProvider()
    email = StubEmailProvider()

    resultado = cron_repasse_comissoes_service.repassar_pendentes(db_session, payout, email)

    assert resultado == {"repassadas": 1, "falhas": 0, "total_processado": 1}
    db_session.refresh(comissao)
    assert comissao.status == "paga"
    assert comissao.pago_em is not None
    assert len(payout.envios) == 1
    assert payout.envios[0]["chave_pix"] == "fulano@pix.com.br"
    assert payout.envios[0]["valor"] == 50.0


def test_repassar_pendentes_marca_falhou_e_nao_reprocessa(db_session):
    _tenant(db_session)
    representante = _representante(db_session)
    comissao = _comissao(db_session, representante.id, 50.0)
    payout = FakePayoutProvider()
    payout.falhar_proximos = 1
    email = StubEmailProvider()

    resultado = cron_repasse_comissoes_service.repassar_pendentes(db_session, payout, email)
    assert resultado == {"repassadas": 0, "falhas": 1, "total_processado": 1}
    db_session.refresh(comissao)
    assert comissao.status == "falhou"
    assert comissao.motivo_falha == "falha simulada"

    # Uma comissão "falhou" não é reprocessada sozinha na próxima rodada.
    resultado_2 = cron_repasse_comissoes_service.repassar_pendentes(db_session, payout, email)
    assert resultado_2 == {"repassadas": 0, "falhas": 0, "total_processado": 0}
    assert len(payout.envios) == 1


def test_repassar_pendentes_ignora_valor_abaixo_do_minimo(db_session):
    _tenant(db_session)
    representante = _representante(db_session)
    _comissao(db_session, representante.id, 5.0)
    payout = FakePayoutProvider()
    email = StubEmailProvider()

    resultado = cron_repasse_comissoes_service.repassar_pendentes(db_session, payout, email)

    assert resultado == {"repassadas": 0, "falhas": 0, "total_processado": 0}
    assert payout.envios == []


def test_repassar_pendentes_notifica_representante_por_email(db_session):
    _tenant(db_session)
    representante = _representante(db_session)
    _comissao(db_session, representante.id, 50.0)
    payout = FakePayoutProvider()
    email = StubEmailProvider()

    cron_repasse_comissoes_service.repassar_pendentes(db_session, payout, email)

    assert len(email.envios) == 1
    assert email.envios[0]["destinatario"] == "fulano@vendedor.com.br"
