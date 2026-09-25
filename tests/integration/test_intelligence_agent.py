"""B2B ON Intelligence Agent — orquestração (Fase 12). GATE: permissions e tools testados."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from app.api.deps import get_plan_limits_provider
from app.contexts.intelligence import registro
from app.contexts.intelligence.orquestrador import ferramentas_registradas, validar
from app.contexts.shared import ferramentas as registro_compartilhado
from app.main import app
from app.models.estagio_funil import EstagioFunil
from app.models.mensagem import Mensagem
from app.models.negocio import Negocio
from app.models.registro_uso_ia import RegistroUsoIa
from app.providers.plan_limits.stub import StubPlanLimitsProvider

A = "/api/v1/inteligencia/agente"
TENANT = "tenant-teste"


def _perguntar(client, pergunta, headers=None):
    resposta = client.post(A, json={"pergunta": pergunta}, headers=headers or {})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _bloquear(monkeypatch, tenant, modulos):
    monkeypatch.setitem(app.dependency_overrides, get_plan_limits_provider,
                        lambda: StubPlanLimitsProvider(modulos_bloqueados={tenant: set(modulos)}))


def _negocio(client) -> int:
    conta = client.post("/api/v1/leads/contas", json={"nome": "Cliente Agente"}).json()
    decisor = client.post(f"/api/v1/contas/{conta['id']}/decisores", json={"nome": "Ana"}).json()
    return client.post("/api/v1/crm/negocios", json={"conta_id": conta["id"], "decisor_id": decisor["id"], "nome": "Licenças", "valor": 1000}).json()["id"]


# --- Registro: ferramentas e agentes coerentes ----------------------------------------


def test_toda_ferramenta_registrada_e_declarada_coerente_e_de_agente_autorizado():
    registradas = registro_compartilhado.registradas()
    assert set(registradas) == set(ferramentas_registradas()), {n: validar(f) for n, f in registradas.items() if validar(f)}
    for nome, ferramenta in registradas.items():
        declarada = registro.FERRAMENTAS[nome]
        assert registro.agente_pode_usar(ferramenta.agente, nome), nome
        assert (ferramenta.executar is not None) == (declarada.sensibilidade == registro.Sensibilidade.READ), nome
    lados = {f.lado for f in registradas.values()}
    assert {"BUY", "SELL"} <= lados


def test_ferramenta_nao_declarada_ou_write_com_execucao_e_rejeitada():
    fantasma = registro_compartilhado.FerramentaExecutavel("x.nao_declarada", agente="pipeline_agent", lado="SELL",
                                                           palavras_chave=("x",), executar=lambda *a: {})
    assert validar(fantasma) == "não declarada em registro.FERRAMENTAS"
    write = registro_compartilhado.FerramentaExecutavel("crm.mover_estagio", agente="pipeline_agent", lado="SELL",
                                                        palavras_chave=("x",), executar=lambda *a: {})
    assert "execução automática" in validar(write)


# --- Roteamento e execução -------------------------------------------------------------


def test_analisa_oportunidade_pelo_agente_de_oportunidade(client):
    negocio_id = _negocio(client)
    resposta = _perguntar(client, f"Analise a oportunidade {negocio_id} e diga o que fazer.")
    assert (resposta["status"], resposta["agente"], resposta["ferramenta"], resposta["roteamento"]) == (
        "OK", "opportunity_agent", "opportunity.analisar_oportunidade", "palavras_chave")
    assert resposta["resultado"]["negocio_id"] == negocio_id and "Próximas ações" in resposta["resposta"]
    assert [p["passo"] for p in resposta["passos"]] == ["ferramentas_permitidas", "roteamento", "execucao"]


def test_parametro_faltando_pergunta_em_vez_de_adivinhar(client):
    resposta = _perguntar(client, "Analise esta oportunidade e diga o que fazer.")
    assert resposta["status"] == "FALTAM_PARAMETROS" and resposta["faltando"] == ["negocio_id"] and resposta["resultado"] is None


def test_ferramenta_sempre_usa_o_tenant_do_usuario(client, criar_usuario_autenticado):
    negocio_id = _negocio(client)
    outro = criar_usuario_autenticado("tenant-outro-agente", papel="admin", email="admin@outro-agente.com")
    assert client.post(A, json={"pergunta": f"Analise a oportunidade {negocio_id}"}, headers=outro).status_code == 404


def test_edital_expansao_e_pca_pelos_agentes_especialistas(client):
    lic = client.post("/api/v1/bids/licitacoes", json={"titulo": "Pregão 1", "prazo_proposta": (datetime.now(UTC) + timedelta(days=9)).isoformat()}).json()
    assert _perguntar(client, f"Analise o edital {lic['id']}")["agente"] == "bid_qualification_agent"
    assert _perguntar(client, "Quais clientes possuem oportunidade de expansão?")["agente"] == "revenue_agent"
    orgao = client.post("/api/v1/procurement/orgaos", json={"nome": "Órgão"}).json()
    plano = client.post("/api/v1/procurement/planos", json={"orgao_id": orgao["id"], "ano": date.today().year, "nome": "PCA"}).json()
    client.post("/api/v1/procurement/itens-pca", json={"plano_id": plano["id"], "descricao": "Uniformes",
                                                       "data_prevista": (date.today() + timedelta(days=10)).isoformat()})
    pca = _perguntar(client, "Quais compras do PCA estão atrasadas?")
    assert (pca["agente"], pca["status"]) == ("procurement_planning_agent", "OK") and len(pca["resultado"]["sinais"]) == 1


def test_compra_e_venda_nao_se_misturam(client):
    ambigua = _perguntar(client, "Mostre contratos próximos do vencimento.")
    assert ambigua["status"] == "ESCLARECER" and ambigua["resultado"] is None
    assert set(ambigua["opcoes"]) == {"bids.contratos_vencendo", "procurement.contratos_vencendo"}
    assert _perguntar(client, "Mostre contratos com fornecedores próximos do vencimento.")["ferramenta"] == "procurement.contratos_vencendo"
    assert _perguntar(client, "Mostre contratos com clientes próximos do vencimento.")["ferramenta"] == "bids.contratos_vencendo"


# --- Permissões ---------------------------------------------------------------------------


def test_modulo_fora_do_plano_esconde_a_ferramenta_ate_da_ia(client, monkeypatch, fake_llm):
    _bloquear(monkeypatch, TENANT, {"procurement"})
    catalogo = {f["ferramenta"] for f in client.get(f"{A}/ferramentas").json()}
    assert not any(n.startswith("procurement.") for n in catalogo)
    fake_llm.definir_respostas([json.dumps({"ferramenta": "procurement.pca_atrasado", "parametros": {}})])

    resposta = _perguntar(client, "Quais compras do PCA estão atrasadas?")

    assert resposta["status"] == "SEM_FERRAMENTA" and resposta["ferramenta"] is None
    assert "procurement." not in fake_llm.chamadas[-1].prompt  # a IA nem vê a ferramenta
    assert _perguntar(client, "Mostre contratos próximos do vencimento.")["ferramenta"] == "bids.contratos_vencendo"


def test_write_e_external_viram_proposta_e_sensitive_e_recusada(client, db_session):
    negocio_id = _negocio(client)
    estagio_antes = db_session.get(Negocio, negocio_id).estagio_id
    mover = _perguntar(client, f"Mover estágio do negócio {negocio_id} para ganho")
    assert (mover["status"], mover["sensibilidade"]) == ("PROPOSTA_REQUER_CONFIRMACAO", "WRITE")
    db_session.expire_all()
    assert db_session.get(Negocio, negocio_id).estagio_id == estagio_antes
    assert db_session.get(EstagioFunil, estagio_antes).tipo == "aberto"

    mensagens_antes = db_session.query(Mensagem).count()
    rascunho = _perguntar(client, "Escrever mensagem de follow-up para o cliente")
    assert (rascunho["status"], rascunho["sensibilidade"]) == ("PROPOSTA_REQUER_CONFIRMACAO", "EXTERNAL_ACTION")
    assert "aprovação" in rascunho["resposta"] and db_session.query(Mensagem).count() == mensagens_antes

    plano = _perguntar(client, "Alterar plano da empresa para o premium")
    assert (plano["status"], plano["sensibilidade"], plano["resultado"]) == ("RECUSADO", "SENSITIVE_ACTION", None)


@pytest.fixture()
def ferramenta_so_admin(monkeypatch):
    nome = "crm.relatorio_admin_teste"
    monkeypatch.setitem(registro.FERRAMENTAS, nome, registro.Ferramenta(nome, registro.Sensibilidade.READ, "crm", "Teste"))
    monkeypatch.setitem(registro.AGENTES, "pipeline_agent", registro.Agente(
        "pipeline_agent", "Pipeline Agent", "crm", registro.StatusAgente.ATIVO,
        ("crm.listar_oportunidades", "crm.mover_estagio", nome)))
    monkeypatch.setitem(registro_compartilhado._REGISTRO, nome, registro_compartilhado.FerramentaExecutavel(
        nome, agente="pipeline_agent", lado="SELL", palavras_chave=("relatório confidencial de diretoria",),
        papeis=("admin", "super_admin"), executar=lambda db, ctx, p: {"resumo": "segredo da diretoria"}))
    return nome


def test_papel_do_usuario_limita_ferramentas(client, criar_usuario_autenticado, ferramenta_so_admin, fake_llm):
    fake_llm.definir_respostas(["{}"])
    vendedor = criar_usuario_autenticado(TENANT, papel="user", email="vendedor@agente.com")
    assert ferramenta_so_admin not in {f["ferramenta"] for f in client.get(f"{A}/ferramentas", headers=vendedor).json()}
    negado = _perguntar(client, "Mostre o relatório confidencial de diretoria", headers=vendedor)
    assert negado["status"] == "SEM_FERRAMENTA" and "segredo" not in json.dumps(negado)
    assert _perguntar(client, "Mostre o relatório confidencial de diretoria")["resposta"] == "segredo da diretoria"


def test_agente_sem_autorizacao_para_a_ferramenta_nao_a_usa(client, monkeypatch, fake_llm):
    fake_llm.definir_respostas(["{}"])
    monkeypatch.setitem(registro.AGENTES, "revenue_agent", registro.Agente("revenue_agent", "Revenue Agent", "map", registro.StatusAgente.ATIVO, ()))
    assert "opportunity.clientes_expansao" not in {f["ferramenta"] for f in client.get(f"{A}/ferramentas").json()}
    assert _perguntar(client, "Quais clientes possuem oportunidade de expansão?")["ferramenta"] != "opportunity.clientes_expansao"


def test_fallback_por_ia_e_medido_e_so_escolhe_do_catalogo_permitido(client, db_session, fake_llm):
    fake_llm.definir_respostas([json.dumps({"ferramenta": "crm.listar_oportunidades", "parametros": {}})])
    resposta = _perguntar(client, "Como anda a carteira comercial?")
    assert (resposta["status"], resposta["roteamento"], resposta["ferramenta"]) == ("OK", "ia", "crm.listar_oportunidades")
    uso = db_session.query(RegistroUsoIa).filter_by(feature="intelligence.orquestrador").one()
    assert uso.agente == "b2bon_intelligence_agent" and uso.classe_modelo == "C1"

    fake_llm.definir_respostas([json.dumps({"ferramenta": "plataforma.alterar_plano_inexistente"})])
    assert _perguntar(client, "Alguma coisa aleatória sem rota")["status"] == "SEM_FERRAMENTA"
