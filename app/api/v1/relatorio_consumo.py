from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_db
from app.models.usuario import Usuario
from app.services import relatorio_consumo_service

router = APIRouter(prefix="/relatorio-consumo-creditos", tags=["relatorio-consumo-creditos"])


@router.get("")
def relatorio(inicio: date | None = None, fim: date | None = None, tenant_id: str | None = None,
              usuario: Usuario = Depends(exigir_papel("admin", "super_admin")), db: Session = Depends(get_db)) -> dict:
    """Consumo de créditos de IA e de enriquecimento por empresa e por usuário, com a franquia e os limites do perfil contratado, as aquisições de
    créditos adicionais (quantidade, data e valor) e o consumo adicional. Super admin vê todas as empresas; admin, a própria e a subárvore. Padrão: mês corrente."""
    return relatorio_consumo_service.gerar(db, usuario, inicio, fim, tenant_id)


@router.get("/csv")
def relatorio_csv(inicio: date | None = None, fim: date | None = None, tenant_id: str | None = None,
                  usuario: Usuario = Depends(exigir_papel("admin", "super_admin")), db: Session = Depends(get_db)) -> Response:
    """Mesmo relatório em planilha (CSV com `;`, UTF-8 com BOM, abre direto no Excel)."""
    dados = relatorio_consumo_service.gerar(db, usuario, inicio, fim, tenant_id)
    return Response(relatorio_consumo_service.para_csv(dados), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="consumo-de-creditos.csv"'})
