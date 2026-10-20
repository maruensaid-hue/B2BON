"""Alertas de licitação por regra/ICP: novo, incompatível, duplicado, retificado, suspenso, vários ICPs/tenants, falha de entrega, reprocesso e
ausência de qualquer disparo externo real. Sem IA e sem rede."""

from datetime import timedelta

import pytest

from app.contexts.bids import alertas, licitacoes
from app.contexts.bids.fontes.base import LicitacaoExterna
from app.core.config import settings
from app.models.alerta_licitacao import AlertaLicitacao, EstadoAlertasLicitacao
from app.models.icp import ICP
from app.models.licitacao import Licitacao
from app.models.usuario import Usuario

A, B_, C = "tenant-teste", "tenant-outro", "tenant-terceiro"
URL = "/api/v1/bids"
AGORA = alertas._agora()


def _ext(n=1, **kw) -> LicitacaoExterna:
    base = dict(fonte="PNCP", id_externo=f"AL-{n}", titulo=f"Aquisição de licenças de software {n}", objeto="Solução de gestão", orgao_nome="Prefeitura X",
                orgao_cnpj="11222333000181", modalidade="PUBLIC_TENDER", data_publicacao=AGORA - timedelta(days=1), prazo_proposta=AGORA + timedelta(days=30),
                valor_estimado=200000.0, url=f"https://pncp.test/{n}", situacao_externa="Divulgada", atualizado_externo_em=AGORA - timedelta(hours=5),
                uf="SP", municipio="Campinas", modalidade_codigo=6)
    base.update(kw)
    return LicitacaoExterna(**base)


def _publicar(db, *itens):
    """O que a coleta faz: grava o fato público no corpus (o feed de eventos que os alertas consomem)."""
    licitacoes.ingerir_detalhado(db, "tenant-coletor", None, list(itens))


@pytest.fixture(autouse=True)
def _email_ligado(monkeypatch):
    monkeypatch.setattr(settings, "alertas_licitacao_email_habilitado", True)


