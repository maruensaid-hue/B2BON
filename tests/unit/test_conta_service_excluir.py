import pytest

from app.models.atividade import Atividade
from app.models.campo_enriquecido import CampoEnriquecido
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.fila_enriquecimento_conta import FilaEnriquecimentoConta
from app.models.indicacao import Indicacao
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


def test_excluir_conta_promotora_de_indicacao_e_bloqueada(db_session):
    """Bug real relatado pelo usuário: `promotor_conta_id`/`conta_gerada_id`
    da Indicação nunca eram checados antes de apagar — não davam
    `RegraNegocioViolada` (que o lote sabe engolir), davam um erro de
    integridade do banco não tratado no meio do `db.delete`, derrubando o
    lote inteiro em vez de só pular aquela conta."""
    conta, decisor = _criar_conta_com_decisor(db_session, nome="Promotora Ltda")
    db_session.add(
        Indicacao(
            tenant_id=TENANT_ID,
            promotor_decisor_id=decisor.id,
            promotor_conta_id=conta.id,
            codigo_indicacao="IND-001",
            canal="whatsapp",
        )
    )
    db_session.commit()

    with pytest.raises(RegraNegocioViolada, match="indicação"):
        conta_service.excluir(db_session, TENANT_ID, "1", conta.id)


def test_excluir_conta_gerada_por_indicacao_e_bloqueada(db_session):
    promotora, decisor_promotor = _criar_conta_com_decisor(db_session, nome="Origem Ltda")
    gerada, _ = _criar_conta_com_decisor(db_session, nome="Gerada Ltda")
    db_session.add(
        Indicacao(
            tenant_id=TENANT_ID,
            promotor_decisor_id=decisor_promotor.id,
            promotor_conta_id=promotora.id,
            codigo_indicacao="IND-002",
            canal="whatsapp",
            conta_gerada_id=gerada.id,
        )
    )
    db_session.commit()

    with pytest.raises(RegraNegocioViolada, match="indicação"):
        conta_service.excluir(db_session, TENANT_ID, "1", gerada.id)


def test_mapear_elegibilidade_exclusao_marca_bloqueadas_com_motivo(db_session):
    livre, _ = _criar_conta_com_decisor(db_session, nome="Livre Ltda")
    bloqueada, decisor_bloqueada = _criar_conta_com_decisor(db_session, nome="Bloqueada Ltda")
    db_session.add(Mensagem(tenant_id=TENANT_ID, decisor_id=decisor_bloqueada.id, canal="email", conteudo="Olá", status="enviado"))
    db_session.commit()

    resultado = {
        item["conta_id"]: item
        for item in conta_service.mapear_elegibilidade_exclusao(db_session, [livre, bloqueada])
    }

    assert resultado[livre.id]["bloqueada"] is False
    assert resultado[livre.id]["motivo"] is None
    assert resultado[bloqueada.id]["bloqueada"] is True
    assert "mensagem enviada" in resultado[bloqueada.id]["motivo"]


def test_excluir_lote_leads_com_conta_ids_restringe_selecao(db_session):
    """A seleção manual (caixas de seleção no frontend) restringe o lote —
    uma conta elegível fora da seleção não é tocada."""
    from app.models.usuario import Usuario

    usuario = Usuario(tenant_id=TENANT_ID, email="admin@teste.com", nome="Admin", papel="super_admin", senha_hash="x")
    db_session.add(usuario)
    db_session.flush()

    selecionada, _ = _criar_conta_com_decisor(db_session, nome="Selecionada Ltda")
    fora_da_selecao, _ = _criar_conta_com_decisor(db_session, nome="Fora Ltda")
    db_session.commit()

    resultado = conta_service.excluir_lote_leads(db_session, TENANT_ID, "1", usuario, conta_ids=[selecionada.id])

    assert resultado["apagadas"] == 1
    assert db_session.query(Conta).filter_by(id=selecionada.id).one_or_none() is None
    assert db_session.query(Conta).filter_by(id=fora_da_selecao.id).one_or_none() is not None


def _criar_super_admin(db_session, email: str = "super@teste.com") -> "Usuario":
    from app.models.usuario import Usuario

    usuario = Usuario(tenant_id=TENANT_ID, email=email, nome="Super", papel="super_admin", senha_hash="x")
    db_session.add(usuario)
    db_session.commit()
    return usuario


