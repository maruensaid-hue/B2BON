from app.models.usuario import Usuario
from app.services import post_rede_social_service
from app.services.errors import NaoAutorizado, NaoEncontrado

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"


def _criar_usuario(db_session, tenant_id: str, **overrides) -> Usuario:
    dados = {"tenant_id": tenant_id, "nome": "Autor Teste", "email": f"autor@{tenant_id}.com.br", "papel": "user"}
    dados.update(overrides)
    usuario = Usuario(**dados)
    db_session.add(usuario)
    db_session.commit()
    return usuario


def test_criar_post(db_session):
    autor = _criar_usuario(db_session, TENANT_A)

    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor.id), "Olá rede!", None, None)

    assert post["texto"] == "Olá rede!"
    assert post["tenant_id"] == TENANT_A
    assert post["autor_nome"] == "Autor Teste"


def test_listar_feed_ordem_cronologica_mais_recente_primeiro(db_session):
    autor_a = _criar_usuario(db_session, TENANT_A)
    autor_b = _criar_usuario(db_session, TENANT_B)
    post_rede_social_service.criar(db_session, TENANT_A, str(autor_a.id), "Primeiro post", None, None)
    post_rede_social_service.criar(db_session, TENANT_B, str(autor_b.id), "Segundo post", None, None)

    feed = post_rede_social_service.listar_feed(db_session)

    assert [item["texto"] for item in feed] == ["Segundo post", "Primeiro post"]


def test_listar_feed_traz_empresa_e_imagem_link(db_session):
    from app.services import rede_social_service

    autor = _criar_usuario(db_session, TENANT_A)
    rede_social_service.atualizar_perfil(db_session, TENANT_A, None, nome_exibicao="Acme", logo_url="https://x/logo.png")
    post_rede_social_service.criar(db_session, TENANT_A, str(autor.id), "Post com mídia", "https://x/img.png", "https://x")

    feed = post_rede_social_service.listar_feed(db_session)

    assert feed[0]["empresa_nome"] == "Acme"
    assert feed[0]["empresa_logo_url"] == "https://x/logo.png"
    assert feed[0]["imagem_url"] == "https://x/img.png"
    assert feed[0]["link_url"] == "https://x"


def test_excluir_post_pelo_proprio_autor(db_session):
    autor = _criar_usuario(db_session, TENANT_A)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor.id), "Apagar", None, None)

    post_rede_social_service.excluir(db_session, TENANT_A, str(autor.id), post["id"])

    assert post_rede_social_service.listar_feed(db_session) == []


def test_excluir_post_de_outro_tenant_falha(db_session):
    autor = _criar_usuario(db_session, TENANT_A)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor.id), "Não apagar", None, None)

    try:
        post_rede_social_service.excluir(db_session, TENANT_B, None, post["id"])
        assert False, "deveria ter levantado NaoAutorizado"
    except NaoAutorizado:
        pass


def test_excluir_post_inexistente_levanta_erro(db_session):
    try:
        post_rede_social_service.excluir(db_session, TENANT_A, None, 9999)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_comentar_post(db_session):
    autor_a = _criar_usuario(db_session, TENANT_A)
    autor_b = _criar_usuario(db_session, TENANT_B)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor_a.id), "Post comentado", None, None)

    comentario = post_rede_social_service.comentar(db_session, TENANT_B, str(autor_b.id), post["id"], "Muito bom!")

    assert comentario["texto"] == "Muito bom!"
    assert comentario["tenant_id"] == TENANT_B
    assert comentario["autor_nome"] == "Autor Teste"


def test_listar_comentarios_ordem_cronologica(db_session):
    autor = _criar_usuario(db_session, TENANT_A)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor.id), "Post", None, None)
    post_rede_social_service.comentar(db_session, TENANT_A, str(autor.id), post["id"], "Primeiro")
    post_rede_social_service.comentar(db_session, TENANT_A, str(autor.id), post["id"], "Segundo")

    comentarios = post_rede_social_service.listar_comentarios(db_session, post["id"])

    assert [item["texto"] for item in comentarios] == ["Primeiro", "Segundo"]


def test_comentar_post_inexistente_levanta_erro(db_session):
    autor = _criar_usuario(db_session, TENANT_A)
    try:
        post_rede_social_service.comentar(db_session, TENANT_A, str(autor.id), 9999, "Oi")
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_reagir_toggle_cria_e_remove(db_session):
    autor_a = _criar_usuario(db_session, TENANT_A)
    autor_b = _criar_usuario(db_session, TENANT_B)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor_a.id), "Post", None, None)

    resultado_1 = post_rede_social_service.reagir(db_session, TENANT_B, str(autor_b.id), post["id"])
    assert resultado_1 == {"reagiu": True, "total": 1}

    resultado_2 = post_rede_social_service.reagir(db_session, TENANT_B, str(autor_b.id), post["id"])
    assert resultado_2 == {"reagiu": False, "total": 0}


def test_reagir_uma_reacao_por_tenant(db_session):
    autor_a = _criar_usuario(db_session, TENANT_A)
    autor_b = _criar_usuario(db_session, TENANT_B)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor_a.id), "Post", None, None)

    post_rede_social_service.reagir(db_session, TENANT_A, str(autor_a.id), post["id"])
    resultado = post_rede_social_service.reagir(db_session, TENANT_B, str(autor_b.id), post["id"])

    assert resultado == {"reagiu": True, "total": 2}


def test_listar_feed_traz_contagens_e_eu_reagi(db_session):
    autor_a = _criar_usuario(db_session, TENANT_A)
    autor_b = _criar_usuario(db_session, TENANT_B)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor_a.id), "Post", None, None)
    post_rede_social_service.comentar(db_session, TENANT_B, str(autor_b.id), post["id"], "Comentário")
    post_rede_social_service.reagir(db_session, TENANT_B, str(autor_b.id), post["id"])

    feed_visto_por_b = post_rede_social_service.listar_feed(db_session, tenant_id_atual=TENANT_B)
    feed_visto_por_a = post_rede_social_service.listar_feed(db_session, tenant_id_atual=TENANT_A)

    assert feed_visto_por_b[0]["total_comentarios"] == 1
    assert feed_visto_por_b[0]["total_reacoes"] == 1
    assert feed_visto_por_b[0]["eu_reagi"] is True
    assert feed_visto_por_a[0]["eu_reagi"] is False
