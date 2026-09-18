from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.oferta import Oferta
from app.services import crm_service, sinal_oportunidade_service

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"


def _criar_conta_com_negocio(db_session, tenant_id, valor, tipo_estagio="aberto", origem="manual", oferta_id=None):
    conta = Conta(tenant_id=tenant_id, nome="Conta Teste", status="priorizada", origem=origem)
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=tenant_id, conta_id=conta.id, nome="Decisor Teste")
    db_session.add(decisor)
    db_session.commit()

    negocio = crm_service.criar_negocio(
        db_session, tenant_id, None, conta.id, decisor.id, "Negócio Teste", valor=valor, oferta_id=oferta_id
    )
    if tipo_estagio != "aberto":
        estagio_alvo = next(e for e in crm_service.garantir_estagios_padrao(db_session, tenant_id) if e.tipo == tipo_estagio)
        crm_service.mover_estagio(db_session, tenant_id, None, negocio.id, estagio_alvo.id)
        db_session.refresh(negocio)
    return conta, decisor, negocio


def test_atribuicao_receita_soma_so_contas_da_rede(db_session):
    _criar_conta_com_negocio(db_session, TENANT_A, 1000, origem="rede_social_signal")
    _criar_conta_com_negocio(db_session, TENANT_A, 5000, origem="manual")

    resultado = sinal_oportunidade_service.calcular_atribuicao_receita(db_session, TENANT_A)

    assert resultado["contas_geradas_pela_rede"] == 1
    assert resultado["negocios_em_aberto_valor"] == 1000


def test_atribuicao_receita_separa_aberto_e_ganho(db_session):
    _criar_conta_com_negocio(db_session, TENANT_A, 1000, tipo_estagio="aberto", origem="rede_social_signal")
    _criar_conta_com_negocio(db_session, TENANT_A, 2000, tipo_estagio="ganho", origem="rede_social_signal")

    resultado = sinal_oportunidade_service.calcular_atribuicao_receita(db_session, TENANT_A)

    assert resultado["negocios_em_aberto_valor"] == 1000
    assert resultado["negocios_ganhos_valor"] == 2000


def test_atribuicao_receita_sem_contas_da_rede_retorna_zero(db_session):
    _criar_conta_com_negocio(db_session, TENANT_A, 1000, origem="manual")

    resultado = sinal_oportunidade_service.calcular_atribuicao_receita(db_session, TENANT_A)

    assert resultado["contas_geradas_pela_rede"] == 0
    assert resultado["negocios_em_aberto_valor"] == 0.0
    assert resultado["sinais_gerados"] == 0
    assert resultado["taxa_conversao_sinais"] == 0.0


def test_atribuicao_receita_isolamento_tenant(db_session):
    _criar_conta_com_negocio(db_session, TENANT_A, 1000, origem="rede_social_signal")
    _criar_conta_com_negocio(db_session, TENANT_B, 9999, origem="rede_social_signal")

    resultado = sinal_oportunidade_service.calcular_atribuicao_receita(db_session, TENANT_A)

    assert resultado["negocios_em_aberto_valor"] == 1000


def test_sugerir_expansao_conta_com_negocio_ganho_e_oferta_nunca_vinculada(db_session):
    oferta = Oferta(tenant_id=TENANT_A, nome="Oferta X", descricao="desc", ativo=True)
    db_session.add(oferta)
    db_session.commit()

    conta, decisor, negocio = _criar_conta_com_negocio(db_session, TENANT_A, 1000, tipo_estagio="ganho")

    sugestoes = sinal_oportunidade_service.sugerir_expansao(db_session, TENANT_A)

    assert len(sugestoes) == 1
    assert sugestoes[0]["conta_id"] == conta.id
    assert sugestoes[0]["oferta_id"] == oferta.id


def test_sugerir_expansao_nao_sugere_oferta_ja_vinculada(db_session):
    oferta = Oferta(tenant_id=TENANT_A, nome="Oferta X", descricao="desc", ativo=True)
    db_session.add(oferta)
    db_session.commit()

    _criar_conta_com_negocio(db_session, TENANT_A, 1000, tipo_estagio="ganho", oferta_id=oferta.id)

    sugestoes = sinal_oportunidade_service.sugerir_expansao(db_session, TENANT_A)

    assert sugestoes == []


def test_sugerir_expansao_nao_sugere_oferta_inativa(db_session):
    oferta = Oferta(tenant_id=TENANT_A, nome="Oferta Inativa", descricao="desc", ativo=False)
    db_session.add(oferta)
    db_session.commit()

    _criar_conta_com_negocio(db_session, TENANT_A, 1000, tipo_estagio="ganho")

    sugestoes = sinal_oportunidade_service.sugerir_expansao(db_session, TENANT_A)

    assert sugestoes == []


def test_sugerir_expansao_conta_sem_negocio_ganho_nao_aparece(db_session):
    oferta = Oferta(tenant_id=TENANT_A, nome="Oferta X", descricao="desc", ativo=True)
    db_session.add(oferta)
    db_session.commit()

    _criar_conta_com_negocio(db_session, TENANT_A, 1000, tipo_estagio="aberto")

    sugestoes = sinal_oportunidade_service.sugerir_expansao(db_session, TENANT_A)

    assert sugestoes == []


def test_sugerir_expansao_isolamento_tenant(db_session):
    oferta_a = Oferta(tenant_id=TENANT_A, nome="Oferta A", descricao="desc", ativo=True)
    db_session.add(oferta_a)
    db_session.commit()
    _criar_conta_com_negocio(db_session, TENANT_B, 1000, tipo_estagio="ganho")

    sugestoes = sinal_oportunidade_service.sugerir_expansao(db_session, TENANT_A)

    assert sugestoes == []
