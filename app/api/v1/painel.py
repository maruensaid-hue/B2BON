from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.schemas.painel import (
    ConfiguracaoPainelSchema,
    ConfiguracaoPainelUpsertSchema,
    IndicadoresResponseSchema,
    MetricaNorteSchema,
)
from app.services import panel_service

router = APIRouter(prefix="/painel", tags=["painel"])


@router.get("/metrica-norte", response_model=MetricaNorteSchema)
def metrica_norte(
    mes: str | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> MetricaNorteSchema:
    """Métrica-norte com evolução mensal — fonte exclusiva no CRM (E8-H1)."""
    return MetricaNorteSchema(**panel_service.metrica_norte(db, tenant_id, mes))


@router.get("/configuracao-meta", response_model=ConfiguracaoPainelSchema)
def obter_meta(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoPainelSchema:
    config = panel_service.obter_meta(db, tenant_id)
    return ConfiguracaoPainelSchema(meta_mensal_reunioes=config.meta_mensal_reunioes if config else None)


@router.put("/configuracao-meta", response_model=ConfiguracaoPainelSchema)
def definir_meta(
    dados: ConfiguracaoPainelUpsertSchema,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoPainelSchema:
    config = panel_service.definir_meta(db, tenant_id, dados.meta_mensal_reunioes)
    return ConfiguracaoPainelSchema(meta_mensal_reunioes=config.meta_mensal_reunioes)


@router.get("/indicadores", response_model=IndicadoresResponseSchema)
def indicadores(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> IndicadoresResponseSchema:
    """Indicadores de energia e atrito por canal, período configurável (E8-H2)."""
    inicio, fim = panel_service.periodo_padrao(data_inicio, data_fim)
    energia = panel_service.indicadores_energia(db, tenant_id, data_inicio, data_fim)
    atrito = panel_service.indicadores_atrito(db, tenant_id, data_inicio, data_fim)
    return IndicadoresResponseSchema(
        periodo_inicio=inicio.isoformat(), periodo_fim=fim.isoformat(), energia=energia, atrito=atrito
    )


@router.get("/indicadores/export.csv")
def exportar_indicadores_csv(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> Response:
    conteudo = panel_service.exportar_csv(db, tenant_id, data_inicio, data_fim)
    return Response(content=conteudo, media_type="text/csv")
