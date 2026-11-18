"""Quadro "Clientes inadimplentes" do MAP (parcelas dos negócios ganhos + licenças da B2B ON) e anotações da daily do gestor (pedido do PO, 18/11/2026)."""

from datetime import UTC, date, datetime, timedelta

from app.models.conta import Conta
from app.models.estagio_funil import EstagioFunil
from app.models.licenca import Licenca
from app.models.negocio import Negocio
from app.models.plano import Plano
from app.models.representante import Representante
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import inadimplencia_service, nota_daily_service

TENANT_ID = "tenant-teste"
HOJE = inadimplencia_service.hoje_brasilia()


def _tenant(db, tenant_id: str, tipo: str = "cliente", pai: str | None = None, representante_id: int | None = None) -> Tenant:
    tenant = db.query(Tenant).filter_by(id=tenant_id).one_or_none()
    if tenant is None:
        tenant = Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}", tipo=tipo, tenant_pai_id=pai, representante_id=representante_id)
        db.add(tenant)
    else:
        tenant.tipo, tenant.tenant_pai_id, tenant.representante_id = tipo, pai, representante_id
    db.commit()
    return tenant


def _usuario_id(db, email: str) -> int:
    return db.query(Usuario).filter_by(email=email).one().id


def _negocio_ganho(db, tenant_id: str, vendedor_id: int | None, nome: str = "Cliente") -> Negocio:
    estagio = db.query(EstagioFunil).filter_by(tenant_id=tenant_id, tipo="ganho").first()
    if estagio is None:
        estagio = EstagioFunil(tenant_id=tenant_id, nome="Ganho", ordem=9, tipo="ganho")
        db.add(estagio)
        db.flush()
    conta = Conta(tenant_id=tenant_id, nome=nome, status="cliente", vendedor_usuario_id=vendedor_id)
    db.add(conta)
    db.flush()
    negocio = Negocio(tenant_id=tenant_id, conta_id=conta.id, vendedor_usuario_id=vendedor_id, estagio_id=estagio.id, nome=f"Venda {nome}",
                      valor=3000, origem="manual", ganho_em=datetime.now(UTC).replace(tzinfo=None))
    db.add(negocio)
    db.commit()
    return negocio


def _lancar(client, headers, negocio_id: int, valor: float, vencimento: date, **extra) -> dict:
    resposta = client.post(f"/api/v1/crm/negocios/{negocio_id}/parcelas",
                           json={"valor": valor, "vencimento": vencimento.isoformat(), **extra}, headers=headers)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


# --- Parcelas ------------------------------------------------------------------------------------------------------------------------------------------

def test_vendedor_lanca_parcelas_e_so_a_vencida_sem_pagamento_entra_no_quadro(client, db_session, criar_usuario_autenticado):
    headers = criar_usuario_autenticado(TENANT_ID, papel="user", email="vend-parc@teste.com.br")
    negocio = _negocio_ganho(db_session, TENANT_ID, _usuario_id(db_session, "vend-parc@teste.com.br"), "Padaria Sol")

    vencida = _lancar(client, headers, negocio.id, 1000, HOJE - timedelta(days=5))
    paga = _lancar(client, headers, negocio.id, 1000, HOJE - timedelta(days=35))
    _lancar(client, headers, negocio.id, 1000, HOJE)  # vence hoje: ainda não está em atraso
    assert [vencida["numero"], paga["numero"]] == [1, 2]
    resp = client.put(f"/api/v1/crm/negocios/{negocio.id}/parcelas/{paga['id']}",
                      json={"valor": 1000, "vencimento": (HOJE - timedelta(days=35)).isoformat(), "pago_em": (HOJE - timedelta(days=34)).isoformat()},
                      headers=headers)
    assert resp.status_code == 200 and resp.json()["pago_em"]

    quadro = client.get("/api/v1/map/inadimplencia/parcelas", headers=headers).json()
    assert [linha["parcela_id"] for linha in quadro["linhas"]] == [vencida["id"]]
    linha = quadro["linhas"][0]
    assert linha["cliente"] == "Padaria Sol" and linha["dias_atraso"] == 5 and linha["valor"] == 1000
    assert quadro["resumo"] == {"total_em_atraso": 1000, "quantidade": 1, "clientes": 1, "maior_atraso_dias": 5}

    lista = client.get(f"/api/v1/crm/negocios/{negocio.id}/parcelas", headers=headers).json()
    assert lista["ganho"] is True and len(lista["parcelas"]) == 3
    assert [p["em_atraso"] for p in lista["parcelas"]] == [False, True, False]


