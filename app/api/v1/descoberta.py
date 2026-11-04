"""Descoberta de empresas por busca de mapa: estimar (quantas buscas e quanto da franquia do mês), depois executar com as buscas
confirmadas. Só administradores. O cliente nunca vê custo nem a fonte usada."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_descoberta_provider, get_sessao_factory, get_tenant_id
from app.contexts.predator import contract as predator
from app.core.config import settings
from app.providers.descoberta_empresas.base import DescobertaEmpresasProvider

router = APIRouter(prefix="/descoberta", tags=["descoberta"])
logger = logging.getLogger(__name__)


class PedidoDescobertaSchema(BaseModel):
    termos: list[str] = Field(min_length=1, max_length=20)
    cidades: list[str] = Field(min_length=1, max_length=20)
    icp_id: int | None = None


class ExecutarDescobertaSchema(PedidoDescobertaSchema):
    buscas_confirmadas: int


@router.post("/estimativa", dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def estimar(
    dados: PedidoDescobertaSchema,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    provedor: DescobertaEmpresasProvider = Depends(get_descoberta_provider),
) -> dict:
    """Quantas buscas o pedido usa e quanto da franquia do mês já foi usado, sem chamar a fonte. `configurado: false` = indisponível."""
    estimativa = predator.descoberta.estimar(
        provedor, dados.termos, dados.cidades, settings.descoberta_busca_max_buscas_por_execucao, db, tenant_id,
        settings.descoberta_busca_franquia_mensal,
    )
    return {
        "buscas": estimativa.buscas, "configurado": estimativa.configurado,
        "usadas_no_mes": estimativa.usadas_no_mes, "franquia_mensal": estimativa.franquia_mensal,
    }


def _executar_em_segundo_plano(sessao_factory, tenant_id, ator_id, provedor, dados: ExecutarDescobertaSchema) -> None:
    """Fonte lenta: roda depois da resposta, com sessão própria (mesmo padrão do disparo imediato de campanha)."""
    sessao = sessao_factory()
    try:
        predator.descoberta.executar(
            sessao, tenant_id, ator_id, provedor, dados.termos, dados.cidades, dados.buscas_confirmadas,
            settings.descoberta_busca_max_buscas_por_execucao, icp_id=dados.icp_id,
            franquia_mensal=settings.descoberta_busca_franquia_mensal,
        )
    except Exception:  # noqa: BLE001 — tarefa sem chamador para propagar
        logger.exception("DESCOBERTA_SEGUNDO_PLANO_FALHOU tenant=%s", tenant_id)
        sessao.rollback()
    finally:
        sessao.close()


@router.post("/executar", dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def executar(
    dados: ExecutarDescobertaSchema,
    tarefas: BackgroundTasks,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    provedor: DescobertaEmpresasProvider = Depends(get_descoberta_provider),
    sessao_factory=Depends(get_sessao_factory),
) -> dict:
    """Roda as buscas (termos x cidades) e cria as contas novas com os sinais da busca. Recusa sem as buscas confirmadas iguais às estimadas.
    Com fonte lenta, confere o pedido na hora e roda em segundo plano: as contas aparecem na lista em alguns minutos."""
    if provedor.lenta and sessao_factory is not None:  # nos testes a fábrica é `None`: roda direto
        estimativa = predator.descoberta.conferir_pedido(
            db, tenant_id, provedor, dados.termos, dados.cidades, dados.buscas_confirmadas,
            settings.descoberta_busca_max_buscas_por_execucao, settings.descoberta_busca_franquia_mensal,
        )
        tarefas.add_task(_executar_em_segundo_plano, sessao_factory, tenant_id, ator_id, provedor, dados)
        return {"em_segundo_plano": True, "buscas": estimativa.buscas}
    return predator.descoberta.executar(
        db, tenant_id, ator_id, provedor, dados.termos, dados.cidades, dados.buscas_confirmadas,
        settings.descoberta_busca_max_buscas_por_execucao, icp_id=dados.icp_id,
        franquia_mensal=settings.descoberta_busca_franquia_mensal,
    )
