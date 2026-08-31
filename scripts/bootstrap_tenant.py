"""Cria o primeiro tenant + super_admin (Onda A — Núcleo).

Uso: python scripts/bootstrap_tenant.py

Só existe como script porque criar o *primeiro* tenant é um problema de
"ovo e galinha" — não há ainda nenhum super_admin autenticado que possa
chamar `POST /admin/tenants`. Tenants seguintes (quando a B2B ON tiver
mais assinantes além da CyberFort) nascem por ali.
"""

import getpass
import sys

import app.models  # noqa: F401 — registra as tabelas em Base.metadata
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.plano import Plano
from app.services import tenant_service
from app.services.errors import ErroServico

# Limite semanal de enriquecimento (site/contatos) — raio-X 2026-08-28:
# vale pra todo plano, não só o "Teste" (cortesia). Proporcional à
# franquia mensal de cada plano, na mesma razão validada no Teste
# (50/semana pra 200 de franquia/mês = 25%).
PLANOS_PADRAO = [
    {
        "nome": "POC", "franquia_contas_mes": 50, "max_usuarios": 3, "preco_mensal": 0.0,
        "limite_enriquecimento_site_semanal": 15, "limite_enriquecimento_contatos_semanal": 15,
    },
    {
        "nome": "Teste", "franquia_contas_mes": 200, "max_usuarios": 10, "preco_mensal": 0.0,
        "visivel_self_service": False,
        "limite_enriquecimento_site_semanal": 50, "limite_enriquecimento_contatos_semanal": 50,
    },
    {
        "nome": "Starter", "franquia_contas_mes": 200, "max_usuarios": 10, "preco_mensal": 490.0,
        "limite_enriquecimento_site_semanal": 50, "limite_enriquecimento_contatos_semanal": 50,
    },
    {
        "nome": "Professional", "franquia_contas_mes": 800, "max_usuarios": 25, "preco_mensal": 990.0,
        "limite_enriquecimento_site_semanal": 200, "limite_enriquecimento_contatos_semanal": 200,
    },
    {
        "nome": "Enterprise", "franquia_contas_mes": 5000, "max_usuarios": 999, "preco_mensal": 2490.0,
        "limite_enriquecimento_site_semanal": 1250, "limite_enriquecimento_contatos_semanal": 1250,
    },
]


def _garantir_planos_padrao(db) -> None:
    if db.query(Plano).count() > 0:
        return
    for dados in PLANOS_PADRAO:
        db.add(Plano(**dados))
    db.commit()
    print(f"Planos padrão criados: {', '.join(p['nome'] for p in PLANOS_PADRAO)}")


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _garantir_planos_padrao(db)
        planos = db.query(Plano).order_by(Plano.id).all()

        print("\nPlanos disponíveis:")
        for plano in planos:
            print(f"  [{plano.id}] {plano.nome} — franquia {plano.franquia_contas_mes} contas/mês")

        tenant_id = input("\nIdentificador do tenant (slug, ex.: cyberfort): ").strip()
        razao_social = input("Razão social: ").strip()
        cnpj = input("CNPJ (opcional): ").strip() or None
        plano_id = int(input("ID do plano: ").strip())
        nome_admin = input("Nome do primeiro super_admin: ").strip()
        email_admin = input("E-mail do primeiro super_admin: ").strip()
        senha_admin = getpass.getpass("Senha do primeiro super_admin: ")

        usuario = tenant_service.criar_tenant_inicial(
            db, tenant_id, razao_social, plano_id, nome_admin, email_admin, senha_admin, cnpj
        )
        print(f"\n✓ Tenant '{tenant_id}' criado. Super_admin '{usuario.email}' pronto para login em POST /api/v1/auth/login.")
    except ErroServico as erro:
        print(f"\nErro: {erro}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
