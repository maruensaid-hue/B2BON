"""Isolamento na hierarquia de tenants (V5.2.1): pai ve a sub-arvore; filho nao ve pai nem irmao; estranho nao ve ninguem.

Cenario: PAI -> {FILHO_1, FILHO_2}; ESTRANHO sem relacao. Cada tenant tem uma conta com nome unico."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.conta import Conta
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auth_service

PAI, FILHO_1, FILHO_2, ESTRANHO = "t-pai", "t-filho-1", "t-filho-2", "t-estranho"
NOME_CONTA = {t: f"Conta confidencial do {t} Ltda" for t in (PAI, FILHO_1, FILHO_2, ESTRANHO)}
ROTAS_COM_TENANT_SELECIONADO = ["/api/v1/leads/contas", "/api/v1/saude-contas/dashboard", "/api/v1/saude-contas/ranking", "/api/v1/registro-oportunidade"]


@pytest.fixture()
def arvore(db_session, client):  # `client` instala os overrides (banco/provedores de teste); sem ele o app cairia no dev.db
    plano = Plano(nome="Plano Hierarquia", franquia_contas_mes=100, max_usuarios=10, preco_mensal=0.0,
                  modulos_contratados=["map", "predator", "crm"])
    db_session.add(plano)
    db_session.flush()
    for tenant_id, pai in ((PAI, None), (FILHO_1, PAI), (FILHO_2, PAI), (ESTRANHO, None)):
        db_session.add(Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}", tenant_pai_id=pai))
    db_session.flush()
    cabecalhos = {}
    for tenant_id in (PAI, FILHO_1, FILHO_2, ESTRANHO):
        db_session.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
        db_session.add(Conta(tenant_id=tenant_id, nome=NOME_CONTA[tenant_id], dominio=f"{tenant_id}.com.br", status="prospectada"))
        usuario = Usuario(tenant_id=tenant_id, nome=f"Admin {tenant_id}", email=f"admin@{tenant_id}.com.br", papel="admin", ativo=True)
        db_session.add(usuario)
        db_session.flush()
        cabecalhos[tenant_id] = {"Authorization": f"Bearer {auth_service.gerar_token(usuario)}"}
    db_session.commit()
    return cabecalhos


def _chamar(cabecalho, metodo, url, **kw):
    return TestClient(app, raise_server_exceptions=False).request(metodo, url, headers=cabecalho, **kw)


@pytest.mark.parametrize("rota", ROTAS_COM_TENANT_SELECIONADO)
@pytest.mark.parametrize(("quem", "alvo"), [(FILHO_1, PAI), (FILHO_1, FILHO_2), (FILHO_2, FILHO_1), (ESTRANHO, PAI), (ESTRANHO, FILHO_1), (PAI, ESTRANHO)])
def test_nao_da_para_dar_zoom_em_tenant_fora_da_propria_subarvore(arvore, rota, quem, alvo):
    resposta = _chamar(arvore[quem], "GET", rota, params={"tenant_id_selecionado": alvo})

    assert resposta.status_code in (403, 404), f"{quem} viu {alvo} em {rota}: {resposta.status_code}"
    assert NOME_CONTA[alvo] not in resposta.text


@pytest.mark.parametrize("rota", ["/api/v1/leads/contas"])
@pytest.mark.parametrize(("quem", "nao_pode_ver"), [(FILHO_1, [PAI, FILHO_2, ESTRANHO]), (FILHO_2, [PAI, FILHO_1, ESTRANHO]), (ESTRANHO, [PAI, FILHO_1, FILHO_2]), (PAI, [ESTRANHO])])
def test_listagem_sem_selecao_nunca_traz_conta_de_fora_da_subarvore(arvore, rota, quem, nao_pode_ver):
    resposta = _chamar(arvore[quem], "GET", rota)

    assert resposta.status_code == 200
    assert NOME_CONTA[quem] in resposta.text
    for alheio in nao_pode_ver:
        assert NOME_CONTA[alheio] not in resposta.text, f"{quem} recebeu conta de {alheio}"


def test_pai_enxerga_filhos_por_desenho(arvore):
    resposta = _chamar(arvore[PAI], "GET", "/api/v1/leads/contas", params={"tenant_id_selecionado": FILHO_1})

    assert resposta.status_code == 200
    assert NOME_CONTA[FILHO_1] in resposta.text and NOME_CONTA[FILHO_2] not in resposta.text


@pytest.mark.parametrize(("quem", "alvo"), [(FILHO_1, PAI), (FILHO_1, FILHO_2), (ESTRANHO, PAI), (ESTRANHO, FILHO_1)])
def test_admin_nao_desativa_nem_exclui_nem_altera_licenca_de_tenant_fora_da_subarvore(arvore, db_session, quem, alvo):
    for metodo, url, corpo in (
        ("POST", f"/api/v1/admin/tenants/{alvo}/desativar", None),
        ("DELETE", f"/api/v1/admin/tenants/{alvo}", None),
        ("GET", f"/api/v1/admin/tenants/{alvo}/licenca", None),
    ):
        resposta = _chamar(arvore[quem], metodo, url, **({"json": corpo} if corpo else {}))
        assert resposta.status_code in (403, 404), f"{quem} -> {metodo} {url}: {resposta.status_code} {resposta.text[:120]}"

    db_session.expire_all()
    alvo_tenant = db_session.get(Tenant, alvo)
    assert alvo_tenant is not None and alvo_tenant.ativo is not False
    assert db_session.query(Usuario).filter_by(tenant_id=alvo, ativo=True).count() == 1


@pytest.mark.parametrize(("quem", "nao_pode_ver"), [(FILHO_1, [PAI, FILHO_2, ESTRANHO]), (ESTRANHO, [PAI, FILHO_1, FILHO_2])])
def test_listagem_de_tenants_so_traz_a_propria_subarvore(arvore, quem, nao_pode_ver):
    resposta = _chamar(arvore[quem], "GET", "/api/v1/admin/tenants")

    assert resposta.status_code in (200, 403)  # sem gestão hierárquica a listagem inteira é negada
    for alheio in nao_pode_ver:
        assert alheio not in resposta.text


# --- API de parceiros por chave: o tenant do caminho nunca pode sair da árvore da chave --------------------------------------------------


@pytest.fixture()
def chaves(arvore, db_session):
    import hashlib
    import secrets

    from app.models.chave_api_parceiro import ChaveApiParceiro

    cabecalhos = {}
    for tenant_id in (PAI, FILHO_1, ESTRANHO):
        completa = f"b2bon_{secrets.token_urlsafe(16)}"
        db_session.add(ChaveApiParceiro(tenant_id=tenant_id, nome="Chave", prefixo=completa[:12], chave_hash=hashlib.sha256(completa.encode()).hexdigest()))
        cabecalhos[tenant_id] = {"Authorization": f"Bearer {completa}"}
    db_session.commit()
    return cabecalhos


@pytest.mark.parametrize(("dono_da_chave", "alvo"), [(FILHO_1, PAI), (FILHO_1, FILHO_2), (ESTRANHO, PAI), (ESTRANHO, FILHO_1), (PAI, ESTRANHO)])
def test_chave_de_parceiro_nao_alcanca_tenant_fora_da_propria_arvore(chaves, dono_da_chave, alvo):
    for metodo, url, corpo in (
        ("GET", f"/api/v1/parceiros/tenants/{alvo}/uso", None),
        ("GET", f"/api/v1/parceiros/tenants/{alvo}/billing", None),
        ("PUT", f"/api/v1/parceiros/tenants/{alvo}/licenca", {"plano_id": 1, "status": "suspensa"}),
    ):
        resposta = _chamar(chaves[dono_da_chave], metodo, url, **({"json": corpo} if corpo else {}))
        assert resposta.status_code in (403, 404), f"chave de {dono_da_chave} -> {metodo} {url}: {resposta.status_code}"


def test_chave_de_parceiro_enxerga_a_propria_arvore_por_desenho(chaves):
    assert _chamar(chaves[PAI], "GET", f"/api/v1/parceiros/tenants/{FILHO_1}/billing").status_code == 200


def test_listagem_de_parceiro_nao_traz_tenant_de_fora(chaves):
    resposta = _chamar(chaves[FILHO_1], "GET", "/api/v1/parceiros/tenants")

    assert resposta.status_code == 200
    ids = {t["id"] for t in resposta.json()}  # o filho conhece o próprio `tenant_pai_id`; o que não pode é o pai/irmão/estranho aparecer como item
    assert ids <= {FILHO_1}
