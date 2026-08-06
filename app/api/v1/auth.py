from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_payment_provider, get_usuario_atual
from app.core.rate_limit import limitar_por_ip
from app.models.licenca import Licenca
from app.models.usuario import Usuario
from app.providers.payment.base import PaymentProvider
from app.schemas.auth import (
    LicencaStatusResponseSchema,
    LoginGoogleRequestSchema,
    LoginRequestSchema,
    RegistrarRequestSchema,
    RegistrarVitrineRequestSchema,
    TokenResponseSchema,
    UsuarioSchema,
)
from app.services import auth_service, pagamento_licenca_service, tenant_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _resposta_token(usuario: Usuario, db: Session, checkout_url: str | None = None) -> TokenResponseSchema:
    licenca = db.query(Licenca).filter_by(tenant_id=usuario.tenant_id).one_or_none()
    return TokenResponseSchema(
        access_token=auth_service.gerar_token(usuario),
        usuario=UsuarioSchema.model_validate(usuario),
        tem_licenca_ativa=licenca is not None and licenca.status == "ativa",
        checkout_url=checkout_url,
    )


@router.post("/login", response_model=TokenResponseSchema, dependencies=[Depends(limitar_por_ip())])
def login(dados: LoginRequestSchema, db: Session = Depends(get_db)) -> TokenResponseSchema:
    usuario = auth_service.autenticar_senha(db, dados.email, dados.senha)
    return _resposta_token(usuario, db)


@router.post("/google", response_model=TokenResponseSchema, dependencies=[Depends(limitar_por_ip())])
def login_google(dados: LoginGoogleRequestSchema, db: Session = Depends(get_db)) -> TokenResponseSchema:
    usuario = auth_service.autenticar_google(db, dados.id_token)
    return _resposta_token(usuario, db)


@router.post(
    "/registrar", response_model=TokenResponseSchema, status_code=201, dependencies=[Depends(limitar_por_ip())]
)
def registrar(dados: RegistrarRequestSchema, db: Session = Depends(get_db)) -> TokenResponseSchema:
    usuario = auth_service.registrar_com_convite(
        db, dados.codigo_convite, dados.nome, dados.email, dados.senha, dados.aceite_termos
    )
    return _resposta_token(usuario, db)


@router.post(
    "/registrar-vitrine",
    response_model=TokenResponseSchema,
    status_code=201,
    dependencies=[Depends(limitar_por_ip())],
)
def registrar_vitrine(
    dados: RegistrarVitrineRequestSchema,
    db: Session = Depends(get_db),
    payment_provider: PaymentProvider = Depends(get_payment_provider),
) -> TokenResponseSchema:
    """Aceite público de convite-vitrine — cria o tenant novo, já loga, e
    abre a cobrança do plano escolhido (Onda H + raio-X de produção). Sem
    autenticação prévia, como `/registrar`. A licença nasce
    `pendente_pagamento`; o frontend redireciona pro `checkout_url`
    devolvido aqui."""
    usuario, checkout_url = tenant_service.criar_tenant_vitrine(
        db,
        dados.codigo_convite,
        dados.razao_social,
        dados.nome_admin,
        dados.email_admin,
        dados.senha_admin,
        dados.aceite_termos,
        dados.plano_id,
        payment_provider,
        dados.cnpj,
    )
    return _resposta_token(usuario, db, checkout_url)


@router.get("/eu", response_model=UsuarioSchema)
def eu(usuario: Usuario = Depends(get_usuario_atual)) -> UsuarioSchema:
    return usuario


@router.get("/licenca-status", response_model=LicencaStatusResponseSchema)
def licenca_status(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> LicencaStatusResponseSchema:
    """Usado pela tela de retorno do checkout (Mercado Pago) pra saber
    quando parar de esperar o webhook confirmar o pagamento."""
    return LicencaStatusResponseSchema(status=pagamento_licenca_service.status_licenca(db, usuario.tenant_id))
