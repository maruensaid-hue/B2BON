from app.models.aprovacao import Aprovacao
from app.models.cadencia import Cadencia
from app.models.icp import ICP
from app.models.oferta import Oferta
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.schemas.regra_aprendida import RegraAprendidaCreateSchema
from app.services import aprovacao_service, regra_aprendida_service
from app.services.errors import NaoEncontrado
from tests.fakes import FakeLLMProvider

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


def _criar_conta_decisor_cadencia(db_session, icp, oferta):
    from app.models.conta import Conta
    from app.models.decisor import Decisor

    conta = Conta(tenant_id=TENANT_ID, nome="Conta Correção", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Correção", email="d@teste.com")
    db_session.add(decisor)
    cadencia = Cadencia(
        tenant_id=TENANT_ID, nome="Cadência Correção", status="ativa", canais=["email"],
        icp_id=icp.id, oferta_id=oferta.id,
    )
    db_session.add(cadencia)
    db_session.flush()
    return conta, decisor, cadencia


def test_listar_correcoes_recentes_resolve_edicao_com_icp_oferta_da_cadencia(db_session):
    icp = _criar_icp(db_session, nome="ICP Correção")
    oferta = _criar_oferta(db_session, nome="Oferta Correção")
    _, decisor, cadencia = _criar_conta_decisor_cadencia(db_session, icp, oferta)
    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", None, "Texto original", StubPlanLimitsProvider(),
    )
    aprovacao = db_session.query(Aprovacao).filter_by(mensagem_id=mensagem.id).one()

    aprovacao_service.editar_mensagem(db_session, TENANT_ID, "usuario-1", aprovacao.id, "Texto editado pelo humano")

    correcoes = regra_aprendida_service.listar_correcoes_recentes(db_session, TENANT_ID)

    assert len(correcoes) == 1
    correcao = correcoes[0]
    assert correcao["tipo"] == "edicao"
    assert correcao["conteudo_anterior"] == "Texto original"
    assert correcao["conteudo_novo"] == "Texto editado pelo humano"
    assert correcao["icp_id"] == icp.id
    assert correcao["oferta_id"] == oferta.id
    assert correcao["canal"] == "email"
    assert correcao["conta_nome"] == "Conta Correção"


def test_listar_correcoes_recentes_resolve_rejeicao_via_aprovacao(db_session):
    icp = _criar_icp(db_session, nome="ICP Rejeição")
    oferta = _criar_oferta(db_session, nome="Oferta Rejeição")
    _, decisor, cadencia = _criar_conta_decisor_cadencia(db_session, icp, oferta)
    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "whatsapp", None, "Texto", StubPlanLimitsProvider(),
    )
    aprovacao = db_session.query(Aprovacao).filter_by(mensagem_id=mensagem.id).one()

    aprovacao_service.rejeitar(db_session, TENANT_ID, "usuario-1", aprovacao.id, "Tom agressivo demais")

    correcoes = regra_aprendida_service.listar_correcoes_recentes(db_session, TENANT_ID)

    assert len(correcoes) == 1
    correcao = correcoes[0]
    assert correcao["tipo"] == "rejeicao"
    assert correcao["motivo"] == "Tom agressivo demais"
    assert correcao["conteudo_anterior"] is None
    assert correcao["icp_id"] == icp.id
    assert correcao["oferta_id"] == oferta.id
    assert correcao["canal"] == "whatsapp"


def test_listar_correcoes_recentes_mensagem_avulsa_sem_cadencia_nao_quebra(db_session):
    from app.models.conta import Conta
    from app.models.decisor import Decisor

    conta = Conta(tenant_id=TENANT_ID, nome="Conta Avulsa", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Avulso", email="avulso@teste.com")
    db_session.add(decisor)
    db_session.flush()

    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Texto avulso", StubPlanLimitsProvider(),
    )
    aprovacao = db_session.query(Aprovacao).filter_by(mensagem_id=mensagem.id).one()

    aprovacao_service.editar_mensagem(db_session, TENANT_ID, "usuario-1", aprovacao.id, "Texto avulso editado")

    correcoes = regra_aprendida_service.listar_correcoes_recentes(db_session, TENANT_ID)

    assert len(correcoes) == 1
    assert correcoes[0]["icp_id"] is None
    assert correcoes[0]["oferta_id"] is None


def test_sugerir_regra_com_ia_para_edicao_cita_antes_e_depois_no_prompt(db_session):
    icp = _criar_icp(db_session, nome="ICP Sugestão")
    oferta = _criar_oferta(db_session, nome="Oferta Sugestão")
    _, decisor, cadencia = _criar_conta_decisor_cadencia(db_session, icp, oferta)
    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "email", None, "Temos uma sinergia incrível", StubPlanLimitsProvider(),
    )
    aprovacao = db_session.query(Aprovacao).filter_by(mensagem_id=mensagem.id).one()
    aprovacao_service.editar_mensagem(db_session, TENANT_ID, "usuario-1", aprovacao.id, "Temos uma proposta relevante")
    log = regra_aprendida_service.listar_correcoes_recentes(db_session, TENANT_ID)[0]

    fake_llm = FakeLLMProvider(respostas=["Nunca usar a palavra sinergia"])

    sugestao = regra_aprendida_service.sugerir_regra_com_ia(db_session, TENANT_ID, log["id"], fake_llm)

    assert sugestao == "Nunca usar a palavra sinergia"
    prompt = fake_llm.chamadas[0].prompt
    assert "Temos uma sinergia incrível" in prompt
    assert "Temos uma proposta relevante" in prompt


def test_sugerir_regra_com_ia_para_rejeicao_cita_motivo_no_prompt(db_session):
    icp = _criar_icp(db_session, nome="ICP Sugestão 2")
    oferta = _criar_oferta(db_session, nome="Oferta Sugestão 2")
    _, decisor, cadencia = _criar_conta_decisor_cadencia(db_session, icp, oferta)
    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, cadencia.id, decisor.id, "whatsapp", None, "Texto", StubPlanLimitsProvider(),
    )
    aprovacao = db_session.query(Aprovacao).filter_by(mensagem_id=mensagem.id).one()
    aprovacao_service.rejeitar(db_session, TENANT_ID, "usuario-1", aprovacao.id, "Tom agressivo demais")
    log = regra_aprendida_service.listar_correcoes_recentes(db_session, TENANT_ID)[0]

    fake_llm = FakeLLMProvider(respostas=["Evitar tom agressivo nas mensagens"])

    sugestao = regra_aprendida_service.sugerir_regra_com_ia(db_session, TENANT_ID, log["id"], fake_llm)

    assert sugestao == "Evitar tom agressivo nas mensagens"
    assert "Tom agressivo demais" in fake_llm.chamadas[0].prompt


def test_sugerir_regra_com_ia_correcao_inexistente_ou_de_outro_tenant_levanta_erro(db_session):
    fake_llm = FakeLLMProvider()

    try:
        regra_aprendida_service.sugerir_regra_com_ia(db_session, TENANT_ID, 9999, fake_llm)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass
    assert fake_llm.chamadas == []
