from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.models.configuracao_envio import ConfiguracaoEnvio
from app.schemas.configuracao_envio import ConfiguracaoEnvioSchema, ConfiguracaoEnvioUpsertSchema
from app.services import auditoria_service

router = APIRouter(prefix="/configuracao-envio", tags=["configuracao-envio"])


@router.get("", response_model=ConfiguracaoEnvioSchema | None)
def obter_configuracao_envio(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoEnvioSchema | None:
    return db.query(ConfiguracaoEnvio).filter_by(tenant_id=tenant_id).one_or_none()


@router.put("", response_model=ConfiguracaoEnvioSchema)
def salvar_configuracao_envio(
    dados: ConfiguracaoEnvioUpsertSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoEnvioSchema:
    """Assinatura e identificação do remetente configuráveis por assinante (E3-H3)."""
    config = db.query(ConfiguracaoEnvio).filter_by(tenant_id=tenant_id).one_or_none()
    if config is None:
        config = ConfiguracaoEnvio(tenant_id=tenant_id, **dados.model_dump())
        db.add(config)
    else:
        for campo, valor in dados.model_dump().items():
            setattr(config, campo, valor)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "configuracao_envio_salva", "configuracao_envio", config.id, ator_id, {}
    )
    db.commit()
    db.refresh(config)
    return config
