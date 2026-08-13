from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.conta import Conta
from app.models.estagio_funil import EstagioFunil
from app.models.icp import ICP
from app.models.usuario import Usuario
from app.services import atividade_service, crm_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

TENANT_ID = "tenant-teste"


def _criar_conta(db_session, **overrides) -> Conta:
    icp = ICP(
        tenant_id=TENANT_ID, grupo_id="grupo-1", nome="ICP", segmento="Tecnologia", porte="PEQUENO",
        regiao="SP", ativo=True,
    )
    db_session.add(icp)
    db_session.flush()
    dados = {"tenant_id": TENANT_ID, "icp_id": icp.id, "nome": "Conta Teste", "status": "prospectada"}
    dados.update(overrides)
    conta = Conta(**dados)
    db_session.add(conta)
    db_session.commit()
    return conta


def _criar_usuario(db_session, email="vendedor@teste.com.br") -> Usuario:
    usuario = Usuario(tenant_id=TENANT_ID, nome="Vendedor Teste", email=email, papel="user", ativo=True)
    db_session.add(usuario)
    db_session.commit()
    return usuario


def test_estagios_padrao_semeados_na_primeira_chamada(db_session):
    estagios = crm_service.garantir_estagios_padrao(db_session, TENANT_ID)

    assert len(estagios) == 5
    assert {e.tipo for e in estagios} == {"aberto", "ganho", "perdido"}
    # idempotente: chamar de novo não duplica
    assert len(crm_service.garantir_estagios_padrao(db_session, TENANT_ID)) == 5


def test_constraint_unica_impede_estagio_duplicado_no_banco(db_session):
    """Trava real contra a corrida: duas requisições concorrentes que
    ambas veem a tabela vazia não conseguem inserir o mesmo (tenant_id,
    ordem) duas vezes — a segunda falha no banco, não na aplicação."""
    db_session.add(EstagioFunil(tenant_id=TENANT_ID, nome="Descoberta", ordem=1, tipo="aberto"))
    db_session.commit()

    db_session.add(EstagioFunil(tenant_id=TENANT_ID, nome="Descoberta (duplicado)", ordem=1, tipo="aberto"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_garantir_estagios_padrao_recua_quando_insercao_colide(db_session, monkeypatch):
    """Simula a corrida real: por baixo do `db.commit()` desta chamada,
    outra transação já gravou o mesmo (tenant_id, ordem) — a função
    precisa recuar (IntegrityError -> rollback) e reler o que já está
    no banco, em vez de propagar o erro pra cima."""

    commit_original = db_session.commit
    colidiu = {"ja": False}

    def commit_que_colide_uma_vez():
        if not colidiu["ja"]:
            colidiu["ja"] = True
            db_session.rollback()
            for nome, ordem, tipo in crm_service._ESTAGIOS_PADRAO:
                db_session.add(EstagioFunil(tenant_id=TENANT_ID, nome=nome, ordem=ordem, tipo=tipo))
            commit_original()
            raise IntegrityError("simulado", params=None, orig=Exception("UNIQUE constraint"))
        commit_original()

    monkeypatch.setattr(db_session, "commit", commit_que_colide_uma_vez)

    estagios = crm_service.garantir_estagios_padrao(db_session, TENANT_ID)
    assert len(estagios) == 5


def test_criar_negocio_usa_primeiro_estagio_aberto_por_padrao(db_session):
    conta = _criar_conta(db_session)

    negocio = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, "Negócio Teste", valor=1000.0)

    estagios = crm_service.listar_estagios(db_session, TENANT_ID)
    primeiro_aberto = next(e for e in estagios if e.tipo == "aberto")
    assert negocio.estagio_id == primeiro_aberto.id
    assert negocio.origem == "manual"


def test_atualizar_negocio_edita_nome_e_valor(db_session):
    """Não havia como corrigir um negócio depois de criado, só mover de
    estágio — bug reportado."""
    conta = _criar_conta(db_session)
    negocio = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, "Nome errado", valor=100.0)

    atualizado = crm_service.atualizar_negocio(
        db_session, TENANT_ID, None, negocio.id, "Nome corrigido", 2500.0, 80
    )

    assert atualizado.nome == "Nome corrigido"
    assert atualizado.valor == 2500.0
    assert atualizado.probabilidade == 80


