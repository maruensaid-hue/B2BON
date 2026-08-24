import pytest

from app.models.atividade import Atividade
from app.models.campo_enriquecido import CampoEnriquecido
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.fila_enriquecimento_conta import FilaEnriquecimentoConta
from app.models.mensagem import Mensagem
from app.models.negocio import Negocio
from app.services import conta_service
from app.services.errors import RegraNegocioViolada

TENANT_ID = "tenant-excluir-conta"


def _criar_conta_com_decisor(db_session, nome: str = "Alpha Tech") -> tuple[Conta, Decisor]:
    conta = Conta(tenant_id=TENANT_ID, icp_id=None, nome=nome, status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Fulano")
    db_session.add(decisor)
    db_session.commit()
    return conta, decisor


def test_excluir_conta_recem_importada_sem_historico(db_session):
    conta, decisor = _criar_conta_com_decisor(db_session)
    conta_id, decisor_id = conta.id, decisor.id
    db_session.add(CampoEnriquecido(conta_id=conta_id, campo="dominio", valor="alphatech.com.br", fonte="teste"))
    db_session.add(FilaEnriquecimentoConta(tenant_id=TENANT_ID, conta_id=conta_id))
    db_session.commit()

    conta_service.excluir(db_session, TENANT_ID, "1", conta_id)

    assert db_session.query(Conta).filter_by(id=conta_id).one_or_none() is None
    assert db_session.query(Decisor).filter_by(id=decisor_id).one_or_none() is None
    assert db_session.query(CampoEnriquecido).filter_by(conta_id=conta_id).count() == 0
    assert db_session.query(FilaEnriquecimentoConta).filter_by(conta_id=conta_id).count() == 0


def test_excluir_conta_permite_reimportar_com_mesmo_nome(db_session):
    """O ponto central do pedido: apagar de verdade, não só marcar como
    inativa, senão o dedupe por nome do import reaproveitaria a conta
    velha em vez de criar uma nova (perdendo o cargo-alvo/mapeamento
    novos que motivaram o reimport)."""
    conta, _ = _criar_conta_com_decisor(db_session, nome="Alpha Tech")
    conta_service.excluir(db_session, TENANT_ID, "1", conta.id)

    nova = Conta(tenant_id=TENANT_ID, icp_id=None, nome="Alpha Tech", status="prospectada")
    db_session.add(nova)
    db_session.commit()

    # A conta velha sumiu de verdade (não é só o dedupe que ignoraria uma
    # inativa) — a nova é a única e nasce sem nenhum decisor herdado.
    assert db_session.query(Conta).filter_by(tenant_id=TENANT_ID, nome="Alpha Tech").count() == 1
    assert db_session.query(Decisor).filter_by(conta_id=nova.id).count() == 0


def test_excluir_conta_com_negocio_e_bloqueada(db_session):
    conta, _ = _criar_conta_com_decisor(db_session)
    estagio = EstagioFunil(tenant_id=TENANT_ID, nome="Descoberta", ordem=1, tipo="aberto")
    db_session.add(estagio)
    db_session.flush()
    db_session.add(Negocio(tenant_id=TENANT_ID, conta_id=conta.id, estagio_id=estagio.id, nome="Oportunidade X", valor=1000.0, origem="manual"))
    db_session.commit()

    with pytest.raises(RegraNegocioViolada, match="negócio no CRM"):
        conta_service.excluir(db_session, TENANT_ID, "1", conta.id)

    assert db_session.query(Conta).filter_by(id=conta.id).one_or_none() is not None


def test_excluir_conta_com_mensagem_enviada_e_bloqueada(db_session):
    conta, decisor = _criar_conta_com_decisor(db_session)
    db_session.add(Mensagem(tenant_id=TENANT_ID, decisor_id=decisor.id, canal="email", conteudo="Olá", status="enviado"))
    db_session.commit()

    with pytest.raises(RegraNegocioViolada, match="mensagem enviada"):
        conta_service.excluir(db_session, TENANT_ID, "1", conta.id)


def test_excluir_conta_com_atividade_e_bloqueada(db_session):
    conta, _ = _criar_conta_com_decisor(db_session)
    db_session.add(Atividade(tenant_id=TENANT_ID, conta_id=conta.id, tipo="nota", descricao="Ligar semana que vem"))
    db_session.commit()

    with pytest.raises(RegraNegocioViolada, match="atividade registrada"):
        conta_service.excluir(db_session, TENANT_ID, "1", conta.id)


def test_excluir_lote_por_lista_apaga_livres_e_bloqueia_com_historico(db_session):
    from app.services import lista_prospeccao_service

    lista_criada = lista_prospeccao_service.criar(db_session, TENANT_ID, "1", "Evento Teste", None, None)
    conta_livre = Conta(tenant_id=TENANT_ID, icp_id=None, lista_prospeccao_id=lista_criada.id, nome="Livre Ltda", status="prospectada")
    conta_com_negocio = Conta(
        tenant_id=TENANT_ID, icp_id=None, lista_prospeccao_id=lista_criada.id, nome="Com Negocio Ltda", status="prospectada"
    )
    db_session.add_all([conta_livre, conta_com_negocio])
    db_session.flush()
    estagio = EstagioFunil(tenant_id=TENANT_ID, nome="Descoberta", ordem=1, tipo="aberto")
    db_session.add(estagio)
    db_session.flush()
    db_session.add(Negocio(tenant_id=TENANT_ID, conta_id=conta_com_negocio.id, estagio_id=estagio.id, nome="Oportunidade Y", valor=500.0, origem="manual"))
    db_session.commit()

    resultado = conta_service.excluir_lote_por_lista(db_session, TENANT_ID, "1", lista_criada.id)

    assert resultado["apagadas"] == 1
    assert resultado["bloqueadas"] == 1
    assert resultado["detalhes_bloqueadas"][0]["nome"] == "Com Negocio Ltda"
    assert db_session.query(Conta).filter_by(id=conta_livre.id).one_or_none() is None
    assert db_session.query(Conta).filter_by(id=conta_com_negocio.id).one_or_none() is not None
