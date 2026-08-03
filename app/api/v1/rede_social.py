from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.schemas.rede_social import (
    AtualizarPerfilRequestSchema,
    ConexaoEmpresaSchema,
    EmpresaDiretorioSchema,
    EnviarMensagemRequestSchema,
    MensagemRedeSocialSchema,
    PerfilEmpresaSchema,
    ResponderConexaoRequestSchema,
    SolicitarConexaoRequestSchema,
)
from app.services import rede_social_service

router = APIRouter(prefix="/rede-social", tags=["rede-social"])


@router.get("/perfil", response_model=PerfilEmpresaSchema)
def obter_perfil(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> PerfilEmpresaSchema:
    return rede_social_service.obter_perfil(db, tenant_id)


@router.put("/perfil", response_model=PerfilEmpresaSchema)
def atualizar_perfil(
    dados: AtualizarPerfilRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> PerfilEmpresaSchema:
    return rede_social_service.atualizar_perfil(
        db, tenant_id, ator_id, dados.nome_exibicao, dados.descricao, dados.setor, dados.site
    )


@router.get("/empresas", response_model=list[EmpresaDiretorioSchema])
def listar_empresas(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[EmpresaDiretorioSchema]:
    """Diretório/vitrine — descobrir empresas para conectar (Onda C)."""
    return rede_social_service.listar_empresas(db, tenant_id)


@router.post("/conexoes", response_model=ConexaoEmpresaSchema, status_code=201)
def solicitar_conexao(
    dados: SolicitarConexaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConexaoEmpresaSchema:
    return rede_social_service.solicitar_conexao(db, tenant_id, ator_id, dados.tenant_id_destino)


@router.get("/conexoes", response_model=list[ConexaoEmpresaSchema])
def listar_conexoes(
    status: str | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[ConexaoEmpresaSchema]:
    return rede_social_service.listar_conexoes(db, tenant_id, status)


@router.put("/conexoes/{conexao_id}", response_model=ConexaoEmpresaSchema)
def responder_conexao(
    conexao_id: int,
    dados: ResponderConexaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConexaoEmpresaSchema:
    return rede_social_service.responder_conexao(db, tenant_id, ator_id, conexao_id, dados.aceitar)


@router.post("/mensagens", response_model=MensagemRedeSocialSchema, status_code=201)
def enviar_mensagem(
    dados: EnviarMensagemRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> MensagemRedeSocialSchema:
    """Só entre empresas já conectadas (Onda C)."""
    return rede_social_service.enviar_mensagem(db, tenant_id, ator_id, dados.tenant_id_destinatario, dados.texto)


@router.get("/mensagens/{com_tenant_id}", response_model=list[MensagemRedeSocialSchema])
def listar_conversa(
    com_tenant_id: str,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[MensagemRedeSocialSchema]:
    return rede_social_service.listar_conversa(db, tenant_id, com_tenant_id)


@router.post("/mensagens/{mensagem_id}/marcar-lida", response_model=MensagemRedeSocialSchema)
def marcar_lida(
    mensagem_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> MensagemRedeSocialSchema:
    return rede_social_service.marcar_lida(db, tenant_id, mensagem_id)