def test_mover_para_ganho_marca_cliente_desde_so_na_primeira_vez(db_session):
    conta = _criar_conta(db_session)
    negocio = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, "Negócio", valor=500.0)
    estagio_ganho = next(e for e in crm_service.listar_estagios(db_session, TENANT_ID) if e.tipo == "ganho")

    movido = crm_service.mover_estagio(db_session, TENANT_ID, None, negocio.id, estagio_ganho.id)
    db_session.refresh(conta)
    primeira_data = conta.cliente_desde

    assert movido.ganho_em is not None
    assert primeira_data is not None

    # mover de novo para o mesmo estágio não reseta a data
    crm_service.mover_estagio(db_session, TENANT_ID, None, negocio.id, estagio_ganho.id)
    db_session.refresh(conta)
    assert conta.cliente_desde == primeira_data


def test_mover_para_perdido_grava_motivo(db_session):
    conta = _criar_conta(db_session)
    negocio = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, "Negócio", valor=500.0)
    estagio_perdido = next(e for e in crm_service.listar_estagios(db_session, TENANT_ID) if e.tipo == "perdido")

    movido = crm_service.mover_estagio(db_session, TENANT_ID, None, negocio.id, estagio_perdido.id, motivo_perda="Sem orçamento")

    assert movido.perdido_em is not None
    assert movido.motivo_perda == "Sem orçamento"


def test_mover_para_perdido_sem_motivo_falha(db_session):
    """Pedido do usuário: motivo da perda passa a ser obrigatório."""
    conta = _criar_conta(db_session)
    negocio = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, "Negócio", valor=500.0)
    estagio_perdido = next(e for e in crm_service.listar_estagios(db_session, TENANT_ID) if e.tipo == "perdido")

    with pytest.raises(ValidacaoFalhou):
        crm_service.mover_estagio(db_session, TENANT_ID, None, negocio.id, estagio_perdido.id)
    with pytest.raises(ValidacaoFalhou):
        crm_service.mover_estagio(db_session, TENANT_ID, None, negocio.id, estagio_perdido.id, motivo_perda="   ")


def test_excluir_negocio(db_session):
    conta = _criar_conta(db_session)
    negocio = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, "Negócio a excluir", valor=500.0)
    crm_service.registrar_atividade(db_session, TENANT_ID, "1", negocio.id, "nota", "Nota qualquer")

    crm_service.excluir_negocio(db_session, TENANT_ID, None, negocio.id)

    with pytest.raises(NaoEncontrado):
        crm_service.obter_negocio(db_session, TENANT_ID, negocio.id)
    # Atividades ligadas à conta sobrevivem (perdem só o vínculo com o negócio).
    atividades_da_conta = atividade_service.listar_por_conta(db_session, TENANT_ID, conta.id)
    assert len(atividades_da_conta) >= 2  # "negócio criado" + "nota qualquer" + "negócio excluído"
    assert all(a.negocio_id is None for a in atividades_da_conta)


def test_excluir_negocio_inexistente_falha(db_session):
    with pytest.raises(NaoEncontrado):
        crm_service.excluir_negocio(db_session, TENANT_ID, None, 999999)


def test_marcar_cliente_cancelado_exige_ser_cliente(db_session):
    import pytest

    from app.services.errors import RegraNegocioViolada

    conta = _criar_conta(db_session)

    with pytest.raises(RegraNegocioViolada):
        crm_service.marcar_cliente_cancelado(db_session, TENANT_ID, None, conta.id, "teste")


