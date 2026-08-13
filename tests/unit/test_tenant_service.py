from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.models.conta import Conta
from app.models.convite_vitrine import ConviteVitrine
from app.models.decisor import Decisor
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.providers.payment.stub import StubPaymentProvider
from app.services import tenant_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou
from tests.fakes import (
    FakeAccountDataProvider,
    FakeContactEnrichmentProvider,
    FakeGraphClient,
    FakeLLMProvider,
    FakeWebSearchProvider,
)

TENANT_ID_ORIGEM = "tenant-teste"


def _plano(db_session) -> Plano:
    plano = Plano(nome=f"Plano {db_session.query(Plano).count() + 1}", franquia_contas_mes=500, max_usuarios=20, preco_mensal=499.0)
    db_session.add(plano)
    db_session.commit()
    return plano


def _deps_enriquecimento():
    """Providers Fake, na ordem que `criar_tenant_vitrine` espera depois de
    `payment_provider` — o enriquecimento automático da conta-prospect
    criada junto do tenant é tolerante a falha, mas os testes daqui não
    se importam com esse comportamento, só com o cadastro do tenant."""
    return (
        FakeLLMProvider(),
        lambda dominio: "=== home ===\nConteúdo.",
        FakeWebSearchProvider(),
        FakeAccountDataProvider(),
        FakeContactEnrichmentProvider(),
        FakeGraphClient(),
    )


def test_criar_tenant_vitrine_gera_licenca_pendente_de_pagamento(db_session):
    """Raio-X de produção: cadastro self-service agora exige plano e abre
    uma cobrança — a licença nasce `pendente_pagamento`, não mais ausente
    (comportamento anterior da Onda H), e só vira `ativa` quando o
    webhook do Mercado Pago confirmar."""
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    plano = _plano(db_session)

    usuario, checkout_url = tenant_service.criar_tenant_vitrine(
        db_session,
        convite.codigo,
        "Empresa Convidada Ltda",
        "Admin Convidado",
        "admin@convidada.com.br",
        "senha123",
        True,
        plano.id,
        StubPaymentProvider(),
        *_deps_enriquecimento(),
    )

    assert usuario.papel == "admin"
    assert usuario.tenant_id != TENANT_ID_ORIGEM
    assert usuario.termos_aceitos_em is not None
    assert checkout_url.startswith("https://checkout.stub.local/")
    licenca = db_session.query(Licenca).filter_by(tenant_id=usuario.tenant_id).one()
    assert licenca.status == "pendente_pagamento"
    assert licenca.plano_id == plano.id
    assert db_session.query(Tenant).filter_by(id=usuario.tenant_id).one_or_none() is not None


def test_criar_tenant_vitrine_plano_inexistente_levanta_nao_encontrado(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)

    with pytest.raises(NaoEncontrado):
        tenant_service.criar_tenant_vitrine(
            db_session,
            convite.codigo,
            "Empresa Sem Plano",
            "Admin",
            "sem-plano@convidada.com.br",
            "senha123",
            True,
            999999,
            StubPaymentProvider(),
            *_deps_enriquecimento(),
        )


