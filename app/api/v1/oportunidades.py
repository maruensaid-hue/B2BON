"""Opportunity Intelligence (Fase 6, master prompt §20-§26).

O card é determinístico (não chama IA, não custa crédito). Só a extração
de necessidades usa IA, pelo AI Gateway, e o resultado nasce como
sugestão até um humano confirmar.
"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_llm_provider, get_tenant_id, limitar_ia_por_tenant
from app.contexts.opportunity import contract as oportunidade
from app.llm.base import LLMProvider
from app.models.necessidade_oportunidade import CATEGORIAS

router = APIRouter(prefix="/inteligencia/oportunidades", tags=["opportunity-intelligence"])

Categoria = Literal[CATEGORIAS]  # type: ignore[valid-type]


class ExtrairNecessidadesSchema(BaseModel):
    reuniao_id: int | None = None
    atividade_id: int | None = None


class NovaNecessidadeSchema(BaseModel):
    categoria: Categoria
    descricao: str = Field(min_length=3, max_length=300)
    citacao: str | None = Field(default=None, max_length=1000)


class RevisaoNecessidadeSchema(BaseModel):
    status: Literal["confirmada", "descartada"]
    descricao: str | None = Field(default=None, min_length=3, max_length=300)
    categoria: Categoria | None = None


def _usuario(ator_id: str | None) -> int | None:
    return int(ator_id) if ator_id and ator_id.isdigit() else None


@router.get("/{negocio_id}/card")
def card(negocio_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return oportunidade.card_oportunidade(db, tenant_id, negocio_id)


@router.get("/{negocio_id}/necessidades")
def listar_necessidades(
    negocio_id: int,
    incluir_descartadas: bool = False,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        oportunidade.necessidades.como_dict(n)
        for n in oportunidade.necessidades.listar(db, tenant_id, negocio_id, incluir_descartadas)
    ]


@router.post("/{negocio_id}/necessidades", status_code=201)
def registrar_necessidade(
    negocio_id: int,
    dados: NovaNecessidadeSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> dict:
    return oportunidade.necessidades.registrar_manual(
        db, tenant_id, _usuario(ator_id), negocio_id, dados.categoria, dados.descricao, dados.citacao
    )


@router.post("/{negocio_id}/necessidades/extrair", dependencies=[Depends(limitar_ia_por_tenant())])
def extrair_necessidades(
    negocio_id: int,
    dados: ExtrairNecessidadesSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    llm: LLMProvider = Depends(get_llm_provider),
    db: Session = Depends(get_db),
) -> dict:
    return oportunidade.necessidades.extrair(
        db, llm, tenant_id, _usuario(ator_id), negocio_id, dados.reuniao_id, dados.atividade_id
    )


@router.patch("/necessidades/{necessidade_id}")
def revisar_necessidade(
    necessidade_id: int,
    dados: RevisaoNecessidadeSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> dict:
    return oportunidade.necessidades.revisar(
        db, tenant_id, _usuario(ator_id), necessidade_id, dados.status, dados.descricao, dados.categoria
    )


@router.get("/contas/{conta_id}/white-space")
def white_space(conta_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return oportunidade.white_space_da_conta(db, tenant_id, conta_id)
