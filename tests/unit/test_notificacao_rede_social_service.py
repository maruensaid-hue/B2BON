from app.models.usuario import Usuario
from app.services import (
    notificacao_rede_social_service,
    post_rede_social_service,
    rede_social_service,
    sala_corporativa_service,
)
from tests.fakes import FakeEmailProvider

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"


def _criar_usuario(db_session, tenant_id: str, **overrides) -> Usuario:
    dados = {"tenant_id": tenant_id, "nome": "Autor Teste", "email": f"autor@{tenant_id}.com.br", "papel": "user"}
    dados.update(overrides)
    usuario = Usuario(**dados)
    db_session.add(usuario)
    db_session.commit()
    return usuario


def test_criar_e_listar_notificacao(db_session):
    notificacao_rede_social_service.criar(db_session, TENANT_A, "new_message", "mensagem_rede_social", 1, "Oi")
    db_session.commit()

    notificacoes = notificacao_rede_social_service.listar(db_session, TENANT_A)

    assert len(notificacoes) == 1
    assert notificacoes[0]["tipo"] == "new_message"
    assert notificacoes[0]["lida"] is False


def test_contar_nao_lidas_e_marcar_lida(db_session):
    notificacao_rede_social_service.criar(db_session, TENANT_A, "new_comment", "post_rede_social", 1, "Comentário")
    db_session.commit()
    notificacao_id = notificacao_rede_social_service.listar(db_session, TENANT_A)[0]["id"]

    assert notificacao_rede_social_service.contar_nao_lidas(db_session, TENANT_A) == 1

    notificacao_rede_social_service.marcar_lida(db_session, TENANT_A, notificacao_id)

    assert notificacao_rede_social_service.contar_nao_lidas(db_session, TENANT_A) == 0


def test_marcar_todas_lidas(db_session):
    notificacao_rede_social_service.criar(db_session, TENANT_A, "new_comment", "post_rede_social", 1, "A")
    notificacao_rede_social_service.criar(db_session, TENANT_A, "new_reaction", "post_rede_social", 2, "B")
    db_session.commit()

    notificacao_rede_social_service.marcar_todas_lidas(db_session, TENANT_A)

    assert notificacao_rede_social_service.contar_nao_lidas(db_session, TENANT_A) == 0


def test_isolamento_por_tenant(db_session):
    notificacao_rede_social_service.criar(db_session, TENANT_A, "new_comment", "post_rede_social", 1, "A")
    db_session.commit()

    assert notificacao_rede_social_service.listar(db_session, TENANT_B) == []
    assert notificacao_rede_social_service.contar_nao_lidas(db_session, TENANT_B) == 0


def test_solicitar_conexao_notifica_destino(db_session):
    rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)

    notificacoes = notificacao_rede_social_service.listar(db_session, TENANT_B)

    assert len(notificacoes) == 1
    assert notificacoes[0]["tipo"] == "connection_request"


def test_aceitar_conexao_notifica_quem_pediu(db_session):
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)

    rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=True)

    notificacoes = notificacao_rede_social_service.listar(db_session, TENANT_A)
    assert any(n["tipo"] == "connection_accepted" for n in notificacoes)


def test_recusar_conexao_nao_notifica(db_session):
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)

    rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=False)

    notificacoes = notificacao_rede_social_service.listar(db_session, TENANT_A)
    assert not any(n["tipo"] == "connection_accepted" for n in notificacoes)


def test_comentar_notifica_autor_do_post(db_session):
    autor_a = _criar_usuario(db_session, TENANT_A)
    autor_b = _criar_usuario(db_session, TENANT_B)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor_a.id), "Post", None, None)

    post_rede_social_service.comentar(db_session, TENANT_B, str(autor_b.id), post["id"], "Comentário")

    notificacoes = notificacao_rede_social_service.listar(db_session, TENANT_A)
    assert any(n["tipo"] == "new_comment" for n in notificacoes)


def test_comentar_no_proprio_post_nao_notifica(db_session):
    autor = _criar_usuario(db_session, TENANT_A)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor.id), "Post", None, None)

    post_rede_social_service.comentar(db_session, TENANT_A, str(autor.id), post["id"], "Comentário próprio")

    assert notificacao_rede_social_service.listar(db_session, TENANT_A) == []


def test_reagir_notifica_autor_do_post(db_session):
    autor_a = _criar_usuario(db_session, TENANT_A)
    autor_b = _criar_usuario(db_session, TENANT_B)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor_a.id), "Post", None, None)

    post_rede_social_service.reagir(db_session, TENANT_B, str(autor_b.id), post["id"])

    notificacoes = notificacao_rede_social_service.listar(db_session, TENANT_A)
    assert any(n["tipo"] == "new_reaction" for n in notificacoes)


def test_remover_reacao_nao_gera_notificacao_extra(db_session):
    autor_a = _criar_usuario(db_session, TENANT_A)
    autor_b = _criar_usuario(db_session, TENANT_B)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor_a.id), "Post", None, None)

    post_rede_social_service.reagir(db_session, TENANT_B, str(autor_b.id), post["id"])
    post_rede_social_service.reagir(db_session, TENANT_B, str(autor_b.id), post["id"])

    notificacoes = notificacao_rede_social_service.listar(db_session, TENANT_A)
    assert len(notificacoes) == 1


