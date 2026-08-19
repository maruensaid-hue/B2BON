from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.models.conta import Conta
from app.models.convite_vitrine import ConviteVitrine
from app.models.decisor import Decisor
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.payment.stub import StubPaymentProvider
from app.services import tenant_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou
from tests.fakes import (
    FakeAccountDataProvider,
    FakeContactEnrichmentProvider,
    FakeEmailProvider,
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


def test_gerar_convite_vitrine_com_email_enviado_com_sucesso(db_session):
    email_provider = FakeEmailProvider()

    convite = tenant_service.gerar_convite_vitrine(
        db_session, TENANT_ID_ORIGEM, None, validade_horas=24,
        email_destinatario="parceiro@empresa.com.br", email_provider=email_provider,
    )

    assert convite.email_enviado is True
    assert len(email_provider.envios) == 1
    assert email_provider.envios[0]["destinatario"] == "parceiro@empresa.com.br"


def test_gerar_convite_vitrine_com_falha_no_envio_de_email(db_session):
    """Raio-X de produção real: StubEmailProvider sempre reportava sucesso
    mesmo sem enviar nada de verdade — o convite parecia enviado quando
    não saía nada. `email_enviado` precisa refletir o resultado real."""
    email_provider = FakeEmailProvider()
    email_provider.falhar_proximos = 1

    convite = tenant_service.gerar_convite_vitrine(
        db_session, TENANT_ID_ORIGEM, None, validade_horas=24,
        email_destinatario="parceiro@empresa.com.br", email_provider=email_provider,
    )

    assert convite.email_enviado is False


def test_gerar_convite_vitrine_sem_email_nao_seta_email_enviado(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)

    assert convite.email_enviado is None


def test_reativar_convite_vitrine_revogado_volta_a_disponivel(db_session):
    """Pedido do usuário: revogar por engano ou mudar de ideia não pode
    obrigar a gerar um convite novo pra mesma empresa."""
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    tenant_service.revogar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, convite.codigo)
    plano = _plano(db_session)

    reativado = tenant_service.reativar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, convite.codigo)

    assert reativado.status == "disponivel"
    usuario, _ = tenant_service.criar_tenant_vitrine(
        db_session, convite.codigo, "Empresa Reaproveitada", "Admin", "reaproveitado@convidada.com.br",
        "senha123", True, plano.id, StubPaymentProvider(), *_deps_enriquecimento(),
    )
    assert usuario.email == "reaproveitado@convidada.com.br"


def test_reativar_convite_vitrine_disponivel_falha(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)

    with pytest.raises(RegraNegocioViolada):
        tenant_service.reativar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, convite.codigo)


def test_excluir_convite_vitrine_revogado(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    tenant_service.revogar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, convite.codigo)

    tenant_service.excluir_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, convite.codigo)

    assert db_session.query(ConviteVitrine).filter_by(codigo=convite.codigo).one_or_none() is None


def test_excluir_convite_vitrine_disponivel_falha(db_session):
    """Nunca apagar um convite que alguém ainda possa usar."""
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)

    with pytest.raises(RegraNegocioViolada):
        tenant_service.excluir_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, convite.codigo)


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


# --- Hierarquia de tenants (raio-X: fundação da API de provisionamento) ---


def _criar_tenant_inicial(db_session, tenant_id: str, email: str, **overrides) -> Usuario:
    plano = _plano(db_session)
    kwargs = {
        "tenant_id": tenant_id,
        "razao_social": f"Empresa {tenant_id}",
        "plano_id": plano.id,
        "nome_admin": "Admin",
        "email_admin": email,
        "senha_admin": "senha123",
    }
    kwargs.update(overrides)
    return tenant_service.criar_tenant_inicial(db_session, **kwargs)


def test_criar_tenant_inicial_default_preserva_bootstrap_super_admin(db_session):
    """scripts/bootstrap_tenant.py não passa `papel_primeiro_usuario` —
    o default precisa continuar criando um super_admin de verdade."""
    usuario = _criar_tenant_inicial(db_session, "cyberfort-boot", "boot@cyberfort.com.br")

    assert usuario.papel == "super_admin"
    tenant = db_session.query(Tenant).filter_by(id="cyberfort-boot").one()
    assert tenant.tipo == "cliente"
    assert tenant.tenant_pai_id is None
    assert tenant.modo_cobranca == "direta"


def test_criar_tenant_inicial_via_http_nunca_cria_super_admin(db_session):
    """POST /admin/tenants sempre passa papel_primeiro_usuario="admin" —
    sem isso, Distribuidor/Revendedor conseguiria mintar acesso cross-*toda*
    a plataforma ao criar um tenant novo."""
    usuario = _criar_tenant_inicial(
        db_session, "empresa-via-http", "admin@empresahttp.com.br", papel_primeiro_usuario="admin"
    )

    assert usuario.papel == "admin"


def test_criar_tenant_inicial_cadeia_distribuidor_revendedor_cliente(db_session):
    distribuidor = _criar_tenant_inicial(
        db_session, "distribuidora-a", "dist@a.com.br", tipo="distribuidor", papel_primeiro_usuario="admin"
    )
    revendedor = _criar_tenant_inicial(
        db_session, "revenda-a1", "rev@a1.com.br", tipo="revendedor",
        tenant_pai_id=distribuidor.tenant_id, papel_primeiro_usuario="admin",
    )
    cliente = _criar_tenant_inicial(
        db_session, "cliente-a1x", "cli@a1x.com.br", tipo="cliente",
        tenant_pai_id=revendedor.tenant_id, papel_primeiro_usuario="admin",
    )

    assert db_session.query(Tenant).filter_by(id="distribuidora-a").one().tenant_pai_id is None
    assert db_session.query(Tenant).filter_by(id="revenda-a1").one().tenant_pai_id == "distribuidora-a"
    assert db_session.query(Tenant).filter_by(id="cliente-a1x").one().tenant_pai_id == "revenda-a1"
    assert cliente.papel == "admin"


