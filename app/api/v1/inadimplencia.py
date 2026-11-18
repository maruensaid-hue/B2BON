"""Quadro "Clientes inadimplentes" e anotações da daily do gestor, no MAP (pedido do PO em 18/11/2026).

O quadro de parcelas exige o módulo MAP (é o MAP vendido ao cliente); o de licenças é da gestão da B2B ON e da rede (distribuidor, revenda, representante) e
não depende do módulo. Quem vê o quê está em `inadimplencia_service`.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import exigir_modulo, get_db, get_usuario_atual
from app.models.usuario import Usuario
from app.schemas.inadimplencia import ConcluirNotaDailyRequestSchema, CriarNotaDailyRequestSchema
from app.services import inadimplencia_service, nota_daily_service

router = APIRouter(prefix="/map", tags=["map-inadimplencia"])


@router.get("/inadimplencia/acesso")
def acesso(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return inadimplencia_service.acesso(db, usuario)


@router.get("/inadimplencia/parcelas", dependencies=[Depends(exigir_modulo("map"))])
def quadro_parcelas(
    tenant_id_selecionado: str | None = None,
    vendedor_usuario_id: int | None = None,
    representante_id: int | None = None,
    revenda_id: str | None = None,
    distribuidor_id: str | None = None,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> dict:
    return inadimplencia_service.quadro_parcelas(
        db, usuario, tenant_id_selecionado=tenant_id_selecionado, vendedor_usuario_id=vendedor_usuario_id,
        representante_id=representante_id, revenda_id=revenda_id, distribuidor_id=distribuidor_id,
    )


@router.get("/inadimplencia/licencas")
def quadro_licencas(
    tenant_id_selecionado: str | None = None,
    representante_id: int | None = None,
    revenda_id: str | None = None,
    distribuidor_id: str | None = None,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> dict:
    return inadimplencia_service.quadro_licencas(
        db, usuario, tenant_id_selecionado=tenant_id_selecionado, representante_id=representante_id,
        revenda_id=revenda_id, distribuidor_id=distribuidor_id,
    )


@router.get("/notas-daily")
def listar_notas(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return nota_daily_service.listar(db, usuario)


@router.post("/notas-daily", status_code=201)
def criar_nota(dados: CriarNotaDailyRequestSchema, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return nota_daily_service.criar(db, usuario, dados.texto, dados.exibir_em)


@router.put("/notas-daily/{nota_id}/concluir")
def concluir_nota(nota_id: int, dados: ConcluirNotaDailyRequestSchema, usuario: Usuario = Depends(get_usuario_atual),
                  db: Session = Depends(get_db)) -> dict:
    return nota_daily_service.concluir(db, usuario, nota_id, dados.concluida)


@router.delete("/notas-daily/{nota_id}", status_code=204)
def excluir_nota(nota_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> Response:
    nota_daily_service.excluir(db, usuario, nota_id)
    return Response(status_code=204)
