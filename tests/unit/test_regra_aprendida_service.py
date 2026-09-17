from app.models.icp import ICP
from app.models.oferta import Oferta
from app.schemas.regra_aprendida import RegraAprendidaCreateSchema
from app.services import regra_aprendida_service
from app.services.errors import NaoEncontrado

TENANT_ID = "tenant-regra"


def _criar_icp(db_session, **overrides) -> ICP:
    dados = {
        "tenant_id": TENANT_ID, "grupo_id": "grupo-1", "nome": "ICP Teste",
        "segmento": "Tecnologia", "porte": "PEQUENO", "regiao": "SP",
    }
    dados.update(overrides)
    icp = ICP(**dados)
    db_session.add(icp)
    db_session.commit()
    return icp


def _criar_oferta(db_session, **overrides) -> Oferta:
    dados = {"tenant_id": TENANT_ID, "nome": "Oferta Teste", "descricao": "Descrição"}
    dados.update(overrides)
    oferta = Oferta(**dados)
    db_session.add(oferta)
    db_session.commit()
    return oferta


def test_criar_atualizar_ativar_desativar_excluir(db_session):
    regra = regra_aprendida_service.criar(
        db_session, TENANT_ID, "usuario-1", RegraAprendidaCreateSchema(regra="Nunca usar 'sinergia'")
    )
    assert regra.ativa is True

    atualizada = regra_aprendida_service.atualizar(
        db_session, TENANT_ID, "usuario-1", regra.id, RegraAprendidaCreateSchema(regra="Nunca usar 'sinergia' ou 'disruptivo'")
    )
    assert atualizada.regra == "Nunca usar 'sinergia' ou 'disruptivo'"

    desativada = regra_aprendida_service.desativar(db_session, TENANT_ID, "usuario-1", regra.id)
    assert desativada.ativa is False

    reativada = regra_aprendida_service.ativar(db_session, TENANT_ID, "usuario-1", regra.id)
    assert reativada.ativa is True

    regra_aprendida_service.excluir(db_session, TENANT_ID, "usuario-1", regra.id)
    assert regra_aprendida_service.listar(db_session, TENANT_ID) == []


def test_operacoes_em_regra_de_outro_tenant_ou_inexistente_falham(db_session):
    regra = regra_aprendida_service.criar(
        db_session, TENANT_ID, "usuario-1", RegraAprendidaCreateSchema(regra="Regra tenant A")
    )
    try:
        regra_aprendida_service.desativar(db_session, "outro-tenant", "usuario-1", regra.id)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_regras_aplicaveis_texto_regra_geral_do_tenant_aplica_a_qualquer_icp_oferta_canal(db_session):
    regra_aprendida_service.criar(
        db_session, TENANT_ID, None, RegraAprendidaCreateSchema(regra="Regra geral do tenant")
    )

    texto = regra_aprendida_service.regras_aplicaveis_texto(db_session, TENANT_ID, icp_id=123, oferta_id=456, canal="email")

    assert "Regra geral do tenant" in texto


def test_regras_aplicaveis_texto_filtra_por_icp_oferta_canal(db_session):
    icp_a = _criar_icp(db_session, nome="ICP A")
    icp_b = _criar_icp(db_session, nome="ICP B")
    oferta_a = _criar_oferta(db_session, nome="Oferta A")

    regra_aprendida_service.criar(
        db_session, TENANT_ID, None,
        RegraAprendidaCreateSchema(icp_id=icp_a.id, regra="Só ICP A"),
    )
    regra_aprendida_service.criar(
        db_session, TENANT_ID, None,
        RegraAprendidaCreateSchema(oferta_id=oferta_a.id, regra="Só Oferta A"),
    )
    regra_aprendida_service.criar(
        db_session, TENANT_ID, None,
        RegraAprendidaCreateSchema(canal="whatsapp", regra="Só WhatsApp"),
    )

    texto_icp_a = regra_aprendida_service.regras_aplicaveis_texto(db_session, TENANT_ID, icp_a.id, None, "email")
    assert "Só ICP A" in texto_icp_a
    assert "Só Oferta A" not in texto_icp_a
    assert "Só WhatsApp" not in texto_icp_a

    texto_icp_b = regra_aprendida_service.regras_aplicaveis_texto(db_session, TENANT_ID, icp_b.id, None, "email")
    assert "Só ICP A" not in texto_icp_b

    texto_oferta_a = regra_aprendida_service.regras_aplicaveis_texto(db_session, TENANT_ID, None, oferta_a.id, "email")
    assert "Só Oferta A" in texto_oferta_a

    texto_whatsapp = regra_aprendida_service.regras_aplicaveis_texto(db_session, TENANT_ID, None, None, "whatsapp")
    assert "Só WhatsApp" in texto_whatsapp
    texto_email = regra_aprendida_service.regras_aplicaveis_texto(db_session, TENANT_ID, None, None, "email")
    assert "Só WhatsApp" not in texto_email


def test_regras_aplicaveis_texto_ignora_regra_inativa_e_de_outro_tenant(db_session):
    regra = regra_aprendida_service.criar(
        db_session, TENANT_ID, None, RegraAprendidaCreateSchema(regra="Regra desativada")
    )
    regra_aprendida_service.desativar(db_session, TENANT_ID, None, regra.id)
    regra_aprendida_service.criar(
        db_session, "outro-tenant", None, RegraAprendidaCreateSchema(regra="Regra de outro tenant")
    )

    texto = regra_aprendida_service.regras_aplicaveis_texto(db_session, TENANT_ID, None, None, "email")

    assert texto == ""


def test_regras_aplicaveis_texto_sem_regra_nenhuma_retorna_vazio(db_session):
    texto = regra_aprendida_service.regras_aplicaveis_texto(db_session, "tenant-sem-regras", None, None, "email")

    assert texto == ""
