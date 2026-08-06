from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_usuario_atual
from app.core.rate_limit import limitar_por_ip
from app.models.licenca import Licenca
from app.models.usuario import Usuario
from app.schemas.auth import (
    LoginGoogleRequestSchema,
    LoginRequestSchema,
    RegistrarRequestSchema,
    RegistrarVitrineRequestSchema,
    TokenResponseSchema,
    UsuarioSchema,
)
from app.services import auth_service, tenant_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _resposta_token(usuario: Usuario, db: Session) -> TokenResponseSchema:
    licenca = db.query(Licenca).filter_by(tenant_id=usuario.tenant_id).one_or_none()
    return TokenResponseSchema(
        access_token=auth_service.gerar_token(usuario),
        usuario=UsuarioSchema.model_validate(usuario),
        tem_licenca_ativa=licenca is not None and licenca.status == "ativa",
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
def registrar_vitrine(dados: RegistrarVitrineRequestSchema, db: Session = Depends(get_db)) -> TokenResponseSchema:
    """Aceite público de convite-vitrine — cria o tenant novo e já loga
    (Onda H). Sem autenticação prévia, como `/registrar`."""
    usuario = tenant_service.criar_tenant_vitrine(
        db,
        dados.codigo_convite,
        dados.razao_social,
        dados.nome_admin,
        dados.email_admin,
        dados.senha_admin,
        dados.aceite_termos,
        dados.cnpj,
    )
    return _resposta_token(usuario, db)


@router.get("/eu", response_model=UsuarioSchema)
def eu(usuario: Usuario = Depends(get_usuario_atual)) -> UsuarioSchema:
    return usuario