def test_enviar_mensagem_notifica_destinatario(db_session):
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)
    rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=True)

    rede_social_service.enviar_mensagem(db_session, TENANT_A, None, TENANT_B, "Olá!")

    notificacoes = notificacao_rede_social_service.listar(db_session, TENANT_B)
    assert any(n["tipo"] == "new_message" for n in notificacoes)


def test_solicitar_conexao_envia_email_pro_destino(db_session):
    _criar_usuario(db_session, TENANT_B, email="destino@tenant-outro.com.br")
    email = FakeEmailProvider()

    rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B, email)

    assert len(email.envios) == 1
    assert email.envios[0]["destinatario"] == "destino@tenant-outro.com.br"


def test_aceitar_conexao_envia_email_pra_quem_pediu(db_session):
    _criar_usuario(db_session, TENANT_A, email="pediu@tenant-teste.com.br")
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)
    email = FakeEmailProvider()

    rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=True, email_provider=email)

    assert len(email.envios) == 1
    assert email.envios[0]["destinatario"] == "pediu@tenant-teste.com.br"


def test_recusar_conexao_nao_envia_email(db_session):
    _criar_usuario(db_session, TENANT_A)
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)
    email = FakeEmailProvider()

    rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=False, email_provider=email)

    assert email.envios == []


def test_enviar_mensagem_envia_email_pro_destinatario(db_session):
    _criar_usuario(db_session, TENANT_B, email="destino@tenant-outro.com.br")
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)
    rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=True)
    email = FakeEmailProvider()

    rede_social_service.enviar_mensagem(db_session, TENANT_A, None, TENANT_B, "Olá!", email)

    assert len(email.envios) == 1
    assert email.envios[0]["destinatario"] == "destino@tenant-outro.com.br"


def test_comentar_envia_email_pro_autor_do_post(db_session):
    autor_a = _criar_usuario(db_session, TENANT_A, email="autor@tenant-teste.com.br")
    autor_b = _criar_usuario(db_session, TENANT_B)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor_a.id), "Post", None, None)
    email = FakeEmailProvider()

    post_rede_social_service.comentar(db_session, TENANT_B, str(autor_b.id), post["id"], "Comentário", email)

    assert len(email.envios) == 1
    assert email.envios[0]["destinatario"] == "autor@tenant-teste.com.br"


def test_comentar_no_proprio_post_nao_envia_email(db_session):
    autor = _criar_usuario(db_session, TENANT_A)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor.id), "Post", None, None)
    email = FakeEmailProvider()

    post_rede_social_service.comentar(db_session, TENANT_A, str(autor.id), post["id"], "Comentário próprio", email)

    assert email.envios == []


def test_reagir_envia_email_pro_autor_do_post(db_session):
    autor_a = _criar_usuario(db_session, TENANT_A, email="autor@tenant-teste.com.br")
    autor_b = _criar_usuario(db_session, TENANT_B)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor_a.id), "Post", None, None)
    email = FakeEmailProvider()

    post_rede_social_service.reagir(db_session, TENANT_B, str(autor_b.id), post["id"], email_provider=email)

    assert len(email.envios) == 1
    assert email.envios[0]["destinatario"] == "autor@tenant-teste.com.br"


def test_compartilhar_envia_email_pro_autor_do_post(db_session):
    autor_a = _criar_usuario(db_session, TENANT_A, email="autor@tenant-teste.com.br")
    autor_b = _criar_usuario(db_session, TENANT_B)
    post = post_rede_social_service.criar(db_session, TENANT_A, str(autor_a.id), "Post", None, None)
    email = FakeEmailProvider()

    post_rede_social_service.compartilhar(db_session, TENANT_B, str(autor_b.id), post["id"], email)

    assert len(email.envios) == 1
    assert email.envios[0]["destinatario"] == "autor@tenant-teste.com.br"


def test_mensagem_sala_envia_email_pro_outro_tenant(db_session):
    from app.models.canal_sala import CanalSala
    from app.models.sala_corporativa import SalaCorporativa

    _criar_usuario(db_session, TENANT_B, email="destino@tenant-outro.com.br")
    tenant_a, tenant_b = sorted((TENANT_A, TENANT_B))
    sala = SalaCorporativa(tenant_id_a=tenant_a, tenant_id_b=tenant_b)
    db_session.add(sala)
    db_session.flush()
    canal = CanalSala(sala_id=sala.id, tipo="GENERAL", criado_por=TENANT_A)
    db_session.add(canal)
    db_session.commit()
    email = FakeEmailProvider()

    sala_corporativa_service.enviar_mensagem_sala(db_session, TENANT_A, None, canal.id, "Olá!", None, email)

    assert len(email.envios) == 1
    assert email.envios[0]["destinatario"] == "destino@tenant-outro.com.br"


def test_email_de_notificacao_ignora_usuario_inativo(db_session):
    _criar_usuario(db_session, TENANT_B, email="ativo@tenant-outro.com.br", ativo=True)
    _criar_usuario(db_session, TENANT_B, email="inativo@tenant-outro.com.br", ativo=False)
    email = FakeEmailProvider()

    rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B, email)

    destinatarios = [envio["destinatario"] for envio in email.envios]
    assert destinatarios == ["ativo@tenant-outro.com.br"]


def test_falha_no_envio_de_email_nao_quebra_a_acao(db_session):
    _criar_usuario(db_session, TENANT_B)
    email = FakeEmailProvider()
    email.falhar_proximos = 1

    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B, email)

    assert conexao.id is not None
    notificacoes = notificacao_rede_social_service.listar(db_session, TENANT_B)
    assert len(notificacoes) == 1
