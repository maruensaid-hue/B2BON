"""Nome de empresa e de contato com a codificação trocada é corrigido na gravação e, para o que já estava gravado, pelo serviço de correção."""

import pytest

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.services import codificacao_service

TENANT_ID = "tenant-codificacao"

# O texto com a troca é montado a partir do certo, para o teste não depender do arquivo ser salvo na codificação "certa".
TROCADO_QUEBEC = "Québec".encode("utf-8").decode("latin-1")
TROCADO_SEGURANCA = "Ministère de la Sécurité publique du Québec".encode("utf-8").decode("latin-1")
TROCADO_GESTAO = "Gestão de produtos".encode("utf-8").decode("latin-1")


def _conta(db_session, nome: str, **extras) -> Conta:
    conta = Conta(tenant_id=TENANT_ID, nome=nome, status="prospectada", **extras)
    db_session.add(conta)
    db_session.commit()
    db_session.refresh(conta)
    return conta


def test_nome_da_conta_com_codificacao_trocada_e_corrigido_ao_gravar(db_session):
    assert TROCADO_QUEBEC != "Québec"  # o ponto de partida do teste está de fato trocado

    conta = _conta(db_session, TROCADO_SEGURANCA, nome_fantasia=TROCADO_QUEBEC, segmento=TROCADO_GESTAO)

    assert conta.nome == "Ministère de la Sécurité publique du Québec"
    assert conta.nome_fantasia == "Québec"
    assert conta.segmento == "Gestão de produtos"


def test_atualizar_a_conta_tambem_corrige(db_session):
    conta = _conta(db_session, "Empresa Boa")

    conta.nome = TROCADO_SEGURANCA
    db_session.commit()
    db_session.refresh(conta)

    assert conta.nome == "Ministère de la Sécurité publique du Québec"


def test_contato_tem_nome_e_cargo_corrigidos(db_session):
    conta = _conta(db_session, "Empresa Boa")
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="João".encode("utf-8").decode("latin-1"), cargo=TROCADO_GESTAO)
    db_session.add(decisor)
    db_session.commit()
    db_session.refresh(decisor)

    assert decisor.nome == "João" and decisor.cargo == "Gestão de produtos"


def test_texto_que_nao_tem_a_troca_passa_intacto(db_session):
    for nome in ("SÃO PAULO Comércio", "CÂMBIO Ltda", "José & Filhos", "Dr. Oetker Ibérica, S.A.", "parethus®", "4Asset"):
        assert _conta(db_session, nome).nome == nome


def test_campo_livre_nao_e_mexido(db_session):
    conta = _conta(db_session, "Empresa Boa", observacoes=TROCADO_GESTAO)

    assert conta.observacoes == TROCADO_GESTAO  # só os campos curtos de identificação entram


def test_servico_simula_sem_alterar_e_aplica_com_o_pedido(db_session):
    # Inserção direta (SQL) para simular o que já estava gravado antes do conserto na gravação.
    db_session.execute(
        Conta.__table__.insert(),
        [{"tenant_id": TENANT_ID, "nome": TROCADO_SEGURANCA, "status": "prospectada"}, {"tenant_id": TENANT_ID, "nome": "Empresa Boa", "status": "prospectada"}],
    )
    db_session.commit()

    simulacao = codificacao_service.corrigir_dados_gravados(db_session)

    assert simulacao["aplicado"] is False and simulacao["Conta"]["registros"] == 1
    assert simulacao["Conta"]["exemplos"] == [{"antes": TROCADO_SEGURANCA, "depois": "Ministère de la Sécurité publique du Québec"}]
    assert db_session.query(Conta).filter_by(nome=TROCADO_SEGURANCA).count() == 1  # a simulação não grava

    aplicado = codificacao_service.corrigir_dados_gravados(db_session, aplicar=True)

    assert aplicado["aplicado"] is True and aplicado["tenants_afetados"] == 1
    assert db_session.query(Conta).filter_by(nome=TROCADO_SEGURANCA).count() == 0
    assert db_session.query(Conta).filter_by(nome="Ministère de la Sécurité publique du Québec").count() == 1
    assert codificacao_service.corrigir_dados_gravados(db_session)["Conta"]["registros"] == 0  # idempotente


def test_exemplos_nunca_trazem_nome_de_pessoa(db_session):
    conta = _conta(db_session, "Empresa Boa")
    db_session.execute(
        Decisor.__table__.insert(),
        [{"tenant_id": TENANT_ID, "conta_id": conta.id, "nome": "João".encode("utf-8").decode("latin-1")}],
    )
    db_session.commit()

    relatorio = codificacao_service.corrigir_dados_gravados(db_session)

    assert relatorio["Decisor"]["registros"] == 1 and relatorio["Decisor"]["exemplos"] == []  # pessoa só entra na contagem


@pytest.mark.parametrize(
    "correto",
    [
        "Ministère de la Sécurité publique du Québec (MSP)",
        "Dr. Oetker Ibérica, S.A.",
        "parethus®",
        "Young | PM - Gestão de produtos, numa nova visão",
    ],
)
def test_nomes_reais_com_a_troca_vistos_na_lista_de_contas_sao_corrigidos(db_session, correto):
    trocado = correto.encode("utf-8").decode("latin-1")
    assert trocado != correto  # ex.: "parethusÂ®"

    assert _conta(db_session, trocado).nome == correto
