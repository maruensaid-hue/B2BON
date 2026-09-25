"""GATE da Fase 8 — sinais da rede viram oportunidades sem duplicação.

Também cobre a privacidade do matching (bloqueio, diretório, arestas
privadas, conexões de terceiros), o sinal de Intent do lado vendedor,
Relationship Intelligence e Corporate Rooms só leitura sem conexão.
"""

from app.api.deps import get_plan_limits_provider
from app.main import app
from app.models.conta import Conta
from app.models.evento_dominio import EventoDominio
from app.models.negocio import Negocio
from app.models.tenant import Tenant
from app.providers.plan_limits.stub import StubPlanLimitsProvider

A = "tenant-teste"
B = "tenant-b-sinal"
C = "tenant-c-sinal"
REDE = "/api/v1/rede-social"
INTEL = "/api/v1/inteligencia-rede"
PERFIL_SAUDE = {"nome_exibicao": "Hospital B", "cnae_principal": "8610-1/01", "porte": "grande", "sede_uf": "SP", "site": "https://hospitalb.com.br"}


def _icp(client):
    client.post("/api/v1/icp", json={
        "nome": "Healthcare", "segmento": "healthcare", "porte": "grande", "regiao": "sudeste",
        "cnae_codigos": ["8610-1/01"], "ufs": ["SP"],
    })


def _empresa(client, criar_usuario_autenticado, tenant, email, perfil=None):
    headers = criar_usuario_autenticado(tenant, papel="admin", email=email)
    client.put(f"{REDE}/perfil", json=perfil or {"nome_exibicao": tenant}, headers=headers)
    return headers


def _conectar(client, destino, headers_destino, headers_origem=None):
    conexao = client.post(f"{REDE}/conexoes", json={"tenant_id_destino": destino}, headers=headers_origem or {}).json()
    client.put(f"{REDE}/conexoes/{conexao['id']}", json={"aceitar": True}, headers=headers_destino)


def _sinais(client, headers=None):
    return client.post(f"{INTEL}/sinais/gerar", headers=headers or {}).json()


def _contagens(db):
    return (
        db.query(Conta).filter_by(tenant_id=A).count(),
        db.query(Negocio).filter_by(tenant_id=A).count(),
        db.query(EventoDominio).filter_by(tenant_id=A, tipo="OpportunityCreated").count(),
    )


# --- GATE: sem duplicação ----------------------------------------------------


def test_dois_sinais_da_mesma_empresa_viram_uma_conta_e_um_negocio(client, db_session, criar_usuario_autenticado):
    headers_b = _empresa(client, criar_usuario_autenticado, B, "admin@b-sinal.com", PERFIL_SAUDE)
    _icp(client)
    client.post(f"{REDE}/relacionamentos", json={"tenant_id_destino": A, "tipo": "LOOKING_FOR"}, headers=headers_b)
    sinais = _sinais(client)
    assert sorted(s["tipo_sinal"] for s in sinais) == ["fit_icp", "relacionamento_declarado"]

    resposta = client.post(f"{INTEL}/sinais/{sinais[0]['id']}/converter")
    assert resposta.status_code == 200, resposta.text
    conversao = resposta.json()
    assert conversao["destino"] == "crm" and conversao["negocio_id"] is not None
    assert sorted(conversao["sinais_fechados"]) == sorted(s["id"] for s in sinais)
    assert _contagens(db_session) == (1, 1, 1)

    # o outro sinal já está convertido para a mesma conta/negócio
    outro = next(s for s in client.get(f"{INTEL}/sinais").json() if s["id"] != sinais[0]["id"])
    assert (outro["status"], outro["conta_id_gerada"], outro["negocio_id_gerado"]) == (
        "convertido", conversao["conta_id"], conversao["negocio_id"],
    )
    assert client.post(f"{INTEL}/sinais/{outro['id']}/converter").status_code == 409
    assert client.post(f"{INTEL}/sinais/{sinais[0]['id']}/converter").status_code == 409

    # regenerar não reabre nem duplica; sinal novo da mesma empresa já nasce convertido
    client.post(f"{REDE}/intents", json={"categoria": "saude", "titulo": "Gestão hospitalar", "descricao": "hospital grande"})
    regenerados = _sinais(client)
    assert all(s["status"] == "convertido" and s["conta_id_gerada"] == conversao["conta_id"] for s in regenerados)
    assert _contagens(db_session) == (1, 1, 1)


