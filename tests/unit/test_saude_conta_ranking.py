from app.models.conta import Conta
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import saude_conta_service

TENANT_ID = "tenant-teste"


def test_ranking_saude_contas_resolve_vendedor_em_lote(db_session):
    """Fase 7B, hardening — regressão do fix de N+1: o vendedor de cada
    conta precisa continuar resolvido certo (ou None, quando não tem
    vendedor) depois de trocar a busca por-conta pra busca em lote."""
    db_session.add(Tenant(id=TENANT_ID, razao_social="Empresa Teste"))
    admin = Usuario(tenant_id=TENANT_ID, nome="Admin", email="admin@teste.com.br", papel="admin", ativo=True)
    vendedor_1 = Usuario(tenant_id=TENANT_ID, nome="Vendedor Um", email="v1@teste.com.br", papel="user", ativo=True)
    vendedor_2 = Usuario(tenant_id=TENANT_ID, nome="Vendedor Dois", email="v2@teste.com.br", papel="user", ativo=True)
    db_session.add_all([admin, vendedor_1, vendedor_2])
    db_session.flush()

    conta_sem_vendedor = Conta(tenant_id=TENANT_ID, nome="Conta Sem Vendedor", status="prospectada")
    conta_v1 = Conta(
        tenant_id=TENANT_ID, nome="Conta V1", status="prospectada", vendedor_usuario_id=vendedor_1.id
    )
    conta_v2 = Conta(
        tenant_id=TENANT_ID, nome="Conta V2", status="prospectada", vendedor_usuario_id=vendedor_2.id
    )
    db_session.add_all([conta_sem_vendedor, conta_v1, conta_v2])
    db_session.commit()

    ranking = saude_conta_service.ranking_saude_contas(db_session, admin)

    por_nome = {item["nome"]: item for item in ranking}
    assert por_nome["Conta Sem Vendedor"]["vendedor_nome"] is None
    assert por_nome["Conta V1"]["vendedor_nome"] == "Vendedor Um"
    assert por_nome["Conta V2"]["vendedor_nome"] == "Vendedor Dois"