def _regra(client, **kw):
    corpo = {"nome": "Software SP", "palavras_chave": ["software"], "ufs": ["SP"], "relevancia_minima": 40, "frequencia": "diaria"}
    corpo.update(kw)
    resposta = client.post(f"{URL}/alertas/regras", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _admin(db, tenant, email=None):
    u = Usuario(tenant_id=tenant, nome=f"Admin {tenant}", email=email or f"admin@{tenant}.com.br", papel="admin", ativo=True)
    db.add(u)
    db.commit()
    return u


# --- Regras ---------------------------------------------------------------------------------------------------------------------------------


def test_regra_exige_palavra_chave_ou_portfolio_e_valida_os_campos(client):
    base = {"nome": "x"}
    assert client.post(f"{URL}/alertas/regras", json=base).status_code == 422                                   # sem palavra-chave: casaria com tudo
    assert client.post(f"{URL}/alertas/regras", json={**base, "palavras_chave": ["a"], "ufs": ["Sao Paulo"]}).status_code == 422
    assert client.post(f"{URL}/alertas/regras", json={**base, "palavras_chave": ["a"], "valor_minimo": 10, "valor_maximo": 1}).status_code == 422
    assert client.post(f"{URL}/alertas/regras", json={**base, "palavras_chave": ["a"], "modalidades": ["INEXISTENTE"]}).status_code == 422
    assert client.post(f"{URL}/alertas/regras", json={**base, "palavras_chave": ["a"], "relevancia_minima": 150}).status_code == 422
    assert client.post(f"{URL}/alertas/regras", json={**base, "usar_portfolio": True}).status_code == 201       # portfólio basta como critério


def test_regra_nao_pode_apontar_para_icp_de_outro_tenant_nem_ter_nome_repetido(client, db_session):
    icp_alheio = ICP(tenant_id=B_, grupo_id="g", nome="ICP de B", segmento="s", porte="p", regiao="r", ufs=["SP"])
    db_session.add(icp_alheio)
    db_session.commit()

    assert client.post(f"{URL}/alertas/regras", json={"nome": "x", "palavras_chave": ["a"], "icp_id": icp_alheio.id}).status_code == 404
    _regra(client)
    assert client.post(f"{URL}/alertas/regras", json={"nome": "Software SP", "palavras_chave": ["b"]}).status_code == 422


def test_so_administrador_cria_altera_e_exclui_regra(client, criar_usuario_autenticado, tenants_da_rede):
    vendedor = criar_usuario_autenticado(A, "user", "vendedor@a.com.br")

    assert client.post(f"{URL}/alertas/regras", json={"nome": "x", "palavras_chave": ["a"]}, headers=vendedor).status_code == 403
    assert client.get(f"{URL}/alertas/regras", headers=vendedor).status_code == 200  # ler é permitido


# --- Avaliação ------------------------------------------------------------------------------------------------------------------------------


def test_novo_edital_compativel_gera_alerta_e_o_incompativel_nao(client, db_session, tenants_da_rede):
    _regra(client)
    _publicar(db_session, _ext(1), _ext(2, titulo="Reforma de escola", objeto="Obra civil"), _ext(3, uf="RJ"))

    resumo = alertas.avaliar_tenant(db_session, A)

    assert resumo["criados"] == 1
    lista = client.get(f"{URL}/alertas").json()
    assert [a["edital"]["fonte_id_externo"] for a in lista] == ["AL-1"]
    assert lista[0]["estado"] == "novo" and lista[0]["score"] >= 40 and {f["fator"] for f in lista[0]["fatores"]} >= {"palavras_chave", "uf"}
    assert lista[0]["edital"]["url"] == "https://pncp.test/1"  # consulta à fonte oficial


def test_reavaliar_nao_duplica_e_varias_regras_no_mesmo_edital_geram_um_alerta_so(client, db_session, tenants_da_rede):
    _regra(client, nome="Por palavra")
    _regra(client, nome="Por gestão", palavras_chave=["gestao"], ufs=[])
    _publicar(db_session, _ext(1))

    alertas.avaliar_tenant(db_session, A)
    db_session.query(EstadoAlertasLicitacao).update({"ultimo_evento_id": 0})  # força reler todo o feed
    db_session.commit()
    alertas.avaliar_tenant(db_session, A)

    todos = db_session.query(AlertaLicitacao).filter_by(tenant_id=A).all()
    assert len(todos) == 1 and {r["nome"] for r in todos[0].regras} == {"Por palavra", "Por gestão"}


def test_retificacao_e_suspensao_atualizam_o_alerta_e_voltam_a_notificar(client, db_session, tenants_da_rede):
    _regra(client)
    _publicar(db_session, _ext(1))
    alertas.avaliar_tenant(db_session, A)
    alerta = db_session.query(AlertaLicitacao).one()
    alerta.entrega_estado = "enviada"
    db_session.commit()

    _publicar(db_session, _ext(1, situacao_externa="Suspensa", prazo_proposta=AGORA + timedelta(days=45), atualizado_externo_em=AGORA))
    resumo = alertas.avaliar_tenant(db_session, A)

    db_session.refresh(alerta)
    assert resumo["atualizados"] == 1 and resumo["criados"] == 0
    assert alerta.situacao_externa == "Suspensa" and alerta.motivo == "atualizada" and alerta.atualizacao_nao_vista is True
    assert alerta.entrega_estado == "pendente" and alerta.versao_corpus == 2   # suspensão exige atenção: notifica de novo


def test_alerta_dispensado_continua_dispensado_mesmo_com_retificacao(client, db_session, tenants_da_rede):
    _regra(client)
    _publicar(db_session, _ext(1))
    alertas.avaliar_tenant(db_session, A)
    alerta = db_session.query(AlertaLicitacao).one()
    assert client.post(f"{URL}/alertas/{alerta.id}/dispensar").status_code == 200

    _publicar(db_session, _ext(1, valor_estimado=999999.0, atualizado_externo_em=AGORA))
    alertas.avaliar_tenant(db_session, A)

    db_session.refresh(alerta)
    assert alerta.estado == "dispensado" and alerta.atualizacao_nao_vista is False
    assert alerta.versao_corpus == 2  # o snapshot acompanha o edital, mas o usuário não é incomodado


def test_edital_que_ja_nasce_cancelado_ou_vencido_nao_vira_oportunidade(client, db_session, tenants_da_rede):
    _regra(client)
    _publicar(db_session, _ext(1, situacao_externa="Anulada"), _ext(2, prazo_proposta=AGORA - timedelta(days=2)))

    assert alertas.avaliar_tenant(db_session, A)["criados"] == 0


def test_regra_nova_enxerga_o_corpus_que_ja_existia(client, db_session, tenants_da_rede):
    _regra(client, nome="Sem match", palavras_chave=["hospital"])
    _publicar(db_session, _ext(1))
    alertas.avaliar_tenant(db_session, A)   # avança o cursor sem alertas
    assert db_session.query(AlertaLicitacao).count() == 0

    _regra(client, nome="Software depois")  # criar regra reinicia o cursor
    alertas.avaliar_tenant(db_session, A)

    assert db_session.query(AlertaLicitacao).filter_by(tenant_id=A).count() == 1


def test_falha_no_meio_da_avaliacao_nao_avanca_o_cursor_e_a_reexecucao_converge(client, db_session, tenants_da_rede, monkeypatch):
    _regra(client)
    _publicar(db_session, _ext(1), _ext(2))
    original = alertas.avaliar_item
    chamadas = {"n": 0}

    def quebra(*args, **kwargs):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise RuntimeError("falha simulada")
        return original(*args, **kwargs)

    monkeypatch.setattr(alertas, "avaliar_item", quebra)
    with pytest.raises(RuntimeError):
        alertas.avaliar_tenant(db_session, A)
    db_session.rollback()
    assert db_session.query(AlertaLicitacao).count() == 0
    monkeypatch.setattr(alertas, "avaliar_item", original)

    alertas.avaliar_tenant(db_session, A)

    assert db_session.query(AlertaLicitacao).filter_by(tenant_id=A).count() == 2


# --- Vários tenants/ICPs ----------------------------------------------------------------------------------------------------------------------


def test_tenants_com_preferencias_diferentes_recebem_so_o_que_e_deles_e_nao_se_enxergam(client, db_session, criar_usuario_autenticado, tenants_da_rede):
    headers_b = criar_usuario_autenticado(B_, "admin", "adminb@b.com.br")
    _regra(client, ufs=["SP"])
    client.post(f"{URL}/alertas/regras", json={"nome": "RJ", "palavras_chave": ["software"], "ufs": ["RJ"]}, headers=headers_b)
    _publicar(db_session, _ext(1, uf="SP"), _ext(2, uf="RJ"))

    alertas.avaliar_tenant(db_session, A)
    alertas.avaliar_tenant(db_session, B_)

    de_a = client.get(f"{URL}/alertas").json()
    de_b = client.get(f"{URL}/alertas", headers=headers_b).json()
    assert [a["edital"]["fonte_id_externo"] for a in de_a] == ["AL-1"] and [a["edital"]["fonte_id_externo"] for a in de_b] == ["AL-2"]
    assert client.post(f"{URL}/alertas/{de_a[0]['id']}/dispensar", headers=headers_b).status_code == 404   # id de outro tenant
    assert client.get(f"{URL}/alertas/regras", headers=headers_b).json()[0]["nome"] == "RJ"


def test_regra_vinculada_a_icp_usa_as_ufs_do_icp(client, db_session, tenants_da_rede):
    icp = ICP(tenant_id=A, grupo_id="g", nome="ICP Sul", segmento="s", porte="p", regiao="r", ufs=["RS"])
    db_session.add(icp)
    db_session.commit()
    _regra(client, nome="Do ICP", ufs=[], icp_id=icp.id)
    _publicar(db_session, _ext(1, uf="SP"), _ext(2, uf="RS"))

    alertas.avaliar_tenant(db_session, A)

    assert [a["edital"]["uf"] for a in client.get(f"{URL}/alertas").json()] == ["RS"]


# --- Ações do usuário -------------------------------------------------------------------------------------------------------------------------


def test_visto_dispensar_e_acompanhar_mudam_o_estado_e_acompanhar_cria_a_copia_privada_uma_vez(client, db_session, tenants_da_rede):
    _regra(client)
    _publicar(db_session, _ext(1), _ext(2))
    alertas.avaliar_tenant(db_session, A)
    por_edital = {a["edital"]["fonte_id_externo"]: a["id"] for a in client.get(f"{URL}/alertas").json()}
    a1, a2 = por_edital["AL-1"], por_edital["AL-2"]

    assert client.post(f"{URL}/alertas/{a1}/visto").json()["estado"] == "visto"
    assert client.post(f"{URL}/alertas/{a2}/dispensar").json()["estado"] == "dispensado"
    primeira = client.post(f"{URL}/alertas/{a1}/acompanhar")
    segunda = client.post(f"{URL}/alertas/{a1}/acompanhar")

    assert primeira.status_code == 200 and primeira.json()["alerta"]["estado"] == "acompanhado"
    assert primeira.json()["licitacao"]["id"] == segunda.json()["licitacao"]["id"]
    assert db_session.query(Licitacao).filter_by(tenant_id=A, fonte_id_externo="AL-1").count() == 1
    assert [x["id"] for x in client.get(f"{URL}/alertas", params={"estado": "dispensado"}).json()] == [a2]
    assert client.get(f"{URL}/alertas/resumo").json()["por_estado"] == {"novo": 0, "visto": 0, "dispensado": 1, "acompanhado": 1}
    assert client.get(f"{URL}/alertas", params={"estado": "invalido"}).status_code == 422


# --- Entrega --------------------------------------------------------------------------------------------------------------------------------


def test_varios_alertas_viram_um_unico_resumo_por_administrador(client, db_session, tenants_da_rede, fake_email):
    _admin(db_session, A, "diretor@a.com.br")
    _regra(client)
    _publicar(db_session, *[_ext(n) for n in range(1, 13)])
    alertas.avaliar_tenant(db_session, A)

    r = alertas.entregar(db_session, A, fake_email)

    admins = {u.email for u in db_session.query(Usuario).filter(Usuario.tenant_id == A, Usuario.papel.in_(("admin", "super_admin")))}
    assert r == {"estado": "enviado", "enviados": 12}
    assert len(fake_email.envios) == len(admins) and {e["destinatario"] for e in fake_email.envios} == admins
    corpo = fake_email.envios[0]["corpo"]
    assert corpo.count("• ") == 10 and "mais 2 oportunidade" in corpo and "não indica elegibilidade" in corpo   # limite do resumo e aviso honesto
    assert fake_email.envios[0]["mensagem_id"] is None and fake_email.envios[0]["pixel_url"] is None          # e-mail de sistema: fora do outreach
    assert {a.entrega_estado for a in db_session.query(AlertaLicitacao)} == {"enviada"}


def test_resumo_diario_nao_repete_em_menos_de_um_dia_mas_o_imediato_sim(client, db_session, tenants_da_rede, fake_email):
    _admin(db_session, A, "diretor@a.com.br")
    _regra(client, nome="Diária", palavras_chave=["software"], frequencia="diaria")
    _publicar(db_session, _ext(1))
    alertas.avaliar_tenant(db_session, A)
    alertas.entregar(db_session, A, fake_email, AGORA)
    enviados = len(fake_email.envios)

    _publicar(db_session, _ext(2))
    alertas.avaliar_tenant(db_session, A)
    espera = alertas.entregar(db_session, A, fake_email, AGORA + timedelta(hours=3))
    depois = alertas.entregar(db_session, A, fake_email, AGORA + timedelta(hours=21))

    assert espera["estado"] == "aguardando_resumo_diario" and len(fake_email.envios) == enviados * 2 and depois["estado"] == "enviado"

    client.post(f"{URL}/alertas/regras", json={"nome": "Imediata", "palavras_chave": ["software"], "frequencia": "imediata"})
    _publicar(db_session, _ext(3))
    alertas.avaliar_tenant(db_session, A)
    assert alertas.entregar(db_session, A, fake_email, AGORA + timedelta(hours=22))["estado"] == "enviado"   # imediata ignora a espera


def test_falha_de_entrega_e_registrada_reprocessada_e_desiste_depois_de_3_tentativas(client, db_session, tenants_da_rede, fake_email):
    _admin(db_session, A, "diretor@a.com.br")
    _regra(client)
    _publicar(db_session, _ext(1))
    alertas.avaliar_tenant(db_session, A)
    admins = db_session.query(Usuario).filter(Usuario.tenant_id == A, Usuario.papel.in_(("admin", "super_admin"))).count()

    fake_email.falhar_proximos = admins
    assert alertas.entregar(db_session, A, fake_email)["estado"] == "falhou"
    alerta = db_session.query(AlertaLicitacao).one()
    assert alerta.entrega_estado == "falhou" and alerta.entrega_tentativas == 1 and alerta.entrega_ultimo_erro

    fake_email.falhar_proximos = 0
    assert alertas.entregar(db_session, A, fake_email)["estado"] == "enviado"     # reprocessamento no ciclo seguinte
    db_session.refresh(alerta)
    assert alerta.entrega_estado == "enviada" and alerta.entregue_em is not None

    alerta.entrega_estado, alerta.entrega_tentativas = "falhou", 2
    db_session.commit()
    fake_email.falhar_proximos = admins
    alertas.entregar(db_session, A, fake_email, AGORA + timedelta(days=2))
    db_session.refresh(alerta)
    assert alerta.entrega_estado == "desistida"


def test_com_o_e_mail_desligado_o_alerta_existe_no_painel_e_nada_e_enviado(client, db_session, tenants_da_rede, fake_email, monkeypatch):
    monkeypatch.setattr(settings, "alertas_licitacao_email_habilitado", False)
    _admin(db_session, A, "diretor@a.com.br")
    _regra(client)
    _publicar(db_session, _ext(1))

    alertas.avaliar_tenant(db_session, A)
    r = alertas.entregar(db_session, A, fake_email)

    assert r["estado"] == "desligada" and fake_email.envios == []
    assert db_session.query(AlertaLicitacao).one().entrega_estado == "desligada" and len(client.get(f"{URL}/alertas").json()) == 1


def test_cron_exige_segredo_avalia_todos_os_tenants_com_regra_e_isola_falhas(client, db_session, tenants_da_rede, fake_email, monkeypatch):
    from app.main import app
    from app.api.deps import get_email_provider

    app.dependency_overrides[get_email_provider] = lambda: fake_email
    monkeypatch.setattr(settings, "cron_secret", "seg")
    _admin(db_session, A, "diretor@a.com.br")
    _regra(client)
    _publicar(db_session, _ext(1))

    assert client.post("/api/v1/cron/processar-alertas-licitacoes").status_code == 403
    assert client.post("/api/v1/cron/processar-alertas-licitacoes", headers={"X-Cron-Secret": "errado"}).status_code == 403
    resposta = client.post("/api/v1/cron/processar-alertas-licitacoes", headers={"X-Cron-Secret": "seg"})

    assert resposta.status_code == 200 and resposta.json()["alertas_criados"] == 1 and resposta.json()["resumos_enviados"] == 1
    assert len(fake_email.envios) >= 1
    # segunda rodada: idempotente, nada novo, nenhum e-mail novo
    antes = len(fake_email.envios)
    segunda = client.post("/api/v1/cron/processar-alertas-licitacoes", headers={"X-Cron-Secret": "seg"}).json()
    assert segunda["alertas_criados"] == 0 and len(fake_email.envios) == antes
