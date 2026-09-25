"""GATE da Fase 7 — privacidade e fronteiras de tenant na Business Network.

Uma regra só (`network.privacidade.pode_ver`) para arestas do grafo,
necessidades (intents) e feed: `publica` para a rede (menos bloqueados),
`conexoes` para as partes e conexões do autor, `privada` só para o autor.
Dado de CRM nunca atravessa. Ações que mudam a identidade pública da
empresa exigem admin (Membership). Company Claim exige empresa verificada
e CNPJ igual.
"""

import pytest

from app.models.conta import Conta
from app.models.oferta import Oferta
from app.models.perfil_empresa import PerfilEmpresa
from app.models.tenant import Tenant

A = "tenant-teste"  # usuário super_admin da fixture `client`
B = "tenant-b-rede"
C = "tenant-c-rede"
CNPJ_ACME = "11.222.333/0001-81"
BASE = "/api/v1/rede-social"


@pytest.fixture()
def rede(client, criar_usuario_autenticado):
    headers = {
        "B": criar_usuario_autenticado(B, papel="admin", email="admin@b-rede.com"),
        "C": criar_usuario_autenticado(C, papel="admin", email="admin@c-rede.com"),
        "A_user": criar_usuario_autenticado(A, papel="user", email="vendedor@a-rede.com"),
    }
    for chave in ("B", "C"):
        assert client.get(f"{BASE}/perfil", headers=headers[chave]).status_code == 200
    client.get(f"{BASE}/perfil")
    return headers


def _conectar(client, headers_origem, destino, headers_destino):
    conexao = client.post(f"{BASE}/conexoes", json={"tenant_id_destino": destino}, headers=headers_origem).json()
    resposta = client.put(f"{BASE}/conexoes/{conexao['id']}", json={"aceitar": True}, headers=headers_destino)
    assert resposta.status_code == 200, resposta.text


