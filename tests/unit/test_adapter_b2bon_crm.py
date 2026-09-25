"""Adapter B2B ON CRM → canônico: mapeamento, paginação e isolamento (Fase 2)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.contexts.integrations.adapters.b2bon_crm import B2BOnCrmAdapter, cid
from app.contexts.integrations.contract import OperacaoNaoSuportada, iterar_todos
from app.contexts.shared.canonical.base import DataOrigin
from app.contexts.shared.canonical.commercial import AccountLifecycle, BuyingRole, OpportunityStatus, StageType
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.interacao_conta import InteracaoConta
from app.models.pesquisa_nps import PesquisaNps
from app.services import crm_service

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def _conta(db, tenant_id, nome, **extra):
    conta = Conta(tenant_id=tenant_id, nome=nome, status="prospectada", icp_id=None, **extra)
    db.add(conta)
    db.commit()
    return conta


def _decisor(db, conta, **extra):
    decisor = Decisor(tenant_id=conta.tenant_id, conta_id=conta.id, nome=f"Decisor {conta.nome}", **extra)
    db.add(decisor)
    db.commit()
    return decisor


def test_nenhum_metodo_devolve_dado_de_outro_tenant(db_session):
    conta_a = _conta(db_session, TENANT_A, "A")
    conta_b = _conta(db_session, TENANT_B, "Segredo do B")
    _decisor(db_session, conta_a)
    decisor_b = _decisor(db_session, conta_b)
    crm_service.criar_negocio(db_session, TENANT_B, None, conta_b.id, decisor_b.id, "Negócio secreto", valor=999.0)
    db_session.add(InteracaoConta(tenant_id=TENANT_B, conta_id=conta_b.id, tipo="reclamacao"))
    db_session.add(PesquisaNps(tenant_id=TENANT_B, conta_id=conta_b.id, decisor_id=decisor_b.id, marco="x", nota=2, enviada_em=datetime.now(UTC)))
    db_session.commit()

    adapter = B2BOnCrmAdapter(db_session)
    listagens = [
        iterar_todos(adapter.list_organizations, TENANT_A),
        iterar_todos(adapter.list_accounts, TENANT_A),
        iterar_todos(adapter.list_customers, TENANT_A),
        iterar_todos(adapter.list_people, TENANT_A),
        iterar_todos(adapter.list_contacts, TENANT_A),
        iterar_todos(adapter.list_opportunities, TENANT_A),
        iterar_todos(adapter.list_activities, TENANT_A),
        iterar_todos(adapter.list_interactions, TENANT_A),
        iterar_todos(adapter.list_cs_metrics, TENANT_A),
        adapter.list_stages(TENANT_A),
        adapter.list_offers(TENANT_A),
    ]
    for itens in listagens:
        assert all(item.tenant_id == TENANT_A for item in itens)
        assert "Segredo do B" not in str([item.model_dump() for item in itens])
        assert "Negócio secreto" not in str([item.model_dump() for item in itens])


def test_mapeia_conta_negocio_e_decisor_para_o_canonico(db_session):
    conta = _conta(db_session, TENANT_A, "Acme Ltda", nome_fantasia="Acme", cnpj="12345678000199", origem="receita_federal")
    decisor = _decisor(db_session, conta, cargo="CFO", papel_confirmado="ECONOMIC_BUYER")
    ganho = next(e for e in crm_service.garantir_estagios_padrao(db_session, TENANT_A) if e.tipo == "ganho")
    negocio = crm_service.criar_negocio(db_session, TENANT_A, None, conta.id, decisor.id, "Deal", valor=1234.5)
    crm_service.mover_estagio(db_session, TENANT_A, None, negocio.id, ganho.id)

    adapter = B2BOnCrmAdapter(db_session)
    org = adapter.list_organizations(TENANT_A).items[0]
    conta_canonica = adapter.list_accounts(TENANT_A).items[0]
    contato = adapter.list_contacts(TENANT_A).items[0]
    oportunidade = adapter.list_opportunities(TENANT_A).items[0]
    estagios = adapter.list_stages(TENANT_A)

    assert org.id == cid("organization", conta.id) and org.tax_id == "12345678000199"
    assert org.origin == DataOrigin.OFFICIAL
    assert org.source.system == "b2bon_crm" and org.source.entity == "conta"
    assert conta_canonica.organization_id == org.id
    assert conta_canonica.lifecycle == AccountLifecycle.CUSTOMER
    assert contato.buying_role == BuyingRole.ECONOMIC_BUYER and contato.buying_role_confirmed
    assert oportunidade.status == OpportunityStatus.WON
    assert oportunidade.amount.amount == Decimal("1234.5") and oportunidade.amount.currency == "BRL"
    assert oportunidade.account_id == conta_canonica.id
    assert {e.stage_type for e in estagios} == {StageType.OPEN, StageType.WON, StageType.LOST}
    assert adapter.list_customers(TENANT_A).items[0].account_id == conta_canonica.id


def test_ciclo_de_vida_da_conta(db_session):
    agora = datetime.now(UTC)
    casos = {
        "prospect": (dict(icp_id=None, status="prospectada"), AccountLifecycle.LEAD),
        "descartada": (dict(status="descartada"), AccountLifecycle.DISQUALIFIED),
        "priorizada": (dict(status="priorizada"), AccountLifecycle.QUALIFIED),
        "cliente": (dict(cliente_desde=agora), AccountLifecycle.CUSTOMER),
        "churn": (dict(cliente_desde=agora - timedelta(days=90), cliente_cancelado_em=agora), AccountLifecycle.CHURNED),
    }
    for nome, (campos, _) in casos.items():
        dados = {"status": "prospectada", **campos}
        db_session.add(Conta(tenant_id=TENANT_A, nome=nome, **dados))
    db_session.commit()
    org_por_nome = {o.id: o.legal_name for o in B2BOnCrmAdapter(db_session).list_organizations(TENANT_A).items}
    for conta in B2BOnCrmAdapter(db_session).list_accounts(TENANT_A).items:
        nome = org_por_nome[conta.organization_id]
        assert conta.lifecycle == casos[nome][1], nome


def test_paginacao_por_cursor_percorre_tudo_sem_repetir(db_session):
    for i in range(5):
        _conta(db_session, TENANT_A, f"Conta {i}")
    adapter = B2BOnCrmAdapter(db_session)
    vistos = []
    cursor = None
    while True:
        pagina = adapter.list_accounts(TENANT_A, cursor=cursor, limit=2)
        vistos.extend(item.id for item in pagina.items)
        if not pagina.next_cursor:
            break
        cursor = pagina.next_cursor
    assert len(vistos) == 5 == len(set(vistos))


def test_escrita_nao_suportada_e_explicita(db_session):
    adapter = B2BOnCrmAdapter(db_session)
    try:
        adapter.add_note(TENANT_A, "x", "nota")
    except OperacaoNaoSuportada:
        pass
    else:
        raise AssertionError("adapter somente leitura não pode fingir que escreveu")