def test_parcela_so_em_negocio_ganho(client, db_session):
    negocio = _negocio_ganho(db_session, TENANT_ID, None, "Aberto")
    negocio.ganho_em = None
    db_session.commit()
    resp = client.post(f"/api/v1/crm/negocios/{negocio.id}/parcelas", json={"valor": 10, "vencimento": HOJE.isoformat()})
    assert resp.status_code == 422


def test_vendedor_nao_ve_nem_lanca_parcela_de_negocio_alheio(client, db_session, criar_usuario_autenticado):
    headers_a = criar_usuario_autenticado(TENANT_ID, papel="user", email="vend-a@teste.com.br")
    headers_b = criar_usuario_autenticado(TENANT_ID, papel="user", email="vend-b@teste.com.br")
    negocio_a = _negocio_ganho(db_session, TENANT_ID, _usuario_id(db_session, "vend-a@teste.com.br"), "Cliente do A")
    _lancar(client, headers_a, negocio_a.id, 500, HOJE - timedelta(days=2))

    assert client.get("/api/v1/map/inadimplencia/parcelas", headers=headers_b).json()["linhas"] == []
    assert client.get(f"/api/v1/crm/negocios/{negocio_a.id}/parcelas", headers=headers_b).status_code == 404
    resp = client.post(f"/api/v1/crm/negocios/{negocio_a.id}/parcelas", json={"valor": 1, "vencimento": HOJE.isoformat()}, headers=headers_b)
    assert resp.status_code == 404
    # Filtrar por outro vendedor não abre a carteira alheia: o vendedor segue travado nele mesmo.
    vend_a = _usuario_id(db_session, "vend-a@teste.com.br")
    assert client.get(f"/api/v1/map/inadimplencia/parcelas?vendedor_usuario_id={vend_a}", headers=headers_b).json()["linhas"] == []


def test_admin_ve_o_tenant_e_filtra_por_vendedor(client, db_session, criar_usuario_autenticado):
    headers_admin = criar_usuario_autenticado(TENANT_ID, papel="admin", email="gestor-parc@teste.com.br")
    headers_x = criar_usuario_autenticado(TENANT_ID, papel="user", email="vend-x@teste.com.br")
    headers_y = criar_usuario_autenticado(TENANT_ID, papel="user", email="vend-y@teste.com.br")
    vx, vy = _usuario_id(db_session, "vend-x@teste.com.br"), _usuario_id(db_session, "vend-y@teste.com.br")
    _lancar(client, headers_x, _negocio_ganho(db_session, TENANT_ID, vx, "Cliente X").id, 100, HOJE - timedelta(days=1))
    _lancar(client, headers_y, _negocio_ganho(db_session, TENANT_ID, vy, "Cliente Y").id, 200, HOJE - timedelta(days=9))

    quadro = client.get("/api/v1/map/inadimplencia/parcelas", headers=headers_admin).json()
    assert {linha["cliente"] for linha in quadro["linhas"]} == {"Cliente X", "Cliente Y"}
    assert {v["id"] for v in quadro["opcoes"]["vendedores"]} == {vx, vy}
    so_y = client.get(f"/api/v1/map/inadimplencia/parcelas?vendedor_usuario_id={vy}", headers=headers_admin).json()
    assert [linha["cliente"] for linha in so_y["linhas"]] == ["Cliente Y"]
    assert so_y["resumo"]["total_em_atraso"] == 200