def test_limpeza_leads_protege_oportunidade_ou_enriquecida_mas_nao_atividade_isolada(db_session):
    """Critério pontual pedido pelo usuário 2026-08-24: mais solto que o
    crivo padrão — só oportunidade OU enriquecimento (site/contato)
    protegem; atividade/mensagem sozinhas NÃO protegem aqui (embora
    bloqueassem em `excluir_lote_leads`)."""
    usuario = _criar_super_admin(db_session)

    com_negocio = Conta(tenant_id=TENANT_ID, icp_id=None, nome="Com Negocio", status="prospectada")
    db_session.add(com_negocio)
    db_session.flush()
    estagio = EstagioFunil(tenant_id=TENANT_ID, nome="Descoberta", ordem=1, tipo="aberto")
    db_session.add(estagio)
    db_session.flush()
    db_session.add(Negocio(tenant_id=TENANT_ID, conta_id=com_negocio.id, estagio_id=estagio.id, nome="Oportunidade", valor=100.0, origem="manual"))

    com_site = Conta(tenant_id=TENANT_ID, icp_id=None, nome="Com Site", status="prospectada")
    db_session.add(com_site)
    db_session.flush()
    db_session.add(CampoEnriquecido(conta_id=com_site.id, campo="dominio", valor="site.com.br", fonte="teste"))

    com_contato, _ = _criar_conta_com_decisor(db_session, nome="Com Contato")

    com_atividade_isolada = Conta(tenant_id=TENANT_ID, icp_id=None, nome="Com Atividade Isolada", status="prospectada")
    db_session.add(com_atividade_isolada)
    db_session.flush()
    db_session.add(Atividade(tenant_id=TENANT_ID, conta_id=com_atividade_isolada.id, tipo="nota", descricao="Ligar"))

    sem_nada = Conta(tenant_id=TENANT_ID, icp_id=None, nome="Sem Nada", status="prospectada")
    db_session.add(sem_nada)
    db_session.commit()

    previa = conta_service.prever_limpeza_leads_nao_trabalhados(db_session, TENANT_ID, usuario)
    assert previa == {"total": 5, "serao_apagadas": 2, "protegidas": 3}

    resultado = conta_service.executar_limpeza_leads_nao_trabalhados(db_session, TENANT_ID, "1", usuario)

    assert resultado["apagadas"] == 2
    assert resultado["bloqueadas"] == 3
    nomes_protegidos = {item["nome"] for item in resultado["detalhes_bloqueadas"]}
    assert nomes_protegidos == {"Com Negocio", "Com Site", "Com Contato"}
    assert db_session.query(Conta).filter_by(id=com_negocio.id).one_or_none() is not None
    assert db_session.query(Conta).filter_by(id=com_site.id).one_or_none() is not None
    assert db_session.query(Conta).filter_by(id=com_contato.id).one_or_none() is not None
    assert db_session.query(Conta).filter_by(id=com_atividade_isolada.id).one_or_none() is None
    assert db_session.query(Conta).filter_by(id=sem_nada.id).one_or_none() is None


def test_excluir_lote_respeita_o_tamanho_do_lote_em_varias_rodadas(db_session, monkeypatch):
    """Garante que o chunking (`_TAMANHO_LOTE_EXCLUSAO`) não perde nem
    duplica contas quando o lote elegível precisa de mais de uma rodada."""
    monkeypatch.setattr(conta_service, "_TAMANHO_LOTE_EXCLUSAO", 2)
    from app.services import lista_prospeccao_service

    lista_criada = lista_prospeccao_service.criar(db_session, TENANT_ID, "1", "Evento Grande", None, None)
    contas = [
        Conta(tenant_id=TENANT_ID, icp_id=None, lista_prospeccao_id=lista_criada.id, nome=f"Empresa {i}", status="prospectada")
        for i in range(5)
    ]
    db_session.add_all(contas)
    db_session.commit()

    resultado = conta_service.excluir_lote_por_lista(db_session, TENANT_ID, "1", lista_criada.id)

    assert resultado["apagadas"] == 5
    assert db_session.query(Conta).filter(Conta.lista_prospeccao_id == lista_criada.id).count() == 0
