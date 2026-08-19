import hashlib
import secrets

from app.models.chave_api_parceiro import ChaveApiParceiro
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant


def _criar_distribuidor_com_chave(db_session, tenant_id: str = "distribuidor-api") -> tuple[str, dict[str, str]]:
    plano = Plano(nome=f"Plano {tenant_id}", franquia_contas_mes=500, max_usuarios=20, preco_mensal=490.0)
    db_session.add(plano)
    db_session.flush()
    db_session.add(Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}", tipo="distribuidor"))
    db_session.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
    db_session.flush()

    chave_completa = f"b2bon_{secrets.token_urlsafe(16)}"
    db_session.add(
        ChaveApiParceiro(
            tenant_id=tenant_id, nome="Chave Integração", prefixo=chave_completa[:12],
            chave_hash=hashlib.sha256(chave_completa.encode()).hexdigest(),
        )
    )
    db_session.commit()
    return plano.id, {"Authorization": f"Bearer {chave_completa}"}


def test_provisionar_tenant_cria_revendedor_sob_o_distribuidor(client, db_session) -> None:
    plano_id, headers = _criar_distribuidor_com_chave(db_session)

    resposta = client.post(
        "/api/v1/parceiros/tenants",
        json={
            "tenant_id": "revenda-via-api",
            "razao_social": "Revenda Via API",
            "plano_id": plano_id,
            "nome_admin": "Admin API",
            "email_admin": "admin@revendaviaapi.com.br",
            "senha_admin": "senha12345",
        },
        headers=headers,
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["tipo"] == "revendedor"
    assert corpo["tenant_pai_id"] == "distribuidor-api"


def test_sem_chave_de_api_recusa(client, db_session) -> None:
    resposta = client.get("/api/v1/parceiros/tenants", headers={"Authorization": ""})
    assert resposta.status_code == 401


def test_chave_invalida_recusa(client, db_session) -> None:
    resposta = client.get("/api/v1/parceiros/tenants", headers={"Authorization": "Bearer chave-forjada"})
    assert resposta.status_code == 401


def test_listar_tenants_traz_a_propria_subarvore(client, db_session) -> None:
    plano_id, headers = _criar_distribuidor_com_chave(db_session, tenant_id="distribuidor-lista")
    client.post(
        "/api/v1/parceiros/tenants",
        json={
            "tenant_id": "revenda-lista-1",
            "razao_social": "Revenda Lista 1",
            "plano_id": plano_id,
            "nome_admin": "Admin",
            "email_admin": "admin@revendalista1.com.br",
            "senha_admin": "senha12345",
        },
        headers=headers,
    )

    resposta = client.get("/api/v1/parceiros/tenants", headers=headers)

    assert resposta.status_code == 200
    ids = {t["id"] for t in resposta.json()}
    assert ids == {"distribuidor-lista", "revenda-lista-1"}


def test_atualizar_licenca_fora_da_arvore_e_negado(client, db_session) -> None:
    _, headers = _criar_distribuidor_com_chave(db_session, tenant_id="distribuidor-a-lic")
    _criar_distribuidor_com_chave(db_session, tenant_id="distribuidor-b-lic")

    resposta = client.put(
        "/api/v1/parceiros/tenants/distribuidor-b-lic/licenca", json={"status": "suspensa"}, headers=headers
    )

    assert resposta.status_code == 403


def test_obter_uso_e_billing_do_proprio_tenant(client, db_session) -> None:
    _, headers = _criar_distribuidor_com_chave(db_session, tenant_id="distribuidor-uso")

    resposta_uso = client.get("/api/v1/parceiros/tenants/distribuidor-uso/uso", headers=headers)
    resposta_billing = client.get("/api/v1/parceiros/tenants/distribuidor-uso/billing", headers=headers)

    assert resposta_uso.status_code == 200
    assert set(resposta_uso.json()) == {"limite", "usado", "restante"}
    assert resposta_billing.status_code == 200
    assert resposta_billing.json()["status"] == "ativa"