def test_hierarquia_distribuidor_revenda_e_isolamento_entre_tenants(client, db_session, criar_usuario_autenticado):
    rep = Representante(nome="Rep Sul", email="rep-sul@rep.com", chave_pix="pix", percentual_comissao=0.1)
    db_session.add(rep)
    db_session.commit()
    _tenant(db_session, "dist-a", tipo="distribuidor")
    _tenant(db_session, "rev-a", tipo="revendedor", pai="dist-a")
    _tenant(db_session, "cli-a", pai="rev-a", representante_id=rep.id)
    _tenant(db_session, "cli-fora")  # outra rede

    headers_dist = criar_usuario_autenticado("dist-a", papel="admin", email="admin@dist-a.com.br")
    headers_rev = criar_usuario_autenticado("rev-a", papel="admin", email="admin@rev-a.com.br")
    headers_cli = criar_usuario_autenticado("cli-a", papel="admin", email="admin@cli-a.com.br")
    headers_fora = criar_usuario_autenticado("cli-fora", papel="admin", email="admin@cli-fora.com.br")
    _lancar(client, headers_cli, _negocio_ganho(db_session, "cli-a", None, "Cliente da Ponta").id, 700, HOJE - timedelta(days=3))
    _lancar(client, headers_fora, _negocio_ganho(db_session, "cli-fora", None, "Cliente de Fora").id, 900, HOJE - timedelta(days=3))

    def clientes(headers, filtro=""):
        return [linha["cliente"] for linha in client.get(f"/api/v1/map/inadimplencia/parcelas{filtro}", headers=headers).json()["linhas"]]

    assert clientes(headers_dist) == ["Cliente da Ponta"]
    assert clientes(headers_rev) == ["Cliente da Ponta"]
    assert clientes(headers_cli) == ["Cliente da Ponta"]
    assert clientes(headers_fora) == ["Cliente de Fora"]
    assert set(clientes(client.headers)) == {"Cliente da Ponta", "Cliente de Fora"}  # super_admin vê tudo
    linha = client.get("/api/v1/map/inadimplencia/parcelas", headers=headers_dist).json()["linhas"][0]
    assert (linha["tenant_id"], linha["revenda_id"], linha["distribuidor_id"], linha["representante_nome"]) == ("cli-a", "rev-a", "dist-a", "Rep Sul")

    assert clientes(client.headers, f"?representante_id={rep.id}") == ["Cliente da Ponta"]
    assert clientes(client.headers, "?distribuidor_id=dist-a") == ["Cliente da Ponta"]
    assert clientes(client.headers, "?tenant_id_selecionado=cli-fora") == ["Cliente de Fora"]
    # Zoom num tenant de outra rede é recusado.
    assert client.get("/api/v1/map/inadimplencia/parcelas?tenant_id_selecionado=cli-fora", headers=headers_dist).status_code == 403
    # Nem o cliente da ponta nem a revenda enxergam para cima ou para o lado.
    assert client.get("/api/v1/map/inadimplencia/parcelas?tenant_id_selecionado=dist-a", headers=headers_rev).status_code == 403


# --- Licenças ------------------------------------------------------------------------------------------------------------------------------------------

def _licenca(db, tenant_id: str, dias_vencida: int, status: str = "ativa") -> None:
    plano = db.query(Plano).first()
    expiracao = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=dias_vencida)
    existente = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
    if existente is None:
        db.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status=status, data_expiracao=expiracao))
    else:
        existente.status, existente.data_expiracao = status, expiracao
    db.commit()


def test_quadro_de_licencas_por_papel(client, db_session, criar_usuario_autenticado):
    _tenant(db_session, "dist-l", tipo="distribuidor")
    headers_dist = criar_usuario_autenticado("dist-l", papel="admin", email="admin@dist-l.com.br")
    rep_usuario_headers = criar_usuario_autenticado(TENANT_ID, papel="user", email="rep-lic@teste.com.br")
    rep = Representante(nome="Rep Lic", email="rep-lic@rep.com", chave_pix="pix", percentual_comissao=0.1,
                        usuario_id=_usuario_id(db_session, "rep-lic@teste.com.br"))
    db_session.add(rep)
    db_session.commit()
    _tenant(db_session, "lic-filho", pai="dist-l")
    _tenant(db_session, "lic-do-rep", representante_id=rep.id)
    _tenant(db_session, "lic-em-dia")
    criar_usuario_autenticado("lic-filho", papel="admin", email="admin@lic-filho.com.br")
    criar_usuario_autenticado("lic-do-rep", papel="admin", email="admin@lic-do-rep.com.br")
    headers_comum = criar_usuario_autenticado("lic-em-dia", papel="admin", email="admin@lic-em-dia.com.br")
    _licenca(db_session, "lic-filho", 10, status="suspensa")
    _licenca(db_session, "lic-do-rep", 2)
    _licenca(db_session, "lic-em-dia", -20)  # vence daqui a 20 dias

    def tenants(headers):
        resposta = client.get("/api/v1/map/inadimplencia/licencas", headers=headers)
        assert resposta.status_code == 200, resposta.text
        return {linha["tenant_id"]: linha["situacao"] for linha in resposta.json()["linhas"]}

    todos = tenants(client.headers)
    assert todos["lic-filho"] == "suspensa" and todos["lic-do-rep"] == "em_carencia" and "lic-em-dia" not in todos
    assert tenants(headers_dist) == {"lic-filho": "suspensa"}
    assert tenants(rep_usuario_headers) == {"lic-do-rep": "em_carencia"}
    # Admin de tenant cliente (folha) não tem este quadro. (O do tenant suspenso nem entra: a licença suspensa já barra a rota.)
    assert client.get("/api/v1/map/inadimplencia/licencas", headers=headers_comum).status_code == 403
    assert client.get("/api/v1/map/inadimplencia/acesso", headers=headers_comum).json()["licencas"] is False
    assert client.get("/api/v1/map/inadimplencia/acesso", headers=rep_usuario_headers).json() == {
        "parcelas": True, "licencas": True, "notas_daily": False}


