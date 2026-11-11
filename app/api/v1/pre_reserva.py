from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_tenant_id
from app.core.rate_limit import limitar_por_ip
from app.schemas.pre_reserva import (
    AlterarStatusPreReservaSchema,
    ConfiguracaoPreReservaSchema,
    CriarPreReservaRequestSchema,
    InfoPublicaPreReservaSchema,
    PreReservaCriadaSchema,
    PreReservaSchema,
)
from app.services import pre_reserva_service

router = APIRouter(prefix="/pre-reserva", tags=["pre-reserva"])

_SO_GESTOR = [Depends(exigir_papel("super_admin", "admin"))]


@router.get("/config", response_model=ConfiguracaoPreReservaSchema | None, dependencies=_SO_GESTOR)
def obter_config(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)):
    config = pre_reserva_service.obter_config(db, tenant_id)
    return ConfiguracaoPreReservaSchema.model_validate(config) if config is not None else None


@router.put("/config", response_model=ConfiguracaoPreReservaSchema, dependencies=_SO_GESTOR)
def salvar_config(
    dados: ConfiguracaoPreReservaSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoPreReservaSchema:
    config = pre_reserva_service.salvar_config(db, tenant_id, ator_id, dados.model_dump())
    return ConfiguracaoPreReservaSchema.model_validate(config)


@router.get("/reservas", response_model=list[PreReservaSchema], dependencies=_SO_GESTOR)
def listar(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[PreReservaSchema]:
    return [PreReservaSchema.model_validate(linha) for linha in pre_reserva_service.listar(db, tenant_id)]


@router.post("/reservas/{pre_reserva_id}/status", status_code=204, dependencies=_SO_GESTOR)
def alterar_status(
    pre_reserva_id: int,
    dados: AlterarStatusPreReservaSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> Response:
    pre_reserva_service.alterar_status(db, tenant_id, ator_id, pre_reserva_id, dados.status)
    return Response(status_code=204)


@router.get("/{codigo}/info", response_model=InfoPublicaPreReservaSchema)
def obter_info_publica(codigo: str, db: Session = Depends(get_db)) -> InfoPublicaPreReservaSchema:
    """Pública, sem autenticação: a página do formulário mostra a marca, as condições e só as datas que ainda estão livres."""
    return InfoPublicaPreReservaSchema(**pre_reserva_service.info_publica(db, codigo))


@router.post(
    "/{codigo}",
    status_code=201,
    response_model=PreReservaCriadaSchema,
    # Mesmo limite apertado da captura de lead: link público, potencialmente divulgado em massa.
    dependencies=[Depends(limitar_por_ip(max_tentativas=3, janela_segundos=600))],
)
def criar_pre_reserva(codigo: str, dados: CriarPreReservaRequestSchema, db: Session = Depends(get_db)) -> PreReservaCriadaSchema:
    pre_reserva = pre_reserva_service.criar_pre_reserva_publica(db, codigo, dados)
    config = pre_reserva_service.obter_config(db, pre_reserva.tenant_id)
    return PreReservaCriadaSchema(
        data_evento=pre_reserva.data_evento,
        expira_em=pre_reserva.expira_em,
        valor=pre_reserva.valor,
        valor_sinal=pre_reserva.valor * config.percentual_sinal / 100,
    )
