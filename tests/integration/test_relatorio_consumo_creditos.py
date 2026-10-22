"""Relatório de consumo de créditos de IA e de enriquecimento (Lusha): por empresa e por usuário, franquia/limites do perfil contratado, aquisições de
créditos adicionais (quantidade, data, valor) e consumo adicional. Provedores sempre simulados."""

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.contexts.enriquecimento import config, ledger
from app.contexts.finops import carteira
from app.contexts.finops.comercial import TipoLote
from app.models.creditos_ia import CompraCreditos, ExecucaoIa, PacoteCreditos
from app.models.usuario import Usuario
from app.services import relatorio_consumo_service as relatorio
from app.services.errors import NaoEncontrado, ValidacaoFalhou
from tests.integration.test_pesquisa_decisores_governanca import A, B, URL, ProvedorPago, cenario, contas, eu, preparar_tenant_b, rodar  # noqa: F401

RELATORIO = "/api/v1/relatorio-consumo-creditos"


def usuario(db, papel="super_admin", tenant=A) -> Usuario:
    eu(db, tenant, papel)
    return db.query(Usuario).filter_by(tenant_id=tenant, papel=papel).first()


def consumir_ia(db, tenant, usuario_id, creditos, suf):
    """Uma execução de IA liquidada que consome `creditos` da carteira (primeiro o lote que vence antes)."""
    execucao = ExecucaoIa(id=f"exec-{suf}", tenant_id=tenant, idempotency_key=f"k-{suf}", workload_codigo="teste", catalogo_versao="v1", classe="C1",
                          modulo="predator", usuario_id=usuario_id, status="LIQUIDADA", creditos_liquidados=creditos,
                          liquidado_em=config.agora_utc())
    db.add(execucao)
    db.flush()
    carteira.travar(db, tenant)
    carteira.consumir(db, tenant, Decimal(creditos), execucao)
    db.commit()


def test_relatorio_junta_ia_e_lusha_por_empresa_e_por_usuario_com_franquia_limites_e_aquisicoes(client, db_session, fake_graph):
    cenario(db_session, franquia=30, itens=None, maximo=5, limite_pesquisa=30, orcamento=6800)
    chefe, vendedor = usuario(db_session, "admin"), usuario(db_session, "user")
    super_admin = usuario(db_session)
    solic_chefe, solic_vendedor = eu(db_session, A, "admin"), eu(db_session, A, "user")
    # Lusha: 20 créditos da franquia (vendedor), depois um pacote de 400 e mais 20 (10 da franquia que sobrou + 10 do pacote) pelo admin
    rodar(db_session, fake_graph, solic_vendedor, contas(db_session, 10), ProvedorPago(), d=2, chave="chave-vend-01")
    ledger.travar_carteira(db_session, A)
    ledger.conceder_compra(db_session, A, 1, 400, config.agora_utc() + timedelta(days=30), "ENRIQ_400", config.agora_utc())
    db_session.commit()
    rodar(db_session, fake_graph, solic_chefe, contas(db_session, 20), ProvedorPago(), d=1, chave="chave-chefe-01")
    # IA: franquia de 100 e um pacote de 50 comprado; 120 consumidos (100 da franquia + 20 do pacote)
    carteira.conceder(db_session, A, TipoLote.SUBSCRIPTION, 100, "FRANQUIA_MENSAL", referencia="teste", expira_em=config.fim_do_mes(config.agora_utc()))
    carteira.conceder(db_session, A, TipoLote.TOPUP, 50, "COMPRA", referencia="pacote")
    db_session.add(PacoteCreditos(codigo="PCK50", nome="50", creditos=50, preco=Decimal("90.00")))
    db_session.flush()
    db_session.add(CompraCreditos(tenant_id=A, pacote_id=db_session.query(PacoteCreditos).first().id, pacote_codigo="PCK50", pacote_versao=1, creditos=50,
                                  preco=Decimal("90.00"), status="APROVADA", confirmado_em=config.agora_utc()))
    db_session.commit()
    consumir_ia(db_session, A, vendedor.id, 70, "1")
    consumir_ia(db_session, A, chefe.id, 50, "2")

    r = relatorio.gerar(db_session, super_admin)
    empresa = next(e for e in r["empresas"] if e["tenant_id"] == A)
    lusha, ia = empresa["lusha"], empresa["ia"]
    # --- Lusha
    assert (lusha["consumo_total"], lusha["consumo_da_franquia"], lusha["consumo_adicional"]["pacotes_comprados"]) == (40, 30, 10)
    assert (lusha["franquia_mensal"], lusha["decisores_por_empresa_max"]) == (30, 5) and lusha["uso_da_franquia_percentual"] == 100.0
    assert (lusha["limite_por_pesquisa"], lusha["limite_por_pesquisa_origem"]) == (400, "pacote adicional")  # o pacote vale: limite = tamanho do pacote
    por_usuario = {u["papel"]: u for u in lusha["por_usuario"]}
    assert (por_usuario["user"]["creditos"], por_usuario["user"]["pesquisas"], por_usuario["user"]["empresas"]) == (20, 1, 10)
    assert (por_usuario["admin"]["creditos"], por_usuario["admin"]["empresas"]) == (20, 20)
    assert [(a["creditos"], a["valor_brl"], a["pacote"]) for a in lusha["aquisicoes"]] == []  # a compra de teste foi creditada direto no razão (sem pedido pago)
    # --- IA
    assert (ia["consumo_da_franquia"], ia["consumo_adicional"]["pacotes_comprados"], ia["consumo_total"]) == (100.0, 20.0, 120.0)
    assert {u["papel"]: u["creditos"] for u in ia["por_usuario"]} == {"user": 70.0, "admin": 50.0}
    assert [(a["creditos"], a["valor_brl"]) for a in ia["aquisicoes"]] == [(50, "90.00")]
    # --- totais e aquisições do relatório
    assert r["totais"]["ia"]["consumo_total"] >= 120 and r["totais"]["lusha"]["consumo_total"] >= 40
    assert any(a["produto"] == "IA" and a["creditos"] == 50 and a["valor_brl"] == "90.00" for a in r["aquisicoes"])
    assert r["periodo"]["inicio"] < r["periodo"]["fim"] and r["notas"]


def test_aquisicao_de_pacote_de_lusha_aparece_com_quantidade_valor_e_data(client, db_session):
    cenario(db_session, franquia=30, itens=None, maximo=5, limite_pesquisa=30, orcamento=6800)
    from app.models.enriquecimento_creditos import EnriquecimentoCompra

    agora = config.agora_utc()
    db_session.add(EnriquecimentoCompra(tenant_id=A, pacote_id=1, pacote_codigo="ENRIQ_3000", pacote_versao=1, creditos=3000, preco_unitario_brl=Decimal("1.08"),
                                        preco_total_brl=Decimal("3240.00"), expira_em_previsto=agora + timedelta(days=30), status="APROVADA",
                                        confirmado_em=agora, expira_em=agora + timedelta(days=30)))
    db_session.commit()
    r = relatorio.gerar(db_session, usuario(db_session))
    compra = next(a for a in r["aquisicoes"] if a["produto"] == "Lusha")
    assert (compra["creditos"], compra["valor_brl"], compra["pacote"], compra["data"]) == (3000, "3240.00", "ENRIQ_3000", agora.isoformat())
    assert compra["valido_ate"] == (agora + timedelta(days=30)).isoformat() and r["totais"]["aquisicoes"]["valor_brl"] == "3240.00"


def test_escopo_admin_so_ve_a_propria_empresa_e_super_admin_ve_todas(client, db_session):
    cenario(db_session)
    preparar_tenant_b(db_session)
    admin_a, admin_b = usuario(db_session, "admin", A), usuario(db_session, "admin", B)
    assert {e["tenant_id"] for e in relatorio.gerar(db_session, admin_a)["empresas"]} == {A}
    assert {e["tenant_id"] for e in relatorio.gerar(db_session, admin_b)["empresas"]} == {B}
    assert {A, B} <= {e["tenant_id"] for e in relatorio.gerar(db_session, usuario(db_session))["empresas"]}
    with pytest.raises(NaoEncontrado):
        relatorio.gerar(db_session, admin_a, tenant_id=B)  # empresa fora do escopo: mesma resposta de "não existe"


def test_periodo_invalido_e_recusado_e_periodo_futuro_vem_zerado(client, db_session):
    cenario(db_session)
    sa = usuario(db_session)
    with pytest.raises(ValidacaoFalhou):
        relatorio.gerar(db_session, sa, date(2026, 10, 10), date(2026, 10, 1))
    with pytest.raises(ValidacaoFalhou):
        relatorio.gerar(db_session, sa, date(2024, 1, 1), date(2026, 1, 1))
    with pytest.raises(ValidacaoFalhou):
        relatorio.gerar(db_session, sa, date(2026, 1, 1), None)
    futuro = relatorio.gerar(db_session, sa, date(2030, 1, 1), date(2030, 1, 31))
    assert futuro["totais"]["lusha"]["consumo_total"] == 0 and futuro["totais"]["ia"]["consumo_total"] == 0 and futuro["aquisicoes"] == []


def test_rota_json_e_csv(client, db_session):
    cenario(db_session)
    r = client.get(RELATORIO)
    assert r.status_code == 200 and r.json()["empresas"] and "totais" in r.json()
    assert client.get(RELATORIO, params={"inicio": "2026-10-10", "fim": "2026-10-01"}).status_code in (400, 422)
    csv_resposta = client.get(f"{RELATORIO}/csv")
    assert csv_resposta.status_code == 200 and "attachment" in csv_resposta.headers["content-disposition"]
    linhas = list(csv.reader(io.StringIO(csv_resposta.content.decode("utf-8-sig")), delimiter=";"))
    assert linhas[0] == ["tipo", "empresa", "plano", "produto", "usuario", "descricao", "creditos", "valor_brl", "data"]
    tipos = {linha[0] for linha in linhas[1:]}
    assert {"franquia", "limite", "consumo_empresa", "consumo_adicional"} <= tipos
