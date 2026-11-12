"""Toque com texto fixo: a geração usa o texto escrito por quem montou a cadência (com [Nome] e [Empresa]) em vez de chamar a IA."""

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from tests.conftest import TENANT_ID

TEXTO = "Olá, [Nome],\n\nA [Empresa] já tem palestrante para a convenção?\n\nMaruen"


def _toques(texto_no_primeiro: bool = True):
    primeiro = {"ordem": 1, "canal": "email", "intervalo_dias_apos_anterior": 0}
    if texto_no_primeiro:
        primeiro |= {"texto_fixo": TEXTO, "assunto_fixo": "Convenção da [Empresa]"}
    return [
        primeiro,
        {"ordem": 2, "canal": "linkedin", "intervalo_dias_apos_anterior": 2, "texto_fixo": "[Nome], achei que valia conectar."},
        {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 3},
        {"ordem": 4, "canal": "email", "intervalo_dias_apos_anterior": 3},
        {"ordem": 5, "canal": "email", "intervalo_dias_apos_anterior": 3},
    ]


def _lista_com_empresa(client, db_session, nome_decisor="ana souza"):
    lista = client.post("/api/v1/listas-prospeccao", json={"nome": "Lista da palestra"}).json()
    conta = Conta(tenant_id=TENANT_ID, icp_id=None, lista_prospeccao_id=lista["id"], nome="Acme Ltda", status="prospectada", origem="lista_prospeccao")
    db_session.add(conta)
    db_session.flush()
    db_session.add(Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome=nome_decisor, cargo="Diretora", email="ana@acme.com.br"))
    db_session.commit()
    return lista, conta


def _criar(client, lista_id, toques):
    return client.post("/api/v1/cadencias", json={"nome": "Palestra", "toques": toques, "lista_prospeccao_id": lista_id})


def test_toque_com_texto_fixo_nao_chama_a_ia_e_troca_os_marcadores(client, db_session, onboarding_completo, fake_llm):
    lista, conta = _lista_com_empresa(client, db_session)
    cadencia = _criar(client, lista["id"], _toques()).json()

    r = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    assert r.status_code == 200, r.text
    assert r.json()["mensagens_geradas"] == 5
    assert len(fake_llm.chamadas) == 3  # só os 3 toques sem texto fixo foram para a IA
    mensagens = db_session.query(Mensagem).filter_by(tenant_id=TENANT_ID).order_by(Mensagem.id).all()
    primeira, segunda = mensagens[0], mensagens[1]
    assert primeira.conteudo.startswith("Olá, Ana,\n\nA Acme Ltda já tem palestrante")
    assert primeira.assunto == "Convenção da Acme Ltda"
    assert segunda.conteudo.startswith("Ana, achei que valia conectar.")
    assert segunda.assunto is None


def test_cadencia_toda_em_texto_fixo_gera_sem_ia(client, db_session, onboarding_completo, fake_llm):
    lista, conta = _lista_com_empresa(client, db_session)
    toques = [
        {"ordem": i + 1, "canal": "linkedin" if i == 1 else "email", "intervalo_dias_apos_anterior": 0 if i == 0 else 3,
         "texto_fixo": f"Olá, [Nome]! Toque {i + 1}.", "assunto_fixo": f"Assunto {i + 1}"}
        for i in range(5)
    ]
    cadencia = _criar(client, lista["id"], toques).json()

    r = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    assert (r.status_code, r.json()["mensagens_geradas"], r.json()["toques_falha_ia"]) == (200, 5, 0)
    assert fake_llm.chamadas == []


def test_sem_nome_a_saudacao_fica_so_com_a_pontuacao(client, db_session, onboarding_completo, fake_llm):
    lista, conta = _lista_com_empresa(client, db_session, nome_decisor="")
    cadencia = _criar(client, lista["id"], _toques()).json()

    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    primeira = db_session.query(Mensagem).filter_by(tenant_id=TENANT_ID).order_by(Mensagem.id).first()
    assert primeira.conteudo.startswith("Olá!\n\nA Acme Ltda")


def test_email_com_texto_fixo_exige_assunto(client, db_session, onboarding_completo):
    lista, _ = _lista_com_empresa(client, db_session)
    toques = _toques()
    toques[0].pop("assunto_fixo")

    assert _criar(client, lista["id"], toques).status_code == 422


def test_definir_e_desligar_texto_fixo_de_um_toque(client, db_session, onboarding_completo):
    lista, _ = _lista_com_empresa(client, db_session)
    cadencia = _criar(client, lista["id"], _toques(texto_no_primeiro=False)).json()
    toque = client.get(f"/api/v1/cadencias/{cadencia['id']}/toques").json()[0]
    url = f"/api/v1/cadencias/{cadencia['id']}/toques/{toque['id']}/texto-fixo"

    sem_assunto = client.put(url, json={"texto_fixo": TEXTO})
    ligado = client.put(url, json={"texto_fixo": TEXTO, "assunto_fixo": "Convenção"})
    desligado = client.put(url, json={"texto_fixo": "  "})

    assert sem_assunto.status_code == 422
    assert (ligado.status_code, ligado.json()["texto_fixo"], ligado.json()["assunto_fixo"]) == (200, TEXTO, "Convenção")
    assert (desligado.json()["texto_fixo"], desligado.json()["assunto_fixo"]) == (None, None)
