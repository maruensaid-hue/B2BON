from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.oferta import Oferta
from app.services import atividade_service, conta_service
from app.services.errors import NaoEncontrado
from tests.fakes import FakeLLMProvider

TENANT_ID = "tenant-teste"


def _criar_conta(db_session, icp: ICP | None = None, cargo_decisor: str | None = "Diretor Financeiro") -> tuple:
    conta = Conta(
        tenant_id=TENANT_ID, nome="Conta Teste", status="priorizada", segmento="saude", porte="grande",
        regiao="sudeste", icp_id=icp.id if icp else None,
    )
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste", cargo=cargo_decisor)
    db_session.add(decisor)
    db_session.commit()
    return conta, decisor


def test_sugerir_estrategia_venda_chama_llm_com_dados_da_conta(db_session):
    conta, decisor = _criar_conta(db_session)
    llm = FakeLLMProvider()

    resultado = conta_service.sugerir_estrategia_venda(db_session, TENANT_ID, conta.id, llm)

    assert "estrategia" in resultado
    assert len(llm.chamadas) == 1
    prompt = llm.chamadas[0].prompt
    assert "Conta Teste" in prompt
    assert "Decisor Teste" in prompt
    assert "ECONOMIC_BUYER" in prompt


def test_sugerir_estrategia_venda_sem_icp_nao_cita_oferta(db_session):
    conta, decisor = _criar_conta(db_session)
    llm = FakeLLMProvider()

    conta_service.sugerir_estrategia_venda(db_session, TENANT_ID, conta.id, llm)

    assert "Nenhuma oferta ativa" in llm.chamadas[0].prompt


def test_sugerir_estrategia_venda_com_icp_e_oferta_ativa_cita_oferta(db_session):
    icp = ICP(tenant_id=TENANT_ID, grupo_id="grupo-1", nome="ICP Saúde", segmento="saude", porte="grande", regiao="sudeste", ativo=True)
    db_session.add(icp)
    db_session.flush()
    db_session.add(Oferta(tenant_id=TENANT_ID, icp_id=icp.id, nome="Backup Imutável", descricao="Solução de backup", ativo=True))
    db_session.commit()
    conta, decisor = _criar_conta(db_session, icp=icp)
    llm = FakeLLMProvider()

    conta_service.sugerir_estrategia_venda(db_session, TENANT_ID, conta.id, llm)

    assert "Backup Imutável" in llm.chamadas[0].prompt


def test_sugerir_estrategia_venda_cita_atividades_recentes(db_session):
    conta, decisor = _criar_conta(db_session)
    atividade_service.registrar(db_session, TENANT_ID, conta_id=conta.id, tipo="nota", descricao="Cliente pediu proposta")
    llm = FakeLLMProvider()

    conta_service.sugerir_estrategia_venda(db_session, TENANT_ID, conta.id, llm)

    assert "Cliente pediu proposta" in llm.chamadas[0].prompt


def test_sugerir_estrategia_venda_conta_inexistente_levanta_erro(db_session):
    llm = FakeLLMProvider()
    try:
        conta_service.sugerir_estrategia_venda(db_session, TENANT_ID, 9999, llm)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_sugerir_estrategia_venda_isolamento_tenant(db_session):
    conta, decisor = _criar_conta(db_session)
    llm = FakeLLMProvider()

    try:
        conta_service.sugerir_estrategia_venda(db_session, "tenant-outro", conta.id, llm)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass
