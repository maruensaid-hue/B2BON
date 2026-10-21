"""Pesquisa de decisores governada por créditos de enriquecimento (prévia → confirmação → execução) e o painel do tenant.

Nenhum parâmetro do cliente altera plano, saldo, limite, orçamento ou estado: o backend recalcula e revalida tudo na confirmação. Não existe
rota que aceite "o ICP inteiro": só uma lista explícita de empresas (`conta_ids`), cada uma conferida contra o tenant e o escopo do vendedor.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import (
    exigir_escopo_conta_usuario,
    get_contact_enrichment_provider,
    get_db,
    get_graph_client,
    get_sessao_factory,
    get_usuario_atual,
    limitar_ia_por_tenant,
)
from app.contexts.enriquecimento.contract import Solicitante, execucao, painel, pesquisa
from app.graph.client import Neo4jClient
from app.models.usuario import Usuario
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.services.errors import NaoAutorizado

router = APIRouter(prefix="/pesquisas-decisores", tags=["pesquisas-decisores"])
logger = logging.getLogger("b2bon.enriquecimento")


class PreviaRequest(BaseModel):
    """Seleção EXPLÍCITA de empresas. Campos extras (ex.: `icp_id`, `todas`) são recusados: o universo do ICP nunca dispara pesquisa."""

    model_config = ConfigDict(extra="forbid")

    conta_ids: list[int] = Field(min_length=1, max_length=500)
    decisores_por_empresa: int | None = Field(default=None, ge=1, le=1000)


class ConfirmarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selecao_hash: str = Field(min_length=16, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=100)


def _solicitante(usuario: Usuario) -> Solicitante:
    return Solicitante(id=usuario.id, papel=usuario.papel, tenant_id=usuario.tenant_id)


def _detalhe(db: Session, pesq) -> dict:
    return painel.serializar_pesquisa(db, pesq, com_itens=True, com_transicoes=True)


def _executar_em_segundo_plano(sessao_factory, db_da_requisicao: Session, tenant_id: str, pesquisa_id: str, provider: ContactEnrichmentProvider,
                               graph: Neo4jClient, ator_id: str) -> None:
    """Roda depois da resposta, para a requisição não ficar presa nas chamadas ao provedor (uma por empresa). Sessão própria em produção; nos testes
    a fábrica é `None` e a sessão da requisição serve. Qualquer falha fica registrada por empresa (estados `enviado`/`ambiguo`) — nunca se repete
    sozinha; `retomar` continua só o que ainda está pendente."""
    sessao = sessao_factory() if sessao_factory is not None else db_da_requisicao
    try:
        execucao.executar(sessao, tenant_id=tenant_id, pesquisa_id=pesquisa_id, provider=provider, graph=graph, ator_id=ator_id)
    except Exception:  # noqa: BLE001 — tarefa sem chamador para propagar
        logger.exception("ENRIQUECIMENTO_TAREFA_FALHOU pesquisa=%s", pesquisa_id)
        sessao.rollback()
    finally:
        if sessao_factory is not None:
            sessao.close()


@router.post("/previa", status_code=201, dependencies=[Depends(limitar_ia_por_tenant(30, 300))])
def criar_previa(dados: PreviaRequest, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db),
                 provider: ContactEnrichmentProvider = Depends(get_contact_enrichment_provider)) -> dict:
    """Etapa de revisão: devolve a estimativa (máximo de créditos, saldo, limites, ajustes sugeridos, incertezas). Não reserva nem consulta nada."""
    for conta_id in dict.fromkeys(dados.conta_ids):
        exigir_escopo_conta_usuario(conta_id, usuario.tenant_id, usuario, db)  # vendedor só seleciona o que enxerga
    criada = pesquisa.estimar(db, solicitante=_solicitante(usuario), conta_ids=dados.conta_ids,
                              decisores_por_empresa=dados.decisores_por_empresa, provider=provider)
    return _detalhe(db, criada)


@router.get("")
def listar(estado: str | None = None, limite: int = 50, offset: int = 0, usuario: Usuario = Depends(get_usuario_atual),
           db: Session = Depends(get_db)) -> list[dict]:
    return painel.listar_pesquisas(db, _solicitante(usuario), estado, limite, offset)


@router.get("/painel")
def painel_do_tenant(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return painel.painel_tenant(db, _solicitante(usuario))


@router.get("/movimentacoes")
def movimentacoes(tipo: str | None = None, pesquisa_id: str | None = None, desde: datetime | None = None, ate: datetime | None = None,
                  limite: int = 100, offset: int = 0, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[dict]:
    """Extrato do razão do próprio tenant. Só gestores (admin/super_admin): mostra o consumo de todos os usuários."""
    if not _solicitante(usuario).gestor:
        raise NaoAutorizado("O extrato de créditos é restrito a administradores.")
    return painel.listar_movimentacoes(db, usuario.tenant_id, tipo=tipo, pesquisa_id=pesquisa_id, desde=desde, ate=ate, limite=limite, offset=offset)


@router.get("/{pesquisa_id}")
def detalhar(pesquisa_id: str, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return _detalhe(db, pesquisa.obter(db, usuario.tenant_id, _solicitante(usuario), pesquisa_id))


@router.post("/{pesquisa_id}/confirmar", dependencies=[Depends(limitar_ia_por_tenant(30, 300))])
def confirmar(pesquisa_id: str, dados: ConfirmarRequest, tarefas: BackgroundTasks, usuario: Usuario = Depends(get_usuario_atual),
              db: Session = Depends(get_db), provider: ContactEnrichmentProvider = Depends(get_contact_enrichment_provider),
              graph: Neo4jClient = Depends(get_graph_client), sessao_factory=Depends(get_sessao_factory)) -> dict:
    """Confirma exatamente a prévia revista: o servidor revalida tudo e reserva os créditos; a consulta ao provedor roda em segundo plano
    (acompanhe por `GET /pesquisas-decisores/{id}`)."""
    solicitante = _solicitante(usuario)
    reservada = pesquisa.confirmar(db, solicitante=solicitante, pesquisa_id=pesquisa_id, selecao_hash=dados.selecao_hash,
                                   idempotency_key=dados.idempotency_key, provider=provider)
    if reservada.estado == "reservada":
        tarefas.add_task(_executar_em_segundo_plano, sessao_factory, db, usuario.tenant_id, pesquisa_id, provider, graph, str(usuario.id))
    return _detalhe(db, reservada)


@router.post("/{pesquisa_id}/retomar", dependencies=[Depends(limitar_ia_por_tenant(30, 300))])
def retomar(pesquisa_id: str, tarefas: BackgroundTasks, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db),
            provider: ContactEnrichmentProvider = Depends(get_contact_enrichment_provider), graph: Neo4jClient = Depends(get_graph_client),
            sessao_factory=Depends(get_sessao_factory)) -> dict:
    """Continua uma pesquisa interrompida em segundo plano (só as empresas ainda pendentes; nada já enviado é repetido)."""
    atual = pesquisa.obter(db, usuario.tenant_id, _solicitante(usuario), pesquisa_id)
    if atual.estado in ("reservada", "enviada"):
        tarefas.add_task(_executar_em_segundo_plano, sessao_factory, db, usuario.tenant_id, pesquisa_id, provider, graph, str(usuario.id))
    return _detalhe(db, atual)


@router.post("/{pesquisa_id}/cancelar")
def cancelar(pesquisa_id: str, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return _detalhe(db, execucao.cancelar(db, solicitante=_solicitante(usuario), pesquisa_id=pesquisa_id))
