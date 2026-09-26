"""TD-040 (Phase J2): decisores só da conta já validada e do tenant dela — um decisor de outro tenant que aponte
para o mesmo id de conta nunca aparece, e a rota recusa conta de outro tenant antes de ler qualquer decisor."""

from app.contexts.shared import organizations
from app.models.conta import Conta
from app.models.decisor import Decisor


def test_decisores_filtrados_pela_conta_validada_e_pelo_tenant(client, db_session, criar_usuario_autenticado):
    conta = Conta(tenant_id="tenant-teste", nome="Cliente Alfa", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    db_session.add_all([Decisor(tenant_id="tenant-teste", conta_id=conta.id, nome="Ana"),
                        Decisor(tenant_id="tenant-invasor", conta_id=conta.id, nome="Intruso")])
    db_session.commit()
    assert [d.nome for d in organizations.decisores_da_conta(db_session, conta)] == ["Ana"]
    assert [d["nome"] for d in client.get(f"/api/v1/contas/{conta.id}/decisores").json()] == ["Ana"]
    outro = criar_usuario_autenticado("tenant-invasor", email="x@invasor.com")
    assert client.get(f"/api/v1/contas/{conta.id}/decisores", headers=outro).status_code == 404
