"""Parcelas a receber de um negócio ganho, lançadas pelo vendedor (fonte do quadro de inadimplentes do MAP). Mesmo escopo das outras rotas do negócio:
vendedor (`user`) só mexe nos negócios dele (404 nos demais); admin/super_admin no tenant inteiro."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.api.v1.crm import exigir_escopo_negocio
from app.schemas.inadimplencia import AtualizarParcelaRequestSchema, CriarParcelaRequestSchema
from app.services import inadimplencia_service

router = APIRouter(prefix="/crm", tags=["crm-parcelas"])
_ESCOPO = [Depends(exigir_escopo_negocio)]


def _saida(parcela) -> dict:
    return {"id": parcela.id, "numero": parcela.numero, "valor": parcela.valor, "vencimento": parcela.vencimento,
            "pago_em": parcela.pago_em, "observacao": parcela.observacao}


@router.get("/negocios/{negocio_id}/parcelas", dependencies=_ESCOPO)
def listar(negocio_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return inadimplencia_service.listar_parcelas(db, tenant_id, negocio_id)


@router.post("/negocios/{negocio_id}/parcelas", status_code=201, dependencies=_ESCOPO)
def criar(negocio_id: int, dados: CriarParcelaRequestSchema, tenant_id: str = Depends(get_tenant_id),
          ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return _saida(inadimplencia_service.criar_parcela(db, tenant_id, negocio_id, ator_id, valor=dados.valor,
                                                      vencimento=dados.vencimento, observacao=dados.observacao))


@router.put("/negocios/{negocio_id}/parcelas/{parcela_id}", dependencies=_ESCOPO)
def atualizar(negocio_id: int, parcela_id: int, dados: AtualizarParcelaRequestSchema, tenant_id: str = Depends(get_tenant_id),
              ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return _saida(inadimplencia_service.atualizar_parcela(db, tenant_id, negocio_id, parcela_id, ator_id, valor=dados.valor,
                                                          vencimento=dados.vencimento, pago_em=dados.pago_em, observacao=dados.observacao))


@router.delete("/negocios/{negocio_id}/parcelas/{parcela_id}", status_code=204, dependencies=_ESCOPO)
def excluir(negocio_id: int, parcela_id: int, tenant_id: str = Depends(get_tenant_id), ator_id: str | None = Depends(get_ator_id),
            db: Session = Depends(get_db)) -> Response:
    inadimplencia_service.excluir_parcela(db, tenant_id, negocio_id, parcela_id, ator_id)
    return Response(status_code=204)
