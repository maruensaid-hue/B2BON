from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_usuario_atual
from app.models.usuario import Usuario
from app.schemas.auth import (
    LoginGoogleRequestSchema,
    LoginRequestSchema,
    RegistrarRequestSchema,
    TokenResponseSchema,
    UsuarioSchema,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _resposta_token(usuario: Usuario) -> TokenResponseSchema:
    return TokenResponseSchema(
        access_token=auth_service.gerar_token(usuario), usuario=UsuarioSchema.model_validate(usuario)
    )


@router.post("/login", response_model=TokenResponseSchema)
def login(dados: LoginRequestSchema, db: Session = Depends(get_db)) -> TokenResponseSchema:
    usuario = auth_service.autenticar_senha(db, dados.email, dados.senha)
    return _resposta_token(usuario)


@router.post("/google", response_model=TokenResponseSchema)
def login_google(dados: LoginGoogleRequestSchema, db: Session = Depends(get_db)) -> TokenResponseSchema:
    usuario = auth_service.autenticar_google(db, dados.id_token)
    return _resposta_token(usuario)


@router.post("/registrar", response_model=TokenResponseSchema, status_code=201)
def registrar(dados: RegistrarRequestSchema, db: Session = Depends(get_db)) -> TokenResponseSchema:
    usuario = auth_service.registrar_com_convite(db, dados.codigo_convite, dados.nome, dados.email, dados.senha)
    return _resposta_token(usuario)


@router.get("/eu", response_model=UsuarioSchema)
def eu(usuario: Usuario = Depends(get_usuario_atual)) -> UsuarioSchema:
    return usuario
