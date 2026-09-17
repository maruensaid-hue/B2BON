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


def test_atualizar_perfil_campos_corporate_profile(db_session):
    """Master prompt Fase 1 (§38) — campos de identidade/richness novos."""
    rede_social_service.atualizar_perfil(
        db_session, TENANT_A, None,
        logo_url="https://acme.com/logo.png",
        capa_url="https://acme.com/capa.png",
        cnae_principal="6201500",
        porte="MEDIO",
        sede_cidade="São Paulo",
        sede_uf="SP",
        mercados=["Saúde", "Educação"],
        produtos_servicos=["Consultoria de LGPD"],
        tecnologias=["AWS", "Kubernetes"],
        certificacoes=["ISO 27001"],
        redes_sociais={"linkedin": "https://linkedin.com/company/acme"},
    )

    perfil = rede_social_service.obter_perfil(db_session, TENANT_A)
    assert perfil.logo_url == "https://acme.com/logo.png"
    assert perfil.porte == "MEDIO"
    assert perfil.mercados == ["Saúde", "Educação"]
    assert perfil.redes_sociais == {"linkedin": "https://linkedin.com/company/acme"}
    assert perfil.status_verificacao == "nao_verificada"  # default até a 1B


def test_listar_empresas_filtra_por_setor_porte_mercado_e_busca(db_session):
    """Master prompt Fase 1C (§59 Company Search)."""
    rede_social_service.atualizar_perfil(
        db_session, TENANT_B, None, nome_exibicao="Beta Saúde", setor="Saúde", porte="GRANDE",
        mercados=["Hospitais"],
    )
    rede_social_service.atualizar_perfil(
        db_session, "tenant-c", None, nome_exibicao="Gama Tech", setor="Tecnologia", porte="PEQUENO",
        mercados=["Varejo"],
    )

    assert {e["perfil"].nome_exibicao for e in rede_social_service.listar_empresas(db_session, TENANT_A, setor="Saúde")} == {"Beta Saúde"}
    assert {e["perfil"].nome_exibicao for e in rede_social_service.listar_empresas(db_session, TENANT_A, porte="PEQUENO")} == {"Gama Tech"}
    assert {e["perfil"].nome_exibicao for e in rede_social_service.listar_empresas(db_session, TENANT_A, mercado="Hospitais")} == {"Beta Saúde"}
    assert {e["perfil"].nome_exibicao for e in rede_social_service.listar_empresas(db_session, TENANT_A, busca="gama")} == {"Gama Tech"}
    assert len(rede_social_service.listar_empresas(db_session, TENANT_A)) == 2


def test_listar_empresas_apenas_verificadas(db_session):
    rede_social_service.atualizar_perfil(db_session, TENANT_B, None, nome_exibicao="Beta")
    perfil_b = rede_social_service.obter_perfil(db_session, TENANT_B)
    perfil_b.status_verificacao = "verificada"
    db_session.commit()
    rede_social_service.atualizar_perfil(db_session, "tenant-c", None, nome_exibicao="Gama")

    resultado = rede_social_service.listar_empresas(db_session, TENANT_A, apenas_verificadas=True)

    assert {e["perfil"].nome_exibicao for e in resultado} == {"Beta"}


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
