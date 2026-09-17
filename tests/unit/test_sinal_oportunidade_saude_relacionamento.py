from datetime import UTC, datetime, timedelta

from app.models.mensagem_rede_social import MensagemRedeSocial
from app.models.perfil_empresa import PerfilEmpresa
from app.services import rede_social_service, relacionamento_empresarial_service, sinal_oportunidade_service

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"
TENANT_C = "tenant-terceiro"


def _conectar(db_session, tenant_a, tenant_b):
    conexao = rede_social_service.solicitar_conexao(db_session, tenant_a, None, tenant_b)
    rede_social_service.responder_conexao(db_session, tenant_b, None, conexao.id, aceitar=True)


def _criar_perfil(db_session, tenant_id, **overrides) -> PerfilEmpresa:
    dados = {"tenant_id": tenant_id, "nome_exibicao": f"Empresa {tenant_id}"}
    dados.update(overrides)
    perfil = PerfilEmpresa(**dados)
    db_session.add(perfil)
    db_session.commit()
    return perfil


def test_sem_interacao_e_sem_relacionamento(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    _criar_perfil(db_session, TENANT_B)

    resultado = sinal_oportunidade_service.analisar_saude_relacionamento(db_session, TENANT_A, TENANT_B)

    assert resultado["dias_sem_interacao"] is None
    assert resultado["classificacao"] == "sem_interacao"
    assert resultado["tem_relacionamento_declarado"] is False
    assert len(resultado["sugestoes"]) == 2


def test_aquecido_com_mensagem_recente(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    _criar_perfil(db_session, TENANT_B)
    rede_social_service.enviar_mensagem(db_session, TENANT_A, None, TENANT_B, "Oi!")

    resultado = sinal_oportunidade_service.analisar_saude_relacionamento(db_session, TENANT_A, TENANT_B)

    assert resultado["dias_sem_interacao"] == 0
    assert resultado["classificacao"] == "aquecido"


def test_esfriando_com_mensagem_antiga(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    _criar_perfil(db_session, TENANT_B)
    mensagem = MensagemRedeSocial(
        tenant_id_remetente=TENANT_A, tenant_id_destinatario=TENANT_B, texto="Oi, há muito tempo!"
    )
    db_session.add(mensagem)
    db_session.commit()
    mensagem.criado_em = datetime.now(UTC) - timedelta(days=45)
    db_session.commit()

    resultado = sinal_oportunidade_service.analisar_saude_relacionamento(db_session, TENANT_A, TENANT_B)

    assert resultado["dias_sem_interacao"] == 45
    assert resultado["classificacao"] == "esfriando"


def test_tem_relacionamento_declarado_remove_sugestao(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    _criar_perfil(db_session, TENANT_B)
    relacionamento_empresarial_service.declarar(db_session, TENANT_A, None, TENANT_B, "CUSTOMER_OF", "publica")

    resultado = sinal_oportunidade_service.analisar_saude_relacionamento(db_session, TENANT_A, TENANT_B)

    assert resultado["tem_relacionamento_declarado"] is True
    assert len(resultado["sugestoes"]) == 1


def test_listar_saude_relacionamentos_so_conexoes_aceitas(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    _criar_perfil(db_session, TENANT_B)
    rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_C)  # pendente, não aceita

    resultados = sinal_oportunidade_service.listar_saude_relacionamentos(db_session, TENANT_A)

    assert len(resultados) == 1
    assert resultados[0]["tenant_id_alvo"] == TENANT_B


def test_listar_saude_relacionamentos_ordena_esfriando_primeiro(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    _conectar(db_session, TENANT_A, TENANT_C)
    _criar_perfil(db_session, TENANT_B)
    _criar_perfil(db_session, TENANT_C)
    rede_social_service.enviar_mensagem(db_session, TENANT_A, None, TENANT_C, "Recente")

    resultados = sinal_oportunidade_service.listar_saude_relacionamentos(db_session, TENANT_A)

    assert resultados[0]["tenant_id_alvo"] == TENANT_B  # sem_interacao vem antes de aquecido
    assert resultados[1]["tenant_id_alvo"] == TENANT_C
