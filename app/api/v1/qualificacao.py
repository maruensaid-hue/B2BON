from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.core.config import settings
from app.models.configuracao_qualificacao import ConfiguracaoQualificacao
from app.schemas.qualificacao import ConfiguracaoQualificacaoSchema, ConfiguracaoQualificacaoUpsertSchema

router = APIRouter(prefix="/qualificacao", tags=["qualificacao"])


@router.get("/configuracao", response_model=ConfiguracaoQualificacaoSchema)
def obter_configuracao(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoQualificacaoSchema:
    config = db.query(ConfiguracaoQualificacao).filter_by(tenant_id=tenant_id).one_or_none()
    if config is None:
        return ConfiguracaoQualificacaoSchema(
            id=0, tenant_id=tenant_id, limiar_padrao=settings.limiar_qualificacao_padrao
        )
    return config


@router.put("/configuracao", response_model=ConfiguracaoQualificacaoSchema)
def salvar_configuracao(
    dados: ConfiguracaoQualificacaoUpsertSchema,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoQualificacaoSchema:
    """Limiar de qualificação configurável por assinante (E5-H2)."""
    config = db.query(ConfiguracaoQualificacao).filter_by(tenant_id=tenant_id).one_or_none()
    if config is None:
        config = ConfiguracaoQualificacao(tenant_id=tenant_id, limiar_padrao=dados.limiar_padrao)
        db.add(config)
    else:
        config.limiar_padrao = dados.limiar_padrao
    db.commit()
    db.refresh(config)
    return config