def test_conversao_reaproveita_conta_e_negocio_que_ja_existiam(client, db_session, criar_usuario_autenticado):
    _empresa(client, criar_usuario_autenticado, B, "admin@b-sinal.com", PERFIL_SAUDE)
    db_session.get(Tenant, B).cnpj = "11.222.333/0001-81"
    conta = Conta(tenant_id=A, nome="Hospital B (importado)", status="cliente", cnpj="11222333000181")
    db_session.add(conta)
    db_session.commit()
    negocio = client.post("/api/v1/crm/negocios", json={
        "conta_id": conta.id, "nome": "Renovação", "valor": 1000,
        "decisor_id": client.post(f"/api/v1/contas/{conta.id}/decisores", json={"nome": "Ana"}).json()["id"],
    }).json()
    _icp(client)
    antes = _contagens(db_session)

    conversao = client.post(f"{INTEL}/sinais/{_sinais(client)[0]['id']}/converter").json()

    assert conversao["conta_id"] == conta.id and conversao["conta_reaproveitada"] is True
    assert conversao["negocio_id"] == negocio["id"] and conversao["negocio_reaproveitado"] is True
    assert _contagens(db_session) == antes


def test_conversao_para_predator_cria_so_a_conta_e_respeita_o_plano(client, db_session, criar_usuario_autenticado, monkeypatch):
    _empresa(client, criar_usuario_autenticado, B, "admin@b-sinal.com", PERFIL_SAUDE)
    _icp(client)
    sinal = _sinais(client)[0]
    monkeypatch.setitem(
        app.dependency_overrides, get_plan_limits_provider,
        lambda: StubPlanLimitsProvider(modulos_bloqueados={A: {"crm"}}),
    )
    assert client.post(f"{INTEL}/sinais/{sinal['id']}/converter?destino=crm").status_code == 403

    conversao = client.post(f"{INTEL}/sinais/{sinal['id']}/converter").json()

    assert conversao["destino"] == "predator" and conversao["negocio_id"] is None
    assert _contagens(db_session) == (1, 0, 0)
    assert db_session.get(Conta, conversao["conta_id"]).origem == "rede_social_signal"


def test_sinal_de_empresa_bloqueada_nao_converte(client, criar_usuario_autenticado):
    _empresa(client, criar_usuario_autenticado, B, "admin@b-sinal.com", PERFIL_SAUDE)
    _icp(client)
    sinal = _sinais(client)[0]
    client.post(f"{REDE}/bloquear/{B}")
    assert client.post(f"{INTEL}/sinais/{sinal['id']}/converter").status_code == 409


# --- Privacidade do matching -------------------------------------------------


def test_matching_ignora_bloqueadas_e_empresas_fora_do_diretorio(client, criar_usuario_autenticado):
    headers_b = _empresa(client, criar_usuario_autenticado, B, "admin@b-sinal.com", PERFIL_SAUDE)
    _empresa(client, criar_usuario_autenticado, C, "admin@c-sinal.com", {**PERFIL_SAUDE, "nome_exibicao": "Hospital C"})
    _icp(client)
    icp_id = client.get("/api/v1/icp").json()[0]["id"]
    assert {f["tenant_id_candidato"] for f in client.get(f"{INTEL}/fit-icp?icp_id={icp_id}").json()} >= {B, C}

    client.put(f"{REDE}/perfil/visibilidade", json={"visivel_no_diretorio": False}, headers=headers_b)
    client.post(f"{REDE}/bloquear/{C}")

    candidatos = {f["tenant_id_candidato"] for f in client.get(f"{INTEL}/fit-icp?icp_id={icp_id}").json()}
    assert B not in candidatos and C not in candidatos
    assert _sinais(client) == []


def test_aresta_privada_nao_vira_sinal_para_a_empresa_citada(client, criar_usuario_autenticado):
    headers_b = _empresa(client, criar_usuario_autenticado, B, "admin@b-sinal.com")
    client.post(
        f"{REDE}/relacionamentos", json={"tenant_id_destino": A, "tipo": "LOOKING_FOR", "visibilidade": "privada"},
        headers=headers_b,
    )
    assert _sinais(client) == []


