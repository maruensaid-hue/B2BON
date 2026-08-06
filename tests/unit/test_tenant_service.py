from datetime import UTC, datetime, timedelta

import pytest

from app.models.convite_vitrine import ConviteVitrine
from app.models.licenca import Licenca
from app.models.tenant import Tenant
from app.services import tenant_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

TENANT_ID_ORIGEM = "tenant-teste"


def test_criar_tenant_vitrine_nao_gera_licenca(db_session):
    """Onda H: a ausência de licença é o que restringe a conta só à Rede
    Social — não pode nascer com uma sem querer."""
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)

    usuario = tenant_service.criar_tenant_vitrine(
        db_session,
        convite.codigo,
        "Empresa Convidada Ltda",
        "Admin Convidado",
        "admin@convidada.com.br",
        "senha123",
        aceite_termos=True,
    )

    assert usuario.papel == "admin"
    assert usuario.tenant_id != TENANT_ID_ORIGEM
    assert usuario.termos_aceitos_em is not None
    assert db_session.query(Licenca).filter_by(tenant_id=usuario.tenant_id).one_or_none() is None
    assert db_session.query(Tenant).filter_by(id=usuario.tenant_id).one_or_none() is not None


def test_criar_tenant_vitrine_sem_aceitar_termos_e_bloqueado(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)

    with pytest.raises(ValidacaoFalhou):
        tenant_service.criar_tenant_vitrine(
            db_session,
            convite.codigo,
            "Empresa Sem Aceite",
            "Admin",
            "sem-aceite@convidada.com.br",
            "senha123",
            aceite_termos=False,
        )


def test_criar_tenant_vitrine_gera_slug_a_partir_do_nome(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)

    usuario = tenant_service.criar_tenant_vitrine(
        db_session,
        convite.codigo,
        "Clínica Vida Plena & Saúde",
        "Admin",
        "admin2@convidada.com.br",
        "senha123",
        aceite_termos=True,
    )

    assert usuario.tenant_id.startswith("clinica-vida-plena")


def test_criar_tenant_vitrine_colisao_de_slug_gera_sufixo(db_session):
    convite1 = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    convite2 = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)

    usuario1 = tenant_service.criar_tenant_vitrine(
        db_session, convite1.codigo, "Mesma Empresa", "Admin 1", "admin3@convidada.com.br", "senha123", aceite_termos=True
    )
    usuario2 = tenant_service.criar_tenant_vitrine(
        db_session, convite2.codigo, "Mesma Empresa", "Admin 2", "admin4@convidada.com.br", "senha123", aceite_termos=True
    )

    assert usuario1.tenant_id != usuario2.tenant_id


def test_convite_vitrine_usado_duas_vezes_falha(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    tenant_service.criar_tenant_vitrine(
        db_session, convite.codigo, "Empresa A", "Admin A", "a@convidada.com.br", "senha123", aceite_termos=True
    )

    with pytest.raises(RegraNegocioViolada):
        tenant_service.criar_tenant_vitrine(
            db_session, convite.codigo, "Empresa B", "Admin B", "b@convidada.com.br", "senha123", aceite_termos=True
        )


def test_convite_vitrine_revogado_bloqueia_aceite(db_session):
    convite = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    tenant_service.revogar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, convite.codigo)

    with pytest.raises(RegraNegocioViolada):
        tenant_service.criar_tenant_vitrine(
            db_session, convite.codigo, "Empresa C", "Admin C", "c@convidada.com.br", "senha123", aceite_termos=True
        )


def test_convite_vitrine_expirado_bloqueia_aceite(db_session):
    convite = ConviteVitrine(
        tenant_id_origem=TENANT_ID_ORIGEM,
        codigo="VITRINEEXPIRADO",
        validade_em=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(convite)
    db_session.commit()

    with pytest.raises(RegraNegocioViolada):
        tenant_service.criar_tenant_vitrine(
            db_session, "VITRINEEXPIRADO", "Empresa D", "Admin D", "d@convidada.com.br", "senha123", aceite_termos=True
        )


def test_convite_vitrine_inexistente_levanta_nao_encontrado(db_session):
    with pytest.raises(NaoEncontrado):
        tenant_service.criar_tenant_vitrine(
            db_session, "CODIGO-QUE-NAO-EXISTE", "Empresa E", "Admin E", "e@convidada.com.br", "senha123", aceite_termos=True
        )


def test_criar_tenant_vitrine_email_ja_cadastrado_falha(db_session):
    convite1 = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    tenant_service.criar_tenant_vitrine(
        db_session, convite1.codigo, "Empresa F", "Admin F", "repetido@convidada.com.br", "senha123", aceite_termos=True
    )

    convite2 = tenant_service.gerar_convite_vitrine(db_session, TENANT_ID_ORIGEM, None, validade_horas=24)
    with pytest.raises(RegraNegocioViolada):
        tenant_service.criar_tenant_vitrine(
            db_session, convite2.codigo, "Empresa G", "Admin G", "repetido@convidada.com.br", "senha123", aceite_termos=True
        )