def test_marcar_cliente_cancelado_apos_ganho(db_session):
    conta = _criar_conta(db_session)
    negocio = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, "Negócio", valor=500.0)
    estagio_ganho = next(e for e in crm_service.listar_estagios(db_session, TENANT_ID) if e.tipo == "ganho")
    crm_service.mover_estagio(db_session, TENANT_ID, None, negocio.id, estagio_ganho.id)

    cancelada = crm_service.marcar_cliente_cancelado(db_session, TENANT_ID, None, conta.id, "Insatisfeito")

    assert cancelada.cliente_cancelado_em is not None


def test_registrar_e_listar_atividade(db_session):
    conta = _criar_conta(db_session)
    negocio = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, "Negócio", valor=100.0)

    crm_service.registrar_atividade(db_session, TENANT_ID, "1", negocio.id, "ligacao", "Liguei para o cliente")

    atividades = crm_service.listar_atividades(db_session, TENANT_ID, negocio.id)
    # +1 automática ("negócio criado", vem primeiro) além da registrada manualmente aqui.
    assert len(atividades) == 2
    assert atividades[-1].tipo == "ligacao"
    assert atividades[-1].usuario_id == 1


def test_dashboard_funil_calcula_taxa_de_conversao(db_session):
    conta = _criar_conta(db_session)
    estagios = {e.tipo: e for e in crm_service.listar_estagios(db_session, TENANT_ID)}
    n1 = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, "N1", valor=100.0)
    n2 = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, "N2", valor=200.0)
    crm_service.mover_estagio(db_session, TENANT_ID, None, n1.id, estagios["ganho"].id)

    resultado = crm_service.dashboard_funil(db_session, TENANT_ID)

    assert resultado["taxa_conversao"] == 0.5
    ganho_resumo = next(e for e in resultado["estagios"] if e["tipo"] == "ganho")
    assert ganho_resumo["quantidade"] == 1
    assert ganho_resumo["valor_total"] == 100.0


def test_dashboard_atividade_agrupa_por_usuario(db_session):
    conta = _criar_conta(db_session)
    usuario = _criar_usuario(db_session)
    negocio = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, "Negócio", valor=0.0)

    crm_service.registrar_atividade(db_session, TENANT_ID, str(usuario.id), negocio.id, "ligacao", "Ligação 1")
    crm_service.registrar_atividade(db_session, TENANT_ID, str(usuario.id), negocio.id, "nota", "Nota 1")

    resultado = crm_service.dashboard_atividade(db_session, TENANT_ID)

    assert resultado["total_equipe"] == 2
    assert resultado["por_vendedor"][0]["usuario_id"] == usuario.id
    assert resultado["por_vendedor"][0]["quantidade"] == 2


def test_dashboard_economia_calcula_ltv_cac_churn(db_session):
    conta1 = _criar_conta(db_session, nome="Cliente 1")
    conta2 = _criar_conta(db_session, nome="Cliente 2")
    estagio_ganho = next(e for e in crm_service.listar_estagios(db_session, TENANT_ID) if e.tipo == "ganho")

    n1 = crm_service.criar_negocio(db_session, TENANT_ID, None, conta1.id, "N1", valor=1000.0)
    n2 = crm_service.criar_negocio(db_session, TENANT_ID, None, conta2.id, "N2", valor=2000.0)
    crm_service.mover_estagio(db_session, TENANT_ID, None, n1.id, estagio_ganho.id)
    crm_service.mover_estagio(db_session, TENANT_ID, None, n2.id, estagio_ganho.id)

    periodo_atual = datetime.now(UTC).strftime("%Y-%m")
    crm_service.definir_custo_aquisicao(db_session, TENANT_ID, None, periodo_atual, 3000.0)

    resultado = crm_service.dashboard_economia(db_session, TENANT_ID, periodo_atual)

    assert resultado["ltv_medio"] == 1500.0
    assert resultado["novos_clientes"] == 2
    assert resultado["cac"] == 1500.0
