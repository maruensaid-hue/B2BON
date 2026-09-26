"""Phase J3 (OI-023, D-071): B2B ON Bid Intelligence com 10 usuários incluídos por tenant.

- O limite vem do entitlement (plano + usuários adicionais da licença), não de número no código.
- Usuários adicionais são suportados (`licenca.usuarios_adicionais`); o preço deles segue PENDING_DEFINITION.
- O pool de AI Credits é do tenant e não cresce com o número de usuários.
- Papel externo (fornecedor convidado) não ocupa assento interno.
"""

import pytest

from app.contexts.finops import contract as finops
from app.contexts.shared.entitlements import PAPEIS_EXTERNOS, Entitlements
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.usuario import Usuario
from app.providers.plan_limits.nucleo import NucleoPlanLimitsProvider
from app.services import auth_service
from app.services.errors import RegraNegocioViolada

TENANT = "tenant-teste"


@pytest.fixture()
def bid_intelligence(client, db_session):
    plano = Plano(nome="Bid Intelligence", franquia_contas_mes=0, max_usuarios=10, preco_mensal=1490.0, modulos_contratados=["bids"],
                  categoria="modulo", tipo_preco="FIXED")
    db_session.add(plano)
    db_session.flush()
    licenca = db_session.query(Licenca).filter_by(tenant_id=TENANT).one()
    licenca.plano_id = plano.id
    db_session.commit()
    return licenca


def _usuarios(db_session, quantidade: int, papel: str = "user") -> None:
    inicio = db_session.query(Usuario).count()
    for i in range(quantidade):
        db_session.add(Usuario(tenant_id=TENANT, nome=f"U{inicio + i}", email=f"u{inicio + i}-{papel}@teste.com", papel=papel, ativo=True))
    db_session.commit()


def test_limite_de_10_vem_do_entitlement_e_adicionais_somam(db_session, bid_intelligence):
    direitos = Entitlements(NucleoPlanLimitsProvider(db_session), TENANT)
    assert direitos.limite_usuarios() == 10 == auth_service.limite_de_usuarios(db_session, TENANT)
    _usuarios(db_session, 10 - auth_service.contar_assentos(db_session, TENANT))
    with pytest.raises(RegraNegocioViolada, match=r"atingido \(10\)"):
        auth_service._verificar_limite_de_usuarios(db_session, TENANT)

    bid_intelligence.usuarios_adicionais = 2  # additional_user_quantity (contratado por fora; preço em definição)
    db_session.commit()
    assert direitos.limite_usuarios() == 12
    auth_service._verificar_limite_de_usuarios(db_session, TENANT)  # há assento
    _usuarios(db_session, 2)
    with pytest.raises(RegraNegocioViolada, match=r"atingido \(12\)"):
        auth_service._verificar_limite_de_usuarios(db_session, TENANT)


def test_papel_externo_nao_ocupa_assento(db_session, bid_intelligence):
    assert "supplier_guest" in PAPEIS_EXTERNOS
    antes = auth_service.contar_assentos(db_session, TENANT)
    _usuarios(db_session, 3, papel="supplier_guest")
    assert auth_service.contar_assentos(db_session, TENANT) == antes


def test_pool_de_ai_credits_nao_multiplica_por_usuario(db_session, bid_intelligence):
    assert finops.carteira.franquia_do_tenant(db_session, TENANT)[0] == 25_000
    bid_intelligence.usuarios_adicionais = 5
    _usuarios(db_session, 8)
    assert finops.carteira.franquia_do_tenant(db_session, TENANT)[0] == 25_000


def test_catalogo_e_assinatura_mostram_10_incluidos_sem_preco_de_adicional(client, db_session, bid_intelligence):
    linhas = {linha["id"]: linha for linha in client.get("/api/v1/catalogo").json()["linhas"]}
    bids = linhas["bid_intelligence"]
    assert [(p["usuarios_incluidos"], p["preco_mensal"], p["ai_credits_mensais"]) for p in bids["planos"]] == [(10, 1490.0, 25_000)]
    assert bids["pendencias"] == ["preco_usuario_adicional"]
    assert "usuario_adicional" not in str({k: v for k, v in bids.items() if k != "pendencias"})  # nenhum valor inventado
    bid_intelligence.usuarios_adicionais = 3
    db_session.commit()
    assert client.get("/api/v1/assinatura").json()["uso"]["usuarios"]["limite"] == 13