def test_terceiro_nao_descobre_relacionamento_privado_nem_conexao_de_outros_pelos_matches(client, criar_usuario_autenticado):
    headers_b = _empresa(client, criar_usuario_autenticado, B, "admin@b-sinal.com",
                         {"nome_exibicao": "Fornecedor B", "produtos_servicos": ["software hospitalar"]})
    headers_c = _empresa(client, criar_usuario_autenticado, C, "admin@c-sinal.com")
    intent = client.post(f"{REDE}/intents", json={
        "categoria": "software", "titulo": "Software hospitalar", "descricao": "software para hospital", "visibilidade": "publica",
    }).json()
    client.post(f"{REDE}/relacionamentos", json={"tenant_id_destino": B, "tipo": "PARTNER_OF", "visibilidade": "privada"})
    _conectar(client, B, headers_b)

    vistos_pelo_autor = client.get(f"{INTEL}/intents/{intent['id']}/matches").json()
    vistos_por_terceiro = client.get(f"{INTEL}/intents/{intent['id']}/matches", headers=headers_c).json()

    sinais_autor = next(m for m in vistos_pelo_autor if m["tenant_id_candidato"] == B)["signals"]
    assert any("conexão aceita" in s for s in sinais_autor) and any("PARTNER_OF" in s for s in sinais_autor)
    sinais_terceiro = next(m for m in vistos_por_terceiro if m["tenant_id_candidato"] == B)["signals"]
    assert sinais_terceiro == []


# --- Intent Intelligence (lado vendedor) --------------------------------------


def test_intent_publica_compativel_vira_sinal_para_o_vendedor(client, criar_usuario_autenticado):
    client.put(f"{REDE}/perfil", json={"nome_exibicao": "A Software", "produtos_servicos": ["software hospitalar"]})
    headers_b = _empresa(client, criar_usuario_autenticado, B, "admin@b-sinal.com")
    client.post(f"{REDE}/intents", headers=headers_b, json={
        "categoria": "software", "titulo": "Software hospitalar", "descricao": "procuramos software", "visibilidade": "conexoes",
    })
    assert [s for s in _sinais(client) if s["tipo_sinal"] == "intent_compativel"] == []

    _conectar(client, B, headers_b)
    sinal = next(s for s in _sinais(client) if s["tipo_sinal"] == "intent_compativel")
    assert sinal["tenant_id_alvo"] == B and "Software hospitalar" in sinal["motivo"]
    assert sinal["evidencias"][0].startswith("intent:")


# --- Relationship Intelligence ------------------------------------------------


def test_forca_do_relacionamento_explicada(client, criar_usuario_autenticado):
    headers_b = _empresa(client, criar_usuario_autenticado, B, "admin@b-sinal.com")
    _conectar(client, B, headers_b)
    rel = client.post(f"{REDE}/relacionamentos", json={"tenant_id_destino": B, "tipo": "SUPPLIER_OF"}).json()
    client.post(f"{REDE}/relacionamentos/{rel['id']}/confirmar", headers=headers_b)
    client.post(f"{REDE}/mensagens", json={"tenant_id_destinatario": B, "texto": "Olá"})

    saude = next(s for s in client.get(f"{INTEL}/saude-relacionamentos").json() if s["tenant_id_alvo"] == B)

    assert saude["forca"] == "FORTE" and saude["conectadas"] is True
    assert saude["relacionamentos"] == [{"tipo": "SUPPLIER_OF", "verificacao": "confirmada_pela_contraparte", "confianca": "ALTA"}]
    assert len(saude["motivos"]) == 3


# --- Corporate Rooms ----------------------------------------------------------


def test_sala_so_das_duas_empresas_e_so_leitura_sem_conexao(client, criar_usuario_autenticado):
    headers_b = _empresa(client, criar_usuario_autenticado, B, "admin@b-sinal.com")
    headers_c = _empresa(client, criar_usuario_autenticado, C, "admin@c-sinal.com")
    assert client.post(f"{REDE}/salas", json={"tenant_id_alvo": B}).status_code == 409  # sem conexão
    _conectar(client, B, headers_b)
    sala = client.post(f"{REDE}/salas", json={"tenant_id_alvo": B}).json()
    canal = client.get(f"{REDE}/salas/{sala['id']}/canais").json()[0]
    assert client.post(f"{REDE}/salas/canais/{canal['id']}/mensagens", json={"texto": "proposta"}).status_code == 201

    assert client.get(f"{REDE}/salas/{sala['id']}/canais", headers=headers_c).status_code == 403
    assert client.get(f"{REDE}/salas/canais/{canal['id']}/mensagens", headers=headers_c).status_code == 403

    client.post(f"{REDE}/bloquear/{B}")
    assert client.post(f"{REDE}/salas/canais/{canal['id']}/mensagens", json={"texto": "x"}).status_code == 409
    assert [m["texto"] for m in client.get(f"{REDE}/salas/canais/{canal['id']}/mensagens", headers=headers_b).json()] == ["proposta"]
