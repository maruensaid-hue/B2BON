import pytest

from app.models.oferta import Oferta
from app.services import rede_social_service
from app.services.errors import RegraNegocioViolada

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"


def test_perfil_lazy_criado_na_primeira_chamada(db_session):
    perfil = rede_social_service.obter_perfil(db_session, TENANT_A)

    assert perfil.tenant_id == TENANT_A
    assert perfil.nome_exibicao == TENANT_A  # fallback, sem razão social conhecida
    # idempotente
    assert rede_social_service.obter_perfil(db_session, TENANT_A).id == perfil.id


def test_atualizar_perfil(db_session):
    rede_social_service.atualizar_perfil(
        db_session, TENANT_A, None, nome_exibicao="CyberFort Consultoria", setor="Consultoria B2B"
    )

    perfil = rede_social_service.obter_perfil(db_session, TENANT_A)
    assert perfil.nome_exibicao == "CyberFort Consultoria"
    assert perfil.setor == "Consultoria B2B"


def test_solicitar_e_aceitar_conexao(db_session):
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)
    assert conexao.status == "pendente"

    aceita = rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=True)

    assert aceita.status == "aceita"
    assert aceita.respondida_em is not None


def test_recusar_conexao(db_session):
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)

    recusada = rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=False)

    assert recusada.status == "recusada"


def test_nao_permite_solicitar_conexao_duplicada_pendente(db_session):
    rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)

    with pytest.raises(RegraNegocioViolada):
        rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)


def test_enviar_mensagem_sem_conexao_aceita_falha(db_session):
    with pytest.raises(RegraNegocioViolada):
        rede_social_service.enviar_mensagem(db_session, TENANT_A, None, TENANT_B, "Olá!")


def test_enviar_mensagem_com_conexao_aceita_funciona(db_session):
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)
    rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=True)

    mensagem = rede_social_service.enviar_mensagem(db_session, TENANT_A, None, TENANT_B, "Olá, tudo bem?")

    conversa = rede_social_service.listar_conversa(db_session, TENANT_B, TENANT_A)
    assert len(conversa) == 1
    assert conversa[0].id == mensagem.id


def test_marcar_lida(db_session):
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)
    rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=True)
    mensagem = rede_social_service.enviar_mensagem(db_session, TENANT_A, None, TENANT_B, "Oi")

    lida = rede_social_service.marcar_lida(db_session, TENANT_B, mensagem.id)

    assert lida.lida_em is not None


def test_listar_empresas_mostra_status_de_conexao_e_oferta(db_session):
    rede_social_service.obter_perfil(db_session, TENANT_B)
    db_session.add(Oferta(tenant_id=TENANT_B, nome="Consultoria SHARK", descricao="Vendas B2B", ativo=True))
    db_session.commit()

    diretorio_antes = rede_social_service.listar_empresas(db_session, TENANT_A)
    entrada = next(item for item in diretorio_antes if item["perfil"].tenant_id == TENANT_B)
    assert entrada["status_conexao"] == "nenhuma"
    assert entrada["oferta_principal"]["nome"] == "Consultoria SHARK"

    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)
    diretorio_pendente = rede_social_service.listar_empresas(db_session, TENANT_A)
    entrada_pendente = next(item for item in diretorio_pendente if item["perfil"].tenant_id == TENANT_B)
    assert entrada_pendente["status_conexao"] == "pendente_enviada"

    diretorio_do_b = rede_social_service.listar_empresas(db_session, TENANT_B)
    entrada_do_b = next(item for item in diretorio_do_b if item["perfil"].tenant_id == TENANT_A)
    assert entrada_do_b["status_conexao"] == "pendente_recebida"

    rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=True)
    diretorio_depois = rede_social_service.listar_empresas(db_session, TENANT_A)
    entrada_depois = next(item for item in diretorio_depois if item["perfil"].tenant_id == TENANT_B)
    assert entrada_depois["status_conexao"] == "aceita"