# --- Notas da daily --------------------------------------------------------------------------------------------------------------------------------

def test_hoje_e_o_de_brasilia():
    # 01:30 UTC de 19/11 ainda é 22:30 de 18/11 em Brasília.
    assert inadimplencia_service.hoje_brasilia(datetime(2026, 11, 19, 1, 30, tzinfo=UTC)) == date(2026, 11, 18)
    assert inadimplencia_service.hoje_brasilia(datetime(2026, 11, 19, 3, 0, tzinfo=UTC)) == date(2026, 11, 19)


def test_nota_aparece_no_dia_seguinte_por_padrao_e_na_data_escolhida(client, monkeypatch):
    dia = {"hoje": date(2026, 11, 18)}
    monkeypatch.setattr(nota_daily_service, "hoje_brasilia", lambda: dia["hoje"])

    padrao = client.post("/api/v1/map/notas-daily", json={"texto": "Cobrar proposta da Padaria Sol"})
    assert padrao.status_code == 201 and padrao.json()["exibir_em"] == "2026-11-19"
    escolhida = client.post("/api/v1/map/notas-daily", json={"texto": "Revisar metas", "exibir_em": "2026-11-23"}).json()
    assert client.post("/api/v1/map/notas-daily", json={"texto": "Ontem", "exibir_em": "2026-11-17"}).status_code == 422

    hoje = client.get("/api/v1/map/notas-daily").json()
    assert hoje["destaque"] == [] and [n["texto"] for n in hoje["agendadas"]] == ["Cobrar proposta da Padaria Sol", "Revisar metas"]

    dia["hoje"] = date(2026, 11, 19)
    amanha = client.get("/api/v1/map/notas-daily").json()
    assert [n["texto"] for n in amanha["destaque"]] == ["Cobrar proposta da Padaria Sol"]

    dia["hoje"] = date(2026, 11, 23)  # sem marcar como vista, a de 19/11 continua em destaque junto com a de 23/11
    assert [n["texto"] for n in client.get("/api/v1/map/notas-daily").json()["destaque"]] == ["Cobrar proposta da Padaria Sol", "Revisar metas"]
    assert client.put(f"/api/v1/map/notas-daily/{padrao.json()['id']}/concluir", json={"concluida": True}).status_code == 200
    depois = client.get("/api/v1/map/notas-daily").json()
    assert [n["texto"] for n in depois["destaque"]] == ["Revisar metas"]
    assert [n["texto"] for n in depois["historico"]] == ["Cobrar proposta da Padaria Sol"]
    assert client.delete(f"/api/v1/map/notas-daily/{escolhida['id']}").status_code == 204


def test_nota_e_privada_do_autor_e_so_gestor_escreve(client, criar_usuario_autenticado):
    nota = client.post("/api/v1/map/notas-daily", json={"texto": "Minha nota", "exibir_em": HOJE.isoformat()}).json()
    headers_outro_gestor = criar_usuario_autenticado(TENANT_ID, papel="admin", email="outro-gestor@teste.com.br")
    headers_vendedor = criar_usuario_autenticado(TENANT_ID, papel="user", email="vend-nota@teste.com.br")
    headers_outro_tenant = criar_usuario_autenticado("tenant-nota-b", papel="admin", email="admin@nota-b.com.br")

    outro = client.get("/api/v1/map/notas-daily", headers=headers_outro_gestor).json()
    assert outro["destaque"] == [] and outro["agendadas"] == []
    assert client.put(f"/api/v1/map/notas-daily/{nota['id']}/concluir", json={"concluida": True}, headers=headers_outro_gestor).status_code == 404
    assert client.delete(f"/api/v1/map/notas-daily/{nota['id']}", headers=headers_outro_tenant).status_code == 404
    assert client.post("/api/v1/map/notas-daily", json={"texto": "x"}, headers=headers_vendedor).status_code == 403
    assert [n["texto"] for n in client.get("/api/v1/map/notas-daily").json()["destaque"]] == ["Minha nota"]