def test_criar_tenant_inicial_revendedor_sem_pai_distribuidor_falha(db_session):
    with pytest.raises(RegraNegocioViolada):
        _criar_tenant_inicial(db_session, "revenda-orfa", "orfa@revenda.com.br", tipo="revendedor")


def test_criar_tenant_inicial_revendedor_com_pai_do_tipo_errado_falha(db_session):
    cliente = _criar_tenant_inicial(db_session, "cliente-base", "base@cliente.com.br")

    with pytest.raises(RegraNegocioViolada):
        _criar_tenant_inicial(
            db_session, "revenda-com-pai-errado", "errado@revenda.com.br",
            tipo="revendedor", tenant_pai_id=cliente.tenant_id,
        )


def test_criar_tenant_inicial_distribuidor_com_pai_falha(db_session):
    outro = _criar_tenant_inicial(db_session, "outro-distribuidor", "outro@distribuidor.com.br", tipo="distribuidor")

    with pytest.raises(RegraNegocioViolada):
        _criar_tenant_inicial(
            db_session, "distribuidor-com-pai", "compai@distribuidor.com.br",
            tipo="distribuidor", tenant_pai_id=outro.tenant_id,
        )


def test_criar_tenant_inicial_tipo_invalido_falha(db_session):
    with pytest.raises(ValidacaoFalhou):
        _criar_tenant_inicial(db_session, "tipo-invalido", "x@invalido.com.br", tipo="franqueado")


def test_listar_tenants_visiveis_super_admin_ve_tudo(db_session):
    super_admin_usuario = _criar_tenant_inicial(db_session, "raiz-super", "raiz@super.com.br")
    _criar_tenant_inicial(db_session, "outro-qualquer", "outro@qualquer.com.br")

    visiveis = tenant_service.listar_tenants_visiveis(db_session, super_admin_usuario)

    ids = {t.id for t in visiveis}
    assert {"raiz-super", "outro-qualquer"}.issubset(ids)


def test_listar_tenants_visiveis_distribuidor_ve_so_a_propria_subarvore(db_session):
    distribuidor_a = _criar_tenant_inicial(
        db_session, "distribuidora-b", "dist@b.com.br", tipo="distribuidor", papel_primeiro_usuario="admin"
    )
    revendedor_a = _criar_tenant_inicial(
        db_session, "revenda-b1", "rev@b1.com.br", tipo="revendedor",
        tenant_pai_id=distribuidor_a.tenant_id, papel_primeiro_usuario="admin",
    )
    _criar_tenant_inicial(
        db_session, "cliente-b1x", "cli@b1x.com.br", tipo="cliente",
        tenant_pai_id=revendedor_a.tenant_id, papel_primeiro_usuario="admin",
    )
    # Árvore irmã — distribuidor_a não deveria enxergar nada aqui dentro.
    distribuidor_c = _criar_tenant_inicial(
        db_session, "distribuidora-c", "dist@c.com.br", tipo="distribuidor", papel_primeiro_usuario="admin"
    )
    _criar_tenant_inicial(
        db_session, "revenda-c1", "rev@c1.com.br", tipo="revendedor",
        tenant_pai_id=distribuidor_c.tenant_id, papel_primeiro_usuario="admin",
    )

    visiveis = tenant_service.listar_tenants_visiveis(db_session, distribuidor_a)

    ids = {t.id for t in visiveis}
    assert ids == {"distribuidora-b", "revenda-b1", "cliente-b1x"}


def test_suspender_licencas_vencidas_suspende_so_direta_e_vencida(db_session):
    plano = _plano(db_session)
    tenant_vencido = Tenant(id="tenant-vencido", razao_social="Vencido", modo_cobranca="direta")
    tenant_consolidado_vencido = Tenant(
        id="tenant-consolidado-vencido", razao_social="Consolidado Vencido",
        tenant_pai_id="tenant-vencido", modo_cobranca="consolidada",
    )
    tenant_em_dia = Tenant(id="tenant-em-dia", razao_social="Em dia", modo_cobranca="direta")
    db_session.add_all([tenant_vencido, tenant_consolidado_vencido, tenant_em_dia])
    db_session.flush()

    ontem = datetime.now(UTC) - timedelta(days=1)
    amanha = datetime.now(UTC) + timedelta(days=1)
    db_session.add_all([
        Licenca(tenant_id="tenant-vencido", plano_id=plano.id, status="ativa", data_expiracao=ontem),
        Licenca(tenant_id="tenant-consolidado-vencido", plano_id=plano.id, status="ativa", data_expiracao=ontem),
        Licenca(tenant_id="tenant-em-dia", plano_id=plano.id, status="ativa", data_expiracao=amanha),
    ])
    db_session.commit()

    suspensos = tenant_service.suspender_licencas_vencidas(db_session)

    assert suspensos == ["tenant-vencido"]
    assert db_session.query(Licenca).filter_by(tenant_id="tenant-vencido").one().status == "suspensa"
    assert db_session.query(Licenca).filter_by(tenant_id="tenant-consolidado-vencido").one().status == "ativa"
    assert db_session.query(Licenca).filter_by(tenant_id="tenant-em-dia").one().status == "ativa"
