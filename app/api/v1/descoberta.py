"""Descoberta de empresas por busca de mapa (paga por busca): estimar, depois executar com o custo confirmado. Só administradores."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_descoberta_provider, get_tenant_id
from app.contexts.predator import contract as predator
from app.core.config import settings
from app.providers.descoberta_empresas.base import DescobertaEmpresasProvider

router = APIRouter(prefix="/descoberta", tags=["descoberta"])


class PedidoDescobertaSchema(BaseModel):
    termos: list[str] = Field(min_length=1, max_length=20)
    cidades: list[str] = Field(min_length=1, max_length=20)
    icp_id: int | None = None


class ExecutarDescobertaSchema(PedidoDescobertaSchema):
    custo_confirmado_usd: float


@router.post("/estimativa", dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def estimar(dados: PedidoDescobertaSchema, provedor: DescobertaEmpresasProvider = Depends(get_descoberta_provider)) -> dict:
    """Quantas buscas e quanto custam, sem chamar a fonte. `configurado: false` = a descoberta não está disponível nesta instalação."""
    estimativa = predator.descoberta.estimar(provedor, dados.termos, dados.cidades, settings.descoberta_busca_max_buscas_por_execucao)
    return {"buscas": estimativa.buscas, "custo_usd": estimativa.custo_usd, "configurado": estimativa.configurado}


@router.post("/executar", dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def executar(
    dados: ExecutarDescobertaSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    provedor: DescobertaEmpresasProvider = Depends(get_descoberta_provider),
) -> dict:
    """Roda as buscas (termos x cidades) e cria as contas novas com os sinais da busca. Recusa sem o custo confirmado igual ao estimado."""
    return predator.descoberta.executar(
        db, tenant_id, ator_id, provedor, dados.termos, dados.cidades, dados.custo_confirmado_usd,
        settings.descoberta_busca_max_buscas_por_execucao, icp_id=dados.icp_id,
    )
