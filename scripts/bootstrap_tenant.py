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
#
# Recursos de escala (raio-X 2026-09-09) — gancho de upgrade além de
# volume: teste A/B, auto-aprovação, webhook de relatório, API de
# parceiros e hierarquia de sub-tenants só fazem sentido pra quem já
# opera em escala, nunca pro "core" do produto (CRM, cadência básica,
# WhatsApp/e-mail continuam iguais em todo plano). "Teste" espelha
# Starter de propósito, igual já faz pra franquia/usuários.
POC_STARTER_TESTE = {
    "permite_ab_teste_cadencia": False, "permite_auto_aprovacao": False,
    "permite_webhook_relatorio": False, "permite_api_parceiros": False, "permite_subtenants": False,
    "permite_registro_oportunidade": False,
    "retencao_dias_relatorio": 30, "retencao_dias_auditoria": 90,
}
# Contratação avulsa por módulo (raio-X 2026-09-24) — todo plano de
# suíte libera os três módulos.
_TODOS_MODULOS = ["map", "predator", "crm"]
PLANOS_PADRAO = [
    {
        "nome": "POC", "franquia_contas_mes": 50, "max_usuarios": 3, "preco_mensal": 0.0,
        "limite_enriquecimento_site_semanal": 15, "limite_enriquecimento_contatos_semanal": 15,
        "limite_cadencias_mes": 5, "limite_campanhas_mes": 2,
        "modulos_contratados": _TODOS_MODULOS, "categoria": "suite",
        **POC_STARTER_TESTE,
    },
    {
        # max_usuarios=None (sem limite) — raio-X 2026-09-22, admin
        # gratuito precisa convidar quantos vendedores quiser; espelha
        # Starter só na franquia/enriquecimento/cadência/campanha, não em
        # usuários (essa restrição específica foi removida de propósito).
        "nome": "Teste", "franquia_contas_mes": 200, "max_usuarios": None, "preco_mensal": 0.0,
        "visivel_self_service": False,
        "limite_enriquecimento_site_semanal": 50, "limite_enriquecimento_contatos_semanal": 50,
        "limite_cadencias_mes": 20, "limite_campanhas_mes": 10,
        "modulos_contratados": _TODOS_MODULOS, "categoria": "suite",
        **POC_STARTER_TESTE,
    },
    {
        # Preço/limite de usuários alinhados com a tabela comercial
        # validada com o usuário (raio-X 2026-09-22) — ver migração
        # `a1b2c3d4e5f6` pra quem já tinha "Starter" seedado com os
        # valores provisórios antigos (R$490/10 usuários).
        "nome": "Starter", "franquia_contas_mes": 200, "max_usuarios": 5, "preco_mensal": 924.50,
        "limite_enriquecimento_site_semanal": 50, "limite_enriquecimento_contatos_semanal": 50,
        "limite_cadencias_mes": 20, "limite_campanhas_mes": 10,
        "modulos_contratados": _TODOS_MODULOS, "categoria": "suite",
        **POC_STARTER_TESTE,
    },
    {
        "nome": "Professional", "franquia_contas_mes": 800, "max_usuarios": 10, "preco_mensal": 1664.10,
        "limite_enriquecimento_site_semanal": 200, "limite_enriquecimento_contatos_semanal": 200,
        "limite_cadencias_mes": 80, "limite_campanhas_mes": 40,
        "modulos_contratados": _TODOS_MODULOS, "categoria": "suite",
        "permite_ab_teste_cadencia": True, "permite_auto_aprovacao": False,
        "permite_webhook_relatorio": True, "permite_api_parceiros": True, "permite_subtenants": True,
        "permite_registro_oportunidade": True,
        "retencao_dias_relatorio": 90, "retencao_dias_auditoria": 365,
    },
    {
        "nome": "Enterprise", "franquia_contas_mes": 5000, "max_usuarios": 20, "preco_mensal": 2958.40,
        "limite_enriquecimento_site_semanal": 1250, "limite_enriquecimento_contatos_semanal": 1250,
        "limite_cadencias_mes": 500, "limite_campanhas_mes": 250,
        "modulos_contratados": _TODOS_MODULOS, "categoria": "suite",
        "permite_ab_teste_cadencia": True, "permite_auto_aprovacao": True,
        "permite_webhook_relatorio": True, "permite_api_parceiros": True, "permite_subtenants": True,
        "permite_registro_oportunidade": True,
        "retencao_dias_relatorio": None, "retencao_dias_auditoria": None,
    },
]

# Planos avulsos por módulo (raio-X 2026-09-24) — mesmos valores já
# publicados em `frontend/src/pages/Planos.tsx`. Franquia/enriquecimento/
# cadência/campanha só fazem sentido pra quem tem PREDATOR; nos planos
# MAP/CRM avulsos ficam em 0 (irrelevante, a rota já está bloqueada pelo
# módulo mesmo assim). "On Demand" por módulo não vira `Plano` — mesmo
# padrão da suíte, é "fale com o comercial".
_PLANO_AVULSO_BASE = {
    "franquia_contas_mes": 0,
    "limite_enriquecimento_site_semanal": 0, "limite_enriquecimento_contatos_semanal": 0,
    "limite_cadencias_mes": 0, "limite_campanhas_mes": 0,
    "categoria": "modulo",
    "retencao_dias_relatorio": 30, "retencao_dias_auditoria": 90,
    **POC_STARTER_TESTE,
}
for _nome, _preco, _max_usuarios, _modulo in [
    ("MAP Starter", 149.50, 5, "map"),
    ("MAP Professional", 269.10, 10, "map"),
    ("MAP Enterprise", 478.40, 20, "map"),
    ("PREDATOR Starter", 475.50, 5, "predator"),
    ("PREDATOR Professional", 855.90, 10, "predator"),
    ("PREDATOR Enterprise", 1521.60, 20, "predator"),
    ("CRM Starter", 299.50, 5, "crm"),
    ("CRM Professional", 539.10, 10, "crm"),
    ("CRM Enterprise", 958.40, 20, "crm"),
]:
    PLANOS_PADRAO.append({
        "nome": _nome, "max_usuarios": _max_usuarios, "preco_mensal": _preco,
        "modulos_contratados": [_modulo],
        **_PLANO_AVULSO_BASE,
    })


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
