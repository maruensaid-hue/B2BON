"""Descoberta de empresas por busca de mapa: estimar (quantas buscas e quanto da franquia do mês), depois executar com as buscas
confirmadas. Só administradores. O cliente nunca vê custo nem a fonte usada."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_descoberta_provider, get_sessao_factory, get_tenant_id, get_usuario_atual
from app.contexts.enriquecimento import contract as enriquecimento
from app.contexts.predator import contract as predator
from app.core.config import settings
from app.models.usuario import Usuario
from app.providers.descoberta_empresas.base import DescobertaEmpresasProvider

router = APIRouter(prefix="/descoberta", tags=["descoberta"])
logger = logging.getLogger(__name__)


def franquia_do_tenant(db: Session, tenant_id: str, papel: str | None) -> tuple[int, bool]:
    """(limite, vale_para_a_vida_toda) da descoberta: a MESMA régua da pesquisa de decisores (matriz aprovada pelo PO), com 1 busca no
    lugar de 1 crédito. Plano com franquia mensal (Teste/Starter 30, Professional 60, Business 120, Corporate 180; Enterprise pela condição
    do tenant) usa esse número por mês de Brasília; POC, o limite de pesquisas na vida da empresa; super admin, sem limite (mesma chave da
    pesquisa de decisores). Sem configuração aprovada vale `DESCOBERTA_BUSCA_FRANQUIA_MENSAL` (0 = sem limite): a descoberta não fica
    bloqueada como a pesquisa paga de decisores."""
    if papel == "super_admin" and settings.enriquecimento_super_admin_sem_limites:
        return 0, False
    config, motivo = enriquecimento.config.config_vigente(db, tenant_id)
    if config is not None and config.franquia_creditos:
        return int(config.franquia_creditos), False
    if motivo == "poc_sem_autorizacao":
        poc = enriquecimento.matriz_dados.PLANOS["POC"]["config"]
        return int(poc["limite_pesquisas_periodo"]), True
    return settings.descoberta_busca_franquia_mensal, False


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
    usuario: Usuario = Depends(get_usuario_atual),
) -> dict:
    """Quantas buscas o pedido usa e quanto da franquia já foi usado, sem chamar a fonte. `configurado: false` = indisponível."""
    franquia, vida_toda = franquia_do_tenant(db, tenant_id, usuario.papel)
    estimativa = predator.descoberta.estimar(
        provedor, dados.termos, dados.cidades, settings.descoberta_busca_max_buscas_por_execucao, db, tenant_id, franquia, vida_toda,
    )
    return {
        "buscas": estimativa.buscas, "configurado": estimativa.configurado, "usadas_no_mes": estimativa.usadas_no_mes,
        "franquia_mensal": estimativa.franquia_mensal, "franquia_vida_toda": estimativa.franquia_vida_toda,
    }


def _executar_em_segundo_plano(sessao_factory, tenant_id, ator_id, provedor, dados: ExecutarDescobertaSchema, franquia: tuple[int, bool]) -> None:
    """Fonte lenta: roda depois da resposta, com sessão própria (mesmo padrão do disparo imediato de campanha)."""
    sessao = sessao_factory()
    try:
        predator.descoberta.executar(
            sessao, tenant_id, ator_id, provedor, dados.termos, dados.cidades, dados.buscas_confirmadas,
            settings.descoberta_busca_max_buscas_por_execucao, icp_id=dados.icp_id,
            franquia_mensal=franquia[0], franquia_vida_toda=franquia[1],
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
    usuario: Usuario = Depends(get_usuario_atual),
) -> dict:
    """Roda as buscas (termos x cidades) e cria as contas novas com os sinais da busca. Recusa sem as buscas confirmadas iguais às estimadas.
    Com fonte lenta, confere o pedido na hora e roda em segundo plano: as contas aparecem na lista em alguns minutos."""
    franquia = franquia_do_tenant(db, tenant_id, usuario.papel)
    if provedor.lenta and sessao_factory is not None:  # nos testes a fábrica é `None`: roda direto
        estimativa = predator.descoberta.conferir_pedido(
            db, tenant_id, provedor, dados.termos, dados.cidades, dados.buscas_confirmadas,
            settings.descoberta_busca_max_buscas_por_execucao, *franquia,
        )
        tarefas.add_task(_executar_em_segundo_plano, sessao_factory, tenant_id, ator_id, provedor, dados, franquia)
        return {"em_segundo_plano": True, "buscas": estimativa.buscas}
    return predator.descoberta.executar(
        db, tenant_id, ator_id, provedor, dados.termos, dados.cidades, dados.buscas_confirmadas,
        settings.descoberta_busca_max_buscas_por_execucao, icp_id=dados.icp_id,
        franquia_mensal=franquia[0], franquia_vida_toda=franquia[1],
    )
