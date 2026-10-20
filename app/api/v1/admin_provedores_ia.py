"""Estado dos provedores de IA (somente leitura, super_admin): o que está implementado, testado, habilitado e aprovado."""

from fastapi import APIRouter, Depends

from app.api.deps import exigir_papel
from app.llm import fallback

router = APIRouter(prefix="/admin/provedores-ia", tags=["admin"], dependencies=[Depends(exigir_papel("super_admin"))])


@router.get("")
def listar_provedores() -> list[dict]:
    """Nunca devolve credenciais: só presença/ausência, bloqueios e a documentação oficial consultada."""
    return fallback.status_provedores()