def _declarar(client, destino, visibilidade, headers=None, tipo="SUPPLIER_OF"):
    resposta = client.post(
        f"{BASE}/relacionamentos",
        json={"tenant_id_destino": destino, "tipo": tipo, "visibilidade": visibilidade},
        headers=headers or {},
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _tipos(client, alvo, headers=None):
    return [r["visibilidade"] for r in client.get(f"{BASE}/relacionamentos/{alvo}", headers=headers or {}).json()]


def _identidade(client, headers=None):
    return client.get(f"{BASE}/identidade", headers=headers or {}).json()["empresa"]


# --- Arestas do Business Graph ---------------------------------------------


def test_aresta_privada_so_o_autor_ve_nem_a_empresa_citada(client, rede):
    _declarar(client, B, "privada")
    assert _tipos(client, A) == ["privada"]
    assert _tipos(client, B, rede["B"]) == []
    assert _tipos(client, B, rede["C"]) == []
    empresa_b = _identidade(client, rede["B"])
    assert client.get(f"{BASE}/grafo/{empresa_b['id']}", headers=rede["B"]).json() == []


def test_aresta_de_conexoes_ve_quem_e_parte_ou_conectado_ao_autor(client, rede):
    _declarar(client, B, "conexoes")
    assert _tipos(client, B, rede["B"]) == ["conexoes"]
    assert _tipos(client, A, rede["C"]) == []
    _conectar(client, {}, C, rede["C"])
    assert _tipos(client, A, rede["C"]) == ["conexoes"]


def test_aresta_publica_some_para_empresa_bloqueada_nas_duas_direcoes(client, rede):
    _declarar(client, B, "publica")
    assert _tipos(client, A, rede["C"]) == ["publica"]
    assert client.post(f"{BASE}/bloquear/{C}").status_code == 200  # A bloqueia C
    assert _tipos(client, A, rede["C"]) == []
    assert _tipos(client, B, rede["C"]) == []


def test_connected_to_so_aparece_no_grafo_da_propria_empresa(client, rede):
    _conectar(client, {}, B, rede["B"])
    empresa_a = _identidade(client)
    proprio = client.get(f"{BASE}/grafo/{empresa_a['id']}").json()
    assert [a["type"] for a in proprio] == ["CONNECTED_TO"]
    assert client.get(f"{BASE}/grafo/{empresa_a['id']}", headers=rede["C"]).json() == []


def test_aresta_canonica_tem_todas_as_propriedades_do_par28(client, rede):
    client.post(
        f"{BASE}/relacionamentos",
        json={"tenant_id_destino": B, "tipo": "PARTNER_OF", "visibilidade": "publica",
              "valido_desde": "2026-01-01", "valido_ate": "2027-01-01"},
    )
    empresa_a = _identidade(client)
    aresta = client.get(f"{BASE}/grafo/{empresa_a['id']}", headers=rede["C"]).json()[0]
    assert {"source", "visibility", "confidence", "verification", "valid_from", "valid_until", "creator_tenant_id", "metadata"} <= set(aresta)
    assert aresta["confidence"] == "MEDIA" and aresta["verification"] == "autodeclarada"
    assert aresta["valid_from"] == "2026-01-01" and aresta["creator_tenant_id"] == A


# --- Feed, intents, diretório ------------------------------------------------


def test_bloqueio_esconde_feed_e_intents_publicas(client, rede):
    assert client.post(f"{BASE}/posts", data={"texto": "Novidade da A"}).status_code == 201
    intent = {"categoria": "software", "titulo": "Buscamos ERP", "descricao": "ERP para 50 usuários", "visibilidade": "publica"}
    assert client.post(f"{BASE}/intents", json=intent).status_code == 201
    assert [p["texto"] for p in client.get(f"{BASE}/posts", headers=rede["C"]).json()] == ["Novidade da A"]
    assert len(client.get(f"{BASE}/intents", headers=rede["C"]).json()) == 1

    client.post(f"{BASE}/bloquear/{A}", headers=rede["C"])

    assert client.get(f"{BASE}/posts", headers=rede["C"]).json() == []
    assert client.get(f"{BASE}/intents", headers=rede["C"]).json() == []
    assert client.get(f"{BASE}/posts").json()[0]["texto"] == "Novidade da A"  # autor continua vendo


def test_intent_de_conexoes_so_para_conexoes(client, rede):
    intent = {"categoria": "servico", "titulo": "Auditoria", "descricao": "d", "visibilidade": "conexoes"}
    criada = client.post(f"{BASE}/intents", json=intent).json()
    assert client.get(f"{BASE}/intents/{criada['id']}", headers=rede["C"]).status_code == 404
    _conectar(client, {}, C, rede["C"])
    assert client.get(f"{BASE}/intents/{criada['id']}", headers=rede["C"]).status_code == 200


def test_empresa_fora_do_diretorio_so_aparece_para_conexoes(client, rede):
    assert client.put(f"{BASE}/perfil/visibilidade", json={"visivel_no_diretorio": False}, headers=rede["B"]).status_code == 200
    assert B not in [e["perfil"]["tenant_id"] for e in client.get(f"{BASE}/empresas", headers=rede["C"]).json()]
    assert B not in [e["perfil"]["tenant_id"] for e in client.get(f"{BASE}/empresas").json()]
    _conectar(client, {}, B, rede["B"])
    assert B in [e["perfil"]["tenant_id"] for e in client.get(f"{BASE}/empresas").json()]


def test_dado_de_crm_nunca_atravessa_para_a_rede(client, db_session, rede):
    db_session.add(Conta(tenant_id=B, nome="Cliente Secreto da B", status="cliente"))
    db_session.add(Oferta(
        tenant_id=B, nome="Oferta Pública B", descricao="descrição pública", diferenciais=[], provas_sociais=[],
        ativo=True, margem_media=42.5, ticket_medio=98765, objecoes=["objeção confidencial"],
    ))
    db_session.commit()
    _declarar(client, A, "publica", headers=rede["B"])
    empresa_b = _identidade(client, rede["B"])

    respostas = " ".join(
        client.get(path, headers=rede["C"]).text
        for path in (
            f"{BASE}/empresas", f"{BASE}/posts", f"{BASE}/intents", f"{BASE}/relacionamentos/{B}",
            f"{BASE}/grafo/{empresa_b['id']}", f"{BASE}/membros",
        )
    )
    assert "Oferta Pública B" in respostas  # vitrine: só nome/descrição da oferta ativa
    for segredo in ("Cliente Secreto da B", "42.5", "98765", "objeção confidencial", "margem_media", "admin@b-rede.com"):
        assert segredo not in respostas, segredo


def test_membros_so_da_propria_empresa(client, rede):
    nomes = [m["nome"] for m in client.get(f"{BASE}/membros", headers=rede["B"]).json()]
    assert nomes == [f"Usuário {B}"]
    papeis = {m["papel_na_rede"] for m in client.get(f"{BASE}/membros").json()}
    assert papeis == {"ADMIN", "MEMBRO"}


# --- Membership ---------------------------------------------------------------


def test_membro_nao_muda_identidade_publica_da_empresa_mas_participa_da_rede(client, rede):
    usuario = rede["A_user"]
    assert client.put(f"{BASE}/perfil", json={"nome_exibicao": "Hack"}, headers=usuario).status_code == 403
    assert client.post(
        f"{BASE}/relacionamentos", json={"tenant_id_destino": B, "tipo": "SUPPLIER_OF"}, headers=usuario
    ).status_code == 403
    assert client.put(f"{BASE}/perfil/visibilidade", json={"visivel_no_diretorio": False}, headers=usuario).status_code == 403
    assert client.post(f"{BASE}/identidades/1/reivindicar", headers=usuario).status_code == 403
    assert client.post(f"{BASE}/posts", data={"texto": "post do vendedor"}, headers=usuario).status_code == 201
    assert client.post(f"{BASE}/conexoes", json={"tenant_id_destino": C}, headers=usuario).status_code == 201


# --- Company Identity / Claim -----------------------------------------------


def test_relacionamento_por_cnpj_cria_empresa_nao_reivindicada_sem_dado_privado(client, rede):
    resposta = client.post(
        f"{BASE}/relacionamentos/por-cnpj",
        json={"cnpj": CNPJ_ACME, "nome": "ACME Indústria", "tipo": "CUSTOMER_OF", "visibilidade": "publica"},
    )
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["tenant_id_destino"] is None and corpo["destino_reivindicado"] is False
    assert corpo["outro_tenant_nome"] == "ACME Indústria"

    aresta = client.get(f"{BASE}/grafo/{corpo['empresa_destino_id']}", headers=rede["C"]).json()[0]
    assert aresta["to_company"] == {
        "id": corpo["empresa_destino_id"], "tenant_id": None, "cnpj": "11222333000181",
        "display_name": "ACME Indústria", "status": "NAO_REIVINDICADA", "origin": "SELF_DECLARED",
    }
    # a mesma empresa citada de novo reaproveita a identidade
    outra = client.post(
        f"{BASE}/relacionamentos/por-cnpj", json={"cnpj": "11222333000181", "tipo": "PARTNER_OF"}, headers=rede["C"]
    ).json()
    assert outra["empresa_destino_id"] == corpo["empresa_destino_id"]
    assert client.post(
        f"{BASE}/relacionamentos/por-cnpj", json={"cnpj": "11222333000182", "tipo": "PARTNER_OF"}
    ).status_code == 422


def test_reivindicacao_exige_verificacao_e_cnpj_igual_e_mescla_as_arestas(client, db_session, rede, criar_usuario_autenticado):
    citada = client.post(
        f"{BASE}/relacionamentos/por-cnpj", json={"cnpj": CNPJ_ACME, "nome": "ACME", "tipo": "CUSTOMER_OF"}
    ).json()
    empresa_citada_id = citada["empresa_destino_id"]

    acme = "tenant-acme"
    headers_acme = criar_usuario_autenticado(acme, papel="admin", email="admin@acme.com")
    db_session.get(Tenant, acme).cnpj = CNPJ_ACME
    db_session.commit()
    client.get(f"{BASE}/perfil", headers=headers_acme)
    identidade = client.get(f"{BASE}/identidade", headers=headers_acme).json()
    assert [e["id"] for e in identidade["reivindicaveis"]] == [empresa_citada_id]

    # sem verificação: não reivindica
    assert client.post(f"{BASE}/identidades/{empresa_citada_id}/reivindicar", headers=headers_acme).status_code == 409
    # outra empresa verificada, CNPJ diferente: não reivindica
    db_session.query(PerfilEmpresa).filter_by(tenant_id=B).update({"status_verificacao": "verificada"})
    db_session.commit()
    assert client.post(f"{BASE}/identidades/{empresa_citada_id}/reivindicar", headers=rede["B"]).status_code == 403

    db_session.query(PerfilEmpresa).filter_by(tenant_id=acme).update({"status_verificacao": "verificada"})
    db_session.commit()
    resposta = client.post(f"{BASE}/identidades/{empresa_citada_id}/reivindicar", headers=headers_acme)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "VERIFICADA" and resposta.json()["tenant_id"] == acme

    recebidas = client.get(f"{BASE}/relacionamentos/{acme}", headers=headers_acme).json()
    assert [(r["tenant_id_origem"], r["pode_confirmar"]) for r in recebidas] == [(A, True)]
    assert client.post(f"{BASE}/relacionamentos/{recebidas[0]['id']}/confirmar", headers=headers_acme).status_code == 200
    assert client.get(f"{BASE}/grafo/{empresa_citada_id}").json() == []  # identidade antiga mesclada
    assert client.post(f"{BASE}/identidades/{empresa_citada_id}/reivindicar", headers=headers_acme).status_code == 404


def test_citar_cnpj_de_empresa_ja_na_rede_aponta_para_o_tenant(client, db_session, rede):
    db_session.get(Tenant, B).cnpj = CNPJ_ACME
    db_session.commit()
    _identidade(client, rede["B"])
    corpo = client.post(f"{BASE}/relacionamentos/por-cnpj", json={"cnpj": CNPJ_ACME, "tipo": "SUPPLIER_OF"}).json()
    assert corpo["tenant_id_destino"] == B and corpo["destino_reivindicado"] is True
