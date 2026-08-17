"""Semeia o tenant/usuário/licença fixos usados pelos testes E2E do
Playwright. Roda uma vez no `globalSetup`, contra o banco apontado por
`DATABASE_URL` (isolado do banco de desenvolvimento — ver
playwright.config.ts). Idempotente: pode rodar de novo sem duplicar nada
nem quebrar em cima de dados já semeados de uma execução anterior."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import app.models  # noqa: E402 — registra todas as tabelas em Base.metadata
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.licenca import Licenca  # noqa: E402
from app.models.plano import Plano  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.services.auth_service import hash_senha  # noqa: E402

TENANT_ID = "e2e-playwright"
EMAIL = "e2e@teste.com.br"
SENHA = "SenhaE2E123!"


def main() -> None:
    # DB dedicado do E2E (arquivo próprio, ver playwright.config.ts) —
    # ainda não tem tabela nenhuma na primeira execução.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(Tenant).filter_by(id=TENANT_ID).one_or_none() is None:
            db.add(Tenant(id=TENANT_ID, razao_social="E2E Playwright Ltda"))
            db.flush()

        plano = db.query(Plano).filter_by(nome="E2E Teste").one_or_none()
        if plano is None:
            plano = Plano(nome="E2E Teste", franquia_contas_mes=1000, max_usuarios=10, preco_mensal=0.0)
            db.add(plano)
            db.flush()

        if db.query(Licenca).filter_by(tenant_id=TENANT_ID).one_or_none() is None:
            db.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="ativa"))

        usuario = db.query(Usuario).filter_by(email=EMAIL).one_or_none()
        if usuario is None:
            db.add(
                Usuario(
                    tenant_id=TENANT_ID,
                    nome="E2E Playwright",
                    email=EMAIL,
                    senha_hash=hash_senha(SENHA),
                    papel="super_admin",
                    ativo=True,
                )
            )
        else:
            # Garante que a senha bate mesmo se o usuário já existia de
            # uma execução anterior com outro valor.
            usuario.senha_hash = hash_senha(SENHA)
            usuario.ativo = True

        db.commit()
        print(f"Seed OK - tenant={TENANT_ID} email={EMAIL}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
