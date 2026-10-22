from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db
from app.contexts.enriquecimento.contract import matriz, pacotes
from app.schemas.plano import AtualizarPlanoRequestSchema, CriarPlanoRequestSchema, PlanoSchema
from app.services import tenant_service

router = APIRouter(prefix="/planos", tags=["planos"])


@router.get("", response_model=list[PlanoSchema])
def listar_planos(apenas_self_service: bool = False, db: Session = Depends(get_db)) -> list[PlanoSchema]:
    """Lista pública dos planos — não exige autenticação (Onda A).
    `apenas_self_service=True` (usado pela tela de cadastro público)
    esconde planos como "Teste", só concedíveis por convite gratuito."""
    return tenant_service.listar_planos(db, apenas_self_service)


@router.get("/enriquecimento")
def franquias_de_enriquecimento(db: Session = Depends(get_db)) -> dict:
    """Pública (site): franquias mensais de enriquecimento por plano, limites por pesquisa e por empresa e pacotes adicionais. Só dado de plataforma
    (a matriz aprovada e o catálogo vigente), nunca de cliente nem de custo/margem. Vale só para a pesquisa de decisores por provedor pago; ICP e
    análise de sites têm regras próprias."""
    return {
        "planos": matriz.vitrine(), **pacotes.catalogo(db),
        "observacoes": [
            "A franquia mensal é o máximo de créditos por pesquisa e vence no fim do mês: o que não for usado não acumula.",
            "O limite de decisores vale por empresa, em cada pesquisa.",
            "Créditos adicionais ficam em saldo separado e valem por 30 dias a partir da confirmação do pagamento. Enquanto houver crédito de pacote válido, o limite de créditos por pesquisa passa a ser o do pacote comprado; ao acabar o crédito ou vencer o prazo, volta ao do plano.",
            "Não há limite de tamanho do ICP: os limites valem só para a pesquisa de decisores no provedor pago.",
        ],
    }


@router.post("", response_model=PlanoSchema, status_code=201, dependencies=[Depends(exigir_papel("super_admin"))])
def criar_plano(dados: CriarPlanoRequestSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> PlanoSchema:
    corpo = dados.model_dump()
    motivo = corpo.pop("motivo")
    return tenant_service.criar_plano(db, corpo, ator_id=ator_id, motivo=motivo)


@router.put("/{plano_id}", response_model=PlanoSchema, dependencies=[Depends(exigir_papel("super_admin"))])
def atualizar_plano(plano_id: int, dados: AtualizarPlanoRequestSchema, ator_id: str | None = Depends(get_ator_id),
                    db: Session = Depends(get_db)) -> PlanoSchema:
    # D-072: campos que o cliente não mandou não voltam ao padrão (um Admin antigo não apaga a oferta Government)
    corpo = dados.model_dump(exclude_unset=True)
    motivo = corpo.pop("motivo", None)
    return tenant_service.atualizar_plano(db, plano_id, corpo, ator_id=ator_id, motivo=motivo)
