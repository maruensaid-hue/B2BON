from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_email_provider_do_tenant, get_tenant_id, get_usuario_atual
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider
from app.schemas.email_direto import (
    ArquivarConversaRequestSchema,
    ArquivarConversaResponseSchema,
    AtualizarConfiguracaoEmailAgenteRequestSchema,
    ConfiguracaoEmailAgenteSchema,
    EmailDiretoCreateSchema,
    EmailDiretoSchema,
    EmailRecebidoSchema,
    PendenteArquivamentoSchema,
)
from app.services import email_direto_service

router = APIRouter(prefix="/email-direto", tags=["email-direto"])


@router.post("", response_model=EmailDiretoSchema)
def enviar(
    dados: EmailDiretoCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    email_provider: EmailProvider = Depends(get_email_provider_do_tenant),
    db: Session = Depends(get_db),
) -> EmailDiretoSchema:
    """Webmail (raio-X 2026-09-24) — e-mail direto do vendedor pra um
    decisor do CRM, envio síncrono sem fila de aprovação."""
    item = email_direto_service.enviar(
        db, tenant_id, usuario, dados.decisor_id, dados.assunto, dados.corpo, email_provider
    )
    return EmailDiretoSchema(**item)


@router.get("", response_model=list[EmailDiretoSchema])
def listar_enviados(
    conta_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[EmailDiretoSchema]:
    itens = email_direto_service.listar_enviados(db, tenant_id, usuario, conta_id)
    return [EmailDiretoSchema(**item) for item in itens]


@router.get("/recebidos", response_model=list[EmailRecebidoSchema])
def listar_recebidos(
    conta_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[EmailRecebidoSchema]:
    itens = email_direto_service.listar_recebidos(db, tenant_id, usuario, conta_id)
    return [EmailRecebidoSchema(**item) for item in itens]


@router.get("/pendentes-arquivamento", response_model=list[PendenteArquivamentoSchema])
def listar_pendentes_arquivamento(
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[PendenteArquivamentoSchema]:
    itens = email_direto_service.listar_pendentes_arquivamento(db, tenant_id, usuario)
    return [PendenteArquivamentoSchema(**item) for item in itens]


@router.post("/arquivar", response_model=ArquivarConversaResponseSchema)
def arquivar_conversa(
    dados: ArquivarConversaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> ArquivarConversaResponseSchema:
    return ArquivarConversaResponseSchema(
        **email_direto_service.arquivar_conversa(db, tenant_id, usuario, dados.decisor_id)
    )


@router.get("/configuracao", response_model=ConfiguracaoEmailAgenteSchema)
def obter_configuracao(usuario: Usuario = Depends(get_usuario_atual)) -> ConfiguracaoEmailAgenteSchema:
    return ConfiguracaoEmailAgenteSchema(**email_direto_service.obter_configuracao(usuario))


@router.put("/configuracao", response_model=ConfiguracaoEmailAgenteSchema)
def atualizar_configuracao(
    dados: AtualizarConfiguracaoEmailAgenteRequestSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> ConfiguracaoEmailAgenteSchema:
    return ConfiguracaoEmailAgenteSchema(
        **email_direto_service.atualizar_configuracao(db, usuario, dados.email_nome_exibicao, dados.email_assinatura)
    )
