"""Cadência para LISTA DE PROSPECÇÃO (ex.: "Importação LinkedIn"), que não tem ICP: cria, gera só para empresas da lista e não depende de ICP ativo."""

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from tests.conftest import TENANT_ID

TOQUES = [
    {"ordem": 1, "canal": "email", "intervalo_dias_apos_anterior": 0},
    {"ordem": 2, "canal": "whatsapp", "intervalo_dias_apos_anterior": 1, "template_whatsapp_id": "tpl-1"},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 4, "canal": "linkedin", "intervalo_dias_apos_anterior": 2},
    {"ordem": 5, "canal": "email", "intervalo_dias_apos_anterior": 2},
]


def _lista_com_empresa(client, db_session, nome_lista="Importação LinkedIn", com_decisor=True):
    lista = client.post("/api/v1/listas-prospeccao", json={"nome": nome_lista}).json()
    conta = Conta(tenant_id=TENANT_ID, icp_id=None, lista_prospeccao_id=lista["id"], nome="Empresa da Lista", status="prospectada", origem="linkedin")
    db_session.add(conta)
    db_session.flush()
    if com_decisor:
        db_session.add(Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Ana Conexão", cargo="CEO", linkedin_url="https://linkedin.com/in/ana"))
    db_session.commit()
    return lista, conta


def _criar(client, **extra):
    return client.post("/api/v1/cadencias", json={"nome": "Cadência da lista", "toques": TOQUES, **extra})


def test_cria_cadencia_para_lista_sem_icp_e_nao_usa_o_icp_ativo(client, db_session, onboarding_completo):
    lista, _ = _lista_com_empresa(client, db_session)
    r = _criar(client, lista_prospeccao_id=lista["id"])
    assert r.status_code == 201, r.text
    assert (r.json()["lista_prospeccao_id"], r.json()["icp_id"]) == (lista["id"], None)  # existe ICP ativo no tenant, mas a cadência da lista não o herda


def test_nao_aceita_icp_e_lista_ao_mesmo_tempo_nem_lista_inexistente(client, db_session, onboarding_completo):
    lista, _ = _lista_com_empresa(client, db_session)
    icp = db_session.query(ICP).first()
    assert _criar(client, lista_prospeccao_id=lista["id"], icp_id=icp.id).status_code == 409
    assert _criar(client, lista_prospeccao_id=999999).status_code == 404


def test_gera_mensagens_para_empresas_da_lista_mesmo_sem_nenhum_icp_ativo(client, db_session, onboarding_completo, fake_llm):
    lista, conta = _lista_com_empresa(client, db_session)
    for icp in db_session.query(ICP).all():
        icp.ativo = False  # o tenant só tem listas de prospecção
    db_session.commit()
    cadencia = _criar(client, lista_prospeccao_id=lista["id"]).json()
    r = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    assert r.status_code == 200, r.text
    assert (r.json()["contas_processadas"], r.json()["mensagens_geradas"]) == ([conta.id], 5)
    assert "lista de prospecção 'Importação LinkedIn'" in fake_llm.chamadas[0].prompt and "ICP '" not in fake_llm.chamadas[0].prompt


def test_cadencia_de_lista_recusa_empresa_de_fora_da_lista(client, db_session, onboarding_completo):
    lista, _ = _lista_com_empresa(client, db_session)
    outra_lista, conta_de_fora = _lista_com_empresa(client, db_session, "Outra lista")
    cadencia = _criar(client, lista_prospeccao_id=lista["id"]).json()
    r = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_de_fora.id]})
    assert r.status_code == 409 and "Importação LinkedIn" in r.json()["detalhe"]
    avulsa = client.post("/api/v1/leads/contas", json={"nome": "Lead Avulso"}).json()
    assert client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [avulsa["id"]]}).status_code == 409


def test_cadencia_sem_lista_e_sem_icp_continua_recusando_a_geracao(client, db_session, criar_oferta, configurar_comunicacao, criar_cadencia):
    criar_oferta()
    configurar_comunicacao()  # oferta e tom configurados, mas nenhum ICP e a cadência não é de lista
    lead = client.post("/api/v1/leads/contas", json={"nome": "Lead Avulso"}).json()
    client.post(f"/api/v1/contas/{lead['id']}/decisores", json={"nome": "Pessoa", "cargo": "CEO"})
    cadencia = criar_cadencia()
    r = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [lead["id"]]})
    assert r.status_code == 409 and "Sem ICP ativo" in r.json()["detalhe"]
