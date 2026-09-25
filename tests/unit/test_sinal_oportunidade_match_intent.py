import pytest

from app.models.perfil_empresa import PerfilEmpresa
from app.services import intent_service, rede_social_service, relacionamento_empresarial_service, sinal_oportunidade_service
from app.services.errors import NaoEncontrado
from tests.fakes import FakeLLMProvider

pytestmark = pytest.mark.usefixtures("tenants_da_rede")

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"
TENANT_C = "tenant-terceiro"


def _criar_intent(db_session, tenant_id, **overrides):
    dados = {
        "categoria": "backup",
        "titulo": "Backup imutavel para 500 endpoints",
        "descricao": "Procuramos solucao de backup imutavel resistente a ransomware.",
        "requisitos": ["imutabilidade"],
        "faixa_orcamento": None,
        "localizacao": None,
        "prazo": None,
        "perfil_fornecedor_desejado": None,
        "visibilidade": "publica",
    }
    dados.update(overrides)
    return intent_service.criar(db_session, tenant_id, None, **dados)


def _criar_perfil(db_session, tenant_id, **overrides) -> PerfilEmpresa:
    dados = {"tenant_id": tenant_id, "nome_exibicao": f"Empresa {tenant_id}"}
    dados.update(overrides)
    perfil = PerfilEmpresa(**dados)
    db_session.add(perfil)
    db_session.commit()
    return perfil


def test_match_por_palavra_chave_em_comum(db_session):
    intent = _criar_intent(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, produtos_servicos=["backup imutavel", "disaster recovery"])

    matches = sinal_oportunidade_service.sugerir_fornecedores_para_intent(db_session, TENANT_A, intent["id"])

    assert len(matches) == 1
    assert matches[0]["tenant_id_candidato"] == TENANT_B
    assert matches[0]["match_score"] > 0
    assert any("backup" in motivo for motivo in matches[0]["match_reasons"])


def test_sem_palavra_em_comum_e_sem_sinal_nao_aparece(db_session):
    intent = _criar_intent(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, produtos_servicos=["consultoria juridica"])

    matches = sinal_oportunidade_service.sugerir_fornecedores_para_intent(db_session, TENANT_A, intent["id"])

    assert matches == []


def test_boost_por_conexao_aceita_mesmo_sem_palavra_em_comum(db_session):
    intent = _criar_intent(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, produtos_servicos=["consultoria juridica"])
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)
    rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=True)

    matches = sinal_oportunidade_service.sugerir_fornecedores_para_intent(db_session, TENANT_A, intent["id"])

    assert len(matches) == 1
    assert any("conex" in sinal.lower() for sinal in matches[0]["signals"])


def test_boost_por_relacionamento_declarado(db_session):
    intent = _criar_intent(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, produtos_servicos=["consultoria juridica"])
    relacionamento_empresarial_service.declarar(db_session, TENANT_A, None, TENANT_B, "LOOKING_FOR", "publica")

    matches = sinal_oportunidade_service.sugerir_fornecedores_para_intent(db_session, TENANT_A, intent["id"])

    assert len(matches) == 1
    assert any("LOOKING_FOR" in sinal for sinal in matches[0]["signals"])


def test_matches_ordenados_por_score_desc(db_session):
    intent = _criar_intent(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, produtos_servicos=["backup"])
    _criar_perfil(db_session, TENANT_C, produtos_servicos=["backup imutavel ransomware"])

    matches = sinal_oportunidade_service.sugerir_fornecedores_para_intent(db_session, TENANT_A, intent["id"])

    assert [m["tenant_id_candidato"] for m in matches] == [TENANT_C, TENANT_B]


def test_sugerir_fornecedores_intent_inexistente_levanta_erro(db_session):
    try:
        sinal_oportunidade_service.sugerir_fornecedores_para_intent(db_session, TENANT_A, 9999)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_explicar_match_com_ia_usa_apenas_motivos_calculados(db_session):
    intent = _criar_intent(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, produtos_servicos=["backup imutavel"])
    fake_llm = FakeLLMProvider(respostas=["Empresa B oferece backup imutavel, compatível com a necessidade."])

    explicacao = sinal_oportunidade_service.explicar_match_com_ia(db_session, intent["id"], TENANT_B, fake_llm)

    assert explicacao == "Empresa B oferece backup imutavel, compatível com a necessidade."
    prompt = fake_llm.chamadas[0].prompt
    assert "backup" in prompt.lower()
    assert "não invente" in prompt.lower()


def test_explicar_match_sem_match_plausivel_levanta_erro(db_session):
    intent = _criar_intent(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, produtos_servicos=["consultoria juridica"])
    fake_llm = FakeLLMProvider(respostas=["não deveria chamar"])

    try:
        sinal_oportunidade_service.explicar_match_com_ia(db_session, intent["id"], TENANT_B, fake_llm)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass
    assert fake_llm.chamadas == []