def test_criar_tenant_vitrine_sem_aceitar_termos_e_bloqueado(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    plano = _plano(db_session)

    with pytest.raises(ValidacaoFalhou):
        tenant_service.criar_tenant_vitrine(
            db_session,
            convite.codigo,
            "Empresa Sem Aceite",
            "Admin",
            "sem-aceite@convidada.com.br",
            "senha123",
            False,
            plano.id,
            StubPaymentProvider(),
            *_deps_enriquecimento(),
        )


def test_criar_tenant_vitrine_gera_slug_a_partir_do_nome(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    plano = _plano(db_session)

    usuario, _ = tenant_service.criar_tenant_vitrine(
        db_session,
        convite.codigo,
        "Clínica Vida Plena & Saúde",
        "Admin",
        "admin2@convidada.com.br",
        "senha123",
        True,
        plano.id,
        StubPaymentProvider(),
        *_deps_enriquecimento(),
    )

    assert usuario.tenant_id.startswith("clinica-vida-plena")


def test_criar_tenant_vitrine_colisao_de_slug_gera_sufixo(db_session):
    convite1 = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    convite2 = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    plano = _plano(db_session)

    usuario1, _ = tenant_service.criar_tenant_vitrine(
        db_session, convite1.codigo, "Mesma Empresa", "Admin 1", "admin3@convidada.com.br", "senha123", True, plano.id, StubPaymentProvider(), *_deps_enriquecimento()
    )
    usuario2, _ = tenant_service.criar_tenant_vitrine(
        db_session, convite2.codigo, "Mesma Empresa", "Admin 2", "admin4@convidada.com.br", "senha123", True, plano.id, StubPaymentProvider(), *_deps_enriquecimento()
    )

    assert usuario1.tenant_id != usuario2.tenant_id


def test_convite_vitrine_usado_duas_vezes_falha(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    plano = _plano(db_session)
    tenant_service.criar_tenant_vitrine(
        db_session, convite.codigo, "Empresa A", "Admin A", "a@convidada.com.br", "senha123", True, plano.id, StubPaymentProvider(), *_deps_enriquecimento()
    )

    with pytest.raises(RegraNegocioViolada):
        tenant_service.criar_tenant_vitrine(
            db_session, convite.codigo, "Empresa B", "Admin B", "b@convidada.com.br", "senha123", True, plano.id, StubPaymentProvider(), *_deps_enriquecimento()
        )


def test_convite_vitrine_revogado_bloqueia_aceite(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    tenant_service.revogar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, convite.codigo)
    plano = _plano(db_session)

    with pytest.raises(RegraNegocioViolada):
        tenant_service.criar_tenant_vitrine(
            db_session, convite.codigo, "Empresa C", "Admin C", "c@convidada.com.br", "senha123", True, plano.id, StubPaymentProvider(), *_deps_enriquecimento()
        )


def test_convite_vitrine_expirado_bloqueia_aceite(db_session):
    convite = ConviteVitrine(
        tenant_id_origem=TENANT_ID_ORIGEM,
        codigo="VITRINEEXPIRADO",
        validade_em=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(convite)
    db_session.commit()
    plano = _plano(db_session)

    with pytest.raises(RegraNegocioViolada):
        tenant_service.criar_tenant_vitrine(
            db_session, "VITRINEEXPIRADO", "Empresa D", "Admin D", "d@convidada.com.br", "senha123", True, plano.id, StubPaymentProvider(), *_deps_enriquecimento()
        )


def test_convite_vitrine_inexistente_levanta_nao_encontrado(db_session):
    plano = _plano(db_session)

    with pytest.raises(NaoEncontrado):
        tenant_service.criar_tenant_vitrine(
            db_session, "CODIGO-QUE-NAO-EXISTE", "Empresa E", "Admin E", "e@convidada.com.br", "senha123", True, plano.id, StubPaymentProvider(), *_deps_enriquecimento()
        )


def test_criar_tenant_vitrine_email_ja_cadastrado_falha(db_session):
    convite1 = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    plano = _plano(db_session)
    tenant_service.criar_tenant_vitrine(
        db_session, convite1.codigo, "Empresa F", "Admin F", "repetido@convidada.com.br", "senha123", True, plano.id, StubPaymentProvider(), *_deps_enriquecimento()
    )

    convite2 = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    with pytest.raises(RegraNegocioViolada):
        tenant_service.criar_tenant_vitrine(
            db_session, convite2.codigo, "Empresa G", "Admin G", "repetido@convidada.com.br", "senha123", True, plano.id, StubPaymentProvider(), *_deps_enriquecimento()
        )


def test_criar_tenant_vitrine_cria_conta_prospect_no_tenant_de_origem(db_session):
    """Pedido do usuário: empresa convidada pela Rede Social vira prospect
    no CRM de quem convidou, não só um tenant novo e isolado."""
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    plano = _plano(db_session)

    tenant_service.criar_tenant_vitrine(
        db_session, convite.codigo, "Empresa Convidada Ltda", "Admin Convidado", "admin-h@convidada.com.br",
        "senha123", True, plano.id, StubPaymentProvider(), *_deps_enriquecimento(), "11222333000181",
    )

    conta = db_session.query(Conta).filter_by(tenant_id=TENANT_ID_ORIGEM, origem="rede_social_convite").one()
    assert conta.nome == "Empresa Convidada Ltda"
    assert conta.cnpj == "11222333000181"
    decisor = db_session.query(Decisor).filter_by(conta_id=conta.id).one()
    assert decisor.nome == "Admin Convidado"
    assert decisor.email == "admin-h@convidada.com.br"


def test_criar_tenant_vitrine_tolera_falha_no_enriquecimento(db_session):
    """O cadastro do tenant não pode travar se o enriquecimento automático
    da conta-prospect falhar (provedor de site fora do ar, por exemplo)."""
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    plano = _plano(db_session)

    def site_fetcher_com_falha(dominio: str) -> str:
        raise httpx.HTTPError("indisponível")

    usuario, checkout_url = tenant_service.criar_tenant_vitrine(
        db_session, convite.codigo, "Empresa Falha Enriquecimento", "Admin", "admin-falha@convidada.com.br",
        "senha123", True, plano.id, StubPaymentProvider(),
        FakeLLMProvider(), site_fetcher_com_falha, FakeWebSearchProvider(), FakeAccountDataProvider(),
        FakeContactEnrichmentProvider(), FakeGraphClient(),
    )

    assert checkout_url.startswith("https://checkout.stub.local/")
    conta = db_session.query(Conta).filter_by(tenant_id=TENANT_ID_ORIGEM, nome="Empresa Falha Enriquecimento").one()
    assert conta.origem == "rede_social_convite"
