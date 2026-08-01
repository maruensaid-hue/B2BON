from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.models.configuracao_notificacao import ConfiguracaoNotificacao
from app.models.notificacao_vendedor import NotificacaoVendedor
from app.schemas.notificacao import (
    ConfiguracaoNotificacaoSchema,
    ConfiguracaoNotificacaoUpsertSchema,
    NotificacaoVendedorSchema,
)
from app.services import notificacao_service

router = APIRouter(tags=["notificacoes"])


def _com_sla(notificacao: NotificacaoVendedor) -> NotificacaoVendedorSchema:
    sla = (
        (notificacao.primeiro_contato_em - notificacao.criado_em).total_seconds()
        if notificacao.primeiro_contato_em
        else None
    )
    return NotificacaoVendedorSchema.model_validate(notificacao).model_copy(update={"sla_segundos": sla})


@router.put("/notificacoes/configuracao", response_model=ConfiguracaoNotificacaoSchema)
def salvar_configuracao_notificacao(
    dados: ConfiguracaoNotificacaoUpsertSchema,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoNotificacaoSchema:
    config = db.query(ConfiguracaoNotificacao).filter_by(tenant_id=tenant_id).one_or_none()
    if config is None:
        config = ConfiguracaoNotificacao(tenant_id=tenant_id, **dados.model_dump())
        db.add(config)
    else:
        config.vendedor_id = dados.vendedor_id
        config.vendedor_telefone = dados.vendedor_telefone
    db.commit()
    db.refresh(config)
    return config


@router.get("/notificacoes", response_model=list[NotificacaoVendedorSchema])
def listar_notificacoes(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[NotificacaoVendedorSchema]:
    """Notificação em tempo real ao vendedor (E5-H3)."""
    notificacoes = db.query(NotificacaoVendedor).filter_by(tenant_id=tenant_id).all()
    return [_com_sla(notificacao) for notificacao in notificacoes]


@router.post("/notificacoes/{notificacao_id}/confirmar-contato", response_model=NotificacaoVendedorSchema)
def confirmar_contato(
    notificacao_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> NotificacaoVendedorSchema:
    """SLA visível: tempo entre qualificação e primeiro contato humano (E5-H3)."""
    notificacao = notificacao_service.confirmar_contato(db, tenant_id, notificacao_id)
    return _com_sla(notificacao)
